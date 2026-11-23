import psycopg
import pytest

from fds_worker import handlers as H
from fds_worker.main import run

from .conftest import make_project, steps


def job_status(conn, job):
    return conn.execute("select status from jobs where id=%s", (job,)).fetchone()["status"]


def test_create_pipeline_has_all_steps(conn):
    _, job = make_project(conn)
    s = steps(conn, job)
    assert len(s) == 17
    assert all(r["status"] == "pending" for r in s.values())
    assert job_status(conn, job) == "queued"


def test_no_handlers_means_nothing_runs(db_url, conn):
    _, job = make_project(conn)
    assert run(db_url, max_minutes=1, dry_run=False, once=False) == 0
    assert all(r["status"] == "pending" for r in steps(conn, job).values())


def test_full_flow_with_gates(db_url, conn):
    pid, job = make_project(conn)

    # 1) Araştırma adımları çalışır, kullanıcı onayında durur.
    run(db_url, 1, dry_run=True, once=False)
    s = steps(conn, job)
    assert [k for k, r in s.items() if r["status"] == "done"] == [
        "research_collect", "research_verify", "research_report"]
    assert s["research_review"]["status"] == "waiting_input"
    assert job_status(conn, job) == "waiting_input"

    # 2) Onay → senaryolar yazılır, senaryo onayında durur.
    assert conn.execute("select resolve_input_step(%s) as ok", (s["research_review"]["id"],)).fetchone()["ok"]
    run(db_url, 1, dry_run=True, once=False)
    s = steps(conn, job)
    assert s["script_shorts"]["status"] == "done" and s["script_review"]["status"] == "waiting_input"
    assert s["visual_plan"]["status"] == "pending"                  # görsel plan artık seslendirmeden sonra

    # 3) Senaryo onayı → ElevenLabs metinleri, seslendirme beklemede durur.
    conn.execute("select resolve_input_step(%s)", (s["script_review"]["id"],))
    run(db_url, 1, dry_run=True, once=False)
    s = steps(conn, job)
    assert s["voiceover_texts"]["status"] == "done"
    assert s["voiceover_wait"]["status"] == "waiting_input"

    # 3) Ses yokken render'ı elle başlatmaya çalışmak veritabanı tarafından reddedilir.
    with pytest.raises(psycopg.errors.RaiseException, match="RENDER_BLOCKED_NO_VOICEOVER"):
        conn.execute("update job_steps set status='running' where id=%s", (s["render_doc"]["id"],))

    # 4) Yalnızca belgesel sesi yüklenince bekleme sürer; iki ses yüklenince serbest kalır.
    conn.execute("insert into voiceovers (project_id, kind, storage_key, filename, bytes) "
                 "values (%s,'doc','projects/pompei/voiceover/doc.mp3','doc.mp3', 1000)", (pid,))
    assert steps(conn, job)["voiceover_wait"]["status"] == "waiting_input"
    conn.execute("insert into voiceovers (project_id, kind, storage_key, filename, bytes) "
                 "values (%s,'shorts','projects/pompei/voiceover/shorts.mp3','shorts.mp3', 500)", (pid,))
    assert steps(conn, job)["voiceover_wait"]["status"] == "done"

    # 5) Analiz + görsel plan/eşleştirme → görsel onayında durur.
    run(db_url, 1, dry_run=True, once=False)
    s = steps(conn, job)
    assert s["asset_match"]["status"] == "done" and s["visual_review"]["status"] == "waiting_input"

    # 6) Görsel onayı → altyazı + render + teslim.
    conn.execute("select resolve_input_step(%s)", (s["visual_review"]["id"],))
    run(db_url, 1, dry_run=True, once=False)
    s = steps(conn, job)
    assert all(r["status"] == "done" for r in s.values()), {k: r["status"] for k, r in s.items()}
    assert job_status(conn, job) == "done"
    assert conn.execute("select status from projects where id=%s", (pid,)).fetchone()["status"] == "done"


def _advance_to_render(db_url, conn, pid, job):
    run(db_url, 1, dry_run=True, once=False)
    conn.execute("select resolve_input_step(%s)", (steps(conn, job)["research_review"]["id"],))
    run(db_url, 1, dry_run=True, once=False)
    conn.execute("select resolve_input_step(%s)", (steps(conn, job)["script_review"]["id"],))
    run(db_url, 1, dry_run=True, once=False)
    for kind in ("doc", "shorts"):
        conn.execute("insert into voiceovers (project_id, kind, storage_key, filename, bytes, status) "
                     "values (%s,%s,'k','f', 10, 'analyzed')", (pid, kind))
    run(db_url, 1, dry_run=True, once=False)
    conn.execute("select resolve_input_step(%s)", (steps(conn, job)["visual_review"]["id"],))


def test_storage_guard_blocks_render(db_url, conn):
    pid, job = make_project(conn)
    _advance_to_render(db_url, conn, pid, job)
    conn.execute("update settings set value=to_jsonb(5::bigint) where key='storage_guard_bytes'")
    run(db_url, 1, dry_run=True, once=False)
    s = steps(conn, job)
    assert s["subtitles"]["status"] == "done"
    assert s["render_doc"]["status"] == "pending"
    assert "RENDER_BLOCKED_STORAGE" in s["render_doc"]["error"]
    # Uyarı bir kez kaydedilir, her denemede tekrar yazılmaz.
    run(db_url, 1, dry_run=True, once=False)
    n = conn.execute("select count(*) n from error_logs where message like 'RENDER_BLOCKED_STORAGE%%'").fetchone()["n"]
    assert n == 1


def test_retry_then_fail_then_manual_retry(db_url, conn, monkeypatch):
    _, job = make_project(conn)

    def boom(_conn, _step):
        raise RuntimeError("geçici ağ hatası")

    monkeypatch.setattr(H, "registry", lambda dry: {"research_collect": boom})
    import fds_worker.main as M
    monkeypatch.setattr(M, "registry", H.registry)

    for _ in range(3):
        run(db_url, 1, dry_run=True, once=True)
    s = steps(conn, job)["research_collect"]
    assert s["status"] == "failed" and s["attempts"] == 3
    assert job_status(conn, job) == "failed"
    assert conn.execute("select count(*) n from error_logs").fetchone()["n"] == 3

    assert conn.execute("select retry_step(%s) ok", (s["id"],)).fetchone()["ok"]
    s = steps(conn, job)["research_collect"]
    assert s["status"] == "pending" and s["attempts"] == 0
    assert job_status(conn, job) == "queued"


def test_stale_running_step_is_requeued(conn):
    _, job = make_project(conn)
    step = conn.execute("select * from claim_next_step('dead-worker', null)").fetchone()
    assert step["step_key"] == "research_collect"
    conn.execute("update job_steps set heartbeat_at = now() - interval '1 hour' where id=%s", (step["id"],))
    assert conn.execute("select requeue_stale_steps() n").fetchone()["n"] == 1
    assert steps(conn, job)["research_collect"]["status"] == "pending"
    # Ölü işçi artık adımı tamamlayamaz.
    assert not conn.execute("select complete_step(%s,'dead-worker') ok", (step["id"],)).fetchone()["ok"]


def test_cancelled_job_is_not_claimed(conn):
    _, job = make_project(conn)
    conn.execute("update jobs set status='cancelled' where id=%s", (job,))
    assert conn.execute("select * from claim_next_step('w', null)").fetchone() is None


def test_reset_from_step(db_url, conn):
    _, job = make_project(conn)
    run(db_url, 1, dry_run=True, once=False)
    s = steps(conn, job)
    conn.execute("select resolve_input_step(%s)", (s["research_review"]["id"],))
    run(db_url, 1, dry_run=True, once=False)
    assert steps(conn, job)["script_doc"]["status"] == "done"
    n = conn.execute("select reset_from_step(%s, 'research_verify') n", (job,)).fetchone()["n"]
    s = steps(conn, job)
    assert s["research_collect"]["status"] == "done"
    assert s["research_verify"]["status"] == "pending" and s["script_doc"]["status"] == "pending"
    assert s["research_review"]["status"] == "pending" and n >= 6
    run(db_url, 1, dry_run=True, once=False)
    assert steps(conn, job)["research_review"]["status"] == "waiting_input"   # onay yeniden istenir


def test_quota_exhausted_defers_without_burning_attempts(db_url, conn, monkeypatch):
    from fds_worker.llm import QuotaExhausted
    import fds_worker.main as M
    _, job = make_project(conn)

    def quota(_conn, _step):
        raise QuotaExhausted("429 GenerateRequestsPerDayPerProjectPerModel-FreeTier")

    monkeypatch.setattr(M, "registry", lambda dry: {"research_collect": quota, "research_verify": quota})
    for _ in range(5):
        run(db_url, 1, dry_run=False, once=False)
    s = steps(conn, job)["research_collect"]
    assert s["status"] == "pending" and s["attempts"] == 0          # 5 kez ertelendi, hak harcanmadı
    assert "PerDay" in s["error"]
    assert conn.execute("select status from jobs where id=%s", (job,)).fetchone()["status"] != "failed"


def test_voiceovers_uploaded_before_wait_step_opens(db_url, conn):
    """Hata düzeltmesi: sesler, 'seslendirme bekleniyor' adımı açılmadan önce yüklenirse süreç takılmamalı."""
    pid, job = make_project(conn)
    run(db_url, 1, dry_run=True, once=False)
    conn.execute("select resolve_input_step(%s)", (steps(conn, job)["research_review"]["id"],))
    run(db_url, 1, dry_run=True, once=False)
    conn.execute("select resolve_input_step(%s)", (steps(conn, job)["script_review"]["id"],))
    # İşçi henüz voiceover_texts'i çalıştırmadan kullanıcı iki sesi de yükler
    assert steps(conn, job)["voiceover_wait"]["status"] == "pending"
    for kind in ("doc", "shorts"):
        conn.execute("insert into voiceovers (project_id, kind, storage_key, filename, bytes) values (%s,%s,'k','f',10)", (pid, kind))
    run(db_url, 1, dry_run=True, once=False)
    s = steps(conn, job)
    assert s["voiceover_texts"]["status"] == "done"
    assert s["voiceover_wait"]["status"] == "done"
    assert s["voiceover_analyze"]["status"] == "done"
    assert s["visual_review"]["status"] == "waiting_input"


def test_idle_worker_picks_up_approval_without_new_trigger(db_url, conn, monkeypatch):
    """Panel GitHub'ı tetikleyemese bile: işçi onay bekleyen iş varken kuyruğu yoklar, onay gelince devam eder."""
    import threading

    from fds_worker import main as M
    monkeypatch.setattr(M, "IDLE_POLL_SEC", 0.2)
    pid, job = make_project(conn)
    run(db_url, 1, dry_run=True, once=False)                        # araştırma onayında durur
    review = steps(conn, job)["research_review"]
    assert review["status"] == "waiting_input"

    def approve_later():
        import time
        time.sleep(0.4)
        with psycopg.connect(db_url, autocommit=True) as c:
            c.execute("select resolve_input_step(%s)", (review["id"],))
    t = threading.Thread(target=approve_later)
    t.start()
    n = run(db_url, 1, dry_run=True, once=False, idle_minutes=0.4)    # ~24 sn yoklama penceresi (yük altında da yeterli)
    t.join()
    s = steps(conn, job)
    assert n >= 2 and s["script_shorts"]["status"] == "done" and s["script_review"]["status"] == "waiting_input"


def test_idle_disabled_or_nothing_waiting_exits_immediately(db_url, conn):
    import time
    _, job = make_project(conn)
    run(db_url, 1, dry_run=True, once=False)
    t0 = time.monotonic()
    run(db_url, 1, dry_run=True, once=False, idle_minutes=0)          # yoklama kapalı → hemen çıkar
    assert time.monotonic() - t0 < 2
    conn.execute("alter table jobs disable trigger jobs_touch")          # updated_at'i elle geriye almak için
    conn.execute("update jobs set updated_at = now() - interval '5 hours' where id=%s", (job,))
    conn.execute("alter table jobs enable trigger jobs_touch")
    t0 = time.monotonic()
    run(db_url, 1, dry_run=True, once=False, idle_minutes=1)          # eski bekleyen iş → yoklama yok
    assert time.monotonic() - t0 < 2

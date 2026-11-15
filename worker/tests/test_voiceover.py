"""Seslendirme testleri: metin üretimi, hizalama, R2 (moto S3 taklidi) + ffmpeg ile uçtan uca analiz.

Gerçek whisper testi yavaştır ve model indirir: yalnızca RUN_WHISPER=1 ile çalışır.
"""
import os
import shutil
import subprocess

import pytest

from fds_worker import storage, voiceover as V

from .conftest import make_project, steps

DOC = ["The town of Pompeii was buried under ash and pumice.",
       "Pliny the Younger watched the eruption from Misenum across the bay.",
       "Scholars still debate whether it happened in August or in October."]
SHORTS = ["How did a whole city vanish in one day?", "Vesuvius erupted and buried Pompeii under metres of ash."]


def test_build_text():
    t = V.build_text([{"voiceover_text": "Birinci  sahne.\n"}, {"voiceover_text": "İkinci sahne."}, {"voiceover_text": None}])
    assert t == "Birinci sahne.\n\nİkinci sahne.\n"


def _words(scenes, gap_scene=None, t0=0.5, per=0.4):
    out, t = [], t0
    for i, s in enumerate(scenes):
        for w in s.split():
            if i != gap_scene:
                out.append((w, t, t + per * 0.8))
            t += per
        t += 0.6
    return out, t


def test_align_contiguous_and_interpolates_missing_scene():
    words, end = _words(DOC, gap_scene=1)                 # 2. sahne hiç tanınmamış (ör. gürültü)
    bounds, cov = V.align(DOC, words, end + 1)
    assert bounds[0][0] == 0.0 and bounds[-1][1] == round(end + 1, 3)
    assert all(bounds[i][1] == bounds[i + 1][0] for i in range(len(bounds) - 1))   # kesintisiz
    assert bounds[0][1] < bounds[1][1] < bounds[2][1]
    assert 0.6 < cov < 0.75                               # 3 sahneden biri eksik


def test_align_wrong_audio_low_coverage():
    words, end = _words(["completely different words here"] * 3)
    _, cov = V.align(DOC, words, end)
    assert cov < 0.1


def _flite(text: str, path: str):
    tf = path + ".txt"
    open(tf, "w").write(text)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"flite=textfile={tf}:voice=slt",
                    "-ac", "1", "-ar", "22050", path], check=True)


@pytest.fixture()
def s3(monkeypatch, tmp_path):
    from moto.server import ThreadedMotoServer
    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    monkeypatch.setenv("R2_ENDPOINT", f"http://{host}:{port}")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("R2_BUCKET", "fds-test")
    monkeypatch.setenv("R2_REGION", "us-east-1")
    monkeypatch.setattr(storage, "_client", None)
    storage.client().create_bucket(Bucket="fds-test")
    yield
    storage._client = None
    server.stop()


def _prepare(conn, tmp_path, lang="en"):
    pid, job = make_project(conn)
    conn.execute("update projects set language=%s where id=%s", (lang, pid))
    for kind, scenes in (("doc", DOC), ("shorts", SHORTS)):
        for i, t in enumerate(scenes, 1):
            conn.execute("insert into scenes (project_id, kind, idx, voiceover_text) values (%s,%s,%s,%s)", (pid, kind, i, t))
        wav = str(tmp_path / f"{kind}.wav")
        _flite(" ".join(scenes), wav)
        key = f"projects/pompei-son-gunu/voiceover/{kind}.wav"
        sha = storage.upload_file(key, wav, "audio/wav")
        conn.execute("insert into voiceovers (project_id, kind, storage_key, filename, bytes, sha256) values (%s,%s,%s,%s,%s,%s)",
                     (pid, kind, key, f"{kind}.wav", os.path.getsize(wav), sha))
    return pid, job


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg yok")
def test_analyze_end_to_end_with_fake_transcriber(conn, s3, tmp_path, monkeypatch):
    pid, job = _prepare(conn, tmp_path)

    def fake_transcribe(path, lang, prompt):
        # Gerçek ses süresine yayılmış, senaryodaki kelimeler (whisper taklidi)
        dur = V.probe_duration(path)
        ws = prompt.split()
        return [(w, i * dur / len(ws), (i + 0.8) * dur / len(ws)) for i, w in enumerate(ws)]

    monkeypatch.setattr(V, "transcribe", fake_transcribe)
    res = V.analyze(conn, steps(conn, job)["voiceover_analyze"]).output
    for kind in ("doc", "shorts"):
        assert res[kind]["coverage"] == 1.0
        assert res[kind]["duration_sec"] > 2
        assert any("hedef aralık" in w for w in res[kind]["warnings"])     # test sesi kısa → süre uyarısı
    vo = conn.execute("select * from voiceovers where project_id=%s and kind='doc'", (pid,)).fetchone()
    assert vo["status"] == "analyzed" and vo["words_key"].endswith("doc_words.json")
    body = storage.client().get_object(Bucket="fds-test", Key=vo["words_key"])["Body"].read()
    assert b'"w"' in body
    sc = conn.execute("select start_sec, end_sec from scenes where project_id=%s and kind='doc' order by idx", (pid,)).fetchall()
    assert float(sc[0]["start_sec"]) == 0 and float(sc[-1]["end_sec"]) == pytest.approx(float(vo["duration_sec"]), abs=0.01)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg yok")
def test_analyze_detects_tampered_file(conn, s3, tmp_path, monkeypatch):
    pid, job = _prepare(conn, tmp_path)
    conn.execute("update voiceovers set sha256='deadbeef' where project_id=%s and kind='doc'", (pid,))
    monkeypatch.setattr(V, "transcribe", lambda *a: [])
    with pytest.raises(RuntimeError, match="bütünlük"):
        V.analyze(conn, steps(conn, job)["voiceover_analyze"])


@pytest.mark.skipif(os.environ.get("RUN_WHISPER") != "1", reason="gerçek whisper testi: RUN_WHISPER=1")
def test_real_whisper_alignment(conn, s3, tmp_path, monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL", "tiny")
    pid, job = _prepare(conn, tmp_path)
    res = V.analyze(conn, steps(conn, job)["voiceover_analyze"]).output
    print(res)
    assert res["doc"]["coverage"] > 0.6
    sc = conn.execute("select start_sec, end_sec from scenes where project_id=%s and kind='doc' order by idx", (pid,)).fetchall()
    assert float(sc[0]["end_sec"]) < float(sc[1]["end_sec"]) < float(sc[2]["end_sec"])

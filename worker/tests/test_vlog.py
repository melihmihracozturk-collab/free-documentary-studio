"""Gezi vlogu biçimi: Wikivoyage toplama, durak bölümleri, pratik bilgi işareti, YouTube bölümleri."""
import re

import pytest
from psycopg.types.json import Jsonb

from fds_worker import deliver, llm, research, script, vlog
from fds_worker import sources as S

from .conftest import make_project, steps
from .test_research import scene

STOPS = [{"name_en": "Colosseum", "name_native": "Kolezyum"}, {"name_en": "Trevi Fountain", "name_native": "Aşk Çeşmesi"}]


def _vlog_project(conn):
    pid, job = make_project(conn, "roma-gezisi")
    conn.execute("update projects set format='vlog', topic='Roma Gezisi', title='Roma Gezisi', target_minutes=10 where id=%s",
                 (pid,))
    return pid, job


def test_plan_acts_stops_become_chapters():
    acts, titles, plan = vlog.plan_acts(STOPS, 1050)
    assert acts == ["giris", "durak_1", "durak_2", "ipuclari", "kapanis"]
    assert titles["durak_1"] == "Kolezyum" and titles["ipuclari"] == "Pratik ipuçları"
    assert abs(sum(w for w, _ in plan.values()) - 1050) <= 5
    assert plan["durak_1"][0] > plan["giris"][0]                       # ağırlık duraklarda


def test_mark_needs_check_only_practical_scenes():
    scenes = [{"claim_refs": ["C1"]}, {"claim_refs": ["C2", "C3"]}, {"claim_refs": []}]
    assert script.mark_needs_check(scenes, {"C3"}) == 1
    assert [s["needs_check"] for s in scenes] == [False, True, False]


def test_chapters_use_stop_titles():
    sc = [{"act": "giris", "start_sec": 0}, {"act": "durak_1", "start_sec": 30}, {"act": "durak_1", "start_sec": 60},
          {"act": "durak_2", "start_sec": 200}, {"act": "ipuclari", "start_sec": 400}, {"act": "kapanis", "start_sec": 500}]
    ch = deliver.chapters(sc, titles={"giris": "Giriş", "durak_1": "Kolezyum", "durak_2": "Aşk Çeşmesi",
                                      "ipuclari": "Pratik ipuçları", "kapanis": "Kapanış"})
    assert [n for _, n in ch] == ["Giriş", "Kolezyum", "Aşk Çeşmesi", "Pratik ipuçları", "Kapanış"]
    assert "Fiyat, açılış saati" in deliver.doc_description({"title": "Roma", "format": "vlog"}, None, None, ch, [], [])
    assert "#gezi" in deliver.shorts_description({"title": "Roma", "format": "vlog"}, None)


def test_vlog_collect_uses_wikivoyage_and_stops(conn, monkeypatch):
    pid, job = _vlog_project(conn)
    monkeypatch.setenv("FDS_FAKE_LLM", "1")
    monkeypatch.setattr(llm, "fake_responder", lambda sys, prompt: {
        "stops": STOPS, "destination_en": "Rome", "queries_en": ["Rome history"], "queries_native": ["Roma"],
        "keywords": ["Rome"], "core_keywords": ["Rome", "Roma"]})
    asked = []

    def wiki(q, lang="en", limit=3, site="wikipedia"):
        asked.append((site, q))
        typ = "guide" if site == "wikivoyage" else "encyclopedia"
        return [S.Source(f"https://{lang}.{site}.org/wiki/{q}", q, site.title(), typ, site,
                         f"{q} in Rome is a famous place. Tickets cost 18 euros. " * 40, lang=lang)]
    monkeypatch.setattr(S, "wikipedia", wiki)
    monkeypatch.setattr(S, "wikivoyage", lambda q, limit=2: wiki(q, "en", limit, "wikivoyage"))
    monkeypatch.setattr(S, "crossref", lambda q, limit=6: [])
    monkeypatch.setattr(S, "openalex", lambda q, limit=6: [])
    out = research.collect(conn, steps(conn, job)["research_collect"]).output
    assert ("wikivoyage", "Rome") in asked and ("wikivoyage", "Colosseum") in asked and ("wikipedia", "Trevi Fountain") in asked
    assert out["by_type"].get("guide", 0) >= 2 and out["plan"]["stops"] == STOPS
    keys = {r["independence_key"] for r in conn.execute("select independence_key from sources where project_id=%s", (pid,))}
    assert {"wikipedia", "pub:wikivoyage"} <= keys                    # rehber ve ansiklopedi bağımsız sayılır


class FakeVlog:
    def __init__(self):
        self.calls = []

    def __call__(self, system, prompt):
        if "TRAVEL VLOG in" in prompt and "Chapters (fixed order)" in prompt:
            self.calls.append("outline")
            acts = re.findall(r"^- (\w+) = ", prompt, re.M)
            return {"title": "Roma'da Bir Gün", "logline": "Sonsuz şehirde bir tur.",
                    "acts": [{"act": a, "beats": ["sahne"], "claim_refs": ["C1"]} for a in acts]}
        if "You are writing ONE chapter" in prompt:
            act = re.search(r"CHAPTER: (\w+)", prompt).group(1)
            self.calls.append(f"chapter_{act}")
            assert "FIRST-PERSON travel vlog" in prompt
            n = int(re.search(r"EXACTLY (\d+) scenes", prompt).group(1))
            total = int(re.search(r"total about (\d+) words", prompt).group(1))
            refs = ["C2"] if act == "ipuclari" else ["C1"]
            return {"scenes": [scene(int(total / script.LENGTH_BOOST) // n, refs) for _ in range(n)]}
        if "fact-checking EDITOR of a travel vlog" in prompt:
            self.calls.append("edit")
            assert "FIRST-PERSON travel vlog" in prompt                   # editör de vlog üslubunu korur
            return {"notes": ["ok"]}
        if "too short" in prompt:
            return {"insert_after": []}
        if "YouTube Shorts" in prompt:
            self.calls.append("shorts")
            assert "full travel vlog" in prompt and "FIRST-PERSON" in prompt
            sizes = [int(x) for x in re.search(r"narration lengths in words: \[([^\]]*)\]", prompt).group(1).split(",")]
            return {"title": "Roma", "scenes": [scene(round(w / script.LENGTH_BOOST) if i else w, ["C2"])
                                                for i, w in enumerate(sizes)]}
        raise AssertionError("beklenmeyen istem: " + prompt[:200])


def test_vlog_script_chapters_and_needs_check(conn, monkeypatch):
    pid, job = _vlog_project(conn)
    conn.execute("update job_steps set output=%s where job_id=%s and step_key='research_collect'",
                 (Jsonb({"plan": {"stops": STOPS}}), job))
    for ref, text, cat in (("C1", "Kolezyum MS 80'de açıldı.", "time"), ("C2", "Kolezyum bileti 18 avro.", "practical")):
        conn.execute("insert into claims (project_id, ref, text, status, category, importance) values (%s,%s,%s,'weak',%s,2)",
                     (pid, ref, text, cat))
    monkeypatch.setenv("FDS_FAKE_LLM", "1")
    fake = FakeVlog()
    monkeypatch.setattr(llm, "fake_responder", fake)
    out = script.script_doc(conn, steps(conn, job)["script_doc"]).output
    assert out["format"] == "vlog" and out["chapters"] == ["Giriş", "Kolezyum", "Aşk Çeşmesi", "Pratik ipuçları", "Kapanış"]
    assert out["validation_errors"] == [], out["validation_errors"]
    rows = conn.execute("select act, needs_check from scenes where project_id=%s and kind='doc' order by idx", (pid,)).fetchall()
    assert rows[0]["act"] == "giris" and rows[-1]["act"] == "kapanis"
    assert all(r["needs_check"] == (r["act"] == "ipuclari") for r in rows)     # yalnızca pratik bilgi sahneleri
    content = conn.execute("select content from scripts where project_id=%s and kind='doc'", (pid,)).fetchone()["content"]
    assert content["act_titles"]["durak_2"] == "Aşk Çeşmesi"

    sh = script.script_shorts(conn, steps(conn, job)["script_shorts"]).output
    assert sh["validation_errors"] == [] and "shorts" in fake.calls
    assert conn.execute("select bool_and(needs_check) b from scenes where project_id=%s and kind='shorts'",
                        (pid,)).fetchone()["b"] is True


def test_documentary_still_default(conn):
    pid, _ = make_project(conn, "belgesel-varsayilan")
    assert conn.execute("select format from projects where id=%s", (pid,)).fetchone()["format"] == "documentary"
    with pytest.raises(Exception):
        conn.execute("update projects set format='podcast' where id=%s", (pid,))

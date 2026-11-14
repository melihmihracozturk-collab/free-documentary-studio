"""Araştırma ve senaryo motoru testleri.

Gerçek LLM ve ağ çağrısı yapılmaz: kaynaklar sabit metinlerle, LLM sahte bir yanıtlayıcıyla taklit edilir.
Amaç kodun kurallarını sınamak: alıntı doğrulama, bağımsız kaynak sayımı, çelişki, kelime bütçesi, düzeltme döngüsü.
"""
import re

import pytest

from fds_worker import handlers as H
from fds_worker import llm, research, script, sources as S
from fds_worker.main import run

from .conftest import make_project, steps

PLINY = ("Pliny the Younger wrote that the eruption began on the ninth day before the Kalends of September, "
         "that is 24 August AD 79, when a cloud of unusual size and appearance rose from the mountain. "
         "The town of Pompeii was buried under several metres of pumice and ash.")
WIKI = ("Mount Vesuvius erupted in AD 79 and destroyed the Roman towns of Pompeii and Herculaneum. "
        "The eruption buried Pompeii under four to six metres of volcanic ash and pumice. "
        "Pliny the Elder died at Stabiae while attempting a rescue by sea.")
INSCRIPTION = ("A charcoal inscription found in 2018 dated to 17 October suggests the eruption of Vesuvius "
               "happened in autumn AD 79 rather than in August, a date debated by archaeologists.")

FIXTURES = [
    S.Source("https://en.wikipedia.org/wiki/Pompeii", "Pompeii", "Wikipedia", "encyclopedia", "wikipedia", WIKI),
    S.Source("https://doi.org/10.1/pliny", "Letters of Pliny", "Journal of Roman Studies", "academic", "crossref", PLINY,
             extra={"doi": "10.1/pliny"}),
    S.Source("https://doi.org/10.1/pliny", "Letters of Pliny (dup)", "OpenAlex", "academic", "openalex", PLINY,
             extra={"doi": "10.1/pliny"}),
    S.Source("https://doi.org/10.2/insc", "New inscription", "Antiquity", "academic", "openalex", INSCRIPTION,
             extra={"doi": "10.2/insc"}),
    S.Source("https://loc.gov/x", "Unrelated stamp collection", "Library of Congress", "archive", "loc",
             "A catalogue of postage stamps from the nineteenth century " * 10),
]


def scene(text_words: int, refs):
    return {"voiceover": " ".join(["kelime"] * text_words), "visual_description": "Vezüv tablosu",
            "search_keywords": ["Vesuvius painting"], "camera_move": "zoom_in", "transition": "crossfade",
            "music": "gergin yaylılar", "sfx": "uzak gök gürültüsü", "on_screen_text": None, "claim_refs": refs}


class Fake:
    """Görev türüne göre sahte LLM yanıtı. calls: hangi görevlerin çağrıldığını kaydeder."""

    def __init__(self, bad_first_script=False):
        self.calls = []
        self.bad_first_script = bad_first_script

    def __call__(self, system, prompt):
        if "Plan research" in prompt:
            self.calls.append("plan")
            return {"subquestions": ["Ne zaman?"], "queries_en": ["Pompeii eruption"], "queries_native": ["Pompei"],
                    "keywords": ["Pompeii", "Vesuvius", "Pliny"]}
        if "extract the factual claims" in prompt:
            self.calls.append("extract")
            return {"claims": [
                {"text": "Vezüv MS 79'da patladı ve Pompei'yi yok etti.", "category": "time", "importance": 3,
                 "event_date": "MS 79", "source_ref": ref("Pompeii"), "quote": "Mount Vesuvius erupted in AD 79 and destroyed the Roman towns"},
                {"text": "Pompei metrelerce kül ve süngertaşı altında kaldı.", "category": "consequence", "importance": 3,
                 "event_date": None, "source_ref": ref("Pompeii"), "quote": "buried Pompeii under four to six metres of volcanic ash and pumice"},
                {"text": "Pompei metrelerce süngertaşı ve kül altında kaldı.", "category": "consequence", "importance": 3,
                 "event_date": None, "source_ref": ref("Letters of Pliny"), "quote": "The town of Pompeii was buried under several metres of pumice and ash"},
                {"text": "Patlama 24 Ağustos 79'da başladı.", "category": "time", "importance": 3, "event_date": "24 Ağustos 79",
                 "source_ref": ref("Letters of Pliny"), "quote": "that is 24 August AD 79, when a cloud of unusual size"},
                {"text": "Bir yazıt patlamanın Ekim 79'da olduğunu düşündürüyor.", "category": "debate", "importance": 2,
                 "event_date": "17 Ekim 79", "source_ref": ref("New inscription"), "quote": "dated to 17 October suggests the eruption of Vesuvius happened in autumn"},
                # Uydurma alıntı: kaynakta yok → reddedilmeli
                {"text": "Patlamada 20.000 kişi öldü.", "category": "number", "importance": 3, "event_date": None,
                 "source_ref": ref("Pompeii"), "quote": "the eruption killed exactly twenty thousand inhabitants of the city"},
            ]}
        if "Group claims" in prompt:
            self.calls.append("merge")
            ids = {int(m.group(1)): m.group(2) for m in re.finditer(r"^(\d+)\. \[S\d+\] (.*)$", prompt, re.M)}
            find = lambda frag: [i for i, t in ids.items() if frag in t]
            return {"groups": [
                {"text": "Vezüv MS 79'da patladı.", "category": "time", "importance": 3, "event_date": "MS 79", "members": find("MS 79'da patladı")},
                {"text": "Pompei metrelerce kül altında kaldı.", "category": "consequence", "importance": 3, "event_date": None,
                 "members": find("metrelerce")},
                {"text": "Patlama 24 Ağustos 79'da başladı.", "category": "time", "importance": 3, "event_date": "24 Ağustos 79", "members": find("24 Ağustos")},
                {"text": "Patlama Ekim 79'da olmuş olabilir.", "category": "debate", "importance": 2, "event_date": "Ekim 79", "members": find("Ekim 79")},
            ], "conflicts": [{"groups": [2, 3], "note": "Plinius 24 Ağustos der; 2018 yazıtı Ekim'e işaret eder."}]}
        if "research summary" in prompt:
            self.calls.append("summary")
            return {"summary": "Vezüv MS 79'da patladı; tarih tartışmalı."}
        if "documentary script" in prompt:
            self.calls.append("script_doc" if "previous answer" not in prompt else "script_doc_repair")
            budget = int(re.search(r"about (\d+) words", prompt).group(1))
            if self.bad_first_script and self.calls.count("script_doc") == 1 and "previous answer" not in prompt:
                return {"title": "x", "acts": [{"act": "giris", "scenes": [scene(10, ["C99"])]}]}
            per = budget // 30
            acts = [{"act": a, "scenes": [scene(per, ["C1"]) for _ in range(5)]} for a in script.ACTS]
            return {"title": "Pompei'nin Son Günü", "logline": "Bir şehir bir günde.", "acts": acts}
        if "YouTube Shorts" in prompt:
            self.calls.append("shorts")
            budget = int(re.search(r"about (\d+) words", prompt).group(1))
            rest = budget - 6
            return {"title": "Pompei", "scenes": [scene(6, ["C1"])] + [scene(rest // 6, ["C2"]) for _ in range(6)]}
        raise AssertionError("beklenmeyen istem: " + prompt[:200])


def ref(title):
    return REFS[title]


REFS = {}


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setenv("FDS_FAKE_LLM", "1")
    f = Fake()
    monkeypatch.setattr(llm, "fake_responder", f)
    srcs = list(FIXTURES)
    # Toplama sırasına göre S# kimlikleri (tekilleştirme + alaka filtresinden sonra)
    REFS.clear()
    REFS.update({"Pompeii": "S1", "Letters of Pliny": "S2", "New inscription": "S3"})
    monkeypatch.setattr(S, "wikipedia", lambda q, lang="en", limit=3: [srcs[0]] if lang == "en" else [])
    monkeypatch.setattr(S, "crossref", lambda q, limit=6: [srcs[1]])
    monkeypatch.setattr(S, "openalex", lambda q, limit=6: [srcs[2], srcs[3]])
    monkeypatch.setattr(S, "library_of_congress", lambda q, limit=5: [srcs[4]])
    monkeypatch.setattr(S, "internet_archive", lambda q, limit=5: (_ for _ in ()).throw(RuntimeError("ağ hatası")))
    monkeypatch.setattr(S, "europeana", lambda q, limit=5: [])
    return f


def test_quote_matching():
    assert research.quote_in_text("Mount Vesuvius erupted in AD 79", WIKI)
    assert research.quote_in_text("MOUNT vesuvius  erupted, in AD 79", WIKI)       # biçim farkı
    assert research.quote_in_text("buried Pompeii under four to six meters of volcanic ash", WIKI)  # küçük yazım farkı
    assert not research.quote_in_text("killed exactly twenty thousand inhabitants", WIKI)
    assert not research.quote_in_text("AD 79", WIKI)                                  # çok kısa alıntı geçmez


def test_no_llm_key_no_handlers(monkeypatch):
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "FDS_FAKE_LLM"):
        monkeypatch.delenv(k, raising=False)
    assert H.registry(False) == {}
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert set(H.registry(False)) == {"research_collect", "research_verify", "research_report", "script_doc", "script_shorts"}


def test_research_and_script_pipeline(db_url, conn, fake):
    pid, job = make_project(conn)
    run(db_url, 1, dry_run=False, once=False)
    s = steps(conn, job)
    assert [k for k, r in s.items() if r["status"] == "done"] == ["research_collect", "research_verify", "research_report"]
    assert s["research_review"]["status"] == "waiting_input"

    # Kaynaklar: DOI tekilleştirildi, alakasız LoC kaydı elendi, çöken toplayıcı uyarı olarak kaydedildi
    srcs = conn.execute("select ref, title from sources where project_id=%s order by ref", (pid,)).fetchall()
    assert [r["title"] for r in srcs] == ["Pompeii", "Letters of Pliny", "New inscription"]
    assert conn.execute("select count(*) n from error_logs where message like 'Kaynak toplanamadı%%'").fetchone()["n"] >= 1

    claims = {c["text"]: c for c in conn.execute("select * from claims where project_id=%s", (pid,)).fetchall()}
    assert claims["Pompei metrelerce kül altında kaldı."]["status"] == "verified"          # Wikipedia + dergi
    assert claims["Pompei metrelerce kül altında kaldı."]["independent_sources"] == 2
    assert claims["Vezüv MS 79'da patladı."]["status"] == "weak"                            # tek kaynak
    assert claims["Patlama 24 Ağustos 79'da başladı."]["status"] == "conflict"
    assert "2018" in claims["Patlama Ekim 79'da olmuş olabilir."]["conflict_note"]
    assert not any("20.000" in t for t in claims)                                            # uydurma alıntı elendi
    assert s["research_verify"]["output"]["quotes_rejected"] == 1

    rep = conn.execute("select * from research_reports where project_id=%s", (pid,)).fetchone()
    assert "## Çelişkiler" in rep["markdown"] and "Plinius 24 Ağustos" in rep["markdown"]
    assert "## Kaynaklar" in rep["markdown"] and "Antiquity" in rep["markdown"]

    # Onay → senaryolar
    conn.execute("select resolve_input_step(%s)", (s["research_review"]["id"],))
    run(db_url, 1, dry_run=False, once=False)
    s = steps(conn, job)
    assert s["script_doc"]["status"] == "done" and s["script_shorts"]["status"] == "done"
    assert s["visual_plan"]["status"] == "pending"                                           # Stage 5 işleyicisi yok
    out = s["script_doc"]["output"]
    assert out["validation_errors"] == [] and out["scenes"] == 30
    assert 10 <= out["est_minutes"] * 1.0 <= 12.2
    doc_scenes = conn.execute("select * from scenes where project_id=%s and kind='doc' order by idx", (pid,)).fetchall()
    assert len(doc_scenes) == 30 and doc_scenes[0]["act"] == "giris" and doc_scenes[-1]["act"] == "kapanis"
    assert doc_scenes[0]["search_keywords"] == ["Vesuvius painting"]
    sh = s["script_shorts"]["output"]
    assert sh["validation_errors"] == [] and 45 <= sh["est_seconds"] <= 62
    vo = conn.execute("select voiceover_text from scripts where project_id=%s and kind='shorts'", (pid,)).fetchone()
    assert vo["voiceover_text"].count("\n\n") == 6

    # Önbellek: aynı adımları yeniden çalıştırmak LLM'e tekrar gitmez
    n_calls = len(fake.calls)
    research.report(conn, s["research_report"])
    assert len(fake.calls) == n_calls


def test_script_repair_loop(db_url, conn, monkeypatch):
    monkeypatch.setenv("FDS_FAKE_LLM", "1")
    f = Fake(bad_first_script=True)
    monkeypatch.setattr(llm, "fake_responder", f)
    pid, job = make_project(conn)
    conn.execute("insert into claims (project_id, ref, text, status) values (%s,'C1','x','verified'),(%s,'C2','y','weak')", (pid, pid))
    step = steps(conn, job)["script_doc"]
    res = script.script_doc(conn, step)
    assert f.calls == ["script_doc", "script_doc_repair"]
    assert res.output["validation_errors"] == []


def test_validators():
    status = {"C1": "verified", "C2": "conflict"}
    errs = script.validate_doc({"acts": [{"act": "giris", "scenes": [scene(80, ["C2", "C9"])]}]}, 1500, status)
    joined = " ".join(errs)
    for frag in ("acts sırası", "80 kelime", "bilinmeyen iddia C9", "çelişkili iddia C2", "toplam seslendirme"):
        assert frag in joined
    ok = scene(5, ["C2"]) | {"disputed": True}
    assert not any("C2" in e for e in script._validate_scene(ok, 1, status))
    errs = script.validate_shorts({"scenes": [scene(15, ["C1"])] * 5}, 140, status)
    assert any("kanca" in e for e in errs)

"""Araştırma ve senaryo motoru testleri.

Gerçek LLM ve ağ çağrısı yapılmaz: kaynaklar sabit metinlerle, LLM sahte bir yanıtlayıcıyla taklit edilir.
Amaç kodun kurallarını sınamak: alıntı doğrulama, bağımsız kaynak sayımı, çelişki, kelime bütçesi, düzeltme döngüsü.
"""
import json
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
             extra={"doi": "10.1/pliny", "work_type": "journal-article"}),
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
        self.edit_prompts = []
        self.bad_first_script = bad_first_script

    def __call__(self, system, prompt):
        if "Plan research" in prompt:
            self.calls.append("plan")
            return {"subquestions": ["Ne zaman?"], "queries_en": ["Pompeii eruption"], "queries_native": ["Pompei"],
                    "keywords": ["Pompeii", "Vesuvius", "Pliny"],
                    "core_keywords": ["Pompeii", "Vesuvius"]}
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
                {"text": "Yaşlı Plinius Stabiae'de öldü.", "category": "person", "importance": 2, "event_date": None,
                 "source_ref": ref("Pompeii"), "quote": "Pliny the Elder died at Stabiae while attempting a rescue by sea"},
                # Uydurma alıntı: kaynakta yok → reddedilmeli
                {"text": "Patlamada 20.000 kişi öldü.", "category": "number", "importance": 3, "event_date": None,
                 "source_ref": ref("Pompeii"), "quote": "the eruption killed exactly twenty thousand inhabitants of the city"},
            ]}
        if "Group claims" in prompt:
            self.calls.append("merge")
            ids = {int(m.group(1)): m.group(2) for m in re.finditer(r"^(\d+)\. \[S\d+\] (.*)$", prompt, re.M)}
            find = lambda frag: [i for i, t in ids.items() if frag in t]
            return {"groups": [
                {"gid": "G1", "text": "Vezüv MS 79'da patladı.", "category": "time", "importance": 3, "event_date": "MS 79", "members": find("MS 79'da patladı")},
                {"gid": "G2", "text": "Pompei metrelerce kül altında kaldı.", "category": "consequence", "importance": 3, "event_date": None,
                 "members": find("metrelerce")},
                {"gid": "G3", "text": "Patlama 24 Ağustos 79'da başladı.", "category": "time", "importance": 3, "event_date": "24 Ağustos 79", "members": find("24 Ağustos")},
                {"gid": "G4", "text": "Patlama Ekim 79'da olmuş olabilir.", "category": "debate", "importance": 2, "event_date": "Ekim 79", "members": find("Ekim 79")},
                {"gid": "G5", "text": "Yaşlı Plinius Stabiae'de öldü.", "category": "person", "importance": 2, "event_date": None, "members": find("Stabiae")},
            ], "conflicts": [{"gids": ["G3", "G4"], "note": "Plinius 24 Ağustos der; 2018 yazıtı Ekim'e işaret eder."},
                             {"gids": ["G1", "G99"], "note": "geçersiz kimlik: yok sayılmalı"}]}
        if "independently support the SAME fact" in prompt:
            self.calls.append("crosscheck")
            out = []
            if "[S2]" in prompt and "G1:" in prompt:
                # Gerçek destek: S2 (Pliny) metninde 79 tarihi geçiyor → G1 doğrulanmalı
                out.append({"gid": "G1", "source_ref": "S2", "quote": "that is 24 August AD 79, when a cloud of unusual size"})
                # Uydurma destek: S3 metninde yok → reddedilmeli
                out.append({"gid": "G5", "source_ref": "S3", "quote": "Pliny the Elder died at Stabiae during the rescue"})
            return {"support": out}
        if "research summary" in prompt:
            self.calls.append("summary")
            return {"summary": "Vezüv MS 79'da patladı; tarih tartışmalı."}
        if "Plan a " in prompt and "documentary in" in prompt:
            self.calls.append("outline")
            return {"title": "Pompei'nin Son Günü", "logline": "Bir şehir bir günde.",
                    "acts": [{"act": a, "beats": ["sahne"], "claim_refs": ["C1"]} for a in script.ACTS]}
        if "You are writing ONE act" in prompt:
            act = re.search(r"ACT: (\w+)", prompt).group(1)
            self.calls.append(f"act_{act}" + ("_repair" if "previous answer" in prompt else ""))
            n = int(re.search(r"EXACTLY (\d+) scenes", prompt).group(1))
            total = int(re.search(r"total about (\d+) words", prompt).group(1))
            if self.bad_first_script and act == "giris" and "previous answer" not in prompt:
                return {"scenes": [scene(5, ["C99"])]}
            # Gerçek model gibi: istenenin ~1/LENGTH_BOOST'u kadar yazar (ölçülen kısa yazma eğilimi)
            per = int(total / script.LENGTH_BOOST) // n
            return {"scenes": [scene(per, ["C1"]) for _ in range(n)]}
        if "fact-checking EDITOR" in prompt:
            kind = "doc" if "script_edit" not in prompt and "Shorts" not in prompt.split("Fix the script")[1][:2000] else "shorts"
            self.calls.append("edit")
            self.edit_prompts.append(prompt)
            return {"replace": [{"scene": 1, "voiceover": "Gökyüzü karardı ve şehir sustu.", "claim_refs": ["C1"]}],
                    "delete": [2], "insert_after": [{"scene": 1, "new_scene": {"voiceover": "Yeni sahne metni burada.",
                                                     "claim_refs": ["C2"], "visual_description": "harita",
                                                     "search_keywords": ["map"]}}], "notes": ["tekrar giderildi"]}
        if "YouTube Shorts" in prompt:
            self.calls.append("shorts")
            sizes = json.loads(re.search(r"narration lengths in words: (\[[^\]]*\])", prompt).group(1))
            return {"title": "Pompei", "scenes": [scene(round(w / script.LENGTH_BOOST) if i else w, ["C2"])
                                                  for i, w in enumerate(sizes)]}
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
    for k in ("R2_ACCOUNT_ID", "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.delenv(k, raising=False)
    assert set(H.registry(False)) == {"voiceover_texts", "visual_plan", "asset_match"}   # LLM/R2 gerektirmeyenler
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert set(H.registry(False)) == {"voiceover_texts", "visual_plan", "asset_match", "research_collect", "research_verify", "research_report",
                                      "script_doc", "script_shorts"}


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
    assert claims["Vezüv MS 79'da patladı."]["status"] == "verified"                        # çapraz doğrulamayla 2. kaynak
    assert any(x.get("cross_check") for x in claims["Vezüv MS 79'da patladı."]["support"])
    assert claims["Yaşlı Plinius Stabiae'de öldü."]["status"] == "weak"                     # uydurma destek reddedildi
    assert s["research_verify"]["output"]["cross_check_added"] == 1
    assert s["research_verify"]["output"]["cross_check_rejected"] == 1
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
    assert s["script_review"]["status"] == "waiting_input"                                   # senaryo onayı bekleniyor
    out = s["script_doc"]["output"]
    assert out["validation_errors"] == [] and 25 <= out["scenes"] <= 40
    assert 10 <= out["est_minutes"] * 1.0 <= 12.2
    doc_scenes = conn.execute("select * from scenes where project_id=%s and kind='doc' order by idx", (pid,)).fetchall()
    assert doc_scenes[0]["act"] == "giris" and doc_scenes[-1]["act"] == "kapanis"
    assert fake.calls.count("outline") == 1 and all(f"act_{a}" in fake.calls for a in script.ACTS)
    assert doc_scenes[0]["search_keywords"] == ["Vesuvius painting"]
    sh = s["script_shorts"]["output"]
    assert sh["validation_errors"] == [] and 45 <= sh["est_seconds"] <= 62
    vo = conn.execute("select voiceover_text from scripts where project_id=%s and kind='shorts'", (pid,)).fetchone()
    assert vo["voiceover_text"].count("\n\n") == 7

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
    assert f.calls[:3] == ["outline", "act_giris", "act_giris_repair"]   # kısa/hatalı bölüm yeniden yazdırıldı
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


def test_independence_keys():
    wiki_en = S.Source("a", "Pompeii", "Wikipedia", "encyclopedia", "wikipedia", "x", lang="en")
    wiki_tr = S.Source("b", "Pompei", "Wikipedia", "encyclopedia", "wikipedia", "x", lang="tr")
    plos1 = S.Source("c", "A", "PLoS ONE", "academic", "crossref", "x", extra={"doi": "10.1/a", "work_type": "journal-article"})
    plos2 = S.Source("d", "B", "PLoS ONE", "academic", "crossref", "x", extra={"doi": "10.1/b", "work_type": "journal-article"})
    ch1 = S.Source("e", "Ch1", "Escape from Pompeii", "academic", "crossref", "x", extra={"doi": "10.2/1", "work_type": "book-chapter"})
    ch2 = S.Source("f", "Ch2", "Escape from Pompeii", "academic", "openalex", "x", extra={"doi": "10.2/2", "work_type": "book-chapter"})
    k = S.independence_key
    assert k(wiki_en) == k(wiki_tr)                 # Wikipedia dilleri tek kaynak
    assert k(plos1) != k(plos2)                     # aynı dergide farklı makaleler bağımsız
    assert k(ch1) == k(ch2)                         # aynı kitabın bölümleri tek kaynak


def test_relevance_filter():
    kw = ["Pompeii", "Vesuvius"]
    ararat = S.Source("u1", "Mount Ararat", "Wikipedia", "encyclopedia", "wikipedia",
                      "Ararat is a dormant volcano in Turkey. Unlike Vesuvius it has not erupted in historic times. "
                      "It is the highest peak in Turkey and has a long history in religious texts.")
    pompeii = S.Source("u2", "Pompeii", "Wikipedia", "encyclopedia", "wikipedia", "An ancient city.")
    eruption_wiki = S.Source("u3", "AD 79 eruption", "Wikipedia", "encyclopedia", "wikipedia",
                             "Vesuvius buried Pompeii. Pompeii was a city. Vesuvius is a volcano.")
    abstract = S.Source("u4", "Ash fall study", "J", "academic", "crossref", "Ash layers from Vesuvius were sampled.")
    assert not research._relevant(ararat, kw)       # Wikipedia: başlıkta yok, metinde yalnızca 1 geçiş
    assert research._relevant(pompeii, kw)          # başlıkta geçiyor
    assert research._relevant(eruption_wiki, kw)
    assert research._relevant(abstract, kw)         # akademik: 1 geçiş yeterli


def test_apply_edits_and_repeats():
    sc = lambda t, refs: {"voiceover": t, "claim_refs": refs, "_act": "gelisme", "camera_move": "static",
                          "transition": "cut", "music": "m", "sfx": "s", "search_keywords": ["k"], "visual_description": "v"}
    scenes = [sc("bir", ["C1"]), sc("iki", ["C1", "C2"]), sc("üç", ["C3"])]
    assert script.find_repeats(scenes) == {"C1": [1, 2]}
    out, _ = script.apply_edits(scenes, {"replace": [{"scene": 3, "voiceover": "ÜÇ", "claim_refs": ["C4"]}],
                                      "delete": [2],
                                      "insert_after": [{"scene": 1, "new_scene": {"voiceover": "yeni", "claim_refs": ["C5"]}},
                                                       {"scene": 99, "new_scene": {"voiceover": "geçersiz"}}]})
    assert [s["voiceover"] for s in out] == ["bir", "yeni", "ÜÇ"]
    assert out[1]["_act"] == "gelisme" and out[1]["camera_move"] == "static"   # eklenen sahne komşusundan alanları alır
    assert out[2]["claim_refs"] == ["C4"]


def test_guarded_edits():
    sc = lambda t, refs: {"voiceover": t, "claim_refs": refs, "_act": "gelisme"}
    claims = "C1 (MS 62) MS 62 depremi. C2 Patlama iki gün sürdü."
    scenes = [sc("Milattan sonra altmış iki yılında büyük bir deprem şehri sarstı ve evler hasar gördü.", ["C1"]),
              sc("Patlama tam iki gün sürdü ve gökyüzü karardı, insanlar kaçtı.", ["C2"]),
              sc("Patlama iki gün boyunca sürdü.", ["C2"])]
    out, rej = script.apply_edits(scenes, {
        "replace": [{"scene": 1, "voiceover": "Milattan sonra altmış yılında büyük bir deprem şehri sarstı ve evler hasar gördü."},
                    {"scene": 2, "voiceover": "Kısa."}],
        "delete": [3, 1],
        "insert_after": [{"scene": 2, "new_scene": {"voiceover": "Üç yüz kişi öldü."}}]}, claims, guard=True)
    assert "altmış iki" in out[0]["voiceover"]                     # yeni kaynaksız sayı (60) reddedildi
    assert out[1]["voiceover"].startswith("Patlama tam")          # kısaltma reddedildi
    assert len(out) == 2                                          # sahne 3 silindi (C2 başka sahnede var), sahne 1 silinmedi
    assert len(rej) == 4                                          # 60, kısaltma, silme(1), ekleme(300)


def test_media_works_are_not_sources():
    dizi = S.Source("u", "Rise of Empires: Ottoman", "Wikipedia", "encyclopedia", "wikipedia",
                    "Rise of Empires: Ottoman is a Turkish historical docudrama television series created for Netflix. "
                    "It depicts the Fall of Constantinople in 1453 and Mehmed II. " * 3)
    tarih = S.Source("u2", "Fall of Constantinople", "Wikipedia", "encyclopedia", "wikipedia",
                     "The Fall of Constantinople was the capture of the capital of the Byzantine Empire by the Ottoman Empire "
                     "in 1453. Constantinople was besieged by Mehmed II. " * 3)
    film = S.Source("u3", "Fetih 1453", "Wikipedia", "encyclopedia", "wikipedia",
                    "Fetih 1453 is a 2012 Turkish epic action film about the Fall of Constantinople. " * 3)
    makale = S.Source("u4", "Ottoman artillery", "J", "academic", "crossref",
                      "This article studies the television series coverage... Constantinople 1453 artillery. " * 3)
    assert research.is_media_work(dizi) and research.is_media_work(film)
    assert not research.is_media_work(tarih)
    assert not research.is_media_work(makale)                     # akademik kaynaklara uygulanmaz
    kept = research.select_sources([dizi, tarih, film], ["Constantinople"])
    assert [k.title for k in kept] == ["Fall of Constantinople"]

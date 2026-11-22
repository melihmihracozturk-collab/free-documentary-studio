"""Öneri biçimi: katalog toplama, sunucu senaryosu, sahne düzenleri, sunucu animasyonu, hareketli grafikler, otomatik ses."""
import re
import subprocess
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from fds_worker import catalog, deliver, llm, motion, presenter, render, research, review, script, tts
from fds_worker import sources as S

from .conftest import make_project, steps
from .test_research import scene

TITLES = [{"ref": "oneri_1", "name": "Frieren", "name_en": "Frieren: Beyond Journey's End", "kind": "anime", "year": 2023,
           "genres": ["Adventure", "Drama"], "score": 90, "score_source": "AniList", "episodes": 28, "studio": "Madhouse",
           "format": "TV anime dizisi", "color": "#bbf1a1"},
          {"ref": "oneri_2", "name": "Dark", "name_en": "Dark", "kind": "series", "year": 2017, "seasons": 3}]


def _review_project(conn):
    pid, job = make_project(conn, "kis-animeleri")
    conn.execute("update projects set format='review', topic='Bu kış izlenecek animeler', title='Kış animeleri', "
                 "target_minutes=8 where id=%s", (pid,))
    return pid, job


# ----------------------------------------------------------------- yapı
def test_review_format_allowed_and_settings(conn):
    pid, _ = _review_project(conn)
    assert conn.execute("select format from projects where id=%s", (pid,)).fetchone()["format"] == "review"
    st = {r["key"]: r["value"] for r in conn.execute("select key, value from settings").fetchall()}
    assert st["presenter_name"] == "Ayla" and st["tts_voice"] == "tr-TR-EmelNeural"


def test_plan_acts_titles_become_chapters():
    acts, titles, plan = review.plan_acts(TITLES, 1000)
    assert acts == ["giris", "oneri_1", "oneri_2", "kapanis"] and titles["oneri_2"] == "Dark"
    assert abs(sum(w for w, _ in plan.values()) - 1000) <= 4 and plan["oneri_1"][0] > plan["giris"][0]


def test_assign_layouts_rules():
    scenes = [{"_act": "giris"}, {"_act": "oneri_1", "layout": "full"}, {"_act": "oneri_1", "layout": "full"},
              {"_act": "oneri_1", "layout": "full"}, {"_act": "oneri_2", "layout": "mood"}, {"_act": "oneri_2", "layout": "bogus"},
              {"_act": "kapanis"}]
    review.assign_layouts(scenes)
    assert [s["layout"] for s in scenes] == ["host", "title", "full", "mood", "title", "poster", "host"]
    assert [s["title_ref"] for s in scenes] == [None, "oneri_1", "oneri_1", "oneri_1", "oneri_2", "oneri_2", None]


def test_shorts_layouts_follow_named_title():
    scenes = [{"voiceover": "Kanca!"}, {"voiceover": "Dark zamanı büküyor."}, {"voiceover": "Dark üç sezon."},
              {"voiceover": "Sonra bir elf büyücü."}, {"voiceover": "Hangisiyle başlarsınız?"}]
    review.shorts_layouts(scenes, TITLES)
    assert [s["layout"] for s in scenes] == ["host", "title", "poster", "title", "host"]
    assert [s["title_ref"] for s in scenes] == [None, "oneri_2", "oneri_2", "oneri_1", None]


# ----------------------------------------------------------------- katalog
class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        return self._d


def test_anilist_parse_and_mismatch(monkeypatch):
    media = {"id": 1, "siteUrl": "https://anilist.co/anime/154587", "isAdult": False, "format": "TV", "episodes": 28,
             "duration": 24, "season": "FALL", "seasonYear": 2023, "source": "MANGA", "genres": ["Adventure", "Fantasy"],
             "averageScore": 90, "title": {"romaji": "Sousou no Frieren", "english": "Frieren: Beyond Journey’s End",
                                           "native": "葬送のフリーレン"},
             "description": "An elf mage <br>outlives her party. (Source: Crunchyroll)",
             "studios": {"nodes": [{"name": "Madhouse"}]}, "coverImage": {"extraLarge": "https://img/x.jpg", "color": "#bbf1a1"}}
    monkeypatch.setattr(catalog.http, "request", lambda *a, **k: Resp({"data": {"Page": {"media": [media]}}}))
    meta, src = catalog.anilist("Frieren: Beyond Journey's End")
    assert meta["episodes"] == 28 and meta["studio"] == "Madhouse" and meta["poster_source"] == "anilist"
    assert src.source_type == "catalog" and "It has 28 episodes" in src.text and "(Source" not in src.text
    assert research.quote_in_text("It has 28 episodes of about 24 minutes each", src.text)
    assert catalog.anilist("Attack on Titan") is None                    # yanlış yapım kabul edilmez


def test_dominant_color_is_vivid():
    from PIL import Image
    img = Image.new("RGB", (60, 90), (20, 20, 20))
    img.paste((40, 160, 230), (10, 10, 50, 80))
    r, g, b = motion.hex_rgb(catalog.dominant_color(img))
    assert b > 180 and r < 90


def test_collect_review_uses_catalogs_and_keeps_media_articles(conn, monkeypatch):
    pid, job = _review_project(conn)
    monkeypatch.setenv("FDS_FAKE_LLM", "1")
    monkeypatch.setattr(llm, "fake_responder", lambda sys, prompt: {"titles": [
        {"name_en": "Frieren", "name_native": "Frieren", "kind": "anime", "year": 2023, "wiki_en": "Frieren"},
        {"name_en": "Imaginary Show", "name_native": "Hayali", "kind": "series", "year": 2020, "wiki_en": "Imaginary Show"}],
        "core_keywords": ["Frieren"]})
    monkeypatch.setattr(catalog, "anilist", lambda q: ({"year": 2023, "episodes": 28, "poster_url": "https://img/f.jpg",
                                                        "poster_source": "anilist", "color": "#bbf1a1"},
                                                       S.Source("https://anilist.co/anime/1", "Frieren", "AniList", "catalog",
                                                                "anilist", "Frieren is a Japanese anime. " * 20))
                        if q == "Frieren" else None)
    monkeypatch.setattr(catalog, "tmdb", lambda *a, **k: None)

    def wiki(q, lang="en", limit=3, site="wikipedia"):
        if "Frieren" not in q:
            return []
        return [S.Source(f"https://{lang}.wikipedia.org/wiki/Frieren", "Frieren", "Wikipedia", "encyclopedia", "wikipedia",
                         "Frieren is a 2023 anime television series. Frieren travels. " * 60, lang=lang)]
    monkeypatch.setattr(S, "wikipedia", wiki)
    out = research.collect(conn, steps(conn, job)["research_collect"]).output
    titles = out["plan"]["titles"]
    assert [t["ref"] for t in titles] == ["oneri_1"] and titles[0]["poster_url"] == "https://img/f.jpg"
    assert any("Imaginary Show" in e for e in out["collector_errors"])        # bulunamayan yapım önerilmez
    assert out["by_type"].get("catalog") == 1 and out["by_type"].get("encyclopedia", 0) >= 1  # eser maddesi elenmedi


# ----------------------------------------------------------------- senaryo
class FakeReview:
    def __init__(self):
        self.calls = []

    def __call__(self, system, prompt):
        if "RECOMMENDATION video in" in prompt and "Chapters (fixed order)" in prompt:
            self.calls.append("outline")
            acts = re.findall(r"^- (\w+) = ", prompt, re.M)
            acts = [a for a in acts if a in ("giris", "kapanis") or a.startswith("oneri_")]
            return {"title": "Kış Animeleri", "logline": "Ayla'nın seçtikleri.",
                    "acts": [{"act": a, "beats": ["sahne"], "claim_refs": ["C1"]} for a in dict.fromkeys(acts)]}
        if "You are writing ONE chapter" in prompt:
            assert "SPOILER-FREE" in prompt and "You are Ayla" in prompt
            n = int(re.search(r"EXACTLY (\d+) scenes", prompt).group(1))
            total = int(re.search(r"total about (\d+) words", prompt).group(1))
            return {"scenes": [{**scene(int(total / script.LENGTH_BOOST) // n, ["C1"]), "layout": "mood"} for _ in range(n)]}
        if "fact-checking EDITOR of a recommendation video" in prompt:
            self.calls.append("edit")
            assert "SPOILER" in prompt
            return {"notes": ["ok"]}
        if "too short" in prompt:
            return {"insert_after": []}
        if "YouTube Shorts" in prompt:
            self.calls.append("shorts")
            assert "quick-fire picks" in prompt and "STANDALONE" in prompt and "full recommendation" not in prompt
            sizes = [int(x) for x in re.search(r"narration lengths in words: \[([^\]]*)\]", prompt).group(1).split(",")]
            return {"title": "Kış", "scenes": [scene(round(w / script.LENGTH_BOOST) if i else w, ["C1"])
                                               for i, w in enumerate(sizes)]}
        raise AssertionError("beklenmeyen istem: " + prompt[:200])


def test_review_script_layouts_saved(conn, monkeypatch):
    pid, job = _review_project(conn)
    conn.execute("update job_steps set output=%s where job_id=%s and step_key='research_collect'",
                 (Jsonb({"plan": {"titles": TITLES}}), job))
    conn.execute("insert into claims (project_id, ref, text, status, category, importance) "
                 "values (%s,'C1','Frieren 28 bölümdür.','weak','context',2)", (pid,))
    monkeypatch.setenv("FDS_FAKE_LLM", "1")
    fake = FakeReview()
    monkeypatch.setattr(llm, "fake_responder", fake)
    # Öneri biçimi yalnızca Shorts üretir: uzun senaryo adımı atlanır
    assert script.script_doc(conn, steps(conn, job)["script_doc"]).output == {"skipped": "Öneri biçimi yalnızca Shorts üretir"}
    p = conn.execute("select * from projects where id=%s", (pid,)).fetchone()
    out = review.script_review(conn, steps(conn, job)["script_doc"], p).output        # uzun yazım kodu yine çalışır
    assert out["format"] == "review" and out["chapters"] == ["Giriş", "Frieren", "Dark", "Kapanış"]
    rows = conn.execute("select act, layout, title_ref from scenes where project_id=%s and kind='doc' order by idx",
                        (pid,)).fetchall()
    assert rows[0]["layout"] == "host" and rows[-1]["layout"] == "host"
    first = {}
    for r in rows:
        first.setdefault(r["act"], r["layout"])
    assert first["oneri_1"] == "title" and first["oneri_2"] == "title"
    assert {r["title_ref"] for r in rows if r["act"].startswith("oneri_")} == {"oneri_1", "oneri_2"}
    sh = script.script_shorts(conn, steps(conn, job)["script_shorts"]).output
    assert "shorts" in fake.calls and sh["scenes"] >= 4
    lay = [r["layout"] for r in conn.execute("select layout from scenes where project_id=%s and kind='shorts' order by idx",
                                             (pid,)).fetchall()]
    assert lay[0] == "host" and lay[-1] == "host" and "title" in lay


def test_review_job_skips_long_video_steps(conn):
    pid, job = _review_project(conn)
    conn.execute("delete from jobs where project_id=%s", (pid,))
    job = conn.execute("select create_pipeline_job(%s) as id", (pid,)).fetchone()["id"]
    st = steps(conn, job)
    assert st["script_doc"]["status"] == "skipped" and st["render_doc"]["status"] == "skipped"
    assert st["script_shorts"]["status"] == "pending" and st["render_shorts"]["status"] == "pending"
    conn.execute("select reset_from_step(%s, 'research_collect')", (job,))             # yeniden başlatınca da atlanır
    assert steps(conn, job)["render_doc"]["status"] == "skipped"
    # Belgesel projeleri etkilenmez
    did, djob = make_project(conn, "belgesel-etkilenmez")
    assert steps(conn, djob)["render_doc"]["status"] == "pending"
    # Seslendirme beklemesi: öneride yalnızca Shorts sesi yeterli
    conn.execute("insert into voiceovers (project_id, kind, storage_key, filename) values (%s,'shorts','k','f')", (pid,))
    assert conn.execute("select input_already_satisfied('voiceover_wait', %s) ok", (pid,)).fetchone()["ok"] is True
    conn.execute("insert into voiceovers (project_id, kind, storage_key, filename) values (%s,'shorts','k','f')", (did,))
    assert conn.execute("select input_already_satisfied('voiceover_wait', %s) ok", (did,)).fetchone()["ok"] is False


# ----------------------------------------------------------------- sunucu
def test_presenter_tracks():
    env = [(0.0, 0.0)] * 20 + [(0.9, 0.1)] * 10 + [(0.4, 0.4)] * 10 + [(0.0, 0.0)] * 10
    m = presenter.mouth_track(env)
    assert m[0] == "rest" and set(m[20:30]) - {"rest"} and m[-1] == "rest"
    assert all(a == b for a, b in zip(m[20:22], m[20:22]))
    brows = presenter.brow_track(env, 25)
    assert brows[21] == "up" and brows[0] == "neutral"
    blinks = presenter.blink_track(25 * 30, 25)
    assert blinks.count("closed") >= 5 and blinks[0] == "open"


def test_presenter_mode_transition():
    tl = [(0, 5, "host"), (5, 10, "full")]
    big = presenter.DOC_STAGE.modes["big"]
    assert presenter.mode_at(tl, 2, presenter.DOC_STAGE) == big
    mid = presenter.mode_at(tl, 5.3, presenter.DOC_STAGE)
    assert big[1] < mid[1] < presenter.DOC_STAGE.modes["hidden"][1]
    assert presenter.mode_at(tl, 7, presenter.DOC_STAGE) == presenter.DOC_STAGE.modes["hidden"]


def test_presenter_draw_and_render(tmp_path):
    pytest.importorskip("cairosvg")
    import numpy as np
    f = presenter.draw(presenter.Pose(scale=0.5, x=0, y=0, angle=3, mouth="wide", eyes="half"), (500, 650))
    assert f.mode == "RGBA" and f.getbbox() is not None
    hidden = presenter.draw(presenter.Pose(scale=0.5, x=900, y=0), (500, 650))
    assert hidden.getbbox() is None
    sr = 16000
    t = np.arange(sr) / sr
    samples = (np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 3 * t) > 0)).astype(np.float32) * 0.3
    small = presenter.Stage(0, 0, 320, 420, {"big": (0.4, 0, 0), "medium": (0.3, 40, 60), "hidden": (0.3, 400, 60)})
    out = tmp_path / "p.webm"
    n = presenter.render(out, 1.0, 10, small, [(0, 0.5, "host"), (0.5, 1.0, "title")], samples, sr)
    assert n == 10 and out.stat().st_size > 1000
    assert 'svg' in presenter.full_svg() and presenter.full_svg().count("<svg") == 1


# ----------------------------------------------------------------- grafikler
@pytest.mark.parametrize("layout", ["host", "title", "poster", "mood", "full"])
def test_motion_layouts_build(layout):
    from PIL import Image
    poster = Image.new("RGB", (460, 650), (200, 120, 60))
    for kind, w, h in (("doc", 1920, 1080), ("shorts", 1080, 1920)):
        bg, move, layers = motion.build(layout, kind, w, h, None if layout == "host" else TITLES[0], poster,
                                        "Kimler sevecek?", 1, "Giriş")
        assert bg.size == (w, h) and move in render.ZOOMS and layers
        assert all(L.img.mode == "RGBA" for L in layers)


def test_motion_card_without_poster_and_render(tmp_path):
    card, pad = motion.poster_card(None, TITLES[1], 300, (90, 60, 160))
    assert card.width == 200 + 8 + 4 * 24 and pad == 48
    fmt = render.Format("doc", 640, 360, 10, 20, 20, 30)
    out = tmp_path / "c.mp4"
    motion.render_scene(out, tmp_path, 1.0, fmt, "title", TITLES[1], None, None, 2, None)
    info = render.probe(out)
    assert info["streams"][0]["width"] == 640 and abs(float(info["format"]["duration"]) - 1.0) < 0.2


def test_info_card_turkish_genres_and_meta():
    assert motion.meta_line(TITLES[0]) == "2023 · TV anime dizisi · 28 bölüm"
    assert motion.meta_line(TITLES[1]) == "2017 · 3 sezon"
    assert motion.tr_upper("giriş") == "GİRİŞ"
    assert motion.info_card(TITLES[0], 1, 600, (120, 90, 200)).height > 300


def test_review_subtitles_stay_left_of_presenter():
    ass = render.to_ass([(0, 1, "Merhaba")], render.REVIEW_DOC)
    assert ",80,860,60,1" in ass
    assert render.fmt_for({"format": "review"}, render.SHORTS) is render.REVIEW_SHORTS
    assert render.fmt_for({"format": "vlog"}, render.DOC) is render.DOC


def test_lofi_music_filter_runs(tmp_path):
    out = tmp_path / "m.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-filter_complex", render.lofi_filter(3) + "[a]", "-map", "[a]",
                    "-t", "3", str(out)], check=True)
    assert out.stat().st_size > 100000


# ----------------------------------------------------------------- otomatik ses
def _tone(text: str, out: Path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=f=300:d={0.2 + len(text) / 50}",
                    "-c:a", "libmp3lame", str(out)], check=True)


def test_tts_synthesize_with_fallback(tmp_path):
    def broken(text, out):
        raise RuntimeError("servis kapalı")
    out = tmp_path / "v.mp3"
    res = tts.synthesize(["Merhaba ben Ayla.", "", "Bugün üç anime var."], out, [("edge", broken), ("gemini", _tone)])
    assert res["provider"] == "gemini" and res["paragraphs"] == 2 and res["fallback_errors"]
    from fds_worker.voiceover import probe_duration
    assert probe_duration(out) > 2 * tts.PAUSE_SEC
    with pytest.raises(RuntimeError, match="Otomatik seslendirme"):
        tts.synthesize(["x"], tmp_path / "y.mp3", [("edge", broken)])


def test_tts_chain_order_from_settings(conn):
    chain, info = tts.synth_for(conn)
    assert [n for n, _ in chain] == ["edge", "gemini"] and info["voice"] == "tr-TR-EmelNeural"
    conn.execute("update settings set value='\"gemini\"' where key='tts_provider'")
    assert [n for n, _ in tts.synth_for(conn)[0]] == ["gemini", "edge"]


def test_review_descriptions_and_promo_license():
    from fds_worker.licenses import allowed, needs_attribution
    d = deliver.doc_description({"title": "Kış animeleri", "format": "review"}, None, None, [], [], [])
    assert "TMDB" in d and "telif" in d and "spoiler" in d
    sd = deliver.shorts_description({"title": "x", "format": "review"}, None)
    assert "#anime" in sd and "TMDB" in sd and "kanalımızdaki videoda" not in sd      # uzun video yok, açıklama kendi başına
    assert allowed("promo")[0] and needs_attribution("promo")


# ----------------------------------------------------------------- uçtan uca (veritabanı + R2 + FFmpeg)
from .test_voiceover import s3  # noqa: F401,E402  (moto S3 fikstürü)


def test_tts_texts_step_creates_voiceovers_and_releases_wait(conn, s3, monkeypatch):  # noqa: F811
    from fds_worker import storage, voiceover
    pid, job = _review_project(conn)
    for kind in ("shorts",):
        sid = conn.execute("insert into scripts (project_id, kind, version, content, approved_at) values (%s,%s,1,'{}',now()) "
                           "returning id", (pid, kind)).fetchone()["id"]
        for i, t in enumerate(["Merhaba, ben Ayla.", "Bugün iki öneri var."], 1):
            conn.execute("insert into scenes (project_id, script_id, kind, idx, voiceover_text) values (%s,%s,%s,%s,%s)",
                         (pid, sid, kind, i, t))
    monkeypatch.setattr(tts, "synth_for", lambda conn: ([("fake", _tone)], {"voice": "fake"}))
    out = voiceover.texts(conn, steps(conn, job)["voiceover_texts"]).output
    assert "doc" not in out["tts"] and out["tts"]["shorts"]["provider"] == "fake" and out["tts"]["shorts"]["paragraphs"] == 2
    vos = conn.execute("select kind, status, storage_key from voiceovers where project_id=%s order by kind", (pid,)).fetchall()
    assert [(v["kind"], v["status"]) for v in vos] == [("shorts", "uploaded")]
    storage.client().head_object(Bucket="fds-test", Key=vos[0]["storage_key"])
    # Bekleme adımı açıldığında sesler hazır olduğu için kendiliğinden geçer
    conn.execute("update job_steps set status='done' where job_id=%s and seq < 80", (job,))
    conn.execute("select refresh_job_status(%s)", (job,))
    assert steps(conn, job)["voiceover_wait"]["status"] == "done"


def test_review_render_end_to_end(conn, s3, tmp_path):  # noqa: F811
    pytest.importorskip("cairosvg")
    import json
    from PIL import Image
    from fds_worker import storage
    pid, job = _review_project(conn)
    slug = "kis-animeleri"
    conn.execute("update job_steps set output=%s where job_id=%s and step_key='research_collect'",
                 (Jsonb({"plan": {"titles": TITLES}}), job))
    texts = ["Merhaba, ben Ayla.", "İlk önerim Frieren.", "Hüzünlü ama sıcak."]
    bounds = [(0.0, 1.5), (1.5, 3.0), (3.0, 4.0)]
    wav = tmp_path / "shorts.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=220:d=4", str(wav)], check=True)
    storage.upload_file(f"projects/{slug}/voiceover/shorts.wav", wav, "audio/wav")
    words = [{"w": w, "s": round(b[0] + 0.1 + k * 0.3, 2), "e": round(b[0] + 0.35 + k * 0.3, 2)}
             for t, b in zip(texts, bounds) for k, w in enumerate(t.split())]
    storage.upload_bytes(f"projects/{slug}/voiceover/shorts_words.json", json.dumps(words).encode())
    conn.execute("insert into voiceovers (project_id, kind, storage_key, filename, bytes, sha256, status, duration_sec, words_key) "
                 "values (%s,'shorts',%s,'shorts.wav',1,'abc','analyzed',4.0,%s)",
                 (pid, f"projects/{slug}/voiceover/shorts.wav", f"projects/{slug}/voiceover/shorts_words.json"))
    img = tmp_path / "poster.jpg"
    Image.new("RGB", (460, 650), (200, 120, 60)).save(img)
    sha = storage.upload_file(f"projects/{slug}/assets/poster.jpg", img, "image/jpeg")
    aid = conn.execute("insert into assets (project_id, kind, storage_key, sha256, status, license_class, source) "
                       "values (%s,'image',%s,%s,'approved','promo','anilist') returning id",
                       (pid, f"projects/{slug}/assets/poster.jpg", sha)).fetchone()["id"]
    for i, (t, (a, b), lay, ref) in enumerate(zip(texts, bounds, ["host", "title", "full"], [None, "oneri_1", "oneri_1"]), 1):
        conn.execute("insert into scenes (project_id, kind, idx, act, voiceover_text, start_sec, end_sec, transition, asset_id, "
                     "layout, title_ref, on_screen_text) values (%s,'shorts',%s,'shorts',%s,%s,%s,'crossfade',%s,%s,%s,%s)",
                     (pid, i, t, a, b, aid if ref else None, lay, ref, "Bleach izlediniz mi?" if i == 1 else None))
    sub = render.subtitles(conn, steps(conn, job)["subtitles"]).output
    assert list(sub) == ["shorts"]                                       # öneride yalnızca Shorts altyazısı
    ass = storage.get_bytes(f"projects/{slug}/subtitles/shorts.ass").decode()
    assert ",80,80,800,1" in ass and "Bleach izlediniz mi?" not in ass    # ekran yazısı grafikte, altyazıda değil
    assert render.render_doc(conn, steps(conn, job)["render_doc"]).output == {"skipped": "Öneri biçimi yalnızca Shorts üretir"}
    out = render.render_shorts(conn, steps(conn, job)["render_shorts"])
    assert out.output["presenter"] is True and out.output["clips_rendered"] == 3
    assert abs(out.output["duration_sec"] - 4.0) < 0.3
    r = conn.execute("select kind, width, height, status from renders where project_id=%s", (pid,)).fetchall()
    assert [(x["kind"], x["width"], x["height"], x["status"]) for x in r] == [("shorts", 1080, 1920, "done")]
    done = deliver.ready(conn, steps(conn, job)["preview_ready"]).output   # teslim: uzun video beklenmez
    assert "shorts_description.txt" in done["files"] and "youtube_description.txt" not in done["files"]
    assert done["doc_seconds"] is None and done["shorts_seconds"] > 3


def test_long_title_words_shrink_to_fit():
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    f, lines = motion.fit_font(d, "Bleach: Thousand-Year Blood War", 66, 360, 3)
    assert f.size < 66 and all(d.textlength(ln, font=f) <= 360 for ln in lines) and len(lines) <= 3

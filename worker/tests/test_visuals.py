"""Görsel eşleştirme testleri: arşivler sahte (ağ yok), lisans filtresi, puanlama, tekrar önleme, atıf, indirme."""
import io

import pytest

from fds_worker import http, images, storage, visuals as VZ
from fds_worker.images import ImageCandidate

from .conftest import make_project, steps
from .test_voiceover import s3  # noqa: F401  (moto S3 fikstürü)


def cand(title, source="commons", lic="cc0", w=3000, h=2000, url=None, desc=""):
    return ImageCandidate(source=source, title=title, page_url=f"https://src/{title}", file_url=url or f"https://img/{title}.jpg",
                          thumb_url=f"https://img/{title}_t.jpg", license_raw=lic, license_class=lic, author="Yazar",
                          attribution=f"{title} — Yazar — {lic}", width=w, height=h, description=desc)


def test_queries_for_adds_topic():
    sc = {"search_keywords": ["volcano eruption painting", "Pompeii fresco"]}
    q = VZ.queries_for(sc, ["Pompeii", "Vesuvius"])
    assert q[0] == "Pompeii volcano eruption painting" and q[1] == "Pompeii fresco" and q[-1] == "Pompeii"


def test_score_prefers_relevant_high_res_cc0():
    sc = {"search_keywords": ["Vesuvius eruption painting"], "visual_description": "painting of the eruption"}
    core = ["Vesuvius"]
    good = cand("Eruption of Vesuvius painting", "met", "cc0", 4000, 3000)
    low = cand("Eruption of Vesuvius painting", "openverse", "by", 800, 600)
    off = cand("Portrait of a lady", "met", "cc0", 4000, 3000)
    assert VZ.score(good, sc, core, "doc") > VZ.score(low, sc, core, "doc") > 0
    assert VZ.score(good, sc, core, "doc") > VZ.score(off, sc, core, "doc")


def _setup(conn):
    pid, job = make_project(conn)
    conn.execute("update job_steps set output=%s::jsonb where job_id=%s and step_key='research_collect'",
                 ('{"plan": {"core_keywords": ["Pompeii", "Vesuvius"]}}', job))
    for kind, n in (("doc", 3), ("shorts", 2)):
        for i in range(1, n + 1):
            conn.execute("insert into scenes (project_id, kind, idx, voiceover_text, visual_description, search_keywords) "
                         "values (%s,%s,%s,'metin','eruption painting',%s)", (pid, kind, i, ["Vesuvius eruption painting"]))
    return pid, job


def fake_archives(monkeypatch, pool):
    calls = []

    def mk(name):
        def f(q):
            calls.append((name, q))
            return [c for c in pool if c.source == name]
        return f
    monkeypatch.setattr(VZ, "SEARCHERS", {"met": mk("met"), "commons": mk("commons"), "smithsonian": mk("smithsonian")})
    monkeypatch.setattr(images, "openverse", mk("openverse"))
    return calls


def test_match_filters_licenses_and_avoids_reuse(conn, monkeypatch):
    pid, job = _setup(conn)
    pool = [cand("Vesuvius eruption painting A", "met", "cc0"), cand("Vesuvius eruption painting B", "commons", "pd"),
            cand("Vesuvius eruption painting C", "commons", "by-sa"),
            cand("Vesuvius eruption painting NC", "commons", "nc"), cand("Vesuvius eruption painting ND", "commons", "nd"),
            cand("Vesuvius eruption painting X", "commons", "unknown")]
    calls = fake_archives(monkeypatch, pool)
    VZ.plan(conn, steps(conn, job)["visual_plan"])
    res = VZ.match(conn, steps(conn, job)["asset_match"]).output
    assert res["assigned"] == 5 and res["missing"] == []
    lic = {r["license_class"] for r in conn.execute("select license_class from assets where project_id=%s", (pid,)).fetchall()}
    assert lic <= {"cc0", "pd", "by-sa"}                                     # NC, ND, bilinmeyen elendi
    doc = conn.execute("select a.file_url from scenes s join assets a on a.id=s.asset_id where s.project_id=%s and s.kind='doc'",
                       (pid,)).fetchall()
    assert len({r["file_url"] for r in doc}) == 3                            # aynı belgeselde tekrar yok
    # Aynı sorgu önbellekten gelir: arşiv başına sorgu sayısı sahne sayısından az
    assert len(calls) < 5 * 3 * 2
    credits = VZ.write_credits(conn, pid, "pompei-son-gunu")
    assert "Belgesel sahne 1" in credits and "Lisans:" in credits


def test_match_reports_missing_when_no_allowed_images(conn, monkeypatch):
    pid, job = _setup(conn)
    fake_archives(monkeypatch, [cand("Vesuvius eruption painting ND", "commons", "nd")])
    res = VZ.match(conn, steps(conn, job)["asset_match"]).output
    assert res["assigned"] == 0 and len(res["missing"]) == 5


def test_nc_allowed_only_when_setting_on(conn, monkeypatch):
    pid, job = _setup(conn)
    fake_archives(monkeypatch, [cand(f"Vesuvius eruption painting {i}", "commons", "nc") for i in range(6)])
    assert VZ.match(conn, steps(conn, job)["asset_match"]).output["assigned"] == 0
    conn.execute("update settings set value='true'::jsonb where key='license_allow_nc'")
    assert VZ.match(conn, steps(conn, job)["asset_match"]).output["assigned"] == 5


def test_download_resizes_and_uploads(conn, s3, monkeypatch):  # noqa: F811
    from PIL import Image
    pid, job = _setup(conn)
    fake_archives(monkeypatch, [cand(f"Vesuvius eruption painting {i}", "met", "cc0") for i in range(4)])
    big = io.BytesIO()
    Image.new("RGB", (5000, 3000), (200, 80, 40)).save(big, "PNG")

    class R:
        content = big.getvalue()
    monkeypatch.setattr(http, "request", lambda *a, **k: R())
    res = VZ.match(conn, steps(conn, job)["asset_match"]).output
    assert res["downloaded"] == 5
    a = conn.execute("select a.* from scenes s join assets a on a.id=s.asset_id where s.project_id=%s limit 1", (pid,)).fetchone()
    assert a["width"] == 2560 and a["height"] == 1536 and a["storage_key"].endswith(".jpg") and a["sha256"]
    body = storage.client().get_object(Bucket="fds-test", Key="projects/pompei-son-gunu/assets/credits.txt")["Body"].read()
    assert b"CC0" in body or b"cc0" in body


def test_commons_title_cleanup(monkeypatch):
    page = {"title": "File:The_Eruption_of_Vesuvius.jpg", "imageinfo": [{
        "mime": "image/jpeg", "url": "https://u/full.jpg", "thumburl": "https://u/2560px-x.jpg", "descriptionurl": "https://c/File",
        "width": 3000, "height": 2000, "extmetadata": {
            "ObjectName": {"value": '<span>label QS:Len,"The Eruption of Vesuvius"</span>'},
            "LicenseShortName": {"value": "Public domain"}, "Artist": {"value": "<a href='x'>Pierre-Jacques Volaire</a>"}}}]}
    monkeypatch.setattr(http, "get_json", lambda *a, **k: {"query": {"pages": {"1": page}}})
    c = images.commons("Vesuvius")[0]
    assert c.title == "The Eruption of Vesuvius" and c.license_class == "pd" and c.author == "Pierre-Jacques Volaire"


def test_commons_thumb_from_original():
    u = "https://upload.wikimedia.org/wikipedia/commons/c/cd/%27Vesuvius%27_by_Dahl.JPG?utm_source=commons.wikimedia.org"
    assert images.commons_thumb(u) == ("https://upload.wikimedia.org/wikipedia/commons/thumb/c/cd/%27Vesuvius%27_by_Dahl.JPG/"
                                       "500px-%27Vesuvius%27_by_Dahl.JPG")
    assert images.commons_thumb("https://upload.wikimedia.org/wikipedia/commons/a/ab/Map.tif") .endswith("Map.tif")   # tif: dokunma


def test_commons_download_url_uses_standard_thumbs():
    orig = "https://upload.wikimedia.org/wikipedia/commons/5/5b/Colonna_Ionica_a_Pompei.jpg?utm_source=x"
    assert images.commons_download_url(orig, 3000).endswith("/1920px-Colonna_Ionica_a_Pompei.jpg")
    assert images.commons_download_url(orig, 5000).endswith("/3840px-Colonna_Ionica_a_Pompei.jpg")
    assert images.commons_download_url(orig, 1000).endswith("/960px-Colonna_Ionica_a_Pompei.jpg")
    t = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/X.jpg/3840px-X.jpg"
    assert images.commons_download_url(t, 5000) == t


def test_download_falls_back_to_1920(conn, s3, monkeypatch):  # noqa: F811
    from PIL import Image
    pid, job = _setup(conn)
    orig = "https://upload.wikimedia.org/wikipedia/commons/5/5b/Ruins.jpg"
    fake_archives(monkeypatch, [cand("Vesuvius eruption painting R", "commons", "pd", w=5000, url=orig)])
    buf = io.BytesIO(); Image.new("RGB", (1920, 1280)).save(buf, "JPEG")
    asked = []

    class R:
        content = buf.getvalue()

    def req(method, url, **k):
        asked.append(url)
        if "3840px" in url:
            raise http.RateLimited("429")
        return R()
    monkeypatch.setattr(http, "request", req)
    res = VZ.match(conn, steps(conn, job)["asset_match"]).output
    assert res["downloaded"] >= 1
    assert any("3840px-Ruins.jpg" in u for u in asked) and any("1920px-Ruins.jpg" in u for u in asked)
    assert not any(u == orig for u in asked)                                 # orijinale hiç gidilmedi

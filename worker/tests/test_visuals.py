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
    assert "volcano eruption painting" in q                  # önekli sorgu boş dönerse sahnenin kendi sorgusu


def test_match_reuses_best_image_instead_of_leaving_scene_empty(conn, monkeypatch):
    pid, job = _setup(conn)
    fake_archives(monkeypatch, [cand("Vesuvius eruption painting A", "met", "cc0")])   # 3 sahneye tek görsel
    VZ.plan(conn, steps(conn, job)["visual_plan"])
    res = VZ.match(conn, steps(conn, job)["asset_match"]).output
    assert res["missing"] == [] and res["assigned"] == 5
    assert res["reused"] == ["doc#2", "doc#3", "shorts#2"]


def test_score_prefers_relevant_high_res_cc0():
    sc = {"search_keywords": ["Vesuvius eruption painting"], "visual_description": "painting of the eruption"}
    core = ["Vesuvius"]
    good = cand("Eruption of Vesuvius painting", "met", "cc0", 4000, 3000)
    low = cand("Eruption of Vesuvius painting", "openverse", "by", 800, 600)
    off = cand("Portrait of a lady", "met", "cc0", 4000, 3000)
    assert VZ.score(good, sc, core, "doc") > VZ.score(low, sc, core, "doc") > 0
    assert VZ.score(good, sc, core, "doc") > VZ.score(off, sc, core, "doc")


def test_topic_phrase_not_split_into_generic_words():
    core = ["Committee of Union and Progress", "İttihat ve Terakki"]
    sc = {"search_keywords": ["Talaat Pasha portrait"], "visual_description": "portrait of Talaat"}
    off = cand("The Progress of the Century – The Lightning Steam Press", "met", "cc0", 4000, 3000)
    on = cand("Members of the Central Committee of the Committee of Union and Progress", "commons", "pd", 2000, 1500)
    tr = cand("İttihat ve Terakki amblemi", "commons", "pd", 1000, 1000)
    talaat = cand("Talaat Pasha 1915", "commons", "pd", 1200, 1600)
    assert VZ.relevance(off, sc, core) == (0.0, 0.0)
    assert VZ.relevance(on, sc, core)[1] == 1.0 and VZ.relevance(tr, sc, core)[1] == 1.0
    assert VZ.relevance(talaat, sc, core)[0] > 0
    assert VZ.score(talaat, sc, core, "doc") > VZ.score(off, sc, core, "doc")


def test_match_prefers_reusing_relevant_over_unrelated(conn, monkeypatch):
    pid, job = _setup(conn)
    fake_archives(monkeypatch, [cand("Vesuvius eruption painting A", "met", "cc0"),
                                cand("Pilgrim vase", "met", "cc0"), cand("Jardiniere", "met", "cc0")])
    VZ.plan(conn, steps(conn, job)["visual_plan"])
    VZ.match(conn, steps(conn, job)["asset_match"])
    titles = {r["title"] for r in conn.execute("select a.title from scenes s join assets a on a.id=s.asset_id "
                                               "where s.project_id=%s", (pid,)).fetchall()}
    assert titles == {"Vesuvius eruption painting A"}                     # vazo seçilmez


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


def test_set_image_assigns_manual_commons_file(conn, monkeypatch):
    from fds_worker import set_image
    pid, job = _setup(conn)
    slug = conn.execute("select slug from projects where id=%s", (pid,)).fetchone()["slug"]
    monkeypatch.setattr(images, "commons_file", lambda t: cand("Talat Pasha", "commons", "pd", 2560, 1834))
    msg = set_image.assign(conn, slug, "doc", 2, "File:Talat Pasha.jpg")
    assert "doc#2" in msg
    row = conn.execute("select a.title, a.status from scenes s join assets a on a.id=s.asset_id "
                       "where s.project_id=%s and s.kind='doc' and s.idx=2", (pid,)).fetchone()
    assert row["title"] == "Talat Pasha" and row["status"] == "approved"
    monkeypatch.setattr(images, "commons_file", lambda t: cand("Kısıtlı", "commons", "nd"))
    with pytest.raises(SystemExit):                                    # ND lisans reddedilir
        set_image.assign(conn, slug, "doc", 3, "File:X.jpg")


def test_download_reuses_already_downloaded_same_file(conn, s3, monkeypatch):  # noqa: F811
    from PIL import Image
    pid, job = _setup(conn)
    fake_archives(monkeypatch, [cand(f"Vesuvius eruption painting {i}", "met", "cc0") for i in range(4)])
    img = io.BytesIO()
    Image.new("RGB", (800, 600)).save(img, "PNG")
    calls = []

    class R:
        content = img.getvalue()

    def req(*a, **k):
        calls.append(a)
        return R()
    monkeypatch.setattr(http, "request", req)
    VZ.match(conn, steps(conn, job)["asset_match"])
    n = len(calls)
    # Shorts sahnesine belgeselde indirilmiş görselin yeni bir kaydı atanır (panelde seçilen aday gibi)
    a = conn.execute("select a.* from scenes s join assets a on a.id=s.asset_id where s.project_id=%s and s.kind='doc' "
                     "and s.idx=1", (pid,)).fetchone()
    sh = conn.execute("select id from scenes where project_id=%s and kind='shorts' and idx=1", (pid,)).fetchone()
    new = conn.execute("insert into assets (project_id, scene_id, kind, source, title, file_url, license_class, status) "
                       "values (%s,%s,'image','met',%s,%s,'cc0','approved') returning id",
                       (pid, sh["id"], a["title"], a["file_url"])).fetchone()["id"]
    conn.execute("update scenes set asset_id=%s where id=%s", (new, sh["id"]))
    assert VZ.download_selected(conn, pid, "pompei-son-gunu") == 1
    assert len(calls) == n                                                    # yeniden indirilmedi
    got = conn.execute("select storage_key from assets where id=%s", (new,)).fetchone()["storage_key"]
    assert got == a["storage_key"]


def test_download_tries_thumb_host_when_upload_host_limited(conn, s3, monkeypatch):  # noqa: F811
    from PIL import Image
    pid, job = _setup(conn)
    orig = "https://upload.wikimedia.org/wikipedia/commons/f/fb/Ottoman_artillery.jpg"
    fake_archives(monkeypatch, [cand("Vesuvius eruption painting O", "commons", "pd", w=3675, url=orig)])
    buf = io.BytesIO(); Image.new("RGB", (1920, 1318)).save(buf, "JPEG")

    class R:
        content = buf.getvalue()

    def req(method, url, **k):
        if url.startswith("https://upload.wikimedia.org/"):
            raise http.RateLimited("upload.wikimedia.org: 429")
        return R()
    monkeypatch.setattr(http, "request", req)
    res = VZ.match(conn, steps(conn, job)["asset_match"]).output
    assert res["downloaded"] >= 1


def test_set_image_after_approval_needs_force(conn, monkeypatch):
    from fds_worker import set_image
    pid, job = _setup(conn)
    slug = conn.execute("select slug from projects where id=%s", (pid,)).fetchone()["slug"]
    conn.execute("update job_steps set status='done' where job_id=%s and step_key='visual_review'", (job,))
    monkeypatch.setattr(images, "commons_file", lambda t: cand("Roman Forum", "commons", "by", 3000, 2000))
    with pytest.raises(SystemExit):
        set_image.assign(conn, slug, "doc", 1, "File:Roman Forum.jpg")
    assert "doc#1" in set_image.assign(conn, slug, "doc", 1, "File:Roman Forum.jpg", force=True)


def test_user_upload_is_normalized_and_raw_deleted(conn, s3):  # noqa: F811
    from PIL import Image
    pid, job = _setup(conn)
    sc = conn.execute("select id from scenes where project_id=%s and kind='doc' and idx=1", (pid,)).fetchone()
    raw = io.BytesIO()
    Image.new("RGB", (6000, 4000), (10, 120, 200)).save(raw, "PNG")
    raw_key = "projects/pompei-son-gunu/uploads/abc.png"
    storage.upload_bytes(raw_key, raw.getvalue(), "image/png")
    aid = conn.execute("insert into assets (project_id, scene_id, kind, source, title, file_url, license, license_class, status) "
                       "values (%s,%s,'image','upload','Benim fotoğrafım',%s,'Kullanıcı yüklemesi','own','approved') returning id",
                       (pid, sc["id"], "r2:" + raw_key)).fetchone()["id"]
    conn.execute("update scenes set asset_id=%s where id=%s", (aid, sc["id"]))
    assert VZ.download_selected(conn, pid, "pompei-son-gunu") == 1
    a = conn.execute("select * from assets where id=%s", (aid,)).fetchone()
    assert a["storage_key"].endswith(f"{aid}.jpg") and (a["width"], a["height"]) == (2560, 1707)
    keys = [o["Key"] for o in storage.client().list_objects_v2(Bucket="fds-test").get("Contents", [])]
    assert raw_key not in keys                                                 # ham yükleme silindi
    assert "kullanıcı yüklemesi" in VZ.credits_text([{**a, "scene_kind": "doc", "scene_idx": 1}])
    from fds_worker.licenses import allowed, needs_attribution
    assert allowed("own")[0] and not needs_attribution("own")


def test_draft_mode_offers_restricted_and_marks_them(conn, monkeypatch):
    from fds_worker.licenses import allowed, is_restricted
    assert not allowed("nd")[0] and allowed("nd", allow_restricted=True)[0]
    assert is_restricted("restricted") and not is_restricted("by-sa")
    pid, job = _setup(conn)
    press = cand("Vesuvius eruption painting press photo", "web", "restricted", 2400, 1600)
    fake_archives(monkeypatch, [cand("Unrelated vase", "met", "cc0")])
    monkeypatch.setattr(images, "web_pool", lambda urls, limit=30: [press])
    VZ.plan(conn, steps(conn, job)["visual_plan"])
    res = VZ.match(conn, steps(conn, job)["asset_match"]).output
    assert "web_candidates" not in res and res["restricted_chosen"] == 0            # varsayılan: kapalı
    conn.execute("insert into settings (key, value) values ('license_allow_restricted', 'true') "
                 "on conflict (key) do update set value = excluded.value")
    res = VZ.match(conn, steps(conn, job)["asset_match"]).output
    assert res["web_candidates"] == 1 and res["restricted_chosen"] >= 1                # ilgili telifli görsel seçildi
    rows = conn.execute("select a.*, s.kind scene_kind, s.idx scene_idx from scenes s join assets a on a.id=s.asset_id "
                        "where s.project_id=%s order by s.kind, s.idx", (pid,)).fetchall()
    assert "YAYINDAN ÖNCE DEĞİŞTİRİN" in VZ.credits_text(rows)


def test_og_image_extraction(monkeypatch):
    from fds_worker import web

    class R:
        status_code = 200
        url = "https://news.example/tr/haber/1"
        text = ('<html><head><meta property="og:image" content="/img/kongre.jpg">'
                '<meta property="og:title" content="Parti kongresi yapıldı">'
                '<meta property="og:description" content="Kongrede yeni yönetim seçildi."></head>'
                '<body><p>' + "Kongre İstanbul'da toplandı ve yeni yönetim seçildi. " * 3 + '</p></body></html>')
    monkeypatch.setattr(web, "allowed", lambda url: True)
    monkeypatch.setattr(http, "request", lambda *a, **k: R())
    m = web.og_image("https://news.example/tr/haber/1")
    assert m["image"] == "https://news.example/img/kongre.jpg" and m["title"] == "Parti kongresi yapıldı"
    assert "yeni yönetim" in m["description"]

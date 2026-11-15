from fds_worker import deliver as D, storage

from .conftest import make_project, steps
from .test_voiceover import s3  # noqa: F401


def test_chapters_rules():
    scenes = [{"act": "giris", "start_sec": 0}, {"act": "giris", "start_sec": 15}, {"act": "arka_plan", "start_sec": 52},
              {"act": "gelisme", "start_sec": 194}, {"act": "donum_noktasi", "start_sec": 366.5},
              {"act": "sonuclar", "start_sec": 503}, {"act": "kapanis", "start_sec": 628}]
    ch = D.chapters(scenes)
    assert ch[0] == (0.0, "Giriş") and len(ch) == 6
    assert [D.ts(t) for t, _ in ch] == ["0:00", "0:52", "3:14", "6:06", "8:23", "10:28"]
    assert D.chapters([{"act": "giris", "start_sec": 0}, {"act": "kapanis", "start_sec": 5}]) == []   # < 3 bölüm → yok
    assert D.ts(3725) == "1:02:05"


def test_ready_writes_descriptions_and_completes(db_url, conn, s3):  # noqa: F811
    pid, job = make_project(conn)
    for kind, dur in (("doc", 696.3), ("shorts", 59.0)):
        conn.execute("insert into renders (project_id, kind, storage_key, status, duration_sec, bytes) values (%s,%s,'k','done',%s,1)",
                     (pid, kind, dur))
    conn.execute("insert into scripts (project_id, kind, content) values (%s,'doc','{\"logline\": \"Bir şehir bir günde.\"}'),"
                 "(%s,'shorts','{\"title\": \"Pompei 60 saniyede\"}')", (pid, pid))
    conn.execute("insert into research_reports (project_id, summary, markdown) values (%s,'MS 79 yılında Vezüv patladı.','#')", (pid,))
    conn.execute("insert into sources (project_id, url, title, publisher, source_type, ref, published) values "
                 "(%s,'https://doi.org/x','Lethal Thermal Impact','PLoS ONE','academic','S1','2010')", (pid,))
    aid = conn.execute("insert into assets (project_id, kind, title, author, license, license_class, source_url, status) values "
                       "(%s,'image','Pompeii ruins','Jebulon','CC BY 4.0','by','https://commons/x','approved') returning id", (pid,)).fetchone()["id"]
    for i, (act, st) in enumerate([("giris", 0), ("arka_plan", 52), ("gelisme", 194), ("kapanis", 628)], 1):
        conn.execute("insert into scenes (project_id, kind, idx, act, start_sec, asset_id) values (%s,'doc',%s,%s,%s,%s)", (pid, i, act, st, aid))
    out = D.ready(conn, steps(conn, job)["preview_ready"]).output
    assert out["chapters"] == 4
    desc = storage.client().get_object(Bucket="fds-test", Key=out["files"]["youtube_description.txt"])["Body"].read().decode()
    assert "0:00 Giriş" in desc and "3:14 Olayların gelişimi" in desc
    assert "Lethal Thermal Impact — PLoS ONE (2010)" in desc and "Jebulon" in desc and "CC BY 4.0" in desc
    sh = storage.client().get_object(Bucket="fds-test", Key=out["files"]["shorts_description.txt"])["Body"].read().decode()
    assert "#Shorts" in sh and "Pompei 60 saniyede" in sh

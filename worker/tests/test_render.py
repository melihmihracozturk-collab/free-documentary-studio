"""Render testleri: altyazı zamanlaması, SRT/ASS biçimi, zaman çizelgesi ve küçük bir gerçek FFmpeg render'ı."""
import shutil

from .test_voiceover import s3  # noqa: F401  (moto S3 fikstürü)

import pytest

from fds_worker import render as R

TEXTS = ["Gökyüzü karardı ve şehir sustu.", "Genç Plinius patlamayı Misenum'dan izledi, her şeyi yazdı."]


def words_for(texts, t0=0.2, per=0.35, drop=()):
    out, t = [], t0
    for i, s in enumerate(texts):
        for k, w in enumerate(s.split()):
            if (i, k) not in drop:
                out.append((w.strip(".,"), t, t + per * 0.8))
            t += per
        t += 0.5
    return out, t


def test_cues_follow_spoken_times_and_scenes():
    words, end = words_for(TEXTS)
    bounds = [(0.0, 2.3), (2.3, end)]
    cues = R.build_cues(TEXTS, words, bounds, 42)
    assert cues[0][2] == "Gökyüzü karardı ve şehir sustu."          # senaryonun doğru yazımı kullanılır
    assert abs(cues[0][0] - 0.2) < 0.01
    assert all(c[1] <= n[0] for c, n in zip(cues, cues[1:]))         # çakışma yok
    assert all(len(line) <= 42 for c in cues for line in c[2].split("\n"))
    assert not any(TEXTS[0].split()[-1] in c[2] and TEXTS[1].split()[0] in c[2] for c in cues)  # sahneler karışmaz


def test_cues_interpolate_unrecognized_words():
    words, end = words_for(TEXTS, drop={(1, 1), (1, 2), (1, 3)})       # bazı kelimeler tanınmamış
    cues = R.build_cues(TEXTS, words, [(0.0, 2.3), (2.3, end)], 42)
    assert sum(len(c[2].split()) for c in cues) == sum(len(t.split()) for t in TEXTS)   # kelime kaybı yok


def test_srt_and_ass_format():
    cues = [(0.0, 1.5, "Birinci satır"), (61.25, 63.0, "İkinci\nsatır {x}")]
    srt = R.to_srt(cues)
    assert "1\n00:00:00,000 --> 00:00:01,500\nBirinci satır" in srt and "00:01:01,250 --> 00:01:03,000" in srt
    ass = R.to_ass(cues, R.DOC, [(0.3, 4.3, "MS 79 · Pompei")])
    assert "PlayResX: 1920" in ass and "Dialogue: 0,0:01:01.25,0:01:03.00,Default,,0,0,0,,İkinci\\Nsatır (x)" in ass
    assert "Caption" in ass and "MS 79 · Pompei" in ass
    assert R._retime_ass("Dialogue: 0,0:00:10.00,0:00:11.10", 1.1) == "Dialogue: 0,0:00:09.09,0:00:10.09"


def test_timeline_transition_centered_on_boundary():
    bounds = [(0.0, 20.0), (20.0, 45.0), (45.0, 60.0)]
    offsets, lens, trans = R.plan_timeline(bounds, ["crossfade", "crossfade", "cut"], 60.0)
    assert trans[1] == ("fade", 0.8) and trans[2][0] == "fade" and trans[2][1] < 0.2
    assert offsets[1] == pytest.approx(20.0 - 0.4)                    # geçiş sınırın ortasında
    # xfade zinciri: k. klip eklenmeden önceki çıktı uzunluğu = offsets[k] + geçiş süresi
    out_len = lens[0]
    for k in range(1, 3):
        assert out_len == pytest.approx(offsets[k] + trans[k][1], abs=1e-3)
        out_len = offsets[k] + lens[k]
    assert out_len == pytest.approx(60.0, abs=1e-3)                  # toplam = ses süresi


def test_timeline_short_scenes_clamp_transitions():
    offsets, lens, trans = R.plan_timeline([(0, 1.0), (1.0, 1.6), (1.6, 3.0)], ["x", "fade_black", "fade_black"], 3.0)
    assert all(t[1] <= 0.3 + 1e-9 for t in trans[1:])                 # 0.6 sn'lik sahnede geçiş en fazla 0.3 sn
    assert all(x > 0 for x in lens)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg yok")
def test_small_real_render(tmp_path):
    from PIL import Image
    imgs = []
    for i, c in enumerate([(150, 60, 30), (40, 90, 140)]):
        p = tmp_path / f"i{i}.jpg"
        Image.new("RGB", (1600, 1200), c).save(p)
        imgs.append(p)
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=220:d=4", str(tmp_path / "v.wav")], check=True)
    offsets, lens, trans = R.plan_timeline([(0, 2.0), (2.0, 4.0)], ["crossfade", "crossfade"], 4.0)
    clips = []
    for i in range(2):
        R.render_clip(imgs[i], tmp_path / f"c{i}.mp4", lens[i], ["zoom_in", "pan_left"][i], R.DOC, seed=i)
        clips.append(tmp_path / f"c{i}.mp4")
    ass = tmp_path / "s.ass"
    ass.write_text(R.to_ass([(0.1, 1.9, "Altyazı ğüşıöç")], R.DOC))
    R.assemble(clips, lens, offsets, trans, tmp_path / "v.wav", ass, tmp_path / "out.mp4", R.DOC, 4.0)
    info = R.probe(tmp_path / "out.mp4")
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"], v["r_frame_rate"]) == (1920, 1080, "25/1")
    assert abs(float(info["format"]["duration"]) - 4.0) < 0.15


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg yok")
def test_subtitles_and_render_doc_end_to_end(conn, s3, tmp_path):  # noqa: F811
    """Veritabanı + R2 (moto) + gerçek FFmpeg: altyazı adımı ve belgesel render adımı uçtan uca."""
    import json
    import subprocess
    from PIL import Image
    from fds_worker import storage
    from .conftest import make_project, steps

    pid, job = make_project(conn)
    slug = "pompei-son-gunu"
    texts = ["Gökyüzü karardı.", "Şehir küllerin altında kaldı.", "Bugün kalıntılar hikâyeyi anlatıyor."]
    bounds = [(0.0, 1.6), (1.6, 3.4), (3.4, 5.0)]
    wav = tmp_path / "doc.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=200:d=5", str(wav)], check=True)
    storage.upload_file(f"projects/{slug}/voiceover/doc.wav", wav, "audio/wav")
    words = [{"w": w, "s": round(b[0] + 0.1 + k * 0.4, 2), "e": round(b[0] + 0.4 + k * 0.4, 2)}
             for t, b in zip(texts, bounds) for k, w in enumerate(t.split())]
    storage.upload_bytes(f"projects/{slug}/voiceover/doc_words.json", json.dumps(words).encode())
    for kind in ("doc", "shorts"):
        conn.execute("insert into voiceovers (project_id, kind, storage_key, filename, bytes, status, duration_sec, words_key) "
                     "values (%s,%s,%s,'doc.wav',1,'analyzed',5.0,%s)",
                     (pid, kind, f"projects/{slug}/voiceover/doc.wav", f"projects/{slug}/voiceover/doc_words.json"))
    for kind in ("doc", "shorts"):
        for i, (t, (a, b)) in enumerate(zip(texts, bounds), 1):
            img = tmp_path / f"{kind}{i}.jpg"
            Image.new("RGB", (2000, 1400), (40 * i, 60, 90)).save(img)
            key = f"projects/{slug}/assets/{kind}{i}.jpg"
            sha = storage.upload_file(key, img, "image/jpeg")
            aid = conn.execute("insert into assets (project_id, kind, storage_key, sha256, status) values (%s,'image',%s,%s,'approved') "
                               "returning id", (pid, key, sha)).fetchone()["id"]
            conn.execute("insert into scenes (project_id, kind, idx, voiceover_text, start_sec, end_sec, camera_move, transition, "
                         "asset_id, on_screen_text) values (%s,%s,%s,%s,%s,%s,'zoom_in','crossfade',%s,%s)",
                         (pid, kind, i, t, a, b, aid, "MS 79" if i == 1 else None))
    sub = R.subtitles(conn, steps(conn, job)["subtitles"]).output
    assert sub["doc"]["cues"] == 3
    srt = storage.client().get_object(Bucket="fds-test", Key=f"projects/{slug}/subtitles/doc.srt")["Body"].read().decode()
    assert "Gökyüzü karardı." in srt and "-->" in srt

    out = R.render_doc(conn, steps(conn, job)["render_doc"])
    assert out.output["clips_rendered"] == 3 and out.output["clips_reused"] == 0
    assert abs(out.output["duration_sec"] - 5.0) < 0.2 and out.output_key.endswith("renders/documentary.mp4")
    r = conn.execute("select * from renders where project_id=%s", (pid,)).fetchone()
    assert (r["width"], r["height"], r["status"]) == (1920, 1080, "done") and r["bytes"] > 10_000

    assert out.output["clips_deleted"] == 3                                  # başarılı render sonrası ara klipler silindi
    assert r["poster_key"].endswith("doc_contact.jpg")
    storage.client().head_object(Bucket="fds-test", Key=r["poster_key"])

    # Kaldığı yerden devam: render ortasında kesilirse (birleştirme hatası) klipler R2'de kalır ve tekrar kullanılır
    import fds_worker.render as RR
    orig = RR.assemble
    RR.assemble = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kesinti"))
    try:
        with pytest.raises(RuntimeError):
            R.render_doc(conn, steps(conn, job)["render_doc"])
    finally:
        RR.assemble = orig
    out2 = R.render_doc(conn, steps(conn, job)["render_doc"])
    assert out2.output["clips_reused"] == 3 and out2.output["clips_rendered"] == 0


def test_no_orphan_last_word():
    # Pompei render'ında görülen gerçek durum: 76 karakterlik bölme sınırı son kelimede aşılıyordu → "ediyor." tek başına
    t = "Günümüzde bilim insanları bu eşsiz kalıntıları modern yöntemlerle incelemeye devam ediyor."
    words, end = words_for([t])
    cues = R.build_cues([t], words, [(0.0, end)], 42)
    assert all(len(c[2].split()) >= 3 for c in cues), cues           # tek başına "ediyor." kalmaz
    assert all(len(c[2].split("\n")) <= 2 for c in cues)


def test_shorts_tempo_policy():
    assert R.shorts_tempo(55, 60, 1.15) == (1.0, None)                    # sınır içinde: dokunma
    t, w = R.shorts_tempo(66.19, 60, 1.15)                                # Pompei: 66,2 sn
    assert w is None and 1.10 < t < 1.13 and 66.19 / t == pytest.approx(59, abs=0.05)
    t, w = R.shorts_tempo(80, 60, 1.15)                                   # çok uzun: tavan + uyarı
    assert t == 1.15 and "sınırı aşılıyor" in w


def test_vertical_framing_pans_wide_images():
    assert R.frame_move("zoom_in", R.SHORTS, 3000, 2000, 1) == "pan_right"
    assert R.frame_move("zoom_in", R.SHORTS, 3000, 2000, 2) == "pan_left"
    assert R.frame_move("zoom_in", R.SHORTS, 1200, 2000, 1) == "zoom_in"   # dikey görsel: hareket korunur
    assert R.frame_move("zoom_in", R.DOC, 3000, 2000, 1) == "zoom_in"      # belgesel etkilenmez


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg yok")
def test_render_shorts_with_tempo(conn, s3, tmp_path):  # noqa: F811
    """Shorts: 1080x1920 30 fps; ses sınırı aşınca hızlandırılır, altyazı ve sahne zamanları da ölçeklenir."""
    import subprocess
    from PIL import Image
    from fds_worker import storage
    from .conftest import make_project, steps

    pid, job = make_project(conn)
    slug = "pompei-son-gunu"
    conn.execute("update settings set value='4'::jsonb where key='shorts_max_seconds'")
    conn.execute("update settings set value='2'::jsonb where key='shorts_auto_tempo_max'")
    wav = tmp_path / "s.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=300:d=4.4", str(wav)], check=True)
    storage.upload_file(f"projects/{slug}/voiceover/s.wav", wav, "audio/wav")
    conn.execute("insert into voiceovers (project_id, kind, storage_key, filename, bytes, status, duration_sec) "
                 "values (%s,'shorts',%s,'s.wav',1,'analyzed',4.4)", (pid, f"projects/{slug}/voiceover/s.wav"))
    for i, (a, b) in enumerate([(0.0, 2.2), (2.2, 4.4)], 1):
        img = tmp_path / f"i{i}.jpg"
        Image.new("RGB", (3000, 2000), (90, 40 * i, 60)).save(img)
        key = f"projects/{slug}/assets/s{i}.jpg"
        sha = storage.upload_file(key, img, "image/jpeg")
        aid = conn.execute("insert into assets (project_id, kind, storage_key, sha256, width, height, status) "
                           "values (%s,'image',%s,%s,3000,2000,'approved') returning id", (pid, key, sha)).fetchone()["id"]
        conn.execute("insert into scenes (project_id, kind, idx, voiceover_text, start_sec, end_sec, camera_move, transition, asset_id) "
                     "values (%s,'shorts',%s,'metin',%s,%s,'zoom_in','crossfade',%s)", (pid, i, a, b, aid))
    out = R.render_shorts(conn, steps(conn, job)["render_shorts"]).output
    assert out["tempo"] == pytest.approx(4.4 / 3, abs=0.01)
    assert out["duration_sec"] == pytest.approx(3.0, abs=0.15)
    r = conn.execute("select * from renders where project_id=%s and kind='shorts'", (pid,)).fetchone()
    assert (r["width"], r["height"], float(r["fps"])) == (1080, 1920, 30.0)

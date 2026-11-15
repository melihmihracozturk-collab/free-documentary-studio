"""Render motoru (Stage 6): altyazı + sahne klipleri + geçişler + ambiyans + son video. Yalnızca FFmpeg (ücretsiz).

subtitles  : whisper kelime zamanları ile senaryo metnini hizalar → SRT (ayrı dosya) + ASS (videoya gömülür)
render_doc : 1920x1080, 25 fps, H.264/AAC MP4. Her sahne ayrı klip olarak üretilir ve R2'de saklanır;
             render yarıda kalırsa yalnızca eksik klipler yeniden üretilir.

Not: "parallax" bu sürümde gerçek derinlik ayrıştırması değildir; yavaş yakınlaşma + kaydırma olarak uygulanır.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from psycopg.types.json import Jsonb

from . import storage, visuals, voiceover
from .handlers import StepResult

RENDER_VERSION = "r3"          # klip önbellek anahtarına girer; görüntü işleme değişince artırılır


@dataclass(frozen=True)
class Format:
    kind: str
    w: int
    h: int
    fps: int
    font_size: int
    margin_v: int
    max_line: int


DOC = Format("doc", 1920, 1080, 25, 52, 70, 42)
SHORTS = Format("shorts", 1080, 1920, 30, 64, 420, 24)

TRANSITIONS = {"crossfade": ("fade", 0.8), "fade_black": ("fadeblack", 1.0), "dip_white": ("fadewhite", 0.8),
               "wipe": ("wipeleft", 0.7), "slide": ("slideleft", 0.7), "cut": ("fade", 0.12)}


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg hatası ({cmd[0]}): {r.stderr[-800:]}")
    return r.stderr


# ----------------------------------------------------------------- altyazı
Cue = tuple[float, float, str]


def word_times(scene_texts: list[str], words: list[tuple[str, float, float]], bounds: list[tuple[float, float]]):
    """Senaryodaki her kelimeye zaman verir: konuşulan kelimeyle eşleşenler gerçek zamanı, diğerleri ara değer alır."""
    script = [(w, si) for si, t in enumerate(scene_texts) for w in t.split()]
    norm_s = [voiceover._norm(w) for w, _ in script]
    norm_w = [voiceover._norm(w) for w, _, _ in words]
    times: list[tuple[float, float] | None] = [None] * len(script)
    for a, b, size in SequenceMatcher(None, norm_s, norm_w, autojunk=False).get_matching_blocks():
        for k in range(size):
            times[a + k] = (words[b + k][1], words[b + k][2])
    # Eşleşmeyenler: sahne sınırları içinde komşu bilinen zamanlar arasında doğrusal dağıt
    out: list[tuple[float, float]] = []
    i = 0
    while i < len(script):
        if times[i] is not None:
            out.append(times[i])  # type: ignore[arg-type]
            i += 1
            continue
        j = i
        while j < len(script) and times[j] is None:
            j += 1
        si = script[i][1]
        left = out[-1][1] if out and script[i - 1][1] == si else bounds[si][0]
        right = times[j][0] if j < len(script) and script[j][1] == si else bounds[si][1]  # type: ignore[index]
        step = max(0.05, (right - left) / (j - i))
        for k in range(i, j):
            s = left + (k - i) * step
            out.append((s, s + step * 0.9))
        i = j
    return script, out


def build_cues(scene_texts, words, bounds, max_line: int = 42) -> list[Cue]:
    script, times = word_times(scene_texts, words, bounds)
    cues: list[Cue] = []
    cur: list[int] = []

    def flush():
        if not cur:
            return
        text = " ".join(script[k][0] for k in cur)
        lines, line = [], ""
        for w in text.split():
            if line and len(line) + 1 + len(w) > max_line:
                lines.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        lines.append(line)
        cues.append((times[cur[0]][0], times[cur[-1]][1], "\n".join(lines)))
        cur.clear()

    for k, (w, si) in enumerate(script):
        if cur and script[cur[-1]][1] != si:
            flush()                                         # sahne değişince yeni altyazı
        cur.append(k)
        length = len(" ".join(script[x][0] for x in cur))
        if re.search(r"[.!?…]$", w) or length > max_line * 2 - 8 or (re.search(r"[,;:]$", w) and length > max_line):
            flush()
    flush()
    # Çakışma yok, en az 0.8 sn görünür, sonrakinden hemen önce biter
    fixed: list[Cue] = []
    for n, (s, e, t) in enumerate(cues):
        nxt = cues[n + 1][0] if n + 1 < len(cues) else e + 2
        e = min(max(e + 0.15, s + 0.8), nxt - 0.02)
        fixed.append((round(s, 3), round(max(e, s + 0.3), 3), t))
    return fixed


def _ts_srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def _ts_ass(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def to_srt(cues: list[Cue]) -> str:
    return "\n".join(f"{i}\n{_ts_srt(s)} --> {_ts_srt(e)}\n{t}\n" for i, (s, e, t) in enumerate(cues, 1))


def _ass_escape(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def to_ass(cues: list[Cue], fmt: Format, captions: list[Cue] = ()) -> str:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {fmt.w}
PlayResY: {fmt.h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{fmt.font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,{fmt.margin_v},1
Style: Caption,DejaVu Sans,{int(fmt.font_size * 0.75)},&H00E6F2FF,&H000000FF,&H00000000,&H80000000,0,-1,0,0,100,100,1,0,1,2,1,7,80,80,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = [f"Dialogue: 0,{_ts_ass(s)},{_ts_ass(e)},Default,,0,0,0,,{_ass_escape(t)}" for s, e, t in cues]
    ev += [f"Dialogue: 1,{_ts_ass(s)},{_ts_ass(e)},Caption,,0,0,0,,{{\\fad(400,400)}}{_ass_escape(t)}" for s, e, t in captions]
    return head + "\n".join(ev) + "\n"


def captions_for(scenes, bounds) -> list[Cue]:
    """Ekran yazıları (tarih/yer): sahnenin ilk 4 saniyesi, sol üst."""
    out = []
    for sc, (s, e) in zip(scenes, bounds):
        if sc.get("on_screen_text"):
            out.append((s + 0.3, min(e, s + 4.3), str(sc["on_screen_text"])[:60]))
    return out


def _load_words(v) -> list[tuple[str, float, float]]:
    data = json.loads(storage.client().get_object(Bucket=storage.bucket(), Key=v["words_key"])["Body"].read())
    return [(x["w"], x["s"], x["e"]) for x in data]


def subtitles(conn, step) -> StepResult:
    p = conn.execute("select * from projects where id=%s", (step["project_id"],)).fetchone()
    out = {}
    for fmt in (DOC, SHORTS):
        v = conn.execute("select * from voiceovers where project_id=%s and kind=%s and status='analyzed'", (p["id"], fmt.kind)).fetchone()
        if not v or not v["words_key"]:
            raise RuntimeError(f"{fmt.kind} seslendirmesi analiz edilmemiş")
        scenes = conn.execute("select * from scenes where project_id=%s and kind=%s order by idx", (p["id"], fmt.kind)).fetchall()
        bounds = [(float(s["start_sec"]), float(s["end_sec"])) for s in scenes]
        cues = build_cues([s["voiceover_text"] for s in scenes], _load_words(v), bounds, fmt.max_line)
        srt_key = storage.project_key(p["slug"], "subtitles", f"{fmt.kind}.srt")
        ass_key = storage.project_key(p["slug"], "subtitles", f"{fmt.kind}.ass")
        storage.upload_bytes(srt_key, to_srt(cues).encode(), "application/x-subrip; charset=utf-8")
        storage.upload_bytes(ass_key, to_ass(cues, fmt, captions_for(scenes, bounds)).encode(), "text/plain; charset=utf-8")
        out[fmt.kind] = {"cues": len(cues), "srt_key": srt_key, "ass_key": ass_key}
    return StepResult(output=out)


# ----------------------------------------------------------------- görüntü hareketi
ZOOMS = {"zoom_in": (1.0, 1.18), "zoom_out": (1.18, 1.0), "ken_burns": (1.04, 1.16), "parallax": (1.08, 1.16),
         "static": (1.04, 1.06), "pan_left": (1.2, 1.2), "pan_right": (1.2, 1.2), "pan_up": (1.2, 1.2), "pan_down": (1.2, 1.2)}


SUPERSAMPLE = 3     # zoompan tamsayı koordinatlarla çalışır; 3x iç çözünürlükte adımlar 1/3 piksele iner (titreme yok)


def motion_filter(move: str, dur: float, fmt: Format, seed: int = 0) -> tuple[str, int]:
    """Ken Burns hareketi (zoompan). Görsel önce kadrajı dolduracak şekilde 3x çözünürlüğe getirilip tam çıktı oranında
    kırpılır; böylece zoom=1 tüm kadrajdır ve kare boyutu hiç değişmez. Dönüş: (filtre, kare sayısı)."""
    W, H = fmt.w, fmt.h
    n = max(2, int(round(dur * fmt.fps)))
    e = f"(0.5-0.5*cos(PI*on/{n - 1}))"                           # yumuşak başla/bitir (0→1)
    z0, z1 = ZOOMS.get(move, (1.12, 1.12))
    z = f"{z0}+{z1 - z0:.4f}*{e}"
    if move in ("pan_left", "pan_right"):
        fx, fy = (e if move == "pan_right" else f"(1-{e})"), "0.5"
    elif move in ("pan_up", "pan_down"):
        fx, fy = "0.5", (e if move == "pan_down" else f"(1-{e})")
    elif move in ("ken_burns", "parallax"):
        dx = 1 if seed % 2 == 0 else -1
        fx, fy = f"(0.5+{0.35 * dx}*({e}-0.5))", f"(0.5-0.25*({e}-0.5))"
    else:
        fx, fy = "0.5", "0.5"
    SW, SH = W * SUPERSAMPLE, H * SUPERSAMPLE
    vf = (f"scale={SW}:{SH}:force_original_aspect_ratio=increase:flags=bicubic,crop={SW}:{SH},"
          f"zoompan=z='{z}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d={n}:s={W}x{H}:fps={fmt.fps},"
          f"setsar=1,format=yuv420p")
    return vf, n


def render_clip(img: Path, out: Path, dur: float, move: str, fmt: Format, seed: int = 0) -> None:
    vf, n = motion_filter(move, dur, fmt, seed)
    run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", str(img), "-vf", vf, "-frames:v", str(n), "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(fmt.fps), str(out)])


# ----------------------------------------------------------------- ses
def ambient_filter(dur: float) -> str:
    """Telifsiz ambiyans: yavaş nefes alan alçak tonlar + kahverengi gürültü + yankı. Tamamen FFmpeg ile üretilir."""
    d = f"{dur + 1:.2f}"
    return (f"aevalsrc='0.10*sin(2*PI*55*t)*(0.6+0.4*sin(2*PI*0.05*t))+0.06*sin(2*PI*82.41*t)*(0.6+0.4*sin(2*PI*0.033*t+1))"
            f"+0.035*sin(2*PI*110*t)*(0.5+0.5*sin(2*PI*0.021*t+2))':s=48000:d={d},aformat=channel_layouts=stereo[tones];"
            f"anoisesrc=color=brown:amplitude=0.05:d={d}:r=48000,lowpass=f=320,aformat=channel_layouts=stereo[noise];"
            f"[tones][noise]amix=inputs=2:normalize=0,aecho=0.8:0.6:90|170:0.25|0.18,"
            f"afade=t=in:d=3,afade=t=out:st={max(0, dur - 4):.2f}:d=4,volume=0.55")


# ----------------------------------------------------------------- birleştirme
def assemble(clips: list[Path], lens: list[float], starts: list[float], trans: list[tuple[str, float]], audio: Path,
             ass: Path | None, out: Path, fmt: Format, duration: float, tempo: float = 1.0, ambient: bool = True) -> None:
    """Klipleri xfade ile birleştirir; renk/grain/vinyet, altyazı, ses miksajı (ducking + loudnorm)."""
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    inputs += ["-i", str(audio)]
    ai = len(clips)
    fg, last = [], "[0:v]"
    for k in range(1, len(clips)):
        name, td = trans[k]
        lbl = f"[x{k}]"
        fg.append(f"{last}[{k}:v]xfade=transition={name}:duration={td:.3f}:offset={starts[k]:.3f}{lbl}")
        last = lbl
    look = "eq=contrast=1.06:saturation=0.92:gamma=0.98,vignette=angle=PI/5,noise=alls=7:allf=t"
    sub = f",subtitles=filename='{ass}'" if ass else ""
    fg.append(f"{last}{look}{sub},trim=duration={duration:.3f},format=yuv420p[vout]")
    voice = f"[{ai}:a]aresample=48000,aformat=channel_layouts=stereo" + (f",atempo={tempo:.4f}" if abs(tempo - 1) > 1e-3 else "")
    if ambient:
        fg.append(f"{voice},asplit=2[v1][vsc]")
        fg.append(ambient_filter(duration) + "[amb]")
        fg.append("[amb][vsc]sidechaincompress=threshold=0.02:ratio=10:attack=30:release=600:makeup=1[duck]")
        fg.append("[v1][duck]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    else:
        fg.append(f"{voice},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fg),
         "-map", "[vout]", "-map", "[aout]", "-r", str(fmt.fps), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
         "-t", f"{duration:.3f}", str(out)])


def plan_timeline(bounds: list[tuple[float, float]], transitions: list[str], duration: float):
    """Klip uzunlukları ve geçişler. Geçiş, sahne sınırının ORTASINA yerleşir: yarısı önceki sahnenin sonunda,
    yarısı yeni sahnenin başında; böylece yeni görsel, anlatımı başladıktan en geç td/2 sonra tam görünür.

    Dönüş: (offsets, lens, trans) — offsets[k]: k. klibin çıktıdaki başlangıcı (xfade offset), lens[k]: klip süresi.
    """
    n = len(bounds)
    starts = [0.0] + [b[0] for b in bounds[1:]]
    trans = [("none", 0.0)] + [TRANSITIONS.get(t or "crossfade", TRANSITIONS["crossfade"]) for t in transitions[1:]]
    # Geçiş süresi komşu sahnelerin yarısını aşamaz
    for k in range(1, n):
        prev_len = starts[k] - starts[k - 1]
        next_len = (starts[k + 1] if k + 1 < n else duration) - starts[k]
        trans[k] = (trans[k][0], max(0.04, min(trans[k][1], prev_len * 0.5, next_len * 0.5)))
    half = [trans[k][1] / 2 if k else 0.0 for k in range(n)] + [0.0]
    offsets = [starts[k] - half[k] for k in range(n)]
    lens = []
    for k in range(n):
        end = (starts[k + 1] + half[k + 1]) if k + 1 < n else duration
        lens.append(round(end - offsets[k], 3))
    return offsets, lens, trans


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _clip_key(slug: str, kind: str, idx: int, asset_sha: str, dur: float, move: str) -> str:
    h = hashlib.sha256(f"{RENDER_VERSION}|{asset_sha}|{dur:.3f}|{move}".encode()).hexdigest()[:16]
    return storage.project_key(slug, "scenes", kind, f"{idx:03d}-{h}.mp4")


def _exists(key: str) -> bool:
    try:
        storage.client().head_object(Bucket=storage.bucket(), Key=key)
        return True
    except Exception:  # noqa: BLE001
        return False


def render_video(conn, step, fmt: Format, out_name: str, tempo: float = 1.0) -> StepResult:
    p = conn.execute("select * from projects where id=%s", (step["project_id"],)).fetchone()
    if not storage.configured():
        raise RuntimeError("R2 yapılandırılmamış")
    v = conn.execute("select * from voiceovers where project_id=%s and kind=%s and status='analyzed'", (p["id"], fmt.kind)).fetchone()
    if not v:
        raise RuntimeError("Analiz edilmiş gerçek seslendirme yok")       # (veritabanı kuralı da render'ı engeller)
    visuals.download_selected(conn, p["id"], p["slug"])                   # eksik görselleri tamamla
    scenes = conn.execute("select s.*, a.storage_key as img_key, a.sha256 as img_sha from scenes s left join assets a "
                          "on a.id = s.asset_id where s.project_id=%s and s.kind=%s order by s.idx", (p["id"], fmt.kind)).fetchall()
    missing = [s["idx"] for s in scenes if not s["img_key"]]
    if missing:
        raise RuntimeError(f"Görseli indirilmemiş sahneler: {missing}")
    duration = float(v["duration_sec"]) / tempo
    bounds = [(float(s["start_sec"]) / tempo, float(s["end_sec"]) / tempo) for s in scenes]
    starts, lens, trans = plan_timeline(bounds, [s["transition"] for s in scenes], duration)

    reused = rendered = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clips = []
        for i, s in enumerate(scenes):
            key = _clip_key(p["slug"], fmt.kind, s["idx"], s["img_sha"] or s["img_key"], lens[i], s["camera_move"] or "static")
            path = tmp / f"clip{i:03d}.mp4"
            if _exists(key):                                              # kaldığı yerden devam
                storage.download(key, path)
                reused += 1
            else:
                img = storage.download(s["img_key"], tmp / f"img{i:03d}.jpg")
                render_clip(img, path, lens[i], s["camera_move"] or "static", fmt, seed=s["idx"])
                storage.upload_file(key, path, "video/mp4")
                rendered += 1
            clips.append(path)
        audio = storage.download(v["storage_key"], tmp / ("voice" + Path(v["storage_key"]).suffix))
        ass_key = storage.project_key(p["slug"], "subtitles", f"{fmt.kind}.ass")
        ass = storage.download(ass_key, tmp / f"{fmt.kind}.ass") if _exists(ass_key) else None
        if ass and abs(tempo - 1) > 1e-3:
            ass.write_text(_retime_ass(ass.read_text(), tempo))
        out = tmp / out_name
        assemble(clips, lens, starts, trans, audio, ass, out, fmt, duration, tempo=tempo)

        info = probe(out)
        got = float(info["format"]["duration"])
        vs = next(x for x in info["streams"] if x["codec_type"] == "video")
        if abs(got - duration) > 1.0 or (vs["width"], vs["height"]) != (fmt.w, fmt.h):
            raise RuntimeError(f"Çıktı kontrolü başarısız: süre {got:.1f}/{duration:.1f} sn, {vs['width']}x{vs['height']}")
        key = storage.project_key(p["slug"], "renders" if fmt.kind == "doc" else "shorts", out_name)
        sha = storage.upload_file(key, out, "video/mp4")
        size = out.stat().st_size
    conn.execute("delete from renders where project_id=%s and kind=%s", (p["id"], fmt.kind))
    conn.execute("insert into renders (project_id, kind, storage_key, width, height, fps, duration_sec, bytes, sha256, status) "
                 "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'done')", (p["id"], fmt.kind, key, fmt.w, fmt.h, fmt.fps, got, size, sha))
    return StepResult(output={"duration_sec": round(got, 2), "bytes": size, "clips_rendered": rendered, "clips_reused": reused,
                              "scenes": len(scenes), "tempo": tempo, "codec": vs["codec_name"]},
                      output_key=key, sha256=sha)


def _retime_ass(text: str, tempo: float) -> str:
    def conv(m):
        h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return _ts_ass((h * 3600 + mi * 60 + s + cs / 100) / tempo)
    return re.sub(r"(\d+):(\d{2}):(\d{2})\.(\d{2})", conv, text)


def render_doc(conn, step) -> StepResult:
    return render_video(conn, step, DOC, "documentary.mp4")

"""Seslendirme (Stage 4).

voiceover_texts   : onaylı senaryodan ElevenLabs metinlerini üretir (documentary_voiceover.txt, shorts_voiceover.txt)
voiceover_analyze : yüklenen MP3/WAV'ı indirir; süre (ffprobe), duraklamalar (ffmpeg silencedetect),
                    kelime zamanları (faster-whisper, açık kaynak, CPU) ve senaryo ile hizalama →
                    her sahnenin GERÇEK başlangıç/bitiş zamanı.

Hiçbir ücretli API kullanılmaz. Whisper modeli ilk çalıştırmada Hugging Face'ten indirilir (önbelleğe alınır).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from psycopg.types.json import Jsonb

from . import storage
from .handlers import StepResult

LIMITS = {"doc": (8 * 60, 15 * 60), "shorts": (45, 60)}
FILES = {"doc": "documentary_voiceover.txt", "shorts": "shorts_voiceover.txt"}
MIN_COVERAGE = 0.6


# ----------------------------------------------------------------- metinler
def build_text(scenes: list[dict]) -> str:
    """ElevenLabs için: yalnızca okunacak cümleler; sahneler arası boş satır (doğal duraklama)."""
    return "\n\n".join(re.sub(r"\s+", " ", s["voiceover_text"]).strip() for s in scenes if s["voiceover_text"]) + "\n"


def texts(conn, step) -> StepResult:
    p = conn.execute("select * from projects where id=%s", (step["project_id"],)).fetchone()
    out = {}
    for kind in ("doc", "shorts"):
        sc = conn.execute("select id, approved_at from scripts where project_id=%s and kind=%s order by version desc limit 1",
                          (p["id"], kind)).fetchone()
        if not sc:
            raise RuntimeError(f"{kind} senaryosu yok")
        if not sc["approved_at"]:
            raise RuntimeError(f"{kind} senaryosu onaylanmamış")
        scenes = conn.execute("select voiceover_text from scenes where project_id=%s and kind=%s order by idx",
                              (p["id"], kind)).fetchall()
        text = build_text(scenes)
        conn.execute("update scripts set voiceover_text=%s where id=%s", (text, sc["id"]))
        key = None
        if storage.configured():
            key = storage.project_key(p["slug"], "scripts", FILES[kind])
            storage.upload_bytes(key, text.encode(), "text/plain; charset=utf-8")
        out[kind] = {"chars": len(text), "words": len(text.split()), "file": FILES[kind], "r2_key": key}
    out["elevenlabs_credits_estimate"] = out["doc"]["chars"] + out["shorts"]["chars"]
    return StepResult(output=out)


# ----------------------------------------------------------------- ses ölçümleri
def probe_duration(path: str | Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def detect_silences(path: str | Path, noise_db: int = -35, min_sec: float = 0.35) -> list[tuple[float, float]]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        f"silencedetect=noise={noise_db}dB:d={min_sec}", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends))


Word = tuple[str, float, float]   # (kelime, başlangıç, bitiş)


def decode_16k(path: str | Path):
    """Sesi ffmpeg ile 16 kHz mono float32'ye çözer (PyAV sürüm uyumsuzluklarından bağımsız)."""
    import numpy as np

    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1",
                        "-ar", "16000", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32)


def whisper_transcribe(path: str | Path, lang: str, prompt: str = "") -> list[Word]:
    from faster_whisper import WhisperModel

    model = WhisperModel(os.environ.get("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
    segments, _ = model.transcribe(decode_16k(path), language=lang, word_timestamps=True, vad_filter=True,
                                   initial_prompt=prompt[:200] or None, beam_size=1)
    return [(w.word.strip(), float(w.start), float(w.end)) for seg in segments for w in (seg.words or [])]


# Testler bu kancayı değiştirir
transcribe: Callable[[str | Path, str, str], list[Word]] = whisper_transcribe


# ----------------------------------------------------------------- hizalama
def _norm(w: str) -> str:
    w = unicodedata.normalize("NFKC", w).lower().replace("i̇", "i")
    return re.sub(r"[^\w]", "", w)


def align(scene_texts: list[str], words: list[Word], duration: float) -> tuple[list[tuple[float, float]], float]:
    """Senaryo sahnelerini konuşulan kelimelerle eşleştirir → [(başlangıç, bitiş)] ve eşleşme oranı.

    Eşleşmeyen sahneler komşuları arasında kelime sayısına göre orantılı yerleştirilir.
    Sahneler kesintisiz ardışık olur: ilk sahne 0'da başlar, son sahne ses bitiminde biter.
    """
    script: list[tuple[str, int]] = []
    for si, t in enumerate(scene_texts):
        script += [(n, si) for n in (_norm(x) for x in t.split()) if n]
    spoken = [_norm(w) for w, _, _ in words]
    sm = SequenceMatcher(None, [s for s, _ in script], spoken, autojunk=False)
    hit: dict[int, list[tuple[float, float]]] = {}
    matched = 0
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            si = script[a + k][1]
            hit.setdefault(si, []).append((words[b + k][1], words[b + k][2]))
            matched += 1
    coverage = matched / max(1, len(script))

    n = len(scene_texts)
    first = [min(t[0] for t in hit[i]) if i in hit else None for i in range(n)]
    last = [max(t[1] for t in hit[i]) if i in hit else None for i in range(n)]
    # Eşleşmeyen sahneleri komşu bilinen zamanlar arasında kelime sayısına göre dağıt
    wc = [max(1, len(t.split())) for t in scene_texts]
    i = 0
    while i < n:
        if first[i] is not None:
            i += 1
            continue
        j = i
        while j < n and first[j] is None:
            j += 1
        left = last[i - 1] if i > 0 else 0.0
        right = first[j] if j < n else duration
        span, total = max(0.0, right - left), sum(wc[i:j])
        t = left
        for k in range(i, j):
            first[k] = t
            t += span * wc[k] / total
            last[k] = t
        i = j
    # Ardışık sınırlar: bir sahnenin bitişi = sonrakinin ilk kelimesinin başlangıcı
    bounds = []
    for k in range(n):
        start = 0.0 if k == 0 else bounds[-1][1]
        end = duration if k == n - 1 else max(start, first[k + 1])
        bounds.append((round(start, 3), round(end, 3)))
    return bounds, round(coverage, 3)


# ----------------------------------------------------------------- analiz adımı
def analyze(conn, step) -> StepResult:
    p = conn.execute("select * from projects where id=%s", (step["project_id"],)).fetchone()
    if not storage.configured():
        raise RuntimeError("R2 yapılandırılmamış (R2_* secret'ları); ses dosyaları indirilemiyor")
    vos = conn.execute("select * from voiceovers where project_id=%s order by kind", (p["id"],)).fetchall()
    if {v["kind"] for v in vos} != {"doc", "shorts"}:
        raise RuntimeError("İki seslendirme dosyası da yüklenmiş olmalı (belgesel + Shorts)")
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        for v in vos:
            local = storage.download(v["storage_key"], Path(tmp) / Path(v["storage_key"]).name)
            sha = storage.sha256_file(local)
            if v["sha256"] and v["sha256"] != sha:
                raise RuntimeError(f"{v['kind']} ses dosyası bütünlük kontrolünden geçmedi (SHA-256 farklı)")
            duration = probe_duration(local)
            silences = detect_silences(local)
            scenes = conn.execute("select id, voiceover_text from scenes where project_id=%s and kind=%s order by idx",
                                  (p["id"], v["kind"])).fetchall()
            texts_ = [s["voiceover_text"] or "" for s in scenes]
            words = transcribe(local, p["language"], " ".join(texts_))
            bounds, coverage = align(texts_, words, duration)
            for s, (a, b) in zip(scenes, bounds):
                conn.execute("update scenes set start_sec=%s, end_sec=%s where id=%s", (a, b, s["id"]))

            lo, hi = LIMITS[v["kind"]]
            warnings = []
            if not lo <= duration <= hi:
                warnings.append(f"Süre {duration:.1f} sn; hedef aralık {lo}-{hi} sn")
            if coverage < MIN_COVERAGE:
                warnings.append(f"Ses ile senaryo yalnızca %{coverage * 100:.0f} eşleşiyor — yanlış dosya veya farklı metin olabilir")
            speech = sum(e - s for _, s, e in words) if words else 0
            analysis = {
                "duration_sec": round(duration, 3), "coverage": coverage, "words_spoken": len(words),
                "wpm": round(len(words) / (duration / 60), 1) if duration else None,
                "pauses": len(silences), "longest_pause_sec": round(max((e - s for s, e in silences), default=0), 2),
                "speech_sec": round(speech, 1), "scene_times": bounds, "warnings": warnings,
            }
            words_key = storage.project_key(p["slug"], "voiceover", f"{v['kind']}_words.json")
            storage.upload_bytes(words_key, json.dumps([{"w": w, "s": s, "e": e} for w, s, e in words],
                                                       ensure_ascii=False).encode(), "application/json")
            conn.execute("update voiceovers set status='analyzed', duration_sec=%s, analysis=%s, coverage=%s, words_key=%s, "
                         "sha256=%s where id=%s", (duration, Jsonb(analysis), coverage, words_key, sha, v["id"]))
            for w_ in warnings:
                conn.execute("insert into error_logs (project_id, job_id, step_key, level, message) values (%s,%s,%s,'warning',%s)",
                             (p["id"], step["job_id"], step["step_key"], f"{v['kind']}: {w_}"))
            results[v["kind"]] = {k: analysis[k] for k in ("duration_sec", "coverage", "wpm", "pauses", "warnings")}
    return StepResult(output=results)

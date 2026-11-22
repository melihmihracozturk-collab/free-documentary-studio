"""Ücretsiz otomatik seslendirme (öneri biçimi): sunucunun sesi.

Sağlayıcılar (ayarlar → tts_provider):
- edge   : Microsoft Edge'in sesli okuma servisi (edge-tts paketi, anahtar gerekmez). Türkçe kadın sesi: tr-TR-EmelNeural.
           Resmî bir API değildir; servis değişirse/engellenirse otomatik olarak Gemini'ye geçilir.
- gemini : Google Gemini TTS (GEMINI_API_KEY ile, ücretsiz katman). Ses: ayarlar → gemini_tts_voice (ör. Leda, Kore).

Metin sahne sahne seslendirilir, sahneler arasına kısa sessizlik konur ve tek MP3 olarak birleştirilir. Ardından
voiceover_analyze (faster-whisper) her sahnenin gerçek zamanlarını çıkarır; dudak senkronu bu sesten yapılır.
"""
from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from . import http

GEMINI_TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL") or "gemini-2.5-flash-preview-tts"
PAUSE_SEC = 0.45


def _settings(conn) -> dict:
    rows = conn.execute("select key, value from settings where key in "
                        "('tts_provider','tts_voice','tts_rate','gemini_tts_voice')").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ----------------------------------------------------------------- sağlayıcılar
def edge(text: str, out: Path, voice: str, rate: str) -> None:
    import edge_tts

    async def go():
        await edge_tts.Communicate(text, voice, rate=rate).save(str(out))
    asyncio.run(go())
    if not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError("Edge TTS boş ses döndürdü")


def gemini(text: str, out: Path, voice: str, style: str = "") -> None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY yok")
    prompt = (style + "\n\n" + text) if style else text
    r = http.request("POST", f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TTS_MODEL}:generateContent",
                     headers={"x-goog-api-key": key}, timeout=180, json={
                         "contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                             "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}})
    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = base64.b64decode(part["data"])               # 24 kHz, 16-bit, mono PCM
    subprocess.run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "-",
                    "-c:a", "libmp3lame", "-q:a", "2", str(out)], input=pcm, check=True)


Synth = Callable[[str, Path], None]


def synth_for(conn) -> tuple[list[tuple[str, Synth]], dict]:
    st = _settings(conn)
    voice, rate = str(st.get("tts_voice") or "tr-TR-EmelNeural"), str(st.get("tts_rate") or "+0%")
    gvoice = str(st.get("gemini_tts_voice") or "Leda")
    style = "Read aloud in Turkish as a warm, cheerful young woman hosting an anime and film recommendation show:"
    chain: list[tuple[str, Synth]] = [("edge", lambda t, o: edge(t, o, voice, rate)),
                                      ("gemini", lambda t, o: gemini(t, o, gvoice, style))]
    if (st.get("tts_provider") or "edge") == "gemini":
        chain.reverse()
    return chain, {"voice": voice, "rate": rate, "gemini_voice": gvoice}


# ----------------------------------------------------------------- birleştirme
def synthesize(paragraphs: list[str], out: Path, chain: list[tuple[str, Synth]]) -> dict:
    """Her paragrafı seslendirir (sağlayıcı zinciri: ilk çalışan kullanılır), aralara sessizlik koyup MP3'e birleştirir."""
    errors: list[str] = []
    used: str | None = None
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        parts = []
        for i, text in enumerate(p for p in paragraphs if p.strip()):
            f = tmp / f"p{i:03d}.mp3"
            order = [c for c in chain if c[0] == used] + [c for c in chain if c[0] != used] if used else chain
            for name, fn in order:
                try:
                    fn(text, f)
                    used = name
                    break
                except Exception as e:  # noqa: BLE001 — sıradaki sağlayıcı denenir
                    errors.append(f"{name}: {type(e).__name__}: {str(e)[:160]}")
            else:
                raise RuntimeError("Otomatik seslendirme başarısız: " + " | ".join(errors[-4:]))
            parts.append(f)
        if not parts:
            raise RuntimeError("Seslendirilecek metin yok")
        # Her parça 48 kHz mono'ya çevrilip arkasına kısa sessizlik eklenir, sonra uç uca eklenir
        inputs, fg = [], []
        for k, f in enumerate(parts):
            inputs += ["-i", str(f)]
            fg.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=mono,apad=pad_dur={PAUSE_SEC}[a{k}]")
        fg.append("".join(f"[a{k}]" for k in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]")
        subprocess.run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fg),
                        "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", str(out)], check=True)
    return {"provider": used, "paragraphs": len(parts), "fallback_errors": errors[:6]}


def voice_project(conn, p, texts_by_kind: dict[str, str], hooks: dict | None = None) -> dict:
    """Projenin belgesel + Shorts metnini seslendirir, R2'ye yükler ve voiceovers kayıtlarını oluşturur.
    'Seslendirme dosyalarını bekle' adımı iki kayıt hazır olunca kendiliğinden geçer."""
    from . import storage

    chain, info = synth_for(conn)
    if hooks and hooks.get("chain"):
        chain = hooks["chain"]
    out = {"settings": info}
    with tempfile.TemporaryDirectory() as tmp:
        for kind, text in texts_by_kind.items():
            f = Path(tmp) / f"{kind}.mp3"
            res = synthesize([x for x in text.split("\n\n")], f, chain)
            key = storage.project_key(p["slug"], "voiceover", f"{kind}-tts.mp3")
            sha = storage.upload_file(key, f, "audio/mpeg")
            size = f.stat().st_size
            conn.execute(
                "insert into voiceovers (project_id, kind, storage_key, filename, mime, bytes, sha256, uploaded_at) "
                "values (%s,%s,%s,%s,'audio/mpeg',%s,%s,now()) on conflict (project_id, kind) do update set "
                "storage_key=excluded.storage_key, filename=excluded.filename, mime=excluded.mime, bytes=excluded.bytes, "
                "sha256=excluded.sha256, uploaded_at=now(), status='uploaded'",
                (p["id"], kind, key, f"{kind}-tts.mp3", size, sha))
            out[kind] = {**res, "bytes": size, "key": key}
    return out

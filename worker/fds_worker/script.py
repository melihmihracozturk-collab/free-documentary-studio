"""Senaryo motoru (Stage 3): ana belgesel ve bağımsız Shorts senaryosu.

Senaryo yalnızca doğrulanmış/tek kaynaklı iddialara dayanır; her olgusal sahne iddia kimliği (C#) taşır.
Çıktı kodla doğrulanır (yapı, kelime bütçesi, alanlar, iddia kimlikleri). Hata varsa LLM'e
hatalar listesiyle en fazla 2 kez düzeltme yaptırılır.
"""
from __future__ import annotations

import json
import re

from psycopg.types.json import Jsonb

from . import llm
from .handlers import StepResult
from .research import LANG_NAME, SYSTEM

ACTS = ["giris", "arka_plan", "gelisme", "donum_noktasi", "sonuclar", "kapanis"]
ACT_TR = {"giris": "Çarpıcı giriş", "arka_plan": "Tarihsel arka plan", "gelisme": "Olayların gelişimi",
          "donum_noktasi": "Kritik dönüm noktası", "sonuclar": "Sonuçlar", "kapanis": "Güçlü kapanış"}
CAMERA = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "parallax", "ken_burns", "static"]
TRANSITIONS = ["cut", "crossfade", "fade_black", "dip_white", "wipe", "slide"]
MAX_SCENE_WORDS = 75
TOLERANCE = 0.12


def words(text: str) -> int:
    return len(re.findall(r"\w+", text or "", re.U))


def _setting(conn, key, default):
    row = conn.execute("select value from settings where key=%s", (key,)).fetchone()
    return float(row["value"]) if row else default


def _claims_block(conn, project_id):
    rows = conn.execute(
        "select ref, status, text, event_date, conflict_note from claims where project_id=%s "
        "and status in ('verified','weak','conflict') order by importance desc, ref", (project_id,)).fetchall()
    lines = []
    for c in rows:
        date = f" ({c['event_date']})" if c["event_date"] else ""
        note = f" — CONFLICT: {c['conflict_note']}" if c["status"] == "conflict" else ""
        lines.append(f"{c['ref']} [{c['status']}]{date} {c['text']}{note}")
    return "\n".join(lines), {c["ref"]: c["status"] for c in rows}


SCENE_SCHEMA = """{"voiceover": "narration text spoken in this scene",
 "visual_description": "what is on screen (archival photo, painting, map, document, artifact, infographic...)",
 "search_keywords": ["2-4 English archive search phrases"],
 "camera_move": one of CAMERA, "transition": one of TRANSITIONS (transition INTO this scene),
 "music": "mood/instrumentation", "sfx": "sound effect or 'none'",
 "on_screen_text": "short caption/date/place or null", "claim_refs": ["C#", ...],
 "disputed": false}"""


def validate_doc(data: dict, budget: int, claim_status: dict) -> list[str]:
    errs = []
    acts = data.get("acts")
    if not isinstance(acts, list):
        return ["'acts' listesi yok"]
    names = [a.get("act") for a in acts]
    if names != ACTS:
        errs.append(f"acts sırası tam olarak {ACTS} olmalı, gelen: {names}")
    total, n = 0, 0
    for a in acts:
        scenes = a.get("scenes") or []
        if not scenes:
            errs.append(f"{a.get('act')}: sahne yok")
        for s in scenes:
            n += 1
            errs += _validate_scene(s, n, claim_status)
            total += words(s.get("voiceover", ""))
    lo, hi = int(budget * (1 - TOLERANCE)), int(budget * (1 + TOLERANCE))
    if not lo <= total <= hi:
        errs.append(f"toplam seslendirme {total} kelime; {lo}-{hi} arasında olmalı (hedef {budget})")
    if n and not 20 <= n <= 60:
        errs.append(f"sahne sayısı {n}; 20-60 arasında olmalı")
    return errs


def _validate_scene(s: dict, n: int, claim_status: dict) -> list[str]:
    errs = []
    for f in ("voiceover", "visual_description", "camera_move", "transition", "music", "sfx"):
        if not s.get(f):
            errs.append(f"sahne {n}: '{f}' boş")
    if s.get("camera_move") and s["camera_move"] not in CAMERA:
        errs.append(f"sahne {n}: camera_move '{s['camera_move']}' geçersiz")
    if s.get("transition") and s["transition"] not in TRANSITIONS:
        errs.append(f"sahne {n}: transition '{s['transition']}' geçersiz")
    w = words(s.get("voiceover", ""))
    if w > MAX_SCENE_WORDS:
        errs.append(f"sahne {n}: {w} kelime; en fazla {MAX_SCENE_WORDS}")
    if not s.get("search_keywords"):
        errs.append(f"sahne {n}: search_keywords boş")
    for ref in s.get("claim_refs") or []:
        st = claim_status.get(ref)
        if st is None:
            errs.append(f"sahne {n}: bilinmeyen iddia {ref}")
        elif st == "conflict" and not s.get("disputed"):
            errs.append(f"sahne {n}: çelişkili iddia {ref} yalnızca disputed=true ve tartışmalı olarak anlatılabilir")
    return errs


def validate_shorts(data: dict, budget: int, claim_status: dict) -> list[str]:
    errs = []
    scenes = data.get("scenes") or []
    if not 4 <= len(scenes) <= 14:
        errs.append(f"sahne sayısı {len(scenes)}; 4-14 arasında olmalı")
    for i, s in enumerate(scenes, 1):
        errs += _validate_scene(s, i, claim_status)
    if scenes and words(scenes[0].get("voiceover", "")) > 10:
        errs.append("ilk sahne (kanca) en fazla 10 kelime olmalı (≈3 sn)")
    total = sum(words(s.get("voiceover", "")) for s in scenes)
    lo, hi = int(budget * (1 - TOLERANCE)), int(budget * (1 + TOLERANCE))
    if not lo <= total <= hi:
        errs.append(f"toplam {total} kelime; {lo}-{hi} arasında olmalı (hedef {budget})")
    return errs


def _generate(conn, prompt: str, validator, task: str) -> tuple[dict, list[str]]:
    data = llm.complete_json(conn, SYSTEM, prompt, task=task, temperature=0.7)
    errs = validator(data)
    for attempt in range(2):
        if not errs:
            break
        data = llm.complete_json(conn, SYSTEM, f"""{prompt}

Your previous answer had these problems:
{chr(10).join('- ' + e for e in errs)}

Previous answer:
{json.dumps(data, ensure_ascii=False)[:30000]}

Return the corrected complete JSON.""", task=f"{task}_repair", temperature=0.4)
        errs = validator(data)
    return data, errs


def _save(conn, project_id, kind, data, scenes, wpm, errs):
    total = sum(words(s.get("voiceover", "")) for s in scenes)
    vo = "\n\n".join(s["voiceover"].strip() for s in scenes)
    version = conn.execute("select coalesce(max(version),0)+1 v from scripts where project_id=%s and kind=%s",
                           (project_id, kind)).fetchone()["v"]
    sid = conn.execute(
        "insert into scripts (project_id, kind, version, content, voiceover_text, word_count, est_seconds, validation) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s) returning id",
        (project_id, kind, version, Jsonb(data), vo, total, round(total / wpm * 60, 1),
         Jsonb({"errors": errs, "ok": not errs}))).fetchone()["id"]
    conn.execute("delete from scenes where project_id=%s and kind=%s", (project_id, kind))
    for i, s in enumerate(scenes, 1):
        w = words(s["voiceover"])
        conn.execute(
            "insert into scenes (project_id, script_id, kind, idx, act, est_duration_sec, voiceover_text, visual_description, "
            "camera_move, transition, music, sfx, search_keywords, claim_refs, on_screen_text, word_count) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (project_id, sid, kind, i, s.get("_act"), round(w / wpm * 60, 2), s["voiceover"], s.get("visual_description"),
             s.get("camera_move"), s.get("transition"), s.get("music"), s.get("sfx"), s.get("search_keywords") or [],
             s.get("claim_refs") or [], s.get("on_screen_text"), w))
    return version, total


def script_doc(conn, step) -> StepResult:
    p = conn.execute("select * from projects where id=%s", (step["project_id"],)).fetchone()
    wpm = _setting(conn, "narration_wpm", 135)
    budget = int(float(p["target_minutes"]) * wpm)
    claims, status = _claims_block(conn, p["id"])
    if not claims:
        raise RuntimeError("Senaryo için doğrulanmış iddia yok; araştırma adımları tamamlanmalı")
    lang = LANG_NAME.get(p["language"], p["language"])
    prompt = f"""
Write a {p['target_minutes']}-minute documentary script in {lang}. Style: {p['style']}.
Topic: {p['topic']}

STRUCTURE (exactly these acts, in this order): {', '.join(f'{a} = {ACT_TR[a]}' for a in ACTS)}.
- giris: a gripping cold open (a vivid moment, question or paradox) in the first 20 seconds.
- donum_noktasi: the critical turning point of the story.
- kapanis: a strong, memorable ending that resonates with today.

LENGTH: total narration about {budget} words (±10%). Each scene 10-25 seconds (≈ 25-55 words), max {MAX_SCENE_WORDS} words.

FACTS: use ONLY the claims below. Every factual sentence must cite claim ids in "claim_refs".
[weak] = single source: phrase carefully ("kaynaklara göre", "anlatılana göre").
[conflict] claims may only appear as an explicitly disputed point with "disputed": true.
Never invent names, numbers, dates or quotes.

Narration must sound natural when read aloud by a TTS voice: no stage directions, no brackets,
no abbreviations, write numbers as words if ambiguous, short sentences.

CAMERA = {CAMERA}
TRANSITIONS = {TRANSITIONS}

Return JSON:
{{"title": "...", "logline": "one sentence",
  "acts": [{{"act": "giris", "scenes": [{SCENE_SCHEMA}]}}, ...]}}

CLAIMS:
{claims}
"""
    data, errs = _generate(conn, prompt, lambda d: validate_doc(d, budget, status), "script_doc")
    scenes = [{**s, "_act": a.get("act")} for a in data.get("acts", []) for s in a.get("scenes", [])]
    if not scenes:
        raise RuntimeError("Senaryo üretilemedi: " + "; ".join(errs[:5]))
    version, total = _save(conn, p["id"], "doc", data, scenes, wpm, errs)
    return StepResult(output={"version": version, "scenes": len(scenes), "words": total,
                              "est_minutes": round(total / wpm, 2), "budget_words": budget, "validation_errors": errs})


def script_shorts(conn, step) -> StepResult:
    p = conn.execute("select * from projects where id=%s", (step["project_id"],)).fetchone()
    wpm = _setting(conn, "shorts_wpm", 155)
    budget = int(p["shorts_seconds"] / 60 * wpm)
    claims, status = _claims_block(conn, p["id"])
    doc = conn.execute("select content->>'title' t from scripts where project_id=%s and kind='doc' order by version desc limit 1",
                       (p["id"],)).fetchone()
    lang = LANG_NAME.get(p["language"], p["language"])
    prompt = f"""
Write an independent YouTube Shorts script ({p['shorts_seconds']} seconds, vertical 9:16) in {lang}.
Topic: {p['topic']}. The full documentary is titled: "{doc['t'] if doc else p['title']}".

- Scene 1 is the HOOK: max 8 words, about 3 seconds, creates instant curiosity (shocking fact, question, or tension).
- Must make sense on its own, tell ONE focused story arc with escalating tension.
- End with a natural line that makes viewers want the full documentary (no "like and subscribe").
- Total narration about {budget} words (±10%), 5-12 scenes, each 3-8 seconds.
- Visuals must work in vertical framing (close-ups, details, single subjects).
- Use ONLY the claims below, cite them in "claim_refs". Same rules for [weak]/[conflict] as a documentary.

CAMERA = {CAMERA}
TRANSITIONS = {TRANSITIONS}

Return JSON: {{"title": "...", "scenes": [{SCENE_SCHEMA}]}}

CLAIMS:
{claims}
"""
    data, errs = _generate(conn, prompt, lambda d: validate_shorts(d, budget, status), "script_shorts")
    scenes = [{**s, "_act": "shorts"} for s in data.get("scenes", [])]
    if not scenes:
        raise RuntimeError("Shorts senaryosu üretilemedi: " + "; ".join(errs[:5]))
    version, total = _save(conn, p["id"], "shorts", data, scenes, wpm, errs)
    return StepResult(output={"version": version, "scenes": len(scenes), "words": total,
                              "est_seconds": round(total / wpm * 60, 1), "budget_words": budget, "validation_errors": errs})

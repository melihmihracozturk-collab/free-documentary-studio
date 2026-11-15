"""Senaryo motoru (Stage 3): ana belgesel ve bağımsız Shorts senaryosu.

Senaryo yalnızca doğrulanmış/tek kaynaklı iddialara dayanır; her olgusal sahne iddia kimliği (C#) taşır.
Uzun metinde LLM'ler kısaltma eğilimindedir; bu yüzden belgesel önce TASLAK (bölüm, sahne sayısı,
iddia dağılımı), sonra BÖLÜM BÖLÜM yazılır. Her bölüm kodla kontrol edilir (alanlar, kelime hedefi,
iddia kimlikleri); kısa veya hatalı bölüm hatalar listesiyle yeniden yazdırılır (en fazla 2 kez).
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



ACT_SHARE = {"giris": 0.08, "arka_plan": 0.17, "gelisme": 0.30, "donum_noktasi": 0.20, "sonuclar": 0.15, "kapanis": 0.10}
SCENE_WORDS = 42          # sahne başına hedef kelime (~20 sn)

STYLE = """NARRATION STYLE (very important):
- Cinematic documentary storytelling, not an encyclopedia. In Turkish use the narrative past tense (-dı/-di, e.g. "Gökyüzü karardı.")
  NOT the report style (-mıştır/-miştir, "meydana gelmiştir").
- Short, vivid, spoken sentences (6-18 words). Vary rhythm. Occasional rhetorical question or pause line is welcome.
- Atmosphere and emotion are allowed, but every FACT (date, number, name, place, cause, event) must come from the claims.
- Attribution phrases like "kaynaklara göre", "anlatılana göre", "araştırmalara göre": at most 3 in the whole script,
  only for debated or surprising single-source facts. Never start consecutive sentences with them.
- Numbers as words when read aloud ("iki yüz elli derece"). No brackets, no stage directions, no claim ids in narration."""


def _llm_json(conn, prompt: str, task: str, temperature: float = 0.7) -> dict:
    return llm.complete_json(conn, SYSTEM, prompt, task=task, temperature=temperature)


def _write_with_repair(conn, prompt: str, validator, task: str) -> tuple[dict, list[str]]:
    data = _llm_json(conn, prompt, task)
    errs = validator(data)
    for _ in range(2):
        if not errs:
            break
        data = _llm_json(conn, f"""{prompt}

Your previous answer had these problems — fix ALL of them (if too short, ADD scenes/sentences, do not just pad words):
{chr(10).join('- ' + e for e in errs)}

Previous answer:
{json.dumps(data, ensure_ascii=False)[:30000]}

Return the corrected complete JSON.""", f"{task}_repair", 0.5)
        errs = validator(data)
    return data, errs


def _validate_act(data: dict, n_scenes: int, words_target: int, claim_status: dict, act: str) -> list[str]:
    scenes = data.get("scenes") or []
    errs = []
    if not scenes:
        return [f"{act}: sahne yok"]
    if not (n_scenes - 1 <= len(scenes) <= n_scenes + 2):
        errs.append(f"{act}: {len(scenes)} sahne; yaklaşık {n_scenes} olmalı")
    for i, sc in enumerate(scenes, 1):
        errs += [f"{act} {e}" for e in _validate_scene(sc, i, claim_status)]
    total = sum(words(sc.get("voiceover", "")) for sc in scenes)
    lo, hi = int(words_target * (1 - TOLERANCE)), int(words_target * (1 + TOLERANCE))
    if not lo <= total <= hi:
        errs.append(f"{act}: {total} kelime; {lo}-{hi} arasında olmalı (hedef {words_target}). "
                    f"{'Daha fazla sahne/cümle ekleyin.' if total < lo else 'Kısaltın.'}")
    return errs


def script_doc(conn, step) -> StepResult:
    p = conn.execute("select * from projects where id=%s", (step["project_id"],)).fetchone()
    wpm = _setting(conn, "narration_wpm", 125)
    budget = int(float(p["target_minutes"]) * wpm)
    claims, status = _claims_block(conn, p["id"])
    if not claims:
        raise RuntimeError("Senaryo için doğrulanmış iddia yok; araştırma adımları tamamlanmalı")
    lang = LANG_NAME.get(p["language"], p["language"])
    plan = {a: (round(budget * ACT_SHARE[a]), max(2, round(budget * ACT_SHARE[a] / SCENE_WORDS))) for a in ACTS}

    # 1) Taslak
    outline = _llm_json(conn, f"""
Plan a {p['target_minutes']}-minute documentary in {lang}. Style: {p['style']}. Topic: {p['topic']}

Acts (fixed order) with target scene counts:
{chr(10).join(f"- {a} = {ACT_TR[a]}: {plan[a][1]} scenes" for a in ACTS)}

- giris: a gripping cold open — start in the middle of the most dramatic moment, a paradox or a question. Not a date.
- donum_noktasi: the critical turning point. kapanis: a resonant ending connecting to today.
- Distribute the claims so that every important claim is used once, in a logical order. Do not invent facts.

Return JSON: {{"title": "...", "logline": "one sentence",
  "acts": [{{"act": "giris", "beats": ["one line per scene: what happens + claim ids"], "claim_refs": ["C#", ...]}}, ...]}}

CLAIMS ([verified]=2+ sources, [weak]=single source, [conflict]=disputed):
{claims}
""", "script_outline", 0.6)
    beats = {a.get("act"): a for a in outline.get("acts", [])}

    # 2) Bölüm bölüm yazım
    acts_out, all_errs, previous = [], [], ""
    for a in ACTS:
        words_target, n_scenes = plan[a]
        b = beats.get(a, {})
        prompt = f"""
You are writing ONE act of a {p['target_minutes']}-minute documentary in {lang}: "{outline.get('title', p['title'])}".
Logline: {outline.get('logline', '')}

ACT: {a} = {ACT_TR[a]}
Write EXACTLY {n_scenes} scenes, about {SCENE_WORDS} words of narration each (total about {words_target} words, ±10%).
Planned beats: {json.dumps(b.get('beats', []), ensure_ascii=False)}

{STYLE}

{"The previous act ended with: " + chr(34) + previous[-400:] + chr(34) + " — continue smoothly, do not repeat it." if previous else "This is the opening of the film."}

Each scene must cite the claim ids it uses in "claim_refs" (atmosphere-only scenes may have an empty list).
[conflict] claims only as an explicitly disputed point with "disputed": true.

CAMERA = {CAMERA}
TRANSITIONS = {TRANSITIONS}

Return JSON: {{"scenes": [{SCENE_SCHEMA}]}}

CLAIMS:
{claims}
"""
        data, errs = _write_with_repair(conn, prompt, lambda d, a=a, w=words_target, n=n_scenes: _validate_act(d, n, w, status, a),
                                        f"script_act_{a}")
        scenes = data.get("scenes") or []
        acts_out.append({"act": a, "scenes": scenes})
        all_errs += errs
        previous = " ".join(sc.get("voiceover", "") for sc in scenes[-2:])

    full = {"title": outline.get("title") or p["title"], "logline": outline.get("logline"), "acts": acts_out}
    final_errs = validate_doc(full, budget, status)
    scenes = [{**sc, "_act": a["act"]} for a in acts_out for sc in a["scenes"]]
    if not scenes:
        raise RuntimeError("Senaryo üretilemedi: " + "; ".join(all_errs[:5]))
    version, total = _save(conn, p["id"], "doc", full, scenes, wpm, final_errs)
    return StepResult(output={"version": version, "scenes": len(scenes), "words": total,
                              "est_minutes": round(total / wpm, 2), "budget_words": budget, "validation_errors": final_errs})


SHORTS_PLAN = [7, 17, 17, 17, 17, 17, 17, 23]   # kelime/sahne: 3 sn kanca + gövde + kapanış (≈132 kelime ≈ 55 sn)


def script_shorts(conn, step) -> StepResult:
    p = conn.execute("select * from projects where id=%s", (step["project_id"],)).fetchone()
    wpm = _setting(conn, "shorts_wpm", 145)
    budget = int(p["shorts_seconds"] / 60 * wpm)
    scale = budget / sum(SHORTS_PLAN)
    per_scene = [max(5, round(w * scale)) for w in SHORTS_PLAN]
    per_scene[0] = min(per_scene[0], 8)
    claims, status = _claims_block(conn, p["id"])
    doc = conn.execute("select content->>'title' t from scripts where project_id=%s and kind='doc' order by version desc limit 1",
                       (p["id"],)).fetchone()
    lang = LANG_NAME.get(p["language"], p["language"])
    prompt = f"""
Write an independent YouTube Shorts script ({p['shorts_seconds']} seconds, vertical 9:16) in {lang}.
Topic: {p['topic']}. The full documentary is titled: "{doc['t'] if doc else p['title']}".

Write EXACTLY {len(per_scene)} scenes with these narration lengths in words: {per_scene} (total about {budget} words).
- Scene 1 = HOOK (about 3 seconds): instant curiosity — a shocking fact, a question or tension. It must be TRUE to the claims.
- One focused story arc with escalating tension; it must make sense on its own.
- Last scene: a natural line that makes viewers want the full documentary (no "like and subscribe").
- Visuals must work in vertical framing (close-ups, details, single subjects).

{STYLE}

Cite claim ids in "claim_refs". [conflict] claims only as an explicitly disputed point with "disputed": true.

CAMERA = {CAMERA}
TRANSITIONS = {TRANSITIONS}

Return JSON: {{"title": "...", "scenes": [{SCENE_SCHEMA}]}}

CLAIMS:
{claims}
"""
    data, errs = _write_with_repair(conn, prompt, lambda d: validate_shorts(d, budget, status), "script_shorts")
    scenes = [{**sc, "_act": "shorts"} for sc in data.get("scenes", [])]
    if not scenes:
        raise RuntimeError("Shorts senaryosu üretilemedi: " + "; ".join(errs[:5]))
    version, total = _save(conn, p["id"], "shorts", data, scenes, wpm, errs)
    return StepResult(output={"version": version, "scenes": len(scenes), "words": total,
                              "est_seconds": round(total / wpm * 60, 1), "budget_words": budget, "validation_errors": errs})


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



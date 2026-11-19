"""Gezi vlogu senaryosu: birinci ağızdan, samimi anlatım; bölümler = duraklar.

Belgeselle aynı güvenceler geçerlidir: her olgu bir iddiaya (C#) dayanır, sayılar kodla denetlenir, editör turu
kaynaksız ayrıntıyı ayıklar. Fiyat/saat/ulaşım gibi değişebilen bilgiler [practical] iddialardan gelir ve bu
sahneler 'needs_check' ile işaretlenir; kullanıcı yayından önce kontrol eder.

Görüntüler arşiv fotoğraflarıdır; anlatıcı oraya gitmiş gibi uydurma kişisel deneyim (tat, hava, kalabalık,
"dün yediğimiz…") anlatmaz — "burada göreceğiniz", "gelirseniz" gibi davet diliyle konuşur.
"""
from __future__ import annotations

import json

from . import script as SC
from .handlers import StepResult
from .research import LANG_NAME

STYLE_VLOG = """NARRATION STYLE (very important):
- Warm, friendly FIRST-PERSON travel vlog voice, as if guiding the viewer along: "Şimdi Kolezyum'un önündeyiz…",
  "Buraya gelirseniz mutlaka…", "Bakın, şu kemerler…". Present tense, conversational Turkish ("-iyoruz", "görüyorsunuz").
- Do NOT invent personal experiences (taste of food, today's weather, crowds, "we ate", "I felt"). The visuals are
  archive photos: describe what the viewer would see and why it matters, invite rather than claim you were there.
- Short spoken sentences (6-18 words), lively rhythm, an occasional question to the viewer.
- Every FACT (date, number, name, price, opening hour, distance) must come from the claims.
- PRACTICAL facts ([practical] claims: prices, hours, transport, booking) are welcome: say them plainly and, if the claim
  gives a year, mention it ("iki bin yirmi dört itibarıyla"). Never invent or estimate a price or time.
- Numbers as words when read aloud. No brackets, no stage directions, no claim ids in narration."""

OPEN_SHARE, TIPS_SHARE, CLOSE_SHARE = 0.07, 0.12, 0.06


def plan_acts(stops: list[dict], budget: int) -> tuple[list[str], dict[str, str], dict[str, tuple[int, int]]]:
    """Bölüm listesi (giris, durak_1..n, ipuclari, kapanis), başlıkları ve (kelime, sahne) hedefleri."""
    stops = stops or [{"name_native": "Gezi"}]
    acts = ["giris"] + [f"durak_{i}" for i in range(1, len(stops) + 1)] + ["ipuclari", "kapanis"]
    titles = {"giris": "Giriş", "ipuclari": "Pratik ipuçları", "kapanis": "Kapanış"}
    for i, st in enumerate(stops, 1):
        titles[f"durak_{i}"] = st.get("name_native") or st.get("name_en") or f"Durak {i}"
    stop_share = (1 - OPEN_SHARE - TIPS_SHARE - CLOSE_SHARE) / len(stops)
    share = {"giris": OPEN_SHARE, "ipuclari": TIPS_SHARE, "kapanis": CLOSE_SHARE,
             **{a: stop_share for a in acts if a.startswith("durak_")}}
    plan = {a: (round(budget * share[a]), max(2, round(budget * share[a] / SC.SCENE_WORDS))) for a in acts}
    return acts, titles, plan


def _stops(conn, project_id) -> list[dict]:
    row = conn.execute("select output from job_steps where project_id=%s and step_key='research_collect' and output is not null "
                       "order by finished_at desc nulls last limit 1", (project_id,)).fetchone()
    plan = ((row or {}).get("output") or {}).get("plan") or {}
    return [x for x in plan.get("stops") or [] if isinstance(x, dict)]


def script_vlog(conn, step, p) -> StepResult:
    wpm = SC._setting(conn, "narration_wpm", 125)
    budget = int(float(p["target_minutes"]) * wpm)
    claims, status = SC._claims_block(conn, p["id"])
    if not claims:
        raise RuntimeError("Senaryo için iddia yok; araştırma adımları tamamlanmalı")
    lang = LANG_NAME.get(p["language"], p["language"])
    acts, titles, plan = plan_acts(_stops(conn, p["id"]), budget)

    outline = SC._llm_json(conn, f"""
Plan a {p['target_minutes']}-minute first-person TRAVEL VLOG in {lang}. Topic: {p['topic']}

Chapters (fixed order) with target scene counts:
{chr(10).join(f"- {a} = {titles[a]}: {plan[a][1]} scenes" for a in acts)}

- giris: a warm, curious hook that welcomes the viewer and promises the route. Not a date.
- each durak_N: that stop — what it is, a little history, what to look at, one local/cultural detail.
- ipuclari: practical tips gathered from [practical] claims (tickets, hours, transport, booking, best time).
- kapanis: a friendly goodbye that sums up the route. No "like and subscribe".
- Use each important claim once, in the chapter it belongs to. Do not invent facts.

Return JSON: {{"title": "...", "logline": "one sentence",
  "acts": [{{"act": "giris", "beats": ["one line per scene + claim ids"], "claim_refs": ["C#"]}}, ...]}}

CLAIMS ([practical]=prices/hours/transport, [verified]=2+ sources, [weak]=single source):
{claims}
""", "script_outline_vlog", 0.6)
    beats = {a.get("act"): a for a in outline.get("acts", [])}

    acts_out, all_errs, previous = [], [], ""
    for a in acts:
        words_target, n_scenes = plan[a]
        prompt = f"""
You are writing ONE chapter of a {p['target_minutes']}-minute travel vlog in {lang}: "{outline.get('title', p['title'])}".
Logline: {outline.get('logline', '')}

CHAPTER: {a} = {titles[a]}
Write EXACTLY {n_scenes} scenes, about {int(SC.SCENE_WORDS * SC.LENGTH_BOOST)} words of narration each
(total about {int(words_target * SC.LENGTH_BOOST)} words). Each scene needs 3-4 full sentences.
Planned beats: {json.dumps(beats.get(a, {}).get('beats', []), ensure_ascii=False)}

{STYLE_VLOG}

{"The previous chapter ended with: " + chr(34) + previous[-400:] + chr(34) + " — continue smoothly (a short transition to the next place is welcome)." if previous else "This is the opening of the vlog."}

Each scene cites the claim ids it uses in "claim_refs". "on_screen_text": the place name or a short tip.
"visual_description"/"search_keywords": archive/landmark photos of THIS place (e.g. "Colosseum exterior", "Trevi Fountain").

CAMERA = {SC.CAMERA}
TRANSITIONS = {SC.TRANSITIONS}

Return JSON: {{"scenes": [{SC.SCENE_SCHEMA}]}}

CLAIMS:
{claims}
"""
        data, errs = SC._write_with_repair(
            conn, prompt, lambda d, a=a, w=words_target, n=n_scenes: SC._validate_act(d, n, w, status, a, claims),
            f"script_vlog_{a.split('_')[0]}")
        scenes = data.get("scenes") or []
        acts_out.append({"act": a, "scenes": scenes})
        all_errs += errs
        previous = " ".join(sc.get("voiceover", "") for sc in scenes[-2:])

    scenes = [{**sc, "_act": x["act"]} for x in acts_out for sc in x["scenes"]]
    if not scenes:
        raise RuntimeError("Vlog senaryosu üretilemedi: " + "; ".join(all_errs[:5]))
    words_before = sum(SC.words(sc.get("voiceover", "")) for sc in scenes)

    scenes, edits = SC._edit(conn, p, "vlog", scenes, claims, status, budget,
                             "5. Keep the first-person travel-vlog voice. Remove invented personal experiences "
                             "(taste, weather, crowds, 'we ate'). Prices/hours only from [practical] claims.\n"
                             "6. Keep each scene in its chapter (stop); do not move facts of one place into another.",
                             style=STYLE_VLOG)
    scenes, dd_notes = SC.dedupe_scenes(scenes, int(budget * (1 - SC.TOLERANCE)) - int(budget * 0.15))
    checks = SC.mark_needs_check(scenes, SC.practical_refs(conn, p["id"]))
    full = {"title": outline.get("title") or p["title"], "logline": outline.get("logline"), "format": "vlog",
            "act_titles": titles,
            "acts": [{"act": a, "scenes": [sc for sc in scenes if sc.get("_act") == a]} for a in acts],
            "editor_notes": edits.get("notes", []) + dd_notes}
    final_errs = SC.validate_doc(full, budget, status, acts) + [
        f"sahne {i}: kaynakta olmayan sayı {', '.join(n)}" for i, n in SC.number_issues(scenes, claims).items()]
    version, total = SC._save(conn, p["id"], "doc", full, scenes, wpm, final_errs)
    return StepResult(output={"version": version, "format": "vlog", "scenes": len(scenes), "words": total,
                              "words_before_edit": words_before, "est_minutes": round(total / wpm, 2),
                              "budget_words": budget, "chapters": [titles[a] for a in acts], "needs_check": checks,
                              "editor_notes": full["editor_notes"][:12], "validation_errors": final_errs})

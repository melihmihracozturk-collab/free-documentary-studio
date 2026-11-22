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

from . import llm, numbers
from .handlers import StepResult
from .research import LANG_NAME, SYSTEM

ACTS = ["giris", "arka_plan", "gelisme", "donum_noktasi", "sonuclar", "kapanis"]
ACT_TR = {"giris": "Çarpıcı giriş", "arka_plan": "Tarihsel arka plan", "gelisme": "Olayların gelişimi",
          "donum_noktasi": "Kritik dönüm noktası", "sonuclar": "Sonuçlar", "kapanis": "Güçlü kapanış"}
CAMERA = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "parallax", "ken_burns", "static"]
TRANSITIONS = ["cut", "crossfade", "fade_black", "dip_white", "wipe", "slide"]
MAX_SCENE_WORDS = 75
TOLERANCE = 0.12
ACT_TOLERANCE = 0.25
LENGTH_BOOST = 1.3   # ölçüm: model istenen uzunluğun ~%70'ini yazıyor; istekte hedef büyütülür


def words(text: str) -> int:
    return len(re.findall(r"\w+", text or "", re.U))


def _setting(conn, key, default):
    row = conn.execute("select value from settings where key=%s", (key,)).fetchone()
    return float(row["value"]) if row else default


def _claims_block(conn, project_id):
    rows = conn.execute(
        "select ref, status, text, event_date, conflict_note, category from claims where project_id=%s "
        "and status in ('verified','weak','conflict') order by importance desc, ref", (project_id,)).fetchall()
    lines = []
    for c in rows:
        date = f" ({c['event_date']})" if c["event_date"] else ""
        note = f" — CONFLICT: {c['conflict_note']}" if c["status"] == "conflict" else ""
        prac = " [practical]" if is_practical(c["text"], c.get("category")) else ""
        lines.append(f"{c['ref']} [{c['status']}]{prac}{date} {c['text']}{note}")
    return "\n".join(lines), {c["ref"]: c["status"] for c in rows}


# Kategoriye güvenilmez (model fiyatı "number" diye etiketleyebiliyor): metinden de tanınır.
PRACTICAL_RE = re.compile(
    r"(€|\beuro|\bavro|\bbilet|ücret|fiyat|rezerv|açılış saat|kapanış saat|\b\d{1,2}[:.]\d{2}\b|saatleri arasında|"
    r"\btren|otobüs|vapur|vaporetto|otopark|konaklama vergisi|\bceza|yasak|emanet|\bkartı?\b)", re.I)


def is_practical(text: str, category: str | None = None) -> bool:
    return category == "practical" or bool(PRACTICAL_RE.search(text or ""))


def practical_refs(conn, project_id) -> set[str]:
    rows = conn.execute("select ref, text, category from claims where project_id=%s", (project_id,)).fetchall()
    return {r["ref"] for r in rows if is_practical(r["text"], r["category"])}


def mark_needs_check(scenes: list[dict], practical: set[str]) -> int:
    """Fiyat/saat/ulaşım gibi değişebilen bilgi içeren sahneleri işaretler (yayın öncesi kullanıcı kontrolü)."""
    n = 0
    for sc in scenes:
        sc["needs_check"] = bool(set(sc.get("claim_refs") or []) & practical)
        n += sc["needs_check"]
    return n


SCENE_SCHEMA = """{"voiceover": "narration text spoken in this scene",
 "visual_description": "what is on screen (archival photo, painting, map, document, artifact, infographic...)",
 "search_keywords": ["2-4 English archive search phrases"],
 "camera_move": one of CAMERA, "transition": one of TRANSITIONS (transition INTO this scene),
 "music": "mood/instrumentation", "sfx": "sound effect or 'none'",
 "on_screen_text": "short caption/date/place or null", "claim_refs": ["C#", ...],
 "disputed": false}"""


def validate_doc(data: dict, budget: int, claim_status: dict, acts_order: list[str] | None = None) -> list[str]:
    acts_order = acts_order or ACTS
    errs = []
    acts = data.get("acts")
    if not isinstance(acts, list):
        return ["'acts' listesi yok"]
    names = [a.get("act") for a in acts]
    if names != acts_order:
        errs.append(f"acts sırası tam olarak {acts_order} olmalı, gelen: {names}")
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
- Numbers as words when read aloud ("iki yüz elli derece"). No brackets, no stage directions, no claim ids in narration.
- NEUTRALITY for living people, political parties, governments and contested topics: no praise or condemnation in the
  narrator's voice ("başarılı", "karanlık", "efsane", "zalim"); report what happened and attribute evaluations to who
  made them ("destekçilerine göre…", "eleştirmenler … diyor"). Where the claims contain both achievements and
  criticisms, include both in proportion. Election results and numbers exactly as in the claims."""


def _llm_json(conn, prompt: str, task: str, temperature: float = 0.7) -> dict:
    return llm.complete_json(conn, SYSTEM, prompt, task=task, temperature=temperature)


def _write_with_repair(conn, prompt: str, validator, task: str) -> tuple[dict, list[str]]:
    data = _llm_json(conn, prompt, task)
    errs = validator(data)
    for _ in range(1):           # en fazla 1 düzeltme: kota korunur, kalan eksikleri editör turu giderir
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


REPORT_STYLE = re.compile(r"\w+(mıştır|miştir|muştur|müştür|maktadır|mektedir|dır\.|dir\.)(?=[\s.,;]|$)", re.I)


def report_style(text: str) -> bool:
    """Rapor/ansiklopedi dili (anlatımda kaçınılır): bir sahnede en az 2 '-mıştır/-mektedir' kalıbı veya
    araştırma raporundan kopyalanmış ifadeler."""
    return len(REPORT_STYLE.findall(text or "")) >= 2 or bool(re.search(r"çelişki vardır|genel kabul", text or "", re.I))


def _tok(text: str) -> set[str]:
    """Kaba Türkçe kök: ilk 5 harf (ekler farklı olsa da 'kaybetti/kaybetmiştir' aynı sayılır)."""
    return {w[:5] for w in re.findall(r"\w+", (text or "").lower()) if len(w) > 3}


def dedupe_scenes(scenes: list[dict], min_words: int) -> tuple[list[dict], list[str]]:
    """Aynı bilgiyi tekrar eden SONRAKİ sahneyi kaldırır: aynı iddia kümesi veya kelimelerin büyük ölçüde örtüşmesi.
    Toplam uzunluk min_words'ün altına düşecekse durur."""
    out, notes = list(scenes), []
    total = sum(words(x.get("voiceover", "")) for x in out)
    i = 0
    while i < len(out):
        j = i + 1
        while j < len(out):
            a, b = out[i], out[j]
            ra, rb = set(a.get("claim_refs") or []), set(b.get("claim_refs") or [])
            ta, tb = _tok(a.get("voiceover")), _tok(b.get("voiceover"))
            jac = len(ta & tb) / max(1, len(ta | tb))
            no_new_info = bool(rb) and rb <= ra                  # sonraki sahne hiçbir yeni bilgiye dayanmıyor
            shared = bool(ra & rb)
            last_of_act = b.get("_act") and sum(1 for x in out if x.get("_act") == b.get("_act")) <= 1
            if not last_of_act and ((no_new_info and jac >= 0.1) or (shared and jac >= 0.3) or jac >= 0.45):
                w = words(b.get("voiceover", ""))
                if total - w < min_words:
                    return out, notes + ["tekrar ayıklama: uzunluk sınırı nedeniyle durdu"]
                notes.append(f"tekrar kaldırıldı: '{b.get('voiceover', '')[:50]}…'")
                total -= w
                out.pop(j)
                continue
            j += 1
        i += 1
    return out, notes


def number_issues(scenes: list[dict], claims: str) -> dict[int, list[str]]:
    """Sahne → kaynakta olmayan sayılar (1 tabanlı sahne numarası)."""
    out = {}
    for i, sc in enumerate(scenes, 1):
        bad = numbers.unsupported(sc.get("voiceover", "") + " " + (sc.get("on_screen_text") or ""), claims)
        if bad:
            out[i] = sorted(numbers.fmt(b) for b in bad)
    return out


def _validate_act(data: dict, n_scenes: int, words_target: int, claim_status: dict, act: str, claims: str = "") -> list[str]:
    scenes = data.get("scenes") or []
    errs = []
    if not scenes:
        return [f"{act}: sahne yok"]
    if not (n_scenes - 1 <= len(scenes) <= n_scenes + 2):
        errs.append(f"{act}: {len(scenes)} sahne; yaklaşık {n_scenes} olmalı")
    for i, sc in enumerate(scenes, 1):
        errs += [f"{act} {e}" for e in _validate_scene(sc, i, claim_status)]
    for i, nums in number_issues(scenes, claims).items():
        errs.append(f"{act} sahne {i}: kaynakta olmayan sayı {', '.join(nums)} — iddialardaki sayıyı kullanın veya sayıyı kaldırın")
    # Bölüm uzunluğunda geniş tolerans: toplamı editör turu tamamlar (gereksiz düzeltme çağrısı = kota israfı).
    total = sum(words(sc.get("voiceover", "")) for sc in scenes)
    lo, hi = int(words_target * (1 - ACT_TOLERANCE)), int(words_target * (1 + ACT_TOLERANCE))
    if not lo <= total <= hi:
        errs.append(f"{act}: {total} kelime; {lo}-{hi} arasında olmalı (hedef {words_target}). "
                    f"{'Daha fazla sahne/cümle ekleyin.' if total < lo else 'Kısaltın.'}")
    return errs


def script_doc(conn, step) -> StepResult:
    p = conn.execute("select * from projects where id=%s", (step["project_id"],)).fetchone()
    if (p.get("format") or "documentary") == "vlog":
        from .vlog import script_vlog            # döngüsel içe aktarmayı önler
        return script_vlog(conn, step, p)
    if (p.get("format") or "documentary") == "review":
        # Öneri biçimi yalnızca ~1 dakikalık Shorts üretir (veritabanı bu adımı zaten atlar)
        return StepResult(output={"skipped": "Öneri biçimi yalnızca Shorts üretir"})
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
Write EXACTLY {n_scenes} scenes, about {int(SCENE_WORDS * LENGTH_BOOST)} words of narration each (total about {int(words_target * LENGTH_BOOST)} words).
Each scene needs 3-4 full sentences. Short scenes are the most common mistake — write fully.
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
        data, errs = _write_with_repair(conn, prompt, lambda d, a=a, w=words_target, n=n_scenes: _validate_act(d, n, w, status, a, claims),
                                        f"script_act_{a}")
        scenes = data.get("scenes") or []
        acts_out.append({"act": a, "scenes": scenes})
        all_errs += errs
        previous = " ".join(sc.get("voiceover", "") for sc in scenes[-2:])

    scenes = [{**sc, "_act": a["act"]} for a in acts_out for sc in a["scenes"]]
    if not scenes:
        raise RuntimeError("Senaryo üretilemedi: " + "; ".join(all_errs[:5]))
    words_before = sum(words(sc.get("voiceover", "")) for sc in scenes)

    # 3) Editör turu: kaynakta olmayan ayrıntılar, tekrarlar, zaman kipi, eksik uzunluk
    scenes, edits = _edit(conn, p, "doc", scenes, claims, status, budget,
                          "5. The ending (kapanis) must be strong and resonant, not a list. It must NOT introduce earlier "
                          "background facts (e.g. events before the climax); it reflects on legacy and today.\n"
                          "6. Acts must stay chronological: no scene in sonuclar/kapanis may describe events before the turning point.")
    scenes, dd_notes = dedupe_scenes(scenes, int(budget * (1 - TOLERANCE)) - int(budget * 0.15))
    edits["notes"] = edits.get("notes", []) + dd_notes
    full = {"title": outline.get("title") or p["title"], "logline": outline.get("logline"),
            "acts": [{"act": a, "scenes": [sc for sc in scenes if sc.get("_act") == a]} for a in ACTS],
            "editor_notes": edits.get("notes", [])}
    final_errs = validate_doc(full, budget, status) + [
        f"sahne {i}: rapor dili (-mıştır/-mektedir) — anlatım diline çevirin" for i, x in enumerate(scenes, 1)
        if report_style(x.get("voiceover", ""))] + [
        f"sahne {i}: kaynakta olmayan sayı {', '.join(n)}" for i, n in number_issues(scenes, claims).items()]
    version, total = _save(conn, p["id"], "doc", full, scenes, wpm, final_errs)
    return StepResult(output={"version": version, "scenes": len(scenes), "words": total, "words_before_edit": words_before,
                              "est_minutes": round(total / wpm, 2), "budget_words": budget,
                              "repeats_after": len(find_repeats(scenes)), "editor_notes": edits.get("notes", [])[:12],
                              "number_issues_after": edits.get("number_issues_after", {}),
                              "validation_errors": final_errs})


# ----------------------------------------------------------------- editör turu
def find_repeats(scenes: list[dict]) -> dict[str, list[int]]:
    """Aynı iddianın birden fazla sahnede kullanılması (tekrar adayı)."""
    used: dict[str, list[int]] = {}
    for i, sc in enumerate(scenes, 1):
        for ref in sc.get("claim_refs") or []:
            used.setdefault(ref, []).append(i)
    return {r: idx for r, idx in used.items() if len(idx) > 1}


def apply_edits(scenes: list[dict], edits: dict, claims: str = "", guard: bool = False,
                new_claims_only: bool = False) -> tuple[list[dict], list[str]]:
    """Editörün sahne bazlı düzeltmelerini uygular: replace / delete / insert_after (1 tabanlı, ORİJİNAL numaralar).

    guard=True: sahneyi %85'ten fazla kısaltan veya kaynakta olmayan sayı ekleyen değişiklik reddedilir;
    silme yalnızca sahnenin tüm iddiaları başka sahnede de geçiyorsa kabul edilir.
    """
    out = [dict(sc) for sc in scenes]
    rejected: list[str] = []
    for e in edits.get("replace", []):
        i = e.get("scene")
        if not (isinstance(i, int) and 1 <= i <= len(out)):
            continue
        old_vo, new_vo = out[i - 1].get("voiceover", ""), e.get("voiceover", out[i - 1].get("voiceover", ""))
        if guard:
            if words(new_vo) < 0.85 * words(old_vo):
                rejected.append(f"sahne {i}: kısaltma reddedildi")
                continue
            if numbers.unsupported(new_vo, claims) - numbers.unsupported(old_vo, claims):
                rejected.append(f"sahne {i}: yeni kaynaksız sayı reddedildi")
                continue
        for k in ("voiceover", "claim_refs", "visual_description", "on_screen_text", "disputed"):
            if k in e:
                out[i - 1][k] = e[k]
    deleted = set()
    for i in edits.get("delete", []):
        if not (isinstance(i, int) and 1 <= i <= len(out)):
            continue
        if guard:
            others = {r for j, sc in enumerate(out, 1) if j != i and j not in deleted for r in sc.get("claim_refs") or []}
            if not set(out[i - 1].get("claim_refs") or []) <= others:
                rejected.append(f"sahne {i}: silme reddedildi (bilgisi başka sahnede yok)")
                continue
        deleted.add(i)
    inserts: dict[int, list[dict]] = {}
    for e in edits.get("insert_after", []):
        i, sc = e.get("scene"), e.get("new_scene")
        if isinstance(i, int) and 0 <= i <= len(out) and isinstance(sc, dict) and sc.get("voiceover"):
            if guard and numbers.unsupported(sc["voiceover"], claims):
                rejected.append(f"sahne {i} sonrası ekleme: kaynaksız sayı reddedildi")
                continue
            if new_claims_only:
                used_now = {r for x in out for r in x.get("claim_refs") or []} | {
                    r for xs in inserts.values() for x in xs for r in x.get("claim_refs") or []}
                refs = set(sc.get("claim_refs") or [])
                if not refs or refs <= used_now:
                    rejected.append(f"sahne {i} sonrası ekleme: yeni bilgi yok (tekrar) reddedildi")
                    continue
            inserts.setdefault(i, []).append(sc)
    result = [{**sc, "_act": out[0].get("_act")} for sc in inserts.get(0, [])]
    for i, sc in enumerate(out, 1):
        if i not in deleted:
            result.append(sc)
        for new in inserts.get(i, []):
            base = {k: sc.get(k) for k in ("_act", "camera_move", "transition", "music", "sfx", "search_keywords", "visual_description")}
            result.append({**base, **new, "_act": sc.get("_act")})
    return result, rejected


def film_word(p) -> str:
    return {"vlog": "travel vlog", "review": "recommendation video (anime / series / film)"}.get(p.get("format") or "", "documentary")


def _listing(scenes):
    return "\n".join(f"{i}. [{sc.get('_act')}] ({', '.join(sc.get('claim_refs') or [])}) {sc.get('voiceover')}"
                     for i, sc in enumerate(scenes, 1))


def _unused(scenes, claims):
    used = {r for sc in scenes for r in sc.get("claim_refs") or []}
    return [line for line in claims.splitlines() if line.split(" ", 1)[0] not in used]


def _edit(conn, p, kind: str, scenes: list[dict], claims: str, status: dict, budget: int, extra_rules: str,
          style: str | None = None) -> tuple[list[dict], dict]:
    style = style or STYLE
    lang = LANG_NAME.get(p["language"], p["language"])
    total = sum(words(sc.get("voiceover", "")) for sc in scenes)
    nums = number_issues(scenes, claims)
    edits = llm.complete_json(conn, SYSTEM, f"""
You are the fact-checking EDITOR of a {film_word(p)} script in {lang} about: {p['topic']}.

Fix the script with minimal, targeted edits. Never shorten a scene; rewrite it at similar or greater length.
1. NUMBERS: these scenes contain numbers that are NOT in the claims (scene: numbers): {json.dumps(nums, ensure_ascii=False)}
   Replace them with the exact number from the claims, or remove the number.
2. FACTS: every factual detail (event, number, date, cause, physical detail like "roofs collapsed", duration like "in seconds")
   must be supported by the CLAIMS. Rewrite sentences that add unsupported facts. Atmosphere without new facts is fine.
   A hypothesis in the claims must stay a hypothesis ("…olabileceği düşünülüyor").
3. REPETITION: do not state the same fact twice. Repeated claim usage (claim: scenes): {json.dumps(find_repeats(scenes), ensure_ascii=False)}
   Prefer rewriting the second occurrence with a different (unused) claim over deleting it.
4. TENSE: facts true today (e.g. UNESCO listing) use present tense ("yer alıyor"); the story uses narrative past (-dı/-di).
{extra_rules}

{style}

Return JSON with scene numbers from the CURRENT list (1-based):
{{"replace": [{{"scene": n, "voiceover": "...", "claim_refs": ["C#"]}}],
  "delete": [n, ...],
  "insert_after": [{{"scene": n, "new_scene": {{"voiceover": "...", "claim_refs": ["C#"], "visual_description": "...",
                                                "search_keywords": ["..."], "on_screen_text": null}}}}],
  "notes": ["short list of what you fixed"]}}

CURRENT SCRIPT ({total} words):
{_listing(scenes)}

UNUSED CLAIMS:
{chr(10).join(_unused(scenes, claims)) or "none"}

ALL CLAIMS:
{claims}
""", task=f"script_edit_{kind}", temperature=0.4)
    scenes, rejected = apply_edits(scenes, edits, claims, guard=True)
    notes = list(edits.get("notes", [])) + rejected

    # Genişletme turu: hâlâ kısa ise yalnızca YENİ sahne eklenir (mevcut sahnelere dokunulmaz)
    total = sum(words(sc.get("voiceover", "")) for sc in scenes)
    deficit = budget - total
    if deficit > budget * TOLERANCE:
        n_new = max(1, round(deficit / SCENE_WORDS))
        ext = llm.complete_json(conn, SYSTEM, f"""
The {film_word(p)} script in {lang} about {p['topic']} is too short: {total} words, target {budget}.
INSERT about {n_new} NEW scenes of {SCENE_WORDS}-{SCENE_WORDS + 15} words each where they fit the story best.
Use ONLY the UNUSED CLAIMS (new facts). A scene that repeats a fact already told will be rejected. Do not change existing scenes.
Place each new scene where it fits {"in the chapter (stop) the fact belongs to" if (p.get("format") or "") == "vlog" else "in the chapter (title) the fact belongs to" if (p.get("format") or "") == "review" else "CHRONOLOGICALLY"}.
Every fact and number must come from the claims.
{extra_rules}

{style}

Return JSON: {{"insert_after": [{{"scene": n, "new_scene": {{"voiceover": "...", "claim_refs": ["C#"],
  "visual_description": "...", "search_keywords": ["..."], "on_screen_text": null}}}}]}}

CURRENT SCRIPT:
{_listing(scenes)}

UNUSED CLAIMS:
{chr(10).join(_unused(scenes, claims)) or "none"}

ALL CLAIMS:
{claims}
""", task=f"script_extend_{kind}", temperature=0.6)
        scenes, rejected = apply_edits(scenes, {"insert_after": ext.get("insert_after", [])}, claims, guard=True,
                                       new_claims_only=True)
        notes += [f"genişletme: {len(ext.get('insert_after', []))} sahne önerildi"] + rejected
    return scenes, {"notes": notes, "number_issues_before": nums, "number_issues_after": number_issues(scenes, claims)}

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
    vlog = (p.get("format") or "documentary") == "vlog"
    review = (p.get("format") or "documentary") == "review"
    if vlog:
        from .vlog import STYLE_VLOG
        style = STYLE_VLOG
    elif review:
        from . import review as RV
        style = RV.style(conn)
    else:
        style = STYLE
    film = film_word(p)
    prompt = f"""
Write an independent YouTube Shorts script ({p['shorts_seconds']} seconds, vertical 9:16) in {lang}.
Topic: {p['topic']}. {"This Shorts is a STANDALONE recommendation video (there is no longer video)." if review else f'The full {film} is titled: "{doc["t"] if doc else p["title"]}".'}

Write EXACTLY {len(per_scene)} scenes with these narration lengths in words: {[round(w * LENGTH_BOOST) if i else w for i, w in enumerate(per_scene)]}.
- Scene 1 = HOOK (about 3 seconds): instant curiosity — a shocking fact, a question or tension. It must be TRUE to the claims.
- {"The most striking places/facts of the route as a quick teaser" if vlog else "The host's quick-fire picks: one or two spoiler-free lines per title, name each title clearly" if review else "One focused story arc with escalating tension"}; it must make sense on its own.
- Last scene: {"a short question to the viewer (e.g. which one they will start with / have they seen it) — no 'like and subscribe'" if review else f'a natural line that makes viewers want the full {film} (no "like and subscribe")'}.
- Visuals must work in vertical framing (close-ups, details, single subjects).

{style}

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
    scenes, edits = _edit(conn, p, "shorts", scenes, claims, status, budget,
                          "5. This is a 45-60 s Shorts: keep scene 1 as a hook of at most 8 words. Keep 6-10 scenes.\n"
                          + ("6. The last line is a short question to the viewer — no 'abone ol', 'beğen', no mention of a longer video."
                           if review else
                           f"6. The last line invites to the full {film} naturally — no 'izleyin', 'hemen', 'abone ol', 'beğen'."),
                          style=style)
    scenes, dd_notes = dedupe_scenes(scenes, int(budget * (1 - TOLERANCE)) - 10)
    scenes, short_note = _shorten(conn, p, scenes, budget, claims, style)
    mark_needs_check(scenes, practical_refs(conn, p["id"]))
    if review:
        RV.shorts_layouts(scenes, RV.titles(conn, p["id"]))
    data = {**data, "scenes": scenes, "editor_notes": edits.get("notes", []) + dd_notes + short_note}
    errs = validate_shorts(data, budget, status) + [
        f"sahne {i}: kaynakta olmayan sayı {', '.join(n)}" for i, n in number_issues(scenes, claims).items()]
    version, total = _save(conn, p["id"], "shorts", data, scenes, wpm, errs)
    return StepResult(output={"version": version, "scenes": len(scenes), "words": total,
                              "est_seconds": round(total / wpm * 60, 1), "budget_words": budget,
                              "editor_notes": edits.get("notes", [])[:10], "validation_errors": errs})


def _shorten(conn, p, scenes: list[dict], budget: int, claims: str, style: str) -> tuple[list[dict], list[str]]:
    """Shorts hedefi aşıyorsa sahneleri kısaltır (60 sn sınırı: render'da hızlandırma en fazla %15).

    Sahne sayısı ve iddia kimlikleri korunur; kaynakta olmayan sayı ekleyen veya hâlâ uzun kalan sonuç reddedilir.
    """
    total = sum(words(x.get("voiceover", "")) for x in scenes)
    hi = int(budget * (1 + TOLERANCE))
    if total <= hi:
        return scenes, []
    lang = LANG_NAME.get(p["language"], p["language"])
    per = [max(4, round(words(x.get("voiceover", "")) * budget / total)) for x in scenes]
    out = llm.complete_json(conn, SYSTEM, f"""
This YouTube Shorts script in {lang} is too long: {total} words, it must be about {budget} words to fit 60 seconds.
Shorten each scene to the target word count below. Keep the meaning, order, hook and closing line; keep facts and numbers
exactly as they are (drop a detail rather than change it). Do not add new facts.
Target words per scene: {per}

{style}

Return JSON: {{"scenes": ["shortened narration of scene 1", "... scene 2", ...]}}  (exactly {len(scenes)} items)

SCENES:
{chr(10).join(f"{i}. {x.get('voiceover', '')}" for i, x in enumerate(scenes, 1))}
""", task="shorts_shorten", temperature=0.3)
    texts = out.get("scenes") or []
    if len(texts) != len(scenes) or not all(isinstance(t, str) and t.strip() for t in texts):
        return scenes, ["kısaltma reddedildi: sahne sayısı uyuşmadı"]
    new = [{**x, "voiceover": t.strip()} for x, t in zip(scenes, texts)]
    new_total = sum(words(x["voiceover"]) for x in new)
    flat = lambda sc: {n for v in number_issues(sc, claims).values() for n in v}      # noqa: E731
    if new_total > hi or not flat(new) <= flat(scenes):                              # yeni kaynaksız sayı eklenmemeli
        return scenes, [f"kısaltma reddedildi: {new_total} kelime veya kaynakta olmayan sayı"]
    return new, [f"Shorts kısaltıldı: {total} → {new_total} kelime"]


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
            "camera_move, transition, music, sfx, search_keywords, claim_refs, on_screen_text, word_count, needs_check, layout, title_ref) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (project_id, sid, kind, i, s.get("_act"), round(w / wpm * 60, 2), s["voiceover"], s.get("visual_description"),
             s.get("camera_move"), s.get("transition"), s.get("music"), s.get("sfx"), s.get("search_keywords") or [],
             s.get("claim_refs") or [], s.get("on_screen_text"), w, bool(s.get("needs_check")), s.get("layout"), s.get("title_ref")))
    return version, total



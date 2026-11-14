"""Araştırma motoru (Stage 3).

research_collect : LLM araştırma planı + ücretsiz kaynaklardan metin toplama
research_verify  : iddiaları alıntılarıyla çıkarma, alıntıları kaynak metinde DOĞRULAMA,
                   eşdeğer iddiaları birleştirme, çelişkileri bulma, durum atama
research_report  : araştırma raporu (Markdown) + kısa özet

Uydurma kaynağa karşı önlem: LLM'in verdiği her alıntı, kaynak metninde gerçekten geçiyor mu
diye kodla kontrol edilir. Geçmeyen alıntı destek sayılmaz.
"""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher

from psycopg.types.json import Jsonb

from . import llm, sources as S
from .handlers import StepResult

CHUNK_CHARS = 24000
LANG_NAME = {"tr": "Turkish", "en": "English"}

SYSTEM = (
    "You are a meticulous historical researcher and fact-checker for documentary films. "
    "You only state what the provided sources support. You always answer with valid JSON."
)


# ----------------------------------------------------------------- yardımcılar
def _project(conn, project_id):
    return conn.execute("select * from projects where id=%s", (project_id,)).fetchone()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def quote_in_text(quote: str, text: str, threshold: float = 0.85) -> bool:
    """Alıntı kaynak metinde geçiyor mu? (büyük/küçük harf, noktalama ve aksan farkları yok sayılır)"""
    q, t = _norm(quote), _norm(text)
    if len(q) < 12:
        return False
    if q in t:
        return True
    m = SequenceMatcher(None, t, q, autojunk=False).find_longest_match(0, len(t), 0, len(q))
    if m.size >= len(q) * threshold:
        return True
    # Kelime bazlı yaklaşık eşleşme: alıntının kelimelerinin büyük kısmı ardışık bir pencerede geçiyor mu?
    qw, tw = q.split(), t.split()
    n = len(qw)
    if n < 4:
        return False
    qs = set(qw)
    for i in range(0, max(1, len(tw) - n + 1)):
        window = tw[i:i + n + 3]
        if len(qs.intersection(window)) >= threshold * len(qs):
            return True
    return False


def _relevant(src: S.Source, keywords: list[str]) -> bool:
    if src.collector == "wikipedia":
        return True
    blob = _norm(src.title + " " + src.text)
    return any(_norm(k) in blob for k in keywords if len(_norm(k)) >= 3)


# Kaynak türüne göre metin üst sınırı ve toplam bütçe (LLM kotasını korur: ~4-5 çıkarma çağrısı)
TYPE_CAP = {"encyclopedia": 12000, "academic": 4000, "archive": 3000}
TOTAL_BUDGET = 110000
TYPE_PRIORITY = {"encyclopedia": 0, "academic": 1, "archive": 2}


def select_sources(found: list[S.Source], keywords: list[str]) -> list[S.Source]:
    """Tekilleştir (URL, DOI, başlık), alakasızları ele, metni kırp, toplam bütçeye sığdır."""
    seen, unique = set(), []
    for s in found:
        keys = {s.url, s.extra.get("doi"), (s.collector, _norm(s.title))}
        keys.discard(None)
        if keys & seen or not _relevant(s, keywords):
            continue
        seen |= keys
        s.text = s.text[:TYPE_CAP.get(s.source_type, 4000)]
        unique.append(s)
    # Öncelik: ansiklopedi (iskelet) → akademik → arşiv; aynı türde bulunma sırası korunur
    unique.sort(key=lambda s: TYPE_PRIORITY.get(s.source_type, 3))
    out, total = [], 0
    for s in unique:
        if total + len(s.text) > TOTAL_BUDGET:
            continue
        out.append(s)
        total += len(s.text)
    return out


# ----------------------------------------------------------------- 1) toplama
def collect(conn, step) -> StepResult:
    p = _project(conn, step["project_id"])
    lang = p["language"]
    plan = llm.complete_json(conn, SYSTEM, f"""
Plan research for a {p['target_minutes']}-minute documentary.
Topic: {p['topic']}
Narration language: {LANG_NAME.get(lang, lang)}

Return JSON:
{{"subquestions": [6-10 concrete research questions: background, timeline, key people, places, numbers, causes, consequences],
  "queries_en": [4-6 short English search queries for encyclopedias and academic databases],
  "queries_native": [2-3 short search queries in {LANG_NAME.get(lang, lang)}],
  "keywords": [5-10 single distinctive keywords to judge relevance, include English and native spellings]}}
""", task="research_plan", temperature=0.2)
    q_en = plan.get("queries_en") or [p["topic"]]
    q_native = plan.get("queries_native") or []
    keywords = plan.get("keywords") or p["topic"].split()

    found: list[S.Source] = []
    errors: list[str] = []

    def run(name, fn, *args):
        try:
            found.extend(fn(*args))
        except Exception as e:  # noqa: BLE001 — bir kaynak çökerse diğerleri sürer
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:160]}")

    for q in q_en[:4]:
        run("wikipedia:en", S.wikipedia, q, "en", 2)
    if lang != "en":
        for q in q_native[:2]:
            run(f"wikipedia:{lang}", S.wikipedia, q, lang, 2)
    for q in q_en[:3]:
        run("crossref", S.crossref, q, 5)
        run("openalex", S.openalex, q, 5)
    for q in q_en[:2]:
        run("loc", S.library_of_congress, q, 5)
        run("archive", S.internet_archive, q, 5)
        run("europeana", S.europeana, q, 5)

    unique = select_sources(found, keywords)

    if not unique:
        raise RuntimeError("Hiç kaynak bulunamadı. Hatalar: " + " | ".join(errors))

    # Yeniden çalıştırılabilir: projenin önceki kaynakları silinir
    conn.execute("delete from claims where project_id=%s", (p["id"],))
    conn.execute("delete from sources where project_id=%s", (p["id"],))
    for i, s in enumerate(unique, 1):
        sid = conn.execute(
            "insert into sources (project_id, url, title, publisher, source_type, collector, published, ref) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s) on conflict (project_id, url) do nothing returning id",
            (p["id"], s.url, s.title, s.publisher, s.source_type, s.collector, s.published, f"S{i}"),
        ).fetchone()
        if sid:
            conn.execute("insert into source_excerpts (source_id, project_id, lang, text) values (%s,%s,%s,%s)",
                         (sid["id"], p["id"], s.lang, s.text))
    for e in errors:
        conn.execute("insert into error_logs (project_id, job_id, step_key, level, message) values (%s,%s,%s,'warning',%s)",
                     (p["id"], step["job_id"], step["step_key"], f"Kaynak toplanamadı — {e}"))

    by_type: dict[str, int] = {}
    for s in unique:
        by_type[s.source_type] = by_type.get(s.source_type, 0) + 1
    return StepResult(output={"plan": plan, "sources": len(unique), "by_type": by_type, "collector_errors": errors})


# ----------------------------------------------------------------- 2) doğrulama
def _load_sources(conn, project_id):
    return conn.execute(
        "select s.id, s.ref, s.title, s.publisher, s.collector, s.source_type, e.text "
        "from sources s join source_excerpts e on e.source_id = s.id where s.project_id=%s order by s.ref", (project_id,)
    ).fetchall()


def _chunks(rows):
    chunk, size = [], 0
    for r in rows:
        block = f"[{r['ref']}] {r['title']} — {r['publisher']}\n{r['text']}\n"
        if chunk and size + len(block) > CHUNK_CHARS:
            yield chunk
            chunk, size = [], 0
        chunk.append(block)
        size += len(block)
    if chunk:
        yield chunk


def verify(conn, step) -> StepResult:
    p = _project(conn, step["project_id"])
    lang = LANG_NAME.get(p["language"], p["language"])
    rows = _load_sources(conn, p["id"])
    if not rows:
        raise RuntimeError("Doğrulanacak kaynak yok; önce araştırma toplama adımı çalışmalı")
    text_by_ref = {r["ref"]: r for r in rows}

    # a) Parça parça iddia çıkarma
    raw: list[dict] = []
    for chunk in _chunks(rows):
        res = llm.complete_json(conn, SYSTEM, f"""
Topic: {p['topic']}
From the SOURCES below, extract the factual claims a documentary on this topic would need
(dates, sequence of events, people, places, numbers, causes, consequences, scholarly debates).

Rules:
- Every claim must be supported by a VERBATIM quote (5-30 words, copied exactly, original language) from one source.
- Do not use outside knowledge. Do not invent quotes.
- Write "text" in {lang}.
- If sources disagree (e.g. different dates or numbers), extract each version as its own claim.

Return JSON: {{"claims": [{{"text": "...", "category": "time|person|place|number|cause|consequence|debate|context",
  "importance": 1-3, "event_date": "free text or null", "source_ref": "S#", "quote": "..."}}]}}

SOURCES:
{''.join(chunk)}
""", task="claim_extract", temperature=0.1)
        raw.extend(res.get("claims", []))

    # b) Alıntıları kaynak metninde kontrol et
    checked = []
    for i, c in enumerate(raw, 1):
        src = text_by_ref.get(str(c.get("source_ref", "")).strip())
        ok = bool(src and c.get("quote") and quote_in_text(c["quote"], src["text"]))
        checked.append({**c, "id": i, "verified_quote": ok})
    dropped = [c for c in checked if not c["verified_quote"]]
    valid = [c for c in checked if c["verified_quote"]]

    # c) Eşdeğer iddiaları birleştir, çelişkileri bul
    listing = "\n".join(f"{c['id']}. [{c['source_ref']}] {c['text']}" for c in valid)
    merged = llm.complete_json(conn, SYSTEM, f"""
Topic: {p['topic']}
Below are claims extracted from different sources (id. [source] text).
1) Group claims that state the SAME fact (even if worded differently).
2) Identify CONFLICTS: groups that contradict each other (different dates, numbers, causes...).

Return JSON:
{{"groups": [{{"text": "best single wording in {lang}", "category": "...", "importance": 1-3,
   "event_date": "... or null", "members": [claim ids]}}],
 "conflicts": [{{"groups": [indexes into groups array, 0-based], "note": "explanation in {lang}"}}]}}
Every claim id must appear in exactly one group.

CLAIMS:
{listing}
""", task="claim_merge", temperature=0.1)

    groups = merged.get("groups", [])
    by_id = {c["id"]: c for c in valid}
    conflict_note: dict[int, str] = {}
    for cf in merged.get("conflicts", []):
        for gi in cf.get("groups", []):
            if isinstance(gi, int) and 0 <= gi < len(groups):
                conflict_note[gi] = cf.get("note", "Kaynaklar çelişiyor")

    # Hiçbir gruba girmeyen geçerli iddiaları kaybetme
    used = {m for g in groups for m in g.get("members", []) if isinstance(m, int)}
    for c in valid:
        if c["id"] not in used:
            groups.append({"text": c["text"], "category": c.get("category"), "importance": c.get("importance", 2),
                           "event_date": c.get("event_date"), "members": [c["id"]]})

    conn.execute("delete from claims where project_id=%s", (p["id"],))
    stats = {"verified": 0, "weak": 0, "conflict": 0, "extracted": len(raw), "quotes_rejected": len(dropped)}
    for gi, g in enumerate(groups):
        members = [by_id[m] for m in g.get("members", []) if m in by_id]
        if not members:
            continue
        support = [{"source_ref": m["source_ref"], "quote": m["quote"]} for m in members]
        indep = {S.independence_key(text_by_ref[m["source_ref"]]["publisher"], text_by_ref[m["source_ref"]]["collector"])
                 for m in members}
        status = "conflict" if gi in conflict_note else ("verified" if len(indep) >= 2 else "weak")
        stats[status] += 1
        src_ids = list({text_by_ref[m["source_ref"]]["id"] for m in members})
        conn.execute(
            "insert into claims (project_id, ref, text, status, conflict_note, source_ids, category, importance, "
            "event_date, support, independent_sources) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (p["id"], f"C{gi + 1}", g["text"], status, conflict_note.get(gi), src_ids, g.get("category"),
             max(1, min(3, int(g.get("importance") or 2))), g.get("event_date"), Jsonb(support), len(indep)))

    if not (stats["verified"] + stats["weak"]):
        raise RuntimeError("Kaynaklarla desteklenen iddia çıkarılamadı")
    return StepResult(output=stats)


# ----------------------------------------------------------------- 3) rapor
STATUS_TR = {"verified": "Doğrulandı", "weak": "Tek kaynak", "conflict": "Çelişkili"}


def build_markdown(p, summary: str, claims, srcs) -> str:
    ref_url = {s["ref"]: s for s in srcs}
    out = [f"# Araştırma Raporu — {p['title']}", "", f"**Konu:** {p['topic']}  ", f"**Hedef süre:** {p['target_minutes']} dk", ""]
    out += ["## Özet", "", summary or "—", ""]
    counts = {k: sum(1 for c in claims if c["status"] == k) for k in STATUS_TR}
    out += ["## Doğrulama durumu", "",
            f"- Doğrulandı (≥2 bağımsız kaynak): **{counts['verified']}**",
            f"- Tek kaynak (zayıf): **{counts['weak']}**",
            f"- Çelişkili: **{counts['conflict']}**", ""]

    def line(c):
        refs = ", ".join(sorted({s["source_ref"] for s in c["support"]}))
        date = f"**{c['event_date']}** — " if c.get("event_date") else ""
        return f"- `{c['ref']}` {date}{c['text']} _({refs})_"

    timeline = sorted((c for c in claims if c["status"] == "verified"), key=lambda c: (-c["importance"], c["ref"]))
    out += ["## Doğrulanmış bilgiler", ""] + [line(c) for c in timeline] + [""]
    weak = [c for c in claims if c["status"] == "weak"]
    out += ["## Tek kaynağa dayanan bilgiler", "", "_Senaryoda kullanılabilir ama dikkatli ifade edilmeli._", ""]
    out += [line(c) for c in weak] + [""]
    conf = [c for c in claims if c["status"] == "conflict"]
    out += ["## Çelişkiler", ""]
    out += ([f"{line(c)}\n  - ⚠️ {c['conflict_note']}" for c in conf] or ["Kaynaklar arasında çelişki bulunmadı."]) + [""]
    out += ["## Kaynaklar", ""]
    for s in srcs:
        pub = f" ({s['published']})" if s.get("published") else ""
        out.append(f"- **{s['ref']}** [{s['title']}]({s['url']}) — {s['publisher']}{pub} · {s['source_type']}")
    return "\n".join(out) + "\n"


def report(conn, step) -> StepResult:
    p = _project(conn, step["project_id"])
    claims = conn.execute("select * from claims where project_id=%s order by importance desc, ref", (p["id"],)).fetchall()
    srcs = conn.execute("select * from sources where project_id=%s order by ref", (p["id"],)).fetchall()
    usable = [c for c in claims if c["status"] in ("verified", "weak")]
    listing = "\n".join(f"{c['ref']} [{c['status']}] {c['text']}" for c in usable[:150])
    res = llm.complete_json(conn, SYSTEM, f"""
Write a concise research summary (150-250 words) in {LANG_NAME.get(p['language'], p['language'])} for a documentary team
about: {p['topic']}. Use ONLY the claims below. Mention where evidence is single-source.
Return JSON: {{"summary": "..."}}

CLAIMS:
{listing}
""", task="research_summary", temperature=0.3)
    md = build_markdown(p, res.get("summary", ""), claims, srcs)
    version = conn.execute("select coalesce(max(version),0)+1 v from research_reports where project_id=%s", (p["id"],)).fetchone()["v"]
    stats = {"sources": len(srcs), **{k: sum(1 for c in claims if c["status"] == k) for k in STATUS_TR}}
    conn.execute("insert into research_reports (project_id, version, summary, markdown, stats) values (%s,%s,%s,%s,%s)",
                 (p["id"], version, res.get("summary"), md, json.dumps(stats)))
    return StepResult(output={"version": version, **stats})

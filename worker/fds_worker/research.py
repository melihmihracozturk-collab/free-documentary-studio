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
    """Kaynak konuyla ilgili mi? Çekirdek kelime başlıkta geçmeli ya da metnin başında yeterince sık geçmeli.

    Wikipedia aramaları geniş sonuç döndürdüğü için (ör. "Mount Ararat") daha sıkı eşik uygulanır.
    """
    keys = [_norm(k) for k in keywords if len(_norm(k)) >= 3]
    title = _norm(src.title)
    if any(k in title for k in keys):
        return True
    head = " " + _norm(src.text[:3000]) + " "
    need = 3 if src.collector == "wikipedia" else 1
    return sum(head.count(" " + k) for k in keys) >= need


# Kaynak türüne göre metin üst sınırı ve toplam bütçe (LLM kotasını korur: ~4-5 çıkarma çağrısı)
# Ansiklopedi maddesi başına 12k: tek uzun madde bütçeyi doldurmasın, daha çok farklı madde (kişiler, olaylar,
# proje dilindeki Vikipedi) girsin. İttihat ve Terakki'de 30k sınırla yalnızca 3 madde girebilmişti.
TYPE_CAP = {"encyclopedia": 12000, "academic": 4000, "archive": 3000}
TOTAL_BUDGET = 110000
TYPE_BUDGET = {"encyclopedia": 55000, "academic": 40000, "archive": 15000}
TYPE_PRIORITY = {"encyclopedia": 0, "academic": 1, "archive": 2}


MEDIA_WORK = re.compile(
    r"\b(is|was) an? (\d{4} )?(\w+ ){0,4}(film|movie|television series|tv series|docudrama|documentary series|miniseries|"
    r"video game|novel|play|opera|musical|song|album|anime|comic)\b"
    r"|\b(dizisidir|filmidir|belgesel dizisi|bilgisayar oyunu|romanıdır)\b", re.I)


def is_media_work(src: S.Source) -> bool:
    """Film, dizi, oyun, roman gibi eserleri anlatan ansiklopedi maddeleri tarih kaynağı değildir (ör. Netflix
    belgesel-dizisi 'Rise of Empires: Ottoman' 1453 araştırmasına kaynak olarak girmişti)."""
    return src.source_type == "encyclopedia" and bool(MEDIA_WORK.search(src.text[:600]))


def _interleave(srcs: list[S.Source]) -> list[S.Source]:
    """Toplayıcı + dil gruplarını sırayla karıştırır (round-robin); grup içi sıra korunur.

    Böylece bütçe yalnızca ilk sorgunun sonuçlarıyla (ör. hep İngilizce Vikipedi) dolmaz.
    """
    groups: dict[tuple, list[S.Source]] = {}
    for s in srcs:
        groups.setdefault((s.collector, getattr(s, "lang", None)), []).append(s)
    out, lists = [], list(groups.values())
    while any(lists):
        for g in lists:
            if g:
                out.append(g.pop(0))
    return out


def select_sources(found: list[S.Source], keywords: list[str]) -> list[S.Source]:
    """Tekilleştir (URL, DOI, başlık), alakasızları ele, metni kırp, toplam bütçeye sığdır."""
    seen, unique = set(), []
    for s in found:
        keys = {s.url, s.extra.get("doi"), (s.collector, _norm(s.title))}
        keys.discard(None)
        if keys & seen or not _relevant(s, keywords) or is_media_work(s):
            continue
        seen |= keys
        s.text = s.text[:TYPE_CAP.get(s.source_type, 4000)]
        unique.append(s)
    unique = _interleave(unique)
    # Tür başına bütçe: uzun ansiklopedi maddeleri akademik kaynakları dışarıda bırakamaz (1453'te 22 → 4 kaynak olmuştu)
    used = {t: 0 for t in TYPE_BUDGET}
    out, total = [], 0
    for s in unique:
        t = s.source_type if s.source_type in TYPE_BUDGET else "archive"
        if used[t] + len(s.text) > TYPE_BUDGET[t] or total + len(s.text) > TOTAL_BUDGET:
            continue
        out.append(s)
        used[t] += len(s.text)
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
  "keywords": [5-10 single distinctive keywords to judge relevance, include English and native spellings],
  "core_keywords": [2-4 proper nouns WITHOUT which a source is off-topic (e.g. the place/event/person), English and native spellings]}}
""", task="research_plan", temperature=0.2)
    q_en = plan.get("queries_en") or [p["topic"]]
    q_native = plan.get("queries_native") or []
    keywords = plan.get("core_keywords") or plan.get("keywords") or p["topic"].split()

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
            "insert into sources (project_id, url, title, publisher, source_type, collector, published, ref, independence_key) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict (project_id, url) do nothing returning id",
            (p["id"], s.url, s.title, s.publisher, s.source_type, s.collector, s.published, f"S{i}", S.independence_key(s)),
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
        "select s.id, s.ref, s.title, s.publisher, s.collector, s.source_type, s.independence_key, e.text "
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


def _extract(conn, p, lang, chunk):
    return llm.complete_json(conn, SYSTEM, f"""
Topic: {p['topic']}
From the SOURCES below, extract the factual claims a documentary on this topic would need:
dates and sequence of events, people, places, numbers, causes, consequences, eyewitness accounts,
scientific findings and scholarly debates. Aim for 15-30 claims if the sources allow; skip off-topic material.

Rules:
- Every claim must be supported by a VERBATIM quote (5-30 words, copied exactly, original language) from one source.
- Do not use outside knowledge. Do not invent quotes.
- Write "text" in {lang}, one fact per claim.
- If sources disagree or mention a debate (e.g. different dates or numbers), extract each version as its own claim.

Return JSON: {{"claims": [{{"text": "...", "category": "time|person|place|number|cause|consequence|debate|context",
  "importance": 1-3, "event_date": "free text or null", "source_ref": "S#", "quote": "..."}}]}}

SOURCES:
{''.join(chunk)}
""", task="claim_extract", temperature=0.1)


def _merge(conn, p, lang, valid):
    listing = "\n".join(f"{c['id']}. [{c['source_ref']}] {c['text']}" for c in valid)
    return llm.complete_json(conn, SYSTEM, f"""
Topic: {p['topic']}
Below are claims extracted from different sources (id. [source] text).
1) Group claims that state the SAME fact (even if worded differently). Give each group an id "G1", "G2", ...
2) Identify CONFLICTS: only groups that genuinely CONTRADICT each other about the same thing
   (e.g. different dates for the same event, incompatible numbers). Different facts are NOT conflicts.
   A general statement does NOT conflict with a more specific one ("in AD 79" vs "in October AD 79" is NOT a conflict;
   "24 August AD 79" vs "October AD 79" IS a conflict). Put each competing VERSION in its own group and list those groups.
   If a debate is mentioned by a single claim (e.g. "scholars debate whether August or October"), keep it as one group
   with category "debate" instead of a conflict.

Return JSON:
{{"groups": [{{"gid": "G1", "text": "best single wording in {lang}", "category": "...", "importance": 1-3,
   "event_date": "... or null", "members": [claim ids]}}],
 "conflicts": [{{"gids": ["G3", "G7"], "note": "what exactly disagrees, in {lang}"}}]}}
Every claim id must appear in exactly one group.

CLAIMS:
{listing}
""", task="claim_merge", temperature=0.1)


def _cross_check(conn, p, groups, chunk):
    """Tek kaynaklı iddialar için diğer kaynaklarda birebir destek alıntısı ara."""
    listing = "\n".join(f"{g['gid']}: {g['text']} (already from {', '.join(sorted(g['refs']))})" for g in groups)
    return llm.complete_json(conn, SYSTEM, f"""
Topic: {p['topic']}
For each CLAIM below, look for passages in the SOURCES that independently support the SAME fact.
Only report support from sources other than those the claim is already from.
Copy each supporting quote VERBATIM (5-30 words, original language). If there is no support, omit the claim.
Do not report passages that merely mention the topic or contradict the claim.

Return JSON: {{"support": [{{"gid": "G#", "source_ref": "S#", "quote": "..."}}]}}

CLAIMS:
{listing}

SOURCES:
{''.join(chunk)}
""", task="claim_crosscheck", temperature=0.1)


def verify(conn, step) -> StepResult:
    p = _project(conn, step["project_id"])
    lang = LANG_NAME.get(p["language"], p["language"])
    rows = _load_sources(conn, p["id"])
    if not rows:
        raise RuntimeError("Doğrulanacak kaynak yok; önce araştırma toplama adımı çalışmalı")
    text_by_ref = {r["ref"]: r for r in rows}
    chunks = list(_chunks(rows))

    def indep(ref):
        r = text_by_ref[ref]
        return r["independence_key"] or f"{r['collector']}:{r['publisher']}"

    # a) Parça parça iddia çıkarma
    raw: list[dict] = []
    for chunk in chunks:
        raw.extend(_extract(conn, p, lang, chunk).get("claims", []))

    # b) Alıntıları kaynak metninde kontrol et
    checked = []
    for i, c in enumerate(raw, 1):
        src = text_by_ref.get(str(c.get("source_ref", "")).strip())
        ok = bool(src and c.get("quote") and quote_in_text(c["quote"], src["text"]))
        checked.append({**c, "id": i, "source_ref": str(c.get("source_ref", "")).strip(), "verified_quote": ok})
    valid = [c for c in checked if c["verified_quote"]]
    dropped = len(checked) - len(valid)
    if not valid:
        raise RuntimeError("Kaynaklarla desteklenen iddia çıkarılamadı")

    # c) Eşdeğer iddiaları birleştir, çelişkileri bul
    merged = _merge(conn, p, lang, valid)
    by_id = {c["id"]: c for c in valid}
    groups: list[dict] = []
    used: set[int] = set()
    for g in merged.get("groups", []):
        members = [by_id[m] for m in g.get("members", []) if isinstance(m, int) and m in by_id and m not in used]
        if not members:
            continue
        used |= {m["id"] for m in members}
        groups.append({**g, "gid": str(g.get("gid") or f"G{len(groups) + 1}"),
                       "support": [{"source_ref": m["source_ref"], "quote": m["quote"]} for m in members]})
    for c in valid:  # hiçbir gruba girmeyenleri kaybetme
        if c["id"] not in used:
            groups.append({"gid": f"X{c['id']}", "text": c["text"], "category": c.get("category"),
                           "importance": c.get("importance", 2), "event_date": c.get("event_date"),
                           "support": [{"source_ref": c["source_ref"], "quote": c["quote"]}]})
    gid_index = {g["gid"]: g for g in groups}
    for g in groups:
        g["refs"] = {s["source_ref"] for s in g["support"]}

    # d) Çapraz doğrulama: tek bağımsız kaynaklı iddialara diğer kaynaklarda destek ara (alıntılar yine kodla kontrol edilir)
    cross_added = cross_rejected = 0
    weak = [g for g in groups if len({indep(r) for r in g["refs"]}) < 2]
    if weak:
        for chunk in chunks:
            res = _cross_check(conn, p, weak, chunk)
            for s in res.get("support", []):
                g = gid_index.get(str(s.get("gid", "")))
                ref = str(s.get("source_ref", "")).strip()
                if not g or ref not in text_by_ref or ref in g["refs"] or not s.get("quote"):
                    continue
                if quote_in_text(s["quote"], text_by_ref[ref]["text"]):
                    g["support"].append({"source_ref": ref, "quote": s["quote"], "cross_check": True})
                    g["refs"].add(ref)
                    cross_added += 1
                else:
                    cross_rejected += 1

    # e) Çelişkiler (sabit grup kimlikleriyle)
    conflict_note: dict[str, str] = {}
    for cf in merged.get("conflicts", []):
        gids = [str(x) for x in cf.get("gids", []) if str(x) in gid_index]
        if len(gids) >= 2:
            for gid in gids:
                conflict_note[gid] = cf.get("note") or "Kaynaklar çelişiyor"

    conn.execute("delete from claims where project_id=%s", (p["id"],))
    stats = {"verified": 0, "weak": 0, "conflict": 0, "extracted": len(raw), "quotes_rejected": dropped,
             "cross_check_added": cross_added, "cross_check_rejected": cross_rejected}
    for n, g in enumerate(groups, 1):
        n_indep = len({indep(r) for r in g["refs"]})
        status = "conflict" if g["gid"] in conflict_note else ("verified" if n_indep >= 2 else "weak")
        stats[status] += 1
        conn.execute(
            "insert into claims (project_id, ref, text, status, conflict_note, source_ids, category, importance, "
            "event_date, support, independent_sources) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (p["id"], f"C{n}", g["text"], status, conflict_note.get(g["gid"]),
             list({text_by_ref[r]["id"] for r in g["refs"]}), g.get("category"),
             max(1, min(3, int(g.get("importance") or 2))), g.get("event_date"), Jsonb(g["support"]), n_indep))
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
about: {p['topic']}. Use ONLY the claims below. Write flowing prose: do NOT list claim ids or status labels.
Tell the story chronologically, then add one or two sentences on what is debated or rests on a single source.
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

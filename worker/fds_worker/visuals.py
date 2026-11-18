"""Görsel plan ve görsel eşleştirme (Stage 5).

visual_plan : her sahne için arşiv sorguları (senaryodaki İngilizce arama ifadeleri + konunun çekirdek kelimeleri).
              LLM kullanmaz.
asset_match : arşivlerde arar, lisansı uygun olmayanları eler, adayları puanlar, her sahneye tekrar etmeyen
              en iyi görseli atar, seçilenleri R2'ye indirir (en fazla 2560 px, JPEG), credits.txt üretir.
"""
from __future__ import annotations

import io
import re
import unicodedata

from psycopg.types.json import Jsonb

from . import http, images, storage
from .handlers import StepResult
from .licenses import allowed, needs_attribution

MAX_CANDIDATES = 6
MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024
LONG_SIDE = 2560
SOURCE_PREF = {"met": 1.0, "smithsonian": 1.0, "commons": 0.8, "openverse": 0.4}
LICENSE_PREF = {"cc0": 1.0, "pd": 1.0, "by": 0.7, "by-sa": 0.5, "nc": 0.2}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


STOP = set("the a an of in on at and or to from with for by is was are de la le el di del".split())


def _tokens(s: str) -> set[str]:
    return {t for t in _norm(s).split() if len(t) > 2 and t not in STOP}


def _settings(conn) -> dict:
    rows = conn.execute("select key, value from settings where key like 'license_%%'").fetchall()
    return {r["key"]: r["value"] for r in rows}


def _core_keywords(conn, project_id) -> list[str]:
    row = conn.execute("select output from job_steps where project_id=%s and step_key='research_collect' and output is not null "
                       "order by finished_at desc nulls last limit 1", (project_id,)).fetchone()
    plan = (row or {}).get("output", {}) or {}
    plan = plan.get("plan", {}) if isinstance(plan, dict) else {}
    keys = [k for k in (plan.get("core_keywords") or []) if k and k.strip()]
    return sorted(keys, key=lambda k: not k.isascii())[:4]          # sorgu öneki için ASCII olan önce


# ----------------------------------------------------------------- 1) görsel plan
def queries_for(scene: dict, core: list[str]) -> list[str]:
    qs = [q.strip() for q in (scene.get("search_keywords") or []) if q and q.strip()][:3]
    if core:
        # Konu adı geçmeyen sorgulara çekirdek kelime ekle (alakasız sonuçları azaltır)
        raw = [q for q in qs if not _tokens(q) & _tokens(" ".join(core))]
        qs = [q if q not in raw else f"{core[0]} {q}" for q in qs]
        # Önek eklenmiş uzun sorgular Commons'ta çoğu zaman sıfır sonuç verir ("Committee of Union and
        # Progress Talaat Pasha portrait"); sahnenin kendi sorgusu da aranır, puanlama konu kelimesini ödüllendirir.
        qs += raw
        qs.append(core[0])                                        # son çare: konunun kendisi
    seen, out = set(), []
    for q in qs:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def plan(conn, step) -> StepResult:
    core = _core_keywords(conn, step["project_id"])
    scenes = conn.execute("select id, kind, idx, search_keywords from scenes where project_id=%s order by kind, idx",
                          (step["project_id"],)).fetchall()
    if not scenes:
        raise RuntimeError("Sahne yok; senaryo adımları tamamlanmalı")
    for s in scenes:
        conn.execute("update scenes set visual_queries=%s where id=%s", (queries_for(s, core), s["id"]))
    return StepResult(output={"scenes": len(scenes), "core_keywords": core,
                              "unique_queries": len({q for s in scenes for q in queries_for(s, core)})})


# ----------------------------------------------------------------- 2) eşleştirme
def relevance(c: images.ImageCandidate, scene: dict, core: list[str]) -> tuple[float, float]:
    """(sahne kelimeleriyle örtüşme 0-1, konu adı geçiyor mu 0/1).

    Konu adı TAM ifade olarak aranır: "Committee of Union and Progress" kelimelere bölününce
    "The Progress of the Century" gibi alakasız eserler konu puanı alıyordu.
    """
    words = _tokens(" ".join((scene.get("search_keywords") or []) + [scene.get("visual_description") or ""]))
    words -= {t for k in core for t in _tokens(k)} if any(len(_tokens(k)) > 1 for k in core) else set()
    text = _tokens(f"{c.title} {c.description}")
    rel = len(words & text) / max(1, min(len(words), 6))
    hay = f" {_norm(f'{c.title} {c.description}')} "
    topic = 1.0 if any(_norm(k) and f" {_norm(k)} " in hay for k in core) else 0.0
    return rel, topic


def score(c: images.ImageCandidate, scene: dict, core: list[str], kind: str) -> float:
    rel, topic = relevance(c, scene, core)
    w, h = c.width or 0, c.height or 0
    need = 1920 if kind == "doc" else 1080                         # Shorts dikey: kısa kenar ≥ 1080 yeterli
    res = 0.6 if not w else min(1.0, (min(w, h) if kind == "shorts" else w) / need)
    return round(3 * rel + 1.5 * topic + 1.5 * res + SOURCE_PREF.get(c.source, 0.3) + LICENSE_PREF.get(c.license_class, 0), 3)


SEARCHERS = {"met": images.met, "commons": images.commons, "smithsonian": images.smithsonian}


def search_all(queries: list[str], cache: dict, errors: list[str], with_openverse: bool) -> list[images.ImageCandidate]:
    found: list[images.ImageCandidate] = []
    for q in queries:
        names = list(SEARCHERS) + (["openverse"] if with_openverse else [])
        for name in names:
            key = (name, q)
            if key not in cache:
                fn = SEARCHERS.get(name) or images.openverse
                try:
                    cache[key] = fn(q)
                except Exception as e:  # noqa: BLE001 — bir arşiv çökerse diğerleri sürer
                    cache[key] = []
                    errors.append(f"{name} '{q}': {type(e).__name__}: {str(e)[:120]}")
            found += cache[key]
    return found


def match(conn, step) -> StepResult:
    pid = step["project_id"]
    p = conn.execute("select slug from projects where id=%s", (pid,)).fetchone()
    st = _settings(conn)
    allow_nc, allow_sa = st.get("license_allow_nc") is True, st.get("license_allow_sa") is not False
    core = _core_keywords(conn, pid)
    cache: dict = {}
    errors: list[str] = []
    stats = {"scenes": 0, "assigned": 0, "missing": [], "reused": [], "rejected_license": 0, "candidates": 0}
    conn.execute("update scenes set asset_id=null where project_id=%s", (pid,))
    conn.execute("delete from assets where project_id=%s and scene_id is not null", (pid,))

    for kind in ("doc", "shorts"):
        used: set[str] = set()
        scenes = conn.execute("select * from scenes where project_id=%s and kind=%s order by idx", (pid, kind)).fetchall()
        for sc in scenes:
            stats["scenes"] += 1
            qs = sc["visual_queries"] or queries_for(sc, core)
            cands = search_all(qs, cache, errors, with_openverse=False)
            ok = [c for c in cands if allowed(c.license_class, allow_nc, allow_sa)[0] and c.file_url]
            if len(ok) < 3:                                       # yetersizse yedek arşiv
                cands += search_all(qs[:2], cache, errors, with_openverse=True)
                ok = [c for c in cands if allowed(c.license_class, allow_nc, allow_sa)[0] and c.file_url]
            stats["rejected_license"] += len(cands) - len(ok)
            uniq: dict[str, images.ImageCandidate] = {}
            for c in ok:
                uniq.setdefault(c.file_url, c)
            ranked = sorted(uniq.values(), key=lambda c: score(c, sc, core, kind), reverse=True)
            fits = [c for c in ranked if any(relevance(c, sc, core))]      # sahneyle ya da konuyla en az bir bağ
            chosen = next((c for c in fits if c.file_url not in used), None)
            if chosen is None and (fits or ranked):
                # Alakasız yeni görsel yerine ilgili bir görsel tekrar kullanılır; hiç ilgili yoksa en iyisi
                chosen = (fits or ranked)[0]
                stats["reused"].append(f"{kind}#{sc['idx']}")
            top = ranked[:MAX_CANDIDATES]
            if chosen and chosen not in top:
                top = [chosen] + top[:MAX_CANDIDATES - 1]
            chosen_id = None
            for c in top:
                aid = conn.execute(
                    "insert into assets (project_id, scene_id, kind, source, title, source_url, file_url, thumb_url, author, "
                    "license, license_url, license_class, attribution, width, height, score, query, status, is_ai) "
                    "values (%s,%s,'image',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false) returning id",
                    (pid, sc["id"], c.source, c.title, c.page_url, c.file_url, c.thumb_url, c.author, c.license_raw,
                     c.license_url, c.license_class, c.attribution, c.width, c.height, score(c, sc, core, kind), c.query,
                     "approved" if c is chosen else "candidate")).fetchone()["id"]
                if c is chosen:
                    chosen_id = aid
            stats["candidates"] += len(top)
            if chosen_id:
                used.add(chosen.file_url)
                conn.execute("update scenes set asset_id=%s where id=%s", (chosen_id, sc["id"]))
                stats["assigned"] += 1
            else:
                stats["missing"].append(f"{kind}#{sc['idx']}")

    downloaded = download_selected(conn, pid, p["slug"]) if storage.configured() else 0
    write_credits(conn, pid, p["slug"])
    for e in errors[:20]:
        conn.execute("insert into error_logs (project_id, job_id, step_key, level, message) values (%s,%s,%s,'warning',%s)",
                     (pid, step["job_id"], step["step_key"], f"Arşiv araması — {e}"))
    return StepResult(output={**stats, "downloaded": downloaded, "archive_errors": len(errors)})


# ----------------------------------------------------------------- indirme ve atıf
def fetch_image(url: str) -> tuple[bytes, int, int]:
    """Görseli indirir, en fazla LONG_SIDE piksele küçültür, JPEG'e çevirir → (bayt, genişlik, yükseklik)."""
    from PIL import Image

    r = http.request("GET", url, timeout=120)
    if len(r.content) > MAX_DOWNLOAD_BYTES:
        raise RuntimeError("görsel çok büyük")
    img = Image.open(io.BytesIO(r.content))
    img = img.convert("RGB")
    img.thumbnail((LONG_SIDE, LONG_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue(), img.width, img.height


def download_selected(conn, pid, slug) -> int:
    """Sahnelere atanmış ama henüz R2'de olmayan görselleri indirir (render öncesi de çağrılır)."""
    rows = conn.execute("select a.* from assets a join scenes s on s.asset_id = a.id where s.project_id=%s "
                        "and a.storage_key is null", (pid,)).fetchall()
    n = 0
    for a in rows:
        # Aynı dosya başka bir sahne için zaten indirildiyse yeniden indirme (Wikimedia hız sınırına takılmaz)
        twin = conn.execute("select storage_key, sha256, bytes, width, height from assets where project_id=%s "
                            "and file_url=%s and storage_key is not null limit 1", (pid, a["file_url"])).fetchone()
        if twin:
            conn.execute("update assets set storage_key=%s, sha256=%s, bytes=%s, width=%s, height=%s, reject_reason=null "
                         "where id=%s", (twin["storage_key"], twin["sha256"], twin["bytes"], twin["width"], twin["height"],
                                         a["id"]))
            n += 1
            continue
        urls = [a["file_url"]]
        if a["source"] == "commons":
            # Eski kayıtlar orijinal adresi tutuyor olabilir → standart küçük resme çevir; olmazsa 1920 px dene
            urls = [images.commons_download_url(a["file_url"], a["width"])]
            urls.append(images.commons_thumb(re.sub(r"/thumb/(.+)/\d+px-[^/]+$", r"/\1", urls[0]), 1920))
            # upload.wikimedia.org GitHub sunucularını hız sınırına alabiliyor; aynı küçük resim thumb.wikimedia.org'da da var
            urls += [u.replace("https://upload.wikimedia.org/", "https://thumb.wikimedia.org/", 1) for u in urls]
        data = None
        for u in dict.fromkeys(urls):
            try:
                data, w, h = fetch_image(u)
                break
            except Exception as e:  # noqa: BLE001
                err = f"indirilemedi: {type(e).__name__}: {str(e)[:120]}"
        if data is None:
            conn.execute("update assets set reject_reason=%s where id=%s", (err[:200], a["id"]))
            continue
        key = storage.project_key(slug, "assets", f"{a['id']}.jpg")
        sha = storage.upload_bytes(key, data, "image/jpeg")
        conn.execute("update assets set storage_key=%s, sha256=%s, bytes=%s, width=%s, height=%s, reject_reason=null where id=%s",
                     (key, sha, len(data), w, h, a["id"]))
        n += 1
    return n


def credits_text(rows) -> str:
    lines = ["GÖRSEL KAYNAKLARI VE LİSANSLAR", ""]
    for r in rows:
        lic = r["license"] or r["license_class"]
        lines.append(f"[{'Belgesel' if r['scene_kind'] == 'doc' else 'Shorts'} sahne {r['scene_idx']}] {r['title']}")
        lines.append(f"  Yapan: {r['author'] or 'bilinmiyor'} · Lisans: {lic}"
                     + (f" ({r['license_url']})" if r["license_url"] else "")
                     + (" · ATIF ZORUNLU" if needs_attribution(r["license_class"]) else ""))
        lines.append(f"  Kaynak: {r['source_url']}")
    return "\n".join(lines) + "\n"


def write_credits(conn, pid, slug) -> str:
    rows = conn.execute("select a.*, s.kind as scene_kind, s.idx as scene_idx from scenes s join assets a on a.id = s.asset_id "
                        "where s.project_id=%s order by s.kind, s.idx", (pid,)).fetchall()
    text = credits_text(rows)
    if storage.configured():
        storage.upload_bytes(storage.project_key(slug, "assets", "credits.txt"), text.encode(), "text/plain; charset=utf-8")
    return text

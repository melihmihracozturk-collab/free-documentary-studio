"""Teslim (Stage 8): YouTube açıklama metinleri, bölüm zaman damgaları, kaynaklar ve görsel atıfları.

preview_ready : iki videonun da hazır olduğunu doğrular, açıklama metinlerini R2'ye yazar, projeyi tamamlar.
"""
from __future__ import annotations

from . import storage
from .handlers import StepResult
from .licenses import needs_attribution
from .visuals import credits_text

ACT_TITLE = {"giris": "Giriş", "arka_plan": "Tarihsel arka plan", "gelisme": "Olayların gelişimi",
             "donum_noktasi": "Dönüm noktası", "sonuclar": "Sonuçlar", "kapanis": "Kapanış"}


def ts(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600}:{s // 60 % 60:02}:{s % 60:02}" if s >= 3600 else f"{s // 60}:{s % 60:02}"


def chapters(scenes: list[dict], min_len: float = 10.0, titles: dict | None = None) -> list[tuple[float, str]]:
    """YouTube bölümleri: ilk bölüm 0:00'da, en az 3 bölüm, her biri en az 10 sn. Senaryonun bölümlerinden üretilir.

    titles: senaryonun kendi bölüm başlıkları (vlog'da durak adları); yoksa belgesel bölüm adları kullanılır.
    """
    names = {**ACT_TITLE, **(titles or {})}
    out: list[tuple[float, str]] = []
    for s in scenes:
        act = s.get("act")
        if act in names and (not out or out[-1][1] != names[act]):
            start = 0.0 if not out else float(s["start_sec"])
            if out and start - out[-1][0] < min_len:
                continue
            out.append((start, names[act]))
    return out if len(out) >= 3 else []


def doc_description(p: dict, logline: str | None, summary: str | None, chaps, sources, assets) -> str:
    lines = [p["title"], ""]
    if logline:
        lines += [logline, ""]
    if summary:
        lines += [summary.strip(), ""]
    if chaps:
        lines += ["BÖLÜMLER"] + [f"{ts(t)} {name}" for t, name in chaps] + [""]
    if sources:
        lines += ["KAYNAKLAR"] + [f"• {s['title']} — {s['publisher']}{' (' + s['published'] + ')' if s['published'] else ''}: {s['url']}"
                                  for s in sources[:12]] + [""]
    attr = [a for a in assets if needs_attribution(a["license_class"])]
    lines += ["GÖRSELLER",
              "Görseller açık lisanslı arşivlerden alınmıştır (Met Museum Open Access, Wikimedia Commons). "
              "Kamu malı ve CC0 görseller atıf gerektirmez."]
    if attr:
        lines.append("Atıf gerektiren görseller:")
        for a in attr:
            lines.append(f"• {a['title']} — {a['author'] or 'bilinmiyor'} — {a['license'] or a['license_class']} — {a['source_url']}")
    lines += ["", "Müzik: telifsiz, özgün olarak üretilmiş ambiyans."]
    if (p.get("format") or "documentary") == "vlog":
        lines += ["Bu video kaynaklı araştırmaya dayanır. Fiyat, açılış saati ve ulaşım bilgileri değişebilir; "
                  "gitmeden önce resmî sitelerden kontrol edin."]
    else:
        lines += ["Bu belgesel kaynaklı araştırmaya dayanır; tartışmalı bilgiler anlatımda belirtilmiştir."]
    return "\n".join(lines) + "\n"


def shorts_description(p: dict, title: str | None) -> str:
    if (p.get("format") or "documentary") == "vlog":
        return f"{title or p['title']}\n\nTam gezi videosu kanalımızda.\n\n#Shorts #gezi #seyahat\n"
    return f"{title or p['title']}\n\nTam belgesel kanalımızda.\n\n#Shorts #tarih #belgesel\n"


def ready(conn, step) -> StepResult:
    p = conn.execute("select * from projects where id=%s", (step["project_id"],)).fetchone()
    renders = {r["kind"]: r for r in conn.execute(
        "select * from renders where project_id=%s and status='done'", (p["id"],)).fetchall()}
    missing = [k for k in ("doc", "shorts") if k not in renders]
    if missing:
        raise RuntimeError(f"Render eksik: {missing}")
    scripts = {r["kind"]: r for r in conn.execute(
        "select distinct on (kind) kind, content from scripts where project_id=%s order by kind, version desc", (p["id"],)).fetchall()}
    report = conn.execute("select summary from research_reports where project_id=%s order by version desc limit 1",
                          (p["id"],)).fetchone()
    scenes = conn.execute("select act, start_sec from scenes where project_id=%s and kind='doc' order by idx", (p["id"],)).fetchall()
    sources = conn.execute("select title, publisher, published, url from sources where project_id=%s "
                           "order by source_type='academic' desc, ref", (p["id"],)).fetchall()
    assets = conn.execute("select distinct on (a.id) a.* from scenes s join assets a on a.id = s.asset_id where s.project_id=%s",
                          (p["id"],)).fetchall()
    doc_c = (scripts.get("doc") or {}).get("content") or {}
    sh_c = (scripts.get("shorts") or {}).get("content") or {}
    chaps = chapters(scenes, titles=doc_c.get("act_titles"))
    files = {
        "youtube_description.txt": doc_description(p, doc_c.get("logline"), (report or {}).get("summary"), chaps, sources, assets),
        "shorts_description.txt": shorts_description(p, sh_c.get("title")),
        "credits.txt": credits_text(conn.execute(
            "select a.*, s.kind as scene_kind, s.idx as scene_idx from scenes s join assets a on a.id = s.asset_id "
            "where s.project_id=%s order by s.kind, s.idx", (p["id"],)).fetchall()),
    }
    keys = {}
    for name, text in files.items():
        key = storage.project_key(p["slug"], "renders", name)
        storage.upload_bytes(key, text.encode(), "text/plain; charset=utf-8")
        keys[name] = key
    return StepResult(output={"files": keys, "chapters": len(chaps),
                              "doc_seconds": float(renders["doc"]["duration_sec"]),
                              "shorts_seconds": float(renders["shorts"]["duration_sec"])})

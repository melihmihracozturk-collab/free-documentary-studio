"""Açık web kaynakları: Vikipedi maddesinin kaynakçasındaki sayfalar ve GDELT haber arşivi (ücretsiz, anahtarsız).

Güncel konularda (yaşayan kişiler, son olaylar) akademik/arşiv kaynağı yoktur; bilgiler kulüp/kurum resmî
sayfalarında ve haberlerde bulunur. Bu modül:
- Vikipedi maddesinin dış bağlantılarını (dipnotlarda kullanılan haber, resmî site, röportaj sayfaları) okur,
- GDELT DOC API ile son üç ayın haberlerini bulur,
- her sayfanın robots.txt kuralına uyar, yalnızca paragraf metnini alır (iddia çıkarmak için; yeniden yayınlanmaz).
Her alan adı ayrı bağımsız kaynak sayılır (sources.independence_key: "pub:<alan adı>").
"""
from __future__ import annotations

import html as H
import json
import re
from urllib import robotparser
from urllib.parse import urlparse

from . import http
from .sources import MIN_TEXT, Source

PAGE_MAX_TEXT = 20000
SKIP_DOMAINS = ("wikipedia.org", "wikimedia.org", "wikidata.org", "wikiquote.org", "twitter.com", "x.com",
                "instagram.com", "facebook.com", "youtube.com", "youtu.be", "tiktok.com", "google.", "archive.org",
                "doi.org", "worldcat.org", "jstor.org", "books.google", "archive.today", "archive.ph", "linkedin.com")
OFFICIAL_DOMAINS = ("realmadrid.com", "fenerbahce.org", "uefa.com", "fifa.com", "tff.org", "laliga.com",
                    "olympics.com", "galatasaray.org", "bjk.com.tr")
_robots: dict[str, robotparser.RobotFileParser | None] = {}


def domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def skipped(url: str) -> bool:
    d = domain(url)
    return not url.startswith(("http://", "https://")) or any(s in d for s in SKIP_DOMAINS) or \
        url.lower().split("?")[0].endswith((".pdf", ".jpg", ".png", ".mp4"))


def is_official(url: str) -> bool:
    d = domain(url)
    return any(d == o or d.endswith("." + o) for o in OFFICIAL_DOMAINS) or d.endswith(".gov") or ".gov." in d


def allowed(url: str) -> bool:
    """robots.txt: yoksa (404) serbest; okunamıyorsa (hata) temkinli davranıp atlanır."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = robotparser.RobotFileParser()
        try:
            r = http.request("GET", base + "/robots.txt", retries=1, timeout=15)
            if r.status_code >= 400:
                rp.parse([])                       # robots.txt yok → serbest
            else:
                rp.parse(r.text.splitlines())
            _robots[base] = rp
        except Exception:  # noqa: BLE001
            _robots[base] = None
    rp = _robots[base]
    return bool(rp and rp.can_fetch(http.UA, url))


_DROP = re.compile(r"<(script|style|noscript|nav|footer|header|aside|form|figure|svg)\b.*?</\1>", re.S | re.I)
_P = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S | re.I)
_BOILER = re.compile(r"(cookie|çerez|subscribe|abone ol|newsletter|all rights reserved|tüm hakları saklıdır|"
                     r"javascript|reklam|advertisement)", re.I)


def _meta(html: str, *names: str) -> str | None:
    for n in names:
        m = re.search(rf'<meta[^>]+(?:property|name|itemprop)=["\']{re.escape(n)}["\'][^>]*content=["\']([^"\']+)', html, re.I) \
            or re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\']{re.escape(n)}["\']', html, re.I)
        if m:
            return H.unescape(m.group(1)).strip()
    return None


def extract(html: str) -> tuple[str, str | None, str | None]:
    """HTML → (paragraf metni, başlık, yayın tarihi)."""
    title = _meta(html, "og:title", "twitter:title")
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        title = H.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else None
    published = _meta(html, "article:published_time", "datePublished", "pubdate", "date")
    if not published:
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
        published = m.group(1) if m else None
    body = _DROP.sub(" ", html)
    paras = []
    for raw in _P.findall(body):
        t = H.unescape(re.sub(r"<[^>]+>", " ", raw))
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) >= 40 and not _BOILER.search(t):
            paras.append(t)
    return "\n".join(dict.fromkeys(paras))[:PAGE_MAX_TEXT], title, (published or "")[:10] or None


def fetch_page(url: str, lang: str | None = None) -> Source | None:
    if skipped(url) or not allowed(url):
        return None
    try:
        r = http.request("GET", url, retries=1, timeout=20)
    except Exception:  # noqa: BLE001 — erişilemeyen sayfa atlanır
        return None
    if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
        return None
    text, title, published = extract(r.text)
    if len(text) < 2 * MIN_TEXT or re.search(r"\b(error|404|not found|sayfa bulunamadı)\b", title or "", re.I):
        return None                                   # JS ile yüklenen, hata veya boş sayfa
    d = domain(str(r.url))
    return Source(url=str(r.url), title=(title or d)[:300], publisher=d,
                  source_type="official" if is_official(str(r.url)) else "news", collector="web",
                  text=text, lang=lang or "", published=published, extra={"domain": d})


def og_image(url: str) -> dict | None:
    """Sayfanın paylaşım görseli (og:image / twitter:image), başlığı ve açıklaması. robots.txt'ye uyar."""
    if skipped(url) or not allowed(url):
        return None
    try:
        r = http.request("GET", url, retries=1, timeout=20)
    except Exception:  # noqa: BLE001
        return None
    if r.status_code >= 400:
        return None
    img = _meta(r.text, "og:image", "og:image:url", "twitter:image", "twitter:image:src")
    if not img:
        return None
    img = H.unescape(img)
    if img.startswith("//"):
        img = "https:" + img
    elif img.startswith("/"):
        p = urlparse(str(r.url))
        img = f"{p.scheme}://{p.netloc}{img}"
    if not img.startswith("http") or re.search(r"(logo|placeholder|default|favicon)", img, re.I):
        return None
    _, title, published = extract(r.text)
    return {"image": img, "title": title or domain(url), "description": _meta(r.text, "og:description", "description") or "",
            "page": str(r.url), "domain": domain(str(r.url)), "published": published}


def wiki_ref_urls(title: str, lang: str = "en", limit: int = 40) -> list[str]:
    """Vikipedi maddesinin dış bağlantıları (dipnot kaynakları), alan adı başına en fazla 2."""
    data = http.get_json(f"https://{lang}.wikipedia.org/w/api.php", params={
        "action": "query", "format": "json", "prop": "extlinks", "titles": title, "ellimit": 500, "redirects": 1})
    urls = [x.get("*") or x.get("url") for p in (data.get("query") or {}).get("pages", {}).values()
            for x in p.get("extlinks", [])]
    out, per = [], {}
    for u in urls:
        if not u or skipped(u):
            continue
        d = domain(u)
        if per.get(d, 0) >= 2:
            continue
        per[d] = per.get(d, 0) + 1
        out.append(u)
    # Resmî siteler önce
    out.sort(key=lambda u: not is_official(u))
    return out[:limit]


def wiki_refs(title: str, lang: str = "en", limit: int = 12) -> list[Source]:
    out = []
    for u in wiki_ref_urls(title, lang):
        s = fetch_page(u, lang)
        if s:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def gdelt(query: str, limit: int = 8) -> list[Source]:
    """GDELT DOC 2.0 (son ~3 ay haberleri; ücretsiz, anahtarsız). Türkçe ve İngilizce haberler."""
    q = f'"{query}" (sourcelang:turkish OR sourcelang:english)'
    r = http.request("GET", "https://api.gdeltproject.org/api/v2/doc/doc",
                     params={"query": q, "mode": "artlist", "maxrecords": 40, "format": "json", "sort": "hybridrel"})
    try:
        arts = json.loads(r.text or "{}").get("articles", [])
    except ValueError:
        return []
    out, seen = [], set()
    for a in arts:
        u, d = a.get("url", ""), domain(a.get("url", ""))
        if not u or d in seen:
            continue
        seen.add(d)
        lang = "tr" if (a.get("language") or "").lower().startswith("turk") else "en"
        s = fetch_page(u, lang)
        if s:
            out.append(s)
        if len(out) >= limit:
            break
    return out

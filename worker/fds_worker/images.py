"""Açık lisanslı görsel arşivleri (Stage 5). Hepsi ücretsiz; Smithsonian için ücretsiz api.data.gov anahtarı gerekir.

Her toplayıcı ImageCandidate listesi döndürür; lisans sınıfı licenses.classify ile belirlenir.
"""
from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass, field

from . import http
from .licenses import classify

COMMONS_THUMB = 3840          # Commons yalnızca standart genişlikleri verir (…1920, 3840); indirince 2560px'e küçültülür


@dataclass
class ImageCandidate:
    source: str                    # commons | met | openverse | smithsonian
    title: str
    page_url: str                  # insanların açacağı kaynak sayfası
    file_url: str                  # indirilecek dosya
    thumb_url: str                 # panelde önizleme
    license_raw: str
    license_class: str
    license_url: str | None = None
    author: str | None = None
    attribution: str | None = None
    width: int | None = None
    height: int | None = None
    description: str = ""
    query: str = ""
    extra: dict = field(default_factory=dict)


def _strip(s: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# ----------------------------------------------------------------- Wikimedia Commons
def commons_thumb(url: str, width: int = 500) -> str:
    """Orijinal Commons adresinden standart genişlikte küçük resim adresi üretir.

    Wikimedia yalnızca standart genişlikleri (500, 960, 1280, 1920, 3840…) verir; orijinal dosyalara doğrudan
    erişim (hotlink) kota sınırına takılır. Yalnızca jpg/png/gif/webp için uygulanır.
    """
    m = re.match(r"https://upload\.wikimedia\.org/wikipedia/commons/([0-9a-f])/([0-9a-f]{2})/([^/?]+\.(?:jpe?g|png|gif|webp))(?:\?.*)?$",
                 url or "", re.I)
    if not m:
        return url
    a, ab, name = m.groups()
    return f"https://upload.wikimedia.org/wikipedia/commons/thumb/{a}/{ab}/{name}/{width}px-{name}"


STANDARD_WIDTHS = (3840, 1920, 1280, 960, 500)   # Wikimedia'nın verdiği standart küçük resim genişlikleri


def commons_download_url(url: str, width: int | None) -> str:
    """İndirme adresi: orijinal dosya yerine, orijinal genişliği aşmayan en büyük standart küçük resim.

    Orijinal dosyalara toplu erişim kota sınırına (429) takılıyor; standart küçük resimler takılmıyor.
    """
    if "/commons/thumb/" in (url or ""):
        return url                                         # zaten standart küçük resim (API'nin döndürdüğü)
    w = next((x for x in STANDARD_WIDTHS if width and x <= width), 1920)
    return commons_thumb(url, w)


def commons(query: str, limit: int = 8) -> list[ImageCandidate]:
    data = http.get_json("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": limit, "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime", "iiurlwidth": COMMONS_THUMB})
    out = []
    for p in (data.get("query") or {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii or not str(ii.get("mime", "")).startswith("image/"):
            continue
        md = {k: (v or {}).get("value", "") for k, v in (ii.get("extmetadata") or {}).items()}
        lic_raw = " ".join(x for x in (md.get("LicenseShortName"), md.get("License"), md.get("UsageTerms")) if x)
        if md.get("Copyrighted", "").lower() == "false" and not lic_raw:
            lic_raw = "public domain"
        author = _strip(md.get("Artist")) or None
        file_title = p.get("title", "").removeprefix("File:").rsplit(".", 1)[0].replace("_", " ")
        obj = _strip(md.get("ObjectName"))
        # ObjectName bazen Wikidata iç kodları ("label QS:Len,...") veya çok dilli karışık metin içerir
        title = obj if obj and "QS:" not in obj and len(obj) < 140 else file_title
        cls = classify(lic_raw, md.get("LicenseUrl"))
        out.append(ImageCandidate(
            source="commons", title=title[:300], page_url=ii.get("descriptionurl", ""),
            file_url=commons_download_url(ii.get("thumburl") or ii.get("url", ""), ii.get("width")),
            thumb_url=commons_thumb(ii.get("url", "")),
            license_raw=lic_raw[:200], license_class=cls, license_url=md.get("LicenseUrl") or None, author=author,
            attribution=f"{title} — {author or 'bilinmeyen'} — {md.get('LicenseShortName') or lic_raw} — Wikimedia Commons",
            width=ii.get("width"), height=ii.get("height"),
            description=_strip(md.get("ImageDescription"))[:500], query=query))
    return out


# ----------------------------------------------------------------- Met Museum Open Access (CC0)
def met(query: str, limit: int = 5) -> list[ImageCandidate]:
    ids = (http.get_json("https://collectionapi.metmuseum.org/public/collection/v1.1/search",
                         params={"q": query, "hasImages": "true", "limit": limit * 2, "offset": 0}) or {}).get("objectIDs") or []
    out = []
    for oid in ids[: limit * 2]:
        try:
            o = http.get_json(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}", retries=1)
        except Exception:  # noqa: BLE001 — kaldırılmış eser (404) aramayı düşürmesin
            continue
        if not o.get("isPublicDomain") or not o.get("primaryImage"):
            continue                                        # yalnızca kamu malı (CC0) eserler
        author = o.get("artistDisplayName") or o.get("culture") or None
        title = o.get("title") or "Untitled"
        out.append(ImageCandidate(
            source="met", title=title[:300], page_url=o.get("objectURL", ""), file_url=o["primaryImage"],
            thumb_url=o.get("primaryImageSmall") or o["primaryImage"], license_raw="CC0 (Met Open Access, public domain)",
            license_class="cc0", license_url="https://creativecommons.org/publicdomain/zero/1.0/", author=author,
            attribution=f"{title} — {author or 'The Met'} — CC0 — The Metropolitan Museum of Art",
            description=" ".join(x for x in (o.get("objectDate"), o.get("medium"), o.get("department")) if x)[:500],
            query=query, extra={"object_id": oid}))
        if len(out) >= limit:
            break
    return out


# ----------------------------------------------------------------- Openverse (yedek)
def openverse(query: str, limit: int = 6) -> list[ImageCandidate]:
    # commercial + modification: NC ve ND lisanslar sunucu tarafında elenir
    res = http.get_json("https://api.openverse.org/v1/images/", params={
        "q": query, "license_type": "commercial,modification", "page_size": limit, "mature": "false"}).get("results", [])
    out = []
    for r in res:
        lic = f"{r.get('license', '')} {r.get('license_version', '')}".strip()
        cls = classify("cc " + lic if r.get("license") not in ("cc0", "pdm") else r.get("license"), r.get("license_url"))
        out.append(ImageCandidate(
            source="openverse", title=(r.get("title") or "Untitled")[:300], page_url=r.get("foreign_landing_url") or "",
            file_url=r.get("url") or "", thumb_url=r.get("thumbnail") or r.get("url") or "", license_raw=lic,
            license_class=cls, license_url=r.get("license_url"), author=r.get("creator"),
            attribution=r.get("attribution"), width=r.get("width"), height=r.get("height"), query=query,
            extra={"provider": r.get("source")}))
    return out


# ----------------------------------------------------------------- Smithsonian Open Access (CC0, anahtar gerekir)
def smithsonian(query: str, limit: int = 5) -> list[ImageCandidate]:
    key = os.environ.get("SMITHSONIAN_API_KEY", "").strip()
    if not key:
        return []
    rows = http.get_json("https://api.si.edu/openaccess/api/v1.0/search", params={
        "q": f"{query} AND online_media_type:Images", "rows": limit * 2, "api_key": key}).get("response", {}).get("rows", [])
    out = []
    for r in rows:
        media = (((r.get("content") or {}).get("descriptiveNonRepeating") or {}).get("online_media") or {}).get("media") or []
        m = next((x for x in media if (x.get("usage") or {}).get("access") == "CC0"), None)
        if not m:
            continue
        title = r.get("title") or "Untitled"
        out.append(ImageCandidate(
            source="smithsonian", title=title[:300],
            page_url=((r.get("content") or {}).get("descriptiveNonRepeating") or {}).get("record_link", ""),
            file_url=m.get("content", ""), thumb_url=m.get("thumbnail") or m.get("content", ""),
            license_raw="CC0 (Smithsonian Open Access)", license_class="cc0",
            license_url="https://creativecommons.org/publicdomain/zero/1.0/", author=r.get("unitCode"),
            attribution=f"{title} — Smithsonian Institution — CC0", query=query))
        if len(out) >= limit:
            break
    return out

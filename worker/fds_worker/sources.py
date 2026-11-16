"""Ücretsiz bilgi kaynakları. Hepsi anahtarsız çalışır; OpenAlex ve Europeana anahtar varsa eklenir.

Her toplayıcı Source listesi döndürür. Metni olmayan (yalnızca başlık) kayıtlar
iddia doğrulamada işe yaramadığı için atılır.
"""
from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass, field
from urllib.parse import quote

from . import http

MAX_TEXT = 30000
MIN_TEXT = 200


@dataclass
class Source:
    url: str
    title: str
    publisher: str
    source_type: str          # archive | academic | official | encyclopedia | museum | news | web
    collector: str
    text: str
    lang: str = "en"
    published: str | None = None
    extra: dict = field(default_factory=dict)


def _clean(s: str | None) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def wikipedia(query: str, lang: str = "en", limit: int = 3) -> list[Source]:
    base = f"https://{lang}.wikipedia.org/w/api.php"
    hits = http.get_json(base, params={"action": "query", "list": "search", "srsearch": query,
                                       "srlimit": limit, "format": "json"})["query"]["search"]
    out = []
    for h in hits:
        pages = http.get_json(base, params={"action": "query", "prop": "extracts", "explaintext": 1,
                                            "titles": h["title"], "format": "json", "redirects": 1})["query"]["pages"]
        for p in pages.values():
            text = (p.get("extract") or "")
            # Kaynakça / dış bağlantılar bölümlerini at
            text = re.split(r"\n==\s*(References|See also|External links|Kaynakça|Dış bağlantılar|Ayrıca bakınız|Notlar)\s*==", text)[0]
            text = re.sub(r"\n+", "\n", text).strip()[:MAX_TEXT]
            if len(text) >= MIN_TEXT:
                out.append(Source(url=f"https://{lang}.wikipedia.org/wiki/{quote(p['title'].replace(' ', '_'))}",
                                  title=p["title"], publisher="Wikipedia", source_type="encyclopedia",
                                  collector="wikipedia", text=text, lang=lang))
    return out


def crossref(query: str, limit: int = 6) -> list[Source]:
    params = {"query": query, "rows": limit, "filter": "has-abstract:true",
              "select": "DOI,title,container-title,issued,abstract,publisher,author,type"}
    if os.environ.get("CROSSREF_MAILTO"):
        params["mailto"] = os.environ["CROSSREF_MAILTO"]
    items = http.get_json("https://api.crossref.org/works", params=params)["message"]["items"]
    out = []
    for it in items:
        text = _clean(it.get("abstract"))
        if len(text) < MIN_TEXT:
            continue
        year = (it.get("issued", {}).get("date-parts") or [[None]])[0][0]
        out.append(Source(url=f"https://doi.org/{it['DOI']}", title=_clean((it.get("title") or [""])[0]),
                          publisher=(it.get("container-title") or [it.get("publisher", "Crossref")])[0],
                          source_type="academic", collector="crossref", text=text[:MAX_TEXT],
                          published=str(year) if year else None,
                          extra={"doi": it["DOI"].lower(), "work_type": it.get("type", "")}))
    return out


def openalex(query: str, limit: int = 6) -> list[Source]:
    params = {"search": query, "per_page": limit, "filter": "has_abstract:true",
              "select": "id,doi,title,publication_year,abstract_inverted_index,primary_location"}
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    res = http.get_json("https://api.openalex.org/works", params=params)["results"]
    out = []
    for w in res:
        inv = w.get("abstract_inverted_index") or {}
        words = sorted(((pos, word) for word, poss in inv.items() for pos in poss))
        text = " ".join(word for _, word in words)
        if len(text) < MIN_TEXT:
            continue
        src_info = (w.get("primary_location") or {}).get("source") or {}
        venue = src_info.get("display_name") or "OpenAlex"
        doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
        out.append(Source(url=w.get("doi") or w["id"], title=_clean(w.get("title")), publisher=venue,
                          source_type="academic", collector="openalex", text=text[:MAX_TEXT],
                          published=str(w.get("publication_year") or ""),
                          extra={"doi": doi, "work_type": "book-chapter" if src_info.get("type") in ("book", "ebook platform", "book series") else "article"}
                          if doi else {"work_type": "article"}))
    return out


def library_of_congress(query: str, limit: int = 5) -> list[Source]:
    res = http.get_json("https://www.loc.gov/search/", params={"q": query, "fo": "json", "c": limit})["results"]
    out = []
    for r in res:
        desc = r.get("description") or []
        text = _clean(" ".join(desc) if isinstance(desc, list) else desc)
        if len(text) < MIN_TEXT:
            continue
        out.append(Source(url=r.get("url") or r.get("id"), title=_clean(r.get("title")), publisher="Library of Congress",
                          source_type="archive", collector="loc", text=text[:MAX_TEXT], published=r.get("date")))
    return out


def internet_archive(query: str, limit: int = 5) -> list[Source]:
    res = http.get_json("https://archive.org/advancedsearch.php", params={
        "q": f"({query}) AND mediatype:texts", "fl[]": ["identifier", "title", "description", "date", "creator"],
        "rows": limit, "output": "json"})["response"]["docs"]
    out = []
    for d in res:
        desc = d.get("description")
        text = _clean(" ".join(desc) if isinstance(desc, list) else desc)
        if len(text) < MIN_TEXT:
            continue
        out.append(Source(url=f"https://archive.org/details/{d['identifier']}", title=_clean(str(d.get("title", ""))),
                          publisher="Internet Archive", source_type="archive", collector="archive",
                          text=text[:MAX_TEXT], published=str(d.get("date", ""))[:10] or None))
    return out


def europeana(query: str, limit: int = 5) -> list[Source]:
    key = os.environ.get("EUROPEANA_API_KEY")
    if not key:
        return []
    res = http.get_json("https://api.europeana.eu/record/v2/search.json",
                        params={"wskey": key, "query": query, "rows": limit, "profile": "standard"}).get("items", [])
    out = []
    for it in res:
        text = _clean(" ".join(it.get("dcDescription") or []))
        if len(text) < MIN_TEXT:
            continue
        out.append(Source(url=it.get("guid", ""), title=_clean((it.get("title") or [""])[0]),
                          publisher=(it.get("dataProvider") or ["Europeana"])[0], source_type="archive",
                          collector="europeana", text=text[:MAX_TEXT], published=(it.get("year") or [None])[0]))
    return out


BOOK_TYPES = {"book-chapter", "book-section", "book-part", "book", "monograph", "edited-book", "reference-entry"}


def independence_key(src: "Source") -> str:
    """Bağımsızlık sayımı.

    - Wikipedia: tüm diller ve maddeler TEK kaynak (çeviriler/birbirinden kopyalar).
    - Kitap bölümleri: aynı kitap TEK kaynak.
    - Dergi makaleleri: her makale ayrı kaynak (aynı dergide farklı yazarlar).
    - Arşiv kayıtları: yayıncı/kurum başına tek kaynak.
    """
    if src.collector == "wikipedia":
        return "wikipedia"
    if src.source_type == "academic":
        if src.extra.get("work_type") in BOOK_TYPES:
            return "book:" + (src.publisher or "").strip().lower()
        return "work:" + (src.extra.get("doi") or src.url)
    return "pub:" + (src.publisher or src.collector).strip().lower()

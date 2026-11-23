"""Yapım katalogları (öneri biçimi): AniList (anime, anahtarsız), TMDB (film/dizi/anime, ücretsiz anahtar), Vikipedi afişi.

Her arama bir Title döndürür: yapı bilgisi (yıl, tür, bölüm, puan, stüdyo), afiş adresi, baskın renk ve araştırmada
iddia çıkarılabilecek bir metin (Source). Kaynak metni yapı alanlarından cümle olarak üretilir; böylece LLM'in
alıntıları ("Episodes: 28") kodla doğrulanabilir.

Afişler telif hakkı sahiplerinindir; yalnızca inceleme/eleştiri amaçlı kullanılır (license_class = "promo").
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from . import http
from .sources import MIN_TEXT, Source, _clean

ANILIST = "https://graphql.anilist.co"
TMDB = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p/"

ANILIST_QUERY = """
query ($search: String) {
  Page(perPage: 6) { media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
    id siteUrl isAdult format status episodes duration season seasonYear source countryOfOrigin
    title { romaji english native }
    description(asHtml: false)
    genres averageScore popularity
    studios(isMain: true) { nodes { name } }
    coverImage { extraLarge color }
    bannerImage
  } }
}"""

FORMAT_TR = {"TV": "TV anime dizisi", "TV_SHORT": "kısa TV anime dizisi", "MOVIE": "anime filmi", "OVA": "OVA",
             "ONA": "internet anime dizisi", "SPECIAL": "özel bölüm", "movie": "film", "tv": "dizi"}


@dataclass
class Title:
    ref: str                       # oneri_1, oneri_2, ...
    name: str                      # ekranda görünen ad (proje dilinde yaygın ad)
    kind: str                      # anime | series | film
    original: str | None = None
    year: int | None = None
    genres: list[str] = field(default_factory=list)
    score: float | None = None     # 0-100
    score_source: str | None = None
    episodes: int | None = None
    seasons: int | None = None
    runtime: int | None = None     # dakika (film) / bölüm süresi
    studio: str | None = None
    format: str | None = None
    poster_url: str | None = None
    poster_page: str | None = None
    poster_source: str | None = None
    color: str | None = None       # baskın renk (#rrggbb)
    url: str | None = None

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], "")}

    @staticmethod
    def from_json(d: dict) -> "Title":
        return Title(**{k: v for k, v in d.items() if k in Title.__dataclass_fields__})


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def similar(a: str, b: str) -> bool:
    """Aranan ad ile bulunan ad aynı yapım mı? (küçük harf, noktalama yok; biri diğerini içeriyorsa yeterli)"""
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a == b or a in b or b in a)


# ----------------------------------------------------------------- AniList
def anilist(query: str, year: int | None = None) -> tuple[dict, Source] | None:
    """year verilirse aynı adlı yapımlardan o yılın yapımı seçilir (ör. Berserk 1997 / 2016)."""
    import httpx

    try:
        r = http.request("POST", ANILIST, json={"query": ANILIST_QUERY, "variables": {"search": query}})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:          # AniList "bulunamadı" için 404 döndürür
            return None
        raise
    found = ((r.json().get("data") or {}).get("Page") or {}).get("media") or []

    def names(m):
        t = m["title"]
        return [x for x in (t.get("english"), t.get("romaji"), t.get("native")) if x]
    # Arama sırası korunur; adı tam eşleşen önce, sonra adı içeren ilk sonuç
    ok = [m for m in found if not m.get("isAdult") and any(similar(query, n) for n in names(m))]
    exact = [m for m in ok if any(_norm(query) == _norm(n) for n in names(m))]
    if not ok:
        return None
    pool = exact or ok
    same_year = [m for m in pool if year and m.get("seasonYear") == year]
    m = (same_year or pool)[0]
    t = m["title"]
    studio = ", ".join(n["name"] for n in (m.get("studios") or {}).get("nodes") or [])
    desc = _clean(re.sub(r"\(Source:[^)]*\)", "", m.get("description") or ""))
    main = t.get("english") or t.get("romaji")
    facts = [f"{main} ({t.get('romaji')}) is a Japanese anime ({(m.get('format') or '').replace('_', ' ')})."]
    if m.get("seasonYear"):
        facts.append(f"It premiered in the {(m.get('season') or '').lower()} {m['seasonYear']} season.".replace("the  ", "the "))
    if m.get("episodes"):
        facts.append(f"It has {m['episodes']} episodes" + (f" of about {m['duration']} minutes each." if m.get("duration") else "."))
    if studio:
        facts.append(f"It was animated by {studio}.")
    if m.get("source"):
        facts.append(f"Source material: {m['source'].replace('_', ' ').lower()}.")
    if m.get("genres"):
        facts.append(f"Genres: {', '.join(m['genres'])}.")
    if m.get("averageScore"):
        facts.append(f"Its average score on AniList is {m['averageScore']} out of 100.")
    text = " ".join(facts) + ("\nSynopsis: " + desc if desc else "")
    meta = {"original": t.get("native") or t.get("romaji"), "year": m.get("seasonYear"), "genres": m.get("genres") or [],
            "score": m.get("averageScore"), "score_source": "AniList" if m.get("averageScore") else None,
            "episodes": m.get("episodes"), "runtime": m.get("duration"), "studio": studio or None,
            "format": FORMAT_TR.get(m.get("format") or "", m.get("format")),
            "poster_url": (m.get("coverImage") or {}).get("extraLarge"), "poster_page": m.get("siteUrl"),
            "poster_source": "anilist", "color": (m.get("coverImage") or {}).get("color"), "url": m.get("siteUrl"),
            "name_en": main}
    src = Source(url=m["siteUrl"], title=main, publisher="AniList", source_type="catalog", collector="anilist",
                 text=text, lang="en")
    return meta, src


# ----------------------------------------------------------------- TMDB
def tmdb_key() -> str | None:
    return (os.environ.get("TMDB_API_KEY") or "").strip() or None


def _tmdb(path: str, **params) -> dict:
    key = tmdb_key()
    headers = {}
    if key and key.startswith("eyJ"):            # v4 "okuma erişim belirteci" (Bearer)
        headers["Authorization"] = f"Bearer {key}"
    else:
        params["api_key"] = key
    return http.get_json(f"{TMDB}{path}", params=params, headers=headers)


def tmdb(query: str, kind: str, lang: str = "tr", year: int | None = None) -> tuple[dict, Source] | None:
    """kind: film → /movie, diğerleri → /tv. Türkçe açıklama yoksa İngilizce kullanılır."""
    if not tmdb_key():
        return None
    media = "movie" if kind == "film" else "tv"
    params = {"query": query, "include_adult": "false", "language": "en-US"}
    if year:
        params["year" if media == "movie" else "first_air_date_year"] = year
    hits = _tmdb(f"/search/{media}", **params).get("results") or []
    hits = [h for h in hits if similar(query, h.get("title") or h.get("name") or "")
            or similar(query, h.get("original_title") or h.get("original_name") or "")]
    if not hits:
        return None
    h = max(hits[:5], key=lambda x: x.get("popularity") or 0)
    d = _tmdb(f"/{media}/{h['id']}", language="en-US")
    loc = _tmdb(f"/{media}/{h['id']}", language={"tr": "tr-TR"}.get(lang, "en-US")) if lang != "en" else d
    name = d.get("title") or d.get("name")
    date = d.get("release_date") or d.get("first_air_date") or ""
    year_ = int(date[:4]) if date[:4].isdigit() else None
    genres = [g["name"] for g in d.get("genres") or []]
    creators = ", ".join(c["name"] for c in d.get("created_by") or [])
    companies = ", ".join(c["name"] for c in (d.get("production_companies") or [])[:3])
    facts = [f"{name} is a {year_ or ''} {'film' if media == 'movie' else 'television series'}.".replace("a  ", "a ")]
    if media == "movie" and d.get("runtime"):
        facts.append(f"Its runtime is {d['runtime']} minutes.")
    if media == "tv":
        if d.get("number_of_seasons"):
            facts.append(f"It has {d['number_of_seasons']} seasons and {d.get('number_of_episodes')} episodes.")
        if creators:
            facts.append(f"It was created by {creators}.")
    if companies:
        facts.append(f"Production companies: {companies}.")
    if genres:
        facts.append(f"Genres: {', '.join(genres)}.")
    if d.get("tagline"):
        facts.append(f"Tagline: {d['tagline']}")
    text = " ".join(facts) + "\nOverview: " + (d.get("overview") or "")
    if loc is not d and loc.get("overview"):
        text += "\nÖzet: " + loc["overview"]
    page = f"https://www.themoviedb.org/{media}/{h['id']}"
    meta = {"original": d.get("original_title") or d.get("original_name"), "year": year_, "genres": genres,
            "score": round(d["vote_average"] * 10) if d.get("vote_average") and d.get("vote_count", 0) >= 50 else None,
            "score_source": "TMDB" if d.get("vote_average") and d.get("vote_count", 0) >= 50 else None,
            "episodes": d.get("number_of_episodes"), "seasons": d.get("number_of_seasons"),
            "runtime": d.get("runtime") or None, "studio": creators or companies or None,
            "format": FORMAT_TR[media], "poster_url": (TMDB_IMG + "w780" + d["poster_path"]) if d.get("poster_path") else None,
            "poster_page": page, "poster_source": "tmdb", "url": page, "name_en": name,
            "name_local": loc.get("title") or loc.get("name")}
    src = Source(url=page, title=name, publisher="TMDB", source_type="catalog", collector="tmdb", text=text, lang="en")
    return meta, src


# ----------------------------------------------------------------- Vikipedi afişi (anahtarsız yedek)
def wikipedia_poster(title: str, lang: str = "en") -> tuple[str, str] | None:
    """Maddenin ana görseli (film/dizi maddelerinde genellikle afiş). Dönüş: (dosya adresi, madde adresi)."""
    data = http.get_json(f"https://{lang}.wikipedia.org/w/api.php", params={
        "action": "query", "prop": "pageimages", "piprop": "original", "pilicense": "any", "titles": title, "format": "json", "redirects": 1})
    for p in (data.get("query") or {}).get("pages", {}).values():
        src = (p.get("original") or {}).get("source")
        if src and not src.lower().endswith(".svg"):
            return src, f"https://{lang}.wikipedia.org/wiki/{p['title'].replace(' ', '_')}"
    return None


# ----------------------------------------------------------------- renk
def dominant_color(img) -> str:
    """Afişin canlı baskın rengi (çok koyu/çok açık/gri pikseller hariç)."""
    import colorsys

    small = img.convert("RGB").resize((48, 72))
    best, best_score = (120, 90, 200), -1.0
    buckets: dict[tuple, list] = {}
    for r, g, b in small.getdata():
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if l < 0.15 or l > 0.85 or s < 0.25:
            continue
        key = (int(h * 12), int(l * 3))
        buckets.setdefault(key, []).append((r, g, b, s))
    for px in buckets.values():
        score = len(px) * (sum(p[3] for p in px) / len(px))
        if score > best_score:
            best_score = score
            best = tuple(sum(p[i] for p in px) // len(px) for i in range(3))
    return "#%02x%02x%02x" % best

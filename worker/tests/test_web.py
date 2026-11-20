"""Açık web kaynakları: HTML'den metin, kaynakça bağlantı süzgeci, robots.txt, bağımsızlık."""
from fds_worker import http, research, web
from fds_worker import sources as S

HTML = """<html><head><title>Fallback</title>
<meta property="og:title" content="Arda Güler signs new contract">
<meta property="article:published_time" content="2026-11-18T10:00:00Z">
<script>var x = "<p>script paragraph should vanish completely here</p>";</script></head>
<body><nav><p>Menu item that is long enough to be a paragraph but is navigation</p></nav>
<p>Arda Güler has extended his contract with Real Madrid until 2032, the club announced on Tuesday.</p>
<p>We use cookies to improve your experience on this website, please accept them all.</p>
<p>The Turkish midfielder joined from Fenerbahçe in July 2023 and has become a regular starter.</p>
<footer><p>All rights reserved by the publisher of this page and its partners.</p></footer></body></html>"""


def test_extract_keeps_article_paragraphs_only():
    text, title, published = web.extract(HTML)
    assert title == "Arda Güler signs new contract" and published == "2026-11-18"
    assert "2032" in text and "July 2023" in text
    assert "cookies" not in text and "script paragraph" not in text and "Menu item" not in text
    assert "All rights reserved" not in text


def test_skip_and_official_domains():
    assert web.skipped("https://en.wikipedia.org/wiki/X") and web.skipped("https://www.youtube.com/watch?v=1")
    assert web.skipped("https://web.archive.org/web/2020/https://x.com") and web.skipped("https://a.com/b.pdf")
    assert not web.skipped("https://www.bbc.com/sport/football/1")
    assert web.is_official("https://www.realmadrid.com/en/news") and web.is_official("https://www.uefa.com/x")
    assert not web.is_official("https://www.goal.com/x")


def test_wiki_ref_urls_filters_and_puts_official_first(monkeypatch):
    links = ["https://www.goal.com/a", "https://www.goal.com/b", "https://www.goal.com/c",
             "https://twitter.com/x", "https://www.uefa.com/news/1", "https://en.wikipedia.org/wiki/Y"]
    monkeypatch.setattr(http, "get_json", lambda url, params=None, **k: {
        "query": {"pages": {"1": {"extlinks": [{"*": u} for u in links]}}}})
    out = web.wiki_ref_urls("Arda Güler")
    assert out[0] == "https://www.uefa.com/news/1"                       # resmî site önce
    assert sum("goal.com" in u for u in out) == 2                          # alan adı başına en fazla 2
    assert not any("twitter" in u or "wikipedia" in u for u in out)


def test_robots_disallow_is_respected(monkeypatch):
    web._robots.clear()

    class R:
        status_code = 200
        text = "User-agent: *\nDisallow: /private/\n"
    monkeypatch.setattr(http, "request", lambda *a, **k: R())
    assert web.allowed("https://site.example/news/1")
    assert not web.allowed("https://site.example/private/2")


def test_web_sources_are_independent_per_domain():
    a = S.Source("https://bbc.com/1", "Güler", "bbc.com", "news", "web", "Arda Güler " * 50)
    b = S.Source("https://uefa.com/1", "Güler at EURO", "uefa.com", "official", "web", "Arda Güler " * 50)
    w = S.Source("https://en.wikipedia.org/wiki/Arda", "Arda Güler", "Wikipedia", "encyclopedia", "wikipedia", "Arda Güler " * 50)
    keys = {S.independence_key(x) for x in (a, b, w)}
    assert len(keys) == 3
    kept = research.select_sources([w, a, b], ["Arda Güler"])
    assert {k.source_type for k in kept} == {"encyclopedia", "news", "official"}

"""Kibar HTTP istemcisi: tanımlayıcı User-Agent, sunucu başına aralık, 429/5xx'te Retry-After'a uyan yeniden deneme."""
from __future__ import annotations

import os
import time
from urllib.parse import urlparse

import httpx

UA = "FreeDocumentaryStudio/0.3 (open-source documentary research bot" + (
    f"; {os.environ['FDS_CONTACT']})" if os.environ.get("FDS_CONTACT") else ")"
)
MIN_INTERVAL = 1.0      # aynı sunucuya iki istek arasında en az 1 sn
HOST_INTERVAL = {"collectionapi.metmuseum.org": 0.15, "api.gdeltproject.org": 5.0}   # GDELT: 5 sn'de bir istek   # Met API saniyede 80 isteğe izin veriyor
MAX_RETRY_WAIT = 60     # Retry-After bundan uzunsa beklemeyiz (ör. günlük kota bitti)

_last: dict[str, float] = {}
_client: httpx.Client | None = None


class RateLimited(Exception):
    """Sunucu uzun süre beklememizi istedi (günlük kota vb.)."""


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": UA})
    return _client


def _throttle(host: str):
    wait = _last.get(host, 0) + HOST_INTERVAL.get(host, MIN_INTERVAL) - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.monotonic()


def request(method: str, url: str, *, retries: int = 4, **kw) -> httpx.Response:
    host = urlparse(url).netloc
    delay = 2.0
    for attempt in range(retries + 1):
        _throttle(host)
        try:
            r = client().request(method, url, **kw)
        except httpx.TransportError:
            if attempt == retries:
                raise
            time.sleep(delay)
            delay *= 2
            continue
        if r.status_code == 429 or r.status_code >= 500:
            ra = r.headers.get("retry-after")
            wait = float(ra) if ra and ra.isdigit() else delay
            if wait > MAX_RETRY_WAIT:
                raise RateLimited(f"{host}: {r.status_code}, {int(wait)} sn sonra tekrar denenebilir")
            if attempt == retries:
                r.raise_for_status()
            time.sleep(wait)
            delay *= 2
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("unreachable")


def get_json(url: str, **kw):
    return request("GET", url, **kw).json()

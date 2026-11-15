"""Servis bağlantı kontrolü (GitHub Actions → check-services). Yalnızca OK/HATA yazar; gizli değer yazdırmaz.

  python -m fds_worker.check
"""
from __future__ import annotations

import os
import sys
import uuid

import httpx

TEST_ORIGIN = "https://ornek-panel.vercel.app"


def _db():
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as c:
        n = c.execute("select count(*) from projects").fetchone()[0]
    return f"bağlandı ({n} proje)"


def _r2():
    from . import storage
    if not storage.configured():
        missing = [k for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET") if not os.environ.get(k)]
        raise RuntimeError("eksik secret: " + ", ".join(missing))
    acct = os.environ.get("R2_ACCOUNT_ID", "")
    if acct.startswith("http") or "." in acct:
        raise RuntimeError("R2_ACCOUNT_ID yalnızca https:// ile .r2 arasındaki kısım olmalı")
    key = f"healthcheck/{uuid.uuid4().hex}.txt"
    storage.upload_bytes(key, b"ok", "text/plain")
    body = storage.client().get_object(Bucket=storage.bucket(), Key=key)["Body"].read()
    storage.client().delete_object(Bucket=storage.bucket(), Key=key)
    if body != b"ok":
        raise RuntimeError("yazılan ve okunan içerik farklı")
    # Tarayıcının yaptığı gibi CORS ön isteği (OPTIONS): bucket ayarını okuma izni gerektirmez
    url = storage.client().generate_presigned_url(
        "put_object", Params={"Bucket": storage.bucket(), "Key": key, "ContentType": "audio/mpeg"}, ExpiresIn=300)
    pre = httpx.options(url, timeout=30, headers={
        "Origin": TEST_ORIGIN, "Access-Control-Request-Method": "PUT", "Access-Control-Request-Headers": "content-type"})
    allow = pre.headers.get("access-control-allow-origin")
    if allow in ("*", TEST_ORIGIN):
        cors = "ayarlı (tarayıcıdan yükleme çalışır)"
    else:
        cors = f"AYARLI DEĞİL (ön istek yanıtı {pre.status_code}; tarayıcıdan yükleme çalışmaz)"
    return f"yaz/oku/sil çalışıyor; CORS {cors}"


def _gemini():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY yok")
    r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return f"anahtar geçerli ({len(r.json().get('models', []))} model görünüyor; istek kotası harcanmadı)"


def main():
    failed = False
    for name, fn in (("Supabase veritabanı", _db), ("Cloudflare R2", _r2), ("Gemini API", _gemini)):
        try:
            print(f"✓ {name}: {fn()}")
        except Exception as e:  # noqa: BLE001
            failed = True
            msg = str(e).replace(os.environ.get("R2_SECRET_ACCESS_KEY") or "\0", "***")
            print(f"✗ {name}: {type(e).__name__}: {msg[:200]}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

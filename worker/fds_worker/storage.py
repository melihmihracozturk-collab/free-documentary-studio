"""Cloudflare R2 (S3 uyumlu) depolama. Anahtarlar yalnızca ortam değişkenlerinden okunur.

R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
Testlerde R2_ENDPOINT ile yerel bir S3 taklidi (moto) kullanılabilir.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def configured() -> bool:
    return all(os.environ.get(k) for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")) and bool(
        os.environ.get("R2_ACCOUNT_ID") or os.environ.get("R2_ENDPOINT"))


_client = None


def client():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        endpoint = os.environ.get("R2_ENDPOINT") or f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
        _client = boto3.client("s3", endpoint_url=endpoint, region_name=os.environ.get("R2_REGION", "auto"),
                               aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                               aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                               config=Config(retries={"max_attempts": 5, "mode": "standard"}))
    return _client


def bucket() -> str:
    return os.environ["R2_BUCKET"]


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(key: str, dest: str | Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    client().download_file(bucket(), key, str(dest))
    return dest


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    client().put_object(Bucket=bucket(), Key=key, Body=data, ContentType=content_type)
    return hashlib.sha256(data).hexdigest()


def upload_file(key: str, path: str | Path, content_type: str = "application/octet-stream") -> str:
    client().upload_file(str(path), bucket(), key, ExtraArgs={"ContentType": content_type})
    return sha256_file(path)


def project_key(slug: str, *parts: str) -> str:
    return "/".join(["projects", slug, *parts])

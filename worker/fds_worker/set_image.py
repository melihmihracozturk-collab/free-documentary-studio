"""Bir sahneye elle Commons görseli atar (ör. "33. sahneye Talat Paşa portresi").

Kullanım: SLUG=... KIND=doc IDX=33 FILE="File:Talat Pasha.jpg" python -m fds_worker.set_image
Lisans kurallarına uyar (NC/ND/bilinmeyen reddedilir), görseli R2'ye indirir, credits.txt'yi yeniler.
Görsel onayı verilmişse değişiklik yapmaz.
"""
from __future__ import annotations

import os
import sys

from . import images, storage, visuals
from .licenses import allowed
from .main import connect


def assign(conn, slug: str, kind: str, idx: int, file_title: str, force: bool = False) -> str:
    p = conn.execute("select id from projects where slug=%s", (slug,)).fetchone()
    if not p:
        raise SystemExit(f"Proje yok: {slug}")
    st = conn.execute("select s.status from job_steps s join jobs j on j.id=s.job_id where s.project_id=%s "
                      "and s.step_key='visual_review' order by j.created_at desc limit 1", (p["id"],)).fetchone()
    if st and st["status"] == "done" and not force:
        raise SystemExit("Görseller onaylanmış; önce panelden onayı geri alın (veya force ile değiştirip yeniden render edin).")
    sc = conn.execute("select id from scenes where project_id=%s and kind=%s and idx=%s", (p["id"], kind, idx)).fetchone()
    if not sc:
        raise SystemExit(f"Sahne yok: {kind}#{idx}")
    c = images.commons_file(file_title)
    if not c:
        raise SystemExit(f"Commons dosyası bulunamadı: {file_title}")
    s = visuals._settings(conn)
    ok, why = allowed(c.license_class, s.get("license_allow_nc") is True, s.get("license_allow_sa") is not False,
                      s.get("license_allow_restricted") is True)
    if not ok:
        raise SystemExit(f"Lisans uygun değil ({c.license_class}): {why}")
    conn.execute("update assets set status='candidate' where scene_id=%s and status='approved'", (sc["id"],))
    aid = conn.execute(
        "insert into assets (project_id, scene_id, kind, source, title, source_url, file_url, thumb_url, author, license, "
        "license_url, license_class, attribution, width, height, score, query, status, is_ai) "
        "values (%s,%s,'image',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,99,'manual','approved',false) returning id",
        (p["id"], sc["id"], c.source, c.title, c.page_url, c.file_url, c.thumb_url, c.author, c.license_raw,
         c.license_url, c.license_class, c.attribution, c.width, c.height)).fetchone()["id"]
    conn.execute("update scenes set asset_id=%s where id=%s", (aid, sc["id"]))
    if storage.configured():
        visuals.download_selected(conn, p["id"], slug)
        row = conn.execute("select storage_key, reject_reason from assets where id=%s", (aid,)).fetchone()
        if not row["storage_key"]:
            raise SystemExit(f"Görsel indirilemedi: {row['reject_reason']}")
    visuals.write_credits(conn, p["id"], slug)
    return f"{kind}#{idx} ← {c.title} ({c.license_class}, {c.width}x{c.height}) {c.page_url}"


def main() -> None:
    e = lambda k: os.environ.get(k, "").strip()  # noqa: E731
    with connect(e("DATABASE_URL")) as conn:
        for i, f in zip(e("IDX").split(","), e("FILE").split("|")):
            print(assign(conn, e("SLUG"), e("KIND") or "doc", int(i), f.strip(), force=e("FORCE") == "true"), flush=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as ex:
        print(f"Hata: {ex}", file=sys.stderr)
        sys.exit(1)

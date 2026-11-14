"""İşçi döngüsü.

  python -m fds_worker [--max-minutes 300] [--dry-run] [--once]

- Önce kalp atışı kesilmiş adımları yeniden kuyruğa alır (kaldığı yerden devam).
- Sonra desteklediği adımları sırayla alır, çalıştırır, sonucu yazar.
- Uzun adımlar sırasında arka planda kalp atışı gönderir.
- Süre sınırına yaklaşınca yeni adım almaz; yarım iş bir sonraki çalıştırmada sürer.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import traceback
import uuid

import psycopg
from psycopg.rows import dict_row

from .handlers import registry

HEARTBEAT_SEC = 30


def connect(url: str) -> psycopg.Connection:
    # prepare_threshold=None: Supabase havuzlayıcısı (transaction mode) ile uyumlu.
    return psycopg.connect(url, autocommit=True, row_factory=dict_row, prepare_threshold=None)


class Heartbeat(threading.Thread):
    def __init__(self, url: str, step_id, worker_id: str):
        super().__init__(daemon=True)
        self.url, self.step_id, self.worker_id = url, step_id, worker_id
        self.stop_event = threading.Event()

    def run(self):
        with connect(self.url) as conn:
            while not self.stop_event.wait(HEARTBEAT_SEC):
                conn.execute("select heartbeat_step(%s, %s)", (self.step_id, self.worker_id))

    def stop(self):
        self.stop_event.set()


def run(url: str, max_minutes: float, dry_run: bool, once: bool) -> int:
    worker_id = f"{os.environ.get('GITHUB_RUN_ID', socket.gethostname())}-{uuid.uuid4().hex[:6]}"
    handlers = registry(dry_run)
    deadline = time.monotonic() + max_minutes * 60
    processed = 0

    with connect(url) as conn:
        requeued = conn.execute("select requeue_stale_steps() as n").fetchone()["n"]
        print(f"[worker {worker_id}] yeniden kuyruğa alınan: {requeued}; işleyiciler: {sorted(handlers) or 'yok'}")
        if not handlers:
            print("[worker] Kayıtlı işleyici yok (LLM anahtarı tanımlı mı?). Yapılacak iş yok.")
            return 0

        while time.monotonic() < deadline:
            step = conn.execute(
                "select * from claim_next_step(%s, %s)", (worker_id, list(handlers))
            ).fetchone()
            if step is None:
                print("[worker] Kuyrukta uygun adım yok.")
                break

            print(f"[worker] → {step['step_key']} (deneme {step['attempts']}/{step['max_attempts']})")
            hb = Heartbeat(url, step["id"], worker_id)
            hb.start()
            try:
                result = handlers[step["step_key"]](conn, step)
                conn.execute(
                    "select complete_step(%s, %s, %s::jsonb, %s, %s)",
                    (step["id"], worker_id, psycopg.types.json.Jsonb(result.output),
                     result.output_key, result.sha256),
                )
                print(f"[worker] ✓ {step['step_key']}")
            except Exception as exc:  # noqa: BLE001 — her hata kayda geçmeli
                msg = f"{type(exc).__name__}: {exc}"
                new_status = conn.execute(
                    "select fail_step(%s, %s, %s) as s", (step["id"], worker_id, msg[:4000])
                ).fetchone()["s"]
                print(f"[worker] ✗ {step['step_key']} → {new_status}\n{traceback.format_exc()}", file=sys.stderr)
            finally:
                hb.stop()
            processed += 1
            if once:
                break

    print(f"[worker] bitti; işlenen adım: {processed}")
    return processed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=float(os.environ.get("WORKER_MAX_MINUTES", 300)))
    ap.add_argument("--dry-run", action="store_true", help="Yalnızca test: sahte işleyiciler")
    ap.add_argument("--once", action="store_true", help="Tek adım işle ve çık")
    args = ap.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL tanımlı değil")
    run(url, args.max_minutes, args.dry_run, args.once)


if __name__ == "__main__":
    main()

"""Adım işleyicileri.

Her işleyici (conn, step) alır ve StepResult döndürür. Bir adımın işleyicisi
kayıtlı değilse işçi o adımı hiç almaz; adım veritabanında beklemede kalır.
Gerçek işleyiciler ilgili Stage'lerde eklenecek (araştırma: Stage 3, ses: Stage 4, ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class StepResult:
    output: dict[str, Any] = field(default_factory=dict)
    output_key: str | None = None
    sha256: str | None = None


Handler = Callable[[Any, dict], StepResult]

# Stage 2'de üretim için kayıtlı gerçek işleyici yok.
REAL_HANDLERS: dict[str, Handler] = {}


def _dry_run(conn, step: dict) -> StepResult:
    """Yalnızca test: altyapıyı uçtan uca sınamak için sahte çıktı üretir.

    Çıktıya her zaman dry_run=true yazılır; bu çıktılar gerçek içerik sayılmaz.
    """
    if step["step_key"] == "voiceover_analyze":
        # Test: yüklenmiş sesleri "analiz edildi" olarak işaretle (gerçek analiz Stage 4'te).
        with conn.cursor() as cur:
            cur.execute(
                "update voiceovers set status='analyzed', analysis=%s::jsonb "
                "where project_id=%s and status in ('uploaded','analyzing')",
                ('{"dry_run": true}', step["project_id"]),
            )
    return StepResult(output={"dry_run": True, "note": "Test çıktısı — gerçek içerik değil"})


DRY_RUN_KEYS = [
    "research_collect", "research_verify", "research_report", "script_doc", "script_shorts",
    "visual_plan", "voiceover_texts", "voiceover_analyze", "asset_match", "subtitles",
    "render_doc", "render_shorts", "preview_ready",
]


def registry(dry_run: bool) -> dict[str, Handler]:
    if dry_run:
        return {k: _dry_run for k in DRY_RUN_KEYS}
    return dict(REAL_HANDLERS)

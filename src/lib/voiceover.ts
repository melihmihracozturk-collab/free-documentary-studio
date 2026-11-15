import "server-only";
import { z } from "zod";
import { db } from "./db";

export const ALLOWED = {
  "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
} as const;

export const UploadMeta = z.object({
  kind: z.enum(["doc", "shorts"]),
  filename: z.string().min(1).max(200),
  size: z.number().int().positive(),
  type: z.string(),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
});

/** Yükleme ön koşulları: proje var, senaryo onaylı, dosya türü/boyutu uygun, depolama eşiği aşılmıyor. */
export async function checkUpload(slug: string, meta: z.infer<typeof UploadMeta>) {
  const sql = db();
  const [p] = await sql<{ id: string; slug: string }[]>`select id, slug from projects where slug = ${slug}`;
  if (!p) return { error: "Proje bulunamadı", status: 404 } as const;
  const ext = ALLOWED[meta.type as keyof typeof ALLOWED] ?? (/\.(mp3|wav)$/i.exec(meta.filename)?.[1]?.toLowerCase() as "mp3" | "wav" | undefined);
  if (!ext) return { error: "Yalnızca MP3 veya WAV yüklenebilir", status: 400 } as const;
  const [cfg] = await sql<{ max_mb: number; used: string; guard: string; approved: boolean }[]>`
    select (select (value #>> '{}')::int from settings where key = 'voiceover_max_mb') max_mb,
           (select used_bytes from storage_usage) used, (select guard_bytes from storage_usage) guard,
           exists (select 1 from job_steps s join jobs j on j.id = s.job_id where s.project_id = ${p.id}
                    and s.step_key = 'script_review' and s.status = 'done' and j.status <> 'cancelled') approved`;
  if (!cfg.approved) return { error: "Önce senaryoyu onaylayın (Senaryo sayfası)", status: 409 } as const;
  if (meta.size > cfg.max_mb * 1024 * 1024) return { error: `Dosya en fazla ${cfg.max_mb} MB olabilir`, status: 413 } as const;
  if (Number(cfg.used) + meta.size > Number(cfg.guard)) return { error: "Depolama koruma eşiği aşılır; eski dosyaları silin", status: 507 } as const;
  return { project: p, ext } as const;
}

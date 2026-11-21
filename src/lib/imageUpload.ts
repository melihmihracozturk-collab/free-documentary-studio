import "server-only";
import { z } from "zod";
import { db } from "./db";

export const IMAGE_TYPES = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp" } as const;
export const MAX_IMAGE_MB = 25;

export const ImageUploadMeta = z.object({
  sceneId: z.string().uuid(),
  filename: z.string().min(1).max(200),
  size: z.number().int().positive(),
  type: z.string(),
});

/** Sahne bu projeye ait mi, görsel onayı açık mı, dosya türü/boyutu ve depolama eşiği uygun mu. */
export async function checkImageUpload(slug: string, m: z.infer<typeof ImageUploadMeta>) {
  const sql = db();
  const [sc] = await sql<{ project_id: string }[]>`
    select s.project_id from scenes s join projects p on p.id = s.project_id where p.slug = ${slug} and s.id = ${m.sceneId}`;
  if (!sc) return { error: "Sahne bulunamadı", status: 404 } as const;
  const ext = IMAGE_TYPES[m.type as keyof typeof IMAGE_TYPES];
  if (!ext) return { error: "Yalnızca JPG, PNG veya WEBP yüklenebilir", status: 400 } as const;
  if (m.size > MAX_IMAGE_MB * 1024 * 1024) return { error: `Görsel en fazla ${MAX_IMAGE_MB} MB olabilir`, status: 413 } as const;
  const [st] = await sql<{ locked: boolean; over: boolean }[]>`
    select exists (select 1 from job_steps s join jobs j on j.id = s.job_id where s.project_id = ${sc.project_id}
                    and s.step_key = 'visual_review' and s.status = 'done' and j.status <> 'cancelled') locked,
           (select used_bytes + ${m.size} > guard_bytes from storage_usage) over`;
  if (st.locked) return { error: "Görseller onaylanmış; değiştirmek için önce onayı geri alın", status: 409 } as const;
  if (st.over) return { error: "Depolama koruma eşiği aşılır; eski dosyaları silin", status: 507 } as const;
  return { projectId: sc.project_id, ext } as const;
}

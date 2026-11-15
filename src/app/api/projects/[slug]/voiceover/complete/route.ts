import { NextResponse } from "next/server";
import { z } from "zod";
import { db } from "@/lib/db";
import { dispatchWorker } from "@/lib/github";
import { headObject, projectKey, r2Configured } from "@/lib/r2";
import { UploadMeta, checkUpload } from "@/lib/voiceover";

const Body = UploadMeta.extend({ key: z.string() });

// Yükleme bittiğinde: dosyanın R2'de gerçekten olduğunu ve boyutunu doğrular, kaydı oluşturur, işçiyi tetikler.
export async function POST(req: Request, ctx: RouteContext<"/api/projects/[slug]/voiceover/complete">) {
  const { slug } = await ctx.params;
  if (!r2Configured()) return NextResponse.json({ error: "R2 yapılandırılmamış" }, { status: 503 });
  const parsed = Body.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "Geçersiz istek" }, { status: 400 });
  const m = parsed.data;
  const check = await checkUpload(slug, m);
  if ("error" in check) return NextResponse.json({ error: check.error }, { status: check.status });
  if (!m.key.startsWith(projectKey(slug, "voiceover", `${m.kind}-`))) return NextResponse.json({ error: "Geçersiz anahtar" }, { status: 400 });
  const head = await headObject(m.key);
  if (!head) return NextResponse.json({ error: "Dosya R2'de bulunamadı; yükleme tamamlanmamış" }, { status: 409 });
  if (head.size !== m.size) return NextResponse.json({ error: `Boyut uyuşmuyor (${head.size} ≠ ${m.size}); tekrar yükleyin` }, { status: 409 });

  const sql = db();
  const pid = check.project.id;
  await sql.begin(async (tx) => {
    await tx`insert into voiceovers (project_id, kind, storage_key, filename, mime, bytes, sha256, uploaded_at)
             values (${pid}, ${m.kind}, ${m.key}, ${m.filename}, ${head.contentType}, ${m.size}, ${m.sha256}, now())
             on conflict (project_id, kind) do update
               set storage_key = excluded.storage_key, filename = excluded.filename, mime = excluded.mime,
                   bytes = excluded.bytes, sha256 = excluded.sha256, uploaded_at = now()`;
    // Daha önce analiz edildiyse (dosya değişti) analizden itibaren yeniden çalıştır
    const [an] = await tx<{ job_id: string }[]>`
      select s.job_id from job_steps s join jobs j on j.id = s.job_id
       where s.project_id = ${pid} and s.step_key = 'voiceover_analyze' and s.status in ('done', 'failed')
       order by j.created_at desc limit 1`;
    if (an) await tx`select reset_from_step(${an.job_id}, 'voiceover_analyze')`;
  });
  const dispatch = await dispatchWorker(`seslendirme yüklendi: ${slug}/${m.kind}`);
  return NextResponse.json({ ok: true, dispatch });
}

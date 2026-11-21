import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { db } from "@/lib/db";
import { headObject, projectKey, r2Configured } from "@/lib/r2";
import { ImageUploadMeta, checkImageUpload } from "@/lib/imageUpload";

const Body = ImageUploadMeta.extend({ key: z.string(), rights: z.literal(true) });

// Yükleme bitti: dosya R2'de mi, boyutu doğru mu; görsel sahneye atanır. Render öncesi işçi 2560 px JPEG'e çevirir.
export async function POST(req: Request, ctx: RouteContext<"/api/projects/[slug]/images/complete">) {
  const { slug } = await ctx.params;
  if (!r2Configured()) return NextResponse.json({ error: "R2 yapılandırılmamış" }, { status: 503 });
  const parsed = Body.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "Kullanım hakkı onayı ve geçerli dosya bilgisi gerekli" }, { status: 400 });
  const m = parsed.data;
  const check = await checkImageUpload(slug, m);
  if ("error" in check) return NextResponse.json({ error: check.error }, { status: check.status });
  if (!m.key.startsWith(projectKey(slug, "uploads", "")) || m.key.includes("..")) return NextResponse.json({ error: "Geçersiz anahtar" }, { status: 400 });
  const head = await headObject(m.key);
  if (!head) return NextResponse.json({ error: "Dosya R2'de bulunamadı; yükleme tamamlanmamış" }, { status: 409 });
  if (head.size !== m.size) return NextResponse.json({ error: "Boyut uyuşmuyor; tekrar yükleyin" }, { status: 409 });

  const title = m.filename.replace(/\.[^.]+$/, "").slice(0, 300);
  await db().begin(async (tx) => {
    const [a] = await tx<{ id: string }[]>`
      insert into assets (project_id, scene_id, kind, source, title, source_url, file_url, thumb_url, author, license,
                          license_class, attribution, score, query, status, is_ai)
      values (${check.projectId}, ${m.sceneId}, 'image', 'upload', ${title}, null, ${"r2:" + m.key}, null, 'Kullanıcı',
              'Kullanıcı yüklemesi (kullanım hakkı kullanıcı beyanıyla)', 'own', null, 100, 'upload', 'approved', false)
      returning id`;
    await tx`update assets set thumb_url = ${`/api/projects/${slug}/assets/${a.id}/thumb`} where id = ${a.id}`;
    await tx`update assets set status = 'candidate' where scene_id = ${m.sceneId} and status = 'approved' and id <> ${a.id}`;
    await tx`update scenes set asset_id = ${a.id} where id = ${m.sceneId}`;
  });
  revalidatePath("/gorseller");
  return NextResponse.json({ ok: true });
}

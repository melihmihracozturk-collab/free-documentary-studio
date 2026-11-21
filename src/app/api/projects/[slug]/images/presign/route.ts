import { NextResponse } from "next/server";
import { randomUUID } from "node:crypto";
import { presignPut, projectKey, r2Configured } from "@/lib/r2";
import { ImageUploadMeta, checkImageUpload } from "@/lib/imageUpload";

// Kullanıcının kendi görseli: tarayıcı R2'ye imzalı URL ile doğrudan yükler (Vercel gövde sınırına takılmaz).
export async function POST(req: Request, ctx: RouteContext<"/api/projects/[slug]/images/presign">) {
  const { slug } = await ctx.params;
  if (!r2Configured()) return NextResponse.json({ error: "R2 yapılandırılmamış (Ayarlar)" }, { status: 503 });
  const parsed = ImageUploadMeta.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "Geçersiz istek" }, { status: 400 });
  const check = await checkImageUpload(slug, parsed.data);
  if ("error" in check) return NextResponse.json({ error: check.error }, { status: check.status });
  const key = projectKey(slug, "uploads", `${randomUUID()}.${check.ext}`);
  return NextResponse.json({ url: await presignPut(key, parsed.data.type), key, contentType: parsed.data.type });
}

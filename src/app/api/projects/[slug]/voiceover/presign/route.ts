import { NextResponse } from "next/server";
import { presignPut, projectKey, r2Configured } from "@/lib/r2";
import { UploadMeta, checkUpload } from "@/lib/voiceover";

// Tarayıcıya R2'ye doğrudan yükleme için 15 dakikalık imzalı URL verir.
export async function POST(req: Request, ctx: RouteContext<"/api/projects/[slug]/voiceover/presign">) {
  const { slug } = await ctx.params;
  if (!r2Configured()) return NextResponse.json({ error: "R2 yapılandırılmamış (Ayarlar)" }, { status: 503 });
  const parsed = UploadMeta.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "Geçersiz istek" }, { status: 400 });
  const check = await checkUpload(slug, parsed.data);
  if ("error" in check) return NextResponse.json({ error: check.error }, { status: check.status });
  const contentType = check.ext === "mp3" ? "audio/mpeg" : "audio/wav";
  const key = projectKey(slug, "voiceover", `${parsed.data.kind}-${parsed.data.sha256.slice(0, 12)}.${check.ext}`);
  return NextResponse.json({ url: await presignPut(key, contentType), key, contentType });
}

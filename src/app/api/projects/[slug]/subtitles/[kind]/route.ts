import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { presignGet, projectKey, r2Configured, headObject } from "@/lib/r2";

// SRT altyazı dosyası (YouTube'a ayrı altyazı olarak da yüklenebilir).
export async function GET(_req: Request, ctx: RouteContext<"/api/projects/[slug]/subtitles/[kind]">) {
  const { slug, kind } = await ctx.params;
  if (kind !== "doc" && kind !== "shorts") return NextResponse.json({ error: "Geçersiz tür" }, { status: 400 });
  if (!r2Configured()) return NextResponse.json({ error: "R2 yapılandırılmamış" }, { status: 503 });
  const [p] = await db()<{ slug: string }[]>`select slug from projects where slug = ${slug}`;
  if (!p) return NextResponse.json({ error: "Proje yok" }, { status: 404 });
  const key = projectKey(slug, "subtitles", `${kind}.srt`);
  if (!(await headObject(key))) return NextResponse.json({ error: "Altyazı henüz üretilmedi" }, { status: 404 });
  return NextResponse.redirect(await presignGet(key, `${slug}-${kind}.srt`), 302);
}

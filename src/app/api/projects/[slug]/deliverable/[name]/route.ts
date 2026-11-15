import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { headObject, presignGet, projectKey, r2Configured } from "@/lib/r2";

const ALLOWED = new Set(["youtube_description.txt", "shorts_description.txt", "credits.txt"]);

// Teslim dosyaları (YouTube açıklamaları, credits) — yalnızca izin verilen adlar.
export async function GET(_req: Request, ctx: RouteContext<"/api/projects/[slug]/deliverable/[name]">) {
  const { slug, name } = await ctx.params;
  if (!ALLOWED.has(name)) return NextResponse.json({ error: "Geçersiz dosya" }, { status: 400 });
  if (!r2Configured()) return NextResponse.json({ error: "R2 yapılandırılmamış" }, { status: 503 });
  const [p] = await db()<{ slug: string }[]>`select slug from projects where slug = ${slug}`;
  if (!p) return NextResponse.json({ error: "Proje yok" }, { status: 404 });
  const key = projectKey(slug, "renders", name);
  if (!(await headObject(key))) return NextResponse.json({ error: "Henüz hazırlanmadı" }, { status: 404 });
  return NextResponse.redirect(await presignGet(key, `${slug}-${name}`), 302);
}

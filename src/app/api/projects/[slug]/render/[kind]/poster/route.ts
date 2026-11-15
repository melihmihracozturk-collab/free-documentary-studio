import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { presignGet, r2Configured } from "@/lib/r2";

// Render kontrol görseli (videodan eşit aralıklı 9 kare).
export async function GET(_req: Request, ctx: RouteContext<"/api/projects/[slug]/render/[kind]/poster">) {
  const { slug, kind } = await ctx.params;
  if (!r2Configured()) return NextResponse.json({ error: "R2 yapılandırılmamış" }, { status: 503 });
  const [r] = await db()<{ poster_key: string | null }[]>`
    select r.poster_key from renders r join projects p on p.id = r.project_id
     where p.slug = ${slug} and r.kind = ${kind} and r.status = 'done' order by r.created_at desc limit 1`;
  if (!r?.poster_key) return NextResponse.json({ error: "Kontrol görseli yok" }, { status: 404 });
  return NextResponse.redirect(await presignGet(r.poster_key), 302);
}

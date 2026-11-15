import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { presignGet, r2Configured } from "@/lib/r2";

// Yüklenen sesi dinlemek/indirmek için kısa ömürlü imzalı adrese yönlendirir.
export async function GET(_req: Request, ctx: RouteContext<"/api/projects/[slug]/voiceover/[kind]">) {
  const { slug, kind } = await ctx.params;
  if (!r2Configured()) return NextResponse.json({ error: "R2 yapılandırılmamış" }, { status: 503 });
  const [v] = await db()<{ storage_key: string; filename: string }[]>`
    select v.storage_key, v.filename from voiceovers v join projects p on p.id = v.project_id
     where p.slug = ${slug} and v.kind = ${kind}`;
  if (!v) return NextResponse.json({ error: "Ses yok" }, { status: 404 });
  return NextResponse.redirect(await presignGet(v.storage_key), 302);
}

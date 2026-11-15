import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { presignGet, r2Configured } from "@/lib/r2";

// Render edilmiş videoyu izlemek (?download=1 ile indirmek) için kısa ömürlü imzalı adrese yönlendirir.
export async function GET(req: Request, ctx: RouteContext<"/api/projects/[slug]/render/[kind]">) {
  const { slug, kind } = await ctx.params;
  if (kind !== "doc" && kind !== "shorts") return NextResponse.json({ error: "Geçersiz tür" }, { status: 400 });
  if (!r2Configured()) return NextResponse.json({ error: "R2 yapılandırılmamış" }, { status: 503 });
  const [r] = await db()<{ storage_key: string }[]>`
    select r.storage_key from renders r join projects p on p.id = r.project_id
     where p.slug = ${slug} and r.kind = ${kind} and r.status = 'done' order by r.created_at desc limit 1`;
  if (!r) return NextResponse.json({ error: "Render yok" }, { status: 404 });
  const download = new URL(req.url).searchParams.has("download");
  const name = `${slug}-${kind === "doc" ? "belgesel" : "shorts"}.mp4`;
  return NextResponse.redirect(await presignGet(r.storage_key, download ? name : undefined), 302);
}

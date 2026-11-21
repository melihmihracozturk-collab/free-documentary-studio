import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { presignGet } from "@/lib/r2";

// Kullanıcı yüklemesinin önizlemesi: R2'deki dosyaya kısa ömürlü imzalı adrese yönlendirir.
export async function GET(_req: Request, ctx: RouteContext<"/api/projects/[slug]/assets/[id]/thumb">) {
  const { slug, id } = await ctx.params;
  const [a] = await db()<{ storage_key: string | null; file_url: string | null }[]>`
    select a.storage_key, a.file_url from assets a join projects p on p.id = a.project_id
     where p.slug = ${slug} and a.id = ${id} and a.source = 'upload'`;
  const key = a?.storage_key ?? (a?.file_url?.startsWith("r2:") ? a.file_url.slice(3) : null);
  if (!key) return NextResponse.json({ error: "Bulunamadı" }, { status: 404 });
  return NextResponse.redirect(await presignGet(key, undefined, 600));
}

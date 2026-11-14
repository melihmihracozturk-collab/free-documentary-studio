import { NextResponse } from "next/server";
import { getProjectStatus } from "@/lib/queries";

export async function GET(_req: Request, ctx: RouteContext<"/api/projects/[slug]/status">) {
  const { slug } = await ctx.params;
  const data = await getProjectStatus(slug);
  if (!data) return NextResponse.json({ error: "Proje bulunamadı" }, { status: 404 });
  return NextResponse.json(data, { headers: { "Cache-Control": "no-store" } });
}

import { getProject, getResearch } from "@/lib/queries";

export async function GET(_req: Request, ctx: RouteContext<"/api/projects/[slug]/research">) {
  const { slug } = await ctx.params;
  const p = await getProject(slug);
  if (!p) return new Response("Proje bulunamadı", { status: 404 });
  const { report } = await getResearch(p.id);
  if (!report) return new Response("Rapor yok", { status: 404 });
  return new Response(report.markdown, {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Content-Disposition": `attachment; filename="${slug}-research-v${report.version}.md"`,
    },
  });
}

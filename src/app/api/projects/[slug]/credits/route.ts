import { db } from "@/lib/db";

// credits.txt: kullanılan her görselin başlığı, sahibi, lisansı ve kaynağı (video açıklamasına eklenir).
export async function GET(_req: Request, ctx: RouteContext<"/api/projects/[slug]/credits">) {
  const { slug } = await ctx.params;
  const rows = await db()<{ kind: string; idx: number; title: string; author: string | null; license: string | null;
    license_class: string | null; license_url: string | null; source_url: string | null }[]>`
    select s.kind, s.idx, a.title, a.author, a.license, a.license_class, a.license_url, a.source_url
      from scenes s join projects p on p.id = s.project_id join assets a on a.id = s.asset_id
     where p.slug = ${slug} order by s.kind, s.idx`;
  if (!rows.length) return new Response("Seçilmiş görsel yok", { status: 404 });
  const attr = new Set(["by", "by-sa", "nc"]);
  const lines = ["GÖRSEL KAYNAKLARI VE LİSANSLAR", ""];
  for (const r of rows) {
    lines.push(`[${r.kind === "doc" ? "Belgesel" : "Shorts"} sahne ${r.idx}] ${r.title}`);
    lines.push(`  Yapan: ${r.author ?? "bilinmiyor"} · Lisans: ${r.license ?? r.license_class}${r.license_url ? ` (${r.license_url})` : ""}${attr.has(r.license_class ?? "") ? " · ATIF ZORUNLU" : ""}`);
    lines.push(`  Kaynak: ${r.source_url ?? ""}`);
  }
  return new Response(lines.join("\n") + "\n", {
    headers: { "Content-Type": "text/plain; charset=utf-8", "Content-Disposition": `attachment; filename="${slug}-credits.txt"` },
  });
}

import { getProject, getScripts } from "@/lib/queries";

export async function GET(_req: Request, ctx: RouteContext<"/api/projects/[slug]/script/[kind]">) {
  const { slug, kind } = await ctx.params;
  if (kind !== "doc" && kind !== "shorts") return new Response("Geçersiz tür", { status: 400 });
  const p = await getProject(slug);
  if (!p) return new Response("Proje bulunamadı", { status: 404 });
  const data = await getScripts(p.id);
  const script = kind === "doc" ? data.doc : data.shorts;
  const scenes = kind === "doc" ? data.docScenes : data.shortsScenes;
  if (!script) return new Response("Senaryo yok", { status: 404 });
  const lines = [`# ${script.content.title ?? p.title} (${kind === "doc" ? "Belgesel" : "Shorts"}, sürüm ${script.version})`, ""];
  if (script.content.logline) lines.push(`_${script.content.logline}_`, "");
  for (const s of scenes) {
    lines.push(
      `## Sahne ${s.idx}${s.act && s.act !== "shorts" ? ` · ${s.act}` : ""} · ~${Number(s.est_duration_sec).toFixed(0)} sn`,
      "", s.voiceover_text, "",
      `- **Görsel:** ${s.visual_description ?? ""}`,
      `- **Kamera:** ${s.camera_move ?? ""} · **Geçiş:** ${s.transition ?? ""}`,
      `- **Müzik:** ${s.music ?? ""} · **Efekt:** ${s.sfx ?? ""}`,
      ...(s.on_screen_text ? [`- **Ekran yazısı:** ${s.on_screen_text}`] : []),
      `- **İddialar:** ${s.claim_refs.join(", ") || "—"}`, "",
    );
  }
  return new Response(lines.join("\n"), {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Content-Disposition": `attachment; filename="${slug}-${kind}-script-v${script.version}.md"`,
    },
  });
}

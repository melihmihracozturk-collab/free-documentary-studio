import { db } from "@/lib/db";

const FILES = { doc: "documentary_voiceover.txt", shorts: "shorts_voiceover.txt" } as const;

// ElevenLabs metni: onaylı senaryodaki sahneler, aralarında boş satır. Yalnızca okunacak cümleler.
export async function GET(_req: Request, ctx: RouteContext<"/api/projects/[slug]/voiceover-text/[kind]">) {
  const { slug, kind } = await ctx.params;
  if (kind !== "doc" && kind !== "shorts") return new Response("Geçersiz tür", { status: 400 });
  const sql = db();
  const [s] = await sql<{ id: string; approved_at: Date | null; project_id: string }[]>`
    select sc.id, sc.approved_at, sc.project_id from scripts sc join projects p on p.id = sc.project_id
     where p.slug = ${slug} and sc.kind = ${kind} order by sc.version desc limit 1`;
  if (!s) return new Response("Senaryo yok", { status: 404 });
  if (!s.approved_at) return new Response("Senaryo henüz onaylanmadı", { status: 409 });
  const scenes = await sql<{ voiceover_text: string }[]>`
    select voiceover_text from scenes where project_id = ${s.project_id} and kind = ${kind} order by idx`;
  const text = scenes.map((x) => x.voiceover_text.replace(/\s+/g, " ").trim()).join("\n\n") + "\n";
  return new Response(text, {
    headers: { "Content-Type": "text/plain; charset=utf-8", "Content-Disposition": `attachment; filename="${FILES[kind]}"` },
  });
}

import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { searchCommons, searchOpenverse, type Candidate } from "@/lib/imageSearch";
import { allowed } from "@/lib/licenses";

// Panelden anlık görsel araması: Commons + Openverse; lisans politikasına uymayanlar elenir.
export async function GET(req: Request, ctx: RouteContext<"/api/projects/[slug]/images/search">) {
  await ctx.params;
  const q = new URL(req.url).searchParams.get("q")?.trim() ?? "";
  if (q.length < 2 || q.length > 120) return NextResponse.json({ error: "Arama 2-120 karakter olmalı" }, { status: 400 });
  const rows = await db()<{ key: string; value: unknown }[]>`select key, value from settings where key in ('license_allow_nc','license_allow_sa','license_allow_restricted')`;
  const s = Object.fromEntries(rows.map((r) => [r.key, r.value]));
  const allowNc = s.license_allow_nc === true, allowSa = s.license_allow_sa !== false;
  const draft = s.license_allow_restricted === true;
  const [c, o] = await Promise.allSettled([searchCommons(q), searchOpenverse(q, 12, draft)]);
  const all: Candidate[] = [...(c.status === "fulfilled" ? c.value : []), ...(o.status === "fulfilled" ? o.value : [])];
  const results = all.filter((x) => allowed(x.license_class, allowNc, allowSa, draft));
  const errors = ([["Wikimedia Commons", c], ["Openverse", o]] as const)
    .filter(([, x]) => x.status === "rejected")
    .map(([name, x]) => `${name} (${String((x as PromiseRejectedResult).reason).replace(/^Error: /, "").replace(/^[\w.]+: /, "").slice(0, 40)})`);
  return NextResponse.json({ results, rejected: all.length - results.length, errors });
}

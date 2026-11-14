import { NextResponse } from "next/server";
import { dbHealthy } from "@/lib/queries";
import { env } from "@/lib/env";

export async function GET() {
  const db = env.databaseUrl ? await dbHealthy() : false;
  return NextResponse.json({ ok: db, db }, { status: db ? 200 : 503, headers: { "Cache-Control": "no-store" } });
}

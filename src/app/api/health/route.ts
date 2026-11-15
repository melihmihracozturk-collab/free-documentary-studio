import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { env } from "@/lib/env";

// Herkese açık sağlık kontrolü. Bağlantı adresi veya şifre ASLA yazdırılmaz; yalnızca hata türü bildirilir.
function urlProblem(u: string): string | null {
  if (!u) return "DATABASE_URL tanımlı değil (Vercel → Settings → Environment Variables)";
  if (u.includes("[") || u.includes("]")) return "DATABASE_URL içinde köşeli parantez var ([YOUR-PASSWORD] değiştirilmemiş)";
  if (!/^postgres(ql)?:\/\//.test(u)) return "DATABASE_URL 'postgresql://' ile başlamıyor";
  try {
    const p = new URL(u);
    if (!p.hostname.includes(".") && p.hostname !== "localhost") return "DATABASE_URL sunucu adı geçersiz";
    if (p.hostname.includes("supabase") && p.port !== "6543") return "Supabase 'Transaction pooler' adresi (port 6543) kullanılmalı";
  } catch {
    return "DATABASE_URL çözümlenemedi (şifrede # / ? % @ gibi özel karakter olabilir)";
  }
  return null;
}

const HINTS: Record<string, string> = {
  "28P01": "şifre yanlış",
  "28000": "kullanıcı adı/şifre reddedildi",
  ENOTFOUND: "sunucu adı bulunamadı",
  ECONNREFUSED: "bağlantı reddedildi",
  CONNECT_TIMEOUT: "bağlantı zaman aşımı (Supabase projesi duraklatılmış olabilir)",
  XX000: "Supabase havuzlayıcı hatası (kullanıcı adı 'postgres.<proje-kimliği>' biçiminde olmalı)",
};

export async function GET() {
  const problem = urlProblem(env.databaseUrl);
  if (problem) return NextResponse.json({ ok: false, db: false, reason: problem }, { status: 503, headers: { "Cache-Control": "no-store" } });
  try {
    await db()`select 1`;
    return NextResponse.json({ ok: true, db: true }, { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    const code = String((e as { code?: string }).code ?? "");
    return NextResponse.json({ ok: false, db: false, reason: `bağlantı hatası ${code}: ${HINTS[code] ?? "bilinmeyen"}` },
      { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}

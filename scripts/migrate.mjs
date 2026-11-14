// Veritabanı migration'larını sırayla uygular. Kullanım: DATABASE_URL=... node scripts/migrate.mjs
// Yerel kurulum gerekmez: GitHub Actions'taki "migrate" iş akışı bunu bulutta çalıştırır.
import fs from "node:fs";
import path from "node:path";
import postgres from "postgres";

const url = process.env.DATABASE_URL;
if (!url) {
  console.error("DATABASE_URL tanımlı değil");
  process.exit(1);
}
// Bağlantı adresini doğrula. Hata mesajlarında adres veya şifre ASLA yazdırılmaz (Actions günlükleri herkese açık).
function checkUrl(u) {
  let parsed;
  try {
    parsed = new URL(u);
  } catch {
    return "DATABASE_URL geçerli bir adres değil. Şifredeki özel karakterler (@ # / ? % : [ ]) adresi bozar; köşeli parantezleri silin veya yalnızca harf/rakamdan oluşan yeni bir şifre belirleyin.";
  }
  if (!/^postgres(ql)?:$/.test(parsed.protocol)) return "DATABASE_URL 'postgresql://' ile başlamalı.";
  if (u.includes("[") || u.includes("]")) return "DATABASE_URL içinde köşeli parantez var: [YOUR-PASSWORD] kısmı şifreyle değiştirilmemiş olabilir.";
  if (parsed.hostname !== "localhost" && !parsed.hostname.includes(".")) return "DATABASE_URL içindeki sunucu adı geçersiz görünüyor (şifrede özel karakter olabilir).";
  return null;
}
const problem = checkUrl(url);
if (problem) {
  console.error(problem);
  process.exit(1);
}
const sql = postgres(url, { prepare: false, max: 1, onnotice: () => {} });
const dir = path.join(path.dirname(new URL(import.meta.url).pathname), "..", "supabase", "migrations");

try {
  await sql`create table if not exists schema_migrations (name text primary key, applied_at timestamptz not null default now())`;
  await sql`alter table schema_migrations enable row level security`;
  const applied = new Set((await sql`select name from schema_migrations`).map((r) => r.name));
  const files = fs.readdirSync(dir).filter((f) => f.endsWith(".sql")).sort();
  for (const f of files) {
    if (applied.has(f)) {
      console.log(`= ${f} (zaten uygulandı)`);
      continue;
    }
    const body = fs.readFileSync(path.join(dir, f), "utf8");
    await sql.begin(async (tx) => {
      await tx.unsafe(body);
      await tx`insert into schema_migrations (name) values (${f})`;
    });
    console.log(`+ ${f}`);
  }
} catch (e) {
  // Sürücü hataları bağlantı bilgisini içerebilir: yalnızca güvenli alanları yazdır.
  console.error(`Migration hatası: ${e.code ?? ""} ${String(e.message ?? e).replaceAll(url, "***").replace(/postgres(ql)?:\/\/\S+/g, "***").slice(0, 300)}`);
  process.exitCode = 1;
} finally {
  await sql.end({ timeout: 5 });
}

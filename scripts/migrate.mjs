// Veritabanı migration'larını sırayla uygular. Kullanım: DATABASE_URL=... node scripts/migrate.mjs
// Yerel kurulum gerekmez: GitHub Actions'taki "migrate" iş akışı bunu bulutta çalıştırır.
import fs from "node:fs";
import path from "node:path";
import postgres from "postgres";

if (process.env.DATABASE_URL) process.env.DATABASE_URL = process.env.DATABASE_URL.trim();

const url = process.env.DATABASE_URL;
if (!url) {
  console.error("DATABASE_URL tanımlı değil");
  process.exit(1);
}
// Bağlantı adresini doğrula. Hata mesajlarında adres veya şifre ASLA yazdırılmaz (Actions günlükleri herkese açık).
function checkUrl(u) {
  // Yalnızca yapı bilgisi raporlanır; adresin kendisi veya şifre yazdırılmaz.
  const hints = [];
  if (/^\s|\s$/.test(u)) hints.push("başında/sonunda boşluk veya satır sonu var");
  if (/\s/.test(u.trim())) hints.push("içinde boşluk var");
  if (/["'`]/.test(u)) hints.push("tırnak işareti var (tırnaksız yapıştırın)");
  if (/^DATABASE_URL\s*=/i.test(u.trim())) hints.push("başında 'DATABASE_URL=' var (yalnızca adresi yapıştırın)");
  else if (!/^postgres(ql)?:\/\//.test(u.trim())) hints.push("'postgresql://' ile başlamıyor");
  if (u.includes("[") || u.includes("]")) hints.push("köşeli parantez var ([YOUR-PASSWORD] yerine şifre yazılmalı, parantezler silinmeli)");
  const at = (u.match(/@/g) || []).length;
  if (at !== 1) hints.push(`'@' işareti ${at} kez geçiyor (1 olmalı; şifrede @ olmamalı)`);
  const afterScheme = u.trim().replace(/^postgres(ql)?:\/\//, "");
  const userinfo = afterScheme.split("@")[0] ?? "";
  if (/[#/?%]/.test(userinfo)) hints.push("şifrede # / ? % gibi özel karakter var");
  if (u.includes("supabase") && !/:6543\/postgres/.test(u)) hints.push("':6543/postgres' ile bitmiyor (Transaction pooler adresi olmalı)");
  let parsed = null;
  try {
    parsed = new URL(u.trim());
  } catch {
    /* aşağıda raporlanır */
  }
  if (!parsed || hints.length) {
    return `DATABASE_URL hatalı (uzunluk ${u.length} karakter). Sorunlar: ${hints.join("; ") || "adres çözümlenemedi"}.`;
  }
  if (parsed.hostname !== "localhost" && !parsed.hostname.includes(".")) return "DATABASE_URL içindeki sunucu adı geçersiz.";
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

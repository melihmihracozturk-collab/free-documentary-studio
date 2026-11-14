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
} finally {
  await sql.end();
}

// Bir projenin üretim hattını belirtilen adımdan itibaren yeniden başlatır.
// Kullanım: DATABASE_URL=... SLUG=... FROM_STEP=research_collect node scripts/rerun.mjs
import postgres from "postgres";

if (process.env.DATABASE_URL) process.env.DATABASE_URL = process.env.DATABASE_URL.trim();

const { DATABASE_URL, SLUG, FROM_STEP } = process.env;
const sql = postgres(DATABASE_URL, { prepare: false, max: 1, onnotice: () => {} });
try {
  const [j] = await sql`select j.id from jobs j join projects p on p.id = j.project_id
                        where p.slug = ${SLUG} order by j.created_at desc limit 1`;
  if (!j) throw new Error(`Proje veya iş bulunamadı: ${SLUG}`);
  const [r] = await sql`select reset_from_step(${j.id}, ${FROM_STEP}) as n`;
  console.log(`${SLUG}: ${FROM_STEP} ve sonrası yeniden kuyrukta (${r.n} adım).`);
} catch (e) {
  console.error(`Hata: ${String(e.message ?? e).replace(/postgres(ql)?:\/\/\S+/g, "***").slice(0, 300)}`);
  process.exitCode = 1;
} finally {
  await sql.end({ timeout: 5 });
}

// Panel olmadan proje oluşturur (GitHub Actions → "create-project" iş akışı).
// Kullanım: DATABASE_URL=... TOPIC="..." MINUTES=11 LANGUAGE=tr STYLE="..." node scripts/create-project.mjs
import postgres from "postgres";

if (process.env.DATABASE_URL) process.env.DATABASE_URL = process.env.DATABASE_URL.trim();

const TR = { ç: "c", ğ: "g", ı: "i", İ: "i", ö: "o", ş: "s", ü: "u", â: "a", î: "i", û: "u" };
function slugify(input, max = 48) {
  const s = [...input].map((c) => TR[c] ?? TR[c.toLowerCase()] ?? c).join("")
    .normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/['’`]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return s.slice(0, max).replace(/-+$/g, "") || "belgesel";
}

const { DATABASE_URL, TOPIC, MINUTES = "11", LANGUAGE = "tr", STYLE = "Sinematik kısa belgesel" } = process.env;
if (!DATABASE_URL || !TOPIC) {
  console.error("DATABASE_URL ve TOPIC gerekli");
  process.exit(1);
}
const minutes = Number(MINUTES);
if (!(minutes >= 8 && minutes <= 15)) {
  console.error("Süre 8-15 dakika olmalı");
  process.exit(1);
}
const sql = postgres(DATABASE_URL, { prepare: false, max: 1, onnotice: () => {} });
try {
  const base = slugify(TOPIC.split(/[—–:-]/)[0] || TOPIC);
  let slug = base;
  for (let i = 2; (await sql`select 1 from projects where slug = ${slug}`).length; i++) slug = `${base}-${i}`;
  await sql.begin(async (tx) => {
    const [p] = await tx`insert into projects (slug, title, topic, language, target_minutes, style)
                         values (${slug}, ${TOPIC}, ${TOPIC}, ${LANGUAGE}, ${minutes}, ${STYLE}) returning id`;
    await tx`select create_pipeline_job(${p.id})`;
  });
  console.log(`Proje oluşturuldu: ${slug}`);
} catch (e) {
  console.error(`Hata: ${e.code ?? ""} ${String(e.message ?? e).replace(/postgres(ql)?:\/\/\S+/g, "***").slice(0, 300)}`);
  process.exitCode = 1;
} finally {
  await sql.end({ timeout: 5 });
}

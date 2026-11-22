// Panel olmadan bir üretim ayarını değiştirir (yalnızca izinli anahtarlar).
// Kullanım: DATABASE_URL=... KEY=license_allow_restricted VALUE=true node scripts/set-setting.mjs
import postgres from "postgres";

const ALLOWED = { license_allow_nc: "bool", license_allow_sa: "bool", license_allow_restricted: "bool", default_minutes: "int" };
const { KEY, VALUE } = process.env;
const url = (process.env.DATABASE_URL ?? "").trim();
if (!ALLOWED[KEY]) {
  console.error(`İzinli anahtarlar: ${Object.keys(ALLOWED).join(", ")}`);
  process.exit(1);
}
const value = ALLOWED[KEY] === "bool" ? VALUE === "true" : Number(VALUE);
if (ALLOWED[KEY] === "int" && !(value >= 8 && value <= 15)) {
  console.error("Geçersiz değer");
  process.exit(1);
}
const sql = postgres(url, { prepare: false, max: 1, onnotice: () => {} });
try {
  await sql`insert into settings (key, value) values (${KEY}, ${sql.json(value)})
            on conflict (key) do update set value = excluded.value`;
  console.log(`${KEY} = ${JSON.stringify(value)}`);
} catch (e) {
  console.error(`Hata: ${String(e.message ?? e).replace(/postgres(ql)?:\/\/\S+/g, "***").slice(0, 200)}`);
  process.exitCode = 1;
} finally {
  await sql.end({ timeout: 5 });
}

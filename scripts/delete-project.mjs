// Bir projeyi KALICI olarak siler: veritabanı kayıtları (iş, adımlar, kaynaklar, senaryolar, sesler, görseller…)
// ve R2'deki projects/<slug>/ altındaki tüm dosyalar. Geri alınamaz.
// Kullanım: DATABASE_URL=... SLUG=... CONFIRM=<slug> [R2_*] node scripts/delete-project.mjs
import postgres from "postgres";
import { S3Client, ListObjectsV2Command, DeleteObjectsCommand } from "@aws-sdk/client-s3";

const e = (k) => (process.env[k] ?? "").trim();
const SLUG = e("SLUG");
const clean = (m) => String(m ?? "").replace(/postgres(ql)?:\/\/\S+/g, "***").slice(0, 300);

async function deleteR2(prefix) {
  if (!(e("R2_ACCESS_KEY_ID") && e("R2_SECRET_ACCESS_KEY") && e("R2_BUCKET") && e("R2_ACCOUNT_ID"))) {
    console.log("R2 bilgileri yok; dosyalar silinmedi.");
    return 0;
  }
  const s3 = new S3Client({
    region: "auto", endpoint: `https://${e("R2_ACCOUNT_ID")}.r2.cloudflarestorage.com`,
    credentials: { accessKeyId: e("R2_ACCESS_KEY_ID"), secretAccessKey: e("R2_SECRET_ACCESS_KEY") },
  });
  let n = 0, token;
  do {
    const r = await s3.send(new ListObjectsV2Command({ Bucket: e("R2_BUCKET"), Prefix: prefix, ContinuationToken: token }));
    const keys = (r.Contents ?? []).map((o) => ({ Key: o.Key }));
    if (keys.length) {
      await s3.send(new DeleteObjectsCommand({ Bucket: e("R2_BUCKET"), Delete: { Objects: keys, Quiet: true } }));
      n += keys.length;
    }
    token = r.IsTruncated ? r.NextContinuationToken : undefined;
  } while (token);
  return n;
}

if (!/^[a-z0-9-]+$/.test(SLUG)) {
  console.error("Geçersiz kısa ad.");
  process.exit(1);
}
if (e("CONFIRM") !== SLUG) {
  console.error("Onay metni kısa adla aynı değil; hiçbir şey silinmedi.");
  process.exit(1);
}
const sql = postgres(e("DATABASE_URL"), { prepare: false, max: 1, onnotice: () => {} });
try {
  const [p] = await sql`select id, title from projects where slug = ${SLUG}`;
  if (!p) throw new Error(`Proje bulunamadı: ${SLUG}`);
  const files = await deleteR2(`projects/${SLUG}/`);
  await sql`delete from projects where id = ${p.id}`;   // bağlı tüm tablolar "on delete cascade"
  console.log(`Silindi: "${p.title}" (${SLUG}) — veritabanı kayıtları ve ${files} R2 dosyası.`);
} catch (err) {
  console.error(`Hata: ${clean(err.message ?? err)}`);
  process.exitCode = 1;
} finally {
  await sql.end({ timeout: 5 });
}

// Kullanıcı onayı gerektiren adımı onaylar (panel yayında değilken). Kullanım: SLUG=... STEP=research_review
import postgres from "postgres";

if (process.env.DATABASE_URL) process.env.DATABASE_URL = process.env.DATABASE_URL.trim();

const { DATABASE_URL, SLUG, STEP = "research_review" } = process.env;
const sql = postgres(DATABASE_URL, { prepare: false, max: 1, onnotice: () => {} });
try {
  const [s] = await sql`select s.id from job_steps s join jobs j on j.id = s.job_id join projects p on p.id = s.project_id
                        where p.slug = ${SLUG} and s.step_key = ${STEP} and s.status = 'waiting_input'
                        order by j.created_at desc limit 1`;
  if (!s) throw new Error(`${SLUG}: onay bekleyen '${STEP}' adımı yok`);
  if (STEP === "visual_review") {
    // Paneldeki kural: her sahnede görsel olmalı (Ayla'nın sunucu sahneleri hariç)
    const [m] = await sql`select count(*)::int n from scenes sc join projects p on p.id = sc.project_id
                          where p.slug = ${SLUG} and sc.asset_id is null and coalesce(sc.layout, '') <> 'host'`;
    if (m.n > 0) throw new Error(`${SLUG}: ${m.n} sahnede görsel yok; önce panelden görsel seçin`);
  }
  if (STEP === "script_review") {
    // Paneldeki gibi: en son senaryo sürümleri onaylı işaretlenir (seslendirme onaylı metinden üretilir)
    await sql`update scripts s set approved_at = now() from projects p
               where p.id = s.project_id and p.slug = ${SLUG}
                 and s.version = (select max(version) from scripts x where x.project_id = s.project_id and x.kind = s.kind)`;
  }
  const [r] = await sql`select resolve_input_step(${s.id}, ${sql.json({ approved_by: "user", via: "github-actions", at: new Date().toISOString() })}) ok`;
  console.log(r.ok ? `${SLUG}: ${STEP} onaylandı.` : "Onaylanamadı");
  if (!r.ok) process.exitCode = 1;
} catch (e) {
  console.error(`Hata: ${String(e.message ?? e).replace(/postgres(ql)?:\/\/\S+/g, "***").slice(0, 300)}`);
  process.exitCode = 1;
} finally {
  await sql.end({ timeout: 5 });
}

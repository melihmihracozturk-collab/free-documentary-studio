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
  const [r] = await sql`select resolve_input_step(${s.id}, ${sql.json({ approved_by: "user", via: "github-actions", at: new Date().toISOString() })}) ok`;
  console.log(r.ok ? `${SLUG}: ${STEP} onaylandı.` : "Onaylanamadı");
  if (!r.ok) process.exitCode = 1;
} catch (e) {
  console.error(`Hata: ${String(e.message ?? e).replace(/postgres(ql)?:\/\/\S+/g, "***").slice(0, 300)}`);
  process.exitCode = 1;
} finally {
  await sql.end({ timeout: 5 });
}

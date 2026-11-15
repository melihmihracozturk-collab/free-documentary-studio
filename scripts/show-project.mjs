// Proje durumunu ve araştırma raporunu yazdırır (GitHub Actions → "show-project").
// Çıktı herkese açık günlüğe gider: yalnızca belgesel içeriği yazılır, bağlantı bilgisi yazılmaz.
import fs from "node:fs";
import postgres from "postgres";

if (process.env.DATABASE_URL) process.env.DATABASE_URL = process.env.DATABASE_URL.trim();

const { DATABASE_URL, SLUG, GITHUB_STEP_SUMMARY } = process.env;
const sql = postgres(DATABASE_URL, { prepare: false, max: 1, onnotice: () => {} });
const out = [];
try {
  const [p] = await sql`select * from projects where slug = ${SLUG}`;
  if (!p) throw new Error(`Proje yok: ${SLUG}`);
  out.push(`# ${p.title}`, "", `Durum: **${p.status}**`, "", "## Üretim hattı", "", "| # | Adım | Durum | Deneme | Çıktı / hata |", "|---|---|---|---|---|");
  const steps = await sql`select s.seq, d.label, s.status, s.attempts, s.output, s.error from job_steps s
    join step_definitions d using (step_key) join jobs j on j.id = s.job_id
    where s.project_id = ${p.id} and j.id = (select id from jobs where project_id = ${p.id} order by created_at desc limit 1) order by s.seq`;
  for (const s of steps) {
    const o = s.error ?? (s.output ? JSON.stringify(s.output).replace(/\|/g, "/").slice(0, 300) : "");
    out.push(`| ${s.seq / 10} | ${s.label} | ${s.status} | ${s.attempts} | ${o} |`);
  }
  const errs = await sql`select level, step_key, message from error_logs where project_id = ${p.id} order by created_at desc limit 15`;
  if (errs.length) out.push("", "## Uyarılar / hatalar", "", ...errs.map((e) => `- ${e.level} · ${e.step_key ?? ""}: ${e.message}`));
  const usage = await sql`select metric, sum(value)::int n from usage_metrics where period = current_date group by metric order by metric`;
  if (usage.length) out.push("", "## Bugünkü LLM kullanımı", "", ...usage.map((u) => `- ${u.metric}: ${u.n}`));
  const [r] = await sql`select markdown from research_reports where project_id = ${p.id} order by version desc limit 1`;
  if (r) out.push("", "---", "", r.markdown);
  for (const kind of ["doc", "shorts"]) {
    const [sc] = await sql`select version, word_count, est_seconds, content->>'title' title, validation from scripts
                           where project_id = ${p.id} and kind = ${kind} order by version desc limit 1`;
    if (!sc) continue;
    out.push("", "---", "", `# Senaryo (${kind}) · ${sc.title} · sürüm ${sc.version} · ${sc.word_count} kelime · ~${Math.round(sc.est_seconds)} sn`, "");
    if (sc.validation?.errors?.length) out.push("Kontrol uyarıları: " + sc.validation.errors.join("; "), "");
    const scenes = await sql`select idx, act, voiceover_text, visual_description, camera_move, transition, claim_refs
                             from scenes where project_id = ${p.id} and kind = ${kind} order by idx`;
    for (const s of scenes) out.push(`**${s.idx}. ${s.act ?? ""}** — ${s.voiceover_text}`, `> Görsel: ${s.visual_description} · ${s.camera_move}/${s.transition} · ${s.claim_refs.join(" ")}`, "");
  }
} catch (e) {
  out.push(`Hata: ${e.code ?? ""} ${String(e.message ?? e).replace(/postgres(ql)?:\/\/\S+/g, "***").slice(0, 300)}`);
  process.exitCode = 1;
} finally {
  await sql.end({ timeout: 5 });
}
const text = out.join("\n") + "\n";
console.log(text);
if (GITHUB_STEP_SUMMARY) fs.appendFileSync(GITHUB_STEP_SUMMARY, text);

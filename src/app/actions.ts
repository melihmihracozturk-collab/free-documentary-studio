"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { db } from "@/lib/db";
import { SESSION_COOKIE, checkPassword, createSessionToken } from "@/lib/auth";
import { dispatchWorker } from "@/lib/github";
import { slugify } from "@/lib/slug";

export type FormState = { error?: string; ok?: string } | undefined;

const NewProject = z.object({
  topic: z.string().trim().min(3, "Konu en az 3 karakter olmalı").max(200),
  language: z.enum(["tr", "en"]),
  target_minutes: z.coerce.number().min(8, "En az 8 dakika").max(15, "En fazla 15 dakika"),
  style: z.string().trim().min(2).max(120),
});

export async function createProject(_prev: FormState, form: FormData): Promise<FormState> {
  const parsed = NewProject.safeParse(Object.fromEntries(form));
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Geçersiz form" };
  const { topic, language, target_minutes, style } = parsed.data;

  const sql = db();
  const base = slugify(topic.split(/[—–:-]/)[0] || topic);
  let slug = base;
  for (let i = 2; ; i++) {
    const [exists] = await sql`select 1 from projects where slug = ${slug}`;
    if (!exists) break;
    slug = `${base}-${i}`;
  }

  await sql.begin(async (tx) => {
    const [p] = await tx<{ id: string }[]>`
      insert into projects (slug, title, topic, language, target_minutes, style)
      values (${slug}, ${topic}, ${topic}, ${language}, ${target_minutes}, ${style}) returning id`;
    await tx`select create_pipeline_job(${p.id})`;
  });

  await dispatchWorker(`yeni proje: ${slug}`);
  revalidatePath("/", "layout");
  redirect(`/projeler/${slug}`);
}

export async function approveStep(stepId: string, slug: string) {
  await db()`select resolve_input_step(${stepId}, ${db().json({ approved_by: "user", at: new Date().toISOString() })})
             where exists (select 1 from job_steps where id = ${stepId} and step_key = 'research_review')`;
  await dispatchWorker(`onay: ${slug}`);
  revalidatePath(`/projeler/${slug}`);
}

export async function retryStep(stepId: string, slug: string) {
  await db()`select retry_step(${stepId})`;
  await dispatchWorker(`yeniden dene: ${slug}`);
  revalidatePath(`/projeler/${slug}`);
  revalidatePath("/render");
}

export async function cancelJob(jobId: string, slug: string) {
  await db().begin(async (tx) => {
    await tx`update jobs set status = 'cancelled', finished_at = now() where id = ${jobId} and status not in ('done','cancelled')`;
    await tx`update job_steps set status = 'cancelled' where job_id = ${jobId} and status in ('pending','waiting_input')`;
    await tx`select refresh_job_status(${jobId})`;
  });
  revalidatePath(`/projeler/${slug}`);
}

export async function restartPipeline(projectId: string, slug: string) {
  await db()`select create_pipeline_job(${projectId})`;
  await dispatchWorker(`yeniden başlat: ${slug}`);
  revalidatePath(`/projeler/${slug}`);
}

export async function archiveProject(projectId: string, slug: string) {
  await db()`update projects set status = 'archived' where id = ${projectId}`;
  revalidatePath(`/projeler/${slug}`);
  revalidatePath("/projeler");
}

const SettingsForm = z.object({
  storage_guard_gb: z.coerce.number().min(0.5).max(10),
  license_allow_nc: z.enum(["on"]).optional(),
  license_allow_sa: z.enum(["on"]).optional(),
  default_minutes: z.coerce.number().min(8).max(15),
});

export async function saveSettings(_prev: FormState, form: FormData): Promise<FormState> {
  const parsed = SettingsForm.safeParse(Object.fromEntries(form));
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Geçersiz değer" };
  const s = parsed.data;
  const sql = db();
  const rows: [string, unknown][] = [
    ["storage_guard_bytes", Math.round(s.storage_guard_gb * 1024 ** 3)],
    ["license_allow_nc", s.license_allow_nc === "on"],
    ["license_allow_sa", s.license_allow_sa === "on"],
    ["default_minutes", s.default_minutes],
  ];
  for (const [key, value] of rows) {
    await sql`insert into settings (key, value) values (${key}, ${sql.json(value as never)})
              on conflict (key) do update set value = excluded.value, updated_at = now()`;
  }
  revalidatePath("/ayarlar");
  return { ok: "Ayarlar kaydedildi" };
}

export async function login(_prev: FormState, form: FormData): Promise<FormState> {
  const password = String(form.get("password") ?? "");
  const next = String(form.get("next") ?? "/");
  if (!checkPassword(password)) return { error: "Şifre hatalı" };
  const { token, maxAge } = await createSessionToken();
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  });
  redirect(next.startsWith("/") && !next.startsWith("//") ? next : "/");
}

export async function logout() {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}

// ----------------------------------------------------------------- Stage 4: senaryo düzenleme ve onay

async function projectBySlug(slug: string) {
  const [p] = await db()<{ id: string }[]>`select id from projects where slug = ${slug}`;
  if (!p) throw new Error("Proje bulunamadı");
  return p;
}

async function scriptLocked(projectId: string) {
  const [r] = await db()<{ locked: boolean }[]>`
    select exists (select 1 from scripts s where s.project_id = ${projectId} and s.approved_at is not null
                    and s.version = (select max(version) from scripts x where x.project_id = s.project_id and x.kind = s.kind)) as locked`;
  return r.locked;
}

export async function updateSceneText(slug: string, sceneId: string, text: string): Promise<FormState> {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length < 3) return { error: "Metin boş olamaz" };
  if (clean.length > 1500) return { error: "Bir sahne en fazla 1500 karakter olabilir" };
  const p = await projectBySlug(slug);
  if (await scriptLocked(p.id)) return { error: "Senaryo onaylanmış; düzenlemek için önce onayı geri alın" };
  const sql = db();
  const [wpm] = await sql<{ doc: number; shorts: number }[]>`
    select (select (value #>> '{}')::numeric from settings where key='narration_wpm') doc,
           (select (value #>> '{}')::numeric from settings where key='shorts_wpm') shorts`;
  const words = (clean.match(/[\p{L}\p{N}]+/gu) ?? []).length;
  const [cur] = await sql<{ kind: "doc" | "shorts"; script_id: string }[]>`
    select kind, script_id from scenes where id = ${sceneId} and project_id = ${p.id}`;
  if (!cur) return { error: "Sahne bulunamadı" };
  const rate = cur.kind === "doc" ? wpm.doc : wpm.shorts;
  await sql`update scenes set voiceover_text = ${clean}, word_count = ${words}, edited_at = now(),
                   est_duration_sec = round(${words}::numeric / ${rate} * 60, 2)
             where id = ${sceneId}`;
  await sql`update scripts s set word_count = t.w, est_seconds = round(t.w::numeric / ${rate} * 60, 1)
              from (select coalesce(sum(word_count), 0) w from scenes where project_id = ${p.id} and kind = ${cur.kind}) t
             where s.id = ${cur.script_id}`;
  revalidatePath("/senaryo");
  return { ok: "Kaydedildi" };
}

export async function approveScripts(slug: string): Promise<FormState> {
  const p = await projectBySlug(slug);
  const sql = db();
  const step = await sql<{ id: string }[]>`
    select s.id from job_steps s join jobs j on j.id = s.job_id
     where s.project_id = ${p.id} and s.step_key = 'script_review' and s.status = 'waiting_input'
     order by j.created_at desc limit 1`;
  if (!step.length) return { error: "Onay bekleyen senaryo adımı yok" };
  await sql.begin(async (tx) => {
    await tx`update scripts s set approved_at = now()
              where s.project_id = ${p.id}
                and s.version = (select max(version) from scripts x where x.project_id = s.project_id and x.kind = s.kind)`;
    await tx`select resolve_input_step(${step[0].id}, ${tx.json({ approved_by: "user", at: new Date().toISOString() })})`;
  });
  await dispatchWorker(`senaryo onayı: ${slug}`);
  revalidatePath("/senaryo");
  revalidatePath("/seslendirme");
  return { ok: "Senaryo onaylandı; ElevenLabs metinleri hazırlanıyor" };
}

export async function unapproveScripts(slug: string): Promise<FormState> {
  const p = await projectBySlug(slug);
  const sql = db();
  const [vo] = await sql<{ n: number }[]>`select count(*)::int n from voiceovers where project_id = ${p.id}`;
  if (vo.n > 0) return { error: "Seslendirme yüklendikten sonra senaryo onayı geri alınamaz (ses ile metin uyuşmaz)" };
  const [job] = await sql<{ id: string }[]>`select id from jobs where project_id = ${p.id} order by created_at desc limit 1`;
  await sql.begin(async (tx) => {
    await tx`update scripts set approved_at = null where project_id = ${p.id}`;
    await tx`select reset_from_step(${job.id}, 'script_review')`;
  });
  revalidatePath("/senaryo");
  return { ok: "Onay geri alındı; senaryo yeniden düzenlenebilir" };
}

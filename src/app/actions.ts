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

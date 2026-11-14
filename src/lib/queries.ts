import "server-only";
import { connection } from "next/server";
import { db } from "./db";

export type StepStatus = "pending" | "running" | "waiting_input" | "done" | "failed" | "skipped" | "cancelled";
export type JobStatus = "queued" | "running" | "waiting_input" | "done" | "failed" | "cancelled";

export type Project = {
  id: string;
  slug: string;
  title: string;
  topic: string;
  language: string;
  target_minutes: string;
  shorts_seconds: number;
  style: string;
  status: string;
  created_at: Date;
  updated_at: Date;
};

export type Step = {
  id: string;
  job_id: string;
  step_key: string;
  seq: number;
  label: string;
  stage: number;
  requires_input: boolean;
  status: StepStatus;
  attempts: number;
  max_attempts: number;
  heartbeat_at: Date | null;
  started_at: Date | null;
  finished_at: Date | null;
  error: string | null;
  output: Record<string, unknown> | null;
};

export type ErrorLog = {
  id: string;
  project_id: string | null;
  step_key: string | null;
  level: "info" | "warning" | "error";
  message: string;
  created_at: Date;
  slug: string | null;
};

export async function listProjects() {
  await connection();
  return db()<(Project & { job_id: string | null; job_status: JobStatus | null; done_steps: number; total_steps: number })[]>`
    select p.*, j.id as job_id, j.status as job_status,
           coalesce((select count(*) from job_steps s where s.job_id = j.id and s.status in ('done','skipped')), 0)::int as done_steps,
           coalesce((select count(*) from job_steps s where s.job_id = j.id), 0)::int as total_steps
      from projects p
      left join lateral (select * from jobs where project_id = p.id order by created_at desc limit 1) j on true
     order by p.updated_at desc`;
}

export async function getProject(slug: string) {
  await connection();
  const [p] = await db()<Project[]>`select * from projects where slug = ${slug}`;
  return p ?? null;
}

export async function getLatestJob(projectId: string) {
  const [j] = await db()<{ id: string; status: JobStatus; created_at: Date; updated_at: Date }[]>`
    select id, status, created_at, updated_at from jobs where project_id = ${projectId} order by created_at desc limit 1`;
  return j ?? null;
}

export async function getSteps(jobId: string) {
  return db()<Step[]>`
    select s.id, s.job_id, s.step_key, s.seq, d.label, d.stage, d.requires_input, s.status, s.attempts,
           s.max_attempts, s.heartbeat_at, s.started_at, s.finished_at, s.error, s.output
      from job_steps s join step_definitions d using (step_key)
     where s.job_id = ${jobId} order by s.seq`;
}

export async function getProjectStatus(slug: string) {
  const project = await getProject(slug);
  if (!project) return null;
  const job = await getLatestJob(project.id);
  const steps = job ? await getSteps(job.id) : [];
  return { project, job, steps };
}

export async function getStorageUsage() {
  await connection();
  const [u] = await db()<{ used_bytes: string; limit_bytes: string; guard_bytes: string }[]>`select * from storage_usage`;
  return { used: Number(u.used_bytes), limit: Number(u.limit_bytes), guard: Number(u.guard_bytes) };
}

export async function getDashboard() {
  await connection();
  const sql = db();
  const [counts] = await sql<{
    active: number;
    done: number;
    waiting_voice: number;
    renders_done: number;
    running_steps: number;
    queued_steps: number;
    failed_steps: number;
  }[]>`
    select
      (select count(*) from projects where status in ('active','waiting_input','rendering'))::int as active,
      (select count(*) from projects where status = 'done')::int as done,
      (select count(*) from job_steps s join jobs j on j.id = s.job_id
         where s.step_key = 'voiceover_wait' and s.status = 'waiting_input' and j.status <> 'cancelled')::int as waiting_voice,
      (select count(*) from renders where status = 'done')::int as renders_done,
      (select count(*) from job_steps where status = 'running')::int as running_steps,
      (select count(*) from job_steps s join jobs j on j.id = s.job_id
         where s.status = 'pending' and j.status in ('queued','running'))::int as queued_steps,
      (select count(*) from job_steps where status = 'failed')::int as failed_steps`;
  const errors = await sql<ErrorLog[]>`
    select e.id::text, e.project_id, e.step_key, e.level, e.message, e.created_at, p.slug
      from error_logs e left join projects p on p.id = e.project_id
     order by e.created_at desc limit 8`;
  const active = await sql<(Project & { current_label: string | null; current_status: StepStatus | null })[]>`
    select p.*, c.label as current_label, c.status as current_status
      from projects p
      left join lateral (
        select d.label, s.status from jobs j
          join job_steps s on s.job_id = j.id join step_definitions d using (step_key)
         where j.project_id = p.id and s.status not in ('done','skipped')
         order by j.created_at desc, s.seq limit 1) c on true
     where p.status in ('active','waiting_input','rendering')
     order by p.updated_at desc limit 6`;
  return { counts, errors, active, storage: await getStorageUsage() };
}

export async function getRenderQueue() {
  await connection();
  return db()<(Step & { slug: string; title: string })[]>`
    select s.id, s.job_id, s.step_key, s.seq, d.label, d.stage, d.requires_input, s.status, s.attempts,
           s.max_attempts, s.heartbeat_at, s.started_at, s.finished_at, s.error, s.output, p.slug, p.title
      from job_steps s join step_definitions d using (step_key)
      join jobs j on j.id = s.job_id join projects p on p.id = s.project_id
     where j.status not in ('cancelled')
       and (s.status in ('running','failed','waiting_input')
            or (s.status = 'pending' and not exists (
                  select 1 from job_steps x where x.job_id = s.job_id and x.seq < s.seq and x.status not in ('done','skipped'))))
     order by case s.status when 'running' then 0 when 'failed' then 1 when 'waiting_input' then 2 else 3 end, s.updated_at desc`;
}

export async function getSettings() {
  await connection();
  const rows = await db()<{ key: string; value: unknown }[]>`select key, value from settings`;
  return Object.fromEntries(rows.map((r) => [r.key, r.value])) as Record<string, unknown>;
}

export async function dbHealthy() {
  try {
    await db()`select 1`;
    return true;
  } catch {
    return false;
  }
}

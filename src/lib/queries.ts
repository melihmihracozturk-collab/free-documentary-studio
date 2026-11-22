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
  format: "documentary" | "vlog" | "review";
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

/** Projenin biçimi (documentary | vlog | review). Öneri (Ayla) projeleri yalnızca Shorts üretir. */
export async function getProjectFormat(projectId: string) {
  await connection();
  const [p] = await db()<{ format: Project["format"] }[]>`select format from projects where id = ${projectId}`;
  return p?.format ?? "documentary";
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
  const usage = await sql<{ metric: string; n: number }[]>`
    select metric, sum(value)::int n from usage_metrics where period = current_date and metric like 'llm:%' group by metric order by n desc`;
  return { counts, errors, active, usage, storage: await getStorageUsage() };
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

export type Claim = {
  id: string; ref: string; text: string; status: "verified" | "weak" | "conflict" | "rejected" | "pending";
  conflict_note: string | null; category: string | null; importance: number; event_date: string | null;
  support: { source_ref: string; quote: string }[]; independent_sources: number;
};
export type Source = {
  id: string; ref: string; url: string; title: string; publisher: string; source_type: string;
  collector: string; published: string | null;
};
export type Scene = {
  id: string; kind: "doc" | "shorts"; idx: number; act: string | null; est_duration_sec: string | null;
  voiceover_text: string; visual_description: string | null; camera_move: string | null; transition: string | null;
  music: string | null; sfx: string | null; search_keywords: string[]; claim_refs: string[];
  on_screen_text: string | null; word_count: number | null; needs_check: boolean;
};
export type Script = {
  id: string; kind: "doc" | "shorts"; version: number; approved_at: Date | null; word_count: number | null; est_seconds: string | null;
  voiceover_text: string | null;
  content: { title?: string; logline?: string; format?: "documentary" | "vlog" | "review"; act_titles?: Record<string, string> }; validation: { errors?: string[]; ok?: boolean };
  created_at: Date;
};

export async function getResearch(projectId: string) {
  const sql = db();
  const [report] = await sql<{ version: number; summary: string | null; markdown: string; stats: Record<string, number>; created_at: Date }[]>`
    select version, summary, markdown, stats, created_at from research_reports
     where project_id = ${projectId} order by version desc limit 1`;
  const claims = await sql<Claim[]>`
    select id, ref, text, status, conflict_note, category, importance, event_date, support, independent_sources
      from claims where project_id = ${projectId}
     order by case status when 'conflict' then 0 when 'verified' then 1 when 'weak' then 2 else 3 end,
              importance desc, (substring(ref from 2))::int`;
  const sources = await sql<Source[]>`
    select id, ref, url, title, publisher, source_type, collector, published from sources
     where project_id = ${projectId} order by (substring(ref from 2))::int`;
  return { report: report ?? null, claims, sources };
}

export async function getScripts(projectId: string) {
  const sql = db();
  const scripts = await sql<Script[]>`
    select distinct on (kind) id, kind, version, approved_at, word_count, est_seconds, voiceover_text, content, validation, created_at
      from scripts where project_id = ${projectId} order by kind, version desc`;
  const scenes = await sql<Scene[]>`
    select id, kind, idx, act, est_duration_sec, voiceover_text, visual_description, camera_move, transition, music, sfx,
           search_keywords, claim_refs, on_screen_text, word_count, needs_check
      from scenes where project_id = ${projectId} order by kind, idx`;
  return {
    doc: scripts.find((s) => s.kind === "doc") ?? null,
    shorts: scripts.find((s) => s.kind === "shorts") ?? null,
    docScenes: scenes.filter((s) => s.kind === "doc"),
    shortsScenes: scenes.filter((s) => s.kind === "shorts"),
  };
}

export type Voiceover = {
  id: string; kind: "doc" | "shorts"; storage_key: string; filename: string; mime: string | null; bytes: string;
  sha256: string | null; duration_sec: string | null; coverage: string | null; status: "uploaded" | "analyzing" | "analyzed" | "failed";
  analysis: { duration_sec?: number; coverage?: number; wpm?: number; pauses?: number; longest_pause_sec?: number;
    warnings?: string[]; scene_times?: [number, number][] } | null;
  uploaded_at: Date;
};

export async function getVoiceovers(projectId: string) {
  return db()<Voiceover[]>`select id, kind, storage_key, filename, mime, bytes, sha256, duration_sec, coverage, status, analysis, uploaded_at
                           from voiceovers where project_id = ${projectId} order by kind`;
}

/** Senaryo düzenleme ekranı için iddia metinleri (sayı denetimi panelde yapılır). */
export async function getClaimsText(projectId: string) {
  const rows = await db()<{ ref: string; status: string; text: string; event_date: string | null }[]>`
    select ref, status, text, event_date from claims where project_id = ${projectId} and status in ('verified','weak','conflict')`;
  return rows.map((c) => `${c.ref} [${c.status}]${c.event_date ? ` (${c.event_date})` : ""} ${c.text}`).join("\n");
}

export async function getStepState(projectId: string, stepKey: string) {
  const [s] = await db()<{ id: string; status: StepStatus; job_id: string }[]>`
    select s.id, s.status, s.job_id from job_steps s join jobs j on j.id = s.job_id
     where s.project_id = ${projectId} and s.step_key = ${stepKey} order by j.created_at desc limit 1`;
  return s ?? null;
}

export type VisualAsset = {
  id: string; scene_id: string; source: string | null; title: string | null; source_url: string | null; thumb_url: string | null;
  author: string | null; license: string | null; license_class: string | null; license_url: string | null;
  width: number | null; height: number | null; score: string | null; status: string; storage_key: string | null;
};
export type VisualScene = {
  id: string; kind: "doc" | "shorts"; idx: number; act: string | null; voiceover_text: string; visual_description: string | null;
  asset_id: string | null; start_sec: string | null; end_sec: string | null; search_keywords: string[];
};

export async function getVisuals(projectId: string) {
  const sql = db();
  const scenes = await sql<VisualScene[]>`
    select id, kind, idx, act, voiceover_text, visual_description, asset_id, start_sec, end_sec, search_keywords
      from scenes where project_id = ${projectId} order by kind, idx`;
  const assets = await sql<VisualAsset[]>`
    select id, scene_id, source, title, source_url, thumb_url, author, license, license_class, license_url, width, height,
           score, status, storage_key
      from assets where project_id = ${projectId} and scene_id is not null order by score desc nulls last`;
  return { scenes, assets };
}

export type Render = {
  id: string; kind: "doc" | "shorts"; width: number; height: number; fps: string; duration_sec: string; bytes: string;
  sha256: string | null; status: string; created_at: Date;
};

export async function getRenders(projectId: string) {
  return db()<Render[]>`select id, kind, width, height, fps, duration_sec, bytes, sha256, status, created_at
                        from renders where project_id = ${projectId} and status = 'done' order by created_at desc`;
}

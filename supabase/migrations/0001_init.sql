-- FREE DOCUMENTARY STUDIO — Stage 2 başlangıç şeması
-- Supabase (Postgres 15+) ve yerel Postgres 16 ile uyumludur.
-- Uygulama veritabanına yalnızca sunucu tarafından (DATABASE_URL) erişir.
-- Tüm tablolarda RLS açıktır ve anon/authenticated için politika yoktur:
-- böylece Supabase'in herkese açık REST API'si üzerinden veri okunamaz.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- ayarlar
create table if not exists settings (
  key         text primary key,
  value       jsonb not null,
  updated_at  timestamptz not null default now()
);

insert into settings (key, value) values
  ('storage_limit_bytes', to_jsonb(10737418240::bigint)),      -- R2 ücretsiz: 10 GB
  ('storage_guard_bytes', to_jsonb(8589934592::bigint)),       -- 8 GB'ta yeni render durur
  ('license_allow_nc',    'false'::jsonb),                     -- NC lisanslar varsayılan kapalı
  ('license_allow_sa',    'true'::jsonb),
  ('default_language',    '"tr"'::jsonb),
  ('default_minutes',     '11'::jsonb)
on conflict (key) do nothing;

-- ---------------------------------------------------------------- projeler
create table if not exists projects (
  id              uuid primary key default gen_random_uuid(),
  slug            text not null unique check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  title           text not null,
  topic           text not null,
  language        text not null default 'tr',
  target_minutes  numeric(4,1) not null default 11 check (target_minutes between 8 and 15),
  shorts_seconds  int not null default 55 check (shorts_seconds between 45 and 60),
  style           text not null default 'Sinematik kısa belgesel',
  status          text not null default 'active'
                  check (status in ('active','waiting_input','rendering','done','failed','archived')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create table if not exists sources (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references projects(id) on delete cascade,
  url          text not null,
  title        text,
  publisher    text,
  source_type  text not null default 'web'
               check (source_type in ('archive','academic','official','encyclopedia','museum','news','web')),
  accessed_at  timestamptz not null default now(),
  notes        text,
  unique (project_id, url)
);

create table if not exists claims (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references projects(id) on delete cascade,
  text           text not null,
  status         text not null default 'pending'
                 check (status in ('pending','verified','weak','conflict','rejected')),
  conflict_note  text,
  source_ids     uuid[] not null default '{}',
  created_at     timestamptz not null default now()
);

create table if not exists scripts (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id) on delete cascade,
  kind            text not null check (kind in ('doc','shorts')),
  version         int not null default 1,
  content         jsonb not null default '{}',
  voiceover_text  text,
  created_at      timestamptz not null default now(),
  unique (project_id, kind, version)
);

create table if not exists assets (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references projects(id) on delete cascade,
  kind           text not null check (kind in ('image','video','map','document','graphic','ai_image','music','sfx')),
  source_url     text,
  file_url       text,
  storage_key    text,
  author         text,
  license        text,
  license_url    text,
  attribution    text,
  is_ai          boolean not null default false,
  sha256         text,
  bytes          bigint not null default 0,
  status         text not null default 'candidate' check (status in ('candidate','approved','rejected')),
  reject_reason  text,
  created_at     timestamptz not null default now()
);

create table if not exists scenes (
  id                  uuid primary key default gen_random_uuid(),
  project_id          uuid not null references projects(id) on delete cascade,
  script_id           uuid references scripts(id) on delete cascade,
  kind                text not null check (kind in ('doc','shorts')),
  idx                 int not null,
  est_duration_sec    numeric(6,2),
  voiceover_text      text,
  visual_description  text,
  camera_move         text,
  transition          text,
  music               text,
  sfx                 text,
  start_sec           numeric(8,3),
  end_sec             numeric(8,3),
  asset_id            uuid references assets(id) on delete set null,
  unique (project_id, kind, idx)
);

create table if not exists voiceovers (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  kind          text not null check (kind in ('doc','shorts')),
  storage_key   text not null,
  filename      text not null,
  mime          text,
  bytes         bigint not null default 0,
  sha256        text,
  duration_sec  numeric(8,3),
  analysis      jsonb,
  status        text not null default 'uploaded'
                check (status in ('uploaded','analyzing','analyzed','failed')),
  created_at    timestamptz not null default now(),
  unique (project_id, kind)
);

create table if not exists renders (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  kind          text not null check (kind in ('doc','shorts','silent_preview')),
  storage_key   text,
  width         int,
  height        int,
  fps           numeric(5,2),
  duration_sec  numeric(8,3),
  bytes         bigint not null default 0,
  sha256        text,
  status        text not null default 'pending' check (status in ('pending','running','done','failed','deleted')),
  created_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------- iş kuyruğu
create table if not exists jobs (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references projects(id) on delete cascade,
  kind         text not null default 'pipeline',
  status       text not null default 'queued'
               check (status in ('queued','running','waiting_input','done','failed','cancelled')),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  finished_at  timestamptz
);

-- Adım tanımları: sıra, kullanıcı girdisi gerekip gerekmediği ve hangi Stage'de uygulanacağı.
create table if not exists step_definitions (
  step_key        text primary key,
  seq             int not null unique,
  label           text not null,
  requires_input  boolean not null default false,
  stage           int not null,
  max_attempts    int not null default 3
);

insert into step_definitions (step_key, seq, label, requires_input, stage) values
  ('research_collect',  10,  'Konuyu araştır',                        false, 3),
  ('research_verify',   20,  'Kaynakları doğrula',                    false, 3),
  ('research_report',   30,  'Araştırma raporu oluştur',              false, 3),
  ('research_review',   40,  'Araştırma onayı (kullanıcı)',           true,  3),
  ('script_doc',        50,  'Belgesel senaryosu yaz',                false, 3),
  ('script_shorts',     60,  'Shorts senaryosu yaz',                  false, 3),
  ('visual_plan',       70,  'Sahne sahne görsel plan',               false, 5),
  ('voiceover_texts',   80,  'ElevenLabs metinlerini hazırla',        false, 4),
  ('voiceover_wait',    90,  'Seslendirme dosyalarını bekle',         true,  4),
  ('voiceover_analyze', 100, 'Sesleri analiz et',                     false, 4),
  ('asset_match',       110, 'Görselleri seslendirmeyle eşleştir',    false, 5),
  ('subtitles',         120, 'Altyazıları oluştur',                   false, 6),
  ('render_doc',        130, 'Ana belgeseli render et',               false, 6),
  ('render_shorts',     140, 'Shorts videosunu render et',            false, 7),
  ('preview_ready',     150, 'Önizlemeye sun ve indirmeye hazırla',   false, 8)
on conflict (step_key) do update
  set seq = excluded.seq, label = excluded.label,
      requires_input = excluded.requires_input, stage = excluded.stage;

create table if not exists job_steps (
  id            uuid primary key default gen_random_uuid(),
  job_id        uuid not null references jobs(id) on delete cascade,
  project_id    uuid not null references projects(id) on delete cascade,
  step_key      text not null references step_definitions(step_key),
  seq           int not null,
  status        text not null default 'pending'
                check (status in ('pending','running','waiting_input','done','failed','skipped','cancelled')),
  attempts      int not null default 0,
  max_attempts  int not null default 3,
  worker_id     text,
  heartbeat_at  timestamptz,
  started_at    timestamptz,
  finished_at   timestamptz,
  output        jsonb,
  output_key    text,
  sha256        text,
  error         text,
  updated_at    timestamptz not null default now(),
  unique (job_id, step_key)
);

create index if not exists job_steps_claim_idx on job_steps (status, seq) where status = 'pending';
create index if not exists job_steps_running_idx on job_steps (heartbeat_at) where status = 'running';

create table if not exists error_logs (
  id          bigint generated always as identity primary key,
  project_id  uuid references projects(id) on delete cascade,
  job_id      uuid references jobs(id) on delete cascade,
  step_key    text,
  level       text not null default 'error' check (level in ('info','warning','error')),
  message     text not null,
  detail      jsonb,
  created_at  timestamptz not null default now()
);
create index if not exists error_logs_created_idx on error_logs (created_at desc);

create table if not exists usage_metrics (
  id           bigint generated always as identity primary key,
  metric       text not null,        -- ör. llm_requests:gemini, actions_minutes, neurons
  value        numeric not null,
  period       date not null default current_date,
  recorded_at  timestamptz not null default now()
);
create index if not exists usage_metrics_metric_idx on usage_metrics (metric, period);

-- ---------------------------------------------------------------- görünümler
create or replace view storage_usage as
select
  coalesce((select sum(bytes) from assets), 0)
  + coalesce((select sum(bytes) from voiceovers), 0)
  + coalesce((select sum(bytes) from renders where status <> 'deleted'), 0) as used_bytes,
  (select (value #>> '{}')::bigint from settings where key = 'storage_limit_bytes') as limit_bytes,
  (select (value #>> '{}')::bigint from settings where key = 'storage_guard_bytes') as guard_bytes;

-- ---------------------------------------------------------------- yardımcılar
create or replace function touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;

drop trigger if exists projects_touch on projects;
create trigger projects_touch before update on projects for each row execute function touch_updated_at();
drop trigger if exists jobs_touch on jobs;
create trigger jobs_touch before update on jobs for each row execute function touch_updated_at();
drop trigger if exists job_steps_touch on job_steps;
create trigger job_steps_touch before update on job_steps for each row execute function touch_updated_at();

-- Yeni proje + iş + tüm adımlar (tek işlemde)
create or replace function create_pipeline_job(p_project_id uuid) returns uuid
language plpgsql as $$
declare v_job uuid;
begin
  insert into jobs (project_id) values (p_project_id) returning id into v_job;
  insert into job_steps (job_id, project_id, step_key, seq, max_attempts)
  select v_job, p_project_id, d.step_key, d.seq, d.max_attempts
  from step_definitions d order by d.seq;
  perform refresh_job_status(v_job);
  return v_job;
end $$;

-- Sıradaki adım kullanıcı girdisi istiyorsa waiting_input'a alınır; iş ve proje durumları güncellenir.
create or replace function refresh_job_status(p_job uuid) returns void
language plpgsql as $$
declare
  v_next record;
  v_status text;
  v_project uuid;
begin
  select project_id into v_project from jobs where id = p_job;

  select s.* into v_next from job_steps s
   where s.job_id = p_job and s.status not in ('done','skipped')
   order by s.seq limit 1;

  if v_next.id is not null and v_next.status = 'pending'
     and exists (select 1 from step_definitions d where d.step_key = v_next.step_key and d.requires_input) then
    update job_steps set status = 'waiting_input' where id = v_next.id;
    v_next.status := 'waiting_input';
  end if;

  v_status := case
    when exists (select 1 from jobs where id = p_job and status = 'cancelled') then 'cancelled'
    when v_next.id is null then 'done'
    when v_next.status = 'failed' then 'failed'
    when v_next.status = 'waiting_input' then 'waiting_input'
    when v_next.status = 'running' then 'running'
    when exists (select 1 from job_steps where job_id = p_job and status in ('done','skipped')) then 'running'
    else 'queued' end;

  update jobs set status = v_status,
                  finished_at = case when v_status in ('done','failed','cancelled') then now() else null end
   where id = p_job and status is distinct from v_status;

  update projects set status = case
      when v_status = 'done' then 'done'
      when v_status = 'failed' then 'failed'
      when v_status = 'waiting_input' then 'waiting_input'
      when v_next.step_key in ('render_doc','render_shorts') and v_next.status = 'running' then 'rendering'
      else 'active' end
   where id = v_project and status <> 'archived';
end $$;

-- KURAL: Gerçek seslendirme yüklenip analiz edilmeden render başlayamaz.
-- KURAL: Depolama koruma eşiği aşıldıysa yeni render başlamaz.
create or replace function guard_render_start() returns trigger
language plpgsql as $$
declare v_kind text; v_used bigint; v_guard bigint;
begin
  if new.status = 'running' and old.status is distinct from 'running'
     and new.step_key in ('render_doc','render_shorts') then
    v_kind := case new.step_key when 'render_doc' then 'doc' else 'shorts' end;
    if not exists (select 1 from voiceovers v
                    where v.project_id = new.project_id and v.kind = v_kind and v.status = 'analyzed') then
      raise exception 'RENDER_BLOCKED_NO_VOICEOVER: % için analiz edilmiş gerçek seslendirme yok', v_kind
        using errcode = 'P0001';
    end if;
    select used_bytes, guard_bytes into v_used, v_guard from storage_usage;
    if v_used >= v_guard then
      raise exception 'RENDER_BLOCKED_STORAGE: depolama koruma eşiği aşıldı (% / % bayt)', v_used, v_guard
        using errcode = 'P0001';
    end if;
  end if;
  return new;
end $$;

drop trigger if exists job_steps_render_guard on job_steps;
create trigger job_steps_render_guard before update on job_steps
  for each row execute function guard_render_start();

-- İşçi: sıradaki uygun adımı kilitleyip alır. p_keys: işçinin desteklediği adımlar.
-- Bir adım ancak aynı işteki önceki tüm adımlar done/skipped ise alınabilir.
create or replace function claim_next_step(p_worker text, p_keys text[] default null)
returns setof job_steps language plpgsql as $$
declare v_id uuid;
begin
  loop
    select s.id into v_id
      from job_steps s
      join jobs j on j.id = s.job_id and j.status not in ('cancelled','failed','done')
     where s.status = 'pending'
       and (p_keys is null or s.step_key = any(p_keys))
       and not exists (select 1 from job_steps p
                        where p.job_id = s.job_id and p.seq < s.seq
                          and p.status not in ('done','skipped'))
     order by j.created_at, s.seq
     for update of s skip locked
     limit 1;

    if v_id is null then return; end if;

    begin
      return query
        update job_steps set status = 'running', attempts = attempts + 1, worker_id = p_worker,
               heartbeat_at = now(), started_at = now(), error = null
         where id = v_id returning *;
      perform refresh_job_status((select job_id from job_steps where id = v_id));
      return;
    exception when sqlstate 'P0001' then
      -- Render koruması: adım beklemede kalır, nedeni kaydedilir, sonraki adaya geçilmez.
      if (select error from job_steps where id = v_id) is distinct from sqlerrm then
        update job_steps set error = sqlerrm where id = v_id;
        insert into error_logs (project_id, job_id, step_key, level, message)
          select project_id, job_id, step_key, 'warning', sqlerrm from job_steps where id = v_id;
      end if;
      return;
    end;
  end loop;
end $$;

create or replace function heartbeat_step(p_step uuid, p_worker text) returns boolean
language sql as $$
  update job_steps set heartbeat_at = now()
   where id = p_step and worker_id = p_worker and status = 'running'
  returning true;
$$;

create or replace function complete_step(p_step uuid, p_worker text, p_output jsonb default null,
                                         p_output_key text default null, p_sha256 text default null)
returns boolean language plpgsql as $$
declare v_job uuid;
begin
  update job_steps set status = 'done', finished_at = now(), output = p_output,
         output_key = p_output_key, sha256 = p_sha256, error = null
   where id = p_step and worker_id = p_worker and status = 'running'
  returning job_id into v_job;
  if v_job is null then return false; end if;
  perform refresh_job_status(v_job);
  return true;
end $$;

create or replace function fail_step(p_step uuid, p_worker text, p_error text) returns text
language plpgsql as $$
declare v_row job_steps; v_new text;
begin
  select * into v_row from job_steps where id = p_step and worker_id = p_worker and status = 'running' for update;
  if v_row.id is null then return null; end if;
  v_new := case when v_row.attempts >= v_row.max_attempts then 'failed' else 'pending' end;
  update job_steps set status = v_new, error = p_error, worker_id = null,
         finished_at = case when v_new = 'failed' then now() else null end
   where id = p_step;
  insert into error_logs (project_id, job_id, step_key, level, message, detail)
  values (v_row.project_id, v_row.job_id, v_row.step_key,
          case when v_new = 'failed' then 'error' else 'warning' end, p_error,
          jsonb_build_object('attempt', v_row.attempts, 'max_attempts', v_row.max_attempts));
  perform refresh_job_status(v_row.job_id);
  return v_new;
end $$;

-- Kalp atışı kesilen (ör. runner kapandı) adımları yeniden kuyruğa al.
create or replace function requeue_stale_steps(p_stale interval default interval '10 minutes')
returns int language plpgsql as $$
declare v_count int := 0; r record;
begin
  for r in select * from job_steps where status = 'running' and heartbeat_at < now() - p_stale for update skip locked loop
    update job_steps set status = case when r.attempts >= r.max_attempts then 'failed' else 'pending' end,
           worker_id = null, error = 'Kalp atışı kesildi; adım yeniden kuyruğa alındı'
     where id = r.id;
    insert into error_logs (project_id, job_id, step_key, level, message)
    values (r.project_id, r.job_id, r.step_key, 'warning', 'Kalp atışı kesildi; adım yeniden kuyruğa alındı');
    perform refresh_job_status(r.job_id);
    v_count := v_count + 1;
  end loop;
  return v_count;
end $$;

-- Kullanıcı girdisi gerektiren adımı tamamla (ör. araştırma onayı).
create or replace function resolve_input_step(p_step uuid, p_output jsonb default null) returns boolean
language plpgsql as $$
declare v_job uuid;
begin
  update job_steps set status = 'done', finished_at = now(), output = p_output
   where id = p_step and status = 'waiting_input' returning job_id into v_job;
  if v_job is null then return false; end if;
  perform refresh_job_status(v_job);
  return true;
end $$;

-- Başarısız adımı yeniden dene (kullanıcı isteğiyle; deneme sayacı sıfırlanır).
create or replace function retry_step(p_step uuid) returns boolean
language plpgsql as $$
declare v_job uuid;
begin
  update job_steps set status = 'pending', attempts = 0, error = null, finished_at = null, worker_id = null
   where id = p_step and status = 'failed' returning job_id into v_job;
  if v_job is null then return false; end if;
  update jobs set status = 'running' where id = v_job and status = 'failed';
  perform refresh_job_status(v_job);
  return true;
end $$;

-- İki seslendirme de yüklendiğinde "seslendirme bekleniyor" adımı otomatik serbest kalır.
create or replace function release_voiceover_wait() returns trigger
language plpgsql as $$
declare r record;
begin
  if (select count(distinct kind) from voiceovers
       where project_id = new.project_id and status in ('uploaded','analyzing','analyzed')) = 2 then
    for r in select s.id from job_steps s join jobs j on j.id = s.job_id
              where s.project_id = new.project_id and s.step_key = 'voiceover_wait'
                and s.status = 'waiting_input' and j.status <> 'cancelled' loop
      perform resolve_input_step(r.id, jsonb_build_object('released_by', 'voiceover_upload'));
    end loop;
  end if;
  return new;
end $$;

drop trigger if exists voiceovers_release on voiceovers;
create trigger voiceovers_release after insert or update on voiceovers
  for each row execute function release_voiceover_wait();

-- ---------------------------------------------------------------- RLS
do $$
declare t text;
begin
  foreach t in array array['settings','projects','sources','claims','scripts','assets','scenes',
                           'voiceovers','renders','jobs','step_definitions','job_steps',
                           'error_logs','usage_metrics'] loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

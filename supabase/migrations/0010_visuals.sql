-- Stage 5: görsel arşiv ve sahne yönetimi
alter table assets add column if not exists scene_id uuid references scenes(id) on delete cascade;
alter table assets add column if not exists source text;            -- commons | met | openverse | smithsonian | upload
alter table assets add column if not exists title text;
alter table assets add column if not exists thumb_url text;
alter table assets add column if not exists license_class text;     -- pd | cc0 | by | by-sa | nc | nd | unknown
alter table assets add column if not exists score numeric(6,3);
alter table assets add column if not exists query text;
alter table assets add column if not exists width int;
alter table assets add column if not exists height int;
create index if not exists assets_scene_idx on assets (scene_id);

alter table scenes add column if not exists visual_queries text[];

-- Kullanıcı görsel onayı (render öncesi)
insert into step_definitions (step_key, seq, label, requires_input, stage)
values ('visual_review', 115, 'Görsel onayı (kullanıcı)', true, 5)
on conflict (step_key) do update set seq = excluded.seq, label = excluded.label, requires_input = true, stage = 5;

insert into job_steps (job_id, project_id, step_key, seq, max_attempts, status)
select j.id, j.project_id, 'visual_review', 115, 3, 'pending'
  from jobs j
 where not exists (select 1 from job_steps s where s.job_id = j.id and s.step_key = 'visual_review');

-- Kullanıcı kararı (Pompei): Shorts sesi 60 sn'yi aşarsa render sırasında hızlandır (en fazla %15)
insert into settings (key, value) values
  ('shorts_max_seconds', '60'::jsonb),
  ('shorts_auto_tempo_max', '1.15'::jsonb)
on conflict (key) do nothing;

do $$
declare r record;
begin
  for r in select id from jobs where status not in ('done','cancelled') loop
    perform refresh_job_status(r.id);
  end loop;
end $$;

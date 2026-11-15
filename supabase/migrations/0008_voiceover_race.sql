-- Düzeltme: sesler "seslendirme bekleniyor" adımı açılmadan ÖNCE yüklendiyse adım sonsuza dek bekliyordu.
-- Artık bekleme adımı açılırken iki ses de zaten yüklüyse adım hemen tamamlanır.
create or replace function input_already_satisfied(p_step_key text, p_project uuid) returns boolean
language sql stable as $$
  select case p_step_key
    when 'voiceover_wait' then (select count(distinct kind) from voiceovers
                                 where project_id = p_project and status in ('uploaded','analyzing','analyzed')) = 2
    else false end;
$$;

create or replace function refresh_job_status(p_job uuid) returns void
language plpgsql as $$
declare
  v_next record;
  v_status text;
  v_project uuid;
begin
  select project_id into v_project from jobs where id = p_job;

  loop
    select s.* into v_next from job_steps s
     where s.job_id = p_job and s.status not in ('done','skipped')
     order by s.seq limit 1;
    exit when v_next.id is null
           or v_next.status not in ('pending','waiting_input')
           or not exists (select 1 from step_definitions d where d.step_key = v_next.step_key and d.requires_input);
    if input_already_satisfied(v_next.step_key, v_project) then
      update job_steps set status = 'done', finished_at = now(),
             output = jsonb_build_object('released_by', 'already_satisfied')
       where id = v_next.id;
      continue;
    end if;
    if v_next.status = 'pending' then
      update job_steps set status = 'waiting_input' where id = v_next.id;
      v_next.status := 'waiting_input';
    end if;
    exit;
  end loop;

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

-- Takılı kalmış işleri hemen düzelt
do $$
declare r record;
begin
  for r in select id from jobs where status not in ('done','cancelled') loop
    perform refresh_job_status(r.id);
  end loop;
end $$;

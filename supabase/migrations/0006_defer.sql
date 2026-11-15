-- LLM kotası dolduğunda adım başarısız sayılmaz: deneme hakkı iade edilir, adım beklemeye döner.
create or replace function defer_step(p_step uuid, p_worker text, p_reason text) returns boolean
language plpgsql as $$
declare v_job uuid;
begin
  update job_steps set status = 'pending', attempts = greatest(attempts - 1, 0), worker_id = null,
         heartbeat_at = null, error = p_reason
   where id = p_step and worker_id = p_worker and status = 'running'
  returning job_id into v_job;
  if v_job is null then return false; end if;
  insert into error_logs (project_id, job_id, step_key, level, message)
    select project_id, job_id, step_key, 'warning', p_reason from job_steps where id = p_step;
  perform refresh_job_status(v_job);
  return true;
end $$;

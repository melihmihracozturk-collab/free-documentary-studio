-- Bir adımı ve sonraki tüm adımları yeniden çalıştırmak için (ör. araştırmayı iyileştirilmiş kodla tekrar yapmak).
create or replace function reset_from_step(p_job uuid, p_step_key text) returns int
language plpgsql as $$
declare v_seq int; v_count int;
begin
  select seq into v_seq from job_steps where job_id = p_job and step_key = p_step_key;
  if v_seq is null then raise exception 'Adım bulunamadı: %', p_step_key; end if;
  if exists (select 1 from job_steps where job_id = p_job and seq >= v_seq and status = 'running') then
    raise exception 'Çalışan bir adım var; bitmesini bekleyin';
  end if;
  update job_steps set status = 'pending', attempts = 0, output = null, output_key = null, sha256 = null,
         error = null, worker_id = null, heartbeat_at = null, started_at = null, finished_at = null
   where job_id = p_job and seq >= v_seq and status <> 'pending';
  get diagnostics v_count = row_count;
  update jobs set status = 'running', finished_at = null where id = p_job and status <> 'cancelled';
  perform refresh_job_status(p_job);
  return v_count;
end $$;

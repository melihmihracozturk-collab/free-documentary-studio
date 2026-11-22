-- Öneri biçimi (Ayla) yalnızca ~1 dakikalık Shorts üretir: uzun videonun senaryo ve render adımları atlanır,
-- seslendirme beklemesi yalnızca Shorts sesini bekler. Belgesel ve vlog projeleri etkilenmez.

-- 1) Uzun videoya ait adımlar öneri projelerinde beklemeye düştüğü anda "atlandı" olur
--    (iş oluşturma, "Yeniden başlat" ve reset_from_step dahil; böylece adım hiç takılı kalmaz).
create or replace function skip_doc_steps_for_review() returns trigger
language plpgsql as $$
begin
  if new.status = 'pending' and new.step_key in ('script_doc', 'render_doc')
     and exists (select 1 from projects p where p.id = new.project_id and p.format = 'review') then
    new.status := 'skipped';
    new.output := jsonb_build_object('skipped', 'Öneri biçimi yalnızca Shorts üretir');
    new.finished_at := now();
  end if;
  return new;
end $$;

drop trigger if exists job_steps_skip_doc_for_review on job_steps;
create trigger job_steps_skip_doc_for_review before insert or update on job_steps
  for each row execute function skip_doc_steps_for_review();

-- 2) Seslendirme beklemesi: öneri projelerinde yalnızca Shorts sesi yeterli
create or replace function input_already_satisfied(p_step_key text, p_project uuid) returns boolean
language sql stable as $$
  select case p_step_key
    when 'voiceover_wait' then
      case when (select format from projects where id = p_project) = 'review'
           then exists (select 1 from voiceovers where project_id = p_project and kind = 'shorts'
                          and status in ('uploaded','analyzing','analyzed'))
           else (select count(distinct kind) from voiceovers
                  where project_id = p_project and status in ('uploaded','analyzing','analyzed')) = 2 end
    else false end;
$$;

-- 3) Öneri projelerinde Shorts hedefi ~1 dakika
update projects set shorts_seconds = 58 where format = 'review' and shorts_seconds < 58;

-- 4) Hâlihazırda açılmış öneri işleri: bekleyen uzun video adımlarını atla, iş durumunu tazele
update job_steps s set status = 'pending'
  from projects p
 where p.id = s.project_id and p.format = 'review' and s.step_key in ('script_doc', 'render_doc') and s.status = 'pending';

do $$
declare r record;
begin
  for r in select j.id from jobs j join projects p on p.id = j.project_id
            where p.format = 'review' and j.status not in ('done','cancelled') loop
    perform refresh_job_status(r.id);
  end loop;
end $$;

-- Stage 4: senaryo onayı, seslendirme yükleme ve analiz

-- 1) Adım sırası: görsel plan (Stage 5) seslendirmenin önünü tıkamasın; senaryo onayı eklensin.
--    seq benzersiz olduğundan önce geçici değerlere taşınır.
update step_definitions set seq = seq + 1000;
insert into step_definitions (step_key, seq, label, requires_input, stage)
values ('script_review', 1065, 'Senaryo onayı (kullanıcı)', true, 4)
on conflict (step_key) do nothing;

update step_definitions d set seq = v.seq, label = v.label
  from (values
    ('research_collect', 10, 'Konuyu araştır'),
    ('research_verify', 20, 'Kaynakları doğrula'),
    ('research_report', 30, 'Araştırma raporu oluştur'),
    ('research_review', 40, 'Araştırma onayı (kullanıcı)'),
    ('script_doc', 50, 'Belgesel senaryosu yaz'),
    ('script_shorts', 60, 'Shorts senaryosu yaz'),
    ('script_review', 65, 'Senaryo onayı (kullanıcı)'),
    ('voiceover_texts', 70, 'ElevenLabs metinlerini hazırla'),
    ('voiceover_wait', 80, 'Seslendirme dosyalarını bekle'),
    ('voiceover_analyze', 90, 'Sesleri analiz et'),
    ('visual_plan', 100, 'Sahne sahne görsel plan'),
    ('asset_match', 110, 'Görselleri seslendirmeyle eşleştir'),
    ('subtitles', 120, 'Altyazıları oluştur'),
    ('render_doc', 130, 'Ana belgeseli render et'),
    ('render_shorts', 140, 'Shorts videosunu render et'),
    ('preview_ready', 150, 'Önizlemeye sun ve indirmeye hazırla')
  ) as v(step_key, seq, label)
 where d.step_key = v.step_key;

-- Mevcut işlerin adım sıralarını güncelle ve eksik "senaryo onayı" adımını ekle.
update job_steps s set seq = d.seq from step_definitions d where d.step_key = s.step_key and s.seq <> d.seq;
insert into job_steps (job_id, project_id, step_key, seq, max_attempts, status)
select j.id, j.project_id, 'script_review', 65, 3,
       -- Senaryosu zaten yazılmış ve sonrası başlamamış işlerde onay beklensin
       'pending'
  from jobs j
 where not exists (select 1 from job_steps s where s.job_id = j.id and s.step_key = 'script_review');

do $$
declare r record;
begin
  for r in select id from jobs where status not in ('done','cancelled') loop
    perform refresh_job_status(r.id);
  end loop;
end $$;

-- 2) Düzenleme izi (uyarılar panelde canlı hesaplanır)

alter table scenes add column if not exists edited_at timestamptz;
alter table scripts add column if not exists approved_at timestamptz;

-- 3) Seslendirme analizi
alter table voiceovers add column if not exists words_key text;          -- R2: kelime zamanları (JSON)
alter table voiceovers add column if not exists coverage numeric(5,3);   -- senaryo ile eşleşen kelime oranı
alter table voiceovers add column if not exists uploaded_at timestamptz not null default now();

insert into settings (key, value) values
  ('voiceover_max_mb', '200'::jsonb),
  ('whisper_model', '"small"'::jsonb)
on conflict (key) do nothing;

-- 4) Yeni ses yüklenince (aynı tür yeniden yüklenirse) analiz yeniden yapılmalı
create or replace function reset_voiceover_analysis() returns trigger
language plpgsql as $$
begin
  if tg_op = 'UPDATE' and new.storage_key is distinct from old.storage_key then
    new.status := 'uploaded';
    new.analysis := null;
    new.duration_sec := null;
    new.coverage := null;
    new.words_key := null;
  end if;
  return new;
end $$;

drop trigger if exists voiceovers_reset on voiceovers;
create trigger voiceovers_reset before update on voiceovers
  for each row execute function reset_voiceover_analysis();

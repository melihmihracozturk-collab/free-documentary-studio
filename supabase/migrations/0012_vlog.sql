-- Vlog biçimi: gezi vlogu (birinci ağızdan, durak durak, pratik ipuçlarıyla). Görüntü/ses/render hattı belgeselle ortak.
alter table projects add column if not exists format text not null default 'documentary';
do $$ begin
  alter table projects add constraint projects_format_check check (format in ('documentary', 'vlog'));
exception when duplicate_object then null; end $$;

-- Fiyat, saat, ulaşım gibi değişebilen pratik bilgi içeren sahne: yayından önce kullanıcı kontrol etmeli
alter table scenes add column if not exists needs_check boolean not null default false;

-- Wikivoyage gibi gezi rehberleri için kaynak türü
alter table sources drop constraint if exists sources_source_type_check;
alter table sources add constraint sources_source_type_check
  check (source_type in ('archive','academic','official','encyclopedia','museum','news','web','guide'));

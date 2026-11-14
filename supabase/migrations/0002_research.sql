-- Stage 3: araştırma ve senaryo motoru

-- Kaynak metin parçaları (iddiaların alıntılarla doğrulanması için saklanır).
create table if not exists source_excerpts (
  id          uuid primary key default gen_random_uuid(),
  source_id   uuid not null references sources(id) on delete cascade,
  project_id  uuid not null references projects(id) on delete cascade,
  lang        text,
  text        text not null
);
create index if not exists source_excerpts_project_idx on source_excerpts (project_id);

alter table sources add column if not exists ref text;              -- S1, S2 … (LLM'e verilen kısa kimlik)
alter table sources add column if not exists collector text;        -- wikipedia, crossref, openalex, loc, archive …
alter table sources add column if not exists published text;        -- yıl / tarih (biliniyorsa)

alter table claims add column if not exists ref text;               -- C1, C2 …
alter table claims add column if not exists category text;          -- zaman, kişi, mekân, sayı, neden, sonuç
alter table claims add column if not exists importance int not null default 2 check (importance between 1 and 3);
alter table claims add column if not exists event_date text;        -- zaman çizelgesi için (serbest metin)
alter table claims add column if not exists support jsonb not null default '[]';  -- [{source_ref, quote, verified_quote}]
alter table claims add column if not exists independent_sources int not null default 0;

create table if not exists research_reports (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references projects(id) on delete cascade,
  version     int not null default 1,
  summary     text,
  markdown    text not null,
  stats       jsonb not null default '{}',
  created_at  timestamptz not null default now(),
  unique (project_id, version)
);

-- LLM yanıt önbelleği: aynı istek iki kez gönderilmez (ücretsiz kotayı korur, yeniden çalıştırmayı ucuzlatır).
create table if not exists llm_cache (
  key         text primary key,
  provider    text not null,
  model       text not null,
  response    jsonb not null,
  created_at  timestamptz not null default now()
);

alter table scenes add column if not exists act text;                -- giris, arka_plan, gelisme, donum_noktasi, sonuclar, kapanis
alter table scenes add column if not exists search_keywords text[] not null default '{}';
alter table scenes add column if not exists claim_refs text[] not null default '{}';
alter table scenes add column if not exists on_screen_text text;
alter table scenes add column if not exists word_count int;

alter table scripts add column if not exists word_count int;
alter table scripts add column if not exists est_seconds numeric(8,2);
alter table scripts add column if not exists validation jsonb not null default '{}';

insert into settings (key, value) values
  ('narration_wpm', '135'::jsonb),          -- Türkçe anlatım hızı (kelime/dk), seslendirme sonrası gerçek süre ölçülür
  ('shorts_wpm', '155'::jsonb)
on conflict (key) do nothing;

alter table source_excerpts enable row level security;
alter table research_reports enable row level security;
alter table llm_cache enable row level security;

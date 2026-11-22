-- Öneri biçimi: kodla çizilmiş kadın sunucunun anlattığı anime / dizi / film öneri videoları.
-- Araştırma: AniList + TMDB (anahtar varsa) + Vikipedi. Görüntü: resmî afiş + kodla üretilen hareketli grafikler.
-- Ses: ücretsiz otomatik seslendirme (Edge TTS, yedek Gemini TTS); dudak senkronu sese göre yapılır.
alter table projects drop constraint if exists projects_format_check;
alter table projects add constraint projects_format_check check (format in ('documentary', 'vlog', 'review'));

-- Katalog kaynakları (AniList, TMDB): yapım bilgisi, tür, bölüm sayısı, puan, konu özeti
alter table sources drop constraint if exists sources_source_type_check;
alter table sources add constraint sources_source_type_check
  check (source_type in ('archive','academic','official','encyclopedia','museum','news','web','guide','catalog'));

-- Sahne düzeni: host (sunucu büyük), title (afiş + bilgi kartı), poster (afiş), mood (renk paleti animasyonu),
-- full (sunucu gizli, afiş tam ekran). title_ref: sahnenin anlattığı yapım (oneri_1, oneri_2, ...)
alter table scenes add column if not exists layout text;
alter table scenes add column if not exists title_ref text;

insert into settings (key, value) values
  ('presenter_name', '"Ayla"'::jsonb),
  ('tts_provider', '"edge"'::jsonb),                 -- edge | gemini
  ('tts_voice', '"tr-TR-EmelNeural"'::jsonb),        -- Edge TTS Türkçe kadın sesi
  ('tts_rate', '"+4%"'::jsonb),
  ('gemini_tts_voice', '"Leda"'::jsonb)
on conflict (key) do nothing;

-- Türkçe anlatım hızı: kelimeler uzun olduğu için dakikada ~125 kelime (gerçek süre seslendirmeden ölçülür).
update settings set value = '125'::jsonb, updated_at = now() where key = 'narration_wpm' and value = '135'::jsonb;
update settings set value = '145'::jsonb, updated_at = now() where key = 'shorts_wpm' and value = '155'::jsonb;

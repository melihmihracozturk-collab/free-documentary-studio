-- Gerçek ölçüme göre kalibrasyon (Pompei, ElevenLabs Türkçe): belgesel 103 kelime/dk, Shorts 89 kelime/dk.
-- Senaryo kelime bütçesi bu hızlarla hesaplanır; böylece hedef süre gerçek sese daha yakın çıkar.
update settings set value = '105'::jsonb, updated_at = now() where key = 'narration_wpm' and value = '125'::jsonb;
update settings set value = '110'::jsonb, updated_at = now() where key = 'shorts_wpm' and value = '145'::jsonb;

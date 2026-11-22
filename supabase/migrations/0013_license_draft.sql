-- Taslak modu: telifli görseller de önerilir (kırmızı işaretli; yayından önce kullanıcı değiştirir). Varsayılan kapalı.
insert into settings (key, value) values ('license_allow_restricted', 'false'::jsonb) on conflict (key) do nothing;

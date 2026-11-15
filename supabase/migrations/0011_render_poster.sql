-- Render kontrol görseli (9 kare) ve ara kliplerin silinmesiyle depolama takibi
alter table renders add column if not exists poster_key text;

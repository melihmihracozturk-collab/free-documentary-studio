-- Bağımsız kaynak sayımı için anahtar (wikipedia / book:<kitap> / work:<doi> / pub:<kurum>)
alter table sources add column if not exists independence_key text;

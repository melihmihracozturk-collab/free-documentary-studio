# Free Documentary Studio

Tek bir konu girişiyle 8–15 dakikalık belgesel ve 45–60 saniyelik YouTube Shorts üreten, tamamen web tabanlı stüdyo.
Bilgisayarınıza hiçbir şey kurulmaz: panel Vercel'de, veriler Supabase'de, medya Cloudflare R2'de, ağır işler GitHub Actions'ta çalışır.

Mimari ve servis seçimleri: [`docs/STAGE1_MIMARI_RAPORU.md`](docs/STAGE1_MIMARI_RAPORU.md)

## Durum

| Stage | Kapsam | Durum |
|---|---|---|
| 1 | Mimari ve ücretsiz servis araştırması | ✅ |
| 2 | Panel, veritabanı şeması, iş kuyruğu, bulut işçisi iskeleti | ✅ |
| 3 | Araştırma ve senaryo motoru | ✅ (gerçek LLM ile henüz çalıştırılmadı) |
| 4 | Senaryo onayı, ElevenLabs metinleri, ses yükleme (R2) ve analiz (faster-whisper) | ✅ (Pompei ile gerçek veride doğrulandı) |
| 5 | Görsel arşiv ve sahne yönetimi (Commons, Met, Openverse, Smithsonian; lisans filtresi; credits.txt) | ✅ |
| 6 | Bulut video montaj motoru: altyazı, Ken Burns, geçişler, ambiyans, ses seviyesi (FFmpeg) | ✅ |
| 7 | Shorts motoru | ⏳ |
| 8 | Teslim paketi (YouTube açıklaması, bölümler, kaynaklar), Dashboard kullanımı, iyileştirmeler | ✅ |

## Yapı

```
src/app/(studio)/      Panel sayfaları (Dashboard, Yeni Belgesel, … Ayarlar)
src/app/actions.ts     Sunucu eylemleri (proje oluşturma, onay, yeniden deneme, ayarlar, giriş)
src/lib/               Veritabanı, giriş, GitHub tetikleme
src/proxy.ts           Giriş koruması
supabase/migrations/   Veritabanı şeması + iş kuyruğu fonksiyonları + render kuralları
worker/                GitHub Actions'ta çalışan Python işçisi
.github/workflows/     worker (cron + tetikleme), migrate, ci
```

## İş kuyruğu nasıl çalışır?

1. Panelde proje oluşturulunca veritabanına 15 adımlık bir iş yazılır.
2. GitHub Actions işçisi (panelden anında ya da 15 dakikada bir) sıradaki adımı **kilitleyerek** alır, çalıştırır, sonucu yazar.
3. Uzun adımlarda 30 saniyede bir kalp atışı gönderilir. Atış 10 dakika kesilirse adım yeniden kuyruğa alınır (kaldığı yerden devam).
4. Hatalı adım 3 kez otomatik denenir, sonra "Hata" olur. Panelden "Yeniden dene" ile sürdürülür.
5. Kullanıcı adımları: **araştırma onayı** ve **seslendirme yükleme**. İki ses dosyası yüklenince süreç kendiliğinden devam eder.
6. Veritabanı kuralları:
   - Analiz edilmiş gerçek seslendirme yoksa render adımı **başlatılamaz**.
   - Depolama koruma eşiği (varsayılan 8 GB) aşıldıysa yeni render **başlatılamaz**.

## Araştırma ve senaryo motoru

1. **Toplama:** LLM bir araştırma planı çıkarır. Wikipedia (en + Türkçe), Crossref, OpenAlex, Library of Congress, Internet Archive ve Europeana'dan metin toplanır. Kayıtlar tekilleştirilir, alakasızlar elenir, toplam metin ~110 bin karakterle sınırlanır.
2. **Doğrulama:** LLM her iddiayı kaynaktan **birebir alıntıyla** çıkarır. Kod, alıntının kaynak metninde gerçekten geçip geçmediğini kontrol eder; geçmeyen iddia atılır. Eşdeğer iddialar birleştirilir. ≥2 bağımsız yayıncı = *doğrulandı*, 1 = *tek kaynak*. Kaynaklar çelişiyorsa *çelişkili* olarak işaretlenir ve nedeni yazılır.
3. **Rapor:** özet, doğrulama durumu, çelişkiler ve kaynak listesi (Markdown, panelden indirilebilir). Ardından kullanıcı onayı beklenir.
4. **Senaryo:** 6 bölüm (giriş, arka plan, gelişme, dönüm noktası, sonuçlar, kapanış), her sahnede seslendirme, görsel, arama kelimeleri, kamera, geçiş, müzik, efekt ve iddia kimlikleri. Kelime bütçesi = süre × 135 kelime/dk (±%12). Kod yapıyı kontrol eder, hata varsa LLM'e en fazla 2 kez düzelttirir.
5. **Shorts:** bağımsız 45–60 sn senaryo; ilk sahne ≤10 kelimelik kanca.

LLM yanıtları veritabanında önbelleğe alınır; bir adımı yeniden çalıştırmak kotayı tekrar harcamaz.

## Seslendirme (Stage 4)

1. **Senaryo onayı:** Senaryo sayfasında sahneler düzenlenir. Kod iki tür uyarıyı canlı gösterir: kaynakta olmayan sayılar (Türkçe yazıyla sayılar dahil) ve tekrarlanan bilgiler. Kaynakta olmayan *ayrıntıları* kod yakalayamaz; son okuma kullanıcınındır.
2. **ElevenLabs metinleri:** `documentary_voiceover.txt` ve `shorts_voiceover.txt` yalnızca okunacak cümlelerden oluşur, sahneler arasında boş satır vardır.
3. **Yükleme:** Tarayıcı dosyanın SHA-256 özetini hesaplar, dosyayı imzalı URL ile doğrudan Cloudflare R2'ye yükler. Sunucu boyutu doğrular.
4. **Analiz (bulut işçisi):** ffprobe ile süre, silencedetect ile duraklamalar, faster-whisper ile kelime zamanları ölçülür. Senaryo ile hizalanarak her sahnenin gerçek başlangıç ve bitiş zamanı çıkarılır. Ses ile metin %60'tan az eşleşirse ya da süre hedef dışındaysa uyarı verilir.

## Görsel arşiv (Stage 5)

1. **Görsel plan:** her sahnenin İngilizce arama ifadelerine konunun adı eklenir (LLM kullanılmaz).
2. **Arama:** Met Museum Open Access (CC0), Wikimedia Commons, Smithsonian (anahtar varsa); yetersizse Openverse.
3. **Lisans filtresi (kodla):** kamu malı, CC0, CC BY, CC BY-SA kabul; NC varsayılan kapalı; ND ve belirsiz lisans her zaman ret.
4. **Puanlama:** konuyla ilgi, çözünürlük (Shorts için dikey kırpmaya uygunluk), kaynak ve lisans tercihi; aynı görsel bir videoda iki kez kullanılmaz.
5. **Panel:** her sahnede seçili görsel + alternatifler; değiştirilebilir; `credits.txt` indirilebilir; kullanıcı onayı.
6. Seçilen görseller en fazla 2560 px JPEG olarak R2'ye indirilir; SHA-256 kaydedilir.

## Render (Stage 6)

- **Altyazı:** whisper kelime zamanları ile senaryonun doğru yazımı hizalanır → SRT (indirilebilir) + ASS (videoya gömülü); ekran yazıları sol üstte.
- **Sahne klipleri:** her görsel kendi sahnesinin gerçek ses süresi boyunca Ken Burns hareketiyle (zoompan, 3x iç çözünürlük → titreme yok). Klipler R2'de saklanır; render kesilirse yalnızca eksikler üretilir.
- **Birleştirme:** geçişler sahne sınırının ortasına yerleşir; renk düzenleme, vinyet, film greni.
- **Ses:** seslendirme + FFmpeg ile üretilen telifsiz ambiyans (konuşmada otomatik kısılır), -14 LUFS.
- **Çıktı:** 1920x1080, 25 fps, H.264/AAC MP4; süre ve boyut kontrol edilir, SHA-256 kaydedilir.
- Not: "parallax" bu sürümde yavaş yakınlaşma + kaydırmadır (gerçek derinlik ayrıştırması yok).

## Kurulum (tamamı tarayıcıdan)

1. **Supabase:** Yeni proje → Project Settings → Database → *Transaction pooler* bağlantı adresini kopyalayın.
2. **GitHub Secrets** (repo → Settings → Secrets and variables → Actions):
   - `DATABASE_URL` (zorunlu)
   - `GEMINI_API_KEY` (araştırma/senaryo için; Google AI Studio'dan ücretsiz)
   - opsiyonel: `GROQ_API_KEY`, `OPENROUTER_API_KEY` (+ `OPENROUTER_MODEL` değişkeni, `:free` model), `OPENALEX_API_KEY`, `EUROPEANA_API_KEY`
3. **Şema:** repo → Actions → *migrate* → *Run workflow*.
4. **Vercel:** GitHub ile giriş → bu repoyu içe aktarın → ortam değişkenleri: `.env.example` dosyasındakiler.
5. Panel adresine girin, `ADMIN_PASSWORD` ile giriş yapın.

## Testler

- `worker/tests`: veritabanı kuralları, işçi, araştırma ve senaryo motoru (12 test). LLM ve ağ taklit edilir. CI'da Postgres servisiyle çalışır.
- `npm run lint`, `npm run typecheck`, `npm run build`.

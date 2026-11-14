# Free Documentary Studio

Tek bir konu girişiyle 8–15 dakikalık belgesel ve 45–60 saniyelik YouTube Shorts üreten, tamamen web tabanlı stüdyo.
Bilgisayarınıza hiçbir şey kurulmaz: panel Vercel'de, veriler Supabase'de, medya Cloudflare R2'de, ağır işler GitHub Actions'ta çalışır.

Mimari ve servis seçimleri: [`docs/STAGE1_MIMARI_RAPORU.md`](docs/STAGE1_MIMARI_RAPORU.md)

## Durum

| Stage | Kapsam | Durum |
|---|---|---|
| 1 | Mimari ve ücretsiz servis araştırması | ✅ |
| 2 | Panel, veritabanı şeması, iş kuyruğu, bulut işçisi iskeleti | ✅ |
| 3 | Araştırma ve senaryo motoru | ⏳ |
| 4 | Seslendirme yükleme ve analiz (R2) | ⏳ |
| 5 | Görsel arşiv ve sahne yönetimi | ⏳ |
| 6 | Bulut video montaj motoru (FFmpeg) | ⏳ |
| 7 | Shorts motoru | ⏳ |
| 8 | Entegrasyon, test, optimizasyon | ⏳ |

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

## Kurulum (tamamı tarayıcıdan)

1. **Supabase:** Yeni proje → Project Settings → Database → *Transaction pooler* bağlantı adresini kopyalayın.
2. **GitHub Secrets** (repo → Settings → Secrets and variables → Actions): `DATABASE_URL`.
3. **Şema:** repo → Actions → *migrate* → *Run workflow*.
4. **Vercel:** GitHub ile giriş → bu repoyu içe aktarın → ortam değişkenleri: `.env.example` dosyasındakiler.
5. Panel adresine girin, `ADMIN_PASSWORD` ile giriş yapın.

## Testler

- `worker/tests`: veritabanı kuralları ve işçi (7 test). CI'da Postgres servisiyle çalışır.
- `npm run lint`, `npm run typecheck`, `npm run build`.

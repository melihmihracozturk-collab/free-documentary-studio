# FREE DOCUMENTARY STUDIO — STAGE 1: Mimari ve Servis Seçim Raporu

Tarih: 14 Kasım 2026 · Durum: **Onay bekliyor. Bu aşamada uygulama kodu yazılmadı.**

---

## 0. Özet

| Katman | Seçim | Neden | Yedek |
|---|---|---|---|
| Web arayüzü (Next.js) | **Vercel Hobby** | Next.js için en sorunsuz yer, kart istemez, fonksiyon başına 300 sn | Cloudflare Workers + OpenNext, Netlify Free |
| Veritabanı + Auth + küçük dosyalar | **Supabase Free** | Postgres, Auth, Realtime (canlı render durumu), Storage tek pakette | Neon (DB) + Auth.js |
| Büyük medya (ses, görsel, render) | **Cloudflare R2** (10 GB ücretsiz, çıkış trafiği ücretsiz) | Videoyu izlemek ve indirmek için trafik ücreti yok | Backblaze B2 (10 GB) veya GitHub Releases (kart gerekmez) |
| Render ve uzun işler | **GitHub Actions** (FFmpeg + Python) | Public repoda standart runner ücretsiz: 4 vCPU / 16 GB RAM. Tarayıcı kapansa da iş devam eder | Private repo (~2.000 dk/ay, 2 vCPU), Hugging Face Space (CPU Basic) |
| Araştırma ve senaryo (LLM) | **Gemini API Free (Flash)** | Kotası en geniş ücretsiz LLM, uzun bağlam | Groq Free, OpenRouter `:free` modelleri |
| Görsel arşivler | Wikimedia Commons, Openverse, Internet Archive, Europeana, Library of Congress, Met Museum Open Access, Smithsonian Open Access | Hepsi ücretsiz API sunuyor ve lisans bilgisi veriyor | Pexels (temsili modern görüntü) |
| Akademik doğrulama | OpenAlex, Crossref, Wikidata | Ücretsiz, anahtar gerektirmiyor | Semantic Scholar |
| Temsili yapay zekâ görseli | Cloudflare Workers AI (günde 10.000 neuron) | Ücretsiz, limit aşılınca **hata verir, ücret almaz** (Free planda) | Yalnızca arşiv görseli + 2D grafik |
| Ses analizi ve altyazı | FFmpeg `silencedetect` + **faster-whisper** (açık kaynak, CPU üzerinde) | Kelime düzeyinde zaman damgası, API ücreti yok | `aeneas` ile zorunlu hizalama (forced alignment) |
| Müzik ve efekt | Freesound API (CC0/CC-BY filtresiyle), Incompetech/FMA (CC-BY), kullanıcının yüklediği parçalar | Lisanslar kayıt altında tutulur | Sessiz ambiyans ve FFmpeg ile üretilen tonlar |

Blender, yerel FFmpeg, yerel Python ya da Windows'a dosya yazmak **hiçbir yerde yok**. Tarayıcı yalnızca arayüz, ses yükleme ve video indirme için kullanılıyor.

---

## 1. Ücretsiz katmanların doğrulanmış durumu (Kasım 2026)

Bu rakamlar resmî dokümanlardan ve güncel kaynaklardan derlendi. Bazı sağlayıcılar kesin sayı yayımlamıyor; bu durumlar **"doğrulanmadı"** diye işaretlendi. Uygulama bu limitleri sabit kodlamayacak, kullanımı kendisi ölçecek.

### GitHub Actions (render motoru) — DOĞRULANDI (resmî doküman)
- Public repoda standart GitHub-hosted runner kullanımı **ücretsiz** ve kotadan düşmüyor.
- Runner: public repoda **4 vCPU / 16 GB RAM / 14 GB SSD**, private repoda 2 vCPU / 8 GB.
- Private repo, Free planda aylık **12 $ değerinde** işlem süresi içeriyor (≈2.000 dk Linux 2-core).
- 2026 değişiklikleri: hosted runner fiyatları düştü. Self-hosted runner ücretiyle ilgili kaynaklar çelişkili, ama **bizi etkilemiyor** çünkü self-hosted kullanmıyoruz.
- Dikkat: job süresi sınırı (bilinen değer 6 saat) bu kez dokümanda teyit edilemedi. Mimari zaten her sahneyi ayrı parça olarak render ediyor, bu yüzden tek bir job uzun sürmüyor.
- Dikkat: public repoda 60 gün commit olmazsa zamanlanmış (cron) iş akışları devre dışı kalır. Dashboard bunun için uyarı gösterecek.

### Supabase Free — çoğu kaynak tutarlı, resmî sayfadan bir kez daha teyit edilecek
- 500 MB Postgres, **1 GB dosya deposu**, dosya başına ~50 MB yükleme sınırı, ~5 GB çıkış trafiği, en fazla 2 aktif proje.
- **7 gün hareketsiz kalan proje duraklatılır.** Çözüm: GitHub Actions cron işi günde bir kez hafif bir sorgu atacak. Dashboard'da da uyarı olacak.
- Sonuç: 12 dakikalık 1080p bir MP4 yaklaşık 300–500 MB ve WAV seslendirme ~120 MB tutuyor, yani **video ve büyük ses dosyası Supabase'e sığmaz.** Supabase yalnızca veri, metin ve küçük dosyalar için kullanılacak.

### Cloudflare R2 — DOĞRULANDI (resmî fiyat sayfası)
- Aylık 10 GB-ay depolama, 1M Class A ve 10M Class B işlem, **internete çıkış trafiği ücretsiz**.
- ⚠️ **Risk:** Bucket açmak için hesaba ödeme yöntemi eklemek gerekebilir (kaynaklar çelişkili). Kart ekliyse limit aşıldığında **otomatik ücret** kesilebilir. Cloudflare'de R2 için sert bir harcama tavanı yok.
- Önlem: Uygulama, **8 GB'ta yeni render'ı durduran** kendi kota korumasını uygulayacak, eski render'ları arşivlemenizi ya da silmenizi isteyecek. Kullanım her zaman Dashboard'da görünecek.

### Vercel Hobby — DOĞRULANDI (resmî doküman)
- Fonksiyon başına en fazla 300 sn. **Yalnızca kişisel ve ticari olmayan kullanım.**
- ⚠️ YouTube kanalınız para kazanıyorsa (monetize) bu kural ihlal sayılabilir. O durumda arayüz **Cloudflare Workers (OpenNext)** veya Netlify'a taşınır. Kod Vercel'e özgü API kullanmayacak, taşımak bir yapılandırma işi olacak.

### Gemini API Free — limitler değişken, doğrulanamadı
- Free tier sürüyor, ama Aralık 2025'te kotalar ciddi biçimde düşürüldü. Google artık model başına RPM/RPD sayılarını sabit olarak yayımlamıyor, değerler AI Studio'da görünüyor.
- ⚠️ Free tier'da gönderilen veriler **Google ürünlerini geliştirmek için kullanılabilir.** Belgesel araştırması için sorun değil, ama kişisel veri gönderilmeyecek.
- Önlem: Bir LLM sağlayıcı katmanı kurulacak: Gemini → Groq → OpenRouter `:free`. 429 hatasında sıradaki sağlayıcıya geçilecek. Tüm istekler önbelleğe alınacak, aynı soru iki kez sorulmayacak.

### Groq Free — süre sınırı yok, limitler model başına
- Örnek tablo: dakikada ~30 istek, günde ~1.000 istek, günde ~200K token (kuruluş başına). Kaynaklar çelişkili, kesin değerler konsoldan okunacak.

### Cloudflare Workers AI — DOĞRULANDI
- **Günde 10.000 neuron ücretsiz.** Free Workers planında limit aşılınca istek hata verir, ücret alınmaz.
- FLUX modelleri megapiksel başına ~1.300+ neuron harcıyor, yani günde **yaklaşık 5–7 görsel**. Bu yüzden yapay zekâ görseli yalnızca arşivde karşılığı olmayan sahnelerde kullanılacak ve ekranda "temsili görsel" etiketiyle gösterilecek.

### Hugging Face Spaces CPU Basic — DOĞRULANDI
- 2 vCPU / 16 GB / ücretsiz. 48 saat hareketsiz kalırsa uyur, uyku süresi ayarlanamaz. Yalnızca yedek render ortamı olarak düşünülüyor.

### Openverse
- Anonim erişimde sorgu başına en fazla ~240 sonuç, kayıtlı token ile limit biraz artıyor. Yanıtta `license`, `license_url` ve `attribution` alanları var.

---

## 2. Sistem mimarisi

```
┌────────────────────────── TARAYICI (yalnızca arayüz) ──────────────────────────┐
│ Next.js + React + TS + Tailwind  →  Dashboard / Yeni Belgesel / Render Merkezi  │
│ Ses yükleme: doğrudan R2'ye (imzalı URL)   •  Önizleme ve indirme: R2'den        │
└───────────────┬─────────────────────────────────────────────▲──────────────────┘
                │ API route'ları (Vercel, en fazla 300 sn)      │ Supabase Realtime
                ▼                                               │ (canlı ilerleme)
┌──────────── SUPABASE (Postgres + Auth) ────────────┐          │
│ projects, sources, claims, scripts, scenes, assets, │──────────┘
│ voiceovers, renders, jobs, job_steps, usage, errors │
└───────────────┬────────────────────────────────────┘
                │ iş kaydı (status = queued)
                ▼
┌──────────── GITHUB ACTIONS (bulut işçi) ───────────────────────────────────────┐
│ workflow_dispatch (anında) + cron her 15 dk (takılan ve yarım kalan işler)     │
│  ├─ research.py   : arşiv/akademik API'ler + LLM → iddia/kaynak tablosu        │
│  ├─ script.py     : belgesel + shorts senaryosu, sahne planı, VO metinleri     │
│  ├─ assets.py     : görsel arama, lisans filtresi, indirme, parallax katmanları│
│  ├─ audio.py      : ffprobe + silencedetect + faster-whisper → zaman çizelgesi │
│  ├─ render.py     : sahne sahne FFmpeg → parça MP4 → birleştirme + ses + ASS    │
│  └─ shorts.py     : 9:16 bağımsız kurgu                                         │
│ Her adım çıktıyı R2'ye yazar, SHA-256 kaydeder, job_steps tablosunu günceller   │
└───────────────┬────────────────────────────────────────────────────────────────┘
                ▼
┌──────────── CLOUDFLARE R2 (medya) ────────────┐
│ projects/<slug>/research|scripts|voiceover|    │
│ assets|scenes|subtitles|renders|shorts/        │
└───────────────────────────────────────────────┘
```

### Neden GitHub Actions?
- Ücretsiz seçenekler arasında **en güçlü ve en güvenilir** CPU bu (4 vCPU / 16 GB). Uyumuyor, kart istemiyor.
- Sunucu kurmaya gerek yok. Tarayıcı ve bilgisayar kapalı olsa da iş bulutta çalışmaya devam ediyor.
- FFmpeg, Python, faster-whisper ve rembg her çalışmada runner'a kuruluyor (önbellek ile hızlı). **Sizin bilgisayarınıza hiçbir şey kurulmuyor.**
- Öneri: **uygulama kodu public repoda dursun** (sınırsız ücretsiz dakika). Gizli anahtarlar GitHub Secrets'ta durur, medya ve proje verileri repoda değil R2/Supabase'de tutulur, yani kodun açık olması içeriğinizi açığa çıkarmaz. Private repo isterseniz ayda ≈2.000 dakika ile çalışır, bu da tahminen ~40–60 tam belgesel render'ı demek.

### İş kuyruğu, kaldığı yerden devam etme ve bütünlük
- `jobs` tablosu bir projenin bütün iş akışını, `job_steps` her aşamayı tutar (araştırma, senaryo, …, render sahne-07 gibi): `pending | running | done | failed`, deneme sayısı, çıktı yolu, SHA-256, kalp atışı zamanı.
- Render **sahne başına bir parça MP4** olarak yapılır. Bir kesinti olursa yalnızca bitmemiş sahneler yeniden işlenir. Birleştirme en son adımdır.
- Her çıktı dosyası boyut, hash ve `ffprobe` kontrolünden geçer. Bozuk dosya çıkarsa adım otomatik tekrarlanır (en fazla 3 kez).
- Cron işçisi 10 dakikadan uzun süre kalp atışı göndermeyen `running` adımları yeniden kuyruğa alır.
- **Kural:** Gerçek seslendirme dosyası yüklenmeden ve analiz edilmeden `render_final` adımı başlatılamaz. Bu hem veritabanı kısıtı hem de API kontrolü olarak uygulanır. Sessiz önizleme (animatik) ayrı bir iş türü olacak ve "sessiz önizleme" diye etiketlenecek.

---

## 3. Modül tasarımları (özet)

### 3.1 Araştırma motoru
1. LLM konuyu alt sorulara böler: zaman çizelgesi, kişiler, mekânlar, sayısal veriler.
2. Kaynaklar toplanır: Wikipedia/Wikidata (iskelet olarak), OpenAlex ve Crossref (akademik), LoC, Europeana ve Internet Archive (birincil belgeler), resmî kurum siteleri.
3. Her bilgi bir **iddia kaydına** dönüşür: `claim`, `source_url`, `source_type`, `quote`, `accessed_at`.
4. Doğrulama kuralı: en az 2 bağımsız kaynak = "doğrulandı", tek kaynak = "zayıf", kaynaklar uyuşmuyorsa = "**çelişki**". Çelişkiler raporda ayrı bölümde listelenir. Örnek: Vezüv patlamasının tarihi. Plinius'un mektubu 24 Ağustos 79 der, yeni arkeolojik bulgular Ekim 79'a işaret eder.
5. Çıktılar: `research/report.md`, `research/claims.json`, `research/sources.json`.
6. **Dürüst sınır:** LLM tabanlı doğrulama hatasız değildir. Bu yüzden senaryoya geçmeden önce bir "araştırma onayı" ekranı olacak.

### 3.2 Senaryo motoru
- Yapı: çarpıcı giriş → tarihsel arka plan → olayların gelişimi → dönüm noktası → sonuçlar → kapanış.
- Hedef: 10–12 dk. Türkçe anlatımda dakikada ~140 kelime kabul edilerek kelime bütçesi çıkarılır.
- Her sahne şu alanları içerir: numara, tahmini süre, seslendirme metni, görsel açıklaması ve arama anahtar kelimeleri, kamera hareketi, geçiş, müzik ruh hâli, ses efekti, ilgili `claim_id`'ler.
- Shorts ayrı yazılır: 45–60 sn, ilk 3 saniyede kanca, kendi başına anlamlı, ana belgesele yönlendiren doğal bir kapanış.

### 3.3 ElevenLabs akışı (manuel)
- `documentary_voiceover.txt` ve `shorts_voiceover.txt` indirilebilir olur. Metin yalnızca okunacak cümlelerden oluşur, sahne numarası gibi işaretler içermez. ElevenLabs'in doğal duraklaması için sahneler arasında paragraf boşluğu bırakılır.
- MP3 veya WAV yüklediğinizde dosya **doğrudan R2'ye** gider, Supabase'in 50 MB sınırına takılmaz.
- Analiz: `ffprobe` ile süre, `silencedetect` ile duraklamalar, faster-whisper ile kelime zaman damgaları. Ardından whisper çıktısı senaryo metniyle bulanık eşleştirilir ve **her sahnenin gerçek başlangıç ve bitiş zamanı** çıkarılır. Kelime zamanları altyazı (SRT/ASS) için de kullanılır.

### 3.4 Görsel arşiv ve lisans politikası
- Aranacak kaynaklar: Wikimedia Commons (`extmetadata` lisans alanları), Openverse, Met Museum Open Access (CC0, Pompeii için çok zengin), Smithsonian Open Access (CC0), Europeana, LoC, Internet Archive. Temsili modern görüntü için Pexels.
- **İzin verilen lisanslar:** Public Domain, PDM, CC0, CC BY. CC BY-SA kabul edilir ama işaretlenir.
- **Reddedilenler:** lisansı bilinmeyenler, "All rights reserved", ND. NC lisanslar, kanal monetize ise reddedilir.
- Her varlık için şu kayıt tutulur: kaynak URL, dosya URL, eser sahibi, lisans, lisans URL, atıf metni, indirme tarihi, SHA-256. Bu kayıtlardan otomatik olarak `credits.txt` dosyası ve video açıklamasına konacak atıf metni üretilir.
- Görsel seçimi şöyle yapılır: sahne metni ve görsel açıklaması LLM ile anahtar kelimeye çevrilir, aday görseller metadata ve başlık benzerliğine göre puanlanır. Son seçimi panelde değiştirebilirsiniz.
- Dürüst not: Arşiv görüntülerinde YouTube Content ID yanlış eşleşmesi olabilir. Lisans kaydı itiraz için kanıt olarak saklanır.

### 3.5 Video montaj motoru (FFmpeg, bulutta)
- **Ana belgesel:** 1920x1080, 25 fps, H.264 (libx264, CRF 20), AAC 192k, MP4, `+faststart`.
- **Shorts:** 1080x1920, 30 fps, H.264, MP4.
- Hareket: zoom/pan (Ken Burns) için yüksek çözünürlüğe ölçekleyip ifadeli `crop`. Parallax için rembg (açık kaynak U²-Net) ile ön plan ve arka plan ayrılır, iki katman farklı hızlarda kaydırılır.
- Geçişler: `xfade` (fade, dissolve, wipe, slide). Film grain: `noise`. Renk: `eq` + `curves` + `lut3d` (açık kaynak LUT). Vinyet: `vignette`.
- 2D grafikler (harita, zaman çizelgesi, bilgi kartı) Python (Pillow/Cairo) ile kare kare üretilir, sonra FFmpeg ile hareketlendirilir.
- Ses: seslendirme, müzik ve efekt katmanları. Müzik konuşma altında otomatik kısılır (`sidechaincompress` ile ducking), ardından `loudnorm` ile YouTube için −14 LUFS.
- Altyazı: whisper kelime zamanlarından ASS üretilir, `libass` ile videoya gömülür. Ayrıca ayrı SRT dosyası verilir.
- Opsiyonel: daha zengin animasyonlu grafikler için **Remotion** kullanılabilir. Bireyler ve 3 kişiye kadar şirketler için ücretsiz lisansı var. Karar Stage 6'da verilecek.

### 3.6 Shorts motoru
- Ana kurgudan bağımsız kendi senaryosu ve kendi seslendirmesi olur.
- Dikey kompozisyon: yatay görselde ilgi alanı merkezli kırpma ya da bulanık arka plan üstüne yerleşim. Büyük ve kelime kelime vurgulanan altyazı.
- İlk 3 saniye: en çarpıcı görsel, hızlı zoom ve kanca cümlesi.

---

## 4. Veritabanı şeması (taslak)

`projects` (slug, konu, dil, hedef süre, üslup, durum) · `sources` · `claims` (doğrulama durumu, çelişki notu) · `scripts` (tür: doc|shorts, versiyon) · `scenes` (sıra, metin, görsel planı, kamera, geçiş, gerçek zamanlar) · `assets` (lisans alanları, hash, R2 yolu) · `voiceovers` (tür, dosya, süre, analiz JSON) · `renders` (tür, çözünürlük, durum, R2 yolu, boyut) · `jobs` / `job_steps` · `usage_metrics` (R2 GB, LLM istekleri, Actions dakikaları, neuron) · `error_logs`.
Tüm tablolarda Supabase RLS açık olacak, her kullanıcı yalnızca kendi projesini görecek.

R2 klasör yapısı (istediğiniz şekilde):
```
projects/pompeii-son-gunu/
  research/ scripts/ voiceover/ assets/ scenes/ subtitles/ renders/ shorts/
```

---

## 5. Ücretsiz limitlerin yetmediği noktalar ve alternatifler

| # | Darboğaz | Etki | Çözüm |
|---|---|---|---|
| 1 | Video depolama (Supabase 1 GB) | 2–3 belgeselde dolar | R2 (10 GB) + 8 GB'ta durduran kota koruması + eski render'ları silme/arşivleme. Kart istemeyen yedekler: B2 veya GitHub Releases |
| 2 | R2'de harcama tavanı yok | Kart ekliyse limit aşımında ücret çıkabilir | Uygulama seviyesinde sert limit + Dashboard uyarısı. İsterseniz kart gerektirmeyen yedek |
| 3 | Yapay zekâ görsel kotası (günde ~5–7) | Çok sayıda temsili görsel gerekiyorsa üretim günlere yayılır | Önce arşiv görseli. Yapay zekâ görseli yalnızca boşlukta. Kuyruk ertesi güne kalır |
| 4 | LLM free tier kotaları | Uzun araştırma kotaya takılabilir | Sağlayıcı zinciri + önbellek + aşamaların günlere bölünebilmesi |
| 5 | Supabase 7 gün duraklatma | Uzun aradan sonra panel açılmaz | Günlük cron ping |
| 6 | Vercel Hobby ticari kullanım yasağı | Monetize kanalda kural ihlali riski | Cloudflare Workers/Netlify'a taşınabilir kod |
| 7 | Private repoda Actions dakikaları | Ayda ≈40–60 render | Public repo önerisi |
| 8 | Lisanslı müzik arşivi API'si sınırlı | Otomatik müzik seçimi kısıtlı | Freesound + CC-BY kütüphaneleri + kendi yüklediğiniz parçalar (ör. YouTube Audio Library'den manuel) |

**Tahmini render süreleri** (ölçülmedi, Stage 6'da gerçek ölçüm yapılacak): 12 dk belgesel 4 vCPU üzerinde ≈ 15–35 dk, Shorts ≈ 2–5 dk, whisper analizi ≈ 5–10 dk.

---

## 6. Hesaplar (sizin açmanız gerekenler, hepsi ücretsiz)

1. **GitHub** repo (kod + Actions). Bu Claude Code oturumuna repo bağlanması gerekiyor, şu anda bağlı bir repo yok.
2. **Supabase** projesi (URL + anon key + service role key).
3. **Cloudflare** hesabı: R2 bucket ve Workers AI token.
4. **Google AI Studio** Gemini API anahtarı. Opsiyonel: Groq ve OpenRouter anahtarları.
5. **Vercel** hesabı (GitHub ile giriş).
6. Opsiyonel ücretsiz anahtarlar: Europeana, Freesound, Pexels, api.data.gov (Smithsonian).

Anahtarlar sohbete yazılmayacak. GitHub Secrets ve Vercel ortam değişkenlerine siz gireceksiniz.

---

## 7. Stage 2 için önerilen plan (onayınızdan sonra)
- Next.js 15 + TS + Tailwind iskeleti, menülerin tamamı (Dashboard … Ayarlar), Supabase şeması ve RLS, Auth.
- `jobs`/`job_steps` altyapısı ve sahte (dummy) bir GitHub Actions işçisi ile uçtan uca durum akışı testi.
- Dashboard: aktif projeler, bekleyen seslendirmeler, render durumu, depolama kullanımı, hata kayıtları.

---

## Kaynaklar
- GitHub Actions faturalama: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- GitHub-hosted runner özellikleri: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- GitHub Actions 2026 fiyat değişiklikleri: https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/ , https://resources.github.com/actions/2026-pricing-changes-for-github-actions/
- Supabase free tier (ikincil kaynaklar): https://www.jetadmin.io/blog/supabase-pricing-2026-guide-to-plans-limits-and-real-world-costs/ , https://designrevision.com/blog/supabase-pricing.md , https://automationatlas.io/answers/supabase-free-tier-limits-2026/
- Cloudflare R2 fiyatlandırma: https://developers.cloudflare.com/r2/pricing/ , https://tech-insider.org/au/how-to-set-up-cloudflare-r2-2026/
- Cloudflare Workers AI fiyatlandırma: https://developers.cloudflare.com/workers-ai/platform/pricing/
- Vercel Hobby: https://vercel.com/docs/plans/hobby
- Gemini API: https://ai.google.dev/gemini-api/docs/pricing , https://agentdeals.dev/gemini-api-pricing-changes
- Groq free tier: https://benchlm.ai/free-tier/groq , https://openrouter.ai/blog/tutorials/free-llm-apis-compared/
- Backblaze B2: https://backblaze.com/cloud-storage/pricing
- Hugging Face Spaces: https://huggingface.co/docs/hub/en/spaces-overview , https://huggingface.co/docs/huggingface_hub/guides/manage-spaces
- Openverse API: https://wordpress.github.io/openverse-api/reference/api/authentication_and_throttling.html

---

## 8. Kullanıcı kararları (14 Kasım 2026)
- Repo: **public** (GitHub Actions ücretsiz, 4 vCPU).
- Depolama: **Cloudflare R2**, kart ekleme kabul edildi. Uygulama 8 GB'ta yeni render'ı durduracak.
- Kanal: şimdilik para kazanmıyor, ileride kazanabilir. Bu nedenle:
  - NC (ticari olmayan) lisanslı görseller **varsayılan olarak reddedilecek**. Ayarlardan açılabilir.
  - Arayüz Vercel Hobby ile başlayacak, Cloudflare Workers/Netlify'a taşınabilir kalacak.

---

## 9. Stage 3 sırasında tespit edilen güncellemeler (14 Kasım 2026)
- **OpenAlex** Şubat 2026'dan beri kullanım bazlı fiyatlandırmaya geçti: anahtarsız günde 0,10 $, **ücretsiz anahtarla günde 1 $** kullanım hakkı. Bir arama ≈0,001 $; bir proje ≈3–6 arama yapar, yani ücretsiz anahtar fazlasıyla yeter. Anahtar `OPENALEX_API_KEY` olarak eklenir. Anahtarsız paylaşımlı IP'lerde (ör. bulut runner'ları) kota çabuk dolabilir; o durumda OpenAlex atlanır, diğer kaynaklar sürer.
- **Gemini** varsayılan modeli `gemini-3.8-flash` (kararlı, ücretsiz katmanda), yedek `gemini-3.5-flash-lite`. `gemini-2.5-flash` kullanımdan kalkıyor (1 Aralık 2026). Ücretsiz katmanda gönderilen içerik Google ürünlerini geliştirmek için kullanılır.
- Bir belgesel projesi yaklaşık **10–14 LLM isteği** harcar (plan 1, iddia çıkarma ~4, birleştirme 1, özet 1, senaryo 1–3, Shorts 1–3).

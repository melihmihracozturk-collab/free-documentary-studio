# Öneri videoları: animasyonlu kadın sunucu (Ayla)

Anime / dizi / film öneri **Shorts'ları** (≈1 dakika, dikey) için yeni bir biçim (`format = 'review'`). Videoyu, kodla çizilmiş 2D anime tarzı
bir kadın sunucu anlatır: ninja kostümlü, kızıl gözlü, yırtıcı bakışlı Ayla (pençe izli alın plakası, kırmızı atkı, omuz zırhı, sırtında kılıç). Sunucu göz kırpar, nefes alır, başını sallar, ağzı sese göre hareket eder. Sunucunun yanında
her yapımı anlatan hareketli grafikler yer alır: afiş kartı, bilgi kartı, renk paleti animasyonu ve tam ekran afiş.

Bilgisayarınıza hiçbir şey kurulmaz; her şey mevcut stüdyonun bulut hattında (GitHub Actions) çalışır.

## Kullanılan araçlar (hepsi ücretsiz)

| İş | Araç | Ücret / anahtar |
|---|---|---|
| Karakter çizimi | Kodla yazılmış katmanlı SVG (`worker/fds_worker/presenter.py`) | Ücretsiz, anahtar yok |
| SVG → PNG | [CairoSVG](https://cairosvg.org) (LGPL) | Ücretsiz |
| Kare kare animasyon | Pillow | Ücretsiz |
| Saydam sunucu videosu | FFmpeg + VP9 (alfa kanallı WebM) | Ücretsiz |
| Dudak senkronu | Sesin genliği + sıfır geçiş oranı → 6 ağız şekli | Ücretsiz (kod) |
| Sunucu sesi | [edge-tts](https://github.com/rany2/edge-tts), Türkçe kadın sesi `tr-TR-EmelNeural` | Ücretsiz, anahtar yok |
| Yedek ses | Gemini TTS (`GEMINI_API_KEY`, ücretsiz katman; ses: `Leda`) | Ücretsiz katman |
| Anime bilgisi + afiş | [AniList GraphQL API](https://anilist.co) | Ücretsiz, anahtar yok |
| Film/dizi bilgisi + afiş | [TMDB API](https://www.themoviedb.org/settings/api) | Ücretsiz anahtar (isteğe bağlı) |
| Ek bilgi + yedek afiş | Vikipedi | Ücretsiz |
| Senaryo | Mevcut LLM hattı (Gemini / Groq / OpenRouter ücretsiz katmanları) | Ücretsiz katman |
| Altyazı zamanlaması | faster-whisper (mevcut) | Ücretsiz |
| Müzik | FFmpeg ile üretilen telifsiz akor yastığı (Cmaj7–Am7–Fmaj7–G) | Ücretsiz |
| Montaj | FFmpeg (mevcut) | Ücretsiz |

## Akış

**Öneri biçimi yalnızca ≈1 dakikalık dikey Shorts üretir (1080×1920, en fazla 58 sn). Uzun video yoktur.** Uzun videonun
senaryo ve render adımları öneri projelerinde veritabanı tarafından otomatik olarak "atlandı" yapılır
(`0015_review_shorts_only.sql`). Belgesel ve vlog projeleri etkilenmez.

1. **Yeni proje → "Anime / dizi / film önerisi".** Konu tek bir yapım ("Bleach"), en fazla 3 yapım ("Frieren, Dark,
   Arcane") ya da bir tema olabilir ("Bu kış izlenecek fantastik animeler"). Süre seçilmez.
2. **Araştırma:** LLM en fazla 3 gerçek yapım seçer. Her yapım AniList'te (anime), TMDB'de (anahtar varsa) ve
   Vikipedi'de aranır. **Hiçbir katalogda bulunamayan yapım listeden çıkarılır**, böylece uydurma bir yapım önerilmez.
   İddialar kaynaktan birebir alıntıyla doğrulanır. Araştırma onayı sizdedir.
3. **Shorts senaryosu:** kanca → yapımlar (spoiler'sız) → izleyiciye kısa bir soru. Ayla birinci ağızdan konuşur.
   Görüş bildirmek serbesttir; olgular iddialardan gelir ve kodla denetlenir. Senaryo onayı sizdedir.
4. **Ses:** onaydan sonra işçi Shorts metnini Edge TTS ile seslendirir (çalışmazsa Gemini TTS). Yükleme beklenmez.
   İsterseniz Seslendirme sayfasından kendi kaydınızı yükleyerek otomatik sesi değiştirebilirsiniz.
5. **Görseller:** her yapımın afişi indirilir ve o yapımın sahnelerine atanır. Afiş önceliği: TMDB, sonra AniList,
   sonra Vikipedi. Görsel onayı sizdedir.
6. **Render:** sahne başına hareketli grafik üretilir. Ayla alt bölümde saydam bir katman olarak durur. Altyazı
   Ayla'nın hemen üstündeki bantta görünür, grafiklerin üstüne binmez.
7. **Teslim:** Shorts videosu, `shorts_description.txt` (afiş telif notu, TMDB atfı ve yapay zekâ sesi notu dahil)
   ve `credits.txt`.

### Sahne düzenleri

| Düzen | Ne görünür | Sunucu |
|---|---|---|
| `host` | Stüdyo arka planı (bokeh ışıklar), kayan büyük başlık | Büyük |
| `title` | Bulanık afiş arka planı; afiş kartı aşağıdan kayarak gelir; bilgi kartı (sıra, ad, yıl · biçim · bölüm, tür etiketleri, puan çubuğu, stüdyo) | Orta |
| `poster` | Süzülen afiş kartı + ekran yazısı etiketi | Orta |
| `mood` | Afişin baskın renginden palet, yüzen şekiller, büyük ekran yazısı | Orta |
| `full` | Afiş büyük ve ortada | Gizli (yana kayar) |

Düzenler kodla atanır: giriş ve kapanış `host`, her yapımın ilk sahnesi `title`, diğer sahneler `poster` / `mood` /
`full` arasında döner. Art arda iki `full` sahne gelmez. Kipler arasında 0,6 saniyelik yumuşak geçiş vardır.

## Diğer biçimlerden ayrım

- Ayla'nın kodu yalnızca `format = 'review'` projelerde çalışır; belgesel ve vlog akışı değişmez.
- Panelde her projede renkli bir biçim etiketi vardır: Belgesel (amber), Vlog (mavi), Öneri · Ayla (mor). Proje
  Arşivi'nde biçime göre sekmeler, modül sayfalarındaki proje seçicide biçime göre gruplar bulunur.
- Öneri projelerinin adresleri ve R2 klasörleri `oneri-` ön ekiyle başlar (`projects/oneri-bleach/…`).
- Ortak olanlar: tek iş kuyruğu (projeler sırayla işlenir), R2 depolama kotası, GitHub Actions dakikaları, Gemini kotası.

## Kurulum (yalnızca yeni olanlar)

1. **Şema:** Actions → *migrate* → *Run workflow* (`0013_license_draft.sql`, `0014_review.sql` ve `0015_review_shorts_only.sql` uygulanır).
2. **İsteğe bağlı, TMDB anahtarı:** themoviedb.org'da ücretsiz hesap açın → Settings → API → anahtar
   (v3 "API Key" ya da v4 "Read Access Token") → GitHub Secrets'a `TMDB_API_KEY` olarak ekleyin. Anahtar yoksa anime
   için AniList, film/dizi için Vikipedi kullanılır.
3. **Ayarlar** (`settings` tablosu, isteğe bağlı):
   - `presenter_name`: sunucunun adı (varsayılan `"Ayla"`)
   - `tts_provider`: `"edge"` (varsayılan) ya da `"gemini"`
   - `tts_voice`: Edge sesi (varsayılan `"tr-TR-EmelNeural"`)
   - `tts_rate`: konuşma hızı (ör. `"+4%"`)
   - `gemini_tts_voice`: Gemini sesi (ör. `"Leda"`, `"Kore"`)
   - Gemini TTS modelini değiştirmek için GitHub değişkeni: `GEMINI_TTS_MODEL`

İşçi `cairosvg` ve `edge-tts` paketlerini `worker/requirements.txt` dosyasından kurar. `libcairo2` iş akışında
apt ile kurulur.

## Karakteri değiştirmek

Karakterin tamamı `presenter.py` içindeki SVG katmanlarıdır: `layer_back_hair`, `layer_body`, `layer_face`,
`layer_eyes(open|half|closed)`, `layer_brows(neutral|up)`, `layer_mouth(rest|a|b|wide|o|e)` ve `layer_front_hair`.
Renkler en üstteki `C` sözlüğündedir; saç, göz, ninja giysisi, atkı ve zırh rengi tek satırla değişir. Panelde görünen önizleme
`public/sunucu.svg` dosyasıdır. Karakteri değiştirdikten sonra bu dosyayı yeniden üretin:

```bash
cd worker && python -c "from fds_worker import presenter as P; open('../public/sunucu.svg','w').write(P.full_svg())"
```

Görünüm değişince `PRESENTER_VERSION` değerini artırın; önbellekteki eski sunucu videoları yeniden üretilir.

## Hukuki notlar (önemli)

- **Afişler telif hakkı sahiplerinindir.** Yalnızca inceleme/eleştiri amacıyla kullanılır (`license_class = 'promo'`),
  açıklamada kaynak belirtilir. Bu yaygın bir uygulamadır ama YouTube Content ID ya da hak sahibi itirazı riski sıfır
  değildir. Fragman veya sahne görüntüsü kullanılmaz.
- **TMDB:** açıklamada "This product uses the TMDB API but is not endorsed or certified by TMDB." yazar (otomatik eklenir).
  TMDB'nin ücretsiz anahtarı ticari olmayan kullanım içindir; kanal para kazanıyorsa TMDB'nin ticari koşullarına bakın.
- **AniList API:** ticari olmayan kullanım için ücretsizdir; para kazanan kanallar için AniList'in koşullarını kontrol edin.
- **Edge TTS** resmî bir API değildir; Microsoft servisi değiştirir ya da engellerse sistem otomatik olarak Gemini TTS'e
  geçer. Açıklamada sesin yapay zekâ ile üretildiği belirtilir (YouTube'un sentetik içerik politikası).
- Sunucu karakter ve tüm animasyonlar özgün olarak kodla üretilmiştir; telif sorunu yoktur.

## Performans (GitHub Actions, 1 dakikalık Shorts için tahmini)

- Sunucu katmanı: kare başına yaklaşık 20 ms → yaklaşık 40 saniye
- Sahne grafikleri: videonun her saniyesi için yaklaşık 1–2 saniye → yaklaşık 1–2 dakika
- Ses analizi (whisper) ve birleştirme: birkaç dakika

Render yarıda kalırsa sahne klipleri ve sunucu videosu R2'den yeniden kullanılır.

# Öneri videoları: animasyonlu kadın sunucu (Ayla)

Anime / dizi / film öneri videoları için yeni bir biçim (`format = 'review'`). Videoyu, kodla çizilmiş 2D anime tarzı
bir kadın sunucu anlatır. Sunucu göz kırpar, nefes alır, başını sallar, ağzı sese göre hareket eder. Sunucunun yanında
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

1. **Yeni proje → "Anime / dizi / film önerisi".** Konu bir tema olabilir ("Bu kış izlenecek 5 fantastik anime")
   ya da doğrudan yapım listesi ("Frieren, Dark, Arcane").
2. **Araştırma:** LLM 4–6 gerçek yapım seçer. Her yapım AniList'te (anime), TMDB'de (anahtar varsa) ve Vikipedi'de
   aranır. **Hiçbir katalogda bulunamayan yapım listeden çıkarılır**, böylece uydurma bir yapım önerilmez. İddialar,
   belgeseldeki gibi kaynaktan birebir alıntıyla doğrulanır. Araştırma onayı yine sizdedir.
3. **Senaryo:** önce giriş, sonra her yapım için bir bölüm, en sonda kapanış. Sunucu birinci ağızdan, sıcak ve
   **spoiler'sız** konuşur. Görüş bildirmek serbesttir; yıl, stüdyo, bölüm sayısı, puan ve konu gibi olgular ise
   iddialardan gelir ve kodla denetlenir. Shorts'ta sunucu yapımları hızlıca sıralar. Senaryo onayı yine sizdedir.
4. **Ses:** onaydan sonra işçi metni Edge TTS ile seslendirir (çalışmazsa Gemini TTS). Yükleme beklenmez. İsterseniz
   Seslendirme sayfasından kendi kaydınızı yükleyerek otomatik sesi değiştirebilirsiniz.
5. **Görseller:** her yapımın afişi indirilir ve o yapımın sahnelerine atanır. Afiş önceliği: TMDB, sonra AniList,
   sonra Vikipedi.
6. **Render:** sahne başına hareketli grafik üretilir. Sunucu tüm video boyunca ayrı bir saydam katman olarak üstte
   durur. Altyazı sunucunun üstüne binmez: yatayda sol alanda, dikeyde sunucunun hemen üstünde görünür.

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

## Kurulum (yalnızca yeni olanlar)

1. **Şema:** Actions → *migrate* → *Run workflow* (`0013_review.sql` uygulanır).
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
Renkler en üstteki `C` sözlüğündedir; saç, göz ve kapüşon rengi tek satırla değişir. Panelde görünen önizleme
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

## Performans (GitHub Actions, 10 dakikalık video için tahmini)

- Sunucu katmanı: kare başına yaklaşık 20 ms → yaklaşık 5 dakika
- Sahne grafikleri: videonun her saniyesi için yaklaşık 1 saniye → yaklaşık 10 dakika
- Birleştirme: belgeselle aynı

Render yarıda kalırsa sahne klipleri ve sunucu videosu R2'den yeniden kullanılır.

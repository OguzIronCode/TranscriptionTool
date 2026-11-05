# Transkript Aracı

**Canlı:** <https://oguzhandemirbas.com.tr/transkript/> · [Tüm araçlar](https://oguzhandemirbas.com.tr/araclar)

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688) ![Lisans](https://img.shields.io/badge/lisans-MIT-green)

Video veya ses dosyasından saniyeler içinde metin çıkaran, **hesap ve veritabanı gerektirmeyen** küçük bir web uygulaması.
Dosya yükle, mikrofonla kaydet ya da YouTube/URL yapıştır; transkripti kopyala veya **TXT / SRT** olarak indir. İstersen yapay zekâ özeti (TXT/PDF) al.

**Gizlilik:** Hiçbir şey kalıcı saklanmaz. Yüklenen dosyalar işlem biter bitmez silinir, transkriptler yalnızca tarayıcında durur.

> Canlı sürümde kötüye kullanımı önlemek için IP başına saatlik limit uygulanır ve URL ile indirme yalnızca belirli sitelerle (YouTube, Vimeo, X/Twitter) sınırlıdır. Kendi kurulumunuzda bu ayarlar `.env` ile değiştirilebilir.

## Özellikler

- Dosya yükleme (MP4, MKV, AVI, MOV, WEBM, MP3, WAV, M4A, FLAC, OGG), mikrofon kaydı, YouTube/URL ile indirme
- **Groq Whisper Large v3** ile transkripsiyon, 13 dil + otomatik algılama
- Zaman damgalı gösterim, kopyalama, **TXT** ve **SRT** indirme
- Özet, temel noktalar ve anahtar kelimeler (TXT/PDF olarak indirilebilir)
- Koyu/açık tema

## Nasıl çalışır?

```
Tarayıcı ──▶ FastAPI ──▶ ffmpeg (16 kHz mono mp3) ──▶ Groq Whisper ──▶ metin + zaman damgaları
                │
                └─▶ yt-dlp (yalnızca URL ile)
```

Ses, Groq'un dosya sınırına (≈25 MB) sığacak şekilde sıkıştırılır; bu yaklaşık 3,5 saatlik kayda denk gelir.

## Gereksinimler

- Python 3.10+
- **ffmpeg** (`PATH` içinde)
- [Groq API anahtarı](https://console.groq.com) (ücretsiz katman yeterli)

## Yerelde çalıştırma

```bash
git clone https://github.com/OguzIronCode/TranscriptionTool.git
cd TranscriptionTool
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # GROQ_API_KEY değerini doldurun
uvicorn main:app --reload
```

Aç: <http://localhost:8000>

ffmpeg kurulumu: Windows `winget install ffmpeg`, macOS `brew install ffmpeg`, Linux `sudo apt install ffmpeg`.

## Ayarlar (ortam değişkenleri)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `GROQ_API_KEY` | *(zorunlu)* | Groq API anahtarı |
| `RATE_PER_HOUR` | `10` | IP başına saatlik transkripsiyon isteği |
| `RATE_SUMMARY_PER_HOUR` | `30` | IP başına saatlik özet isteği |
| `MAX_CONCURRENT_JOBS` | `2` | Aynı anda çalışan transkripsiyon sayısı (CPU/RAM koruması) |
| `JOB_QUEUE_TIMEOUT` | `30` | Boş yer beklerken en fazla bekleme (sn), sonra `503` |
| `MAX_UPLOAD_MB` | `500` | Yükleme boyut sınırı |
| `MAX_MEDIA_SECONDS` | `14400` | URL ile indirilen en uzun video (sn) |
| `URL_ALLOWED_HOSTS` | *(boş)* | URL indirme için izinli siteler, virgülle (örn. `youtube.com,youtu.be`). Boş = tüm genel adresler |
| `PUBLIC_URL` | *(boş)* | Sitenin herkese açık adresi (örn. `https://alanadi.com/transkript/`). `canonical`, Open Graph, sitemap ve robots için gerekir |
| `SUMMARY_MODEL` | `openai/gpt-oss-120b` | Özet için Groq modeli |
| `YTDLP_YOUTUBE_CLIENTS` | *(boş)* | İsteğe bağlı yt-dlp YouTube istemcileri (örn. `android,ios`) |
| `LOG_LEVEL` | `INFO` | Log seviyesi |

## API

| Uç | Açıklama |
|---|---|
| `POST /transcribe` | `multipart/form-data`: `file`, `language` (`auto` veya `tr`, `en`, ...). Yanıt: `text`, `segments[]`, `language`, `duration_seconds` |
| `POST /transcribe-url` | JSON: `{"url": "...", "language": "auto"}`. Yanıt `/transcribe` ile aynı |
| `POST /summarize` | JSON: `{"text": "...", "filename": "...", "language": "tr"}`. Yanıt: `summary`, `key_points[]`, `keywords[]`, `word_count` |
| `GET /health` | `200 ok`; ffmpeg yoksa `503` |

Hatalar `{"detail": "..."}` biçiminde döner (`400` geçersiz girdi, `413` çok büyük, `429` limit, `503` meşgul).

## Gizli bilgiler

- API anahtarı yalnızca sunucudaki `.env` dosyasında (ya da ortam değişkeninde) tutulur; **repoya hiçbir anahtar girmez**. `.env` dosyası `.gitignore` içindedir.
- `.env.example` yalnızca boş/örnek değerler içerir.
- Anahtar sızdığından şüphelenirseniz [console.groq.com](https://console.groq.com) üzerinden yenileyip `.env` dosyasını güncelleyin ve servisi yeniden başlatın.

## Üretim notları

- **Hız sınırı** IP başına ve bellekte tutulur (tek süreç). Tek worker ile çalıştırın.
- **SSRF:** URL indirme; http(s) dışı şemaları, 80/443 dışı portları, URL içindeki şifreleri ve özel/yerel adreslere çözülen hostları reddeder. Herkese açık sunucuda `URL_ALLOWED_HOSTS` ile siteleri kısıtlamanız önerilir.
- **Yüklemeler:** boyut ve hız kontrolleri gövde okunmadan önce yapılır; geçici dosyalar her istekten sonra silinir.
- **Hatalar** sunucuda loglanır, kullanıcıya genel mesaj gösterilir.
- **Başlıklar:** CSP (`script-src 'self'`: satır içi betik yok; stil için `'unsafe-inline'` açık), `nosniff`, `X-Frame-Options`, `Cross-Origin-Resource-Policy`, `Referrer-Policy`, `Permissions-Policy`; API yanıtları `no-store` + `noindex`. HSTS proxy tarafında eklenir.
- **SEO:** başlık/açıklama, canonical, Open Graph/Twitter kartı, JSON-LD (`WebApplication` + `FAQPage`), `robots.txt`, `sitemap.xml`, paylaşım görseli (`design/og.html` → `static/og.png`).
- **8000 portunu doğrudan yayınlamayın;** uygulama IP bilgisi için proxy'den gelen `X-Forwarded-For`'a güvenir. Caddy arkasında çalıştırın (`docker-compose.yml`).
- **Anahtar:** herkese açık sunucuda Groq kotanız limitlerle korunur; yine de limitleri ihtiyacınıza göre ayarlayın.
- **YouTube** sunucu IP'lerini engelleyebilir ve sık değişir; imajı yeniden derleyerek `yt-dlp`'yi güncel tutun.

## Testler

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Testler ağ, ffmpeg ya da Groq gerektirmez (sahte servislerle çalışır).

## Sunucuya kurulum

[DEPLOY.md](DEPLOY.md) iki yol anlatır: **Docker + Caddy** (otomatik HTTPS) ya da **mevcut nginx arkasında alt yol (`/transkript`) + systemd** (canlı sürümün çalıştığı düzen). Alternatif olarak `render.yaml` ile Render'a da dağıtılabilir.

## Proje yapısı

```
main.py               FastAPI uygulaması (uçlar, middleware)
app/config.py         Ortam değişkenlerinden ayarlar
app/audio.py          ffmpeg sıkıştırma + Groq Whisper çağrısı
app/limits.py         Bellek içi kayan pencere hız sınırlayıcı
app/urlcheck.py       URL indirme için SSRF koruması
static/               index.html, style.css, theme.js
tests/                pytest paketi
Dockerfile, docker-compose.yml, Caddyfile, DEPLOY.md, render.yaml
```

## Lisans

MIT, bkz. [LICENSE](LICENSE).

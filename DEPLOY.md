# Ubuntu VPS'e kurulum (Docker + Caddy)

Caddy HTTPS sertifikasını otomatik alır ve yeniler. Mikrofon kaydı için HTTPS şarttır.
Veritabanı veya hesap sistemi yoktur; tek gereken bir Groq API anahtarıdır.

## 1. Ön hazırlık
- Bir alan adı/alt alan adı seçin (örn. `transkript.example.com`) ve DNS'te **A kaydı** olarak VPS'in IP adresine yönlendirin.
- [console.groq.com](https://console.groq.com) adresinden bir API anahtarı alın.

## 2. Sunucuda Docker kurulumu
```bash
sudo apt update && sudo apt install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER     # oturumu kapatıp açın

sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw enable
```

## 3. Projeyi çekip başlatma
```bash
git clone https://github.com/OguzIronCode/TranscriptionTool.git
cd TranscriptionTool
cp .env.example .env
nano .env                          # DOMAIN ve GROQ_API_KEY değerlerini doldurun
docker compose up -d --build
```
Kontrol: `docker compose ps`, `docker compose logs -f app`, ardından `https://<alan-adınız>/health`.

## 4. Güncelleme
```bash
git pull
docker compose up -d --build
```
`yt-dlp` YouTube değişikliklerine yetişmek için sık güncellenmelidir. Her `--build` en güncel sürümü kurar; YouTube indirme hata verirse `docker compose build --no-cache app && docker compose up -d`.

## Herkese açık yayın için önerilen `.env` ayarları
```env
URL_ALLOWED_HOSTS=youtube.com,youtu.be # URL ile indirme sadece bu sitelerden
MAX_CONCURRENT_JOBS=2                  # küçük VPS'te 1-2; RAM/CPU artarsa yükseltin
RATE_PER_HOUR=10                       # IP başına saatlik transkripsiyon limiti
```

## Sorun giderme
| Belirti | Çözüm |
|---|---|
| Container sürekli yeniden başlıyor | `docker compose logs app`: "Eksik ortam değişkeni" varsa `.env`'i tamamlayın |
| Sertifika alınamıyor | DNS A kaydı VPS IP'sine işaret ediyor mu, 80/443 açık mı? (`docker compose logs caddy`) |
| Mikrofon çalışmıyor | Siteyi `https://` ile açın |
| 429 hatası | Saatlik limit; `RATE_*` değişkenleriyle ayarlanır |
| URL ile transkript çalışmıyor | YouTube sunucu IP'lerini engelleyebilir ya da yt-dlp eskidi: `docker compose build --no-cache app && docker compose up -d` |

## Notlar
- `.env` içindeki anahtarı kimseyle paylaşmayın ve repoya göndermeyin.
- 8000 portunu dışarı açmayın; uygulama yalnızca Caddy arkasında çalışmalıdır (compose bunu zaten böyle kurar).
- Zamanlı güncelleme için `git pull && docker compose up -d --build` komutunu bir cron'a ekleyebilirsiniz.

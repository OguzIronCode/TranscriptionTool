# Ubuntu VPS'e kurulum

İki yol var: **A) Docker + Caddy** (sunucuda başka site yoksa) veya **B) mevcut nginx arkasında alt yol + systemd** (sunucuda zaten bir site varsa).

---

## Seçenek A — Docker + Caddy

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

---

## Seçenek B — Mevcut nginx arkasında alt yol (`/transkript`), systemd ile

Sunucuda 80/443'ü zaten nginx kullanıyorsa Caddy kurmayın; uygulamayı `127.0.0.1:8300`'de çalıştırıp nginx ile yayınlayın.
Ön yüz göreli adresler kullandığı için uygulama alt yolda (`https://alanadi.com/transkript/`) ve kökte (`/`) aynen çalışır.

```bash
# 1. Gereksinimler (ffmpeg, python venv, git)
sudo apt install -y ffmpeg python3-venv git

# 2. Servis kullanıcısı ve kod
sudo useradd --system --home /srv/transkript --shell /usr/sbin/nologin transkript
sudo mkdir -p /srv/transkript && sudo chown transkript:transkript /srv/transkript
sudo -u transkript git clone https://github.com/OguzIronCode/TranscriptionTool.git /srv/transkript/app
sudo -u transkript python3 -m venv /srv/transkript/venv
sudo -u transkript /srv/transkript/venv/bin/pip install -r /srv/transkript/app/requirements.txt

# 3. Ayarlar (yalnızca servis kullanıcısı okuyabilsin)
sudo install -m 600 -o transkript -g transkript /dev/null /srv/transkript/.env
echo 'GROQ_API_KEY=gsk_...' | sudo tee -a /srv/transkript/.env
echo 'URL_ALLOWED_HOSTS=youtube.com,youtu.be' | sudo tee -a /srv/transkript/.env

# 4. systemd
sudo cp /srv/transkript/app/deploy/transkript.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now transkript
curl -s http://127.0.0.1:8300/health

# 5. nginx: deploy/nginx-transkript.conf içeriğini ilgili server { } bloğuna ekleyin
sudo nginx -t && sudo systemctl reload nginx
```

Güncelleme:
```bash
sudo -u transkript git -C /srv/transkript/app pull
sudo -u transkript /srv/transkript/venv/bin/pip install -r /srv/transkript/app/requirements.txt
sudo systemctl restart transkript
```
`yt-dlp` güncel kalması için: `sudo -u transkript /srv/transkript/venv/bin/pip install -U yt-dlp && sudo systemctl restart transkript`.

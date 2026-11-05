# Ubuntu VPS'e kurulum (Docker + Caddy)

Caddy HTTPS sertifikasını otomatik alır ve yeniler. Mikrofon kaydı için HTTPS şarttır.

## 1. Ön hazırlık
- Bir alan adı/alt alan adı seçin (örn. `transkript.example.com`) ve DNS'te **A kaydı** olarak VPS'in IP adresine yönlendirin.
- Supabase projesini hazırlayın (README → *Supabase Setup*): şema SQL'i, `avatars` bucket'ı.
- Supabase **Authentication → URL Configuration → Redirect URLs** alanına `https://<alan-adınız>/reset-password` ekleyin.

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
nano .env                          # DOMAIN ve anahtarları doldurun
docker compose up -d --build
```
Kontrol: `docker compose ps`, `docker compose logs -f app`, ardından `https://<alan-adınız>/health`.

## 4. Güncelleme
```bash
git pull
docker compose up -d --build
```
`yt-dlp` YouTube değişikliklerine yetişmek için sık güncellenmelidir. Her `--build` en güncel sürümü kurar; YouTube indirme hata verirse `docker compose build --no-cache app && docker compose up -d`.

## Notlar
- `.env` içindeki anahtarları kimseyle paylaşmayın ve repoya göndermeyin.
- Uygulama giriş yapmadan da çalışır. Herkese açık yayınlarsanız Groq kotanız başkaları tarafından tüketilebilir.
- Datacenter IP'leri YouTube tarafından engellenebilir; URL ile transkript bu durumda çalışmayabilir (dosya yükleme etkilenmez).

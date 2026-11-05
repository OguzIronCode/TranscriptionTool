"""Ortam değişkenlerinden okunan uygulama ayarları."""
import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "evet")


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} bir tam sayı olmalı (verilen: {raw!r})")


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise RuntimeError(f"{name} bir sayı olmalı (verilen: {raw!r})")


@dataclass(frozen=True)
class Settings:
    # Zorunlu
    groq_api_key: str
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str

    # Erişim ve kötüye kullanım koruması
    allow_anonymous: bool = True          # False: transkripsiyon için giriş zorunlu
    rate_anon_per_hour: int = 5           # giriş yapmamış kullanıcı (IP başına)
    rate_user_per_hour: int = 40          # giriş yapmış kullanıcı (hesap başına)
    url_allowed_hosts: tuple[str, ...] = ()   # boş: tüm genel (public) adresler

    # Kaynak sınırları
    max_upload_bytes: int = 500 * 1024 * 1024
    max_audio_mb: float = 24.5            # Groq dosya sınırı
    max_media_seconds: int = 4 * 3600     # URL ile indirilen medya süre sınırı
    max_concurrent_jobs: int = 2          # aynı anda çalışan transkripsiyon sayısı
    job_queue_timeout: float = 30.0       # sıra beklerken en fazla bekleme (sn)
    ffmpeg_timeout: float = 900.0
    download_timeout: float = 600.0

    # Diğer
    debug: bool = False                   # True: /docs açık


def load_settings() -> Settings:
    missing = [
        name for name in ("GROQ_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        raise RuntimeError("Eksik ortam değişkenleri: " + ", ".join(missing))

    hosts = tuple(
        h.strip().lower().lstrip(".")
        for h in os.environ.get("URL_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    )
    return Settings(
        groq_api_key=os.environ["GROQ_API_KEY"].strip(),
        supabase_url=os.environ["SUPABASE_URL"].strip().rstrip("/"),
        supabase_anon_key=os.environ["SUPABASE_ANON_KEY"].strip(),
        supabase_service_key=os.environ["SUPABASE_SERVICE_KEY"].strip(),
        allow_anonymous=_bool("ALLOW_ANONYMOUS", True),
        rate_anon_per_hour=_int("RATE_ANON_PER_HOUR", 5),
        rate_user_per_hour=_int("RATE_USER_PER_HOUR", 40),
        url_allowed_hosts=hosts,
        max_upload_bytes=_int("MAX_UPLOAD_MB", 500) * 1024 * 1024,
        max_concurrent_jobs=max(1, _int("MAX_CONCURRENT_JOBS", 2)),
        job_queue_timeout=_float("JOB_QUEUE_TIMEOUT", 30.0),
        max_media_seconds=_int("MAX_MEDIA_SECONDS", 4 * 3600),
        debug=_bool("DEBUG", False),
    )

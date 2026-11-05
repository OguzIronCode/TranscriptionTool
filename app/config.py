"""Ortam değişkenlerinden okunan uygulama ayarları."""
import os
from dataclasses import dataclass


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

    # Kötüye kullanım koruması (IP başına, saatlik)
    rate_per_hour: int = 10               # transkripsiyon istekleri
    rate_summary_per_hour: int = 30       # özet istekleri
    url_allowed_hosts: tuple[str, ...] = ()   # boş: tüm genel (public) adresler

    # Kaynak sınırları
    max_upload_bytes: int = 500 * 1024 * 1024
    max_audio_mb: float = 24.5            # Groq dosya sınırı
    max_media_seconds: int = 4 * 3600     # URL ile indirilen medya süre sınırı
    max_concurrent_jobs: int = 2          # aynı anda çalışan transkripsiyon sayısı
    job_queue_timeout: float = 30.0       # sıra beklerken en fazla bekleme (sn)
    ffmpeg_timeout: float = 900.0
    download_timeout: float = 600.0

    # Modeller
    summary_model: str = "openai/gpt-oss-120b"   # llama-3.3-70b-versatile Groq'ta kaldırıldı


def load_settings() -> Settings:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Eksik ortam değişkeni: GROQ_API_KEY")

    hosts = tuple(
        h.strip().lower().lstrip(".")
        for h in os.environ.get("URL_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    )
    return Settings(
        groq_api_key=key,
        rate_per_hour=_int("RATE_PER_HOUR", 10),
        rate_summary_per_hour=_int("RATE_SUMMARY_PER_HOUR", 30),
        url_allowed_hosts=hosts,
        max_upload_bytes=_int("MAX_UPLOAD_MB", 500) * 1024 * 1024,
        max_concurrent_jobs=max(1, _int("MAX_CONCURRENT_JOBS", 2)),
        job_queue_timeout=_float("JOB_QUEUE_TIMEOUT", 30.0),
        max_media_seconds=_int("MAX_MEDIA_SECONDS", 4 * 3600),
        summary_model=os.environ.get("SUMMARY_MODEL", "").strip() or "openai/gpt-oss-120b",
    )

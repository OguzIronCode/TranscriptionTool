"""ffmpeg ile ses sıkıştırma ve Groq Whisper ile transkripsiyon."""
import asyncio
import logging
import os
import re

import groq
from fastapi import HTTPException

log = logging.getLogger("transkript.audio")

LANG_RE = re.compile(r"^[a-z]{2,3}$")


def normalize_language(language: str | None) -> str | None:
    """'auto' veya boş -> None (otomatik algıla). Geçersiz kod -> 400."""
    if not language or language.strip().lower() == "auto":
        return None
    code = language.strip().lower()
    if not LANG_RE.match(code):
        raise HTTPException(400, "Geçersiz dil kodu.")
    return code


async def compress_to_mp3(input_path: str, output_path: str, timeout: float) -> None:
    """Girdiyi 16 kHz mono düşük bit hızlı mp3'e çevirir. Başarısızsa HTTPException fırlatır."""
    ext = os.path.splitext(input_path)[1].lower()

    async def _run(extra: list[str]) -> tuple[int, bytes]:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", *extra,
            "-probesize", "200M", "-analyzeduration", "200M",
            "-i", input_path,
            "-vn", "-ac", "1", "-b:a", "16k", "-ar", "16000", "-y",
            output_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise HTTPException(408, "Medya işlenirken zaman aşımı oldu. Daha kısa bir dosya deneyin.")
        return proc.returncode, stderr

    try:
        if ext in (".webm", ".weba"):
            # MediaRecorder/yt-dlp çıktısı WebM'ler için daha toleranslı demuxer sırayla denenir
            stderr = b""
            for fmt in (["-f", "matroska"], ["-f", "webm"], []):
                if os.path.exists(output_path):
                    os.unlink(output_path)
                code, stderr = await _run(fmt)
                if code == 0:
                    return
        else:
            code, stderr = await _run([])
            if code == 0:
                return
    except FileNotFoundError:
        log.error("ffmpeg bulunamadı")
        raise HTTPException(500, "Sunucu yapılandırma hatası: ffmpeg kurulu değil.")

    log.warning("ffmpeg başarısız: %s", stderr.decode(errors="replace")[-500:])
    raise HTTPException(422, "Medya dosyası işlenemedi. Dosya bozuk ya da desteklenmeyen bir biçimde olabilir.")


def _field(seg, name):
    return seg[name] if isinstance(seg, dict) else getattr(seg, name)


async def transcribe_file(client: groq.AsyncGroq, mp3_path: str, language: str | None, max_audio_mb: float) -> dict:
    """Sıkıştırılmış sesi Whisper'a gönderir, sonucu sözlük olarak döndürür."""
    size_mb = os.path.getsize(mp3_path) / (1024 * 1024)
    if size_mb > max_audio_mb:
        raise HTTPException(
            413, f"Sıkıştırılmış ses hâlâ çok büyük ({size_mb:.1f} MB). Dosyayı bölerek ya da daha kısa bir kayıtla deneyin."
        )
    try:
        with open(mp3_path, "rb") as f:
            transcription = await client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=("audio.mp3", f),
                language=language,
                response_format="verbose_json",
            )
    except groq.RateLimitError:
        log.warning("Groq hız sınırı")
        raise HTTPException(503, "Transkripsiyon servisi şu an yoğun. Biraz sonra tekrar deneyin.", headers={"Retry-After": "60"})
    except groq.APITimeoutError:
        raise HTTPException(504, "Transkripsiyon servisi zamanında yanıt vermedi. Tekrar deneyin.")
    except (groq.APIConnectionError, groq.APIStatusError) as e:
        log.error("Groq hatası: %s", e)
        raise HTTPException(502, "Transkripsiyon servisine ulaşılamadı. Biraz sonra tekrar deneyin.")

    segments, texts = [], []
    for seg in transcription.segments or []:
        text = str(_field(seg, "text")).strip()
        segments.append({"start": round(float(_field(seg, "start")), 2), "end": round(float(_field(seg, "end")), 2), "text": text})
        texts.append(text)

    return {
        "text": " ".join(texts) or (transcription.text or ""),
        "segments": segments,
        "language": getattr(transcription, "language", None) or (language or "unknown"),
        "language_probability": 1.0,
        "duration_seconds": round(segments[-1]["end"], 1) if segments else 0,
    }

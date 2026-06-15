import os
import asyncio
import tempfile
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from groq import AsyncGroq

ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".mp3", ".wav", ".m4a", ".flac", ".ogg"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500MB


@asynccontextmanager
async def lifespan(app: FastAPI):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY ortam değişkeni ayarlanmamış")
    app.state.groq = AsyncGroq(api_key=api_key)
    yield
    await app.state.groq.close()


app = FastAPI(title="Video Transcript Tool", lifespan=lifespan)


async def compress_to_mp3(input_path: str, output_path: str):
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", input_path,
        "-ac", "1", "-b:a", "16k", "-ar", "16000", "-y",
        output_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(500, f"FFmpeg hatası: {stderr.decode()}")


@app.post("/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Desteklenmeyen dosya türü: {ext}")

    tmp_input = None
    tmp_compressed = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_input = tmp.name
            total = 0
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(400, f"Dosya çok büyük. Maksimum {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.")
                tmp.write(chunk)

        tmp_compressed = tmp_input + "_compressed.mp3"
        await compress_to_mp3(tmp_input, tmp_compressed)

        size_mb = os.path.getsize(tmp_compressed) / (1024 * 1024)
        if size_mb > 24.5:
            raise HTTPException(400, f"Sıkıştırılmış dosya hâlâ çok büyük ({size_mb:.1f}MB). Dosyayı bölerek deneyin.")

        lang = language if language and language != "auto" else None
        client: AsyncGroq = request.app.state.groq

        with open(tmp_compressed, "rb") as f:
            transcription = await client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=("audio.mp3", f),
                language=lang,
                response_format="verbose_json",
            )

        segments = []
        texts = []
        for seg in (transcription.segments or []):
            segments.append({
                "start": round(seg["start"], 2),
                "end": round(seg["end"], 2),
                "text": seg["text"].strip(),
            })
            texts.append(seg["text"].strip())

        return JSONResponse({
            "text": " ".join(texts) or (transcription.text or ""),
            "segments": segments,
            "language": transcription.language or (lang or "unknown"),
            "language_probability": 1.0,
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Transkripsiyon hatası: {str(e)}")
    finally:
        for path in [tmp_input, tmp_compressed]:
            if path and os.path.exists(path):
                os.unlink(path)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")

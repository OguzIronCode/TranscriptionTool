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
from pydantic import BaseModel
from groq import AsyncGroq
from supabase import create_client
import json
import yt_dlp

ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".mp3", ".wav", ".m4a", ".flac", ".ogg"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500MB


@asynccontextmanager
async def lifespan(app: FastAPI):
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        raise RuntimeError("GROQ_API_KEY ayarlanmamış")
    app.state.groq = AsyncGroq(api_key=groq_key)

    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not sb_url or not sb_key:
        raise RuntimeError("SUPABASE_URL veya SUPABASE_SERVICE_KEY ayarlanmamış")
    app.state.supabase = create_client(sb_url, sb_key)

    yield
    await app.state.groq.close()


app = FastAPI(title="Video Transcript Tool", lifespan=lifespan)


async def get_user_id(request: Request) -> str | None:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        return None
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, lambda: request.app.state.supabase.auth.get_user(token)
        )
        return response.user.id
    except Exception:
        return None


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


@app.get("/config")
async def config():
    return JSONResponse({
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", ""),
    })


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
        groq_client: AsyncGroq = request.app.state.groq

        with open(tmp_compressed, "rb") as f:
            transcription = await groq_client.audio.transcriptions.create(
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

        duration_seconds = round(segments[-1]["end"], 1) if segments else 0

        result = {
            "text": " ".join(texts) or (transcription.text or ""),
            "segments": segments,
            "language": transcription.language or (lang or "unknown"),
            "language_probability": 1.0,
            "duration_seconds": duration_seconds,
        }

        user_id = await get_user_id(request)
        if user_id:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: request.app.state.supabase.table("transcripts").insert({
                    "user_id": user_id,
                    "filename": file.filename or "unknown",
                    "language": result["language"],
                    "text": result["text"],
                    "segments": segments,
                    "duration_seconds": duration_seconds,
                    "tags": [],
                }).execute()
            )

        return JSONResponse(result)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Transkripsiyon hatası: {str(e)}")
    finally:
        for path in [tmp_input, tmp_compressed]:
            if path and os.path.exists(path):
                os.unlink(path)


@app.get("/transcripts")
async def list_transcripts(request: Request):
    user_id = await get_user_id(request)
    if not user_id:
        raise HTTPException(401, "Giriş yapmanız gerekiyor")

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: request.app.state.supabase
            .table("transcripts")
            .select("id, filename, language, created_at, text, segments, tags, duration_seconds, is_public, share_token")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
    )
    return JSONResponse(response.data)


@app.put("/transcripts/{transcript_id}")
async def update_transcript(transcript_id: str, request: Request):
    user_id = await get_user_id(request)
    if not user_id:
        raise HTTPException(401, "Giriş yapmanız gerekiyor")

    body = await request.json()
    update_data = {k: v for k, v in body.items() if k in ("text", "filename", "tags")}
    if not update_data:
        raise HTTPException(400, "Güncellenecek alan yok")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: request.app.state.supabase
            .table("transcripts")
            .update(update_data)
            .eq("id", transcript_id)
            .eq("user_id", user_id)
            .execute()
    )
    return JSONResponse({"ok": True})


@app.post("/transcripts/{transcript_id}/share")
async def toggle_share(transcript_id: str, request: Request):
    user_id = await get_user_id(request)
    if not user_id:
        raise HTTPException(401, "Giriş yapmanız gerekiyor")

    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: request.app.state.supabase
            .table("transcripts")
            .select("is_public, share_token")
            .eq("id", transcript_id)
            .eq("user_id", user_id)
            .single()
            .execute()
    )
    if not resp.data:
        raise HTTPException(404, "Transkript bulunamadı")

    new_public = not resp.data.get("is_public", False)
    await loop.run_in_executor(
        None,
        lambda: request.app.state.supabase
            .table("transcripts")
            .update({"is_public": new_public})
            .eq("id", transcript_id)
            .eq("user_id", user_id)
            .execute()
    )
    return JSONResponse({"is_public": new_public, "share_token": resp.data.get("share_token")})


@app.get("/share/{share_token}")
async def share_page(share_token: str, request: Request):
    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: request.app.state.supabase
            .table("transcripts")
            .select("id, filename, language, text, segments, created_at, duration_seconds")
            .eq("share_token", share_token)
            .eq("is_public", True)
            .single()
            .execute()
    )
    if not resp.data:
        raise HTTPException(404, "Bu transkript bulunamadı veya paylaşım kapatılmış")
    return FileResponse("static/share.html")


@app.get("/api/share/{share_token}")
async def share_data(share_token: str, request: Request):
    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: request.app.state.supabase
            .table("transcripts")
            .select("id, filename, language, text, segments, created_at, duration_seconds")
            .eq("share_token", share_token)
            .eq("is_public", True)
            .single()
            .execute()
    )
    if not resp.data:
        raise HTTPException(404, "Bu transkript bulunamadı veya paylaşım kapatılmış")
    return JSONResponse(resp.data)


@app.delete("/transcripts/{transcript_id}")
async def delete_transcript(transcript_id: str, request: Request):
    user_id = await get_user_id(request)
    if not user_id:
        raise HTTPException(401, "Giriş yapmanız gerekiyor")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: request.app.state.supabase
            .table("transcripts")
            .delete()
            .eq("id", transcript_id)
            .eq("user_id", user_id)
            .execute()
    )
    return JSONResponse({"ok": True})


class UrlRequest(BaseModel):
    url: str
    language: Optional[str] = None


@app.post("/transcribe-url")
async def transcribe_url(body: UrlRequest, request: Request):
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Geçersiz URL")

    tmp_downloaded = None
    tmp_compressed = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".%(ext)s") as tmp:
            tmp_downloaded_tpl = tmp.name

        loop = asyncio.get_running_loop()

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": tmp_downloaded_tpl,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [],
        }

        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        tmp_downloaded = await loop.run_in_executor(None, download)

        if not os.path.exists(tmp_downloaded):
            # yt-dlp bazı formatlarda .webm .m4a gibi uzantı ekler
            base = tmp_downloaded_tpl.replace(".%(ext)s", "")
            for ext in (".webm", ".m4a", ".mp4", ".opus", ".ogg"):
                if os.path.exists(base + ext):
                    tmp_downloaded = base + ext
                    break
            else:
                raise HTTPException(500, "Video indirilemedi")

        tmp_compressed = tmp_downloaded + "_compressed.mp3"
        await compress_to_mp3(tmp_downloaded, tmp_compressed)

        size_mb = os.path.getsize(tmp_compressed) / (1024 * 1024)
        if size_mb > 24.5:
            raise HTTPException(400, f"Sıkıştırılmış ses hâlâ çok büyük ({size_mb:.1f}MB). Daha kısa bir video deneyin.")

        lang = body.language if body.language and body.language != "auto" else None
        groq_client: AsyncGroq = request.app.state.groq

        with open(tmp_compressed, "rb") as f:
            transcription = await groq_client.audio.transcriptions.create(
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

        duration_seconds = round(segments[-1]["end"], 1) if segments else 0
        result = {
            "text": " ".join(texts) or (transcription.text or ""),
            "segments": segments,
            "language": transcription.language or (lang or "unknown"),
            "language_probability": 1.0,
            "duration_seconds": duration_seconds,
        }

        user_id = await get_user_id(request)
        if user_id:
            filename = url.split("?")[0].rstrip("/").split("/")[-1] or "video"
            await loop.run_in_executor(
                None,
                lambda: request.app.state.supabase.table("transcripts").insert({
                    "user_id": user_id,
                    "filename": filename[:200],
                    "language": result["language"],
                    "text": result["text"],
                    "segments": segments,
                    "duration_seconds": duration_seconds,
                    "tags": [],
                }).execute()
            )

        return JSONResponse(result)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"URL transkripsiyon hatası: {str(e)}")
    finally:
        for path in [tmp_downloaded, tmp_compressed]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception:
                    pass


@app.get("/stats")
async def get_stats(request: Request):
    user_id = await get_user_id(request)
    if not user_id:
        raise HTTPException(401, "Giriş yapmanız gerekiyor")

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: request.app.state.supabase
            .table("transcripts")
            .select("language, duration_seconds")
            .eq("user_id", user_id)
            .execute()
    )

    data = response.data
    total = len(data)
    total_minutes = round(sum(r.get("duration_seconds") or 0 for r in data) / 60, 1)

    lang_count: dict = {}
    for r in data:
        lang = r.get("language") or "unknown"
        lang_count[lang] = lang_count.get(lang, 0) + 1
    top_lang = max(lang_count, key=lang_count.get) if lang_count else None

    return JSONResponse({
        "total_transcripts": total,
        "total_minutes": total_minutes,
        "top_language": top_lang,
    })


@app.delete("/account")
async def delete_account(request: Request):
    user_id = await get_user_id(request)
    if not user_id:
        raise HTTPException(401, "Giriş yapmanız gerekiyor")

    loop = asyncio.get_running_loop()
    # Önce tüm transkriptleri sil
    await loop.run_in_executor(
        None,
        lambda: request.app.state.supabase
            .table("transcripts")
            .delete()
            .eq("user_id", user_id)
            .execute()
    )
    # Sonra kullanıcıyı sil
    await loop.run_in_executor(
        None,
        lambda: request.app.state.supabase.auth.admin.delete_user(user_id)
    )
    return JSONResponse({"ok": True})


class SummarizeRequest(BaseModel):
    transcript_id: Optional[str] = None
    text: Optional[str] = None
    filename: Optional[str] = None
    language: Optional[str] = None


@app.post("/summarize")
async def summarize(body: SummarizeRequest, request: Request):
    groq_client: AsyncGroq = request.app.state.groq
    text = body.text
    filename = body.filename or "Transkript"
    language = body.language or "unknown"

    if body.transcript_id:
        user_id = await get_user_id(request)
        if not user_id:
            raise HTTPException(401, "Giriş yapmanız gerekiyor")
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: request.app.state.supabase
                .table("transcripts")
                .select("text, filename, language")
                .eq("id", body.transcript_id)
                .eq("user_id", user_id)
                .single()
                .execute()
        )
        if not resp.data:
            raise HTTPException(404, "Transkript bulunamadı")
        text = resp.data["text"]
        filename = resp.data.get("filename", filename)
        language = resp.data.get("language", language)

    if not text or len(text.split()) < 20:
        raise HTTPException(400, "Özetlenecek yeterli metin yok (en az 20 kelime gerekli)")

    word_count = len(text.split())
    lang_hint = {
        "tr": "Türkçe", "turkish": "Türkçe",
        "en": "İngilizce", "english": "İngilizce",
    }.get((language or "").lower(), "transkriptle aynı dilde")

    prompt = f"""Aşağıdaki ses/video transkriptini analiz et ve MUTLAKA geçerli JSON formatında yanıtla:

{{
  "summary": "{lang_hint} dilinde kapsamlı bir özet (2-3 paragraf)",
  "key_points": ["önemli nokta 1", "nokta 2", "..."],
  "keywords": ["anahtar kelime 1", "kelime 2", "..."]
}}

Kurallar:
- summary: 2-3 paragraf, ana fikir ve çıkarımları kapsar
- key_points: 5-10 madde
- keywords: 8-15 kelime veya kısa ifade
- Tüm içerik {lang_hint} dilinde olsun

Transkript:
{text[:12000]}"""

    try:
        api_resp = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "Sen profesyonel bir metin analisti olarak ses/video transkriptlerini analiz eder ve yapılandırılmış JSON özetler üretirsin.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.3,
        )
        result = json.loads(api_resp.choices[0].message.content)
        return JSONResponse({
            "summary": result.get("summary", ""),
            "key_points": result.get("key_points", []),
            "keywords": result.get("keywords", []),
            "word_count": word_count,
            "filename": filename,
            "language": language,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Özetleme hatası: {str(e)}")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/login")
async def login_page():
    return FileResponse("static/login.html")


@app.get("/register")
async def register_page():
    return FileResponse("static/register.html")


@app.get("/forgot")
async def forgot_page():
    return FileResponse("static/forgot.html")


@app.get("/reset-password")
async def reset_password_page():
    return FileResponse("static/reset-password.html")


@app.get("/archive")
async def archive_page():
    return FileResponse("static/archive.html")


@app.get("/profile")
async def profile_page():
    return FileResponse("static/profile.html")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")

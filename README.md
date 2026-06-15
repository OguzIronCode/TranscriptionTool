# Transkript Aracı

<div align="center">

**Live demo:** [transcriptiontool.onrender.com](https://transcriptiontool.onrender.com)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-Whisper_Large_v3-F55036?logo=groq&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL_%2B_Auth-3ECF8E?logo=supabase&logoColor=white)
![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render&logoColor=white)

A full-stack audio and video transcription web application powered by **Groq API (Whisper Large v3)**. Upload files, record from microphone, or paste a YouTube link — get accurate, timestamped transcripts in seconds. Built-in AI summarization, a personal archive, and shareable public links.

</div>

---

> **Note:** Hosted on Render's free tier. If the service hasn't been accessed recently, the first request may take **30–60 seconds** to cold-start. Subsequent requests respond instantly.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Supabase Setup](#supabase-setup)
- [Local Development](#local-development)
- [Environment Variables](#environment-variables)
- [Deploy to Render](#deploy-to-render)
- [Supported Languages](#supported-languages)

---

## Features

### Transcription
- **File upload** — drag & drop or click to select (MP4, MKV, AVI, MOV, WEBM, MP3, WAV, M4A, FLAC, OGG, up to 500 MB)
- **Microphone recording** — in-browser audio capture via MediaRecorder API with live timer
- **YouTube / URL** — paste any video URL; yt-dlp extracts the audio automatically
- **Automatic compression** — ffmpeg compresses input to mono 16 kHz 16 kbps MP3 before sending to Groq, staying within the 25 MB API limit regardless of source size
- **Language selection** — 12 supported languages or auto-detect
- **Timestamped view** — toggle segment-level timestamps on/off
- **Export** — download as plain **.TXT** or **.SRT** subtitle file, or copy to clipboard

### AI Summarization & Reports
- **One-click summary** — sends transcript text to Groq `llama-3.3-70b-versatile` via structured JSON mode
- **Structured output** — returns a paragraph-level **summary**, a bulleted list of **key points** (5–10 items), and **keywords** (8–15 terms)
- **Report download** — formatted **.TXT** report with a fixed template (header, date, language, word count, all three sections)
- **PDF download** — opens a print-optimised HTML page in a new tab and triggers `window.print()` → "Save as PDF"
- Available on both the transcription page (freshly produced transcript) and the archive (any saved transcript)

### Authentication
- Email + password sign-up and sign-in via Supabase Auth
- "Remember me" checkbox — persists session in `localStorage` vs. `sessionStorage`
- Password strength meter on registration
- Forgot password → `resetPasswordForEmail` → reset link email → new-password form
- JWT is sent as a `Bearer` token on every authenticated API request

### Archive
- Every transcript produced by a logged-in user is saved automatically to Supabase
- **Search** — full-text filter across filename and transcript body (client-side, instant)
- **Filters** — language, date range (this week / this month / all time), sort order
- **Tags** — add / remove free-form tags per transcript; click `+ Etiket` inline
- **Inline editing** — click the filename to rename; click "Düzenle" to edit transcript text
- **Bulk operations** — multi-select with checkboxes, then bulk-download as ZIP (TXT or SRT) or bulk-delete
- **Public sharing** — toggle share on/off per transcript; generates a `uuid` share token; link is copied to clipboard automatically
- **AI report** — per-card `📊 Rapor` button opens the summarization modal

### Profile
- Editable username, read-only email
- Avatar upload — stored in Supabase Storage `avatars` bucket; falls back to DiceBear initials SVG
- Usage statistics — total transcripts, total minutes processed, most-used language
- Sign out all devices (`scope: 'global'`)
- Account deletion (with confirmation modal) — deletes all transcripts then removes the Supabase user

### UX
- **Dark / Light mode** toggle — persisted in `localStorage`; FOUC-free via inline IIFE in `theme.js` that runs before CSS
- "Midnight Slate" design system — shared `style.css` with CSS custom properties used across all 8 pages
- Fully responsive, no frontend framework — Vanilla HTML/CSS/JS

---

## Architecture

```
Browser
  │
  ├─ GET /static/*           → FastAPI StaticFiles
  ├─ GET /config             → returns Supabase URL + anon key
  │
  ├─ POST /transcribe        → upload file
  ├─ POST /transcribe-url    → YouTube / URL
  │       │
  │       ├─ yt-dlp (download audio)
  │       ├─ ffmpeg (mono · 16kHz · 16kbps MP3)
  │       └─ Groq Whisper Large v3 → segments + language
  │
  ├─ POST /summarize         → AI report generation
  │       └─ Groq llama-3.3-70b-versatile (JSON mode)
  │
  ├─ GET    /transcripts     → list user's transcripts (Supabase RLS)
  ├─ PUT    /transcripts/:id → update text / filename / tags
  ├─ DELETE /transcripts/:id → delete single transcript
  ├─ POST   /transcripts/:id/share → toggle public link
  │
  ├─ GET /share/:token       → serve share.html (public, no auth)
  ├─ GET /api/share/:token   → fetch shared transcript data
  │
  ├─ GET  /stats             → total transcripts, minutes, top language
  └─ DELETE /account         → delete all data + Supabase user
```

**Auth flow:**
```
Browser ←→ Supabase JS SDK v2 (CDN)
                │  JWT in request header
                ↓
FastAPI → supabase.auth.get_user(token) → user_id
        → supabase.table("transcripts").select(...).eq("user_id", user_id)
```

**Compression pipeline:**
```
Original file (any size / format)
  → ffmpeg -ac 1 -b:a 16k -ar 16000 -y  output.mp3
  → compressed MP3 ≤ 24.5 MB
  → Groq API /audio/transcriptions  (Whisper Large v3)
  → verbose_json response with segments
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | **FastAPI** (Python 3.10+) | REST API, static file serving |
| Async runtime | **uvicorn** | ASGI server |
| Transcription | **Groq API** — Whisper Large v3 | STT model |
| Summarization | **Groq API** — llama-3.3-70b-versatile | LLM, JSON mode |
| Audio processing | **ffmpeg** | Compression, format conversion |
| Video download | **yt-dlp** | YouTube / URL audio extraction |
| Auth + Database | **Supabase** (PostgreSQL + GoTrue) | Users, sessions, transcripts table |
| File storage | **Supabase Storage** | User avatar images |
| Frontend | Vanilla HTML / CSS / JS | No framework |
| Design system | CSS custom properties | Dark/light theme tokens |
| Bulk download | **JSZip** (CDN) | Client-side ZIP generation |
| Deploy | **Render** (`render.yaml`) | PaaS hosting |

---

## Project Structure

```
TranscriptionTool/
├── main.py               # FastAPI app — all endpoints
├── requirements.txt      # Python dependencies
├── render.yaml           # Render deployment config
├── .env                  # Local secrets (not committed)
│
└── static/
    ├── style.css         # Shared design system (CSS tokens, components)
    ├── theme.js          # Dark/light mode — FOUC-free IIFE + toggle handler
    ├── index.html        # Main transcription page (file / mic / URL)
    ├── archive.html      # Transcript archive with search, filters, tags
    ├── profile.html      # User profile, stats, avatar, account management
    ├── share.html        # Public share view (no login required)
    ├── login.html        # Sign in
    ├── register.html     # Sign up with strength meter
    ├── forgot.html       # Password reset request
    └── reset-password.html # New password form
```

---

## API Reference

All authenticated endpoints require `Authorization: Bearer <supabase_jwt>` header.

### `GET /config`
Returns Supabase credentials for the frontend to initialise the JS client.

```json
{
  "supabase_url": "https://xxx.supabase.co",
  "supabase_anon_key": "eyJ..."
}
```

---

### `POST /transcribe`
Transcribe an uploaded audio or video file.

**Request** — `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | File | ✓ | Audio or video file (max 500 MB) |
| `language` | string | — | `tr`, `en`, `de`, … or `auto` |

**Response**
```json
{
  "text": "Full transcript as a single string",
  "segments": [
    { "start": 0.0, "end": 3.5, "text": "Segment text" }
  ],
  "language": "tr",
  "language_probability": 1.0,
  "duration_seconds": 142.8
}
```

If a valid JWT is present the transcript is saved to the `transcripts` table automatically.

---

### `POST /transcribe-url`
Download audio from a URL (YouTube, Twitter/X, etc.) and transcribe.

**Request** — JSON body

```json
{
  "url": "https://youtube.com/watch?v=...",
  "language": "auto"
}
```

**Response** — same shape as `/transcribe`.

---

### `POST /summarize`
Generate an AI summary, key points, and keywords from a transcript.

**Request** — JSON body (one of two forms)

```json
{ "transcript_id": "uuid" }
```
*or*
```json
{
  "text": "Transcript text to summarise...",
  "filename": "video.mp4",
  "language": "tr"
}
```

**Response**
```json
{
  "summary": "Paragraph-level summary of the transcript...",
  "key_points": ["Point one", "Point two", "..."],
  "keywords": ["keyword1", "keyword2", "..."],
  "word_count": 1234,
  "filename": "video.mp4",
  "language": "tr"
}
```

Requires minimum 20 words. Uses `llama-3.3-70b-versatile` with `response_format: json_object`.

---

### `GET /transcripts`
List all transcripts for the authenticated user (newest first).

**Response** — array of transcript objects:
```json
[
  {
    "id": "uuid",
    "filename": "lecture.mp4",
    "language": "tr",
    "created_at": "2026-06-15T10:00:00Z",
    "text": "...",
    "segments": [...],
    "tags": ["ders", "fizik"],
    "duration_seconds": 183.4,
    "is_public": false,
    "share_token": "uuid"
  }
]
```

---

### `PUT /transcripts/:id`
Update a transcript's text, filename, or tags.

**Request** — JSON body (any subset):
```json
{
  "text": "Corrected transcript text",
  "filename": "new-name.mp4",
  "tags": ["tag1", "tag2"]
}
```

---

### `POST /transcripts/:id/share`
Toggle public sharing on/off. Returns new share state and token.

```json
{
  "is_public": true,
  "share_token": "uuid"
}
```

Public share URL: `https://your-domain.com/share/<share_token>`

---

### `DELETE /transcripts/:id`
Delete a single transcript.

---

### `GET /api/share/:token`
Fetch a publicly shared transcript (no auth required).

---

### `GET /stats`
Return usage statistics for the authenticated user.

```json
{
  "total_transcripts": 47,
  "total_minutes": 312.5,
  "top_language": "tr"
}
```

---

### `DELETE /account`
Delete all transcripts then permanently remove the Supabase user account.

---

### `GET /health`
Health check used by Render.

```json
{ "status": "ok" }
```

---

## Supabase Setup

### 1. Create a project
Go to [supabase.com](https://supabase.com), create a new project, and note down:
- **Project URL** → `SUPABASE_URL`
- **anon public key** → `SUPABASE_ANON_KEY`
- **service_role secret** → `SUPABASE_SERVICE_KEY`

### 2. Run the schema SQL
In **SQL Editor**, execute:

```sql
-- Transcripts table
CREATE TABLE IF NOT EXISTS transcripts (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid REFERENCES auth.users ON DELETE CASCADE NOT NULL,
  filename         text NOT NULL,
  language         text,
  text             text,
  segments         jsonb,
  created_at       timestamptz DEFAULT now(),
  tags             text[]  DEFAULT '{}',
  duration_seconds float   DEFAULT 0,
  is_public        bool    DEFAULT false,
  share_token      uuid    DEFAULT gen_random_uuid()
);

-- Row Level Security — users can only see their own rows
ALTER TABLE transcripts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own transcripts"
  ON transcripts FOR ALL
  USING  (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Allow public read of shared transcripts (used by /api/share/:token)
CREATE POLICY "Public can read shared transcripts"
  ON transcripts FOR SELECT
  USING (is_public = true);
```

If you already have a `transcripts` table without the newer columns, run the migrations instead:

```sql
ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS tags             text[]  DEFAULT '{}';
ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS duration_seconds float   DEFAULT 0;
ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS is_public        bool    DEFAULT false;
ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS share_token      uuid    DEFAULT gen_random_uuid();
```

### 3. Create the avatars storage bucket
**Storage → New bucket** — Name: `avatars`, Public: **on**.

### 4. Configure Auth redirect URLs
**Authentication → URL Configuration → Redirect URLs** — add:

```
https://your-domain.com/reset-password
http://localhost:8000/reset-password
```

---

## Local Development

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.10+ | |
| ffmpeg | any recent | must be on `PATH` |
| Groq API key | — | [console.groq.com](https://console.groq.com) — free tier available |
| Supabase project | — | free tier sufficient |

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/OguzHAN/TranscriptionTool.git
cd TranscriptionTool

# 2. Create and activate a virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Create .env with your credentials
cp .env.example .env   # or create manually
```

**.env** contents:
```env
GROQ_API_KEY=gsk_...
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...
```

```bash
# 5. Start the development server
uvicorn main:app --reload
```

Open [http://localhost:8000](http://localhost:8000)

> **ffmpeg installation**
> - **Windows:** `winget install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html)
> - **macOS:** `brew install ffmpeg`
> - **Linux:** `sudo apt install ffmpeg`

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✓ | Groq API key for Whisper and LLM calls |
| `SUPABASE_URL` | ✓ | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | ✓ | Supabase anon/public key (used by frontend JS) |
| `SUPABASE_SERVICE_KEY` | ✓ | Supabase service role key (server-side JWT verification and admin operations) |

---

## Deploy to Render

The repository includes a `render.yaml` that defines the web service. Render reads it automatically.

### Steps

1. Fork or push this repo to GitHub.
2. Go to [render.com](https://render.com) → **New → Web Service**.
3. Connect your GitHub repository.
4. Render detects `render.yaml` and pre-fills the build/start commands:
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Under **Environment Variables**, add all four variables from the table above.
6. Click **Deploy**.

**Health check** is configured at `/health` — Render will restart the service if it returns non-200.

> **Note on ffmpeg:** Render's Python environment includes ffmpeg by default. If you deploy to a different platform, ensure ffmpeg is installed in the build environment.

---

## Supported Languages

| Code | Language |
|---|---|
| `tr` | Turkish |
| `en` | English |
| `de` | German |
| `fr` | French |
| `es` | Spanish |
| `it` | Italian |
| `pt` | Portuguese |
| `ru` | Russian |
| `ja` | Japanese |
| `ko` | Korean |
| `zh` | Chinese |
| `ar` | Arabic |

Select `auto` to let Whisper detect the language automatically.

---

## Audio Compression Pipeline

The compression step is critical for keeping files within Groq's 25 MB API limit while preserving transcription accuracy:

```
Input (any format, up to 500 MB)
  │
  ▼
ffmpeg
  -ac 1          mono channel
  -b:a 16k       16 kbps bitrate
  -ar 16000      16 kHz sample rate (Whisper's native rate)
  -y             overwrite temp file
  │
  ▼
Compressed MP3 (~7 MB per hour of audio)
  │
  ▼
Groq Whisper Large v3 API
```

A 500 MB video file typically compresses to **under 10 MB** of audio. If the compressed file still exceeds 24.5 MB, the API returns a `400` error with a suggestion to split the file.

---

## Report Template (TXT)

When downloading a report as TXT, the following template is used:

```
══════════════════════════════════════════════
   TRANSKRİPT ANALİZ RAPORU
══════════════════════════════════════════════

Dosya        : lecture.mp4
Dil          : TR
Kelime sayısı: 3,412
Tarih        : 15 Haziran 2026

──────────────────────────────────────────────
ÖZET
──────────────────────────────────────────────

[2–3 paragraph summary generated by LLM]

──────────────────────────────────────────────
TEMEL NOKTALAR
──────────────────────────────────────────────

  1. First key point
  2. Second key point
  ...

──────────────────────────────────────────────
ANAHTAR KELİMELER
──────────────────────────────────────────────

  keyword1  ·  keyword2  ·  keyword3  ·  ...

══════════════════════════════════════════════
   Transkript Aracı
══════════════════════════════════════════════
```

---

## License

MIT

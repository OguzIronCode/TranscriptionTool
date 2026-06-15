# TranscriptionTool

A web-based audio and video transcription tool powered by **Groq API (Whisper Large v3)**. Upload any media file, get accurate transcripts with timestamps — fast.

---

## Features

- Drag & drop file upload (MP4, MKV, AVI, MOV, WEBM, MP3, WAV, M4A, FLAC, OGG)
- Automatic audio compression via ffmpeg before sending to Groq API
- Timestamped transcript view with toggle
- Language detection (12 languages supported)
- Export as **TXT** or **SRT**
- Copy to clipboard

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python) |
| Transcription | Groq API — Whisper Large v3 |
| Audio processing | ffmpeg |
| Frontend | Vanilla HTML/CSS/JS |
| Deploy | Render |

## Pipeline

```
Upload (video/audio)
    → ffmpeg compress (mono, 16kHz, 16kbps MP3)
    → Groq API (Whisper Large v3)
    → Timestamped transcript
```

---

## Local Setup

**Requirements:** Python 3.10+, ffmpeg installed on system

```bash
# 1. Clone
git clone https://github.com/OguzHAN/TranscriptionTool.git
cd TranscriptionTool

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set API key
echo "GROQ_API_KEY=your_key_here" > .env

# 4. Run
py -m uvicorn main:app --reload
```

Open [http://localhost:8000](http://localhost:8000)

Get your Groq API key at [console.groq.com](https://console.groq.com)

---

## Deploy to Render

1. Fork or push this repo to GitHub
2. Go to [render.com](https://render.com) → **New → Web Service**
3. Connect your GitHub repository
4. Render will auto-detect `render.yaml`
5. Set `GROQ_API_KEY` in the **Environment Variables** section
6. Deploy

---

## API

### `POST /transcribe`

| Field | Type | Description |
|-------|------|-------------|
| `file` | File | Audio or video file (max 500MB) |
| `language` | string | Language code (`tr`, `en`, `auto`, ...) |

**Response**
```json
{
  "text": "Full transcript text",
  "segments": [
    { "start": 0.0, "end": 3.5, "text": "Hello world" }
  ],
  "language": "en",
  "language_probability": 1.0
}
```

### `GET /health`

Returns `{ "status": "ok" }`

---

## Supported Languages

Turkish · English · German · French · Spanish · Italian · Portuguese · Russian · Japanese · Korean · Chinese · Arabic

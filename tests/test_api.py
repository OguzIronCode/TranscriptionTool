import asyncio
import io

import groq
import httpx
from yt_dlp.utils import DownloadError

from tests.conftest import ALICE, BOB


def upload(client, headers=None, name="clip.mp3", data=b"fake-audio-bytes", lang="tr"):
    return client.post(
        "/transcribe",
        files={"file": (name, io.BytesIO(data), "audio/mpeg")},
        data={"language": lang},
        headers=headers or {},
    )


# ── Genel ────────────────────────────────────────────────────
def test_health_and_config(client):
    assert client.get("/health").json() == {"status": "ok"}
    cfg = client.get("/config")
    assert cfg.json() == {"supabase_url": "https://example.supabase.co", "supabase_anon_key": "anon"}
    assert "service" not in cfg.text


def test_health_degraded_without_ffmpeg(client, monkeypatch):
    import main
    monkeypatch.setattr(main.shutil, "which", lambda n: None)
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["ffmpeg"] is False


def test_pages_and_docs(client):
    for path in ("/", "/login", "/register", "/forgot", "/reset-password", "/archive", "/profile"):
        assert client.get(path).status_code == 200, path
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/static/style.css").status_code == 200


def test_security_headers(client):
    h = client.get("/").headers
    assert h["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "https://example.supabase.co" in h["content-security-policy"]
    assert "microphone=(self)" in h["permissions-policy"]


# ── /transcribe ──────────────────────────────────────────────
def test_transcribe_anonymous_success(client):
    r = upload(client)
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "Merhaba dünya ikinci cümle"
    assert body["segments"][0] == {"start": 0.0, "end": 2.5, "text": "Merhaba dünya"}
    assert body["duration_seconds"] == 5.0 and body["saved"] is False
    assert client.db.tables.get("transcripts") is None


def test_transcribe_logged_in_saves_to_archive(client):
    r = upload(client, ALICE)
    assert r.status_code == 200 and r.json()["saved"] is True
    row = client.db.tables["transcripts"][0]
    assert row["user_id"] == "alice" and row["filename"] == "clip.mp3"


def test_transcribe_still_returns_result_if_archive_fails(client):
    client.db.fail_inserts = True
    r = upload(client, ALICE)
    assert r.status_code == 200 and r.json()["saved"] is False


def test_transcribe_rejects_bad_extension_and_language_and_empty(client):
    assert upload(client, name="evil.exe").status_code == 400
    assert upload(client, name="noext").status_code == 400
    assert upload(client, lang="turkish").status_code == 400
    assert upload(client, data=b"").status_code == 400


def test_transcribe_rejects_oversize(make_client):
    c = make_client(MAX_UPLOAD_MB=1)
    r = upload(c, data=b"x" * (3 * 1024 * 1024))
    assert r.status_code == 413


def test_auto_language_passes_none_to_groq(client):
    upload(client, lang="auto")
    assert client.app.state.groq.calls[-1]["language"] is None


def test_anonymous_rate_limit_then_user_unaffected(make_client):
    c = make_client(RATE_ANON_PER_HOUR=2)
    assert upload(c).status_code == 200
    assert upload(c).status_code == 200
    r = upload(c)
    assert r.status_code == 429 and "Retry-After" in r.headers and "Giriş" in r.json()["detail"]
    assert upload(c, ALICE).status_code == 200      # giriş yapmış kullanıcı ayrı sayılır


def test_user_rate_limit(make_client):
    c = make_client(RATE_USER_PER_HOUR=1)
    assert upload(c, ALICE).status_code == 200
    assert upload(c, ALICE).status_code == 429
    assert upload(c, BOB).status_code == 200


def test_anonymous_disabled_requires_login(make_client):
    c = make_client(ALLOW_ANONYMOUS="false")
    assert upload(c).status_code == 401
    assert upload(c, {"Authorization": "Bearer bogus"}).status_code == 401
    assert upload(c, ALICE).status_code == 200


def test_busy_server_returns_503(make_client):
    c = make_client(MAX_CONCURRENT_JOBS=1, JOB_QUEUE_TIMEOUT="0.05")
    c.app.state.slots = asyncio.Semaphore(0)          # tüm slotlar dolu
    r = upload(c)
    assert r.status_code == 503 and r.headers["Retry-After"] == "30"


def test_slot_released_after_failure(make_client):
    c = make_client(MAX_CONCURRENT_JOBS=1)
    assert upload(c, data=b"").status_code == 400     # slot içinde hata
    assert upload(c).status_code == 200
    assert upload(c).status_code == 200


def test_groq_rate_limit_mapped_to_503(client):
    resp = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com"))

    async def boom(**kw):
        raise groq.RateLimitError("secret-detail", response=resp, body=None)

    client.app.state.groq.audio.transcriptions.create = boom
    r = upload(client)
    assert r.status_code == 503 and "yoğun" in r.json()["detail"] and "secret-detail" not in r.text


def test_unexpected_error_hides_details(make_client, monkeypatch):
    import main
    from fastapi.testclient import TestClient

    async def boom(*a, **k):
        raise RuntimeError("secret internal path /srv/app")

    make_client()
    monkeypatch.setattr(main, "compress_to_mp3", boom)
    with TestClient(main.app, raise_server_exceptions=False) as c:
        r = upload(c)
    assert r.status_code == 500 and "secret" not in r.text


# ── /transcribe-url ──────────────────────────────────────────
def test_url_ssrf_blocked(client):
    for url in ("http://127.0.0.1:8000/", "http://169.254.169.254/", "file:///etc/passwd", "http://localhost/x"):
        assert client.post("/transcribe-url", json={"url": url}).status_code == 400, url


def test_url_success_and_filename(client, monkeypatch):
    import main
    from app import urlcheck
    monkeypatch.setattr(urlcheck, "_resolve", lambda h: ["93.184.216.34"])

    def fake_download(url, workdir, settings, cancel=None):
        path = f"{workdir}/media.webm"
        with open(path, "wb") as f:
            f.write(b"x")
        return path

    monkeypatch.setattr(main, "_download_media", fake_download)
    r = client.post("/transcribe-url", json={"url": "https://example.com/v/abc.mp4?x=1", "language": "en"}, headers=ALICE)
    assert r.status_code == 200 and r.json()["saved"] is True
    assert client.db.tables["transcripts"][0]["filename"] == "abc.mp4"


def test_url_download_error_is_sanitized(client, monkeypatch):
    import main
    from app import urlcheck
    monkeypatch.setattr(urlcheck, "_resolve", lambda h: ["93.184.216.34"])

    def boom(url, workdir, settings, cancel=None):
        raise DownloadError("\x1b[0;31mERROR:\x1b[0m [youtube] abc: Video unavailable")

    monkeypatch.setattr(main, "_download_media", boom)
    r = client.post("/transcribe-url", json={"url": "https://youtu.be/abc"})
    assert r.status_code == 400 and "\x1b" not in r.json()["detail"] and "Video unavailable" in r.json()["detail"]


def test_url_respects_allowlist(make_client, monkeypatch):
    from app import urlcheck
    monkeypatch.setattr(urlcheck, "_resolve", lambda h: ["93.184.216.34"])
    c = make_client(URL_ALLOWED_HOSTS="youtube.com")
    r = c.post("/transcribe-url", json={"url": "https://vimeo.com/1"})
    assert r.status_code == 400 and "izin verilmiyor" in r.json()["detail"]


def test_url_validation_errors(client):
    assert client.post("/transcribe-url", json={"url": ""}).status_code == 422
    assert client.post("/transcribe-url", json={}).status_code == 422


# ── /summarize ───────────────────────────────────────────────
LONG = " ".join(["kelime"] * 40)


def test_summarize_text(client):
    r = client.post("/summarize", json={"text": LONG, "language": "tr"})
    assert r.status_code == 200 and r.json()["summary"] == "özet" and r.json()["word_count"] == 40


def test_summarize_too_short(client):
    assert client.post("/summarize", json={"text": "kısa"}).status_code == 400


def test_summarize_transcript_id_ownership(client):
    upload(client, ALICE)
    tid = client.db.tables["transcripts"][0]["id"]
    assert client.post("/summarize", json={"transcript_id": tid}).status_code == 401
    assert client.post("/summarize", json={"transcript_id": tid}, headers=BOB).status_code == 404
    assert client.post("/summarize", json={"transcript_id": tid}, headers=ALICE).status_code == 400   # metin çok kısa
    assert client.post("/summarize", json={"transcript_id": "not-a-uuid"}, headers=ALICE).status_code == 422


def test_summarize_llm_failure_hides_details(client):
    async def boom(**kw):
        raise RuntimeError("api key gsk_leak")

    client.app.state.groq.chat.completions.create = boom
    r = client.post("/summarize", json={"text": LONG})
    assert r.status_code == 502 and "gsk_leak" not in r.text


def test_summarize_rate_limited(make_client):
    c = make_client(RATE_ANON_PER_HOUR=1)
    assert c.post("/summarize", json={"text": LONG}).status_code == 200
    assert c.post("/summarize", json={"text": LONG}).status_code == 429


# ── Arşiv ────────────────────────────────────────────────────
def test_archive_requires_auth(client):
    for method, path in (("get", "/transcripts"), ("get", "/stats"), ("delete", "/account"),
                         ("post", "/transcripts/00000000-0000-4000-8000-000000000001/share")):
        assert getattr(client, method)(path).status_code == 401, path


def test_archive_list_is_per_user(client):
    upload(client, ALICE, name="alice.mp3")
    upload(client, BOB, name="bob.mp3")
    assert [r["filename"] for r in client.get("/transcripts", headers=ALICE).json()] == ["alice.mp3"]
    assert [r["filename"] for r in client.get("/transcripts", headers=BOB).json()] == ["bob.mp3"]


def test_update_validation_and_ownership(client):
    upload(client, ALICE)
    tid = client.db.tables["transcripts"][0]["id"]
    url = f"/transcripts/{tid}"
    assert client.put(url, json={"tags": ["a", " b "]}, headers=ALICE).status_code == 200
    assert client.db.tables["transcripts"][0]["tags"] == ["a", "b"]
    assert client.put(url, json={"tags": ["x" * 21]}, headers=ALICE).status_code == 422
    assert client.put(url, json={"filename": ""}, headers=ALICE).status_code == 422
    assert client.put(url, json={}, headers=ALICE).status_code == 400
    assert client.put(url, json={"user_id": "bob", "is_public": True}, headers=ALICE).status_code == 400   # izinsiz alanlar yok sayılır
    row = client.db.tables["transcripts"][0]
    assert row["user_id"] == "alice" and row["is_public"] is False
    assert client.put(url, json={"filename": "yeni"}, headers=BOB).status_code == 404
    assert client.put("/transcripts/xyz", json={"filename": "a"}, headers=ALICE).status_code == 422


def test_share_flow(client):
    upload(client, ALICE)
    row = client.db.tables["transcripts"][0]
    tid, token = row["id"], row["share_token"]
    assert client.get(f"/api/share/{token}").status_code == 404                     # varsayılan kapalı
    assert client.post(f"/transcripts/{tid}/share", headers=BOB).status_code == 404
    r = client.post(f"/transcripts/{tid}/share", headers=ALICE)
    assert r.json() == {"is_public": True, "share_token": token}
    shared = client.get(f"/api/share/{token}")
    assert shared.status_code == 200 and "user_id" not in shared.json()
    assert client.get(f"/share/{token}").status_code == 200
    assert client.post(f"/transcripts/{tid}/share", headers=ALICE).json()["is_public"] is False
    assert client.get(f"/api/share/{token}").status_code == 404
    assert client.get("/api/share/not-a-uuid").status_code == 422


def test_delete_stats_and_account(client):
    upload(client, ALICE)
    upload(client, ALICE)
    assert client.get("/stats", headers=ALICE).json() == {"total_transcripts": 2, "total_minutes": 0.2, "top_language": "turkish"}
    tid = client.db.tables["transcripts"][0]["id"]
    assert client.delete(f"/transcripts/{tid}", headers=BOB).status_code == 404
    assert client.delete(f"/transcripts/{tid}", headers=ALICE).status_code == 200
    assert client.delete(f"/transcripts/{tid}", headers=ALICE).status_code == 404
    assert client.delete("/account", headers=ALICE).status_code == 200
    assert client.db.deleted_users == ["alice"] and client.db.tables["transcripts"] == []


# ── Gövde okunmadan önce reddetme ────────────────────────────
def test_oversize_rejected_before_body_is_read(make_client):
    c = make_client(MAX_UPLOAD_MB=1)
    # Gövde gönderilmeden yalnızca başlıkla: middleware 413 döndürmeli, 422/400 değil
    r = c.post("/transcribe", headers={"Content-Length": str(50 * 1024 * 1024), "Content-Type": "multipart/form-data; boundary=x"}, content=b"")
    assert r.status_code == 413


def test_rate_limit_applies_before_body_is_read(make_client):
    c = make_client(RATE_ANON_PER_HOUR=1)
    assert upload(c).status_code == 200
    r = c.post("/transcribe", headers={"Content-Type": "multipart/form-data; boundary=x"}, content=b"")
    assert r.status_code == 429


def test_early_rejections_still_get_security_headers(make_client):
    c = make_client(ALLOW_ANONYMOUS="false")
    r = upload(c)
    assert r.status_code == 401 and r.headers["x-content-type-options"] == "nosniff"


def test_download_cancel_hook_stops_download(monkeypatch):
    import threading
    import pytest
    import main
    from app.config import Settings
    from yt_dlp.utils import DownloadCancelled

    captured = {}

    class FakeYDL:
        def __init__(self, opts):
            captured.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            for hook in captured["progress_hooks"]:
                hook({"status": "downloading"})

    cancel = threading.Event()
    cancel.set()
    s = Settings("g", "https://x.supabase.co", "a", "b")
    import tempfile
    with tempfile.TemporaryDirectory() as d, pytest.raises(DownloadCancelled):
        monkeypatch.setattr(main.yt_dlp, "YoutubeDL", FakeYDL)
        main._download_media("https://example.com/v", d, s, cancel)


def test_summary_model_is_configurable(make_client):
    c = make_client(SUMMARY_MODEL="openai/gpt-oss-20b")
    seen = {}

    async def spy(**kw):
        seen.update(kw)
        import json, types
        content = json.dumps({"summary": "s", "key_points": [], "keywords": []})
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))])

    c.app.state.groq.chat.completions.create = spy
    assert c.post("/summarize", json={"text": LONG}).status_code == 200
    assert seen["model"] == "openai/gpt-oss-20b" and seen["reasoning_effort"] == "low"

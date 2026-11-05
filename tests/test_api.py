import asyncio
import io
import json
import tempfile
import threading
import types

import groq
import httpx
import pytest
from fastapi.testclient import TestClient
from yt_dlp.utils import DownloadCancelled, DownloadError


def upload(client, name="clip.mp3", data=b"fake-audio-bytes", lang="tr"):
    return client.post(
        "/transcribe",
        files={"file": (name, io.BytesIO(data), "audio/mpeg")},
        data={"language": lang},
    )


LONG = " ".join(["kelime"] * 40)


def fake_download(url, workdir, settings, cancel=None):
    path = f"{workdir}/media.webm"
    with open(path, "wb") as f:
        f.write(b"x")
    return path


# ── Genel ────────────────────────────────────────────────────
def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_health_degraded_without_ffmpeg(client, monkeypatch):
    import main
    monkeypatch.setattr(main.shutil, "which", lambda n: None)
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["ffmpeg"] is False


def test_pages(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/theme.js").status_code == 200
    for removed in ("/login", "/archive", "/profile", "/config", "/transcripts", "/docs", "/openapi.json"):
        assert client.get(removed).status_code == 404, removed


def test_security_headers(client):
    h = client.get("/").headers
    assert h["x-content-type-options"] == "nosniff"
    csp = h["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "connect-src 'self'" in csp
    assert "http" not in csp                         # dış kaynak yok
    assert "script-src 'self';" in csp               # satır içi betik yok
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert "microphone=(self)" in h["permissions-policy"]


def test_index_has_no_account_or_external_scripts(client):
    html = client.get("/").text
    for word in ("supabase", "Giriş Yap", "/archive", "cdn.jsdelivr"):
        assert word not in html, word


# ── /transcribe ──────────────────────────────────────────────
def test_transcribe_success(client):
    r = upload(client)
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "Merhaba dünya ikinci cümle"
    assert body["segments"][0] == {"start": 0.0, "end": 2.5, "text": "Merhaba dünya"}
    assert body["duration_seconds"] == 5.0
    assert "saved" not in body


def test_transcribe_rejects_bad_extension_language_and_empty(client):
    assert upload(client, name="evil.exe").status_code == 400
    assert upload(client, name="noext").status_code == 400
    assert upload(client, lang="turkish").status_code == 400
    assert upload(client, data=b"").status_code == 400


def test_transcribe_rejects_oversize(make_client):
    c = make_client(MAX_UPLOAD_MB=1)
    assert upload(c, data=b"x" * (3 * 1024 * 1024)).status_code == 413


def test_auto_language_passes_none_to_groq(client):
    upload(client, lang="auto")
    assert client.app.state.groq.calls[-1]["language"] is None


def test_rate_limit(make_client):
    c = make_client(RATE_PER_HOUR=2)
    assert upload(c).status_code == 200
    assert upload(c).status_code == 200
    r = upload(c)
    assert r.status_code == 429 and "Retry-After" in r.headers and "dakika" in r.json()["detail"]


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

    async def boom(*a, **k):
        raise RuntimeError("secret internal path /srv/app")

    make_client()
    monkeypatch.setattr(main, "compress_to_mp3", boom)
    with TestClient(main.app, raise_server_exceptions=False) as c:
        r = upload(c)
    assert r.status_code == 500 and "secret" not in r.text


# ── Gövde okunmadan önce reddetme ────────────────────────────
def test_oversize_rejected_before_body_is_read(make_client):
    c = make_client(MAX_UPLOAD_MB=1)
    r = c.post("/transcribe", headers={"Content-Length": str(50 * 1024 * 1024), "Content-Type": "multipart/form-data; boundary=x"}, content=b"")
    assert r.status_code == 413


def test_rate_limit_applies_before_body_is_read(make_client):
    c = make_client(RATE_PER_HOUR=1)
    assert upload(c).status_code == 200
    r = c.post("/transcribe", headers={"Content-Type": "multipart/form-data; boundary=x"}, content=b"")
    assert r.status_code == 429 and r.headers["x-content-type-options"] == "nosniff"


# ── /transcribe-url ──────────────────────────────────────────
def test_url_ssrf_blocked(client):
    for url in ("http://127.0.0.1:8000/", "http://169.254.169.254/", "file:///etc/passwd", "http://localhost/x"):
        assert client.post("/transcribe-url", json={"url": url}).status_code == 400, url


def test_url_success(client, monkeypatch):
    import main
    from app import urlcheck
    monkeypatch.setattr(urlcheck, "_resolve", lambda h: ["93.184.216.34"])
    monkeypatch.setattr(main, "_download_media", fake_download)
    r = client.post("/transcribe-url", json={"url": "https://example.com/v/abc.mp4?x=1", "language": "en"})
    assert r.status_code == 200 and r.json()["text"]


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


def test_url_rate_limited(make_client, monkeypatch):
    import main
    from app import urlcheck
    monkeypatch.setattr(urlcheck, "_resolve", lambda h: ["93.184.216.34"])
    monkeypatch.setattr(main, "_download_media", fake_download)
    c = make_client(RATE_PER_HOUR=1)
    assert c.post("/transcribe-url", json={"url": "https://example.com/a"}).status_code == 200
    assert c.post("/transcribe-url", json={"url": "https://example.com/a"}).status_code == 429


def test_url_validation_errors(client):
    assert client.post("/transcribe-url", json={"url": ""}).status_code == 422
    assert client.post("/transcribe-url", json={}).status_code == 422


def test_download_cancel_hook_stops_download(monkeypatch):
    import main
    from app.config import Settings

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
    monkeypatch.setattr(main.yt_dlp, "YoutubeDL", FakeYDL)
    with tempfile.TemporaryDirectory() as d, pytest.raises(DownloadCancelled):
        main._download_media("https://example.com/v", d, Settings("g"), cancel)


# ── /summarize ───────────────────────────────────────────────
def test_summarize(client):
    r = client.post("/summarize", json={"text": LONG, "language": "tr"})
    assert r.status_code == 200 and r.json()["summary"] == "özet" and r.json()["word_count"] == 40


def test_summarize_validation(client):
    assert client.post("/summarize", json={"text": "kısa"}).status_code == 400
    assert client.post("/summarize", json={}).status_code == 422
    assert client.post("/summarize", json={"text": ""}).status_code == 422


def test_summarize_llm_failure_hides_details(client):
    async def boom(**kw):
        raise RuntimeError("api key gsk_leak")

    client.app.state.groq.chat.completions.create = boom
    r = client.post("/summarize", json={"text": LONG})
    assert r.status_code == 502 and "gsk_leak" not in r.text


def test_summarize_rate_limited(make_client):
    c = make_client(RATE_SUMMARY_PER_HOUR=1)
    assert c.post("/summarize", json={"text": LONG}).status_code == 200
    assert c.post("/summarize", json={"text": LONG}).status_code == 429


def test_summary_model_is_configurable(make_client):
    c = make_client(SUMMARY_MODEL="openai/gpt-oss-20b")
    seen = {}

    async def spy(**kw):
        seen.update(kw)
        content = json.dumps({"summary": "s", "key_points": [], "keywords": []})
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))])

    c.app.state.groq.chat.completions.create = spy
    assert c.post("/summarize", json={"text": LONG}).status_code == 200
    assert seen["model"] == "openai/gpt-oss-20b" and seen["reasoning_effort"] == "low"


def test_frontend_uses_relative_urls_so_subpath_hosting_works(client):
    import re
    html = client.get("/").text
    js = client.get("/static/app.js").text
    assert not re.search(r'(?:src|href)="/(?!/)', html), "mutlak yol var"
    assert not re.search(r"fetch\('/", js), "mutlak fetch yolu var"
    for rel in ("static/theme.js", "static/style.css", "static/app.js"):
        assert rel in html
    for rel in ("fetch('transcribe'", "fetch('transcribe-url'", "fetch('summarize'"):
        assert rel in js



# ── SEO ──────────────────────────────────────────────────────
PUBLIC = "https://example.com/transkript/"


def test_seo_tags_when_public_url_set(make_client):
    import json
    import re
    c = make_client(PUBLIC_URL=PUBLIC)
    html = c.get("/").text
    assert "{{" not in html                                           # yer tutucu kalmadı
    assert "<title>Video ve Ses Transkript Aracı" in html
    assert f'<link rel="canonical" href="{PUBLIC}">' in html
    assert f'<meta property="og:url" content="{PUBLIC}">' in html
    assert f'content="{PUBLIC}static/og.png?v=' in html
    assert 'name="description"' in html and 'name="twitter:card"' in html and 'lang="tr"' in html
    assert html.count("<h1") == 1
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    data = [json.loads(b) for b in blocks]                            # geçerli JSON-LD
    assert {d["@type"] for d in data} == {"WebApplication", "FAQPage"}
    faq = next(d for d in data if d["@type"] == "FAQPage")
    for q in faq["mainEntity"]:                                       # SSS görünür içerikle aynı olmalı
        assert q["name"] in html and q["acceptedAnswer"]["text"] in html
    app = next(d for d in data if d["@type"] == "WebApplication")
    assert app["url"] == PUBLIC and app["isAccessibleForFree"] is True


def test_index_without_public_url_has_no_broken_absolute_tags(client):
    html = client.get("/").text
    assert "{{" not in html and 'rel="canonical"' not in html and 'property="og:image"' not in html


def test_index_has_no_inline_script_and_versions_assets(client):
    import re
    html = client.get("/").text
    inline = [m for m in re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*ld\+json)[^>]*>", html)]
    assert inline == []
    assert re.search(r"static/app\.js\?v=[0-9a-f]{10}", html)


def test_robots_and_sitemap(make_client):
    c = make_client(PUBLIC_URL=PUBLIC)
    r = c.get("/robots.txt")
    assert r.status_code == 200 and "Allow: /" in r.text and "Sitemap: https://example.com/transkript/sitemap.xml" in r.text
    s = c.get("/sitemap.xml")
    assert s.status_code == 200 and "<loc>https://example.com/transkript/</loc>" in s.text
    assert s.headers["content-type"].startswith("application/xml")


def test_sitemap_404_without_public_url(client):
    assert client.get("/sitemap.xml").status_code == 404
    assert "Sitemap" not in client.get("/robots.txt").text


def test_static_assets(client):
    for name in ("app.js", "favicon.svg", "og.png", "style.css"):
        r = client.get(f"/static/{name}")
        assert r.status_code == 200 and "max-age" in r.headers["cache-control"], name
    assert client.get("/").headers["cache-control"] == "no-cache"


# ── Güvenlik başlıkları ve sınırlar ──────────────────────────
def test_extra_security_headers(client):
    h = client.get("/").headers
    assert h["x-frame-options"] == "DENY"
    assert h["cross-origin-resource-policy"] == "same-origin"
    assert "payment=()" in h["permissions-policy"]


def test_api_responses_are_not_cacheable_or_indexable(client):
    r = upload(client)
    assert r.headers["cache-control"] == "no-store" and r.headers["x-robots-tag"] == "noindex"
    h = client.get("/health").headers
    assert h["cache-control"] == "no-store" and h["x-robots-tag"] == "noindex"
    assert "x-robots-tag" not in client.get("/").headers


def test_oversized_json_body_rejected(client):
    r = client.post("/summarize", headers={"Content-Length": str(5 * 1024 * 1024), "Content-Type": "application/json"}, content=b"{}")
    assert r.status_code == 413

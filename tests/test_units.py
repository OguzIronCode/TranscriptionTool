import asyncio

import pytest
from fastapi import HTTPException

from app import limits
from app.audio import normalize_language
from app.config import load_settings
from app.limits import RateLimiter
from app.urlcheck import UnsafeUrl, validate_public_url
from tests.conftest import ENV


# ── RateLimiter ──────────────────────────────────────────────
def test_limiter_blocks_after_limit_and_reports_retry():
    rl = RateLimiter(limit=2, window=60)
    assert rl.check("a") == (True, 0)
    assert rl.check("a") == (True, 0)
    ok, retry = rl.check("a")
    assert not ok and 1 <= retry <= 61


def test_limiter_keys_are_independent():
    rl = RateLimiter(limit=1, window=60)
    assert rl.check("a")[0] and rl.check("b")[0]
    assert not rl.check("a")[0]


def test_limiter_window_expires(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(limits.time, "monotonic", lambda: now[0])
    rl = RateLimiter(limit=1, window=60)
    assert rl.check("a")[0]
    assert not rl.check("a")[0]
    now[0] += 61
    assert rl.check("a")[0]


def test_limiter_memory_is_bounded():
    rl = RateLimiter(limit=5, window=3600, max_keys=100)
    for i in range(1000):
        rl.check(f"k{i}")
    assert len(rl._hits) <= 100


# ── URL doğrulama (SSRF) ─────────────────────────────────────
def check(url, **kw):
    return asyncio.run(validate_public_url(url, **kw))


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x", "http://localhost/x", "http://10.0.0.5/x", "http://192.168.1.1/",
    "http://172.16.0.1/", "http://169.254.169.254/latest/meta-data", "http://[::1]/", "http://0.0.0.0/",
    "http://[::ffff:127.0.0.1]/", "http://100.64.0.1/",
])
def test_private_addresses_rejected(url):
    with pytest.raises(UnsafeUrl):
        check(url)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)", "http://user:pw@example.com/",
    "http://example.com:8080/x", "http://", "", "https://" + "a" * 2100,
])
def test_bad_schemes_ports_credentials_rejected(url):
    with pytest.raises(UnsafeUrl):
        check(url)


def test_hostname_resolving_to_private_ip_rejected(monkeypatch):
    from app import urlcheck
    monkeypatch.setattr(urlcheck, "_resolve", lambda host: ["10.1.2.3"])
    with pytest.raises(UnsafeUrl):
        check("https://evil.example.com/video")


def test_hostname_with_mixed_public_and_private_rejected(monkeypatch):
    from app import urlcheck
    monkeypatch.setattr(urlcheck, "_resolve", lambda host: ["93.184.216.34", "127.0.0.1"])
    with pytest.raises(UnsafeUrl):
        check("https://rebind.example.com/")


def test_public_url_accepted(monkeypatch):
    from app import urlcheck
    monkeypatch.setattr(urlcheck, "_resolve", lambda host: ["93.184.216.34"])
    assert check("https://www.youtube.com/watch?v=abc") == "https://www.youtube.com/watch?v=abc"
    assert check("http://8.8.8.8/file.mp3")


def test_allowlist(monkeypatch):
    from app import urlcheck
    monkeypatch.setattr(urlcheck, "_resolve", lambda host: ["93.184.216.34"])
    allowed = ("youtube.com", "youtu.be")
    assert check("https://www.youtube.com/watch?v=1", allowed_hosts=allowed)
    assert check("https://youtu.be/1", allowed_hosts=allowed)
    with pytest.raises(UnsafeUrl):
        check("https://evilyoutube.com/1", allowed_hosts=allowed)
    with pytest.raises(UnsafeUrl):
        check("https://youtube.com.evil.com/1", allowed_hosts=allowed)


# ── Dil kodu ve ayarlar ──────────────────────────────────────
def test_normalize_language():
    assert normalize_language(None) is None
    assert normalize_language("auto") is None
    assert normalize_language(" TR ") == "tr"
    for bad in ("turkish", "t", "tr;rm", "../x"):
        with pytest.raises(HTTPException):
            normalize_language(bad)


def test_settings_missing_env_lists_names(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError) as e:
        load_settings()
    assert "GROQ_API_KEY" in str(e.value) and "SUPABASE_SERVICE_KEY" in str(e.value)


def test_settings_parsing(env):
    env.setenv("ALLOW_ANONYMOUS", "false")
    env.setenv("MAX_UPLOAD_MB", "10")
    env.setenv("URL_ALLOWED_HOSTS", "YouTube.com, .youtu.be ,")
    env.setenv("SUPABASE_URL", "https://x.supabase.co/")
    s = load_settings()
    assert s.allow_anonymous is False
    assert s.max_upload_bytes == 10 * 1024 * 1024
    assert s.url_allowed_hosts == ("youtube.com", "youtu.be")
    assert s.supabase_url == "https://x.supabase.co"


def test_settings_bad_number(env):
    env.setenv("RATE_ANON_PER_HOUR", "abc")
    with pytest.raises(RuntimeError):
        load_settings()

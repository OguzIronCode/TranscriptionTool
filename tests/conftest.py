import json
import types

import pytest
from fastapi.testclient import TestClient

ENV = {"GROQ_API_KEY": "gsk_test"}
OPTIONAL = ("RATE_PER_HOUR", "RATE_SUMMARY_PER_HOUR", "MAX_UPLOAD_MB", "MAX_CONCURRENT_JOBS",
            "JOB_QUEUE_TIMEOUT", "URL_ALLOWED_HOSTS", "SUMMARY_MODEL", "MAX_MEDIA_SECONDS")


class FakeGroq:
    def __init__(self, *a, **k):
        self.calls = []
        self.audio = types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=self._transcribe))
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._chat))

    async def _transcribe(self, **kw):
        self.calls.append(kw)
        return types.SimpleNamespace(
            segments=[{"start": 0.0, "end": 2.5, "text": " Merhaba dünya "}, {"start": 2.5, "end": 5.0, "text": "ikinci cümle"}],
            text="Merhaba dünya ikinci cümle", language="turkish",
        )

    async def _chat(self, **kw):
        content = json.dumps({"summary": "özet", "key_points": ["a"], "keywords": ["k"]})
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))])

    async def close(self):
        pass


@pytest.fixture
def env(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    for k in OPTIONAL:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


@pytest.fixture
def make_client(env):
    """Ortam değişkenlerini ayarlayıp sahte Groq ve ffmpeg ile bir TestClient döndüren fabrika."""
    import main

    created = []

    def factory(**extra_env):
        for k, v in extra_env.items():
            env.setenv(k, str(v))
        env.setattr(main, "AsyncGroq", FakeGroq)
        env.setattr(main.shutil, "which", lambda name: "/usr/bin/ffmpeg")

        async def fake_compress(src, dst, timeout):
            with open(dst, "wb") as f:
                f.write(b"\x00" * 1024)

        env.setattr(main, "compress_to_mp3", fake_compress)
        client = TestClient(main.app, client=("203.0.113.9", 50000))
        client.__enter__()
        created.append(client)
        return client

    yield factory
    for c in created:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()

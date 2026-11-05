import json
import os
import types
from itertools import count

import pytest
from fastapi.testclient import TestClient

ENV = {
    "GROQ_API_KEY": "gsk_test",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_ANON_KEY": "anon",
    "SUPABASE_SERVICE_KEY": "service",
}


# ── Sahte Supabase ───────────────────────────────────────────
class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.op, self.payload, self.filters, self._limit = "select", None, [], None

    def select(self, cols="*"):
        self.op = "select"
        self.cols = None if cols.strip() == "*" else [c.strip() for c in cols.split(",")]
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, k, v):
        self.filters.append((k, v))
        return self

    def order(self, *_, **__):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _match(self, row):
        return all(row.get(k) == v for k, v in self.filters)

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.db.fail_inserts and self.op == "insert":
            raise RuntimeError("db down")
        if self.op == "insert":
            row = {"id": f"00000000-0000-4000-8000-{next(self.db.ids):012d}", "is_public": False,
                   "share_token": f"11111111-1111-4111-8111-{next(self.db.ids):012d}", **self.payload}
            rows.append(row)
            return Result([row])
        hit = [r for r in rows if self._match(r)]
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
        elif self.op == "delete":
            for r in hit:
                rows.remove(r)
        hit = hit[: self._limit] if self._limit else hit
        if self.op == "select" and getattr(self, "cols", None):
            hit = [{c: r.get(c) for c in self.cols} for r in hit]
        return Result(hit)


class FakeAuth:
    def __init__(self, db):
        self.db = db
        self.admin = types.SimpleNamespace(delete_user=lambda uid: db.deleted_users.append(uid))

    def get_user(self, token):
        if token not in self.db.tokens:
            raise ValueError("invalid token")
        return types.SimpleNamespace(user=types.SimpleNamespace(id=self.db.tokens[token]))


class FakeStorage:
    def from_(self, bucket):
        return types.SimpleNamespace(list=lambda path: [], remove=lambda paths: None)


class FakeSupabase:
    def __init__(self):
        self.tables, self.ids, self.deleted_users, self.fail_inserts = {}, count(1), [], False
        self.tokens = {"tok-alice": "alice", "tok-bob": "bob"}
        self.auth = FakeAuth(self)
        self.storage = FakeStorage()

    def table(self, name):
        return Query(self, name)


# ── Sahte Groq ───────────────────────────────────────────────
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
    for k in ("ALLOW_ANONYMOUS", "RATE_ANON_PER_HOUR", "RATE_USER_PER_HOUR", "MAX_UPLOAD_MB",
              "MAX_CONCURRENT_JOBS", "JOB_QUEUE_TIMEOUT", "URL_ALLOWED_HOSTS", "DEBUG"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


@pytest.fixture
def make_client(env):
    """Ortam değişkenlerini ayarlayıp sahte servislerle bir TestClient döndüren fabrika."""
    import main

    created = []

    def factory(**extra_env):
        for k, v in extra_env.items():
            env.setattr(os, "environ", {**os.environ, k: str(v)}) if False else env.setenv(k, str(v))
        db = FakeSupabase()
        env.setattr(main, "create_client", lambda *a, **k: db)
        env.setattr(main, "AsyncGroq", FakeGroq)
        env.setattr(main.shutil, "which", lambda name: "/usr/bin/ffmpeg")

        async def fake_compress(src, dst, timeout):
            with open(dst, "wb") as f:
                f.write(b"\x00" * 1024)

        env.setattr(main, "compress_to_mp3", fake_compress)
        client = TestClient(main.app, client=("203.0.113.9", 50000))
        client.__enter__()
        created.append(client)
        client.db = db
        return client

    yield factory
    for c in created:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()


ALICE = {"Authorization": "Bearer tok-alice"}
BOB = {"Authorization": "Bearer tok-bob"}

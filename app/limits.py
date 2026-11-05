"""Bellekte çalışan kayan pencere hız sınırlayıcı (tek süreç için)."""
import time
from collections import deque


class RateLimiter:
    """`limit` isteğe `window` saniye içinde izin verir. Anahtar başına ayrı sayar."""

    def __init__(self, limit: int, window: float = 3600.0, max_keys: int = 50_000):
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> tuple[bool, int]:
        """(izin verildi mi, yeniden deneme için beklenecek saniye)."""
        now = time.monotonic()
        q = self._hits.get(key)
        if q is None:
            if len(self._hits) >= self.max_keys:
                self._prune(now)
            q = self._hits[key] = deque()
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False, max(1, int(self.window - (now - q[0])) + 1)
        q.append(now)
        return True, 0

    def _prune(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] >= self.window]:
            del self._hits[k]
        if len(self._hits) >= self.max_keys:     # hâlâ doluysa en eskileri at
            for k in sorted(self._hits, key=lambda k: self._hits[k][-1])[: self.max_keys // 10]:
                del self._hits[k]

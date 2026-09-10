from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int | None = None, window_seconds: int = 60) -> None:
        self.limit = int(limit or os.environ.get("ARBITER_PUBLIC_RATE_LIMIT_PER_MINUTE", "120"))
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int, int]:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._events[key]
            while q and q[0] <= cutoff:
                q.popleft()
            remaining = max(0, self.limit - len(q))
            if len(q) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - q[0])))
                return False, 0, retry_after
            q.append(now)
            return True, max(0, remaining - 1), 0


limiter = SlidingWindowLimiter()

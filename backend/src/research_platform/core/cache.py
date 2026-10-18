"""Bounded in-process TTL cache for public upstream responses.

Intraday quotes are deliberately not persisted (docs/decisions.md D13). Research
runs and private results need real storage and provenance; a short-lived public
quote cache only keeps the public endpoints from being hit once per request.

Keys are built by the caller and never contain credentials. Market data is
public, so sharing one cache does not cross a user boundary; personalisation
must not be added here without a scope in the key.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any


@dataclass
class _Entry:
    value: Any
    expires_at: float


class TTLCache:
    def __init__(
        self,
        max_entries: int = 512,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[Hashable, _Entry] = {}
        self._lock = threading.Lock()
        # One creation lock per key currently being fetched (see get_or_create).
        self._pending: dict[Hashable, threading.Lock] = {}

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: Hashable, value: Any, ttl_seconds: float) -> None:
        """Store a value; a non-positive TTL means "do not cache this"."""
        if ttl_seconds <= 0:
            return
        with self._lock:
            if key not in self._entries and len(self._entries) >= self._max_entries:
                self._evict_locked()
            self._entries[key] = _Entry(value, self._clock() + ttl_seconds)

    def get_or_create(self, key: Hashable, ttl_seconds: float, factory: Callable[[], Any]) -> Any:
        """Return the cached value, otherwise call ``factory`` once and store it.

        Concurrent misses for the same key are collapsed: the first caller *holds*
        a per-key lock while it runs ``factory``, and the others block on that lock
        and then read the result from the cache. Without this, two page loads
        arriving together would both hit the upstream endpoint, which is exactly
        what the public quote sources rate limit.

        A non-positive TTL means "do not cache", so a waiter cannot read a result
        and simply takes its turn; the loop always makes progress instead of
        recursing. A ``DomainError`` from ``factory`` is not cached: a transient
        upstream failure must not be replayed for the whole TTL.
        """
        while True:
            cached = self.get(key)
            if cached is not None:
                return cached
            with self._lock:
                creation_lock = self._pending.get(key)
                if creation_lock is None:
                    creation_lock = self._pending[key] = threading.Lock()
                    owner = True
                else:
                    owner = False
            if owner:
                # Hold the creation lock for the whole fetch so waiters actually
                # block; release it before removing the entry so a waiter that
                # wakes up finds either the cached value or a clean slate.
                creation_lock.acquire()
                try:
                    # Re-check after acquiring: between the first ``get()`` above
                    # and registering ``_pending``, another thread may have
                    # completed a fill and removed its entry. Without this second
                    # check this thread becomes the next owner and calls
                    # ``factory`` again even though the cache is already warm.
                    cached = self.get(key)
                    if cached is not None:
                        return cached
                    value = factory()
                    self.set(key, value, ttl_seconds)
                    return value
                finally:
                    creation_lock.release()
                    with self._lock:
                        self._pending.pop(key, None)
            # Another thread is fetching: block until it is done, then loop to
            # re-check the cache (or take over if it failed and cached nothing).
            with creation_lock:
                pass

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _evict_locked(self) -> None:
        oldest = min(self._entries, key=lambda item: self._entries[item].expires_at)
        self._entries.pop(oldest, None)

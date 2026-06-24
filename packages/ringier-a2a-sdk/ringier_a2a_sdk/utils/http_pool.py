"""Lazy, thread-safe process-wide HTTP client singletons.

Several modules keep ONE long-lived pooled httpx client (sync or async) for the process
lifetime instead of building a fresh TCP+TLS connection per call — indexing a catalog or
serving per-request gateway traffic otherwise pays a handshake per call. They all need the
same double-checked-locking lazy-init dance; ``LazyClient`` centralizes it so each call
site declares only *what* client it wants, not *how* to memoize it safely.

The client is intentionally never closed: it is a process-lifetime gateway pool, not a
per-request resource, so there is nothing to clean up at shutdown for these call sites.
"""

import threading
from collections.abc import Callable
from typing import Generic, TypeVar

C = TypeVar("C")


class LazyClient(Generic[C]):
    """A process-wide client built on first use and reused thereafter.

    ``factory`` constructs the client, e.g. ``LazyClient(lambda: httpx.Client(timeout=60))``
    or ``LazyClient(lambda: httpx.AsyncClient(event_hooks=..., timeout=600))``. The lock
    makes init exactly-once even when a *sync* client is shared across executor threads; it
    is uncontended (and harmless) for an async client confined to a single event loop.
    """

    def __init__(self, factory: Callable[[], C]) -> None:
        self._factory = factory
        self._client: C | None = None
        self._lock = threading.Lock()

    def get(self) -> C:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = self._factory()
        return self._client

    def reset(self) -> None:
        """Drop the cached client so the next ``get()`` rebuilds it. For tests only —
        production keeps the single process-lifetime client."""
        with self._lock:
            self._client = None

from __future__ import annotations

import json
import time
from threading import Lock
from typing import Any, cast

import redis

from knowledge_ops.config import get_settings


class CacheBackend:
    def get_json(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int = 300) -> None:
        raise NotImplementedError

    def status(self) -> str:
        raise NotImplementedError

    def increment(self, key: str, ttl_seconds: int) -> int:
        raise NotImplementedError


class MemoryCache(CacheBackend):
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._counters: dict[str, tuple[float, int]] = {}
        self._lock = Lock()

    def get_json(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, payload = item
            if expires_at <= time.time():
                self._items.pop(key, None)
                return None
            return payload

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int = 300) -> None:
        with self._lock:
            self._items[key] = (time.time() + ttl_seconds, value)

    def status(self) -> str:
        return "memory-fallback"

    def increment(self, key: str, ttl_seconds: int) -> int:
        with self._lock:
            expires_at, value = self._counters.get(key, (0.0, 0))
            now = time.time()
            if expires_at <= now:
                expires_at, value = now + ttl_seconds, 0
            value += 1
            self._counters[key] = (expires_at, value)
            return value


class RedisCache(CacheBackend):
    def __init__(self, url: str) -> None:
        self.client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1)

    def get_json(self, key: str) -> dict[str, Any] | None:
        value = cast(str | None, self.client.get(key))
        return json.loads(value) if value else None

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int = 300) -> None:
        self.client.setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False))

    def status(self) -> str:
        try:
            self.client.ping()
            return "redis"
        except redis.RedisError:
            return "redis-unavailable"

    def increment(self, key: str, ttl_seconds: int) -> int:
        try:
            with self.client.pipeline() as pipeline:
                pipeline.incr(key)
                pipeline.expire(key, ttl_seconds, nx=True)
                result = pipeline.execute()
            return int(result[0])
        except redis.RedisError:
            # Rate limiting fails open during a cache outage; the database workflow remains live.
            return 1


_cache: CacheBackend | None = None


def get_cache() -> CacheBackend:
    global _cache
    if _cache is None:
        redis_url = get_settings().redis_url.strip()
        if redis_url:
            candidate = RedisCache(redis_url)
            _cache = candidate if candidate.status() == "redis" else MemoryCache()
        else:
            _cache = MemoryCache()
    return _cache

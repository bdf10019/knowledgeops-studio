from __future__ import annotations

from knowledge_ops.cache import MemoryCache


def test_memory_cache_json_and_counter() -> None:
    cache = MemoryCache()
    cache.set_json("dashboard", {"requests": 3}, ttl_seconds=30)
    assert cache.get_json("dashboard") == {"requests": 3}
    assert cache.increment("rate:user", ttl_seconds=30) == 1
    assert cache.increment("rate:user", ttl_seconds=30) == 2

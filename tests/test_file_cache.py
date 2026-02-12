"""Tests for filesystem-based receipt cache."""

import json
import time
from pathlib import Path

import pytest

from app.cache.file_cache import FileCache


@pytest.fixture
def cache(tmp_path):
    return FileCache(cache_dir=tmp_path / "test_cache")


class TestImageCache:
    def test_set_and_get_image(self, cache):
        data = b"\x89PNG fake image bytes"
        cache.set_image("base", "0xabc", "classic", data)
        result = cache.get_image("base", "0xabc", "classic")
        assert result == data

    def test_get_missing_image(self, cache):
        assert cache.get_image("base", "0xmissing", "classic") is None

    def test_different_templates_stored_separately(self, cache):
        cache.set_image("base", "0xabc", "classic", b"classic_png")
        cache.set_image("base", "0xabc", "dark", b"dark_png")
        assert cache.get_image("base", "0xabc", "classic") == b"classic_png"
        assert cache.get_image("base", "0xabc", "dark") == b"dark_png"


class TestSummaryCache:
    def test_set_and_get_summary(self, cache):
        summary = {"chain": "base", "action_label": "Swapped", "action_detail": "100 USDC → 0.035 ETH"}
        cache.set_summary("base", "0xabc", summary)
        result = cache.get_summary("base", "0xabc")
        assert result["action_label"] == "Swapped"

    def test_get_missing_summary(self, cache):
        assert cache.get_summary("base", "0xmissing") is None

    def test_summary_shared_across_templates(self, cache):
        """Summary is stored per chain:txHash, not per template."""
        summary = {"chain": "base", "action_label": "Sent"}
        cache.set_summary("base", "0xabc", summary)
        # Same hash, any template should get same summary
        result = cache.get_summary("base", "0xabc")
        assert result["action_label"] == "Sent"


class TestNegativeCache:
    def test_pending(self, cache):
        cache.set_negative("base", "0xpending", "pending")
        assert cache.get_negative("base", "0xpending") == "pending"

    def test_not_found(self, cache):
        cache.set_negative("base", "0xgone", "not_found")
        assert cache.get_negative("base", "0xgone") == "not_found"

    def test_missing_negative(self, cache):
        assert cache.get_negative("base", "0xnone") is None

    def test_pending_expires(self, cache):
        cache.set_negative("base", "0xpending", "pending")
        # Manually backdate the file mtime
        path = cache._path(cache._negative_key("base", "0xpending"))
        old_time = time.time() - 25  # 25 seconds ago (TTL is 20)
        import os
        os.utime(path, (old_time, old_time))
        assert cache.get_negative("base", "0xpending") is None

    def test_not_found_expires(self, cache):
        cache.set_negative("base", "0xgone", "not_found")
        path = cache._path(cache._negative_key("base", "0xgone"))
        old_time = time.time() - 35  # 35 seconds ago (TTL is 30)
        import os
        os.utime(path, (old_time, old_time))
        assert cache.get_negative("base", "0xgone") is None


class TestCacheMaintenance:
    def test_clear(self, cache):
        cache.set_image("base", "0x1", "classic", b"data")
        cache.set_summary("base", "0x1", {"a": 1})
        cache.set_negative("base", "0x2", "pending")
        cache.clear()
        assert cache.get_image("base", "0x1", "classic") is None
        assert cache.get_summary("base", "0x1") is None
        assert cache.get_negative("base", "0x2") is None

    def test_cleanup_expired(self, cache):
        cache.set_negative("base", "0xold", "not_found")
        # Backdate beyond TTL
        path = cache._path(cache._negative_key("base", "0xold"))
        old_time = time.time() - 60
        import os
        os.utime(path, (old_time, old_time))

        removed = cache.cleanup_expired()
        assert removed >= 1
        assert cache.get_negative("base", "0xold") is None

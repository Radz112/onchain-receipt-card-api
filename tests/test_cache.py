import time
from unittest.mock import patch

from app.cache.manager import CACHE_MISS, TransactionCache
from app.models.transaction import FeeInfo, NormalizedTransaction


def _make_tx(chain: str = "base", tx_hash: str = "0x" + "ab" * 32) -> NormalizedTransaction:
    return NormalizedTransaction(
        chain=chain,
        tx_hash=tx_hash,
        status="confirmed",
        from_address="0x" + "11" * 20,
        fee=FeeInfo(amount="0.001", token="ETH"),
        raw={},
    )


class TestTransactionCache:
    def test_get_miss(self):
        cache = TransactionCache()
        assert cache.get("base", "0xabc") is CACHE_MISS

    def test_set_and_get(self):
        cache = TransactionCache()
        tx = _make_tx()
        cache.set("base", tx.tx_hash, tx)
        result = cache.get("base", tx.tx_hash)
        assert result is not CACHE_MISS
        assert result.tx_hash == tx.tx_hash

    def test_negative_cache(self):
        cache = TransactionCache()
        cache.set("base", "0xmissing", None, ttl=30)
        result = cache.get("base", "0xmissing")
        assert result is None  # cached None, not CACHE_MISS

    def test_ttl_expiry(self):
        cache = TransactionCache()
        tx = _make_tx()
        cache.set("base", tx.tx_hash, tx, ttl=0.01)

        assert cache.get("base", tx.tx_hash) is not CACHE_MISS

        time.sleep(0.02)

        assert cache.get("base", tx.tx_hash) is CACHE_MISS

    def test_lru_eviction(self):
        cache = TransactionCache(max_entries=3)

        for i in range(3):
            tx = _make_tx(tx_hash=f"0x{i:064x}")
            cache.set("base", tx.tx_hash, tx)

        assert len(cache) == 3

        # Access first entry to make it recently used
        cache.get("base", f"0x{0:064x}")

        # Add a 4th entry — should evict the second (least recently used)
        tx4 = _make_tx(tx_hash=f"0x{99:064x}")
        cache.set("base", tx4.tx_hash, tx4)

        assert len(cache) == 3
        # Second entry (index 1) should be evicted
        assert cache.get("base", f"0x{1:064x}") is CACHE_MISS
        # First entry should still be there (was accessed recently)
        assert cache.get("base", f"0x{0:064x}") is not CACHE_MISS

    def test_pending_tx_gets_short_ttl(self):
        cache = TransactionCache()
        tx = _make_tx()
        tx = tx.model_copy(update={"status": "pending"})
        cache.set("base", tx.tx_hash, tx)

        entry = cache._store[cache._key("base", tx.tx_hash)]
        # Should have a short TTL (15s), not the default 300s
        remaining = entry.expires_at - time.monotonic()
        assert remaining <= 16

    def test_clear(self):
        cache = TransactionCache()
        cache.set("base", "0x1", _make_tx())
        cache.set("base", "0x2", _make_tx())
        assert len(cache) == 2
        cache.clear()
        assert len(cache) == 0

    def test_overwrite_existing_key(self):
        cache = TransactionCache()
        tx1 = _make_tx()
        tx2 = tx1.model_copy(update={"status": "failed"})

        cache.set("base", tx1.tx_hash, tx1)
        cache.set("base", tx1.tx_hash, tx2)

        result = cache.get("base", tx1.tx_hash)
        assert result.status == "failed"
        assert len(cache) == 1

    def test_different_chains_same_hash(self):
        cache = TransactionCache()
        tx_base = _make_tx(chain="base")
        tx_sol = _make_tx(chain="solana")

        cache.set("base", tx_base.tx_hash, tx_base)
        cache.set("solana", tx_sol.tx_hash, tx_sol)

        assert cache.get("base", tx_base.tx_hash).chain == "base"
        assert cache.get("solana", tx_sol.tx_hash).chain == "solana"
        assert len(cache) == 2

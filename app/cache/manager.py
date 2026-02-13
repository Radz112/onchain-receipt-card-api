import time
from collections import OrderedDict

from app.models.transaction import NormalizedTransaction

DEFAULT_TTL = 300  # 5 minutes for confirmed txs
PENDING_TTL = 15   # 15 seconds for pending txs
NOT_FOUND_TTL = 30 # 30 seconds for not-found entries
MAX_ENTRIES = 1000

_SENTINEL = object()


class _CacheEntry:
    __slots__ = ("data", "expires_at")

    def __init__(self, data: NormalizedTransaction | None, ttl: float):
        self.data = data
        self.expires_at = time.monotonic() + ttl


class TransactionCache:
    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._max_entries = max_entries

    @staticmethod
    def _key(chain: str, tx_hash: str) -> str:
        return f"{chain}:{tx_hash}"

    def get(self, chain: str, tx_hash: str) -> NormalizedTransaction | None | object:
        key = self._key(chain, tx_hash)
        entry = self._store.get(key)
        if entry is None:
            return _SENTINEL

        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return _SENTINEL

        self._store.move_to_end(key)
        return entry.data

    def set(
        self,
        chain: str,
        tx_hash: str,
        data: NormalizedTransaction | None,
        ttl: float | None = None,
    ) -> None:
        if ttl is None:
            if data is None:
                ttl = NOT_FOUND_TTL
            elif data.status == "pending":
                ttl = PENDING_TTL
            else:
                ttl = DEFAULT_TTL

        key = self._key(chain, tx_hash)

        if key in self._store:
            del self._store[key]

        self._store[key] = _CacheEntry(data, ttl)

        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


CACHE_MISS = _SENTINEL
tx_cache = TransactionCache()

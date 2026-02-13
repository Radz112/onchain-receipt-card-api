from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# TTLs in seconds
CONFIRMED_TTL = 30 * 86400  # 30 days
PENDING_TTL = 20             # 20 seconds
NOT_FOUND_TTL = 30           # 30 seconds

DEFAULT_CACHE_DIR = Path(".cache/receipts")


class FileCache:
    def __init__(self, cache_dir: Path | str | None = None):
        self._dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _image_key(self, chain: str, tx_hash: str, template: str) -> str:
        return f"receipt_{chain}_{tx_hash}_{template}.png"

    def _summary_key(self, chain: str, tx_hash: str) -> str:
        return f"receipt_{chain}_{tx_hash}.json"

    def _negative_key(self, chain: str, tx_hash: str) -> str:
        return f"neg_{chain}_{tx_hash}.txt"

    def _path(self, key: str) -> Path:
        return self._dir / key

    def _is_expired(self, path: Path, ttl: float) -> bool:
        if not path.exists():
            return True
        age = time.time() - path.stat().st_mtime
        return age > ttl

    def get_image(self, chain: str, tx_hash: str, template: str) -> bytes | None:
        path = self._path(self._image_key(chain, tx_hash, template))
        if not path.exists():
            return None
        if self._is_expired(path, CONFIRMED_TTL):
            path.unlink(missing_ok=True)
            return None
        return path.read_bytes()

    def set_image(self, chain: str, tx_hash: str, template: str, data: bytes) -> Path:
        path = self._path(self._image_key(chain, tx_hash, template))
        path.write_bytes(data)
        return path

    def get_summary(self, chain: str, tx_hash: str) -> dict | None:
        path = self._path(self._summary_key(chain, tx_hash))
        if not path.exists():
            return None
        if self._is_expired(path, CONFIRMED_TTL):
            path.unlink(missing_ok=True)
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupt cache file %s, removing: %s", path, exc)
            path.unlink(missing_ok=True)
            return None

    def set_summary(self, chain: str, tx_hash: str, summary: dict) -> Path:
        path = self._path(self._summary_key(chain, tx_hash))
        path.write_text(json.dumps(summary, default=str))
        return path

    def get_negative(self, chain: str, tx_hash: str) -> str | None:
        path = self._path(self._negative_key(chain, tx_hash))
        if not path.exists():
            return None
        content = path.read_text().strip()
        ttl = PENDING_TTL if content == "pending" else NOT_FOUND_TTL
        if self._is_expired(path, ttl):
            path.unlink(missing_ok=True)
            return None
        return content

    def set_negative(self, chain: str, tx_hash: str, state: str) -> None:
        path = self._path(self._negative_key(chain, tx_hash))
        path.write_text(state)

    def clear(self) -> None:
        for f in self._dir.iterdir():
            if f.is_file():
                f.unlink()

    def cleanup_expired(self) -> int:
        removed = 0
        for f in self._dir.iterdir():
            if not f.is_file():
                continue
            name = f.name
            if name.startswith("neg_"):
                content = f.read_text().strip()
                ttl = PENDING_TTL if content == "pending" else NOT_FOUND_TTL
            elif name.endswith(".png") or name.endswith(".json"):
                ttl = CONFIRMED_TTL
            else:
                continue
            if self._is_expired(f, ttl):
                f.unlink(missing_ok=True)
                removed += 1
        return removed


file_cache = FileCache()

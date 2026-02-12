"""
Token resolver: local registry lookup with on-chain metadata fallback.
200ms timeout on fallback. Permanent in-memory cache for resolved tokens.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.config import settings

_REGISTRY_PATH = Path(__file__).parent / "registry.json"
_registry: dict[str, dict[str, dict]] = {}
_cache: dict[str, dict] = {}  # permanent in-memory cache for on-chain lookups

ONCHAIN_TIMEOUT = 0.2  # 200ms


def _load_registry() -> dict[str, dict[str, dict]]:
    global _registry
    if not _registry:
        with open(_REGISTRY_PATH) as f:
            _registry = json.load(f)
    return _registry


def _truncate_address(address: str) -> str:
    if len(address) > 12:
        return f"{address[:6]}...{address[-4:]}"
    return address


def resolve_token_sync(chain: str, address: str) -> dict:
    """Synchronous registry-only lookup. Returns {symbol, name, decimals}."""
    registry = _load_registry()
    chain_registry = registry.get(chain, {})

    addr_key = address.lower() if chain == "base" else address

    if addr_key in chain_registry:
        return chain_registry[addr_key]

    # Check permanent cache
    cache_key = f"{chain}:{addr_key}"
    if cache_key in _cache:
        return _cache[cache_key]

    return {
        "symbol": _truncate_address(address),
        "name": "Unknown Token",
        "decimals": 18 if chain == "base" else 9,
    }


async def resolve_token(chain: str, address: str) -> dict:
    """Async lookup: registry -> cache -> on-chain fallback (200ms timeout)."""
    registry = _load_registry()
    chain_registry = registry.get(chain, {})

    addr_key = address.lower() if chain == "base" else address

    if addr_key in chain_registry:
        return chain_registry[addr_key]

    cache_key = f"{chain}:{addr_key}"
    if cache_key in _cache:
        return _cache[cache_key]

    # On-chain fallback
    result = None
    if chain == "base":
        result = await _fetch_evm_token_metadata(addr_key)
    elif chain == "solana":
        result = await _fetch_solana_token_metadata(addr_key)

    if result:
        _cache[cache_key] = result
        return result

    fallback = {
        "symbol": _truncate_address(address),
        "name": "Unknown Token",
        "decimals": 18 if chain == "base" else 9,
    }
    _cache[cache_key] = fallback
    return fallback


async def _fetch_evm_token_metadata(address: str) -> dict | None:
    """Fetch symbol(), name(), decimals() from EVM contract."""
    url = settings.base_rpc_url

    # Function selectors
    calls = [
        {"method": "eth_call", "params": [{"to": address, "data": "0x95d89b41"}, "latest"], "id": 1},  # symbol()
        {"method": "eth_call", "params": [{"to": address, "data": "0x06fdde03"}, "latest"], "id": 2},  # name()
        {"method": "eth_call", "params": [{"to": address, "data": "0x313ce567"}, "latest"], "id": 3},  # decimals()
    ]

    try:
        async with httpx.AsyncClient(timeout=ONCHAIN_TIMEOUT) as client:
            responses = []
            for call in calls:
                payload = {"jsonrpc": "2.0", **call}
                resp = await client.post(url, json=payload)
                responses.append(resp.json())
    except (httpx.TimeoutException, httpx.HTTPError):
        return None

    try:
        symbol = _decode_string_result(responses[0].get("result", "0x"))
        name = _decode_string_result(responses[1].get("result", "0x"))
        decimals_hex = responses[2].get("result", "0x12")
        decimals = int(decimals_hex, 16) if decimals_hex and decimals_hex != "0x" else 18
    except Exception:
        return None

    if not symbol:
        return None

    return {"symbol": symbol, "name": name or symbol, "decimals": decimals}


def _decode_string_result(hex_data: str) -> str:
    """Decode ABI-encoded string from eth_call result."""
    if not hex_data or hex_data == "0x" or len(hex_data) < 66:
        return ""
    try:
        data = bytes.fromhex(hex_data[2:])
        # ABI string: offset (32 bytes) + length (32 bytes) + data
        if len(data) < 64:
            return ""
        length = int.from_bytes(data[32:64], "big")
        if length == 0 or length > 256:
            return ""
        return data[64 : 64 + length].decode("utf-8", errors="replace").strip("\x00")
    except Exception:
        return ""


async def _fetch_solana_token_metadata(mint: str) -> dict | None:
    """Fetch SPL token metadata from Solana RPC."""
    url = settings.solana_rpc_url

    # Use getAccountInfo on the mint to get decimals, then try Metaplex for name/symbol
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [mint, {"encoding": "jsonParsed"}],
    }

    try:
        async with httpx.AsyncClient(timeout=ONCHAIN_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
    except (httpx.TimeoutException, httpx.HTTPError):
        return None

    result = resp.json().get("result", {})
    if not result or not result.get("value"):
        return None

    parsed = result["value"].get("data", {})
    if isinstance(parsed, dict) and "parsed" in parsed:
        info = parsed["parsed"].get("info", {})
        decimals = info.get("decimals", 9)
        return {
            "symbol": _truncate_address(mint),
            "name": "SPL Token",
            "decimals": decimals,
        }

    return None

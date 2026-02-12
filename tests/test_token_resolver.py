"""Tests for token resolver: registry lookup, cache, and fallback."""

import pytest

from app.tokens.resolver import _cache, resolve_token, resolve_token_sync


class TestRegistryLookup:
    def test_base_usdc(self):
        result = resolve_token_sync("base", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913")
        assert result["symbol"] == "USDC"
        assert result["decimals"] == 6

    def test_base_native_eth(self):
        result = resolve_token_sync("base", "native")
        assert result["symbol"] == "ETH"
        assert result["decimals"] == 18

    def test_solana_usdc(self):
        result = resolve_token_sync("solana", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
        assert result["symbol"] == "USDC"
        assert result["decimals"] == 6

    def test_solana_native_sol(self):
        result = resolve_token_sync("solana", "native")
        assert result["symbol"] == "SOL"
        assert result["decimals"] == 9

    def test_base_weth(self):
        result = resolve_token_sync("base", "0x4200000000000000000000000000000000000006")
        assert result["symbol"] == "WETH"

    def test_solana_bonk(self):
        result = resolve_token_sync("solana", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
        assert result["symbol"] == "BONK"
        assert result["decimals"] == 5

    def test_case_insensitive_base(self):
        """Base addresses should match case-insensitively."""
        result = resolve_token_sync("base", "0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913")
        assert result["symbol"] == "USDC"


class TestUnknownToken:
    def test_unknown_base_token(self):
        result = resolve_token_sync("base", "0x" + "ff" * 20)
        assert "..." in result["symbol"]
        assert result["name"] == "Unknown Token"
        assert result["decimals"] == 18

    def test_unknown_solana_token(self):
        result = resolve_token_sync("solana", "SomeUnknownMint1111111111111111111111111111")
        assert "..." in result["symbol"]
        assert result["decimals"] == 9


class TestAsyncResolver:
    @pytest.fixture(autouse=True)
    def clear_resolver_cache(self):
        _cache.clear()
        yield
        _cache.clear()

    async def test_registry_hit(self):
        result = await resolve_token("base", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913")
        assert result["symbol"] == "USDC"

    async def test_unknown_gets_cached(self):
        addr = "0x" + "ab" * 20
        result1 = await resolve_token("base", addr)
        assert result1["name"] == "Unknown Token"

        # Should be cached now
        cache_key = f"base:{addr}"
        assert cache_key in _cache

        result2 = await resolve_token("base", addr)
        assert result2 == result1

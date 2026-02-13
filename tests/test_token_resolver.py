"""Tests for token resolver: registry lookup, cache, and fallback."""

import httpx
import pytest
import respx

from app.config import settings
from app.tokens.resolver import (
    _cache,
    _decode_string_result,
    resolve_token,
    resolve_token_sync,
)


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


class TestOnChainFallback:
    """Test the actual on-chain resolution paths with mocked HTTP."""

    @pytest.fixture(autouse=True)
    def clear_resolver_cache(self):
        _cache.clear()
        yield
        _cache.clear()

    @respx.mock
    async def test_evm_onchain_resolution_success(self):
        """Mock eth_call responses for symbol(), name(), decimals()."""
        addr = "0x" + "ee" * 20  # not in registry
        url = settings.base_rpc_url

        # ABI-encode "TEST" as string: offset(32) + length(32) + data(32)
        # offset = 0x20, length = 4, data = "TEST" padded
        symbol_hex = (
            "0x"
            + "0000000000000000000000000000000000000000000000000000000000000020"  # offset
            + "0000000000000000000000000000000000000000000000000000000000000004"  # length
            + "5445535400000000000000000000000000000000000000000000000000000000"  # "TEST"
        )
        name_hex = (
            "0x"
            + "0000000000000000000000000000000000000000000000000000000000000020"
            + "000000000000000000000000000000000000000000000000000000000000000a"  # length=10
            + "5465737420546f6b656e00000000000000000000000000000000000000000000"  # "Test Token"
        )
        decimals_hex = "0x0000000000000000000000000000000000000000000000000000000000000012"  # 18

        respx.post(url).side_effect = [
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": symbol_hex}),
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "result": name_hex}),
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 3, "result": decimals_hex}),
        ]

        result = await resolve_token("base", addr)
        assert result["symbol"] == "TEST"
        assert result["name"] == "Test Token"
        assert result["decimals"] == 18

        # Verify it's cached
        cache_key = f"base:{addr}"
        assert cache_key in _cache

    @respx.mock
    async def test_evm_onchain_timeout_falls_back(self):
        """On-chain call timeout should return fallback, not crash."""
        addr = "0x" + "dd" * 20
        url = settings.base_rpc_url

        respx.post(url).mock(side_effect=httpx.TimeoutException("timeout"))

        result = await resolve_token("base", addr)
        assert result["name"] == "Unknown Token"
        assert "..." in result["symbol"]

    @respx.mock
    async def test_solana_onchain_resolution_success(self):
        """Mock getAccountInfo for SPL token metadata."""
        mint = "SomeNewMint1111111111111111111111111111111111"
        url = settings.solana_rpc_url

        respx.post(url).mock(return_value=httpx.Response(200, json={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "value": {
                    "data": {
                        "parsed": {
                            "info": {"decimals": 8},
                            "type": "mint",
                        },
                        "program": "spl-token",
                    },
                },
            },
        }))

        result = await resolve_token("solana", mint)
        assert result["decimals"] == 8
        assert result["name"] == "SPL Token"

    @respx.mock
    async def test_solana_onchain_timeout_falls_back(self):
        """Solana RPC timeout should return fallback."""
        mint = "AnotherMint11111111111111111111111111111111111"
        url = settings.solana_rpc_url

        respx.post(url).mock(side_effect=httpx.TimeoutException("timeout"))

        result = await resolve_token("solana", mint)
        assert result["name"] == "Unknown Token"
        assert result["decimals"] == 9


class TestDecodeStringResult:
    """Test the ABI string decoder directly."""

    def test_valid_string(self):
        # ABI-encode "USDC"
        hex_data = (
            "0x"
            + "0000000000000000000000000000000000000000000000000000000000000020"
            + "0000000000000000000000000000000000000000000000000000000000000004"
            + "5553444300000000000000000000000000000000000000000000000000000000"
        )
        assert _decode_string_result(hex_data) == "USDC"

    def test_empty_result(self):
        assert _decode_string_result("0x") == ""
        assert _decode_string_result("") == ""
        assert _decode_string_result(None) == ""

    def test_too_short(self):
        assert _decode_string_result("0x1234") == ""

    def test_zero_length_string(self):
        hex_data = (
            "0x"
            + "0000000000000000000000000000000000000000000000000000000000000020"
            + "0000000000000000000000000000000000000000000000000000000000000000"  # length=0
        )
        assert _decode_string_result(hex_data) == ""

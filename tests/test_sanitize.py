"""Tests for input sanitization."""

from app.validation.sanitize import (
    sanitize_action,
    sanitize_address,
    sanitize_note,
    sanitize_protocol,
    sanitize_symbol,
)


class TestSanitizeSymbol:
    def test_normal_symbol(self):
        assert sanitize_symbol("USDC") == "USDC"

    def test_symbol_with_hash(self):
        assert sanitize_symbol("NFT #42") == "NFT #42"

    def test_symbol_too_long(self):
        result = sanitize_symbol("A" * 50)
        assert len(result) == 20

    def test_symbol_with_html(self):
        result = sanitize_symbol("<script>alert(1)</script>")
        assert "<" not in result
        assert ">" not in result

    def test_empty_symbol(self):
        assert sanitize_symbol("") == "?"

    def test_whitespace_stripped(self):
        assert sanitize_symbol("  ETH  ") == "ETH"


class TestSanitizeAddress:
    def test_normal_address(self):
        addr = "0x" + "ab" * 20
        assert sanitize_address(addr) == addr

    def test_too_long_address(self):
        result = sanitize_address("0x" + "a" * 200)
        assert len(result) == 66


class TestSanitizeProtocol:
    def test_normal_protocol(self):
        assert sanitize_protocol("Uniswap V3") == "Uniswap V3"

    def test_too_long_protocol(self):
        result = sanitize_protocol("A" * 100)
        assert len(result) == 50


class TestSanitizeNote:
    def test_normal_note(self):
        assert sanitize_note("Function: 0xabcd1234") == "Function: 0xabcd1234"

    def test_too_long_note(self):
        result = sanitize_note("x" * 200)
        assert len(result) == 100


class TestSanitizeAction:
    def test_sanitizes_token_in(self):
        action = {
            "type": "swap",
            "token_in": {"address": "0x" + "a" * 200, "symbol": "<script>", "amount": "100"},
            "token_out": None,
        }
        result = sanitize_action(action)
        assert len(result["token_in"]["address"]) == 66
        assert "<" not in result["token_in"]["symbol"]

    def test_sanitizes_protocol(self):
        action = {
            "type": "swap",
            "protocol": "X" * 100,
            "token_in": None,
            "token_out": None,
        }
        result = sanitize_action(action)
        assert len(result["protocol"]) == 50

    def test_sanitizes_spender(self):
        action = {
            "type": "approve",
            "spender": "0x" + "f" * 200,
            "token_in": None,
            "token_out": None,
        }
        result = sanitize_action(action)
        assert len(result["spender"]) == 66

    def test_no_crash_on_none_fields(self):
        action = {
            "type": "contract_call",
            "token_in": None,
            "token_out": None,
            "protocol": None,
            "note": None,
            "spender": None,
            "to": None,
            "from_": None,
        }
        result = sanitize_action(action)
        assert result["type"] == "contract_call"

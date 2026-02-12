import pytest
from fastapi import HTTPException

from app.validation.input import validate_chain, validate_tx_hash


class TestValidateChain:
    def test_valid_base(self):
        assert validate_chain("base") == "base"

    def test_valid_solana(self):
        assert validate_chain("solana") == "solana"

    def test_case_insensitive(self):
        assert validate_chain("Base") == "base"
        assert validate_chain("SOLANA") == "solana"

    def test_strips_whitespace(self):
        assert validate_chain("  base  ") == "base"

    def test_invalid_chain(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_chain("ethereum")
        assert exc_info.value.status_code == 400
        assert "Unsupported chain" in exc_info.value.detail

    def test_empty_chain(self):
        with pytest.raises(HTTPException):
            validate_chain("")


class TestValidateTxHashBase:
    def test_valid_hash(self):
        tx = "0x" + "ab" * 32
        assert validate_tx_hash("base", tx) == tx

    def test_valid_hash_mixed_case(self):
        tx = "0x" + "aB" * 32
        assert validate_tx_hash("base", tx) == tx

    def test_missing_0x_prefix(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_tx_hash("base", "ab" * 32)
        assert exc_info.value.status_code == 400

    def test_too_short(self):
        with pytest.raises(HTTPException):
            validate_tx_hash("base", "0x" + "ab" * 31)

    def test_too_long(self):
        with pytest.raises(HTTPException):
            validate_tx_hash("base", "0x" + "ab" * 33)

    def test_invalid_hex_chars(self):
        with pytest.raises(HTTPException):
            validate_tx_hash("base", "0x" + "zz" * 32)

    def test_empty_string(self):
        with pytest.raises(HTTPException):
            validate_tx_hash("base", "")


class TestValidateTxHashSolana:
    def test_valid_signature(self):
        import base58
        sig = base58.b58encode(b"\x01" * 64).decode()
        assert validate_tx_hash("solana", sig) == sig

    def test_invalid_base58(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_tx_hash("solana", "0OIl")  # ambiguous chars not in base58
        # base58 library may or may not reject these; the real test is length
        # Just ensure it doesn't crash unexpectedly

    def test_wrong_length(self):
        import base58
        short_sig = base58.b58encode(b"\x01" * 32).decode()
        with pytest.raises(HTTPException) as exc_info:
            validate_tx_hash("solana", short_sig)
        assert exc_info.value.status_code == 400
        assert "64 bytes" in exc_info.value.detail

    def test_empty_string(self):
        with pytest.raises(HTTPException):
            validate_tx_hash("solana", "")

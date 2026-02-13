"""Tests for the SVG card renderer."""

from app.models.action import Action, NFTInfo, TokenInfo
from app.renderer.card import _apply_decimals, build_summary
from app.renderer.svg_builder import (
    _escape_xml,
    _format_action_text,
    _format_amount,
    _token_color,
    _truncate_address,
    render_receipt_svg,
)


class TestHelpers:
    def test_truncate_address_long(self):
        addr = "0x1234567890abcdef1234567890abcdef12345678"
        assert _truncate_address(addr) == "0x1234...5678"

    def test_truncate_address_short(self):
        assert _truncate_address("0x1234") == "0x1234"

    def test_truncate_address_none(self):
        assert _truncate_address(None) == ""

    def test_token_color_deterministic(self):
        color1 = _token_color("0xabc")
        color2 = _token_color("0xabc")
        assert color1 == color2

    def test_token_color_different_for_different_addresses(self):
        color1 = _token_color("0xabc")
        color2 = _token_color("0xdef")
        assert color1 != color2

    def test_token_color_is_valid_hex(self):
        color = _token_color("0xabc123")
        assert color.startswith("#")
        assert len(color) == 7

    def test_format_amount_large(self):
        assert _format_amount("1500000") == "1,500,000"

    def test_format_amount_normal(self):
        result = _format_amount("1.23456789")
        assert result == "1.2346"

    def test_format_amount_small(self):
        result = _format_amount("0.000123")
        assert result == "0.000123"

    def test_format_amount_zero(self):
        assert _format_amount("0") == "0"

    def test_format_amount_invalid(self):
        assert _format_amount("not_a_number") == "not_a_number"


class TestRenderReceiptSVG:
    def _make_tx_dict(self, chain="base"):
        return {
            "chain": chain,
            "tx_hash": "0x" + "ab" * 32,
            "status": "confirmed",
            "block_number": 12345678,
            "block_time": "2026-02-12T08:00:00+00:00",
            "from_address": "0x" + "11" * 20,
            "to_address": "0x" + "22" * 20,
            "fee": {"amount": "0.0001", "token": "ETH"},
            "raw": {},
        }

    def _make_swap_action(self):
        return Action(
            type="swap",
            primary=True,
            token_in=TokenInfo(address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", symbol="USDC", amount="100", decimals=6),
            token_out=TokenInfo(address="native", symbol="ETH", amount="0.035", decimals=18),
            protocol="Uniswap V3",
        )

    def test_classic_template_generates_valid_svg(self):
        svg = render_receipt_svg(self._make_tx_dict(), [self._make_swap_action()], "classic")
        assert svg.startswith("<svg")
        assert "</svg>" in svg
        assert "ONCHAIN RECEIPT" in svg

    def test_minimal_template(self):
        svg = render_receipt_svg(self._make_tx_dict(), [self._make_swap_action()], "minimal")
        assert "#0D1117" in svg  # minimal background color

    def test_dark_template(self):
        svg = render_receipt_svg(self._make_tx_dict(), [self._make_swap_action()], "dark")
        assert "#0A0A0F" in svg  # dark background color

    def test_swap_action_rendered(self):
        svg = render_receipt_svg(self._make_tx_dict(), [self._make_swap_action()])
        assert "Swapped" in svg
        assert "USDC" in svg
        assert "ETH" in svg
        assert "Uniswap V3" in svg

    def test_transfer_action_rendered(self):
        action = Action(
            type="transfer",
            primary=True,
            token_in=TokenInfo(address="native", symbol="ETH", amount="1.5", decimals=18),
        )
        svg = render_receipt_svg(self._make_tx_dict(), [action])
        assert "Sent" in svg
        assert "ETH" in svg

    def test_confirmed_status_badge(self):
        svg = render_receipt_svg(self._make_tx_dict(), [self._make_swap_action()])
        assert "CONFIRMED" in svg

    def test_failed_status_badge(self):
        tx = self._make_tx_dict()
        tx["status"] = "failed"
        svg = render_receipt_svg(tx, [self._make_swap_action()])
        assert "FAILED" in svg

    def test_pending_status_badge(self):
        tx = self._make_tx_dict()
        tx["status"] = "pending"
        svg = render_receipt_svg(tx, [self._make_swap_action()])
        assert "PENDING" in svg

    def test_null_block_time(self):
        tx = self._make_tx_dict()
        tx["block_time"] = None
        svg = render_receipt_svg(tx, [self._make_swap_action()])
        assert "Timestamp unavailable" in svg

    def test_solana_chain(self):
        tx = self._make_tx_dict(chain="solana")
        tx["fee"] = {"amount": "0.000005", "token": "SOL"}
        action = Action(
            type="swap",
            primary=True,
            token_in=TokenInfo(address="native", symbol="SOL", amount="1.0"),
            token_out=TokenInfo(address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", symbol="USDC", amount="25.0"),
            protocol="Jupiter",
        )
        svg = render_receipt_svg(tx, [action])
        assert "SOLANA" in svg
        assert "#9945FF" in svg  # Solana chain color

    def test_contract_call_action(self):
        action = Action(type="contract_call", primary=True, note="Function: 0xabcd1234")
        svg = render_receipt_svg(self._make_tx_dict(), [action])
        assert "Contract Call" in svg

    def test_nft_transfer_action(self):
        action = Action(
            type="nft_transfer",
            primary=True,
            nft=NFTInfo(token_id="42"),
            token_out=TokenInfo(address="0x" + "dd" * 20, symbol="NFT #42", amount="1", decimals=0),
        )
        svg = render_receipt_svg(self._make_tx_dict(), [action])
        assert "NFT #42" in svg

    def test_powered_by_footer(self):
        svg = render_receipt_svg(self._make_tx_dict(), [self._make_swap_action()])
        assert "powered by APIX402" in svg

    def test_token_circles_rendered(self):
        svg = render_receipt_svg(self._make_tx_dict(), [self._make_swap_action()])
        # Should have circle elements for token visual
        assert "<circle" in svg

    def test_xml_escaping(self):
        """Ensure special characters don't break SVG."""
        action = Action(
            type="transfer",
            primary=True,
            token_in=TokenInfo(address="native", symbol="A<B>C", amount="1"),
        )
        svg = render_receipt_svg(self._make_tx_dict(), [action])
        assert "A&lt;B&gt;C" in svg
        assert "<svg" in svg  # Still valid SVG structure


class TestApplyDecimals:
    """Verify _apply_decimals converts correctly per chain."""

    def test_evm_converts_raw_usdc(self):
        """1 USDC raw (1000000) with 6 decimals → 1.0 on EVM."""
        action = Action(
            type="swap",
            token_in=TokenInfo(address="0xusdc", symbol="USDC", amount="1000000", decimals=6),
        )
        result = _apply_decimals(action, "base")
        assert result.token_in.amount == "1.0"

    def test_evm_converts_small_usdc(self):
        """0.5 USDC raw (500000) with 6 decimals → 0.5 on EVM."""
        action = Action(
            type="transfer",
            token_in=TokenInfo(address="0xusdc", symbol="USDC", amount="500000", decimals=6),
        )
        result = _apply_decimals(action, "base")
        assert result.token_in.amount == "0.5"

    def test_evm_converts_large_eth(self):
        """1 ETH raw (1e18) with 18 decimals → 1.0 on EVM."""
        action = Action(
            type="transfer",
            token_in=TokenInfo(address="native", symbol="ETH", amount="1000000000000000000", decimals=18),
        )
        result = _apply_decimals(action, "base")
        assert result.token_in.amount == "1.0"

    def test_evm_converts_token_out_too(self):
        """Both token_in and token_out should be converted."""
        action = Action(
            type="swap",
            token_in=TokenInfo(address="0xa", symbol="A", amount="1000000", decimals=6),
            token_out=TokenInfo(address="0xb", symbol="B", amount="2000000000000000000", decimals=18),
        )
        result = _apply_decimals(action, "base")
        assert result.token_in.amount == "1.0"
        assert result.token_out.amount == "2.0"

    def test_solana_not_converted(self):
        """Solana amounts are already human-readable — should NOT be touched."""
        action = Action(
            type="swap",
            token_in=TokenInfo(address="mint1", symbol="BONK", amount="2000000.0", decimals=5),
            token_out=TokenInfo(address="native", symbol="SOL", amount="1.5", decimals=9),
        )
        result = _apply_decimals(action, "solana")
        assert result.token_in.amount == "2000000.0"
        assert result.token_out.amount == "1.5"

    def test_evm_zero_decimals_nft(self):
        """NFT with decimals=0 should not divide (0 is falsy, skipped)."""
        action = Action(
            type="nft_transfer",
            token_in=TokenInfo(address="0xnft", symbol="NFT #1", amount="1", decimals=0),
        )
        result = _apply_decimals(action, "base")
        assert result.token_in.amount == "1"


class TestEscapeXml:
    def test_ampersand(self):
        assert _escape_xml("A&B") == "A&amp;B"

    def test_less_than(self):
        assert _escape_xml("A<B") == "A&lt;B"

    def test_greater_than(self):
        assert _escape_xml("A>B") == "A&gt;B"

    def test_double_quote(self):
        assert _escape_xml('A"B') == "A&quot;B"

    def test_single_quote(self):
        assert _escape_xml("A'B") == "A&apos;B"

    def test_all_entities(self):
        assert _escape_xml("&<>\"'") == "&amp;&lt;&gt;&quot;&apos;"

    def test_empty_string(self):
        assert _escape_xml("") == ""

    def test_no_special_chars(self):
        assert _escape_xml("hello world") == "hello world"


class TestFormatActionText:
    def test_swap(self):
        action = Action(
            type="swap",
            token_in=TokenInfo(address="0xa", symbol="USDC", amount="100"),
            token_out=TokenInfo(address="0xb", symbol="ETH", amount="0.035"),
        )
        label, detail = _format_action_text(action)
        assert label == "Swapped"
        assert "USDC" in detail
        assert "ETH" in detail

    def test_transfer_send(self):
        action = Action(
            type="transfer",
            token_in=TokenInfo(address="native", symbol="ETH", amount="1.5"),
        )
        label, detail = _format_action_text(action)
        assert label == "Sent"
        assert "ETH" in detail

    def test_transfer_receive(self):
        action = Action(
            type="transfer",
            token_out=TokenInfo(address="native", symbol="SOL", amount="10"),
        )
        label, detail = _format_action_text(action)
        assert label == "Received"
        assert "SOL" in detail

    def test_transfer_no_tokens(self):
        action = Action(type="transfer")
        label, detail = _format_action_text(action)
        assert label == "Transfer"
        assert detail == ""

    def test_nft_sent(self):
        action = Action(
            type="nft_transfer",
            nft=NFTInfo(token_id="42"),
            token_in=TokenInfo(address="0xa", symbol="NFT #42", amount="1"),
        )
        label, detail = _format_action_text(action)
        assert label == "Sent NFT"
        assert "42" in detail

    def test_nft_received_no_token_id(self):
        action = Action(type="nft_transfer")
        label, detail = _format_action_text(action)
        assert label == "Received NFT"
        assert detail == "NFT"

    def test_approve(self):
        action = Action(type="approve", spender="0x" + "aa" * 20)
        label, detail = _format_action_text(action)
        assert label == "Approved"
        assert "Spender" in detail

    def test_mint(self):
        label, detail = _format_action_text(Action(type="mint"))
        assert label == "Minted"

    def test_burn(self):
        label, detail = _format_action_text(Action(type="burn"))
        assert label == "Burned"

    def test_contract_call(self):
        action = Action(type="contract_call", note="Function: 0xabcdef00")
        label, detail = _format_action_text(action)
        assert label == "Contract Call"
        assert "0xabcdef00" in detail

    def test_overflow(self):
        action = Action(type="overflow", note="and 3 more actions...")
        label, detail = _format_action_text(action)
        assert label == ""
        assert "3 more" in detail

    def test_swap_missing_tokens(self):
        action = Action(type="swap")
        label, detail = _format_action_text(action)
        assert label == "Swapped"
        assert "?" in detail


class TestBuildSummary:
    def _make_tx_dict(self):
        return {
            "chain": "base",
            "tx_hash": "0x" + "ab" * 32,
            "status": "confirmed",
            "block_number": 12345,
            "block_time": "2026-01-01T00:00:00",
            "from_address": "0x" + "11" * 20,
            "to_address": "0x" + "22" * 20,
            "fee": {"amount": "0.001", "token": "ETH"},
        }

    def test_basic_summary(self):
        tx = self._make_tx_dict()
        actions = [Action(type="swap", primary=True,
                          token_in=TokenInfo(address="0xa", symbol="USDC", amount="100"),
                          token_out=TokenInfo(address="0xb", symbol="ETH", amount="0.035"),
                          protocol="Uniswap V3")]
        summary = build_summary(tx, actions)
        assert summary["chain"] == "base"
        assert summary["tx_hash"] == tx["tx_hash"]
        assert summary["status"] == "confirmed"
        assert summary["action_label"] == "Swapped"
        assert "USDC" in summary["action_detail"]
        assert summary["protocol"] == "Uniswap V3"
        assert len(summary["actions"]) == 1

    def test_empty_actions(self):
        tx = self._make_tx_dict()
        summary = build_summary(tx, [])
        assert summary["action_label"] == ""
        assert summary["action_detail"] == ""
        assert summary["protocol"] is None
        assert summary["actions"] == []

    def test_contract_call_summary(self):
        tx = self._make_tx_dict()
        actions = [Action(type="contract_call", primary=True, note="Function: 0xabcd")]
        summary = build_summary(tx, actions)
        assert summary["action_label"] == "Contract Call"
        assert "0xabcd" in summary["action_detail"]

    def test_all_tx_fields_preserved(self):
        tx = self._make_tx_dict()
        actions = [Action(type="transfer", primary=True)]
        summary = build_summary(tx, actions)
        assert summary["block_number"] == 12345
        assert summary["from_address"] == tx["from_address"]
        assert summary["to_address"] == tx["to_address"]
        assert summary["fee"] == tx["fee"]

"""Tests for the SVG card renderer."""

from app.models.action import Action, NFTInfo, TokenInfo
from app.renderer.svg_builder import (
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

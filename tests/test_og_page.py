"""Tests for OG meta page and card image endpoint."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.cache.file_cache import file_cache
from app.main import _build_og_title, app
from app.models.transaction import FeeInfo, NormalizedTransaction

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_file_cache(tmp_path):
    """Use a temp dir for file cache during tests."""
    file_cache._dir = tmp_path / "test_cache"
    file_cache._dir.mkdir(parents=True, exist_ok=True)
    yield
    file_cache.clear()


class TestOGPage:
    def test_og_page_returns_html(self):
        tx = "0x" + "ab" * 32
        resp = client.get(f"/receipt/base/{tx}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_og_page_has_meta_tags(self):
        tx = "0x" + "ab" * 32
        resp = client.get(f"/receipt/base/{tx}")
        html = resp.text
        assert 'og:title' in html
        assert 'og:image' in html
        assert 'twitter:card' in html
        assert 'summary_large_image' in html

    def test_og_page_has_apix402_branding(self):
        tx = "0x" + "ab" * 32
        resp = client.get(f"/receipt/base/{tx}")
        assert "APIX402" in resp.text

    def test_og_page_with_cached_summary(self, tmp_path):
        tx = "0x" + "ab" * 32
        summary = {
            "chain": "base",
            "tx_hash": tx,
            "action_label": "Swapped",
            "action_detail": "100 USDC → 0.035 ETH",
            "status": "confirmed",
        }
        file_cache.set_summary("base", tx, summary)

        resp = client.get(f"/receipt/base/{tx}")
        html = resp.text
        assert "Swapped" in html
        assert "100 USDC" in html

    def test_og_page_without_cached_summary(self):
        tx = "0x" + "cd" * 32
        resp = client.get(f"/receipt/base/{tx}")
        assert resp.status_code == 200
        assert "Transaction on Base" in resp.text

    def test_og_page_invalid_chain(self):
        resp = client.get("/receipt/ethereum/0x" + "ab" * 32)
        assert resp.status_code == 400

    def test_og_page_invalid_tx(self):
        resp = client.get("/receipt/base/not_a_hash")
        assert resp.status_code == 400

    def test_og_page_image_url_format(self):
        tx = "0x" + "ab" * 32
        resp = client.get(f"/receipt/base/{tx}")
        assert f"/v1/receipt/base/card/{tx}/classic.png" in resp.text


class TestReceiptInfoEndpoint:
    def test_get_base_info(self):
        resp = client.get("/v1/receipt/base")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chain"] == "base"
        assert "template" in str(data["usage"])

    def test_get_solana_info(self):
        resp = client.get("/v1/receipt/solana")
        assert resp.status_code == 200
        assert resp.json()["chain"] == "solana"

    def test_get_invalid_chain(self):
        resp = client.get("/v1/receipt/ethereum")
        assert resp.status_code == 400


class TestBuildOgTitle:
    def test_label_and_detail(self):
        summary = {"action_label": "Swapped", "action_detail": "100 USDC → 0.035 ETH", "chain": "base"}
        assert _build_og_title(summary) == "Swapped 100 USDC → 0.035 ETH on Base"

    def test_label_only(self):
        summary = {"action_label": "Contract Call", "action_detail": "", "chain": "solana"}
        assert _build_og_title(summary) == "Contract Call on Solana"

    def test_no_label_no_detail(self):
        summary = {"action_label": "", "action_detail": "", "chain": "base"}
        assert _build_og_title(summary) == "Transaction on Base"

    def test_missing_chain(self):
        summary = {"action_label": "Sent", "action_detail": "1 ETH"}
        assert _build_og_title(summary) == "Sent 1 ETH on "

    def test_empty_summary(self):
        assert _build_og_title({}) == "Transaction on "


class TestPostReceiptGeneration:
    """Integration tests for the POST /v1/receipt/{chain} endpoint."""

    def _make_mock_tx(self):
        return NormalizedTransaction(
            chain="base",
            tx_hash="0x" + "ab" * 32,
            status="confirmed",
            block_number=12345,
            from_address="0x" + "11" * 20,
            to_address="0x" + "22" * 20,
            fee=FeeInfo(amount="0.001", token="ETH"),
            raw={
                "transaction": {
                    "from": "0x" + "11" * 20,
                    "to": "0x" + "22" * 20,
                    "value": "0xde0b6b3a7640000",
                    "input": "0x",
                },
                "receipt": {
                    "from": "0x" + "11" * 20,
                    "logs": [],
                },
            },
        )

    @patch("app.main.fetch_transaction")
    def test_json_response(self, mock_fetch):
        mock_fetch.return_value = self._make_mock_tx()
        resp = client.post("/v1/receipt/base", json={"tx_hash": "0x" + "ab" * 32, "format": "json"})
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "card" in data
        assert data["summary"]["chain"] == "base"
        assert data["card"]["format"] == "json"
        assert data["card"]["cached"] is False

    @patch("app.main.fetch_transaction")
    def test_svg_response(self, mock_fetch):
        mock_fetch.return_value = self._make_mock_tx()
        resp = client.post("/v1/receipt/base", json={"tx_hash": "0x" + "ab" * 32, "format": "svg"})
        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers["content-type"]
        assert resp.text.startswith("<svg")

    @patch("app.main.fetch_transaction")
    def test_invalid_template_defaults_to_classic(self, mock_fetch):
        mock_fetch.return_value = self._make_mock_tx()
        resp = client.post("/v1/receipt/base", json={"tx_hash": "0x" + "ab" * 32, "template": "neon", "format": "svg"})
        assert resp.status_code == 200
        assert "#FFFFFF" in resp.text  # classic background

    @patch("app.main.fetch_transaction")
    def test_invalid_format_defaults_to_json(self, mock_fetch):
        mock_fetch.return_value = self._make_mock_tx()
        resp = client.post("/v1/receipt/base", json={"tx_hash": "0x" + "ab" * 32, "format": "gif"})
        assert resp.status_code == 200
        assert "summary" in resp.json()

    def test_invalid_chain_returns_400(self):
        resp = client.post("/v1/receipt/ethereum", json={"tx_hash": "0x" + "ab" * 32})
        assert resp.status_code == 400

    def test_invalid_tx_hash_returns_400(self):
        resp = client.post("/v1/receipt/base", json={"tx_hash": "not_a_hash"})
        assert resp.status_code == 400

    @patch("app.main.fetch_transaction")
    def test_pending_tx_returns_202(self, mock_fetch):
        mock_fetch.return_value = NormalizedTransaction(
            chain="base",
            tx_hash="0x" + "ab" * 32,
            status="pending",
            from_address="0x" + "11" * 20,
            fee=FeeInfo(amount="0", token="ETH"),
            raw={},
        )
        resp = client.post("/v1/receipt/base", json={"tx_hash": "0x" + "ab" * 32, "format": "json"})
        assert resp.status_code == 202
        assert resp.json()["status"] == "pending"

    @patch("app.main.fetch_transaction")
    def test_cached_json_returns_cached(self, mock_fetch):
        tx = self._make_mock_tx()
        mock_fetch.return_value = tx
        tx_hash = "0x" + "ab" * 32

        # First call populates cache
        client.post("/v1/receipt/base", json={"tx_hash": tx_hash, "format": "json"})

        # Second call should use cache (fetch_transaction not called again)
        mock_fetch.reset_mock()
        resp = client.post("/v1/receipt/base", json={"tx_hash": tx_hash, "format": "json"})
        assert resp.status_code == 200
        assert resp.json()["card"]["cached"] is True
        mock_fetch.assert_not_called()

    @patch("app.main.fetch_transaction")
    def test_negative_cache_not_found(self, mock_fetch):
        from fastapi import HTTPException
        mock_fetch.return_value = None
        tx_hash = "0x" + "cc" * 32

        # First call should 404
        resp = client.post("/v1/receipt/base", json={"tx_hash": tx_hash, "format": "json"})
        assert resp.status_code == 404

        # Second call should hit negative cache (no fetch)
        mock_fetch.reset_mock()
        resp = client.post("/v1/receipt/base", json={"tx_hash": tx_hash, "format": "json"})
        assert resp.status_code == 404
        mock_fetch.assert_not_called()

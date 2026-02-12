"""Tests for OG meta page and card image endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.cache.file_cache import FileCache, file_cache
from app.main import app

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

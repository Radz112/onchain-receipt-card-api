import httpx
import pytest
import respx
from fastapi import HTTPException

from app.config import settings
from app.fetchers.base_fetcher import fetch_base_transaction
from tests.conftest import (
    MOCK_BASE_BLOCK,
    MOCK_BASE_RECEIPT,
    MOCK_BASE_RECEIPT_FAILED,
    MOCK_BASE_RECEIPT_NULL,
    MOCK_BASE_TX,
    MOCK_BASE_TX_NULL,
)

TX_HASH = "0x" + "ab" * 32


@respx.mock
async def test_confirmed_transaction():
    url = settings.base_rpc_url
    respx.post(url).side_effect = [
        httpx.Response(200, json=MOCK_BASE_TX),
        httpx.Response(200, json=MOCK_BASE_RECEIPT),
        httpx.Response(200, json=MOCK_BASE_BLOCK),
    ]

    result = await fetch_base_transaction(TX_HASH)

    assert result.chain == "base"
    assert result.tx_hash == TX_HASH
    assert result.status == "confirmed"
    assert result.from_address == "0x" + "11" * 20
    assert result.to_address == "0x" + "22" * 20
    assert result.fee.token == "ETH"
    assert float(result.fee.amount) > 0
    assert result.block_number == 1


@respx.mock
async def test_failed_transaction():
    url = settings.base_rpc_url
    respx.post(url).side_effect = [
        httpx.Response(200, json=MOCK_BASE_TX),
        httpx.Response(200, json=MOCK_BASE_RECEIPT_FAILED),
        httpx.Response(200, json=MOCK_BASE_BLOCK),
    ]

    result = await fetch_base_transaction(TX_HASH)
    assert result.status == "failed"


@respx.mock
async def test_pending_transaction():
    url = settings.base_rpc_url
    respx.post(url).side_effect = [
        httpx.Response(200, json=MOCK_BASE_TX),
        httpx.Response(200, json=MOCK_BASE_RECEIPT_NULL),
    ]

    result = await fetch_base_transaction(TX_HASH)
    assert result.status == "pending"
    assert result.fee.amount == "0"


@respx.mock
async def test_not_found():
    url = settings.base_rpc_url
    respx.post(url).side_effect = [
        httpx.Response(200, json=MOCK_BASE_TX_NULL),
        httpx.Response(200, json=MOCK_BASE_RECEIPT_NULL),
    ]

    with pytest.raises(HTTPException) as exc_info:
        await fetch_base_transaction(TX_HASH)
    assert exc_info.value.status_code == 404


@respx.mock
async def test_timeout():
    url = settings.base_rpc_url
    respx.post(url).mock(side_effect=httpx.TimeoutException("timeout"))

    with pytest.raises(HTTPException) as exc_info:
        await fetch_base_transaction(TX_HASH)
    assert exc_info.value.status_code == 504

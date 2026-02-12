import httpx
import pytest
import respx
from fastapi import HTTPException

from app.config import settings
from app.fetchers.solana_fetcher import fetch_solana_transaction
from tests.conftest import (
    MOCK_SOLANA_TX,
    MOCK_SOLANA_TX_FAILED,
    MOCK_SOLANA_TX_NULL,
    MOCK_SOLANA_TX_NULL_BLOCKTIME,
)

SIGNATURE = "5" * 88  # placeholder


@respx.mock
async def test_confirmed_transaction():
    url = settings.solana_rpc_url
    respx.post(url).mock(return_value=httpx.Response(200, json=MOCK_SOLANA_TX))

    result = await fetch_solana_transaction(SIGNATURE)

    assert result.chain == "solana"
    assert result.status == "confirmed"
    assert result.from_address == "So11111111111111111111111111111111111111112"
    assert result.to_address == "11111111111111111111111111111111"
    assert result.fee.token == "SOL"
    assert float(result.fee.amount) == 5000 / 1e9
    assert result.block_number == 12345
    assert result.block_time is not None


@respx.mock
async def test_failed_transaction():
    url = settings.solana_rpc_url
    respx.post(url).mock(return_value=httpx.Response(200, json=MOCK_SOLANA_TX_FAILED))

    result = await fetch_solana_transaction(SIGNATURE)
    assert result.status == "failed"


@respx.mock
async def test_null_blocktime():
    url = settings.solana_rpc_url
    respx.post(url).mock(return_value=httpx.Response(200, json=MOCK_SOLANA_TX_NULL_BLOCKTIME))

    result = await fetch_solana_transaction(SIGNATURE)
    assert result.status == "confirmed"
    assert result.block_time is None


@respx.mock
async def test_not_found():
    url = settings.solana_rpc_url
    respx.post(url).mock(return_value=httpx.Response(200, json=MOCK_SOLANA_TX_NULL))

    with pytest.raises(HTTPException) as exc_info:
        await fetch_solana_transaction(SIGNATURE)
    assert exc_info.value.status_code == 404


@respx.mock
async def test_timeout():
    url = settings.solana_rpc_url
    respx.post(url).mock(side_effect=httpx.TimeoutException("timeout"))

    with pytest.raises(HTTPException) as exc_info:
        await fetch_solana_transaction(SIGNATURE)
    assert exc_info.value.status_code == 504

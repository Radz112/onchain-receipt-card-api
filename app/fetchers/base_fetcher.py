import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

from app.config import settings
from app.models.transaction import FeeInfo, NormalizedTransaction

RPC_TIMEOUT = 5.0


def _rpc_payload(method: str, params: list, req_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}


async def fetch_base_transaction(tx_hash: str) -> NormalizedTransaction:
    url = settings.base_rpc_url

    async with httpx.AsyncClient(timeout=RPC_TIMEOUT) as client:
        try:
            tx_resp, receipt_resp = await asyncio.gather(
                client.post(url, json=_rpc_payload("eth_getTransactionByHash", [tx_hash], 1)),
                client.post(url, json=_rpc_payload("eth_getTransactionReceipt", [tx_hash], 2)),
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="RPC request timed out")

    tx_data = tx_resp.json().get("result")
    receipt_data = receipt_resp.json().get("result")

    if tx_data is None and receipt_data is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if tx_data is not None and receipt_data is None:
        return NormalizedTransaction(
            chain="base",
            tx_hash=tx_hash,
            status="pending",
            from_address=tx_data["from"],
            to_address=tx_data.get("to"),
            fee=FeeInfo(amount="0", token="ETH"),
            value=str(int(tx_data.get("value", "0x0"), 16) / 1e18) if tx_data.get("value") else None,
            raw={"transaction": tx_data},
        )

    block_number_hex = receipt_data.get("blockNumber") or (tx_data or {}).get("blockNumber")
    block_number = int(block_number_hex, 16) if block_number_hex else None

    block_time = None
    if block_number_hex:
        try:
            async with httpx.AsyncClient(timeout=RPC_TIMEOUT) as client:
                block_resp = await client.post(
                    url,
                    json=_rpc_payload("eth_getBlockByNumber", [block_number_hex, False], 3),
                )
            block_data = block_resp.json().get("result")
            if block_data and block_data.get("timestamp"):
                block_time = datetime.fromtimestamp(
                    int(block_data["timestamp"], 16), tz=timezone.utc
                )
        except httpx.TimeoutException:
            logger.debug("Block timestamp fetch timed out for block %s", block_number_hex)

    gas_used = int(receipt_data["gasUsed"], 16)
    effective_gas_price = int(receipt_data.get("effectiveGasPrice", "0x0"), 16)
    fee_wei = gas_used * effective_gas_price
    fee_eth = fee_wei / 1e18

    status_code = int(receipt_data["status"], 16)
    status = "confirmed" if status_code == 1 else "failed"

    tx_source = tx_data or {}
    value_hex = tx_source.get("value", "0x0")
    value_wei = int(value_hex, 16)
    value_eth = str(value_wei / 1e18) if value_wei > 0 else None

    return NormalizedTransaction(
        chain="base",
        tx_hash=tx_hash,
        status=status,
        block_number=block_number,
        block_time=block_time,
        from_address=receipt_data.get("from") or tx_source.get("from", ""),
        to_address=receipt_data.get("to") or tx_source.get("to"),
        fee=FeeInfo(amount=str(fee_eth), token="ETH"),
        value=value_eth,
        logs=receipt_data.get("logs"),
        raw={"transaction": tx_data, "receipt": receipt_data},
    )

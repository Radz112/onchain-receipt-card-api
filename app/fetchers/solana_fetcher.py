import logging
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

from app.config import settings
from app.models.transaction import FeeInfo, NormalizedTransaction

logger = logging.getLogger(__name__)
RPC_TIMEOUT = 5.0


async def fetch_solana_transaction(signature: str) -> NormalizedTransaction:
    url = settings.solana_rpc_url
    logger.info("SOLANA RPC: fetching tx %s... from %s", signature[:12], url.split("?")[0])
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"},
        ],
    }

    async with httpx.AsyncClient(timeout=RPC_TIMEOUT) as client:
        try:
            resp = await client.post(url, json=payload)
        except httpx.TimeoutException:
            logger.error("SOLANA RPC TIMEOUT for %s...", signature[:12])
            raise HTTPException(status_code=504, detail="RPC request timed out")

    logger.info("SOLANA RPC RESPONSE: status=%s, body_len=%d", resp.status_code, len(resp.content))
    resp_json = resp.json()
    if resp_json.get("error"):
        logger.error("SOLANA RPC ERROR: %s", resp_json["error"])
    result = resp_json.get("result")
    if result is None:
        logger.warning("SOLANA RPC: result is None for %s...", signature[:12])
        raise HTTPException(status_code=404, detail="Transaction not found")

    meta = result.get("meta", {})
    transaction = result.get("transaction", {})
    message = transaction.get("message", {})

    account_keys = message.get("accountKeys", [])
    from_address = ""
    to_address = None
    if account_keys:
        first = account_keys[0]
        from_address = first["pubkey"] if isinstance(first, dict) else str(first)
        if len(account_keys) > 1:
            second = account_keys[1]
            to_address = second["pubkey"] if isinstance(second, dict) else str(second)

    fee_lamports = meta.get("fee", 0)
    fee_sol = fee_lamports / 1e9

    status = "confirmed" if meta.get("err") is None else "failed"

    block_time = None
    if result.get("blockTime") is not None:
        block_time = datetime.fromtimestamp(result["blockTime"], tz=timezone.utc)

    return NormalizedTransaction(
        chain="solana",
        tx_hash=signature,
        status=status,
        block_number=result.get("slot"),
        block_time=block_time,
        from_address=from_address,
        to_address=to_address,
        fee=FeeInfo(amount=str(fee_sol), token="SOL"),
        logs=meta.get("logMessages"),
        raw=result,
    )

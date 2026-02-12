import re

import base58
from fastapi import HTTPException

SUPPORTED_CHAINS = {"base", "solana"}
EVM_TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def validate_chain(chain: str) -> str:
    chain = chain.lower().strip()
    if chain not in SUPPORTED_CHAINS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported chain '{chain}'. Supported: {', '.join(sorted(SUPPORTED_CHAINS))}",
        )
    return chain


def validate_tx_hash(chain: str, tx_hash: str) -> str:
    tx_hash = tx_hash.strip()

    if chain == "base":
        if not EVM_TX_HASH_RE.match(tx_hash):
            raise HTTPException(
                status_code=400,
                detail="Invalid Base tx hash. Expected 66-char hex string starting with 0x.",
            )
    elif chain == "solana":
        try:
            decoded = base58.b58decode(tx_hash)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid Solana signature. Must be a valid base58 string.",
            )
        if len(decoded) != 64:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid Solana signature. Expected 64 bytes, got {len(decoded)}.",
            )

    return tx_hash

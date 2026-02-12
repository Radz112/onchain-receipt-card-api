from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class FeeInfo(BaseModel):
    amount: str
    token: str


class NormalizedTransaction(BaseModel):
    chain: Literal["base", "solana"]
    tx_hash: str
    status: Literal["confirmed", "failed", "pending"]
    block_number: int | None = None
    block_time: datetime | None = None
    from_address: str
    to_address: str | None = None
    fee: FeeInfo
    value: str | None = None
    logs: list[Any] | None = None
    raw: dict

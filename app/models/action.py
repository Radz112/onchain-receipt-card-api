from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ActionType = Literal[
    "swap", "transfer", "nft_transfer", "mint", "burn", "approve", "contract_call", "overflow"
]


class TokenInfo(BaseModel):
    address: str
    symbol: str = "Unknown"
    amount: str = "0"
    decimals: int = 18


class NFTInfo(BaseModel):
    name: str | None = None
    collection: str | None = None
    token_id: str | None = None


class Action(BaseModel):
    type: ActionType
    primary: bool = False
    token_in: TokenInfo | None = None
    token_out: TokenInfo | None = None
    protocol: str | None = None
    nft: NFTInfo | None = None
    spender: str | None = None
    to: str | None = None
    from_: str | None = None
    count: int | None = None
    note: str | None = None

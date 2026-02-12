from app.fetchers.base_fetcher import fetch_base_transaction
from app.fetchers.solana_fetcher import fetch_solana_transaction
from app.models.transaction import NormalizedTransaction

_FETCHERS = {
    "base": fetch_base_transaction,
    "solana": fetch_solana_transaction,
}


async def fetch_transaction(chain: str, tx_hash: str) -> NormalizedTransaction:
    fetcher = _FETCHERS[chain]
    return await fetcher(tx_hash)

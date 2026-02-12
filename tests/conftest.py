import pytest

from app.cache.manager import tx_cache


@pytest.fixture(autouse=True)
def clear_cache():
    tx_cache.clear()
    yield
    tx_cache.clear()


# --- Mock RPC responses ---

MOCK_BASE_TX = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "hash": "0x" + "ab" * 32,
        "from": "0x" + "11" * 20,
        "to": "0x" + "22" * 20,
        "value": "0xde0b6b3a7640000",  # 1 ETH
        "gasPrice": "0x3b9aca00",
        "blockNumber": "0x1",
        "type": "0x2",
    },
}

MOCK_BASE_RECEIPT = {
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "status": "0x1",
        "blockNumber": "0x1",
        "from": "0x" + "11" * 20,
        "to": "0x" + "22" * 20,
        "gasUsed": "0x5208",  # 21000
        "effectiveGasPrice": "0x3b9aca00",  # 1 gwei
        "logs": [],
    },
}

MOCK_BASE_BLOCK = {
    "jsonrpc": "2.0",
    "id": 3,
    "result": {
        "timestamp": "0x65b0c800",  # 2024-01-24T00:00:00Z
    },
}

MOCK_BASE_TX_NULL = {"jsonrpc": "2.0", "id": 1, "result": None}
MOCK_BASE_RECEIPT_NULL = {"jsonrpc": "2.0", "id": 2, "result": None}

MOCK_BASE_RECEIPT_FAILED = {
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "status": "0x0",
        "blockNumber": "0x1",
        "from": "0x" + "11" * 20,
        "to": "0x" + "22" * 20,
        "gasUsed": "0x5208",
        "effectiveGasPrice": "0x3b9aca00",
        "logs": [],
    },
}

MOCK_SOLANA_TX = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "slot": 12345,
        "blockTime": 1706140800,
        "meta": {
            "fee": 5000,
            "err": None,
            "logMessages": ["Program log: Hello"],
        },
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "So11111111111111111111111111111111111111112", "signer": True},
                    {"pubkey": "11111111111111111111111111111111", "signer": False},
                ],
            },
        },
    },
}

MOCK_SOLANA_TX_FAILED = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "slot": 12345,
        "blockTime": 1706140800,
        "meta": {
            "fee": 5000,
            "err": {"InstructionError": [0, "Custom"]},
            "logMessages": [],
        },
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "So11111111111111111111111111111111111111112", "signer": True},
                ],
            },
        },
    },
}

MOCK_SOLANA_TX_NULL_BLOCKTIME = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "slot": 12345,
        "blockTime": None,
        "meta": {
            "fee": 5000,
            "err": None,
            "logMessages": [],
        },
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "So11111111111111111111111111111111111111112", "signer": True},
                ],
            },
        },
    },
}

MOCK_SOLANA_TX_NULL = {"jsonrpc": "2.0", "id": 1, "result": None}

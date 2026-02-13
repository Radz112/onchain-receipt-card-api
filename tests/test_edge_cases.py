"""Tests for edge case detection in classifiers."""

from app.classifiers import normalize_actions
from app.classifiers.evm_classifier import classify_evm_actions
from app.classifiers.solana_classifier import classify_solana_actions

USER = "0x" + "11" * 20
OTHER = "0x" + "22" * 20
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _pad_address(addr: str) -> str:
    return "0x" + addr[2:].zfill(64)


class TestContractCreation:
    def test_contract_deployment(self):
        """to=None and contractAddress in receipt → contract deployed."""
        raw = {
            "transaction": {"from": USER, "to": None, "value": "0x0", "input": "0x6060604052"},
            "receipt": {
                "from": USER,
                "contractAddress": "0x" + "cc" * 20,
                "logs": [],
            },
        }
        actions = classify_evm_actions(raw)
        assert len(actions) == 1
        assert actions[0].type == "contract_call"
        assert "Contract Deployed" in actions[0].note
        assert actions[0].to == "0x" + "cc" * 20


class TestMulticall:
    def test_multicall_detection(self):
        """Input starts with multicall selector 0xac9650d8 → batch detection."""
        # Fake multicall with ~3 encoded calls
        fake_data = "0xac9650d8" + "00" * 204  # ~3 calls worth of data
        raw = {
            "transaction": {
                "from": USER,
                "to": "0x2626664c2603336e57b271c5c0b26f421741e481",
                "value": "0x0",
                "input": fake_data,
            },
            "receipt": {"from": USER, "logs": []},
        }
        actions = classify_evm_actions(raw)
        assert actions[0].type == "contract_call"
        assert "Batch" in actions[0].note


class TestSolanaVoteTransaction:
    def test_vote_tx_detected(self):
        """Presence of Vote program → Validator Vote."""
        raw = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": "ValidatorPubkey1111111111111111111111111111", "signer": True},
                        {"pubkey": "Vote111111111111111111111111111111111111111", "signer": False},
                    ],
                    "instructions": [],
                },
            },
            "meta": {
                "fee": 5000,
                "err": None,
                "preBalances": [1_000_000_000, 0],
                "postBalances": [999_995_000, 0],
                "preTokenBalances": [],
                "postTokenBalances": [],
            },
        }
        actions = classify_solana_actions(raw)
        assert len(actions) == 1
        assert actions[0].type == "contract_call"
        assert "Validator Vote" in actions[0].note

    def test_non_vote_tx_not_flagged(self):
        """Normal tx without vote program should not be flagged as vote."""
        raw = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": "Signer111111111111111111111111111111111111", "signer": True},
                    ],
                    "instructions": [],
                },
            },
            "meta": {
                "fee": 5000,
                "err": None,
                "preBalances": [1_000_000_000],
                "postBalances": [999_995_000],
                "preTokenBalances": [],
                "postTokenBalances": [],
            },
        }
        actions = classify_solana_actions(raw)
        # Should be contract_call (fallback), not "Validator Vote"
        assert actions[0].note != "Validator Vote"


class TestFailedTransaction:
    def test_evm_failed_still_classifies(self):
        """Failed EVM tx should still classify based on logs/input."""
        raw = {
            "transaction": {"from": USER, "to": OTHER, "value": "0x0", "input": "0xabcdef00"},
            "receipt": {"from": USER, "status": "0x0", "logs": []},
        }
        actions = classify_evm_actions(raw)
        assert len(actions) == 1
        assert actions[0].type == "contract_call"


class TestPureNativeTransfer:
    def test_pure_eth_transfer(self):
        """ETH sent with no logs → simple transfer."""
        raw = {
            "transaction": {"from": USER, "to": OTHER, "value": "0xde0b6b3a7640000", "input": "0x"},
            "receipt": {"from": USER, "logs": []},
        }
        actions = classify_evm_actions(raw)
        assert actions[0].type == "transfer"
        assert actions[0].token_in.address == "native"


class TestNormalizeActions:
    def test_primary_flag_set_on_first(self):
        raw = {
            "transaction": {"from": USER, "to": OTHER, "value": "0xde0b6b3a7640000", "input": "0x"},
            "receipt": {"from": USER, "logs": []},
        }
        actions = normalize_actions(raw, "base")
        assert actions[0].primary is True

    def test_overflow_truncation(self):
        """More than 5 actions should be capped with overflow marker."""
        raw = {
            "transaction": {"from": USER, "to": OTHER, "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    {
                        "address": f"0x{'0' * 39}{i}",
                        "topics": [
                            TRANSFER_TOPIC,
                            _pad_address(f"0x{'0' * 39}{i}"),
                            _pad_address(USER),
                        ],
                        "data": hex(1000000 * (i + 1)),
                    }
                    for i in range(7)
                ],
            },
        }
        actions = normalize_actions(raw, "base")
        assert len(actions) == 5
        assert actions[-1].type == "overflow"
        assert actions[-1].count == 3

    def test_exactly_max_actions_no_overflow(self):
        """Exactly MAX_DISPLAY_ACTIONS should not trigger overflow."""
        raw = {
            "transaction": {"from": USER, "to": OTHER, "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    {
                        "address": f"0x{'0' * 39}{i}",
                        "topics": [
                            TRANSFER_TOPIC,
                            _pad_address(f"0x{'0' * 39}{i}"),
                            _pad_address(USER),
                        ],
                        "data": hex(1000000 * (i + 1)),
                    }
                    for i in range(5)
                ],
            },
        }
        actions = normalize_actions(raw, "base")
        assert all(a.type != "overflow" for a in actions)

    def test_unknown_chain_returns_contract_call(self):
        actions = normalize_actions({}, "ethereum")
        assert len(actions) == 1
        assert actions[0].type == "contract_call"
        assert actions[0].primary is True

    def test_empty_actions_returns_fallback(self):
        """If classifier returns empty list, normalize should return contract_call."""
        raw = {"transaction": {}, "receipt": {"logs": []}}
        actions = normalize_actions(raw, "base")
        assert len(actions) >= 1
        assert actions[0].primary is True

"""Tests for the Solana action classifier using net token delta approach."""

from app.classifiers.solana_classifier import classify_solana_actions

SIGNER = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
BONK_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
JUPITER_PROGRAM = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"


def _make_token_balance(account_index: int, mint: str, amount: float, decimals: int, owner: str) -> dict:
    return {
        "accountIndex": account_index,
        "mint": mint,
        "owner": owner,
        "uiTokenAmount": {
            "uiAmount": amount,
            "decimals": decimals,
            "amount": str(int(amount * (10 ** decimals))),
        },
    }


class TestSwapClassification:
    def test_simple_token_swap(self):
        """User loses USDC, gains BONK → swap."""
        raw = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": SIGNER, "signer": True},
                        {"pubkey": "other_account", "signer": False},
                        {"pubkey": JUPITER_PROGRAM, "signer": False},
                    ],
                    "instructions": [],
                },
            },
            "meta": {
                "fee": 5000,
                "err": None,
                "preBalances": [1_000_000_000, 0, 0],
                "postBalances": [999_995_000, 0, 0],
                "preTokenBalances": [
                    _make_token_balance(0, USDC_MINT, 100.0, 6, SIGNER),
                    _make_token_balance(0, BONK_MINT, 0.0, 5, SIGNER),
                ],
                "postTokenBalances": [
                    _make_token_balance(0, USDC_MINT, 0.0, 6, SIGNER),
                    _make_token_balance(0, BONK_MINT, 50000.0, 5, SIGNER),
                ],
            },
        }
        actions = classify_solana_actions(raw)
        assert actions[0].type == "swap"
        assert actions[0].protocol == "Jupiter"
        assert float(actions[0].token_in.amount) == 100.0
        assert float(actions[0].token_out.amount) == 50000.0

    def test_swap_sol_for_token(self):
        """User loses SOL (beyond fee), gains USDC → swap."""
        raw = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": SIGNER, "signer": True},
                    ],
                    "instructions": [],
                },
            },
            "meta": {
                "fee": 5000,
                "err": None,
                "preBalances": [2_000_000_000, 0],
                "postBalances": [1_000_000_000, 0],
                "preTokenBalances": [
                    _make_token_balance(0, USDC_MINT, 0.0, 6, SIGNER),
                ],
                "postTokenBalances": [
                    _make_token_balance(0, USDC_MINT, 50.0, 6, SIGNER),
                ],
            },
        }
        actions = classify_solana_actions(raw)
        assert actions[0].type == "swap"
        assert actions[0].token_in.address == "native"  # SOL
        assert actions[0].token_out.address == USDC_MINT


class TestTransferClassification:
    def test_token_send(self):
        """User sends USDC, no incoming → transfer."""
        raw = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": SIGNER, "signer": True},
                    ],
                    "instructions": [],
                },
            },
            "meta": {
                "fee": 5000,
                "err": None,
                "preBalances": [1_000_000_000],
                "postBalances": [999_995_000],
                "preTokenBalances": [
                    _make_token_balance(0, USDC_MINT, 100.0, 6, SIGNER),
                ],
                "postTokenBalances": [
                    _make_token_balance(0, USDC_MINT, 50.0, 6, SIGNER),
                ],
            },
        }
        actions = classify_solana_actions(raw)
        assert actions[0].type == "transfer"
        assert actions[0].token_in.address == USDC_MINT
        assert float(actions[0].token_in.amount) == 50.0

    def test_token_receive(self):
        """User receives USDC → transfer (received)."""
        raw = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": SIGNER, "signer": True},
                    ],
                    "instructions": [],
                },
            },
            "meta": {
                "fee": 5000,
                "err": None,
                "preBalances": [1_000_000_000],
                "postBalances": [999_995_000],
                "preTokenBalances": [
                    _make_token_balance(0, USDC_MINT, 0.0, 6, SIGNER),
                ],
                "postTokenBalances": [
                    _make_token_balance(0, USDC_MINT, 25.0, 6, SIGNER),
                ],
            },
        }
        actions = classify_solana_actions(raw)
        assert actions[0].type == "transfer"
        assert actions[0].token_out.address == USDC_MINT


class TestNFTClassification:
    def test_nft_transfer_detected(self):
        """SPL transfer with decimals=0 and amount=1 → nft_transfer."""
        nft_mint = "NFTmint1111111111111111111111111111111111111"
        raw = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": SIGNER, "signer": True},
                    ],
                    "instructions": [],
                },
            },
            "meta": {
                "fee": 5000,
                "err": None,
                "preBalances": [1_000_000_000],
                "postBalances": [999_995_000],
                "preTokenBalances": [
                    _make_token_balance(0, nft_mint, 0.0, 0, SIGNER),
                ],
                "postTokenBalances": [
                    _make_token_balance(0, nft_mint, 1.0, 0, SIGNER),
                ],
            },
        }
        actions = classify_solana_actions(raw)
        assert any(a.type == "nft_transfer" for a in actions)


class TestProtocolLabeling:
    def test_jupiter_detected(self):
        raw = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": SIGNER, "signer": True},
                        {"pubkey": JUPITER_PROGRAM, "signer": False},
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
        assert actions[0].protocol == "Jupiter"

    def test_no_known_program(self):
        raw = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": SIGNER, "signer": True},
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
        assert actions[0].protocol is None


class TestFallbackClassification:
    def test_no_deltas(self):
        """No meaningful balance changes → contract_call."""
        raw = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": SIGNER, "signer": True},
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
        assert actions[0].type == "contract_call"

    def test_empty_signer(self):
        raw = {
            "transaction": {"message": {"accountKeys": []}},
            "meta": {"fee": 0, "preBalances": [], "postBalances": [], "preTokenBalances": [], "postTokenBalances": []},
        }
        actions = classify_solana_actions(raw)
        assert actions == []

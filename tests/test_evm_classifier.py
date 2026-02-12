"""Tests for the EVM action classifier using net token delta approach."""

from app.classifiers.evm_classifier import classify_evm_actions

USER = "0x" + "11" * 20
OTHER = "0x" + "22" * 20
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
WETH = "0x4200000000000000000000000000000000000006"

# ERC20 Transfer topic
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
WETH_DEPOSIT = "0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c"
WETH_WITHDRAWAL = "0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65"
APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"


def _pad_address(addr: str) -> str:
    """Pad address to 32 bytes for event topics."""
    return "0x" + addr[2:].zfill(64)


def _encode_uint256(value: int) -> str:
    return hex(value)


class TestSwapClassification:
    def test_simple_swap_usdc_for_token(self):
        """User sends USDC, receives another token → swap."""
        token_b = "0x" + "bb" * 20
        raw = {
            "transaction": {"from": USER, "to": "0x2626664c2603336e57b271c5c0b26f421741e481", "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    # User sends 100 USDC
                    {
                        "address": USDC,
                        "topics": [TRANSFER_TOPIC, _pad_address(USER), _pad_address(OTHER)],
                        "data": _encode_uint256(100_000_000),  # 100 USDC (6 decimals)
                    },
                    # User receives token B
                    {
                        "address": token_b,
                        "topics": [TRANSFER_TOPIC, _pad_address(OTHER), _pad_address(USER)],
                        "data": _encode_uint256(50_000_000_000_000_000_000),  # 50 tokens (18 decimals)
                    },
                ],
            },
        }
        actions = classify_evm_actions(raw)
        assert len(actions) >= 1
        assert actions[0].type == "swap"
        assert actions[0].token_in.address == USDC
        assert actions[0].token_out.address == token_b
        assert actions[0].protocol == "Uniswap V3"

    def test_swap_with_weth_unwrap(self):
        """User swaps token for ETH via WETH unwrap → should be classified as swap, not WETH transfer."""
        raw = {
            "transaction": {"from": USER, "to": "0x2626664c2603336e57b271c5c0b26f421741e481", "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    # User sends USDC
                    {
                        "address": USDC,
                        "topics": [TRANSFER_TOPIC, _pad_address(USER), _pad_address(OTHER)],
                        "data": _encode_uint256(100_000_000),
                    },
                    # WETH Withdrawal event (user unwraps WETH → ETH)
                    {
                        "address": WETH,
                        "topics": [WETH_WITHDRAWAL, _pad_address(USER)],
                        "data": _encode_uint256(50_000_000_000_000_000),  # 0.05 ETH
                    },
                    # WETH transferred to user (ERC20 transfer part of unwrap)
                    {
                        "address": WETH,
                        "topics": [TRANSFER_TOPIC, _pad_address(OTHER), _pad_address(USER)],
                        "data": _encode_uint256(50_000_000_000_000_000),
                    },
                ],
            },
        }
        actions = classify_evm_actions(raw)
        assert actions[0].type == "swap"
        # tokenOut should be native ETH, not WETH
        assert actions[0].token_out.address == "native"

    def test_swap_with_native_eth_sent(self):
        """User sends ETH (tx.value > 0) and receives token → swap."""
        token_b = "0x" + "cc" * 20
        raw = {
            "transaction": {"from": USER, "to": OTHER, "value": "0xde0b6b3a7640000", "input": "0x"},  # 1 ETH
            "receipt": {
                "from": USER,
                "logs": [
                    {
                        "address": token_b,
                        "topics": [TRANSFER_TOPIC, _pad_address(OTHER), _pad_address(USER)],
                        "data": _encode_uint256(1000_000_000),
                    },
                ],
            },
        }
        actions = classify_evm_actions(raw)
        assert actions[0].type == "swap"
        assert actions[0].token_in.address == "native"


class TestTransferClassification:
    def test_erc20_send(self):
        """User sends tokens, nothing received → transfer."""
        raw = {
            "transaction": {"from": USER, "to": USDC, "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    {
                        "address": USDC,
                        "topics": [TRANSFER_TOPIC, _pad_address(USER), _pad_address(OTHER)],
                        "data": _encode_uint256(100_000_000),
                    },
                ],
            },
        }
        actions = classify_evm_actions(raw)
        assert actions[0].type == "transfer"
        assert actions[0].token_in.address == USDC

    def test_erc20_receive(self):
        """User receives tokens → transfer (received)."""
        raw = {
            "transaction": {"from": USER, "to": USDC, "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    {
                        "address": USDC,
                        "topics": [TRANSFER_TOPIC, _pad_address(OTHER), _pad_address(USER)],
                        "data": _encode_uint256(50_000_000),
                    },
                ],
            },
        }
        actions = classify_evm_actions(raw)
        assert actions[0].type == "transfer"
        assert actions[0].token_out.address == USDC

    def test_native_eth_transfer(self):
        """Pure ETH transfer with no logs → transfer."""
        raw = {
            "transaction": {"from": USER, "to": OTHER, "value": "0xde0b6b3a7640000", "input": "0x"},
            "receipt": {"from": USER, "logs": []},
        }
        actions = classify_evm_actions(raw)
        assert actions[0].type == "transfer"
        assert actions[0].token_in.address == "native"


class TestNFTClassification:
    def test_erc721_transfer(self):
        """ERC721 Transfer with 3 indexed topics → nft_transfer."""
        nft_contract = "0x" + "dd" * 20
        raw = {
            "transaction": {"from": USER, "to": nft_contract, "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    {
                        "address": nft_contract,
                        "topics": [
                            TRANSFER_TOPIC,
                            _pad_address(USER),
                            _pad_address(OTHER),
                            "0x" + "00" * 31 + "05",  # tokenId = 5
                        ],
                        "data": "0x",
                    },
                ],
            },
        }
        actions = classify_evm_actions(raw)
        assert any(a.type == "nft_transfer" for a in actions)
        nft_action = next(a for a in actions if a.type == "nft_transfer")
        assert nft_action.nft.token_id == "5"

    def test_erc1155_transfer_single(self):
        """ERC1155 TransferSingle event → nft_transfer."""
        nft_contract = "0x" + "ee" * 20
        operator = "0x" + "ff" * 20
        erc1155_topic = "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62"
        # data = tokenId (32 bytes) + amount (32 bytes)
        token_id_hex = "00" * 31 + "0a"  # tokenId = 10
        amount_hex = "00" * 31 + "01"  # amount = 1
        raw = {
            "transaction": {"from": USER, "to": nft_contract, "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    {
                        "address": nft_contract,
                        "topics": [
                            erc1155_topic,
                            _pad_address(operator),
                            _pad_address(USER),
                            _pad_address(OTHER),
                        ],
                        "data": "0x" + token_id_hex + amount_hex,
                    },
                ],
            },
        }
        actions = classify_evm_actions(raw)
        assert any(a.type == "nft_transfer" for a in actions)


class TestApprovalClassification:
    def test_approval_only(self):
        """Only an Approval event, nothing else → approve."""
        raw = {
            "transaction": {"from": USER, "to": USDC, "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    {
                        "address": USDC,
                        "topics": [APPROVAL_TOPIC, _pad_address(USER), _pad_address(OTHER)],
                        "data": _encode_uint256(2**256 - 1),
                    },
                ],
            },
        }
        actions = classify_evm_actions(raw)
        assert actions[0].type == "approve"
        assert actions[0].spender is not None


class TestFallbackClassification:
    def test_no_logs_no_value(self):
        """No logs and no value → contract_call."""
        raw = {
            "transaction": {"from": USER, "to": OTHER, "value": "0x0", "input": "0xabcd1234"},
            "receipt": {"from": USER, "logs": []},
        }
        actions = classify_evm_actions(raw)
        assert actions[0].type == "contract_call"

    def test_empty_transaction(self):
        """Missing from → empty actions."""
        raw = {"transaction": {}, "receipt": {"logs": []}}
        actions = classify_evm_actions(raw)
        assert actions == []


class TestProtocolLabeling:
    def test_uniswap_v3_router(self):
        raw = {
            "transaction": {"from": USER, "to": "0x2626664c2603336e57b271c5c0b26f421741e481", "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    {
                        "address": USDC,
                        "topics": [TRANSFER_TOPIC, _pad_address(USER), _pad_address(OTHER)],
                        "data": _encode_uint256(100),
                    },
                    {
                        "address": "0x" + "aa" * 20,
                        "topics": [TRANSFER_TOPIC, _pad_address(OTHER), _pad_address(USER)],
                        "data": _encode_uint256(200),
                    },
                ],
            },
        }
        actions = classify_evm_actions(raw)
        assert actions[0].protocol == "Uniswap V3"

    def test_unknown_router(self):
        raw = {
            "transaction": {"from": USER, "to": "0x" + "99" * 20, "value": "0x0", "input": "0x"},
            "receipt": {
                "from": USER,
                "logs": [
                    {
                        "address": USDC,
                        "topics": [TRANSFER_TOPIC, _pad_address(USER), _pad_address(OTHER)],
                        "data": _encode_uint256(100),
                    },
                ],
            },
        }
        actions = classify_evm_actions(raw)
        assert actions[0].protocol is None

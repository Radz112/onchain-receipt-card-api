"""
EVM action classifier using net token delta approach.

Instead of pattern-matching swap event signatures, compute the user's net
ERC20/native balance changes from Transfer events. This handles aggregators,
multi-hop swaps, WETH wrap/unwrap, and unknown protocols correctly.
"""

from __future__ import annotations

from app.models.action import Action, NFTInfo, TokenInfo

# --- Event topic signatures ---
ERC20_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ERC721_TRANSFER = ERC20_TRANSFER  # same sig, distinguished by 3 vs 2 indexed topics
APPROVAL = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
ERC1155_TRANSFER_SINGLE = "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62"
ERC1155_TRANSFER_BATCH = "0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb"
WETH_DEPOSIT = "0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c"
WETH_WITHDRAWAL = "0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65"

# Known WETH addresses on Base
WETH_ADDRESSES = {
    "0x4200000000000000000000000000000000000006",  # Base WETH
}

# --- Known router registry (Base) ---
KNOWN_ROUTERS: dict[str, str] = {
    "0x2626664c2603336e57b271c5c0b26f421741e481": "Uniswap V3",
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": "Uniswap Universal Router",
    "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43": "Aerodrome",
    "0x111111125421ca6dc452d289314280a0f8842a65": "1inch",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch",
}

# Multicall function selector
MULTICALL_SELECTOR = "0xac9650d8"

# Known multisig contracts (Safe/Gnosis)
KNOWN_MULTISIGS: set[str] = {
    "0xd9db270c1b5e3bd161e8c8503c55ceabee709552",  # Safe 1.3.0
    "0x69f4d1788e39c87893c980c06edf4b75dae3e3db",  # Safe L2 1.3.0
}


def _decode_address(topic_hex: str) -> str:
    return "0x" + topic_hex[-40:].lower()


def _hex_to_int(hex_str: str) -> int:
    if not hex_str or hex_str == "0x":
        return 0
    return int(hex_str, 16)


def _identify_protocol(tx: dict) -> str | None:
    to_addr = (tx.get("to") or "").lower()
    return KNOWN_ROUTERS.get(to_addr)


def classify_evm_actions(raw_tx: dict) -> list[Action]:
    tx_data = raw_tx.get("transaction") or {}
    receipt = raw_tx.get("receipt") or {}
    logs = receipt.get("logs", []) or []
    user = (tx_data.get("from") or receipt.get("from") or "").lower()

    if not user:
        return []

    # --- Edge case: contract creation (to is None, contractAddress in receipt) ---
    contract_address = receipt.get("contractAddress")
    if contract_address and not tx_data.get("to"):
        return [
            Action(
                type="contract_call",
                note=f"Contract Deployed: {contract_address}",
                from_=user,
                to=contract_address,
            )
        ]

    protocol = _identify_protocol(tx_data)

    # Track net deltas: token_address -> delta (positive = user received, negative = user sent)
    deltas: dict[str, int] = {}
    # Track token metadata from logs
    token_contracts: dict[str, str] = {}  # address -> address (for reference)

    nft_actions: list[Action] = []
    approval_actions: list[Action] = []
    weth_net_delta = 0

    for log in logs:
        topics = log.get("topics", [])
        if not topics:
            continue

        event_sig = topics[0].lower() if topics[0] else ""
        contract = (log.get("address") or "").lower()

        # --- WETH Deposit/Withdrawal: fold into native ETH ---
        if contract in WETH_ADDRESSES:
            if event_sig == WETH_DEPOSIT and len(topics) >= 2:
                depositor = _decode_address(topics[1])
                amount = _hex_to_int(log.get("data", "0x"))
                if depositor == user:
                    weth_net_delta -= amount  # user wrapped ETH → loses ETH
                continue
            if event_sig == WETH_WITHDRAWAL and len(topics) >= 2:
                withdrawer = _decode_address(topics[1])
                amount = _hex_to_int(log.get("data", "0x"))
                if withdrawer == user:
                    weth_net_delta += amount  # user unwrapped WETH → gains ETH
                continue

        # --- ERC721 Transfer (3 indexed topics: from, to, tokenId) ---
        if event_sig == ERC721_TRANSFER and len(topics) == 4:
            from_addr = _decode_address(topics[1])
            to_addr = _decode_address(topics[2])
            token_id = str(_hex_to_int(topics[3]))

            if from_addr == user or to_addr == user:
                nft_actions.append(
                    Action(
                        type="nft_transfer",
                        nft=NFTInfo(token_id=token_id),
                        from_=from_addr,
                        to=to_addr,
                        token_in=TokenInfo(address=contract, symbol=f"NFT #{token_id}", amount="1", decimals=0)
                        if from_addr == user
                        else None,
                        token_out=TokenInfo(address=contract, symbol=f"NFT #{token_id}", amount="1", decimals=0)
                        if to_addr == user
                        else None,
                        protocol=protocol,
                    )
                )
            continue

        # --- ERC1155 TransferSingle ---
        if event_sig == ERC1155_TRANSFER_SINGLE and len(topics) >= 4:
            from_addr = _decode_address(topics[2])
            to_addr = _decode_address(topics[3])
            data = log.get("data", "0x")
            # data contains tokenId (32 bytes) + amount (32 bytes)
            if len(data) >= 130:  # 0x + 64 + 64
                token_id = str(_hex_to_int("0x" + data[2:66]))
                amount = _hex_to_int("0x" + data[66:130])
            else:
                token_id = "0"
                amount = 1

            if from_addr == user or to_addr == user:
                nft_actions.append(
                    Action(
                        type="nft_transfer",
                        nft=NFTInfo(token_id=token_id),
                        from_=from_addr,
                        to=to_addr,
                        token_in=TokenInfo(address=contract, symbol=f"NFT #{token_id}", amount=str(amount), decimals=0)
                        if from_addr == user
                        else None,
                        token_out=TokenInfo(address=contract, symbol=f"NFT #{token_id}", amount=str(amount), decimals=0)
                        if to_addr == user
                        else None,
                        protocol=protocol,
                    )
                )
            continue

        # --- ERC20 Transfer (2 indexed topics: from, to; data = amount) ---
        if event_sig == ERC20_TRANSFER and len(topics) == 3:
            from_addr = _decode_address(topics[1])
            to_addr = _decode_address(topics[2])
            amount = _hex_to_int(log.get("data", "0x"))

            token_contracts[contract] = contract

            if from_addr == user:
                deltas[contract] = deltas.get(contract, 0) - amount
            if to_addr == user:
                deltas[contract] = deltas.get(contract, 0) + amount
            continue

        # --- Approval ---
        if event_sig == APPROVAL and len(topics) >= 3:
            owner = _decode_address(topics[1])
            spender = _decode_address(topics[2])
            if owner == user:
                approval_actions.append(
                    Action(
                        type="approve",
                        spender=spender,
                        token_in=TokenInfo(address=contract, amount="0"),
                    )
                )
            continue

    # --- Handle native ETH value transfer ---
    value_hex = tx_data.get("value", "0x0")
    native_sent = _hex_to_int(value_hex)
    native_delta = -native_sent + weth_net_delta  # WETH unwrap adds to native

    # Remove WETH from ERC20 deltas (already folded into native)
    for weth_addr in WETH_ADDRESSES:
        weth_erc20_delta = deltas.pop(weth_addr, 0)
        native_delta += weth_erc20_delta  # fold any WETH ERC20 transfers too

    # Add native ETH as a special "token" if there's a meaningful delta
    NATIVE_KEY = "native_eth"
    if native_delta != 0:
        deltas[NATIVE_KEY] = native_delta

    # --- Classify based on net deltas ---
    negative_deltas = {k: v for k, v in deltas.items() if v < 0}
    positive_deltas = {k: v for k, v in deltas.items() if v > 0}

    actions: list[Action] = []

    if negative_deltas and positive_deltas:
        # Swap: largest negative = tokenIn, largest positive = tokenOut
        token_in_addr = min(negative_deltas, key=negative_deltas.get)  # most negative
        token_out_addr = max(positive_deltas, key=positive_deltas.get)  # most positive

        actions.append(
            Action(
                type="swap",
                token_in=TokenInfo(
                    address=token_in_addr if token_in_addr != NATIVE_KEY else "native",
                    amount=str(abs(negative_deltas[token_in_addr])),
                ),
                token_out=TokenInfo(
                    address=token_out_addr if token_out_addr != NATIVE_KEY else "native",
                    amount=str(positive_deltas[token_out_addr]),
                ),
                protocol=protocol,
            )
        )
    elif negative_deltas:
        # Transfer out
        for addr, delta in negative_deltas.items():
            actions.append(
                Action(
                    type="transfer",
                    token_in=TokenInfo(
                        address=addr if addr != NATIVE_KEY else "native",
                        amount=str(abs(delta)),
                    ),
                    to=(tx_data.get("to") or receipt.get("to") or ""),
                    from_=user,
                    protocol=protocol,
                )
            )
    elif positive_deltas:
        # Transfer in / received
        for addr, delta in positive_deltas.items():
            actions.append(
                Action(
                    type="transfer",
                    token_out=TokenInfo(
                        address=addr if addr != NATIVE_KEY else "native",
                        amount=str(delta),
                    ),
                    to=user,
                    protocol=protocol,
                )
            )

    # NFT actions come next
    actions.extend(nft_actions)

    # Approvals last
    if not actions:
        actions.extend(approval_actions)
    elif approval_actions:
        actions.extend(approval_actions)

    # Fallback: contract_call
    if not actions:
        input_data = tx_data.get("input", "0x")
        selector = input_data[:10] if len(input_data) >= 10 else input_data

        # Detect multicall/batch
        if selector == MULTICALL_SELECTOR:
            # Estimate call count from data length (each call ≈ 68+ bytes encoded)
            data_len = (len(input_data) - 10) // 2  # hex chars to bytes
            estimated_calls = max(1, data_len // 68)
            actions.append(
                Action(
                    type="contract_call",
                    note=f"Batch: ~{estimated_calls} calls",
                    to=tx_data.get("to"),
                    protocol=protocol,
                )
            )
        else:
            actions.append(
                Action(
                    type="contract_call",
                    note=f"Function: {selector}",
                    to=tx_data.get("to"),
                )
            )

    return actions

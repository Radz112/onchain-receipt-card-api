"""
Solana action classifier using net token delta approach.

Uses pre/postTokenBalances and pre/postBalances natively provided by Solana
to compute per-account, per-mint deltas. No inner instruction parsing needed.
"""

from __future__ import annotations

from app.models.action import Action, TokenInfo

# Known program IDs for protocol labeling
VOTE_PROGRAM = "Vote111111111111111111111111111111111111111"

KNOWN_PROGRAMS: dict[str, str] = {
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca",
    "MERLuDFBMmsHnsBPZw2sDQZHvXFMwp8EdjudcU2HKky": "Mercurial",
    "SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ": "Saber",
    "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY": "Phoenix",
}


def _get_signer(raw_tx: dict) -> str:
    message = raw_tx.get("transaction", {}).get("message", {})
    account_keys = message.get("accountKeys", [])
    if account_keys:
        first = account_keys[0]
        return first["pubkey"] if isinstance(first, dict) else str(first)
    return ""


def _identify_protocol(raw_tx: dict) -> str | None:
    message = raw_tx.get("transaction", {}).get("message", {})

    # Check account keys for known program IDs
    for key in message.get("accountKeys", []):
        pubkey = key["pubkey"] if isinstance(key, dict) else str(key)
        if pubkey in KNOWN_PROGRAMS:
            return KNOWN_PROGRAMS[pubkey]

    # Check instructions for program IDs
    for ix in message.get("instructions", []):
        program_id = ix.get("programId", "")
        if program_id in KNOWN_PROGRAMS:
            return KNOWN_PROGRAMS[program_id]

    return None


def _is_vote_transaction(raw_tx: dict) -> bool:
    """Check if this is a validator vote transaction."""
    message = raw_tx.get("transaction", {}).get("message", {})
    for key in message.get("accountKeys", []):
        pubkey = key["pubkey"] if isinstance(key, dict) else str(key)
        if pubkey == VOTE_PROGRAM:
            return True
    for ix in message.get("instructions", []):
        if ix.get("programId", "") == VOTE_PROGRAM:
            return True
    return False


def classify_solana_actions(raw_tx: dict) -> list[Action]:
    meta = raw_tx.get("meta", {})
    signer = _get_signer(raw_tx)
    if not signer:
        return []

    # Edge case: Solana vote transaction
    if _is_vote_transaction(raw_tx):
        return [
            Action(
                type="contract_call",
                note="Validator Vote",
                from_=signer,
            )
        ]

    protocol = _identify_protocol(raw_tx)

    # --- Compute SPL token deltas for the signer ---
    pre_balances = meta.get("preTokenBalances", []) or []
    post_balances = meta.get("postTokenBalances", []) or []

    # Build lookup: (accountIndex, mint) -> amount
    pre_map: dict[tuple[int, str], float] = {}
    post_map: dict[tuple[int, str], float] = {}
    mint_decimals: dict[str, int] = {}

    # Get account keys to resolve owner from accountIndex
    message = raw_tx.get("transaction", {}).get("message", {})
    account_keys = message.get("accountKeys", [])

    def _get_owner(balance_entry: dict) -> str:
        owner = balance_entry.get("owner", "")
        if owner:
            return owner
        # Fallback: resolve from accountIndex
        idx = balance_entry.get("accountIndex", -1)
        if 0 <= idx < len(account_keys):
            key = account_keys[idx]
            return key["pubkey"] if isinstance(key, dict) else str(key)
        return ""

    for entry in pre_balances:
        owner = _get_owner(entry)
        if owner != signer:
            continue
        mint = entry.get("mint", "")
        ui_amount = entry.get("uiTokenAmount", {})
        amount = float(ui_amount.get("uiAmount") or 0)
        decimals = ui_amount.get("decimals", 0)
        idx = entry.get("accountIndex", 0)
        pre_map[(idx, mint)] = amount
        mint_decimals[mint] = decimals

    for entry in post_balances:
        owner = _get_owner(entry)
        if owner != signer:
            continue
        mint = entry.get("mint", "")
        ui_amount = entry.get("uiTokenAmount", {})
        amount = float(ui_amount.get("uiAmount") or 0)
        decimals = ui_amount.get("decimals", 0)
        idx = entry.get("accountIndex", 0)
        post_map[(idx, mint)] = amount
        mint_decimals[mint] = decimals

    # Compute per-mint deltas
    all_keys = set(pre_map.keys()) | set(post_map.keys())
    mint_deltas: dict[str, float] = {}
    for key in all_keys:
        mint = key[1]
        pre_val = pre_map.get(key, 0.0)
        post_val = post_map.get(key, 0.0)
        delta = post_val - pre_val
        mint_deltas[mint] = mint_deltas.get(mint, 0.0) + delta

    # --- Compute native SOL delta ---
    pre_sol_balances = meta.get("preBalances", [])
    post_sol_balances = meta.get("postBalances", [])
    fee = meta.get("fee", 0)

    sol_delta = 0.0
    if pre_sol_balances and post_sol_balances:
        # Index 0 = signer
        pre_sol = pre_sol_balances[0] if pre_sol_balances else 0
        post_sol = post_sol_balances[0] if post_sol_balances else 0
        sol_delta = (post_sol - pre_sol + fee) / 1e9  # add fee back since it's not an "action"

    # --- Check for NFT transfers (decimals=0, amount=1) ---
    nft_actions: list[Action] = []
    nft_mints: set[str] = set()
    for mint, delta in list(mint_deltas.items()):
        decimals = mint_decimals.get(mint, 0)
        if decimals == 0 and abs(delta) == 1.0:
            nft_mints.add(mint)
            nft_actions.append(
                Action(
                    type="nft_transfer",
                    token_in=TokenInfo(address=mint, symbol=f"NFT", amount="1", decimals=0)
                    if delta < 0
                    else None,
                    token_out=TokenInfo(address=mint, symbol=f"NFT", amount="1", decimals=0)
                    if delta > 0
                    else None,
                    from_=signer if delta < 0 else None,
                    to=signer if delta > 0 else None,
                    protocol=protocol,
                )
            )

    # Remove NFT mints from deltas
    for mint in nft_mints:
        mint_deltas.pop(mint, None)

    # Add native SOL if meaningful
    NATIVE_KEY = "native_sol"
    if abs(sol_delta) > 0.000001:
        mint_deltas[NATIVE_KEY] = sol_delta

    # --- Classify based on net deltas ---
    negative = {k: v for k, v in mint_deltas.items() if v < -0.000001}
    positive = {k: v for k, v in mint_deltas.items() if v > 0.000001}

    actions: list[Action] = []

    if negative and positive:
        token_in_mint = min(negative, key=negative.get)
        token_out_mint = max(positive, key=positive.get)

        actions.append(
            Action(
                type="swap",
                token_in=TokenInfo(
                    address=token_in_mint if token_in_mint != NATIVE_KEY else "native",
                    amount=str(abs(negative[token_in_mint])),
                    decimals=mint_decimals.get(token_in_mint, 9),
                ),
                token_out=TokenInfo(
                    address=token_out_mint if token_out_mint != NATIVE_KEY else "native",
                    amount=str(positive[token_out_mint]),
                    decimals=mint_decimals.get(token_out_mint, 9),
                ),
                protocol=protocol,
            )
        )
    elif negative:
        for mint, delta in negative.items():
            actions.append(
                Action(
                    type="transfer",
                    token_in=TokenInfo(
                        address=mint if mint != NATIVE_KEY else "native",
                        amount=str(abs(delta)),
                        decimals=mint_decimals.get(mint, 9),
                    ),
                    from_=signer,
                    protocol=protocol,
                )
            )
    elif positive:
        for mint, delta in positive.items():
            actions.append(
                Action(
                    type="transfer",
                    token_out=TokenInfo(
                        address=mint if mint != NATIVE_KEY else "native",
                        amount=str(delta),
                        decimals=mint_decimals.get(mint, 9),
                    ),
                    to=signer,
                    protocol=protocol,
                )
            )

    actions.extend(nft_actions)

    if not actions:
        actions.append(Action(type="contract_call", protocol=protocol))

    return actions

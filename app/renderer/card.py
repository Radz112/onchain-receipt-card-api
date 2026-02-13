from __future__ import annotations

from app.classifiers import normalize_actions
from app.models.action import Action
from app.renderer.svg_builder import render_receipt_svg
from app.validation.sanitize import sanitize_action


async def _resolve_action_tokens(action: Action, chain: str) -> Action:
    from app.tokens.resolver import resolve_token

    if action.token_in and action.token_in.symbol in ("Unknown", "?"):
        meta = await resolve_token(chain, action.token_in.address)
        action.token_in.symbol = meta["symbol"]
        action.token_in.decimals = meta["decimals"]

    if action.token_out and action.token_out.symbol in ("Unknown", "?"):
        meta = await resolve_token(chain, action.token_out.address)
        action.token_out.symbol = meta["symbol"]
        action.token_out.decimals = meta["decimals"]

    return action


def _apply_decimals(action: Action, chain: str) -> Action:
    if chain != "base":
        return action

    for token in (action.token_in, action.token_out):
        if token and token.decimals:
            raw = float(token.amount)
            token.amount = str(raw / (10 ** token.decimals))

    return action


def build_summary(normalized_tx: dict, actions: list[Action]) -> dict:
    primary = actions[0] if actions else None
    from app.renderer.svg_builder import _format_action_text

    action_label, action_detail = _format_action_text(primary) if primary else ("", "")

    return {
        "chain": normalized_tx.get("chain"),
        "tx_hash": normalized_tx.get("tx_hash"),
        "status": normalized_tx.get("status"),
        "block_number": normalized_tx.get("block_number"),
        "block_time": normalized_tx.get("block_time"),
        "from_address": normalized_tx.get("from_address"),
        "to_address": normalized_tx.get("to_address"),
        "fee": normalized_tx.get("fee"),
        "action_label": action_label,
        "action_detail": action_detail,
        "protocol": primary.protocol if primary else None,
        "actions": [a.model_dump(mode="json") for a in actions],
    }


async def render_receipt_card(
    normalized_tx: dict,
    template: str = "classic",
    format: str = "svg",
) -> tuple[str | bytes, dict]:
    chain = normalized_tx.get("chain", "base")
    raw = normalized_tx.get("raw", {})

    actions = normalize_actions(raw, chain)

    for i, action in enumerate(actions):
        action = await _resolve_action_tokens(action, chain)
        action = _apply_decimals(action, chain)
        action = Action(**sanitize_action(action.model_dump()))
        actions[i] = action

    summary = build_summary(normalized_tx, actions)
    svg_string = render_receipt_svg(normalized_tx, actions, template)

    if format == "png":
        return _svg_to_png(svg_string), summary

    return svg_string, summary


def _svg_to_png(svg_string: str) -> bytes:
    import cairosvg

    return cairosvg.svg2png(
        bytestring=svg_string.encode("utf-8"),
        output_width=1200,
        output_height=630,
    )

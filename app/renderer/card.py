"""
High-level card rendering entry point.
Combines action classification, token resolution, and SVG rendering.
"""

from __future__ import annotations

from app.classifiers import normalize_actions
from app.models.action import Action
from app.renderer.svg_builder import render_receipt_svg
from app.tokens.resolver import resolve_token_sync


async def _resolve_action_tokens(action: Action, chain: str) -> Action:
    """Resolve token symbols/decimals for an action using the token registry."""
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


def _apply_decimals(action: Action) -> Action:
    """Convert raw integer amounts to human-readable using decimals."""
    if action.token_in and action.token_in.decimals:
        try:
            raw = float(action.token_in.amount)
            if raw > 1e6:  # likely still in raw integer form
                action.token_in.amount = str(raw / (10 ** action.token_in.decimals))
        except (ValueError, TypeError):
            pass

    if action.token_out and action.token_out.decimals:
        try:
            raw = float(action.token_out.amount)
            if raw > 1e6:
                action.token_out.amount = str(raw / (10 ** action.token_out.decimals))
        except (ValueError, TypeError):
            pass

    return action


async def render_receipt_card(
    normalized_tx: dict,
    template: str = "classic",
    format: str = "svg",
) -> str | bytes:
    """
    Main entry point: classify actions, resolve tokens, render card.
    Returns SVG string or PNG bytes depending on format.
    """
    chain = normalized_tx.get("chain", "base")
    raw = normalized_tx.get("raw", {})

    actions = normalize_actions(raw, chain)

    # Resolve token metadata and apply decimal formatting
    for i, action in enumerate(actions):
        action = await _resolve_action_tokens(action, chain)
        action = _apply_decimals(action)
        actions[i] = action

    svg_string = render_receipt_svg(normalized_tx, actions, template)

    if format == "png":
        return _svg_to_png(svg_string)

    return svg_string


def _svg_to_png(svg_string: str) -> bytes:
    """Convert SVG string to PNG bytes using cairosvg."""
    try:
        import cairosvg

        return cairosvg.svg2png(
            bytestring=svg_string.encode("utf-8"),
            output_width=1200,
            output_height=630,
        )
    except ImportError:
        raise RuntimeError(
            "cairosvg is required for PNG output. Install it with: pip install cairosvg"
        )

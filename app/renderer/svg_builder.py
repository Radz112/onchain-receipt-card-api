"""
Pure-function SVG receipt card builder.
No external dependencies, no DOM, no headless browser.
All text embedded with system-safe fonts. All icons are SVG paths.
Token visuals = deterministic colored circles with first letter.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from app.models.action import Action
from app.renderer.templates import (
    ACTION_ICONS,
    CHAIN_COLORS,
    STATUS_COLORS,
    TEMPLATES,
    TemplateColors,
)

WIDTH = 1200
HEIGHT = 630


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _truncate_address(address: str) -> str:
    if not address or len(address) <= 12:
        return address or ""
    return f"{address[:6]}...{address[-4:]}"


def _token_color(address: str) -> str:
    """Deterministic color for a token based on its address hash."""
    h = hashlib.md5(address.encode()).hexdigest()
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    # Ensure decent saturation by boosting the values
    r = 80 + (r % 176)
    g = 80 + (g % 176)
    b = 80 + (b % 176)
    return f"#{r:02x}{g:02x}{b:02x}"


def _format_action_text(action: Action) -> tuple[str, str]:
    """Returns (action_label, detail_text)."""
    if action.type == "swap":
        in_sym = action.token_in.symbol if action.token_in else "?"
        in_amt = action.token_in.amount if action.token_in else "?"
        out_sym = action.token_out.symbol if action.token_out else "?"
        out_amt = action.token_out.amount if action.token_out else "?"
        return "Swapped", f"{_format_amount(in_amt)} {in_sym}  →  {_format_amount(out_amt)} {out_sym}"
    elif action.type == "transfer":
        if action.token_in:
            sym = action.token_in.symbol
            amt = action.token_in.amount
            return "Sent", f"{_format_amount(amt)} {sym}"
        elif action.token_out:
            sym = action.token_out.symbol
            amt = action.token_out.amount
            return "Received", f"{_format_amount(amt)} {sym}"
        return "Transfer", ""
    elif action.type == "nft_transfer":
        nft_label = ""
        if action.nft and action.nft.token_id:
            nft_label = f"NFT #{action.nft.token_id}"
        else:
            nft_label = "NFT"
        if action.token_in:
            return "Sent NFT", nft_label
        return "Received NFT", nft_label
    elif action.type == "approve":
        return "Approved", f"Spender: {_truncate_address(action.spender or '')}"
    elif action.type == "mint":
        return "Minted", ""
    elif action.type == "burn":
        return "Burned", ""
    elif action.type == "contract_call":
        return "Contract Call", action.note or ""
    elif action.type == "overflow":
        return "", action.note or ""
    return action.type.title(), ""


def _format_amount(raw: str) -> str:
    """Format a raw amount string to a readable number."""
    try:
        val = float(raw)
    except (ValueError, TypeError):
        return raw
    if val == 0:
        return "0"
    if val >= 1_000_000:
        return f"{val:,.0f}"
    if val >= 1:
        return f"{val:,.4f}".rstrip("0").rstrip(".")
    if val >= 0.0001:
        return f"{val:.6f}".rstrip("0").rstrip(".")
    return f"{val:.10f}".rstrip("0").rstrip(".")


def _format_block_time(block_time: datetime | str | None) -> str:
    if block_time is None:
        return "Timestamp unavailable"
    if isinstance(block_time, str):
        try:
            block_time = datetime.fromisoformat(block_time)
        except ValueError:
            return str(block_time)
    return block_time.strftime("%b %d, %Y %H:%M UTC")


def _render_token_circle(x: int, y: int, symbol: str, address: str, radius: int = 20) -> str:
    color = _token_color(address)
    letter = _escape_xml(symbol[0].upper()) if symbol else "?"
    return f"""<circle cx="{x}" cy="{y}" r="{radius}" fill="{color}"/>
<text x="{x}" y="{y + 6}" text-anchor="middle" fill="white" font-size="16" font-weight="bold" font-family="Arial, Helvetica, sans-serif">{letter}</text>"""


def _render_action_icon(x: int, y: int, action_type: str, color: str) -> str:
    icon_path = ACTION_ICONS.get(action_type, ACTION_ICONS["contract_call"])
    colored_path = icon_path.replace("{color}", color)
    return f'<g transform="translate({x},{y}) scale(1.2)">{colored_path}</g>'


def render_receipt_svg(
    normalized_tx: dict,
    actions: list[Action],
    template: str = "classic",
) -> str:
    colors = TEMPLATES.get(template, TEMPLATES["classic"])
    chain = normalized_tx.get("chain", "base")
    chain_color = CHAIN_COLORS.get(chain, colors.accent)

    status = normalized_tx.get("status", "confirmed")
    status_color = STATUS_COLORS.get(status, "#6B7280")
    status_label = status.upper()

    tx_hash = normalized_tx.get("tx_hash", "")
    from_addr = _truncate_address(normalized_tx.get("from_address", ""))
    fee = normalized_tx.get("fee", {})
    fee_text = f'{fee.get("amount", "0")} {fee.get("token", "")}'
    block_number = normalized_tx.get("block_number")
    block_time_raw = normalized_tx.get("block_time")
    block_time_text = _format_block_time(block_time_raw)
    block_text = f"Block {block_number:,}" if block_number else "Block N/A"

    primary_action = actions[0] if actions else Action(type="contract_call", primary=True)
    action_label, action_detail = _format_action_text(primary_action)

    # Build SVG
    parts: list[str] = []

    # Header
    parts.append(f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}">
<defs>
  <style>
    .title {{ font-family: Arial, Helvetica, sans-serif; font-size: 22px; font-weight: bold; fill: {colors.text_primary}; }}
    .label {{ font-family: Arial, Helvetica, sans-serif; font-size: 16px; fill: {colors.text_secondary}; }}
    .value {{ font-family: 'Courier New', Courier, monospace; font-size: 16px; fill: {colors.text_primary}; }}
    .action-label {{ font-family: Arial, Helvetica, sans-serif; font-size: 28px; font-weight: bold; fill: {colors.text_primary}; }}
    .action-detail {{ font-family: 'Courier New', Courier, monospace; font-size: 22px; fill: {colors.text_primary}; }}
    .protocol {{ font-family: Arial, Helvetica, sans-serif; font-size: 16px; fill: {colors.text_secondary}; }}
    .footer {{ font-family: Arial, Helvetica, sans-serif; font-size: 13px; fill: {colors.text_secondary}; }}
    .chain-label {{ font-family: Arial, Helvetica, sans-serif; font-size: 14px; font-weight: bold; fill: {chain_color}; text-transform: uppercase; letter-spacing: 2px; }}
  </style>
</defs>

<!-- Background -->
<rect width="{WIDTH}" height="{HEIGHT}" rx="16" fill="{colors.background}"/>
<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" rx="15" fill="none" stroke="{colors.border}" stroke-width="1"/>
""")

    # Chain logo circle + header text
    parts.append(f"""<!-- Header -->
<circle cx="60" cy="52" r="18" fill="{chain_color}"/>
<text x="60" y="58" text-anchor="middle" fill="white" font-size="14" font-weight="bold" font-family="Arial">{_escape_xml(chain[0].upper())}</text>
<text x="90" y="48" class="chain-label">{_escape_xml(chain.upper())}</text>
<text x="90" y="66" class="title">ONCHAIN RECEIPT</text>
""")

    # Status badge
    parts.append(f"""<!-- Status -->
<rect x="{WIDTH - 200}" y="32" width="160" height="36" rx="18" fill="{status_color}" opacity="0.15"/>
<circle cx="{WIDTH - 180}" cy="50" r="5" fill="{status_color}"/>
<text x="{WIDTH - 166}" y="55" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="bold" fill="{status_color}">{status_label}</text>
""")

    # Divider
    parts.append(f"""<line x1="40" y1="90" x2="{WIDTH - 40}" y2="90" stroke="{colors.divider}" stroke-width="1"/>
""")

    # Action icon + label + detail
    y_action = 140
    parts.append(_render_action_icon(44, y_action - 16, primary_action.type, chain_color))

    parts.append(f"""<text x="85" y="{y_action}" class="action-label">{_escape_xml(action_label)}</text>
<text x="85" y="{y_action + 36}" class="action-detail">{_escape_xml(action_detail)}</text>
""")

    # Protocol label
    protocol_text = primary_action.protocol or ""
    if protocol_text:
        parts.append(f"""<text x="85" y="{y_action + 64}" class="protocol">via {_escape_xml(protocol_text)}</text>
""")

    # Token circles
    y_tokens = y_action + 96
    token_circles = []
    if primary_action.token_in:
        token_circles.append(
            _render_token_circle(65, y_tokens, primary_action.token_in.symbol, primary_action.token_in.address)
        )
    if primary_action.token_out:
        offset = 110 if primary_action.token_in else 0
        token_circles.append(
            _render_token_circle(65 + offset, y_tokens, primary_action.token_out.symbol, primary_action.token_out.address)
        )
    if primary_action.token_in and primary_action.token_out:
        # Arrow between circles
        token_circles.insert(1, f'<text x="110" y="{y_tokens + 6}" font-size="20" fill="{colors.text_secondary}" font-family="Arial">→</text>')

    parts.extend(token_circles)

    # Transaction details
    y_details = 380
    parts.append(f"""<!-- Details -->
<line x1="40" y1="{y_details - 20}" x2="{WIDTH - 40}" y2="{y_details - 20}" stroke="{colors.divider}" stroke-width="1"/>
<text x="60" y="{y_details + 10}" class="label">From</text>
<text x="160" y="{y_details + 10}" class="value">{_escape_xml(from_addr)}</text>

<text x="60" y="{y_details + 40}" class="label">Fee</text>
<text x="160" y="{y_details + 40}" class="value">{_escape_xml(fee_text)}</text>

<text x="400" y="{y_details + 10}" class="label">Tx</text>
<text x="440" y="{y_details + 10}" class="value">{_escape_xml(_truncate_address(tx_hash))}</text>
""")

    # Block + timestamp
    y_footer = HEIGHT - 75
    parts.append(f"""<line x1="40" y1="{y_footer - 10}" x2="{WIDTH - 40}" y2="{y_footer - 10}" stroke="{colors.divider}" stroke-width="1"/>
<text x="60" y="{y_footer + 16}" class="label">{_escape_xml(block_text)}  ·  {_escape_xml(block_time_text)}</text>
""")

    # Powered by footer
    parts.append(f"""<text x="{WIDTH // 2}" y="{HEIGHT - 20}" text-anchor="middle" class="footer">powered by APIX402</text>
""")

    parts.append("</svg>")

    return "\n".join(parts)

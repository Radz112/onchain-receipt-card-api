"""
Input sanitization for SVG rendering.

All text rendered into SVG strings must be sanitized to prevent SVG injection.
"""

from __future__ import annotations

import re

MAX_SYMBOL_LEN = 20
MAX_ADDRESS_LEN = 66
MAX_PROTOCOL_LEN = 50
MAX_NOTE_LEN = 100

# Token symbols: alphanumeric + limited special chars
_SYMBOL_RE = re.compile(r"^[a-zA-Z0-9_.\-#/ ]+$")


def sanitize_symbol(symbol: str) -> str:
    """Sanitize token symbol for SVG rendering."""
    symbol = symbol.strip()[:MAX_SYMBOL_LEN]
    if not symbol or not _SYMBOL_RE.match(symbol):
        return symbol[:MAX_SYMBOL_LEN].replace("<", "").replace(">", "").replace("&", "") or "?"
    return symbol


def sanitize_address(address: str) -> str:
    """Cap address length and strip dangerous characters."""
    return address.strip()[:MAX_ADDRESS_LEN]


def sanitize_protocol(name: str) -> str:
    """Cap protocol name length."""
    return name.strip()[:MAX_PROTOCOL_LEN]


def sanitize_note(note: str) -> str:
    """Cap note/selector length."""
    return note.strip()[:MAX_NOTE_LEN]


def sanitize_action(action_dict: dict) -> dict:
    """Sanitize all text fields in an action dict before SVG rendering."""
    if "token_in" in action_dict and action_dict["token_in"]:
        ti = action_dict["token_in"]
        if "symbol" in ti:
            ti["symbol"] = sanitize_symbol(ti["symbol"])
        if "address" in ti:
            ti["address"] = sanitize_address(ti["address"])

    if "token_out" in action_dict and action_dict["token_out"]:
        to = action_dict["token_out"]
        if "symbol" in to:
            to["symbol"] = sanitize_symbol(to["symbol"])
        if "address" in to:
            to["address"] = sanitize_address(to["address"])

    if "protocol" in action_dict and action_dict["protocol"]:
        action_dict["protocol"] = sanitize_protocol(action_dict["protocol"])

    if "note" in action_dict and action_dict["note"]:
        action_dict["note"] = sanitize_note(action_dict["note"])

    if "spender" in action_dict and action_dict["spender"]:
        action_dict["spender"] = sanitize_address(action_dict["spender"])

    if "to" in action_dict and action_dict["to"]:
        action_dict["to"] = sanitize_address(action_dict["to"])

    if "from_" in action_dict and action_dict["from_"]:
        action_dict["from_"] = sanitize_address(action_dict["from_"])

    return action_dict

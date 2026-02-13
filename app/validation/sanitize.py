from __future__ import annotations

import re

MAX_SYMBOL_LEN = 20
MAX_ADDRESS_LEN = 66
MAX_PROTOCOL_LEN = 50
MAX_NOTE_LEN = 100

# Token symbols: alphanumeric + limited special chars
_SYMBOL_RE = re.compile(r"^[a-zA-Z0-9_.\-#/ ]+$")


def sanitize_symbol(symbol: str) -> str:
    symbol = symbol.strip()[:MAX_SYMBOL_LEN]
    if not symbol or not _SYMBOL_RE.match(symbol):
        return symbol[:MAX_SYMBOL_LEN].replace("<", "").replace(">", "").replace("&", "") or "?"
    return symbol


def sanitize_address(address: str) -> str:
    return address.strip()[:MAX_ADDRESS_LEN]


def sanitize_protocol(name: str) -> str:
    return name.strip()[:MAX_PROTOCOL_LEN]


def sanitize_note(note: str) -> str:
    return note.strip()[:MAX_NOTE_LEN]


_FIELD_SANITIZERS = {
    "protocol": sanitize_protocol,
    "note": sanitize_note,
    "spender": sanitize_address,
    "to": sanitize_address,
    "from_": sanitize_address,
}

_TOKEN_FIELD_SANITIZERS = {
    "symbol": sanitize_symbol,
    "address": sanitize_address,
}


def sanitize_action(action_dict: dict) -> dict:
    for token_key in ("token_in", "token_out"):
        token = action_dict.get(token_key)
        if token:
            for field, fn in _TOKEN_FIELD_SANITIZERS.items():
                if field in token:
                    token[field] = fn(token[field])

    for field, fn in _FIELD_SANITIZERS.items():
        if action_dict.get(field):
            action_dict[field] = fn(action_dict[field])

    return action_dict

"""Template color schemes and constants for receipt card rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateColors:
    background: str
    text_primary: str
    text_secondary: str
    accent: str
    border: str
    card_bg: str
    divider: str


TEMPLATES: dict[str, TemplateColors] = {
    "classic": TemplateColors(
        background="#FFFFFF",
        text_primary="#1A1A2E",
        text_secondary="#6B7280",
        accent="#0052FF",  # Base blue default, overridden by chain
        border="#E5E7EB",
        card_bg="#F9FAFB",
        divider="#E5E7EB",
    ),
    "minimal": TemplateColors(
        background="#0D1117",
        text_primary="#E6EDF3",
        text_secondary="#8B949E",
        accent="#58A6FF",
        border="#30363D",
        card_bg="#161B22",
        divider="#30363D",
    ),
    "dark": TemplateColors(
        background="#0A0A0F",
        text_primary="#FFFFFF",
        text_secondary="#9CA3AF",
        accent="#00FF88",
        border="#1F2937",
        card_bg="#111118",
        divider="#1F2937",
    ),
}

CHAIN_COLORS = {
    "base": "#0052FF",
    "solana": "#9945FF",
}

# Action type icons as SVG path data
ACTION_ICONS: dict[str, str] = {
    "swap": '<path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z" fill="{color}"/>',
    "transfer": '<path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z" fill="{color}"/>',
    "nft_transfer": '<path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z" fill="{color}"/>',
    "mint": '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="{color}"/>',
    "burn": '<path d="M13.5.67s.74 2.65.74 4.8c0 2.06-1.35 3.73-3.41 3.73-2.07 0-3.63-1.67-3.63-3.73l.03-.36C5.21 7.51 4 10.62 4 14c0 4.42 3.58 8 8 8s8-3.58 8-8C20 8.61 17.41 3.8 13.5.67z" fill="{color}"/>',
    "approve": '<path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" fill="{color}"/>',
    "contract_call": '<path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94L14.4 2.81c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41L9.25 5.35c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" fill="{color}"/>',
}

STATUS_COLORS = {
    "confirmed": "#10B981",
    "failed": "#EF4444",
    "pending": "#F59E0B",
}

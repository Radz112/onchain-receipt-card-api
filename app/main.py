import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from app.cache.file_cache import file_cache
from app.cache.manager import CACHE_MISS, tx_cache
from app.fetchers import fetch_transaction
from app.renderer.card import render_receipt_card
from app.validation.input import validate_chain, validate_tx_hash

logger = logging.getLogger(__name__)

app = FastAPI(title="Onchain Receipt Card API", version="0.2.0")


class ReceiptRequest(BaseModel):
    tx_hash: str
    template: str = "classic"
    format: str = "json"


# ---------- GET endpoint info ----------

@app.get("/v1/receipt/{chain}")
async def receipt_info(chain: str):
    chain = validate_chain(chain)
    return {
        "chain": chain,
        "description": f"POST a tx_hash to fetch a normalized {chain} transaction receipt.",
        "usage": {
            "method": "POST",
            "body": {
                "tx_hash": "string",
                "template": "classic|minimal|dark",
                "format": "json|svg|png",
            },
        },
    }


# ---------- POST receipt generation ----------

@app.post("/v1/receipt/{chain}")
async def generate_receipt(chain: str, body: ReceiptRequest):
    # 1. Validate input
    chain = validate_chain(chain)
    tx_hash = validate_tx_hash(chain, body.tx_hash)
    template = body.template if body.template in ("classic", "minimal", "dark") else "classic"
    fmt = body.format if body.format in ("json", "svg", "png") else "json"

    # 2. Check file cache for image (PNG only) + summary
    if fmt == "png":
        cached_image = file_cache.get_image(chain, tx_hash, template)
        if cached_image:
            cached_summary = file_cache.get_summary(chain, tx_hash)
            return Response(content=cached_image, media_type="image/png")

    if fmt == "json":
        cached_summary = file_cache.get_summary(chain, tx_hash)
        if cached_summary:
            return _json_response(cached_summary, cached=True)

    # 3. Check negative cache
    neg = file_cache.get_negative(chain, tx_hash)
    if neg == "pending":
        raise HTTPException(status_code=202, detail="Transaction pending confirmation. Try again shortly.")
    if neg == "not_found":
        raise HTTPException(status_code=404, detail="Transaction not found")

    # 4. Check in-memory tx cache, else fetch from RPC
    tx_data = tx_cache.get(chain, tx_hash)
    if tx_data is CACHE_MISS:
        tx_data = await fetch_transaction(chain, tx_hash)
        tx_cache.set(chain, tx_hash, tx_data)

    if tx_data is None:
        file_cache.set_negative(chain, tx_hash, "not_found")
        raise HTTPException(status_code=404, detail="Transaction not found")

    # 5. Handle pending
    if tx_data.status == "pending":
        file_cache.set_negative(chain, tx_hash, "pending")
        if fmt == "json":
            return JSONResponse(
                content={"status": "pending", "detail": "Transaction pending confirmation. Try again shortly."},
                status_code=202,
            )
        raise HTTPException(status_code=202, detail="Transaction pending confirmation. Try again shortly.")

    # 6. Render card (classifies actions, resolves tokens, renders SVG/PNG)
    tx_dict = tx_data.model_dump(mode="json")

    try:
        card_data, summary = await render_receipt_card(tx_dict, template=template, format=fmt)
    except Exception:
        logger.exception("Card render failed for %s:%s", chain, tx_hash)
        raise HTTPException(status_code=500, detail="Failed to generate receipt card. Please try again.")

    # 7. Cache summary JSON (shared across templates)
    file_cache.set_summary(chain, tx_hash, summary)

    # 8. Cache PNG to filesystem (SVG returned inline, not persisted)
    if fmt == "png" and isinstance(card_data, bytes):
        file_cache.set_image(chain, tx_hash, template, card_data)

    # 9. Return
    if fmt == "svg":
        return Response(content=card_data, media_type="image/svg+xml")
    elif fmt == "png":
        return Response(content=card_data, media_type="image/png")
    else:
        return _json_response(summary, cached=False)


def _json_response(summary: dict, cached: bool) -> JSONResponse:
    return JSONResponse(content={
        "summary": summary,
        "card": {
            "format": "json",
            "width": 1200,
            "height": 630,
            "cached": cached,
        },
    })


# ---------- OG Meta Page (Phase 7: Viral Loop) ----------

@app.get("/receipt/{chain}/{tx_hash}", response_class=HTMLResponse)
async def receipt_page(chain: str, tx_hash: str):
    """
    Public receipt page with OG meta tags for social embed previews.
    Serves HTML that X/Discord/Telegram crawlers will parse for auto-embedding.
    """
    try:
        chain = validate_chain(chain)
        tx_hash = validate_tx_hash(chain, tx_hash)
    except HTTPException:
        return HTMLResponse(content=_error_html("Invalid chain or transaction hash"), status_code=400)

    # Try cached summary first (fast path for OG pages)
    summary = file_cache.get_summary(chain, tx_hash)

    if summary:
        title = _build_og_title(summary)
        status = summary.get("status", "confirmed")
    else:
        title = f"Transaction on {chain.title()}"
        status = "confirmed"

    image_url = f"/v1/receipt/{chain}/card/{tx_hash}/classic.png"
    page_url = f"/receipt/{chain}/{tx_hash}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape_html(title)}</title>

    <!-- Open Graph -->
    <meta property="og:title" content="{_escape_html(title)}" />
    <meta property="og:description" content="Onchain receipt powered by APIX402" />
    <meta property="og:image" content="{image_url}" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta property="og:type" content="website" />

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{_escape_html(title)}" />
    <meta name="twitter:description" content="Onchain receipt powered by APIX402" />
    <meta name="twitter:image" content="{image_url}" />

    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0D1117; color: #E6EDF3; margin: 0; padding: 40px 20px;
            display: flex; flex-direction: column; align-items: center; min-height: 100vh;
        }}
        .card {{ max-width: 640px; width: 100%; }}
        .card img {{ width: 100%; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.3); }}
        h1 {{ font-size: 20px; margin: 24px 0 8px; }}
        .meta {{ color: #8B949E; font-size: 14px; }}
        a {{ color: #58A6FF; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .cta {{ margin-top: 32px; padding: 12px 24px; background: #238636; color: white;
                border-radius: 8px; font-weight: bold; display: inline-block; }}
    </style>
</head>
<body>
    <div class="card">
        <img src="{image_url}" alt="Onchain Receipt" />
        <h1>{_escape_html(title)}</h1>
        <p class="meta">{chain.title()} &middot; {_escape_html(tx_hash[:10])}...{_escape_html(tx_hash[-6:])}</p>
        <a class="cta" href="https://apix402.com">Powered by APIX402 &rarr;</a>
    </div>
</body>
</html>"""

    return HTMLResponse(content=html)


# ---------- Direct card image endpoint (for OG image tags) ----------

@app.get("/v1/receipt/{chain}/card/{tx_hash}/{template}.png")
async def receipt_card_image(chain: str, tx_hash: str, template: str):
    """Direct PNG endpoint for OG image tags and direct linking."""
    try:
        chain = validate_chain(chain)
        tx_hash = validate_tx_hash(chain, tx_hash)
    except HTTPException:
        raise HTTPException(status_code=400, detail="Invalid chain or transaction hash")

    template = template if template in ("classic", "minimal", "dark") else "classic"

    # Check file cache
    cached_image = file_cache.get_image(chain, tx_hash, template)
    if cached_image:
        return Response(content=cached_image, media_type="image/png")

    # Fetch + render on demand
    tx_data = tx_cache.get(chain, tx_hash)
    if tx_data is CACHE_MISS:
        tx_data = await fetch_transaction(chain, tx_hash)
        tx_cache.set(chain, tx_hash, tx_data)

    if tx_data is None or tx_data.status == "pending":
        raise HTTPException(status_code=404, detail="Transaction not available for rendering")

    tx_dict = tx_data.model_dump(mode="json")
    card_data, summary = await render_receipt_card(tx_dict, template=template, format="png")

    file_cache.set_summary(chain, tx_hash, summary)
    file_cache.set_image(chain, tx_hash, template, card_data)

    return Response(content=card_data, media_type="image/png")


# ---------- Helpers ----------

def _build_og_title(summary: dict) -> str:
    label = summary.get("action_label", "")
    detail = summary.get("action_detail", "")
    chain = (summary.get("chain") or "").title()

    if label and detail:
        return f"{label} {detail} on {chain}"
    if label:
        return f"{label} on {chain}"
    return f"Transaction on {chain}"


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _error_html(message: str) -> str:
    return f"""<!DOCTYPE html><html><head><title>Error</title></head>
<body style="font-family:sans-serif;padding:40px;background:#0D1117;color:#E6EDF3">
<h1>Error</h1><p>{_escape_html(message)}</p></body></html>"""

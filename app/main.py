import logging
import re
from typing import Optional

import base58
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from app.cache.file_cache import file_cache
from app.cache.manager import CACHE_MISS, tx_cache
from app.fetchers import fetch_transaction
from app.renderer.card import render_receipt_card
from app.validation.input import validate_chain, validate_tx_hash

EVM_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

app = FastAPI(title="Onchain Receipt Card API", version="0.2.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8", errors="replace")[:2000]
    logger.info(
        "INCOMING REQUEST: %s %s | content-type=%s | body=%s",
        request.method,
        request.url.path,
        request.headers.get("content-type", "MISSING"),
        body_text or "(empty)",
    )
    logger.info(
        "REQUEST HEADERS: %s",
        dict(request.headers),
    )
    response = await call_next(request)
    logger.info(
        "RESPONSE: %s %s -> %s",
        request.method,
        request.url.path,
        response.status_code,
    )
    return response


class ReceiptRequest(BaseModel):
    tx_hash: Optional[str] = None
    query: Optional[str] = None
    prompt: Optional[str] = None
    body: Optional[dict] = None
    template: str = "classic"
    format: str = "json"


def _unwrap_apix_body(body: ReceiptRequest) -> ReceiptRequest:
    """Handle APIX agent quirks: nested body.body wrapping and query/prompt aliases."""
    if body.body and isinstance(body.body, dict):
        logger.info("APIX UNWRAP: detected nested body: %s", body.body)
        inner = body.body
        if not body.tx_hash:
            body.tx_hash = inner.get("tx_hash") or inner.get("query") or inner.get("prompt")
        if body.template == "classic" and inner.get("template"):
            body.template = inner["template"]
        if body.format == "json" and inner.get("format"):
            body.format = inner["format"]

    if not body.tx_hash:
        body.tx_hash = body.query or body.prompt
        if body.tx_hash:
            logger.info("APIX ALIAS: used query/prompt as tx_hash: %s", body.tx_hash)

    # Strip key=value prefixes that APIX agents sometimes include
    if body.tx_hash:
        for prefix in ("tx_hash=", "query=", "prompt="):
            if body.tx_hash.startswith(prefix):
                body.tx_hash = body.tx_hash[len(prefix):]
                logger.info("APIX STRIP: removed '%s' prefix, tx_hash now: %s", prefix, body.tx_hash)
                break

    return body


@app.get("/v1/receipt/{chain}")
async def receipt_info(chain: str):
    logger.info("GET /v1/receipt/%s (info endpoint)", chain)
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


@app.post("/v1/receipt/{chain}")
async def generate_receipt(chain: str, body: ReceiptRequest):
    logger.info("POST /v1/receipt/%s | raw body fields: tx_hash=%s, query=%s, prompt=%s, nested_body=%s, template=%s, format=%s",
                chain, body.tx_hash, body.query, body.prompt, body.body, body.template, body.format)

    body = _unwrap_apix_body(body)

    if not body.tx_hash:
        logger.error("NO tx_hash after unwrapping. Full body model: %s", body.model_dump())
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Missing tx_hash",
                "hint": "Send {\"tx_hash\": \"0x...\"}. Also accepted: query or prompt fields.",
                "received_body": body.model_dump(),
            },
        )

    chain = validate_chain(chain)
    tx_hash = validate_tx_hash(chain, body.tx_hash)
    template = body.template if body.template in ("classic", "minimal", "dark") else "classic"
    fmt = body.format if body.format in ("json", "svg", "png") else "json"

    logger.info("VALIDATED: chain=%s tx_hash=%s template=%s format=%s", chain, tx_hash, template, fmt)

    if fmt == "png":
        cached_image = file_cache.get_image(chain, tx_hash, template)
        if cached_image:
            logger.info("CACHE HIT (png image) for %s/%s/%s", chain, tx_hash[:12], template)
            return Response(content=cached_image, media_type="image/png")

    if fmt == "json":
        cached_summary = file_cache.get_summary(chain, tx_hash)
        if cached_summary:
            logger.info("CACHE HIT (json summary) for %s/%s", chain, tx_hash[:12])
            return _json_response(cached_summary, cached=True)

    neg = file_cache.get_negative(chain, tx_hash)
    if neg == "pending":
        logger.info("NEGATIVE CACHE: pending for %s/%s", chain, tx_hash[:12])
        raise HTTPException(status_code=202, detail="Transaction pending confirmation. Try again shortly.")
    if neg == "not_found":
        logger.info("NEGATIVE CACHE: not_found for %s/%s", chain, tx_hash[:12])
        raise HTTPException(status_code=404, detail="Transaction not found")

    tx_data = tx_cache.get(chain, tx_hash)
    if tx_data is CACHE_MISS:
        logger.info("CACHE MISS (memory): fetching %s/%s from RPC", chain, tx_hash[:12])
        tx_data = await fetch_transaction(chain, tx_hash)
        tx_cache.set(chain, tx_hash, tx_data)
    else:
        logger.info("CACHE HIT (memory) for %s/%s", chain, tx_hash[:12])

    if tx_data is None:
        logger.warning("RPC returned None for %s/%s", chain, tx_hash[:12])
        file_cache.set_negative(chain, tx_hash, "not_found")
        raise HTTPException(status_code=404, detail="Transaction not found")

    if tx_data.status == "pending":
        logger.info("Transaction pending: %s/%s", chain, tx_hash[:12])
        file_cache.set_negative(chain, tx_hash, "pending")
        if fmt == "json":
            return JSONResponse(
                content={"status": "pending", "detail": "Transaction pending confirmation. Try again shortly."},
                status_code=202,
            )
        raise HTTPException(status_code=202, detail="Transaction pending confirmation. Try again shortly.")

    logger.info("RENDERING card for %s/%s (template=%s, format=%s)", chain, tx_hash[:12], template, fmt)
    tx_dict = tx_data.model_dump(mode="json")
    card_data, summary = await render_receipt_card(tx_dict, template=template, format=fmt)

    file_cache.set_summary(chain, tx_hash, summary)

    if fmt == "png" and isinstance(card_data, bytes):
        file_cache.set_image(chain, tx_hash, template, card_data)

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


@app.get("/receipt/{chain}/{tx_hash}", response_class=HTMLResponse)
async def receipt_page(chain: str, tx_hash: str):
    try:
        chain = validate_chain(chain)
        tx_hash = validate_tx_hash(chain, tx_hash)
    except HTTPException:
        return HTMLResponse(content=_error_html("Invalid chain or transaction hash"), status_code=400)

    summary = file_cache.get_summary(chain, tx_hash)

    if summary:
        title = _build_og_title(summary)
    else:
        title = f"Transaction on {chain.title()}"

    image_url = f"/v1/receipt/{chain}/card/{tx_hash}/classic.png"

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


@app.get("/v1/receipt/{chain}/card/{tx_hash}/{template}.png")
async def receipt_card_image(chain: str, tx_hash: str, template: str):
    try:
        chain = validate_chain(chain)
        tx_hash = validate_tx_hash(chain, tx_hash)
    except HTTPException:
        raise HTTPException(status_code=400, detail="Invalid chain or transaction hash")

    template = template if template in ("classic", "minimal", "dark") else "classic"

    cached_image = file_cache.get_image(chain, tx_hash, template)
    if cached_image:
        return Response(content=cached_image, media_type="image/png")

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


def _detect_chain(tx_hash: str) -> str:
    """Auto-detect chain from tx hash format."""
    if EVM_TX_RE.match(tx_hash):
        return "base"
    try:
        decoded = base58.b58decode(tx_hash)
        if len(decoded) == 64:
            return "solana"
    except Exception:
        pass
    raise HTTPException(status_code=400, detail="Cannot detect chain from tx hash format")


@app.get("/{tx_hash}")
async def short_image_route(tx_hash: str, template: str = Query(default="classic")):
    """Short-path image route for APIX: /{tx_hash}?template=dark"""
    logger.info("SHORT PATH: /%s?template=%s", tx_hash[:16], template)
    chain = _detect_chain(tx_hash)
    validate_tx_hash(chain, tx_hash)
    template = template if template in ("classic", "minimal", "dark") else "classic"

    cached_image = file_cache.get_image(chain, tx_hash, template)
    if cached_image:
        logger.info("SHORT PATH CACHE HIT for %s/%s/%s", chain, tx_hash[:12], template)
        return Response(content=cached_image, media_type="image/png")

    tx_data = tx_cache.get(chain, tx_hash)
    if tx_data is CACHE_MISS:
        logger.info("SHORT PATH: fetching %s/%s from RPC", chain, tx_hash[:12])
        tx_data = await fetch_transaction(chain, tx_hash)
        tx_cache.set(chain, tx_hash, tx_data)

    if tx_data is None or tx_data.status == "pending":
        raise HTTPException(status_code=404, detail="Transaction not available for rendering")

    tx_dict = tx_data.model_dump(mode="json")
    card_data, summary = await render_receipt_card(tx_dict, template=template, format="png")

    file_cache.set_summary(chain, tx_hash, summary)
    file_cache.set_image(chain, tx_hash, template, card_data)

    logger.info("SHORT PATH: rendered and cached %s/%s/%s", chain, tx_hash[:12], template)
    return Response(content=card_data, media_type="image/png")


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

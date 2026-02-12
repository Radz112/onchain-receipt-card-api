from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.cache.manager import CACHE_MISS, tx_cache
from app.fetchers import fetch_transaction
from app.renderer.card import render_receipt_card
from app.validation.input import validate_chain, validate_tx_hash

app = FastAPI(title="Onchain Receipt Card API", version="0.1.0")


class ReceiptRequest(BaseModel):
    tx_hash: str
    template: str = "classic"
    format: str = "json"


@app.get("/v1/receipt/{chain}")
async def receipt_info(chain: str):
    chain = validate_chain(chain)
    return {
        "chain": chain,
        "description": f"POST a tx_hash to fetch a normalized {chain} transaction receipt.",
        "usage": {
            "method": "POST",
            "body": {"tx_hash": "string", "template": "classic|minimal|dark", "format": "json|svg|png"},
        },
    }


@app.post("/v1/receipt/{chain}")
async def fetch_receipt(chain: str, body: ReceiptRequest):
    chain = validate_chain(chain)
    tx_hash = validate_tx_hash(chain, body.tx_hash)

    cached = tx_cache.get(chain, tx_hash)
    if cached is not CACHE_MISS:
        if cached is None:
            raise HTTPException(status_code=404, detail="Transaction not found (cached)")
        tx_data = cached
    else:
        tx_data = await fetch_transaction(chain, tx_hash)
        tx_cache.set(chain, tx_hash, tx_data)

    if tx_data.status == "pending" and body.format == "json":
        return JSONResponse(content=tx_data.model_dump(mode="json"), status_code=202)

    if body.format in ("svg", "png"):
        tx_dict = tx_data.model_dump(mode="json")
        result = await render_receipt_card(tx_dict, template=body.template, format=body.format)

        if body.format == "svg":
            return Response(content=result, media_type="image/svg+xml")
        else:
            return Response(content=result, media_type="image/png")

    return tx_data

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import requests
from database import db, create_document, get_documents

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QuoteResponse(BaseModel):
    symbol: str
    price: float
    change: Optional[float] = None
    percent_change: Optional[float] = None
    name: Optional[str] = None

class WatchItemIn(BaseModel):
    user_id: str
    symbol: str
    name: Optional[str] = None

@app.get("/")
def read_root():
    return {"message": "Stocks API running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# --- Market Data Helpers ---
# We'll use a free public source for demo (Yahoo Finance unofficial JSON)
YF_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols}"


def fetch_quotes(symbols: List[str]) -> List[QuoteResponse]:
    if not symbols:
        return []
    url = YF_QUOTE_URL.format(symbols=",".join(symbols))
    r = requests.get(url, timeout=10)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch quotes")
    data = r.json()
    results = data.get("quoteResponse", {}).get("result", [])
    out: List[QuoteResponse] = []
    for item in results:
        out.append(
            QuoteResponse(
                symbol=item.get("symbol"),
                price=float(item.get("regularMarketPrice")) if item.get("regularMarketPrice") is not None else 0.0,
                change=item.get("regularMarketChange"),
                percent_change=item.get("regularMarketChangePercent"),
                name=item.get("shortName") or item.get("longName"),
            )
        )
    return out

# --- Endpoints ---

@app.get("/api/quotes", response_model=List[QuoteResponse])
def get_quotes(symbols: str):
    # symbols query param: "AAPL,MSFT,GOOG"
    syms = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    if not syms:
        raise HTTPException(status_code=400, detail="No symbols provided")
    return fetch_quotes(syms)

@app.get("/api/search")
def search_symbol(q: str):
    # Use Yahoo finance search API
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=6&newsCount=0"
    r = requests.get(url, timeout=10)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Search failed")
    data = r.json()
    quotes = data.get("quotes", [])
    results = [
        {
            "symbol": it.get("symbol"),
            "name": it.get("shortname") or it.get("longname") or it.get("symbol"),
            "exch": it.get("exchDisp"),
        }
        for it in quotes
        if it.get("symbol")
    ]
    return {"results": results}

@app.post("/api/watchlist")
def add_watchlist(item: WatchItemIn):
    try:
        from schemas import Watchitem
        doc = Watchitem(user_id=item.user_id, symbol=item.symbol.upper(), name=item.name)
        inserted_id = create_document("watchitem", doc)
        return {"id": inserted_id, "message": "Added to watchlist"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/watchlist")
def get_watchlist(user_id: str):
    try:
        items = get_documents("watchitem", {"user_id": user_id})
        # clean ObjectId
        for it in items:
            it["_id"] = str(it.get("_id"))
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

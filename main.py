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
    watchlist_id: Optional[str] = None
    group: Optional[str] = None

class WatchlistIn(BaseModel):
    user_id: str
    name: str

class OrderIn(BaseModel):
    user_id: str
    symbol: str
    side: str
    quantity: float
    price: float

class OrderUpdate(BaseModel):
    status: str

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
YF_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range}"


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

# --- Watchlists & Groups ---
@app.post("/api/watchlist")
def add_watchlist(item: WatchItemIn):
    try:
        from schemas import Watchitem
        doc = Watchitem(user_id=item.user_id, symbol=item.symbol.upper(), name=item.name, watchlist_id=item.watchlist_id, group=item.group)
        inserted_id = create_document("watchitem", doc)
        return {"id": inserted_id, "message": "Added to watchlist"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/watchlist")
def get_watchlist(user_id: str, watchlist_id: Optional[str] = None, group: Optional[str] = None):
    try:
        filt = {"user_id": user_id}
        if watchlist_id:
            filt["watchlist_id"] = watchlist_id
        if group:
            filt["group"] = group
        items = get_documents("watchitem", filt)
        for it in items:
            it["_id"] = str(it.get("_id"))
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/watchlists")
def create_watchlist(w: WatchlistIn):
    try:
        from schemas import Watchlist
        wid = create_document("watchlist", Watchlist(user_id=w.user_id, name=w.name))
        return {"id": wid, "message": "Watchlist created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/watchlists")
def list_watchlists(user_id: str):
    try:
        lists = get_documents("watchlist", {"user_id": user_id})
        for it in lists:
            it["_id"] = str(it.get("_id"))
        return {"items": lists}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Charts: Intraday & Historical OHLC ---
@app.get("/api/chart/intraday")
def intraday(symbol: str, interval: str = "1m", range: str = "1d"):
    try:
        url = YF_CHART_URL.replace("{symbol}", symbol).replace("{interval}", interval).replace("{range}", range)
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Chart fetch failed")
        data = r.json().get("chart", {})
        result = (data.get("result") or [])[0]
        timestamps = result.get("timestamp", [])
        indicators = result.get("indicators", {})
        ohlc = indicators.get("quote", [{}])[0]
        opens = ohlc.get("open", [])
        highs = ohlc.get("high", [])
        lows = ohlc.get("low", [])
        closes = ohlc.get("close", [])
        series = []
        for i, t in enumerate(timestamps):
            try:
                series.append({
                    "t": t,
                    "o": opens[i],
                    "h": highs[i],
                    "l": lows[i],
                    "c": closes[i]
                })
            except Exception:
                continue
        return {"symbol": symbol.upper(), "interval": interval, "range": range, "series": series}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chart/historical")
def historical(symbol: str, interval: str = "1d", range: str = "1y"):
    return intraday(symbol=symbol, interval=interval, range=range)

# --- Paper Trading Orders & Positions ---
@app.post("/api/orders")
def create_order(o: OrderIn):
    try:
        from schemas import Order
        # For demo, we immediately mark filled at the given price
        oid = create_document("order", Order(user_id=o.user_id, symbol=o.symbol.upper(), side=o.side, quantity=o.quantity, price=o.price, status='filled'))
        return {"id": oid, "message": "Order placed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders")
def list_orders(user_id: str):
    try:
        orders = get_documents("order", {"user_id": user_id})
        for it in orders:
            it["_id"] = str(it.get("_id"))
        return {"items": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/positions")
def positions(user_id: str):
    """Aggregate filled orders into net positions and P&L"""
    try:
        orders = get_documents("order", {"user_id": user_id, "status": "filled"})
        # Aggregate by symbol
        agg = {}
        for o in orders:
            sym = o.get("symbol").upper()
            qty = float(o.get("quantity", 0)) * (1 if o.get("side") == "buy" else -1)
            cost = float(o.get("price", 0)) * float(o.get("quantity", 0)) * (1 if o.get("side") == "buy" else -1)
            if sym not in agg:
                agg[sym] = {"symbol": sym, "qty": 0.0, "cost": 0.0}
            agg[sym]["qty"] += qty
            agg[sym]["cost"] += cost
        symbols = list(agg.keys())
        quotes = fetch_quotes(symbols) if symbols else []
        qmap = {q.symbol: q for q in quotes}
        positions = []
        for sym, a in agg.items():
            qty = a["qty"]
            avg_cost = (a["cost"] / abs(a["qty"])) if a["qty"] != 0 else 0.0
            mkt = qmap.get(sym)
            last = float(mkt.price) if mkt else 0.0
            pnl = (last - avg_cost) * qty
            positions.append({
                "symbol": sym,
                "quantity": qty,
                "avg_price": round(avg_cost, 4),
                "last": last,
                "unrealized_pnl": round(pnl, 2)
            })
        return {"items": positions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

from __future__ import annotations
import yfinance as yf


def last_price(symbol: str) -> float:
    t = yf.Ticker(symbol)
    # fast path
    info = getattr(t, "fast_info", None)
    if info and info.get("lastPrice"):
        return float(info["lastPrice"])
    # fallback
    hist = t.history(period="5d")
    if hist.empty:
        raise ValueError(f"No price data for {symbol}")
    return float(hist["Close"].iloc[-1])


def history(symbol: str, period: str = "6mo", interval: str = "1d"):
    t = yf.Ticker(symbol)
    df = t.history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No history for {symbol}")
    return df

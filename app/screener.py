from __future__ import annotations
import pandas as pd
from app.market_data import history


def momentum_score(symbol: str) -> dict:
    df = history(symbol, period="6mo", interval="1d")
    close = df["Close"].dropna()

    if len(close) < 60:
        raise ValueError(f"Not enough data for {symbol}")

    ret_1m = (close.iloc[-1] / close.iloc[-21]) - 1
    ret_3m = (close.iloc[-1] / close.iloc[-63]) - 1
    ret_6m = (close.iloc[-1] / close.iloc[0]) - 1

    vol_20d = close.pct_change().rolling(20).std().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1]
    above_sma50 = close.iloc[-1] > sma50

    return {
        "symbol": symbol,
        "ret_1m": float(ret_1m),
        "ret_3m": float(ret_3m),
        "ret_6m": float(ret_6m),
        "vol_20d": float(vol_20d),
        "above_sma50": bool(above_sma50),
        "score": float(ret_3m + ret_1m),
    }


def screen(symbols: list[str], top_n: int = 10) -> pd.DataFrame:
    rows = []
    for s in symbols:
        try:
            rows.append(momentum_score(s))
        except Exception:
            continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # ensure stable ordering and expected columns
    df = df.sort_values("score", ascending=False).head(top_n)
    return df

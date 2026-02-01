from __future__ import annotations
from datetime import date
from sqlmodel import select
from app.models import BenchmarkMark
from app.market_data import history


def init_benchmark(session, symbol: str, start_value: float):
    """Seed benchmark with starting capital."""
    exists = session.exec(
        select(BenchmarkMark).where(BenchmarkMark.symbol == symbol)
    ).first()
    if exists:
        return

    session.add(
        BenchmarkMark(
            symbol=symbol,
            marked_on=date.today(),
            value=start_value,
        )
    )
    session.commit()


def mark_benchmark(session, symbol: str):
    """Update benchmark value based on daily returns."""
    last = session.exec(
        select(BenchmarkMark)
        .where(BenchmarkMark.symbol == symbol)
        .order_by(BenchmarkMark.marked_on.desc())
    ).first()
    if not last:
        raise ValueError(f"Benchmark {symbol} not initialized")

    df = history(symbol, period="10d", interval="1d")
    if len(df) < 2:
        return last

    ret = (df["Close"].iloc[-1] / df["Close"].iloc[-2]) - 1
    new_value = last.value * (1 + ret)

    bm = BenchmarkMark(
        symbol=symbol,
        marked_on=date.today(),
        value=float(new_value),
    )
    session.add(bm)
    session.commit()
    return bm

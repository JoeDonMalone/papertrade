from __future__ import annotations
import pandas as pd
from sqlmodel import select
from app.models import DailyMark, BenchmarkMark


def load_equity_curve(session, account_id: int) -> pd.DataFrame:
    rows = session.exec(
        select(DailyMark)
        .where(DailyMark.account_id == account_id)
        .order_by(DailyMark.marked_on)
    ).all()
    return pd.DataFrame(
        [{"date": r.marked_on, "equity": r.equity} for r in rows]
    ).set_index("date")


def load_benchmark_curve(session, symbol: str) -> pd.DataFrame:
    rows = session.exec(
        select(BenchmarkMark)
        .where(BenchmarkMark.symbol == symbol)
        .order_by(BenchmarkMark.marked_on)
    ).all()
    return pd.DataFrame(
        [{"date": r.marked_on, "value": r.value} for r in rows]
    ).set_index("date")


def max_drawdown(series: pd.Series) -> float:
    peak = series.cummax()
    dd = (series / peak) - 1
    return float(dd.min())


def summary(portfolio: pd.Series, benchmark: pd.Series) -> dict:
    p_ret = (portfolio.iloc[-1] / portfolio.iloc[0]) - 1
    b_ret = (benchmark.iloc[-1] / benchmark.iloc[0]) - 1

    return {
        "portfolio_return": float(p_ret),
        "benchmark_return": float(b_ret),
        "alpha": float(p_ret - b_ret),
        "portfolio_max_dd": max_drawdown(portfolio),
        "benchmark_max_dd": max_drawdown(benchmark),
    }

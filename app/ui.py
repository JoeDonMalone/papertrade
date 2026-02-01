from __future__ import annotations

from datetime import date
import pandas as pd
import streamlit as st
import plotly.express as px
from sqlmodel import select

from app.db import create_db_and_tables, get_session
from app.models import Account, PositionLot, Trade, DailyMark, BenchmarkMark
from app.engine import mark_to_market, compute_equity
from app.benchmark import init_benchmark, mark_benchmark
from app.market_data import last_price


DEFAULT_BENCHMARKS = ["SPY", "QQQ"]


def fmt_pct(x: float) -> str:
    return f"{x*100:.2f}%"


def max_drawdown(series: pd.Series) -> float:
    peak = series.cummax()
    dd = (series / peak) - 1.0
    return float(dd.min()) if len(dd) else 0.0


def load_equity_curve(session, account_id: int) -> pd.DataFrame:
    rows = session.exec(
        select(DailyMark)
        .where(DailyMark.account_id == account_id)
        .order_by(DailyMark.marked_on)
    ).all()
    if not rows:
        return pd.DataFrame(columns=["date", "equity"]).set_index("date")
    df = pd.DataFrame(
        [{"date": r.marked_on, "equity": r.equity} for r in rows]
    ).set_index("date")
    return df


def load_benchmark_curve(session, symbol: str) -> pd.DataFrame:
    rows = session.exec(
        select(BenchmarkMark)
        .where(BenchmarkMark.symbol == symbol)
        .order_by(BenchmarkMark.marked_on)
    ).all()
    if not rows:
        return pd.DataFrame(columns=["date", "value"]).set_index("date")
    df = pd.DataFrame(
        [{"date": r.marked_on, "value": r.value} for r in rows]
    ).set_index("date")
    return df


def normalize_to_100(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    return (series / series.iloc[0]) * 100.0


def ensure_benchmarks(session, account: Account, benchmarks: list[str]):
    # seed benchmark series using current account equity (or cash if no marks)
    eq = compute_equity(session, account.name)
    for b in benchmarks:
        init_benchmark(session, b, start_value=eq)


def positions_table(session, account: Account) -> pd.DataFrame:
    lots = session.exec(
        select(PositionLot).where(PositionLot.account_id == account.id)
    ).all()
    rows = []
    for lot in lots:
        try:
            px = last_price(lot.symbol)
        except Exception:
            px = float("nan")
        mv = px * lot.qty if pd.notna(px) else float("nan")
        pnl = (px - lot.avg_cost) * lot.qty if pd.notna(px) else float("nan")
        rows.append(
            {
                "symbol": lot.symbol,
                "qty": lot.qty,
                "avg_cost": lot.avg_cost,
                "last": px,
                "mkt_value": mv,
                "pnl": pnl,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("mkt_value", ascending=False)
    return df


def trades_table(session, account: Account, limit: int = 50) -> pd.DataFrame:
    trs = session.exec(
        select(Trade)
        .where(Trade.account_id == account.id)
        .order_by(Trade.filled_at.desc())
        .limit(limit)
    ).all()
    rows = []
    for t in trs:
        rows.append(
            {
                "time": t.filled_at,
                "side": t.side,
                "symbol": t.symbol,
                "qty": t.qty,
                "fill": t.fill_price,
                "commission": t.commission,
                "note": t.note,
            }
        )
    return pd.DataFrame(rows)


st.set_page_config(page_title="Paper Trading Dashboard", layout="wide")
st.title("📈 Paper Trading Dashboard (Local)")

create_db_and_tables()

with get_session() as s:
    accounts = s.exec(select(Account).order_by(Account.name)).all()

if not accounts:
    st.warning("No accounts found. Run your init once to create 'core' and 'risk'.")
    st.stop()

acct_names = [a.name for a in accounts]

left, right = st.columns([1, 3])

with left:
    st.subheader("Controls")
    selected = st.selectbox(
        "Account",
        acct_names,
        index=acct_names.index("risk") if "risk" in acct_names else 0,
    )

    # Persist account selection across reruns
    if "account" not in st.session_state:
        st.session_state["account"] = "risk" if "risk" in acct_names else acct_names[0]

    selected = st.selectbox(
        "Account",
        acct_names,
        index=acct_names.index(st.session_state["account"]),
        key="account",
    )

    benchmarks = st.multiselect(
        "Benchmarks", DEFAULT_BENCHMARKS + ["VUG", "IWM"], default=DEFAULT_BENCHMARKS
    )

    if st.button("🔄 Update (Mark-to-market + Benchmarks)", width='content'):
        with get_session() as s:
            acct = s.exec(select(Account).where(Account.name == selected)).first()
            mark_to_market(s, selected)
            if benchmarks:
                ensure_benchmarks(s, acct, benchmarks)
                for b in benchmarks:
                    mark_benchmark(s, b)
        st.success("Updated for today.")
        st.rerun()

    st.caption("Tip: click Update once per day (or whenever you want fresh marks).")

with right:
    with get_session() as s:
        acct = s.exec(select(Account).where(Account.name == selected)).first()
        eq_now = compute_equity(s, selected)
        pos_df = positions_table(s, acct)
        tr_df = trades_table(s, acct)

        eq_curve = load_equity_curve(s, acct.id)
        bm_curves = {b: load_benchmark_curve(s, b) for b in benchmarks}

    k1, k2, k3 = st.columns(3)
    k1.metric("Equity", f"${eq_now:,.2f}")
    k2.metric("Cash", f"${acct.cash:,.2f}")
    k3.metric("Positions", f"{len(pos_df)}")

    st.markdown("---")

    # Equity vs Benchmarks
    st.subheader("Equity vs Benchmarks (Normalized)")
    chart_df = pd.DataFrame()

    # --- FIX: make x-axis a clean date, and de-dupe to 1 row/day ---
    chart_df = chart_df.copy()

    # Ensure index is a date (not datetime)
    idx = pd.to_datetime(chart_df.index).date
    chart_df.index = pd.Index(idx, name="date")

    # If multiple marks exist for the same date, keep the last one
    chart_df = chart_df.groupby(level=0).last().sort_index()

    # Portfolio
    if not eq_curve.empty:
        # de-dupe portfolio marks to 1/day
        eq_curve = eq_curve.groupby(level=0).last().sort_index()
        chart_df["Portfolio"] = normalize_to_100(eq_curve["equity"])

    # Benchmarks
    for b, df in bm_curves.items():
        if df is None or df.empty:
            continue

        # de-dupe benchmark marks to 1/day
        df = df.groupby(level=0).last().sort_index()

        # align to chart_df index safely
        chart_df[b] = normalize_to_100(df["value"]).reindex(chart_df.index)

    if chart_df.empty:
        st.info("No marks yet. Click Update to create your first marks.")
    else:
        chart_df = chart_df.dropna(how="all")
        long_df = chart_df.reset_index().melt(
            id_vars="date", var_name="series", value_name="index"
        )

        fig = px.line(long_df, x="date", y="index", color="series")
        st.plotly_chart(fig, width='content')
    chart_df = pd.DataFrame()

    # Portfolio: use its dates as the anchor index (if present)
    if not eq_curve.empty:
        eq_curve = eq_curve.groupby(level=0).last().sort_index()  # 1/day
        chart_df["Portfolio"] = normalize_to_100(eq_curve["equity"])

    # Benchmarks: if we have portfolio marks, align to them; otherwise keep benchmark dates
    for b, df in bm_curves.items():
        if df is None or df.empty:
            continue
        df = df.groupby(level=0).last().sort_index()  # 1/day
        s = normalize_to_100(df["value"])

        if not chart_df.empty:
            chart_df[b] = s.reindex(chart_df.index)
        else:
            chart_df[b] = s

    if chart_df.empty:
        st.info("No marks yet. Click Update to create your first marks.")
    else:
        chart_df = chart_df.groupby(level=0).last().sort_index()
        chart_df.index = pd.to_datetime(chart_df.index)  # clean date axis for plotly

        long_df = (
            chart_df.reset_index()
            .rename(columns={"index": "date"})
            .melt(id_vars="date", var_name="series", value_name="index")
            .dropna()
        )

        fig = px.line(long_df, x="date", y="index", color="series", markers=True)
        st.plotly_chart(fig, width='content')

        # Simple stats
        st.subheader("Stats")
        stats_rows = []
        p = (
            chart_df["Portfolio"].dropna()
            if "Portfolio" in chart_df.columns
            else pd.Series(dtype=float)
        )

        if not p.empty:
            p_ret = (p.iloc[-1] / p.iloc[0]) - 1.0
            p_dd = max_drawdown(p)
            stats_rows.append(
                {"series": "Portfolio", "return": p_ret, "max_drawdown": p_dd}
            )
            for b in benchmarks:
                srs = chart_df.get(b, pd.Series(dtype=float)).dropna()
                if not srs.empty:
                    b_ret = (srs.iloc[-1] / srs.iloc[0]) - 1.0
                    b_dd = max_drawdown(srs)
                    stats_rows.append(
                        {"series": b, "return": b_ret, "max_drawdown": b_dd}
                    )

        if stats_rows:
            stats_df = pd.DataFrame(stats_rows)
            stats_df["return"] = stats_df["return"].map(fmt_pct)
            stats_df["max_drawdown"] = stats_df["max_drawdown"].map(fmt_pct)
            st.dataframe(stats_df, width='content')

    st.markdown("---")

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Positions")
        if pos_df.empty:
            st.write("No positions.")
        else:
            st.dataframe(pos_df, width='content')

    with c2:
        st.subheader("Recent Trades")
        if tr_df.empty:
            st.write("No trades yet.")
        else:
            st.dataframe(tr_df, width='content')

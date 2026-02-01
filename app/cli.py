#!/usr/bin/env python

from __future__ import annotations
import typer
from rich import print
from rich.table import Table

from app.benchmark import init_benchmark, mark_benchmark
from app.compare import load_equity_curve, load_benchmark_curve, summary
from sqlmodel import select
from app.models import Account

from app.db import create_db_and_tables, get_session
from app.engine import (
    ensure_account,
    place_market_order,
    mark_to_market,
    compute_equity,
)
from app.screener import screen
from app.models import Journal
from app.reports import positions, recent_trades

app = typer.Typer(no_args_is_help=True)


@app.command()
def init(core_cash: float = 0, risk_cash: float = 0):
    """Initialize DB + create 'core' and 'risk' accounts."""
    create_db_and_tables()
    with get_session() as s:
        if core_cash:
            ensure_account(s, "core", core_cash)
        if risk_cash:
            ensure_account(s, "risk", risk_cash)
        if not core_cash and not risk_cash:
            ensure_account(s, "core", None)
            ensure_account(s, "risk", None)
    print("[green]Initialized.[/green]")


@app.command()
def buy(account: str, symbol: str, qty: float, note: str = typer.Argument("")):
    with get_session() as s:
        tr = place_market_order(s, account, symbol.upper(), "BUY", qty, note=note)
    print(
        f"[green]BUY[/green] {tr.qty} {tr.symbol} @ {tr.fill_price:.2f} (req {tr.requested_price:.2f})"
    )


@app.command()
def sell(account: str, symbol: str, qty: float, note: str = typer.Argument("")):
    with get_session() as s:
        tr = place_market_order(s, account, symbol.upper(), "SELL", qty, note=note)
    print(
        f"[red]SELL[/red] {tr.qty} {tr.symbol} @ {tr.fill_price:.2f} (req {tr.requested_price:.2f})"
    )


@app.command()
def journal(account: str, symbol: str, kind: str, text: str):
    with get_session() as s:
        # get account id
        from sqlmodel import select
        from app.models import Account

        acct = s.exec(select(Account).where(Account.name == account)).first()
        if not acct:
            raise typer.BadParameter("Account not found")
        j = Journal(
            account_id=acct.id, symbol=symbol.upper(), kind=kind.upper(), text=text
        )
        s.add(j)
        s.commit()
    print("[cyan]Journal entry saved.[/cyan]")


@app.command()
def mtm(account: str):
    with get_session() as s:
        m = mark_to_market(s, account)
    print(f"[yellow]MTM[/yellow] {account}: equity={m.equity:.2f} cash={m.cash:.2f}")


@app.command()
def equity(account: str):
    with get_session() as s:
        eq = compute_equity(s, account)
    print(f"[bold]{account}[/bold] equity: {eq:.2f}")


@app.command()
def show(account: str):
    with get_session() as s:
        rows, cash = positions(s, account)
        trs = recent_trades(s, account)

    t = Table(title=f"Positions ({account})")
    t.add_column("Symbol")
    t.add_column("Qty", justify="right")
    t.add_column("Avg Cost", justify="right")
    t.add_column("Last", justify="right")
    t.add_column("Mkt Value", justify="right")
    t.add_column("PnL", justify="right")

    for sym, qty, avg, last, mv, pnl in rows:
        t.add_row(
            sym, f"{qty:.4f}", f"{avg:.2f}", f"{last:.2f}", f"{mv:.2f}", f"{pnl:.2f}"
        )

    print(t)
    print(f"Cash: [bold]{cash:.2f}[/bold]")

    tt = Table(title="Recent Trades")
    tt.add_column("Time")
    tt.add_column("Side")
    tt.add_column("Symbol")
    tt.add_column("Qty", justify="right")
    tt.add_column("Fill", justify="right")
    tt.add_column("Note")
    for tr in trs:
        tt.add_row(
            str(tr.filled_at),
            tr.side,
            tr.symbol,
            f"{tr.qty:.4f}",
            f"{tr.fill_price:.2f}",
            tr.note or "",
        )
    print(tt)


@app.command()
def screen_symbols(symbols: str, top_n: int = 10):
    """
    Screen a comma-separated list, e.g. "AAPL,MSFT,NVDA,TSLA"
    """
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    df = screen(syms, top_n=top_n)
    print(df.columns)
    if df.empty:
        print("[red]No results.[/red]")
        raise typer.Exit(1)

    t = Table(title="Screen Results")
    for col in [
        "symbol",
        "score",
        "ret_1m",
        "ret_3m",
        "ret_6m",
        "vol_20d",
        "above_sma50",
    ]:
        t.add_column(col)
    for _, r in df.iterrows():
        t.add_row(
            r["symbol"],
            f'{r["score"]:.4f}',
            f'{r["ret_1m"]:.4f}',
            f'{r["ret_3m"]:.4f}',
            f'{r["ret_6m"]:.4f}',
            f'{r["vol_20d"]:.4f}',
            str(bool(r["above_sma50"])),
        )
    print(t)


@app.command()
def init_benchmarks(account: str, symbols: str = "SPY,QQQ"):
    with get_session() as s:
        acct = s.exec(select(Account).where(Account.name == account)).first()
        for sym in symbols.split(","):
            init_benchmark(s, sym.strip().upper(), acct.cash)
    print("[green]Benchmarks initialized.[/green]")


@app.command()
def mark_all(account: str, benchmarks: str = "SPY,QQQ"):
    with get_session() as s:
        mark_to_market(s, account)
        for sym in benchmarks.split(","):
            mark_benchmark(s, sym.strip().upper())
    print("[green]Marked portfolio + benchmarks.[/green]")


@app.command()
def compare(account: str, benchmark: str = "SPY"):
    with get_session() as s:
        acct = s.exec(select(Account).where(Account.name == account)).first()
        p = load_equity_curve(s, acct.id)["equity"]
        b = load_benchmark_curve(s, benchmark)["value"]

    stats = summary(p, b)
    print(
        f"""
Portfolio vs {benchmark}

Return:       {stats['portfolio_return']*100:.2f}%
Benchmark:    {stats['benchmark_return']*100:.2f}%
Alpha:        {stats['alpha']*100:.2f}%

Max DD (you): {stats['portfolio_max_dd']*100:.2f}%
Max DD (bm):  {stats['benchmark_max_dd']*100:.2f}%
"""
    )


if __name__ == "__main__":
    app()

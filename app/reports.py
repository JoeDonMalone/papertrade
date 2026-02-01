from __future__ import annotations
from sqlmodel import select
from app.models import Account, PositionLot, Trade
from app.market_data import last_price


def positions(session, account_name: str):
    acct = session.exec(select(Account).where(Account.name == account_name)).first()
    lots = session.exec(
        select(PositionLot).where(PositionLot.account_id == acct.id)
    ).all()
    out = []
    for lot in lots:
        px = last_price(lot.symbol)
        mv = px * lot.qty
        pnl = (px - lot.avg_cost) * lot.qty
        out.append((lot.symbol, lot.qty, lot.avg_cost, px, mv, pnl))
    return out, acct.cash


def recent_trades(session, account_name: str, limit: int = 20):
    acct = session.exec(select(Account).where(Account.name == account_name)).first()
    trs = session.exec(
        select(Trade)
        .where(Trade.account_id == acct.id)
        .order_by(Trade.filled_at.desc())
        .limit(limit)
    ).all()
    return trs

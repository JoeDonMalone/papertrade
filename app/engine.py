from __future__ import annotations
from datetime import date
from sqlmodel import select
from app.config import settings
from app.models import Account, PositionLot, Trade, DailyMark
from app.market_data import last_price


def _apply_slippage(price: float, side: str, bps: float) -> float:
    # BUY pays up; Sell receives less
    slip = price * (bps / 10_000.0)
    return price + slip if side.upper() == "BUY" else price - slip


def ensure_account(session, name: str, cash: float | None = None) -> Account:
    acct = session.exec(select(Account).where(Account.name == name)).first()
    if acct:
        return acct

    acct = Account(
        name=name, cash=float(cash if cash is not None else settings.default_cash)
    )
    session.add(acct)
    session.commit()
    session.refresh(acct)
    return acct


def place_market_order(
    session, account_name: str, symbol: str, side: str, qty: float, note: str = ""
) -> Trade:
    acct = session.exec(select(Account).where(Account.name == account_name)).first()
    if not acct:
        raise ValueError(f"Account '{account_name}' not found. Run init first")

    px = last_price(symbol)
    fill = _apply_slippage(px, side, settings.slippage_bps)
    commission = settings.commistion_per_trade
    side = side.upper()

    cost = fill * qty
    if side == "BUY":
        total = cost + commission
        if acct.cash < total:
            raise ValueError(
                f"Insufficient cash. Need {total:.2f}, have {acct.cash:.2f}"
            )
        acct.cash -= total
        # Add/merge lot
        lot = session.exec(
            select(PositionLot).where(
                PositionLot.account_id == acct.id, PositionLot.symbol == symbol
            )
        ).first()
        if lot:
            new_qty = lot.qty + qty
            lot.avg_cost = (lot.avg_cost * lot.qty + fill * qty) / new_qty
            lot.qty = new_qty

        else:
            session.add(
                PositionLot(account_id=acct.id, symbol=symbol, qty=qty, avg_cost=fill)
            )
    elif side == "SELL":
        lot = session.exec(
            select(PositionLot).where(
                PositionLot.account_id == acct.id, PositionLot.symbol == symbol
            )
        ).first()
        if not lot or lot.qty < qty:
            raise ValueError(f"Not enough shares to sell. Have {lot.qty if lot else 0}")
        proceeds = cost - commission
        acct.cash += proceeds
        lot.qty -= qty
        if lot.qty == 0:
            session.delete(lot)

    else:
        raise ValueError("Side must be BUY or SELL")

    tr = Trade(
        account_id=acct.id,
        symbol=symbol,
        side=side,
        qty=qty,
        requested_price=px,
        fill_price=fill,
        commission=commission,
        slippage_bps=settings.slippage_bps,
        note=note,
    )
    session.add(tr)
    session.add(acct)
    session.commit()
    session.refresh(tr)
    return tr


def compute_equity(session, account_name: str) -> float:
    acct = session.exec(select(Account).where(Account.name == account_name)).first()
    if not acct:
        raise ValueError(f"Account '{account_name}' not fount")
    lots = session.exec(
        select(PositionLot).where(PositionLot.account_id == acct.id)
    ).all()
    positions_value = 0.0
    for lot in lots:
        positions_value += lot.qty * last_price(lot.symbol)
    return float(acct.cash + positions_value)


def mark_to_market(session, account_name: str) -> DailyMark:
    acct = session.exec(select(Account).where(Account.name == account_name)).first()
    if not acct:
        raise ValueError(f"Account '{account_name}' not fount")
    equity = compute_equity(session, account_name)
    mark = DailyMark(
        account_id=acct.id, marked_on=date.today(), equity=equity, cash=acct.cash
    )
    session.add(mark)
    session.commit()
    session.refresh(mark)
    return mark

from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from sqlmodel import SQLModel, Field
from app.helpers import _utcnow


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    cash: float
    created_at: datetime = Field(default_factory=_utcnow)


class PositionLot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(index=True)
    symbol: str = Field(index=True)
    qty: float
    avg_cost: float
    opened_at: datetime = Field(default_factory=_utcnow)


class Trade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(index=True)
    symbol: str = Field(index=True)
    side: str  # BUY/SELL
    qty: float
    requested_price: float
    fill_price: float
    commission: float
    slippage_bps: float
    filled_at: datetime = Field(default_factory=_utcnow)
    note: str = ""


class DailyMark(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(index=True)
    marked_on: date = Field(index=True)
    equity: float
    cash: float


class Journal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow)
    account_id: int = Field(index=True)
    symbol: str = Field(index=True)
    kind: str
    text: str


class BenchmarkMark(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    marked_on: date = Field(index=True)
    value: float

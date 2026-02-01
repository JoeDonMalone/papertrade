from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("PAPERTRADE_DB", "papertrade.db")
    slippage_bps: float = float(os.getenv("SLIPPAGE_BPS", "10"))  # 10 bps = 0.10%
    commistion_per_trade: float = float(os.getenv("COMMISION_PER_TRADE", "0.50"))
    default_cash = float = float(os.getenv("DEFAULT_CASH", "5000"))


settings = Settings()

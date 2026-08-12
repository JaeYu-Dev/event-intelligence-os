import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import SessionLocal
from api.models import PortfolioPosition, Source


def seed():
    db = SessionLocal()
    try:
        # Sources
        for name, tier in [("sec_edgar", "A"), ("polymarket", "B"), ("yahoo_finance", "B")]:
            if not db.query(Source).filter(Source.source_name == name).first():
                db.add(Source(source_name=name, source_tier=tier))

        # Portfolio positions
        positions = [
            {"ticker": "LAC", "name": "Lithium Americas", "shares": 1200, "avg_cost": 4.85, "current_price": 5.62, "pl_percent": 15.9, "pl_usd": 924, "scenario_bias": "Bull"},
            {"ticker": "NVDA", "name": "NVIDIA", "shares": 50, "avg_cost": 875.0, "current_price": 812.5, "pl_percent": -7.1, "pl_usd": -3125, "scenario_bias": "Bear"},
            {"ticker": "XLE", "name": "Energy Select SPDR", "shares": 300, "avg_cost": 88.4, "current_price": 91.2, "pl_percent": 3.2, "pl_usd": 840, "scenario_bias": "Base"},
            {"ticker": "XBI", "name": "Biotech ETF", "shares": 200, "avg_cost": 78.0, "current_price": 84.5, "pl_percent": 8.3, "pl_usd": 1300, "scenario_bias": "Bull"},
            {"ticker": "TLT", "name": "20+ Year Treasury", "shares": 150, "avg_cost": 92.0, "current_price": 94.8, "pl_percent": 3.0, "pl_usd": 420, "scenario_bias": "Bull"},
        ]
        for p in positions:
            if not db.query(PortfolioPosition).filter(PortfolioPosition.ticker == p["ticker"]).first():
                db.add(PortfolioPosition(**p))
        db.commit()
        print("Seeded sources and portfolio positions")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

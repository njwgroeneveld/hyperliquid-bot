"""
Sla trade logs op als JSON bestanden (alleen bij daadwerkelijke trade).
"""

import json
from datetime import datetime, timezone
from pathlib import Path


class TradeLogger:
    def __init__(self, log_dir: str = "logs/trades"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def save(self, trade: dict) -> str:
        trade_id = trade.get("trade_id", "UNKNOWN")
        filename = f"{trade_id}.json"
        filepath = self.log_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(trade, f, indent=2, ensure_ascii=False, default=str)

        return str(filepath)

    def update(self, trade_id: str, updates: dict):
        """Update een bestaand trade log (bijv. bij sluiting)."""
        filepath = self.log_dir / f"{trade_id}.json"
        if not filepath.exists():
            return

        with open(filepath, encoding="utf-8") as f:
            trade = json.load(f)

        trade.update(updates)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(trade, f, indent=2, ensure_ascii=False, default=str)

    def load(self, trade_id: str) -> dict | None:
        filepath = self.log_dir / f"{trade_id}.json"
        if not filepath.exists():
            return None
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)

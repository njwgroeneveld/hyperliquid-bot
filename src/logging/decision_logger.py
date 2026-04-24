"""
Sla beslissingsrapporten op als JSON bestanden.
Beslissingsrapporten worden elk uur gegenereerd, ongeacht of er een trade is.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


class DecisionLogger:
    def __init__(self, log_dir: str = "logs/decisions"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def save(self, report: dict) -> str:
        coin = report.get("coin", "UNKNOWN")
        timestamp = report.get("timestamp", datetime.now(timezone.utc).isoformat())
        ts = timestamp.replace(":", "-").replace(".", "-")[:19]
        filename = f"{coin}_{ts}.json"
        filepath = self.log_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        return str(filepath)

    def load_latest(self, coin: str) -> dict | None:
        files = sorted(self.log_dir.glob(f"{coin}_*.json"), reverse=True)
        if not files:
            return None
        with open(files[0], encoding="utf-8") as f:
            return json.load(f)

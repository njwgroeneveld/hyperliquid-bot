"""
Sla detectierapporten op als JSON bestanden en in de SQLite database.
Detectierapporten worden elk uur gegenereerd, ongeacht of er een trade is.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class DetectionLogger:
    def __init__(self, log_dir: str = "logs/detection"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def save(self, report: dict) -> str:
        """
        Sla detectierapport op als JSON bestand.
        Bestandsnaam: BTC_2025-04-23_09-00.json
        Returns the file path.
        """
        coin = report.get("coin", "UNKNOWN")
        timestamp = report.get("timestamp", datetime.now(timezone.utc).isoformat())

        # Maak leesbare bestandsnaam
        ts = timestamp.replace(":", "-").replace(".", "-")[:19]
        filename = f"{coin}_{ts}.json"
        filepath = self.log_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        return str(filepath)

    def load_latest(self, coin: str) -> dict | None:
        """Laad het meest recente detectierapport voor een coin."""
        files = sorted(self.log_dir.glob(f"{coin}_*.json"), reverse=True)
        if not files:
            return None
        with open(files[0], encoding="utf-8") as f:
            return json.load(f)

    def load_all(self, coin: str, limit: int = 24) -> list[dict]:
        """Laad de laatste N detectierapporten voor een coin."""
        files = sorted(self.log_dir.glob(f"{coin}_*.json"), reverse=True)[:limit]
        reports = []
        for fp in files:
            with open(fp, encoding="utf-8") as f:
                reports.append(json.load(f))
        return reports

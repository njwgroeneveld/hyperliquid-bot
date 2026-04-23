"""
SQLite database interface voor detectierapporten, beslissingsrapporten en trade logs.
"""

import json
import sqlite3
from pathlib import Path


CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS detection_reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    coin        TEXT NOT NULL,
    price       REAL,
    trend_4h    TEXT,
    trend_1h    TEXT,
    raw_json    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    coin        TEXT NOT NULL,
    score       TEXT,
    beslissing  TEXT,
    raw_json    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT UNIQUE NOT NULL,
    timestamp_open  TEXT NOT NULL,
    coin            TEXT NOT NULL,
    richting        TEXT NOT NULL,
    entry           REAL,
    stop_loss       REAL,
    target          REAL,
    leverage        REAL,
    positie_usd     REAL,
    risico_usd      REAL,
    score           TEXT,
    vertrouwen      TEXT,
    sessie          TEXT,
    hl_order_id     TEXT,
    status          TEXT DEFAULT 'OPEN',
    timestamp_close TEXT,
    close_prijs     REAL,
    resultaat_usd   REAL,
    resultaat_r     REAL,
    close_reden     TEXT,
    raw_json        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_detection_coin ON detection_reports(coin, timestamp);
CREATE INDEX IF NOT EXISTS idx_decision_coin ON decision_reports(coin, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_coin ON trades(coin, status);
"""


class Database:
    def __init__(self, db_path: str = "database/bot.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(CREATE_TABLES)
        self._migrate()

    def _migrate(self):
        with self._connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
            if "hl_order_id" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN hl_order_id TEXT")

    def insert_detection(self, report: dict):
        sql = """
        INSERT INTO detection_reports (timestamp, coin, price, trend_4h, trend_1h, raw_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        trend_4h = report.get("structuur_4h", {}).get("trend")
        trend_1h = report.get("structuur_1h", {}).get("trend")
        with self._connect() as conn:
            conn.execute(sql, (
                report.get("timestamp"),
                report.get("coin"),
                report.get("huidige_prijs"),
                trend_4h,
                trend_1h,
                json.dumps(report, default=str),
            ))

    def insert_decision(self, report: dict):
        sql = """
        INSERT INTO decision_reports (timestamp, coin, score, beslissing, raw_json)
        VALUES (?, ?, ?, ?, ?)
        """
        with self._connect() as conn:
            conn.execute(sql, (
                report.get("timestamp"),
                report.get("coin"),
                report.get("eindscore"),
                report.get("beslissing"),
                json.dumps(report, default=str),
            ))

    def insert_trade(self, trade: dict):
        sql = """
        INSERT INTO trades (
            trade_id, timestamp_open, coin, richting, entry, stop_loss, target,
            leverage, positie_usd, risico_usd, score, vertrouwen, sessie, hl_order_id, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._connect() as conn:
            conn.execute(sql, (
                trade["trade_id"],
                trade["timestamp_open"],
                trade["coin"],
                trade["richting"],
                trade.get("entry"),
                trade.get("stop_loss"),
                trade.get("target"),
                trade.get("leverage"),
                trade.get("positiegrootte_usd"),
                trade.get("risico_usd"),
                trade.get("score"),
                trade.get("vertrouwen"),
                trade.get("sessie"),
                trade.get("hl_order_id"),
                json.dumps(trade, default=str),
            ))

    def close_trade(self, trade_id: str, close_prijs: float, resultaat_usd: float,
                    resultaat_r: float, reden: str, timestamp: str):
        sql = """
        UPDATE trades
        SET status='GESLOTEN', timestamp_close=?, close_prijs=?,
            resultaat_usd=?, resultaat_r=?, close_reden=?
        WHERE trade_id=?
        """
        with self._connect() as conn:
            conn.execute(sql, (timestamp, close_prijs, resultaat_usd, resultaat_r, reden, trade_id))

    def get_open_trades(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()
            return [dict(row) for row in rows]

    def get_recent_detections(self, coin: str, limit: int = 24) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM detection_reports WHERE coin=? ORDER BY timestamp DESC LIMIT ?",
                (coin, limit),
            ).fetchall()
            return [dict(row) for row in rows]

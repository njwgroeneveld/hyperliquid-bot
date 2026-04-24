"""
Combineert alle detectiemodules tot één detectierapport per coin per uur.
"""

from datetime import datetime, timezone

import pandas as pd

from src.detection import market_structure, supply_demand, imbalance, liquidity, momentum, order_flow


class Detector:
    def __init__(self, settings: dict):
        self.swing_n = settings["strategy"]["swing_n"]
        self.equal_tolerance = settings["strategy"]["equal_tolerance"]
        self.impulse_min_body_pct = settings["strategy"]["impulse_min_body_pct"]
        self.impulse_min_move_pct = settings["strategy"]["impulse_min_move_pct"]

    def run(
        self,
        coin: str,
        df_4h: pd.DataFrame,
        df_1h: pd.DataFrame,
        orderbook: dict,
        meta: dict,
        meta_previous: dict | None = None,
    ) -> dict:
        """
        Run all detection modules and return the complete detection report.
        This runs every hour regardless of whether a trade is taken.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        current_price = float(df_1h["close"].iloc[-1]) if not df_1h.empty else 0.0

        # --- 4H analyse ---
        struct_4h = market_structure.detect(df_4h, "4H", n=self.swing_n)
        zones_4h = supply_demand.detect(
            df_4h, "4H",
            min_body_pct=self.impulse_min_body_pct,
            min_move_pct=self.impulse_min_move_pct,
        )
        imbalances_4h = imbalance.detect(df_4h, "4H")

        # Liquidity needs swing points from market structure
        swing_highs_4h = struct_4h.get("alle_swing_highs", [])
        swing_lows_4h = struct_4h.get("alle_swing_lows", [])
        liq_4h = liquidity.detect(
            df_4h, swing_highs_4h, swing_lows_4h, "4H",
            tolerance=self.equal_tolerance,
        )
        mom_4h = momentum.detect(df_4h, "4H")

        # --- 1H analyse ---
        struct_1h = market_structure.detect(df_1h, "1H", n=self.swing_n)
        zones_1h = supply_demand.detect(
            df_1h, "1H",
            min_body_pct=self.impulse_min_body_pct,
            min_move_pct=self.impulse_min_move_pct,
        )
        imbalances_1h = imbalance.detect(df_1h, "1H")

        swing_highs_1h = struct_1h.get("alle_swing_highs", [])
        swing_lows_1h = struct_1h.get("alle_swing_lows", [])
        liq_1h = liquidity.detect(
            df_1h, swing_highs_1h, swing_lows_1h, "1H",
            tolerance=self.equal_tolerance,
        )
        mom_1h = momentum.detect(df_1h, "1H")

        # --- Order flow ---
        of = order_flow.detect(orderbook, meta, meta_previous, coin, current_price)

        return {
            "timestamp": timestamp,
            "coin": coin,
            "huidige_prijs": current_price,
            "structuur_4h": struct_4h,
            "structuur_1h": struct_1h,
            "zones_4h": zones_4h,
            "zones_1h": zones_1h,
            "imbalances_4h": imbalances_4h,
            "imbalances_1h": imbalances_1h,
            "liquiditeit_4h": liq_4h,
            "liquiditeit_1h": liq_1h,
            "momentum_4h": mom_4h,
            "momentum_1h": mom_1h,
            "order_flow": of,
        }

"""
Python re-implementation of the Pine Script v5 strategy "TQQQ TEMACD".

Reproduces, bar-for-bar:
  - EMA1 / EMA2 / EMA3  (ta.ema equivalents)
  - MACD / signal / delta histogram
  - long/short crossover & crossunder conditions
  - the entry/exit/reversal position state machine driven by
    strategy.entry(...) and strategy.exit(..., stop=close)

Notes on the translation:
  - Pine's strategy.entry() with an opposing existing position reverses
    the net position; combined with the explicit stop-exits in the
    script, the net effect (for pyramiding=1, which is the default) is
    a same-bar state machine: whichever condition fires wins, and if
    no new condition fires, an opposite-direction exit condition can
    still flatten an open position. That state machine is implemented
    in TemacdStrategy.run() below.
  - All order-fill timing / slippage / commission nuances of the Pine
    broker emulator are intentionally not modeled — this is meant for
    directional signal generation (weekly alerts), not cent-perfect
    backtest replication.
"""

import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    """Equivalent to Pine's ta.ema()."""
    return series.ewm(span=length, adjust=False).mean()


def crossover(a: pd.Series, b) -> pd.Series:
    """Equivalent to Pine's ta.crossover(a, b)."""
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    return (a.shift(1) <= b.shift(1)) & (a > b)


def crossunder(a: pd.Series, b) -> pd.Series:
    """Equivalent to Pine's ta.crossunder(a, b)."""
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    return (a.shift(1) >= b.shift(1)) & (a < b)


class TemacdStrategy:
    def __init__(
        self,
        len1=5,
        len2=50,
        len3=222,
        fast=61,
        slow=70,
        macd_len=15,
        trade_direction="Long",
        start_date="2018-01-01",
        end_date="2170-12-31",
    ):
        self.len1 = len1
        self.len2 = len2
        self.len3 = len3
        self.fast = fast
        self.slow = slow
        self.macd_len = macd_len
        self.trade_direction = trade_direction
        self.start_date = pd.Timestamp(start_date)
        self.end_date = pd.Timestamp(end_date)

    # ── indicators ────────────────────────────────────────────────
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["Close"]

        df["EMA1"] = ema(close, self.len1)
        df["EMA2"] = ema(close, self.len2)
        df["EMA3"] = ema(close, self.len3)

        macd = ema(close, self.fast) - ema(close, self.slow)
        amacd = ema(macd, self.macd_len)

        df["MACD"] = macd
        df["aMACD"] = amacd
        df["delta"] = macd - amacd
        return df

    # ── signals ───────────────────────────────────────────────────
    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.compute_indicators(df)

        long_cond = (
            crossover(df["delta"], 0)
            | crossover(df["EMA1"], df["EMA2"])
            | crossover(df["EMA1"], df["EMA3"])
            | crossover(df["EMA2"], df["EMA3"])
        )
        short_cond = (
            crossunder(df["delta"], 0)
            | crossunder(df["EMA1"], df["EMA2"])
            | crossunder(df["EMA1"], df["EMA3"])
            | crossunder(df["EMA2"], df["EMA3"])
        )

        in_range = (df.index >= self.start_date) & (df.index < self.end_date)
        df["long_condition"] = long_cond & in_range
        df["short_condition"] = short_cond & in_range
        return df

    # ── position state machine (mirrors strategy.entry/exit) ───────
    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.compute_signals(df)

        long_ok = self.trade_direction in ("Long", "Both")
        short_ok = self.trade_direction in ("Short", "Both")

        positions = []
        actions = []
        pos = 0  # 1 = long, -1 = short, 0 = flat

        for long_c, short_c in zip(df["long_condition"], df["short_condition"]):
            new_pos = pos
            long_c = bool(long_c)
            short_c = bool(short_c)

            # strategy.entry() calls (direction-gated, reverse net position)
            if long_c and long_ok:
                new_pos = 1
            elif short_c and short_ok:
                new_pos = -1
            else:
                # explicit stop-exits: only relevant when the opposite
                # entry wasn't taken (e.g. Long-only mode + short_condition)
                if pos > 0 and short_c:
                    new_pos = 0
                elif pos < 0 and long_c:
                    new_pos = 0

            action = None
            if new_pos != pos:
                if pos == 0 and new_pos == 1:
                    action = "ENTER LONG"
                elif pos == 0 and new_pos == -1:
                    action = "ENTER SHORT"
                elif pos == 1 and new_pos == 0:
                    action = "EXIT LONG"
                elif pos == -1 and new_pos == 0:
                    action = "EXIT SHORT"
                elif pos == -1 and new_pos == 1:
                    action = "REVERSE SHORT->LONG"
                elif pos == 1 and new_pos == -1:
                    action = "REVERSE LONG->SHORT"

            positions.append(new_pos)
            actions.append(action)
            pos = new_pos

        df["position"] = positions
        df["action"] = actions
        return df

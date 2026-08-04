"""
Institutional-grade backtest engine built on top of strategy.py.

Adds what a signal-only alert system doesn't need but a real backtest does:
  - commission + slippage cost modeling (in basis points, applied per fill)
  - explicit trade-by-trade ledger (entry/exit price, holding period, return)
  - a full institutional metrics set (CAGR, Sharpe, Sortino, Calmar,
    Max Drawdown + duration, Ulcer Index, historical VaR/CVaR, exposure,
    profit factor, expectancy, win rate)
  - Monte Carlo bootstrap of the trade-return distribution (robustness /
    confidence interval on final equity, not just a single backtest path)
  - Walk-forward split (in-sample vs out-of-sample) as a basic overfitting
    check

This operates on the output of TemacdStrategy.run() (columns: Close,
position, action) so the trading LOGIC is guaranteed identical to the
Pine script / the daily alert job — only the accounting layer differs.
"""

import numpy as np
import pandas as pd

import metrics as m


class BacktestEngine:
    def __init__(
        self,
        df: pd.DataFrame,
        periods_per_year: float = 52,
        leverage: float = 1.0,
        commission_bps: float = 1.0,
        slippage_bps: float = 2.0,
        initial_equity: float = 100_000.0,
    ):
        self.df = df.copy()
        self.periods_per_year = periods_per_year
        self.leverage = leverage
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.initial_equity = initial_equity

    # ── cost model ───────────────────────────────────────────────
    def _apply_cost(self, price: float, side: str) -> float:
        cost = (self.commission_bps + self.slippage_bps) / 10000.0
        return price * (1 + cost) if side == "buy" else price * (1 - cost)

    # ── trade ledger ─────────────────────────────────────────────
    def extract_trades(self) -> pd.DataFrame:
        df = self.df
        trades = []
        entry = None

        for ts, row in df.iterrows():
            action = row["action"]
            if action is None or (isinstance(action, float) and pd.isna(action)):
                continue

            if "ENTER" in action or "REVERSE" in action:
                if entry is not None:
                    trades.append(self._close_trade(entry, ts, row["Close"]))
                direction = "LONG" if row["position"] == 1 else "SHORT"
                entry = {"entry_ts": ts, "entry_price": row["Close"], "direction": direction}
            elif "EXIT" in action and entry is not None:
                trades.append(self._close_trade(entry, ts, row["Close"]))
                entry = None

        if entry is not None:  # mark-to-market any still-open position
            trades.append(self._close_trade(entry, df.index[-1], df["Close"].iloc[-1], open_trade=True))

        cols = ["entry_ts", "exit_ts", "direction", "entry_price", "exit_price",
                "bars_held", "return_pct", "open_trade"]
        return pd.DataFrame(trades, columns=cols)

    def _close_trade(self, entry, exit_ts, exit_price, open_trade=False):
        direction = entry["direction"]
        entry_price = entry["entry_price"]

        if direction == "LONG":
            entry_fill = self._apply_cost(entry_price, "buy")
            exit_fill = self._apply_cost(exit_price, "sell")
            ret = exit_fill / entry_fill - 1
        else:
            entry_fill = self._apply_cost(entry_price, "sell")
            exit_fill = self._apply_cost(exit_price, "buy")
            ret = entry_fill / exit_fill - 1

        ret *= self.leverage
        bars_held = self.df.index.get_loc(exit_ts) - self.df.index.get_loc(entry["entry_ts"])

        return {
            "entry_ts": entry["entry_ts"],
            "exit_ts": exit_ts,
            "direction": direction,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "bars_held": bars_held,
            "return_pct": round(ret * 100, 4),
            "open_trade": open_trade,
        }

    # ── equity curve ─────────────────────────────────────────────
    def equity_curve(self):
        df = self.df
        held = df["position"].shift(1).fillna(0.0)
        bar_return = df["Close"].pct_change().fillna(0.0)
        # cost drag applied on bars where a position change happened
        cost_drag = np.where(df["action"].notna(), (self.commission_bps + self.slippage_bps) / 10000.0, 0.0)
        strat_return = held * bar_return * self.leverage - cost_drag
        equity = self.initial_equity * (1 + strat_return).cumprod()
        return equity, strat_return

    # ── full metrics run ─────────────────────────────────────────
    def run(self) -> dict:
        equity, returns = self.equity_curve()
        trades = self.extract_trades()
        closed = trades[~trades["open_trade"].fillna(False)] if not trades.empty else trades

        cagr_v = m.cagr(equity, self.periods_per_year)
        vol_v = m.annual_vol(returns, self.periods_per_year)
        sharpe_v = m.sharpe_ratio(returns, self.periods_per_year)
        sortino_v = m.sortino_ratio(returns, self.periods_per_year)
        mdd = m.max_drawdown(equity)
        mdd_dur = m.max_drawdown_duration(equity)
        calmar_v = m.calmar_ratio(cagr_v, mdd)
        ulcer_v = m.ulcer_index(equity)
        var95 = m.historical_var(returns)
        cvar95 = m.historical_cvar(returns)

        n_trades = len(closed)
        wins = closed[closed["return_pct"] > 0] if n_trades else closed
        losses = closed[closed["return_pct"] <= 0] if n_trades else closed
        win_rate = len(wins) / n_trades * 100 if n_trades else float("nan")
        avg_win = wins["return_pct"].mean() if len(wins) else float("nan")
        avg_loss = losses["return_pct"].mean() if len(losses) else float("nan")
        gross_profit = wins["return_pct"].sum() if len(wins) else 0.0
        gross_loss = abs(losses["return_pct"].sum()) if len(losses) else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss else float("nan")
        expectancy = closed["return_pct"].mean() if n_trades else float("nan")
        avg_bars = closed["bars_held"].mean() if n_trades else float("nan")
        exposure_pct = (self.df["position"].shift(1).fillna(0) != 0).mean() * 100

        def r(x, nd=2):
            return round(x, nd) if isinstance(x, (int, float)) and x == x else "n/a"

        metrics_dict = {
            "Start": str(self.df.index[0].date()),
            "End": str(self.df.index[-1].date()),
            "Bars": len(self.df),
            "Total Return %": r((equity.iloc[-1] / equity.iloc[0] - 1) * 100),
            "CAGR %": r(cagr_v * 100 if cagr_v == cagr_v else float("nan")),
            "Annual Vol %": r(vol_v * 100 if vol_v == vol_v else float("nan")),
            "Sharpe": r(sharpe_v),
            "Sortino": r(sortino_v),
            "Calmar": r(calmar_v),
            "Max Drawdown %": r(mdd * 100),
            "Max DD Duration (bars)": mdd_dur,
            "Ulcer Index": r(ulcer_v),
            "VaR 95% (per bar) %": r(var95 * 100 if var95 == var95 else float("nan")),
            "CVaR 95% (per bar) %": r(cvar95 * 100 if cvar95 == cvar95 else float("nan")),
            "Trades": n_trades,
            "Win Rate %": r(win_rate),
            "Profit Factor": r(profit_factor),
            "Avg Win %": r(avg_win),
            "Avg Loss %": r(avg_loss),
            "Expectancy % / trade": r(expectancy),
            "Avg Bars Held": r(avg_bars, 1),
            "Exposure %": r(exposure_pct, 1),
        }

        return {"equity": equity, "returns": returns, "trades": trades, "metrics": metrics_dict}

    # ── Monte Carlo robustness check ────────────────────────────
    def monte_carlo(self, n_sims: int = 5000, seed: int = 42):
        trades = self.extract_trades()
        closed = trades[~trades["open_trade"].fillna(False)] if not trades.empty else trades
        if closed.empty or len(closed) < 5:
            return None

        rng = np.random.default_rng(seed)
        rets = closed["return_pct"].values / 100.0
        n = len(rets)
        sims = rng.choice(rets, size=(n_sims, n), replace=True)
        final_multiples = np.prod(1 + sims, axis=1)

        return {
            "n_sims": n_sims,
            "n_trades": n,
            "p5": round(float(np.percentile(final_multiples, 5)), 3),
            "p50": round(float(np.percentile(final_multiples, 50)), 3),
            "p95": round(float(np.percentile(final_multiples, 95)), 3),
            "prob_profit_%": round(float((final_multiples > 1).mean() * 100), 1),
        }

    # ── walk-forward split ───────────────────────────────────────
    def walk_forward(self, split: float = 0.5):
        n = len(self.df)
        split_idx = int(n * split)
        if split_idx < 20 or (n - split_idx) < 20:
            return None

        in_df, out_df = self.df.iloc[:split_idx], self.df.iloc[split_idx:]
        in_engine = BacktestEngine(in_df, self.periods_per_year, self.leverage,
                                    self.commission_bps, self.slippage_bps, self.initial_equity)
        out_engine = BacktestEngine(out_df, self.periods_per_year, self.leverage,
                                     self.commission_bps, self.slippage_bps, self.initial_equity)
        return {"in_sample": in_engine.run()["metrics"], "out_of_sample": out_engine.run()["metrics"]}

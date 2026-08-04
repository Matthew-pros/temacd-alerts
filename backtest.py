"""
Optional: run locally (not part of the daily alert job) to see approximate
historical performance stats, similar to the stats table in the Pine script
(Max DD, Sharpe, Sortino, Profit Factor, Profitable %, Trades, Avg Bars).

Usage:
    python backtest.py NQ
    python backtest.py ES --leverage 1

This is a simplified equity simulation (no commissions/slippage/margin
modeling) meant to give you a directional sense of the strategy's
historical behavior — not a certified backtest. For a precise backtest,
use TradingView's Strategy Tester on the original Pine script.
"""

import argparse
import numpy as np
import pandas as pd

from config import TICKERS, STRATEGY_PARAMS, INTERVAL, LOOKBACK_PERIOD
from data_fetch import fetch_weekly
from strategy import TemacdStrategy


def simulate_equity(df: pd.DataFrame, leverage: float = 1.0) -> pd.DataFrame:
    df = df.copy()
    df["bar_return"] = df["Close"].pct_change().fillna(0.0)
    # position held DURING bar t is the position established at bar t-1
    held = df["position"].shift(1).fillna(0.0)
    df["strategy_return"] = held * df["bar_return"] * leverage
    df["equity"] = (1.0 + df["strategy_return"]).cumprod()
    return df


def compute_stats(df: pd.DataFrame, annualization: int = 52) -> dict:
    returns = df["strategy_return"]
    equity = df["equity"]

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_dd = drawdown.min() * 100

    std = returns.std()
    neg_std = returns[returns < 0].std()
    mean_r = returns.mean()

    sharpe = (mean_r / std * np.sqrt(annualization)) if std and not np.isnan(std) else float("nan")
    sortino = (mean_r / neg_std * np.sqrt(annualization)) if neg_std and not np.isnan(neg_std) else float("nan")

    # trades: count of non-null actions that open OR close a position
    trade_actions = df["action"].dropna()
    entries = trade_actions[trade_actions.str.contains("ENTER|REVERSE")]
    n_trades = len(entries)

    wins = 0
    gross_profit = 0.0
    gross_loss = 0.0
    bars_in_trade = []
    entry_idx = None
    entry_equity = None
    for i, (ts, action) in enumerate(df["action"].items()):
        has_action = isinstance(action, str)
        if has_action and ("ENTER" in action or "REVERSE" in action):
            entry_idx = i
            entry_equity = df["equity"].iloc[i]
        elif has_action and "EXIT" in action and entry_idx is not None:
            exit_equity = df["equity"].iloc[i]
            pnl = exit_equity - entry_equity
            if pnl > 0:
                wins += 1
                gross_profit += pnl
            else:
                gross_loss += abs(pnl)
            bars_in_trade.append(i - entry_idx)
            entry_idx = None

    closed_trades = len(bars_in_trade)
    win_pct = (wins / closed_trades * 100) if closed_trades else float("nan")
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("nan")
    avg_bars = np.mean(bars_in_trade) if bars_in_trade else float("nan")

    return {
        "Max DD %": round(max_dd, 2),
        "Sharpe": round(sharpe, 2),
        "Sortino": round(sortino, 2),
        "Profit Factor": round(profit_factor, 2) if profit_factor == profit_factor else "n/a",
        "Profitable %": round(win_pct, 2) if win_pct == win_pct else "n/a",
        "Closed Trades": closed_trades,
        "Avg Bars/Trade": round(avg_bars, 1) if avg_bars == avg_bars else "n/a",
        "Total Return %": round((equity.iloc[-1] - 1) * 100, 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", choices=list(TICKERS.keys()))
    parser.add_argument("--leverage", type=float, default=1.0)
    args = parser.parse_args()

    symbol = TICKERS[args.ticker]
    raw = fetch_weekly(symbol, period=LOOKBACK_PERIOD, interval=INTERVAL)
    strat = TemacdStrategy(**STRATEGY_PARAMS)
    result = strat.run(raw)
    result = simulate_equity(result, leverage=args.leverage)

    stats = compute_stats(result, annualization=52)  # 52 = weekly bars/year

    print(f"\n=== {args.ticker} ({symbol}) — Weekly TEMACD backtest (approx.) ===")
    for k, v in stats.items():
        print(f"{k:>16}: {v}")
    print()


if __name__ == "__main__":
    main()

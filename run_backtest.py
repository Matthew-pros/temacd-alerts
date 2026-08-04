"""
Fully automatic institutional backtest runner.

Run with zero arguments:

    python run_backtest.py

For every ticker in config.TICKERS this:
  1. pulls full weekly history (free, via yfinance)
  2. runs the strategy (strategy.py — identical logic to the Pine script)
  3. runs the institutional BacktestEngine (costs, metrics, Monte Carlo,
     walk-forward)
  4. writes a self-contained HTML report to reports/<TICKER>_report.html
  5. writes a combined reports/summary.csv across all tickers

Also runs automatically once a week via
.github/workflows/institutional-backtest.yml — reports get committed back
to the repo and are viewable for free through GitHub Pages, no manual step
required.
"""

import os
import pandas as pd

from config import TICKERS, STRATEGY_PARAMS
from data_fetch import fetch_weekly
from strategy import TemacdStrategy
from backtest_engine import BacktestEngine
from report import build_html_report

REPORTS_DIR = "reports"

# Institutional accounting assumptions — tune these to your broker/venue.
BACKTEST_CONFIG = dict(
    periods_per_year=52,     # weekly bars/year
    leverage=1.0,
    commission_bps=1.0,      # 0.01% per fill
    slippage_bps=2.0,        # 0.02% per fill
    initial_equity=100_000.0,
)


def run_all(period: str = "max"):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    strat = TemacdStrategy(**STRATEGY_PARAMS)
    summary_rows = []

    for label, symbol in TICKERS.items():
        print(f"=== {label} ({symbol}) ===")
        try:
            raw = fetch_weekly(symbol, period=period, interval="1wk")
        except Exception as e:  # noqa: BLE001
            print(f"  fetch failed: {e}")
            continue

        result_df = strat.run(raw)
        engine = BacktestEngine(result_df, **BACKTEST_CONFIG)
        result = engine.run()
        mc = engine.monte_carlo()
        wf = engine.walk_forward()

        out_path = os.path.join(REPORTS_DIR, f"{label}_report.html")
        build_html_report(
            label, symbol, result,
            monte_carlo=mc, walk_forward=wf,
            params={**STRATEGY_PARAMS, **BACKTEST_CONFIG},
            out_path=out_path,
        )
        print(f"  report -> {out_path}")

        row = {"Ticker": label, "Symbol": symbol}
        row.update(result["metrics"])
        summary_rows.append(row)

    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        summary_path = os.path.join(REPORTS_DIR, "summary.csv")
        summary_df.to_csv(summary_path, index=False)
        print(f"\nSummary -> {summary_path}")
        print(summary_df.to_string(index=False))
    else:
        print("No results produced.")


if __name__ == "__main__":
    run_all()

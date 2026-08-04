"""
Runs daily via GitHub Actions.

For each configured ticker:
  1. Pull free weekly OHLC data (yfinance)
  2. Run the TEMACD strategy engine (strategy.py — same logic as the Pine script)
  3. Regenerate the chart (charts/<TICKER>.png)
  4. If the most recently CLOSED weekly bar produced a new entry/exit that
     hasn't been alerted on yet, send an email
  5. Persist state.json so alerts are never duplicated across daily runs
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd

from config import TICKERS, STRATEGY_PARAMS, INTERVAL, LOOKBACK_PERIOD, STATE_FILE, CHARTS_DIR, BARS_ON_CHART
from data_fetch import fetch_weekly
from strategy import TemacdStrategy
from charting import plot_strategy
from notifier import send_email


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def get_last_closed_bar(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance's most recent weekly row is often the still-forming current
    week. Drop it if it's less than 7 days old so we only ever alert on a
    fully closed weekly bar."""
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    last_idx = df.index[-1]
    if (now - last_idx).days < 7:
        return df.iloc[:-1]
    return df


def main():
    state = load_state()
    strat = TemacdStrategy(**STRATEGY_PARAMS)
    alerts_sent = []

    for label, symbol in TICKERS.items():
        print(f"[{label}] fetching {symbol} ...")
        try:
            raw = fetch_weekly(symbol, period=LOOKBACK_PERIOD, interval=INTERVAL)
        except Exception as e:  # noqa: BLE001
            print(f"[{label}] fetch failed: {e}")
            continue

        result = strat.run(raw)
        closed = get_last_closed_bar(result)
        if closed.empty:
            print(f"[{label}] not enough closed bars yet, skipping.")
            continue

        last_row = closed.iloc[-1]
        last_ts = closed.index[-1].isoformat()

        # Always refresh the chart so the "live view" stays current
        chart_path = os.path.join(CHARTS_DIR, f"{label}.png")
        plot_strategy(result, label, chart_path, n_bars=BARS_ON_CHART)

        ticker_state = state.get(label, {})
        already_alerted = ticker_state.get("last_alert_ts") == last_ts
        action = last_row["action"]
        if isinstance(action, float) and pd.isna(action):
            action = None

        if action and not already_alerted:
            subject = f"[{label}] {action} — Weekly signal ({closed.index[-1].date()})"
            body = (
                f"Ticker: {label} ({symbol})\n"
                f"Timeframe: Weekly\n"
                f"Bar date: {closed.index[-1].date()}\n"
                f"Action: {action}\n\n"
                f"Close:  {last_row['Close']:.2f}\n"
                f"EMA5:   {last_row['EMA1']:.2f}\n"
                f"EMA50:  {last_row['EMA2']:.2f}\n"
                f"EMA222: {last_row['EMA3']:.2f}\n"
                f"MACD:   {last_row['MACD']:.4f}\n"
                f"Signal: {last_row['aMACD']:.4f}\n"
            )
            try:
                send_email(subject, body, attachments=[chart_path])
                alerts_sent.append(subject)
                print(f"[{label}] alert sent: {action}")
            except Exception as e:  # noqa: BLE001
                print(f"[{label}] email failed: {e}")
        else:
            print(f"[{label}] no new signal (last action: {action}).")

        state[label] = {
            "last_bar_ts": last_ts,
            "last_action": action,
            "position": int(last_row["position"]),
            "last_alert_ts": last_ts if (action and not already_alerted) else ticker_state.get("last_alert_ts"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    save_state(state)

    if alerts_sent:
        print("\nAlerts sent this run:")
        for a in alerts_sent:
            print(" -", a)
    else:
        print("\nNo new signals this run.")


if __name__ == "__main__":
    main()

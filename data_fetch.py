"""Free weekly OHLC data via yfinance."""

import time
import pandas as pd
import yfinance as yf


def fetch_weekly(symbol: str, period: str = "20y", interval: str = "1wk", retries: int = 3) -> pd.DataFrame:
    last_err = None
    for attempt in range(retries):
        try:
            df = yf.download(
                symbol,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
            )
            if df is None or df.empty:
                raise ValueError(f"No data returned for {symbol}")

            # yfinance can return MultiIndex columns for single tickers
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.dropna(subset=["Close"])
            df.index = pd.to_datetime(df.index).tz_localize(None)
            return df
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {symbol} after {retries} attempts: {last_err}")

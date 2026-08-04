# ═══════════════════════════════════════════════
# CONFIG — edit this file to change tickers / params
# ═══════════════════════════════════════════════

# Friendly label -> Yahoo Finance ticker (free, via yfinance)
# NQ  = Nasdaq-100 E-mini futures (continuous front month)
# ES  = S&P 500 E-mini futures
# GC  = Gold futures
# SIL = Silver futures (Yahoo symbol is SI=F)
TICKERS = {
    "NQ": "NQ=F",
    "ES": "ES=F",
    "GC": "GC=F",
    "SIL": "SI=F",
}

# Same defaults as the Pine Script inputs
STRATEGY_PARAMS = dict(
    len1=5,
    len2=50,
    len3=222,
    fast=61,
    slow=70,
    macd_len=15,
    trade_direction="Long",   # "Long", "Short", or "Both" — same as Pine input
    start_date="2018-01-01",
    end_date="2170-12-31",
)

INTERVAL = "1wk"        # Weekly timeframe, as requested
LOOKBACK_PERIOD = "20y"  # How much history to pull each run (yfinance max is ~ok for weekly)

STATE_FILE = "state.json"
CHARTS_DIR = "charts"
BARS_ON_CHART = 156     # ~3 years of weekly bars shown on the chart

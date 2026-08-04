# TEMACD Weekly Strategy — Free Alerts + Institutional Backtesting

Python re-implementation of the Pine Script v5 strategy **"TQQQ TEMACD"**
(same EMA/MACD-crossover entry/exit logic), running 100% free:

- **Daily alert job** (`main.py`) — checks NQ / ES / GC / SIL on the weekly
  timeframe, e-mails you the moment a new bar produces an entry/exit signal.
- **Institutional backtest** (`run_backtest.py`) — fully automatic, no
  arguments: commission/slippage cost model, Sharpe/Sortino/Calmar,
  Max Drawdown, Ulcer Index, historical VaR/CVaR, Monte Carlo bootstrap,
  walk-forward (in-sample vs out-of-sample) — self-contained HTML report
  per ticker.
- **Free charts** published via GitHub Pages, auto-refreshed.

Everything runs on GitHub Actions' free tier. No TradingView Premium, no
paid data, no server to maintain.

## Files

| File                                          | Purpose                                                      |
|------------------------------------------------|---------------------------------------------------------------|
| `config.py`                                    | Tickers + strategy/backtest parameters                       |
| `strategy.py`                                  | Core indicator + position engine (mirrors the Pine script)   |
| `data_fetch.py`                                | Free weekly OHLC data via `yfinance`                          |
| `charting.py`                                  | Matplotlib chart generation for the alert system              |
| `notifier.py`                                  | Free SMTP e-mail alerts                                       |
| `main.py`                                      | Daily alert job (entry point for the daily workflow)         |
| `metrics.py`                                   | Institutional risk/performance metric functions               |
| `backtest_engine.py`                           | Costs, trade ledger, Monte Carlo, walk-forward                 |
| `report.py`                                    | Self-contained HTML report generator                          |
| `run_backtest.py`                              | Fully automatic backtest runner (entry point for weekly job) |
| `backtest.py`                                  | Lightweight ad-hoc CLI backtest (optional, quick sanity check) |
| `.github/workflows/weekly-alerts.yml`          | Daily cron → e-mail alerts                                    |
| `.github/workflows/institutional-backtest.yml` | Weekly cron → institutional reports                          |
| `index.html`                                   | Landing page for GitHub Pages                                 |

## 1. Create the repo

1. Create a new **private or public** GitHub repository (public is fine —
   nothing here is a secret except your email credentials, which never go
   into the code).
2. Upload all the files from this project keeping the folder structure
   (including the `.github/workflows/` folder).

## 2. Set up free e-mail alerts (Gmail example)

1. Go to your Google Account → Security → **App Passwords** (requires
   2-Step Verification enabled) and create a 16-character app password.
2. In your GitHub repo: **Settings → Secrets and variables → Actions →
   New repository secret**, add:

   | Secret name   | Value                              |
   |---------------|-------------------------------------|
   | `SMTP_SERVER` | `smtp.gmail.com`                    |
   | `SMTP_PORT`   | `465`                               |
   | `SMTP_USER`   | your Gmail address                  |
   | `SMTP_PASS`   | the 16-character app password       |
   | `EMAIL_TO`    | where you want alerts sent          |

   Any SMTP provider works the same way (Outlook, Fastmail, your own
   domain, etc.) — just change `SMTP_SERVER`/`SMTP_PORT`.

## 3. Enable the workflows

Both workflows are already scheduled:

- `weekly-alerts.yml` runs Mon–Fri at 21:30 UTC (checks for a newly closed
  weekly bar and e-mails you only when one actually produced a signal).
- `institutional-backtest.yml` runs every Sunday at 06:00 UTC and rebuilds
  full backtest reports for all tickers.

Go to the **Actions** tab of your repo once, and click **"I understand my
workflows, enable them"** if GitHub prompts you (new repos sometimes need
this). You can also trigger either one manually any time via **Run
workflow**.

## 4. Enable free chart hosting (GitHub Pages)

**Settings → Pages → Source: Deploy from a branch → Branch: `main` /
`(root)` → Save.**

After the first workflow run, your dashboard will be live at:
`https://<your-username>.github.io/<repo-name>/`

— live charts + links to the institutional backtest reports for each
ticker.

## 5. Customize

Edit `config.py`:

- `TICKERS` — add/remove symbols (any Yahoo Finance futures/ETF ticker
  works, e.g. `"CL=F"` for crude oil, `"BTC-USD"` for Bitcoin).
- `STRATEGY_PARAMS` — same fields as the Pine script inputs
  (`len1/len2/len3`, `fast/slow/macd_len`, `trade_direction`,
  `start_date/end_date`).
- `BACKTEST_CONFIG` (in `run_backtest.py`) — `commission_bps`,
  `slippage_bps`, `leverage`, `initial_equity`.

## 6. Run locally (optional)

```bash
pip install -r requirements.txt

# Test the alert logic once without waiting for the scheduled job:
SMTP_SERVER=smtp.gmail.com SMTP_PORT=465 SMTP_USER=you@gmail.com \
SMTP_PASS=xxxxxxxxxxxxxxxx EMAIL_TO=you@gmail.com python main.py

# Full institutional backtest report for all tickers:
python run_backtest.py

# Quick single-ticker stats in the terminal:
python backtest.py NQ
```

## Important caveats

- **Data source**: free Yahoo Finance continuous futures (`NQ=F`, `ES=F`,
  `GC=F`, `SI=F`) are close to, but not identical to, TradingView's
  continuous contracts (roll methodology can differ slightly). Expect
  minor timing differences around contract rolls.
- **Weekly bar alignment**: Yahoo's weekly bars anchor Monday–Friday,
  which should match TradingView's weekly bars for these markets, but
  isn't guaranteed byte-for-byte identical.
- **Backtest realism**: the cost model (commission + slippage in bps) and
  fill-at-close assumption are simplifications — not a certified
  execution simulator. Good for comparing parameter choices and getting a
  realistic *order of magnitude* on performance, not for a final
  investment decision.
- This is a research/education tool, **not financial advice**.

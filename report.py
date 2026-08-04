"""Self-contained HTML report generator (charts embedded as base64 PNG — no
external files, opens anywhere, easy to email or publish via GitHub Pages)."""

import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import metrics as m


def _fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _equity_drawdown_chart(equity: pd.Series) -> str:
    dd = m.drawdown_series(equity) * 100
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), sharex=True,
                                    gridspec_kw={"height_ratios": [2, 1]})
    ax1.plot(equity.index, equity.values, color="#1f77ff")
    ax1.set_title("Equity Curve")
    ax1.grid(alpha=0.3)
    ax2.fill_between(dd.index, dd.values, 0, color="red", alpha=0.4)
    ax2.set_title("Drawdown %")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    return _fig_to_base64(fig)


def _trade_histogram(trades: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(8, 4))
    if not trades.empty:
        ax.hist(trades["return_pct"], bins=30, color="#1f77ff", alpha=0.75)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_title("Trade Return Distribution (%)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return _fig_to_base64(fig)


def _monthly_heatmap(returns: pd.Series):
    r = returns.copy()
    r.index = pd.to_datetime(r.index)
    monthly = (1 + r).resample("ME").prod() - 1
    table = monthly.to_frame("ret")
    table["year"] = table.index.year
    table["month"] = table.index.month
    pivot = table.pivot(index="year", columns="month", values="ret") * 100
    if pivot.empty:
        return None

    fig, ax = plt.subplots(figsize=(10, max(2, 0.4 * len(pivot))))
    im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto", vmin=-10, vmax=10)
    ax.set_xticks(range(pivot.shape[1]))
    month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    ax.set_xticklabels([month_names[c - 1] for c in pivot.columns])
    ax.set_yticks(range(pivot.shape[0]))
    ax.set_yticklabels(pivot.index)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.values[i, j]
            if pd.notna(val):
                ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=7)
    ax.set_title("Monthly Returns %")
    fig.colorbar(im, ax=ax, shrink=0.6)
    fig.tight_layout()
    return _fig_to_base64(fig)


def build_html_report(ticker_label, symbol, result, monte_carlo=None, walk_forward=None,
                       params=None, out_path="report.html"):
    equity, returns, trades = result["equity"], result["returns"], result["trades"]
    metrics_dict = result["metrics"]

    equity_img = _equity_drawdown_chart(equity)
    hist_img = _trade_histogram(trades)
    heat_img = _monthly_heatmap(returns)

    metrics_html = pd.DataFrame(list(metrics_dict.items()), columns=["Metric", "Value"]).to_html(index=False, border=0)

    trades_html = "<p>No closed trades in this period.</p>"
    if not trades.empty:
        show = trades.copy()
        show["entry_ts"] = show["entry_ts"].astype(str)
        show["exit_ts"] = show["exit_ts"].astype(str)
        trades_html = show.tail(300).to_html(index=False, border=0)

    mc_html = ""
    if monte_carlo:
        mc_html = ("<h2>Monte Carlo Robustness Check</h2>"
                   f"<p>Bootstrapped {monte_carlo['n_sims']} simulations by resampling the "
                   f"{monte_carlo['n_trades']} historical trade returns with replacement, to see "
                   "how sensitive the result is to trade sequencing/luck.</p>"
                   + pd.DataFrame([monte_carlo]).to_html(index=False, border=0))

    wf_html = ""
    if walk_forward:
        wf_html = ("<h2>Walk-Forward Check (In-Sample vs Out-of-Sample)</h2>"
                   "<p>First half of history vs second half, same fixed parameters — a large "
                   "gap between the two suggests the parameters may be overfit to one regime.</p>"
                   + pd.DataFrame({"In-Sample": walk_forward["in_sample"],
                                    "Out-of-Sample": walk_forward["out_of_sample"]}).to_html(border=0))

    params_html = ""
    if params:
        params_html = "<h2>Parameters</h2>" + pd.DataFrame(list(params.items()), columns=["Param", "Value"]).to_html(index=False, border=0)

    heat_block = f"<div class='section'><h2>Monthly Returns</h2><img src='data:image/png;base64,{heat_img}'></div>" if heat_img else ""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{ticker_label} Backtest Report</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; background:#0d1117; color:#e6edf3; margin:0; padding:30px; }}
  h1 {{ color:#58a6ff; }}
  h2 {{ color:#58a6ff; margin-top: 0; }}
  table {{ border-collapse: collapse; margin-bottom: 16px; width: 100%; }}
  td, th {{ border: 1px solid #30363d; padding: 6px 10px; text-align: left; font-size: 13px; }}
  th {{ background:#161b22; }}
  img {{ max-width: 100%; border: 1px solid #30363d; border-radius: 4px; }}
  .section {{ margin-bottom: 36px; }}
  .disclaimer {{ color:#8b949e; font-size: 12px; }}
</style></head><body>
<h1>{ticker_label} ({symbol}) — Institutional Backtest Report</h1>
<p class="disclaimer">Auto-generated. Weekly timeframe. Simplified fill/cost model — for research purposes only, not investment advice.</p>

<div class="section"><h2>Performance Metrics</h2>{metrics_html}</div>
<div class="section">{params_html}</div>
<div class="section"><h2>Equity Curve &amp; Drawdown</h2><img src="data:image/png;base64,{equity_img}"></div>
<div class="section"><h2>Trade Return Distribution</h2><img src="data:image/png;base64,{hist_img}"></div>
{heat_block}
<div class="section">{mc_html}</div>
<div class="section">{wf_html}</div>
<div class="section"><h2>Trade Log (last 300)</h2>{trades_html}</div>
</body></html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path

"""Interactive Streamlit dashboard for TEMACD signals and backtests.

Run from the repository root with: streamlit run streamlit_app.py
The existing strategy/data/backtest modules remain the single source of truth;
this file provides the UI and orchestrates their execution.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from backtest_engine import BacktestEngine
from config import TICKERS, STRATEGY_PARAMS, INTERVAL, LOOKBACK_PERIOD, STATE_FILE
from data_fetch import fetch_weekly
from notifier import send_email
from report import build_html_report
from strategy import TemacdStrategy

st.set_page_config(page_title="TEMACD Alerts & Backtest", page_icon="📈", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def load_market_data(symbol: str, period: str) -> pd.DataFrame:
    """Cache Yahoo data for one hour to avoid repeated downloads on reruns."""
    return fetch_weekly(symbol, period=period, interval=INTERVAL)


def read_alert_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as state_file:
            return json.load(state_file)
    except (OSError, json.JSONDecodeError):
        return {}


def send_email_with_credentials(credentials: dict, subject: str, body: str, attachments=None):
    """Use the existing SMTP notifier without retaining form secrets in env."""
    previous = {key: os.environ.get(key) for key in credentials}
    try:
        os.environ.update(credentials)
        send_email(subject, body, attachments=attachments)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def latest_closed_row(result_df: pd.DataFrame):
    """Return the latest fully closed weekly bar and its timestamp."""
    if result_df.empty:
        return None, None
    closed = result_df
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    if (now - pd.Timestamp(result_df.index[-1])).days < 7:
        closed = result_df.iloc[:-1]
    if closed.empty:
        return None, None
    return closed.iloc[-1], closed.index[-1]


def make_strategy_chart(df: pd.DataFrame, label: str, n_bars: int = 156):
    plot_df = df.tail(n_bars)
    fig, (price_ax, macd_ax) = plt.subplots(
        2, 1, figsize=(13, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    price_ax.plot(plot_df.index, plot_df["Close"], color="#dce6f1", label="Close", linewidth=1.3)
    for col, name, color in [
        ("EMA1", "EMA 1", "#35a7ff"),
        ("EMA2", "EMA 2", "#f5a623"),
        ("EMA3", "EMA 3", "#b58cff"),
    ]:
        price_ax.plot(plot_df.index, plot_df[col], label=name, color=color, linewidth=1)
    entries = plot_df[plot_df["action"].fillna("").str.contains("ENTER|REVERSE")]
    exits = plot_df[plot_df["action"].fillna("").str.contains("EXIT")]
    long_entries = entries[entries["position"] == 1]
    short_entries = entries[entries["position"] == -1]
    price_ax.scatter(long_entries.index, long_entries["Close"], marker="^", color="#20c997", s=70, label="Long")
    price_ax.scatter(short_entries.index, short_entries["Close"], marker="v", color="#ff6b6b", s=70, label="Short")
    price_ax.scatter(exits.index, exits["Close"], marker="x", color="white", s=55, label="Exit")
    price_ax.set_title(f"{label} — týdenní TEMACD")
    price_ax.legend(loc="upper left", ncol=3, fontsize=8)
    price_ax.grid(alpha=0.2)
    macd_ax.plot(plot_df.index, plot_df["MACD"], label="MACD", color="#35a7ff")
    macd_ax.plot(plot_df.index, plot_df["aMACD"], label="Signal", color="#f5a623")
    macd_ax.bar(plot_df.index, plot_df["delta"], color=["#20c997" if x >= 0 else "#ff6b6b" for x in plot_df["delta"]], alpha=0.4)
    macd_ax.axhline(0, color="gray", linewidth=0.8)
    macd_ax.legend(loc="upper left", fontsize=8)
    macd_ax.grid(alpha=0.2)
    fig.tight_layout()
    return fig


def build_results(labels, period, strategy_params, backtest_params):
    strategy = TemacdStrategy(**strategy_params)
    results = {}
    errors = {}
    for label in labels:
        symbol = TICKERS[label]
        try:
            raw = load_market_data(symbol, period)
            if raw.empty:
                raise ValueError("Zdroj nevrátil žádná data.")
            strategy_df = strategy.run(raw)
            engine = BacktestEngine(strategy_df, **backtest_params)
            results[label] = {
                "symbol": symbol,
                "data": strategy_df,
                "backtest": engine.run(),
                "monte_carlo": engine.monte_carlo(n_sims=2000),
                "walk_forward": engine.walk_forward(),
            }
        except Exception as exc:  # show per-symbol errors without stopping all tickers
            errors[label] = str(exc)
    return results, errors


st.title("📈 TEMACD — signály a backtest")
st.caption("Streamlit rozhraní pro existující strategii, Yahoo Finance data a backtest engine. Data jsou týdenní; výsledky jsou pouze výzkumné, nikoli investiční doporučení.")

with st.sidebar:
    st.header("Nastavení výpočtu")
    selected = st.multiselect("Instrumenty", options=list(TICKERS), default=list(TICKERS))
    period = st.selectbox("Historie", ["5y", "10y", "20y", "max"], index=2)
    st.subheader("Strategie")
    with st.expander("Parametry strategie", expanded=False):
        len1 = st.number_input("EMA 1", min_value=1, max_value=500, value=int(STRATEGY_PARAMS["len1"]))
        len2 = st.number_input("EMA 2", min_value=1, max_value=500, value=int(STRATEGY_PARAMS["len2"]))
        len3 = st.number_input("EMA 3", min_value=1, max_value=1000, value=int(STRATEGY_PARAMS["len3"]))
        fast = st.number_input("MACD fast", min_value=1, max_value=500, value=int(STRATEGY_PARAMS["fast"]))
        slow = st.number_input("MACD slow", min_value=1, max_value=500, value=int(STRATEGY_PARAMS["slow"]))
        macd_len = st.number_input("MACD signal", min_value=1, max_value=500, value=int(STRATEGY_PARAMS["macd_len"]))
        direction = st.selectbox("Směr obchodování", ["Long", "Short", "Both"], index=["Long", "Short", "Both"].index(STRATEGY_PARAMS["trade_direction"]))
        start_date = st.date_input("Začátek strategie", value=pd.Timestamp(STRATEGY_PARAMS["start_date"]).date())
        end_date = st.date_input("Konec strategie", value=pd.Timestamp(STRATEGY_PARAMS["end_date"]).date())
    strategy_params = {
        "len1": int(len1), "len2": int(len2), "len3": int(len3),
        "fast": int(fast), "slow": int(slow), "macd_len": int(macd_len),
        "trade_direction": direction, "start_date": str(start_date), "end_date": str(end_date),
    }
    st.subheader("Backtest")
    with st.expander("Náklady a kapitál", expanded=False):
        leverage = st.number_input("Páka", min_value=0.1, max_value=20.0, value=1.0, step=0.1)
        commission = st.number_input("Komise (bps za fill)", min_value=0.0, max_value=100.0, value=1.0, step=0.5)
        slippage = st.number_input("Slippage (bps za fill)", min_value=0.0, max_value=100.0, value=2.0, step=0.5)
        initial_equity = st.number_input("Počáteční kapitál", min_value=1.0, value=100000.0, step=10000.0)
    backtest_params = {
        "periods_per_year": 52,
        "leverage": float(leverage),
        "commission_bps": float(commission),
        "slippage_bps": float(slippage),
        "initial_equity": float(initial_equity),
    }
    run_clicked = st.button("Načíst data a spustit výpočty", type="primary", use_container_width=True)
    if st.button("Vymazat cache dat", use_container_width=True):
        load_market_data.clear()
        st.success("Cache vymazána. Nová data se stáhnou při příštím výpočtu.")

if run_clicked:
    if not selected:
        st.warning("Vyber alespoň jeden instrument.")
    else:
        with st.spinner("Stahuji týdenní data a počítám signály, metriky a backtest…"):
            result_set, error_set = build_results(selected, period, strategy_params, backtest_params)
        st.session_state["results"] = result_set
        st.session_state["errors"] = error_set
        st.session_state["calculated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

results = st.session_state.get("results", {})
errors = st.session_state.get("errors", {})
if results:
    st.caption(f"Poslední výpočet: {st.session_state.get('calculated_at', '—')} · {period} · týdenní timeframe")
    if errors:
        for label, message in errors.items():
            st.warning(f"{label}: výpočet se nepodařil — {message}")

    summary_rows = []
    for label, item in results.items():
        row = {"Instrument": label, "Ticker": item["symbol"]}
        row.update(item["backtest"]["metrics"])
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows).set_index("Instrument")
    st.subheader("Přehled backtestu")
    st.dataframe(summary, use_container_width=True)

    tabs = st.tabs(list(results))
    for tab, (label, item) in zip(tabs, results.items()):
        with tab:
            df = item["data"]
            row, timestamp = latest_closed_row(df)
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Poslední uzavřená cena", f"{row['Close']:,.2f}" if row is not None else "—")
            col2.metric("Pozice", {1: "LONG", 0: "FLAT", -1: "SHORT"}.get(int(row["position"]), "—") if row is not None else "—")
            action = row["action"] if row is not None and pd.notna(row["action"]) else "Bez nového signálu"
            col3.metric("Poslední akce", action)
            col4.metric("Datum baru", str(timestamp.date()) if timestamp is not None else "—")

            st.pyplot(make_strategy_chart(df, label), use_container_width=True)
            left, right = st.columns([1, 1])
            with left:
                st.markdown("**Křivka kapitálu**")
                st.line_chart(item["backtest"]["equity"].rename("Equity"), use_container_width=True)
            with right:
                st.markdown("**Drawdown (%)**")
                equity = item["backtest"]["equity"]
                drawdown = (equity / equity.cummax() - 1) * 100
                st.area_chart(drawdown.rename("Drawdown %"), use_container_width=True)

            st.markdown("**Metriky**")
            metrics = item["backtest"]["metrics"]
            metric_cols = st.columns(4)
            for i, (name, value) in enumerate(metrics.items()):
                metric_cols[i % 4].metric(name, str(value))
            mc = item["monte_carlo"]
            if mc:
                st.markdown("**Monte Carlo (bootstrap obchodů)**")
                st.dataframe(pd.DataFrame([mc]), use_container_width=True, hide_index=True)
            wf = item["walk_forward"]
            if wf:
                st.markdown("**Walk-forward: první vs. druhá polovina historie**")
                st.dataframe(pd.DataFrame({"In-sample": wf["in_sample"], "Out-of-sample": wf["out_of_sample"]}), use_container_width=True)

            trades = item["backtest"]["trades"]
            st.markdown("**Obchody**")
            st.dataframe(trades.tail(300), use_container_width=True, hide_index=True)
            if trades.empty:
                st.info("V tomto období nebyly zaznamenány žádné obchody.")

            with st.expander("Export reportu a alerty"):
                report_bytes = None
                try:
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        report_path = os.path.join(tmp_dir, f"{label}_report.html")
                        build_html_report(
                            label, item["symbol"], item["backtest"],
                            monte_carlo=mc, walk_forward=wf,
                            params={**strategy_params, **backtest_params}, out_path=report_path,
                        )
                        with open(report_path, "rb") as report_file:
                            report_bytes = report_file.read()
                except Exception as exc:
                    st.warning(f"Report se nepodařilo vytvořit: {exc}")
                if report_bytes:
                    st.download_button("Stáhnout HTML report", report_bytes, file_name=f"{label}_report.html", mime="text/html", key=f"report-{label}")

                if row is not None and pd.notna(row["action"]):
                    st.write(f"Signál na posledním uzavřeném týdnu: **{row['action']}** ({timestamp.date()}).")
                    st.caption("E-mail se odesílá pouze po ručním potvrzení. Přihlašovací údaje se neukládají do souboru.")
                    with st.form(f"email-form-{label}"):
                        smtp_server = st.text_input("SMTP server", value=os.getenv("SMTP_SERVER", "smtp.gmail.com"), key=f"smtp-server-{label}")
                        smtp_port = st.number_input("SMTP port", min_value=1, max_value=65535, value=int(os.getenv("SMTP_PORT", "465")), key=f"smtp-port-{label}")
                        smtp_user = st.text_input("Odesílatel / SMTP uživatel", value=os.getenv("SMTP_USER", ""), key=f"smtp-user-{label}")
                        smtp_pass = st.text_input("SMTP heslo / app password", type="password", key=f"smtp-pass-{label}")
                        email_to = st.text_input("Příjemce", value=os.getenv("EMAIL_TO", ""), key=f"email-to-{label}")
                        submitted = st.form_submit_button("Odeslat alert e-mailem")
                    if submitted:
                        state = read_alert_state()
                        previous = state.get(label, {}).get("last_alert_ts")
                        current_ts = timestamp.isoformat()
                        if previous == current_ts:
                            st.info("Tento signál už byl podle state.json odeslán.")
                        elif not all([smtp_server, smtp_user, smtp_pass, email_to]):
                            st.error("Vyplň všechna SMTP pole.")
                        else:
                            try:
                                smtp_values = {"SMTP_SERVER": smtp_server, "SMTP_PORT": str(smtp_port), "SMTP_USER": smtp_user, "SMTP_PASS": smtp_pass, "EMAIL_TO": email_to}
                                body = (
                                    f"Ticker: {label} ({item['symbol']})\nTimeframe: Weekly\n"
                                    f"Bar date: {timestamp.date()}\nAction: {row['action']}\n\n"
                                    f"Close: {row['Close']:.2f}\nEMA1: {row['EMA1']:.2f}\n"
                                    f"EMA2: {row['EMA2']:.2f}\nEMA3: {row['EMA3']:.2f}\n"
                                    f"MACD: {row['MACD']:.4f}\nSignal: {row['aMACD']:.4f}\n"
                                )
                                with tempfile.TemporaryDirectory() as tmp_dir:
                                    chart_path = os.path.join(tmp_dir, f"{label}.png")
                                    fig = make_strategy_chart(df, label)
                                    fig.savefig(chart_path, dpi=110, bbox_inches="tight")
                                    plt.close(fig)
                                    send_email_with_credentials(
                                        smtp_values,
                                        f"[{label}] {row['action']} — Weekly signal ({timestamp.date()})",
                                        body,
                                        attachments=[chart_path],
                                    )
                                state[label] = {**state.get(label, {}), "last_alert_ts": current_ts, "updated_at": datetime.now(timezone.utc).isoformat()}
                                with open(STATE_FILE, "w", encoding="utf-8") as state_file:
                                    json.dump(state, state_file, indent=2, default=str)
                                st.success("Alert byl odeslán a zaznamenán do state.json.")
                            except Exception as exc:
                                st.error(f"E-mail se nepodařilo odeslat: {exc}")
                else:
                    st.info("Pro poslední uzavřený týden není nový signál k odeslání.")
else:
    st.info("Vyber instrumenty v levém panelu a klikni na **Načíst data a spustit výpočty**. Při prvním spuštění se data stáhnou z Yahoo Finance.")

st.divider()
st.caption("Výpočty vycházejí z historických dat Yahoo Finance a zjednodušeného modelu nákladů/plnění. Backtest nezaručuje budoucí výnosy a není investičním doporučením.")

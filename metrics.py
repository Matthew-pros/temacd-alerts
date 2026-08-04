"""
Institutional-grade performance/risk metrics.
Pure functions operating on equity curves / return series — no side effects,
so they're easy to unit test and reuse across the alerting and backtesting
tools.
"""

import numpy as np
import pandas as pd

TRADING_PERIODS = {"1d": 252, "1wk": 52, "1mo": 12}


def drawdown_series(equity: pd.Series) -> pd.Series:
    running_max = equity.cummax()
    return equity / running_max - 1.0


def max_drawdown(equity: pd.Series) -> float:
    return float(drawdown_series(equity).min())


def max_drawdown_duration(equity: pd.Series) -> int:
    dd = drawdown_series(equity)
    in_dd = dd < 0
    max_len = cur_len = 0
    for v in in_dd:
        if v:
            cur_len += 1
            max_len = max(max_len, cur_len)
        else:
            cur_len = 0
    return max_len


def cagr(equity: pd.Series, periods_per_year: float) -> float:
    n = len(equity)
    if n < 2:
        return float("nan")
    total_return = equity.iloc[-1] / equity.iloc[0]
    years = n / periods_per_year
    if years <= 0 or total_return <= 0:
        return float("nan")
    return total_return ** (1 / years) - 1


def annual_vol(returns: pd.Series, periods_per_year: float) -> float:
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(returns: pd.Series, periods_per_year: float, risk_free: float = 0.0) -> float:
    excess = returns - risk_free / periods_per_year
    std = excess.std(ddof=1)
    if not std or np.isnan(std):
        return float("nan")
    return float(excess.mean() / std * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, periods_per_year: float, risk_free: float = 0.0) -> float:
    excess = returns - risk_free / periods_per_year
    downside = excess[excess < 0]
    dd_std = downside.std(ddof=1)
    if not dd_std or np.isnan(dd_std):
        return float("nan")
    return float(excess.mean() / dd_std * np.sqrt(periods_per_year))


def calmar_ratio(cagr_value: float, mdd: float) -> float:
    if not mdd or np.isnan(mdd):
        return float("nan")
    return float(cagr_value / abs(mdd))


def ulcer_index(equity: pd.Series) -> float:
    dd = drawdown_series(equity) * 100
    return float(np.sqrt((dd ** 2).mean()))


def historical_var(returns: pd.Series, conf: float = 0.95) -> float:
    r = returns.dropna()
    if r.empty:
        return float("nan")
    return float(-np.percentile(r, (1 - conf) * 100))


def historical_cvar(returns: pd.Series, conf: float = 0.95) -> float:
    var = historical_var(returns, conf)
    if np.isnan(var):
        return var
    tail = returns[returns <= -var]
    if tail.empty:
        return var
    return float(-tail.mean())

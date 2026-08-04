"""Free chart generation (matplotlib -> PNG), published via GitHub Pages."""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_strategy(df, ticker_label: str, out_path: str, n_bars: int = 156):
    plot_df = df.tail(n_bars)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(14, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    ax1.plot(plot_df.index, plot_df["Close"], color="black", linewidth=1.1, label="Close")
    ax1.plot(plot_df.index, plot_df["EMA1"], color="#1f77ff", linewidth=1.2, label="EMA 5")
    ax1.plot(plot_df.index, plot_df["EMA2"], color="#888888", linewidth=1.2, label="EMA 50")
    ax1.plot(plot_df.index, plot_df["EMA3"], color="#ff8c00", linewidth=1.2, label="EMA 222")

    longs = plot_df[plot_df["action"].isin(["ENTER LONG", "REVERSE SHORT->LONG"])]
    shorts = plot_df[plot_df["action"].isin(["ENTER SHORT", "REVERSE LONG->SHORT"])]
    exits = plot_df[plot_df["action"].isin(["EXIT LONG", "EXIT SHORT"])]

    ax1.scatter(longs.index, longs["Close"], marker="^", color="green", s=110, zorder=5, label="Long entry")
    ax1.scatter(shorts.index, shorts["Close"], marker="v", color="red", s=110, zorder=5, label="Short entry")
    ax1.scatter(exits.index, exits["Close"], marker="x", color="black", s=90, zorder=5, label="Exit")

    ax1.set_title(f"{ticker_label} — Weekly TEMACD Strategy (auto-updated)")
    ax1.legend(loc="upper left", fontsize=8, ncol=3)
    ax1.grid(alpha=0.3)

    ax2.plot(plot_df.index, plot_df["MACD"], color="#1f77ff", linewidth=1, label="MACD")
    ax2.plot(plot_df.index, plot_df["aMACD"], color="#ff8c00", linewidth=1, label="Signal")
    colors = ["green" if v >= 0 else "red" for v in plot_df["delta"]]
    ax2.bar(plot_df.index, plot_df["delta"], color=colors, alpha=0.5, width=4)
    ax2.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)

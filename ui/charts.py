"""
Plotly chart builders for the stock screener dashboard.
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from typing import Optional


CHART_THEME = "plotly_dark"
GREEN = "#26a69a"
RED = "#ef5350"
BLUE = "#2196F3"
ORANGE = "#FF9800"


def candlestick_chart(
    df: pd.DataFrame,
    ticker: str,
    show_volume: bool = True,
    show_sma: bool = True,
    show_bb: bool = False,
    signal_lines: dict = None,
) -> go.Figure:
    """
    Interactive candlestick chart with optional overlays.
    signal_lines: {"entry": price, "stop_loss": price, "target_1": price, "target_2": price}
    """
    rows = 2 if show_volume else 1
    row_heights = [0.7, 0.3] if show_volume else [1.0]
    specs = [[{"secondary_y": False}]] * rows

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
    )

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"],
            name=ticker,
            increasing_line_color=GREEN,
            decreasing_line_color=RED,
        ),
        row=1, col=1,
    )

    # Moving averages
    if show_sma:
        for col, color, name in [
            ("SMA_20", "#FF9800", "SMA 20"),
            ("SMA_50", "#2196F3", "SMA 50"),
            ("SMA_200", "#9C27B0", "SMA 200"),
        ]:
            if col in df.columns:
                fig.add_trace(
                    go.Scatter(x=df.index, y=df[col], name=name, line=dict(color=color, width=1)),
                    row=1, col=1,
                )

    # Bollinger Bands
    if show_bb and "BB_upper" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_upper"], name="BB Upper",
                                  line=dict(color="gray", width=1, dash="dash")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_lower"], name="BB Lower",
                                  line=dict(color="gray", width=1, dash="dash"),
                                  fill="tonexty", fillcolor="rgba(128,128,128,0.1)"), row=1, col=1)

    # Signal lines (entry, SL, targets)
    if signal_lines:
        line_styles = {
            "entry": ("blue", "Entry"),
            "stop_loss": ("red", "Stop Loss"),
            "target_1": ("green", "Target 1"),
            "target_2": ("lime", "Target 2"),
        }
        for key, (color, label) in line_styles.items():
            price = signal_lines.get(key)
            if price:
                fig.add_hline(y=price, line_dash="dash", line_color=color,
                               annotation_text=f"{label}: {price:.2f}",
                               annotation_position="right", row=1, col=1)

    # Volume
    if show_volume and "Volume" in df.columns:
        colors = [GREEN if c >= o else RED for c, o in zip(df["Close"], df["Open"])]
        fig.add_trace(
            go.Bar(x=df.index, y=df["Volume"], name="Volume",
                   marker_color=colors, opacity=0.7),
            row=2, col=1,
        )
        if "Volume_SMA_20" in df.columns:
            fig.add_trace(
                go.Scatter(x=df.index, y=df["Volume_SMA_20"], name="Vol SMA 20",
                           line=dict(color=ORANGE, width=1)),
                row=2, col=1,
            )

    fig.update_layout(
        template=CHART_THEME,
        title=ticker,
        xaxis_rangeslider_visible=False,
        height=500,
        margin=dict(l=40, r=40, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        showlegend=True,
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    return fig


def rsi_macd_chart(df: pd.DataFrame) -> go.Figure:
    """RSI and MACD subplot chart."""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.05, row_heights=[0.5, 0.5],
        subplot_titles=("RSI (14)", "MACD"),
    )

    if "RSI_14" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["RSI_14"], name="RSI", line=dict(color=BLUE)), row=1, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color=RED, annotation_text="Overbought", row=1, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color=GREEN, annotation_text="Oversold", row=1, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="gray", row=1, col=1)

    if "MACD" in df.columns and "MACD_signal" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD", line=dict(color=BLUE)), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD_signal"], name="Signal", line=dict(color=ORANGE)), row=2, col=1)
        if "MACD_hist" in df.columns:
            colors = [GREEN if v >= 0 else RED for v in df["MACD_hist"]]
            fig.add_trace(go.Bar(x=df.index, y=df["MACD_hist"], name="Histogram", marker_color=colors), row=2, col=1)

    fig.update_layout(template=CHART_THEME, height=350, margin=dict(l=40, r=40, t=40, b=20))
    return fig


def sector_heatmap(sector_data: list[dict]) -> go.Figure:
    """
    Sector performance heatmap (treemap).
    sector_data: [{"sector": str, "change_pct": float, "market_cap": float}]
    """
    if not sector_data:
        return go.Figure()

    df = pd.DataFrame(sector_data)
    fig = px.treemap(
        df, path=["sector"],
        values="market_cap" if "market_cap" in df.columns else None,
        color="change_pct",
        color_continuous_scale=["#ef5350", "#ffffff", "#26a69a"],
        color_continuous_midpoint=0,
        hover_data={"change_pct": ":.2f"},
    )
    fig.update_traces(texttemplate="<b>%{label}</b><br>%{customdata[0]:+.2f}%")
    fig.update_layout(
        template=CHART_THEME, height=350,
        margin=dict(l=0, r=0, t=20, b=0),
        coloraxis_showscale=False,
    )
    return fig


def index_line_chart(df: pd.DataFrame, name: str) -> go.Figure:
    """Simple line chart for an index."""
    color = GREEN if df["Close"].iloc[-1] >= df["Close"].iloc[0] else RED
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"], name=name,
        line=dict(color=color, width=2),
        fill="tozeroy", fillcolor=f"rgba({'38,166,154' if color == GREEN else '239,83,80'},0.1)",
    ))
    fig.update_layout(
        template=CHART_THEME, height=200,
        margin=dict(l=20, r=20, t=20, b=20),
        showlegend=False,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
    )
    return fig


def ytd_performance_chart(index_data: dict) -> go.Figure:
    """
    Multi-index normalized % return chart with range selector.
    index_data: {"Index Name": df_with_Close_column, ...}
    All series normalized to 0% at the earliest date in the dataset.
    """
    INDEX_COLORS = {
        "Nifty 50":   "#f0b429",
        "Bank Nifty": "#00c896",
        "Sensex":     "#7c83fd",
    }
    DEFAULT_COLORS = ["#f0b429", "#00c896", "#7c83fd", "#ff4d6d", "#2196F3"]

    fig = go.Figure()

    for idx, (name, df) in enumerate(index_data.items()):
        if df is None or df.empty or "Close" not in df.columns:
            continue
        df = df.sort_index().dropna(subset=["Close"])
        base = float(df["Close"].iloc[0])
        pct = ((df["Close"] / base) - 1) * 100
        color = INDEX_COLORS.get(name, DEFAULT_COLORS[idx % len(DEFAULT_COLORS)])
        fig.add_trace(go.Scatter(
            x=df.index,
            y=pct.round(2),
            name=name,
            line=dict(color=color, width=2.5),
            mode="lines",
            hovertemplate=(
                f"<b>{name}</b><br>"
                "Date: %{x|%d %b %Y}<br>"
                "Return: %{y:+.2f}%<br>"
                "Level: ₹%{customdata:,.0f}<extra></extra>"
            ),
            customdata=df["Close"].round(0).values,
        ))

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="rgba(255,255,255,0.18)",
        line_width=1,
    )

    rangeselector_style = dict(
        bgcolor="#1e2235",
        activecolor="#f0b429",
        bordercolor="rgba(255,255,255,0.1)",
        borderwidth=1,
        font=dict(color="#e2e8f0", size=12),
        buttons=[
            dict(count=7,  label="1W",  step="day",   stepmode="backward"),
            dict(count=1,  label="1M",  step="month", stepmode="backward"),
            dict(count=3,  label="3M",  step="month", stepmode="backward"),
            dict(count=6,  label="6M",  step="month", stepmode="backward"),
            dict(count=1,  label="YTD", step="year",  stepmode="todate"),
            dict(count=1,  label="1Y",  step="year",  stepmode="backward"),
        ],
    )

    fig.update_layout(
        template=CHART_THEME,
        height=420,
        margin=dict(l=50, r=30, t=50, b=30),
        yaxis=dict(
            title="% Return",
            ticksuffix="%",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.06)",
            zeroline=False,
        ),
        xaxis=dict(
            rangeselector=rangeselector_style,
            rangeslider=dict(visible=True, thickness=0.04, bgcolor="#12151f"),
            type="date",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.04)",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="right",
            x=1,
            font=dict(size=13),
        ),
        hovermode="x unified",
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
    )
    return fig


def market_breadth_gauge(advances: int, declines: int) -> go.Figure:
    """Gauge chart for market breadth."""
    total = advances + declines
    ratio = advances / total * 100 if total > 0 else 50

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=ratio,
        delta={"reference": 50},
        title={"text": f"Market Breadth<br><span style='font-size:0.8em'>{advances} Adv / {declines} Dec</span>"},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": GREEN if ratio > 55 else RED if ratio < 45 else ORANGE},
            "steps": [
                {"range": [0, 40], "color": "rgba(239,83,80,0.2)"},
                {"range": [40, 60], "color": "rgba(255,152,0,0.2)"},
                {"range": [60, 100], "color": "rgba(38,166,154,0.2)"},
            ],
            "threshold": {"line": {"color": "white", "width": 2}, "thickness": 0.75, "value": 50},
        },
    ))
    fig.update_layout(template=CHART_THEME, height=220, margin=dict(l=20, r=20, t=40, b=20))
    return fig

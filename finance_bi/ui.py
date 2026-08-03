"""Formatting and Plotly helpers for the Streamlit dashboard."""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from finance_bi.data_pipeline import DIMENSION_LABELS, METRIC_LABELS, RATE_METRICS


COLORS = {
    "ink": "#172033",
    "muted": "#667085",
    "line": "#E6EAF0",
    "blue": "#315EFB",
    "blue_light": "#DDE7FF",
    "gold": "#E7A23B",
    "orange": "#D66E3D",
    "slate": "#8290A8",
    "card": "#FFFFFF",
}
PLOTLY_TEMPLATE = "simple_white"


def amount(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    sign = "-" if value < 0 else ""
    value = abs(float(value))
    if value >= 100_000_000:
        return f"{sign}{value / 100_000_000:.2f}亿"
    if value >= 10_000:
        return f"{sign}{value / 10_000:.1f}万"
    return f"{sign}{value:,.0f}"


def rate(value: float | int | None, signed: bool = False) -> str:
    if value is None or pd.isna(value) or not math.isfinite(float(value)):
        return "—"
    return f"{float(value) * 100:+.2f}%" if signed else f"{float(value) * 100:.2f}%"


def yoy(value: float | int | None) -> str:
    if value is None or pd.isna(value) or not math.isfinite(float(value)):
        return "—"
    return f"{float(value) * 100:+.1f}%"


def pp(value: float | int | None) -> str:
    if value is None or pd.isna(value) or not math.isfinite(float(value)):
        return "—"
    return f"{float(value) * 100:+.2f}pp"


def style_figure(fig: go.Figure, height: int = 360, show_legend: bool = False) -> go.Figure:
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        height=height,
        paper_bgcolor=COLORS["card"],
        plot_bgcolor=COLORS["card"],
        font={"family": "Inter, PingFang SC, Microsoft YaHei, sans-serif", "color": COLORS["ink"]},
        margin={"l": 14, "r": 18, "t": 44, "b": 14},
        showlegend=show_legend,
        hoverlabel={"bgcolor": "#172033", "font": {"color": "#FFFFFF"}},
    )
    fig.update_xaxes(showgrid=False, linecolor=COLORS["line"], tickfont={"color": COLORS["muted"]})
    fig.update_yaxes(gridcolor="#EEF1F5", zeroline=False, tickfont={"color": COLORS["muted"]})
    return fig


def compact_table(frame: pd.DataFrame, columns: list[str], limit: int = 100) -> pd.DataFrame:
    return frame.loc[:, [column for column in columns if column in frame.columns]].head(limit).copy()


def chinese_headers(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a user-facing table with all known BI fields labelled in Chinese."""
    labels = {
        **DIMENSION_LABELS,
        **METRIC_LABELS,
        "source_year": "数据年度",
        "source_file": "源文件",
        "period_label": "期间",
        "comparison_period": "数据期间",
        "spu_count": "SPU数",
        "subcategory_spu_sample": "子类目SPU样本数",
        "platform_income": "平台收入",
        "platform_expense": "平台支出",
        "purchase_cost_raw": "采购成本源值",
        "first_leg_cost_raw": "头程费用源值",
        "tail_cost_raw": "尾程费用源值",
        "storage_cost_raw": "海外仓仓储费用源值",
        "refund_raw": "退款费用源值",
        "ad_raw": "广告费用源值",
        "gross_profit_1_raw": "毛利额-1源值",
        "inventory_loss_raw": "库存折损源值（原始符号）",
        "gross_profit_2_source_raw": "毛利额-2源值（仅审计）",
        "sales_amount_本期": "本期销售额",
        "sales_amount_去年同期": "去年同期销售额",
        "standard_gross_profit_1_本期": "本期毛利额-1",
        "standard_gross_profit_1_去年同期": "去年同期毛利额-1",
        "gross_margin_1_本期": "本期毛利率-1",
        "gross_margin_1_去年同期": "去年同期毛利率-1",
        "purchase_rate_本期": "本期采购成本占比",
        "purchase_rate_去年同期": "去年同期采购成本占比",
        "tail_rate_本期": "本期尾程费用占比",
        "tail_rate_去年同期": "去年同期尾程费用占比",
        "refund_rate_本期": "本期退款费用占比",
        "refund_rate_去年同期": "去年同期退款费用占比",
        "ad_rate_本期": "本期广告费占比",
        "ad_rate_去年同期": "去年同期广告费占比",
        "inventory_depreciation_本期": "本期库存折损",
        "inventory_depreciation_去年同期": "去年同期库存折损",
        "inventory_depreciation_rate_本期": "本期库存折损占比",
        "inventory_depreciation_rate_去年同期": "去年同期库存折损占比",
    }
    for metric_key, metric_label in METRIC_LABELS.items():
        labels[f"{metric_key}_本期"] = f"本期{metric_label}"
        labels[f"{metric_key}_去年同期"] = f"去年同期{metric_label}"
        labels[f"{metric_key}_上月"] = f"上月{metric_label}"
        labels[f"subcategory_median_{metric_key}"] = f"子类目中位数（{metric_label}）"
        labels[f"platform_median_{metric_key}"] = f"平台全品类中位数（{metric_label}）"
    return frame.rename(columns=labels)


def display_table(frame: pd.DataFrame, missing_as_dash: bool = False) -> pd.DataFrame:
    """Format a dataframe for Streamlit display while keeping source data numeric.

    Percentage-like fields are converted to explicit percentage strings so table
    cells use the same units as charts.  This function is display-only; exports
    can continue using the numeric dataframe when machine-readable values matter.
    """
    displayed = chinese_headers(frame.copy())
    renamed_columns = dict(zip(frame.columns, displayed.columns))

    period_column = renamed_columns.get("period")
    if period_column in displayed.columns:
        displayed[period_column] = pd.to_datetime(displayed[period_column], errors="coerce").dt.strftime("%Y-%m")

    for source_column, display_column in renamed_columns.items():
        if display_column not in displayed or not pd.api.types.is_numeric_dtype(displayed[display_column]):
            continue
        base_column = source_column.removesuffix("_本期").removesuffix("_去年同期")
        is_rate = (
            base_column in RATE_METRICS
            or base_column.startswith("subcategory_median_")
            or base_column.startswith("platform_median_")
            or any(token in str(display_column) for token in ("占比", "毛利率", "同比", "环比", "差异", "变化"))
        )
        if not is_rate:
            continue
        if any(token in str(display_column) for token in ("中位数差异", "同比变化", "环比变化")):
            displayed[display_column] = displayed[display_column].map(pp)
        elif any(token in str(display_column) for token in ("同比", "环比")):
            displayed[display_column] = displayed[display_column].map(
                lambda value: rate(value, signed=True)
            )
        else:
            displayed[display_column] = displayed[display_column].map(rate)
    if missing_as_dash:
        for column in displayed.columns:
            if displayed[column].isna().any():
                displayed[column] = displayed[column].map(
                    lambda value: "—" if pd.isna(value) else str(value)
                )
    return displayed

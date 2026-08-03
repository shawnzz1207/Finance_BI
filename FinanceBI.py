"""SPU-based finance BI dashboard draft.

Run with: python3 -m streamlit run FinanceBI.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from finance_bi.data_pipeline import (
    ANALYSIS_DIMENSIONS,
    DEFAULT_SOURCE_2025,
    DEFAULT_SOURCE_2026,
    DIMENSION_LABELS,
    METRIC_LABELS,
    RATE_METRICS,
    aggregate_pnl,
    apply_filters,
    available_dimension_values,
    build_monthly_full_metrics,
    build_monthly_metric_analysis,
    build_multi_metric_yoy_comparison,
    build_overview_monthly_detail,
    build_spu_benchmarks,
    load_finance_data,
    same_period_last_year,
    source_status,
)
from finance_bi.ui import (
    COLORS,
    amount,
    chinese_headers,
    compact_table,
    display_table,
    pp,
    rate,
    style_figure,
    yoy,
)


GRADE_ORDER = ["S", "A", "B", "C+", "C-", "C--", "新品", "0"]
GRADE_COLORS = {
    "S": "#2147C7",
    "A": "#315EFB",
    "B": "#6F8DFF",
    "C+": "#8D78D6",
    "C-": "#D66E3D",
    "C--": "#E7A23B",
    "新品": "#3A9188",
    "0": "#8290A8",
    "未分级": "#C3CBD7",
}

COST_OPTIONS = {
    "采购成本": ("purchase_cost", "purchase_rate"),
    "头程费用": ("first_leg_cost", "first_leg_rate"),
    "尾程费用": ("tail_cost", "tail_rate"),
    "仓储成本": ("storage_cost", "storage_rate"),
    "退款费用": ("refund_cost", "refund_rate"),
    "广告费用": ("ad_cost", "ad_rate"),
    "库存折损": ("inventory_depreciation", "inventory_depreciation_rate"),
}
COST_METRIC_KEYS = {metric for pair in COST_OPTIONS.values() for metric in pair}
DEFAULT_OVERVIEW_CARD_LABELS = [
    "销售额",
    "毛利额-1",
    "毛利率-1",
    "采购成本占比",
    "退款费用占比",
    "广告费占比",
]
DATA_MODEL_VERSION = "2026-08-storage-cost-v1"
MONTHLY_SERIES_COLORS = [
    COLORS["blue"],
    COLORS["gold"],
    COLORS["orange"],
    COLORS["slate"],
    "#7761C7",
    "#3A9188",
    "#C25483",
    "#537A49",
    "#8C6D3D",
    "#5574A6",
]


st.set_page_config(
    page_title="SPU 财务经营 BI",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root { --ink:#172033; --muted:#667085; --line:#E6EAF0; --blue:#315EFB; }
        .stApp { background: #F6F7FB; color: var(--ink); }
        [data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E6EAF0; }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1.3rem; }
        .block-container { max-width: 1580px; padding: 1.7rem 2.2rem 3rem; }
        h1, h2, h3 { color: #172033 !important; letter-spacing: -0.02em; }
        h2 { font-size: 1.25rem !important; margin-top: .35rem !important; }
        .hero {
            background: linear-gradient(120deg, #FFFFFF 0%, #F2F6FF 100%);
            border: 1px solid #E4EAF7; border-radius: 18px; padding: 1.2rem 1.45rem;
            margin-bottom: 1.25rem;
        }
        .hero .eyebrow { color:#315EFB; font-size:.74rem; font-weight:700; letter-spacing:.09em; }
        .hero h1 { margin:.18rem 0 .28rem; font-size:1.7rem; }
        .hero p { margin:0; color:#667085; font-size:.9rem; }
        .section-note { color:#667085; font-size:.82rem; margin: -.45rem 0 .8rem; }
        div[data-testid="stMetric"] {
            background:#FFFFFF; border:1px solid #E7EBF2; border-radius:14px;
            padding:.9rem 1rem; box-shadow:0 4px 16px rgba(16,24,40,.035);
        }
        div[data-testid="stMetricLabel"] { color:#667085; font-size:.78rem; }
        div[data-testid="stMetricValue"] { color:#172033; font-size:1.38rem; }
        div[class*="st-key-overview_metric_card_"] { position:relative; }
        div[class*="st-key-overview_metric_card_"] [data-testid="stVerticalBlock"] {
            position:relative;
        }
        div[class*="st-key-overview_metric_card_"] div[data-testid="stElementContainer"]:has([data-testid="stButton"]) {
            position:absolute !important; inset:0 !important; z-index:5;
            width:100% !important; height:100% !important; min-height:114px !important; margin:0 !important;
        }
        div[class*="st-key-overview_metric_card_"] [data-testid="stButton"] {
            width:100%; height:100%; min-height:114px; margin:0;
        }
        div[class*="st-key-overview_metric_card_"] [data-testid="stButton"] button {
            width:100%; height:100%; min-height:114px; opacity:0; cursor:pointer;
        }
        div[class*="st-key-overview_metric_card_"]:hover div[data-testid="stMetric"] {
            border-color:#9CB2FF; box-shadow:0 6px 20px rgba(49,94,251,.10);
        }
        div[class*="st-key-overview_metric_card_selected_"] div[data-testid="stMetric"] {
            border-color:#315EFB; box-shadow:0 0 0 2px rgba(49,94,251,.10);
        }
        [data-testid="stTabs"] [role="tablist"] { gap:.35rem; }
        [data-testid="stTabs"] button[role="tab"] { border-radius:8px 8px 0 0; }
        .filter-caption { color:#667085; font-size:.76rem; margin-top:-.35rem; }
        .data-status { background:#FFFFFF; border:1px solid #E7EBF2; border-radius:12px; padding:.75rem 1rem; }
        [data-testid="stDownloadButton"] button { border-radius:8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner="正在读取原表并汇总 SPU 经营数据…")
def cached_load(
    data_model_version: str,
    path_2025: str,
    path_2026: str,
    mtime_2025: float,
    mtime_2026: float,
    upload_2025: bytes | None,
    upload_2026: bytes | None,
    upload_name_2025: str | None,
    upload_name_2026: str | None,
) -> pd.DataFrame:
    del data_model_version, mtime_2025, mtime_2026
    return load_finance_data(
        upload_2025 if upload_2025 is not None else path_2025,
        upload_2026 if upload_2026 is not None else path_2026,
        upload_name_2025,
        upload_name_2026,
    )


def current_mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


def as_number(frame: pd.DataFrame, key: str) -> float:
    if frame.empty or key not in frame.columns:
        return 0.0
    value = frame.iloc[0][key]
    return float(value) if pd.notna(value) else 0.0


def current_scope_text(periods: list[pd.Timestamp], year: int) -> str:
    if not periods:
        return "未选择期间"
    start, end = periods[0].strftime("%Y-%m"), periods[-1].strftime("%Y-%m")
    return f"{start} ～ {end}" if start != end else start


def source_uploaders() -> tuple[object | None, object | None]:
    with st.sidebar:
        st.markdown("### 数据导入")
        with st.expander("导入原始经营报表", expanded=False):
            upload_2025 = st.file_uploader(
                "2025 年经营报表",
                type=["xlsx"],
                key="source_upload_2025",
                help="上传后替代系统默认的 2025 数据源，不会修改原文件。",
            )
            upload_2026 = st.file_uploader(
                "2026 年经营报表",
                type=["xlsx"],
                key="source_upload_2026",
                help="上传后替代系统默认的 2026 数据源，不会修改原文件。",
            )
            st.caption("未上传的年度继续使用服务器默认原表；系统读取公式缓存值，并按既定字段位置运算。")
        st.markdown("---")
    return upload_2025, upload_2026


def prune_multiselect_state(key: str, options: list[object]) -> None:
    """Remove downstream selections that are invalid under current upstream filters."""
    selected = st.session_state.get(key)
    if selected is None:
        return
    valid_options = set(options)
    valid_selected = [value for value in selected if value in valid_options]
    if valid_selected != selected:
        st.session_state[key] = valid_selected


def make_filters(data: pd.DataFrame) -> tuple[int, list[pd.Timestamp], dict[str, list[str]], bool]:
    filter_keys = [
        "analysis_year",
        "analysis_periods",
        "platform_filter",
        "store_filter",
        "group_filter",
        "owner_filter",
        "grade_filter",
        "category_filter",
        "subcategory_filter",
        "spu_query",
        "spu_filter",
        "yoy_enabled",
    ]
    with st.sidebar:
        st.markdown("### 分析条件")
        if st.button("重置全部筛选", width="stretch"):
            for key in filter_keys:
                st.session_state.pop(key, None)
            st.rerun()

        selected_year = st.radio("分析年度", options=[2026, 2025], horizontal=True, key="analysis_year")
        year_periods = sorted(data.loc[data["source_year"] == selected_year, "period"].drop_duplicates())
        start_period, end_period = st.select_slider(
            "经营期间",
            options=year_periods,
            value=(year_periods[0], year_periods[-1]),
            format_func=lambda value: value.strftime("%Y-%m"),
            key="analysis_periods",
        )
        periods = [period for period in year_periods if start_period <= period <= end_period]
        yoy_enabled = False
        if selected_year == 2026:
            yoy_enabled = st.toggle("同时显示 2025 同期", value=True, key="yoy_enabled")
        else:
            st.caption("同比功能会在选择 2026 年期间时启用。")

        period_data = data.loc[data["period"].isin(periods)].copy()
        st.markdown("---")
        st.markdown("##### 业务范围")
        platform_options = available_dimension_values(period_data, "platform")
        prune_multiselect_state("platform_filter", platform_options)
        platforms = st.multiselect(
            "平台",
            platform_options,
            key="platform_filter",
            placeholder="全部平台",
        )
        platform_constraint = {"platform": platforms}

        store_options = available_dimension_values(period_data, "store", platform_constraint)
        prune_multiselect_state("store_filter", store_options)
        stores = st.multiselect("店铺", store_options, key="store_filter", placeholder="全部店铺")

        group_options = available_dimension_values(period_data, "group", platform_constraint)
        prune_multiselect_state("group_filter", group_options)
        groups = st.multiselect(
            "组别", group_options, key="group_filter", placeholder="全部组别"
        )
        owner_options = available_dimension_values(
            period_data,
            "owner",
            {"platform": platforms, "group": groups},
        )
        prune_multiselect_state("owner_filter", owner_options)
        owners = st.multiselect("负责人", owner_options, key="owner_filter", placeholder="全部负责人")
        st.caption("筛选联动：平台 → 组别 → 负责人；店铺随平台联动。")

        st.markdown("---")
        st.markdown("##### 产品范围")
        grades = st.multiselect("产品分级", sorted(period_data["grade"].unique()), key="grade_filter", placeholder="全部分级")
        categories = st.multiselect(
            "大类目", sorted(period_data["category"].unique()), key="category_filter", placeholder="全部类目"
        )
        subcategory_pool = period_data.loc[
            period_data["category"].isin(categories) if categories else pd.Series(True, index=period_data.index),
            "subcategory",
        ]
        subcategories = st.multiselect(
            "子类目", sorted(subcategory_pool.unique()), key="subcategory_filter", placeholder="全部子类目"
        )
        query = st.text_input("搜索 SPU", placeholder="输入完整或部分 SPU", key="spu_query").strip().upper()
        all_spus = sorted(period_data["spu"].unique())
        matched_spus = [spu for spu in all_spus if query in spu.upper()] if query else all_spus
        spus = st.multiselect(
            "选择 SPU",
            matched_spus,
            key="spu_filter",
            placeholder="全部 SPU",
            help="仅以 SPU 为产品粒度；SKU 和 MSKU 不在页面中显示。",
        )
        st.caption(f"当前期间共 {len(all_spus):,} 个 SPU；搜索匹配 {len(matched_spus):,} 个。")
        st.markdown("<p class='filter-caption'>选择的筛选条件会同步作用于各页图表、表格和导出。</p>", unsafe_allow_html=True)

    filters = {
        "platform": platforms,
        "store": stores,
        "group": groups,
        "owner": owners,
        "grade": grades,
        "category": categories,
        "subcategory": subcategories,
        "spu": spus,
    }
    return selected_year, periods, filters, yoy_enabled


def metric_delta(current: pd.DataFrame, previous: pd.DataFrame, key: str, is_rate: bool = False) -> str | None:
    if previous.empty:
        return None
    current_value, previous_value = as_number(current, key), as_number(previous, key)
    if is_rate:
        return pp(current_value - previous_value)
    if previous_value == 0:
        return None
    return yoy(current_value / previous_value - 1)


def bar_figure(
    data: pd.DataFrame,
    category: str,
    metric: str,
    title: str,
    color: str = COLORS["blue"],
    horizontal: bool = True,
) -> go.Figure:
    metric_is_rate = metric in RATE_METRICS
    ordered = data.sort_values(metric, ascending=horizontal).copy()
    ordered["图表数值"] = ordered[metric].map(rate if metric_is_rate else amount)
    labels = {**DIMENSION_LABELS, **METRIC_LABELS, "图表数值": "数值"}
    category_label = DIMENSION_LABELS.get(category, category)
    metric_label = METRIC_LABELS.get(metric, metric)
    if horizontal:
        fig = px.bar(
            ordered,
            x=metric,
            y=category,
            orientation="h",
            text="图表数值",
            labels=labels,
            color_discrete_sequence=[color],
        )
        fig.update_yaxes(categoryorder="array", categoryarray=ordered[category].tolist(), title=category_label)
        fig.update_xaxes(tickformat=".0%" if metric_is_rate else ",.0f", title=metric_label)
        value_format = ".2%" if metric_is_rate else ",.2f"
        fig.update_traces(
            textposition="outside",
            cliponaxis=False,
            hovertemplate=f"{category_label}=%{{y}}<br>{metric_label}=%{{x:{value_format}}}<extra></extra>",
        )
    else:
        fig = px.bar(
            ordered,
            x=category,
            y=metric,
            text="图表数值",
            labels=labels,
            color_discrete_sequence=[color],
        )
        fig.update_xaxes(title=category_label)
        fig.update_yaxes(tickformat=".0%" if metric_is_rate else ",.0f", title=metric_label)
        value_format = ".2%" if metric_is_rate else ",.2f"
        fig.update_traces(
            textposition="outside",
            cliponaxis=False,
            hovertemplate=f"{category_label}=%{{x}}<br>{metric_label}=%{{y:{value_format}}}<extra></extra>",
        )
    fig.update_layout(title={"text": title, "font": {"size": 14, "color": COLORS["ink"]}})
    fig = style_figure(fig, height=350)
    fig.update_layout(margin={"l": 14, "r": 88, "t": 50, "b": 20})
    return fig


def trend_figure(current: pd.DataFrame, prior: pd.DataFrame, metric: str, title: str) -> go.Figure:
    fig = go.Figure()
    metric_is_rate = metric in RATE_METRICS
    metric_label = METRIC_LABELS.get(metric, metric)
    for frame, suffix, color, text_position in [
        (prior, " 同期", COLORS["slate"], "bottom center"),
        (current, "", COLORS["blue"], "top center"),
    ]:
        if frame.empty:
            continue
        view = aggregate_pnl(frame, ["period"]).sort_values("period")
        year = int(frame["source_year"].iloc[0]) if "source_year" in frame.columns else view["period"].dt.year.iloc[0]
        display_values = view[metric].map(rate if metric_is_rate else amount)
        value_format = ".2%" if metric_is_rate else ",.2f"
        fig.add_trace(
            go.Scatter(
                x=view["period"],
                y=view[metric],
                mode="lines+markers+text",
                name=f"{year}{suffix}",
                text=display_values,
                textposition=text_position,
                textfont={"size": 10, "color": color},
                line={"color": color, "width": 2.5},
                marker={"size": 6},
                hovertemplate=f"月份=%{{x|%Y-%m}}<br>{metric_label}=%{{y:{value_format}}}<extra></extra>",
            )
        )
    fig.update_layout(
        title={"text": title, "font": {"size": 14, "color": COLORS["ink"]}},
        yaxis={"tickformat": ".0%" if metric_is_rate else ",.0f", "title": metric_label},
        xaxis={"title": "月份", "tickformat": "%Y-%m"},
    )
    fig = style_figure(fig, height=340, show_legend=True)
    fig.update_layout(margin={"l": 18, "r": 34, "t": 54, "b": 30})
    return fig


def overview_monthly_detail_figure(
    detail: pd.DataFrame,
    metric: str,
    current_year: int,
    prior_year: int | None,
) -> go.Figure:
    """Render an aligned monthly KPI trend after a metric-card click."""
    fig = go.Figure()
    metric_is_rate = metric in RATE_METRICS
    metric_label = METRIC_LABELS.get(metric, metric)
    prior_column = f"{metric}_去年同期"
    series = []
    if prior_year is not None and prior_column in detail.columns:
        series.append((prior_column, f"{prior_year} 同期", COLORS["slate"], "bottom center"))
    series.append((metric, str(current_year), COLORS["blue"], "top center"))

    for column, name, color, text_position in series:
        display_values = detail[column].map(rate if metric_is_rate else amount)
        value_format = ".2%" if metric_is_rate else ",.2f"
        fig.add_trace(
            go.Scatter(
                x=detail["period"],
                y=detail[column],
                mode="lines+markers+text",
                name=name,
                text=display_values,
                textposition=text_position,
                textfont={"size": 10, "color": color},
                line={"color": color, "width": 2.5},
                marker={"size": 6},
                hovertemplate=(
                    f"月份=%{{x|%Y-%m}}<br>期间={name}<br>"
                    f"{metric_label}=%{{y:{value_format}}}<extra></extra>"
                ),
            )
        )
    fig.update_xaxes(title="月份", tickformat="%Y-%m", dtick="M1")
    fig.update_yaxes(tickformat=".0%" if metric_is_rate else ",.0f", title=metric_label)
    fig.update_layout(title={"text": f"{metric_label}月度明细", "font": {"size": 14}})
    fig = style_figure(fig, height=350, show_legend=True)
    fig.update_layout(margin={"l": 18, "r": 44, "t": 54, "b": 30})
    return fig


def monthly_analysis_figure(
    data: pd.DataFrame,
    dimensions: list[str],
    metric: str,
    title: str,
) -> go.Figure:
    """Render a consistent Top-N set as directly labelled monthly series."""
    view = data.copy()
    view["分析对象"] = view[dimensions].astype(str).agg(" · ".join, axis=1)
    metric_is_rate = metric in RATE_METRICS
    metric_label = METRIC_LABELS.get(metric, metric)
    view["图表数值"] = view[metric].map(rate if metric_is_rate else amount)
    series_order = view["分析对象"].drop_duplicates().tolist()
    color_map = {
        series: MONTHLY_SERIES_COLORS[index % len(MONTHLY_SERIES_COLORS)]
        for index, series in enumerate(series_order)
    }
    fig = px.line(
        view,
        x="period",
        y=metric,
        color="分析对象",
        markers=True,
        text="图表数值",
        category_orders={"分析对象": series_order},
        color_discrete_map=color_map,
        labels={"period": "月份", metric: metric_label, "分析对象": "分析对象"},
    )
    value_format = ".2%" if metric_is_rate else ",.2f"
    fig.update_traces(
        textposition="top center",
        cliponaxis=False,
        hovertemplate=(
            "月份=%{x|%Y-%m}<br>分析对象=%{fullData.name}<br>"
            f"{metric_label}=%{{y:{value_format}}}<extra></extra>"
        ),
    )
    fig.update_xaxes(title="月份", tickformat="%Y-%m", dtick="M1")
    fig.update_yaxes(tickformat=".0%" if metric_is_rate else ",.0f", title=metric_label)
    fig.update_layout(title={"text": title, "font": {"size": 14}})
    fig = style_figure(fig, height=500, show_legend=True)
    fig.update_layout(margin={"l": 18, "r": 54, "t": 54, "b": 34})
    return fig


def build_metric_comparison(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    dimensions: list[str],
    metric: str,
) -> pd.DataFrame:
    """Build a reusable current-vs-prior comparison at the selected grain."""
    if current.empty or prior.empty:
        return pd.DataFrame()
    current_view = aggregate_pnl(current, dimensions)[[*dimensions, metric]].rename(
        columns={metric: f"{metric}_本期"}
    )
    prior_view = aggregate_pnl(prior, dimensions)[[*dimensions, metric]].rename(
        columns={metric: f"{metric}_去年同期"}
    )
    merged = current_view.merge(prior_view, on=dimensions, how="outer")
    current_column, prior_column = f"{metric}_本期", f"{metric}_去年同期"
    merged[[current_column, prior_column]] = merged[[current_column, prior_column]].fillna(0.0)
    merged["状态"] = "存量"
    merged.loc[(merged[prior_column] == 0) & (merged[current_column] != 0), "状态"] = "新增"
    merged.loc[(merged[prior_column] != 0) & (merged[current_column] == 0), "状态"] = "退出"
    metric_label = METRIC_LABELS.get(metric, metric)
    if metric in RATE_METRICS:
        change_column = f"{metric_label}同比变化"
        merged[change_column] = merged[current_column] - merged[prior_column]
    else:
        change_column = f"{metric_label}同比"
        denominator = merged[prior_column].where(merged[prior_column] != 0)
        merged[change_column] = merged[current_column].div(denominator) - 1
    return merged


def period_comparison_figure(
    comparison: pd.DataFrame,
    current: pd.DataFrame,
    prior: pd.DataFrame,
    dimensions: list[str],
    metric: str,
    title: str,
    top_n: int = 20,
) -> go.Figure:
    """Render grouped period bars with direct labels for 2026 and 2025同期."""
    metric_is_rate = metric in RATE_METRICS
    current_column, prior_column = f"{metric}_本期", f"{metric}_去年同期"
    ranked = comparison.copy()
    ranked["_rank"] = ranked[[current_column, prior_column]].abs().max(axis=1)
    ranked = ranked.nlargest(min(top_n, len(ranked)), "_rank").sort_values(current_column)
    ranked["对比项"] = ranked[dimensions].astype(str).agg(" · ".join, axis=1)

    current_year = int(current["source_year"].iloc[0]) if "source_year" in current.columns else 2026
    prior_year = int(prior["source_year"].iloc[0]) if "source_year" in prior.columns else current_year - 1
    current_label, prior_label = str(current_year), f"{prior_year} 同期"
    long_view = pd.concat(
        [
            ranked[["对比项", current_column]].rename(columns={current_column: "指标值"}).assign(期间=current_label),
            ranked[["对比项", prior_column]].rename(columns={prior_column: "指标值"}).assign(期间=prior_label),
        ],
        ignore_index=True,
    )
    long_view["图表数值"] = long_view["指标值"].map(rate if metric_is_rate else amount)
    metric_label = METRIC_LABELS.get(metric, metric)
    fig = px.bar(
        long_view,
        x="指标值",
        y="对比项",
        color="期间",
        orientation="h",
        barmode="group",
        text="图表数值",
        category_orders={"期间": [prior_label, current_label], "对比项": ranked["对比项"].tolist()},
        color_discrete_map={prior_label: COLORS["slate"], current_label: COLORS["blue"]},
        labels={"指标值": metric_label, "对比项": "分析对象", "期间": "期间"},
    )
    value_format = ".2%" if metric_is_rate else ",.2f"
    fig.update_xaxes(tickformat=".0%" if metric_is_rate else ",.0f", title=metric_label)
    fig.update_yaxes(title=" / ".join(DIMENSION_LABELS.get(item, item) for item in dimensions))
    fig.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "分析对象=%{y}<br>期间=%{fullData.name}<br>"
            f"{metric_label}=%{{x:{value_format}}}<extra></extra>"
        ),
    )
    fig.update_layout(title={"text": title, "font": {"size": 14}})
    fig = style_figure(fig, height=max(380, min(680, 34 * len(ranked) + 150)), show_legend=True)
    fig.update_layout(margin={"l": 14, "r": 88, "t": 52, "b": 24})
    return fig


def render_yoy_comparison(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    dimensions: list[str],
    metric: str,
    heading: str,
    top_n: int = 20,
    show_table: bool = True,
) -> None:
    if prior.empty:
        return
    comparison = build_metric_comparison(current, prior, dimensions, metric)
    if comparison.empty:
        return
    st.markdown(f"#### {heading}")
    st.plotly_chart(
        period_comparison_figure(comparison, current, prior, dimensions, metric, heading, top_n),
        width="stretch",
        config={"displayModeBar": False},
    )
    if show_table:
        metric_label = METRIC_LABELS.get(metric, metric)
        change_column = f"{metric_label}同比变化" if metric in RATE_METRICS else f"{metric_label}同比"
        columns = [
            *dimensions,
            "状态",
            f"{metric}_本期",
            f"{metric}_去年同期",
            change_column,
        ]
        table = comparison.loc[:, columns].sort_values(f"{metric}_本期", ascending=False)
        st.dataframe(display_table(table), width="stretch", hide_index=True, height=320)


def render_multi_metric_yoy_detail(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    dimensions: list[str],
    metrics: list[str],
) -> None:
    detail = build_multi_metric_yoy_comparison(current, prior, dimensions, metrics)
    st.markdown(f"#### SPU同期汇总明细 · {len(metrics)}项指标")
    st.markdown(
        "<p class='section-note'>每个SPU仅保留一行；所选指标依次展示本期、去年同期及同比变化。</p>",
        unsafe_allow_html=True,
    )
    if detail.empty:
        st.info("当前筛选条件下没有可展示的SPU同期汇总数据。")
        return

    preferred_sort = "sales_amount_本期" if "sales_amount" in metrics else f"{metrics[0]}_本期"
    detail = detail.sort_values(preferred_sort, ascending=False, kind="stable")
    st.dataframe(display_table(detail), width="stretch", hide_index=True, height=440)
    st.download_button(
        "导出SPU同期汇总明细（CSV）",
        data=chinese_headers(detail).to_csv(index=False).encode("utf-8-sig"),
        file_name="spu_finance_yoy_multi_metric_detail.csv",
        mime="text/csv",
        key="spu_yoy_multi_metric_download",
    )


def render_cost_rate_change(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    top_spus: list[str],
    rate_metric: str,
    cost_label: str,
) -> None:
    """Compare cost shares for the current-period Top10 SPUs in percentage points."""
    if prior.empty or not top_spus:
        return

    current_top = current.loc[current["spu"].isin(top_spus)]
    prior_top = prior.loc[prior["spu"].isin(top_spus)]
    comparison = build_metric_comparison(current_top, prior_top, ["spu"], rate_metric)
    if comparison.empty:
        return

    rate_label = METRIC_LABELS[rate_metric]
    current_column = f"{rate_metric}_本期"
    prior_column = f"{rate_metric}_去年同期"
    change_column = f"{rate_label}同比变化"
    comparison["占比差值_pp"] = comparison[change_column] * 100
    comparison["变化显示"] = comparison[change_column].map(pp)
    comparison["变化方向"] = comparison["占比差值_pp"].map(
        lambda value: "占比上升" if value > 0 else ("占比下降" if value < 0 else "持平")
    )
    comparison = comparison.sort_values("占比差值_pp")

    current_year = int(current_top["source_year"].iloc[0]) if "source_year" in current_top.columns else 2026
    prior_year = int(prior_top["source_year"].iloc[0]) if "source_year" in prior_top.columns else current_year - 1
    title = f"{cost_label}占比同期变化（Top10 SPU）"

    st.markdown(f"#### {title}")
    st.markdown(
        "<p class='section-note'>统一比较成本占销售额的比例；正值表示成本占比上升，负值表示成本占比下降。</p>",
        unsafe_allow_html=True,
    )
    fig = px.bar(
        comparison,
        x="占比差值_pp",
        y="spu",
        color="变化方向",
        orientation="h",
        text="变化显示",
        custom_data=[current_column, prior_column],
        category_orders={"spu": comparison["spu"].tolist()},
        color_discrete_map={
            "占比上升": COLORS["orange"],
            "占比下降": COLORS["blue"],
            "持平": COLORS["slate"],
        },
        labels={"spu": "SPU", "占比差值_pp": "占比差值（pp）", "变化方向": "变化方向"},
    )
    fig.update_xaxes(title="占比差值（pp）", ticksuffix="pp", tickformat="+.1f", zeroline=True)
    fig.update_yaxes(categoryorder="array", categoryarray=comparison["spu"].tolist(), title="SPU")
    fig.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "SPU=%{y}<br>占比变化=%{x:+.2f}pp"
            f"<br>{current_year}占比=%{{customdata[0]:.2%}}"
            f"<br>{prior_year}同期占比=%{{customdata[1]:.2%}}<extra></extra>"
        ),
    )
    fig.update_layout(title={"text": title, "font": {"size": 14}})
    fig = style_figure(fig, height=430, show_legend=True)
    fig.add_vline(x=0, line_width=1, line_color=COLORS["line"])
    fig.update_layout(margin={"l": 14, "r": 100, "t": 52, "b": 24})
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    table_columns = ["spu", "状态", current_column, prior_column, change_column]
    table = comparison.loc[:, table_columns].sort_values(change_column, ascending=False)
    st.dataframe(display_table(table), width="stretch", hide_index=True, height=320)


def toggle_overview_metric(metric: str) -> None:
    current_metric = st.session_state.get("overview_active_metric")
    st.session_state["overview_active_metric"] = None if current_metric == metric else metric


def render_overview_metric_detail(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    metric: str,
    year: int,
    yoy_enabled: bool,
) -> None:
    detail = build_overview_monthly_detail(
        current,
        prior if yoy_enabled else pd.DataFrame(),
        metric,
    )
    if detail.empty:
        st.info("当前筛选条件下没有可展示的月度明细。")
        return

    metric_label = METRIC_LABELS.get(metric, metric)
    prior_year = year - 1 if yoy_enabled and not prior.empty else None
    st.markdown(f"#### 指标卡月度明细 · {metric_label}")
    st.markdown(
        "<p class='section-note'>点击其他指标卡可直接切换；再次点击当前指标卡可收起明细。</p>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        overview_monthly_detail_figure(detail, metric, year, prior_year),
        width="stretch",
        config={"displayModeBar": False},
    )
    st.dataframe(
        display_table(detail, missing_as_dash=True),
        width="stretch",
        hide_index=True,
        height=270,
    )
    st.caption("金额环比/同比以百分比展示；成本占比及毛利率的环比/同比变化以 pp 展示。")


def render_monthly_full_metrics(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    yoy_enabled: bool,
) -> None:
    detail = build_monthly_full_metrics(
        current,
        prior if yoy_enabled else pd.DataFrame(),
    )
    st.markdown("#### 月度经营全指标明细")
    st.markdown(
        "<p class='section-note'>按月汇总当前筛选范围，展示SPU数及全部正式BI经营指标；开启同期后，每个月同步追加去年同期数据。</p>",
        unsafe_allow_html=True,
    )
    if detail.empty:
        st.info("当前筛选条件下没有可展示的月度经营数据。")
        return

    displayed = display_table(detail, missing_as_dash=True)
    table_height = max(300, min(620, 38 * len(displayed) + 54))
    st.dataframe(displayed, width="stretch", hide_index=True, height=table_height)
    st.download_button(
        "导出月度全指标明细（CSV）",
        data=chinese_headers(detail).to_csv(index=False).encode("utf-8-sig"),
        file_name="spu_finance_monthly_all_metrics.csv",
        mime="text/csv",
        key="overview_monthly_all_metrics_download",
    )
    st.caption("占比字段统一以百分比显示；毛利仅采用毛利额-1口径，后台审计字段不在此表展示。")


def metric_cards(current: pd.DataFrame, prior: pd.DataFrame, year: int, yoy_enabled: bool) -> None:
    label_to_metric = {label: key for key, label in METRIC_LABELS.items()}
    saved_selection_key = "overview_card_selection"
    saved_selection = [
        label
        for label in st.session_state.get(saved_selection_key, DEFAULT_OVERVIEW_CARD_LABELS)
        if label in label_to_metric
    ]
    with st.expander("自定义核心指标卡", expanded=False):
        selected_labels = st.multiselect(
            "选择头部展示指标",
            options=list(label_to_metric),
            default=saved_selection,
            key="overview_card_metrics",
            help="可自由增减销售、毛利及各项成本金额/占比；选择结果在当前会话中保留。",
        )
    st.session_state[saved_selection_key] = list(selected_labels)

    if not selected_labels:
        st.info("请在“自定义核心指标卡”中至少选择一个指标。")
        return

    current_summary = aggregate_pnl(current, [])
    prior_summary = aggregate_pnl(prior, [])
    cards = [(label, label_to_metric[label]) for label in selected_labels]
    active_metric = st.session_state.get("overview_active_metric")
    selected_metrics = {metric for _, metric in cards}
    if active_metric not in selected_metrics:
        active_metric = None
        st.session_state["overview_active_metric"] = None

    for start in range(0, len(cards), 6):
        row_cards = cards[start : start + 6]
        columns = st.columns(6 if len(cards) > 6 else len(row_cards))
        for container, (label, key) in zip(columns, row_cards):
            is_rate = key in RATE_METRICS
            value = as_number(current_summary, key)
            value_text = rate(value) if is_rate else amount(value)
            delta = (
                metric_delta(current_summary, prior_summary, key, is_rate)
                if yoy_enabled and year == 2026
                else None
            )
            card_state = "selected" if active_metric == key else "idle"
            with container.container(key=f"overview_metric_card_{card_state}_{key}"):
                st.metric(
                    label,
                    value_text,
                    delta=delta,
                    delta_color="inverse" if key in COST_METRIC_KEYS else "normal",
                    help="同比为 2025 同期；费率同比以百分点展示。成本上升按不利变化标识。",
                )
                st.button(
                    f"查看{label}月度明细",
                    key=f"overview_metric_button_{key}",
                    on_click=toggle_overview_metric,
                    args=(key,),
                    help=f"点击查看{label}的月度趋势与明细表",
                )

    active_metric = st.session_state.get("overview_active_metric")
    if active_metric in selected_metrics:
        render_overview_metric_detail(current, prior, active_metric, year, yoy_enabled)


def cost_top10_section(current: pd.DataFrame, prior: pd.DataFrame) -> None:
    st.markdown("#### 成本 TOP10 SPU")
    st.markdown(
        "<p class='section-note'>可按成本绝对值或销售额占比排序；每根柱同步显示金额和占比。</p>",
        unsafe_allow_html=True,
    )
    controls = st.columns([1.2, 1, 2.8])
    with controls[0]:
        selected_label = st.selectbox("成本项", list(COST_OPTIONS), key="overview_cost_metric")
    with controls[1]:
        sort_basis = st.radio("排序依据", ["绝对值", "占比"], horizontal=True, key="overview_cost_sort")

    amount_metric, rate_metric = COST_OPTIONS[selected_label]
    view = aggregate_pnl(current, ["spu"])
    if sort_basis == "占比":
        view = view.loc[view["sales_amount"] > 0].copy()
        sort_metric = rate_metric
    else:
        sort_metric = amount_metric
    top = view.dropna(subset=[sort_metric]).nlargest(10, sort_metric).sort_values(sort_metric)
    if top.empty:
        st.info("当前筛选条件下没有可用于成本排名的数据。")
        return

    top["金额显示"] = top[amount_metric].map(amount)
    top["占比显示"] = top[rate_metric].map(rate)
    top["同步数值"] = top["金额显示"] + " ｜ " + top["占比显示"]
    fig = px.bar(
        top,
        x=sort_metric,
        y="spu",
        orientation="h",
        text="同步数值",
        custom_data=[amount_metric, rate_metric],
        labels={
            "spu": "SPU",
            sort_metric: f"{selected_label}{'占比' if sort_basis == '占比' else ''}",
        },
        color_discrete_sequence=[COLORS["blue"]],
    )
    fig.update_yaxes(categoryorder="array", categoryarray=top["spu"].tolist(), title="SPU")
    if sort_basis == "占比":
        fig.update_xaxes(tickformat=".0%", title=f"{selected_label}占比")
    else:
        fig.update_xaxes(tickformat=",.0f", title=selected_label)
    fig.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            f"SPU=%{{y}}<br>{selected_label}=%{{customdata[0]:,.2f}}"
            f"<br>{selected_label}占比=%{{customdata[1]:.2%}}<extra></extra>"
        ),
    )
    fig.update_layout(
        title={"text": f"按{sort_basis}排序的 {selected_label} TOP10 SPU", "font": {"size": 14}},
    )
    fig = style_figure(fig, height=430)
    fig.update_layout(margin={"l": 14, "r": 150, "t": 52, "b": 24})
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    table = top[["spu", amount_metric, rate_metric]].sort_values(sort_metric, ascending=False)
    st.dataframe(display_table(table), width="stretch", hide_index=True, height=285)
    if not prior.empty:
        render_cost_rate_change(
            current,
            prior,
            top["spu"].astype(str).tolist(),
            rate_metric,
            selected_label,
        )


def overview_page(current: pd.DataFrame, prior: pd.DataFrame, year: int, yoy_enabled: bool, scope: str) -> None:
    st.markdown("## 经营总览")
    st.markdown(f"<p class='section-note'>当前期间：{scope}。毛利额与毛利率统一采用原表“毛利额-1”口径。</p>", unsafe_allow_html=True)
    metric_cards(current, prior, year, yoy_enabled)

    st.markdown("#### 经营走势")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            trend_figure(current, prior if yoy_enabled else pd.DataFrame(), "sales_amount", "销售额走势"),
            width="stretch",
            config={"displayModeBar": False},
        )
    with right:
        st.plotly_chart(
            trend_figure(
                current, prior if yoy_enabled else pd.DataFrame(), "standard_gross_profit_1", "毛利额-1走势"
            ),
            width="stretch",
            config={"displayModeBar": False},
        )

    render_monthly_full_metrics(current, prior, yoy_enabled)

    st.markdown("#### 当前期间的主要构成")
    left, right = st.columns(2)
    with left:
        platform = aggregate_pnl(current, ["platform"])
        if not prior.empty:
            platform_comparison = build_metric_comparison(current, prior, ["platform"], "sales_amount")
            platform_figure = period_comparison_figure(
                platform_comparison,
                current,
                prior,
                ["platform"],
                "sales_amount",
                "各平台销售额同期对比",
            )
        else:
            platform_figure = bar_figure(platform, "platform", "sales_amount", "各平台销售额")
        st.plotly_chart(
            platform_figure,
            width="stretch",
            config={"displayModeBar": False},
        )
    with right:
        group = aggregate_pnl(current, ["group"])
        if not prior.empty:
            group_comparison = build_metric_comparison(
                current, prior, ["group"], "standard_gross_profit_1"
            )
            group_figure = period_comparison_figure(
                group_comparison,
                current,
                prior,
                ["group"],
                "standard_gross_profit_1",
                "各组别毛利额-1同期对比",
            )
        else:
            group_figure = bar_figure(
                group, "group", "standard_gross_profit_1", "各组别毛利额-1", COLORS["gold"]
            )
        st.plotly_chart(
            group_figure,
            width="stretch",
            config={"displayModeBar": False},
        )
    cost_top10_section(current, prior if yoy_enabled else pd.DataFrame())


def free_analysis_page(
    current: pd.DataFrame,
    history: pd.DataFrame,
    prior: pd.DataFrame,
    yoy_enabled: bool,
) -> None:
    st.markdown("## 自由分析")
    st.markdown("<p class='section-note'>选择分析维度、指标及汇总/月度展示方式；所有结果均按 SPU 归集，不显示 SKU/MSKU。</p>", unsafe_allow_html=True)
    label_to_dimension = {label: key for key, label in DIMENSION_LABELS.items() if key in ANALYSIS_DIMENSIONS}
    left, middle, right, mode_column, far_right = st.columns([1.1, 1.1, 1.1, 0.9, 0.75])
    with left:
        primary_label = st.selectbox("主分析维度", list(label_to_dimension), index=0)
    with middle:
        available_secondary = ["不拆分", *[label for label in label_to_dimension if label != primary_label]]
        secondary_label = st.selectbox("对比维度", available_secondary)
    with right:
        metric_label = st.selectbox("指标", list(METRIC_LABELS.values()), index=0)
    with mode_column:
        display_mode = st.segmented_control(
            "展示方式",
            options=["汇总", "月度"],
            default="汇总",
            key="free_analysis_display_mode",
        )
        display_mode = display_mode or "汇总"
    with far_right:
        top_options = [5, 10, 20, 50] if display_mode == "月度" else [10, 20, 50, 100]
        top_n = st.selectbox("展示数量", top_options, index=1)

    primary = label_to_dimension[primary_label]
    secondary = None if secondary_label == "不拆分" else label_to_dimension[secondary_label]
    metric = next(key for key, label in METRIC_LABELS.items() if label == metric_label)
    dimensions = [primary, *([secondary] if secondary else [])]
    if display_mode == "月度":
        view = build_monthly_metric_analysis(current, history, dimensions, metric, top_n)
    else:
        view = aggregate_pnl(current, dimensions).sort_values(metric, ascending=False).head(top_n)
    if view.empty:
        st.info("当前筛选条件下没有可展示的数据。")
        return

    if display_mode == "月度":
        fig = monthly_analysis_figure(
            view,
            dimensions,
            metric,
            f"按 {primary_label}{' / ' + secondary_label if secondary else ''} 查看 {metric_label}月度表现",
        )
        if view[dimensions].drop_duplicates().shape[0] > 10:
            st.caption("当前月度图超过 10 个分析对象；如标签较密，可将“展示数量”调整为 5 或 10。")
    else:
        if primary == "spu":
            fig = bar_figure(view, primary, metric, f"按 {primary_label} 查看 {metric_label}")
        elif secondary:
            metric_is_rate = metric in RATE_METRICS
            view["图表数值"] = view[metric].map(rate if metric_is_rate else amount)
            fig = px.bar(
                view,
                x=metric,
                y=primary,
                color=secondary,
                orientation="h",
                text="图表数值",
                labels={**DIMENSION_LABELS, **METRIC_LABELS, "图表数值": "数值"},
                color_discrete_sequence=[COLORS["blue"], COLORS["gold"], COLORS["orange"], COLORS["slate"]],
                barmode="group",
            )
            fig.update_layout(title={"text": f"按 {primary_label} / {secondary_label} 查看 {metric_label}", "font": {"size": 14}})
            fig.update_xaxes(tickformat=".0%" if metric_is_rate else ",.0f", title=metric_label)
            fig.update_yaxes(categoryorder="total ascending")
            value_format = ".2%" if metric_is_rate else ",.2f"
            fig.update_traces(
                textposition="outside",
                cliponaxis=False,
                hovertemplate=(
                    f"{primary_label}=%{{y}}<br>{secondary_label}=%{{fullData.name}}"
                    f"<br>{metric_label}=%{{x:{value_format}}}<extra></extra>"
                ),
            )
            fig = style_figure(fig, height=480, show_legend=True)
            fig.update_layout(margin={"l": 14, "r": 90, "t": 54, "b": 24})
        else:
            fig = bar_figure(view, primary, metric, f"按 {primary_label} 查看 {metric_label}")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    previous_column = f"{metric}_上月"
    mom_column = f"{metric_label}环比变化" if metric in RATE_METRICS else f"{metric_label}环比"
    table_columns = list(
        dict.fromkeys(
            [
                *(["period"] if display_mode == "月度" else []),
                *dimensions,
                metric,
                *([previous_column, mom_column] if display_mode == "月度" else []),
                "sales_amount",
                "standard_gross_profit_1",
                "gross_margin_1",
                "purchase_rate",
                "first_leg_rate",
                "tail_rate",
                "storage_cost",
                "storage_rate",
                "refund_rate",
                "ad_rate",
                "inventory_depreciation",
                "inventory_depreciation_rate",
            ]
        )
    )
    table_source = (
        view.sort_values(["period", metric], ascending=[False, False])
        if display_mode == "月度"
        else view
    )
    table = compact_table(table_source, table_columns, limit=500 if display_mode == "月度" else 100)
    st.dataframe(display_table(table), width="stretch", hide_index=True, height=430 if display_mode == "月度" else 380)
    if display_mode == "月度":
        st.caption("环比严格匹配上一个自然月；成本占比及毛利率以 pp 展示，金额指标以百分比展示。若上月无数据则显示为空。")
    export_table = compact_table(view, table_columns, limit=len(view))
    st.download_button(
        "导出当前自由分析结果（CSV）",
        data=chinese_headers(export_table).to_csv(index=False).encode("utf-8-sig"),
        file_name=f"spu_finance_free_analysis_{'monthly' if display_mode == '月度' else 'summary'}.csv",
        mime="text/csv",
    )
    if yoy_enabled and not prior.empty:
        render_yoy_comparison(
            current,
            prior,
            dimensions,
            metric,
            f"按 {primary_label}{' / ' + secondary_label if secondary else ''} 的{metric_label}同期对比"
            f"{'（所选期间汇总）' if display_mode == '月度' else ''}",
            top_n=top_n,
        )


def spu_page(
    current: pd.DataFrame,
    benchmark_population: pd.DataFrame,
    prior: pd.DataFrame,
    yoy_enabled: bool,
) -> None:
    st.markdown("## SPU 经营诊断")
    st.markdown("<p class='section-note'>费用率在 SPU 聚合后计算。子类目中位数按“平台 × 大类目 × 子类目”计算，样本仅使用销售额大于 0 的 SPU；子类目与平台中位数不受组别、负责人和单个 SPU 筛选影响。</p>", unsafe_allow_html=True)
    view = build_spu_benchmarks(current, benchmark_population)
    if view.empty:
        st.info("当前筛选条件下没有 SPU 数据。")
        return

    benchmark_options = {
        "采购成本占比": "purchase_rate",
        "头程费用占比": "first_leg_rate",
        "尾程费用占比": "tail_rate",
        "仓储成本占比": "storage_rate",
        "退款费用占比": "refund_rate",
        "广告费占比": "ad_rate",
        "库存折损占比": "inventory_depreciation_rate",
    }
    selected_label = st.selectbox("对标费用率", list(benchmark_options), key="spu_benchmark_metric")
    metric = benchmark_options[selected_label]
    view["子类目中位数差异"] = view[metric] - view[f"subcategory_median_{metric}"]

    left, right = st.columns([1.15, 1])
    with left:
        scatter = view.loc[view["sales_amount"] > 0].nlargest(300, "sales_amount")
        fig = px.scatter(
            scatter,
            x="sales_amount",
            y="gross_margin_1",
            color="grade",
            hover_name="spu",
            hover_data={"platform": True, "category": True, metric: ":.2%", "sales_amount": ":,.0f"},
            labels={**DIMENSION_LABELS, **METRIC_LABELS},
            color_discrete_sequence=[COLORS["blue"], COLORS["gold"], COLORS["orange"], COLORS["slate"], "#7761C7"],
        )
        fig.update_layout(title={"text": "销售额与毛利率-1分布", "font": {"size": 14}})
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(style_figure(fig, height=400, show_legend=True), width="stretch", config={"displayModeBar": False})
    with right:
        comparison = view.nlargest(12, "sales_amount").sort_values("子类目中位数差异")
        fig = px.bar(
            comparison,
            x="子类目中位数差异",
            y="spu",
            orientation="h",
            text=comparison["子类目中位数差异"].map(rate),
            labels={"spu": "SPU", "子类目中位数差异": "子类目中位数差异"},
            color_discrete_sequence=[COLORS["orange"]],
        )
        fig.update_layout(title={"text": f"Top SPU 的{selected_label}偏离子类目中位数", "font": {"size": 14}})
        fig.update_xaxes(tickformat=".1%", zeroline=True, zerolinecolor=COLORS["slate"])
        fig.update_traces(
            textposition="outside",
            cliponaxis=False,
            hovertemplate=f"SPU=%{{y}}<br>{selected_label}相对子类目偏差=%{{x:.2%}}<extra></extra>",
        )
        fig = style_figure(fig, height=400)
        fig.update_layout(margin={"l": 14, "r": 82, "t": 50, "b": 24})
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    display_columns = [
        "platform",
        "spu",
        "grade",
        "category",
        "subcategory",
        "sales_amount",
        "standard_gross_profit_1",
        "gross_margin_1",
        metric,
        f"subcategory_median_{metric}",
        f"platform_median_{metric}",
        "子类目中位数差异",
        "subcategory_spu_sample",
    ]
    table = view.loc[:, display_columns].sort_values("sales_amount", ascending=False).head(150)
    st.dataframe(display_table(table), width="stretch", hide_index=True, height=420)
    export_table = view.loc[:, display_columns].sort_values("sales_amount", ascending=False)
    st.download_button(
        "导出 SPU 诊断结果（CSV）",
        data=chinese_headers(export_table).to_csv(index=False).encode("utf-8-sig"),
        file_name="spu_finance_diagnosis.csv",
        mime="text/csv",
    )
    if yoy_enabled and not prior.empty:
        yoy_options = {
            "销售额": "sales_amount",
            "毛利额-1": "standard_gross_profit_1",
            "毛利率-1": "gross_margin_1",
            **benchmark_options,
        }
        selected_yoy_labels = st.multiselect(
            "SPU同期对比指标",
            list(yoy_options),
            default=["销售额"],
            key="spu_yoy_metrics",
            help="支持同时选择多个指标；金额同比以百分比展示，毛利率及成本占比变化以 pp 展示。",
        )
        if not selected_yoy_labels:
            st.info("请至少选择一个SPU同期对比指标。")
        else:
            st.markdown(
                "<p class='section-note'>每个指标独立展示Top20 SPU图表；所选字段在下方汇总明细表中分别展开本期、去年同期和同比变化。</p>",
                unsafe_allow_html=True,
            )
            for selected_yoy_label in selected_yoy_labels:
                render_yoy_comparison(
                    current,
                    prior,
                    ["spu"],
                    yoy_options[selected_yoy_label],
                    f"SPU {selected_yoy_label}同期对比",
                    top_n=20,
                    show_table=False,
                )
            render_multi_metric_yoy_detail(
                current,
                prior,
                ["spu"],
                [yoy_options[label] for label in selected_yoy_labels],
            )


def category_grade_page(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    year: int,
    yoy_enabled: bool,
) -> None:
    st.markdown("## 产品分级&类目")
    st.markdown(
        "<p class='section-note'>在产品分级、大类目和子类目之间切换；同步查看经营数据、同比表现及类目内的产品分级结构。</p>",
        unsafe_allow_html=True,
    )
    level_options = {"产品分级": "grade", "大类目": "category", "子类目": "subcategory"}
    selected_level = st.segmented_control(
        "分析层级",
        options=list(level_options),
        default="产品分级",
        key="category_grade_level",
    )
    selected_level = selected_level or "产品分级"
    dimension = level_options[selected_level]
    view = aggregate_pnl(current, [dimension])
    spu_count = (
        current.groupby(dimension, as_index=False)["spu"]
        .nunique()
        .rename(columns={"spu": "SPU数"})
    )
    view = view.merge(spu_count, on=dimension, how="left").sort_values("sales_amount", ascending=False)

    st.markdown(f"#### {selected_level or '产品分级'}经营表现")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            bar_figure(view.head(20), dimension, "sales_amount", f"各{selected_level}销售额", horizontal=dimension != "grade"),
            width="stretch",
            config={"displayModeBar": False},
        )
    with right:
        margin_view = view.loc[view["sales_amount"] > 0].head(20)
        st.plotly_chart(
            bar_figure(
                margin_view,
                dimension,
                "gross_margin_1",
                f"各{selected_level}毛利率-1",
                COLORS["gold"],
                horizontal=dimension != "grade",
            ),
            width="stretch",
            config={"displayModeBar": False},
        )

    table_columns = [
        dimension,
        "SPU数",
        "sales_amount",
        "standard_gross_profit_1",
        "gross_margin_1",
        "purchase_rate",
        "first_leg_rate",
        "tail_rate",
        "storage_cost",
        "storage_rate",
        "refund_rate",
        "ad_rate",
        "inventory_depreciation",
        "inventory_depreciation_rate",
    ]
    st.dataframe(display_table(view.loc[:, table_columns]), width="stretch", hide_index=True, height=360)

    if dimension in {"category", "subcategory"}:
        st.markdown("#### 类目销售占比")
        total_sales = view["sales_amount"].sum()
        share_view = view.copy()
        share_view["类目销售占比"] = (
            share_view["sales_amount"] / total_sales if total_sales != 0 else pd.NA
        )
        share_view = share_view.nlargest(20, "sales_amount").sort_values("类目销售占比")
        share_chart = px.bar(
            share_view,
            x="类目销售占比",
            y=dimension,
            orientation="h",
            text=share_view["类目销售占比"].map(rate),
            custom_data=["sales_amount"],
            labels={**DIMENSION_LABELS, "类目销售占比": "类目销售占比"},
            color_discrete_sequence=[COLORS["blue"]],
        )
        share_chart.update_xaxes(tickformat=".0%", title="类目销售占比")
        share_chart.update_yaxes(title=selected_level)
        share_chart.update_traces(
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                f"{selected_level}=%{{y}}<br>销售额=%{{customdata[0]:,.2f}}"
                "<br>类目销售占比=%{x:.2%}<extra></extra>"
            ),
        )
        share_chart.update_layout(
            title={"text": f"各{selected_level}销售额占总销售额比重", "font": {"size": 14}},
        )
        share_chart = style_figure(share_chart, height=max(360, min(620, 44 * len(share_view))))
        share_chart.update_layout(margin={"l": 14, "r": 82, "t": 50, "b": 24})
        st.plotly_chart(
            share_chart,
            width="stretch",
            config={"displayModeBar": False},
        )
        share_table = share_view[[dimension, "sales_amount", "类目销售占比"]].sort_values(
            "sales_amount", ascending=False
        )
        st.dataframe(display_table(share_table), width="stretch", hide_index=True, height=300)
        if len(view) > 20:
            st.caption(f"图表展示销售额最高的 20 个{selected_level}；占比仍以全部 {len(view)} 个{selected_level}的总销售额为分母。")

    st.markdown(f"#### {selected_level}同期对比")
    if year == 2026 and yoy_enabled and not prior.empty:
        category_yoy_options = {
            "销售额": "sales_amount",
            "毛利额-1": "standard_gross_profit_1",
            "毛利率-1": "gross_margin_1",
            "采购成本占比": "purchase_rate",
            "头程费用占比": "first_leg_rate",
            "尾程费用占比": "tail_rate",
            "仓储成本": "storage_cost",
            "仓储成本占比": "storage_rate",
            "退款费用占比": "refund_rate",
            "广告费占比": "ad_rate",
            "库存折损占比": "inventory_depreciation_rate",
        }
        selected_yoy_label = st.selectbox(
            "同期对比指标",
            list(category_yoy_options),
            key=f"category_yoy_metric_{dimension}",
        )
        render_yoy_comparison(
            current,
            prior,
            [dimension],
            category_yoy_options[selected_yoy_label],
            f"各{selected_level}{selected_yoy_label}同期对比",
            top_n=20,
        )
    else:
        st.info("选择 2026 年并开启“同时显示 2025 同期”后，可查看该层级同比。")

    st.markdown("#### 类目 × 产品分级")
    cross = aggregate_pnl(current, ["category", "grade"])
    cross_spu = (
        current.groupby(["category", "grade"], as_index=False)["spu"]
        .nunique()
        .rename(columns={"spu": "SPU数"})
    )
    cross = cross.merge(cross_spu, on=["category", "grade"], how="left")
    top_categories = aggregate_pnl(current, ["category"]).nlargest(12, "sales_amount")["category"]
    cross_chart = cross.loc[cross["category"].isin(top_categories)].copy()
    grade_order = [*GRADE_ORDER, *sorted(set(cross_chart["grade"]) - set(GRADE_ORDER))]
    cross_chart["grade"] = pd.Categorical(
        cross_chart["grade"], categories=grade_order, ordered=True
    )
    cross_chart = cross_chart.sort_values(["grade", "category"])
    cross_chart["图表数值"] = cross_chart["sales_amount"].map(amount)
    fig = px.bar(
        cross_chart,
        x="sales_amount",
        y="category",
        color="grade",
        orientation="h",
        text="图表数值",
        labels={**DIMENSION_LABELS, **METRIC_LABELS, "图表数值": "数值"},
        category_orders={"grade": grade_order},
        color_discrete_map=GRADE_COLORS,
        barmode="group",
    )
    fig.update_xaxes(title="销售额", tickformat=",.0f")
    fig.update_yaxes(title="大类目", categoryorder="total ascending")
    fig.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate="大类目=%{y}<br>产品分级=%{fullData.name}<br>销售额=%{x:,.2f}<extra></extra>",
    )
    fig.update_layout(title={"text": "重点类目的产品分级销售结构", "font": {"size": 14}})
    fig = style_figure(fig, height=520, show_legend=True)
    fig.update_layout(margin={"l": 14, "r": 86, "t": 50, "b": 24})
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    cross_columns = [
        "category",
        "grade",
        "SPU数",
        "sales_amount",
        "standard_gross_profit_1",
        "gross_margin_1",
        "purchase_rate",
        "tail_rate",
        "storage_cost",
        "storage_rate",
        "refund_rate",
        "ad_rate",
        "inventory_depreciation_rate",
    ]
    st.dataframe(
        display_table(cross.loc[:, cross_columns].sort_values("sales_amount", ascending=False)),
        width="stretch",
        hide_index=True,
        height=360,
    )


def definitions_page(data: pd.DataFrame) -> None:
    st.markdown("## 数据口径与导入状态")
    st.markdown(
        """
        <div class='data-status'>
        <b>产品粒度：</b>全部用户可见分析以 SPU 为准。SKU / MSKU 仅在后台用于导入、映射与审计，不在页面或导出中出现。<br>
        <b>毛利口径：</b>毛利额与毛利率均采用“毛利额-1”；毛利额-2仅保留在后台用于校验，不参与页面指标。<br>
        <b>库存折损：</b>取原表库存折损源值的成本符号（源值为负时转为正成本），并纳入成本金额和成本占比分析。<br>
        <b>仓储成本：</b>取原表“海外仓仓储费用”，沿用成本符号口径（源值为负时转为正成本）；正数冲减值保留为负成本。<br>
        <b>核心费用：</b>采购成本、头程费用、海外仓尾程费用及调整、仓储成本、退款费用、广告费用、库存折损。费用率分母均为销售额合计。<br>
        <b>同期对比：</b>选择 2026 年并开启“同时显示 2025 同期”后，对比数据会直接进入经营总览、自由分析、SPU诊断和产品分级&类目。<br>
        <b>月度与环比：</b>自由分析“月度”模式按自然月展示所选期间固定 TOP N；金额指标环比以百分比展示，成本占比及毛利率环比以 pp 展示；上月无数据时留空。<br>
        <b>中位数：</b>按平台独立计算；子类目中位数按“平台 × 大类目 × 子类目”，平台全品类中位数按“平台”；中位数样本仅使用销售额大于 0 的 SPU。
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("#### 数据源状态")
    status = source_status(data)
    st.dataframe(status, width="stretch", hide_index=True)
    st.caption("支持在左侧导入两年度原始经营报表；外链 XLOOKUP 按当前缓存结果读取为数值，2026 原表第 3 行汇总缓存不参与任何计算。")


def main() -> None:
    inject_css()
    source_2025, source_2026 = Path(DEFAULT_SOURCE_2025), Path(DEFAULT_SOURCE_2026)
    uploaded_2025, uploaded_2026 = source_uploaders()
    upload_bytes_2025 = uploaded_2025.getvalue() if uploaded_2025 is not None else None
    upload_bytes_2026 = uploaded_2026.getvalue() if uploaded_2026 is not None else None
    upload_name_2025 = uploaded_2025.name if uploaded_2025 is not None else None
    upload_name_2026 = uploaded_2026.name if uploaded_2026 is not None else None
    try:
        data = cached_load(
            DATA_MODEL_VERSION,
            str(source_2025),
            str(source_2026),
            current_mtime(source_2025),
            current_mtime(source_2026),
            upload_bytes_2025,
            upload_bytes_2026,
            upload_name_2025,
            upload_name_2026,
        )
    except FileNotFoundError as error:
        st.error(str(error))
        st.info("请在左侧上传缺失年度的原始经营报表，或配置服务器默认原表路径。")
        st.stop()
    except Exception as error:
        st.error(f"原表读取失败：{error}")
        st.info("请确认上传的是对应年度、沿用当前字段结构的 .xlsx 经营报表。")
        st.stop()

    selected_year, periods, filters, yoy_enabled = make_filters(data)
    filtered_history = apply_filters(data, filters)
    current_base = data.loc[data["period"].isin(periods)]
    current = apply_filters(current_base, filters)
    benchmark_filters = {"platform": filters["platform"], "store": filters["store"]}
    benchmark_population = apply_filters(current_base, benchmark_filters)

    prior = pd.DataFrame(columns=data.columns)
    if selected_year == 2026 and yoy_enabled:
        prior_base = data.loc[data["period"].isin(same_period_last_year(periods))]
        prior = apply_filters(prior_base, filters)
    scope = current_scope_text(periods, selected_year)

    st.markdown(
        f"""
        <div class="hero">
          <div class="eyebrow">FINANCE INTELLIGENCE · SPU ONLY</div>
          <h1>SPU 财务经营分析</h1>
          <p>以平台、组织、产品分级、大类目和子类目切换视角；当前分析区间：{scope}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pages = ["经营总览", "自由分析", "SPU 诊断", "产品分级&类目", "数据口径"]
    page = st.radio("页面", pages, horizontal=True, label_visibility="collapsed")
    if current.empty:
        st.warning("当前筛选条件没有可分析的经营数据，请调整侧栏条件。")
        return
    if page == "经营总览":
        overview_page(current, prior, selected_year, yoy_enabled, scope)
    elif page == "自由分析":
        free_analysis_page(current, filtered_history, prior, yoy_enabled)
    elif page == "SPU 诊断":
        spu_page(current, benchmark_population, prior, yoy_enabled)
    elif page == "产品分级&类目":
        category_grade_page(current, prior, selected_year, yoy_enabled)
    else:
        definitions_page(data)


if __name__ == "__main__":
    main()

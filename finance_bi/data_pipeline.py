"""Source loading and semantic calculations for the SPU finance dashboard.

The original workbooks remain untouched.  Formula cells are imported using their
last calculated values; the BI never depends on workbook external links.
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Iterable, Mapping, Sequence

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_2025 = Path(
    os.environ.get(
        "FINANCE_BI_2025_PATH",
        "/Users/shawnz/Documents/Amazon-zxh/财务报表分析原表/2025MSKU经营报表.xlsx",
    )
)
DEFAULT_SOURCE_2026 = Path(
    os.environ.get(
        "FINANCE_BI_2026_PATH",
        "/Users/shawnz/Documents/Amazon-zxh/财务报表分析原表/2026H1MSKU经营报表.xlsx",
    )
)


DIMENSION_LABELS = {
    "period": "月份",
    "platform": "平台",
    "store": "店铺",
    "group": "组别",
    "owner": "负责人",
    "grade": "产品分级",
    "category": "大类目",
    "subcategory": "子类目",
    "spu": "SPU",
}

PRODUCT_DIMENSIONS = ["grade", "category", "subcategory", "spu"]
ANALYSIS_DIMENSIONS = [
    "platform",
    "store",
    "group",
    "owner",
    "grade",
    "category",
    "subcategory",
    "spu",
]

METRIC_LABELS = {
    "sales_amount": "销售额",
    "standard_gross_profit_1": "毛利额-1",
    "gross_margin_1": "毛利率-1",
    "purchase_cost": "采购成本",
    "purchase_rate": "采购成本占比",
    "first_leg_cost": "头程费用",
    "first_leg_rate": "头程费用占比",
    "tail_cost": "尾程费用",
    "tail_rate": "尾程费用占比",
    "storage_cost": "仓储成本",
    "storage_rate": "仓储成本占比",
    "refund_cost": "退款费用",
    "refund_rate": "退款费用占比",
    "ad_cost": "广告费用",
    "ad_rate": "广告费占比",
    "inventory_depreciation": "库存折损",
    "inventory_depreciation_rate": "库存折损占比",
}

AMOUNT_METRICS = {
    "sales_amount",
    "standard_gross_profit_1",
    "standard_gross_profit_2",
    "purchase_cost",
    "first_leg_cost",
    "tail_cost",
    "storage_cost",
    "refund_cost",
    "ad_cost",
    "inventory_depreciation",
}
RATE_METRICS = {
    "gross_margin_1",
    "purchase_rate",
    "first_leg_rate",
    "tail_rate",
    "storage_rate",
    "refund_rate",
    "ad_rate",
    "inventory_depreciation_rate",
}

_NUMERIC_FIELDS = [
    "sales_amount",
    "platform_income",
    "platform_expense",
    "purchase_cost_raw",
    "first_leg_cost_raw",
    "tail_cost_raw",
    "storage_cost_raw",
    "refund_raw",
    "ad_raw",
    "gross_profit_1_raw",
    "inventory_loss_raw",
    "gross_profit_2_source_raw",
]


def _clean_text(series: pd.Series, fallback: str) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    return cleaned.fillna(fallback).replace({"": fallback, "nan": fallback, "<NA>": fallback})


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


Source = str | Path | bytes | BinaryIO


def _read_source(source: Source, year: int, source_name: str | None = None) -> pd.DataFrame:
    """Read cached workbook values and select the columns used by the dashboard."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"未找到数据源：{path}")
        excel_source: str | Path | BinaryIO = path
        display_name = source_name or path.name
    elif isinstance(source, bytes):
        excel_source = BytesIO(source)
        display_name = source_name or f"{year}年度上传文件.xlsx"
    else:
        source.seek(0)
        excel_source = source
        display_name = source_name or Path(getattr(source, "name", f"{year}年度上传文件.xlsx")).name

    raw = pd.read_excel(excel_source, sheet_name=0, header=1, engine="openpyxl")
    if raw.empty or raw.shape[1] == 0:
        raise ValueError(f"{display_name} 没有可读取的数据")
    month_number = pd.to_numeric(raw.iloc[:, 0], errors="coerce")
    data = raw.loc[month_number.between(year * 100 + 1, year * 100 + 12)].copy()
    month_number = month_number.loc[data.index].astype(int)
    if data.empty:
        raise ValueError(f"{display_name} 未找到 {year} 年月份明细，请检查上传年度与表头结构")

    # The 2026 source inserted SKU after MSKU and has two margin columns near
    # the end.  SKU/MSKU are deliberately not surfaced in the dashboard.
    if year == 2025:
        positions = {
            "spu": 2,
            "platform": 3,
            "store": 4,
            "grade": 5,
            "category": 6,
            "subcategory": 7,
            "group": 8,
            "owner": 9,
            "sales_amount": 10,
            "platform_income": 19,
            "platform_expense": 33,
            "purchase_cost_raw": 35,
            "first_leg_cost_raw": 36,
            "tail_base_raw": 40,
            "tail_adjustment_raw": 41,
            "storage_cost_raw": 43,  # 海外仓仓储费用
            "refund_raw": 18,
            "ad_raw": 23,
            "gross_profit_1_raw": 72,  # BU: user-confirmed 毛利润1
            "inventory_loss_raw": 73,  # BV
            "gross_profit_2_source_raw": 74,  # BW: retained only for audit
        }
    else:
        positions = {
            "spu": 3,
            "platform": 4,
            "store": 5,
            "grade": 6,
            "category": 7,
            "subcategory": 8,
            "group": 9,
            "owner": 10,
            "sales_amount": 11,
            "platform_income": 20,
            "platform_expense": 34,
            "purchase_cost_raw": 36,
            "first_leg_cost_raw": 37,
            "tail_base_raw": 41,
            "tail_adjustment_raw": 42,
            "storage_cost_raw": 44,  # 海外仓仓储费用
            "refund_raw": 19,
            "ad_raw": 24,
            "gross_profit_1_raw": 73,  # BV
            "inventory_loss_raw": 75,  # BX
            "gross_profit_2_source_raw": 76,  # BY: retained only for audit
        }

    required_width = max(positions.values()) + 1
    if raw.shape[1] < required_width:
        raise ValueError(
            f"{display_name} 字段列数不足：当前 {raw.shape[1]} 列，{year} 年模板至少需要 {required_width} 列"
        )
    storage_header = str(raw.columns[positions["storage_cost_raw"]]).strip()
    if storage_header != "海外仓仓储费用":
        raise ValueError(
            f"{display_name} 未在预期列找到“海外仓仓储费用”（当前为“{storage_header}”），请检查模板列结构"
        )

    result = pd.DataFrame(
        {
            "period": pd.to_datetime(month_number.astype(str) + "01", format="%Y%m%d"),
            "source_year": year,
            "spu": _clean_text(data.iloc[:, positions["spu"]], "待映射SPU"),
            "platform": _clean_text(data.iloc[:, positions["platform"]], "未归属平台"),
            "store": _clean_text(data.iloc[:, positions["store"]], "未归属店铺"),
            "grade": _clean_text(data.iloc[:, positions["grade"]], "未分级"),
            "category": _clean_text(data.iloc[:, positions["category"]], "未分类"),
            "subcategory": _clean_text(data.iloc[:, positions["subcategory"]], "未分类"),
            "group": _clean_text(data.iloc[:, positions["group"]], "未归属组别"),
            "owner": _clean_text(data.iloc[:, positions["owner"]], "未归属负责人"),
        }
    )
    for field in [
        "sales_amount",
        "platform_income",
        "platform_expense",
        "purchase_cost_raw",
        "first_leg_cost_raw",
        "storage_cost_raw",
        "refund_raw",
        "ad_raw",
        "gross_profit_1_raw",
        "inventory_loss_raw",
        "gross_profit_2_source_raw",
    ]:
        result[field] = _numeric(data.iloc[:, positions[field]])
    result["tail_cost_raw"] = _numeric(data.iloc[:, positions["tail_base_raw"]]) + _numeric(
        data.iloc[:, positions["tail_adjustment_raw"]]
    )
    result["source_file"] = display_name
    return result


def load_finance_data(
    source_2025: Source = DEFAULT_SOURCE_2025,
    source_2026: Source = DEFAULT_SOURCE_2026,
    source_name_2025: str | None = None,
    source_name_2026: str | None = None,
) -> pd.DataFrame:
    """Load both years into one raw-line fact table, using values not formulas."""
    frame = pd.concat(
        [
            _read_source(source_2025, 2025, source_name_2025),
            _read_source(source_2026, 2026, source_name_2026),
        ],
        ignore_index=True,
    )
    frame["period_label"] = frame["period"].dt.strftime("%Y-%m")
    return frame.sort_values(["period", "platform", "spu"], kind="stable").reset_index(drop=True)


def apply_filters(frame: pd.DataFrame, filters: Mapping[str, Sequence[str]]) -> pd.DataFrame:
    """Apply visible dashboard filters.  SKU/MSKU are intentionally absent."""
    filtered = frame
    for column, values in filters.items():
        if values:
            filtered = filtered.loc[filtered[column].isin(values)]
    return filtered.copy()


def available_dimension_values(
    frame: pd.DataFrame,
    column: str,
    upstream_filters: Mapping[str, Sequence[str]] | None = None,
) -> list[object]:
    """Return sorted filter choices after applying upstream cascade filters."""
    constrained = apply_filters(frame, upstream_filters or {})
    values = constrained[column].dropna().drop_duplicates().tolist()
    return sorted(values, key=lambda value: str(value))


def _safe_rate(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    rate = numerator.div(denominator.where(denominator > 0))
    return rate.replace([float("inf"), float("-inf")], pd.NA)


def calculate_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the canonical signs and the user-confirmed gross-profit formula."""
    result = frame.copy()
    result["standard_gross_profit_1"] = result["gross_profit_1_raw"]
    result["standard_gross_profit_2"] = (
        result["gross_profit_1_raw"] + result["inventory_loss_raw"]
    )
    result["purchase_cost"] = -result["purchase_cost_raw"]
    result["first_leg_cost"] = -result["first_leg_cost_raw"]
    result["tail_cost"] = -result["tail_cost_raw"]
    result["storage_cost"] = -result["storage_cost_raw"]
    result["refund_cost"] = -result["refund_raw"]
    result["ad_cost"] = -result["ad_raw"]
    result["inventory_depreciation"] = -result["inventory_loss_raw"]
    result["gross_margin_1"] = _safe_rate(
        result["standard_gross_profit_1"], result["sales_amount"]
    )
    result["gross_margin_2"] = _safe_rate(
        result["standard_gross_profit_2"], result["sales_amount"]
    )
    result["purchase_rate"] = _safe_rate(result["purchase_cost"], result["sales_amount"])
    result["first_leg_rate"] = _safe_rate(result["first_leg_cost"], result["sales_amount"])
    result["tail_rate"] = _safe_rate(result["tail_cost"], result["sales_amount"])
    result["storage_rate"] = _safe_rate(result["storage_cost"], result["sales_amount"])
    result["refund_rate"] = _safe_rate(result["refund_cost"], result["sales_amount"])
    result["ad_rate"] = _safe_rate(result["ad_cost"], result["sales_amount"])
    result["inventory_depreciation_rate"] = _safe_rate(
        result["inventory_depreciation"], result["sales_amount"]
    )
    return result


def aggregate_pnl(frame: pd.DataFrame, dimensions: Iterable[str]) -> pd.DataFrame:
    """Aggregate raw records, then calculate amounts and rates at the requested grain."""
    dimensions = list(dimensions)
    if frame.empty:
        return calculate_metrics(pd.DataFrame(columns=[*dimensions, *_NUMERIC_FIELDS]))

    if dimensions:
        aggregated = (
            frame.groupby(dimensions, as_index=False, dropna=False)[_NUMERIC_FIELDS].sum().copy()
        )
    else:
        aggregated = pd.DataFrame([frame[_NUMERIC_FIELDS].sum(numeric_only=True)])
    return calculate_metrics(aggregated)


def build_monthly_metric_analysis(
    current_frame: pd.DataFrame,
    history_frame: pd.DataFrame,
    dimensions: Iterable[str],
    metric: str,
    top_n: int,
) -> pd.DataFrame:
    """Return monthly detail for the selected-period Top N with exact-calendar MoM.

    Ranking is based on the selected period's aggregate, so every displayed month
    uses the same comparison set.  The prior value is joined from the immediately
    preceding calendar month; missing months are not silently skipped.
    """
    dimensions = list(dimensions)
    if current_frame.empty or not dimensions:
        return pd.DataFrame()

    ranking = aggregate_pnl(current_frame, dimensions).sort_values(metric, ascending=False)
    top_keys = ranking.loc[:, dimensions].head(top_n).drop_duplicates()
    current_monthly = aggregate_pnl(current_frame, ["period", *dimensions]).merge(
        top_keys,
        on=dimensions,
        how="inner",
    )
    if current_monthly.empty:
        return current_monthly

    history_monthly = aggregate_pnl(history_frame, ["period", *dimensions]).merge(
        top_keys,
        on=dimensions,
        how="inner",
    )
    previous_column = f"{metric}_上月"
    previous = history_monthly.loc[:, ["period", *dimensions, metric]].copy()
    previous["period"] = previous["period"] + pd.DateOffset(months=1)
    previous = previous.rename(columns={metric: previous_column})
    result = current_monthly.merge(previous, on=["period", *dimensions], how="left")

    metric_label = METRIC_LABELS.get(metric, metric)
    if metric in RATE_METRICS:
        change_column = f"{metric_label}环比变化"
        result[change_column] = result[metric] - result[previous_column]
    else:
        change_column = f"{metric_label}环比"
        denominator = result[previous_column].where(result[previous_column] != 0)
        result[change_column] = result[metric].div(denominator) - 1
    return result.sort_values(["period", *dimensions], kind="stable").reset_index(drop=True)


def build_overview_monthly_detail(
    current_frame: pd.DataFrame,
    prior_frame: pd.DataFrame,
    metric: str,
) -> pd.DataFrame:
    """Build one KPI's monthly values, MoM, and aligned prior-year comparison."""
    if current_frame.empty:
        return pd.DataFrame()

    current = aggregate_pnl(current_frame, ["period"])[["period", metric]].sort_values("period")
    previous_column = f"{metric}_上月"
    previous = current[["period", metric]].copy()
    previous["period"] = previous["period"] + pd.DateOffset(months=1)
    previous = previous.rename(columns={metric: previous_column})
    result = current.merge(previous, on="period", how="left")

    metric_label = METRIC_LABELS.get(metric, metric)
    if metric in RATE_METRICS:
        mom_column = f"{metric_label}环比变化"
        result[mom_column] = result[metric] - result[previous_column]
    else:
        mom_column = f"{metric_label}环比"
        mom_denominator = result[previous_column].where(result[previous_column] != 0)
        result[mom_column] = result[metric].div(mom_denominator) - 1

    if not prior_frame.empty:
        prior_column = f"{metric}_去年同期"
        prior = aggregate_pnl(prior_frame, ["period"])[["period", metric]].copy()
        prior["period"] = prior["period"] + pd.DateOffset(years=1)
        prior = prior.rename(columns={metric: prior_column})
        result = result.merge(prior, on="period", how="left")
        if metric in RATE_METRICS:
            yoy_column = f"{metric_label}同比变化"
            result[yoy_column] = result[metric] - result[prior_column]
        else:
            yoy_column = f"{metric_label}同比"
            yoy_denominator = result[prior_column].where(result[prior_column] != 0)
            result[yoy_column] = result[metric].div(yoy_denominator) - 1

    return result.sort_values("period", kind="stable").reset_index(drop=True)


def build_monthly_full_metrics(
    current_frame: pd.DataFrame,
    prior_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return one row per month and comparison period with every visible BI metric."""
    frames: list[pd.DataFrame] = []
    source_frames = [(current_frame, "本期", 0)]
    if prior_frame is not None and not prior_frame.empty:
        source_frames.append((prior_frame, "同期", 1))

    for source, period_type, series_order in source_frames:
        if source.empty:
            continue
        monthly = aggregate_pnl(source, ["period"])
        spu_counts = source.groupby("period", as_index=False)["spu"].nunique().rename(
            columns={"spu": "spu_count"}
        )
        monthly = monthly.merge(spu_counts, on="period", how="left")
        source_year = (
            int(source["source_year"].iloc[0])
            if "source_year" in source.columns
            else int(monthly["period"].dt.year.iloc[0])
        )
        monthly["comparison_period"] = f"{source_year} {period_type}"
        monthly["_month_order"] = monthly["period"].dt.month
        monthly["_series_order"] = series_order
        frames.append(monthly)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values(["_month_order", "_series_order"], kind="stable")
    columns = ["period", "comparison_period", "spu_count", *METRIC_LABELS]
    return result.loc[:, columns].reset_index(drop=True)


def build_multi_metric_yoy_comparison(
    current_frame: pd.DataFrame,
    prior_frame: pd.DataFrame,
    dimensions: Iterable[str],
    metrics: Iterable[str],
) -> pd.DataFrame:
    """Combine several current-vs-prior metrics into one detail table."""
    dimensions = list(dimensions)
    metrics = list(dict.fromkeys(metrics))
    if not dimensions or not metrics or (current_frame.empty and prior_frame.empty):
        return pd.DataFrame()

    current_keys = aggregate_pnl(current_frame, dimensions).loc[:, dimensions].drop_duplicates()
    prior_keys = aggregate_pnl(prior_frame, dimensions).loc[:, dimensions].drop_duplicates()
    result = current_keys.merge(prior_keys, on=dimensions, how="outer", indicator=True)
    result["状态"] = result["_merge"].map(
        {"both": "存量", "left_only": "新增", "right_only": "退出"}
    ).astype(object)
    result = result.drop(columns="_merge")

    for metric in metrics:
        current_column = f"{metric}_本期"
        prior_column = f"{metric}_去年同期"
        current_view = aggregate_pnl(current_frame, dimensions)[[*dimensions, metric]].rename(
            columns={metric: current_column}
        )
        prior_view = aggregate_pnl(prior_frame, dimensions)[[*dimensions, metric]].rename(
            columns={metric: prior_column}
        )
        comparison = current_view.merge(prior_view, on=dimensions, how="outer")
        comparison[[current_column, prior_column]] = comparison[
            [current_column, prior_column]
        ].fillna(0.0)
        metric_label = METRIC_LABELS.get(metric, metric)
        if metric in RATE_METRICS:
            change_column = f"{metric_label}同比变化"
            comparison[change_column] = comparison[current_column] - comparison[prior_column]
        else:
            change_column = f"{metric_label}同比"
            denominator = comparison[prior_column].where(comparison[prior_column] != 0)
            comparison[change_column] = comparison[current_column].div(denominator) - 1
        result = result.merge(
            comparison[[*dimensions, current_column, prior_column, change_column]],
            on=dimensions,
            how="left",
        )

    return result


def build_spu_benchmarks(selected_frame: pd.DataFrame, population_frame: pd.DataFrame) -> pd.DataFrame:
    """Attach same-platform subcategory and all-category median cost rates to SPUs.

    The selected data can be narrowed to a group or a searched SPU.  The benchmark
    population deliberately remains the full platform/store context, which prevents
    a small selected group from benchmarking against itself.
    """
    detail_dimensions = ["platform", "category", "subcategory", "grade", "spu"]
    selected = aggregate_pnl(selected_frame, detail_dimensions)
    population = aggregate_pnl(population_frame, detail_dimensions)
    population = population.loc[population["sales_amount"] > 0].copy()

    rate_columns = [
        "purchase_rate",
        "first_leg_rate",
        "tail_rate",
        "storage_rate",
        "refund_rate",
        "ad_rate",
        "inventory_depreciation_rate",
    ]
    subcategory_median = (
        population.groupby(["platform", "category", "subcategory"], as_index=False)[rate_columns]
        .median()
        .rename(columns={column: f"subcategory_median_{column}" for column in rate_columns})
    )
    platform_median = (
        population.groupby("platform", as_index=False)[rate_columns]
        .median()
        .rename(columns={column: f"platform_median_{column}" for column in rate_columns})
    )
    subcategory_sample_size = (
        population.groupby(["platform", "category", "subcategory"], as_index=False)["spu"]
        .nunique()
        .rename(columns={"spu": "subcategory_spu_sample"})
    )
    result = selected.merge(
        subcategory_median,
        on=["platform", "category", "subcategory"],
        how="left",
    )
    result = result.merge(platform_median, on="platform", how="left")
    result = result.merge(
        subcategory_sample_size,
        on=["platform", "category", "subcategory"],
        how="left",
    )
    return result


def same_period_last_year(periods: Sequence[pd.Timestamp]) -> list[pd.Timestamp]:
    return [period - pd.DateOffset(years=1) for period in periods]


def source_status(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby(["source_year", "source_file"], as_index=False)
        .agg(
            数据行数=("spu", "size"),
            期间起点=("period", "min"),
            期间终点=("period", "max"),
            待映射SPU行数=("spu", lambda s: (s == "待映射SPU").sum()),
        )
        .sort_values("source_year")
    )

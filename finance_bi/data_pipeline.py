"""Source loading and semantic calculations for the SPU finance dashboard.

The original workbooks remain untouched.  Formula cells are imported using their
last calculated values; the BI never depends on workbook external links.
"""

from __future__ import annotations

import os
import re
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Iterable, Mapping, Sequence

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_DATA_PATH = PROJECT_ROOT / "data" / "default_finance_data.csv.gz"
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
    "sales_per_active_spu": "品效-销售额",
    "gross_profit_per_active_spu": "品效-毛利额",
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
    "sales_per_active_spu",
    "gross_profit_per_active_spu",
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

# 已确认的美亚户外家具组别调整。仅在 2025 数据作为 2026 同期对比时
# 应用；未列出的名称保留原值，并在归因结果中明确标记为迁入/迁出。
GROUP_NAME_MAP_2025_TO_2026 = {
    "美国第一事业部美亚户外家具运营一部一组": "美国第一事业部美亚户外家具运营部一组",
    "美国第一事业部美亚户外家具运营一部二组": "美国第一事业部美亚户外家具运营部一组",
    "美国第一事业部美亚户外家具运营一部三组": "美国第一事业部美亚户外家具运营部一组",
    "美国第一事业部美亚户外家具运营二部一组": "美国第一事业部美亚户外家具运营部六组",
    "美国第一事业部美亚户外家具运营二部二组": "美国第一事业部美亚户外家具运营部二组",
    "美国第一事业部美亚户外家具运营二部三组": "美国第一事业部美亚户外家具运营部三组",
    "美国第一事业部美亚户外家具运营二部四组": "美国第一事业部美亚户外家具运营部四组",
    "美国第一事业部美亚户外家具运营二部五组": "美国第一事业部美亚户外家具运营部五组",
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


def _2026_profit_positions(headers: pd.DataFrame, display_name: str) -> dict[str, int]:
    """Recognize the two supported tails from labels, not workbook width.

    H1: BV profit 1, BW margin 1, BX inventory loss, BY profit 2.
    Jan-Aug: BV profit 1 (mislabeled profit 2), BW inventory loss, BX profit 2.
    The optional final margin column is not imported: rates are calculated below.
    """
    def label(position: int) -> str:
        if position >= headers.shape[1]:
            return ""
        # Vertically merged tail labels live in row 1; unmerged labels may be
        # in row 2. Prefer the more specific lower header when it is populated.
        for value in reversed(headers.iloc[:, position].tolist()):
            if pd.notna(value) and str(value).strip():
                return re.sub(r"[\s\-－—–]+", "", str(value))
        return ""

    if headers.shape[1] < 76:
        raise ValueError(f"{display_name} 字段列数不足：2026 年模板至少需要 76 列")
    tail = [label(position) for position in range(73, 77)]
    if tail[0] in {"毛利润1", "毛利润2"}:
        if tail[1:3] == ["库存损失", "毛利润2"]:
            return {
                "gross_profit_1_raw": 73,
                "inventory_loss_raw": 74,
                "gross_profit_2_source_raw": 75,
            }
        if tail[1:] == ["毛利率1", "库存损失", "毛利润2"]:
            return {
                "gross_profit_1_raw": 73,
                "inventory_loss_raw": 75,
                "gross_profit_2_source_raw": 76,
            }
    raise ValueError(
        f"{display_name} 无法识别 2026 年毛利/库存损失列结构："
        f"BV–BY 表头为 {tail}。支持 H1 含毛利率列结构，或 1–8 月不含毛利率列结构；"
        "请检查表头与列顺序，不要仅在末尾补空列。"
    )


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

    with pd.ExcelFile(excel_source, engine="openpyxl") as workbook:
        headers = pd.read_excel(workbook, sheet_name=0, header=None, nrows=2)
        raw = pd.read_excel(workbook, sheet_name=0, header=1)
    if raw.empty or raw.shape[1] == 0:
        raise ValueError(f"{display_name} 没有可读取的数据")
    month_number = pd.to_numeric(raw.iloc[:, 0], errors="coerce")
    data = raw.loc[month_number.between(year * 100 + 1, year * 100 + 12)].copy()
    month_number = month_number.loc[data.index].astype(int)
    if data.empty:
        raise ValueError(f"{display_name} 未找到 {year} 年月份明细，请检查上传年度与表头结构")

    # The 2026 source inserted SKU after MSKU. Its tail has variants with and
    # without margin columns. SKU/MSKU are not surfaced in the dashboard.
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
            **_2026_profit_positions(headers, display_name),
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


def _finalize_finance_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["period"] = pd.to_datetime(frame["period"], errors="raise")
    frame["source_year"] = pd.to_numeric(frame["source_year"], errors="raise").astype(int)
    for field in _NUMERIC_FIELDS:
        frame[field] = _numeric(frame[field])
    frame["period_label"] = frame["period"].dt.strftime("%Y-%m")
    return frame.sort_values(["period", "platform", "spu"], kind="stable").reset_index(drop=True)


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
    return _finalize_finance_frame(frame)


def load_bundled_finance_data(source: str | Path = BUNDLED_DATA_PATH) -> pd.DataFrame:
    """Load the deployment-safe normalized snapshot bundled with the application."""
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"未找到系统内置经营数据：{path}")
    text_columns = [
        "spu",
        "platform",
        "store",
        "grade",
        "category",
        "subcategory",
        "group",
        "owner",
        "source_file",
    ]
    frame = pd.read_csv(
        path,
        compression="infer",
        dtype={column: "string" for column in text_columns},
    )
    required_columns = {"period", "source_year", *text_columns, *_NUMERIC_FIELDS}
    missing_columns = sorted(required_columns - set(frame.columns))
    if missing_columns:
        raise ValueError(f"系统内置经营数据缺少字段：{', '.join(missing_columns)}")
    frame["source_file"] = frame["source_file"].map(
        lambda value: str(value) if str(value).endswith("（内置快照）") else f"{value}（内置快照）"
    )
    return _finalize_finance_frame(frame)


def load_finance_data_with_defaults(
    source_2025: Source | None = None,
    source_2026: Source | None = None,
    source_name_2025: str | None = None,
    source_name_2026: str | None = None,
    bundled_source: str | Path = BUNDLED_DATA_PATH,
    fallback_source_2025: Source = DEFAULT_SOURCE_2025,
    fallback_source_2026: Source = DEFAULT_SOURCE_2026,
) -> pd.DataFrame:
    """Use bundled yearly data by default and replace each year when a file is uploaded."""
    bundled_path = Path(bundled_source)
    bundled = (
        load_bundled_finance_data(bundled_path)
        if bundled_path.exists()
        else pd.DataFrame()
    )
    frames: list[pd.DataFrame] = []
    yearly_sources = [
        (2025, source_2025, source_name_2025, fallback_source_2025),
        (2026, source_2026, source_name_2026, fallback_source_2026),
    ]
    for year, uploaded_source, uploaded_name, fallback_source in yearly_sources:
        if uploaded_source is not None:
            frames.append(_read_source(uploaded_source, year, uploaded_name))
            continue
        bundled_year = bundled.loc[bundled["source_year"] == year].copy() if not bundled.empty else pd.DataFrame()
        if not bundled_year.empty:
            frames.append(bundled_year)
        else:
            frames.append(_read_source(fallback_source, year))
    return _finalize_finance_frame(pd.concat(frames, ignore_index=True))


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
        result = calculate_metrics(pd.DataFrame(columns=[*dimensions, *_NUMERIC_FIELDS]))
        result["有效SPU数"] = pd.Series(dtype="int64")
        result["sales_per_active_spu"] = pd.Series(dtype="float64")
        result["gross_profit_per_active_spu"] = pd.Series(dtype="float64")
        return result

    if dimensions:
        aggregated = (
            frame.groupby(dimensions, as_index=False, dropna=False)[_NUMERIC_FIELDS].sum().copy()
        )
    else:
        aggregated = pd.DataFrame([frame[_NUMERIC_FIELDS].sum(numeric_only=True)])
    result = calculate_metrics(aggregated)
    active_counts = active_spu_counts(frame, dimensions)
    if dimensions:
        result = result.merge(active_counts, on=dimensions, how="left")
    else:
        result["有效SPU数"] = active_counts.loc[0, "有效SPU数"]
    result["有效SPU数"] = result["有效SPU数"].fillna(0).astype(int)
    denominator = result["有效SPU数"].where(result["有效SPU数"] > 0)
    result["sales_per_active_spu"] = result["sales_amount"].div(denominator)
    result["gross_profit_per_active_spu"] = result["standard_gross_profit_1"].div(
        denominator
    )
    return result


def active_spu_counts(frame: pd.DataFrame, dimensions: Iterable[str]) -> pd.DataFrame:
    """Count unique SPUs with positive selected-period sales at the requested grain.

    This is the eligibility rule used by the SPU diagnostic median population.
    Keeping it in one helper prevents product-structure tables from counting
    zero-sales SPUs while diagnostic sample sizes exclude them.
    """
    dimensions = list(dimensions)
    columns = [*dimensions, "有效SPU数"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    if not dimensions:
        per_spu = frame.groupby("spu", as_index=False, dropna=False)["sales_amount"].sum()
        return pd.DataFrame(
            {"有效SPU数": [int(per_spu.loc[per_spu["sales_amount"] > 0, "spu"].nunique())]}
        )
    spu_dimensions = dimensions if "spu" in dimensions else [*dimensions, "spu"]
    per_spu = frame.groupby(spu_dimensions, as_index=False, dropna=False)["sales_amount"].sum()
    active = per_spu.loc[per_spu["sales_amount"] > 0]
    if active.empty:
        return pd.DataFrame(columns=columns)
    if "spu" in dimensions:
        result = active.loc[:, dimensions].drop_duplicates().copy()
        result["有效SPU数"] = 1
        return result
    return (
        active.groupby(dimensions, as_index=False, dropna=False)["spu"]
        .nunique()
        .rename(columns={"spu": "有效SPU数"})
    )


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
    columns = ["period", "comparison_period", "spu_count", "有效SPU数", *METRIC_LABELS]
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


def build_category_grade_breakdown(
    frame: pd.DataFrame,
    dimension: str,
    top_n: int = 12,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the full and top-N product-grade breakdown at the requested category grain."""
    if dimension not in {"category", "subcategory"}:
        raise ValueError("类目产品分级分析仅支持大类目或子类目维度")
    if frame.empty:
        empty = pd.DataFrame(columns=[dimension, "grade", "有效SPU数", *METRIC_LABELS])
        return empty, empty.copy()

    breakdown = aggregate_pnl(frame, [dimension, "grade"])

    ranked_dimensions = (
        aggregate_pnl(frame, [dimension])
        .sort_values("sales_amount", ascending=False, kind="stable")
        .head(max(int(top_n), 1))[dimension]
    )
    chart_breakdown = breakdown.loc[breakdown[dimension].isin(ranked_dimensions)].copy()
    return breakdown, chart_breakdown


def normalize_group_comparison(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply confirmed 2025-to-2026 group mappings before group-level filtering."""
    result = frame.copy()
    if "source_year" in result.columns:
        mask = result["source_year"].eq(2025)
        result.loc[mask, "group"] = result.loc[mask, "group"].replace(
            GROUP_NAME_MAP_2025_TO_2026
        )
    return result


def _validate_structure_dimension(dimension: str) -> None:
    if dimension not in {"platform", "group"}:
        raise ValueError("产品结构与SPU表现分析仅支持平台或组别维度")


def _dominant_grade_spu_profile(
    frame: pd.DataFrame, dimension: str | None = None
) -> pd.DataFrame:
    """Aggregate one SPU per slice and keep its sales-dominant grade.

    With no dimension, the function returns a de-duplicated all-scope SPU view;
    this is used for top-level cards so multi-platform SPUs are not counted twice.
    """
    if dimension is not None:
        _validate_structure_dimension(dimension)
    dimensions = [dimension] if dimension else []
    columns = [
        *dimensions,
        "spu",
        "grade",
        "sales_amount",
        "standard_gross_profit_1",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    totals = aggregate_pnl(frame, [*dimensions, "spu"])[
        [*dimensions, "spu", "sales_amount", "standard_gross_profit_1"]
    ]
    grade_sales = aggregate_pnl(frame, [*dimensions, "spu", "grade"])[
        [*dimensions, "spu", "grade", "sales_amount", "standard_gross_profit_1"]
    ]
    dominant_grade = grade_sales.sort_values(
        [*dimensions, "spu", "sales_amount", "standard_gross_profit_1"],
        ascending=[True] * (len(dimensions) + 1) + [False, False],
        kind="stable",
    ).drop_duplicates([*dimensions, "spu"], keep="first")
    return totals.merge(
        dominant_grade[[*dimensions, "spu", "grade"]], on=[*dimensions, "spu"], how="left"
    ).loc[:, columns]


def _c_series_snapshot(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    columns = [dimension, "SPU数", "销售额", "C系列SPU数", "C系列销售额"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    # Keep this aggregation identical to the product-grade detail table: a SPU
    # belongs to the C series when any raw record in the selected period is C+/C-/C--.
    # This deliberately differs from the SPU movement views, which require one
    # dominant grade per SPU to identify the current-product grade.
    overall = frame.groupby(dimension, as_index=False, dropna=False).agg(
        SPU数=("spu", "nunique"), 销售额=("sales_amount", "sum")
    )
    c_series = frame.loc[frame["grade"].astype("string").str.contains("C", na=False)]
    if c_series.empty:
        overall["C系列SPU数"] = 0.0
        overall["C系列销售额"] = 0.0
        return overall.loc[:, columns]
    c_summary = c_series.groupby(dimension, as_index=False, dropna=False).agg(
        C系列SPU数=("spu", "nunique"), C系列销售额=("sales_amount", "sum")
    )
    result = overall.merge(c_summary, on=dimension, how="left")
    result[["C系列SPU数", "C系列销售额"]] = result[
        ["C系列SPU数", "C系列销售额"]
    ].fillna(0.0)
    return result.loc[:, columns]


def build_c_series_structure(
    current_frame: pd.DataFrame, prior_frame: pd.DataFrame, dimension: str
) -> pd.DataFrame:
    """Compare C-series (C+, C-, C--) SPU and sales exposure by platform/group."""
    current = _c_series_snapshot(current_frame, dimension).rename(
        columns={column: f"本期{column}" for column in ["SPU数", "销售额", "C系列SPU数", "C系列销售额"]}
    )
    prior_source = normalize_group_comparison(prior_frame) if dimension == "group" else prior_frame
    prior = _c_series_snapshot(prior_source, dimension).rename(
        columns={column: f"去年同期{column}" for column in ["SPU数", "销售额", "C系列SPU数", "C系列销售额"]}
    )
    if current.empty and prior.empty:
        return pd.DataFrame(columns=[dimension])
    result = current.merge(prior, on=dimension, how="outer", indicator=True)
    result["同比可比状态"] = result.pop("_merge").map(
        {"both": "可比", "left_only": "新增/迁入", "right_only": "退出/迁出"}
    )
    for column in ["本期SPU数", "本期销售额", "本期C系列SPU数", "本期C系列销售额", "去年同期SPU数", "去年同期销售额", "去年同期C系列SPU数", "去年同期C系列销售额"]:
        if column not in result:
            result[column] = pd.NA
    result["本期C系列SPU占比"] = result["本期C系列SPU数"].div(
        result["本期SPU数"].where(result["本期SPU数"] != 0)
    )
    result["去年同期C系列SPU占比"] = result["去年同期C系列SPU数"].div(
        result["去年同期SPU数"].where(result["去年同期SPU数"] != 0)
    )
    result["本期C系列销售额占比"] = result["本期C系列销售额"].div(
        result["本期销售额"].where(result["本期销售额"] != 0)
    )
    result["去年同期C系列销售额占比"] = result["去年同期C系列销售额"].div(
        result["去年同期销售额"].where(result["去年同期销售额"] != 0)
    )
    result["C系列SPU数增减"] = result["本期C系列SPU数"] - result["去年同期C系列SPU数"]
    result["C系列SPU数同比"] = result["本期C系列SPU数"].div(
        result["去年同期C系列SPU数"].where(result["去年同期C系列SPU数"] != 0)
    ) - 1
    result["C系列销售额同比"] = result["本期C系列销售额"].div(
        result["去年同期C系列销售额"].where(result["去年同期C系列销售额"] != 0)
    ) - 1
    result["C系列SPU占比变化"] = result["本期C系列SPU占比"] - result["去年同期C系列SPU占比"]
    result["C系列销售额占比变化"] = result["本期C系列销售额占比"] - result[
        "去年同期C系列销售额占比"
    ]
    return result.sort_values("本期C系列销售额占比", ascending=False, kind="stable").reset_index(drop=True)


def _c_series_total_snapshot(frame: pd.DataFrame) -> dict[str, float]:
    c_series = frame.loc[frame["grade"].astype("string").str.contains("C", na=False)]
    return {
        "SPU数": float(frame["spu"].nunique()),
        "销售额": float(frame["sales_amount"].sum()),
        "C系列SPU数": float(c_series["spu"].nunique()),
        "C系列销售额": float(c_series["sales_amount"].sum()),
    }


def build_c_series_overview(current_frame: pd.DataFrame, prior_frame: pd.DataFrame) -> pd.DataFrame:
    """Return de-duplicated C-series headline metrics for the current filter scope."""
    current = _c_series_total_snapshot(current_frame)
    prior = _c_series_total_snapshot(prior_frame)
    result = pd.DataFrame(
        [
            {
                **{f"本期{key}": value for key, value in current.items()},
                **{f"去年同期{key}": value for key, value in prior.items()},
            }
        ]
    )
    result["本期C系列SPU占比"] = result["本期C系列SPU数"].div(
        result["本期SPU数"].where(result["本期SPU数"] != 0)
    )
    result["去年同期C系列SPU占比"] = result["去年同期C系列SPU数"].div(
        result["去年同期SPU数"].where(result["去年同期SPU数"] != 0)
    )
    result["本期C系列销售额占比"] = result["本期C系列销售额"].div(
        result["本期销售额"].where(result["本期销售额"] != 0)
    )
    result["去年同期C系列销售额占比"] = result["去年同期C系列销售额"].div(
        result["去年同期销售额"].where(result["去年同期销售额"] != 0)
    )
    result["C系列SPU数增减"] = result["本期C系列SPU数"] - result["去年同期C系列SPU数"]
    result["C系列SPU数同比"] = result["本期C系列SPU数"].div(
        result["去年同期C系列SPU数"].where(result["去年同期C系列SPU数"] != 0)
    ) - 1
    result["C系列销售额同比"] = result["本期C系列销售额"].div(
        result["去年同期C系列销售额"].where(result["去年同期C系列销售额"] != 0)
    ) - 1
    result["C系列SPU占比变化"] = result["本期C系列SPU占比"] - result["去年同期C系列SPU占比"]
    result["C系列销售额占比变化"] = result["本期C系列销售额占比"] - result[
        "去年同期C系列销售额占比"
    ]
    return result


def _spu_yoy_profile(
    current_frame: pd.DataFrame, prior_frame: pd.DataFrame, dimension: str
) -> pd.DataFrame:
    """Return comparable SPU-level sales and gross-profit changes at one slice."""
    _validate_structure_dimension(dimension)
    current = _dominant_grade_spu_profile(current_frame, dimension).rename(
        columns={
            "grade": "本期产品分级",
            "sales_amount": "本期销售额",
            "standard_gross_profit_1": "本期毛利额-1",
        }
    )
    prior_source = normalize_group_comparison(prior_frame) if dimension == "group" else prior_frame
    prior = _dominant_grade_spu_profile(prior_source, dimension).rename(
        columns={
            "grade": "去年同期产品分级",
            "sales_amount": "去年同期销售额",
            "standard_gross_profit_1": "去年同期毛利额-1",
        }
    )
    if current.empty and prior.empty:
        return pd.DataFrame(columns=[dimension, "spu"])
    result = current.merge(prior, on=[dimension, "spu"], how="outer", indicator=True)
    result["SPU状态"] = result.pop("_merge").map(
        {"both": "存量", "left_only": "新增/迁入", "right_only": "退出/迁出"}
    )
    result["销售额变动"] = result["本期销售额"].fillna(0.0) - result["去年同期销售额"].fillna(0.0)
    result["毛利额-1变动"] = result["本期毛利额-1"].fillna(0.0) - result[
        "去年同期毛利额-1"
    ].fillna(0.0)
    result["销售额同比"] = result["本期销售额"].div(
        result["去年同期销售额"].where(result["去年同期销售额"] != 0)
    ) - 1
    result["毛利额-1同比"] = result["本期毛利额-1"].div(
        result["去年同期毛利额-1"].where(result["去年同期毛利额-1"] != 0)
    ) - 1
    return result


def _summarize_spu_movement(detail: pd.DataFrame, dimension: str, label: str) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(
            columns=[
                dimension,
                f"{label}SPU数",
                "本期销售额",
                "去年同期销售额",
                "销售额变动",
                "销售额同比",
                "本期毛利额-1",
                "去年同期毛利额-1",
                "毛利额-1变动",
                "毛利额-1同比",
            ]
        )
    result = detail.groupby(dimension, as_index=False, dropna=False).agg(
        **{
            f"{label}SPU数": ("spu", "nunique"),
            "本期销售额": ("本期销售额", "sum"),
            "去年同期销售额": ("去年同期销售额", "sum"),
            "销售额变动": ("销售额变动", "sum"),
            "本期毛利额-1": ("本期毛利额-1", "sum"),
            "去年同期毛利额-1": ("去年同期毛利额-1", "sum"),
            "毛利额-1变动": ("毛利额-1变动", "sum"),
        }
    )
    result["销售额同比"] = result["本期销售额"].div(
        result["去年同期销售额"].where(result["去年同期销售额"] != 0)
    ) - 1
    result["毛利额-1同比"] = result["本期毛利额-1"].div(
        result["去年同期毛利额-1"].where(result["去年同期毛利额-1"] != 0)
    ) - 1
    return result


def build_deteriorated_spu_analysis(
    current_frame: pd.DataFrame, prior_frame: pd.DataFrame, dimension: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Find persistent current S/A/B SPUs whose sales and gross profit both declined."""
    profile = _spu_yoy_profile(current_frame, prior_frame, dimension)
    detail = profile.loc[
        profile["SPU状态"].eq("存量")
        & profile["本期产品分级"].isin({"S", "A", "B"})
        & profile["销售额变动"].lt(0)
        & profile["毛利额-1变动"].lt(0)
    ].copy()
    if detail.empty:
        return _summarize_spu_movement(detail, dimension, "表现变差"), detail
    detail["下降优先级"] = (
        detail["销售额变动"].abs().rank(method="min", ascending=False)
        + detail["毛利额-1变动"].abs().rank(method="min", ascending=False)
    )
    detail = detail.sort_values(
        ["下降优先级", "销售额变动", "毛利额-1变动"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)
    return _summarize_spu_movement(detail, dimension, "表现变差"), detail


def build_improved_spu_analysis(
    current_frame: pd.DataFrame,
    prior_frame: pd.DataFrame,
    dimension: str,
    top_n: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the Top-N persistent SPUs with positive absolute sales and profit growth."""
    profile = _spu_yoy_profile(current_frame, prior_frame, dimension)
    candidates = profile.loc[
        profile["SPU状态"].eq("存量")
        & profile["销售额变动"].gt(0)
        & profile["毛利额-1变动"].gt(0)
    ].copy()
    if candidates.empty:
        return _summarize_spu_movement(candidates, dimension, "表现变好"), candidates
    candidates["销售额增长排名"] = candidates["销售额变动"].rank(
        method="min", ascending=False
    )
    candidates["毛利额-1增长排名"] = candidates["毛利额-1变动"].rank(
        method="min", ascending=False
    )
    candidates["综合增长排名"] = (
        candidates["销售额增长排名"] + candidates["毛利额-1增长排名"]
    )
    top = candidates.sort_values(
        ["综合增长排名", "销售额变动", "毛利额-1变动"],
        ascending=[True, False, False],
        kind="stable",
    ).head(max(int(top_n), 1)).reset_index(drop=True)
    top["全局增长排名"] = range(1, len(top) + 1)
    summary = _summarize_spu_movement(candidates, dimension, "表现变好")
    top_summary = top.groupby(dimension, as_index=False, dropna=False).agg(
        **{
            "Top入选SPU数": ("spu", "nunique"),
            "Top销售额增长": ("销售额变动", "sum"),
            "Top毛利额-1增长": ("毛利额-1变动", "sum"),
        }
    )
    summary = summary.merge(top_summary, on=dimension, how="left")
    for column in ["Top入选SPU数", "Top销售额增长", "Top毛利额-1增长"]:
        summary[column] = pd.to_numeric(summary[column], errors="coerce").fillna(0.0)
    return summary.sort_values("销售额变动", ascending=False, kind="stable").reset_index(drop=True), top


def build_spu_benchmarks(selected_frame: pd.DataFrame, population_frame: pd.DataFrame) -> pd.DataFrame:
    """Attach same-platform subcategory and all-category median cost rates to SPUs.

    The selected data can be narrowed to a group or a searched SPU.  The benchmark
    population deliberately remains the full platform/store context, which prevents
    a small selected group from benchmarking against itself.
    """
    detail_dimensions = ["platform", "category", "subcategory", "grade", "spu"]
    selected = aggregate_pnl(selected_frame, detail_dimensions)
    total_sales = selected["sales_amount"].sum()
    total_profit = selected["standard_gross_profit_1"].sum()
    selected["sales_share_of_total_sales"] = selected["sales_amount"].div(
        total_sales if total_sales != 0 else float("nan")
    )
    selected["gross_profit_share_of_total_profit"] = selected[
        "standard_gross_profit_1"
    ].div(total_profit if total_profit != 0 else float("nan"))
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


def add_spu_benchmark_deltas(frame: pd.DataFrame, metrics: Sequence[str]) -> pd.DataFrame:
    """Add selected SPU cost-rate deviations from the two benchmark baselines.

    The result remains one row per SPU. Each selected cost rate receives its own
    subcategory and platform median deviation column, allowing the UI to place
    several cost-rate comparisons side by side in one diagnostic table.
    """
    result = frame.copy()
    for metric in metrics:
        subcategory_median = f"subcategory_median_{metric}"
        platform_median = f"platform_median_{metric}"
        if metric not in result or subcategory_median not in result or platform_median not in result:
            raise KeyError(f"SPU费用率对标缺少字段：{metric}")
        result[f"{metric}_subcategory_median_gap"] = result[metric] - result[subcategory_median]
        result[f"{metric}_platform_median_gap"] = result[metric] - result[platform_median]
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

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from finance_bi.data_pipeline import (
    METRIC_LABELS,
    active_spu_counts,
    aggregate_pnl,
    apply_filters,
    available_dimension_values,
    build_category_grade_breakdown,
    build_c_series_structure,
    build_c_series_overview,
    build_deteriorated_spu_analysis,
    build_improved_spu_analysis,
    build_monthly_metric_analysis,
    build_monthly_full_metrics,
    build_overview_monthly_detail,
    build_multi_metric_yoy_comparison,
    build_spu_benchmarks,
    add_spu_benchmark_deltas,
    load_finance_data_with_defaults,
    normalize_group_comparison,
)
from finance_bi.ui import chinese_headers, display_table


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "period": [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-01")],
            "platform": ["Amazon", "Amazon"],
            "store": ["US", "US"],
            "group": ["一组", "一组"],
            "owner": ["甲", "甲"],
            "grade": ["A", "A"],
            "category": ["户外", "户外"],
            "subcategory": ["椅子", "椅子"],
            "spu": ["SPU-1", "SPU-1"],
            "sales_amount": [100.0, 100.0],
            "platform_income": [100.0, 100.0],
            "platform_expense": [-10.0, -10.0],
            "purchase_cost_raw": [-30.0, -20.0],
            "first_leg_cost_raw": [-10.0, -10.0],
            "tail_cost_raw": [-8.0, -12.0],
            "storage_cost_raw": [-3.0, -5.0],
            "refund_raw": [-5.0, 0.0],
            "ad_raw": [-4.0, -6.0],
            "gross_profit_1_raw": [20.0, 10.0],
            "inventory_loss_raw": [-2.0, 3.0],
            "gross_profit_2_source_raw": [999.0, 999.0],
        }
    )


def test_standard_gross_profit_uses_confirmed_formula() -> None:
    result = aggregate_pnl(sample_frame(), ["spu"])
    assert result.loc[0, "standard_gross_profit_1"] == 30.0
    assert result.loc[0, "gross_margin_1"] == 0.15
    assert result.loc[0, "standard_gross_profit_2"] == 31.0
    assert result.loc[0, "inventory_depreciation"] == -1.0
    assert result.loc[0, "inventory_depreciation_rate"] == -0.005
    assert result.loc[0, "purchase_cost"] == 50.0
    assert result.loc[0, "purchase_rate"] == 0.25
    assert result.loc[0, "storage_cost"] == 8.0
    assert result.loc[0, "storage_rate"] == 0.04
    assert "standard_gross_profit_2" not in METRIC_LABELS


def test_product_efficiency_uses_positive_sales_spu_count() -> None:
    active = sample_frame().iloc[[0]].copy()
    active["spu"] = "SPU-ON"
    active["sales_amount"] = 100.0
    active["gross_profit_1_raw"] = 20.0
    inactive = active.copy()
    inactive["spu"] = "SPU-OFF"
    inactive["sales_amount"] = 0.0
    inactive["gross_profit_1_raw"] = 0.0

    result = aggregate_pnl(pd.concat([active, inactive], ignore_index=True), [])

    assert result.loc[0, "有效SPU数"] == 1
    assert result.loc[0, "sales_per_active_spu"] == 100.0
    assert result.loc[0, "gross_profit_per_active_spu"] == 20.0


def test_visible_filter_does_not_depend_on_sku_or_msku() -> None:
    filtered = apply_filters(sample_frame(), {"platform": ["Amazon"], "spu": ["SPU-1"]})
    assert len(filtered) == 2


def test_business_filter_options_follow_platform_group_owner_cascade() -> None:
    amazon = sample_frame().iloc[[0]].copy()
    amazon["platform"] = "Amazon"
    amazon["store"] = "Amazon-US"
    amazon["group"] = "一组"
    amazon["owner"] = "甲"

    walmart = amazon.copy()
    walmart["platform"] = "Walmart"
    walmart["store"] = "Walmart-US"
    walmart["group"] = "二组"
    walmart["owner"] = "乙"
    population = pd.concat([amazon, walmart], ignore_index=True)

    assert available_dimension_values(population, "group", {"platform": ["Amazon"]}) == ["一组"]
    assert available_dimension_values(
        population,
        "owner",
        {"platform": ["Amazon"], "group": ["一组"]},
    ) == ["甲"]
    assert available_dimension_values(population, "store", {"platform": ["Walmart"]}) == ["Walmart-US"]


def test_user_facing_columns_are_chinese() -> None:
    result = chinese_headers(aggregate_pnl(sample_frame(), ["spu", "platform"]))
    assert {"SPU", "平台", "销售额", "毛利额-1", "毛利率-1", "仓储成本", "库存折损"}.issubset(result.columns)


def test_table_rates_are_displayed_as_percentages() -> None:
    result = display_table(aggregate_pnl(sample_frame(), ["spu"]))
    assert result.loc[0, "毛利率-1"] == "15.00%"
    assert result.loc[0, "采购成本占比"] == "25.00%"
    assert result.loc[0, "仓储成本占比"] == "4.00%"
    assert result.loc[0, "库存折损占比"] == "-0.50%"


def test_spu_benchmarks_separate_subcategories() -> None:
    base = sample_frame().iloc[[0]].copy()
    rows = []
    for spu, subcategory, purchase_cost in [
        ("SPU-1", "椅子", -10.0),
        ("SPU-2", "椅子", -30.0),
        ("SPU-3", "桌子", -60.0),
        ("SPU-4", "桌子", -80.0),
    ]:
        row = base.copy()
        row["spu"] = spu
        row["subcategory"] = subcategory
        row["purchase_cost_raw"] = purchase_cost
        rows.append(row)
    population = pd.concat(rows, ignore_index=True)

    result = build_spu_benchmarks(population, population).set_index("spu")

    assert abs(result.loc["SPU-1", "subcategory_median_purchase_rate"] - 0.20) < 1e-12
    assert abs(result.loc["SPU-3", "subcategory_median_purchase_rate"] - 0.70) < 1e-12
    assert result.loc["SPU-1", "subcategory_spu_sample"] == 2
    assert result.loc["SPU-3", "subcategory_spu_sample"] == 2
    assert abs(result.loc["SPU-1", "sales_share_of_total_sales"] - 0.25) < 1e-12
    assert abs(result.loc["SPU-1", "gross_profit_share_of_total_sales"] - 0.05) < 1e-12
    result = add_spu_benchmark_deltas(
        result.reset_index(),
        ["purchase_rate", "first_leg_rate"],
    ).set_index("spu")
    assert abs(result.loc["SPU-1", "purchase_rate_subcategory_median_gap"] + 0.10) < 1e-12
    assert abs(result.loc["SPU-1", "purchase_rate_platform_median_gap"] + 0.35) < 1e-12
    displayed = display_table(result.reset_index())
    assert displayed.loc[0, "销售额占总销售额占比"] == "25.00%"
    assert displayed.loc[0, "毛利额-1占总销售额占比"] == "5.00%"
    spu_1_displayed = displayed.loc[displayed["SPU"].eq("SPU-1")].iloc[0]
    assert spu_1_displayed["子类目中位数差异（采购成本占比）"] == "-10.00pp"
    assert spu_1_displayed["平台全品类中位数差异（采购成本占比）"] == "-35.00pp"


def test_active_spu_counts_exclude_zero_sales_and_align_grade_breakdown() -> None:
    active_a = sample_frame().iloc[[0]].copy()
    active_a["spu"] = "SPU-A-ON"
    active_a["grade"] = "A"
    active_a["sales_amount"] = 100.0
    inactive_a = active_a.copy()
    inactive_a["spu"] = "SPU-A-OFF"
    inactive_a["sales_amount"] = 0.0
    active_c = active_a.copy()
    active_c["spu"] = "SPU-C-ON"
    active_c["grade"] = "C-"
    active_c["sales_amount"] = 50.0
    frame = pd.concat([active_a, inactive_a, active_c], ignore_index=True)

    counts = active_spu_counts(frame, ["grade"]).set_index("grade")
    breakdown, _ = build_category_grade_breakdown(frame, "category")

    assert counts.loc["A", "有效SPU数"] == 1
    assert counts.loc["C-", "有效SPU数"] == 1
    assert breakdown.loc[breakdown["grade"].eq("A"), "有效SPU数"].iloc[0] == 1
    assert breakdown.loc[breakdown["grade"].eq("C-"), "有效SPU数"].iloc[0] == 1


def test_monthly_analysis_uses_exact_previous_month_and_pp_for_rates() -> None:
    base = sample_frame().iloc[[0]].copy()
    january = base.copy()
    january["period"] = pd.Timestamp("2026-01-01")
    january["source_year"] = 2026
    january["purchase_cost_raw"] = -20.0
    february = base.copy()
    february["period"] = pd.Timestamp("2026-02-01")
    february["source_year"] = 2026
    february["purchase_cost_raw"] = -30.0
    history = pd.concat([january, february], ignore_index=True)

    rate_result = build_monthly_metric_analysis(
        february,
        history,
        ["spu"],
        "purchase_rate",
        10,
    )
    amount_result = build_monthly_metric_analysis(
        february,
        history,
        ["spu"],
        "purchase_cost",
        10,
    )

    assert abs(rate_result.loc[0, "purchase_rate_上月"] - 0.20) < 1e-12
    assert abs(rate_result.loc[0, "采购成本占比环比变化"] - 0.10) < 1e-12
    assert abs(amount_result.loc[0, "采购成本环比"] - 0.50) < 1e-12

    march = base.copy()
    march["period"] = pd.Timestamp("2026-03-01")
    march["source_year"] = 2026
    skipped_month = build_monthly_metric_analysis(
        march,
        pd.concat([january, march], ignore_index=True),
        ["spu"],
        "purchase_rate",
        10,
    )
    assert pd.isna(skipped_month.loc[0, "purchase_rate_上月"])
    assert pd.isna(skipped_month.loc[0, "采购成本占比环比变化"])


def test_monthly_change_fields_use_percentage_and_pp_display() -> None:
    displayed = display_table(
        pd.DataFrame(
            {
                "period": [pd.Timestamp("2026-02-01")],
                "采购成本环比": [0.25],
                "采购成本占比环比变化": [0.0123],
            }
        )
    )
    assert displayed.loc[0, "月份"] == "2026-02"
    assert displayed.loc[0, "采购成本环比"] == "+25.00%"
    assert displayed.loc[0, "采购成本占比环比变化"] == "+1.23pp"

    missing_display = display_table(
        pd.DataFrame({"sales_amount_上月": [pd.NA, 100.0]}),
        missing_as_dash=True,
    )
    assert missing_display["上月销售额"].tolist() == ["—", "100.0"]


def test_overview_monthly_detail_aligns_prior_year_and_uses_pp() -> None:
    base = sample_frame().iloc[[0]].copy()
    rows = []
    for period, year, purchase_cost in [
        ("2025-01-01", 2025, -15.0),
        ("2025-02-01", 2025, -25.0),
        ("2026-01-01", 2026, -20.0),
        ("2026-02-01", 2026, -30.0),
    ]:
        row = base.copy()
        row["period"] = pd.Timestamp(period)
        row["source_year"] = year
        row["purchase_cost_raw"] = purchase_cost
        rows.append(row)
    population = pd.concat(rows, ignore_index=True)

    current = population.loc[population["source_year"] == 2026]
    prior = population.loc[population["source_year"] == 2025]
    result = build_overview_monthly_detail(current, prior, "purchase_rate")

    assert result["period"].dt.strftime("%Y-%m").tolist() == ["2026-01", "2026-02"]
    assert abs(result.loc[1, "purchase_rate_上月"] - 0.20) < 1e-12
    assert abs(result.loc[1, "采购成本占比环比变化"] - 0.10) < 1e-12
    assert abs(result.loc[1, "purchase_rate_去年同期"] - 0.25) < 1e-12
    assert abs(result.loc[1, "采购成本占比同比变化"] - 0.05) < 1e-12


def test_monthly_full_metrics_contains_every_visible_metric_and_prior_rows() -> None:
    base = sample_frame().iloc[[0]].copy()
    current_january = base.copy()
    current_january["period"] = pd.Timestamp("2026-01-01")
    current_january["source_year"] = 2026
    current_february = current_january.copy()
    current_february["period"] = pd.Timestamp("2026-02-01")
    current_february["spu"] = "SPU-2"
    prior_january = base.copy()
    prior_january["period"] = pd.Timestamp("2025-01-01")
    prior_january["source_year"] = 2025

    result = build_monthly_full_metrics(
        pd.concat([current_january, current_february], ignore_index=True),
        prior_january,
    )

    assert set(METRIC_LABELS).issubset(result.columns)
    assert result["comparison_period"].tolist() == ["2026 本期", "2025 同期", "2026 本期"]
    assert result["period"].dt.strftime("%Y-%m").tolist() == ["2026-01", "2025-01", "2026-02"]
    assert result["spu_count"].tolist() == [1, 1, 1]


def test_multi_metric_yoy_comparison_uses_one_row_per_spu_and_shared_status() -> None:
    base = sample_frame().iloc[[0]].copy()
    current_stored = base.copy()
    current_stored["spu"] = "SPU-1"
    current_stored["sales_amount"] = 120.0
    current_stored["purchase_cost_raw"] = -30.0
    current_new = current_stored.copy()
    current_new["spu"] = "SPU-2"

    prior_stored = base.copy()
    prior_stored["spu"] = "SPU-1"
    prior_stored["sales_amount"] = 100.0
    prior_stored["purchase_cost_raw"] = -20.0
    prior_exited = prior_stored.copy()
    prior_exited["spu"] = "SPU-3"

    result = build_multi_metric_yoy_comparison(
        pd.concat([current_stored, current_new], ignore_index=True),
        pd.concat([prior_stored, prior_exited], ignore_index=True),
        ["spu"],
        ["sales_amount", "purchase_rate"],
    ).set_index("spu")

    assert result.index.tolist() == ["SPU-1", "SPU-2", "SPU-3"]
    assert result["状态"].to_dict() == {"SPU-1": "存量", "SPU-2": "新增", "SPU-3": "退出"}
    assert abs(result.loc["SPU-1", "销售额同比"] - 0.20) < 1e-12
    assert abs(result.loc["SPU-1", "采购成本占比同比变化"] - 0.05) < 1e-12


def test_category_grade_breakdown_respects_category_and_subcategory_grain() -> None:
    rows = []
    for spu, category, subcategory, grade, sales in [
        ("SPU-1", "户外", "餐桌", "A", 300.0),
        ("SPU-2", "户外", "摇椅", "B", 200.0),
        ("SPU-3", "室内", "餐椅", "A", 100.0),
    ]:
        row = sample_frame().iloc[[0]].copy()
        row["spu"] = spu
        row["category"] = category
        row["subcategory"] = subcategory
        row["grade"] = grade
        row["sales_amount"] = sales
        rows.append(row)
    frame = pd.concat(rows, ignore_index=True)

    category_breakdown, _ = build_category_grade_breakdown(frame, "category")
    subcategory_breakdown, top_subcategories = build_category_grade_breakdown(
        frame, "subcategory", top_n=2
    )

    assert set(category_breakdown["category"]) == {"户外", "室内"}
    assert set(subcategory_breakdown["subcategory"]) == {"餐桌", "摇椅", "餐椅"}
    assert set(top_subcategories["subcategory"]) == {"餐桌", "摇椅"}
    assert subcategory_breakdown.groupby("subcategory")["sales_amount"].sum().to_dict() == {
        "摇椅": 200.0,
        "餐椅": 100.0,
        "餐桌": 300.0,
    }


def test_bundled_data_is_default_and_uploaded_year_overrides_it() -> None:
    bundled_2025 = sample_frame().iloc[[0]].copy()
    bundled_2025["source_year"] = 2025
    bundled_2025["source_file"] = "2025.xlsx"
    bundled_2026 = bundled_2025.copy()
    bundled_2026["period"] = pd.Timestamp("2026-01-01")
    bundled_2026["source_year"] = 2026
    bundled_2026["source_file"] = "2026.xlsx"
    bundled_2026["spu"] = "SPU-BUNDLED-2026"
    bundled = pd.concat([bundled_2025, bundled_2026], ignore_index=True)

    uploaded_2025 = bundled_2025.copy()
    uploaded_2025["spu"] = "SPU-UPLOADED-2025"
    uploaded_2025["source_file"] = "uploaded-2025.xlsx"

    with TemporaryDirectory() as directory:
        bundled_path = Path(directory) / "default.csv.gz"
        bundled.to_csv(bundled_path, index=False, compression="gzip")
        with patch("finance_bi.data_pipeline._read_source", return_value=uploaded_2025):
            result = load_finance_data_with_defaults(
                source_2025=b"uploaded",
                source_name_2025="uploaded-2025.xlsx",
                bundled_source=bundled_path,
            )

    assert set(result.loc[result["source_year"] == 2025, "spu"]) == {"SPU-UPLOADED-2025"}
    assert set(result.loc[result["source_year"] == 2026, "spu"]) == {"SPU-BUNDLED-2026"}


def _movement_row(
    spu: str,
    grade: str,
    sales: float,
    gross_profit: float,
    platform: str = "Amazon",
    group: str = "一组",
) -> pd.DataFrame:
    row = sample_frame().iloc[[0]].copy()
    row["spu"] = spu
    row["grade"] = grade
    row["platform"] = platform
    row["group"] = group
    row["sales_amount"] = sales
    row["gross_profit_1_raw"] = gross_profit
    return row


def test_c_series_structure_compares_raw_grade_shares() -> None:
    current = pd.concat(
        [
            _movement_row("SPU-S", "S", 100.0, 20.0),
            _movement_row("SPU-C+", "C+", 40.0, 4.0),
            _movement_row("SPU-C-", "C-", 60.0, -6.0),
        ],
        ignore_index=True,
    )
    prior = pd.concat(
        [
            _movement_row("SPU-S", "S", 100.0, 20.0),
            _movement_row("SPU-C+", "C+", 20.0, 2.0),
        ],
        ignore_index=True,
    )

    result = build_c_series_structure(current, prior, "platform").iloc[0]
    overview = build_c_series_overview(current, prior).iloc[0]

    assert result["本期C系列SPU数"] == 2
    assert abs(result["本期C系列SPU占比"] - 2 / 3) < 1e-12
    assert abs(result["本期C系列销售额占比"] - 0.5) < 1e-12
    assert result["C系列SPU数增减"] == 1
    assert abs(result["C系列SPU数同比"] - 1.0) < 1e-12
    assert overview["本期C系列SPU数"] == 2
    assert abs(overview["本期C系列SPU占比"] - 2 / 3) < 1e-12
    assert abs(overview["C系列SPU数同比"] - 1.0) < 1e-12


def test_c_series_structure_matches_raw_grade_breakdown_for_changed_spu() -> None:
    current = pd.concat(
        [
            _movement_row("SPU-Changed", "C-", 10.0, -1.0),
            _movement_row("SPU-Changed", "A", 90.0, 9.0),
            _movement_row("SPU-S", "S", 100.0, 20.0),
        ],
        ignore_index=True,
    )
    prior = current.iloc[0:0].copy()

    result = build_c_series_structure(current, prior, "platform").iloc[0]
    overview = build_c_series_overview(current, prior).iloc[0]

    assert result["本期C系列SPU数"] == 1
    assert abs(result["本期C系列SPU占比"] - 0.5) < 1e-12
    assert overview["本期C系列SPU数"] == 1
    assert abs(overview["本期C系列SPU占比"] - 0.5) < 1e-12


def test_deteriorated_spu_analysis_only_keeps_current_s_a_b_double_declines() -> None:
    current = pd.concat(
        [
            _movement_row("SPU-A", "A", 80.0, 8.0),
            _movement_row("SPU-C", "C-", 50.0, -5.0),
            _movement_row("SPU-UP", "S", 120.0, 30.0),
        ],
        ignore_index=True,
    )
    prior = pd.concat(
        [
            _movement_row("SPU-A", "A", 100.0, 10.0),
            _movement_row("SPU-C", "C-", 70.0, -2.0),
            _movement_row("SPU-UP", "S", 100.0, 20.0),
        ],
        ignore_index=True,
    )

    summary, detail = build_deteriorated_spu_analysis(current, prior, "platform")

    assert detail["spu"].tolist() == ["SPU-A"]
    assert summary.loc[0, "表现变差SPU数"] == 1
    assert summary.loc[0, "销售额变动"] == -20.0
    assert summary.loc[0, "毛利额-1变动"] == -2.0


def test_improved_spu_analysis_summarizes_all_candidates_and_returns_ranked_top_n() -> None:
    current = pd.concat(
        [
            _movement_row("SPU-1", "A", 150.0, 30.0),
            _movement_row("SPU-2", "C-", 110.0, 100.0),
            _movement_row("SPU-3", "新品", 200.0, 40.0),
        ],
        ignore_index=True,
    )
    prior = pd.concat(
        [
            _movement_row("SPU-1", "A", 100.0, 20.0),
            _movement_row("SPU-2", "C-", 90.0, 70.0),
            _movement_row("SPU-3", "新品", 190.0, 35.0),
        ],
        ignore_index=True,
    )

    summary, top = build_improved_spu_analysis(current, prior, "platform", top_n=2)

    assert summary.loc[0, "表现变好SPU数"] == 3
    assert summary.loc[0, "Top入选SPU数"] == 2
    assert top["spu"].tolist() == ["SPU-1", "SPU-2"]
    assert top["本期产品分级"].tolist() == ["A", "C-"]


def test_confirmed_group_mapping_applies_before_prior_year_comparison() -> None:
    prior = _movement_row(
        "SPU-1",
        "A",
        100.0,
        20.0,
        group="美国第一事业部美亚户外家具运营一部二组",
    )
    prior["source_year"] = 2025

    mapped = normalize_group_comparison(prior)

    assert mapped.loc[0, "group"] == "美国第一事业部美亚户外家具运营部一组"


def test_c_series_share_change_is_displayed_in_pp() -> None:
    result = display_table(pd.DataFrame({"C系列销售额占比变化": [0.0123]}))

    assert result.loc[0, "C系列销售额占比变化"] == "+1.23pp"

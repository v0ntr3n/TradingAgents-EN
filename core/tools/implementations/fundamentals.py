from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['batch_profit_consistency', 'bond_tools', 'cashflow_enhancement', 'dividend_enhancement', 'etf_fundamentals', 'event_study', 'factor_bundle_tools', 'financial_tools', 'macro_cycle_tools', 'macro_tools', 'management_assessment', 'option_tools', 'screening.multi_factor_screening', 'screening.value_screening', 'standard_financial_tools', 'statistical_tools', 'stock_fundamentals', 'valuation.comparable_valuation', 'valuation.dcf_valuation', 'valuation.extended_valuation', 'valuation.wacc_calculator', 'valuation_excel_tool']:
    _sys.modules[f"{__name__}.{_sub}"] = _self_mod
    _top = _sub.split(".")[0]
    setattr(_self_mod, _top, _self_mod)

# === batch_profit_consistency ===
"""
Batch profit stability verification tool

once $in Query stock_financial_periods and calculate the stability of ROE / net profit in the past N years,
Avoid issuing N separate queries for each stock, greatly improving efficiency.
"""

import json
import logging
import math
from typing import Annotated, List, Dict, Any

from langchain_core.tools import tool
from core.tools.base import register_tool

logger = logging.getLogger(__name__)

MAX_DETAIL_PER_GROUP = 5


@tool
@register_tool(
    tool_id="batch_check_profit_consistency",
    name="批量验证盈利稳定性",
    description=(
        "Verify the stability of ROE/net profit of multiple stocks in the past N years in batches, and return the earnings stability assessment of all stocks in one query."
        "Input the stock code list (JSON array) and the number of years of testing, and return the stability conclusion (stable/unstable) of each stock,"
        "coefficient of variation (CV=Standard deviation/mean) and ROE data in the past N years."
        "It is used for secondary verification of profit quality of candidate stocks after batch screening, and the efficiency is much higher than stock-by-stock query."
    ),
    category="screening",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["profit_consistency", "batch_screening", "roe", "profitability", "stability", "screening", "earnings_quality"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["batch_profitability_screening", "earnings_stability_verification", "roe_consistency_check"],
    data_source_handling="local_only",
)
async def batch_check_profit_consistency(
    stock_codes_json: Annotated[
        str,
        'Stock code JSON array, such as ["000001", "600519", "000858"]',
    ],
    years: Annotated[int, "Number of years for inspection, default is 3 years (only annual report data is taken)"] = 3,
    threshold_cv: Annotated[
        float,
        "The coefficient of variation threshold. If it exceeds the threshold, it is determined to be unstable. The default is 0.3 (i.e. fluctuation > 30% of the mean)",
    ] = 0.3,
) -> str:
    """Verify the profitability stability of multiple stocks in the past N years in batches (once $in query, efficient)"""
    try:
        codes = json.loads(stock_codes_json)
        if not isinstance(codes, list) or len(codes) == 0:
            return "Error: stock_codes_json must be a non-empty JSON array."
        if len(codes) > 200:
            return "Error: A maximum of 200 stocks can be verified at a time, please submit in batches."
        years = max(2, min(years, 10))
    except json.JSONDecodeError as e:
        return f"Error: stock_codes_json is not in the correct format:{e}"

    return await _async_check(codes, years, threshold_cv)


def _build_annual_roe_pipeline(codes: List[str]) -> List[Dict[str, Any]]:
    return [
        {
            "$addFields": {
                "normalized_code": {"$ifNull": ["$code", "$symbol"]},
                "effective_roe": {
                    "$ifNull": [
                        "$financial_indicators.roe",
                        "$roe",
                    ]
                },
                "has_roe": {
                    "$cond": [
                        {
                            "$ne": [
                                {
                                    "$ifNull": [
                                        "$financial_indicators.roe",
                                        "$roe",
                                    ]
                                },
                                None,
                            ]
                        },
                        1,
                        0,
                    ]
                },
            }
        },
        {
            "$match": {
                "normalized_code": {"$in": codes},
                "report_type": "annual",
            }
        },
        {
            "$sort": {
                "normalized_code": 1,
                "report_period": -1,
                "has_roe": -1,
                "ann_date": -1,
                "updated_at": -1,
            }
        },
        {
            "$group": {
                "_id": {
                    "code": "$normalized_code",
                    "report_period": "$report_period",
                },
                "roe": {"$first": "$effective_roe"},
                "period": {"$first": "$report_period"},
            }
        },
        {"$match": {"roe": {"$ne": None}}},
        {"$sort": {"_id.code": 1, "period": -1}},
        {
            "$group": {
                "_id": "$_id.code",
                "roe_list": {"$push": "$roe"},
                "periods": {"$push": "$period"},
            }
        },
    ]


async def _async_check(
    codes: List[str],
    years: int,
    threshold_cv: float,
) -> str:
    from app.core.database import init_database, get_mongo_db

    try:
        await init_database()
    except Exception:
        pass

    db = get_mongo_db()
    collection = db["stock_financial_periods"]
    pipeline = _build_annual_roe_pipeline(codes)

    results_map: Dict[str, Any] = {}
    async for doc in collection.aggregate(pipeline):
        code = doc["_id"]
        all_roe = [v for v in doc.get("roe_list", []) if v is not None]
        all_periods = doc.get("periods", [])

        roe_values = all_roe[:years]
        periods_used = all_periods[:years]

        results_map[code] = {
            "roe_values": roe_values,
            "periods": periods_used,
        }

    return _format_results(codes, results_map, years, threshold_cv)


def _cv(values: List[float]) -> float:
    """coefficient of variation = Standard deviation / absolute value of the mean (to prevent division by zero if the mean is close to 0)"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if abs(mean) < 1e-9:
        return 999.0  # The mean value is close to 0, which is considered extremely unstable.
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    std = math.sqrt(variance)
    return std / abs(mean)


def _build_detail_line(
    code: str,
    roe_values: List[float],
    periods: List[str],
    cv_val: float,
    threshold_cv: float,
    all_positive: bool,
    is_stable: bool,
) -> str:
    actual_years = len(roe_values)
    roe_str = " / ".join(f"{v:.1f}%" for v in roe_values)
    periods_str = " / ".join(p[:4] for p in periods)

    if is_stable:
        return (
            f"  ✅ {code}：稳定 | CV={cv_val:.2f} | ROE连续为正=是"
            f" | near{actual_years}year ROE({periods_str}): {roe_str}"
        )

    reasons = []
    if cv_val > threshold_cv:
        reasons.append(f"CV={cv_val:.2f}>{threshold_cv:.0%}")
    if not all_positive:
        reasons.append("ROE含负值")
    reason_text = " / ".join(reasons) if reasons else "波动偏大"
    return (
        f"  ❌ {code}：不稳定 | {reason_text}"
        f" | near{actual_years}year ROE({periods_str}): {roe_str}"
    )


def _append_group_preview(lines: List[str], title: str, entries: List[str], total_count: int) -> None:
    if not entries:
        return
    lines.append(title)
    lines.extend(entries[:MAX_DETAIL_PER_GROUP])
    if total_count > len(entries[:MAX_DETAIL_PER_GROUP]):
        lines.append(f"  ... 其余 {total_count - len(entries[:MAX_DETAIL_PER_GROUP])} 只已省略详细展开")
    lines.append("")


def _format_results(
    codes: List[str],
    results_map: Dict[str, Any],
    years: int,
    threshold_cv: float,
) -> str:
    lines = [
        f"共验证 {len(codes)} 只股票近 {years} 年盈利稳定性（变异系数阈值 ≤ {threshold_cv:.0%}）。",
        "The results have been condensed into a summary summary; if you need to continue filtering, please use the code list below first.",
        "",
    ]

    stable_codes, volatile_codes, no_data_codes = [], [], []
    stable_details: List[str] = []
    volatile_details: List[str] = []

    for code in codes:
        data = results_map.get(code)
        if not data or len(data.get("roe_values", [])) < years:
            no_data_codes.append(code)
            continue

        roe_values = data["roe_values"]
        periods = data["periods"]
        cv_val = _cv(roe_values)
        all_positive = all(v > 0 for v in roe_values)

        # Determine stability: CV required ≤ threshold and ROE is continuously positive
        is_stable = (cv_val <= threshold_cv) and all_positive

        if is_stable:
            stable_codes.append(code)
            stable_details.append(
                _build_detail_line(
                    code, roe_values, periods, cv_val, threshold_cv, all_positive, is_stable=True
                )
            )
        else:
            volatile_codes.append(code)
            volatile_details.append(
                _build_detail_line(
                    code, roe_values, periods, cv_val, threshold_cv, all_positive, is_stable=False
                )
            )

    lines.append(f"📊 汇总：稳定 {len(stable_codes)} 只 | 不稳定 {len(volatile_codes)} 只 | 无数据 {len(no_data_codes)} 只")
    lines.append("")

    _append_group_preview(lines, "Stable example:", stable_details, len(stable_codes))
    _append_group_preview(lines, "Unstable example:", volatile_details, len(volatile_codes))

    if stable_codes:
        lines.append(f"✅ Stable stock code:{', '.join(stable_codes)}")
    if volatile_codes:
        lines.append(f"❌ Unstable stock code:{', '.join(volatile_codes)}")
    if no_data_codes:
        lines.append(f"⚪ No data stock code:{', '.join(no_data_codes)}")

    return "\n".join(lines)


# === bond_tools ===
"""Bond analysis tools: yield calculation, credit spread analysis, duration and convexity calculation."""

import datetime
import json
import logging
import math
from typing import Annotated, Optional, Any

import numpy as np
import pandas as pd
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)

_TENORS = ["3月", "6月", "1年", "3年", "5年", "7年", "10年", "30年"]


def _bond_tools_fetch_china_yield_curve() -> dict:
    """Get the latest data on China s government bond yield curve via AKShare."""
    try:
        import akshare as ak
        df = ak.bond_china_yield()
        treasury = df[df["曲线名称"] == "中债国债收益率曲线"]
        if treasury.empty:
            return {"status": "no_data", "message": "未找到国债收益率曲线数据"}
        treasury["日期"] = pd.to_datetime(treasury["日期"])
        latest = treasury.loc[treasury["日期"].idxmax()]
        yields = {}
        for col in _TENORS:
            val = latest.get(col)
            if val is not None and val == val:
                yields[col] = round(float(val), 4)
            else:
                yields[col] = None
        return {
            "status": "ok",
            "date": str(latest["日期"].date()),
            "yields": yields,
        }
    except Exception as e:
        logger.warning("AKShare Failed to obtain treasury bond yield: %s", e)
        return {"status": "error", "message": str(e)}


def _fetch_china_multi_curve() -> dict:
    """Obtain multiple yield curves (treasury bonds, AAA short-term and medium-term notes, AAA bank ordinary bonds) through AKShare."""
    try:
        import akshare as ak
        df = ak.bond_china_yield()
        df["日期"] = pd.to_datetime(df["日期"])
        curves_found = {}
        latest_dates = {}
        for curve_name in [
            "中债国债收益率曲线",
            "ChinaBond short- and medium-term bill yield curve(AAA)",
            "ChinaBond Commercial Bank ordinary bond yield curve(AAA)",
        ]:
            subset = df[df["曲线名称"] == curve_name]
            if subset.empty:
                curves_found[curve_name] = {"status": "no_data"}
                continue
            latest = subset.loc[subset["日期"].idxmax()]
            latest_dates[curve_name] = str(latest["日期"].date())
            yields = {}
            for col in _TENORS:
                val = latest.get(col)
                if val is not None and val == val:
                    yields[col] = round(float(val), 4)
                else:
                    yields[col] = None
            curves_found[curve_name] = {
                "status": "ok",
                "date": str(latest["日期"].date()),
                "yields": yields,
            }
        # Overall latest date
        all_dates = set(v["date"] for v in curves_found.values() if v.get("status") == "ok" and v.get("date"))
        return {
            "status": "ok",
            "date": max(all_dates) if all_dates else None,
            "curves": curves_found,
        }
    except Exception as e:
        logger.warning("AKShare Failed to obtain multiple curves: %s", e)
        return {"status": "error", "message": str(e)}


def _bond_tools_fetch_zh_us_rate() -> dict:
    """Get the latest data comparing U.S. and Chinese yields with AKShare."""
    try:
        import akshare as ak
        df = ak.bond_zh_us_rate()
        df["日期"] = pd.to_datetime(df["日期"])
        latest = df.sort_values("日期").iloc[-1]
        result = {
            "date": str(latest["日期"].date()),
            "china": {},
            "us": {},
        }
        cn_cols = {"中国国债收益率2年": "2年", "中国国债收益率5年": "5年",
                    "中国国债收益率10年": "10年", "中国国债收益率30年": "30年"}
        us_cols = {"美国国债收益率2年": "2年", "美国国债收益率5年": "5年",
                    "美国国债收益率10年": "10年", "美国国债收益率30年": "30年"}
        for raw, name in cn_cols.items():
            v = latest.get(raw)
            if v is not None and v == v:
                result["china"][name] = round(float(v), 4)
        for raw, name in us_cols.items():
            v = latest.get(raw)
            if v is not None and v == v:
                result["us"][name] = round(float(v), 4)
        return result
    except Exception as e:
        logger.warning("AKShare Failed to obtain Sino-US yield: %s", e)
        return {"status": "error", "message": str(e)}


def _classify_curve_shape(yields: dict) -> str:
    """Determine the shape of the curve based on yield data."""
    y1 = yields.get("1年")
    y10 = yields.get("10年")
    y3m = yields.get("3月")
    if y10 is not None and y1 is not None:
        if y10 > y1 + 0.5:
            return "Normal Upward Sloping"
        elif y10 < y1 - 0.1:
            return "倒挂（Inverted）"
        else:
            return "平坦（Flat）"
    if y10 is not None and y3m is not None:
        if y10 > y3m + 0.5:
            return "Normal Upward Sloping"
        elif y10 < y3m - 0.1:
            return "倒挂（Inverted）"
        else:
            return "平坦（Flat）"
    return "数据不足无法判断"


def _generate_yield_commentary(yields: dict, date: str) -> str:
    """Generate yield level comments."""
    y10 = yields.get("10年")
    y2 = yields.get("1年")
    if y10 is None:
        return "There is insufficient yield data to generate an interpretation."
    parts = [f"截至 {date}，中国10年期国债收益率为 {y10}%。"]
    if y10 < 1.5:
        parts.append("10Y Yields are at historically low levels, reflecting the market s cautious outlook on the economy and expectations of loose money.")
    elif y10 < 2.5:
        parts.append("10Y Yields are on the low side, bonds are priced on the expensive side, and the scope for capital gains is limited.")
    elif y10 < 3.5:
        parts.append("10Y Yields are in a moderate to low range, and bond valuations are neutral to expensive.")
    elif y10 < 4.5:
        parts.append("10Y The yield is in a medium to high range, and the allocation value is gradually emerging.")
    else:
        parts.append("10Y The yield is in a high range, and bonds have good allocation value.")
    if y2 is not None and y10 is not None:
        spread = y10 - y2
        if spread > 1.0:
            parts.append(f"The term spread (10Y-1Y) is {spread:.2f}%, The curve is steep and the risk premium is higher at the long end.")
        elif spread > 0.3:
            parts.append(f"The term spread (10Y-1Y) is {spread:.2f}%, The curve shape is normal.")
        elif spread > 0:
            parts.append(f"The term spread (10Y-1Y) is {spread:.2f}%, Curve flattening.")
        else:
            parts.append(f"The term spread (10Y-1Y) is {spread:.2f}%, The curve is inverted, and we need to pay attention to the risk of recession.")
    return " ".join(parts)


def _generate_spread_commentary(spreads: dict, date: str) -> str:
    """Generate credit spread reviews."""
    if not spreads:
        return "There is insufficient credit spread data to generate an interpretation."
    parts = [f"截至 {date}，信用利差分析如下："]
    avg_spreads = [v for v in spreads.values() if v is not None]
    if avg_spreads:
        avg = sum(avg_spreads) / len(avg_spreads)
        if avg > 2.0:
            parts.append(
                f"平均信用利差约 {avg:.2f}%，处于偏高水平，"
                "Reflecting lower market risk appetite or tight credit environment."
            )
        elif avg > 1.0:
            parts.append(
                f"平均信用利差约 {avg:.2f}%，处于中等水平，"
                "Credit pricing is reasonable and market risk appetite is neutral."
            )
        else:
            parts.append(
                f"平均信用利差约 {avg:.2f}%，处于偏低水平，"
                "Reflecting higher market risk appetite or ample liquidity."
            )
    # Term structure judgment
    short_tenors = ["1年", "3年"]
    long_tenors = ["5年", "7年", "10年"]
    short_vals = [spreads.get(t) for t in short_tenors if spreads.get(t) is not None]
    long_vals = [spreads.get(t) for t in long_tenors if spreads.get(t) is not None]
    if short_vals and long_vals:
        short_avg = sum(short_vals) / len(short_vals)
        long_avg = sum(long_vals) / len(long_vals)
        if long_avg > short_avg + 0.3:
            parts.append("The term structure of credit spreads is upward sloping, and the long-term credit risk premium is significant.")
        elif long_avg < short_avg - 0.2:
            parts.append("The term structure of credit spreads is inverted, and short-term credit risk premiums are higher.")
        else:
            parts.append("The term structure of credit spreads is flat.")
    return " ".join(parts)


def _calculate_duration_convexity(
    coupon_rate: float,
    years_to_maturity: float,
    yield_to_maturity: float,
    frequency: int,
) -> dict:
    """Calculate Macaulay duration, modified duration, and convexity.

    Args:
        coupon_rate: Coupon interest rate (in decimal form, such as 0.03 means 3%)
        years_to_maturity: Remaining term (years)
        yield_to_maturity: Yield to maturity (in decimal form, such as 0.03 means 3%)
        frequency: Annual interest payment frequency (1=Annual payment, 2=Paid half yearly)

    Returns:
        contains macaulay_duration, modified_duration, convexity, price, cash_flows dictionary
    """
    face_value = 100.0
    coupon = coupon_rate * face_value / frequency
    n_periods = int(years_to_maturity * frequency)
    ytm_per_period = yield_to_maturity / frequency

    # Calculate cash flow for each period
    cf_times = []
    cf_amounts = []
    for i in range(1, n_periods + 1):
        t = i  # Period
        if i == n_periods:
            cf = coupon + face_value  # The last period includes the principal
        else:
            cf = coupon
        cf_times.append(t)
        cf_amounts.append(cf)

    # Calculate present value
    pv_factors = [cf / ((1 + ytm_per_period) ** t) for t, cf in zip(cf_times, cf_amounts)]
    price = sum(pv_factors)

    if price <= 0:
        return {"error": "Bond price is negative or zero, duration and convexity cannot be calculated"}

    # Macaulay Duration (Unit: number of periods)
    macaulay_periods = sum(t * pv for t, pv in zip(cf_times, pv_factors)) / price
    # Macaulay Duration (Unit: year)
    macaulay_duration_years = macaulay_periods / frequency

    # Modified Duration
    modified_duration = macaulay_duration_years / (1 + ytm_per_period)

    # Convexity
    # Convexity = Σ [t * (t + 1/frequency) * PV_CF_t] / (Price * (1 + ytm/f)^2)
    # where t is the period and frequency is the number of annual interest payments.
    convexity_numerator = sum(
        t * (t + 1.0 / frequency) * pv
        for t, pv in zip(cf_times, pv_factors)
    )
    convexity = convexity_numerator / (price * (1 + ytm_per_period) ** 2)

    # Estimates of price changes (rising yields 1% = 100bp = 0.01) 
    delta_y = 0.01
    price_change_pct = -modified_duration * delta_y + 0.5 * convexity * (delta_y ** 2)

    # Generate cash flow details
    cash_flow_details = []
    for i, (t, cf, pv) in enumerate(zip(cf_times, cf_amounts, pv_factors)):
        cash_flow_details.append({
            "period": i + 1,
            "year": round(t / frequency, 4),
            "cash_flow": round(cf, 4),
            "present_value": round(pv, 4),
        })

    return {
        "price": round(price, 4),
        "macaulay_duration_years": round(macaulay_duration_years, 4),
        "modified_duration": round(modified_duration, 4),
        "convexity": round(convexity, 6),
        "price_change_1pct": {
            "yield_increase_1pct": round(price_change_pct * 100, 4),
            "explanation": "The approximate percentage change in bond prices when yields rise by 1 percentage point (100bp)",
        },
        "cash_flows_summary": {
            "total_periods": n_periods,
            "total_coupon_payments": round(coupon * (n_periods - 1) + (coupon + face_value) if n_periods > 0 else 0, 4),
            "face_value": face_value,
        },
    }


# ── Tool 1: bond yield calculation ─────────────────────────────────────────

@tool
@register_tool(
    tool_id="get_bond_yield_calculation",
    name="国债收益率曲线",
    description=(
        "Obtain real-time data on China s government bond yield curve and U.S. government bond yield through akshare."
        "Returns the market rate of return rather than individual bond YTM."
        "The difference from get_yield_curve_analysis: This tool focuses on comparison between China and the United States and analysis of income levels."
        "get_yield_curve_analysis Focus on curve shape and spread analysis."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["bond", "yield_curve", "interest_rate", "macro"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["查询中国国债各期限收益率", "中美收益率曲线对比", "收益率水平市场解读"],
    when_to_use=(
        "When a user asks about the current bond market yield level, Treasury bond yields of various maturities,"
        "Used when comparing the yield curves of China and the United States, judging the shape of the yield curve, and interpreting market implications."
    ),
    when_not_to_use=(
        "Not suitable for calculating the yield to maturity (YTM) of a single bond;"
        "Not suitable for bond duration and convexity calculations (please use get_bond_duration_convexity);"
        "Not suitable for credit spread analysis (use get_credit_spread_analysis)."
    ),
    returns=(
        "Returns a JSON string, including date (data date), yields_by_tenor (yield table for each term),"
        "yield_curve_shape_china (China curve shape), yield_curve_shape_us (US curve shape),"
        "commentary_with_key_levels (market interpretation)."
    ),
    example="get_bond_yield_calculation()",
    related_tools=["get_yield_curve_analysis", "get_credit_spread_analysis", "get_bond_duration_convexity"],
)
def get_bond_yield_calculation() -> str:
    """Get a comparison of the Chinese government bond yield curve and the U.S. Treasury bond yield, and provide market interpretation.

    Using AKShare bond_china_yield() and bond_zh_us_rate() interface,
    Return to the latest yield and curve shape judgment for each period.

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            date: Data date (YYYY-MM-DD)
            data_source: Data source description
            data_note: Data annotation (emphasis on returning the spot yield curve rather than individual bond YTM)
            yields_by_tenor: list[dict] Yield table for each term, element structure——
                — tenor: deadline (e.g. "1 year", "10 year") 
                — china_yield_pct: China s government bond yield of this term (%)
            yield_curve_shape_china: Determining the shape of China s yield curve
            yield_curve_shape_us: Determining the shape of the U.S. yield curve
            china_us_comparison: dict Comparison of interest rate spreads between China and the United States (when data are not available) {"status": "unavailable"}) ——
                — china_10y: China 10-year yield
                — us_10y: US 10-year yield
                — china_2y: China s 2-year yield (actually 1 year)
                — us_2y: U.S. 2-year yield
                — cn_us_10y_spread: China-US 10-year interest rate spread (percentage points)
            commentary_with_key_levels: Market interpretation text (including key levels)
            message: Error message (only status="error" exist)
            suggestion: Suggestions (only some error scenarios exist)
    """
    try:
        curve = _bond_tools_fetch_china_yield_curve()
        zh_us = _bond_tools_fetch_zh_us_rate()

        if curve.get("status") == "error":
            return json.dumps({
                "status": "error",
                "message": f"国债收益率数据获取失败: {curve.get('message')}",
                "suggestion": "Passable akshare.bond_china_yield() Get it directly",
            }, ensure_ascii=False, indent=2, default=str)

        yields = curve.get("yields", {})
        date = curve.get("date", "未知")

        # curve shape
        china_shape = _classify_curve_shape(yields)

        us_shape = "数据不足"
        if "status" not in zh_us and zh_us.get("us"):
            us_shape = _classify_curve_shape(zh_us["us"])

        # Interest rate spread between China and the United States
        cn_10y = yields.get("10年")
        us_10y = zh_us.get("us", {}).get("10年") if "status" not in zh_us else None
        cn_2y = yields.get("1年")
        us_2y = zh_us.get("us", {}).get("2年") if "status" not in zh_us else None

        spread_cn_us = None
        if cn_10y is not None and us_10y is not None:
            spread_cn_us = round(cn_10y - us_10y, 4)

        # Comment
        commentary = _generate_yield_commentary(yields, date)

        # Build a rate of return table
        yields_table = []
        for tenor in _TENORS:
            cn_val = yields.get(tenor)
            yields_table.append({
                "tenor": tenor,
                "china_yield_pct": cn_val,
            })

        payload = {
            "status": "ok",
            "date": date,
            "data_source": "akshare.bond_china_yield() / bond_zh_us_rate()",
            "data_note": "This tool returns the market yield level (spot yield curve), not the yield to maturity calculation of individual bonds. If you need to calculate individual bond YTM, please use the bond pricing model.",
            "yields_by_tenor": yields_table,
            "yield_curve_shape_china": china_shape,
            "yield_curve_shape_us": us_shape,
            "china_us_comparison": {
                "china_10y": cn_10y,
                "us_10y": us_10y,
                "china_2y": cn_2y,
                "us_2y": us_2y,
                "cn_us_10y_spread": spread_cn_us,
            } if "status" not in zh_us else {"status": "unavailable"},
            "commentary_with_key_levels": commentary,
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Bond yield calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ── Tool 2: Credit Spread Analysis ───────────────────────────────────────────

@tool
@register_tool(
    tool_id="get_credit_spread_analysis",
    name="信用利差分析",
    description=(
        "Obtain multiple yield curves of the Chinese bond market in real time through akshare,"
        "Calculate the credit spread (AAA short-term and medium-term bills/AAA bank ordinary bond yield - Treasury bond yield of the same maturity)."
        "The widening of credit spreads reflects the decline in market risk appetite (rising risk aversion),"
        "The narrowing of credit spreads reflects the increase in market risk appetite (increased risk appetite)."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["bond", "credit_spread", "credit_analysis", "macro"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["查询信用利差水平", "分析市场风险偏好", "债券信用定价分析"],
    when_to_use=(
        "When a user asks about the level of credit spreads, the spread between AAA-rated bonds and Treasury bonds,"
        "Used when market risk preferences change and credit bond pricing is reasonable."
    ),
    when_not_to_use=(
        "Not suitable for individual bond credit rating analysis of a single credit bond;"
        "Not suitable for calculating the yield to maturity (YTM) of individual bonds;"
        "Not suitable for querying the Treasury yield curve itself (use get_bond_yield_calculation)."
    ),
    returns=(
        "Returns a JSON string, including date (data date), credit_spreads_by_tenor (credit spread table for each term),"
        "interpretation (Market interpretation), warning_if_data_stale (data aging warning)."
    ),
    example="get_credit_spread_analysis()",
    related_tools=["get_bond_yield_calculation", "get_bond_duration_convexity"],
)
def get_credit_spread_analysis() -> str:
    """Get credit spread analysis of China s bond market.

    Use AKShare to obtain multiple yield curves and calculate AAA short- and medium-term bills,
    AAA The credit spread between ordinary bank bonds and government bonds of the same maturity.

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            date: Data date (YYYY-MM-DD)
            data_source: Data source description
            data_note: Data Notes (Definition and Interpretation of Credit Spreads)
            curves_available: dict Available dates for each curve——
                — treasury: Treasury yield curve data dates
                — aaa_corporate_note: AAA Short and medium term bill curve dates
                — aaa_bank_note: AAA Bank ordinary bond curve date
            credit_spreads_by_tenor: list[dict] Credit spread table for each term, element structure——
                — tenor: term
                — treasury_yield_%: Treasury bond yield (%)
                — aaa_corporate_spread_%: AAA Corporate bond credit spread (%)
                — aaa_bank_spread_%: AAA Bank bond credit spread (%)
            key_tenor_spreads: dict Key period (1/3/5/7/10 years) spread summary——
                — <tenor>: within this period aaa_corporate_spread / aaa_bank_spread
            interpretation: Market interpretation text
            warning_if_data_stale: Data age warning (returns a string if the data is older, None otherwise)
            message: Error message (only status="error" exist)
    """
    try:
        multi = _fetch_china_multi_curve()

        if multi.get("status") == "error":
            return json.dumps({
                "status": "error",
                "message": f"收益率曲线数据获取失败: {multi.get('message')}",
            }, ensure_ascii=False, indent=2, default=str)

        date = multi.get("date", "未知")
        curves = multi.get("curves", {})

        treasury = curves.get("中债国债收益率曲线", {})
        corporate = curves.get("中债中短期票据收益率曲线(AAA)", {})
        bank = curves.get("中债商业银行普通债收益率曲线(AAA)", {})

        treasury_yields = treasury.get("yields", {}) if treasury.get("status") == "ok" else {}
        corporate_yields = corporate.get("yields", {}) if corporate.get("status") == "ok" else {}
        bank_yields = bank.get("yields", {}) if bank.get("status") == "ok" else {}

        # Calculate credit spread
        credit_spreads = {}
        for tenor in _TENORS:
            rf = treasury_yields.get(tenor)
            cr = corporate_yields.get(tenor)
            bk = bank_yields.get(tenor)
            entry = {"tenor": tenor}
            if rf is not None and cr is not None:
                entry["aaa_corporate_spread"] = round(cr - rf, 4)
                entry["aaa_corporate_yield"] = cr
            if rf is not None and bk is not None:
                entry["aaa_bank_spread"] = round(bk - rf, 4)
                entry["aaa_bank_yield"] = bk
            if rf is not None:
                entry["treasury_yield"] = rf
            credit_spreads[tenor] = entry

        # Summary of key term spreads
        key_spreads = {}
        for tenor in ["1年", "3年", "5年", "7年", "10年"]:
            entry = credit_spreads.get(tenor, {})
            key = {}
            if "aaa_corporate_spread" in entry:
                key["aaa_corporate_spread"] = entry["aaa_corporate_spread"]
            if "aaa_bank_spread" in entry:
                key["aaa_bank_spread"] = entry["aaa_bank_spread"]
            if key:
                key_spreads[tenor] = key

        # Generate interpretation
        spread_values = {}
        for t in _TENORS:
            entry = credit_spreads.get(t, {})
            if "aaa_corporate_spread" in entry:
                spread_values[f"AAA企业债_{t}"] = entry["aaa_corporate_spread"]
            if "aaa_bank_spread" in entry:
                spread_values[f"AAA银行债_{t}"] = entry["aaa_bank_spread"]

        interpretation = _generate_spread_commentary(spread_values, date)

        # Data aging check
        warning = None
        if date and date != "未知":
            try:
                data_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
                today = datetime.date.today()
                diff = (today - data_date).days
                if diff > 5:
                    warning = f"数据已 {diff} 天未更新（最新日期 {date}），可能影响分析准确性。"
                elif diff > 2:
                    warning = f"数据为 {diff} 天前（{date}），时效性一般。"
            except (ValueError, TypeError):
                pass

        # Organize output into table format
        spreads_table = []
        for tenor in _TENORS:
            entry = credit_spreads.get(tenor, {})
            row = {"tenor": tenor}
            if "treasury_yield" in entry:
                row["treasury_yield_%"] = entry["treasury_yield"]
            if "aaa_corporate_spread" in entry:
                row["aaa_corporate_spread_%"] = entry["aaa_corporate_spread"]
            if "aaa_bank_spread" in entry:
                row["aaa_bank_spread_%"] = entry["aaa_bank_spread"]
            spreads_table.append(row)

        payload = {
            "status": "ok",
            "date": date,
            "data_source": "akshare.bond_china_yield()",
            "data_note": (
                "credit spread = Credit bond yield - Treasury bond yield of the same maturity."
                "Spreads widen = Risk appetite declines (risk aversion), spreads narrow = Risk appetite rises (risk-on-risk)."
            ),
            "curves_available": {
                "treasury": treasury.get("date"),
                "aaa_corporate_note": corporate.get("date", "不可用"),
                "aaa_bank_note": bank.get("date", "不可用"),
            },
            "credit_spreads_by_tenor": spreads_table,
            "key_tenor_spreads": key_spreads,
            "interpretation": interpretation,
            "warning_if_data_stale": warning,
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("信用利差分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ── Tool 3: Bond duration and convexity ─────────────────────────────────────────

@tool
@register_tool(
    tool_id="get_bond_duration_convexity",
    name="债券久期与凸性",
    description=(
        "Calculate Macaulay duration, modified duration, and convexity for a fixed-rate bond,"
        "and estimate the impact of changes in yields on bond prices."
        "If the yield to maturity is not provided, the current 10-year Treasury bond yield will be automatically obtained as a reference."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=["bond", "duration", "convexity", "fixed_income"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["计算债券久期", "计算债券凸性", "Estimate the impact of changes in interest rates on bond prices"],
    when_to_use=(
        "When the user needs to calculate the Macaulay duration, modified duration, and convexity of a fixed-rate bond,"
        "or used when estimating the approximate impact of changes in yields on bond prices."
        "Duration convexity analysis applied to standardized bonds."
    ),
    when_not_to_use=(
        "Not suitable for floating rate bonds (duration is calculated differently);"
        "Not suitable for equity-containing bonds (such as callable/putable bonds, effective duration needs to be used);"
        "Not suitable for querying the market yield curve (please use get_bond_yield_calculation)."
    ),
    returns=(
        "Returns a JSON string, including macaulay_duration (Macaulay duration year),"
        "modified_duration (Modified duration), convexity (convexity),"
        "price_change_1pct (Estimated price change if yield rises by 1%),"
        "parameters_used (Parameters used), methodology (description of calculation method)."
    ),
    example="get_bond_duration_convexity(coupon_rate=0.03, years_to_maturity=10, frequency=2)",
    related_tools=["get_bond_yield_calculation", "get_credit_spread_analysis"],
)
def get_bond_duration_convexity(
    coupon_rate: Annotated[float, "Coupon interest rate, such as 0.03 3%"] = 0.03,
    years_to_maturity: Annotated[float, "剩余期限（年）"] = 10.0,
    yield_to_maturity: Annotated[Optional[float], "Yield to maturity, if not provided, the current 10Y Treasury bond yield will be automatically obtained."] = None,
    frequency: Annotated[int, "Annual interest payment frequency,1=Annual payment,2=Paid half yearly"] = 2,
) -> str:
    """Calculate the Macaulay duration, modified duration, and convexity for a fixed-rate bond.

    If yield_to_maturity is not provided, the current 10-year Treasury bond yield will be obtained through akshare.

    Args:
        coupon_rate: Coupon rate (decimal, such as 0.03 means 3%), default 0.03
        years_to_maturity: Remaining term (years), default 10.0
        yield_to_maturity: Yield to maturity (decimal), automatically obtains the current 10-year Treasury bond yield when it is None, default None
        frequency: Annual interest payment frequency, optional 1 (annual payment) / 2 (semi-annual payment) / 4 (quarterly payment) / 12 (monthly payment), default 2

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            macaulay_duration: dict Macaulay Duration——
                — years: Duration years
                — description: Explanation of meaning
            modified_duration: dict modified duration——
                — value: Modified duration value
                — description: Explanation of meaning
            convexity: dict Convexity——
                — value: convexity value
                — description: Explanation of meaning
            price_change_1pct: dict Estimated price change when yield rises by 1%——
                — yield_increase_1pct_pct_change: Price change percentage
                — explanation: Explanation text
                — formula: formula used
                — linear_estimate_only_mod_duration: Percentage of duration linear estimate only
                — with_convexity_adjustment: Convexity-adjusted percentage
            bond_price: dict bond price——
                — current_price: current price
                — face_value: Face value (100.0)
            parameters_used: dict actual parameters used——
                — coupon_rate: Coupon rate (decimal)
                — coupon_rate_pct: Coupon interest rate (%)
                — years_to_maturity: remaining term
                — yield_to_maturity: Yield to maturity (decimal)
                — yield_to_maturity_pct: Yield to maturity (%)
                — frequency: Interest payment frequency text description
                — payment_periods: Total number of interest payment periods
            methodology: dict Description of calculation methods for each indicator (macaulay_duration/modified_duration/convexity/price_change)
            message: Error message (only status="error" exist)
    """
    try:
        if yield_to_maturity is None:
            curve = _bond_tools_fetch_china_yield_curve()
            if curve.get("status") == "ok":
                y10 = curve.get("yields", {}).get("10年")
                if y10 is not None:
                    yield_to_maturity = y10 / 100.0  # Convert to decimal
                else:
                    return json.dumps({
                        "status": "error",
                        "message": "Unable to obtain the current 10-year Treasury bond yield, please provide the yield_to_maturity parameter manually.",
                    }, ensure_ascii=False, indent=2, default=str)
            else:
                return json.dumps({
                    "status": "error",
                    "message": f"自动获取收益率失败: {curve.get('message')}，请手动提供 yield_to_maturity 参数",
                }, ensure_ascii=False, indent=2, default=str)

        if coupon_rate < 0 or coupon_rate > 1:
            return json.dumps({
                "status": "error",
                "message": "The coupon rate coupon_rate should be in 0~1 Within the range (e.g. 0.03 means 3%)",
            }, ensure_ascii=False, indent=2, default=str)

        if yield_to_maturity < 0 or yield_to_maturity > 1:
            return json.dumps({
                "status": "error",
                "message": "Yield to maturity yield_to_maturity should be in 0~1 Within the range (e.g. 0.03 means 3%)",
            }, ensure_ascii=False, indent=2, default=str)

        if years_to_maturity <= 0:
            return json.dumps({
                "status": "error",
                "message": "Remaining maturity years_to_maturity must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if frequency not in (1, 2, 4, 12):
            return json.dumps({
                "status": "error",
                "message": "Interest payment frequency frequency only supports 1 (annual payment), 2 (semi-annual payment), 4 (quarterly payment), and 12 (monthly payment)",
            }, ensure_ascii=False, indent=2, default=str)

        result = _calculate_duration_convexity(
            coupon_rate=coupon_rate,
            years_to_maturity=years_to_maturity,
            yield_to_maturity=yield_to_maturity,
            frequency=frequency,
        )

        if "error" in result:
            return json.dumps({
                "status": "error",
                "message": result["error"],
            }, ensure_ascii=False, indent=2, default=str)

        payload = {
            "status": "ok",
            "macaulay_duration": {
                "years": result["macaulay_duration_years"],
                "description": "Macaulay Duration = Σ(t × PV_CF_t) / Bond price, which represents the average time (years) it takes to recover investment principal and interest.",
            },
            "modified_duration": {
                "value": result["modified_duration"],
                "description": "modified duration = Macaulay Duration / (1 + YTM/Interest payment frequency), Represents the approximate percentage change in price when yields change by 1%",
            },
            "convexity": {
                "value": result["convexity"],
                "description": "Convexity = Σ[t × (t+1/f) × PV_CF_t] / (price × (1+YTM/f)²), Measures the sensitivity of duration to changes in yields",
            },
            "price_change_1pct": {
                "yield_increase_1pct_pct_change": result["price_change_1pct"]["yield_increase_1pct"],
                "explanation": result["price_change_1pct"]["explanation"],
                "formula": "ΔP/P ≈ -ModDuration × Δy + 0.5 × Convexity × (Δy)²",
                "linear_estimate_only_mod_duration": round(-result["modified_duration"] * 0.01 * 100, 4),
                "with_convexity_adjustment": result["price_change_1pct"]["yield_increase_1pct"],
            },
            "bond_price": {
                "current_price": result["price"],
                "face_value": 100.0,
            },
            "parameters_used": {
                "coupon_rate": coupon_rate,
                "coupon_rate_pct": round(coupon_rate * 100, 2),
                "years_to_maturity": years_to_maturity,
                "yield_to_maturity": round(yield_to_maturity, 6),
                "yield_to_maturity_pct": round(yield_to_maturity * 100, 4),
                "frequency": f"每{'半' if frequency == 2 else ''}年{' ' if frequency == 1 else ''}{frequency}次"
                            if frequency <= 2 else f"每年 {frequency} 次",
                "payment_periods": int(years_to_maturity * frequency),
            },
            "methodology": {
                "macaulay_duration": "Macaulay Duration = Σ(t × PV_CF_t) / Σ(PV_CF_t), Among them, t is the cash flow time (year), and PV_CF_t is the present value of cash flow in each period.",
                "modified_duration": "Modified Duration = Macaulay Duration / (1 + YTM / frequency)",
                "convexity": "Convexity = Σ[t × (t + 1/frequency) × PV_CF_t] / (Price × (1 + YTM/frequency)²)",
                "price_change": "ΔP/P ≈ -MD × Δy + 0.5 × Convexity × (Δy)²",
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Bond duration and convexity calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_bond_yield_calculation",
    "get_credit_spread_analysis",
    "get_bond_duration_convexity",
]

# === cashflow_enhancement ===
"""In-depth enhancement of cash flow quality and performance forecast analysis tools.

Provided by:
1. get_cashflow_quality_deep — In-depth analysis of cash flow quality
2. get_earnings_surprise_analysis — Performance forecast/profit surprise analysis
"""

import json
import logging
from statistics import mean, pstdev
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool

from core.skill_runtime.data_access import (
    get_latest_stock_price,
    get_stock_basic_info,
    get_stock_financial_periods,
)
from core.skill_runtime.standard_financial_apis import (
    get_cashflow_quality_trend,
    get_historical_financial_annual_series,
)
from core.tools.base import register_tool
from core.tools.implementations.risk.extended_risk_models import (
    _detect_period_type,
    _annualize_factor,
    _PERIOD_LABELS,
)

logger = logging.getLogger(__name__)


# ==================== Inside the tool helper ====================

def _cashflow_enhancement_safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _cashflow_enhancement_safe_float(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        text = str(value).strip()
        if not text:
            return None
        numeric = float(text)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _cashflow_enhancement_json_response(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _normalize_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    for prefix in ("SH", "SZ", "SS", "BJ"):
        text = text.replace(prefix, "")
    if "." in text:
        text = text.split(".", 1)[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[-6:].zfill(6) if digits else ""


# ==================== Tool 3: Depth of cash flow quality ====================

@tool
@register_tool(
    tool_id="get_cashflow_quality_deep",
    name="现金流质量深度",
    description=(
        "Conduct in-depth analysis of cash flow quality based on annual report sequence and financial period data."
        "Calculate free cash flow (FCF), FCF Yield, OCF/net profit ratio trend,"
        "Cash flow stability score (0-100), and cash flow quality comprehensive score."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["cashflow_quality", "cashflow", "fcf", "cashflow_analysis", "financial_quality", "fundamentals", "cashflow_deterioration"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["cashflow_quality_analysis", "fcf_yield_assessment", "cashflow_stability_evaluation"],
    when_to_use="Use it when you need in-depth cash flow quality analysis, FCF yield, cash flow stability score, OCF/net profit ratio trend.",
    returns="Returns a JSON string containing fcf, fcf_yield, ocf_to_np_ratio, stability_score, trend_direction, flags.",
    example="get_cashflow_quality_deep(symbol='600519')",
)
def get_cashflow_quality_deep(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
) -> str:
    """Get in-depth enhanced data on cash flow quality.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: Status: "success" | "no_data" | "error"
            symbol: Standardized stock code
            years_analyzed: Number of years analyzed
            current_price: current stock price
            total_market_cap: Total market capitalization
            fcf: Free cash flow for the latest year
            fcf_yield: Free cash flow yield (decimal)
            fcf_yield_pct: Free cash flow yield (%)
            ocf_to_net_profit: dict OCF/net profit ratio——
                — current: latest value
                — average: average
                — min: minimum value
                — max: maximum value
            stability_score: Cash flow stability score (0-100)
            quality_score: Comprehensive score of cash flow quality (0-100)
            score_components: dict Score breakdown (fcf_positive_ratio/avg_ocf_to_net_profit/stability_score)
            trend_direction: trend direction: "improving" | "stable" | "deteriorating"
            flags: list[str] Signal tag list
            trend_series: list[dict] Trend series (up to 10 years), element structure——
                — year: Year
                — report_period: reporting period
                — ocf_to_net_profit: OCF/net profit
                — fcf_to_net_profit: FCF/net profit
                — operating_cashflow: operating cash flow
                — free_cashflow: free cash flow
            coverage: dict Data coverage
            data_quality: Data quality: "Sufficient data" | "Data is limited" | "Not enough data"
            warnings: list[str] warning list
            message: Error message (only status="error" exist)
    """
    try:
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            return _cashflow_enhancement_json_response({"status": "error", "message": "无效股票代码"})

        # 1. Obtain cash flow quality trends (annual report series)
        cashflow = get_cashflow_quality_trend(normalized_symbol, years=10)
        trend = cashflow.get("trend") or []
        summary = cashflow.get("summary") or {}
        coverage = cashflow.get("coverage") or {}
        cashflow_warnings = list(cashflow.get("warnings") or [])

        # 2. Get financial period data (for capex approximation)
        financial_periods = get_stock_financial_periods(normalized_symbol, limit=12) or []

        # 3. Get current price and market cap
        current_price = get_latest_stock_price(normalized_symbol)
        if current_price is None or current_price <= 0:
            basic = get_stock_basic_info(normalized_symbol) or {}
            current_price = _cashflow_enhancement_safe_float(basic.get("close") or basic.get("current_price"))

        total_mv = _cashflow_enhancement_safe_float(basic.get("total_mv") or basic.get("market_cap")) if (basic := get_stock_basic_info(normalized_symbol)) else None

        # 4. Calculate FCF (taken directly from the annual report series; take the latest year)
        fcf = None
        fcf_yield = None
        if trend:
            latest_trend = trend[0]
            fcf = _cashflow_enhancement_safe_float(latest_trend.get("free_cashflow"))
            if fcf is not None and total_mv is not None and total_mv > 0:
                fcf_yield = fcf / total_mv

        # 5. OCF/Net profit ratio trend
        ocf_np_ratios: List[Optional[float]] = [item.get("ocf_to_net_profit") for item in trend]
        valid_ocf_np = [v for v in ocf_np_ratios if v is not None]
        latest_ocf_np = valid_ocf_np[0] if valid_ocf_np else None
        avg_ocf_np = mean(valid_ocf_np) if valid_ocf_np else None

        # Trend direction: last 3 years vs earlier 3 years
        trend_direction = "stable"
        if len(valid_ocf_np) >= 4:
            recent_3 = valid_ocf_np[:3]
            earlier = valid_ocf_np[-3:] if len(valid_ocf_np) >= 6 else valid_ocf_np[-len(valid_ocf_np)//2:]
            if recent_3 and earlier:
                recent_avg = mean(recent_3)
                earlier_avg = mean(earlier)
                if recent_avg > earlier_avg * 1.1:
                    trend_direction = "improving"
                elif recent_avg < earlier_avg * 0.9:
                    trend_direction = "deteriorating"

        # 6. Cash flow stability score (0-100)
        ocf_values: List[Optional[float]] = [item.get("operating_cashflow") for item in trend]
        valid_ocf = [v for v in ocf_values if v is not None]

        stability_score = 50  # Default medium
        if len(valid_ocf) >= 3:
            ocf_mean = mean(valid_ocf)
            if ocf_mean != 0:
                cv = pstdev(valid_ocf) / abs(ocf_mean) if len(valid_ocf) > 1 else 0
                if cv < 0.3:
                    stability_score = 90
                elif cv < 0.5:
                    stability_score = 75
                elif cv < 0.8:
                    stability_score = 60
                elif cv < 1.2:
                    stability_score = 40
                else:
                    stability_score = 20
            # Bonus points for consecutive positive OCF
            positive_ratio = sum(1 for v in valid_ocf if v > 0) / len(valid_ocf)
            if positive_ratio > 0.8:
                stability_score = min(100, stability_score + 10)
            elif positive_ratio < 0.5:
                stability_score = max(0, stability_score - 10)

        # 7. Comprehensive score of cash flow quality (0-100)
        quality_score = 50
        score_components: Dict[str, float] = {}

        # Subkey: FCF Quality
        if len(valid_ocf) >= 3:
            fcf_positive_ratio = sum(1 for v in valid_ocf if v and v > 0) / len(valid_ocf)
            fcf_score = fcf_positive_ratio * 100
            score_components["fcf_positive_ratio"] = round(fcf_positive_ratio, 4)

        # Sub-item: OCF/Net Profit
        if valid_ocf_np:
            avg_ratio = mean(valid_ocf_np)
            ocf_np_score = min(100, max(0, (avg_ratio - 0.5) * 100))
            score_components["avg_ocf_to_net_profit"] = round(avg_ratio, 4)
        else:
            ocf_np_score = 0

        # Sub-item: Stability
        score_components["stability_score"] = stability_score

        # Overall rating
        counts = 0
        total_score = 0.0
        for key in score_components:
            if key == "stability_score":
                total_score += stability_score
                counts += 1
            elif key == "avg_ocf_to_net_profit":
                total_score += ocf_np_score
                counts += 1
            elif key == "fcf_positive_ratio":
                total_score += score_components[key] * 100
                counts += 1
        quality_score = round(total_score / max(counts, 1), 1)

        # 8. signal tag
        flags: List[str] = []
        if latest_ocf_np is not None and latest_ocf_np > 1.0:
            flags.append("High profit content (OCF/net profit>1) ")
        elif latest_ocf_np is not None and latest_ocf_np < 0.5:
            flags.append("The profit content is low (OCF/net profit<0.5) ")
        if stability_score >= 75:
            flags.append("现金流稳定性优秀")
        elif stability_score <= 30:
            flags.append("现金流波动较大")
        if fcf_yield is not None and fcf_yield > 0.05:
            flags.append("Abundant free cash flow (FCF yield>5%) ")
        elif fcf_yield is not None and fcf_yield < 0:
            flags.append("自由现金流为负")
        if trend_direction == "improving":
            flags.append("现金流质量趋势向好")
        elif trend_direction == "deteriorating":
            flags.append("现金流质量趋势恶化")

        # Construct OCF/Net Profit Trends
        trend_series = []
        for item in trend:
            trend_series.append({
                "year": item.get("year"),
                "report_period": item.get("report_period"),
                "ocf_to_net_profit": item.get("ocf_to_net_profit"),
                "fcf_to_net_profit": item.get("fcf_to_net_profit"),
                "operating_cashflow": item.get("operating_cashflow"),
                "free_cashflow": item.get("free_cashflow"),
            })

        return _cashflow_enhancement_json_response({
            "status": "success" if trend else "no_data",
            "symbol": normalized_symbol,
            "years_analyzed": len(trend),
            "current_price": current_price,
            "total_market_cap": total_mv,
            "fcf": fcf,
            "fcf_yield": round(fcf_yield, 6) if fcf_yield is not None else None,
            "fcf_yield_pct": round(fcf_yield * 100, 4) if fcf_yield is not None else None,
            "ocf_to_net_profit": {
                "current": round(latest_ocf_np, 4) if latest_ocf_np is not None else None,
                "average": round(avg_ocf_np, 4) if avg_ocf_np is not None else None,
                "min": round(min(valid_ocf_np), 4) if valid_ocf_np else None,
                "max": round(max(valid_ocf_np), 4) if valid_ocf_np else None,
            },
            "stability_score": stability_score,
            "quality_score": quality_score,
            "score_components": score_components,
            "trend_direction": trend_direction,
            "flags": flags,
            "trend_series": trend_series[:10],
            "coverage": coverage,
            "data_quality": "数据充足" if len(trend) >= 3 else "数据有限" if trend else "数据不足",
            "warnings": cashflow_warnings,
        })
    except Exception as exc:
        logger.error("Failed to obtain in-depth analysis of cash flow quality: %s", exc, exc_info=True)
        return _cashflow_enhancement_json_response({"status": "error", "message": f"Failed to obtain in-depth analysis of cash flow quality: {exc}"})


# ==================== Tool 4: Performance forecast analysis ====================

@tool
@register_tool(
    tool_id="get_earnings_surprise_analysis",
    name="业绩预告分析",
    description=(
        "Analyze performance surprises/shocks based on quarterly trends in net profit based on financial period data."
        "Calculate the net profit, quarter-on-quarter growth, and trend deviation in the last eight quarters,"
        "Identify quarters that deviate significantly from trend (>20%unexpected changes),"
        "And give the overall performance sentiment (significantly exceeding expectations/in line with expectations/significantly below expectations)."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["earnings_surprise", "earnings", "earnings_analysis", "profit_trend", "fundamentals", "earnings_quality"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["earnings_surprise_detection", "profit_trend_analysis", "earnings_consistency_evaluation"],
    when_to_use="Use when you need to analyze quarterly performance trends, identify performance surprises/shocks, and assess performance consistency.",
    returns="Returns a JSON string containing recent_quarters_data, recent_surprises_list, overall_sentiment, data_quality, methodology_note.",
    example="get_earnings_surprise_analysis(symbol='600519')",
)
def get_earnings_surprise_analysis(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
) -> str:
    """Get performance preview/profit surprise analysis.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: Status: "success" | "no_data" | "insufficient_data" | "error"
            symbol: Standardized stock code
            total_periods_available: Total number of available periods
            periods_analyzed: Actual number of periods analyzed
            recent_quarters_data: list[dict] Data for the most recent year (newest first), element structure——
                — period: reporting period
                — period_type: period type: "annual" | "q3" | "h1" | "q1" | "unknown"
                — period_label: period chinese label
                — net_profit: original net profit
                — net_profit_annualized: annualized net profit
                — yoy_growth: year-on-year growth rate
                — expected_profit: Trend expected net profit
                — surprise: Surprise amount (actual - expected)
                — surprise_pct: Surprise percentage
                — surprise_category: Surprise category: "Big positive surprise" | "Gentle positive surprise" | "As expected" | "mild negative surprise" | "Big negative surprise"
            recent_surprises_list: list[dict] List of notable surprises (|surprise_pct|>20%) , Element structure——
                — period: reporting period
                — period_label: period label
                — actual_profit_annualized: actual annualized net profit
                — actual_profit_raw: original net profit
                — expected_profit: expected net profit
                — surprise_pct: Surprise percentage
                — category: Category
            overall_sentiment: overall performance sentiment: "Overall more" | "Overall bearish" | "Caution is too much" | "Cautiously bearish" | "long-short equilibrium" | "stable"
            trend_description: Trend description text
            estimated_trend_params: dict Trend line parameters——
                — slope: slope
                — intercept: intercept
            data_quality: Data quality: "Sufficient data" | "Data is limited"
            methodology_note: Methodological statement
            warnings: list[str] warning list
            message: Error or prompt information (only status is "error"/"no_data"/"insufficient_data" exist)
    """
    try:
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            return _cashflow_enhancement_json_response({"status": "error", "message": "无效股票代码"})

        # 1. Get financial period data (last 16 periods to ensure 8 quarters)
        periods = get_stock_financial_periods(normalized_symbol, limit=16) or []

        if not periods:
            return _cashflow_enhancement_json_response({"status": "no_data", "message": "未获取到财务期间数据", "symbol": normalized_symbol})

        # 2. Extract quarterly net profit data and perform caliber processing
        # 🔑 Key: Net profits in different reporting periods (annual reports/quarterly reports) are cumulative values and cannot be directly compared on a month-on-month basis.
        # Strategy: Prioritize data of the same caliber (such as taking all annual reports), and if insufficient, group them by caliber.
        quarterly_data: List[Dict[str, Any]] = []
        caliber_warnings: List[str] = []
        for p in periods:
            period_label = str(p.get("report_period") or p.get("report_date") or "")
            net_profit = _cashflow_enhancement_safe_float(p.get("net_profit") or p.get("net_income") or p.get("n_income_attr_p"))
            if net_profit is not None:
                period_type = _detect_period_type(p)
                # 🔑 Annualize the non-annual report data to unify the caliber to the annual report caliber
                factor = _annualize_factor(period_type)
                net_profit_annualized = net_profit * factor
                quarterly_data.append({
                    "period": period_label,
                    "period_type": period_type,
                    "period_label": _PERIOD_LABELS.get(period_type, period_type),
                    "net_profit": net_profit,
                    "net_profit_annualized": net_profit_annualized,
                })
                if period_type != "annual" and period_type != "unknown":
                    caliber_warnings.append(f"{period_label}为{_PERIOD_LABELS.get(period_type, period_type)}口径，净利润已年化处理")

        # Sort by time (oldest to newest)
        quarterly_data.sort(key=lambda x: str(x.get("period", "")))

        # 🔑 Removal of duplicates: Keep the one with the largest caliber in the same year (priority annual report > third quarter report > semi-annual report > quarterly report)
        seen_years: Dict[str, Dict[str, Any]] = {}
        for q in quarterly_data:
            yr = str(q["period"])[:4]
            if yr not in seen_years:
                seen_years[yr] = q
            else:
                # Caliber priority:annual > q3 > h1 > q1
                priority = {"annual": 4, "q3": 3, "h1": 2, "q1": 1, "unknown": 0}
                if priority.get(q["period_type"], 0) > priority.get(seen_years[yr]["period_type"], 0):
                    seen_years[yr] = q
        yearly_data = sorted(seen_years.values(), key=lambda x: str(x.get("period", "")))

        # Take the last 8 years (compare on a year-to-year basis after annualization)
        recent_quarters = yearly_data[-8:] if len(yearly_data) >= 8 else yearly_data

        if len(recent_quarters) < 3:
            return _cashflow_enhancement_json_response({
                "status": "insufficient_data",
                "message": f"仅获取到 {len(recent_quarters)} 个年度的净利润数据，至少需要 3 个年度进行分析",
                "symbol": normalized_symbol,
                "recent_quarters_data": recent_quarters,
                "data_quality": "数据不足",
            })

        # 3. Calculate year-over-year growth and trend deviation (using annualized net profit)
        enhanced_quarters: List[Dict[str, Any]] = []
        for i, q in enumerate(recent_quarters):
            entry = {
                "period": q["period"],
                "period_type": q.get("period_type", "unknown"),
                "period_label": q.get("period_label", ""),
                "net_profit": q["net_profit"],
                "net_profit_annualized": q["net_profit_annualized"],
                "yoy_growth": None,
                "expected_profit": None,
                "surprise": None,
                "surprise_pct": None,
                "surprise_category": None,
            }
            if i > 0:
                # 🔑 Use annualized values to make year-on-year comparisons to avoid caliber differences.
                prev_np_ann = recent_quarters[i - 1]["net_profit_annualized"]
                cur_np_ann = q["net_profit_annualized"]
                if prev_np_ann != 0:
                    entry["yoy_growth"] = round((cur_np_ann - prev_np_ann) / abs(prev_np_ann), 4)
            enhanced_quarters.append(entry)

        # 4. Calculate trend line (simple linear regression: based on annualized net profit)
        np_values = [q["net_profit_annualized"] for q in enhanced_quarters]
        n = len(np_values)
        x_mean = (n - 1) / 2
        y_mean = mean(np_values)
        numerator = sum((i - x_mean) * (np_values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean

        # Calculate expected value (trend value) and surprise (using annualized net profit) for each year
        surprises: List[Dict[str, Any]] = []
        for i, entry in enumerate(enhanced_quarters):
            expected = intercept + slope * i
            actual = entry["net_profit_annualized"]
            if expected != 0:
                surprise_pct = (actual - expected) / abs(expected)
                entry["expected_profit"] = round(expected, 2)
                entry["surprise"] = round(actual - expected, 2)
                entry["surprise_pct"] = round(surprise_pct, 4)

                # Classification surprise level
                if surprise_pct > 0.20:
                    category = "大幅正向惊喜"
                elif surprise_pct > 0.05:
                    category = "温和正向惊喜"
                elif surprise_pct > -0.05:
                    category = "符合预期"
                elif surprise_pct > -0.20:
                    category = "温和负向惊喜"
                else:
                    category = "大幅负向惊喜"
                entry["surprise_category"] = category

                # Record significant surprise/scare
                if abs(surprise_pct) > 0.20:
                    surprises.append({
                        "period": entry["period"],
                        "period_label": entry.get("period_label", ""),
                        "actual_profit_annualized": actual,
                        "actual_profit_raw": entry["net_profit"],
                        "expected_profit": round(expected, 2),
                        "surprise_pct": round(surprise_pct, 4),
                        "category": category,
                    })

        # 5. Overall mood judgment
        if surprises:
            positive_count = sum(1 for s in surprises if s["surprise_pct"] > 0)
            negative_count = sum(1 for s in surprises if s["surprise_pct"] < 0)
            total_surprises = len(surprises)
            if positive_count >= total_surprises * 0.7:
                overall_sentiment = "整体偏多"
            elif negative_count >= total_surprises * 0.7:
                overall_sentiment = "整体偏空"
            elif positive_count > negative_count:
                overall_sentiment = "谨慎偏多"
            elif negative_count > positive_count:
                overall_sentiment = "谨慎偏空"
            else:
                overall_sentiment = "多空均衡"
        else:
            overall_sentiment = "稳定"

        # Check trend direction
        if slope > 0:
            trend_desc = "上升"
        elif slope < 0:
            trend_desc = "下降"
        else:
            trend_desc = "持平"

        recent_surprises = surprises[-5:] if len(surprises) > 5 else surprises

        total_periods_available = len(quarterly_data)
        periods_analyzed = len(enhanced_quarters)

        return _cashflow_enhancement_json_response({
            "status": "success",
            "symbol": normalized_symbol,
            "total_periods_available": total_periods_available,
            "periods_analyzed": periods_analyzed,
            "recent_quarters_data": list(reversed(enhanced_quarters)),
            "recent_surprises_list": recent_surprises,
            "overall_sentiment": overall_sentiment,
            "trend_description": f"净利润趋势{trend_desc}（斜率={round(slope, 2)}）",
            "estimated_trend_params": {
                "slope": round(slope, 2),
                "intercept": round(intercept, 2),
            },
            "data_quality": "数据充足" if periods_analyzed >= 6 else "数据有限",
            "methodology_note": (
                "Since the system does not contain brokerage profit forecast data,'expected_profit' Simple linear regression trendline estimate based on the last 8 annualized net profits (annualized)."
                "'surprise' = actual_profit_annualized - expected_profit, greater than ±20% Considered a significant unexpected change."
                "Annual report data are used first in the same year, and quarterly report data have been annualized to unify the caliber."
            ),
            "warnings": (
                ["The amount of data is limited and the reference value of trend lines is limited."] + caliber_warnings if periods_analyzed < 6
                else ["Lack of official profit forecast data, using trend line as expected benchmark"] + caliber_warnings
            ),
        })
    except Exception as exc:
        logger.error("Failed to obtain performance forecast analysis: %s", exc, exc_info=True)
        return _cashflow_enhancement_json_response({"status": "error", "message": f"业绩预告分析获取失败: {exc}"})


__all__ = [
    "get_cashflow_quality_deep",
    "get_earnings_surprise_analysis",
]

# === dividend_enhancement ===
"""Dividend yield valuation enhancement and industry valuation distribution tools.

Provided by:
1. get_dividend_valuation_context — Dividend yield valuation strengthens
2. get_industry_valuation_distribution — Industry valuation distribution
"""

import json
import logging
from statistics import mean, median
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool

from core.skill_runtime.data_access import (
    get_latest_stock_price,
    get_stock_basic_info,
)
from core.skill_runtime.standard_financial_apis import (
    get_historical_financial_annual_series,
    get_shareholder_return_metrics,
)
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


# ==================== Inside the tool helper ====================

def _dividend_enhancement_safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _dividend_enhancement_safe_float(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        text = str(value).strip()
        if not text:
            return None
        numeric = float(text)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _dividend_enhancement_cagr(values: List[Optional[float]]) -> Optional[float]:
    """Calculate the 3-year CAGR (Compound Annual Growth Rate)."""
    valid = [v for v in values if v is not None and v > 0]
    if len(valid) < 2:
        return None
    n = len(valid)
    return (valid[0] / valid[-1]) ** (1.0 / max(n - 1, 1)) - 1.0


def _dividend_enhancement_json_response(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _fetch_akshare_dividend_yield(symbol: str) -> Optional[Dict[str, Any]]:
    """Try using AKShare Oriental Wealth Dividend Data to find out."""
    try:
        import akshare as ak
        df = ak.stock_dividents_cninfo(symbol=symbol)
        if df is None or df.empty:
            return None
        # Get only implemented records
        df = df[df["实施进度"] == "实施"]
        if df.empty:
            return None
        df = df.sort_values("股权登记日", ascending=False)
        records = df.head(5).to_dict("records")
        return {"source": "akshare", "records": records}
    except Exception as exc:
        logger.warning("AKShare dividend fallback failed: %s", exc)
        return None


# ==================== Tool 1: Dividend yield valuation strengthens ====================

@tool
@register_tool(
    tool_id="get_dividend_valuation_context",
    name="股息率估值增强",
    description=(
        "Calculate the current dividend rate, 5-year average dividend rate, and historical dividend rate quantile based on dividend records."
        "Payout ratio, dividend growth rate (3-year CAGR), and give a valuation signal (below average=underestimated)."
        "When local data is insufficient, use AKShare to take care of the problem."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "dividend", "dividend_yield", "payout_ratio", "dividend_growth"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["分红估值分析", "股息率历史分位", "派息率评估"],
    when_to_use="Use when dividend rate valuation, dividend return analysis, dividend rate historical quantile or dividend growth rate are required.",
    when_not_to_use="Not suitable for companies with no dividend record (no_dividend_data will be returned). Not suitable for high growth non-dividend paying companies.",
    returns="Returns a JSON string containing current_yield, avg_5y_yield, yield_percentile, payout_ratio, divided_growth, evaluation_signal, divided_history, data_quality.",
    example="get_dividend_valuation_context(symbol='600519')",
    related_tools=["get_ddm_valuation", "get_dividend_data"],
)
def get_dividend_valuation_context(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
) -> str:
    """Get dividend yield valuation enhancement context.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: Status: "success" | "error"
            symbol: Standardized 6-digit stock code
            current_price: current stock price
            current_yield: Current Dividend Yield (Decimal)
            current_yield_pct: Current dividend yield (%)
            avg_5y_yield: 5 Average annual dividend rate (decimal)
            avg_5y_yield_pct: 5 Annual average dividend rate (%)
            yield_percentile: Current dividend yield historical quantile (0-100)
            payout_ratio: Payout ratio (decimal)
            payout_ratio_pct: Dividend payout rate (%)
            dividend_growth: Dividend 3-year CAGR (decimal)
            dividend_growth_pct: Dividend 3-year CAGR (%)
            valuation_signal: valuation signal: "underestimate" | "Neutral" | "overestimate"
            dividend_history: list[dict] Dividend history (last 5 years), element structure——
                — year: Year
                — cash_dividend_per_share: Cash dividend per share
                — dividend_yield: Dividend rate (decimal)
                — dividend_yield_pct: Dividend yield (%)
            data_quality: Data quality: "Sufficient data" | "Data is limited" | "Not enough data"
            data_source: Data source identification
            warnings: list[str] warning list
            message: Error message (only status="error" exist)
    """
    try:
        normalized_symbol = str(symbol).strip().upper()
        for prefix in ("SH", "SZ", "SS", "BJ"):
            normalized_symbol = normalized_symbol.replace(prefix, "")
        normalized_symbol = "".join(ch for ch in normalized_symbol if ch.isdigit())[-6:].zfill(6)
        if not normalized_symbol:
            return _dividend_enhancement_json_response({"status": "error", "message": "无效股票代码"})

        # 1. Get current price
        current_price = get_latest_stock_price(normalized_symbol)
        if current_price is None or current_price <= 0:
            basic = get_stock_basic_info(normalized_symbol) or {}
            current_price = _dividend_enhancement_safe_float(basic.get("close") or basic.get("current_price"))

        if current_price is None or current_price <= 0:
            return _dividend_enhancement_json_response({"status": "error", "message": "未获取到有效现价", "symbol": normalized_symbol})

        # 2. Get shareholder return/dividend data
        shareholder = get_shareholder_return_metrics(normalized_symbol, years=5)
        dividend_annual = shareholder.get("annual") or []
        dividend_records = shareholder.get("records") or []
        data_source = shareholder.get("data_source") or "local"

        # If the local dividend data is insufficient, try AKShare to find out.
        if not dividend_annual and not dividend_records:
            akshare_data = _fetch_akshare_dividend_yield(normalized_symbol)
            if akshare_data:
                data_source = akshare_data.get("source", "akshare")

        # 3. Calculate dividend rate for each year
        annual_yields: List[Dict[str, Any]] = []
        for entry in dividend_annual:
            year = entry.get("year")
            cash = _dividend_enhancement_safe_float(entry.get("cash_dividend_per_share"))
            if year and cash is not None:
                yield_val = cash / current_price
                annual_yields.append({
                    "year": year,
                    "cash_dividend_per_share": cash,
                    "dividend_yield": yield_val,
                    "dividend_yield_pct": round(yield_val * 100, 4),
                })

        # 4. core indicators
        current_yield = annual_yields[0]["dividend_yield"] if annual_yields else None
        yield_values = [item["dividend_yield"] for item in annual_yields if item["dividend_yield"] is not None]
        avg_5y_yield = mean(yield_values) if yield_values else None

        # Dividend rate historical quantile (the position of the current yield in the historical queue)
        yield_percentile = None
        if current_yield is not None and yield_values:
            sorted_yields = sorted(yield_values)
            yield_percentile = sum(1 for y in sorted_yields if y <= current_yield) / len(sorted_yields) * 100

        # 5. Dividend payout rate (latest period)
        payout_ratio = None
        financial = get_historical_financial_annual_series(normalized_symbol, years=3)
        financial_records = financial.get("records") or []
        latest_cash = annual_yields[0].get("cash_dividend_per_share") if annual_yields else None
        if financial_records and latest_cash is not None:
            latest_financial = financial_records[0]
            net_profit = _dividend_enhancement_safe_float(latest_financial.get("net_profit"))
            if net_profit is not None and net_profit > 0:
                basic_info = get_stock_basic_info(normalized_symbol) or {}
                # total_share/total_shares The unit is "10,000 shares" and requires ×1e4 Converted into "shares",
                # Otherwise, net_profit (yuan)/10,000 shares will amplify EPS by 1e4 times.
                # As a result, the dividend payout ratio is reduced by 1e4 times (for example, Moutai will calculate 0.03%, but the actual ratio is about 50%).
                raw_shares = _dividend_enhancement_safe_float(basic_info.get("total_share") or basic_info.get("total_shares"))
                total_shares = raw_shares * 1e4 if raw_shares is not None and raw_shares > 0 else None
                if total_shares is not None and total_shares > 0:
                    eps_approximate = net_profit / total_shares
                    payout_ratio = latest_cash / eps_approximate if eps_approximate > 0 else None

        # 6. Dividend growth rate (3-year CAGR)
        cash_values = [item["cash_dividend_per_share"] for item in annual_yields[:3]]
        dividend_growth = _dividend_enhancement_cagr(cash_values) if len(cash_values) >= 2 else None

        # 7. valuation signal
        valuation_signal = "中性"
        if current_yield is not None and avg_5y_yield is not None:
            if current_yield > avg_5y_yield:
                valuation_signal = "低估"
            else:
                valuation_signal = "高估"

        # 8. Data quality
        data_quality = "数据充足" if len(annual_yields) >= 3 else "数据有限" if annual_yields else "数据不足"

        return _dividend_enhancement_json_response({
            "status": "success",
            "symbol": normalized_symbol,
            "current_price": current_price,
            "current_yield": round(current_yield, 6) if current_yield is not None else None,
            "current_yield_pct": round(current_yield * 100, 4) if current_yield is not None else None,
            "avg_5y_yield": round(avg_5y_yield, 6) if avg_5y_yield is not None else None,
            "avg_5y_yield_pct": round(avg_5y_yield * 100, 4) if avg_5y_yield is not None else None,
            "yield_percentile": round(yield_percentile, 2) if yield_percentile is not None else None,
            "payout_ratio": round(payout_ratio, 4) if payout_ratio is not None else None,
            "payout_ratio_pct": round(payout_ratio * 100, 2) if payout_ratio is not None else None,
            "dividend_growth": round(dividend_growth, 6) if dividend_growth is not None else None,
            "dividend_growth_pct": round(dividend_growth * 100, 4) if dividend_growth is not None else None,
            "valuation_signal": valuation_signal,
            "dividend_history": annual_yields[:5],
            "data_quality": data_quality,
            "data_source": data_source,
            "warnings": [] if annual_yields else ["Dividend data not found, dividend yield valuation cannot be calculated."],
        })
    except Exception as exc:
        logger.error("Dividend yield valuation enhancement acquisition failed: %s", exc, exc_info=True)
        return _dividend_enhancement_json_response({"status": "error", "message": f"股息率估值增强获取失败: {exc}"})


# ==================== Tool 2: Industry valuation distribution ====================

@tool
@register_tool(
    tool_id="get_industry_valuation_distribution",
    name="行业估值分布",
    description=(
        "Statistical PE/PB distribution by industry (count, mean, median, P25, P75, minimum, maximum),"
        "and returns the Top 10 cheapest and most expensive stocks in each sector."
        "If industry is specified, only this industry will be analyzed, otherwise all industries will be traversed."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need industry valuation distribution, industry PE/PB statistics, or looking for undervalued/overvalued stocks in the industry.",
    returns="Returns a JSON string containing distribution_stats, cheapest_stocks, priciest_stocks, data_quality.",
    example="get_industry_valuation_distribution(industry='Liquor')",
)
def get_industry_valuation_distribution(
    industry: Annotated[str, "Industry name, such as 'Liquor', 'bank'; Analyze all industries for space time"] = "",
) -> str:
    """Get the industry valuation distribution.

    Args:
        industry: Industry name (e.g. "Liquor", "bank") , When it is an empty string, all industries are analyzed, default ""

    Returns:
        str: JSON String, field description——
            status: Status: "success" | "no_data" | "error"
            industries_covered: Number of industries covered
            total_stocks_analyzed: Total number of stocks analyzed
            distribution_stats: dict Industry valuation statistics, key is the industry name, value structure——
                — pe: dict PE Distribution (count/mean/median/p25/p75/min/max)
                — pb: dict PB Distribution (count/mean/median/p25/p75/min/max)
                — sample_count: Number of samples
            cheapest_stocks: dict List of Top 10 stocks with the lowest PE in various industries, element structure——
                — symbol: Stock code
                — name: Stock name
                — pe: PE value
                — pb: PB value
                — total_mv: Total market capitalization
            priciest_stocks: dict List of Top 10 stocks with the highest PE in each industry (structure is the same as above)
            data_quality: Data quality: "Sufficient data" | "Not enough data"
            warnings: list[str] warning list
            message: Error or prompt information (only status is "no_data"/"error" exist)
    """
    try:
        # Get full data from stock_basic_info
        # Aggregation via project_access or direct query
        from core.skill_runtime.project_access import query_stock_collection

        target_industry = str(industry).strip() if industry else None

        # Construct filter conditions
        filters: Dict[str, Any] = {}
        if target_industry:
            filters["industry"] = target_industry
        else:
            filters["industry"] = {"$ne": None, "$ne": ""}

        # Query all stocks with industry affiliation
        stocks = query_stock_collection(
            "stock_basic_info",
            filters=filters,
            projection={
                "_id": 0, "symbol": 1, "name": 1, "industry": 1,
                "pe": 1, "pe_ttm": 1, "pb": 1, "pb_mrq": 1,
                "total_mv": 1, "market_cap": 1,
            },
            limit=500,
        )

        if not stocks:
            msg = f"未找到行业 '{target_industry}' 的股票数据" if target_industry else "No stock data with industry affiliation found"
            return _dividend_enhancement_json_response({"status": "no_data", "message": msg})

        # Group by industry, or use target industry directly
        industry_groups: Dict[str, List[Dict[str, Any]]] = {}
        for stock in stocks:
            ind = str(stock.get("industry") or "").strip()
            if not ind:
                continue
            industry_groups.setdefault(ind, []).append(stock)

        distribution_stats: Dict[str, Dict[str, Any]] = {}
        cheapest_stocks: Dict[str, List[Dict[str, Any]]] = {}
        priciest_stocks: Dict[str, List[Dict[str, Any]]] = {}

        for ind, group in industry_groups.items():
            pe_values = [
                _dividend_enhancement_safe_float(s.get("pe") or s.get("pe_ttm"))
                for s in group
                if _dividend_enhancement_safe_float(s.get("pe") or s.get("pe_ttm")) is not None and _dividend_enhancement_safe_float(s.get("pe") or s.get("pe_ttm")) > 0
            ]
            pb_values = [
                _dividend_enhancement_safe_float(s.get("pb") or s.get("pb_mrq"))
                for s in group
                if _dividend_enhancement_safe_float(s.get("pb") or s.get("pb_mrq")) is not None and _dividend_enhancement_safe_float(s.get("pb") or s.get("pb_mrq")) > 0
            ]

            def _dist(vals: List[float]) -> Dict[str, Any]:
                if not vals:
                    return {"count": 0, "mean": None, "median": None, "p25": None, "p75": None, "min": None, "max": None}
                sorted_vals = sorted(vals)
                n = len(sorted_vals)
                return {
                    "count": n,
                    "mean": round(mean(sorted_vals), 4),
                    "median": round(median(sorted_vals), 4),
                    "p25": round(sorted_vals[n // 4], 4),
                    "p75": round(sorted_vals[3 * n // 4], 4),
                    "min": round(sorted_vals[0], 4),
                    "max": round(sorted_vals[-1], 4),
                }

            distribution_stats[ind] = {
                "pe": _dist(pe_values),
                "pb": _dist(pb_values),
                "sample_count": len(group),
            }

            # Top 10 cheapest / priciest by PE
            pe_stocks = [
                {"symbol": s.get("symbol"), "name": s.get("name"), "pe": _dividend_enhancement_safe_float(s.get("pe") or s.get("pe_ttm")), "pb": _dividend_enhancement_safe_float(s.get("pb") or s.get("pb_mrq")), "total_mv": _dividend_enhancement_safe_float(s.get("total_mv") or s.get("market_cap"))}
                for s in group
                if _dividend_enhancement_safe_float(s.get("pe") or s.get("pe_ttm")) is not None and _dividend_enhancement_safe_float(s.get("pe") or s.get("pe_ttm")) > 0
            ]
            pe_sorted = sorted(pe_stocks, key=lambda x: x["pe"])
            cheapest_stocks[ind] = pe_sorted[:10]
            priciest_stocks[ind] = list(reversed(pe_sorted[-10:])) if len(pe_sorted) >= 10 else list(reversed(pe_sorted))

        # If an industry is specified, only data for that industry will be returned.
        if target_industry and target_industry in distribution_stats:
            result_stats = {target_industry: distribution_stats[target_industry]}
            result_cheapest = {target_industry: cheapest_stocks.get(target_industry, [])}
            result_priciest = {target_industry: priciest_stocks.get(target_industry, [])}
        else:
            result_stats = distribution_stats
            result_cheapest = cheapest_stocks
            result_priciest = priciest_stocks

        total_stocks = sum(v.get("sample_count", 0) for v in result_stats.values())
        industries_covered = len(result_stats)

        return _dividend_enhancement_json_response({
            "status": "success",
            "industries_covered": industries_covered,
            "total_stocks_analyzed": total_stocks,
            "distribution_stats": result_stats,
            "cheapest_stocks": result_cheapest,
            "priciest_stocks": result_priciest,
            "data_quality": "数据充足" if total_stocks > 0 else "数据不足",
            "warnings": [] if total_stocks > 0 else ["No valid data was obtained."],
        })
    except Exception as exc:
        logger.error("Failed to obtain industry valuation distribution: %s", exc, exc_info=True)
        return _dividend_enhancement_json_response({"status": "error", "message": f"行业估值分布获取失败: {exc}"})


__all__ = [
    "get_dividend_valuation_context",
    "get_industry_valuation_distribution",
]

# === etf_fundamentals ===
"""
ETF Fundamental Data Tools

Get the net value, size, fee rate, discount and premium, subscription and redemption status and other indicators of the ETF (ETF does not have PE/PB/ROE).
Support local data priority: if etf_basic_info and etf_daily_quotes have data, use it, otherwise fall back to AKShare / Tushare online interface.
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional, Tuple

from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)

ETF_BASIC_COLLECTION = "etf_basic_info"
ETF_DAILY_COLLECTION = "etf_daily_quotes"
ETF_DEFAULT_SOURCE_PRIORITY = ["local", "tushare", "akshare"]
ETF_SUPPORTED_ONLINE_SOURCES = {"tushare", "akshare"}


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "-", "--", "None", "nan", "NaN"}
    return False


def _coalesce(*values):
    for value in values:
        if not _is_missing(value):
            return value
    return None


def _normalize_date(value) -> Optional[str]:
    if _is_missing(value):
        return None
    text = str(value).strip()
    if len(text) >= 10 and len(text) > 4 and text[4] in {"-", "/"}:
        return text[:10].replace("/", "-")
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return text or None


def _etf_fundamentals_format_value(value, suffix: str = "") -> str:
    if _is_missing(value):
        return "-"
    return f"{value}{suffix}"


def _normalize_source_name(name: str) -> str:
    return str(name or "").strip().lower()


def _get_etf_source_priority() -> list:
    """Get the priority of ETF available data sources and follow the unified configuration."""
    try:
        from app.core.data_source_priority import get_enabled_data_sources_sync

        enabled_sources = get_enabled_data_sources_sync("a_shares")
        priority = []
        for source in enabled_sources:
            normalized = _normalize_source_name(source)
            if normalized == "local" or normalized in ETF_SUPPORTED_ONLINE_SOURCES:
                if normalized not in priority:
                    priority.append(normalized)

        if priority:
            logger.info(f"📊 [ETF Fundamentals] Data source priority: {priority}")
            return priority
    except Exception as e:
        logger.warning(f"⚠️ [ETF Fundamentals] Failed to obtain unified data source priority: {e}")

    logger.info(f"📊 [ETF Fundamentals] Use default data source priority: {ETF_DEFAULT_SOURCE_PRIORITY}")
    return ETF_DEFAULT_SOURCE_PRIORITY.copy()


def _normalize_etf_symbol(symbol: str) -> str:
    """Standardize ETF symbols to 6 digits"""
    if not symbol:
        return ""
    s = str(symbol).strip().upper()
    for prefix in ("SH", "SZ", "SS"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    for suffix in (".SH", ".SZ", ".SS"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    digits = "".join(c for c in s if c.isdigit())
    return digits.zfill(6)[-6:] if digits and len(digits) <= 6 else (digits[-6:] if digits else "")


def _get_etf_full_symbol(symbol: str) -> str:
    """Generate complete code based on code prefix (510050.SH, 159919.SZ) """
    code = _normalize_etf_symbol(symbol)
    if not code or len(code) != 6:
        return ""
    if code.startswith(("50", "51", "52")):
        return f"{code}.SH"
    if code.startswith(("15", "16")):
        return f"{code}.SZ"
    return f"{code}.SH"


def _fetch_etf_from_local(code: str) -> Tuple[Optional[dict], list]:
    """Get ETF fundamentals and daily data from local MongoDB."""
    try:
        from app.core.database import get_mongo_db_sync

        db = get_mongo_db_sync()
        if not db:
            return None, []

        basic = db[ETF_BASIC_COLLECTION].find_one({"code": code}, {"_id": 0})
        if not basic:
            return None, []

        cursor = db[ETF_DAILY_COLLECTION].find(
            {"code": code},
            {"_id": 0, "trade_date": 1, "close": 1, "pct_chg": 1, "volume": 1, "amount": 1, "unit_nav": 1, "accum_nav": 1},
        ).sort("trade_date", -1).limit(30)
        daily = list(cursor)
        return basic, daily
    except Exception as e:
        logger.debug(f"Local ETF data query failed: {e}")
        return None, []


def _fetch_etf_data_akshare(symbol: str) -> Optional[dict]:
    """Get real-time ETF market data from AKShare."""
    try:
        import akshare as ak

        code = _normalize_etf_symbol(symbol)
        full = _get_etf_full_symbol(symbol)
        if not full:
            return None

        df = ak.fund_etf_spot_em()
        if df is None or df.empty:
            return None

        code_col = "代码" if "代码" in df.columns else "基金代码"
        name_col = "名称" if "名称" in df.columns else "基金名称"
        df["code_clean"] = df[code_col].astype(str).str.extract(r"(\d{6})", expand=False).fillna("")
        row = df[df["code_clean"] == code]
        if row.empty:
            return None

        record = row.iloc[0]
        return {
            "name": record.get(name_col, record.get("名称", "")),
            "code": code,
            "full_symbol": full,
            "latest_price": record.get("最新价", record.get("当前-单位净值", record.get("最新-单位净值"))),
            "change_pct": record.get("涨跌幅", record.get("增长率")),
            "volume": record.get("成交量"),
            "amount": record.get("成交额"),
            "fund_scale": record.get("规模"),
            "track_index": record.get("跟踪指数", ""),
            "fund_type": record.get("基金类型", ""),
        }
    except Exception as e:
        logger.warning(f"AKShare ETF Data acquisition failed: {e}")
        return None


def _fetch_etf_valuation_akshare(symbol: str) -> Optional[dict]:
    """Get ETF net value, discount and premium, and on-market application and redemption status from AKShare."""
    try:
        import akshare as ak

        code = _normalize_etf_symbol(symbol)
        if not code:
            return None

        valuation_df = ak.fund_etf_fund_daily_em()
        if valuation_df is None or valuation_df.empty:
            return None

        code_col = "基金代码" if "基金代码" in valuation_df.columns else "代码"
        valuation_df["code_clean"] = valuation_df[code_col].astype(str).str.extract(r"(\d{6})", expand=False).fillna("")
        row = valuation_df[valuation_df["code_clean"] == code]
        if row.empty:
            return None

        record = row.iloc[0]
        unit_nav_col = next((col for col in valuation_df.columns if str(col).endswith("单位净值")), None)
        accum_nav_col = next((col for col in valuation_df.columns if str(col).endswith("累计净值")), None)

        result = {
            "unit_nav": record.get(unit_nav_col) if unit_nav_col else None,
            "accum_nav": record.get(accum_nav_col) if accum_nav_col else None,
            "nav_change_value": record.get("增长值"),
            "nav_growth_rate": record.get("增长率"),
            "market_price": record.get("市价"),
            "premium_discount_rate": record.get("折价率"),
            "fund_type": record.get("类型"),
        }

        try:
            info_df = ak.fund_etf_fund_info_em(
                fund=code,
                start_date=(datetime.now() - timedelta(days=30)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
            )
            if info_df is not None and not info_df.empty:
                latest = info_df.iloc[0]
                result.update(
                    {
                        "latest_nav_date": latest.get("净值日期"),
                        "purchase_status": latest.get("申购状态"),
                        "redemption_status": latest.get("赎回状态"),
                        "unit_nav": _coalesce(result.get("unit_nav"), latest.get("单位净值")),
                        "accum_nav": _coalesce(result.get("accum_nav"), latest.get("累计净值")),
                        "nav_growth_rate": _coalesce(result.get("nav_growth_rate"), latest.get("日增长率")),
                    }
                )
        except Exception as exc:
            logger.warning(f"AKShare ETF Failed to obtain redemption status: {exc}")

        return result
    except Exception as e:
        logger.warning(f"AKShare ETF Failed to obtain valuation data: {e}")
        return None


def _fetch_etf_data_tushare(symbol: str) -> Optional[dict]:
    """Get ETF data from Tushare (fund_basic + latest fund_daily)."""
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider or not provider.api:
            return None

        code = _normalize_etf_symbol(symbol)
        full = _get_etf_full_symbol(symbol)
        if not full:
            return None

        df_basic = provider.api.fund_basic(market="E", status="L", ts_code=full)
        if df_basic is None or df_basic.empty:
            return None

        record = df_basic.iloc[0]
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        df_daily = provider.api.fund_daily(ts_code=full, start_date=start, end_date=end)
        latest_price = None
        change_pct = None
        volume = None
        amount = None
        if df_daily is not None and not df_daily.empty:
            latest = df_daily.iloc[0]
            latest_price = latest.get("close")
            change_pct = latest.get("pct_chg")
            volume = latest.get("vol")
            amount = latest.get("amount")
            if amount is not None:
                try:
                    amount = float(amount) * 1000
                except (TypeError, ValueError):
                    pass

        return {
            "name": record.get("name", ""),
            "code": code,
            "full_symbol": full,
            "latest_price": latest_price,
            "change_pct": change_pct,
            "volume": volume,
            "amount": amount,
            "fund_scale": record.get("issue_amount"),
            "track_index": str(record.get("benchmark", "") or ""),
            "management": record.get("management"),
            "custodian": record.get("custodian"),
            "fund_type": record.get("fund_type"),
            "management_fee": record.get("m_fee"),
            "custodian_fee": record.get("c_fee"),
            "found_date": record.get("found_date"),
            "list_date": record.get("list_date"),
            "issue_date": record.get("issue_date"),
            "due_date": record.get("due_date"),
            "invest_type": record.get("invest_type"),
            "status": record.get("status"),
            "min_amount": record.get("min_amount"),
            "purchase_start_date": record.get("purc_startdate"),
            "redemption_start_date": record.get("redm_startdate"),
        }
    except Exception as e:
        logger.warning(f"Tushare ETF Data acquisition failed: {e}")
        return None


def _fetch_etf_hist_tushare(symbol: str, days: int = 30) -> list:
    """Get ETF historical data from Tushare."""
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider or not provider.api:
            return []

        code = _normalize_etf_symbol(symbol)
        full = _get_etf_full_symbol(symbol)
        if not full:
            return []

        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = provider.api.fund_daily(ts_code=full, start_date=start, end_date=end)
        if df is None or df.empty:
            return []

        records = []
        for _, record in df.iterrows():
            trade_date = record.get("trade_date")
            if trade_date:
                trade_date = str(trade_date)
                if len(trade_date) == 8:
                    trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
            records.append(
                {
                    "日期": trade_date,
                    "date": trade_date,
                    "trade_date": trade_date,
                    "收盘": record.get("close"),
                    "close": record.get("close"),
                    "涨跌幅": record.get("pct_chg"),
                    "pct_chg": record.get("pct_chg"),
                    "增长率": record.get("pct_chg"),
                }
            )
        return records
    except Exception as e:
        logger.warning(f"Tushare ETF Failed to obtain historical data: {e}")
        return []


def _fetch_etf_hist_akshare(symbol: str, days: int = 30) -> list:
    """Get historical ETF data from AKShare."""
    try:
        import akshare as ak

        code = _normalize_etf_symbol(symbol)
        if not code:
            return []
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=start, end_date=end)
        if df is None or df.empty:
            return []
        return df.to_dict("records")
    except Exception as e:
        logger.warning(f"AKShare ETF Failed to obtain historical data: {e}")
        return []


def _merge_missing_fields(target: dict, extra: Optional[dict]) -> dict:
    if not extra:
        return target
    for key, value in extra.items():
        target[key] = _coalesce(target.get(key), value)
    return target


def _fetch_etf_online_bundle(symbol: str, source: str, include_hist: bool = True) -> Tuple[Optional[dict], list]:
    """Obtain ETF data from specified online data sources to avoid disordered rollback across sources."""
    normalized = _normalize_source_name(source)
    hist = []

    if normalized == "tushare":
        spot = _fetch_etf_data_tushare(symbol)
        if spot and include_hist:
            hist = _fetch_etf_hist_tushare(symbol, days=30)
        return spot, hist

    if normalized == "akshare":
        spot = _fetch_etf_data_akshare(symbol)
        spot = _merge_missing_fields(spot or {}, _fetch_etf_valuation_akshare(symbol))
        if not spot:
            return None, []
        if include_hist:
            hist = _fetch_etf_hist_akshare(symbol, days=30)
        return spot, hist

    return None, []


@tool
@register_tool(
    tool_id="get_etf_fundamentals",
    name="ETF 基本面数据",
    description="Get the net value, size, fee rate, discount and premium, subscription and redemption status, tracking index, rise and fall, etc. of the ETF.",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["etf_fundamentals", "etf", "etf_nav", "fundamentals", "etf_valuation", "fund_scale", "premium_discount"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["etf_analysis", "etf_valuation_review", "fund_basics_lookup"],
)
def get_etf_fundamentals(
    ticker: Annotated[str, "ETF Code (such as 510050, 159919)"],
    start_date: Annotated[Optional[str], "Start date, format:YYYY-MM-DD"] = None,
    end_date: Annotated[Optional[str], "End date, format:YYYY-MM-DD"] = None,
    curr_date: Annotated[Optional[str], "Current date, format:YYYY-MM-DD"] = None,
) -> str:
    """Get ETF fundamental analysis data.

    Args:
        ticker: ETF code (such as "510050", "159919") 
        start_date: Start date (YYYY-MM-DD), default None (currently not used)
        end_date: End date (YYYY-MM-DD), default None (currently not used)
        curr_date: Current date (YYYY-MM-DD), used when None datetime.now(), Default None

    Returns:
        str: Markdown Format string containing the following sections——
            Title: "{ticker} ETF fundamental analysis data"
            Analysis date: current or specified date
            ETF Basic information: Name, code, complete code, fund type, tracking index, manager, custodian, establishment date, listing date
            Current market: Latest price, increase or decrease, trading volume, turnover, scale
            ETF Deep attributes: Unit net value, accumulated net value, net value date, market price on the market, discount and premium rate, net value growth rate,
                Management fee, custody fee, minimum purchase amount, subscription start date, redemption start date, subscription status, redemption status,
                Investment type, fund status, tracking error, subscription and redemption list structure
            Recent trends: Date, closing price, increase and decrease of the last 5 trading days
            Description: A reminder that ETFs do not apply to individual stock valuation indicators

            If the code is illegal return "❌ Invalid ETF symbol..." prompt string;
            Returns if the code is not an ETF code "❌ {ticker} Not an ETF symbol..." Prompt string.
    """
    logger.info(f"📊 [ETF Fundamentals] analysis: {ticker}")

    code = _normalize_etf_symbol(ticker)
    if not code or len(code) != 6:
        return f"❌ Invalid ETF symbol: {ticker}, Please enter a 6-digit number (e.g. 510050, 159919)"

    if not (code.startswith(("50", "51", "52")) or code.startswith(("15", "16"))):
        return f"❌ {ticker} Not an ETF symbol. ETF codes usually start with 50/51/52 (Shanghai stock market) or 15/16 (Shenzhen stock market)"

    source_priority = _get_etf_source_priority()
    online_sources = [source for source in source_priority if source in ETF_SUPPORTED_ONLINE_SOURCES]

    spot = None
    hist = []
    spot_source = "local"
    basic_local, daily_local = _fetch_etf_from_local(code)
    if basic_local and daily_local:
        spot = {
            "name": basic_local.get("name", ""),
            "code": code,
            "full_symbol": basic_local.get("full_symbol", _get_etf_full_symbol(ticker)),
            "latest_price": daily_local[0].get("close") if daily_local else None,
            "change_pct": daily_local[0].get("pct_chg") if daily_local else None,
            "volume": daily_local[0].get("volume") if daily_local else None,
            "amount": daily_local[0].get("amount") if daily_local else None,
            "fund_scale": basic_local.get("fund_scale"),
            "track_index": basic_local.get("track_index", ""),
            "management": basic_local.get("management"),
            "custodian": basic_local.get("custodian"),
            "fund_type": basic_local.get("fund_type"),
            "management_fee": basic_local.get("management_fee"),
            "custodian_fee": basic_local.get("custodian_fee"),
            "found_date": basic_local.get("found_date"),
            "list_date": basic_local.get("list_date"),
            "issue_date": basic_local.get("issue_date"),
            "due_date": basic_local.get("due_date"),
            "invest_type": basic_local.get("invest_type"),
            "status": basic_local.get("status"),
            "min_amount": basic_local.get("min_amount"),
            "purchase_start_date": basic_local.get("purchase_start_date"),
            "redemption_start_date": basic_local.get("redemption_start_date"),
            "unit_nav": basic_local.get("unit_nav") or (daily_local[0].get("unit_nav") if daily_local else None),
            "accum_nav": basic_local.get("accum_nav") or (daily_local[0].get("accum_nav") if daily_local else None),
            "market_price": basic_local.get("market_price"),
            "premium_discount_rate": basic_local.get("premium_discount_rate"),
            "nav_growth_rate": basic_local.get("nav_growth_rate"),
            "latest_nav_date": basic_local.get("latest_nav_date"),
            "purchase_status": basic_local.get("purchase_status"),
            "redemption_status": basic_local.get("redemption_status"),
        }
        hist = [{"日期": item.get("trade_date"), "收盘": item.get("close"), "涨跌幅": item.get("pct_chg")} for item in daily_local]
        logger.info(f"📊 [ETF Fundamentals] Use local data: {code}")

    if not spot:
        spot_source = None
        for source in online_sources:
            source_spot, source_hist = _fetch_etf_online_bundle(ticker, source, include_hist=True)
            if source_spot:
                spot = source_spot
                hist = source_hist
                spot_source = source
                logger.info(f"📊 [ETF Fundamentals] Use online data sources: {source}")
                break

    spot = spot or {}

    if spot_source == "local" and online_sources:
        # When there is a local hit, only the highest priority online data source is used for one supplement to avoid additional errors from suboptimal sources.
        enrichment_source = online_sources[0]
        enrichment_spot, _ = _fetch_etf_online_bundle(ticker, enrichment_source, include_hist=False)
        spot = _merge_missing_fields(spot, enrichment_spot)
        logger.info(f"📊 [ETF Fundamentals] Supplementary sources of local data: {enrichment_source}")

    lines = [
        f"# {ticker} ETF 基本面分析数据",
        f"**分析日期**: {curr_date or datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]

    if spot:
        lines.extend(
            [
                "## ETF 基本信息",
                f"- 名称: {_etf_fundamentals_format_value(spot.get('name'))}",
                f"- 代码: {_etf_fundamentals_format_value(spot.get('code'))}",
                f"- 完整代码: {_etf_fundamentals_format_value(spot.get('full_symbol'))}",
                f"- 基金类型: {_etf_fundamentals_format_value(spot.get('fund_type'))}",
                f"- 跟踪指数: {_etf_fundamentals_format_value(spot.get('track_index'))}",
                f"- 管理人: {_etf_fundamentals_format_value(spot.get('management'))}",
                f"- 托管人: {_etf_fundamentals_format_value(spot.get('custodian'))}",
                f"- 成立日期: {_etf_fundamentals_format_value(_normalize_date(spot.get('found_date')))}",
                f"- 上市日期: {_etf_fundamentals_format_value(_normalize_date(spot.get('list_date')))}",
                "",
                "## 当前行情",
                f"- 最新价: {_etf_fundamentals_format_value(spot.get('latest_price'), ' 元')}",
                f"- 涨跌幅: {_etf_fundamentals_format_value(spot.get('change_pct'), '%')}",
                f"- 成交量: {_etf_fundamentals_format_value(spot.get('volume'))} 手",
                f"- 成交额: {_etf_fundamentals_format_value(spot.get('amount'))} 元",
                f"- 规模: {_etf_fundamentals_format_value(spot.get('fund_scale'))} 份",
                "",
                "## ETF 深属性",
                f"- 单位净值: {_etf_fundamentals_format_value(spot.get('unit_nav'))}",
                f"- 累计净值: {_etf_fundamentals_format_value(spot.get('accum_nav'))}",
                f"- 净值日期: {_etf_fundamentals_format_value(_normalize_date(spot.get('latest_nav_date')))}",
                f"- 场内市价: {_etf_fundamentals_format_value(spot.get('market_price'))}",
                f"- 折溢价率: {_etf_fundamentals_format_value(spot.get('premium_discount_rate'), '%')}",
                f"- 净值增长率: {_etf_fundamentals_format_value(spot.get('nav_growth_rate'), '%')}",
                f"- 管理费: {_etf_fundamentals_format_value(spot.get('management_fee'), '%')}",
                f"- 托管费: {_etf_fundamentals_format_value(spot.get('custodian_fee'), '%')}",
                f"- 起购金额: {_etf_fundamentals_format_value(spot.get('min_amount'))}",
                f"- 申购开始日: {_etf_fundamentals_format_value(_normalize_date(spot.get('purchase_start_date')))}",
                f"- 赎回开始日: {_etf_fundamentals_format_value(_normalize_date(spot.get('redemption_start_date')))}",
                f"- 申购状态: {_etf_fundamentals_format_value(spot.get('purchase_status'))}",
                f"- 赎回状态: {_etf_fundamentals_format_value(spot.get('redemption_status'))}",
                f"- 投资类型: {_etf_fundamentals_format_value(spot.get('invest_type'))}",
                f"- 基金状态: {_etf_fundamentals_format_value(spot.get('status'))}",
                "- tracking error: No direct data source yet",
                "- Application and redemption list structure: No direct data source yet",
                "",
            ]
        )
    else:
        lines.append("## Current market\n⚠️ Unable to obtain real-time data, please check the network or data source.\n")

    if hist:
        lines.append("## 近期走势")
        recent = hist[:5] if len(hist) >= 5 else hist
        for item in reversed(recent):
            date = item.get("日期", item.get("date", item.get("trade_date", "-")))
            close = item.get("收盘", item.get("close", "-"))
            pct = item.get("涨跌幅", item.get("pct_chg", item.get("增长率", "-")))
            lines.append(f"- {date}: 收盘 {close}, 涨跌幅 {pct}%")
        lines.append("")
    else:
        lines.append("## Recent trends\n⚠️ Failed to obtain historical data.\n")

    lines.append("---")
    lines.append("*Description: ETF There are no individual stock valuation indicators such as PE/PB/ROE. When analyzing, please pay attention to net value, size, fee rate, discount and premium, subscription and redemption status, tracking index, etc. There is currently no direct data source for tracking error and redemption list structure.*")

    return "\n".join(lines)

# === event_study ===
"""Event study method tool.

Perform statistical analysis on the abnormal returns of specified stocks before and after the event date.
Calculate abnormal returns using the Mean-Adjusted Return Model.
"""

import datetime
import json
import logging
from statistics import mean, stdev
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_daily_quotes
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _event_study_to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        numeric = float(str(value).strip())
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _parse_date(date_str: str) -> str:
    """Normalized dates are in YYYY-MM-DD format."""
    cleaned = "".join(ch for ch in date_str if ch.isdigit())[:8]
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
    return date_str


def _to_dash_date(date_str: str) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD, keeping the existing format unchanged."""
    if "-" in date_str:
        return date_str
    cleaned = "".join(ch for ch in date_str if ch.isdigit())[:8]
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
    return date_str


@tool
@register_tool(
    tool_id="get_event_study",
    name="事件研究法",
    description=(
        "Perform statistical analysis on the abnormal returns of specified stocks before and after the event date."
        "Calculate abnormal returns using the Mean-Adjusted Return Model(AR)and cumulative abnormal returns(CAR), "
        "and calculate the t statistic to test significance."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=["event", "event_study", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["事件驱动分析", "公告效应研究", "市场反应量化评估"],
    when_to_use=(
        "When it is necessary to quantitatively analyze an event (such as financial report release, major announcements, regulatory penalties, executive changes, etc.)"
        "Used when affecting stock prices. Suitable for event-driven strategy research."
    ),
    when_not_to_use=(
        "Not suitable for obtaining historical stock quotes itself (please use get_stock_daily_quotes);"
        "Not suitable for fundamental factor analysis. If you only need the rise and fall before and after the event, you can directly query the market price."
    ),
    returns=(
        "Returns a JSON string, including symbol, event_date, method,"
        "estimation (Estimated period statistics), event_window (daily AR/CAR details),"
        "summary (Total CAR, t-statistic, significance judgment), data_quality (data quality description)."
    ),
    example="get_event_study(symbol='600519', event_date='20251201', window_before=30, window_after=30, estimation_window=120)",
    related_tools=[
        "get_stock_daily_quotes",
        "get_income_analysis",
        "get_stock_news",
    ],
)
def get_event_study(
    symbol: Annotated[str, "A Stock stock code, 6 digits, such as 600519"],
    event_date: Annotated[str, "Event date in the format YYYYMMDD or YYYY-MM-DD"],
    window_before: Annotated[int, "The number of days forward in the event window (before the event), default 30"] = 30,
    window_after: Annotated[int, "The number of days back the event window (after the event), default 30"] = 30,
    estimation_window: Annotated[int, "Number of days in the estimation window, default 120"] = 120,
) -> str:
    """Event study analysis tool.

    Calculated using the Mean-Adjusted Return Model:
    - Estimation period: used to estimate normal income
    - Event Window: Calculating Abnormal Returns(AR)and cumulative abnormal returns(CAR)
    - Significance test: t statistic

    Args:
        symbol: A stock ticker code
        event_date: event date
        window_before: Event window number of days forward
        window_after: Event window number of days backward
        estimation_window: Estimated window number of days

    Returns:
        JSON Event research results in string format
    """
    try:
        symbol = str(symbol).strip().zfill(6)
        event = _parse_date(event_date)

        event_dt = datetime.datetime.strptime(event, "%Y-%m-%d")

        # Calculate date range
        estimation_start = event_dt - datetime.timedelta(days=estimation_window + window_before + 10)
        event_end = event_dt + datetime.timedelta(days=window_after + 10)

        start_str = estimation_start.strftime("%Y%m%d")
        end_str = event_end.strftime("%Y%m%d")

        # Get daily data
        quotes = get_stock_daily_quotes(symbol, start_str, end_str, period="daily", limit=5000)

        if not quotes:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据"},
                ensure_ascii=False,
                default=str,
            )

        # Calculate daily return
        daily_returns: List[Dict[str, Any]] = []
        for q in quotes:
            trade_date = q.get("trade_date", "")
            trade_date_str = _to_dash_date(str(trade_date)) if trade_date else ""

            close = _event_study_to_float(q.get("close"))
            pre_close = _event_study_to_float(q.get("pre_close"))

            if close is not None and pre_close is not None and pre_close > 0:
                daily_return = (close - pre_close) / pre_close
            else:
                continue

            daily_returns.append({
                "date": trade_date_str,
                "return": daily_return,
            })

        if len(daily_returns) < estimation_window // 2:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"日线数据不足，仅获取到 {len(daily_returns)} 条有效交易记录，"
                    f"The estimation period needs to be at least {estimation_window // 2} Article",
                },
                ensure_ascii=False,
                default=str,
            )

        # Sort by date
        daily_returns.sort(key=lambda x: x["date"])

        # Convert date to datetime for comparison
        def _date_key(d: str) -> datetime.datetime:
            try:
                return datetime.datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                return datetime.datetime.min

        event_dt_compare = _date_key(event)

        # Separate estimation periods and event windows
        estimation_returns: List[float] = []
        event_window_returns: List[Dict[str, Any]] = []

        for item in daily_returns:
            item_date = _date_key(item["date"])
            days_diff = (item_date - event_dt_compare).days

            # Estimated period:[event_date - estimation_window - window_before, event_date - window_before)
            est_start = -estimation_window - window_before
            est_end = -window_before

            if est_start <= days_diff < est_end:
                estimation_returns.append(item["return"])

            # Event window:[event_date - window_before, event_date + window_after]
            if -window_before <= days_diff <= window_after:
                event_window_returns.append({
                    "date": item["date"],
                    "days_from_event": days_diff,
                    "actual_return": item["return"],
                })

        if len(estimation_returns) < 10:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"估计期内有效收益数据不足，仅 {len(estimation_returns)} 条（需至少 10 条）",
                },
                ensure_ascii=False,
                default=str,
            )

        # mean adjusted return model
        mean_return = mean(estimation_returns)
        std_return = stdev(estimation_returns) if len(estimation_returns) > 1 else 0.0

        # Compute the AR sum within the event window CAR
        ar_values: List[float] = []
        car = 0.0
        event_results: List[Dict[str, Any]] = []

        for item in event_window_returns:
            ar = item["actual_return"] - mean_return
            ar_values.append(ar)
            car += ar

            event_results.append({
                "date": item["date"],
                "days_from_event": item["days_from_event"],
                "actual_return": round(item["actual_return"], 6),
                "expected_return": round(mean_return, 6),
                "ar": round(ar, 6),
                "car": round(car, 6),
            })

        # t Statistical test:H0: CAR = 0
        n = len(ar_values)
        if n > 1 and std_return > 0:
            # Approximate using the standard deviation of the estimation period
            t_stat = car / (std_return * (n ** 0.5)) if n > 0 else 0.0
        else:
            t_stat = 0.0

        # Critical value approximation (two-tailed test, 5% significance level)
        significant = abs(t_stat) > 1.96

        summary = {
            "car_total": round(car, 6),
            "t_stat": round(t_stat, 4),
            "significant": significant,
            "interpretation": (
                "Events generate statistically significant abnormal returns"
                if significant
                else "事件未产生显著异常收益"
            ),
        }

        payload = {
            "symbol": symbol,
            "event_date": event,
            "method": "mean_adjusted_return",
            "estimation": {
                "window_days": len(estimation_returns),
                "mean_return": round(mean_return, 6),
                "std": round(std_return, 6),
            },
            "event_window": event_results,
            "summary": summary,
            "data_quality": {
                "total_quotes_fetched": len(quotes),
                "valid_return_days": len(daily_returns),
                "estimation_days_used": len(estimation_returns),
                "event_window_days_used": len(event_results),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Event study analysis failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_event_study"]

# === factor_bundle_tools ===
"""Normalization factor bundle tool."""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from core.skill_runtime import (
    get_fundamental_factor_snapshot,
    get_growth_cashflow_factor_bundle,
    get_quality_factor_bundle,
    get_value_factor_bundle,
)
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _factor_bundle_tools_json_response(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


@tool
@register_tool(
    tool_id="get_value_factor_bundle_tool",
    name="价值因子包",
    description=(
        "Returns the stock s value_core package of standardized value factors."
        "Suitable for one-time acquisition of valuation indicators such as PE, PE_TTM, PB, PB_MRQ, PS_TTM, dividend yield, PEG, industry PE/PB median, etc."
        "It also comes with missing factors, rollback warnings and calculation instructions."
        "Here s Value/Valuation Factor is a cross-sectional valuation input and does not directly generate DCF price targets, historical valuation quantiles or full investment ratings."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "It is used when the Agent needs to make valuation judgments, preliminary screening of cheap/expensive, horizontal comparison of PE/PB/PEG, and industry valuation comparison."
        "If the need is to obtain a collection of value indicators instead of reading a certain original field individually, bind this tool first."
    ),
    when_not_to_use=(
        "Not suitable for analysis of income statement trends, solvency, and cash flow quality;"
        "It is also not suitable for making technical judgments, DCF target prices or historical valuation points. If you need quality factor, please use get_quality_factor_bundle_tool."
        "If you need growth/cash flow, please use get_growth_cashflow_factor_bundle_tool, if you need historical percentile, please use get_historical_valuation_percentile_tool."
    ),
    returns=(
        "Returns a JSON string, the structure contains symbol, name, industry, current_price,bundle=value_core, "
        "factors、factor_warnings、industry_samples、calculation_notes、missing_factors。"
        "factors The key fields include pe, pe_ttm, pb, pb_mrq, ps_ttm, divided_yield, peg, industry_pe_median, industry_pb_median."
    ),
    example="get_value_factor_bundle_tool(symbol='600519')",
    related_tools=[
        "get_quality_factor_bundle_tool",
        "get_growth_cashflow_factor_bundle_tool",
        "get_fundamental_factor_snapshot_tool",
        "get_peer_comparison",
    ],
)
def get_value_factor_bundle_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"]
) -> str:
    """Get a package of standardized value factors.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Standardized stock code
            name: Stock name
            industry: Industry
            current_price: current price
            report_period: reporting period
            data_source: Data source
            bundle: Factor package identifier, fixed to "value_core"
            factors: dict value factor set——
                — pe: P/E ratio
                — pe_ttm: TTM P/E ratio
                — pb: price to book ratio
                — pb_mrq: MRQ price to book ratio
                — ps_ttm: TTM price to sales ratio
                — dividend_yield: dividend yield
                — peg: PEG
                — industry_pe_median: Industry PE median
                — industry_pb_median: Industry PB median
            factor_warnings: dict Factor alarm information
            industry_samples: dict Number of industry samples——
                — pe_count: PE Number of samples
                — pb_count: PB Number of samples
            calculation_notes: list[str] Calculation instructions
            missing_factors: list[str] Missing factor list
            message: Error message (only status="error" exist)
    """
    try:
        return _factor_bundle_tools_json_response(get_value_factor_bundle(symbol))
    except Exception as exc:
        logger.error("Failed to obtain value factor package: %s", exc, exc_info=True)
        return _factor_bundle_tools_json_response({"status": "error", "message": f"获取价值因子包失败: {exc}"})


@tool
@register_tool(
    tool_id="get_quality_factor_bundle_tool",
    name="质量因子包",
    description=(
        "Returns the stock s quality_core package of standardized quality factors."
        "Suitable for obtaining ROE, ROA, gross profit margin, net profit margin, asset-liability ratio, current ratio, ROIC,"
        "Quality metrics such as cash conversion ratio, accrual ratio, interest coverage ratio, Piotroski F-Score, Altman Z-Score, Beneish M-Score and more."
        "Here s quality Refers to company fundamentals and financial statement quality, not data quality, reporting quality, technical signal quality, or product quality."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "When the Agent needs to judge the company s profit quality, financial health, debt solvency, profit content,"
        "Used when dealing with earnings manipulation risk or financial distress risk."
        "If you want to directly get a set of quality indicators for scoring, screening or report generation, bind this tool first."
    ),
    when_not_to_use=(
        "It is not suitable for judging whether the valuation is expensive or not, nor is it suitable for outputting technical indicators such as MA, RSI, and MACD."
        "Not used for data quality inspection, report quality review, technical signal quality or short-term capital flow analysis."
        "If you need the valuation factor, please use get_value_factor_bundle_tool. If you need the technical factor, please use get_technical_factor_bundle_tool."
    ),
    returns=(
        "Returns a JSON string, the structure contains symbol,bundle=quality_core, factors, factor_diagnostics, "
        "factor_warnings、calculation_notes、missing_factors。"
        "factors The key fields include roe, roa, gross_margin, netprofit_margin, debt_to_assets, current_ratio, quick_ratio, cash_ratio,"
        "roic、cash_conversion、accrual_ratio、asset_turnover、gross_profit_to_assets、interest_coverage、inventory_turnover、"
        "receivable_turnover、net_cash_position、piotroski_f_score、altman_z_score、beneish_m_score。"
    ),
    example="get_quality_factor_bundle_tool(symbol='600519')",
    related_tools=[
        "get_value_factor_bundle_tool",
        "get_growth_cashflow_factor_bundle_tool",
        "get_fundamental_factor_snapshot_tool",
    ],
)
def get_quality_factor_bundle_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"]
) -> str:
    """Get a package of standardized quality factors.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Standardized stock code
            name: Stock name
            industry: Industry
            current_price: current price
            report_period: reporting period
            data_source: Data source
            bundle: Factor package identifier, fixed to "quality_core"
            factors: dict quality factor set——
                — roe: ROE
                — roa: return on total assets
                — gross_margin: Gross profit margin
                — netprofit_margin: net profit margin
                — debt_to_assets: Asset-liability ratio
                — assets_to_eqt: equity multiplier
                — current_ratio: current ratio
                — quick_ratio: quick ratio
                — cash_ratio: cash ratio
                — roic: return on invested capital
                — cash_conversion: Cash conversion ratio (operating cash flow/net profit)
                — accrual_ratio: Accrual profit ratio (%)
                — asset_turnover: total asset turnover ratio
                — gross_profit_to_assets: Gross profit/total assets (%)
                — interest_coverage: interest coverage ratio
                — inventory_turnover: Inventory turnover
                — receivable_turnover: Accounts receivable turnover ratio
                — net_cash_position: net cash position
                — piotroski_f_score: Piotroski F-Score
                — altman_z_score: Altman Z-Score
                — beneish_m_score: Beneish M-Score
            factor_diagnostics: dict Factor diagnostic information
            factor_warnings: dict Factor alarm information
            calculation_notes: list[str] Calculation instructions
            missing_factors: list[str] Missing factor list
            message: Error message (only status="error" exist)
    """
    try:
        return _factor_bundle_tools_json_response(get_quality_factor_bundle(symbol))
    except Exception as exc:
        logger.error("Failed to obtain quality factor package: %s", exc, exc_info=True)
        return _factor_bundle_tools_json_response({"status": "error", "message": f"获取质量因子包失败: {exc}"})


@tool
@register_tool(
    tool_id="get_growth_cashflow_factor_bundle_tool",
    name="成长现金流因子包",
    description=(
        "Returns the growth_cashflow_core package of standardized growth/cashflow factors for the stock."
        "Suitable for obtaining year-on-year revenue, year-on-year net profit, year-on-year operating profit, three-year CAGR, TTM revenue, TTM net profit,"
        "Operating cash flow, free cash flow, free cash flow yield, operating cash flow yield, net working capital and other indicators."
        "It can be used to analyze deterioration of cash flow, identify continued decline in operating cash flow, identify long-term negative free cash flow, and judge the quality of cash income."
        "Profit content assessment, financial risk signal identification and growth quality analysis."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["growth_analysis", "cashflow_quality", "cashflow_deterioration", "operating_cashflow", "free_cashflow", "financial_risk"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["cashflow_quality_analysis", "financial_risk_signal_detection", "growth_quality_analysis", "valuation_analysis"],
    when_to_use=(
        "When the Agent needs to judge the company s growth rate, cash flow hematopoietic ability, free cash flow quality,"
        "Whether operating cash flow continues to decline, whether free cash flow is negative for a long time, whether the quality of cash income deteriorates,"
        "Used when working capital changes. Ideal for front-loading growth analysis, cash flow health analysis, cash flow deterioration risk identification, and PEG/growth valuation."
    ),
    when_not_to_use=(
        "It is not suitable for separate valuation multiple comparisons, nor is it suitable for technical timing."
        "The cash flow here is operating/free cash flow based on financial statements and is not used to inquire about main capital flow, northbound capital, transaction capital flow or short-term trading capital."
        "If the target is valuation fields such as PE/PB/dividend rate, use get_value_factor_bundle_tool first."
    ),
    returns=(
        "Returns a JSON string, the structure contains symbol,bundle=growth_cashflow_core, factors, factor_warnings, "
        "calculation_notes、missing_factors。"
        "factors The key fields include revenue_yoy, net_profit_yoy, oper_profit_yoy, revenue_cagr_3y, profit_cagr_3y,"
        "revenue_ttm、net_profit_ttm、n_cashflow_act、fcf、fcf_yield、fcf_margin、ocf_yield、net_working_capital、working_capital_change。"
    ),
    example="get_growth_cashflow_factor_bundle_tool(symbol='600519')",
    related_tools=[
        "get_value_factor_bundle_tool",
        "get_quality_factor_bundle_tool",
        "get_fundamental_factor_snapshot_tool",
    ],
)
def get_growth_cashflow_factor_bundle_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"]
) -> str:
    """Get the standardized growth/cash flow factor package.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Standardized stock code
            name: Stock name
            industry: Industry
            current_price: current price
            report_period: reporting period
            data_source: Data source
            bundle: Factor package identifier, fixed to "growth_cashflow_core"
            factors: dict Growth/cash flow factor set——
                — revenue_yoy: Year-on-year revenue growth rate
                — net_profit_yoy: Net profit year-on-year growth rate
                — oper_profit_yoy: Operating profit year-on-year growth rate
                — revenue_cagr_3y: Revenue for 3 years CAGR
                — profit_cagr_3y: Net profit for 3 years CAGR
                — revenue_ttm: TTM Revenue
                — net_profit_ttm: TTM net profit
                — n_cashflow_act: operating cash flow
                — fcf: free cash flow
                — fcf_yield: Free cash flow yield (%)
                — fcf_margin: Free cash flow margin (%)
                — ocf_yield: Operating cash flow yield (%)
                — total_cur_assets: current assets
                — total_cur_liab: current liabilities
                — net_working_capital: net working capital
                — working_capital_change: working capital changes
            factor_warnings: dict Factor alarm information
            calculation_notes: list[str] Calculation instructions
            missing_factors: list[str] Missing factor list
            message: Error message (only status="error" exist)
    """
    try:
        return _factor_bundle_tools_json_response(get_growth_cashflow_factor_bundle(symbol))
    except Exception as exc:
        logger.error("Failed to obtain growth cash flow factor package: %s", exc, exc_info=True)
        return _factor_bundle_tools_json_response({"status": "error", "message": f"Failed to obtain growth cash flow factor package: {exc}"})


@tool
@register_tool(
    tool_id="get_fundamental_factor_snapshot_tool",
    name="标准化基本面因子快照",
    description=(
        "Returns a snapshot of the total normalized fundamental factors for a single A-share stock."
        "This is an aggregation tool that will provide three factor packages: value_core, quality_core, and growth_cashflow_core at the same time."
        "It is suitable for Agent to obtain most common fundamental indicators after one binding without the need to call multiple tools separately."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "When the Agent needs to obtain a complete snapshot of fundamental factors at one time for comprehensive analysis, report generation, preliminary screening,"
        "Or it can be used later when doing multi-dimensional interpretation in Prompt."
    ),
    when_not_to_use=(
        "If the Agent only cares about a certain type of indicators, it should first bind narrower bundle tools to avoid taking too many irrelevant fields."
        "For example, if you only do valuation, use get_value_factor_bundle_tool, and if you only do financial quality, use get_quality_factor_bundle_tool."
    ),
    returns=(
        "Returns a JSON string, the structure contains symbol, name, industry, current_price, report_period, data_source,"
        "factors、factor_diagnostics、factor_warnings、missing_factors、bundles。"
        "bundles The following groups are grouped by value_core, quality_core, and growth_cashflow_core, which are suitable for direct consumption by Agent."
    ),
    example="get_fundamental_factor_snapshot_tool(symbol='600519')",
    related_tools=[
        "get_value_factor_bundle_tool",
        "get_quality_factor_bundle_tool",
        "get_growth_cashflow_factor_bundle_tool",
    ],
)
def get_fundamental_factor_snapshot_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"]
) -> str:
    """Get a snapshot of normalized fundamental factors.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Standardized stock code
            name: Stock name
            industry: Industry
            current_price: current price
            report_period: reporting period
            data_source: Data source
            factors: dict All factors after combining (value_core + quality_core + growth_cashflow_core) 
            factor_diagnostics: dict Combined factor diagnostic information
            factor_warnings: dict Merged factor alarm information
            missing_factors: list[str] Merged list of missing factors (deduplication sorting)
            bundles: dict three factor package grouping——
                — value_core: dict Value factor package (the structure is the same as that returned by get_value_factor_bundle_tool)
                — quality_core: dict Quality factor package (the structure is the same as that returned by get_quality_factor_bundle_tool)
                — growth_cashflow_core: dict Growth cash flow factor package (the structure is the same as that returned by get_growth_cashflow_factor_bundle_tool)
            message: Error message (only status="error" exist)
    """
    try:
        snapshot = get_fundamental_factor_snapshot(symbol)
        return _factor_bundle_tools_json_response(snapshot)
    except Exception as exc:
        logger.error("Normalized fundamental factor snapshot acquisition failed: %s", exc, exc_info=True)
        return _factor_bundle_tools_json_response({"status": "error", "message": f"获取基本面因子快照失败: {exc}"})


__all__ = [
    "get_value_factor_bundle_tool",
    "get_quality_factor_bundle_tool",
    "get_growth_cashflow_factor_bundle_tool",
    "get_fundamental_factor_snapshot_tool",
]

# === financial_tools ===
"""
Special financial analysis tools

8 segmented financial tools are available:
1. get_income_analysis - Income statement analysis (revenue, profit trends)
2. get_balance_sheet_analysis - Balance Sheet Analysis (Financial Health)
3. get_cashflow_analysis - Cash Flow Statement Analysis
4. get_goodwill_analysis - Goodwill analysis (valuation, impairment risk signals)
5. get_dupont_analysis - DuPont analysis (ROE three-factor/five-factor dismantling)
6. get_dividend_data - Dividend share data
7. get_main_business - Main business composition
8. get_accounts_receivable_risk_analyzer - Three-dimensional analysis of accounts receivable risk (recovery efficiency+Income quality+Provision prudence)
"""

import logging
import asyncio
from typing import Annotated, Optional, Dict, Any, List

from langchain_core.tools import tool
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _get_tushare_provider():
    """Delayed import acquisition Tushare Provider"""
    from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
    return get_tushare_provider()


def _get_mongodb_cache():
    """Lazy Import Gets MongoDB Cache Adapter"""
    try:
        from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
        return get_mongodb_cache_adapter()
    except Exception:
        return None


def _safe_val(val, fmt: str = ",.2f") -> str:
    """安全格式化数值"""
    if val is None or val == "N/A":
        return "N/A"
    try:
        return f"{float(val):{fmt}}"
    except (ValueError, TypeError):
        return str(val)


def _safe_pct(val) -> str:
    """安全格式化百分比"""
    if val is None or val == "N/A":
        return "N/A"
    try:
        return f"{float(val):.2f}%"
    except (ValueError, TypeError):
        return str(val)


def _coerce_float(val) -> Optional[float]:
    if val is None or val in ("N/A", "", "--"):
        return None
    try:
        numeric = float(val)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _resolve_gross_margin_percent(data: Dict[str, Any], indicator_list: List[Dict[str, Any]]) -> Optional[float]:
    for candidate in (data.get('grossprofit_margin'), data.get('gross_margin')):
        numeric = _coerce_float(candidate)
        if numeric is not None and -100 <= numeric <= 100:
            return numeric

    for record in indicator_list or []:
        for candidate in (record.get('grossprofit_margin'), record.get('gross_margin')):
            numeric = _coerce_float(candidate)
            if numeric is not None and -100 <= numeric <= 100:
                return numeric

    return None


def _wan_yi(val) -> str:
    """将数值转为 万/亿 显示"""
    if val is None or val == "N/A":
        return "N/A"
    try:
        v = float(val)
        if abs(v) >= 1e8:
            return f"{v / 1e8:.2f}亿"
        elif abs(v) >= 1e4:
            return f"{v / 1e4:.2f}万"
        else:
            return f"{v:,.2f}"
    except (ValueError, TypeError):
        return str(val)


def _run_async(coro):
    """
    Run asynchronous coroutines in a synchronization context, compatible with main threads and worker threads.

    - If the current thread has a running event loop → in new thread asyncio.run()
    - If the current thread does not have an event loop → direct asyncio.run()
    """
    try:
        asyncio.get_running_loop()
        # The current thread has a running event loop and cannot directly asyncio.run()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result(timeout=30)
    except RuntimeError:
        # The current thread does not have a running event loop and can directly asyncio.run()
        return asyncio.run(coro)


def _get_financial_data_from_cache_or_api(symbol: str, limit: int = 8) -> Optional[Dict[str, Any]]:
    """
    Get complete financial data (with raw_data) from MongoDB cache or Tushare API

    Read the MongoDB stock_financial_data collection first, if not, call the Tushare API.
    Returns the standardized data (including lists such as raw_data.income_statement).
    """
    code6 = str(symbol).replace('.SH', '').replace('.SZ', '').replace('.BJ', '').zfill(6)

    # 1. Try MongoDB caching
    cache = _get_mongodb_cache()
    if cache and cache.use_app_cache:
        doc = cache.get_financial_data(code6)
        if doc and doc.get('raw_data'):
            logger.info(f"💰 [Special finance] Using MongoDB cache: {symbol}")
            return doc

    # 2. tune Tushare API
    try:
        provider = _get_tushare_provider()
        if provider and provider.is_available():
            logger.info(f"📊 [Special finance] Get data from Tushare: {symbol}, limit={limit}")
            data = _run_async(provider.get_financial_data(symbol, limit=limit))
            if data:
                return data
    except Exception as e:
        logger.warning(f"⚠️ [Special finance] Tushare Failed to obtain: {e}")

    return None


# ============================================================
# Tool 1: Income statement analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_income_analysis",
    name="利润表分析",
    description="Analyze the core indicators of stock income statements and multi-period growth trends, and return structured multi-period sequence data of revenue, net profit, gross profit margin, net profit rate, expense ratio, etc.",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_income_analysis(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    periods: Annotated[int, "Number of analysis periods (most recent quarters), default 8"] = 8
) -> str:
    """
    Income statement analysis tools —— Get a stock s revenue, profits and growth trends

    The analysis content includes: operating income, net profit, gross profit margin, net profit rate, expense ratio, etc.
    Supports multi-period (last N quarters) trend display.

    Args:
        ticker: Stock code (e.g. 600519, 000001)
        periods: Number of analysis periods, default 8 (last 8 quarters)

    Returns:
        str: Income statement analysis report (Markdown format)
    """
    logger.info(f"📊 [利润表分析] 分析股票: {ticker}, 期数: {periods}")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=periods)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据，请确认股票代码正确"

        raw = data.get("raw_data", {})
        income_list = raw.get("income_statement", [])
        indicator_list = raw.get("financial_indicators", [])

        lines = [f"# {ticker} 利润表分析\n"]

        # Overview of the latest issue
        lines.append("## 📊 最新一期概览")
        lines.append(f"- **报告期**: {data.get('report_period', 'N/A')}")
        lines.append(f"- **营业收入**: {_wan_yi(data.get('revenue'))}")
        lines.append(f"- **operating income(TTM)**: {_wan_yi(data.get('revenue_ttm'))}")
        lines.append(f"- **归母净利润**: {_wan_yi(data.get('net_profit'))}")
        lines.append(f"- **Net profit attributable to parent company(TTM)**: {_wan_yi(data.get('net_profit_ttm'))}")
        lines.append(f"- **营业利润**: {_wan_yi(data.get('oper_profit'))}")
        lines.append(f"- **营业成本**: {_wan_yi(data.get('oper_cost'))}")
        lines.append(f"- **毛利率**: {_safe_pct(_resolve_gross_margin_percent(data, indicator_list))}")
        lines.append(f"- **净利率**: {_safe_pct(data.get('netprofit_margin'))}")
        lines.append(f"- **研发费用**: {_wan_yi(data.get('rd_exp'))}")
        lines.append("")

        # fee structure
        lines.append("## 💰 费用结构")
        lines.append(f"- **Selling expenses/revenue**: {_safe_pct(data.get('saleexp_to_gr'))}")
        lines.append(f"- **overhead/revenue**: {_safe_pct(data.get('adminexp_of_gr'))}")
        lines.append(f"- **Financial expenses/revenue**: {_safe_pct(data.get('finaexp_of_gr'))}")
        lines.append(f"- **销售成本率**: {_safe_pct(data.get('cogs_of_sales'))}")
        lines.append(f"- **期间费用率**: {_safe_pct(data.get('expense_of_sales'))}")
        lines.append("")

        # multi-period trend
        if income_list and len(income_list) > 1:
            lines.append("## 📈 多期趋势")
            lines.append("| reporting period | operating income | Net profit attributable to parent company | operating profit |")
            lines.append("|--------|----------|------------|----------|")
            for rec in income_list[:periods]:
                period = rec.get('end_date', 'N/A')
                rev = _wan_yi(rec.get('revenue'))
                np_ = _wan_yi(rec.get('n_income_attr_p'))
                op = _wan_yi(rec.get('oper_profit'))
                lines.append(f"| {period} | {rev} | {np_} | {op} |")
            lines.append("")

        # Profitability indicator trends
        if indicator_list and len(indicator_list) > 1:
            lines.append("## 📊 盈利能力趋势")
            lines.append("| reporting period | Gross profit margin | net profit margin | ROE |")
            lines.append("|--------|--------|--------|-----|")
            for rec in indicator_list[:periods]:
                period = rec.get('end_date', 'N/A')
                gm = _safe_pct(_resolve_gross_margin_percent({}, [rec]))
                nm = _safe_pct(rec.get('netprofit_margin'))
                roe = _safe_pct(rec.get('roe'))
                lines.append(f"| {period} | {gm} | {nm} | {roe} |")
            lines.append("")

        lines.append("---")
        lines.append("*Data source: Tushare / MongoDB cache*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Income statement analysis] Execution failed: {e}")
        return f"❌ 利润表分析执行失败: {e}"


# ============================================================
# Tool 2: Balance Sheet Analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_balance_sheet_analysis",
    name="资产负债表分析",
    description="Analyze the asset-liability structure, solvency and financial health of stocks, and structurally return indicators such as asset-liability ratio, current ratio, quick ratio, equity multiplier, etc.",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_balance_sheet_analysis(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    periods: Annotated[int, "Number of analysis periods (most recent quarters), default 8"] = 8
) -> str:
    """
    Balance Sheet Analysis Tools —— Analyze financial health

    Analysis content: asset-liability ratio, current ratio, quick ratio, cash ratio, asset structure, etc.

    Args:
        ticker: Stock code
        periods: Number of analysis periods, default 8

    Returns:
        str: Balance Sheet Analysis Report
    """
    logger.info(f"📊 [Balance Sheet Analysis] Analyze stocks: {ticker}")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=periods)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        raw = data.get("raw_data", {})
        balance_list = raw.get("balance_sheet", [])
        indicator_list = raw.get("financial_indicators", [])

        lines = [f"# {ticker} 资产负债表分析\n"]

        # Latest issue
        lines.append("## 📊 Latest asset and liability status")
        lines.append(f"- **报告期**: {data.get('report_period', 'N/A')}")
        lines.append(f"- **总资产**: {_wan_yi(data.get('total_assets'))}")
        lines.append(f"- **总负债**: {_wan_yi(data.get('total_liab'))}")
        lines.append(f"- **股东权益**: {_wan_yi(data.get('total_equity'))}")
        lines.append(f"- **货币资金**: {_wan_yi(data.get('money_cap'))}")
        lines.append(f"- **应收账款**: {_wan_yi(data.get('accounts_receiv'))}")
        lines.append(f"- **存货**: {_wan_yi(data.get('inventories'))}")
        lines.append(f"- **固定资产**: {_wan_yi(data.get('fix_assets'))}")

        # Goodwill (valid value only when disclosed in annual report)
        goodwill = data.get('goodwill')
        if goodwill is not None and goodwill > 0:
            lines.append(f"- **商誉**: {_wan_yi(goodwill)} | 商誉/净资产: {_safe_pct(goodwill / data.get('total_equity') * 100 if data.get('total_equity') else None)}")
        else:
            lines.append("- **goodwill**: Insufficient data (quarterly reports usually do not disclose goodwill details, it is recommended to check annual report data)")
        lines.append("")

        # Solvency
        lines.append("## 🏦 偿债能力指标")
        lines.append(f"- **资产负债率**: {_safe_pct(data.get('debt_to_assets'))}")
        lines.append(f"- **流动比率**: {_safe_val(data.get('current_ratio'))}")
        lines.append(f"- **速动比率**: {_safe_val(data.get('quick_ratio'))}")
        lines.append(f"- **现金比率**: {_safe_val(data.get('cash_ratio'))}")
        lines.append(f"- **权益乘数**: {_safe_val(data.get('assets_to_eqt'))}")
        lines.append("")

        # Asset structure
        lines.append("## 📊 资产结构")
        lines.append(f"- **流动资产**: {_wan_yi(data.get('total_cur_assets'))}")
        lines.append(f"- **非流动资产**: {_wan_yi(data.get('total_nca'))}")
        lines.append(f"- **Proportion of current assets**: {_safe_pct(data.get('ca_to_assets'))}")
        lines.append(f"- **Proportion of non-current assets**: {_safe_pct(data.get('nca_to_assets'))}")
        lines.append(f"- **流动负债**: {_wan_yi(data.get('total_cur_liab'))}")
        lines.append(f"- **非流动负债**: {_wan_yi(data.get('total_ncl'))}")
        lines.append("")

        # multi-period trend
        if balance_list and len(balance_list) > 1:
            lines.append("## 📈 资产负债趋势")
            lines.append("| reporting period | total assets | total liabilities | Shareholders equity | Monetary funds | goodwill |")
            lines.append("|--------|--------|--------|----------|----------|------|")
            for rec in balance_list[:periods]:
                period = rec.get('end_date', 'N/A')
                ta = _wan_yi(rec.get('total_assets'))
                tl = _wan_yi(rec.get('total_liab'))
                eq = _wan_yi(rec.get('total_hldr_eqy_exc_min_int'))
                mc = _wan_yi(rec.get('money_cap'))
                gw = _wan_yi(rec.get('goodwill'))
                lines.append(f"| {period} | {ta} | {tl} | {eq} | {mc} | {gw} |")
            lines.append("")

        # Solvency Trends
        if indicator_list and len(indicator_list) > 1:
            lines.append("## 📊 偿债能力趋势")
            lines.append("| reporting period | Asset-liability ratio | current ratio | quick ratio |")
            lines.append("|--------|-----------|---------|---------|")
            for rec in indicator_list[:periods]:
                period = rec.get('end_date', 'N/A')
                dta = _safe_pct(rec.get('debt_to_assets'))
                cr = _safe_val(rec.get('current_ratio'))
                qr = _safe_val(rec.get('quick_ratio'))
                lines.append(f"| {period} | {dta} | {cr} | {qr} |")
            lines.append("")

        lines.append("---")
        lines.append("*Data source: Tushare / MongoDB cache*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Balance Sheet Analysis] Execution failed: {e}")
        return f"❌ Balance sheet analysis execution failed: {e}"


# ============================================================
# Tool 3: Cash Flow Statement Analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_cashflow_analysis",
    name="现金流量表分析",
    description=(
        "Analyze a stock s operating/investing/financing cash flows and assess cash flow health."
        "Suitable for cash flow deterioration analysis, identification of continued decline in operating cash flow, identification of negative free cash flow, judgment of cash income quality,"
        "Profit value assessment and financial risk signal investigation."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["cashflow_analysis", "cashflow_quality", "cashflow_deterioration", "operating_cashflow", "free_cashflow", "financial_risk"],
    tool_role_hint="specialized",
    output_shape="markdown_report",
    preferred_for=["cashflow_quality_analysis", "financial_risk_signal_detection", "financial_statement_analysis"],
    when_to_use="Use it when you need to explain the operating/investing/financing cash flow, multi-period cash flow trend, free cash flow, cash flow health, cash flow deterioration risk and profit content in terms of financial statements.",
    when_not_to_use="It is not used for analysis of main capital flow, northbound capital, transaction capital flow or short-term trading capital; these are market capital flows, not financial report cash flows. If you need structured long-term cash flow quality indicators, use get_cashflow_quality_trend_tool first.",
)
def get_cashflow_analysis(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    periods: Annotated[int, "Number of analysis periods (most recent quarters), default 8"] = 8
) -> str:
    """
    Cash Flow Statement Analysis Tools —— Assess cash flow health

    Analysis content: operating cash flow, investment cash flow, financing cash flow, free cash flow, etc.

    Args:
        ticker: Stock code
        periods: Number of analysis periods, default 8

    Returns:
        str: Cash flow statement analysis report
    """
    logger.info(f"📊 [cash flow analysis] Analyze stocks: {ticker}")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=periods)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        raw = data.get("raw_data", {})
        cashflow_list = raw.get("cashflow_statement", [])

        lines = [f"# {ticker} 现金流量表分析\n"]

        # Latest issue
        lines.append("## 📊 最新现金流状况")
        lines.append(f"- **报告期**: {data.get('report_period', 'N/A')}")
        ocf = data.get('n_cashflow_act')
        icf = data.get('n_cashflow_inv_act')
        fcf_val = data.get('n_cashflow_fin_act')
        lines.append(f"- **Net cash flow from operating activities**: {_wan_yi(ocf)}")
        lines.append(f"- **Net cash flow from investing activities**: {_wan_yi(icf)}")
        lines.append(f"- **Net cash flow from financing activities**: {_wan_yi(fcf_val)}")
        lines.append(f"- **Closing cash and equivalents**: {_wan_yi(data.get('c_cash_equ_end_period'))}")
        lines.append(f"- **Opening cash and equivalents**: {_wan_yi(data.get('c_cash_equ_beg_period'))}")
        lines.append("")

        # Simple Free Cash Flow Estimate
        if ocf is not None and icf is not None:
            try:
                free_cf = float(ocf) + float(icf)
                lines.append("## 💡 Free cash flow (simple estimate)")
                lines.append(f"- **free cash flow ≈ operating cash flow + investment cash flow**: {_wan_yi(free_cf)}")
                if free_cf > 0:
                    lines.append("- **judge**: ✅ Free cash flow is positive, and the company s hematopoietic ability is good.")
                else:
                    lines.append("- **judge**: ⚠️ Free cash flow is negative, need to pay attention to financial pressure")
                lines.append("")
            except (ValueError, TypeError):
                pass

        # Cash flow quality analysis
        net_profit = data.get('net_profit')
        if ocf is not None and net_profit is not None:
            try:
                ocf_f = float(ocf)
                np_f = float(net_profit)
                if np_f != 0:
                    ratio = ocf_f / np_f
                    lines.append("## 🔍 现金流质量")
                    lines.append(f"- **Operating cash flow/net profit attributable to parent company**: {ratio:.2f}")
                    if ratio > 1:
                        lines.append("- **judge**: ✅ Excellent cash flow quality (>1) , High profit content")
                    elif ratio > 0.5:
                        lines.append("- **judge**: 🟡 Cash flow quality is average (0.5~1) , Part of the profit has not yet been repaid")
                    else:
                        lines.append("- **judge**: ⚠️ Cash flow quality is weak (<0.5) , Low profit content")
                    lines.append("")
            except (ValueError, TypeError):
                pass

        # multi-period trend
        if cashflow_list and len(cashflow_list) > 1:
            lines.append("## 📈 现金流趋势")
            lines.append("| reporting period | operating cash flow | investment cash flow | Financing cash flow | Ending cash |")
            lines.append("|--------|-----------|-----------|-----------|---------|")
            for rec in cashflow_list[:periods]:
                period = rec.get('end_date', 'N/A')
                o = _wan_yi(rec.get('n_cashflow_act'))
                i = _wan_yi(rec.get('n_cashflow_inv_act'))
                f_ = _wan_yi(rec.get('n_cashflow_fin_act'))
                e = _wan_yi(rec.get('c_cash_equ_end_period'))
                lines.append(f"| {period} | {o} | {i} | {f_} | {e} |")
            lines.append("")

        lines.append("---")
        lines.append("*Data source: Tushare / MongoDB cache*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [cash flow analysis] Execution failed: {e}")
        return f"❌ 现金流分析执行失败: {e}"


# ============================================================
# Tool 4: Goodwill analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_goodwill_analysis",
    name="商誉分析",
    description="Analyze the size, proportion and change trend of goodwill of stocks, and assess the risk of goodwill impairment. Extract the goodwill field from the annual report balance sheet and calculate the goodwill/net assets ratio and year-on-year change.",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_goodwill_analysis(
    ticker: Annotated[str, "Stock code, 6 digits (such as 002230, 600519, 000001)"],
    years: Annotated[int, "Number of years to look back, default is 5 years"] = 5
) -> str:
    """
    Goodwill Analysis Tool —— Assessing goodwill scale and impairment risk

    Extract goodwill from balance sheet annual report data(goodwill)Field, calculation:
    - Carrying amount of goodwill
    - Goodwill/Net Assets Ratio
    - Goodwill/total assets ratio
    - Year-on-year trend (identifying impairment signals)

    ⚠️ Goodwill is only fully disclosed in the annual report (Q4). This tool filters annual report data from raw_data.
    There will be no issue of null values in quarterly reports.

    Args:
        ticker: Stock code (e.g. 002230, 600519)
        years: Number of years to look back, default is 5 years

    Returns:
        str: Goodwill Analysis Report
    """
    logger.info(f"📊 [商誉分析] 分析股票: {ticker}, 回溯{years}年")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=years * 4 + 4)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        raw = data.get("raw_data", {})
        balance_list = raw.get("balance_sheet", [])

        # Filter annual reports: take the last reporting period of each year (end_date contains -12-31 or remove duplicates by year and take the last one)
        annual_records: List[Dict[str, Any]] = []
        seen_years: set = set()
        for rec in balance_list:
            end_date = str(rec.get('end_date', '') or rec.get('f_ann_date', ''))
            if not end_date:
                continue
            # Year of extraction
            year = end_date[:4]
            if year not in seen_years:
                seen_years.add(year)
                annual_records.append(rec)

        # Get the annual report of the most recent years
        annual_records = sorted(annual_records, key=lambda r: str(r.get('end_date', '')), reverse=True)[:years]

        if not annual_records:
            return f"📊 {ticker} There is currently no goodwill data (annual report records are not found in the balance sheet cache, it is recommended to pull the data first)"

        goodwill_by_year: Dict[str, Optional[float]] = {}
        equity_by_year: Dict[str, Optional[float]] = {}
        assets_by_year: Dict[str, Optional[float]] = {}

        for rec in annual_records:
            year = str(rec.get('end_date', ''))[:4] or 'N/A'
            goodwill_by_year[year] = rec.get('goodwill')
            equity_by_year[year] = rec.get('total_hldr_eqy_exc_min_int')
            assets_by_year[year] = rec.get('total_assets')

        lines = [f"# {ticker} 商誉分析\n"]

        # The latest issue of Goodwill Profile
        latest_year = list(goodwill_by_year.keys())[0]
        latest_gw = goodwill_by_year.get(latest_year)
        latest_equity = equity_by_year.get(latest_year)
        latest_assets = assets_by_year.get(latest_year)

        lines.append("## 📊 The latest issue of Goodwill Profile")
        lines.append(f"- **报告年度**: {latest_year}")

        if latest_gw is not None and latest_gw > 0:
            lines.append(f"- **Carrying amount of goodwill**: {_wan_yi(latest_gw)}")
            if latest_equity:
                gw_to_equity = latest_gw / latest_equity * 100
                lines.append(f"- **Goodwill/Net Assets**: {gw_to_equity:.1f}%")
                risk_flag = "🔴 High risk (the ratio of goodwill to net assets is too high, and the pressure for impairment is high)" if gw_to_equity > 20 else ("🟡 关注（商誉占比偏高）" if gw_to_equity > 10 else "🟢 正常")
                lines.append(f"- **风险信号**: {risk_flag}")
            if latest_assets:
                lines.append(f"- **Goodwill/Total Assets**: {latest_gw / latest_assets * 100:.1f}%")
        elif latest_gw is not None and latest_gw == 0:
            lines.append("- **Carrying amount of goodwill**: 0 (The company has no goodwill)")
            lines.append("- **risk signal**: 🟢 No goodwill impairment risk")
        else:
            lines.append("- **Carrying amount of goodwill**: Missing data (the annual report does not disclose the goodwill field)")
            lines.append("- **risk signal**: ⬜ Insufficient data to judge")
        lines.append("")

        # Multi-year trend
        if len(annual_records) > 1:
            lines.append("## 📈 商誉年度趋势")
            lines.append("| reporting year | goodwill | net worth | Goodwill/Net Assets | Goodwill/Total Assets |")
            lines.append("|----------|------|--------|------------|------------|")
            sorted_years = sorted(goodwill_by_year.keys(), reverse=True)
            prev_gw = None
            for year in sorted_years:
                gw = goodwill_by_year.get(year)
                eq = equity_by_year.get(year)
                ta = assets_by_year.get(year)
                gwe = f"{gw / eq * 100:.1f}%" if (gw is not None and eq and eq > 0) else "-"
                gwt = f"{gw / ta * 100:.1f}%" if (gw is not None and ta and ta > 0) else "-"
                lines.append(f"| {year} | {_wan_yi(gw)} | {_wan_yi(eq)} | {gwe} | {gwt} |")

                # Detect significant year-on-year decline (impairment signal)
                if prev_gw is not None and gw is not None and prev_gw > 0 and gw > 0:
                    change = (gw - prev_gw) / prev_gw * 100
                    if change < -20:
                        lines.append(f"  ⚠️ {year}年商誉同比下降 {abs(change):.0f}%，可能存在减值！")
                prev_gw = gw
            lines.append("")

        lines.append("## 🔍 减值风险判读")
        if latest_gw is not None and latest_gw > 0 and latest_equity:
            ratio = latest_gw / latest_equity * 100
            lines.append(f"- 商誉/净资产比率 = {ratio:.1f}%")
            if ratio > 20:
                lines.append("- ⚠️ Exceeding the 20% warning line, impairment has a significant impact on net assets")
                lines.append("- It is recommended to pay attention to: the completion of the target company s performance commitments and changes in industry prosperity")
            elif ratio > 10:
                lines.append("- It is in the 10%-20% attention range and needs to be tracked continuously.")
            else:
                lines.append("- Less than 10%, goodwill impairment has limited impact on net assets")
        lines.append("")

        lines.append("---")
        lines.append("*Data source: Annual report balance sheet (Tushare) | The goodwill field is only fully disclosed in the annual report*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Goodwill analysis] Execution failed: {e}")
        return f"❌ 商誉分析执行失败: {e}"


# ============================================================
# Tool 5: DuPont Analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_dupont_analysis",
    name="杜邦分析",
    description="Conduct DuPont analysis on the stock and break down ROE into three factors (net interest rate×asset turnover rate×equity multiplier) and five factors (tax burden×interest burden×operating profit margin×asset turnover rate×Equity Multiplier), supporting multi-year trend comparisons.",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_dupont_analysis(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001, 002230)"],
    years: Annotated[int, "Number of years to look back, default is 5 years"] = 5
) -> str:
    """
    DuPont Analytical Tools — ROE Three-factor / five-factor decomposition

    Read TTM income statement and balance sheet data from cache and calculate:

    **Three-factor decomposition**: 
    - net profit margin = net profit(TTM) / operating income(TTM)
    - asset turnover rate = operating income(TTM) / total assets
    - equity multiplier = total assets/net assets
    - ROE = net profit margin × asset turnover rate × equity multiplier

    **Five factors breakdown** (Operating profit data required):
    - tax burden factor = Net profit / total profit
    - interest burden = Total profit/operating profit
    - operating profit margin = Operating profit/operating income
    - asset turnover rate = Operating income / total assets
    - equity multiplier = total assets/net assets

    Args:
        ticker: Stock code (e.g. 600519, 002230)
        years: Number of years to look back, default is 5 years

    Returns:
        str: DuPont Analysis Report
    """
    logger.info(f"📊 [杜邦分析] 分析股票: {ticker}, 回溯{years}年")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=years * 4 + 4)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        lines = [f"# {ticker} 杜邦分析\n"]

        # ── Three factor dupont ──
        npm, at, em, roe_3f = None, None, None, None

        revenue = _coerce_float(data.get('revenue_ttm'))
        net_profit = _coerce_float(data.get('net_profit_ttm'))
        total_assets = _coerce_float(data.get('total_assets'))
        total_equity = _coerce_float(data.get('total_equity'))

        if all([net_profit, revenue, total_assets, total_equity]) and revenue != 0 and total_equity != 0:
            npm = net_profit / revenue  # Net interest rate (decimal)
            at = revenue / total_assets   # asset turnover rate
            em = total_assets / total_equity  # equity multiplier
            roe_3f = npm * at * em * 100     # DuPont ROE (percent)
            roe_direct = net_profit / total_equity * 100

            lines.append("## Three-factor breakdown (standard DuPont)\n")
            lines.append("**ROE = net profit margin × asset turnover rate × equity multiplier**\n")
            lines.append("| factor | meaning | numerical value |")
            lines.append("|------|------|------|")
            lines.append(f"| net profit margin | net profit(TTM) / operating income(TTM) | {npm*100:.2f}% |")
            lines.append(f"| 资产周转率 | 营业收入(TTM) / 总资产 | {at:.3f} 次 |")
            lines.append(f"| equity multiplier | total assets/net assets | {em:.2f} |")
            lines.append(f"| **ROE** | Multiplying three factors | **{roe_3f:.2f}%** |")
            lines.append("")
            lines.append(f"- Verification: Direct ROE = Net profit/net assets = {roe_direct:.2f}% ({'✅ consistent' if abs(roe_3f - roe_direct) < 0.1 else '⚠️ Deviation (may be due to rounding)'}) ")
            lines.append("")

            # ROE Quality Tips
            lines.append("### ROE Driver judgment\n")
            parts = []
            if npm and npm * 100 > 15:
                parts.append(f"- 🟢 **Driven by high profit margins**: net profit margin {npm*100:.1f}%, Strong product/brand barriers")
            elif npm and npm * 100 < 3:
                parts.append(f"- 🔴 **low profit margin**: net profit margin only {npm*100:.1f}%, Profit margin is thin")
            else:
                parts.append(f"- 🟡 **medium profit margin**: net profit margin {npm*100:.1f}%")
            if at and at > 1:
                parts.append(f"- 🟢 **Efficient asset turnover**: turnover rate {at:.2f} times, light asset model or efficient operation")
            elif at and at < 0.3:
                parts.append(f"- 🔴 **Asset turnover is slow**: turnover rate only {at:.2f} times, heavy assets or production capacity are not fully utilized")
            if em and em > 3:
                parts.append(f"- 🔴 **High leverage**: equity multiplier {em:.1f}, Financial leverage magnifies returns and risks")
            elif em and em < 1.5:
                parts.append(f"- 🟢 **low leverage**: equity multiplier {em:.1f}, Stable financial structure")
            lines.extend(parts)
            lines.append("")
        else:
            lines.append("## Three-factor breakdown (standard DuPont)\n")
            lines.append("⚠️ There is insufficient data to complete the three-factor disassembly.")
            lines.append(f"  revenue_ttm={revenue}  net_profit_ttm={net_profit}  total_assets={total_assets}  total_equity={total_equity}")
            lines.append("")

        # ── Five Factor DuPont ──
        oper_profit = _coerce_float(data.get('oper_profit'))
        total_profit = _coerce_float(data.get('total_profit'))

        if all([net_profit, total_profit, oper_profit, revenue, total_assets, total_equity]) \
                and revenue != 0 and total_equity != 0 and oper_profit != 0:
            tb = net_profit / total_profit        # tax burden factor
            ib = total_profit / oper_profit       # interest burden
            om = oper_profit / revenue            # operating profit margin
            roe_5f = tb * ib * om * at * em * 100

            lines.append("## Five Factor Breakdown (Extended Dupont)\n")
            lines.append("**ROE = tax burden factor × interest burden × operating profit margin × asset turnover rate × equity multiplier**\n")
            lines.append("| factor | meaning | numerical value |")
            lines.append("|------|------|------|")
            lines.append(f"| tax burden factor | Net profit / total profit | {tb:.3f} ({'income tax rate ' + str(int((1-tb)*100)) + '%' if 0 < tb <= 1 else 'Abnormal'}) |")
            lines.append(f"| interest burden | Total profit/operating profit | {ib:.3f} ({'Low interest erosion' if 0.9 < ib < 1.1 else 'Interest/non-recurring gains and losses have a significant impact'}) |")
            lines.append(f"| operating profit margin | Operating profit/operating income(TTM) | {om*100:.2f}% |")
            lines.append(f"| 资产周转率 | 营业收入(TTM) / 总资产 | {at:.3f} 次 |")
            lines.append(f"| equity multiplier | total assets/net assets | {em:.2f} |")
            lines.append(f"| **ROE** | Multiplying five factors | **{roe_5f:.2f}%** |")
            lines.append("")

            # Evaluation
            qualifiers = []
            if 0.7 <= tb <= 0.9:
                qualifiers.append("税负水平正常")
            if ib > 1.1:
                qualifiers.append("⚠️ interest burden factor > 1, Non-operating income contributes significantly to profits (non-operating income)")
            elif ib < 0.9:
                qualifiers.append("⚠️ interest burden factor < 1, Financial charges/non-recurring losses erode operating profit")
            if om and om > 0.2:
                qualifiers.append("经营利润率优秀")
            if qualifiers:
                lines.append("### 评价\n")
                for q in qualifiers:
                    lines.append(f"- {q}")
                lines.append("")
        elif oper_profit is None:
            lines.append("## Five Factor Breakdown (Extended Dupont)\n")
            lines.append("⚠️ The operating profit data is missing and the five-factor disassembly cannot be completed.")
            lines.append("*If the data source is Tushare and has just been repaired `operate_profit` Field mapping requires re-pulling data.*")
            lines.append("")
        else:
            lines.append("## Five Factor Breakdown (Extended Dupont)\n")
            lines.append("⚠️ The fields required for the five-factor split are abnormal (may have zero values or incomplete data).")
            lines.append("")

        # ── Multi-year trend ──
        raw = data.get("raw_data", {})
        inc_list = raw.get("income_statement", [])
        bs_list = raw.get("balance_sheet", [])

        if inc_list and bs_list:
            # Take annual report data for trends
            annual_inc = {}
            for rec in inc_list:
                end = str(rec.get('end_date', ''))
                if not end:
                    continue
                year = end[:4]
                if year not in annual_inc:
                    annual_inc[year] = rec

            annual_bs = {}
            for rec in bs_list:
                end = str(rec.get('end_date', ''))
                if not end:
                    continue
                year = end[:4]
                if year not in annual_bs:
                    annual_bs[year] = rec

            # Cross alignment
            common_years = sorted(set(annual_inc.keys()) & set(annual_bs.keys()), reverse=True)[:years]

            if len(common_years) >= 2:
                lines.append("## 杜邦因子年度趋势\n")
                lines.append("| annual | net profit margin | asset turnover rate | equity multiplier | ROE |")
                lines.append("|------|--------|------------|----------|-----|")
                for yr in common_years:
                    inc = annual_inc[yr]
                    bs = annual_bs[yr]
                    r = _coerce_float(inc.get('total_revenue') or inc.get('revenue'))
                    n = _coerce_float(inc.get('n_income') or inc.get('n_income_attr_p'))
                    ta = _coerce_float(bs.get('total_assets'))
                    eq = _coerce_float(bs.get('total_hldr_eqy_exc_min_int'))
                    if all([n, r, ta, eq]) and r != 0 and eq != 0:
                        n_pm = n / r * 100
                        a_t = r / ta
                        e_m = ta / eq
                        r_oe = n / eq * 100
                        lines.append(f"| {yr} | {n_pm:.1f}% | {a_t:.3f} | {e_m:.2f} | {r_oe:.2f}% |")
                lines.append("")

        lines.append("---")
        lines.append("*DuPont Analysis — ROE = net profit margin × asset turnover rate × equity multiplier*")
        lines.append("*Data source:Tushare | Calculated based on TTM data*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [DuPont Analysis] Execution failed: {e}")
        return f"❌ 杜邦分析执行失败: {e}"


# ============================================================
# Tool 6: Dividend share data
# ============================================================
@tool
@register_tool(
    tool_id="get_dividend_data",
    name="分红送股数据",
    description="Obtain the historical dividend and share record of the stock, including dividend per share, transfer ratio, dividend rate, etc.",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_dividend_data(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    years: Annotated[int, "Query the dividend records in recent years, default 5"] = 5
) -> str:
    """
    Dividend bonus data tool —— Get historical dividend records and dividend rates

    Analysis content: cash dividend per share, bonus share conversion ratio, dividend year, implementation progress, etc.
    need Tushare 2000+ Points authority.

    Args:
        ticker: Stock code (e.g. 600519, 000001)
        years: Query the dividend records in recent years, the default is 5 years

    Returns:
        str: Dividend share analysis report
    """
    logger.info(f"💰 [分红数据] 查询股票: {ticker}, 最近{years}年")
    try:
        provider = _get_tushare_provider()
        if not provider or not provider.is_available():
            return f"❌ Tushare 服务不可用，无法获取 {ticker} 的分红数据"

        # Call Tushare dividend API (use _run_async compatible worker thread)
        try:
            records = _run_async(provider.get_dividend_data(ticker, limit=years * 3))
        except Exception as e:
            logger.warning(f"⚠️ [Dividend data] Tushare call failed: {e}")
            return f"❌ 获取 {ticker} 分红数据失败: {e}（需要 Tushare 2000+ 积分权限）"

        if not records:
            return f"📊 {ticker} 暂无分红送股记录"

        lines = [f"# {ticker} 分红送股数据\n"]

        # Statistical overview
        implemented = [r for r in records if r.get('div_proc') == '实施']
        total_cash_div = sum(float(r.get('cash_div_tax', 0) or 0) for r in implemented)

        lines.append("## 📊 分红概览")
        lines.append(f"- **总记录数**: {len(records)} 条")
        lines.append(f"- **已实施分红**: {len(implemented)} 次")
        lines.append(f"- **累计每股分红（税前）**: {total_cash_div:.4f} 元")
        lines.append("")

        # Dividend details table
        lines.append("## 💰 分红明细")
        lines.append("| dividend year | Progress | Dividend per share(before tax) | Dividend per share(After tax) | Bonus shares per share | Conversion per share | ex-rights ex-dividend date |")
        lines.append("|---------|------|---------------|---------------|---------|---------|-----------|")
        for rec in records:
            end_date = rec.get('end_date', 'N/A')
            proc = rec.get('div_proc', 'N/A')
            cash_tax = _safe_val(rec.get('cash_div_tax'), ".4f")
            cash_after = _safe_val(rec.get('cash_div'), ".4f")
            stk_bo = _safe_val(rec.get('stk_bo_rate'), ".2f")
            stk_co = _safe_val(rec.get('stk_co_rate'), ".2f")
            ex_date = rec.get('ex_date') or 'N/A'
            lines.append(f"| {end_date} | {proc} | {cash_tax} | {cash_after} | {stk_bo} | {stk_co} | {ex_date} |")
        lines.append("")

        # Dividend trend analysis
        if len(implemented) >= 2:
            lines.append("## 📈 分红趋势")
            cash_vals = [float(r.get('cash_div_tax', 0) or 0) for r in implemented[:years]]
            if all(v > 0 for v in cash_vals):
                if cash_vals[0] >= cash_vals[-1]:
                    lines.append("- **Trend judgment**: ✅ The amount of dividends has generally increased or remained the same, and shareholders have a good awareness of returns.")
                else:
                    lines.append("- **Trend judgment**: 🟡 The amount of dividends has dropped recently, and we need to pay attention to the reasons.")
            elif any(v > 0 for v in cash_vals):
                lines.append("- **Trend judgment**: 🟡 Dividends are discontinuous and there are no cash dividends in some years.")
            else:
                lines.append("- **Trend judgment**: ⚠️ No record of cash dividends in recent years")
            lines.append("")

        lines.append("---")
        lines.append("*Data source: Tushare dividend API (Need 2000+ points authority)*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Dividend data] Execution failed: {e}")
        return f"❌ 分红数据查询失败: {e}"


# ============================================================
# Tool 7: Main business composition
# ============================================================
@tool
@register_tool(
    tool_id="get_main_business",
    name="主营业务构成",
    description="Obtain the main business structure of the stock and analyze the revenue source structure, and return structured data such as revenue proportion, gross profit margin, concentration, etc. by product/region segment",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_main_business(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    periods: Annotated[int, "Number of analysis periods (the most recent reporting periods), default 4"] = 4
) -> str:
    """
    Main business composition tools —— Analyze revenue sources and business structure

    Display the main business revenue structure by product/region dimension.

    Args:
        ticker: Stock code (e.g. 600519, 000001)
        periods: Number of analysis periods, default 4

    Returns:
        str: Main business composition analysis report
    """
    logger.info(f"📊 [Main business] Analyze stocks: {ticker}")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=periods)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        raw = data.get("raw_data", {})
        mainbz_list = raw.get("main_business", [])

        if not mainbz_list:
            return f"📊 {ticker} There is currently no main business composition data (some companies may not have disclosed it yet)"

        lines = [f"# {ticker} 主营业务构成\n"]

        # Group by reporting period
        from collections import defaultdict
        period_groups = defaultdict(list)
        for rec in mainbz_list:
            period = rec.get('end_date', 'N/A')
            period_groups[period].append(rec)

        # Display in descending order of reporting period
        sorted_periods = sorted(period_groups.keys(), reverse=True)

        for idx, period in enumerate(sorted_periods[:periods]):
            items = period_groups[period]
            # By product category and region
            products = [r for r in items if r.get('bz_item') and r.get('bz_sales') is not None]

            if not products:
                continue

            lines.append(f"## 📊 {period} 主营业务构成")

            # Calculate total revenue
            total_sales = sum(float(r.get('bz_sales', 0) or 0) for r in products)

            if total_sales > 0:
                lines.append(f"**总营业收入**: {_wan_yi(total_sales)}\n")
                lines.append("| Business/Products | operating income | operating costs | Gross profit margin | Revenue proportion |")
                lines.append("|----------|---------|---------|--------|---------|")

                # Sort by income
                sorted_items = sorted(products, key=lambda x: float(x.get('bz_sales', 0) or 0), reverse=True)
                for item in sorted_items:
                    name = item.get('bz_item', 'N/A')
                    sales = float(item.get('bz_sales', 0) or 0)
                    cost = float(item.get('bz_cost', 0) or 0)
                    profit = float(item.get('bz_profit', 0) or 0)

                    gm = f"{(profit / sales * 100):.1f}%" if sales > 0 else "N/A"
                    pct = f"{(sales / total_sales * 100):.1f}%" if total_sales > 0 else "N/A"

                    lines.append(f"| {name} | {_wan_yi(sales)} | {_wan_yi(cost)} | {gm} | {pct} |")

                lines.append("")
            else:
                lines.append("- 无有效数据\n")

        lines.append("---")
        lines.append("*Data source: Tushare fina_mainbz / MongoDB cache*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Main business] Execution failed: {e}")
        return f"❌ Main business composition query failed: {e}"


# ============================================================
# Tool 8: Accounts Receivable Risk Analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_accounts_receivable_risk_analyzer",
    name="应收账款风险分析",
    description="Three-dimensional assessment of accounts receivable risk: collection efficiency (turnover days), revenue quality (receivable-revenue growth rate deviation), accrual prudence (credit impairment loss trend), and cross-validation to generate a comprehensive risk rating",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_accounts_receivable_risk_analyzer(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    years: Annotated[int, "Number of years to look back, default is 4 years"] = 4
) -> str:
    """
    Accounts Receivable Risk Analysis Tool —— Three-dimensional cross-validation

    Three dimensions:
    1. Collection efficiency: accounts receivable turnover days and changing trends
    2. Income quality: the deviation between the growth rate of accounts receivable and the growth rate of revenue
    3. Provision prudence: credit impairment losses/changes in accounts receivable, cross comparison of turnover days

    Comprehensive rules:
    - All three are normal → low risk
    - Single deterioration → Follow
    - Deterioration in turnover + Decline in provision → High risk (suspected of whitewashing)
    - All three worsen at the same time → extremely high risk

    Args:
        ticker: Stock code
        years: Look back years

    Returns:
        str: Accounts receivable risk analysis report
    """
    logger.info(f"📊 [应收账款风险分析] 分析股票: {ticker}, 回溯{years}年")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=years * 4 + 4)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        raw = data.get("raw_data", {})
        balance_list = raw.get("balance_sheet", [])
        income_list = raw.get("income_statement", [])
        indicator_list = raw.get("financial_indicators", [])

        # ---- Extract annual report data (get the last record for each year) ----
        def _extract_annual(records: list, fields: list) -> dict:
            """Extract the last record of each year from the quarter list and return {year: {field: value}}"""
            by_year: Dict[str, Dict[str, Any]] = {}
            for rec in records:
                end_date = str(rec.get('end_date', '') or rec.get('f_ann_date', ''))
                if not end_date:
                    continue
                year = end_date[:4]
                # For the same year, take the larger end_date (i.e. annual report)
                if year not in by_year or str(rec.get('end_date', '')) > str(by_year[year].get('end_date', '')):
                    by_year[year] = rec
            # Get the most recent years, in descending order of years
            sorted_years = sorted(by_year.keys(), reverse=True)[:years]
            result = {}
            for y in sorted_years:
                result[y] = {f: _coerce_float(by_year[y].get(f)) for f in fields}
            return result

        # Extract Balance Sheet Annual Report: Accounts Receivable
        ar_annual = _extract_annual(balance_list, ['accounts_receiv'])
        # Extract the income statement annual report: operating income, credit impairment losses
        income_annual = _extract_annual(income_list, ['revenue', 'credit_impa_loss', 'assets_impair_loss'])
        # Extract financial indicators from the annual report: accounts receivable turnover days
        indicator_annual = _extract_annual(indicator_list, ['arturn_days'])

        year_keys = sorted(set(list(ar_annual.keys()) + list(income_annual.keys())), reverse=True)[:years]

        # ---- Jump to missing data ----
        if len(year_keys) < 2:
            return f"📊 {ticker} Insufficient annual report data (requires at least 2 years) to conduct trend analysis"

        # ---- Build a year-by-year data table ----
        records = []
        for y in year_keys:
            ar_val = _coerce_float(ar_annual.get(y, {}).get('accounts_receiv'))
            rev_val = _coerce_float(income_annual.get(y, {}).get('revenue'))
            impa_val = _coerce_float(income_annual.get(y, {}).get('credit_impa_loss'))
            arturn_days_val = _coerce_float(indicator_annual.get(y, {}).get('arturn_days'))

            records.append({
                'year': y,
                'accounts_receiv': ar_val,
                'revenue': rev_val,
                'credit_impa_loss': impa_val,
                'arturn_days': arturn_days_val,
            })

        # ---- Calculate trend indicators ----
        def _safe_ratio(curr, prev) -> Optional[float]:
            if curr is not None and prev is not None and prev != 0:
                return (curr - prev) / abs(prev)
            return None

        # Calculate the turnover days of accounts receivable (self-calculated, verified against arturn_days)
        for i, rec in enumerate(records):
            if rec['accounts_receiv'] and rec['revenue'] and rec['revenue'] != 0:
                rec['ar_turnover_days_self'] = 365 * rec['accounts_receiv'] / rec['revenue']
            else:
                rec['ar_turnover_days_self'] = None

        # Calculate growth rate and deviation
        for i in range(len(records) - 1):
            curr, prev = records[i], records[i + 1]
            curr['ar_growth'] = _safe_ratio(curr['accounts_receiv'], prev['accounts_receiv'])
            curr['rev_growth'] = _safe_ratio(curr['revenue'], prev['revenue'])
            if curr['ar_growth'] is not None and curr['rev_growth'] is not None:
                curr['deviation'] = curr['ar_growth'] - curr['rev_growth']
            else:
                curr['deviation'] = None
            # Provision ratio
            if curr['credit_impa_loss'] is not None and curr['accounts_receiv'] is not None and curr['accounts_receiv'] != 0:
                curr['impa_ratio'] = curr['credit_impa_loss'] / curr['accounts_receiv']
            else:
                curr['impa_ratio'] = None

        # ---- Output report ----
        lines = [f"# {ticker} 应收账款风险三维分析\n"]

        # Overview of the latest issue
        latest = records[0]
        lines.append("## 📊 最新一期快照")
        lines.append(f"- **报告年度**: {latest['year']}")
        lines.append(f"- **应收账款**: {_wan_yi(latest['accounts_receiv'])}")
        lines.append(f"- **营业收入**: {_wan_yi(latest['revenue'])}")
        if latest['arturn_days'] is not None:
            lines.append(f"- **应收账款周转天数** (数据源): {latest['arturn_days']:.1f} 天")
        if latest.get('ar_turnover_days_self') is not None:
            lines.append(f"- **应收账款周转天数** (自算): {latest['ar_turnover_days_self']:.1f} 天")
        if latest.get('ar_growth') is not None:
            lines.append(f"- **应收账款增速**: {latest['ar_growth'] * 100:+.1f}% (同比)")
        if latest.get('rev_growth') is not None:
            lines.append(f"- **营收增速**: {latest['rev_growth'] * 100:+.1f}% (同比)")
        if latest.get('deviation') is not None:
            lines.append(f"- **增速偏离度**: {latest['deviation'] * 100:+.1f} 百分点（正值 = 应收跑赢营收，虚胖信号）")
        if latest.get('impa_ratio') is not None:
            lines.append(f"- **Credit impairment loss/accounts receivable**: {latest['impa_ratio'] * 100:.2f}%")
        lines.append("")

        # Year-by-year trend table
        lines.append("## 📈 逐年趋势")
        header = "| annual | Accounts receivable | operating income | Turnover days(source) | Turnover days(Calculate) | Growth rate of receivables | revenue growth | Deviation | Impairment/receivable |"
        lines.append(header)
        lines.append("|" + "|".join(["------"] * 9) + "|")
        for rec in records:
            ar = _wan_yi(rec['accounts_receiv'])
            rev = _wan_yi(rec['revenue'])
            atd = f"{rec['arturn_days']:.1f}" if rec['arturn_days'] is not None else "-"
            atds = f"{rec.get('ar_turnover_days_self'):.1f}" if rec.get('ar_turnover_days_self') is not None else "-"
            arg = f"{rec.get('ar_growth') * 100:+.1f}%" if rec.get('ar_growth') is not None else "-"
            revg = f"{rec.get('rev_growth') * 100:+.1f}%" if rec.get('rev_growth') is not None else "-"
            dev = f"{rec.get('deviation') * 100:+.1f}pp" if rec.get('deviation') is not None else "-"
            impa = f"{rec.get('impa_ratio') * 100:.2f}%" if rec.get('impa_ratio') is not None else "-"
            lines.append(f"| {rec['year']} | {ar} | {rev} | {atd} | {atds} | {arg} | {revg} | {dev} | {impa} |")
        lines.append("")

        # ---- Three-dimensional cross-risk assessment ----
        lines.append("## 🔍 三维风险评估")

        # Determine the status of each dimension
        def _assess_turnover(rec) -> tuple:
            """Determine the trend of turnover days:(direction, degree)"""
            atd = rec.get('arturn_days')
            if atd is None:
                return ("unknown", "数据缺失")
            # Compare with previous issue
            idx = records.index(rec)
            if idx < len(records) - 1:
                prev_atd = records[idx + 1].get('arturn_days')
                if prev_atd is not None:
                    change_pct = (atd - prev_atd) / prev_atd if prev_atd != 0 else 0
                    if change_pct > 0.15:
                        return ("worsening", f"大幅恶化 (+{change_pct * 100:.0f}%)")
                    elif change_pct > 0.05:
                        return ("worsening", f"轻微恶化 (+{change_pct * 100:.0f}%)")
                    elif change_pct < -0.05:
                        return ("improving", f"改善 ({change_pct * 100:.0f}%)")
                    else:
                        return ("stable", "基本稳定")
            # Absolute value judgment
            if atd > 365:
                return ("worsening", f"严重: {atd:.0f}天 (>1年)")
            elif atd > 180:
                return ("worsening", f"偏高: {atd:.0f}天")
            elif atd > 90:
                return ("stable", f"正常偏高: {atd:.0f}天")
            else:
                return ("stable", f"健康: {atd:.0f}天")

        def _assess_deviation(rec) -> tuple:
            dev = rec.get('deviation')
            if dev is None:
                return ("unknown", "数据缺失")
            if dev > 0.2:
                return ("worsening", f"大幅偏离 (+{dev * 100:.0f}pp)")
            elif dev > 0.1:
                return ("worsening", f"明显偏离 (+{dev * 100:.0f}pp)")
            elif dev > 0.05:
                return ("stable", f"轻微偏离 (+{dev * 100:.0f}pp)")
            else:
                return ("stable", "正常")

        def _assess_provision(rec) -> tuple:
            """Determine the prudence of provision: If the turnover deteriorates but the provision ratio decreases instead → suspected of whitewashing"""
            impa = rec.get('impa_ratio')
            if impa is None:
                # Check if there is assets_impair_loss as an alternative
                return ("unknown", "信用减值损失数据缺失")
            idx = records.index(rec)
            # Current accrual ratio
            curr_ratio = impa
            # Compare with previous issue
            if idx < len(records) - 1:
                prev_rec = records[idx + 1]
                prev_ratio = prev_rec.get('impa_ratio')
                prev_atd = prev_rec.get('arturn_days')
                curr_atd = rec.get('arturn_days')
                if prev_ratio is not None and curr_atd is not None and prev_atd is not None:
                    ratio_change = (curr_ratio - prev_ratio) / prev_ratio if prev_ratio != 0 else 0
                    atd_change = (curr_atd - prev_atd) / prev_atd if prev_atd != 0 else 0
                    # Core logic: turnover deterioration + Decline in provision = suspected of whitewashing
                    if atd_change > 0.05 and ratio_change < -0.1:
                        return ("worsening", f"⚠️ 粉饰嫌疑: 周转恶化({atd_change * 100:+.0f}%)但计提下降({ratio_change * 100:+.0f}%)")
                    elif atd_change > 0.05 and ratio_change > 0.1:
                        return ("stable", f"正常响应: 周转恶化({atd_change * 100:+.0f}%)→计提同步上升({ratio_change * 100:+.0f}%)")
                    elif atd_change < -0.05 and ratio_change < -0.1:
                        return ("stable", "reasonable: Turnover improvement→Decline in provision")
                    else:
                        return ("stable", "基本稳定")
            return ("unknown", "缺少对比数据")

        # The latest assessment
        turnover_status, turnover_detail = _assess_turnover(latest)
        dev_status, dev_detail = _assess_deviation(latest)
        provision_status, provision_detail = _assess_provision(latest)

        # Aggregate signals
        signals = []
        if turnover_status == "worsening":
            signals.append(f"🔴 回收效率: {turnover_detail}")
        elif turnover_status == "stable":
            signals.append(f"🟡 回收效率: {turnover_detail}")
        else:
            signals.append(f"⬜ 回收效率: {turnover_detail}")

        if dev_status == "worsening":
            signals.append(f"🔴 收入质量: {dev_detail}")
        elif dev_status == "stable":
            signals.append(f"🟡 收入质量: {dev_detail}")
        else:
            signals.append(f"⬜ 收入质量: {dev_detail}")

        if provision_status == "worsening":
            signals.append(f"🔴 计提审慎性: {provision_detail}")
        elif provision_status == "stable":
            signals.append(f"🟢 计提审慎性: {provision_detail}")
        else:
            signals.append(f"⬜ 计提审慎性: {provision_detail}")

        for s in signals:
            lines.append(f"- {s}")

        # Overall rating
        worsening_count = sum(1 for status in [turnover_status, dev_status, provision_status] if status == "worsening")
        stable_count = sum(1 for status in [turnover_status, dev_status, provision_status] if status == "stable")
        unknown_count = sum(1 for status in [turnover_status, dev_status, provision_status] if status == "unknown")

        lines.append("")
        lines.append("## 🏷️ 综合风险评级")

        if worsening_count == 0 and unknown_count == 0:
            lines.append("> ✅ **low risk** — All three indicators are normal, and the quality of accounts receivable is healthy.")
        elif worsening_count == 1:
            if turnover_status == "worsening":
                lines.append("> ⚠️ **Concern (recycling deterioration)** — The speed of repayment is declining. Pay attention to the customer s repayment ability and changes in credit policies.")
            elif dev_status == "worsening":
                lines.append("> ⚠️ **Attention (income quality issues)** — The expansion of accounts receivable exceeds revenue growth, and there may be aggressive behavior in revenue recognition.")
            else:
                lines.append("> ⚠️ **Attention (accrual issues)** — Abnormal accrual behavior")
        elif worsening_count == 2:
            if turnover_status == "worsening" and provision_status == "worsening":
                lines.append("> 🔴 **high risk — Suspected of financial whitewashing** — Receipts worsen + Provisions fell instead of rising. The company may be deliberately lowering impairments to beautify profits.")
            elif turnover_status == "worsening" and dev_status == "worsening":
                lines.append("> 🔴 **high risk — double aggravation** — The quality of income has declined and it is difficult to collect payments, and operating cash flow has been under pressure.")
            elif dev_status == "worsening" and provision_status == "worsening":
                lines.append("> 🔴 **high risk — Income puffiness + Insufficient provision** — While receivables are inflated, impairment provisions are insufficient, and the credibility of the income statement is questionable.")
            else:
                lines.append("> 🔴 **high risk** — Two indicators have deteriorated and need to be focused on")
        elif worsening_count == 3:
            lines.append("> 🔴🔴 **extremely high risk — perfect storm** — Recovery, income quality, and accrual are all deteriorating at the same time, so we need to be highly vigilant about the possibility of financial fraud.")
        elif unknown_count >= 2:
            lines.append("> ⬜ **Not enough data** — Key fields are missing and a complete evaluation cannot be completed. It is recommended to check the data source.")
        else:
            lines.append("> 🟡 **Unable to determine** — Please evaluate manually based on specific indicators.")

        lines.append("")
        lines.append("---")
        lines.append("*Description: Growth rate deviation = Receivable growth rate - revenue growth rate, a positive value means that accounts receivable are expanding faster than revenue growth, which is'Wealth on paper'signal*")
        lines.append("*Provision prudence = Credit impairment loss/accounts receivable. When turnover deteriorates, this ratio should rise simultaneously. If it deviates, it will be suspected of whitewashing.*")
        lines.append("*Data source: Tushare / MongoDB cache*")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Accounts Receivable Risk Analysis] Execution failed: {e}", exc_info=True)
        return f"❌ Accounts receivable risk analysis failed: {e}"

# === macro_cycle_tools ===
"""Economic cycle positioning, monetary environment analysis and industry rotation signal tools."""

import datetime
import json
import logging
from statistics import median
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _macro_cycle_tools_get_db():
    """Get a synchronous MongoDB connection."""
    from app.core.database import get_mongo_db_sync

    return get_mongo_db_sync()


def _macro_cycle_tools_safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        text = str(value).strip()
        if not text:
            return None
        numeric = float(text)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _macro_cycle_tools_fetch_zh_us_rate() -> dict:
    """Get the latest data comparing U.S. and Chinese yields with AKShare."""
    try:
        import akshare as ak

        df = ak.bond_zh_us_rate()
        df["日期"] = pd.to_datetime(df["日期"])
        latest = df.sort_values("日期").iloc[-1]
        result: dict = {
            "date": str(latest["日期"].date()),
            "china": {},
            "us": {},
            "spread_cn": {},
            "history": [],
        }
        cn_cols = {
            "中国国债收益率2年": "2年",
            "中国国债收益率5年": "5年",
            "中国国债收益率10年": "10年",
            "中国国债收益率30年": "30年",
        }
        us_cols = {
            "美国国债收益率2年": "2年",
            "美国国债收益率5年": "5年",
            "美国国债收益率10年": "10年",
            "美国国债收益率30年": "30年",
        }
        for raw, name in cn_cols.items():
            v = latest.get(raw)
            if v is not None and v == v:
                result["china"][name] = round(float(v), 4)
        for raw, name in us_cols.items():
            v = latest.get(raw)
            if v is not None and v == v:
                result["us"][name] = round(float(v), 4)
        spread = latest.get("中国国债收益率10年-2年")
        if spread is not None and spread == spread:
            result["spread_cn"]["10Y-2Y"] = round(float(spread), 4)

        # Take the past 3 months of historical records for trend calculations
        three_months_ago = latest["日期"] - pd.DateOffset(months=3)
        hist = df[df["日期"] >= three_months_ago].sort_values("日期")
        hist_records = []
        for _, row in hist.iterrows():
            rec = {"date": str(row["日期"].date())}
            for raw, name in cn_cols.items():
                v = row.get(raw)
                if v is not None and v == v:
                    rec[f"china_{name}"] = round(float(v), 4)
            for raw, name in us_cols.items():
                v = row.get(raw)
                if v is not None and v == v:
                    rec[f"us_{name}"] = round(float(v), 4)
            hist_records.append(rec)
        result["history"] = hist_records

        return result
    except Exception as e:
        logger.warning("AKShare Failed to obtain Sino-US yield: %s", e)
        return {"status": "error", "message": str(e)}


def _fetch_csi300_daily(days: int = 90) -> dict:
    """Get CSI 300-day data through AKShare."""
    try:
        import akshare as ak

        df = ak.stock_zh_index_daily("sh000300")
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        # Get the last N days
        cutoff = df["date"].max() - pd.Timedelta(days=days)
        df = df[df["date"] >= cutoff].copy()
        if df.empty:
            return {"status": "no_data", "message": "沪深300数据为空"}
        records = []
        for _, row in df.iterrows():
            records.append({
                "date": str(row["date"].date()),
                "close": round(float(row["close"]), 2),
            })
        return {
            "status": "ok",
            "latest_date": str(df["date"].max().date()),
            "latest_close": round(float(df["close"].iloc[-1]), 2),
            "records": records,
        }
    except Exception as e:
        logger.warning("AKShare Failed to obtain CSI 300: %s", e)
        return {"status": "error", "message": str(e)}


def _compute_merrill_lynch_clock(
    market_return_3m: float,
    yield_change_3m: float,
) -> dict:
    """Mapping the four quadrants of the Merrill Lynch Clock based on market returns and yield changes.

    Args:
        market_return_3m: CSI 300 return rate in the past 3 months (%)
        yield_change_3m: Changes in China s 10Y yield in the past three months (percentage points)

    Returns:
        Dictionary containing quadrants, recommended assets, signal descriptions
    """
    growth_direction = (
        "high"
        if market_return_3m > 5.0
        else ("low" if market_return_3m < -5.0 else "neutral")
    )
    inflation_direction = (
        "rising"
        if yield_change_3m > 0.2
        else ("falling" if yield_change_3m < -0.2 else "stable")
    )

    # Merrill Lynch Clock Map
    if growth_direction == "high" and inflation_direction == "rising":
        quadrant = "过热"
        recommended_asset = "商品"
        signal_desc = "Economic growth is strong and inflation is rising, making it suitable for allocating commodities and cyclical assets."
    elif growth_direction == "low" and inflation_direction == "rising":
        quadrant = "滞涨"
        recommended_asset = "现金"
        signal_desc = "Economic growth is slowing but inflation is high. Cash is king and defense is the priority."
    elif growth_direction == "low" and inflation_direction == "falling":
        quadrant = "衰退"
        recommended_asset = "债券"
        signal_desc = "The economy contracts, inflation falls, and bonds perform best during periods of falling interest rates."
    elif growth_direction == "high" and inflation_direction == "falling":
        quadrant = "复苏"
        recommended_asset = "股票"
        signal_desc = "The economy resumes growth, inflation is moderate, and equity assets benefit from improved corporate profits."
    else:
        # neutral zone
        quadrant = "过渡/模糊"
        recommended_asset = "均衡配置"
        signal_desc = "The signal is unclear. It is recommended to have a balanced allocation of stocks and bonds."

    return {
        "quadrant": quadrant,
        "recommended_asset_class": recommended_asset,
        "signal_description": signal_desc,
    }


@tool
@register_tool(
    tool_id="get_economic_cycle_position",
    name="经济周期定位",
    description=(
        "Based on the Merrill Lynch clock framework, through the Shanghai and Shenzhen 300 return rate in the past three months (as a growth proxy indicator) and"
        "Changes in China s 10-year government bond yield in the past three months (as a proxy indicator of inflation),"
        "Automatically locate the quadrant of the current economic cycle (recovery/overheating/stagflation/recession),"
        "And give the corresponding recommended asset allocation direction."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["macro", "economic_cycle", "asset_allocation"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["经济周期位置判断", "美林时钟分析", "宏观资产配置参考"],
    when_to_use=(
        "When users ask what cycle stage the current economy is in and which quadrant the Merrill Lynch clock points to,"
        "Should be used when allocating stocks/bonds/commodities/cash. Real-time macro data support is required."
    ),
    when_not_to_use=(
        "Not suitable for inquiries about investment advice on specific industries or individual stocks;"
        "Not suitable as a substitute for detailed macro research reports;"
        "Use get_yield_curve_analysis when you only need Treasury yield data."
    ),
    returns=(
        "Returns a JSON string, including cycle_position (cycle phase positioning),"
        "gdp_proxy (Shanghai and Shenzhen 300 yields in the past three months), inflation_proxy (changes in government bond yields),"
        "quadrant (Merrill Lynch Clock Quadrant), recommended_asset_class (recommended asset class),"
        "data_quality (Data quality description) and other fields."
    ),
    example="get_economic_cycle_position()",
    related_tools=["get_yield_curve_analysis", "get_monetary_environment", "get_macro_dashboard"],
)
def get_economic_cycle_position() -> str:
    """Get Business Cycle Positioning (Merrill Lynch Clock) analysis.

    Obtain real-time CSI 300 Index yield and treasury bond yield data through AKShare,
    Use the simplified Merrill Lynch Clock Framework to determine the current cycle position and recommended asset allocation.

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            analysis_date: Analysis date (YYYY-MM-DD)
            data_source: Data source description
            cycle_position: dict Cycle positioning——
                — quadrant: Merrill Lynch Clock Quadrant
                — recommended_asset_class: Recommended asset classes
                — signal_description: Signal description
            gdp_proxy: dict Growth proxy indicator (CSI 300 return rate in the past 3 months)——
                — label: Indicator label
                — value_pct: Yield (%)
                — direction: direction: "high growth" | "low growth" | "Neutral"
                — threshold_note: Threshold description
            inflation_proxy: dict Inflation proxy indicator (10Y Treasury bond yield changes in the past three months)——
                — label: Indicator label
                — value_change: Yield changes
                — direction: direction: "rise" | "fall" | "Smooth"
                — threshold_note: Threshold description
            current_data: dict current data——
                — csi300_latest_close: CSI 300 latest closing price
                — csi300_latest_date: CSI 300 latest date
                — china_10y_yield: China 10-year yield
                — china_10y_3m_ago: 3 China s 10-year yield months ago
                — us_10y_yield: US 10-year yield
                — cn_us_spread_10y: China-U.S. 10-year interest rate spread
            data_quality: dict Data quality——
                — has_csi300_data: Is there CSI 300 data?
                — has_yield_history: Is there a rate of return history?
                — yield_history_days: Historical data days
                — note: Description text
            message: Error message (only status="error" exist)
    """
    try:
        # 1. Obtain Sino-US yield data (including recent 3-month history)
        rate_data = _macro_cycle_tools_fetch_zh_us_rate()
        if "status" in rate_data and rate_data["status"] == "error":
            return json.dumps({
                "status": "error",
                "message": f"收益率数据获取失败: {rate_data.get('message')}",
            }, ensure_ascii=False, indent=2, default=str)

        # 2. Get Shanghai and Shenzhen 300-day line data
        csi300 = _fetch_csi300_daily(days=120)  # Take more and make sure you have 3 months of data
        if csi300.get("status") != "ok":
            return json.dumps({
                "status": "error",
                "message": f"沪深300数据获取失败: {csi300.get('message')}",
            }, ensure_ascii=False, indent=2, default=str)

        # 3. Calculate the CSI 300 return rate in the past 3 months
        records = csi300.get("records", [])
        if len(records) < 2:
            return json.dumps({
                "status": "error",
                "message": "Insufficient data on the CSI 300 makes it impossible to calculate the rate of return",
            }, ensure_ascii=False, indent=2, default=str)

        latest_close = records[-1]["close"]
        # Find the closing price approximately 90 days ago
        target_date = datetime.datetime.strptime(records[-1]["date"], "%Y-%m-%d") - datetime.timedelta(days=90)
        three_month_ago = None
        for rec in records:
            rec_date = datetime.datetime.strptime(rec["date"], "%Y-%m-%d")
            if rec_date >= target_date:
                three_month_ago = rec["close"]
                break
        if three_month_ago is None:
            three_month_ago = records[0]["close"]

        market_return_3m = round((latest_close - three_month_ago) / three_month_ago * 100, 2)

        # 4. Calculate the changes in China's 10Y yield in the past three months
        history = rate_data.get("history", [])
        china_10y_now = rate_data.get("china", {}).get("10年")
        if china_10y_now is None:
            return json.dumps({
                "status": "error",
                "message": "Missing data on China s 10-year government bond yield",
            }, ensure_ascii=False, indent=2, default=str)

        # Find the 10Y return rate approximately 90 days ago
        china_10y_3m_ago = None
        if history:
            target_dt = datetime.datetime.strptime(rate_data["date"], "%Y-%m-%d") - datetime.timedelta(days=90)
            for hrec in history:
                hrec_date = datetime.datetime.strptime(hrec["date"], "%Y-%m-%d")
                if hrec_date >= target_dt:
                    china_10y_3m_ago = hrec.get("china_10年")
                    break
            if china_10y_3m_ago is None and len(history) > 0:
                china_10y_3m_ago = history[0].get("china_10年")

        if china_10y_3m_ago is not None:
            yield_change_3m = round(china_10y_now - china_10y_3m_ago, 4)
        else:
            yield_change_3m = 0.0

        # 5. Merrill Lynch Clock Positioning
        clock = _compute_merrill_lynch_clock(market_return_3m, yield_change_3m)

        # 6. Build results
        today = datetime.date.today()
        payload = {
            "status": "ok",
            "analysis_date": today.isoformat(),
            "data_source": (
                "The CSI 300 yield rate comes from akshare.stock_zh_index_daily('sh000300'), "
                "Treasury bond yields come from akshare.bond_zh_us_rate()"
            ),
            "cycle_position": {
                "quadrant": clock["quadrant"],
                "recommended_asset_class": clock["recommended_asset_class"],
                "signal_description": clock["signal_description"],
            },
            "gdp_proxy": {
                "label": "Growth proxy indicator - CSI 300 return rate in the past three months",
                "value_pct": market_return_3m,
                "direction": "高增长" if market_return_3m > 5 else ("低增长" if market_return_3m < -5 else "中性"),
                "threshold_note": ">5%For high growth,<-5%for low growth",
            },
            "inflation_proxy": {
                "label": "Inflation proxy indicator - China s 10Y government bond yield changes in the past three months",
                "value_change": yield_change_3m,
                "direction": "上升" if yield_change_3m > 0.2 else ("下降" if yield_change_3m < -0.2 else "平稳"),
                "threshold_note": ">0.2%As inflation rises,<-0.2%for inflation to fall",
            },
            "current_data": {
                "csi300_latest_close": csi300["latest_close"],
                "csi300_latest_date": csi300["latest_date"],
                "china_10y_yield": china_10y_now,
                "china_10y_3m_ago": china_10y_3m_ago,
                "us_10y_yield": rate_data.get("us", {}).get("10年"),
                "cn_us_spread_10y": (
                    round(china_10y_now - rate_data["us"]["10年"], 4)
                    if rate_data.get("us", {}).get("10年") is not None
                    else None
                ),
            },
            "data_quality": {
                "has_csi300_data": len(records) > 1,
                "has_yield_history": len(history) > 1,
                "yield_history_days": len(history),
                "note": (
                    "This tool uses a simplified Merrill Lynch clock model, using the CSI 300 yield rate as a proxy for the direction of economic growth,"
                    "10Y Changes in Treasury yields proxy for the direction of inflation. The actual cycle judgment needs to be combined with formal macro indicators such as CPI, GDP, and PMI."
                ),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("经济周期定位失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


@tool
@register_tool(
    tool_id="get_monetary_environment",
    name="货币环境分析",
    description=(
        "Real-time analysis of the current currency/interest rate environment, based on China and US 10-year Treasury bond yield data,"
        "Including assessment of yield levels (low/medium/high), trend direction in the past 1 month and 3 months,"
        "Comparison of interest rate differentials between China and the United States, and judgment of monetary policy stance (easing/neutral/tightening)."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["macro", "monetary_policy", "interest_rate"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["货币环境评估", "利率走势分析", "中美利差查询"],
    when_to_use=(
        "When a user asks whether the current monetary policy is loose or tight, what level the interest rate is,"
        "Used when looking at trends in Sino-US interest rate spreads and Treasury bond yields."
    ),
    when_not_to_use=(
        "Not suitable for querying specific LPR/MLF operating interest rates (official data from the central bank is required);"
        "Not suitable for querying monetary policy tools such as deposit reserve ratio;"
        "It is not suitable for querying historical long-term series of return data."
    ),
    returns=(
        "Returns a JSON string containing interest_rate_environment (interest rate level/trend assessment),"
        "china_10y_yield (China 10Y yield and changes), us_10y_yield (US 10Y yield and changes),"
        "spread_trend (Sino-US interest rate spread trend), monetary_stance (monetary policy stance judgment),"
        "available_data_sources (Data source description) and other fields."
    ),
    example="get_monetary_environment()",
    related_tools=["get_yield_curve_analysis", "get_economic_cycle_position", "get_macro_dashboard"],
)
def get_monetary_environment() -> str:
    """Get an analysis of the currency environment.

    Obtain Sino-US bond yield data through AKShare and analyze interest rate levels, trends,
    Spreads and policy stances.

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            analysis_date: Analysis date (YYYY-MM-DD)
            data_source: Data source description
            interest_rate_environment: dict interest rate environment——
                — china_10y_level: interest rate level: "low position" | "Neutral" | "high position" | "unknown"
                — china_10y_level_detail: Level details
                — trend_1m: dict Trends in the past month——
                    — change_bps: Change (basis points)
                    — direction: direction: "rise" | "fall" | "Smooth" | "unknown"
                — trend_3m: dict Trend in the past three months (the structure is the same as trend_1m)
            china_10y_yield: dict China 10-year yield——
                — current: current value
                — 1m_ago: 1 months ago
                — 3m_ago: 3 months ago
            us_10y_yield: dict US 10-year yield——
                — current: current value
            spread_trend: dict Interest rate spread trend between China and the United States——
                — cn_us_10y_spread: China-U.S. 10-year interest rate spread
                — note: Description text
            monetary_stance: dict monetary policy stance——
                — stance: stance: "Loose" | "Neutral" | "austerity" | "unknown"
                — description: Position description
                — basis: Judgment basis
            available_data_sources: dict Available data sources——
                — current_data: Current data source
                — not_included: list[str] List of data sources not included
            data_quality: dict Data quality——
                — has_full_history: Is there a complete history?
                — has_china_10y: Is there any China 10Y data?
                — has_us_10y: Is there US 10Y data?
                — history_points: historical data points
            message: Error message (only status="error" exist)
    """
    try:
        rate_data = _macro_cycle_tools_fetch_zh_us_rate()
        if "status" in rate_data and rate_data["status"] == "error":
            return json.dumps({
                "status": "error",
                "message": f"收益率数据获取失败: {rate_data.get('message')}",
            }, ensure_ascii=False, indent=2, default=str)

        today = datetime.date.today()
        china_10y = rate_data.get("china", {}).get("10年")
        us_10y = rate_data.get("us", {}).get("10年")
        history = rate_data.get("history", [])

        # Judgment of interest rate levels (China 10Y historical reference:<2.5%Lower, 2.5%-3.5% neutral,>3.5%higher)
        if china_10y is not None:
            if china_10y < 2.5:
                rate_level = "低位"
                rate_level_note = "China s 10Y government bond yield is below 2.5%, at a historically low range"
            elif china_10y > 3.5:
                rate_level = "高位"
                rate_level_note = "The yield on China s 10Y government bonds is higher than 3.5%, which is at a historically high range"
            else:
                rate_level = "中性"
                rate_level_note = "China s 10Y government bond yield is between 2.5% and 3.5%, which is in the neutral range"
        else:
            rate_level = "未知"
            rate_level_note = "Missing data on China s 10Y government bond yield"

        # Trend calculation (last month and last 3 months)
        trend_1m = None
        trend_3m = None
        china_10y_1m_ago = None
        china_10y_3m_ago = None

        if history and china_10y is not None:
            current_date = datetime.datetime.strptime(rate_data["date"], "%Y-%m-%d")
            target_1m = current_date - datetime.timedelta(days=30)
            target_3m = current_date - datetime.timedelta(days=90)

            for hrec in history:
                hrec_date = datetime.datetime.strptime(hrec["date"], "%Y-%m-%d")
                if china_10y_1m_ago is None and hrec_date >= target_1m:
                    china_10y_1m_ago = hrec.get("china_10年")
                if china_10y_3m_ago is None and hrec_date >= target_3m:
                    china_10y_3m_ago = hrec.get("china_10年")

            if china_10y_1m_ago is None and len(history) > 0:
                china_10y_1m_ago = history[0].get("china_10年")
            if china_10y_3m_ago is None and len(history) > 0:
                china_10y_3m_ago = history[0].get("china_10年")

        if china_10y is not None and china_10y_1m_ago is not None:
            trend_1m = round(china_10y - china_10y_1m_ago, 4)
        if china_10y is not None and china_10y_3m_ago is not None:
            trend_3m = round(china_10y - china_10y_3m_ago, 4)

        def trend_label(chg):
            if chg is None:
                return "未知"
            if chg > 0.1:
                return "上升"
            if chg < -0.1:
                return "下降"
            return "平稳"

        # Interest rate spread between China and the United States
        cn_us_spread = None
        if china_10y is not None and us_10y is not None:
            cn_us_spread = round(china_10y - us_10y, 4)

        # Comprehensive judgment on monetary policy stance
        if china_10y is not None:
            if china_10y < 2.0 or (trend_3m is not None and trend_3m < -0.3):
                monetary_stance = "宽松"
                stance_desc = "Interest rates are at low levels and continue to decline, and monetary policy is loose"
            elif china_10y > 3.5 or (trend_3m is not None and trend_3m > 0.3):
                monetary_stance = "紧缩"
                stance_desc = "Interest rates are at a high level and continue to rise, and monetary policy is tightening"
            else:
                monetary_stance = "中性"
                stance_desc = "Interest rates are at a medium level, with little fluctuation, and monetary policy is neutral."
        else:
            monetary_stance = "未知"
            stance_desc = "数据不足无法判断"

        payload = {
            "status": "ok",
            "analysis_date": today.isoformat(),
            "data_source": "akshare.bond_zh_us_rate()",
            "interest_rate_environment": {
                "china_10y_level": rate_level,
                "china_10y_level_detail": rate_level_note,
                "trend_1m": {
                    "change_bps": round(trend_1m * 100, 2) if trend_1m is not None else None,
                    "direction": trend_label(trend_1m),
                },
                "trend_3m": {
                    "change_bps": round(trend_3m * 100, 2) if trend_3m is not None else None,
                    "direction": trend_label(trend_3m),
                },
            },
            "china_10y_yield": {
                "current": china_10y,
                "1m_ago": china_10y_1m_ago,
                "3m_ago": china_10y_3m_ago,
            },
            "us_10y_yield": {
                "current": us_10y,
            },
            "spread_trend": {
                "cn_us_10y_spread": cn_us_spread,
                "note": (
                    "A positive value indicates that China s yield is higher than that of the United States, and a negative value indicates that China s yield is lower than that of the United States."
                    if cn_us_spread is not None else "数据不足"
                ),
            },
            "monetary_stance": {
                "stance": monetary_stance,
                "description": stance_desc,
                "basis": (
                    "Judgment based on the absolute level of 10Y Treasury bond yields and the trend in the past three months,"
                    "The actual monetary policy stance needs to be comprehensively evaluated based on the central bank s open market operations, LPR, MLF interest rates, etc."
                ),
            },
            "available_data_sources": {
                "current_data": "akshare.bond_zh_us_rate()",
                "not_included": [
                    "LPR (Loan market quoted interest rate) - need to be obtained from the central bank s official website or Oriental Wealth",
                    "MLF (Medium-term lending facility) interest rate - need to be obtained from the central bank s official website",
                    "Deposit reserve ratio - need to be obtained from the central bank s official website",
                    "SHIBOR - Available via akshare",
                ],
            },
            "data_quality": {
                "has_full_history": len(history) > 1,
                "has_china_10y": china_10y is not None,
                "has_us_10y": us_10y is not None,
                "history_points": len(history),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("货币环境分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


def _get_industry_sector_snapshot() -> dict:
    """Get a snapshot of valuations by industry from stock_basic_info."""
    db = _macro_cycle_tools_get_db()
    col = db["stock_basic_info"]

    all_stocks = list(col.find({}, {
        "_id": 0,
        "symbol": 1,
        "name": 1,
        "industry": 1,
        "pe_ttm": 1,
        "pb": 1,
        "pb_mrq": 1,
        "total_mv": 1,
    }))

    # Group by industry
    industry_groups: Dict[str, Dict[str, Any]] = {}
    all_pe: List[float] = []
    all_pb: List[float] = []

    for stock in all_stocks:
        if not stock.get("symbol"):
            continue
        industry = (stock.get("industry") or "未知").strip()

        pe = _macro_cycle_tools_safe_float(stock.get("pe_ttm"))
        if pe is not None and 0 < pe < 1000:
            all_pe.append(pe)

        pb_raw = _macro_cycle_tools_safe_float(stock.get("pb") or stock.get("pb_mrq"))
        if pb_raw is not None and 0 < pb_raw < 100:
            all_pb.append(pb_raw)

        if industry not in industry_groups:
            industry_groups[industry] = {"count": 0, "pe_list": [], "pb_list": [], "total_mv": 0.0}
        industry_groups[industry]["count"] += 1
        if pe is not None and 0 < pe < 1000:
            industry_groups[industry]["pe_list"].append(pe)
        if pb_raw is not None and 0 < pb_raw < 100:
            industry_groups[industry]["pb_list"].append(pb_raw)
        mv = _macro_cycle_tools_safe_float(stock.get("total_mv"))
        if mv is not None:
            industry_groups[industry]["total_mv"] += mv

    # Market-wide median
    market_pe_median = round(median(all_pe), 2) if all_pe else None
    market_pb_median = round(median(all_pb), 2) if all_pb else None

    # Calculate the relative strength of each industry
    sector_results = []
    for industry, data in industry_groups.items():
        pe_med = round(median(data["pe_list"]), 2) if data["pe_list"] else None
        pb_med = round(median(data["pb_list"]), 2) if data["pb_list"] else None

        # Relative strength: The lower the PE is than the market median, the better"value", The higher the"grow"
        relative_strength = 0.0
        if pe_med is not None and market_pe_median is not None and market_pe_median > 0:
            # Negative values indicate relative undervaluation (value type), positive values indicate relative overvaluation (growth type).
            relative_strength = round((market_pe_median - pe_med) / market_pe_median, 4)

        sector_results.append({
            "industry": industry,
            "stock_count": data["count"],
            "pe_median": pe_med,
            "pb_median": pb_med,
            "total_mv_billion": round(data["total_mv"], 2),
            "relative_strength": relative_strength,
            "relative_valuation": (
                "价值" if relative_strength > 0.2
                else ("成长" if relative_strength < -0.2 else "中性")
            ),
        })

    # Sort by relative strength (value first)
    sector_results.sort(key=lambda x: x["relative_strength"], reverse=True)

    return {
        "market_pe_median": market_pe_median,
        "market_pb_median": market_pb_median,
        "total_industries": len(sector_results),
        "total_stocks_tracked": len(all_stocks),
        "sectors": sector_results,
    }


@tool
@register_tool(
    tool_id="get_sector_rotation_signals",
    name="行业轮动信号",
    description=(
        "Industry valuation data and real-time macro cycle signals based on the local database stock_basic_info,"
        "Analyze the relative valuation strength of each industry (PE/PB vs market median),"
        "Identify the current industry rotation stage (value-led/growth-led/defensive rotation/balanced),"
        "And gives ranking suggestions for defensive, cyclical and growth sectors."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["macro", "sector_rotation", "industry_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["行业轮动分析", "板块排名查询", "行业配置建议"],
    when_to_use=(
        "When users ask which industry sectors are currently performing well and what stage of industry rotation they are in,"
        "Use it when configuring cyclical or defensive sectors and industry valuation rankings."
    ),
    when_not_to_use=(
        "Not suitable for querying the valuation or market conditions of specific stocks (please use get_value_factor_bundle_tool or get_stock_fundamentals_unified)."
        "Not suitable for querying the real-time rise and fall of sector indexes (please use get_sector_daily);"
        "Not suitable for querying the list of sector constituents (please use get_sector_constituents)."
    ),
    returns=(
        "Returns a JSON string, including current_cycle_position_data (current cycle data),"
        "sector_ranking (Industry list sorted by relative strength), rotation_phase (rotation phase judgment),"
        "top_defensive (Defensive sectors are recommended), top_cyclical (cyclical sectors are recommended),"
        "data_quality (Data quality description) and other fields."
    ),
    example="get_sector_rotation_signals()",
    related_tools=["get_economic_cycle_position", "get_monetary_environment", "get_macro_dashboard"],
)
def get_sector_rotation_signals() -> str:
    """Get industry rotation signal analysis.

    Combine local industry valuation data and real-time macro cycle signals to determine the industry rotation stage
    And give the relative strength ranking of each industry.

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            analysis_date: Analysis date (YYYY-MM-DD)
            data_source: Data source description
            current_cycle_position_data: dict Current period data (included when real-time data is not available cycle_phase="Unknown (live data is not available)") ——
                — market_return_3m: CSI 300 return rate in the past 3 months
                — china_10y_yield: China 10-year yield
                — cycle_phase: cycle phase: "recovery" | "overheating" | "stagflation" | "recession" | "Transition" | "unknown" | "Unknown (live data is not available)"
            rotation_phase: dict rotation phase——
                — phase: stage: "Growth leads the way" | "Cycle leads the rise" | "defensive rotation" | "Value leads the gains" | "balanced rotation"
                — description: Stage description
                — methodology: Methodological statement
            sector_ranking: list[dict] Industry ranking (top 30), element structure——
                — industry: Industry name
                — stock_count: Number of shares
                — pe_median: PE median
                — pb_median: PB median
                — total_mv_billion: Total market value (100 million yuan)
                — relative_strength: relative strength
                — relative_valuation: relative valuation: "value" | "grow" | "Neutral"
            market_valuation_context: dict market valuation context——
                — market_pe_median: Market PE median
                — market_pb_median: Market PB Median
                — total_industries: Total number of industries
                — total_stocks_tracked: Total number of stocks tracked
            top_defensive: list[dict] Recommend defensive sectors (the structure is the same as sector_ranking element)
            top_cyclical: list[dict] Recommended cyclical sectors (the structure is the same as sector_ranking element)
            data_quality: dict Data quality——
                — industry_count: Number of industries
                — defensive_found: Number of defensive tiles found
                — cyclical_found: Number of cyclical sectors found
                — cycle_data_available: Is there real-time cycle data?
                — note: Description text
            message: Error message (only status="error" exist)
    """
    try:
        today = datetime.date.today()

        # 1. Get a snapshot of industry valuations
        snapshot = _get_industry_sector_snapshot()
        sectors = snapshot.get("sectors", [])

        # 2. Try to obtain real-time periodic signals (non-blocking, failure will not affect industry data)
        cycle_info = None
        try:
            import akshare as ak

            rate_df = ak.bond_zh_us_rate()
            rate_df["日期"] = pd.to_datetime(rate_df["日期"])
            latest_rate = rate_df.sort_values("日期").iloc[-1]
            china_10y = _macro_cycle_tools_safe_float(latest_rate.get("中国国债收益率10年"))

            # CSI 300 return rate in the past 3 months
            idx_df = ak.stock_zh_index_daily("sh000300")
            idx_df["date"] = pd.to_datetime(idx_df["date"])
            idx_df = idx_df.sort_values("date")
            if len(idx_df) >= 2:
                latest_close = float(idx_df["close"].iloc[-1])
                three_m_ago = float(idx_df["close"].iloc[0])
                mkt_return = round((latest_close - three_m_ago) / three_m_ago * 100, 2)
            else:
                mkt_return = None

            # Simple cycle judgment
            if mkt_return is not None and china_10y is not None:
                if mkt_return > 5:
                    if china_10y > 3.0:
                        cycle_phase = "过热"
                    else:
                        cycle_phase = "复苏"
                elif mkt_return < -5:
                    if china_10y > 3.0:
                        cycle_phase = "滞涨"
                    else:
                        cycle_phase = "衰退"
                else:
                    cycle_phase = "过渡"
            else:
                cycle_phase = "未知"

            cycle_info = {
                "market_return_3m": mkt_return,
                "china_10y_yield": china_10y,
                "cycle_phase": cycle_phase,
            }
        except Exception as e:
            logger.debug("Failed to obtain cycle data, only industry valuation data is used: %s", e)
            cycle_info = {"cycle_phase": "未知（实时数据不可用）"}

        # 3. Determine the rotation stage
        # Identifying rotation stages based on industry valuation distribution characteristics
        top_value = [s for s in sectors[:10] if s.get("relative_valuation") == "价值"]
        top_growth = [s for s in sectors[-10:] if s.get("relative_valuation") == "成长"]
        defensive_industries = {"银行", "公用事业", "食品饮料", "医药生物", "交通运输", "保险"}
        cyclical_industries = {"有色金属", "钢铁", "煤炭", "基础化工", "建筑材料", "房地产", "机械设备"}

        value_score = len(top_value)  # Number of value sectors
        growth_score = len(top_growth)  # Number of growth sectors

        if cycle_info and isinstance(cycle_info, dict):
            cycle_phase = cycle_info.get("cycle_phase", "")
            if cycle_phase == "复苏":
                rotation_phase = "成长领涨"
                rotation_desc = "During economic recovery, growth and high-beta sectors usually outperform"
            elif cycle_phase == "过热":
                rotation_phase = "周期领涨"
                rotation_desc = "During periods of economic overheating, cyclical sectors (resources, raw materials) usually lead the way."
            elif cycle_phase == "滞涨":
                rotation_phase = "防御轮动"
                rotation_desc = "During stagflation, defensive sectors (utilities, pharmaceuticals, consumer staples) usually outperform"
            elif cycle_phase == "衰退":
                rotation_phase = "防御轮动"
                rotation_desc = "During recessions, defensive sectors and bond-related assets often outperform"
            else:
                # Inference based on valuation data
                if value_score > growth_score + 3:
                    rotation_phase = "价值领涨"
                    rotation_desc = "The relative strength of the value sector is outstanding, and the market favors low valuation defense"
                elif growth_score > value_score + 3:
                    rotation_phase = "成长领涨"
                    rotation_desc = "The relative strength of growth sectors is outstanding, and the market prefers high growth"
                else:
                    rotation_phase = "均衡轮动"
                    rotation_desc = "The relative strengths of value and growth sectors are close, and the market has no obvious preference."
        else:
            if value_score > growth_score + 3:
                rotation_phase = "价值领涨"
                rotation_desc = "The relative strength of the value sector is outstanding, and the market favors low valuation defense"
            elif growth_score > value_score + 3:
                rotation_phase = "成长领涨"
                rotation_desc = "The relative strength of growth sectors is outstanding, and the market prefers high growth"
            else:
                rotation_phase = "均衡轮动"
                rotation_desc = "The relative strengths of value and growth sectors are close, and the market has no obvious preference."

        # 4. Identify defensive and cyclical sector recommendations
        def _filter_by_industry_list(sectors_list: List[dict], industry_set: set) -> List[dict]:
            return [
                s for s in sectors_list
                if s["industry"] in industry_set and s["relative_strength"] is not None
            ]

        top_defensive = sorted(
            _filter_by_industry_list(sectors, defensive_industries),
            key=lambda x: x["relative_strength"],
            reverse=True,
        )[:5]

        top_cyclical = sorted(
            _filter_by_industry_list(sectors, cyclical_industries),
            key=lambda x: x["relative_strength"],
            reverse=True,
        )[:5]

        # 5. Build return results (only the first 30 industries are returned to control output size)
        payload = {
            "status": "ok",
            "analysis_date": today.isoformat(),
            "data_source": (
                "Industry valuation data comes from the local database stock_basic_info collection,"
                "The periodic signal comes from akshare.bond_zh_us_rate() / stock_zh_index_daily()"
            ),
            "current_cycle_position_data": cycle_info,
            "rotation_phase": {
                "phase": rotation_phase,
                "description": rotation_desc,
                "methodology": (
                    "Comprehensive judgment based on macro cycle stage (if any) and industry relative valuation distribution."
                    "Defensive sector reference: banking, public utilities, food and beverages, pharmaceuticals and biology, transportation, and insurance;"
                    "Cyclical sector reference: non-ferrous metals, steel, coal, basic chemicals, building materials, real estate, machinery and equipment."
                ),
            },
            "sector_ranking": sectors[:30],  # Top 30 industries
            "market_valuation_context": {
                "market_pe_median": snapshot.get("market_pe_median"),
                "market_pb_median": snapshot.get("market_pb_median"),
                "total_industries": snapshot.get("total_industries"),
                "total_stocks_tracked": snapshot.get("total_stocks_tracked"),
            },
            "top_defensive": top_defensive,
            "top_cyclical": top_cyclical,
            "data_quality": {
                "industry_count": len(sectors),
                "defensive_found": len(top_defensive),
                "cyclical_found": len(top_cyclical),
                "cycle_data_available": isinstance(cycle_info, dict) and cycle_info.get("cycle_phase") != "未知（实时数据不可用）",
                "note": (
                    "Industry rankings are based on the deviation of PE/PB from the market median,"
                    "It only reflects the relative strength signal at the valuation level and does not constitute investment advice."
                    "The actual rotation also needs to be combined with comprehensive judgments such as capital flow, policy catalysis, and prosperity."
                ),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Industry rotation signal analysis failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_economic_cycle_position",
    "get_monetary_environment",
    "get_sector_rotation_signals",
]

# === macro_tools ===
"""Macro dashboard and yield curve analysis tools."""

import datetime
import json
import logging
from statistics import median
from typing import Any, Dict, List, Optional

import pandas as pd
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _macro_tools_get_db():
    """Get a synchronous MongoDB connection."""
    from app.core.database import get_mongo_db_sync

    return get_mongo_db_sync()


def _macro_tools_safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        text = str(value).strip()
        if not text:
            return None
        numeric = float(text)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _get_market_pe_pb_distribution() -> Dict[str, Any]:
    """Statistics on market-wide PE/PB distribution from stock_basic_info."""
    db = _macro_tools_get_db()
    col = db["stock_basic_info"]

    all_stocks = list(col.find({}, {
        "_id": 0,
        "symbol": 1,
        "name": 1,
        "industry": 1,
        "pe_ttm": 1,
        "pb": 1,
        "pb_mrq": 1,
        "total_mv": 1,
    }))

    pe_values: List[float] = []
    pb_values: List[float] = []
    industry_stats: Dict[str, List[float]] = {}
    total_tracked = 0

    for stock in all_stocks:
        if not stock.get("symbol"):
            continue
        total_tracked += 1

        pe = _macro_tools_safe_float(stock.get("pe_ttm"))
        if pe is not None and 0 < pe < 1000:
            pe_values.append(pe)

        pb_raw = _macro_tools_safe_float(stock.get("pb") or stock.get("pb_mrq"))
        if pb_raw is not None and 0 < pb_raw < 100:
            pb_values.append(pb_raw)

        industry = (stock.get("industry") or "未知").strip()
        if industry not in industry_stats:
            industry_stats[industry] = []
        if pe is not None and 0 < pe < 1000:
            industry_stats[industry].append(pe)

    return {
        "total_tracked": total_tracked,
        "pe": {
            "count": len(pe_values),
            "avg": round(sum(pe_values) / len(pe_values), 2) if pe_values else None,
            "median": round(median(pe_values), 2) if pe_values else None,
            "min": round(min(pe_values), 2) if pe_values else None,
            "max": round(max(pe_values), 2) if pe_values else None,
        },
        "pb": {
            "count": len(pb_values),
            "avg": round(sum(pb_values) / len(pb_values), 2) if pb_values else None,
            "median": round(median(pb_values), 2) if pb_values else None,
            "min": round(min(pb_values), 2) if pb_values else None,
            "max": round(max(pb_values), 2) if pb_values else None,
        },
        "industry_count": len(industry_stats),
    }


@tool
@register_tool(
    tool_id="get_macro_dashboard",
    name="宏观仪表盘",
    description=(
        "Return to the market macro overview dashboard, including market valuation distribution (PE/PB) and macro indicator slots (CPI/GDP/PMI/Interest Rate)"
        "and market breadth statistics. Macro indicators need to be supplemented from external sources."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["macro", "market_overview"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["市场整体估值概览", "宏观数据框架查询"],
    when_to_use=(
        "Use it when you need to quickly understand the full market valuation level, PE/PB distribution, and overall market width."
        "This tool provides market statistics available from a local database, as well as a list of macro indicators that need to be populated externally."
    ),
    when_not_to_use=(
        "Not suitable for querying the fundamentals or financial data of specific stocks;"
        "Not suitable for obtaining real-time CPI/GDP/PMI actual values (these need to be supplemented by external data sources)."
    ),
    returns=(
        "Returns a JSON string, including market_overview (full market valuation statistics),"
        "indicator_slots (Macro indicator occupancy, status is pending_external_data),"
        "market_breadth (Market breadth, including data source description)."
    ),
    example="get_macro_dashboard()",
    related_tools=["get_yield_curve_analysis", "get_sector_performance"],
)
def get_macro_dashboard() -> str:
    """Get a macro overview of the market dashboard.

    Returns market-wide PE/PB statistics, as well as a macro indicator framework that needs to be supplemented by external data sources.

    Returns:
        str: JSON String, field description——
            dashboard_date: Dashboard date (YYYY-MM-DD)
            data_source_note: Data source description
            market_overview: dict Market overview——
                — total_stocks_tracked: Total number of stocks tracked
                — pe_ttm_distribution: dict PE_TTM Distribution (avg/median/min/max/valid_samples)
                — pb_distribution: dict PB Distribution (avg/median/min/max/valid_samples)
                — industry_coverage: dict Industry coverage (total_industries)
            indicator_slots: dict Macro indicator occupancy, each indicator structure——
                — label: Indicator name
                — status: status (fixed to "pending_external_data") 
                — suggested_source: Suggested data sources
                — note: Description
                contains key: cpi / gdp / pmi / interest_rates
            market_breadth: dict market breadth——
                — status: status (fixed to "partial_data") 
                — note: Description
                — available_from_system: list[str] System available data sources
            suggested_external_sources: dict Suggested external data sources (akshare/tushare/eastmoney)
            status: Status (only when abnormal) "error") 
            message: Error message (only status="error" exist)
    """
    try:
        today = datetime.date.today()
        market_stats = _get_market_pe_pb_distribution()

        dashboard = {
            "dashboard_date": today.isoformat(),
            "data_source_note": (
                "The following market_overview is a statistics snapshot from the local database stock_basic_info collection,"
                "Reflects the system-synchronized A-share market-wide PE/PB distribution."
                "indicator_slots The macro indicators in need to be obtained from external data sources (such as Oriental Fortune, National Bureau of Statistics API)."
            ),
            "market_overview": {
                "total_stocks_tracked": market_stats["total_tracked"],
                "pe_ttm_distribution": {
                    "avg": market_stats["pe"]["avg"],
                    "median": market_stats["pe"]["median"],
                    "min": market_stats["pe"]["min"],
                    "max": market_stats["pe"]["max"],
                    "valid_samples": market_stats["pe"]["count"],
                },
                "pb_distribution": {
                    "avg": market_stats["pb"]["avg"],
                    "median": market_stats["pb"]["median"],
                    "min": market_stats["pb"]["min"],
                    "max": market_stats["pb"]["max"],
                    "valid_samples": market_stats["pb"]["count"],
                },
                "industry_coverage": {
                    "total_industries": market_stats["industry_count"],
                },
            },
            "indicator_slots": {
                "cpi": {
                    "label": "consumer price index (CPI)",
                    "status": "pending_external_data",
                    "suggested_source": "National Bureau of Statistics/Oriental Fortune Macroeconomic Data",
                    "note": "External API is required to supplement monthly CPI year-on-year/month-on-month data",
                },
                "gdp": {
                    "label": "国内生产总值 (GDP)",
                    "status": "pending_external_data",
                    "suggested_source": "National Bureau of Statistics/Oriental Fortune Macroeconomic Data",
                    "note": "External API is needed to supplement quarterly GDP year-on-year/cumulative growth rate",
                },
                "pmi": {
                    "label": "purchasing managers index (PMI)",
                    "status": "pending_external_data",
                    "suggested_source": "National Bureau of Statistics/Oriental Fortune Macroeconomic Data",
                    "note": "Requires external API to supplement manufacturing/non-manufacturing industries PMI",
                },
                "interest_rates": {
                    "label": "interest rate (LPR/MLF/Treasury yield)",
                    "status": "pending_external_data",
                    "suggested_source": "People s Bank of China / China Money Network / Oriental Fortune",
                    "note": "External API is needed to supplement LPR, MLF interest rates and government bond yield curves",
                },
            },
            "market_breadth": {
                "status": "partial_data",
                "note": (
                    "Market breadth statistics (number of rising and falling stocks, proportion above MA50, etc.) require full calculation of daily data."
                    "The current system has not pre-aggregated this statistics. Can be supplemented by external data sources or downstream queries."
                ),
                "available_from_system": [
                    "Daily quotes of a single stock (get_stock_daily_quotes)",
                    "Industry valuation summary (summarize_industry_valuation)",
                    "Market-wide PE/PB distribution (provided by this tool)",
                ],
            },
            "suggested_external_sources": {
                "akshare": "Macroeconomic indicators and bond yield data are available through akshare",
                "tushare": "Macroeconomic indicators can be obtained through tushare (points required)",
                "eastmoney": "东方财富宏观经济数据接口",
            },
        }

        return json.dumps(dashboard, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Failed to obtain macro dashboard: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


def _macro_tools_fetch_china_yield_curve() -> dict:
    """Get the latest data on China s government bond yield curve via AKShare."""
    try:
        import akshare as ak
        df = ak.bond_china_yield()
        # Filter"ChinaBond Treasury Bond Yield Curve"
        treasury = df[df["曲线名称"] == "中债国债收益率曲线"]
        if treasury.empty:
            return {"status": "no_data", "message": "未找到国债收益率曲线数据"}
        # Get the latest date
        treasury["日期"] = pd.to_datetime(treasury["日期"])
        latest = treasury.loc[treasury["日期"].idxmax()]
        yields = {}
        for col in ["3月", "6月", "1年", "3年", "5年", "7年", "10年", "30年"]:
            val = latest.get(col)
            if val is not None and val == val:
                yields[col] = round(float(val), 4)
            else:
                yields[col] = None
        return {
            "status": "ok",
            "date": str(latest["日期"].date()),
            "yields": yields,
        }
    except Exception as e:
        logger.warning("AKShare Failed to obtain treasury bond yield: %s", e)
        return {"status": "error", "message": str(e)}


def _macro_tools_fetch_zh_us_rate() -> dict:
    """Get the latest data comparing U.S. and Chinese yields with AKShare."""
    try:
        import akshare as ak
        df = ak.bond_zh_us_rate()
        df["日期"] = pd.to_datetime(df["日期"])
        latest = df.sort_values("日期").iloc[-1]
        result = {
            "date": str(latest["日期"].date()),
            "china": {},
            "us": {},
            "spread_cn": {},
        }
        cn_cols = {"中国国债收益率2年": "2年", "中国国债收益率5年": "5年",
                    "中国国债收益率10年": "10年", "中国国债收益率30年": "30年"}
        us_cols = {"美国国债收益率2年": "2年", "美国国债收益率5年": "5年",
                    "美国国债收益率10年": "10年", "美国国债收益率30年": "30年"}
        for raw, name in cn_cols.items():
            v = latest.get(raw)
            if v is not None and v == v:
                result["china"][name] = round(float(v), 4)
        for raw, name in us_cols.items():
            v = latest.get(raw)
            if v is not None and v == v:
                result["us"][name] = round(float(v), 4)
        spread = latest.get("中国国债收益率10年-2年")
        if spread is not None and spread == spread:
            result["spread_cn"]["10Y-2Y"] = round(float(spread), 4)
        return result
    except Exception as e:
        logger.warning("AKShare Failed to obtain Sino-US yield: %s", e)
        return {"status": "error", "message": str(e)}


@tool
@register_tool(
    tool_id="get_yield_curve_analysis",
    name="收益率曲线分析",
    description=(
        "Get real-time data on China s government bond yield curve through akshare,"
        "Including the yield to maturity of government bonds of various maturities (3 months/6 months/1 year/3 years/5 years/7 years/10 years/30 years),"
        "10Y-2Y Term spreads and yield comparison between China and the United States. It also provides curve shape judgment."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["macro", "yield_curve", "interest_rate"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["国债收益率查询", "收益率曲线形态判断", "中美利差对比"],
    when_to_use=(
        "When users ask about the current level of government bond yields, the shape of the yield curve (normal/inverted/flat),"
        "Used when comparing Sino-US interest rate spreads and term interest rate spreads (10Y-2Y)."
    ),
    when_not_to_use=(
        "Not suitable for querying the yield or valuation data of individual bonds (single bonds);"
        "It is not suitable for querying historical return series (if you need a long-term series, please use akshare directly)."
    ),
    returns=(
        "Returns a JSON string, including yield_curve (the yield of each maturity of Chinese government bonds),"
        "date (Data date), curve_shape (curve shape judgment),"
        "key_spreads (Key spreads), zh_us_comparison (Comparison between China and the United States)."
    ),
    example="get_yield_curve_analysis()",
    related_tools=["get_macro_dashboard", "get_bond_yield_calculation", "get_monetary_environment", "get_credit_spread_analysis"],
)
def get_yield_curve_analysis() -> str:
    """Get real-time analysis of China s government bond yield curve.

    Obtain ChinaBond treasury bond yield curve data through AKShare, including yields of each maturity,
    Judgment of curve shape, term spread and comparison between China and the United States.

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            date: Data date (YYYY-MM-DD)
            data_source: Data source description
            yield_curve: dict The yield rate of each term (key is "3 month"/"6 month"/"1 year"/"3 year"/"5 year"/"7 year"/"10 year"/"30 year") 
            curve_shape: curve shape: "normal upward tilt" | "hanging upside down" | "flat" | "Insufficient data to determine"
            key_spreads: dict Key spread (key such as "10Y-1Y"/"10Y-3Y"/"10Y-5Y") 
            zh_us_comparison: dict Comparison of U.S. and Chinese yields (when data are not available) {"status": "unavailable", "message": ...}) ——
                — date: Date
                — china: dict Yields of various terms in China
                — us: dict U.S. yields by maturity
                — spread_cn: dict China term spread (such as 10Y-2Y)
            data_note: Data annotation
            message: Error message (only status="error" exist)
            suggestion: Suggestions (only some error scenarios exist)
    """
    try:
        curve = _macro_tools_fetch_china_yield_curve()
        zh_us = _macro_tools_fetch_zh_us_rate()

        if curve.get("status") == "error":
            return json.dumps({
                "status": "error",
                "message": f"国债收益率数据获取失败: {curve.get('message')}",
                "suggestion": "Passable akshare.bond_china_yield() Get it directly",
            }, ensure_ascii=False, indent=2, default=str)

        yields = curve.get("yields", {})
        date = curve.get("date", "未知")

        # Determine curve shape
        y1 = yields.get("1年")
        y10 = yields.get("10年")
        y2 = yields.get("3月")
        if y10 is not None and y1 is not None:
            if y10 > y1 + 0.5:
                curve_shape = "正常向上倾斜"
            elif y10 < y1 - 0.1:
                curve_shape = "倒挂"
            else:
                curve_shape = "平坦"
        else:
            curve_shape = "数据不足无法判断"

        # key spread
        spreads = {}
        if y10 is not None and yields.get("1年") is not None:
            spreads["10Y-1Y"] = round(y10 - yields["1年"], 4)
        if y10 is not None and yields.get("3年") is not None:
            spreads["10Y-3Y"] = round(y10 - yields["3年"], 4)
        if y10 is not None and yields.get("5年") is not None:
            spreads["10Y-5Y"] = round(y10 - yields["5年"], 4)

        payload = {
            "status": "ok",
            "date": date,
            "data_source": "akshare.bond_china_yield() / bond_zh_us_rate()",
            "yield_curve": yields,
            "curve_shape": curve_shape,
            "key_spreads": spreads,
            "zh_us_comparison": zh_us if "status" not in zh_us else {
                "status": "unavailable",
                "message": zh_us.get("message", ""),
            },
            "data_note": "The curve is based on the latest data of ChinaBond Treasury Bond Yield Curve, the unit is percentage (%)",
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Yield curve analysis fails: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_macro_dashboard", "get_yield_curve_analysis"]

# === management_assessment ===
"""Management evaluation data acquisition tool - A-share audit opinions, information disclosure ratings, equity incentives, violation penalties

stk_audit / disclosure_rating / equity_incentive / stk_penalty interface based on Tushare Provider
"""

import asyncio
import json
import logging
import threading
from typing import Optional

from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _ticker_to_ts_code(ticker: str) -> str:
    """Convert general ticker to Tushare ts_code format"""
    ticker = str(ticker).strip()
    if "." in ticker:
        return ticker  # Already in ts_code format
    # Pure numbers, judged based on the market
    if ticker.startswith("6"):
        return f"{ticker}.SH"
    elif ticker.startswith(("0", "3")):
        return f"{ticker}.SZ"
    return f"{ticker}.SH"


def _run_async_in_thread(coro, timeout: int = 30):
    """在独立线程中运行异步协程"""
    container = {"result": None, "error": None}

    def _run():
        try:
            container["result"] = asyncio.run(coro)
        except Exception as exc:
            container["error"] = exc

    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=timeout)
    if "error" in container and container["error"] is not None:
        raise container["error"]
    return container["result"]


@tool
@register_tool(
    tool_id="get_audit_opinion",
    name="审计意见查询",
    description="Obtain the type of historical audit opinions of A-share companies (standard unqualified/emphasized matters/qualified/negative/unable to express), audit institutions, audit fees, etc., to evaluate financial integrity",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["审计", "审计意见", "审计机构", "财务诚信", "A股", "管理层"],
    when_to_use="Used when assessing management s financial integrity, checking for abnormalities in audit opinions, and judging the reliability of financial information.",
    tool_role_hint="primary",
    output_shape="structured_records",
)
def get_audit_opinion(
    ticker: str = "600519",
    start_date: str = "2020-01-01",
    end_date: str = "2025-12-31",
) -> str:
    """Obtain audit opinions from A-share companies

    Args:
        ticker: Stock code, such as 600519,000001
        start_date: start date
        end_date: Deadline
    """
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider.is_available():
            return json.dumps({"error": "Tushare Not available (Token is not configured or library is not installed)", "ticker": ticker}, ensure_ascii=False)

        ts_code = _ticker_to_ts_code(ticker)

        async def _fetch():
            return await provider.get_audit_opinion(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

        df = _run_async_in_thread(_fetch())

        if df is None or df.empty:
            return json.dumps({
                "ticker": ticker,
                "ts_code": ts_code,
                "message": "未查询到审计意见数据",
                "records": [],
                "latest_opinion": "未知",
            }, ensure_ascii=False)

        records = []
        for _, row in df.iterrows():
            rec = {
                "公告日期": str(row.get("ann_date", row.get("公告日期", ""))),
                "报告期": str(row.get("end_date", row.get("报告期", ""))),
                "审计意见": str(row.get("audit_result", row.get("审计结果", ""))),
                "审计机构": str(row.get("audit_company", row.get("审计机构", ""))),
                "审计费用(元)": row.get("audit_fees", row.get("审计费用", "")),
            }
            records.append(rec)

        latest = records[0]["审计意见"] if records else "未知"
        return json.dumps({
            "ticker": ticker,
            "ts_code": ts_code,
            "total_records": len(records),
            "latest_opinion": latest,
            "records": records,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ 审计意见查询失败: {e}")
        return json.dumps({"error": str(e), "ticker": ticker}, ensure_ascii=False)


@tool
@register_tool(
    tool_id="get_disclosure_rating",
    name="信息披露评级查询",
    description="Obtain the exchange s annual evaluation results (A/B/C/D) on A-share companies information disclosure to evaluate corporate governance transparency",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["信息披露", "信披评级", "公司治理", "透明度", "A股", "管理层"],
    when_to_use="Used when assessing the quality of company information disclosure and checking exchange information disclosure evaluation records.",
    tool_role_hint="primary",
    output_shape="structured_records",
)
def get_disclosure_rating(
    ticker: str = "600519",
    end_date: str = "2025-12-31",
) -> str:
    """Obtain exchange information disclosure evaluation results

    Args:
        ticker: Stock code, such as 600519
        end_date: Closing reporting period
    """
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider.is_available():
            return json.dumps({"error": "Tushare Not available (Token is not configured or library is not installed)", "ticker": ticker}, ensure_ascii=False)

        ts_code = _ticker_to_ts_code(ticker)

        async def _fetch():
            return await provider.get_disclosure_rating(
                ts_code=ts_code,
                end_date=end_date,
            )

        df = _run_async_in_thread(_fetch())

        if df is None or df.empty:
            return json.dumps({
                "ticker": ticker,
                "ts_code": ts_code,
                "message": "未查询到信息披露评级数据",
                "records": [],
                "latest_rating": "未知",
            }, ensure_ascii=False)

        # Tushare disclosure_rating Return fields:ts_code, end_date, announcement_date, disclosure_result
        records = []
        for _, row in df.iterrows():
            rec = {
                "考评年度": str(row.get("end_date", row.get("考评年度", ""))),
                "考评结果": str(row.get("disclosure_result", row.get("考评结果", ""))),
            }
            records.append(rec)

        latest = records[0]["考评结果"] if records else "未知"
        return json.dumps({
            "ticker": ticker,
            "ts_code": ts_code,
            "total_records": len(records),
            "latest_rating": latest,
            "records": records,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ Information disclosure rating query failed: {e}")
        return json.dumps({"error": str(e), "ticker": ticker}, ensure_ascii=False)


@tool
@register_tool(
    tool_id="get_equity_incentive",
    name="股权激励计划查询",
    description="Obtain the details of the A-share company s equity incentive plan (incentive plan, grant price, exercise conditions, incentive period, proportion of total equity) to evaluate the rationality of management incentives",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["股权激励", "激励计划", "行权条件", "管理层激励", "A股", "管理层"],
    when_to_use="Used when assessing the rationality of management s equity incentives, checking incentive coverage and exercise conditions, and judging the impact of incentive plans on shareholder interests.",
    tool_role_hint="specialized",
    output_shape="structured_records",
)
def get_equity_incentive(
    ticker: str = "600519",
    start_date: str = "2020-01-01",
    end_date: str = "2025-12-31",
) -> str:
    """Get Equity Incentive Plan Details

    Args:
        ticker: Stock code, such as 600519
        start_date: start date
        end_date: Deadline
    """
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider.is_available():
            return json.dumps({"error": "Tushare Not available (Token is not configured or library is not installed)", "ticker": ticker}, ensure_ascii=False)

        ts_code = _ticker_to_ts_code(ticker)

        async def _fetch():
            return await provider.get_equity_incentive(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

        df = _run_async_in_thread(_fetch())

        if df is None or df.empty:
            return json.dumps({
                "ticker": ticker,
                "ts_code": ts_code,
                "message": "未查询到股权激励计划数据",
                "has_incentive_plan": False,
                "records": [],
            }, ensure_ascii=False)

        records = []
        for _, row in df.iterrows():
            rec = {
                "公告日期": str(row.get("ann_date", row.get("公告日期", ""))),
                "激励方案": str(row.get("inc_plan", row.get("激励方案", ""))),
                "授予数量(万股)": str(row.get("grant_num", row.get("授予数量", ""))),
                "授予价格": str(row.get("grant_price", row.get("授予价格", ""))),
                "激励年限": str(row.get("inc_duration", row.get("激励年限", ""))),
                "行权条件": str(row.get("inc_perf", row.get("行权条件", ""))),
                "总股本占比": str(row.get("stockholder_rt", row.get("总股本占比", ""))),
            }
            records.append(rec)

        return json.dumps({
            "ticker": ticker,
            "ts_code": ts_code,
            "has_incentive_plan": True,
            "total_plans": len(records),
            "records": records,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ 股权激励查询失败: {e}")
        return json.dumps({"error": str(e), "ticker": ticker}, ensure_ascii=False)


@tool
@register_tool(
    tool_id="get_management_penalties",
    name="管理层违规处罚查询",
    description="Obtain the historical violation penalty records of A-share companies and their management (penalty type, penalty object, penalty amount, violation reasons) to assess management behavioral risks",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["违规", "处罚", "管理层", "监管", "行为风险", "A股", "管理层"],
    when_to_use="Used when assessing management s historical behavioral risks, checking violation penalty records, and judging the company s compliance culture",
    tool_role_hint="primary",
    output_shape="structured_records",
)
def get_management_penalties(
    ticker: str = "600519",
    start_date: str = "2020-01-01",
    end_date: str = "2025-12-31",
) -> str:
    """Obtain management violation penalty records

    Args:
        ticker: Stock code, such as 600519
        start_date: start date
        end_date: Deadline
    """
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider.is_available():
            return json.dumps({"error": "Tushare Not available (Token is not configured or library is not installed)", "ticker": ticker}, ensure_ascii=False)

        ts_code = _ticker_to_ts_code(ticker)

        async def _fetch():
            return await provider.get_management_penalties(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

        df = _run_async_in_thread(_fetch())

        if df is None or df.empty:
            return json.dumps({
                "ticker": ticker,
                "ts_code": ts_code,
                "message": "No violation penalty records found (no violation records in the past 5 years, a positive sign)",
                "has_penalties": False,
                "total_records": 0,
                "records": [],
            }, ensure_ascii=False)

        records = []
        for _, row in df.iterrows():
            rec = {
                "公告日期": str(row.get("ann_date", row.get("公告日期", ""))),
                "处罚类型": str(row.get("punish_type", row.get("处罚类型", ""))),
                "处罚对象": str(row.get("punish_object", row.get("处罚对象", ""))),
                "违规类型": str(row.get("violat_type", row.get("违规类型", ""))),
                "违规事由": str(row.get("violate_content", row.get("违规事由", "")))[:300],
                "处罚金额(万元)": str(row.get("punish_amount", row.get("处罚金额", ""))),
            }
            records.append(rec)

        return json.dumps({
            "ticker": ticker,
            "ts_code": ts_code,
            "has_penalties": True,
            "total_records": len(records),
            "records": records,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ 违规处罚查询失败: {e}")
        return json.dumps({"error": str(e), "ticker": ticker}, ensure_ascii=False)

# === option_tools ===
"""Options and derivatives pricing tools."""

import json
import logging
import math
from typing import Annotated, Optional

import numpy as np
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)

# ── scipy availability check ────────────────────────────────────────

try:
    from scipy import stats as _stats

    def _norm_cdf(x: float) -> float:
        """Standard normal distribution CDF, scipy first, fallback math.erf."""
        return float(_stats.norm.cdf(x))

    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

    def _norm_cdf(x: float) -> float:
        """standard normal distribution CDF —— math.erf Approximately."""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard Normal Distribution PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# ── Black-Scholes Internal calculation ─────────────────────────────────────────

def _bs_d1(
    spot: float, strike: float, t: float, r: float, sigma: float
) -> float:
    return (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t) / (
        sigma * math.sqrt(t)
    )


def _bs_price(
    spot: float, strike: float, t: float, r: float, sigma: float, opt_type: str
) -> dict:
    """Calculate Black-Scholes prices and intermediate variables.

    Returns
        dict with: price, d1, d2, delta, intrinsic_value, time_value
    """
    d1 = _bs_d1(spot, strike, t, r, sigma)
    d2 = d1 - sigma * math.sqrt(t)

    n1 = _norm_cdf(d1)
    n2 = _norm_cdf(d2)
    nm1 = _norm_cdf(-d1)
    nm2 = _norm_cdf(-d2)

    disc = strike * math.exp(-r * t)

    if opt_type == "call":
        price = spot * n1 - disc * n2
        delta = n1
        intrinsic = max(spot - strike, 0.0)
    else:
        price = disc * nm2 - spot * nm1
        delta = n1 - 1.0
        intrinsic = max(strike - spot, 0.0)

    time_value = price - intrinsic
    return {
        "price": round(price, 6),
        "d1": round(d1, 6),
        "d2": round(d2, 6),
        "delta": round(delta, 6),
        "intrinsic_value": round(intrinsic, 6),
        "time_value": round(time_value, 6),
    }


def _bs_vega(
    spot: float, strike: float, t: float, r: float, sigma: float
) -> float:
    """Calculate Vega = S * N'(d1) * sqrt(T)"""
    d1 = _bs_d1(spot, strike, t, r, sigma)
    return spot * _norm_pdf(d1) * math.sqrt(t)


# ── Tool 1: Black-Scholes option pricing ─────────────────────────────────

@tool
@register_tool(
    tool_id="get_black_scholes_price",
    name="Black-Scholes option pricing",
    description=(
        "Calculate the theoretical price of European options based on the Black-Scholes model, and return d1, d2, Delta,"
        "Intrinsic value and time value. Use scipy.stats.norm.cdf to calculate the normal distribution cumulative function;"
        "Fallback to math.erf approximation if scipy is not available."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["derivatives", "option_pricing", "black_scholes"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["欧式期权理论定价", "Black-Scholes Model calculation"],
    when_to_use=(
        "It is used when users need to calculate the theoretical price, d1/d2, Delta, intrinsic value or time value of European options."
        "Suitable for standardized European call/put option pricing."
    ),
    when_not_to_use=(
        "Not suitable for American options (early exercise needs to be considered);"
        "Not suitable for exotic options (such as barrier options, Asian options, etc.);"
        "Not suitable for implied volatility calculations (use get_implied_volatility instead)."
    ),
    returns=(
        "Returns a JSON string containing option_price (option price), d1, d2, delta,"
        "intrinsic_value (intrinsic value), time_value (time value), parameters_used (use parameters),"
        "methodology (calculation instructions)."
    ),
    example="get_black_scholes_price(spot_price=100, strike_price=100, time_to_expiry=0.5)",
    related_tools=["get_implied_volatility", "get_option_greeks", "get_option_strategy_pnl"],
)
def get_black_scholes_price(
    spot_price: Annotated[float, "标的资产当前价格"],
    strike_price: Annotated[float, "行权价"],
    time_to_expiry: Annotated[float, "Expiration time (year), for example, 0.5 means half a year"],
    risk_free_rate: Annotated[float, "无风险利率"] = 0.025,
    volatility: Annotated[float, "波动率（年化）"] = 0.25,
    option_type: Annotated[str, "Option type: call or put"] = "call",
) -> str:
    """Calculate the Black-Scholes theoretical price of a European option.

    Args:
        spot_price: Current price of the underlying asset
        strike_price: exercise price
        time_to_expiry: Expiration time (year), for example, 0.5 means half a year
        risk_free_rate: Risk-free rate (decimal), default 0.025
        volatility: Volatility (annualized decimal), default 0.25
        option_type: Option type: "call" (bullish) or "put" (bearish), default "call"

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            option_type: Option type: "call" | "put"
            option_price: option theoretical price
            d1: BS in the formula d1
            d2: BS in the formula d2
            delta: Delta value
            intrinsic_value: intrinsic value
            time_value: time value
            moneyness: In-the-money status: "In price" | "At-the-money or out-of-the-money"
            parameters_used: dict Parameters used——
                — spot_price: target price
                — strike_price: exercise price
                — time_to_expiry_years: Expiration time (year)
                — risk_free_rate: risk-free rate
                — volatility: Volatility
                — option_type: Option type
            methodology: Calculation method description
            message: Error message (only status="error" exist)
    """
    try:
        opt_type = option_type.lower()
        if opt_type not in ("call", "put"):
            return json.dumps({
                "status": "error",
                "message": "option_type must be 'call' or 'put'",
            }, ensure_ascii=False, indent=2, default=str)

        if spot_price <= 0 or strike_price <= 0:
            return json.dumps({
                "status": "error",
                "message": "spot_price and strike_price must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if time_to_expiry <= 0:
            return json.dumps({
                "status": "error",
                "message": "time_to_expiry must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if volatility <= 0:
            return json.dumps({
                "status": "error",
                "message": "volatility must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        result = _bs_price(
            spot=spot_price,
            strike=strike_price,
            t=time_to_expiry,
            r=risk_free_rate,
            sigma=volatility,
            opt_type=opt_type,
        )

        payload = {
            "status": "ok",
            "option_type": opt_type,
            "option_price": result["price"],
            "d1": result["d1"],
            "d2": result["d2"],
            "delta": result["delta"],
            "intrinsic_value": result["intrinsic_value"],
            "time_value": result["time_value"],
            "moneyness": "价内" if result["intrinsic_value"] > 0 else "价平或价外",
            "parameters_used": {
                "spot_price": spot_price,
                "strike_price": strike_price,
                "time_to_expiry_years": time_to_expiry,
                "risk_free_rate": risk_free_rate,
                "volatility": volatility,
                "option_type": opt_type,
            },
            "methodology": (
                "Black-Scholes European option pricing model:"
                "d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)；"
                "d2 = d1 - σ√T；"
                "Call = S·N(d1) - K·e^(-rT)·N(d2)；"
                "Put = K·e^(-rT)·N(-d2) - S·N(-d1)。"
                f"{'Calculated using scipy.stats.norm.cdf N(·). ' if _HAS_SCIPY else 'Approximate calculations using math.erf N(·) (scipy Not available).'}"
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Black-Scholes Pricing failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ── Tool 2: Implied volatility ─────────────────────────────────────────────

@tool
@register_tool(
    tool_id="get_implied_volatility",
    name="隐含波动率计算",
    description=(
        "Implied volatility is deduced from option market prices using the Newton-Raphson iteration method."
        "Iteration formula:σ_new = σ - (BS(σ) - market_price) / vega(σ), "
        "Maximum iterations 100, convergence tolerance 0.0001."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["derivatives", "implied_volatility", "option_pricing"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["Deducing implied volatility from option market prices"],
    when_to_use=(
        "It is used when the user knows the option market price and needs to derive the corresponding implied volatility."
        "Commonly used in volatility trading and option pricing verification."
    ),
    when_not_to_use=(
        "Not suitable for theoretical pricing (please use get_black_scholes_price);"
        "Not suitable for historical volatility calculations (please use statistical tools);"
        "Not suitable for deeply out-of-the-money options (iterations may not converge)."
    ),
    returns=(
        "Returns a JSON string containing implied_volatility,"
        "iterations (number of iterations), convergence_status (convergence status),"
        "initial_guess (Initial guess value), price_at_iv (BS price corresponding to IV)."
    ),
    example="get_implied_volatility(spot_price=100, strike_price=100, time_to_expiry=0.5, option_price=10)",
    related_tools=["get_black_scholes_price", "get_option_greeks", "get_option_strategy_pnl"],
)
def get_implied_volatility(
    spot_price: Annotated[float, "标的资产当前价格"],
    strike_price: Annotated[float, "行权价"],
    time_to_expiry: Annotated[float, "到期时间（年）"],
    option_price: Annotated[float, "期权市场价"],
    risk_free_rate: Annotated[float, "无风险利率"] = 0.025,
    option_type: Annotated[str, "Option type: call or put"] = "call",
) -> str:
    """Implied volatility is deduced from market prices via Newton-Raphson iterations.

    Args:
        spot_price: Current price of the underlying asset
        strike_price: exercise price
        time_to_expiry: Expiration time (year)
        option_price: option market price
        risk_free_rate: Risk-free rate (decimal), default 0.025
        option_type: Option type: "call" or "put", Default "call"

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            implied_volatility: Implied volatility (decimal)
            implied_volatility_pct: Implied volatility (%)
            iterations: Number of iterations
            convergence_status: convergence state: "Converged" | "Not converged"
            initial_guess: Initial guess value (0.3)
            price_at_iv: IV Corresponding BS price (only status="ok" exist)
            target_price: Target option market price (only status="ok" exist)
            price_error: Price error (only status="ok" exist)
            parameters_used: dict Parameters used (only status="ok" exist)——
                — spot_price: target price
                — strike_price: exercise price
                — time_to_expiry_years: Expiration time (year)
                — risk_free_rate: risk-free rate
                — option_price: option market price
                — option_type: Option type
            methodology: Description of calculation method (only status="ok" exist)
            message: Error message (only status="error" exist)
    """
    try:
        opt_type = option_type.lower()
        if opt_type not in ("call", "put"):
            return json.dumps({
                "status": "error",
                "message": "option_type must be 'call' or 'put'",
            }, ensure_ascii=False, indent=2, default=str)

        if spot_price <= 0 or strike_price <= 0:
            return json.dumps({
                "status": "error",
                "message": "spot_price and strike_price must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if time_to_expiry <= 0:
            return json.dumps({
                "status": "error",
                "message": "time_to_expiry must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if option_price <= 0:
            return json.dumps({
                "status": "error",
                "message": "option_price must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        # Determine the upper limit of intrinsic value
        intrinsic = max(spot_price - strike_price, 0.0) if opt_type == "call" else max(strike_price - spot_price, 0.0)
        if option_price < intrinsic:
            return json.dumps({
                "status": "error",
                "message": (
                    f"期权价格 {option_price} 低于内在价值 {intrinsic}，"
                    "Risk-free arbitrage opportunities exist and meaningful implied volatility cannot be calculated"
                ),
            }, ensure_ascii=False, indent=2, default=str)

        sigma = 0.3  # initial guess
        max_iter = 100
        tolerance = 0.0001

        for i in range(max_iter):
            bs = _bs_price(spot_price, strike_price, time_to_expiry, risk_free_rate, sigma, opt_type)
            price_diff = bs["price"] - option_price

            if abs(price_diff) < tolerance:
                payload = {
                    "status": "ok",
                    "implied_volatility": round(sigma, 6),
                    "implied_volatility_pct": round(sigma * 100, 4),
                    "iterations": i + 1,
                    "convergence_status": "已收敛",
                    "initial_guess": 0.3,
                    "price_at_iv": bs["price"],
                    "target_price": option_price,
                    "price_error": round(price_diff, 8),
                    "parameters_used": {
                        "spot_price": spot_price,
                        "strike_price": strike_price,
                        "time_to_expiry_years": time_to_expiry,
                        "risk_free_rate": risk_free_rate,
                        "option_price": option_price,
                        "option_type": opt_type,
                    },
                    "methodology": (
                        "Newton-Raphson Iterative method:σ_new = σ - (BS(σ) - market_price) / vega(σ). "
                        + ("Calculated using scipy.stats.norm N(·) and N'(·). " if _HAS_SCIPY else "Approximate calculations using math.erf N(·) (scipy Not available).")
                    ),
                }
                return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

            vega = _bs_vega(spot_price, strike_price, time_to_expiry, risk_free_rate, sigma)
            if abs(vega) < 1e-12:
                break  # vega Too small to continue iterating

            sigma = sigma - price_diff / vega
            sigma = max(sigma, 0.001)  # Volatility floor

        return json.dumps({
            "status": "error",
            "message": f"迭代 {max_iter} 次未收敛，请检查输入参数或尝试不同的初始猜测",
            "implied_volatility": round(sigma, 6) if sigma > 0 else None,
            "iterations": max_iter,
            "convergence_status": "未收敛",
            "initial_guess": 0.3,
        }, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Implied volatility calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ── Tool 3: greek letter calculation ───────────────────────────────────────────

@tool
@register_tool(
    tool_id="get_option_greeks",
    name="期权希腊字母计算",
    description=(
        "Calculate Greeks (Delta, Gamma, Theta, Vega, Rho) for European options,"
        "And give the meaning of each Greek letter. Gamma and Vega are the same for call/put options."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["derivatives", "option_greeks", "risk_management"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["Calculate option Greek letters (Delta, Gamma, Theta, Vega, Rho)"],
    when_to_use=(
        "Used when the user needs to calculate the risk indicators (Delta/Gamma/Theta/Vega/Rho) of European options."
        "Suitable for risk management and hedging strategy analysis."
    ),
    when_not_to_use=(
        "Not suitable for American options Greek letter calculation;"
        "Not suitable for exotic options;"
        "Not suitable for option pricing itself (use get_black_scholes_price)."
    ),
    returns=(
        "Returns a JSON string, including delta, gamma, theta (annualized), vega (1% volatility change),"
        "rho (1%interest rate changes), and the meaning of each Greek letter."
    ),
    example="get_option_greeks(spot_price=100, strike_price=100, time_to_expiry=0.5)",
    related_tools=["get_black_scholes_price", "get_implied_volatility", "get_option_strategy_pnl"],
)
def get_option_greeks(
    spot_price: Annotated[float, "标的资产当前价格"],
    strike_price: Annotated[float, "行权价"],
    time_to_expiry: Annotated[float, "到期时间（年）"],
    risk_free_rate: Annotated[float, "无风险利率"] = 0.025,
    volatility: Annotated[float, "波动率（年化）"] = 0.25,
    option_type: Annotated[str, "Option type: call or put"] = "call",
) -> str:
    """Calculate Delta, Gamma, Theta, Vega, Rho for European options.

    Args:
        spot_price: Current price of the underlying asset
        strike_price: exercise price
        time_to_expiry: Expiration time (year)
        risk_free_rate: Risk-free rate (decimal), default 0.025
        volatility: Volatility (annualized decimal), default 0.25
        option_type: Option type: "call" or "put", Default "call"

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            option_type: Option type: "call" | "put"
            spot_price_used: underlying price used
            delta: dict Delta——
                — value: Delta value
                — description: Explanation of meaning
                — interpretation: Explanation (directional exposure)
            gamma: dict Gamma——
                — value: Gamma value
                — description: Explanation of meaning
                — interpretation: Interpretation (Delta Sensitivity/Convexity Risk)
            theta: dict Theta (annualized)——
                — value: Theta Value (annualized)
                — description: Meaning (including daily average Theta)
                — interpretation: Interpretation (time decay)
            vega: dict Vega (per 1% change in volatility)——
                — value: Vega value
                — description: Explanation of meaning
                — interpretation: Explanation (Volatility Risk Exposure)
            rho: dict Rho (per 1% interest rate change)——
                — value: Rho value
                — description: Explanation of meaning
                — interpretation: Explanation (interest rate risk exposure)
            parameters_used: dict Parameters used
            methodology: Calculation method description
            message: Error message (only status="error" exist)
    """
    try:
        opt_type = option_type.lower()
        if opt_type not in ("call", "put"):
            return json.dumps({
                "status": "error",
                "message": "option_type must be 'call' or 'put'",
            }, ensure_ascii=False, indent=2, default=str)

        if spot_price <= 0 or strike_price <= 0:
            return json.dumps({
                "status": "error",
                "message": "spot_price and strike_price must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if time_to_expiry <= 0:
            return json.dumps({
                "status": "error",
                "message": "time_to_expiry must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if volatility <= 0:
            return json.dumps({
                "status": "error",
                "message": "volatility must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        d1 = _bs_d1(spot_price, strike_price, time_to_expiry, risk_free_rate, volatility)
        d2 = d1 - volatility * math.sqrt(time_to_expiry)

        n1 = _norm_cdf(d1)
        nd1_pdf = _norm_pdf(d1)  # N'(d1)

        sqrt_t = math.sqrt(time_to_expiry)
        disc = strike_price * math.exp(-risk_free_rate * time_to_expiry)

        # Delta
        if opt_type == "call":
            delta = n1
        else:
            delta = n1 - 1.0

        # Gamma (call/put same)
        gamma = nd1_pdf / (spot_price * volatility * sqrt_t)

        # Theta (annualized)
        theta_common = -(spot_price * nd1_pdf * volatility) / (2.0 * sqrt_t)
        if opt_type == "call":
            theta = theta_common - risk_free_rate * disc * _norm_cdf(d2)
        else:
            theta = theta_common + risk_free_rate * disc * _norm_cdf(-d2)

        # Vega (call/put same)
        vega = spot_price * nd1_pdf * sqrt_t

        # Rho
        if opt_type == "call":
            rho = disc * time_to_expiry * _norm_cdf(d2)
        else:
            rho = -disc * time_to_expiry * _norm_cdf(-d2)

        payload = {
            "status": "ok",
            "option_type": opt_type,
            "spot_price_used": spot_price,
            "delta": {
                "value": round(delta, 6),
                "description": (
                    "Changes in underlying asset prices $1 The amount of change in the option price at that time."
                    f"call option Delta={round(delta, 4)}, "
                    f"It means that the underlying price increases $1, Approximate change in option price {round(delta, 4)}. "
                ),
                "interpretation": "方向性风险敞口" if opt_type == "call" else "方向性风险敞口（负值）",
            },
            "gamma": {
                "value": round(gamma, 6),
                "description": (
                    f"Changes in underlying asset prices $1 The amount of change in Delta.Gamma={round(gamma, 6)}, "
                    "Gamma The larger the delta is, the more sensitive it is to price changes."
                ),
                "interpretation": "Delta sensitivity (convexity risk)",
            },
            "theta": {
                "value": round(theta, 6),
                "description": (
                    f"The amount of change in the option price every time one day passes (annualized/365)."
                    f"Theta (annualized)={round(theta, 6)}, "
                    f"Daily average Theta ≈ {round(theta / 365.0, 6)}. "
                ),
                "interpretation": "Time decay (Theta is usually negative, indicating loss of time value)",
            },
            "vega": {
                "value": round(vega / 100.0, 6),
                "description": (
                    f"The amount by which the option price changes for every 1% (or 0.01) increase in volatility."
                    f"Vega (per 1% volatility)≈ {round(vega / 100.0, 6)}. "
                ),
                "interpretation": "波动率风险敞口",
            },
            "rho": {
                "value": round(rho / 100.0, 6),
                "description": (
                    f"The amount by which the option price changes for every 1% (i.e., 0.01) increase in the risk-free interest rate."
                    f"Rho (per 1% interest rate change)≈ {round(rho / 100.0, 6)}. "
                ),
                "interpretation": "Interest rate risk exposure (generally less impact on short-dated options)",
            },
            "parameters_used": {
                "spot_price": spot_price,
                "strike_price": strike_price,
                "time_to_expiry_years": time_to_expiry,
                "risk_free_rate": risk_free_rate,
                "volatility": volatility,
                "option_type": opt_type,
            },
            "methodology": (
                "Delta = N(d1) (call) or N(d1)-1 (put) ; "
                "Gamma = N'(d1) / (S·σ·√T)；"
                "Theta(call) = -(S·N'(d1)·σ)/(2√T) - r·K·e^(-rT)·N(d2)；"
                "Vega = S·N'(d1)·√T；"
                "Rho(call) = K·T·e^(-rT)·N(d2)。"
                + ("Calculated using scipy.stats.norm N(·) and N'(·). " if _HAS_SCIPY else "Approximate calculations using math.erf N(·) (scipy Not available).")
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("希腊字母计算失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ── Tool 4: Options Strategy Profit and Loss Chart ─────────────────────────────────────────

def _covered_call_pnl(
    spot_range: np.ndarray, spot_0: float, k1: float, prem1: float
) -> np.ndarray:
    """covered_call: long stock + short call at k1"""
    call_intrinsic = np.maximum(spot_range - k1, 0.0)
    stock_pnl = spot_range - spot_0
    return stock_pnl + prem1 - call_intrinsic


def _protective_put_pnl(
    spot_range: np.ndarray, spot_0: float, k1: float, prem1: float
) -> np.ndarray:
    """protective_put: long stock + long put at k1"""
    put_intrinsic = np.maximum(k1 - spot_range, 0.0)
    stock_pnl = spot_range - spot_0
    return stock_pnl - prem1 + put_intrinsic


def _straddle_pnl(
    spot_range: np.ndarray, k: float, prem1: float
) -> np.ndarray:
    """straddle: long call + long put at same strike; total_prem = 2*prem1"""
    return np.abs(spot_range - k) - 2.0 * prem1


def _strangle_pnl(
    spot_range: np.ndarray, k1: float, k2: float, prem1: float, prem2: float
) -> np.ndarray:
    """strangle: long put at k1 (< spot) + long call at k2 (> spot)"""
    put_pnl = np.maximum(k1 - spot_range, 0.0) - prem1
    call_pnl = np.maximum(spot_range - k2, 0.0) - prem2
    return put_pnl + call_pnl


def _bull_spread_pnl(
    spot_range: np.ndarray, k1: float, k2: float, prem1: float, prem2: float
) -> np.ndarray:
    """bull_spread: long call at k1 + short call at k2 (k2 > k1)"""
    long_call = np.maximum(spot_range - k1, 0.0) - prem1
    short_call = prem2 - np.maximum(spot_range - k2, 0.0)
    return long_call + short_call


def _bear_spread_pnl(
    spot_range: np.ndarray, k1: float, k2: float, prem1: float, prem2: float
) -> np.ndarray:
    """bear_spread: long put at k1 + short put at k2 (k1 > k2)"""
    long_put = np.maximum(k1 - spot_range, 0.0) - prem1
    short_put = prem2 - np.maximum(k2 - spot_range, 0.0)
    return long_put + short_put


def _iron_condor_pnl(
    spot_range: np.ndarray,
    k1: float, k2: float, k3: float, k4: float,
    prem1: float, prem2: float, prem3: float, prem4: float,
) -> np.ndarray:
    """iron_condor: bear put spread (k1>k2) + bull call spread (k3<k4)"""
    # Bear put spread: long put at k1, short put at k2
    long_put = np.maximum(k1 - spot_range, 0.0) - prem1
    short_put = prem2 - np.maximum(k2 - spot_range, 0.0)
    # Bull call spread: long call at k3, short call at k4
    long_call = np.maximum(spot_range - k3, 0.0) - prem3
    short_call = prem4 - np.maximum(spot_range - k4, 0.0)
    return long_put + short_put + long_call + short_call


_STRATEGIES = {
    "covered_call": {
        "label": "Covered Call",
        "description": "Hold the underlying asset + Selling call options. Suitable for mildly bullish or neutral expectations to enhance returns through premiums.",
        "legs": 2,
    },
    "protective_put": {
        "label": "Protective Put",
        "description": "Hold the underlying asset + Buy put options. It is suitable for those who are bullish but worried about the downside risk, which is equivalent to buying insurance for the position.",
        "legs": 2,
    },
    "straddle": {
        "label": "Straddle",
        "description": "Buy both call and put options at the same price. Applicable to situations where the underlying asset is expected to fluctuate significantly but the direction is uncertain.",
        "legs": 2,
    },
    "strangle": {
        "label": "Strangle combination",
        "description": "Buy out-of-the-money put (K1<S) and out-of-the-money calls (K2>S) . Suitable for large swings expected and costs less than straddle.",
        "legs": 2,
    },
    "bull_spread": {
        "label": "Bull Spread",
        "description": "Buy low strike price call + Sell the high strike price to call. Suitable for mild bullishness and cost reduction.",
        "legs": 2,
    },
    "bear_spread": {
        "label": "Bear Spread",
        "description": "Buy high strike price put + Sell low strike price put. Suitable for mild bearish, cost reduction.",
        "legs": 2,
    },
    "iron_condor": {
        "label": "Iron Condor",
        "description": "Bear Put Spread + Bullish Call Spread (4 legs total). It is suitable for the expected target to fluctuate within a narrow range.",
        "legs": 4,
    },
}


@tool
@register_tool(
    tool_id="get_option_strategy_pnl",
    name="期权策略盈亏图",
    description=(
        "Calculate the profit and loss curves of common option strategies on the expiration date, including maximum profit, maximum loss,"
        "break-even point, and a breakdown of the profit and loss for about 20 price points."
        "Support strategies: covered_call (covered opening), protective_put (protective put),"
        "straddle (straddle), strangle (wide straddle), bull_spread (bull spread),"
        "bear_spread (Bear spread), iron_condor (Iron Eagle style)."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["derivatives", "option_strategy", "pnl_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["期权策略盈亏分析", "策略对比", "盈亏平衡点计算"],
    when_to_use=(
        "When users need to analyze the profit and loss of option portfolio strategies on the expiration date, calculate the maximum profit/loss,"
        "Break-even point, or used when profit and loss visualization data is needed."
    ),
    when_not_to_use=(
        "Not suitable for single-leg option pricing (use get_black_scholes_price);"
        "Not suitable for Greek letter calculations (please use get_option_greeks);"
        "Not suitable for implied volatility calculations (use get_implied_volatility instead)."
    ),
    returns=(
        "Returns a JSON string, including strategy (strategy name and description), max_profit (maximum profit),"
        "max_loss (maximum loss), break_even_points (break-even point list),"
        "pnl_table (Price-P&L array, about 20 points)."
    ),
    example="get_option_strategy_pnl(strategy_type='covered_call', spot_price=100, strike1=100)",
    related_tools=["get_black_scholes_price", "get_option_greeks", "get_implied_volatility"],
)
def get_option_strategy_pnl(
    strategy_type: Annotated[str, "策略类型"] = "covered_call",
    spot_price: Annotated[float, "标的当前价格"] = 100.0,
    strike1: Annotated[float, "主行权价（第一腿）"] = 100.0,
    strike2: Annotated[Optional[float], "Second strike price (used by spread strategy)"] = None,
    premium1: Annotated[float, "第一腿权利金（收/付）"] = 5.0,
    premium2: Annotated[Optional[float], "第二腿权利金（收/付）"] = None,
    volatility: Annotated[float, "Volatility (for ATM options reference)"] = 0.25,
    time_to_expiry: Annotated[float, "到期时间（年）"] = 0.25,
    risk_free_rate: Annotated[float, "无风险利率"] = 0.025,
) -> str:
    """Calculate the profit and loss distribution of the option strategy on the expiration date.

    Args:
        strategy_type: Policy type, optional "covered_call" / "protective_put" / "straddle" /
            "strangle" / "bull_spread" / "bear_spread" / "iron_condor", Default "covered_call"
        spot_price: Current price of the underlying, default 100.0
        strike1: Main strike price (first leg), default 100.0
        strike2: The second exercise price (used by spread strategy) is automatically calculated according to the strategy when it is None. The default is None
        premium1: First leg royalty, default 5.0
        premium2: The second leg premium is automatically calculated according to the strategy when it is None. The default value is None
        volatility: Volatility (for ATM options reference), default 0.25
        time_to_expiry: Expiration time (year), default 0.25
        risk_free_rate: Risk-free rate, default 0.025

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            strategy: Strategy Chinese name
            strategy_description: Strategy description
            legs: Description text for each leg combination
            max_profit: Maximum profit (numeric value or "Infinity (theoretical upper limit)") 
            max_loss: Maximum loss (numeric value or "Infinity (theoretical lower limit)") 
            break_even_points: list[float] Break-even point list
            pnl_table: list[dict] Profit and loss statement (approx. 21 points), element structure——
                — spot_price_at_expiry: Expiration price
                — pnl: Profit and loss at this price
            visualization_note: Visual illustration
            parameters_used: dict Parameters used——
                — strategy_type: Strategy type
                — spot_price: target price
                — strike1: Main strike price
                — strike2: Second exercise price
                — premium1: first leg royalty
                — premium2: second leg royalty
                — time_to_expiry_years: Expiration time (year)
                — volatility: Volatility
            methodology: Calculation method description
            message: Error message (only status="error" exist)
    """
    try:
        strategy = strategy_type.lower()
        if strategy not in _STRATEGIES:
            return json.dumps({
                "status": "error",
                "message": (
                    f"不支持的策略类型 '{strategy_type}'。"
                    f"Support:{', '.join(_STRATEGIES.keys())}"
                ),
            }, ensure_ascii=False, indent=2, default=str)

        s0 = spot_price
        k1 = strike1

        # Generate price range:0 ~ 2*s0, about 20 points
        price_points = 21
        spot_range = np.linspace(0.0, 2.0 * s0, price_points)

        # Calculate profit and loss based on strategy type
        strategy_info = _STRATEGIES[strategy]

        if strategy == "covered_call":
            k2 = strike2 if strike2 is not None else k1
            pnl = _covered_call_pnl(spot_range, s0, k1, premium1)
            legs_desc = f"Long stock @ {s0} + Short call @ {k1}（权利金收入 {premium1}）"
            # max profit = k1 - s0 + premium (capped at k1)
            max_profit = k1 - s0 + premium1
            # max loss = s0 - 0 + (-premium when deep ITM) -- actually at S_T=0, stock loses all, keep premium
            # Actually: max loss = s0 (stock goes to 0, loss S_0) + keep premium
            # Wait: profit = S_T - S_0 + prem - max(S_T-K, 0)
            # If S_T=0: profit = 0 - S0 + prem - 0 = prem - S0
            # If S_T=inf: profit = S_T - S0 + prem - (S_T-K) = K - S0 + prem
            max_loss = premium1 - s0
            be1 = s0 - premium1
            be_points = sorted({round(p, 2) for p in [be1] if p >= 0})

        elif strategy == "protective_put":
            k2 = strike2 if strike2 is not None else k1
            pnl = _protective_put_pnl(spot_range, s0, k1, premium1)
            legs_desc = f"Long stock @ {s0} + Long put @ {k1}（权利金支出 {premium1}）"
            # profit = S_T - S_0 - prem + max(K-S_T, 0)
            # if S_T >= K: profit = S_T - S_0 - prem, unlimited upside
            # if S_T < K: profit = K - S_0 - prem (floor)
            max_profit = None  # unlimited upside
            max_loss = premium1 - (k1 - s0)  # = s0 + prem - k1
            if s0 + premium1 > k1:
                max_loss = s0 + premium1 - k1
            else:
                max_loss = premium1 + s0 - k1
            # Wait: floor is when S_T=0: profit = 0 - s0 - prem + (K-0) = K - s0 - prem
            max_loss = k1 - s0 - premium1  # this is negative if k1 < s0+prem
            be1 = s0 + premium1
            be_points = sorted({round(p, 2) for p in [be1] if p >= 0})

        elif strategy == "straddle":
            k2 = strike2 if strike2 is not None else k1
            pnl = _straddle_pnl(spot_range, k1, premium1)
            legs_desc = f"Long call @ {k1} + Long put @ {k1}（总权利金支出 {2 * premium1}）"
            max_profit = None  # unlimited upside
            max_loss = -2.0 * premium1
            be_low = k1 - 2.0 * premium1
            be_high = k1 + 2.0 * premium1
            be_points = sorted({round(p, 2) for p in [be_low, be_high] if p >= 0})

        elif strategy == "strangle":
            k2 = strike2 if strike2 is not None else s0 * 1.1
            p2 = premium2 if premium2 is not None else premium1 * 0.8
            pnl = _strangle_pnl(spot_range, k1, k2, premium1, p2)
            legs_desc = f"Long put @ {k1}（权利金 {premium1}）+ Long call @ {k2}（权利金 {p2}）"
            total_prem = premium1 + p2
            max_loss = -total_prem
            be_low = k1 - total_prem
            be_high = k2 + total_prem
            max_profit = None  # unlimited upside
            be_points = sorted({round(p, 2) for p in [be_low, be_high] if p >= 0})

        elif strategy == "bull_spread":
            k2 = strike2 if strike2 is not None else k1 * 1.1
            p2 = premium2 if premium2 is not None else premium1 * 0.6
            pnl = _bull_spread_pnl(spot_range, k1, k2, premium1, p2)
            legs_desc = f"Long call @ {k1}（权利金 {premium1}）+ Short call @ {k2}（权利金 {p2}）"
            net_prem = premium1 - p2
            max_loss = -net_prem
            max_profit = (k2 - k1) - net_prem
            be1 = k1 + net_prem
            be_points = sorted({round(p, 2) for p in [be1] if p >= 0})

        elif strategy == "bear_spread":
            k2 = strike2 if strike2 is not None else k1 * 0.9
            p2 = premium2 if premium2 is not None else premium1 * 0.6
            pnl = _bear_spread_pnl(spot_range, k1, k2, premium1, p2)
            legs_desc = f"Long put @ {k1}（权利金 {premium1}）+ Short put @ {k2}（权利金 {p2}）"
            net_prem = premium1 - p2
            max_loss = -net_prem
            max_profit = (k1 - k2) - net_prem
            be1 = k1 - net_prem
            be_points = sorted({round(p, 2) for p in [be1] if p >= 0})

        elif strategy == "iron_condor":
            # Bear put spread: long put at k1, short put at k2
            # Bull call spread: long call at k3, short call at k4
            # Default: k1=s0*1.1, k2=s0*1.05, k3=s0*0.95, k4=s0*0.9
            k2_val = strike2 if strike2 is not None else s0 * 1.05
            k3 = s0 * 0.95
            k4 = s0 * 0.90
            p2_val = premium2 if premium2 is not None else premium1 * 0.7
            p3 = premium1 * 0.7
            p4 = premium1 * 0.5
            pnl = _iron_condor_pnl(spot_range, k1, k2_val, k3, k4, premium1, p2_val, p3, p4)
            legs_desc = (
                f"Bear put spread: long put @ {k1}（{premium1}）+ short put @ {k2_val}（{p2_val}）；"
                f"Bull call spread: long call @ {k3}（{p3}）+ short call @ {k4}（{p4}）"
            )
            net_prem = (p2_val + p4) - (premium1 + p3)
            max_profit = net_prem
            max_loss = (k1 - k2_val) - net_prem  # width of put spread minus net credit
            be_low = k1 + net_prem
            be_high = k4 - net_prem
            be_points = sorted({round(p, 2) for p in [be_low, be_high] if p >= 0})
            # Fix: iron_condor max profit/loss logic
            # Net credit = credit received - debit paid
            # Put spread: sell k2 (higher credit), buy k1 (lower debit)
            # In iron condor: bear put spread = sell put at k2, buy put at k1 (k1 > k2)
            # Bull call spread = buy call at k3, sell call at k4 (k3 < k4)
            # If we receive net credit: max profit = net credit
            # Width = k1 - k2 (put spread width) or k4 - k3 (call spread width)
            # Max loss = width - net credit
            width_put = k1 - k2_val
            width_call = k4 - k3
            width = min(width_put, width_call)
            max_loss = width - net_prem if net_prem < width else 0.0

        # Build PnL table
        pnl_list = []
        for i in range(len(spot_range)):
            pnl_list.append({
                "spot_price_at_expiry": round(float(spot_range[i]), 4),
                "pnl": round(float(pnl[i]), 4),
            })

        # Break-even point filter (make sure it's within price range and reasonable)
        be_points = [p for p in be_points if 0 <= p <= 2 * s0]

        payload = {
            "status": "ok",
            "strategy": strategy_info["label"],
            "strategy_description": strategy_info["description"],
            "legs": legs_desc,
            "max_profit": round(max_profit, 4) if max_profit is not None else "无穷（理论上限）",
            "max_loss": round(max_loss, 4) if max_loss is not None else "无穷（理论下限）",
            "break_even_points": be_points,
            "pnl_table": pnl_list,
            "visualization_note": (
                "The above profit and loss are the profit and loss on the maturity date (time value is not considered)."
                "PnL Tables can be imported into Excel/matplotlib for visualization."
            ),
            "parameters_used": {
                "strategy_type": strategy,
                "spot_price": s0,
                "strike1": k1,
                "strike2": strike2 if strike2 is not None else k2 if strategy in ("covered_call", "protective_put", "straddle") else k2 if strategy in ("strangle", "bull_spread", "bear_spread") else k2_val if strategy == "iron_condor" else None,
                "premium1": premium1,
                "premium2": premium2,
                "time_to_expiry_years": time_to_expiry,
                "volatility": volatility,
            },
            "methodology": (
                "Calculation of profit and loss on maturity date:PnL = Sum of intrinsic value of each leg – net royalty payout (+ net royalty income)."
                "covered_call: PnL = (S_T - S_0) + premium - max(S_T - K, 0)；"
                "protective_put: PnL = (S_T - S_0) - premium + max(K - S_T, 0)；"
                "straddle: PnL = |S_T - K| - 2×premium；"
                "strangle: PnL = max(K1 - S_T, 0) + max(S_T - K2, 0) - (prem1 + prem2)；"
                "bull_spread: PnL = max(S_T-K1,0) - max(S_T-K2,0) - prem1 + prem2；"
                "bear_spread: PnL = max(K1-S_T,0) - max(K2-S_T,0) - prem1 + prem2；"
                "iron_condor: 4 Leg combination = bear put spread + bull call spread. "
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Option strategy profit and loss analysis failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_black_scholes_price",
    "get_implied_volatility",
    "get_option_greeks",
    "get_option_strategy_pnl",
]

# === screening.multi_factor_screening ===
"""Multi-factor stock picking tool.

Screen and score the entire A-share market based on user-specified factor conditions (PE, ROE, asset-liability ratio, etc.).
"""

import json
import logging
from typing import Annotated, Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_financial_periods
from core.tools.base import register_tool

logger = logging.getLogger(__name__)

# The upper limit of the candidate pool (the top N based on total market value are only used as screening candidates)
MAX_CANDIDATES = 500
DEFAULT_LIMIT = 30

# Supported factors and their field names in the data
SUPPORTED_FACTORS = {
    "pe_ttm": {"label": "市盈率(TTM)", "source": "basic_info", "fields": ["pe_ttm", "pe"]},
    "pb": {"label": "市净率", "source": "basic_info", "fields": ["pb", "pb_mrq"]},
    "ps_ttm": {"label": "市销率(TTM)", "source": "basic_info", "fields": ["ps_ttm", "ps"]},
    "total_mv": {"label": "总市值", "source": "basic_info", "fields": ["total_mv"]},
    "roe": {"label": "净资产收益率", "source": "financial", "fields": ["roe", "roe_avg", "roe_waa"]},
    "roa": {"label": "总资产收益率", "source": "financial", "fields": ["roa", "roa2"]},
    "debt_to_assets": {"label": "资产负债率", "source": "financial", "fields": ["debt_to_assets"]},
    "gross_margin": {"label": "毛利率", "source": "financial", "fields": ["grossprofit_margin", "gross_margin"]},
    "netprofit_margin": {"label": "净利率", "source": "financial", "fields": ["netprofit_margin"]},
    "current_ratio": {"label": "流动比率", "source": "financial", "fields": ["current_ratio"]},
}


def _multi_factor_screening_get_db():
    """Get a synchronous MongoDB connection."""
    from app.core.database import get_mongo_db_sync

    return get_mongo_db_sync()


def _multi_factor_screening_safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        text = str(value).strip()
        if not text:
            return None
        numeric = float(text)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _multi_factor_screening_get_field(record: Dict[str, Any], *field_names: str) -> Optional[float]:
    """Attempts to get field values from records in order of priority."""
    for field_name in field_names:
        value = _multi_factor_screening_safe_float(record.get(field_name))
        if value is not None:
            return value
    return None


def _parse_criteria(criteria_json: str) -> Tuple[Dict[str, Dict[str, float]], List[str]]:
    """Parse filter condition JSON and return (conditional dictionary, warning list). """
    warnings: List[str] = []
    try:
        raw = json.loads(criteria_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Conditional JSON parsing failed: {exc}")

    if not isinstance(raw, dict):
        raise ValueError("The condition must be a JSON object, such as {\"pe_ttm\": {\"min\": 0, \"max\": 20}}")

    parsed: Dict[str, Dict[str, float]] = {}
    for factor_key, constraints in raw.items():
        if factor_key not in SUPPORTED_FACTORS:
            warnings.append(f"不支持因子 '{factor_key}'，已忽略。支持: {', '.join(SUPPORTED_FACTORS)}")
            continue
        if not isinstance(constraints, dict):
            warnings.append(f"因子 '{factor_key}' 的条件格式错误，已忽略")
            continue
        parsed[factor_key] = {}
        for op_key in ("min", "max"):
            if op_key in constraints:
                try:
                    parsed[factor_key][op_key] = float(constraints[op_key])
                except (TypeError, ValueError):
                    warnings.append(f"因子 '{factor_key}' 的 {op_key} 值不是有效数值，已忽略")

    if not parsed:
        raise ValueError("未解析出任何有效条件")

    return parsed, warnings


def _multi_factor_screening_fetch_candidate_universe() -> List[Dict[str, Any]]:
    """Get the candidate stock pool from stock_basic_info (take the top N by market capitalization and PE>0) . """
    db = _multi_factor_screening_get_db()
    col = db["stock_basic_info"]

    cursor = col.find(
        {
            "total_mv": {"$gt": 0, "$exists": True},
            "pe_ttm": {"$gt": 0, "$exists": True},
        },
        {
            "_id": 0,
            "symbol": 1,
            "name": 1,
            "industry": 1,
            "pe_ttm": 1,
            "pe": 1,
            "pb": 1,
            "pb_mrq": 1,
            "ps_ttm": 1,
            "ps": 1,
            "total_mv": 1,
        },
    ).sort("total_mv", -1).limit(MAX_CANDIDATES)

    return list(cursor)


def _multi_factor_screening_enrich_with_financials(stocks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Supplement the most recent financial metrics (ROE, debt-to-asset ratio, etc.) for each stock."""
    enriched: Dict[str, Dict[str, Any]] = {}
    for stock in stocks:
        symbol = str(stock.get("symbol") or "").strip().zfill(6)
        if not symbol:
            continue

        # Copy from existing fields in basic_info
        enriched[symbol] = {
            "symbol": symbol,
            "name": stock.get("name", ""),
            "industry": stock.get("industry", ""),
            "pe_ttm": _multi_factor_screening_get_field(stock, "pe_ttm", "pe"),
            "pb": _multi_factor_screening_get_field(stock, "pb", "pb_mrq"),
            "ps_ttm": _multi_factor_screening_get_field(stock, "ps_ttm", "ps"),
            "total_mv": _multi_factor_screening_safe_float(stock.get("total_mv")),
        }

        # Obtain financial cycle data to supplement ROE, asset-liability ratio, etc.
        try:
            periods = get_stock_financial_periods(symbol, limit=1)
            if periods and isinstance(periods, list) and len(periods) > 0:
                latest = periods[0]
                roe = _multi_factor_screening_get_field(latest, "roe", "roe_avg", "roe_waa")
                if roe is not None:
                    enriched[symbol]["roe"] = roe

                debt_to_assets = _multi_factor_screening_get_field(latest, "debt_to_assets")
                if debt_to_assets is not None:
                    enriched[symbol]["debt_to_assets"] = debt_to_assets

                gross_margin = _multi_factor_screening_get_field(latest, "grossprofit_margin", "gross_margin")
                if gross_margin is not None:
                    enriched[symbol]["gross_margin"] = gross_margin

                netprofit_margin = _multi_factor_screening_get_field(latest, "netprofit_margin")
                if netprofit_margin is not None:
                    enriched[symbol]["netprofit_margin"] = netprofit_margin

                roa = _multi_factor_screening_get_field(latest, "roa", "roa2")
                if roa is not None:
                    enriched[symbol]["roa"] = roa

                current_ratio = _multi_factor_screening_get_field(latest, "current_ratio")
                if current_ratio is not None:
                    enriched[symbol]["current_ratio"] = current_ratio

        except Exception:
            pass  # Missing financial data does not block screening

    return enriched


def _get_factor_value(
    stock: Dict[str, Any],
    factor_key: str,
) -> Optional[float]:
    """Gets the value of the specified factor from stock data."""
    factor_def = SUPPORTED_FACTORS.get(factor_key)
    if not factor_def:
        return None
    return _multi_factor_screening_get_field(stock, *factor_def["fields"])


def _normalize_score(value: float, min_val: float, max_val: float) -> float:
    """Values are normalized to a scale of 0-100."""
    if max_val <= min_val:
        return 50.0
    clipped = max(min_val, min(max_val, value))
    return (clipped - min_val) / (max_val - min_val) * 100.0


def _score_stock(
    stock: Dict[str, Any],
    criteria: Dict[str, Dict[str, float]],
) -> Tuple[float, Dict[str, Any], List[str]]:
    """Score individual stocks.

    Returns:
        (total score, Scores and indicators for each factor, warning list)
    """
    all_warnings: List[str] = []
    factor_scores: Dict[str, Any] = {}
    score_sum = 0.0
    valid_factors = 0

    for factor_key, constraints in criteria.items():
        value = _get_factor_value(stock, factor_key)
        factor_label = SUPPORTED_FACTORS.get(factor_key, {}).get("label", factor_key)

        if value is None:
            all_warnings.append(f"{stock.get('symbol', '')} 缺少 {factor_label}")
            factor_scores[factor_key] = {"value": None, "score": 0, "passed": False}
            continue

        factor_scores[factor_key] = {"value": round(value, 4)}

        # Check if conditions are met
        passed = True
        min_val = constraints.get("min")
        max_val = constraints.get("max")

        if min_val is not None and value < min_val:
            passed = False
        if max_val is not None and value > max_val:
            passed = False

        factor_scores[factor_key]["passed"] = passed

        if not passed:
            factor_scores[factor_key]["score"] = 0
            continue

        # Calculate normalized score
        norm_min = min_val if min_val is not None else 0.0
        norm_max = max_val if max_val is not None else value * 2.0
        if min_val is None and max_val is not None:
            norm_min = 0.0
        if max_val is None and min_val is not None:
            norm_max = min_val * 2.0

        score = _normalize_score(value, norm_min, norm_max) if norm_max > norm_min else 50.0
        factor_scores[factor_key]["score"] = round(score, 1)
        score_sum += score
        valid_factors += 1

    total_score = round(score_sum / max(valid_factors, 1), 1)
    return total_score, factor_scores, all_warnings


@tool
@register_tool(
    tool_id="get_multi_factor_screening",
    name="多因子选股",
    description=(
        "Screen stocks from the entire A-share market based on user-specified multi-factor conditions and score each stock."
        "Supported factors: pe_ttm (price-to-earnings ratio), pb (price-to-book ratio), ps_ttm (price-to-sales ratio),"
        "total_mv (total market capitalization), roe (return on net assets), roa (return on total assets),"
        "debt_to_assets (Asset-liability ratio), gross_margin (gross profit margin),"
        "netprofit_margin (net interest rate), current_ratio (current ratio)."
        "The conditional format is JSON, such as {\"pe_ttm\": {\"min\": 0, \"max\": 20}, \"roe\": {\"min\": 15}}. "
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="heavy",
    capability_tags=["screening", "multi_factor", "fundamentals"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["多因子条件选股", "全市场批量筛选", "因子评分排序"],
    when_to_use=(
        "Use it when you need to screen stocks from the entire market based on multiple fundamental factors."
        "For example:PE<20 and ROE>15% And the debt-to-asset ratio<50%. "
        "The candidate pool selects the top 500 stocks based on total market capitalization."
    ),
    when_not_to_use=(
        "Not suitable for querying the detailed fundamental factors of a single stock (please use get_fundamental_factor_snapshot_tool);"
        "Not suitable for technical indicator stock selection or K-line pattern screening."
    ),
    returns=(
        "Returns a JSON string, including criteria_applied (applied conditions), total_screened (total number of candidates),"
        "passed (Number of passes), results (ranking list, including each factor score and total score), data_quality (data description)."
    ),
    example=(
        'get_multi_factor_screening(criteria=\'{"pe_ttm": {"min": 0, "max": 20}, '
        '"roe": {"min": 15}, "debt_to_assets": {"max": 50}}\')'
    ),
    related_tools=[
        "screen_stocks_by_criteria",
        "get_fundamental_factor_snapshot_tool",
        "get_value_factor_bundle_tool",
    ],
)
def get_multi_factor_screening(
    criteria: Annotated[str, "Factor condition JSON string, e.g. '{\"pe_ttm\": {\"min\": 0, \"max\": 20}, \"roe\": {\"min\": 15}}'"],
    sort_by: Annotated[str, "Sorting fields: score (total score), pe_ttm, pb, roe, total_mv, default score"] = "score",
    limit: Annotated[int, "Returns the top N stocks, default 30"] = DEFAULT_LIMIT,
) -> str:
    """Multi-factor stock picking tool.

    Screen the stocks that meet the multi-factor conditions from the entire A-share market (the top 500 stocks based on total market value are taken as the candidate pool),
    and calculate the overall score.

    Args:
        criteria: factor conditions JSON
        sort_by: sort field
        limit: Return quantity

    Returns:
        JSON Filter results in string format
    """
    try:
        limit = max(1, min(int(limit), 100))

        # 1. parsing conditions
        parsed_criteria, parse_warnings = _parse_criteria(criteria)

        # 2. Get candidate pool
        raw_candidates = _multi_factor_screening_fetch_candidate_universe()
        total_candidates = len(raw_candidates)

        if total_candidates == 0:
            return json.dumps(
                {
                    "status": "error",
                    "message": "No valid candidate stocks were obtained from stock_basic_info",
                },
                ensure_ascii=False,
                default=str,
            )

        # 3. Supplementary financial data
        enriched = _multi_factor_screening_enrich_with_financials(raw_candidates)

        # 4. Rating and filtering
        scored_results: List[Dict[str, Any]] = []
        all_warnings: List[str] = list(parse_warnings)

        for symbol, stock_data in enriched.items():
            total_score, factor_scores, stock_warnings = _score_stock(stock_data, parsed_criteria)
            all_warnings.extend(stock_warnings)

            # Check if all conditions are met (hard filtering)
            all_passed = all(
                fs.get("passed", False) for fs in factor_scores.values()
            )

            if all_passed:
                metrics = {
                    "pe_ttm": stock_data.get("pe_ttm"),
                    "pb": stock_data.get("pb"),
                    "total_mv": stock_data.get("total_mv"),
                }
                # Supplementary financial indicators
                for fin_key in ("roe", "roa", "debt_to_assets", "gross_margin", "netprofit_margin", "current_ratio"):
                    if fin_key in stock_data:
                        metrics[fin_key] = stock_data[fin_key]

                scored_results.append({
                    "symbol": symbol,
                    "name": stock_data.get("name", ""),
                    "industry": stock_data.get("industry", ""),
                    "score": total_score,
                    "factor_scores": factor_scores,
                    "metrics": {k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items() if v is not None},
                })

        # 5. sort
        reverse = True
        if sort_by in ("pe_ttm",):
            reverse = False  # The lower the valuation, the better

        if sort_by == "score":
            scored_results.sort(key=lambda x: x["score"], reverse=True)
        elif sort_by == "pe_ttm":
            scored_results.sort(
                key=lambda x: x.get("metrics", {}).get("pe_ttm", float("inf")),
                reverse=reverse,
            )
        elif sort_by == "pb":
            scored_results.sort(
                key=lambda x: x.get("metrics", {}).get("pb", float("inf")),
                reverse=reverse,
            )
        elif sort_by == "roe":
            scored_results.sort(
                key=lambda x: x.get("metrics", {}).get("roe", 0),
                reverse=True,
            )
        elif sort_by == "total_mv":
            scored_results.sort(
                key=lambda x: x.get("metrics", {}).get("total_mv", 0),
                reverse=True,
            )

        top_results = scored_results[:limit]

        # 6. Build output
        ranked_results = []
        for rank, item in enumerate(top_results, 1):
            ranked_results.append({
                "rank": rank,
                "symbol": item["symbol"],
                "name": item["name"],
                "industry": item["industry"],
                "score": item["score"],
                "factor_scores": item["factor_scores"],
                "metrics": item["metrics"],
            })

        payload = {
            "criteria_applied": {
                k: {op: round(v, 4) if isinstance(v, float) else v for op, v in constraints.items()}
                for k, constraints in parsed_criteria.items()
            },
            "total_screened": total_candidates,
            "passed": len(scored_results),
            "returned": len(ranked_results),
            "sort_by": sort_by,
            "results": ranked_results,
            "data_quality": {
                "candidates_examined": total_candidates,
                "financial_data_enriched": len(enriched),
                "warnings": all_warnings[:20],  # Truncate too long warning
                "note": (
                    "The candidate pool is the top 500 A-shares sorted by total market capitalization (pe_ttm>0 and total_mv>0) . "
                    "ROE, Financial indicators such as asset-liability ratio are obtained from the latest financial report, which may be incomplete due to data synchronization delays."
                ),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except ValueError as ve:
        return json.dumps({"status": "error", "message": str(ve)}, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.error("多因子选股失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_multi_factor_screening"]

# === screening.value_screening ===
"""Value filtering toolset.

Provides 4 policy filtering tools:
1. get_graham_screen - Graham filter (low valuation, low debt, positive profits)
2. get_growth_stock_screen - Growth stock screening (high growth, high ROE)
3. get_dividend_stock_screen - Dividend stock screening (high dividends, stable dividends)
4. get_turnaround_screen - Dilemma reversal filter
"""

import json
import logging
import math
from typing import Annotated, Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_financial_periods
from core.tools.base import register_tool
from core.tools.implementations.risk.extended_risk_models import (
    _detect_period_type,
    _annualize_factor,
    _find_same_period_prev,
    _PERIOD_LABELS,
)

logger = logging.getLogger(__name__)

# Candidate pool upper limit
MAX_CANDIDATES = 500
DEFAULT_LIMIT = 30


def _value_screening_get_db():
    """Get a synchronous MongoDB connection."""
    from app.core.database import get_mongo_db_sync
    return get_mongo_db_sync()


def _value_screening_safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        text = str(value).strip()
        if not text:
            return None
        numeric = float(text)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _value_screening_get_field(record: Dict[str, Any], *field_names: str) -> Optional[float]:
    """Attempts to get field values from records in order of priority."""
    for field_name in field_names:
        value = _value_screening_safe_float(record.get(field_name))
        if value is not None:
            return value
    return None


def _value_screening_fetch_candidate_universe(extra_fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Get the candidate stock pool from stock_basic_info (take the top N by market capitalization and PE>0) . """
    db = _value_screening_get_db()
    col = db["stock_basic_info"]

    projection = {
        "_id": 0,
        "symbol": 1,
        "name": 1,
        "industry": 1,
        "pe_ttm": 1,
        "pe": 1,
        "pb": 1,
        "pb_mrq": 1,
        "total_mv": 1,
        "dividend_yield": 1,
        "dividend_yield_ttm": 1,
    }
    if extra_fields:
        for f in extra_fields:
            projection[f] = 1

    cursor = col.find(
        {
            "total_mv": {"$gt": 0, "$exists": True},
            "pe_ttm": {"$gt": 0, "$exists": True},
        },
        projection,
    ).sort("total_mv", -1).limit(MAX_CANDIDATES)

    return list(cursor)


def _value_screening_enrich_with_financials(
    stocks: List[Dict[str, Any]],
    extra_fields: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Supplement the most recent financial metrics for each stock."""
    enriched: Dict[str, Dict[str, Any]] = {}
    for stock in stocks:
        symbol = str(stock.get("symbol") or "").strip().zfill(6)
        if not symbol:
            continue

        record: Dict[str, Any] = {
            "symbol": symbol,
            "name": stock.get("name", ""),
            "industry": stock.get("industry", ""),
            "pe_ttm": _value_screening_get_field(stock, "pe_ttm", "pe"),
            "pb": _value_screening_get_field(stock, "pb", "pb_mrq"),
            "total_mv": _value_screening_safe_float(stock.get("total_mv")),
            "dividend_yield": _value_screening_get_field(stock, "dividend_yield", "dividend_yield_ttm"),
        }
        if extra_fields:
            for f in extra_fields:
                val = _value_screening_safe_float(stock.get(f))
                if val is not None:
                    record[f] = val

        try:
            periods = get_stock_financial_periods(symbol, limit=4)
            if periods and isinstance(periods, list) and len(periods) > 0:
                latest = periods[0]

                roe = _value_screening_get_field(latest, "roe", "roe_avg", "roe_waa")
                if roe is not None:
                    record["roe"] = roe

                debt_to_assets = _value_screening_get_field(latest, "debt_to_assets")
                if debt_to_assets is not None:
                    record["debt_to_assets"] = debt_to_assets

                net_profit = _value_screening_get_field(latest, "net_profit", "n_income_attr_p", "n_income", "net_income")
                if net_profit is not None:
                    record["net_profit"] = net_profit

                revenue = _value_screening_get_field(latest, "revenue", "total_revenue", "oper_rev")
                if revenue is not None:
                    record["revenue"] = revenue

                n_cashflow_act = _value_screening_get_field(latest, "n_cashflow_act")
                if n_cashflow_act is not None:
                    record["n_cashflow_act"] = n_cashflow_act

                total_liab = _value_screening_get_field(latest, "total_liab")
                total_equity = _value_screening_get_field(latest, "total_equity", "total_hldr_eqy_exc_min_int")
                if total_liab is not None and total_equity is not None and total_equity > 0:
                    record["debt_to_equity"] = total_liab / total_equity

                gross_margin = _value_screening_get_field(latest, "grossprofit_margin", "gross_margin")
                if gross_margin is not None:
                    record["gross_margin"] = gross_margin

                # Multi-period data used for growth calculations
                if len(periods) >= 2:
                    rev_growth = _calc_growth(periods, "revenue", "total_revenue", "oper_rev")
                    if rev_growth is not None:
                        record["revenue_growth"] = rev_growth

                    np_growth = _calc_growth(periods, "net_profit", "n_income_attr_p", "n_income", "net_income")
                    if np_growth is not None:
                        record["net_profit_growth"] = np_growth

                # Try calculating 3-year growth (requires multiple periods of data)
                if len(periods) >= 4:
                    rev_growth_3y = _calc_cagr_3y(periods, "revenue", "total_revenue", "oper_rev")
                    if rev_growth_3y is not None:
                        record["revenue_growth_3y"] = rev_growth_3y

        except Exception:
            pass  # Missing financial data does not block screening

    return enriched


def _calc_growth(periods: List[Dict[str, Any]], *fields: str) -> Optional[float]:
    """Calculate the year-on-year growth rate between the latest two periods and automatically handle caliber differences.

    If the caliber of the two periods is inconsistent (such as a quarterly report vs an annual report), first annualize the non-annual report period and then compare.
    Only skip if the calibers are completely different (for example, annual report vs. quarterly report cannot be compared on a simple annualized basis).
    """
    if len(periods) < 2:
        return None
    cur_type = _detect_period_type(periods[0])
    prev_type = _detect_period_type(periods[1])

    current = _value_screening_get_field(periods[0], *fields)
    previous = _value_screening_get_field(periods[1], *fields)

    if current is None or previous is None or previous == 0:
        return None

    # 🔑 Compare directly when calibers are the same
    if cur_type == prev_type:
        return (current - previous) / abs(previous)

    # 🔑 When the calibers are inconsistent, compare after annualization (income statement accounts need to be annualized)
    # Only annualize accounts that may be the cumulative value of the income statement (revenue / net_profit, etc.)
    cur_annualized = current * _annualize_factor(cur_type)
    prev_annualized = previous * _annualize_factor(prev_type)
    if prev_annualized == 0:
        return None
    return (cur_annualized - prev_annualized) / abs(prev_annualized)


def _calc_cagr_3y(periods: List[Dict[str, Any]], *fields: str) -> Optional[float]:
    """Calculate CAGR over approximately 3 years. Take the latest and oldest data (about 3 years ago).

    periods Arrange in reverse order of reporting period, taking issue 0 (latest) and min(3, len-1) period.
    It is only calculated when the caliber of the two periods is the same (both are annual reports or the same quarterly report type), otherwise None is returned.
    """
    if len(periods) < 4:
        return None
    cur_type = _detect_period_type(periods[0])
    older_type = _detect_period_type(periods[3])

    current = _value_screening_get_field(periods[0], *fields)
    older = _value_screening_get_field(periods[3], *fields)

    if current is None or older is None or older <= 0 or current <= 0:
        return None

    # 🔑 CAGR The caliber must be consistent, otherwise it will be meaningless to compare New Year's Eve.
    if cur_type != older_type:
        return None

    ratio = current / older
    if ratio > 0:
        return ratio ** (1.0 / 3.0) - 1.0
    return None


def _score_item(
    score_components: List[Tuple[Optional[float], float, float]],
) -> float:
    """Calculate a weighted composite score.

    Args:
        score_components: [(value, weight, Maximum normalization), ...]
            If the value is None, the component is skipped.
    """
    total_weight = 0.0
    weighted_sum = 0.0
    for value, weight, max_norm in score_components:
        if value is not None:
            # normalized to 0-100
            normalized = min(100.0, max(0.0, value / max_norm * 100)) if max_norm > 0 else 50.0
            weighted_sum += normalized * weight
            total_weight += weight
    return round(weighted_sum / max(total_weight, 0.001), 1)


# ────────────────────────────────────────────────────────────────
# Tool 7: Graham filter
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_graham_screen",
    name="格雷厄姆式筛选",
    description=(
        "Follow Benjamin·Graham s value investing criteria screen for A-shares."
        "Conditions:PE < 15, PB < 1.5, debt-to-equity ratio < 1.0, Net profit is positive."
        "According to Graham s number (√(22.5 × EPS × BVPS))  upside Sort."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="heavy",
    capability_tags=["screening", "value_investing", "graham", "fundamentals", "valuation"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["价值投资选股", "格雷厄姆策略", "低估股票筛选"],
    when_to_use=(
        "When users want to find value stocks with low valuations and select stocks according to Graham s margin of safety principle,"
        "Or when you need a list of stocks with low valuations."
    ),
    when_not_to_use=(
        "Not suitable for screening growth stocks and loss-making companies;"
        "Not suitable for scenarios that require filtering of technical indicators or industry themes."
    ),
    returns=(
        "Returns a JSON string containing criteria_applied, total_screened,"
        "passed, results (Sort by Graham number upside)."
    ),
    example="get_graham_screen(limit=30)",
    related_tools=[
        "get_growth_stock_screen",
        "get_dividend_stock_screen",
        "get_multi_factor_screening",
    ],
)
def get_graham_screen(
    limit: Annotated[int, "Returns the top N stocks, default 30"] = 30,
) -> str:
    """Graham value filter.

    Args:
        limit: Return the first N stocks, default 30, automatically clamp to [1, 100]

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description

        In case of success, return dict, fields:
            criteria_applied: Filter criteria dict —
                pe_ttm: dict — max: 15
                pb: dict — max: 1.5
                debt_to_equity: dict — max: 1.0
                net_profit: dict — min: 0
            total_screened: Total number of candidate pools
            passed: Number of stocks that passed screening
            returned: actual returned quantity
            results: Sorted stock list [{"rank": serial number, "symbol": code, "name": Name, "industry": Industry, "score": Comprehensive score, "pe_ttm": P/E ratio, "pb": price to book ratio, "debt_to_equity": debt to equity ratio, "graham_number": Graham number, "graham_upside_pct": Graham s number upside percentage}, ...]
            data_quality: Data quality dict —
                note: Candidate pool and method description text

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        limit = max(1, min(int(limit), 100))

        raw_candidates = _value_screening_fetch_candidate_universe()
        total_candidates = len(raw_candidates)

        if total_candidates == 0:
            return json.dumps(
                {"status": "error", "message": "未获取到候选股票"},
                ensure_ascii=False, indent=2, default=str,
            )

        enriched = _value_screening_enrich_with_financials(raw_candidates)

        criteria = {
            "pe_ttm": {"max": 15},
            "pb": {"max": 1.5},
            "debt_to_equity": {"max": 1.0},
            "net_profit": {"min": 0},
        }

        passed_results: List[Dict[str, Any]] = []
        for symbol, data in enriched.items():
            pe = data.get("pe_ttm")
            pb = data.get("pb")
            debt_eq = data.get("debt_to_equity")
            net_profit = data.get("net_profit")

            if pe is None or pb is None:
                continue
            if pe <= 0 or pe >= 15:
                continue
            if pb <= 0 or pb >= 1.5:
                continue
            if debt_eq is not None and debt_eq >= 1.0:
                continue
            if net_profit is not None and net_profit <= 0:
                continue
            # If net_profit is missing, try other profit fields
            if net_profit is None:
                continue

            # Graham number = √(22.5 × EPS × BVPS)
            # EPS ≈ net_profit / shares, BVPS ≈ equity / shares
            # Graham Number ≈ √(22.5 × NetProfit × Equity) / shares
            # Simplification: Graham numbers upside = (graham_price - current_price) / current_price
            total_equity = data.get("total_mv") / pb if pb and pb > 0 and data.get("total_mv") else None
            if total_equity and data.get("total_mv"):
                # graham_number = sqrt(22.5 * net_profit * total_equity) / (total_mv / price)
                # Simplify calculations upside
                eps = net_profit / (data["total_mv"] / pe) if pe and pe > 0 else None
                bvps = total_equity / (data["total_mv"] / pe) if pe and pe > 0 else None

                graham_number = None
                if eps is not None and bvps is not None and eps > 0 and bvps > 0:
                    graham_number = math.sqrt(22.5 * eps * bvps)
            else:
                graham_number = None

            current_price = data["total_mv"] / (data["total_mv"] / pe) if pe and pe > 0 else None
            upside = None
            if graham_number is not None and current_price is not None and current_price > 0:
                upside = (graham_number - current_price) / current_price * 100

            score_components: List[Tuple[Optional[float], float, float]] = [
                (pe, 1.0, 15.0) if pe else (None, 0, 1),
                (pb, 1.0, 1.5) if pb else (None, 0, 1),
            ]
            # Invert PE and PB scores (lower is better)
            pe_score = max(0, 100 - (pe / 15 * 100)) if pe else 0
            pb_score = max(0, 100 - (pb / 1.5 * 100)) if pb else 0
            total_score = round((pe_score + pb_score) / 2, 1)

            passed_results.append({
                "symbol": symbol,
                "name": data.get("name", ""),
                "industry": data.get("industry", ""),
                "pe_ttm": pe,
                "pb": pb,
                "debt_to_equity": round(debt_eq, 4) if debt_eq is not None else None,
                "net_profit": round(net_profit, 2) if net_profit is not None else None,
                "graham_number": round(graham_number, 2) if graham_number is not None else None,
                "graham_upside_pct": round(upside, 2) if upside is not None else None,
                "score": total_score,
            })

        # Sort by upside descending
        passed_results.sort(key=lambda x: x.get("graham_upside_pct") or -9999, reverse=True)
        top_results = passed_results[:limit]

        ranked = []
        for rank, item in enumerate(top_results, 1):
            ranked.append({
                "rank": rank,
                "symbol": item["symbol"],
                "name": item["name"],
                "industry": item["industry"],
                "score": item["score"],
                "pe_ttm": item["pe_ttm"],
                "pb": item["pb"],
                "debt_to_equity": item["debt_to_equity"],
                "graham_number": item["graham_number"],
                "graham_upside_pct": item["graham_upside_pct"],
            })

        payload = {
            "criteria_applied": criteria,
            "total_screened": total_candidates,
            "passed": len(passed_results),
            "returned": len(ranked),
            "results": ranked,
            "data_quality": {
                "note": (
                    "The candidate pool is the top 500 A-shares sorted by total market capitalization (pe_ttm>0 and total_mv>0) . "
                    "Graham number = √(22.5 × EPS × BVPS). "
                    "debt_to_equity Calculated from the latest financial report, missing information will not be excluded."
                ),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Graham filter failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 8: Growth Stock Screening
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_growth_stock_screen",
    name="成长股筛选",
    description=(
        "Screen A shares according to growth investment criteria."
        "Conditions: Revenue growth rate in the past three years > 20%, ROE > 15%, PE < 50. "
        "Sort by PEG ratio (PE/Growth) score."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="heavy",
    capability_tags=["screening", "growth", "investing", "fundamentals"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["成长股筛选", "高增长策略", "PEG 选股"],
    when_to_use=(
        "When users want to find high-growth stocks and select stocks based on PEG standards,"
        "Or use it when you need to screen companies with excellent revenue and ROE."
    ),
    when_not_to_use=(
        "Not suitable for screening value stocks, loss-making companies, and financial companies;"
        "Growth rate cannot be calculated when there is insufficient data (financial data for less than 2 periods)."
    ),
    returns=(
        "Returns a JSON string containing criteria_applied, total_screened,"
        "passed, results (Sorted in ascending order by PEG)."
    ),
    example="get_growth_stock_screen(limit=30)",
    related_tools=[
        "get_graham_screen",
        "get_dividend_stock_screen",
        "get_multi_factor_screening",
    ],
)
def get_growth_stock_screen(
    limit: Annotated[int, "Returns the top N stocks, default 30"] = 30,
) -> str:
    """Growth stock screening.

    Args:
        limit: Return the first N stocks, default 30, automatically clamp to [1, 100]

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description

        In case of success, return dict, fields:
            criteria_applied: Filter criteria dict —
                revenue_growth_3y: dict — min: 20
                roe: dict — min: 15
                pe_ttm: dict — max: 50
            total_screened: Total number of candidate pools
            passed: Number of stocks that passed screening
            returned: actual returned quantity
            results: List of stocks in ascending order by PEG [{"rank": serial number, "symbol": code, "name": Name, "industry": Industry, "score": Comprehensive score, "revenue_growth_3y_pct": 3 Annual revenue CAGR percentage, "roe": ROE, "pe_ttm": P/E ratio, "peg": PEG Ratio}, ...]
            data_quality: Data quality dict —
                note: Candidate pool and method description text

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        limit = max(1, min(int(limit), 100))

        raw_candidates = _value_screening_fetch_candidate_universe()
        total_candidates = len(raw_candidates)

        if total_candidates == 0:
            return json.dumps(
                {"status": "error", "message": "未获取到候选股票"},
                ensure_ascii=False, indent=2, default=str,
            )

        enriched = _value_screening_enrich_with_financials(raw_candidates)

        criteria = {
            "revenue_growth_3y": {"min": 20},  # 20% CAGR
            "roe": {"min": 15},  # 15% ROE
            "pe_ttm": {"max": 50},
        }

        passed_results: List[Dict[str, Any]] = []
        for symbol, data in enriched.items():
            growth_3y = data.get("revenue_growth_3y")
            roe = data.get("roe")
            pe = data.get("pe_ttm")

            if growth_3y is None or roe is None or pe is None:
                continue
            if growth_3y <= 0.20:  # 20% CAGR
                continue
            if roe <= 15:
                continue
            if pe <= 0 or pe >= 50:
                continue

            # PEG = PE / (growth rate × 100)
            peg = pe / (growth_3y * 100) if growth_3y > 0 else 999

            # Score: The lower the PEG, the better
            peg_score = max(0, 100 - peg * 20) if peg < 5 else max(0, 100 - peg * 10)
            roe_score = min(100, roe / 15 * 100)
            total_score = round((peg_score + roe_score) / 2, 1)

            passed_results.append({
                "symbol": symbol,
                "name": data.get("name", ""),
                "industry": data.get("industry", ""),
                "revenue_growth_3y_pct": round(growth_3y * 100, 2),
                "roe": round(roe, 2),
                "pe_ttm": pe,
                "peg": round(peg, 2),
                "score": total_score,
            })

        # Sort by PEG ascending
        passed_results.sort(key=lambda x: x.get("peg") or 9999)
        top_results = passed_results[:limit]

        ranked = []
        for rank, item in enumerate(top_results, 1):
            ranked.append({
                "rank": rank,
                "symbol": item["symbol"],
                "name": item["name"],
                "industry": item["industry"],
                "score": item["score"],
                "revenue_growth_3y_pct": item["revenue_growth_3y_pct"],
                "roe": item["roe"],
                "pe_ttm": item["pe_ttm"],
                "peg": item["peg"],
            })

        payload = {
            "criteria_applied": criteria,
            "total_screened": total_candidates,
            "passed": len(passed_results),
            "returned": len(ranked),
            "results": ranked,
            "data_quality": {
                "note": (
                    "The candidate pool is the top 500 A-shares sorted by total market capitalization (pe_ttm>0 and total_mv>0) . "
                    "revenue_growth_3y It is the revenue CAGR in the past 3 years, calculated from the latest 3-4 periods of financial data."
                    "ROE It is the latest reporting period value.PEG = PE / (revenue growth rate×100). "
                ),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("成长股筛选失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 9: Bonus stock screening
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_dividend_stock_screen",
    name="红利股筛选",
    description=(
        "Screen A shares according to dividend investment criteria."
        "Condition: Dividend rate > 3%, Continuous dividends >= 3 Annual dividend rate is 20%-80%."
        "Comprehensive dividend yield and financial health score ranking."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="heavy",
    capability_tags=["screening", "dividend", "income", "fundamentals"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["红利股筛选", "高股息策略", "分红选股"],
    when_to_use=(
        "When users want to find stocks with high dividend yields and build dividend investment portfolios,"
        "Or use it when screening companies with stable and sustainable dividends."
    ),
    when_not_to_use=(
        "Not suitable for screening growth stocks and loss-making companies;"
        "Dividend yield data may be missing (requires dividend_yield field in basic_info)."
    ),
    returns=(
        "Returns a JSON string containing criteria_applied, total_screened,"
        "passed, results (Sorted by overall score)."
    ),
    example="get_dividend_stock_screen(limit=30)",
    related_tools=[
        "get_graham_screen",
        "get_growth_stock_screen",
        "get_multi_factor_screening",
    ],
)
def get_dividend_stock_screen(
    limit: Annotated[int, "Returns the top N stocks, default 30"] = 30,
) -> str:
    """Bonus stock screening.

    Args:
        limit: Return the first N stocks, default 30, automatically clamp to [1, 100]

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description

        In case of success, return dict, fields:
            criteria_applied: Filter criteria dict —
                dividend_yield: dict — min: 3
                payout_ratio: dict — min: 0.2, max: 0.8
                consecutive_dividend_years: dict — min: 3
            total_screened: Total number of candidate pools
            passed: Number of stocks that passed screening
            returned: actual returned quantity
            results: List of stocks in descending order by dividend yield [{"rank": serial number, "symbol": code, "name": Name, "industry": Industry, "score": Comprehensive score, "dividend_yield_pct": Dividend Yield Percent, "pe_ttm": P/E ratio, "payout_ratio": dividend rate}, ...]
            data_quality: Data quality dict —
                note: Candidate pool and method description text

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        limit = max(1, min(int(limit), 100))

        raw_candidates = _value_screening_fetch_candidate_universe(extra_fields=["dividend_yield", "dividend_yield_ttm"])
        total_candidates = len(raw_candidates)

        if total_candidates == 0:
            return json.dumps(
                {"status": "error", "message": "未获取到候选股票"},
                ensure_ascii=False, indent=2, default=str,
            )

        enriched = _value_screening_enrich_with_financials(raw_candidates)

        criteria = {
            "dividend_yield": {"min": 3},  # 3%
            "payout_ratio": {"min": 0.2, "max": 0.8},
            "consecutive_dividend_years": {"min": 3},
        }

        passed_results: List[Dict[str, Any]] = []
        for symbol, data in enriched.items():
            div_yield = data.get("dividend_yield")
            pe = data.get("pe_ttm")

            if div_yield is None:
                continue
            # dividend_yield May be in decimal form (e.g. 0.03 = 3%) or as a percentage (such as 3.0)
            # Try to judge: if value < 1, Treat as a decimal, otherwise as a percentage
            if div_yield < 1:
                div_yield_pct = div_yield * 100
            else:
                div_yield_pct = div_yield

            if div_yield_pct < 3.0:
                continue

            # dividend rate = dividend yield × PE (simplified estimation)
            payout_ratio = None
            if pe is not None and pe > 0:
                payout_ratio = div_yield_pct * pe / 100

            if payout_ratio is not None and (payout_ratio < 0.2 or payout_ratio > 0.8):
                continue

            # Number of consecutive dividend years (simplified: judged from financial data >= 3 period positive profit)
            net_profit = data.get("net_profit")
            if net_profit is None or net_profit <= 0:
                continue

            # score
            div_score = min(100, div_yield_pct / 3 * 100)
            pe_score = max(0, 100 - (pe / 50 * 100)) if pe else 50
            total_score = round((div_score + pe_score) / 2, 1)

            passed_results.append({
                "symbol": symbol,
                "name": data.get("name", ""),
                "industry": data.get("industry", ""),
                "dividend_yield_pct": round(div_yield_pct, 2),
                "pe_ttm": pe,
                "payout_ratio": round(payout_ratio, 4) if payout_ratio is not None else None,
                "net_profit": round(net_profit, 2) if net_profit is not None else None,
                "score": total_score,
            })

        # Sort descending by dividend yield
        passed_results.sort(key=lambda x: x.get("dividend_yield_pct") or 0, reverse=True)
        top_results = passed_results[:limit]

        ranked = []
        for rank, item in enumerate(top_results, 1):
            ranked.append({
                "rank": rank,
                "symbol": item["symbol"],
                "name": item["name"],
                "industry": item["industry"],
                "score": item["score"],
                "dividend_yield_pct": item["dividend_yield_pct"],
                "pe_ttm": item["pe_ttm"],
                "payout_ratio": item["payout_ratio"],
            })

        payload = {
            "criteria_applied": criteria,
            "total_screened": total_candidates,
            "passed": len(passed_results),
            "returned": len(ranked),
            "results": ranked,
            "data_quality": {
                "note": (
                    "The candidate pool is the top 500 A-shares sorted by total market capitalization."
                    "The dividend yield comes from the dividend_yield field of stock_basic_info."
                    "dividend rate = dividend yield × PE, To simplify the estimates."
                    "The number of consecutive dividend years is determined based on whether the net profit has been positive for multiple consecutive periods."
                ),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("红利股筛选失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 10: Dilemma reversal filter
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_turnaround_screen",
    name="困境反转筛选",
    description=(
        "Screen for stocks that may be in the reversal stage of distress."
        "Conditions:PE < 20, Revenue growth rate improved from negative to positive, and operating cash flow became positive."
        "Look for companies that have recently lost money but have a clear trend of improvement."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="heavy",
    capability_tags=["screening", "turnaround", "turnaround_investing", "fundamentals"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["困境反转策略", "逆境反转选股", "拐点型投资"],
    when_to_use=(
        "When users want to find stocks that are struggling but improving,"
        "Use it when mining for performance turning point investment opportunities or screening low-valuation reversal candidate stocks."
    ),
    when_not_to_use=(
        "Not suitable for screening stable growth companies;"
        "Multi-period financial data are needed to determine trends, and incomplete results will be given when the data is insufficient."
    ),
    returns=(
        "Returns a JSON string containing criteria_applied, total_screened,"
        "passed, results (Sort by improvement)."
    ),
    example="get_turnaround_screen(limit=30)",
    related_tools=[
        "get_graham_screen",
        "get_growth_stock_screen",
        "get_multi_factor_screening",
    ],
)
def get_turnaround_screen(
    limit: Annotated[int, "Returns the top N stocks, default 30"] = 30,
) -> str:
    """Dilemma reversal screening.

    Args:
        limit: Return the first N stocks, default 30, automatically clamp to [1, 100]

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description

        In case of success, return dict, fields:
            criteria_applied: Filter criteria dict —
                pe_ttm: dict — max: 20
                revenue_growth_improving: Improve judgment description text
                n_cashflow_act: dict — min: 0
            total_screened: Total number of candidate pools
            passed: Number of stocks that passed screening
            returned: actual returned quantity
            results: List of stocks in descending order of improvement scores [{"rank": serial number, "symbol": code, "name": Name, "industry": Industry, "pe_ttm": P/E ratio, "revenue_growth_pct": revenue growth percentage, "operating_cashflow": operating cash flow, "net_profit": net profit, "roe": ROE, "improvement_score": Improve rating}, ...]
            data_quality: Data quality dict —
                note: Candidate pool and method description text

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        limit = max(1, min(int(limit), 100))

        raw_candidates = _value_screening_fetch_candidate_universe()
        total_candidates = len(raw_candidates)

        if total_candidates == 0:
            return json.dumps(
                {"status": "error", "message": "未获取到候选股票"},
                ensure_ascii=False, indent=2, default=str,
            )

        enriched = _value_screening_enrich_with_financials(raw_candidates)

        criteria = {
            "pe_ttm": {"max": 20},
            "revenue_growth_improving": "The revenue growth rate has improved in the past two periods (negative→Positive or narrowing)",
            "n_cashflow_act": {"min": 0},  # Operating cash flow is positive
        }

        passed_results: List[Dict[str, Any]] = []
        for symbol, data in enriched.items():
            pe = data.get("pe_ttm")
            revenue_growth = data.get("revenue_growth")
            n_cashflow_act = data.get("n_cashflow_act")
            net_profit = data.get("net_profit")
            roe = data.get("roe")

            if pe is None or pe <= 0 or pe >= 20:
                continue

            if n_cashflow_act is None or n_cashflow_act <= 0:
                continue

            # Determine improvement trends: revenue growth turns from negative to positive or losses narrow
            improving = False
            improvement_score = 0

            if revenue_growth is not None:
                # Revenue growth improvement: negative but improving
                if revenue_growth > -0.1:  # Losses narrowed to within -10%
                    improving = True
                    improvement_score += 50
                if revenue_growth > 0:  # Has become a regular
                    improving = True
                    improvement_score += 100

            # Positive operating cash flow indicates that hematopoietic ability is recovering
            if n_cashflow_act > 0:
                improvement_score += 30

            # If there is still a net loss in the most recent period but operating cash flow turns positive, the score will be higher
            if net_profit is not None and net_profit < 0 and n_cashflow_act > 0:
                improvement_score += 40  # Cash flow is a stronger signal

            if not improving and (net_profit is None or net_profit < 0):
                # There must be at least one signal of improvement
                if net_profit is None:
                    continue

            total_score = min(100, improvement_score)

            passed_results.append({
                "symbol": symbol,
                "name": data.get("name", ""),
                "industry": data.get("industry", ""),
                "pe_ttm": pe,
                "revenue_growth_pct": round(revenue_growth * 100, 2) if revenue_growth is not None else None,
                "operating_cashflow": round(n_cashflow_act, 2) if n_cashflow_act is not None else None,
                "net_profit": round(net_profit, 2) if net_profit is not None else None,
                "roe": round(roe, 2) if roe is not None else None,
                "improvement_score": total_score,
            })

        # Sort descending by improvement score
        passed_results.sort(key=lambda x: x.get("improvement_score") or 0, reverse=True)
        top_results = passed_results[:limit]

        ranked = []
        for rank, item in enumerate(top_results, 1):
            ranked.append({
                "rank": rank,
                "symbol": item["symbol"],
                "name": item["name"],
                "industry": item["industry"],
                "pe_ttm": item["pe_ttm"],
                "revenue_growth_pct": item["revenue_growth_pct"],
                "operating_cashflow": item["operating_cashflow"],
                "net_profit": item["net_profit"],
                "roe": item["roe"],
                "improvement_score": item["improvement_score"],
            })

        payload = {
            "criteria_applied": criteria,
            "total_screened": total_candidates,
            "passed": len(passed_results),
            "returned": len(ranked),
            "results": ranked,
            "data_quality": {
                "note": (
                    "The candidate pool is the top 500 A-shares sorted by total market capitalization (pe_ttm>0 and total_mv>0) . "
                    "Improvement judgment is based on the year-on-year revenue growth of the latest two periods of financial data."
                    "Positive operating cash flow indicates that the company s hematopoietic ability has recovered."
                ),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("困境反转筛选失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = [
    "get_graham_screen",
    "get_growth_stock_screen",
    "get_dividend_stock_screen",
    "get_turnaround_screen",
]

# === standard_financial_tools ===
"""Standard financial data capability tools.

These tools encapsulate core.skill_runtime.standard_financial_apis and expose structured and auditable common stock analysis data capabilities to Agent.
"""

import json
import logging
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.skill_runtime.standard_financial_apis import (
    get_adjusted_price_series,
    get_capital_efficiency_trend,
    get_capital_flow_series,
    get_cashflow_quality_trend,
    get_chip_distribution_context,
    get_company_announcements,
    get_company_event_timeline,
    get_current_valuation_snapshot,
    get_debt_solvency_trend,
    get_drawdown_metrics,
    get_growth_quality_metrics,
    get_historical_financial_annual_series,
    get_historical_valuation_percentile,
    get_industry_fundamental_summary,
    get_industry_market_performance,
    get_business_segment_trend,
    get_margin_stability_metrics,
    get_peer_group,
    get_peer_relative_growth,
    get_peer_relative_quality,
    get_peer_relative_valuation,
    get_pledge_historical_series,
    get_pledge_risk_profile,
    get_portfolio_risk_profile,
    get_profitability_stability_metrics,
    get_return_series,
    get_risk_event_flags,
    get_security_master,
    get_shareholder_return_metrics,
    get_single_stock_risk_profile,
    get_technical_indicator_series,
    get_volatility_metrics,
)
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _standard_financial_tools_json_response(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _parse_metrics(metrics: Optional[str]) -> list[str] | None:
    if not metrics:
        return None
    items = [item.strip().lower() for item in str(metrics).replace("，", ",").split(",") if item.strip()]
    return items or None


def _parse_positions(positions_json: str) -> list[dict]:
    data = json.loads(positions_json or "[]")
    if isinstance(data, dict):
        data = data.get("positions") or []
    if not isinstance(data, list):
        raise ValueError("positions_json Must be an array of positions or a JSON object containing a positions field")
    return [item for item in data if isinstance(item, dict)]


@tool
@register_tool(
    tool_id="get_company_event_timeline_tool",
    name="公司公告监管事件时间线",
    description="Structured return to official announcement/regulatory event timeline; local announcement data takes precedence, using news agent to identify events when missing.",
    category="news",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when a timeline of events such as formal announcements, regulatory letters, penalties, shareholding reductions, pledges, litigation, dividend announcements, etc. is needed.",
    when_not_to_use="Not suitable for real-time news stream monitoring (use get_stock_news); not suitable for informal/social media anecdotes; not suitable for quantitative event studies (use get_event_study).",
    capability_tags=["event", "announcement", "regulatory"],
    tool_role_hint="specialized",
    returns="Returns a JSON string containing events, summary, coverage, and warnings.",
    example="get_company_event_timeline_tool(symbol='600519', lookback_days=365)",
    related_tools=["get_risk_event_flags_tool", "get_company_announcements_tool", "get_event_study", "get_stock_news"],
)
def get_company_event_timeline_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back, default 365"] = 365,
    event_types: Annotated[str, "Comma separated event types, can be empty"] = "",
    limit: Annotated[int, "Maximum number of events returned, default 100"] = 100,
) -> str:
    """Get a timeline of company announcements/regulatory events.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back, default 365
        event_types: Comma separated event types, can be empty
        limit: Maximum number of events returned, default 100

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_company_event_timeline`` of Returns ——
            status, symbol, window, data_source, events, summary(event_count/type_counts/high_severity_count),
            warnings
    """
    try:
        return _standard_financial_tools_json_response(get_company_event_timeline(symbol, lookback_days=lookback_days, event_types=_parse_metrics(event_types), limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain company announcement regulatory event timeline: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"Failed to obtain company announcement regulatory event timeline: {exc}"})


@tool
@register_tool(
    tool_id="get_business_segment_trend_tool",
    name="主营结构趋势",
    description="Structured return of main business segment revenue, gross profit, gross profit margin, revenue proportion, Top1/Top3 concentration and HHI trend.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "business_segment", "segment_revenue", "segment_margin", "revenue_mix",
        "product_mix", "regional_mix", "gross_margin", "segment_gross_margin",
        "concentration", "hhi", "top1_concentration", "top3_concentration",
        "business_structure", "revenue_composition", "diversification",
        "moat_analysis", "competitive_advantage", "time_series",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "business_segment_analysis", "revenue_mix_trend", "concentration_analysis",
        "product_mix_analysis", "regional_mix_analysis", "diversification_assessment",
        "moat_analysis",
    ],
    when_to_use="Use it when you need to analyze the main business structure, changes in product/region revenue proportion, business concentration and gross profit margin structure.",
    returns="Returns a JSON string containing periods, concentration, coverage, and warnings.",
    example="get_business_segment_trend_tool(symbol='600519', years=5, segment_type='product')",
)
def get_business_segment_trend_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "number of years, default 5"] = 5,
    segment_type: Annotated[str, "Division type, such as product/region/all"] = "product",
) -> str:
    """Obtain main business structure trends.

    Args:
        symbol: A stock code, such as 600519,000001
        years: number of years, default 5
        segment_type: Division type, such as product/region/all

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_business_segment_trend`` of Returns ——
            status, symbol, segment_type, periods, coverage(period_count/raw_segment_count), warnings
    """
    try:
        return _standard_financial_tools_json_response(get_business_segment_trend(symbol, years=years, segment_type=segment_type))
    except Exception as exc:
        logger.error("Failed to obtain main business structure trend: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"主营结构趋势获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_shareholder_return_metrics_tool",
    name="股东回报指标",
    description="Structured returns dividend history, cash dividends per share, dividend yield, dividend continuity and free cash flow coverage context.",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=[
        "shareholder_return", "dividend", "dividend_history", "cash_dividend",
        "dividend_yield", "dividend_continuity", "payout_ratio",
        "free_cashflow_coverage", "shareholder_value", "dividend_stability",
        "total_shareholder_return", "yield_analysis", "income_investing",
        "value_investing", "dividend_payout", "return_on_capital",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "dividend_analysis", "dividend_yield_assessment", "shareholder_return_analysis",
        "dividend_continuity_check", "free_cashflow_coverage_check",
        "income_investing", "value_investing",
    ],
    when_to_use="Use when you need to analyze dividends, dividend yield, shareholder returns, dividend stability, or cash flow coverage.",
    returns="Returns a JSON string containing records, annual, metrics, coverage, and warnings.",
    example="get_shareholder_return_metrics_tool(symbol='600519', years=5)",
)
def get_shareholder_return_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "number of years, default 5"] = 5,
) -> str:
    """Get shareholder return metrics.

    Args:
        symbol: A stock code, such as 600519,000001
        years: number of years, default 5

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_shareholder_return_metrics`` of Returns ——
            status, symbol, data_source, current_price, records, annual, metrics, coverage, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_shareholder_return_metrics(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain shareholder return indicator: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"股东回报指标获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_portfolio_risk_profile_tool",
    name="组合风险画像",
    description="Returns portfolio volatility, maximum drawdown, VaR, CVaR, industry exposure and concentration based on position JSON and price return series.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    when_to_use="Used when the user provides a position and requires portfolio risk, concentration, sector exposure, VaR or maximum drawdown.",
    when_not_to_use="Not suitable for single stock risk analysis (please use get_single_stock_risk_profile_tool); not suitable for scenarios without position data.",
    capability_tags=["portfolio", "risk_management", "var"],
    tool_role_hint="specialized",
    returns="Returns a JSON string containing positions, metrics, exposure, return_series, coverage, and warnings.",
    example="get_portfolio_risk_profile_tool(positions_json='[{\"symbol\":\"600519\",\"market_value\":100000}]')",
    related_tools=["get_correlation_matrix", "get_single_stock_risk_profile_tool", "get_cointegration_test"],
)
def get_portfolio_risk_profile_tool(
    positions_json: Annotated[str, "Position JSON array, the elements contain symbol/code and market_value or quantity*price"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is nearly one year"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum price samples, default 300"] = 300,
) -> str:
    """Obtain a portfolio risk profile.

    Args:
        positions_json: Position JSON array, the elements contain symbol/code and market_value or quantity*price
        start_date: Start date YYYY-MM-DD, default is nearly one year
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum price samples, default 300

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_portfolio_risk_profile`` of Returns ——
            status, window, positions, metrics, exposure, return_series, coverage, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_portfolio_risk_profile(_parse_positions(positions_json), start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain portfolio risk profile: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"组合风险画像获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_technical_indicator_series_tool",
    name="技术指标历史序列",
    description=(
        "Based on the standard price sequence structured calculation, historical indicators such as MA, MACD, RSI, KDJ, BOLL, ATR, OBV, and support pressure are calculated."
        "Here s Technical signals/trends It refers to the sequence of technical indicators of price and trading volume, not a financial risk signal, announcement event signal or Agent capability gap."
    ),
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need historical sequence of technical indicators, support pressure, ATR/BOLL/OBV or structured technical input, suitable for technical analysis, volume and price indicators and price trend judgment.",
    when_not_to_use="Not used for financial risk, cash flow risk, announcement event signals, fundamental quality or Agent Workshop capability gap analysis. If you only want current values ​​(not historical series), you should use get_technical_factor_bundle_tool; if you want a human-readable text analysis report, you should use get_technical_indicators.",
    capability_tags=["technical_indicators", "historical_series", "structured_data", "ma", "macd", "rsi", "kdj", "boll", "atr", "obv"],
    tool_role_hint="supporting",
    preferred_for=["技术指标历史序列", "回测数据准备", "结构化技术面输入"],
    returns="Returns a JSON string, including records, latest, summary, coverage, and warnings.",
    example="get_technical_indicator_series_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
    related_tools=["get_technical_factor_bundle_tool", "get_technical_indicators", "get_adjusted_price_series_tool"],
)
def get_technical_indicator_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is nearly one year"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    indicators: Annotated[str, "Comma separated indicators like ma,macd,rsi,kdj,boll,atr,obv,support_resistance"] = "ma,macd,rsi,kdj,boll,atr,obv,support_resistance",
    limit: Annotated[int, "Maximum number of items returned, default 300"] = 300,
) -> str:
    """Get the historical sequence of technical indicators.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is nearly one year
        end_date: End date YYYY-MM-DD, default is today
        indicators: Comma separated indicators like ma,macd,rsi,kdj,boll,atr,obv,support_resistance
        limit: Maximum number of items returned, default 300

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_technical_indicator_series`` of Returns ——
            status, symbol, window, data_source, indicators, records, latest, summary, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_technical_indicator_series(symbol, start_date=start_date, end_date=end_date, indicators=_parse_metrics(indicators), limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain technical indicator historical sequence: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"Failed to obtain technical indicator historical sequence: {exc}"})


@tool
@register_tool(
    tool_id="get_industry_market_performance_tool",
    name="行业市场表现",
    description="The structure returns the price rise and fall of peers in the industry where the target stock is located, industry earnings, proportion of risers and fallers, transaction volume, and industry capital flow context.",
    category="market",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=[
        "industry_performance", "industry_returns", "peer_performance",
        "market_breadth", "advance_decline", "industry_rotation",
        "industry_moneyflow", "sector_performance", "top_gainers", "top_losers",
        "industry_relative", "market_heat", "sector_rotation",
        "peer_comparison", "industry_trend",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "industry_performance_analysis", "sector_rotation_analysis",
        "industry_relative_performance", "market_breadth_check",
        "industry_moneyflow_analysis", "peer_performance_comparison",
    ],
    when_to_use="Use it when you need industry ups and downs, industry rotation, industry capital flows, and relative industry performance of target stocks.",
    returns="Returns a JSON string containing summary, top_gainers, top_losers, moneyflow, coverage, and warnings.",
    example="get_industry_market_performance_tool(symbol='600519', lookback_days=20, peer_limit=50)",
)
def get_industry_market_performance_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, can be empty"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    lookback_days: Annotated[int, "Number of days to look back, default 20"] = 20,
    peer_limit: Annotated[int, "Peer sample upper limit, default 100"] = 100,
) -> str:
    """Get industry market performance.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, can be empty
        end_date: End date YYYY-MM-DD, default is today
        lookback_days: Number of days to look back, default 20
        peer_limit: Peer sample upper limit, default 100

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_industry_market_performance`` of Returns ——
            status, symbol, industry, window, summary, top_gainers, top_losers, moneyflow,
            coverage, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_industry_market_performance(symbol, start_date=start_date, end_date=end_date, lookback_days=lookback_days, peer_limit=peer_limit))
    except Exception as exc:
        logger.error("Industry market performance acquisition failed: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"行业市场表现获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_peer_relative_growth_tool",
    name="同业成长分位",
    description="Structured returns the quantiles of revenue, net profit, operating cash flow, and free cash flow CAGR relative to peer samples.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=[
        "peer_comparison", "peer_growth", "industry_growth", "growth_percentile",
        "revenue_cagr", "net_profit_cagr", "operating_cashflow_cagr", "free_cashflow_cagr",
        "growth_benchmarking", "peer_relative", "same_industry_growth",
        "moat_analysis", "competitive_advantage",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "peer_growth_comparison", "industry_growth_percentile", "growth_benchmarking",
        "revenue_growth_peer_ranking", "profit_growth_peer_ranking",
        "moat_analysis", "competitive_advantage_assessment",
    ],
    when_to_use="Use it when you need to judge the relative position of growth among peers and make horizontal comparisons of growth quality.",
    returns="Returns a JSON string, including metrics, samples, coverage, and warnings.",
    example="get_peer_relative_growth_tool(symbol='600519', metrics='revenue_cagr,net_profit_cagr', years=5)",
)
def get_peer_relative_growth_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    metrics: Annotated[str, "Comma separated indicators like revenue_cagr,net_profit_cagr,operating_cashflow_cagr,free_cashflow_cagr"] = "revenue_cagr,net_profit_cagr,operating_cashflow_cagr,free_cashflow_cagr",
    years: Annotated[int, "Year number of annual report, default 5, maximum 15"] = 5,
    peer_limit: Annotated[int, "Peer sample upper limit, default 50"] = 50,
) -> str:
    """Obtain peer growth scores.

    Args:
        symbol: A stock code, such as 600519,000001
        metrics: Comma separated indicators like revenue_cagr,net_profit_cagr,operating_cashflow_cagr,free_cashflow_cagr
        years: Year number of annual report, default 5, maximum 15
        peer_limit: Peer sample upper limit, default 50

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_peer_relative_growth`` of Returns ——
            status, symbol, industry, years, metrics, samples, coverage, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_peer_relative_growth(symbol, metrics=_parse_metrics(metrics), years=years, peer_limit=peer_limit))
    except Exception as exc:
        logger.error("Failed to obtain peer growth score: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"同业成长分位获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_historical_financial_annual_series_tool",
    name="历史年报财务序列",
    description=(
        "Structured returns the financial series of annual reports of a single A-share in the last N years."
        "Suitable for scenarios such as long-term financial quality, profitability stability, cash flow quality, etc."
        "Avoid picking numbers from get_income_analysis s Markdown and mixed quarter series."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "historical_financials", "annual_series", "multi_year_financials",
        "financial_trend", "long_term_financials",
        "gross_margin", "gross_margin_trend", "operating_margin", "operating_margin_trend",
        "netprofit_margin", "profitability_trend",
        "revenue", "revenue_trend", "net_profit", "profit_trend",
        "roe", "roe_trend", "roa", "roic", "return_on_equity",
        "operating_cashflow", "free_cashflow", "cashflow_trend",
        "total_assets", "total_equity", "debt_to_assets", "balance_sheet",
        "moat_analysis", "competitive_advantage",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "historical_financial_trend_analysis", "gross_margin_trend", "operating_margin_trend",
        "profitability_trend", "multi_year_financial_series", "revenue_trend",
        "moat_analysis", "competitive_advantage_assessment", "long_term_financial_quality",
    ],
    when_to_use=(
        "When Agent/Skill needs a complete annual report sequence of 5-10 years, revenue/net profit/ROE/operating cash flow long-term trend,"
        "It will be used first when looking at the multi-year trend of gross profit margin/operating profit margin, or when structured financial ledgers are needed as input for subsequent calculations."
    ),
    when_not_to_use="If you only want a text summary of the income statement for the most recent quarter, use get_income_analysis.",
    returns="Returns a JSON string, including records, coverage, and warnings; records are structured annual report fields in reverse order by year (including gross_margin/operating_margin/netprofit_margin/roe/revenue/net_profit, etc.).",
    example="get_historical_financial_annual_series_tool(symbol='600519', years=10)",
    related_tools=["get_profitability_stability_metrics_tool", "get_cashflow_quality_trend_tool", "get_income_analysis"],
)
def get_historical_financial_annual_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Get structured historical annual report financial series.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_historical_financial_annual_series`` of Returns ——
            status, symbol, requested_years, records, coverage(requested_years/available_years/missing_years),
            warnings
    """
    try:
        return _standard_financial_tools_json_response(get_historical_financial_annual_series(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain financial sequence of historical annual report: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"Failed to obtain financial sequence of historical annual report: {exc}"})


@tool
@register_tool(
    tool_id="get_profitability_stability_metrics_tool",
    name="盈利稳定性指标",
    description=(
        "Calculate the mean, median, volatility and coefficient of variation of revenue, net profit, ROE, gross profit margin and year-on-year growth based on historical annual report sequences."
        "Suitable for profitability stability, long-term quality analysis, and revenue volatility assessment."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "profitability_stability", "financial_stability", "long_term_quality",
        "revenue_volatility", "revenue_stability", "revenue_fluctuation",
        "gross_margin_stability", "gross_margin_volatility",
        "roe_stability", "roe_persistence", "return_stability",
        "profit_volatility", "profit_stability",
        "coefficient_of_variation", "stddev", "growth_stability",
        "growth_volatility", "yoy_growth_stability",
        "moat_analysis", "competitive_advantage",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "profitability_stability_analysis", "revenue_volatility", "revenue_stability",
        "revenue_fluctuation_analysis", "gross_margin_stability", "roe_persistence",
        "moat_analysis", "competitive_advantage_assessment", "long_term_quality_analysis",
    ],
    when_to_use="Use it when you need to quantify profitability stability, revenue volatility, ROE/gross profit margin sustainability, and long-term quality analysis.",
    when_not_to_use="Not used for valuation percentiles; please use get_historical_valuation_percentile_tool for valuation percentiles.",
    returns="Returns a JSON string containing metrics(Contains coefficient_of_variation), trend_series(Contains revenue_growth_yoy), coverage, warnings. ",
    example="get_profitability_stability_metrics_tool(symbol='600519', years=10)",
    related_tools=["get_historical_financial_annual_series_tool", "get_quality_factor_bundle_tool"],
)
def get_profitability_stability_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Get structured earnings stability indicators.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_profitability_stability_metrics`` of Returns ——
            status, symbol, years_used, coverage, metrics, trend_series, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_profitability_stability_metrics(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain profit stability indicator: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"盈利稳定性指标获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_cashflow_quality_trend_tool",
    name="现金流质量趋势",
    description=(
        "Calculate operating cash flow/net profit, free cash flow/net profit, operating cash flow rate, free cash flow rate and other trends based on historical annual report sequences."
        "It is suitable for judging profit content, cash flow stability, free cash flow quality, as well as cash flow deterioration signals such as declining operating cash flow and long-term negative free cash flow."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["cashflow_quality", "cashflow_deterioration", "earnings_quality", "free_cashflow", "operating_cashflow"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["cashflow_quality_analysis", "financial_risk_signal_detection", "earnings_quality_analysis"],
    when_to_use="It is used when structural indicators such as long-term cash flow quality, CFO/net profit, FCF/net profit, cash flow rate, operating cash flow decline, and long-term negative free cash flow are needed.",
    when_not_to_use="If you only want a textual summary of the cash flow statement, use get_cashflow_analysis.",
    returns="Returns a JSON string, including trend, summary, coverage, and warnings.",
    example="get_cashflow_quality_trend_tool(symbol='600519', years=10)",
    related_tools=["get_historical_financial_annual_series_tool", "get_growth_cashflow_factor_bundle_tool", "get_cashflow_analysis"],
)
def get_cashflow_quality_trend_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Capture structured cash flow quality trends.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_cashflow_quality_trend`` of Returns ——
            status, symbol, years_used, coverage, trend, summary, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_cashflow_quality_trend(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain cash flow quality trend: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"现金流质量趋势获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_historical_valuation_percentile_tool",
    name="历史估值分位",
    description=(
        "Structured calculation of historical valuation quantiles such as PE_TTM, PB, PS_TTM, PCF_TTM, etc. supports specifying the number of years to look back."
        "Used as an alternative to the hidden 3-year text quantile output in get_stock_fundamentals_unified."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=[
        "valuation", "historical_valuation", "valuation_percentile",
        "pe_ttm", "pb", "ps_ttm", "pcf_ttm", "valuation_band",
        "valuation_range", "safety_margin", "valuation_channel",
        "historical_range", "percentile_rank", "valuation_analysis",
        "relative_valuation", "time_series", "valuation_metrics",
    ],
    tool_role_hint="primary",
    output_shape="structured_metrics",
    preferred_for=[
        "valuation_percentile", "historical_valuation_analysis",
        "valuation_band_analysis", "safety_margin_assessment",
        "pe_percentile", "pb_percentile", "ps_percentile",
        "valuation_channel_analysis",
    ],
    when_to_use="Used when historical PE/PB/PS/PCF quantile, valuation channel, safety margin or auditable valuation quantile data is required.",
    when_not_to_use="If you only need the current PE/PB snapshot, use get_current_valuation_snapshot_tool or get_value_factor_bundle_tool.",
    returns="Returns a JSON string, including window, data_source, metrics, and warnings; metrics includes current_value, median, percentile, and sample_count.",
    example="get_historical_valuation_percentile_tool(symbol='600519', metrics='pe_ttm,pb,ps_ttm', lookback_years=5)",
    related_tools=["get_current_valuation_snapshot_tool", "get_value_factor_bundle_tool", "get_stock_fundamentals_unified"],
)
def get_historical_valuation_percentile_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    metrics: Annotated[str, "Comma separated indicators like pe_ttm,pb,ps_ttm,pcf_ttm"] = "pe_ttm,pb,ps_ttm",
    lookback_years: Annotated[int, "Number of years to look back, default 5, maximum 15"] = 5,
    as_of_date: Annotated[Optional[str], "Analysis date YYYY-MM-DD, default is today"] = None,
) -> str:
    """Get structured historical valuation quantiles.

    Args:
        symbol: A stock code, such as 600519,000001
        metrics: Comma separated indicators like pe_ttm,pb,ps_ttm,pcf_ttm
        lookback_years: Number of years to look back, default 5, maximum 15
        as_of_date: Analysis date YYYY-MM-DD, default is today

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_historical_valuation_percentile`` of Returns ——
            status, symbol, window, data_source, metrics, warnings
    """
    try:
        return _standard_financial_tools_json_response(
            get_historical_valuation_percentile(
                symbol,
                metrics=_parse_metrics(metrics),
                lookback_years=lookback_years,
                as_of_date=as_of_date,
            )
        )
    except Exception as exc:
        logger.error("Failed to obtain historical valuation quantile: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"历史估值分位获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_security_master_tool",
    name="证券主数据",
    description="Returns unified securities master data by stock code or stock name, including code, name, exchange, industry, listing status, ST mark, market capitalization, etc.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "security_master", "stock_metadata", "symbol_lookup", "stock_identity",
        "exchange_info", "listing_status", "industry_info", "market_cap",
        "st_flag", "basic_info", "security_info", "stock_basics",
        "ticker_lookup", "company_profile", "metadata",
    ],
    tool_role_hint="supporting",
    output_shape="structured_json",
    preferred_for=[
        "stock_identity_verification", "symbol_resolution", "basic_stock_info",
        "listing_status_check", "industry_lookup", "market_cap_lookup",
    ],
    when_to_use="It is used when the Agent needs to confirm the stock identity, code, name, industry, exchange, listing status, and basic metadata. Supports entering stock code or stock name.",
    returns="Returns a JSON string, including query, symbol, name, exchange, industry, listing_status, coverage, and warnings.",
    example="get_security_master_tool(symbol='600519') or get_security_master_tool(symbol='iFlytek')",
)
def get_security_master_tool(symbol: Annotated[str, "A Stock stock code or stock name, such as 600519, iFlytek, Kweichow Moutai"]) -> str:
    """Obtain securities master data.

    Args:
        symbol: A Stock stock code or stock name, such as 600519, iFlytek, Kweichow Moutai

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_security_master`` of Returns ——
            status, query, symbol, ts_code, name, exchange, industry, area, list_date,
            listing_status, is_st, market_cap, float_market_cap, data_source, coverage, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_security_master(symbol))
    except Exception as exc:
        logger.error("Failed to obtain securities master data: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"证券主数据获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_adjusted_price_series_tool",
    name="标准价格序列",
    description="Returns the normalized daily price series containing open/high/low/close/volume/amount/turnover_rate.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "price_series", "ohlcv", "daily_price", "adjusted_price", "kline",
        "candlestick", "volume", "turnover_rate", "market_data",
        "price_history", "time_series", "trading_data", "price_trend",
        "backtest_input", "ohlc",
    ],
    tool_role_hint="supporting",
    output_shape="structured_records",
    preferred_for=[
        "price_history_query", "kline_data", "backtest_data_preparation",
        "price_trend_analysis", "volume_analysis", "technical_analysis_input",
    ],
    when_to_use="Used when inputs for K-line sequence, price trend, and subsequent yield/volatility/retracement calculations are required.",
    returns="Returns a JSON string, including records, window, coverage, and warnings.",
    example="get_adjusted_price_series_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_adjusted_price_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is the past 3 years"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 1000"] = 1000,
) -> str:
    """Get the standard price series.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is the past 3 years
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 1000

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_adjusted_price_series`` of Returns ——
            status, symbol, period, adjustment, data_source, window, records, coverage, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_adjusted_price_series(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain standard price series: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"标准价格序列获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_return_series_tool",
    name="收益率序列",
    description="Structured returns of period-by-period return records, statistical summaries and coverage ratios for volatility calculation and backtest input.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "return_series", "daily_returns", "return_statistics",
        "return_distribution", "price_return", "risk_metrics",
        "volatility_input", "backtest_input", "return_history",
        "time_series", "return_analysis", "performance_measurement",
        "periodic_returns",
    ],
    tool_role_hint="supporting",
    output_shape="structured_records",
    preferred_for=[
        "return_series_analysis", "volatility_calculation", "backtest_input",
        "risk_metrics_calculation", "return_distribution_analysis",
        "performance_measurement",
    ],
    when_to_use="Use when return series, risk indicators, backtest inputs, or volatility calculation inputs are required.",
    returns="Returns a JSON string, including records, summary, coverage, and warnings.",
    example="get_return_series_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_return_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is the past 3 years"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 1000"] = 1000,
) -> str:
    """Get the return series.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is the past 3 years
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 1000

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_return_series`` of Returns ——
            status, symbol, period, window, records, summary, coverage, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_return_series(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain yield series: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"收益率序列获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_volatility_metrics_tool",
    name="波动率指标",
    description="Structured return daily volatility, annualized volatility and sample number indicators are used for individual stock price risk measurement and risk profiling.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "volatility", "annualized_volatility", "price_risk",
        "volatility_metrics", "risk_measurement", "return_volatility",
        "risk_metrics", "market_risk", "volatility_analysis",
        "standard_deviation", "price_volatility",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "volatility_analysis", "annualized_volatility_calculation",
        "price_risk_assessment", "risk_profile", "market_risk_measurement",
    ],
    when_to_use="Use it when you need to measure individual stock price risks, annualized fluctuations, and risk profiles.",
    returns="Returns a JSON string, including metrics, windows, and warnings.",
    example="get_volatility_metrics_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_volatility_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is the past 3 years"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 1000"] = 1000,
) -> str:
    """Get the volatility indicator.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is the past 3 years
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 1000

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_volatility_metrics`` of Returns ——
            status, symbol, period, window, metrics, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_volatility_metrics(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain volatility indicator: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"波动率指标获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_drawdown_metrics_tool",
    name="回撤指标",
    description="Structured return maximum retracement, retracement start and end dates and retracement sequence for downside risk assessment and backtesting.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "drawdown", "max_drawdown", "downside_risk", "drawdown_series",
        "peak_to_trough", "loss_analysis", "risk_metrics",
        "downside_deviation", "drawdown_duration", "recovery_analysis",
        "market_risk", "drawdown_recovery",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "max_drawdown_analysis", "downside_risk_assessment",
        "drawdown_analysis", "backtest_risk_metrics", "loss_analysis",
        "recovery_analysis",
    ],
    when_to_use="Use when you need to measure downside risk, maximum drawdowns, risk profiles, or backtest risk indicators.",
    returns="Returns a JSON string, including metrics, drawdown_series, and warnings.",
    example="get_drawdown_metrics_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_drawdown_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is the past 3 years"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 1000"] = 1000,
) -> str:
    """Get the retracement indicator.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is the past 3 years
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 1000

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_drawdown_metrics`` of Returns ——
            status, symbol, period, window, metrics, drawdown_series, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_drawdown_metrics(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("回撤指标获取失败: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"回撤指标获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_current_valuation_snapshot_tool",
    name="当前估值快照",
    description=(
        "Structured returns a snapshot of current valuations such as PE/PB/PS/PEG/dividend yield/market capitalization."
        "The valuation indicator used for the current cross-section does not calculate historical quantiles, relative positions of peers, DCF target prices or complete valuation ranges."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "valuation", "current_valuation", "valuation_snapshot",
        "pe", "pb", "ps", "peg", "dividend_yield", "market_cap",
        "valuation_metrics", "valuation_analysis", "snapshot",
        "current_metrics", "relative_valuation", "valuation_snapshot",
    ],
    tool_role_hint="primary",
    output_shape="structured_metrics",
    preferred_for=[
        "current_valuation_snapshot", "pe_pb_snapshot", "valuation_quick_check",
        "market_cap_lookup", "dividend_yield_check", "valuation_metrics_lookup",
    ],
    when_to_use="Use when you only need a snapshot of valuation indicators such as current PE/PB/PS/PEG/dividend yield/market capitalization, rather than historical quantiles, peer comparisons or target price models.",
    when_not_to_use="Not used for historical valuation percentiles (with get_historical_valuation_percentile_tool), peer relative valuations (with get_peer_relative_valuation_tool), DCF/price target valuations, or financial quality/risk analyses.",
    returns="Returns a JSON string containing current_price, metrics, data_source, and warnings.",
    example="get_current_valuation_snapshot_tool(symbol='600519')",
)
def get_current_valuation_snapshot_tool(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Get a snapshot of the current valuation.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_current_valuation_snapshot`` of Returns ——
            status, symbol, name, industry, trade_date, current_price, metrics, metric_sources,
            raw_metrics, data_source, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_current_valuation_snapshot(symbol))
    except Exception as exc:
        logger.error("Failed to obtain current valuation snapshot: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"当前估值快照获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_debt_solvency_trend_tool",
    name="偿债能力长期趋势",
    description="Structured return to long-term trends such as gearing ratio, current ratio, quick ratio, debt-to-equity ratio, operating cash flow debt coverage, etc.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "solvency", "debt_solvency", "debt_to_assets", "current_ratio",
        "quick_ratio", "debt_to_equity", "financial_health", "leverage",
        "leverage_trend", "debt_coverage", "cashflow_debt_coverage",
        "balance_sheet", "financial_risk", "long_term_solvency",
        "liquidity_ratio", "time_series",
    ],
    tool_role_hint="specialized",
    output_shape="structured_records",
    preferred_for=[
        "solvency_analysis", "leverage_trend_analysis",
        "financial_health_assessment", "debt_coverage_analysis",
        "liquidity_analysis", "financial_risk_assessment",
    ],
    when_to_use="Used when it is necessary to analyze financial health, solvency, and leverage trends.",
    returns="Returns a JSON string, including trend, summary, coverage, and warnings.",
    example="get_debt_solvency_trend_tool(symbol='600519', years=10)",
)
def get_debt_solvency_trend_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Capture long-term trends in solvency.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_debt_solvency_trend`` of Returns ——
            status, symbol, years_used, coverage, trend, summary, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_debt_solvency_trend(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain long-term trend of solvency: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"Failed to obtain long-term trend of solvency: {exc}"})


@tool
@register_tool(
    tool_id="get_peer_group_tool",
    name="标准同行组",
    description="Returns standardized peer sample groups based on industry, including basic fields such as market capitalization, PE, PB, and ROE.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "peer_group", "peer_comparison", "industry_peers", "peers",
        "same_industry", "competitors", "peer_list", "industry_competition",
        "market_cap", "pe", "pb", "roe", "valuation",
        "moat_analysis", "competitive_advantage", "peer_benchmarking",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "peer_group_construction", "peer_comparison", "industry_peer_analysis",
        "competitor_analysis", "moat_analysis", "competitive_advantage_assessment",
        "peer_benchmarking",
    ],
    when_to_use="It is used when it is necessary to construct peer samples, peer valuations or peer quality comparison preliminary data, and peer competition analysis.",
    returns="Returns a JSON string, including industry, peers, coverage, and warnings.",
    example="get_peer_group_tool(symbol='600519', limit=50)",
)
def get_peer_group_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    limit: Annotated[int, "The upper limit of the number of peers, default 50"] = 50,
) -> str:
    """Get the standard peer group.

    Args:
        symbol: A stock code, such as 600519,000001
        limit: The upper limit of the number of peers, default 50

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_peer_group`` of Returns ——
            status, symbol, industry, peers, coverage(peer_count/limit), warnings
    """
    try:
        return _standard_financial_tools_json_response(get_peer_group(symbol, limit=limit))
    except Exception as exc:
        logger.error("Standard peer group acquisition failed: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"标准同行组获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_peer_relative_valuation_tool",
    name="同业相对估值",
    description=(
        "Structured returns the mean, median and quantile of PE/PB/PS relative to industry peers."
        "It is used for horizontal peer valuation comparison and industry relative position judgment, and is not used for historical valuation quantiles, DCF target prices or simple current valuation snapshots."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "peer_comparison", "peer_valuation", "industry_valuation", "valuation_percentile",
        "pe", "pb", "ps", "valuation_benchmarking", "peer_relative",
        "same_industry_valuation", "relative_valuation",
        "moat_analysis", "competitive_advantage",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "peer_valuation_comparison", "industry_valuation_percentile", "valuation_benchmarking",
        "pe_peer_ranking", "pb_peer_ranking", "ps_peer_ranking",
        "moat_analysis", "competitive_advantage_assessment",
    ],
    when_to_use="It is used when peer valuation comparison, relative position of industry valuation, and PE/PB/PS horizontal quantile are needed.",
    when_not_to_use="Not used for historical valuation quantile time series (with get_historical_valuation_percentile_tool), current valuation snapshots (with get_current_valuation_snapshot_tool), DCF/price target models, or quality factor analysis.",
    returns="Returns a JSON string containing industry, metrics, and warnings.",
    example="get_peer_relative_valuation_tool(symbol='600519', metrics='pe,pb,ps')",
)
def get_peer_relative_valuation_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    metrics: Annotated[str, "Comma separated indicators like pe,pb,ps"] = "pe,pb,ps",
    peer_limit: Annotated[int, "Peer sample upper limit, default 200"] = 200,
) -> str:
    """Get peer relative valuations.

    Args:
        symbol: A stock code, such as 600519,000001
        metrics: Comma separated indicators like pe,pb,ps
        peer_limit: Peer sample upper limit, default 200

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_peer_relative_valuation`` of Returns ——
            status, symbol, industry, metrics, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_peer_relative_valuation(symbol, metrics=_parse_metrics(metrics), peer_limit=peer_limit))
    except Exception as exc:
        logger.error("Failed to obtain peer relative valuation: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"同业相对估值获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_peer_relative_quality_tool",
    name="同业相对质量",
    description=(
        "Structured returns the position of quality or valuation quality metrics such as ROE/PB/PE relative to peers."
        "Here s quality Refers to the company s fundamental quality and peer relative quality, such as ROE, profitability, asset efficiency and partial valuation quality, not data quality, reporting quality, cash flow specific quality or technical signal quality."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "peer_comparison", "peer_quality", "industry_quality", "quality_percentile",
        "roe", "pb", "pe_ttm", "quality_benchmarking", "peer_relative",
        "same_industry_quality", "relative_quality", "profitability",
        "moat_analysis", "competitive_advantage",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "peer_quality_comparison", "industry_quality_percentile", "quality_benchmarking",
        "roe_peer_ranking", "profitability_peer_ranking",
        "moat_analysis", "competitive_advantage_assessment",
    ],
    when_to_use="It is used when it is necessary to judge the relative position of a company s fundamental quality indicators among its peers, such as horizontal comparisons of ROE, profitability, asset efficiency, and valuation quality.",
    when_not_to_use="Not used for data quality checks, report quality reviews, cash flow specific quality trends (with get_cashflow_quality_trend_tool) or technical indicator signal quality.",
    returns="Returns a JSON string containing industry, metrics, and warnings.",
    example="get_peer_relative_quality_tool(symbol='600519', metrics='roe,pb,pe_ttm')",
)
def get_peer_relative_quality_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    metrics: Annotated[str, "Comma separated indicators like roe,pb,pe_ttm"] = "roe,pb,pe_ttm",
    peer_limit: Annotated[int, "Peer sample upper limit, default 200"] = 200,
) -> str:
    """Obtain the relative quality of peers.

    Args:
        symbol: A stock code, such as 600519,000001
        metrics: Comma separated indicators like roe,pb,pe_ttm
        peer_limit: Peer sample upper limit, default 200

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_peer_relative_quality`` of Returns ——
            status, symbol, industry, metrics, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_peer_relative_quality(symbol, metrics=_parse_metrics(metrics), peer_limit=peer_limit))
    except Exception as exc:
        logger.error("Failed to obtain peer relative quality: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"同业相对质量获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_company_announcements_tool",
    name="公司公告代理",
    description="Identify announcement records from recent news as a structured proxy capability before accessing announcement-specific data sources.",
    category="news",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need clues about company announcements, disclosures, financial reports, dividends, shareholding reductions, restructuring and other events.",
    when_not_to_use="Not suitable for formal announcement database query (please use get_company_event_timeline_tool); not suitable for general news analysis (please use get_stock_news).",
    capability_tags=["event", "announcement", "disclosure"],
    tool_role_hint="specialized",
    returns="Returns a JSON string containing announcements, coverage, and warnings.",
    example="get_company_announcements_tool(symbol='600519', lookback_days=365)",
    related_tools=["get_company_event_timeline_tool", "get_risk_event_flags_tool", "get_stock_news"],
)
def get_company_announcements_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back, default 365"] = 365,
    limit: Annotated[int, "Return the upper limit of the number of items, default 50"] = 50,
) -> str:
    """Obtain company announcement agency records.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back, default 365
        limit: Return the upper limit of the number of items, default 50

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_company_announcements`` of Returns ——
            status, symbol, window, announcements, coverage, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_company_announcements(symbol, lookback_days=lookback_days, limit=limit))
    except Exception as exc:
        logger.error("Company Announcement Failed to Obtain Agent: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"公司公告代理获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_risk_event_flags_tool",
    name="风险事件标记",
    description=(
        "Identify risk flags such as regulatory penalties, litigation, shareholding reductions, pledges, performance warnings, restructuring, and executive changes based on recent news headlines/summaries."
        "Here s Risk events/signals Refers to news and announcement event clues, not financial statement anomalies, cash flow deterioration, market fluctuation risks, technical buying and selling signals, or Agent capability gaps."
    ),
    category="news",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need to quickly determine whether there are recent regulatory penalties, lawsuits, shareholding reductions, pledges, performance warnings, restructuring and other major news/announcement event clues.",
    when_not_to_use="It is not suitable for in-depth analysis of financial risks, identification of cash flow anomalies, or detection of financial fraud signals; financial risk/financial report quality tools should be used for such needs. Not suitable for in-depth event quantitative analysis (please use get_event_study); not suitable for formal announcement query (please use get_company_event_timeline_tool); not suitable for general news browsing (please use get_stock_news).",
    capability_tags=["event", "risk", "regulatory"],
    tool_role_hint="specialized",
    returns="Returns a JSON string, including hit_flags, flags, news_count, and warnings.",
    example="get_risk_event_flags_tool(symbol='600519', lookback_days=180)",
    related_tools=["get_company_event_timeline_tool", "get_company_announcements_tool", "get_event_study", "get_stock_news"],
)
def get_risk_event_flags_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back, default 180"] = 180,
    limit: Annotated[int, "The upper limit of the number of news items, default 50"] = 50,
) -> str:
    """Get the risk event tag.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back, default 180
        limit: The upper limit of the number of news items, default 50

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_risk_event_flags`` of Returns ——
            status, symbol, window, news_count, hit_flags, flags, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_risk_event_flags(symbol, lookback_days=lookback_days, limit=limit))
    except Exception as exc:
        logger.error("Risk event tag acquisition failed: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"风险事件标记获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_margin_stability_metrics_tool",
    name="利润率稳定性指标",
    description="Structured return of long-term stability statistics of gross profit margin, net profit margin, operating profit margin, and expense ratio.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "margin_stability", "gross_margin_stability", "net_margin_stability",
        "operating_margin_stability", "expense_ratio", "expense_ratio_stability",
        "profitability_stability", "margin_trend", "margin_volatility",
        "moat_analysis", "competitive_advantage", "cost_control",
        "operating_efficiency", "margin_persistence",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "margin_stability_analysis", "gross_margin_persistence",
        "net_margin_stability", "expense_ratio_analysis", "moat_analysis",
        "competitive_advantage_assessment", "cost_control_assessment",
    ],
    when_to_use="Used when it is necessary to analyze profit margin stability, moat evidence, and expense control quality.",
    returns="Returns a JSON string containing trends, metrics, coverage, and warnings.",
    example="get_margin_stability_metrics_tool(symbol='600519', years=10)",
)
def get_margin_stability_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Get profit margin stability indicators.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_margin_stability_metrics`` of Returns ——
            status, symbol, years_used, coverage, trend, metrics, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_margin_stability_metrics(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain profit margin stability indicator: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"Failed to obtain profit margin stability indicator: {exc}"})


@tool
@register_tool(
    tool_id="get_capital_efficiency_trend_tool",
    name="资本效率趋势",
    description="Structured return to long-term trends in capital efficiency such as ROE, ROA, ROIC, asset turnover, equity multiplier, etc.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "capital_efficiency", "roe", "roa", "roic", "asset_turnover",
        "equity_multiplier", "dupont_analysis", "return_on_equity",
        "return_on_assets", "return_on_invested_capital",
        "operating_efficiency", "capital_allocation",
        "financial_efficiency", "time_series",
    ],
    tool_role_hint="specialized",
    output_shape="structured_records",
    preferred_for=[
        "capital_efficiency_analysis", "dupont_decomposition",
        "roe_trend_analysis", "roa_trend_analysis", "roic_analysis",
        "operating_efficiency_assessment", "capital_allocation_analysis",
    ],
    when_to_use="Use it when you need to analyze capital utilization efficiency, DuPont dismantling basic indicators, and long-term operating efficiency.",
    returns="Returns a JSON string, including trend, summary, coverage, and warnings.",
    example="get_capital_efficiency_trend_tool(symbol='600519', years=10)",
)
def get_capital_efficiency_trend_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Get capital efficiency trends.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_capital_efficiency_trend`` of Returns ——
            status, symbol, years_used, coverage, trend, summary, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_capital_efficiency_trend(symbol, years=years))
    except Exception as exc:
        logger.error("Capital efficiency trend acquisition failed: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"资本效率趋势获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_growth_quality_metrics_tool",
    name="成长质量指标",
    description="Structured returns revenue, net income, operating cash flow, free cash flow CAGR and annual growth stability.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "growth_quality", "revenue_cagr", "net_profit_cagr",
        "operating_cashflow_cagr", "free_cashflow_cagr", "growth_stability",
        "growth_volatility", "earnings_growth", "revenue_growth",
        "sustainable_growth", "growth_persistence", "cashflow_backed_growth",
        "quality_growth", "growth_consistency",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "growth_quality_analysis", "cagr_analysis", "growth_stability_assessment",
        "sustainable_growth_check", "cashflow_backed_growth_verification",
        "earnings_growth_quality",
    ],
    when_to_use="Use it when you need to judge the quality of growth, whether growth is supported by cash flow, and whether revenue and profit growth is stable.",
    returns="Returns a JSON string containing cagr, annual_growth, growth_stability, quality_flags, and warnings.",
    example="get_growth_quality_metrics_tool(symbol='600519', years=10)",
)
def get_growth_quality_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Get growth quality metrics.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_growth_quality_metrics`` of Returns ——
            status, symbol, years_used, coverage, cagr, annual_growth, growth_stability,
            quality_flags, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_growth_quality_metrics(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain growth quality indicators: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"成长质量指标获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_single_stock_risk_profile_tool",
    name="个股风险画像",
    description="Based on the price sequence, risk profiles such as return distribution, annualized volatility, maximum drawdown, downward volatility, and daily ratio of positive and negative returns are returned.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "risk_profile", "single_stock_risk", "return_distribution",
        "annualized_volatility", "max_drawdown", "downside_volatility",
        "upside_ratio", "downside_ratio", "risk_metrics", "price_risk",
        "market_risk", "risk_assessment", "return_distribution_analysis",
        "downside_risk",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "single_stock_risk_profile", "price_risk_assessment",
        "return_distribution_analysis", "downside_risk_analysis",
        "volatility_assessment", "backtest_risk_context",
    ],
    when_to_use="Use when you need an individual stock risk profile, price risk, downside risk, or pre-backtest risk context.",
    returns="Returns a JSON string, including metrics, components, and warnings.",
    example="get_single_stock_risk_profile_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_single_stock_risk_profile_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is the past 3 years"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 1000"] = 1000,
) -> str:
    """Get a risk profile of individual stocks.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is the past 3 years
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 1000

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_single_stock_risk_profile`` of Returns ——
            status, symbol, period, window, metrics, components, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_single_stock_risk_profile(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain individual stock risk profile: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"个股风险画像获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_industry_fundamental_summary_tool",
    name="行业基本面摘要",
    description="Based on peer samples, return industry market capitalization, PE, PB, ROE and other fundamental statistics and top samples.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "industry_fundamental", "industry_summary", "industry_statistics",
        "industry_pe", "industry_pb", "industry_roe", "peer_statistics",
        "industry_valuation", "industry_quality", "top_peers",
        "market_cap_distribution", "peer_comparison", "industry_benchmark",
        "fundamental_summary",
    ],
    tool_role_hint="supporting",
    output_shape="structured_json",
    preferred_for=[
        "industry_fundamental_background", "peer_distribution_analysis",
        "industry_valuation_benchmark", "industry_quality_benchmark",
        "top_peer_identification", "industry_context",
    ],
    when_to_use="Used when industry fundamental background, peer sample distribution, industry valuation/quality statistical context is needed.",
    returns="Returns a JSON string containing industry, metrics, top_market_cap_peers, coverage, and warnings.",
    example="get_industry_fundamental_summary_tool(symbol='600519', peer_limit=100)",
)
def get_industry_fundamental_summary_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    peer_limit: Annotated[int, "Peer sample upper limit, default 100"] = 100,
) -> str:
    """Get a summary of industry fundamentals.

    Args:
        symbol: A stock code, such as 600519,000001
        peer_limit: Peer sample upper limit, default 100

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_industry_fundamental_summary`` of Returns ——
            status, symbol, industry, coverage, metrics, top_market_cap_peers, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_industry_fundamental_summary(symbol, peer_limit=peer_limit))
    except Exception as exc:
        logger.error("Failed to obtain industry fundamentals summary: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"行业基本面摘要获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_capital_flow_series_tool",
    name="个股资金流序列",
    description=(
        "Structured return of local stock capital flow sequence, including main net inflow, net inflow ratio, large order/small order net inflow and other fields."
        "Here s capital flow It refers to the flow of transaction funds and main capital behavior, not operating cash flow, investment cash flow, financing cash flow or free cash flow in financial statements."
    ),
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "capital_flow", "money_flow", "main_force_flow", "institutional_flow",
        "large_order_flow", "small_order_flow", "net_inflow", "inflow_ratio",
        "trading_flow", "fund_flow", "market_behavior", "capital_behavior",
        "liquidity_analysis", "main_force_behavior", "time_series",
    ],
    tool_role_hint="specialized",
    output_shape="structured_records",
    preferred_for=[
        "capital_flow_analysis", "main_force_behavior_analysis",
        "fund_flow_trend", "large_order_flow_analysis",
        "market_behavior_evidence", "liquidity_analysis",
    ],
    when_to_use="Use it when you need to trade capital flow trends, main capital behavior, capital evidence, and large/small order net inflow structure. If the fund flow is not synchronized locally, no_data and reason will be returned.",
    when_not_to_use="Not used for financial statement cash flow quality, operating cash flow decline, negative free cash flow, or profit margin analysis; these needs should use get_cashflow_quality_trend_tool, get_cashflow_analysis, or get_growth_cashflow_factor_bundle_tool.",
    returns="Returns a JSON string, including records, summary, coverage, and warnings.",
    example="get_capital_flow_series_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_capital_flow_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is 180 days"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 120"] = 120,
) -> str:
    """Get the fund flow sequence of individual stocks.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is 180 days
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 120

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_capital_flow_series`` of Returns ——
            status, symbol, window, data_source, records, summary, coverage, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_capital_flow_series(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain individual stock capital flow sequence: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"个股资金流序列获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_chip_distribution_context_tool",
    name="筹码分布上下文",
    description="The structure returns profit ratio, average cost, 70%/90% chip cost range and concentration.",
    category="market",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=[
        "chip_distribution", "profit_ratio", "average_cost", "cost_distribution",
        "chip_concentration", "cost_range", "holder_cost", "market_behavior",
        "chip_structure", "concentration_ratio", "profit_margin_distribution",
        "cost_basis", "holding_cost", "snapshot",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "chip_distribution_analysis", "cost_concentration_analysis",
        "profit_ratio_check", "average_cost_analysis",
        "support_resistance_from_cost", "market_behavior_analysis",
    ],
    when_to_use="It is used when evidence of market behavior such as chip distribution, cost concentration, and profit margin ratio is needed.",
    returns="Returns a JSON string, including metrics, data_source, and warnings.",
    example="get_chip_distribution_context_tool(symbol='600519', trade_date='2024-12-31')",
)
def get_chip_distribution_context_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    trade_date: Annotated[Optional[str], "Transaction date YYYY-MM-DD, default is today"] = None,
) -> str:
    """Get the chip distribution context.

    Args:
        symbol: A stock code, such as 600519,000001
        trade_date: Transaction date YYYY-MM-DD, default is today

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_chip_distribution_context`` of Returns ——
            status, symbol, trade_date, message, data_source, metrics, warnings
    """
    try:
        return _standard_financial_tools_json_response(get_chip_distribution_context(symbol, trade_date=trade_date))
    except Exception as exc:
        logger.error("Failed to obtain chip distribution context: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"筹码分布上下文获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_pledge_risk_profile_tool",
    name="股权质押风险画像",
    description=(
        "Return to the equity pledge risk profile: total pledge ratio, unreleased pledge size, top pledge shareholders, recent pledge events, and risk level."
        "The data source preferentially uses the project s built-in Tushare/akshare data source, and there is no need for the user to specify the data source."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    when_to_use="It is used when it is necessary to analyze the equity pledge ratio, the pledge situation of major shareholders, the risk of pledge liquidation, and the pressure on the liquidation line.",
    when_not_to_use="Not suitable for non-pledged shareholder analysis (please use get_shareholder_return_metrics_tool); not suitable for general risk profiling (please use get_single_stock_risk_profile_tool).",
    capability_tags=["pledge", "shareholder", "risk"],
    tool_role_hint="specialized",
    returns="Returns a JSON string, including status, metrics (total_pledge_ratio/outstanding_amount, etc.), top_pledgers, recent_pledges, risk_level, warnings.",
    example="get_pledge_risk_profile_tool(symbol='600519')",
    related_tools=["get_risk_event_flags_tool", "get_shareholder_return_metrics_tool", "get_single_stock_risk_profile_tool"],
)
def get_pledge_risk_profile_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    source: Annotated[Optional[str], "Data source, automatically selected by default"] = None,
) -> str:
    """Obtain a portrait of equity pledge risk.

    Args:
        symbol: A stock code, such as 600519,000001
        source: Data source, automatically selected by default

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_pledge_risk_profile`` of Returns ——
            status, symbol, data_source, metrics(total_pledge_ratio/outstanding_pledge_amount_wan Wait),
            top_pledgers, recent_pledges, risk_level, warnings, data_source_status
    """
    try:
        return _standard_financial_tools_json_response(get_pledge_risk_profile(symbol, source=source))
    except Exception as exc:
        logger.error("Failed to obtain equity pledge risk profile: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"Failed to obtain equity pledge risk profile: {exc}"})


@register_tool(
    tool_id="get_pledge_historical_series_tool",
    name="股权质押历史趋势",
    description=(
        "Returns the equity pledge trend data of a single A-share within a specified time period, supporting statistics by year/quarter/month."
        "Including the pledge ratio at the end of each cycle, the number of outstanding shares, the number of active pledges, and the automatically assessed trend direction (improvement/deterioration/stable)."
        "The data source preferentially uses the project s built-in Tushare/akshare data source, and there is no need for the user to specify the data source."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    when_to_use="It is used when it is necessary to analyze the historical change trend of equity pledge ratio, determine whether pledge risk is improving or deteriorating, and compare pledge data by time period. Supports customization of start and end dates and statistical granularity.",
    when_not_to_use="Not suitable for querying the current pledge snapshot (please use get_pledge_risk_profile_tool); not suitable for non-pledge shareholder analysis.",
    capability_tags=["pledge", "shareholder", "risk", "trend", "historical"],
    tool_role_hint="specialized",
    returns="Returns a JSON string, including status, period (statistical period), start_date, end_date, series (period array, including period/pledge_ratio/outstanding_pledge_amount_wan, etc.), trend_assessment (trend direction assessment), and warnings.",
    example="get_pledge_historical_series_tool(symbol='600519', start_date='2021-01-01', end_date='2024-12-31', period='year')",
    related_tools=["get_pledge_risk_profile_tool", "get_single_stock_risk_profile_tool", "get_risk_event_flags_tool"],
)
def get_pledge_historical_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date, YYYY-MM-DD format, choose one of years"] = None,
    end_date: Annotated[Optional[str], "End date, YYYY-MM-DD format, default is today"] = None,
    years: Annotated[Optional[int], "Last N years, convenient parameter, alternative to start_date, default is 3 years"] = None,
    period: Annotated[Optional[str], "Statistical period: year/quarter/month, default year"] = "year",
    source: Annotated[Optional[str], "Data source, automatically selected by default"] = None,
) -> str:
    """Get the historical trend of equity pledge.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date, YYYY-MM-DD format, choose one of years
        end_date: End date, YYYY-MM-DD format, default is today
        years: Last N years, convenient parameter, alternative to start_date, default is 3 years
        period: Statistical period: year/quarter/month, default year
        source: Data source, automatically selected by default

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_pledge_historical_series`` of Returns ——
            status, symbol, data_source, period, start_date, end_date, period_count, series,
            trend_assessment(direction/change_pct/summary), warnings
    """
    try:
        return _standard_financial_tools_json_response(get_pledge_historical_series(
            symbol, start_date=start_date, end_date=end_date,
            years=years, period=period, source=source
        ))
    except Exception as exc:
        logger.error("Failed to obtain historical trend of equity pledge: %s", exc, exc_info=True)
        return _standard_financial_tools_json_response({"status": "error", "message": f"Failed to obtain historical trend of equity pledge: {exc}"})

# === statistical_tools ===
"""Statistical toolset.

Provides 6 financial statistics tools:
1. get_correlation_matrix - correlation matrix
2. get_cointegration_test - cointegration test
3. get_rolling_regression - rolling regression
4. get_normality_test - Normality test
5. get_stationarity_test - Stationarity test
6. get_garch_volatility - GARCH Volatility modeling
"""

import datetime
import json
import logging
import math
from typing import Annotated, Any, Dict, List, Optional, Tuple

import numpy as np
from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_daily_quotes, get_latest_stock_price
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


# ─── Helper function ──────────────────────────────────────────────────


def _statistical_tools_to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        numeric = float(str(value).strip())
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _dash_date(date_str: str) -> str:
    """Normalized dates are YYYY-MM-DD."""
    cleaned = "".join(ch for ch in date_str if ch.isdigit())[:8]
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
    return date_str


def _try_get_benchmark_quotes(benchmark_symbol: str, start_date_obj: datetime.date,
                                end_date_obj: datetime.date, lookback_days: int) -> Any:
    """Get benchmark index quotes, use AKShare to get the bottom line when DB has no data."""
    quotes = get_stock_daily_quotes(
        benchmark_symbol, start_date=start_date_obj.isoformat(), end_date=end_date_obj.isoformat(),
        period="daily", limit=lookback_days + 60,
    )
    if quotes:
        return quotes
    # AKShare Keep everything in mind
    if benchmark_symbol in ("000300", "399300", "sh000300"):
        try:
            import akshare as ak
            import pandas as pd
            df = ak.stock_zh_index_daily(symbol="sh000300")
            # date The column is of datetime.date type, and is compared directly with date objects.
            sd = start_date_obj if isinstance(start_date_obj, datetime.date) else start_date_obj
            ed = end_date_obj if isinstance(end_date_obj, datetime.date) else end_date_obj
            df = df[df["date"] >= sd]
            df = df[df["date"] <= ed]
            records = []
            for _, row in df.iterrows():
                records.append({
                    "trade_date": str(row["date"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"]),
                })
            return records
        except Exception:
            return None
    return None


def _compute_daily_returns(quotes: List[Dict[str, Any]]) -> List[float]:
    """Calculate daily returns from daily record list."""
    closes = []
    for q in quotes:
        c = _statistical_tools_to_float(q.get("close"))
        if c is not None and c > 0:
            closes.append(c)
    if len(closes) < 2:
        return []
    returns = []
    for i in range(1, len(closes)):
        returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
    return returns


def _fetch_quotes(symbol: str, lookback_days: int) -> List[Dict[str, Any]]:
    """Get the daily data for the last N days."""
    end = datetime.date.today()
    start = end - datetime.timedelta(days=lookback_days + 30)  # Get more to make sure you have enough data
    return get_stock_daily_quotes(
        symbol,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        period="daily",
        limit=lookback_days + 60,
    )


def _safe_autocorr(series: List[float], lag: int = 1) -> Optional[float]:
    """Calculate the first-order autocorrelation coefficient."""
    if len(series) < lag + 2:
        return None
    arr = np.array(series)
    if np.std(arr[:-lag]) == 0 or np.std(arr[lag:]) == 0:
        return None
    return float(np.corrcoef(arr[:-lag], arr[lag:])[0, 1])


def _adf_test_simple(series: List[float]) -> Tuple[float, float]:
    """Simple ADF inspection.

    Regression of residual series Δε_t = ρ × ε_{t-1}, Inspect ρ Whether it is significantly negative.
    Use critical values from scipy.stats if available.

    Returns:
        (adf_statistic, p_value_simplified)
    """
    if len(series) < 4:
        return float("nan"), 1.0

    arr = np.array(series)
    y = np.diff(arr)  # Δε_t
    x = arr[:-1]      # ε_{t-1}

    if np.std(x) == 0:
        return float("nan"), 1.0

    # OLS: y = β * x + ε (without intercept for ADF on residuals)
    beta = np.sum(x * y) / np.sum(x ** 2)
    residuals = y - beta * x
    se = math.sqrt(np.sum(residuals ** 2) / (len(residuals) - 1))
    se_beta = se / math.sqrt(np.sum(x ** 2))

    if se_beta == 0:
        return float("nan"), 1.0

    adf_stat = beta / se_beta

    # Use scipy to check critical values
    try:
        from scipy import stats
        # ADF critical value approx. -3.43 (1%), -2.86 (5%), -2.57 (10%) - Sample size approx. 500
        # Estimate p-value using approximate t-distribution
        p_value = 2.0 * stats.t.cdf(adf_stat, df=len(residuals) - 1)
    except ImportError:
        # Manual estimation
        if adf_stat < -3.43:
            p_value = 0.01
        elif adf_stat < -2.86:
            p_value = 0.05
        elif adf_stat < -2.57:
            p_value = 0.10
        else:
            p_value = 0.50

    return float(adf_stat), float(p_value)


# ────────────────────────────────────────────────────────────────
# Tool 1: correlation matrix
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_correlation_matrix",
    name="相关性矩阵",
    description=(
        "Calculate the return correlation coefficient matrix between multiple stocks."
        "Supports three methods: Pearson, Spearman, and Kendall."
        "Automatically find high correlations (|r|>0.7) of stock pairs."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=["statistics", "correlation", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["多股票相关性分析", "组合分散化评估", "风险对冲配对识别"],
    when_to_use=(
        "When it is necessary to analyze the price linkage relationship between multiple stocks and construct a low-correlation investment portfolio,"
        "Or use when looking for hedging pairs. Suitable for quantitative analysis and risk management scenarios."
    ),
    when_not_to_use=(
        "Not suitable for single stock analysis; not suitable for causal analysis (correlation does not equal causation);"
        "When there is insufficient data (< 20 trading days) results are unreliable."
    ),
    returns=(
        "Returns a JSON string containing symbols, methods, bars_used,"
        "correlation_matrix (row list format), top_correlated_pairs (|r|>0.7 of high correlation pairs)."
    ),
    example="get_correlation_matrix(symbols='600519,000001,300750')",
    related_tools=[
        "get_cointegration_test",
        "get_rolling_regression",
    ],
)
def get_correlation_matrix(
    symbols: Annotated[str, "Multiple stock codes, separated by commas, such as '600519,000001,300750'"],
    lookback_days: Annotated[int, "Number of days to look back, default 252 (approximately 1 trading day year)"] = 252,
    method: Annotated[str, "Correlation coefficient method: pearson/spearman/kendall, default pearson"] = "pearson",
) -> str:
    """Calculate the return correlation matrix for multiple stocks.

    Args:
        symbols: Multiple stock symbols, separated by commas (e.g. "600519,000001,300750") 
        lookback_days: Number of days to look back (automatically truncated to 20-1000), default 252
        method: correlation coefficient method: "pearson" / "spearman" / "kendall", Default "pearson"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbols: list[str] List of actual stock symbols used
            method: actual method used
            bars_used: Number of return samples used after alignment
            correlation_matrix: list[dict] Correlation matrix, element structure——
                — symbol: Stock code
                — values: list[float] Correlation coefficient with each stock
            top_correlated_pairs: list[dict] Correlation coefficient absolute value > 0.7 Stock pairs (up to 20), element structure——
                — stock_a: stocks A
                — stock_b: stocks B
                — correlation: Correlation coefficient
                — strength: intensity: "strong positive correlation" | "strong negative correlation"
            data_quality: dict Data quality——
                — requested_symbols: Requested stock list
                — valid_symbols: Valid number of shares
                — returns_per_stock: The rate of return for each stock
                — note: Description
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(20, min(int(lookback_days), 1000))
        sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
        if len(sym_list) < 2:
            return json.dumps(
                {"status": "error", "message": "至少需要 2 只股票"},
                ensure_ascii=False, indent=2, default=str,
            )

        method_map = {"pearson": "pearson", "spearman": "spearman", "kendall": "kendall"}
        corr_method = method_map.get(method, "pearson")

        # Get the daily line and return of each stock
        end = datetime.date.today()
        start = end - datetime.timedelta(days=lookback_days + 30)

        returns_by_symbol: Dict[str, List[float]] = {}
        dates_by_symbol: Dict[str, List[str]] = {}
        min_bars = float("inf")

        for sym in sym_list:
            quotes = get_stock_daily_quotes(
                sym,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                period="daily",
                limit=lookback_days + 60,
            )
            if not quotes or len(quotes) < 20:
                continue
            dates = []
            closes = []
            for q in quotes:
                c = _statistical_tools_to_float(q.get("close"))
                d = str(q.get("trade_date", ""))
                if c is not None and c > 0 and d:
                    closes.append(c)
                    dates.append(d)
            if len(closes) < 20:
                continue
            rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
            returns_by_symbol[sym] = rets
            dates_by_symbol[sym] = dates[1:]  # returns align with dates[1:]
            min_bars = min(min_bars, len(rets))

        if len(returns_by_symbol) < 2:
            return json.dumps(
                {"status": "error", "message": "At least 2 stocks with sufficient market data are required"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Align to same length
        aligned_symbols = list(returns_by_symbol.keys())
        aligned_returns: Dict[str, List[float]] = {}
        for sym in aligned_symbols:
            aligned_returns[sym] = returns_by_symbol[sym][-min_bars:]

        # Build matrix
        n = len(aligned_symbols)
        matrix = [[0.0] * n for _ in range(n)]
        top_pairs = []

        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i][j] = 1.0
                elif j > i:
                    xi = np.array(aligned_returns[aligned_symbols[i]])
                    xj = np.array(aligned_returns[aligned_symbols[j]])

                    if corr_method == "pearson":
                        r = float(np.corrcoef(xi, xj)[0, 1])
                    elif corr_method == "spearman":
                        from scipy.stats import spearmanr
                        r = float(spearmanr(xi, xj)[0])
                    elif corr_method == "kendall":
                        from scipy.stats import kendalltau
                        r = float(kendalltau(xi, xj)[0])
                    else:
                        r = float(np.corrcoef(xi, xj)[0, 1])

                    matrix[i][j] = round(r, 4)
                    matrix[j][i] = round(r, 4)

                    if abs(r) > 0.7:
                        top_pairs.append({
                            "stock_a": aligned_symbols[i],
                            "stock_b": aligned_symbols[j],
                            "correlation": round(r, 4),
                            "strength": "强正相关" if r > 0 else "强负相关",
                        })

        top_pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

        payload = {
            "symbols": aligned_symbols,
            "method": corr_method,
            "bars_used": min_bars,
            "correlation_matrix": [
                {"symbol": aligned_symbols[i], "values": matrix[i]}
                for i in range(n)
            ],
            "top_correlated_pairs": top_pairs[:20],
            "data_quality": {
                "requested_symbols": sym_list,
                "valid_symbols": len(aligned_symbols),
                "returns_per_stock": min_bars,
                "note": "Yield is calculated based on daily closing price. Spearman/Kendall requires scipy support.",
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Correlation matrix calculation failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 2: cointegration test
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_cointegration_test",
    name="协整检验",
    description=(
        "Conduct a cointegration test on two stocks."
        "Using OLS regression y = α + β × x + ε, Perform an ADF stationarity test on the residuals,"
        "Determine whether there is a cointegration relationship and calculate the mean reversion half-life."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=["statistics", "cointegration", "pairs_trading", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["配对交易策略研究", "均值回归分析", "统计套利机会识别"],
    when_to_use=(
        "When it is necessary to judge whether there is a long-term equilibrium relationship between two stocks and prepare for a pair trading strategy,"
        "Or used when evaluating the mean reversion properties of a spread series."
    ),
    when_not_to_use=(
        "Not suitable for single stock analysis; at least about 60 trading days of data are required to be statistically significant;"
        "Not suitable for causality testing."
    ),
    returns=(
        "Returns a JSON string containing beta, alpha, hedge_ratio, adf_statistic,"
        "p_value, is_cointegrated, half_life, spread_series (the last 10 issues)."
    ),
    example="get_cointegration_test(symbol_x='600519', symbol_y='000858')",
    related_tools=[
        "get_correlation_matrix",
        "get_stationarity_test",
    ],
)
def get_cointegration_test(
    symbol_x: Annotated[str, "The first stock code, such as 600519"],
    symbol_y: Annotated[str, "The second stock code, such as 000858"],
    lookback_days: Annotated[int, "Number of days to look back, default 504 (about 2 years)"] = 504,
) -> str:
    """Conduct a cointegration test on two stocks.

    Args:
        symbol_x: The first stock code (such as "600519") 
        symbol_y: The second stock code (e.g. "000858") 
        lookback_days: Number of days to look back (automatically truncated to 60-2000), default 504

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol_x: First stock code
            symbol_y: Second stock code
            alpha: OLS regression intercept
            beta: OLS Regression slope (hedge ratio)
            hedge_ratio: Hedge Ratio (= beta) 
            adf_statistic: ADF test statistic
            p_value: ADF Test p-value
            is_cointegrated: Whether it is cointegrated (p<0.05) 
            half_life_days: Mean reversion half-life (days, None if cannot be calculated)
            current_z_score: current spread Z-Score
            spread_series: list[dict] Price difference sequence of the last 10 periods, element structure——
                — date: Date
                — spread: spread
            bars_used: Common trading days
            interpretation: interpret text
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(60, min(int(lookback_days), 2000))

        end = datetime.date.today()
        start = end - datetime.timedelta(days=lookback_days + 30)

        quotes_x = get_stock_daily_quotes(
            symbol_x, start_date=start.isoformat(), end_date=end.isoformat(),
            period="daily", limit=lookback_days + 60,
        )
        quotes_y = get_stock_daily_quotes(
            symbol_y, start_date=start.isoformat(), end_date=end.isoformat(),
            period="daily", limit=lookback_days + 60,
        )

        if not quotes_x or not quotes_y:
            return json.dumps(
                {"status": "error", "message": "未能获取足够行情数据"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Align by trade_date
        prices_x: Dict[str, float] = {}
        prices_y: Dict[str, float] = {}
        for q in quotes_x:
            d = str(q.get("trade_date", ""))
            c = _statistical_tools_to_float(q.get("close"))
            if c and c > 0 and d:
                prices_x[d] = c
        for q in quotes_y:
            d = str(q.get("trade_date", ""))
            c = _statistical_tools_to_float(q.get("close"))
            if c and c > 0 and d:
                prices_y[d] = c

        common_dates = sorted(set(prices_x.keys()) & set(prices_y.keys()))
        if len(common_dates) < 30:
            return json.dumps(
                {"status": "error", "message": f"共同交易日不足（仅 {len(common_dates)} 天）"},
                ensure_ascii=False, indent=2, default=str,
            )

        px = np.array([prices_x[d] for d in common_dates], dtype=float)
        py = np.array([prices_y[d] for d in common_dates], dtype=float)

        # OLS: y = α + β × x + ε
        X = np.vstack([np.ones(len(px)), px]).T
        beta_vec = np.linalg.lstsq(X, py, rcond=None)[0]
        alpha = float(beta_vec[0])
        beta = float(beta_vec[1])
        residuals = py - (alpha + beta * px)

        hedge_ratio = beta  # Hedge ratio = β

        # ADF Test residuals
        adf_stat, p_value = _adf_test_simple(residuals.tolist())
        is_cointegrated = p_value < 0.05

        # half life
        half_life: Optional[float] = None
        rho = _safe_autocorr(residuals.tolist(), lag=1)
        if rho is not None and 0 < rho < 1:
            half_life = round(-math.log(2) / math.log(rho), 2)

        # Spread series (last 10 periods)
        spread = py - beta * px  # spread = y - β × x
        spread_series = [
            {"date": common_dates[i], "spread": round(float(spread[i]), 4)}
            for i in range(max(0, len(spread) - 10), len(spread))
        ]

        current_spread = float(spread[-1]) if len(spread) > 0 else 0
        spread_mean = float(np.mean(spread))
        spread_std = float(np.std(spread))
        z_score = (current_spread - spread_mean) / spread_std if spread_std > 0 else 0

        payload = {
            "symbol_x": symbol_x,
            "symbol_y": symbol_y,
            "alpha": round(alpha, 4),
            "beta": round(beta, 4),
            "hedge_ratio": round(hedge_ratio, 4),
            "adf_statistic": round(adf_stat, 4),
            "p_value": round(p_value, 4),
            "is_cointegrated": is_cointegrated,
            "half_life_days": half_life,
            "current_z_score": round(z_score, 4),
            "spread_series": spread_series,
            "bars_used": len(common_dates),
            "interpretation": (
                "The residual series is stationary (p<0.05) , There is a cointegration relationship" if is_cointegrated
                else "The residual sequence is non-stationary and there is no cointegration relationship."
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("协整检验失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 3: rolling regression
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_rolling_regression",
    name="滚动回归",
    description=(
        "Perform a rolling OLS regression on the stock s return relative to the benchmark index (default CSI 300),"
        "Calculate rolling beta, alpha, and R². Can be used to analyze beta stability."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=["statistics", "beta", "rolling_regression", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["Beta 稳定性分析", "因子暴露时变性研究", "风险模型验证"],
    when_to_use=(
        "When you need to analyze whether a stock s beta changes over time, evaluate rolling alpha trends,"
        "or used when checking the stability of risk exposures relative to a baseline."
    ),
    when_not_to_use=(
        "Not suitable for single-period static beta calculation; insufficient data (< window+20 trading days) cannot be calculated."
    ),
    returns=(
        "Returns a JSON string, including rolling_beta (last 20 periods), rolling_alpha,"
        "rolling_r_squared、latest_beta、beta_stability。"
    ),
    example="get_rolling_regression(symbol='600519', benchmark_symbol='000300')",
    related_tools=[
        "get_correlation_matrix",
        "get_stationarity_test",
    ],
)
def get_rolling_regression(
    symbol: Annotated[str, "Stock code, such as 600519"],
    benchmark_symbol: Annotated[str, "Benchmark index code, default 000300 (CSI 300)"] = "000300",
    lookback_days: Annotated[int, "Total number of days to look back, default 504 (about 2 years)"] = 504,
    window: Annotated[int, "Rolling window size (number of trading days), default 60"] = 60,
) -> str:
    """Perform a rolling regression of individual stocks relative to a benchmark index.

    Args:
        symbol: Stock code (e.g. "600519") 
        benchmark_symbol: Benchmark index code, default "000300" (CSI 300)
        lookback_days: Total lookback days (automatically truncated to 100-2000), default 504
        window: Rolling window size (number of trading days, automatically truncated to 20 to lookback_days/2), default 60

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Stock code
            benchmark: Benchmark index code
            window_days: rolling window size
            total_bars: total yield
            rolling_windows_computed: Calculated number of rolling windows
            latest_beta: Latest Beta Value
            latest_alpha: Latest Alpha value
            latest_r_squared: Latest R² value
            beta_stability: Beta Stability (standard deviation)
            beta_stability_interpretation: Beta Interpretation of stability: "stable" | "medium volatility" | "Highly volatile"
            rolling_series: list[dict] The last 20 rolling regression results, element structure——
                — beta: Beta value
                — alpha: Alpha value
                — r_squared: R² value
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(100, min(int(lookback_days), 2000))
        window = max(20, min(int(window), lookback_days // 2))

        end = datetime.date.today()
        start = end - datetime.timedelta(days=lookback_days + 30)

        quotes_stock = get_stock_daily_quotes(
            symbol, start_date=start.isoformat(), end_date=end.isoformat(),
            period="daily", limit=lookback_days + 60,
        )

        # Benchmark Index: 000300 Use AKShare to save money
        quotes_bm = _try_get_benchmark_quotes(benchmark_symbol, start, end, lookback_days)

        if not quotes_stock or not quotes_bm:
            return json.dumps(
                {"status": "error", "message": "未能获取足够行情数据"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Align closing price by date
        prices_s: Dict[str, float] = {}
        prices_b: Dict[str, float] = {}
        for q in quotes_stock:
            d = str(q.get("trade_date", ""))
            c = _statistical_tools_to_float(q.get("close"))
            if c and c > 0 and d:
                prices_s[d] = c
        for q in quotes_bm:
            d = str(q.get("trade_date", ""))
            c = _statistical_tools_to_float(q.get("close"))
            if c and c > 0 and d:
                prices_b[d] = c

        common_dates = sorted(set(prices_s.keys()) & set(prices_b.keys()))
        if len(common_dates) < window + 10:
            return json.dumps(
                {"status": "error", "message": f"共同交易日不足（仅 {len(common_dates)} 天，需要至少 {window + 10} 天）"},
                ensure_ascii=False, indent=2, default=str,
            )

        ps_arr = np.array([prices_s[d] for d in common_dates], dtype=float)
        pb_arr = np.array([prices_b[d] for d in common_dates], dtype=float)

        # Yield
        ret_s = (ps_arr[1:] - ps_arr[:-1]) / ps_arr[:-1]
        ret_b = (pb_arr[1:] - pb_arr[:-1]) / pb_arr[:-1]

        # rolling regression
        rolling_beta = []
        rolling_alpha = []
        rolling_r2 = []

        for i in range(window, len(ret_s)):
            y = ret_s[i - window:i]
            x = ret_b[i - window:i]

            if np.std(x) == 0:
                continue

            X = np.vstack([np.ones(window), x]).T
            beta_vec = np.linalg.lstsq(X, y, rcond=None)[0]
            a = float(beta_vec[0])
            b = float(beta_vec[1])

            y_pred = a + b * x
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

            rolling_alpha.append(round(a, 6))
            rolling_beta.append(round(b, 4))
            rolling_r2.append(round(float(r2), 4))

        if not rolling_beta:
            return json.dumps(
                {"status": "error", "message": "滚动回归计算失败"},
                ensure_ascii=False, indent=2, default=str,
            )

        latest_beta = rolling_beta[-1]
        beta_std = float(np.std(rolling_beta)) if len(rolling_beta) > 1 else 0.0

        # Last 20 rolling values
        n_latest = min(20, len(rolling_beta))
        rolling_series = [
            {
                "beta": rolling_beta[-(n_latest - i)],
                "alpha": rolling_alpha[-(n_latest - i)],
                "r_squared": rolling_r2[-(n_latest - i)],
            }
            for i in range(n_latest - 1, -1, -1)
        ]

        payload = {
            "symbol": symbol,
            "benchmark": benchmark_symbol,
            "window_days": window,
            "total_bars": len(ret_s),
            "rolling_windows_computed": len(rolling_beta),
            "latest_beta": latest_beta,
            "latest_alpha": round(rolling_alpha[-1], 6),
            "latest_r_squared": round(rolling_r2[-1], 4),
            "beta_stability": round(beta_std, 4),
            "beta_stability_interpretation": (
                "稳定" if beta_std < 0.1
                else "中等波动" if beta_std < 0.3
                else "高度波动"
            ),
            "rolling_series": rolling_series,
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("滚动回归失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 4: Normality test
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_normality_test",
    name="正态性检验",
    description=(
        "Perform Jarque-Bera normality test on stock daily returns."
        "Calculate the skewness and kurtosis to determine whether the return distribution obeys the normal distribution."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["statistics", "normality", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["收益率分布分析", "风险管理假设检验", "金融计量研究"],
    when_to_use=(
        "When it is necessary to test whether stock returns follow a normal distribution (an assumption of many risk models),"
        "Or used when analyzing the skewness and kurtosis characteristics of return distribution."
    ),
    when_not_to_use=(
        "Not suitable for single-day return calculation; insufficient data (< 30 trading days) results are unreliable."
    ),
    returns=(
        "Returns a JSON string, including jb_stat, p_value, is_normal,"
        "skewness、kurtosis、interpretation。"
    ),
    example="get_normality_test(symbol='600519')",
    related_tools=[
        "get_stationarity_test",
        "get_garch_volatility",
    ],
)
def get_normality_test(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    lookback_days: Annotated[int, "Number of days to look back, default 252 (about 1 year)"] = 252,
) -> str:
    """Perform Jarque-Bera normality test on stock daily returns.

    Args:
        symbol: A stock code (such as "600519") 
        lookback_days: Number of days to look back (automatically truncated to 30-1000), default 252

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Stock code
            jb_statistic: Jarque-Bera Statistics
            p_value: p value
            is_normal: Whether it obeys the normal distribution (p>0.05) 
            skewness: Skewness
            kurtosis: kurtosis
            excess_kurtosis: Excess kurtosis (kurtosis - 3)
            samples_used: Number of samples
            interpretation: interpret text
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(30, min(int(lookback_days), 1000))

        quotes = _fetch_quotes(symbol, lookback_days)
        if not quotes or len(quotes) < 30:
            return json.dumps(
                {"status": "error", "message": f"行情数据不足（仅 {len(quotes) if quotes else 0} 条）"},
                ensure_ascii=False, indent=2, default=str,
            )

        returns = _compute_daily_returns(quotes)
        if len(returns) < 30:
            return json.dumps(
                {"status": "error", "message": f"有效收益率数据不足（仅 {len(returns)} 个）"},
                ensure_ascii=False, indent=2, default=str,
            )

        ret_arr = np.array(returns)
        n = len(ret_arr)
        skewness = float(np.mean((ret_arr - np.mean(ret_arr)) ** 3) / (np.std(ret_arr) ** 3 + 1e-10))
        kurtosis = float(np.mean((ret_arr - np.mean(ret_arr)) ** 4) / (np.std(ret_arr) ** 4 + 1e-10))

        # Jarque-Bera Inspect
        try:
            from scipy import stats
            jb_stat, p_value = stats.jarque_bera(ret_arr)
        except ImportError:
            # Manual calculation
            jb_stat = n / 6.0 * (skewness ** 2 + (kurtosis - 3) ** 2 / 4.0)
            from scipy.stats import chi2
            p_value = 1.0 - chi2.cdf(jb_stat, df=2)

        is_normal = p_value > 0.05

        # Interpretation
        if abs(skewness) < 0.5:
            skew_desc = "接近对称"
        elif skewness > 0:
            skew_desc = "Right skew (positive skew), there are more extreme values of positive returns"
        else:
            skew_desc = "Left skewed (negatively skewed), with more extreme values of negative returns"

        if abs(kurtosis - 3) < 0.5:
            kurt_desc = "接近正态峰度"
        elif kurtosis > 3:
            kurt_desc = f"尖峰（kurtosis={kurtosis:.2f}），厚尾分布"
        else:
            kurt_desc = f"低峰（kurtosis={kurtosis:.2f}），薄尾分布"

        payload = {
            "symbol": symbol,
            "jb_statistic": round(float(jb_stat), 4),
            "p_value": round(float(p_value), 4),
            "is_normal": is_normal,
            "skewness": round(float(skewness), 4),
            "kurtosis": round(float(kurtosis), 4),
            "excess_kurtosis": round(float(kurtosis - 3), 4),
            "samples_used": n,
            "interpretation": (
                f"收益率分布{'服从' if is_normal else '不服从'}正态分布 (p={'%.4f' % p_value})。"
                f" Skewness: {skew_desc}. kurtosis: {kurt_desc}. "
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("正态性检验失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 5: Stationarity test
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_stationarity_test",
    name="平稳性检验",
    description=(
        "Perform ADF (Augmented Dickey-Fuller) stationarity test on stock price series."
        "Determine whether the price series has a unit root (non-stationary)."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["statistics", "stationarity", "adf", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["时间序列平稳性判断", "单位根检验", "建模前提验证"],
    when_to_use=(
        "When it is necessary to determine whether the stock price series is stationary (the premise assumption of many time series models),"
        "Or used when testing the existence of a unit root."
    ),
    when_not_to_use=(
        "Not suitable for return series (returns are usually stationary);"
        "Insufficient data (< 30 trading days) results are unreliable."
    ),
    returns=(
        "Returns a JSON string containing adf_statistic, p_value, is_stationary,"
        "critical_values, test_type and interpretation."
    ),
    example="get_stationarity_test(symbol='600519')",
    related_tools=[
        "get_normality_test",
        "get_cointegration_test",
    ],
)
def get_stationarity_test(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    lookback_days: Annotated[int, "Number of days to look back, default 252 (about 1 year)"] = 252,
    price_type: Annotated[str, "Price type: close/adjusted, default close"] = "close",
) -> str:
    """Perform ADF stationarity test on stock price series.

    Args:
        symbol: A stock code (such as "600519") 
        lookback_days: Number of days to look back (automatically truncated to 30-2000), default 252
        price_type: price type: "close" (closing price) or "adjusted" (rights after restoration), default "close"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Stock code
            price_type: price type
            adf_statistic: ADF test statistic
            p_value: p value
            is_stationary: Is it stable (p<0.05) 
            critical_values: dict critical value——
                — "1%": 1% critical value
                — "5%": 5% critical value
                — "10%": 10% critical value
            test_type: Inspection type description
            samples_used: Number of samples
            interpretation: interpret text
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(30, min(int(lookback_days), 2000))

        quotes = _fetch_quotes(symbol, lookback_days)
        if not quotes or len(quotes) < 30:
            return json.dumps(
                {"status": "error", "message": "行情数据不足"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Select price field based on price_type
        if price_type == "adjusted":
            fields = ["adj_close", "adj_close", "close"]
        else:
            fields = ["close"]

        prices = []
        for q in quotes:
            c = None
            for f in fields:
                c = _statistical_tools_to_float(q.get(f))
                if c is not None and c > 0:
                    break
            if c is not None and c > 0:
                prices.append(c)

        if len(prices) < 30:
            return json.dumps(
                {"status": "error", "message": f"有效价格数据不足（仅 {len(prices)} 条）"},
                ensure_ascii=False, indent=2, default=str,
            )

        # ADF Inspect
        adf_stat, p_value = _adf_test_simple(prices)
        test_type = "ADF (Augmented Dickey-Fuller, simplified)"

        is_stationary = p_value < 0.05

        # critical value
        critical_values = {
            "1%": -3.43,
            "5%": -2.86,
            "10%": -2.57,
        }

        payload = {
            "symbol": symbol,
            "price_type": price_type,
            "adf_statistic": round(adf_stat, 4),
            "p_value": round(p_value, 4),
            "is_stationary": is_stationary,
            "critical_values": critical_values,
            "test_type": test_type,
            "samples_used": len(prices),
            "interpretation": (
                f"价格序列{'平稳（拒绝单位根假设）' if is_stationary else '非平稳（无法拒绝单位根假设）'}。"
                f" ADF Statistics = {adf_stat:.4f}, p value = {p_value:.4f}. "
                f" {'Note: Stock prices are usually non-stationary and may be stationary after differences or logarithms.' if not is_stationary else ''}"
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("平稳性检验失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 6: GARCH Volatility (EWMA simplified version)
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_garch_volatility",
    name="EWMA 条件波动率",
    description=(
        "Estimate the conditional volatility of a stock using the EWMA (exponentially weighted moving average) model."
        "Using RiskMetrics standard attenuation factors λ=0.94. "
        "Compare current volatility to long-term historical volatility."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["statistics", "volatility", "garch", "ewma", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["条件波动率估计", "风险度量（VaR 输入）", "波动率趋势分析"],
    when_to_use=(
        "When it is necessary to estimate the current conditional volatility level of a stock and compare volatility changes in different periods,"
        "Or used when providing volatility inputs to risk management models."
    ),
    when_not_to_use=(
        "Not suitable for directly predicting future volatility (EWMA is a simplified method);"
        "Insufficient data (< 60 trading days) results are unreliable."
    ),
    returns=(
        "Returns a JSON string containing current_volatility (annualized), long_term_vol,"
        "vol_ratio, volatility_series (The last 20 issues), method_note."
    ),
    example="get_garch_volatility(symbol='600519')",
    related_tools=[
        "get_normality_test",
        "get_stationarity_test",
    ],
)
def get_garch_volatility(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    lookback_days: Annotated[int, "Number of days to look back, default 504 (about 2 years)"] = 504,
    p: Annotated[int, "GARCH Lag order p, default 1 (fixed to EWMA in EWMA mode)"] = 1,
    q: Annotated[int, "ARCH Lag order q, default 1 (fixed to EWMA in EWMA mode)"] = 1,
) -> str:
    """Conditional volatility is estimated using EWMA (RiskMetrics standard).

    Args:
        symbol: A stock code (such as "600519") 
        lookback_days: Number of days to look back (automatically truncated to 60-2000), default 504
        p: GARCH Lag order p (current implementation is fixed to EWMA, parameters are retained), default 1
        q: ARCH Lag order q (current implementation is fixed to EWMA, parameters are retained), default 1

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Stock code
            model: Model ID (fixed to "EWMA (RiskMetrics, λ=0.94)") 
            current_volatility: Current Conditions Volatility (Annualized)
            long_term_historical_volatility: Long-term historical volatility (annualized)
            volatility_ratio: Current/Long-Term Volatility Ratio
            volatility_regime: volatility status: "High volatility (currently > long term × 1.2) " | "Low volatility (currently < long term × 0.8) " | "normal fluctuations"
            volatility_series: list[dict] Volatility series of the last 20 periods, element structure——
                — date: Date
                — daily_volatility: daily volatility
                — annualized_volatility: annualized volatility
            method_note: Method description
            bars_used: Number of return samples used
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(60, min(int(lookback_days), 2000))

        quotes = _fetch_quotes(symbol, lookback_days)
        if not quotes or len(quotes) < 60:
            return json.dumps(
                {"status": "error", "message": "行情数据不足"},
                ensure_ascii=False, indent=2, default=str,
            )

        returns = _compute_daily_returns(quotes)
        if len(returns) < 60:
            return json.dumps(
                {"status": "error", "message": f"有效收益率数据不足（仅 {len(returns)} 个）"},
                ensure_ascii=False, indent=2, default=str,
            )

        ret_arr = np.array(returns)

        # EWMA: σ²_t = λ × σ²_{t-1} + (1-λ) × r²_{t-1}
        lam = 0.94  # RiskMetrics Standard
        n = len(ret_arr)
        sigma2 = np.zeros(n)

        # Initialization: Use variance of first 10 returns
        sigma2[0] = np.var(ret_arr[:10]) if n >= 10 else np.var(ret_arr)

        for t in range(1, n):
            sigma2[t] = lam * sigma2[t - 1] + (1 - lam) * ret_arr[t - 1] ** 2

        sigma = np.sqrt(sigma2)

        # Annualized (assuming 252 trading days)
        annual_factor = math.sqrt(252)
        current_vol = float(sigma[-1] * annual_factor)
        long_term_vol = float(np.std(ret_arr) * annual_factor)

        # Volatility series (last 20 periods)
        vol_series = [
            {
                "date": str(quotes[min(i + 1, len(quotes) - 1)].get("trade_date", "")),
                "daily_volatility": round(float(sigma[i]), 6),
                "annualized_volatility": round(float(sigma[i] * annual_factor), 4),
            }
            for i in range(max(0, n - 20), n)
        ]

        vol_ratio = current_vol / long_term_vol if long_term_vol > 0 else 1.0

        payload = {
            "symbol": symbol,
            "model": "EWMA (RiskMetrics, λ=0.94)",
            "current_volatility": round(current_vol, 4),
            "long_term_historical_volatility": round(long_term_vol, 4),
            "volatility_ratio": round(vol_ratio, 4),
            "volatility_regime": (
                "High volatility (currently > long term × 1.2) " if vol_ratio > 1.2
                else "Low volatility (currently < long term × 0.8) " if vol_ratio < 0.8
                else "正常波动"
            ),
            "volatility_series": vol_series,
            "method_note": (
                "Using the RiskMetrics EWMA model (λ=0.94) Estimate conditional volatility."
                "annualization factor = sqrt(252). "
                "complete GARCH(p,q) A nonlinear optimization solution is required, and EWMA is used here as a simplified alternative."
            ),
            "bars_used": n,
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("GARCH Volatility modeling failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = [
    "get_correlation_matrix",
    "get_cointegration_test",
    "get_rolling_regression",
    "get_normality_test",
    "get_stationarity_test",
    "get_garch_volatility",
]

# === stock_fundamentals ===
"""
Unified Stock Fundamental Data Tool

Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding data sources
"""

import asyncio
import concurrent.futures
import logging
import re
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool
import pandas as pd

from core.tools.base import register_tool
from core.tools.trade_date_policy import apply_stable_data_cutoff, build_stable_data_cutoff_note

logger = logging.getLogger(__name__)


def _normalize_china_ticker(ticker: str) -> str:
    """Standardized A-share ticker, compatible with inputs with exchange suffixes."""
    return re.sub(r'\.(SZ|SH|BJ|sz|sh|bj)$', '', str(ticker).strip())


def _run_async_in_sync(coro):
    """Safely run asynchronous providers in sync tools."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    def _runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_runner)
        return future.result(timeout=120)


def _coerce_records(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, 'to_dict'):
        try:
            value = value.to_dict('records')
        except Exception:
            return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalize_financial_payload(raw_data: Optional[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Unify financial field structure across different caches/providers."""
    normalized = {
        'income_statement': [],
        'balance_sheet': [],
        'cash_flow': [],
        'financial_indicators': [],
    }
    if not isinstance(raw_data, dict):
        return normalized

    payload = raw_data
    if isinstance(raw_data.get('raw_data'), dict):
        payload = raw_data['raw_data']
    elif isinstance(raw_data.get('financial_data'), dict):
        payload = raw_data['financial_data']

    normalized['income_statement'] = _coerce_records(payload.get('income_statement'))
    normalized['balance_sheet'] = _coerce_records(payload.get('balance_sheet'))
    normalized['cash_flow'] = _coerce_records(payload.get('cash_flow') or payload.get('cashflow_statement'))
    normalized['financial_indicators'] = _coerce_records(
        payload.get('financial_indicators') or payload.get('main_indicators')
    )
    return normalized


def _period_token(record: Dict[str, Any]) -> str:
    for field in ('end_date', 'report_period', 'period', 'ann_date', 'f_ann_date'):
        value = record.get(field)
        if value:
            token = re.sub(r'\D', '', str(value))
            if len(token) >= 8:
                return token[:8]
            return str(value)
    return 'unknown'


def _display_period(period_token: str) -> str:
    digits = re.sub(r'\D', '', str(period_token))
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return str(period_token)


def _sort_and_trim_records(records: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    ordered = sorted(records, key=_period_token, reverse=True)
    return ordered[:limit]


def _load_recent_financial_data(ticker: str, limit: int = 4) -> Dict[str, Any]:
    """Give priority to cached/persistent data, and then downgrade to the online provider if missing."""
    from tradingagents.utils.stock_utils import StockUtils

    normalized_ticker = _normalize_china_ticker(ticker)
    market_info = StockUtils.get_market_info(normalized_ticker)
    payload = None
    data_source = 'unknown'

    try:
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

        provider = OptimizedChinaDataProvider()
        if hasattr(provider, '_get_cached_raw_financial_data'):
            payload = _normalize_financial_payload(provider._get_cached_raw_financial_data(normalized_ticker))
            if any(payload.values()):
                data_source = 'optimized_cache'
    except Exception as exc:
        logger.warning(f"⚠️ 财务缓存读取失败: {exc}")

    if not payload or not any(payload.values()):
        try:
            from tradingagents.dataflows.providers.china.tushare import TushareProvider

            provider = TushareProvider()
            raw_data = _run_async_in_sync(
                provider.get_financial_data(normalized_ticker, report_type='quarterly', limit=limit)
            )
            payload = _normalize_financial_payload(raw_data)
            if any(payload.values()):
                data_source = 'tushare'
        except Exception as exc:
            logger.warning(f"⚠️ Tushare Failed to obtain financial data: {exc}")

    if not payload or not any(payload.values()):
        try:
            from tradingagents.dataflows.providers.china.akshare import AKShareProvider

            provider = AKShareProvider()
            raw_data = _run_async_in_sync(provider.get_financial_data(normalized_ticker))
            payload = _normalize_financial_payload(raw_data)
            if any(payload.values()):
                data_source = 'akshare'
        except Exception as exc:
            logger.warning(f"⚠️ AKShare Failed to obtain financial data: {exc}")

    payload = payload or _normalize_financial_payload(None)
    for key, records in payload.items():
        payload[key] = _sort_and_trim_records(records, limit)

    payload['ticker'] = normalized_ticker
    payload['market_info'] = market_info
    payload['data_source'] = data_source
    return payload


def _snapshot_value(value: Any, default: str = 'N/A') -> str:
    if value in (None, '', 'None', 'nan', 'NaN'):
        return default
    return str(value)


def _format_pct_change(value: Any) -> str:
    number = _stock_fundamentals_to_float(value)
    if number is None:
        return 'N/A'
    return f"{number:+.2f}%"


def _build_china_company_profile(ticker: str) -> Optional[str]:
    """Construct basic information of A-share companies without real-time price fields."""
    normalized_ticker = _normalize_china_ticker(ticker)

    try:
        from tradingagents.dataflows.cache.app_adapter import get_basics_from_cache

        basics_doc = get_basics_from_cache(normalized_ticker)
        if isinstance(basics_doc, list):
            basics_doc = basics_doc[0] if basics_doc else None

        if not basics_doc:
            return None

        lines = [
            f"股票代码: {normalized_ticker}",
            f"股票名称: {_snapshot_value((basics_doc or {}).get('name') or (basics_doc or {}).get('stock_name'), '未知公司')}",
            f"所属地区: {_snapshot_value((basics_doc or {}).get('area'), '未知')}",
            f"所属行业: {_snapshot_value((basics_doc or {}).get('industry') or (basics_doc or {}).get('industry_name'), '未知')}",
            f"上市市场: {_snapshot_value((basics_doc or {}).get('market'), '未知')}",
            f"上市日期: {_snapshot_value((basics_doc or {}).get('list_date'), '未知')}",
        ]
        logger.info(f"📊 [Unified fundamental tools] Constructing A-share company profiles using database static information: {normalized_ticker}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning(f"⚠️ A Failed to read static company information: {exc}")
        return None


def _build_china_snapshot_from_cache(ticker: str) -> Optional[str]:
    """Prioritize constructing current price information from app MongoDB snapshots to avoid pulling historical quotes for fundamental tools."""
    normalized_ticker = _normalize_china_ticker(ticker)

    try:
        from tradingagents.dataflows.cache.app_adapter import get_basics_from_cache, get_market_quote_dataframe

        basics_doc = get_basics_from_cache(normalized_ticker)
        if isinstance(basics_doc, list):
            basics_doc = basics_doc[0] if basics_doc else None

        quote_df = get_market_quote_dataframe(normalized_ticker)
        if not basics_doc and (quote_df is None or quote_df.empty):
            return None

        lines = [
            f"股票代码: {normalized_ticker}",
            f"股票名称: {_snapshot_value((basics_doc or {}).get('name') or (basics_doc or {}).get('stock_name'), '未知公司')}",
            f"所属地区: {_snapshot_value((basics_doc or {}).get('area'), '未知')}",
            f"所属行业: {_snapshot_value((basics_doc or {}).get('industry') or (basics_doc or {}).get('industry_name'), '未知')}",
            f"上市市场: {_snapshot_value((basics_doc or {}).get('market'), '未知')}",
            f"上市日期: {_snapshot_value((basics_doc or {}).get('list_date'), '未知')}",
        ]

        current_price = 'N/A'
        change_pct = 'N/A'
        volume = 'N/A'
        if quote_df is not None and not quote_df.empty:
            latest_quote = quote_df.iloc[-1]
            current_price = _snapshot_value(latest_quote.get('close'))
            change_pct = _format_pct_change(latest_quote.get('pct_chg'))
            volume = _snapshot_value(latest_quote.get('volume'))

        lines.extend([
            f"当前价格: {current_price}",
            f"涨跌幅: {change_pct}",
            f"成交量: {volume}",
        ])
        logger.info(f"📊 [Unified fundamental tools] Use database snapshot to construct A-share price information: {normalized_ticker}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning(f"⚠️ A Stock database snapshot read failed: {exc}")
        return None


def _is_placeholder_china_snapshot(snapshot: Optional[str]) -> bool:
    if not snapshot:
        return True
    markers = (
        '股票名称: 未知公司',
        '当前价格: N/A',
        '涨跌幅: N/A',
        '成交量: N/A',
    )
    return all(marker in snapshot for marker in markers)


def _get_china_price_snapshot(ticker: str, curr_date: str) -> str:
    """Construct A-share price snapshots for unified fundamental tools, read the library first, and then downgrade to the market provider."""
    normalized_ticker = _normalize_china_ticker(ticker)

    cached_snapshot = _build_china_snapshot_from_cache(normalized_ticker)
    if cached_snapshot:
        return cached_snapshot

    try:
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

        analyzer = OptimizedChinaDataProvider()
        snapshot = analyzer._get_stock_basic_info_only(normalized_ticker)
        if not _is_placeholder_china_snapshot(snapshot):
            logger.info(f"📊 [Unified fundamental tools] Use the basic information interface to construct A-share price information: {normalized_ticker}")
            return snapshot
    except Exception as exc:
        logger.warning(f"⚠️ A Failed to obtain basic stock information: {exc}")

    recent_end_date = curr_date
    recent_start_date = (datetime.strptime(curr_date, '%Y-%m-%d') - timedelta(days=2)).strftime('%Y-%m-%d')
    from tradingagents.dataflows.interface import get_china_stock_data_unified

    logger.warning(f"⚠️ A The stock database snapshot is unavailable and is downgraded to the market interface.: {normalized_ticker}")
    return get_china_stock_data_unified(normalized_ticker, recent_start_date, recent_end_date)


def _strip_realtime_snapshot_fields(text: Optional[str]) -> str:
    """Removed live snapshot fields that should not be used in fundamental research."""
    if not text:
        return ""

    dropped_markers = (
        '当前价格',
        '当前股价',
        '最新价格',
        '涨跌幅',
        '成交量',
        '总市值',
        '流通市值',
        '基本价格信息',
        '市盈率(PE)',
        'P/E ratio TTM(PE_TTM)',
        '市净率(PB)',
        '市销率(PS)',
        '股息收益率',
    )

    cleaned_lines: List[str] = []
    previous_blank = False
    for raw_line in str(text).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped and any(marker in stripped for marker in dropped_markers):
            continue

        if not stripped:
            if previous_blank:
                continue
            previous_blank = True
            cleaned_lines.append("")
            continue

        previous_blank = False
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def _stock_fundamentals_to_float(value: Any) -> Optional[float]:
    if value in (None, '', 'None', 'nan', 'NaN'):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(',', ''))
    except Exception:
        return None


def _stock_fundamentals_format_value(value: Any, style: str = 'number') -> str:
    number = _stock_fundamentals_to_float(value)
    if number is None:
        return str(value)
    if style == 'percent':
        return f"{number:.2f}%"
    if style == 'plain':
        return f"{number:.2f}"
    abs_number = abs(number)
    if abs_number >= 1e8:
        return f"{number / 1e8:,.2f}亿元"
    if abs_number >= 1e4:
        return f"{number / 1e4:,.2f}万元"
    return f"{number:,.2f}"


def _pick_value(record: Dict[str, Any], *fields: str) -> Any:
    for field in fields:
        value = record.get(field)
        if value not in (None, '', 'None', 'nan', 'NaN'):
            return value
    return None


def _metric_line(record: Dict[str, Any], label: str, fields: List[str], style: str = 'number') -> Optional[str]:
    value = _pick_value(record, *fields)
    if value is None:
        return None
    return f"- {label}: {_stock_fundamentals_format_value(value, style)}"


def _index_by_period(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for record in records:
        indexed.setdefault(_period_token(record), record)
    return indexed


def _merge_recent_periods(*record_groups: List[Dict[str, Any]], limit: int = 4) -> List[str]:
    period_tokens = set()
    for records in record_groups:
        for record in records:
            period_tokens.add(_period_token(record))
    return sorted(period_tokens, reverse=True)[:limit]


def _quarter_from_period(period_token: str) -> Optional[int]:
    digits = re.sub(r'\D', '', str(period_token))
    if len(digits) != 8:
        return None

    return {
        '0331': 1,
        '0630': 2,
        '0930': 3,
        '1231': 4,
    }.get(digits[4:8])


def _previous_cumulative_period(period_token: str) -> Optional[str]:
    digits = re.sub(r'\D', '', str(period_token))
    if len(digits) != 8:
        return None

    quarter = _quarter_from_period(digits)
    if quarter in (None, 1):
        return None

    previous_suffix = {
        2: '0331',
        3: '0630',
        4: '0930',
    }[quarter]
    return f"{digits[:4]}{previous_suffix}"


def _derive_single_quarter_value(
    period_token: str,
    records_by_period: Dict[str, Dict[str, Any]],
    fields: List[str],
) -> Tuple[Optional[float], str]:
    current_record = records_by_period.get(period_token) or {}
    current_value = _stock_fundamentals_to_float(_pick_value(current_record, *fields))
    if current_value is None:
        return None, 'missing-current'

    quarter = _quarter_from_period(period_token)
    if quarter == 1:
        return current_value, 'q1'

    previous_period = _previous_cumulative_period(period_token)
    if not previous_period:
        return None, 'missing-prev-period'

    previous_record = records_by_period.get(previous_period) or {}
    previous_value = _stock_fundamentals_to_float(_pick_value(previous_record, *fields))
    if previous_value is None:
        return None, 'missing-prev-value'

    return current_value - previous_value, 'derived'


def _single_quarter_metric_line(
    period_token: str,
    records_by_period: Dict[str, Dict[str, Any]],
    label: str,
    fields: List[str],
    style: str = 'number',
) -> Optional[str]:
    value, status = _derive_single_quarter_value(period_token, records_by_period, fields)
    if value is not None:
        return f"- {label}: {_stock_fundamentals_format_value(value, style)}"

    if status in {'missing-prev-period', 'missing-prev-value'}:
        return f"- {label}: N/A (Lacking the cumulative value of the previous period, it is temporarily impossible to derive a single quarter)"

    return None


def _calculate_percentile_rank(values: List[float], current: float) -> Optional[float]:
    valid = [value for value in values if value is not None]
    if not valid:
        return None

    count = sum(1 for value in valid if value <= current)
    return count / len(valid) * 100


def _describe_percentile_band(percentile: Optional[float]) -> str:
    if percentile is None:
        return 'N/A'
    if percentile < 20:
        return '历史低位'
    if percentile < 40:
        return '历史中低位'
    if percentile < 60:
        return '历史中枢附近'
    if percentile < 80:
        return '历史中高位'
    return '历史高位'


def _build_historical_valuation_section_from_frame(
    valuation_df: pd.DataFrame,
    *,
    window_start: str,
    window_end: str,
    requested_analysis_date: Optional[str] = None,
    effective_analysis_date: Optional[str] = None,
) -> str:
    if valuation_df is None or valuation_df.empty:
        return "The tool results do not provide historical valuation quantile data."

    working_df = valuation_df.copy()
    if 'trade_date' not in working_df.columns:
        return "The tool results do not provide historical valuation quantile data."

    working_df['trade_date'] = working_df['trade_date'].astype(str)
    working_df = working_df.sort_values('trade_date', ascending=False)
    latest_available_trade_date = _display_period(str(working_df.iloc[0]['trade_date']))

    lines = [
        f"- 样本窗口: {window_start} 至 {window_end}",
        f"- 有效交易日样本: {len(working_df)}",
        f"- Last available valuation snapshot date: {latest_available_trade_date}",
        "- Valuation snapshot caliber: The following is as written current PE/PB/PS(TTM) etc., all refer to the latest available and valid trading day snapshot in the historical sequence of the indicator, rather than the real-time market price.",
        "- date description: The date in parentheses after each indicator is the valuation snapshot date adopted by the indicator this time; if the available samples for different indicators are different, they will not be regarded as the same trading day by default. The snapshot date must not be replaced with the analysis date.",
    ]

    cutoff_note = build_stable_data_cutoff_note(
        requested_analysis_date or "",
        effective_analysis_date or "",
        subject="Daily frequency data after the close of the day required for valuation analysis",
    )
    if cutoff_note:
        lines.append(f"- 稳定数据说明: {cutoff_note}")

    metric_specs = [
        ('pe', 'PE'),
        ('pe_ttm', 'PE(TTM)'),
        ('pb', 'PB'),
        ('ps_ttm', 'PS(TTM)'),
    ]

    any_metric = False
    for column, label in metric_specs:
        if column not in working_df.columns:
            lines.append(f"- {label}: The tool results do not provide historical series, and historical quantiles cannot be calculated yet.")
            continue

        numeric_series = pd.to_numeric(working_df[column], errors='coerce')
        valid_df = working_df.loc[numeric_series.notna()].copy()
        valid_df[column] = pd.to_numeric(valid_df[column], errors='coerce')
        valid_df = valid_df[valid_df[column] > 0]

        if len(valid_df) < 60:
            lines.append(f"- {label}: The tool results do not provide enough historical samples, and the historical quantiles cannot be calculated at the moment.")
            continue

        latest_row = valid_df.iloc[0]
        current_value = float(latest_row[column])
        percentile = _calculate_percentile_rank(valid_df[column].tolist(), current_value)
        median_value = float(valid_df[column].median())
        latest_trade_date = _display_period(str(latest_row['trade_date']))
        percentile_text = f"{percentile:.1f}%" if percentile is not None else 'N/A'
        band = _describe_percentile_band(percentile)

        lines.append(
            f"- {label}: 当前 {current_value:.2f} 倍（{latest_trade_date}） | 历史中位数 {median_value:.2f} 倍 | 历史分位 {percentile_text} | 历史位置: {band}"
        )
        any_metric = True

    lines.append("- PEG: The current tool does not provide a stable daily PEG historical sequence, and the historical quantiles cannot be calculated yet.")

    if not any_metric:
        return "The tool results do not provide a valid valuation series that can be used to calculate historical valuation quantiles."

    return "\n".join(lines)


def _get_historical_valuation_summary(
    ticker: str,
    curr_date: str,
    *,
    lookback_years: int = 3,
) -> str:
    normalized_ticker = _normalize_china_ticker(ticker)

    requested_curr_date = curr_date
    stable_curr_date = apply_stable_data_cutoff(curr_date)
    if stable_curr_date != curr_date:
        logger.info(
            f"🕖 Fundamental historical valuation input date {requested_curr_date} When stable data has not been reached, fall back to {stable_curr_date}"
        )
        curr_date = stable_curr_date
    try:
        end_dt = datetime.strptime(curr_date, '%Y-%m-%d')
    except Exception:
        end_dt = datetime.now()

    start_dt = end_dt - timedelta(days=365 * lookback_years)

    try:
        from tradingagents.dataflows.providers.china.tushare import TushareProvider

        provider = TushareProvider()
        if not provider.is_available():
            provider.connect_sync()
        if not provider.is_available() or provider.api is None:
            return "The tool results do not provide historical valuation quantile data."

        ts_code = provider._normalize_ts_code(normalized_ticker)
        valuation_df = provider.api.daily_basic(
            ts_code=ts_code,
            start_date=start_dt.strftime('%Y%m%d'),
            end_date=end_dt.strftime('%Y%m%d'),
            fields='ts_code,trade_date,pe,pe_ttm,pb,ps_ttm',
        )

        return _build_historical_valuation_section_from_frame(
            valuation_df,
            window_start=start_dt.strftime('%Y-%m-%d'),
            window_end=end_dt.strftime('%Y-%m-%d'),
            requested_analysis_date=requested_curr_date,
            effective_analysis_date=curr_date,
        )
    except Exception as exc:
        logger.warning(f"⚠️ Historical valuation quantile calculation failed: {exc}")
        return "The tool results do not provide historical valuation quantile data."


@tool
@register_tool(
    tool_id="get_stock_fundamentals_unified",
    name="统一股票基本面数据",
    description="Obtain complete fundamental data of A-share companies: revenue, net profit, ROE, ROIC, gross profit margin, net profit margin, asset-liability ratio, earnings per share and other core financial indicators",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["基本面", "财务数据", "营收", "净利润", "ROE", "ROIC", "毛利率", "净利率", "每股收益", "资产负债率", "利润表", "资产负债表", "A股"],
    when_to_use="Use it when you need to obtain fundamental financial data such as revenue, profit margin, ROE/ROIC, assets and liabilities of A-share stocks.",
    tool_role_hint="primary",
    output_shape="structured_metrics",
)
def get_stock_fundamentals_unified(
    ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
    start_date: Annotated[Optional[str], "Start date, format:YYYY-MM-DD"] = None,
    end_date: Annotated[Optional[str], "End date, format:YYYY-MM-DD"] = None,
    curr_date: Annotated[Optional[str], "Current date, format:YYYY-MM-DD"] = None
) -> str:
    """
    Unified stock fundamental analysis tool
    Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding data sources
    Support data acquisition strategies based on analysis level

    Args:
        ticker: Stock code (such as: 000001, 0700.HK, AAPL)
        start_date: Start date (optional, format: YYYY-MM-DD)
        end_date: End date (optional, format: YYYY-MM-DD)
        curr_date: Current date (optional, format: YYYY-MM-DD)

    Returns:
        str: Fundamental Analysis Data and Reports
    """
    logger.info(f"📊 [Unified fundamental tools] Analyze stocks: {ticker}")

    try:
        from tradingagents.utils.stock_utils import StockUtils

        # Automatically identify stock types
        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']

        logger.info(f"📊 [Unified fundamental tools] Stock type: {market_info['market_name']}")

        # Set default date
        if not curr_date:
            curr_date = datetime.now().strftime('%Y-%m-%d')

        # Fundamental analysis requires only recent data
        days_to_fetch = 10
        if not start_date:
            start_date = (datetime.now() - timedelta(days=days_to_fetch)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = curr_date

        result_data = []

        if is_china:
            # China A shares
            logger.info("🇨🇳 [Unified fundamental tools] Process A-share data...")
            normalized_ticker = _normalize_china_ticker(ticker)
            company_profile_data = ""

            try:
                company_profile_data = _build_china_company_profile(normalized_ticker)
                if not company_profile_data:
                    from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

                    analyzer = OptimizedChinaDataProvider()
                    company_profile_data = _strip_realtime_snapshot_fields(
                        analyzer._get_stock_basic_info_only(normalized_ticker)
                    )

                if company_profile_data:
                    result_data.append(f"## A股公司基础信息\n{company_profile_data}")
            except Exception as e:
                logger.error(f"❌ A Failed to obtain static company information: {e}")

            result_data.append(
                "## A Explanation of stock fundamental analysis caliber\n"
                "- This tool is designed for analysis of historical financials, historical valuation ranges and disclosed operating data.\n"
                "- Real-time snapshot fields such as current stock price, rise and fall, trading volume, and current total market capitalization are not provided, and these fields should not be used as the basis for fundamental conclusions."
            )
            result_data.append(
                "## A Stock Valuation Snapshot Date Description\n"
                "- Valuation snapshot caliber: PE, PE(TTM), PB, PS(TTM) If the valuation indicator is expressed as current value , All refer to the latest available and valid trading day snapshot of the corresponding indicator, rather than the real-time market price.\n"
                "- If the historical valuation quantile part has a date attached to the indicator, that date will be the valuation snapshot date adopted by the indicator this time; if the dates of different indicators are different, they will not be regarded as the same trading day by default."
            )
            stable_curr_date = apply_stable_data_cutoff(curr_date)
            stable_note = build_stable_data_cutoff_note(
                curr_date,
                stable_curr_date,
                subject="Daily frequency data after the close of the day required for valuation analysis",
            )
            if stable_note:
                result_data.append(f"## A Stock data date description\n- {stable_note}")

            try:
                # Get fundamental financial data
                from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
                analyzer = OptimizedChinaDataProvider()
                fundamentals_data = analyzer._generate_fundamentals_report(normalized_ticker, company_profile_data, "standard")
                fundamentals_data = _strip_realtime_snapshot_fields(fundamentals_data)
                result_data.append(f"## A股基本面财务数据\n{fundamentals_data}")
            except Exception as e:
                logger.error(f"❌ A Failed to obtain stock fundamental data: {e}")
                result_data.append(f"## A Stock Fundamentals Financial Data\n Failed to obtain: {e}")

            try:
                historical_valuation = _get_historical_valuation_summary(normalized_ticker, curr_date)
                result_data.append(f"## A股历史估值分位\n{historical_valuation}")
            except Exception as e:
                logger.error(f"❌ A Failed to obtain stock historical valuation quantile: {e}")
                result_data.append("## A Stock historical valuation quantile\n The tool results do not provide historical valuation quantile data.")

        elif is_hk:
            # Hong Kong stocks
            logger.info("🇭🇰 [Unified fundamental tools] Processing Hong Kong stock data...")

            try:
                from tradingagents.dataflows.interface import get_hk_stock_data_unified
                hk_data = get_hk_stock_data_unified(ticker, start_date, end_date)

                if hk_data and len(hk_data) > 100 and "❌" not in hk_data:
                    result_data.append(f"## 港股数据\n{hk_data}")
                else:
                    raise ValueError("港股数据质量不佳")
            except Exception as e:
                logger.error(f"❌ 港股数据获取失败: {e}")
                result_data.append(f"## Hong Kong stock data\n Failed to obtain: {e}")

        elif is_us:
            # US stocks
            logger.info("🇺🇸 [Unified fundamental tools] Processing US stock data...")

            try:
                from tradingagents.dataflows.interface import get_fundamentals_openai
                us_data = get_fundamentals_openai(ticker, curr_date)
                result_data.append(f"## 美股基本面数据\n{us_data}")
            except Exception as e:
                logger.error(f"❌ 美股数据获取失败: {e}")
                result_data.append(f"## U.S. stock fundamentals data\n Failed to obtain: {e}")

        else:
            logger.warning(f"⚠️ [Unified fundamental tools] Unidentified stock market: {ticker} -> {market_info['market_name']}")
            result_data.append(
                f"## 市场识别结果\n{ticker} 未识别到受支持的股票市场，当前识别结果为 {market_info['market_name']}。"
            )

        # Combine all data
        combined_result = f"""# {ticker} 基本面分析数据

**股票类型**: {market_info['market_name']}
**货币**: {market_info['currency_name']} ({market_info['currency_symbol']})
**分析日期**: {curr_date}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的数据源*
"""

        logger.info(f"📊 [Unified fundamental tools] Data acquisition completed, total length: {len(combined_result)}")
        return combined_result

    except Exception as e:
        error_msg = f"Unified fundamental analysis tool execution failed: {str(e)}"
        logger.error(f"❌ [统一基本面工具] {error_msg}")
        return error_msg


@tool
@register_tool(
    tool_id="get_financial_statements",
    name="最近季度财报明细",
    description="Obtain the income statement (operating income, operating costs, net profit, etc.), balance sheet and core financial indicator details of A-shares in recent quarters, and derive a single-quarter caliber for the main income statement fields.",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["利润表", "资产负债表", "财务报表", "净利润", "营收", "营业收入", "营业成本", "A股", "财报"],
    when_to_use="Use it when you need to obtain the latest quarterly financial statements of A-share companies, including income statements and balance sheets.",
    tool_role_hint="primary",
    output_shape="structured_metrics",
)
def get_financial_statements(
    ticker: Annotated[str, "A Stock code, supports 000001 or 000001.SZ format"],
    limit: Annotated[int, "Returns the most recent quarters, default 4"] = 4
) -> str:
    """Get the latest quarterly financial report details.

    Args:
        ticker: A stock ticker code, support "000001" or "000001.SZ" form
        limit: Returns the most recent quarters (automatically truncated to 1-8), default 4

    Returns:
        str: Markdown Format string containing the following sections——
            Title: "{ticker} Recently{N}Quarterly financial report details"
            Stock type: Market name
            Data source: Data source description
            Caliber description: Explanation on cumulative value and single-quarter caliber
            Chapters for each reporting period (by ## reporting period grouping), each reporting period contains——
                - Income statement (single quarter derivation): Single-quarter derived value of total operating income/operating profit/net profit attributable to parent company/net profit
                - Income Statement (original reporting period cumulative/snapshot): Total operating income/operating profit/net profit attributable to parent company/net profit/basic earnings per share
                - balance sheet: Total assets/total liabilities/total shareholders equity/total current assets/total current liabilities/monetary funds
                - core financial indicators: ROE/ROA/Gross profit margin/net profit margin/asset-liability ratio/current ratio/single-quarter net profit margin (derivation)

            If it is not the A-share market, a prompt string will be returned;
            If no data is returned "{ticker} Details of the latest quarterly financial report are not yet available."; 
            If exception returns "get {ticker} Recent quarterly financial report details failed: ..." string.
    """
    try:
        limit = max(1, min(int(limit), 8))
        load_limit = min(limit + 1, 8)
        financial_data = _load_recent_financial_data(ticker, limit=load_limit)
        market_info = financial_data['market_info']

        if not market_info.get('is_china'):
            return f"{ticker} Currently, only China A-share financial report detailed inquiry is supported, which is not supported at the moment. {market_info.get('market_name', 'the market')}. "

        income_records = financial_data['income_statement']
        balance_records = financial_data['balance_sheet']
        indicator_records = financial_data['financial_indicators']
        periods = _merge_recent_periods(income_records, balance_records, indicator_records, limit=limit)

        if not periods:
            return f"{financial_data['ticker']} Details of the latest quarterly financial report are not yet available."

        income_by_period = _index_by_period(income_records)
        balance_by_period = _index_by_period(balance_records)
        indicators_by_period = _index_by_period(indicator_records)

        result_lines = [
            f"# {financial_data['ticker']} 最近{len(periods)}个季度财报明细",
            "",
            f"**股票类型**: {market_info['market_name']}",
            f"**数据来源**: {financial_data['data_source']}",
            "**Caliber description**: A Fields such as operating income and net profit attributable to shareholders in the stock income statement are usually cumulative values from the beginning of the year to the reporting period. Q2/Q3/Q4 are not single-quarter values and cannot be directly added or directly written as a quarter-by-quarter improvement. If a single quarter needs to be estimated, the current period s cumulative minus the previous period s cumulative should usually be used (Q1 can be approximately regarded as a single quarter). Financial indicators such as ROE and net interest rate are currently displayed as snapshots of indicators for the corresponding reporting period and have not been restored to a single quarter.",
            "",
        ]

        for period in periods:
            result_lines.append(f"## 报告期 {_display_period(period)}")

            income = income_by_period.get(period)
            if income:
                single_quarter_lines = [
                    _single_quarter_metric_line(period, income_by_period, '营业总收入（单季度推导）', ['total_revenue', 'revenue']),
                    _single_quarter_metric_line(period, income_by_period, '营业利润（单季度推导）', ['operate_profit', 'oper_profit']),
                    _single_quarter_metric_line(period, income_by_period, '归母净利润（单季度推导）', ['n_income_attr_p', 'net_profit']),
                    _single_quarter_metric_line(period, income_by_period, '净利润（单季度推导）', ['n_income']),
                ]
                if any(single_quarter_lines):
                    result_lines.append("### Income statement (single quarter derivation)")
                    for line in single_quarter_lines:
                        if line:
                            result_lines.append(line)

                result_lines.append("### Income Statement (original reporting period cumulative/snapshot)")
                for line in [
                    _metric_line(income, '营业总收入（原始累计）', ['total_revenue', 'revenue']),
                    _metric_line(income, '营业利润（原始累计）', ['operate_profit', 'oper_profit']),
                    _metric_line(income, '归母净利润（原始累计）', ['n_income_attr_p', 'net_profit']),
                    _metric_line(income, '净利润（原始累计）', ['n_income']),
                    _metric_line(income, '基本每股收益（报告期）', ['basic_eps'], 'plain'),
                ]:
                    if line:
                        result_lines.append(line)

            balance = balance_by_period.get(period)
            if balance:
                result_lines.append("### 资产负债表")
                for line in [
                    _metric_line(balance, '资产总计', ['total_assets']),
                    _metric_line(balance, '负债合计', ['total_liab']),
                    _metric_line(balance, '股东权益合计', ['total_hldr_eqy_exc_min_int', 'total_equity']),
                    _metric_line(balance, '流动资产合计', ['total_cur_assets']),
                    _metric_line(balance, '流动负债合计', ['total_cur_liab']),
                    _metric_line(balance, '货币资金', ['money_cap', 'cash_and_equivalents']),
                ]:
                    if line:
                        result_lines.append(line)

            indicators = indicators_by_period.get(period)
            if indicators:
                result_lines.append("### 核心财务指标")
                single_quarter_revenue, _ = _derive_single_quarter_value(period, income_by_period, ['total_revenue', 'revenue'])
                single_quarter_profit, _ = _derive_single_quarter_value(period, income_by_period, ['n_income_attr_p', 'net_profit'])
                for line in [
                    _metric_line(indicators, 'Return on net assets during the reporting period ROE', ['roe', 'roe_dt'], 'percent'),
                    _metric_line(indicators, 'Return on total assets during the reporting period ROA', ['roa'], 'percent'),
                    _metric_line(indicators, '报告期毛利率', ['grossprofit_margin', 'gross_margin'], 'percent'),
                    _metric_line(indicators, '报告期净利率', ['netprofit_margin', 'net_margin'], 'percent'),
                    _metric_line(indicators, '资产负债率', ['debt_to_assets', 'debt_to_asset'], 'percent'),
                    _metric_line(indicators, '流动比率', ['current_ratio'], 'plain'),
                ]:
                    if line:
                        result_lines.append(line)

                if single_quarter_revenue not in (None, 0) and single_quarter_profit is not None:
                    result_lines.append(
                        f"- Single quarter net profit margin (derivation): {single_quarter_profit / single_quarter_revenue * 100:.2f}%"
                    )

            result_lines.append("")

        return "\n".join(result_lines).strip()

    except Exception as exc:
        logger.error(f"❌ [Financial Report Detail Tool] Execution failed: {exc}", exc_info=True)
        return f"获取 {ticker} 最近季度财报明细失败: {exc}"


@tool
@register_tool(
    tool_id="get_cash_flow_statement",
    name="最近季度现金流量表",
    description="Obtain the cash flow statements of A-shares in recent quarters (operating cash flow, investment cash flow, financing cash flow, free cash flow), and derive a single-quarter caliber for the main cash flow fields.",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["现金流", "现金流量表", "经营现金流", "自由现金流", "FCF", "资本支出", "CAPEX", "折旧", "A股"],
    when_to_use="Use it when you need to obtain the cash flow statement of A-share companies, including operating/investing/financing cash flow, free cash flow, capital expenditure and other data",
    tool_role_hint="primary",
    output_shape="structured_metrics",
)
def get_cash_flow_statement(
    ticker: Annotated[str, "A Stock code, supports 000001 or 000001.SZ format"],
    limit: Annotated[int, "Returns the most recent quarters, default 4"] = 4
) -> str:
    """Obtain the most recent quarterly cash flow statement.

    Args:
        ticker: A stock ticker code, support "000001" or "000001.SZ" form
        limit: Returns the most recent quarters (automatically truncated to 1-8), default 4

    Returns:
        str: Markdown Format string containing the following sections——
            Title: "{ticker} Recently{N}quarterly cash flow statement"
            Stock type: Market name
            Data source: Data source description
            Caliber description: Explanation on cumulative cash flow value and single-quarter caliber
            Chapters for each reporting period (by ## reporting period grouping), each reporting period contains——
                - Cash flow statement (single quarter derivation): Single-quarter derived value of net cash flow from operating/investing/financing activities
                - Cash Flow Statement (Original Reporting Period Cumulative/Snapshot): Net cash flow from operating/investing/financing activities,
                  Opening/ending cash and cash equivalents balance
                - Net operating cash in a single quarter/net profit attributable to parent company (derivation): Ratio
                - Cumulative net operating cash/net profit attributable to parent company during the reporting period: Ratio

            If it is not the A-share market, a prompt string will be returned;
            If no data is returned "{ticker} The most recent quarterly cash flow statement data is not yet available."; 
            If exception returns "get {ticker} Most recent quarterly cash flow statement failed: ..." string.
    """
    try:
        limit = max(1, min(int(limit), 8))
        load_limit = min(limit + 1, 8)
        financial_data = _load_recent_financial_data(ticker, limit=load_limit)
        market_info = financial_data['market_info']

        if not market_info.get('is_china'):
            return f"{ticker} Currently, only China A-share cash flow statement query is supported, which is not currently supported. {market_info.get('market_name', 'the market')}. "

        cash_flow_records = financial_data['cash_flow']
        income_by_period = _index_by_period(financial_data['income_statement'])

        if not cash_flow_records:
            return f"{financial_data['ticker']} The most recent quarterly cash flow statement data is not yet available."

        display_cash_flows = cash_flow_records[:limit]

        result_lines = [
            f"# {financial_data['ticker']} 最近{len(display_cash_flows)}个季度现金流量表",
            "",
            f"**股票类型**: {market_info['market_name']}",
            f"**数据来源**: {financial_data['data_source']}",
            "**Caliber description**: A Fields such as net cash flow from operating activities in the stock cash flow statement are usually cumulative values from the beginning of the year to the reporting period. Q2/Q3/Q4 are not single-quarter values and cannot be directly added or directly written as quarter-by-quarter improvements in a single quarter. If a single quarter needs to be estimated, the current period s accumulation minus the previous period s accumulation should usually be used (Q1 can be approximately regarded as a single quarter).",
            "",
        ]

        cash_flow_by_period = _index_by_period(cash_flow_records)

        for cash_flow in display_cash_flows:
            period = _period_token(cash_flow)
            result_lines.append(f"## 报告期 {_display_period(period)}")

            single_quarter_cash_lines = [
                _single_quarter_metric_line(period, cash_flow_by_period, 'Net cash flow from operating activities (single quarter derivation)', ['n_cashflow_act']),
                _single_quarter_metric_line(period, cash_flow_by_period, 'Net cash flow from investing activities (single quarter derivation)', ['n_cashflow_inv_act']),
                _single_quarter_metric_line(period, cash_flow_by_period, 'Net cash flow from financing activities (single quarter derivation)', ['n_cash_flows_fnc_act', 'n_cashflow_fin_act']),
            ]
            if any(single_quarter_cash_lines):
                result_lines.append("### Cash flow statement (single quarter derivation)")
                for line in single_quarter_cash_lines:
                    if line:
                        result_lines.append(line)

            result_lines.append("### Cash Flow Statement (Original Reporting Period Cumulative/Snapshot)")

            for line in [
                _metric_line(cash_flow, 'Net cash flow from operating activities (original cumulative)', ['n_cashflow_act']),
                _metric_line(cash_flow, 'Net cash flow from investing activities (original cumulative)', ['n_cashflow_inv_act']),
                _metric_line(cash_flow, 'Net cash flow from financing activities (original cumulative)', ['n_cash_flows_fnc_act', 'n_cashflow_fin_act']),
                _metric_line(cash_flow, '期初现金及现金等价物余额', ['c_cash_equ_beg_period']),
                _metric_line(cash_flow, '期末现金及现金等价物余额', ['c_cash_equ_end_period']),
            ]:
                if line:
                    result_lines.append(line)

            matched_income = income_by_period.get(period)
            operating_cash = _stock_fundamentals_to_float(_pick_value(cash_flow, 'n_cashflow_act'))
            net_profit = None
            if matched_income:
                net_profit = _stock_fundamentals_to_float(_pick_value(matched_income, 'n_income_attr_p', 'n_income', 'net_profit'))

            single_quarter_operating_cash, _ = _derive_single_quarter_value(period, cash_flow_by_period, ['n_cashflow_act'])
            single_quarter_profit, _ = _derive_single_quarter_value(period, income_by_period, ['n_income_attr_p', 'n_income', 'net_profit'])

            if single_quarter_operating_cash is not None and single_quarter_profit not in (None, 0):
                result_lines.append(
                    f"- 单季度经营现金净额/归母净利润（推导）: {single_quarter_operating_cash / single_quarter_profit:.2f} 倍"
                )

            if operating_cash is not None and net_profit not in (None, 0):
                result_lines.append(f"- 报告期累计经营现金净额/归母净利润: {operating_cash / net_profit:.2f} 倍")

            result_lines.append("")

        return "\n".join(result_lines).strip()

    except Exception as exc:
        logger.error(f"❌ [cash flow tools] Execution failed: {exc}", exc_info=True)
        return f"获取 {ticker} 最近季度现金流量表失败: {exc}"


# === valuation.comparable_valuation ===
"""可比公司估值工具"""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from core.skill_runtime.data_access import (
    get_industry_peer_basic_info,
    get_latest_stock_price,
    get_stock_basic_info,
    summarize_industry_valuation,
)
from core.skill_runtime.standard_financial_apis import get_security_master
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _comparable_valuation_safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _calc_percentile(values: list[float], current: float) -> float | None:
    valid = [v for v in values if v is not None and v > 0]
    if not valid:
        return None
    return round(sum(1 for v in valid if v <= current) / len(valid) * 100, 1)


@tool
@register_tool(
    tool_id="get_comparable_company_valuation",
    name="可比公司估值",
    description="By comparing with companies in the same industry on PE, PB, and PS valuation indicators, the current stock valuation level is evaluated, and the valuation premium/discount and implied fair value are calculated.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "peer_comparison", "relative_valuation"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["relative_valuation", "peer_valuation_comparison"],
    when_to_use="Use it when you need to know the valuation level of a stock in the same industry and judge whether the valuation is too high or too low.",
    when_not_to_use="Not suitable for cross-industry comparisons; not suitable for companies with negative net profits (PE cannot be calculated, but PB/PS is still available).",
    returns="Returns a JSON string, including evaluation_comparison (PE/PB/PS comparison), overall_assessment and fair_value_estimate.",
    example="get_comparable_company_valuation(symbol='600519')",
    related_tools=["get_dcf_valuation", "get_stock_valuation_context"],
)
def get_comparable_company_valuation(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Calculate the valuation of comparable companies and evaluate the valuation level by comparing it with industry PE/PB/PS.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix), such as 600519,000001

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code (included in some cases)
            industry: Industry (only attached if No comparable company found error)

        In case of success, return dict, fields:
            symbol: Stock code
            name: Stock name
            industry: Industry
            peers_in_industry: Number of comparable companies in the industry
            valuation_comparison: Comparison of each indicator dict, the key is "pe" / "pb" / "ps" (Only available indicators)—
                stock: Current stock value of this indicator
                industry_median: Industry median
                industry_mean: Industry average
                premium_pct: Percent premium/discount to median
                percentile: The percentile of the current value in the industry sample
            overall_assessment: comprehensive assessment dict —
                average_premium_pct: weighted average premium percentage
                valuation_level: Valuation level:"On the high side" | "slightly higher" | "reasonable" | "slightly lower" | "On the low side"
                peers_available: Number of comparable companies
            fair_value_estimate: Implied fair value dict —
                based_on_pe: Fair price based on PE estimate (optional)
                based_on_pb: Fair price based on PB estimate (optional)
                based_on_ps: Fair price based on PS estimate (optional)
                current_price: current stock price
            data_quality: Data quality dict —
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        warnings: list[str] = []

        # 1. Get basic stock information
        basic_info = get_stock_basic_info(symbol)
        if not basic_info:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的基础信息", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        # 2. Obtain securities master data (including industry, name)
        master = get_security_master(symbol)
        industry = master.get("industry")
        name = master.get("name") or basic_info.get("name")

        if not industry:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的行业信息", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        # 3. Get the current valuation indicator
        pe_ttm = _comparable_valuation_safe_float(basic_info.get("pe_ttm") or basic_info.get("pe"))
        pb = _comparable_valuation_safe_float(basic_info.get("pb") or basic_info.get("pb_mrq"))
        ps_ttm = _comparable_valuation_safe_float(basic_info.get("ps_ttm") or basic_info.get("ps"))
        total_mv = _comparable_valuation_safe_float(basic_info.get("total_mv") or basic_info.get("market_cap") or basic_info.get("market_value"))
        current_price = get_latest_stock_price(symbol)

        # 4. Get industry valuation statistics
        industry_pe = summarize_industry_valuation(industry, metric="pe", exclude_symbol=symbol)
        industry_pb = summarize_industry_valuation(industry, metric="pb", exclude_symbol=symbol)
        industry_ps = summarize_industry_valuation(industry, metric="ps", exclude_symbol=symbol)

        peers_count = max(
            industry_pe.get("count", 0),
            industry_pb.get("count", 0),
            industry_ps.get("count", 0),
        )

        if peers_count == 0:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"行业「{industry}」中未找到可比公司数据",
                    "symbol": symbol,
                    "industry": industry,
                },
                ensure_ascii=False, indent=2, default=str,
            )

        # 5. Calculate premium/discount for each indicator
        valuation_comparison: dict = {}

        def _build_metric_comparison(
            metric_name: str,
            stock_value: float | None,
            industry_stats: dict,
        ) -> dict | None:
            if stock_value is None or stock_value <= 0:
                return None
            median_val = industry_stats.get("median")
            mean_val = industry_stats.get("average")
            count = industry_stats.get("count", 0)
            if median_val is None or median_val <= 0:
                return None
            premium_pct = round((stock_value / median_val - 1) * 100, 1)

            # Get all peer sample values to calculate percentiles
            samples = industry_stats.get("samples") or []
            values = [s.get(metric_name) for s in samples if s.get(metric_name) is not None]
            # Added getting more samples from get_industry_peer_basic_info
            peers = get_industry_peer_basic_info(industry, exclude_symbol=symbol, limit=200)
            field_map = {"pe": "pe_ttm", "pb": "pb", "ps": "ps_ttm"}
            field = field_map.get(metric_name, metric_name)
            for p in peers:
                v = _comparable_valuation_safe_float(p.get(field) or p.get(field.replace("_ttm", "")))
                if v is not None and v > 0:
                    values.append(v)

            percentile = _calc_percentile(values, stock_value) if values else None

            return {
                "stock": stock_value,
                "industry_median": median_val,
                "industry_mean": mean_val,
                "premium_pct": premium_pct,
                "percentile": percentile,
            }

        pe_comp = _build_metric_comparison("pe", pe_ttm, industry_pe)
        pb_comp = _build_metric_comparison("pb", pb, industry_pb)
        ps_comp = _build_metric_comparison("ps", ps_ttm, industry_ps)

        if pe_comp:
            valuation_comparison["pe"] = pe_comp
        if pb_comp:
            valuation_comparison["pb"] = pb_comp
        if ps_comp:
            valuation_comparison["ps"] = ps_comp

        if not valuation_comparison:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"无法计算 {symbol} 的有效估值对比（估值指标或行业数据不足）",
                    "symbol": symbol,
                },
                ensure_ascii=False, indent=2, default=str,
            )

        # 6. comprehensive assessment
        premiums = [
            comp["premium_pct"]
            for comp in valuation_comparison.values()
            if isinstance(comp, dict) and comp.get("premium_pct") is not None
        ]

        if premiums:
            average_premium = round(sum(premiums) / len(premiums), 1)
        else:
            average_premium = 0.0

        if average_premium > 50:
            valuation_level = "偏高"
        elif average_premium > 20:
            valuation_level = "略高"
        elif average_premium < -30:
            valuation_level = "偏低"
        elif average_premium < -10:
            valuation_level = "略低"
        else:
            valuation_level = "合理"

        # 7. Implied fair value estimate
        fair_value_estimate: dict = {}
        if current_price is not None and current_price > 0 and average_premium != -100:
            if pe_comp and pe_comp.get("premium_pct") is not None:
                fair_pe = current_price / (1 + pe_comp["premium_pct"] / 100)
                fair_value_estimate["based_on_pe"] = round(fair_pe, 2)
            if pb_comp and pb_comp.get("premium_pct") is not None:
                fair_pb = current_price / (1 + pb_comp["premium_pct"] / 100)
                fair_value_estimate["based_on_pb"] = round(fair_pb, 2)
            if ps_comp and ps_comp.get("premium_pct") is not None:
                fair_ps = current_price / (1 + ps_comp["premium_pct"] / 100)
                fair_value_estimate["based_on_ps"] = round(fair_ps, 2)
            fair_value_estimate["current_price"] = current_price

        # Label data quality
        if peers_count < 10:
            warnings.append(f"行业可比公司仅 {peers_count} 家，统计参考价值有限")
        if pe_comp is None:
            warnings.append("PE Not available (net profit may be negative), PE comparison skipped")
        if pb_comp is None:
            warnings.append("PB Not available, PB comparison skipped")
        if ps_comp is None:
            warnings.append("PS Not available, PS comparison skipped")

        warnings.append("基于当前行业估值分布")

        payload = {
            "symbol": symbol,
            "name": name,
            "industry": industry,
            "peers_in_industry": peers_count,
            "valuation_comparison": valuation_comparison,
            "overall_assessment": {
                "average_premium_pct": average_premium,
                "valuation_level": valuation_level,
                "peers_available": peers_count,
            },
            "fair_value_estimate": fair_value_estimate,
            "data_quality": {
                "warnings": warnings,
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("可比公司估值失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = ["get_comparable_company_valuation"]

# === valuation.dcf_valuation ===
"""DCF Two-stage valuation model tool"""

import json
import logging
from typing import Annotated, Optional

import numpy as np
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="get_dcf_valuation",
    name="DCF 两阶段估值",
    description="Absolute valuation of A-shares based on the two-stage DCF model, returning structured results such as intrinsic value, margin of safety, cash flow at each stage, WACC, terminal value, etc., suitable for mature companies",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["dcf", "valuation", "absolute_valuation", "discounted_cashflow", "two_stage_dcf"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["absolute_valuation", "intrinsic_value_estimation"],
    when_to_use="Use it when you need to perform absolute valuation, estimate intrinsic value, and calculate margin of safety. Suitable for mature businesses with positive free cash flow.",
    when_not_to_use="Not suitable for businesses with persistently negative FCF (will return an error). Not suitable for financial companies (different asset structures). Not suitable for relative valuation scenarios (PE/PB comparison tool should be used).",
    returns="Returns a JSON string containing valuation parameters, scenario analysis, sensitivity matrix, and intrinsic value per share.",
    example="get_dcf_valuation(symbol='600519')",
    related_tools=["get_wacc_calculation", "get_dcf_three_stage_valuation", "get_fcff_fcfe_calculation", "get_capm_cost_of_equity"],
)
def get_dcf_valuation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    growth_rate: Annotated[Optional[float], "Annualized growth rate during the forecast period, default None, automatically estimated from historical data"] = None,
    wacc: Annotated[Optional[float], "Discount rate (weighted average cost of capital), default None automatically calculated"] = None,
    terminal_growth_rate: Annotated[float, "Perpetual growth rate, default 2.5%"] = 2.5,
    forecast_years: Annotated[int, "Number of years in the forecast period, default 5"] = 5,
    base_fcf: Annotated[Optional[float], "Base period free cash flow coverage value, default None Use the latest annual report data"] = None,
) -> str:
    """DCF two-stage valuation model

    Args:
        symbol: A stock stock code, such as 600519
        growth_rate: Annualized growth rate during the forecast period (in decimal form, such as 0.15 means 15%), default None. Automatically estimated from historical revenue data and clamped to [0.03, 0.25]
        wacc: Discount rate (weighted average cost of capital, decimal form), default None Automatically calculated and clamped to [0.05, 0.20]
        terminal_growth_rate: Perpetual growth rate, default 2.5 (>1 regarded as a percentage and automatically divided by 100)
        forecast_years: Number of years in the forecast period, default 5, automatically clamped to [3, 10]
        base_fcf: Free cash flow coverage value in the base period, default None, use the free_cashflow of the latest annual report; if ≤0 Return to operating_cashflow,net_profit×0.7

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code

        In case of success, return dict, fields:
            symbol: Stock code
            method: "two_stage_dcf"
            parameters: Valuation parameters dict —
                growth_rate: Actual growth rate used (decimal)
                wacc: Actual discount rate used (decimal)
                terminal_growth_rate: Perpetual growth rate (decimal)
                forecast_years: Actual forecast years
            base_year: Base period information dict —
                year: base year
                free_cashflow: Base period free cash flow
            valuation: Valuation results dict —
                enterprise_value: enterprise value
                equity_value: equity value
                per_share_value: intrinsic value per share
                current_price: current stock price
                upside_pct: Percent upside relative to current price
                net_debt_adjustment: Net debt adjustment
            scenarios: Scenario analysis dict —
                base: Baseline scenario dict — per_share_value, upside_pct
                bull: optimistic scenario dict — per_share_value, upside_pct
                bear: pessimistic scenario dict — per_share_value, upside_pct
            sensitivity: sensitivity analysis dict —
                wacc_range: WACC list of values (3 values)
                growth_range: Growth rate value list (3 values)
                matrix: per share value matrix [[value, value, value], ...]
            data_quality: Data quality dict —
                years_available: Available annual report periods
                base_fcf_source: FCF Source:"parameter_override" | "free_cashflow" | "operating_cashflow" | "net_profit_estimated"
                growth_source: Source of growth rate:"parameter_override" | "revenue_historical_mean"
                wacc_source: WACC Source:"parameter_override" | "auto_computed"
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.standard_financial_apis import get_historical_financial_annual_series

        series = get_historical_financial_annual_series(symbol, years=5)
        records = series.get("records") or []

        warnings: list = []
        if len(records) < 2:
            return json.dumps(
                {"status": "error", "message": f"可用年报数据不足（仅 {len(records)} 期），无法进行 DCF 估值", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        # 1. Determine the base period FCF
        latest = records[0]
        cf_fcf = base_fcf if base_fcf is not None else latest.get("free_cashflow")
        cf_ocf = latest.get("operating_cashflow")
        cf_np = latest.get("net_profit")

        fcf_source = "parameter_override" if base_fcf is not None else "free_cashflow"
        resolved_fcf = cf_fcf

        if resolved_fcf is None or resolved_fcf <= 0:
            if cf_ocf is not None and cf_ocf > 0:
                resolved_fcf = cf_ocf
                fcf_source = "operating_cashflow"
            elif cf_np is not None and cf_np > 0:
                resolved_fcf = cf_np * 0.7
                fcf_source = "net_profit_estimated"
            else:
                return json.dumps(
                    {
                        "status": "error",
                        "message": (
                            f"The effective base period free cash flow cannot be determined."
                            f"free_cashflow={cf_fcf}, operating_cashflow={cf_ocf}, net_profit={cf_np}"
                        ),
                        "symbol": symbol,
                    },
                    ensure_ascii=False, indent=2, default=str,
                )

        # 2. Determine the growth rate
        if growth_rate is not None:
            resolved_growth = growth_rate
            growth_source = "parameter_override"
        else:
            revenue_values = [r.get("revenue") for r in records if r.get("revenue") is not None and r.get("revenue") > 0]
            if len(revenue_values) >= 2:
                annual_growth_rates = []
                for i in range(len(revenue_values) - 1):
                    prev = revenue_values[i + 1]
                    curr = revenue_values[i]
                    if prev and prev > 0:
                        annual_growth_rates.append((curr - prev) / prev)
                avg_growth = np.mean(annual_growth_rates) if annual_growth_rates else 0.03
            else:
                avg_growth = 0.03
            resolved_growth = max(0.03, min(0.25, avg_growth))
            growth_source = "revenue_historical_mean"
            if avg_growth < 0.03:
                warnings.append(f"历史营收增长率偏低 ({avg_growth:.1%})，已夹钳至下限 3%。")
            if avg_growth > 0.25:
                warnings.append(f"历史营收增长率偏高 ({avg_growth:.1%})，已夹钳至上限 25%。")

        # 3. Calculate WACC
        if wacc is not None:
            resolved_wacc = wacc
            wacc_source = "parameter_override"
        else:
            cost_of_equity = 0.035 + 1.0 * 0.06  # risk-free + beta * ERP
            cost_of_debt = 0.04
            debt_to_assets = latest.get("debt_to_assets")
            if debt_to_assets is not None:
                debt_weight = debt_to_assets / 100.0 if debt_to_assets > 1 else debt_to_assets
            else:
                total_liab = latest.get("total_liab")
                total_assets = latest.get("total_assets")
                if total_liab is not None and total_assets is not None and total_assets > 0:
                    debt_weight = total_liab / total_assets
                else:
                    debt_weight = 0.4
                    warnings.append("The debt ratio data is missing, and the default debt weight of 40% is used.")
            equity_weight = 1.0 - debt_weight
            resolved_wacc = equity_weight * cost_of_equity + debt_weight * cost_of_debt * (1 - 0.25)
            resolved_wacc = max(0.05, min(0.20, resolved_wacc))
            wacc_source = "auto_computed"

        tgr = terminal_growth_rate / 100.0 if terminal_growth_rate > 1 else terminal_growth_rate
        n_forecast = max(3, min(10, int(forecast_years)))

        # 4. DCF Calculate
        projected_fcfs = []
        pv_fcfs = []
        for yr in range(1, n_forecast + 1):
            pfcf = resolved_fcf * (1 + resolved_growth) ** yr
            pv = pfcf / (1 + resolved_wacc) ** yr
            projected_fcfs.append(pfcf)
            pv_fcfs.append(pv)

        terminal_value = projected_fcfs[-1] * (1 + tgr) / (resolved_wacc - tgr)
        pv_terminal = terminal_value / (1 + resolved_wacc) ** n_forecast
        enterprise_value = sum(pv_fcfs) + pv_terminal

        # 5. net debt adjustment
        total_liab = latest.get("total_liab") or 0
        net_debt_adjustment = total_liab
        equity_value = enterprise_value - net_debt_adjustment

        # 6. Get share capital and current price
        from core.skill_runtime.data_access import get_stock_basic_info, get_latest_stock_price

        basic_info = get_stock_basic_info(symbol) or {}
        current_price = get_latest_stock_price(symbol)

        # ── unit alignment ──
        # equity_value / free_cashflow / total_liab The unit of financial reporting caliber is "yuan",
        # However, the unit of share capital total_share/float_share in the basic information table is "10,000 shares".
        # The unit of market capitalization total_mv/circ_mv is "100 million yuan".
        # If you directly use "10,000 shares" as the divisor, per_share_value will be magnified 1e4 times
        #  (For example, Maotai will calculate 12.62 million yuan/share, but the actual price is about 1,264 yuan/share).
        # Here, equity capital is uniformly converted into "shares".
        raw_shares = (
            basic_info.get("total_shares")
            or basic_info.get("total_share")   # Unit: 10,000 shares
            or basic_info.get("float_shares")
            or basic_info.get("float_share")   # Unit: 10,000 shares
        )
        shares = None
        if raw_shares is not None and raw_shares > 0:
            # total_share/float_share The unit is 10,000 shares → ×1e4 Convert to shares
            shares = float(raw_shares) * 1e4
        else:
            # Bottom line: Use market capitalization/current price to calculate the number of shares
            # total_mv/circ_mv The unit is 100 million yuan → ×1e8 Convert to yuan
            raw_mv = basic_info.get("total_mv") or basic_info.get("circ_mv")
            market_cap = basic_info.get("market_cap") or basic_info.get("market_value")
            if raw_mv and raw_mv > 0:
                market_cap = float(raw_mv) * 1e8  # billion → Yuan
            if market_cap and current_price and current_price > 0:
                shares = market_cap / current_price
            else:
                shares = 1.256e9  # Default is about 1.25 billion shares
                warnings.append("Total share capital is not available and the default estimate of approximately 1.25 billion shares is used.")

        per_share_value = equity_value / shares if shares and shares > 0 else None
        upside_pct = ((per_share_value - current_price) / current_price * 100) if (per_share_value and current_price and current_price > 0) else None

        # 7. Scenario analysis
        bear_growth = resolved_growth * 0.7
        bull_growth = resolved_growth * 1.3
        bear_wacc = resolved_wacc * 1.3
        bull_wacc = resolved_wacc * 0.7

        def _scenario(g: float, w: float) -> dict:
            pf = [resolved_fcf * (1 + g) ** y for y in range(1, n_forecast + 1)]
            tv = pf[-1] * (1 + tgr) / (w - tgr)
            ev = sum(pf[y] / (1 + w) ** (y + 1) for y in range(n_forecast)) + tv / (1 + w) ** n_forecast
            eq = ev - net_debt_adjustment
            psv = eq / shares if shares and shares > 0 else None
            up = ((psv - current_price) / current_price * 100) if (psv and current_price and current_price > 0) else None
            return {"per_share_value": psv, "upside_pct": up}

        scenarios = {
            "base": {"per_share_value": per_share_value, "upside_pct": upside_pct},
            "bull": _scenario(bull_growth, bull_wacc),
            "bear": _scenario(bear_growth, bear_wacc),
        }

        # 8. sensitivity analysis
        wacc_range = [resolved_wacc - 0.01, resolved_wacc, resolved_wacc + 0.01]
        growth_range = [resolved_growth - 0.01, resolved_growth, resolved_growth + 0.01]
        matrix = []
        for w in wacc_range:
            row = []
            for g in growth_range:
                s = _scenario(g, w)
                row.append(s.get("per_share_value"))
            matrix.append(row)

        payload = {
            "symbol": symbol,
            "method": "two_stage_dcf",
            "parameters": {
                "growth_rate": round(resolved_growth, 4),
                "wacc": round(resolved_wacc, 4),
                "terminal_growth_rate": round(tgr, 4),
                "forecast_years": n_forecast,
            },
            "base_year": {
                "year": latest.get("year"),
                "free_cashflow": resolved_fcf,
            },
            "valuation": {
                "enterprise_value": round(enterprise_value, 2),
                "equity_value": round(equity_value, 2),
                "per_share_value": round(per_share_value, 2) if per_share_value is not None else None,
                "current_price": current_price,
                "upside_pct": round(upside_pct, 2) if upside_pct is not None else None,
                "net_debt_adjustment": round(net_debt_adjustment, 2),
            },
            "scenarios": scenarios,
            "sensitivity": {
                "wacc_range": [round(w, 4) for w in wacc_range],
                "growth_range": [round(g, 4) for g in growth_range],
                "matrix": [[round(v, 2) if v is not None else None for v in row] for row in matrix],
            },
            "data_quality": {
                "years_available": len(records),
                "base_fcf_source": fcf_source,
                "growth_source": growth_source,
                "wacc_source": wacc_source,
                "warnings": warnings,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("DCF估值失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_dcf_valuation"]

# === valuation.extended_valuation ===
"""Expanded set of valuation model tools: DCF three-stage, DDM, residual income, EVA, FCFF/FCFE, PEG, Graham, CAPM, growth quality adjusted valuation"""

import json
import logging
from statistics import mean, pstdev
from typing import Annotated, Optional

import numpy as np
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _extended_valuation_safe_div(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _extended_valuation_cagr(latest, earliest, periods):
    if latest is None or earliest is None or earliest <= 0 or latest <= 0 or periods <= 0:
        return None
    return (latest / earliest) ** (1 / periods) - 1


def _resolve_shares(basic_info: dict, current_price=None, warnings: Optional[list] = None):
    """Unified analysis of the total share capital returns the value in units of shares .

    In the basic information table:
      - total_share / float_share The unit is 10,000 shares → Need ×1e4 Convert to shares
      - total_mv / circ_mv The unit is billion yuan → Need ×1e8 Convert to yuan
    Financial report caliber (equity_value/net_profit/total_equity, etc.) unit is yuan ,
    If you directly use 10,000 shares as the divisor, the result per share will be magnified 1e4 times (for example, Maotai will calculate tens of millions per share).
    """
    raw_shares = (
        basic_info.get("total_shares")
        or basic_info.get("total_share")   # 10,000 shares
        or basic_info.get("float_shares")
        or basic_info.get("float_share")   # 10,000 shares
    )
    if raw_shares is not None and raw_shares > 0:
        return float(raw_shares) * 1e4  # 10,000 shares → shares

    # Bottom line: market value / current price calculation
    raw_mv = basic_info.get("total_mv") or basic_info.get("circ_mv")
    market_cap = basic_info.get("market_cap") or basic_info.get("market_value")
    if raw_mv and raw_mv > 0:
        market_cap = float(raw_mv) * 1e8  # billion → Yuan
    if market_cap and current_price and current_price > 0:
        return market_cap / current_price

    if warnings is not None:
        warnings.append("Total share capital is not available and the default estimate of approximately 1.25 billion shares is used.")
    return 1.256e9


# ─────────────────────────────────────────────────────────────
# Tool 1: DCF Three-stage valuation
# ─────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_dcf_three_stage_valuation",
    name="DCF 三阶段估值",
    description="Absolute valuation of A-shares based on the three-stage DCF model, returning three-stage cash flow forecast, discounted value, intrinsic value, safety margin and sensitivity analysis, suitable for high-growth companies",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "dcf", "absolute_valuation", "three_stage_dcf", "discounted_cashflow"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["absolute_valuation", "intrinsic_value_estimation", "three_stage_dcf"],
    when_to_use="It is used when three-stage DCF absolute valuation is required to estimate the intrinsic value of high-growth companies. Suitable for companies with clear growth slowdown after a period of high growth.",
    when_not_to_use="Not suitable for businesses with consistently negative FCF. Not suitable for financial companies. Not suitable for simple and mature enterprises (two-stage DCF is sufficient).",
    returns="Returns a JSON string containing three-stage parameters, scenario analysis, sensitivity matrix, and intrinsic value per share.",
    example="get_dcf_three_stage_valuation(symbol='600519')",
    related_tools=["get_dcf_valuation", "get_wacc_calculation"],
)
def get_dcf_three_stage_valuation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    growth_rate: Annotated[Optional[float], "Annualized growth rate during the forecast period, default None, automatically estimated from historical data"] = None,
    wacc: Annotated[Optional[float], "Discount rate (weighted average cost of capital), default None automatically calculated"] = None,
    terminal_growth_rate: Annotated[float, "Perpetual growth rate, default 2.5%"] = 2.5,
    high_growth_years: Annotated[int, "Number of years of high growth period, default 5"] = 5,
    transition_years: Annotated[int, "Number of years of transition period, default 3"] = 3,
    high_growth_rate: Annotated[Optional[float], "Growth rate in high growth period, default used is None growth_rate"] = None,
    transition_end_rate: Annotated[float, "The growth rate at the end of the transition period (that is, the growth rate before sustainability), default 5%"] = 0.05,
    base_fcf: Annotated[Optional[float], "Base period free cash flow coverage value, default None Use the latest annual report data"] = None,
) -> str:
    """DCF Three-stage valuation model: high growth → Transition (linear decrease) → Sustainable

    Args:
        symbol: A stock stock code, such as 600519
        growth_rate: Annualized growth rate during the forecast period (in decimal form), default None. Automatically estimated from historical revenue data and clamped to [0.03, 0.25]
        wacc: Discount rate (in decimal form), default None Automatically calculated and clamped to [0.05, 0.20]
        terminal_growth_rate: Perpetual growth rate, default 2.5 (>1 regarded as a percentage and automatically divided by 100)
        high_growth_years: Number of years of high growth period, default 5, automatic clamp to [1, 15]
        transition_years: Number of years of transition period, default 3, automatic clamp to [1, 10]
        high_growth_rate: Growth rate in the high growth period (in decimal form), used when None is used by default growth_rate
        transition_end_rate: The growth rate at the end of the transition period (that is, the growth rate before sustainability), default 0.05
        base_fcf: Base period free cash flow coverage value, default None, use the latest annual report data; if ≤0 Return to operating_cashflow,net_profit×0.7

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code

        In case of success, return dict, fields:
            symbol: Stock code
            method: "three stages DCF"
            stages: Three stage parameters dict —
                high_growth_years: Years of high growth period
                transition_years: Number of years of transition period
                perpetual_growth_rate: Perpetual growth rate (decimal)
            parameters: Valuation parameters dict —
                high_growth_rate: Growth rate during high growth period (decimal)
                transition_end_rate: Growth rate at the end of the transition period (decimal)
                terminal_growth_rate: Perpetual growth rate (decimal)
                wacc: Discount rate (decimal)
            base_year: Base period information dict —
                year: base year
                free_cashflow: Base period free cash flow
            valuation: Valuation results dict —
                pv_stage1_high_growth: Total present value of high growth period
                pv_stage2_transition: Total present value during transition period
                pv_terminal: Perpetual present value
                enterprise_value: enterprise value
                equity_value: equity value
                per_share_value: intrinsic value per share
                current_price: current stock price
                upside_pct: Percent upside relative to current price
                net_debt_adjustment: Net debt adjustment
            scenarios: Scenario analysis dict —
                base: Baseline scenario dict — per_share_value, upside_pct
                bull: optimistic scenario dict — per_share_value, upside_pct
                bear: pessimistic scenario dict — per_share_value, upside_pct
            sensitivity: sensitivity analysis dict —
                wacc_range: WACC list of values (3 values)
                growth_range: High growth rate value list (3 values)
                matrix: per share value matrix [[value, value, value], ...]
            data_quality: Data quality dict —
                years_available: Available annual report periods
                base_fcf_source: FCF Source:"parameter_override" | "free_cashflow" | "operating_cashflow" | "net_profit_estimated"
                growth_source: Source of growth rate:"parameter_override" | "revenue_historical_mean"
                wacc_source: WACC Source:"parameter_override" | "auto_computed"
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.standard_financial_apis import get_historical_financial_annual_series

        series = get_historical_financial_annual_series(symbol, years=5)
        records = series.get("records") or []

        warnings: list = []
        if len(records) < 2:
            return json.dumps(
                {"status": "error", "message": f"可用年报数据不足（仅 {len(records)} 期），无法进行 DCF 三阶段估值", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        latest = records[0]
        cf_fcf = base_fcf if base_fcf is not None else latest.get("free_cashflow")
        cf_ocf = latest.get("operating_cashflow")
        cf_np = latest.get("net_profit")

        fcf_source = "parameter_override" if base_fcf is not None else "free_cashflow"
        resolved_fcf = cf_fcf

        if resolved_fcf is None or resolved_fcf <= 0:
            if cf_ocf is not None and cf_ocf > 0:
                resolved_fcf = cf_ocf
                fcf_source = "operating_cashflow"
            elif cf_np is not None and cf_np > 0:
                resolved_fcf = cf_np * 0.7
                fcf_source = "net_profit_estimated"
            else:
                return json.dumps(
                    {
                        "status": "error",
                        "message": (
                            f"The effective base period free cash flow cannot be determined."
                            f"free_cashflow={cf_fcf}, operating_cashflow={cf_ocf}, net_profit={cf_np}"
                        ),
                        "symbol": symbol,
                    },
                    ensure_ascii=False, indent=2, default=str,
                )

        # Determine the growth rate
        if growth_rate is not None:
            resolved_growth = growth_rate
            growth_source = "parameter_override"
        else:
            revenue_values = [r.get("revenue") for r in records if r.get("revenue") is not None and r.get("revenue") > 0]
            if len(revenue_values) >= 2:
                annual_growth_rates = []
                for i in range(len(revenue_values) - 1):
                    prev = revenue_values[i + 1]
                    curr = revenue_values[i]
                    if prev and prev > 0:
                        annual_growth_rates.append((curr - prev) / prev)
                avg_growth = np.mean(annual_growth_rates) if annual_growth_rates else 0.03
            else:
                avg_growth = 0.03
            resolved_growth = max(0.03, min(0.25, avg_growth))
            growth_source = "revenue_historical_mean"
            if avg_growth < 0.03:
                warnings.append(f"历史营收增长率偏低 ({avg_growth:.1%})，已夹钳至下限 3%。")
            if avg_growth > 0.25:
                warnings.append(f"历史营收增长率偏高 ({avg_growth:.1%})，已夹钳至上限 25%。")

        resolved_high_growth = high_growth_rate if high_growth_rate is not None else resolved_growth

        # Calculate WACC
        if wacc is not None:
            resolved_wacc = wacc
            wacc_source = "parameter_override"
        else:
            cost_of_equity = 0.035 + 1.0 * 0.06
            cost_of_debt = 0.04
            debt_to_assets = latest.get("debt_to_assets")
            if debt_to_assets is not None:
                debt_weight = debt_to_assets / 100.0 if debt_to_assets > 1 else debt_to_assets
            else:
                total_liab = latest.get("total_liab")
                total_assets = latest.get("total_assets")
                if total_liab is not None and total_assets is not None and total_assets > 0:
                    debt_weight = total_liab / total_assets
                else:
                    debt_weight = 0.4
                    warnings.append("The debt ratio data is missing, and the default debt weight of 40% is used.")
            equity_weight = 1.0 - debt_weight
            resolved_wacc = equity_weight * cost_of_equity + debt_weight * cost_of_debt * (1 - 0.25)
            resolved_wacc = max(0.05, min(0.20, resolved_wacc))
            wacc_source = "auto_computed"

        tgr = terminal_growth_rate / 100.0 if terminal_growth_rate > 1 else terminal_growth_rate
        n_high = max(1, min(15, int(high_growth_years)))
        n_trans = max(1, min(10, int(transition_years)))
        total_years = n_high + n_trans

        # Stage 1: high growth period
        stage1_fcfs = []
        for yr in range(1, n_high + 1):
            fcf = resolved_fcf * (1 + resolved_high_growth) ** yr
            stage1_fcfs.append(fcf)

        # Stage 2: Transition period (linear decrease)
        last_high_fcf = stage1_fcfs[-1] if stage1_fcfs else resolved_fcf
        stage2_fcfs = []
        for yr in range(1, n_trans + 1):
            decay = yr / n_trans
            g = resolved_high_growth * (1 - decay) + transition_end_rate * decay
            fcf = last_high_fcf * (1 + g)
            stage2_fcfs.append(fcf)
            if yr == n_trans:
                last_trans_fcf = fcf

        last_trans_fcf = last_trans_fcf if stage2_fcfs else last_high_fcf

        # Stage 3: sustainable growth
        terminal_value = last_trans_fcf * (1 + tgr) / (resolved_wacc - tgr)

        # Discounted to present value
        pv_stage1 = sum(fcf / (1 + resolved_wacc) ** yr for yr, fcf in enumerate(stage1_fcfs, 1))
        pv_stage2 = sum(fcf / (1 + resolved_wacc) ** (n_high + yr) for yr, fcf in enumerate(stage2_fcfs, 1))
        pv_terminal = terminal_value / (1 + resolved_wacc) ** total_years
        enterprise_value = pv_stage1 + pv_stage2 + pv_terminal

        # net debt adjustment
        net_debt = latest.get("total_liab") or 0
        equity_value = enterprise_value - net_debt

        # Share capital and current price
        from core.skill_runtime.data_access import get_stock_basic_info, get_latest_stock_price

        basic_info = get_stock_basic_info(symbol) or {}
        current_price = get_latest_stock_price(symbol)

        shares = _resolve_shares(basic_info, current_price, warnings)

        per_share_value = equity_value / shares if shares and shares > 0 else None
        upside_pct = ((per_share_value - current_price) / current_price * 100) if (per_share_value and current_price and current_price > 0) else None

        # Scenario analysis
        def _scenario(hg: float, tr: float, w: float) -> dict:
            s1 = [resolved_fcf * (1 + hg) ** y for y in range(1, n_high + 1)]
            ls1 = s1[-1] if s1 else resolved_fcf
            s2 = []
            for y in range(1, n_trans + 1):
                d = y / n_trans
                g = hg * (1 - d) + tr * d
                s2.append(ls1 * (1 + g))
            lt = s2[-1] if s2 else ls1
            tv = lt * (1 + tgr) / (w - tgr)
            ev_ = sum(s1[y] / (1 + w) ** (y + 1) for y in range(n_high))
            ev_ += sum(s2[y] / (1 + w) ** (n_high + y + 1) for y in range(n_trans))
            ev_ += tv / (1 + w) ** total_years
            eq = ev_ - net_debt
            psv = eq / shares if shares and shares > 0 else None
            up = ((psv - current_price) / current_price * 100) if (psv and current_price and current_price > 0) else None
            return {"per_share_value": psv, "upside_pct": up}

        scenarios = {
            "base": {"per_share_value": per_share_value, "upside_pct": upside_pct},
            "bull": _scenario(resolved_high_growth * 1.3, transition_end_rate * 1.3, resolved_wacc * 0.7),
            "bear": _scenario(resolved_high_growth * 0.7, transition_end_rate * 0.7, resolved_wacc * 1.3),
        }

        # sensitivity matrix
        wacc_range = [resolved_wacc - 0.01, resolved_wacc, resolved_wacc + 0.01]
        growth_range = [resolved_high_growth - 0.01, resolved_high_growth, resolved_high_growth + 0.01]
        matrix = []
        for w in wacc_range:
            row = []
            for g in growth_range:
                s = _scenario(g, transition_end_rate, w)
                row.append(s.get("per_share_value"))
            matrix.append(row)

        payload = {
            "symbol": symbol,
            "method": "三阶段DCF",
            "stages": {
                "high_growth_years": n_high,
                "transition_years": n_trans,
                "perpetual_growth_rate": round(tgr, 4),
            },
            "parameters": {
                "high_growth_rate": round(resolved_high_growth, 4),
                "transition_end_rate": round(transition_end_rate, 4),
                "terminal_growth_rate": round(tgr, 4),
                "wacc": round(resolved_wacc, 4),
            },
            "base_year": {
                "year": latest.get("year"),
                "free_cashflow": resolved_fcf,
            },
            "valuation": {
                "pv_stage1_high_growth": round(pv_stage1, 2),
                "pv_stage2_transition": round(pv_stage2, 2),
                "pv_terminal": round(pv_terminal, 2),
                "enterprise_value": round(enterprise_value, 2),
                "equity_value": round(equity_value, 2),
                "per_share_value": round(per_share_value, 2) if per_share_value is not None else None,
                "current_price": current_price,
                "upside_pct": round(upside_pct, 2) if upside_pct is not None else None,
                "net_debt_adjustment": round(net_debt, 2),
            },
            "scenarios": scenarios,
            "sensitivity": {
                "wacc_range": [round(w, 4) for w in wacc_range],
                "growth_range": [round(g, 4) for g in growth_range],
                "matrix": [[round(v, 2) if v is not None else None for v in row] for row in matrix],
            },
            "data_quality": {
                "years_available": len(records),
                "base_fcf_source": fcf_source,
                "growth_source": growth_source,
                "wacc_source": wacc_source,
                "warnings": warnings,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("DCF Three-stage valuation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ─────────────────────────────────────────────────────────────
# Tool 2: DDM dividend discount model
# ─────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_ddm_valuation",
    name="股利贴现模型",
    description="A-share dividend discount valuation based on Gordon Growth model, returns expected dividends, discount rate, dividend growth rate, intrinsic value and safety margin, suitable for stable dividend-paying companies",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "ddm", "dividend_discount", "gordon_growth"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["dividend_valuation", "mature_dividend_stock_valuation"],
    when_to_use="It is suitable for the valuation of mature companies that pay stable dividends, and determines the rationality of stock prices relative to the discounted value of dividends.",
    when_not_to_use="Not suitable for companies that do not pay dividends or have unstable dividends (no_dividend_data will be returned). Not suitable for high growth unprofitable enterprises.",
    returns="Returns a JSON string containing current dividend, growth rate, required rate of return, intrinsic value and upside.",
    example="get_ddm_valuation(symbol='600519')",
    related_tools=["get_dcf_valuation", "get_shareholder_return_metrics"],
)
def get_ddm_valuation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    growth_rate: Annotated[float, "Perpetual growth rate of dividends, default 5%"] = 0.05,
    required_return: Annotated[float, "Required rate of return (discount rate), default 8%"] = 0.08,
) -> str:
    """Dividend Discount Model (Gordon Growth Model)

    Args:
        symbol: A stock stock code, such as 600519
        growth_rate: Perpetual growth rate of dividends (in decimal form), default 0.05; if ≥ required_return, automatically adjust to required_return + 0.03
        required_return: Required rate of return/discount rate (decimal form), default 0.08

    Returns:
        str: JSON A string containing the following possible structures——

        If there is no dividend data, return dict, fields:
            status: "no_dividend_data"
            symbol: Stock code
            message: Description information

        Error/Exception cases return dict, fields:
            status: "error"
            message: Error description

        In case of success, return dict, fields:
            symbol: Stock code
            method: "gordon_growth_model"
            parameters: parameters dict —
                current_dividend_per_share: Current dividend per share
                expected_dividend_d1: Expected next dividend D1
                growth_rate: Perpetual growth rate (decimal)
                required_return: Required rate of return (decimal)
            valuation: Valuation results dict —
                intrinsic_value: intrinsic value
                current_price: current stock price
                upside_pct: Percent upside relative to current price
            dividend_history: List of dividend records over the years (up to 5 records)
            data_quality: Data quality dict —
                dividend_records_count: Number of dividend records
                dividend_positive_years: Number of positive dividend years
                latest_dividend_yield: Latest dividend yield
                warnings: Warning message list
    """
    try:
        from core.skill_runtime.data_access import get_latest_stock_price
        from core.skill_runtime.standard_financial_apis import get_shareholder_return_metrics

        # Get dividend data
        div_metrics = get_shareholder_return_metrics(symbol, years=5)
        records = div_metrics.get("records") or []
        annual = div_metrics.get("annual") or []
        metrics = div_metrics.get("metrics") or {}
        latest_cash = metrics.get("latest_cash_dividend_per_share")
        current_price = div_metrics.get("current_price") or get_latest_stock_price(symbol)

        if latest_cash is None or latest_cash <= 0:
            return json.dumps(
                {
                    "status": "no_dividend_data",
                    "symbol": symbol,
                    "message": "No valid cash dividend data was found, and dividend discount valuation cannot be performed. The stock may not pay a dividend or the dividend data may be out of sync.",
                },
                ensure_ascii=False, indent=2, default=str,
            )

        # Gordon Growth Model: P = D1 / (r - g)
        d1 = latest_cash * (1 + growth_rate)

        if required_return <= growth_rate:
            required_return = growth_rate + 0.03

        intrinsic_value = d1 / (required_return - growth_rate)
        upside_pct = ((intrinsic_value - current_price) / current_price * 100) if (current_price and current_price > 0) else None

        payload = {
            "symbol": symbol,
            "method": "gordon_growth_model",
            "parameters": {
                "current_dividend_per_share": latest_cash,
                "expected_dividend_d1": round(d1, 4),
                "growth_rate": round(growth_rate, 4),
                "required_return": round(required_return, 4),
            },
            "valuation": {
                "intrinsic_value": round(intrinsic_value, 2),
                "current_price": current_price,
                "upside_pct": round(upside_pct, 2) if upside_pct is not None else None,
            },
            "dividend_history": annual[:5] if annual else [],
            "data_quality": {
                "dividend_records_count": len(records),
                "dividend_positive_years": metrics.get("dividend_positive_years"),
                "latest_dividend_yield": metrics.get("latest_dividend_yield"),
                "warnings": div_metrics.get("warnings") or [],
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("DDM估值失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ─────────────────────────────────────────────────────────────
# Tool 3: residual income valuation
# ─────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_residual_income_valuation",
    name="剩余收益估值",
    description="Absolute valuation of A shares based on the residual income model, returns book value, residual income sequence, intrinsic value, premium and applicable scenario judgment, suitable for asset-intensive enterprises such as banks",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "residual_income", "absolute_valuation", "rim"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["residual_income_valuation", "book_value_based_valuation"],
    when_to_use="Suitable for companies with positive book value and ROE data, especially for asset-intensive industries such as banking and insurance.",
    when_not_to_use="Not suitable for businesses with negative book value. Not suitable for companies with light assets and high intangible assets (large valuation deviation).",
    returns="Returns a JSON string containing net assets per share, ROE, cost of equity, residual earnings series, and intrinsic value.",
    example="get_residual_income_valuation(symbol='600519')",
    related_tools=["get_dcf_valuation", "get_wacc_calculation"],
)
def get_residual_income_valuation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    growth_years: Annotated[int, "Number of years in the forecast period, default 5"] = 5,
    terminal_growth: Annotated[float, "Terminal value growth rate, default 3%"] = 0.03,
    cost_of_equity: Annotated[Optional[float], "Equity cost, default None, automatically estimated"] = None,
) -> str:
    """Residual income valuation model:RI_t = (ROE_t - r_e) × BV_{t-1}

    Args:
        symbol: A stock stock code, such as 600519
        growth_years: Number of years in the forecast period, default 5, automatically clamped to [3, 15]
        terminal_growth: Growth rate of terminal value (decimal form), default 0.03
        cost_of_equity: Cost of equity (in decimal form), used when None is used by default 0.035 + 1.0 × 0.06 Automatic estimation

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code

        In case of success, return dict, fields:
            symbol: Stock code
            method: "residual_income_model"
            parameters: parameters dict —
                book_value_per_share: Net assets per share
                roe: Latest ROE (decimal)
                cost_of_equity: Cost of equity (decimal)
                forecast_years: Years of forecast period
                terminal_growth: Growth rate of terminal value (decimal)
            valuation: Valuation results dict —
                current_book_value_per_share: Current net assets per share
                cumulative_pv_ri: The total present value of residual income during the forecast period
                pv_terminal_ri: future value present value of residual income
                intrinsic_value: intrinsic value
                current_price: current stock price
                upside_pct: Percent upside relative to current price
            residual_income_stream: List of residual income streams for each period [{"year": ..., "roe": ..., "book_value_per_share": ..., "residual_income_per_share": ..., "pv_residual_income": ...}, ...]
            data_quality: Data quality dict —
                years_available: Available annual report periods
                roe_source: ROE Source:"latest_roe" | "estimated"
                cost_of_equity_source: Source of equity cost:"parameter_override" | "auto_estimated"
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.data_access import get_latest_stock_price, get_stock_basic_info, get_stock_financial_periods
        from core.skill_runtime.standard_financial_apis import get_historical_financial_annual_series

        series = get_historical_financial_annual_series(symbol, years=5)
        records = series.get("records") or []

        if len(records) < 2:
            return json.dumps(
                {"status": "error", "message": f"可用年报数据不足（仅 {len(records)} 期），无法进行剩余收益估值", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        warnings: list = []
        latest = records[0]
        bvps = _extended_valuation_safe_div(latest.get("total_equity"), None)
        roe = latest.get("roe")
        current_price = get_latest_stock_price(symbol)

        # Get total share capital
        basic_info = get_stock_basic_info(symbol) or {}
        shares = _resolve_shares(basic_info, current_price, warnings)

        total_equity = latest.get("total_equity")
        if total_equity is None or total_equity <= 0 or shares is None or shares <= 0:
            return json.dumps(
                {"status": "error", "message": f"Net worth data is invalid (equity={total_equity}, shares={shares}) , Unable to value", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        bvps = total_equity / shares

        if roe is None or roe <= 0:
            # extrapolated from records ROE
            net_profit = latest.get("net_profit")
            if net_profit and total_equity > 0:
                roe = net_profit / total_equity
            else:
                roe = 0.08
                warnings.append("ROE For missing data, the 8% imputation was used by default.")

        # cost of equity
        if cost_of_equity is not None:
            re = cost_of_equity
            re_source = "parameter_override"
        else:
            re = 0.035 + 1.0 * 0.06  # Rf + beta * ERP
            re_source = "auto_estimated"

        n_years = max(3, min(15, int(growth_years)))
        tg = terminal_growth

        # Estimate ROE for each period (assuming linear regression to industry mean)
        roe_start = roe
        roe_end = 0.10  # Assume that the long-term return to 10%
        ri_stream = []
        prev_bv = bvps
        cumulative_ri_pv = 0

        for yr in range(1, n_years + 1):
            decay = yr / n_years
            roe_t = roe_start * (1 - decay) + roe_end * decay
            ri_t = (roe_t - re) * prev_bv
            pv_ri = ri_t / (1 + re) ** yr
            ri_stream.append({
                "year": yr,
                "roe": round(roe_t, 4),
                "book_value_per_share": round(prev_bv, 4),
                "residual_income_per_share": round(ri_t, 4),
                "pv_residual_income": round(pv_ri, 4),
            })
            cumulative_ri_pv += pv_ri
            # update BV: Assuming dividend payout ratio = 1 - g/ROE
            implied_payout = 1 - tg / roe_t if roe_t > 0 else 0.6
            implied_payout = max(0, min(1, implied_payout))
            retention = 1 - implied_payout
            prev_bv = prev_bv + ri_t + roe_t * prev_bv * (1 - retention)  # Simplifying BV evolution

        # future value
        last_ri = ri_stream[-1]["residual_income_per_share"] if ri_stream else 0
        pv_terminal_ri = (last_ri * (1 + tg) / (re - tg)) / (1 + re) ** n_years if re > tg else 0

        intrinsic_value = bvps + cumulative_ri_pv + pv_terminal_ri
        upside_pct = ((intrinsic_value - current_price) / current_price * 100) if (current_price and current_price > 0) else None

        payload = {
            "symbol": symbol,
            "method": "residual_income_model",
            "parameters": {
                "book_value_per_share": round(bvps, 4),
                "roe": round(roe, 4),
                "cost_of_equity": round(re, 4),
                "forecast_years": n_years,
                "terminal_growth": round(tg, 4),
            },
            "valuation": {
                "current_book_value_per_share": round(bvps, 2),
                "cumulative_pv_ri": round(cumulative_ri_pv, 2),
                "pv_terminal_ri": round(pv_terminal_ri, 2),
                "intrinsic_value": round(intrinsic_value, 2),
                "current_price": current_price,
                "upside_pct": round(upside_pct, 2) if upside_pct is not None else None,
            },
            "residual_income_stream": ri_stream,
            "data_quality": {
                "years_available": len(records),
                "roe_source": "latest_roe" if roe == latest.get("roe") else "estimated",
                "cost_of_equity_source": re_source,
                "warnings": warnings,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("剩余收益估值失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ─────────────────────────────────────────────────────────────
# Tool 4: EVA Valuation
# ─────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_eva_valuation",
    name="EVA 估值",
    description="Calculate A-share economic profits based on the EVA model to reflect value creation capabilities, returning NOPAT, capital occupation, WACC, EVA sequence and value creation assessment",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "eva", "economic_value_added", "value_creation"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["economic_profit_analysis", "value_creation_assessment"],
    when_to_use="Used when it is necessary to evaluate the true economic profit of the enterprise (value creation exceeding the cost of capital). Suitable for capital-intensive enterprises.",
    when_not_to_use="Not suitable for businesses without valid financial data. A positive EVA does not mean that the stock price is undervalued and needs to be combined with other valuation methods.",
    returns="Returns a JSON string containing NOPAT, WACC, invested capital, EVA value, EVA spread and multi-period trend.",
    example="get_eva_valuation(symbol='600519')",
    related_tools=["get_wacc_calculation", "get_dcf_valuation"],
)
def get_eva_valuation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    tax_rate: Annotated[float, "Corporate income tax rate, default 25%"] = 0.25,
) -> str:
    """EVA Valuation:EVA = NOPAT - WACC × Invested_Capital

    Args:
        symbol: A stock stock code, such as 600519
        tax_rate: Corporate income tax rate (decimal form), default 0.25, automatically clamped to [0, 0.5]

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code

        In case of success, return dict, fields:
            symbol: Stock code
            method: "economic_value_added"
            current_eva: The latest EVA indicator dict —
                nopat: Net operating profit after tax
                wacc: Weighted average cost of capital (decimal)
                invested_capital: Invest capital
                eva_value: EVA value
                eva_spread: EVA Interest rate spread (EVA/invested capital)
            trend: Multi-issue EVA trend list [{"year": ..., "nopat": ..., "wacc": ..., "invested_capital": ..., "eva": ..., "eva_spread": ...}, ...]
            current_price: current stock price
            data_quality: Data quality dict —
                years_available: Available annual report periods
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.data_access import get_stock_financial_periods, get_latest_stock_price, get_stock_basic_info
        from core.skill_runtime.standard_financial_apis import get_historical_financial_annual_series

        series = get_historical_financial_annual_series(symbol, years=5)
        records = series.get("records") or []

        if len(records) < 2:
            return json.dumps(
                {"status": "error", "message": f"可用年报数据不足（仅 {len(records)} 期），无法进行 EVA 估值", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        warnings: list = []
        trend = []
        tax = max(0, min(0.5, tax_rate))

        # Calculate WACC
        rf = 0.025
        erp = 0.06
        cost_of_equity = rf + 1.0 * erp
        cost_of_debt = 0.04

        for item in records:
            nopat = _extended_valuation_safe_div(item.get("oper_profit") or item.get("operating_profit"), None)
            if nopat is None:
                nopat = _extended_valuation_safe_div(item.get("net_profit"), None)
                if nopat is not None:
                    nopat = nopat * (1 + tax / (1 - tax)) if tax < 1 else nopat * 1.33
            else:
                nopat = nopat * (1 - tax)

            total_liab = item.get("total_liab") or 0
            total_equity = item.get("total_equity") or 0
            money_cap = item.get("money_cap") or 0
            invested_capital = total_equity + total_liab - money_cap

            if invested_capital <= 0:
                invested_capital = total_equity + total_liab

            # WACC
            debt_to_assets = item.get("debt_to_assets")
            if debt_to_assets is not None:
                debt_w = debt_to_assets / 100.0 if debt_to_assets > 1 else debt_to_assets
            else:
                debt_w = _extended_valuation_safe_div(total_liab, total_liab + total_equity) if (total_liab + total_equity) > 0 else 0.4
            debt_w = max(0, min(1, debt_w if debt_w else 0.4))
            eq_w = 1.0 - debt_w
            wacc_val = eq_w * cost_of_equity + debt_w * cost_of_debt * (1 - tax)

            eva_val = nopat - wacc_val * invested_capital if nopat is not None else None
            eva_spread = _extended_valuation_safe_div(eva_val, invested_capital)

            trend.append({
                "year": item.get("year"),
                "nopat": round(nopat, 2) if nopat is not None else None,
                "wacc": round(wacc_val, 4),
                "invested_capital": round(invested_capital, 2),
                "eva": round(eva_val, 2) if eva_val is not None else None,
                "eva_spread": round(eva_spread, 4) if eva_spread is not None else None,
            })

        latest_trend = trend[0] if trend else {}
        current_price = get_latest_stock_price(symbol)

        payload = {
            "symbol": symbol,
            "method": "economic_value_added",
            "current_eva": {
                "nopat": latest_trend.get("nopat"),
                "wacc": latest_trend.get("wacc"),
                "invested_capital": latest_trend.get("invested_capital"),
                "eva_value": latest_trend.get("eva"),
                "eva_spread": latest_trend.get("eva_spread"),
            },
            "trend": trend,
            "current_price": current_price,
            "data_quality": {
                "years_available": len(records),
                "warnings": warnings,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("EVA估值失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ─────────────────────────────────────────────────────────────
# Tool 5: FCFF / FCFE free cash flow calculation
# ─────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_fcff_fcfe_calculation",
    name="自由现金流计算",
    description="Calculate corporate free cash flow FCFF and equity free cash flow FCFE, returning EBIT, tax rate, NOPAT, capital expenditures, changes in working capital, and multi-period series",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "fcff", "fcfe", "free_cashflow", "cashflow_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["free_cashflow_analysis", "dcf_input_preparation"],
    when_to_use="Used when a detailed breakdown and multi-period trends of FCFF/FCFE and its components are required.",
    when_not_to_use="Not suitable for businesses without detailed cash flow data.",
    returns="Returns a JSON string containing multi-period trends for FCFF, FCFE, and their components.",
    example="get_fcff_fcfe_calculation(symbol='600519')",
    related_tools=["get_dcf_valuation", "get_cashflow_quality_trend"],
)
def get_fcff_fcfe_calculation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    tax_rate: Annotated[float, "Corporate income tax rate, default 25%"] = 0.25,
) -> str:
    """Calculate FCFF = NOPAT + D&A - CapEx - ΔWC and FCFE = FCFF - Interest×(1-t) + NetBorrowing

    Args:
        symbol: A stock stock code, such as 600519
        tax_rate: Corporate income tax rate (decimal form), default 0.25, automatically clamped to [0, 0.5]

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code

        In case of success, return dict, fields:
            symbol: Stock code
            method: "FCFF/FCFE Calculate"
            latest: The latest data dict —
                fcff: company free cash flow
                fcfe: free cash flow to equity
                components: FCFF/FCFE composition dict —
                    nopat: Net operating profit after tax
                    depreciation_amortization: Depreciation and amortization estimates
                    capex: capital expenditure
                    delta_working_capital: working capital changes
                    interest_expense: interest expense
                    net_borrowing: Net new borrowings
            trend: Multi-period trend list [{"year": ..., "nopat": ..., "depreciation_amortization": ..., "capex": ..., "delta_working_capital": ..., "fcff": ..., "interest_expense": ..., "net_borrowing": ..., "fcfe": ...}, ...]
            data_quality: Data quality dict —
                years_available: Available annual report periods
                da_source: Source of depreciation and amortization ("estimated_percent_of_revenue") 
                capex_source: Sources of capital expenditure ("delta_fixed_assets_plus_da") 
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.data_access import get_stock_financial_periods
        from core.skill_runtime.standard_financial_apis import get_historical_financial_annual_series

        series = get_historical_financial_annual_series(symbol, years=5)
        records = series.get("records") or []

        if len(records) < 2:
            return json.dumps(
                {"status": "error", "message": f"可用年报数据不足（仅 {len(records)} 期），无法计算 FCFF/FCFE", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        tax = max(0, min(0.5, tax_rate))
        raw_periods = get_stock_financial_periods(symbol, limit=max(len(records) + 2, 10))

        # 🔑 When grouping by year, the annual report of the same year (ends on 12-31) is given priority to avoid the cumulative value of the quarterly report being regarded as the annual report.
        from core.tools.implementations.risk.extended_risk_models import (
            _detect_period_type, _PERIOD_LABELS,
        )
        period_by_year = {}
        for p in raw_periods:
            yr = p.get("report_period") or p.get("report_date") or ""
            y = str(yr)[:4] if yr else ""
            if y.isdigit():
                year_int = int(y)
                p_type = _detect_period_type(p)
                # When data for the same year are available, priority will be given to retaining data with a larger caliber.
                if year_int not in period_by_year:
                    period_by_year[year_int] = p
                else:
                    priority = {"annual": 4, "q3": 3, "h1": 2, "q1": 1, "unknown": 0}
                    existing_type = _detect_period_type(period_by_year[year_int])
                    if priority.get(p_type, 0) > priority.get(existing_type, 0):
                        period_by_year[year_int] = p

        warnings: list = []
        trend = []
        prev_wc = None

        for item in records:
            year = item.get("year")
            revenue = item.get("revenue")
            oper_profit = item.get("oper_profit") or item.get("operating_profit")
            net_profit = item.get("net_profit")
            ocf = item.get("operating_cashflow")

            # NOPAT = oper_profit × (1 - tax)
            nopat = oper_profit * (1 - tax) if oper_profit is not None else None
            if nopat is None and net_profit is not None:
                nopat = net_profit * (1 + tax / (1 - tax)) * (1 - tax) if tax < 1 else net_profit

            # D&A Estimate: 3% of revenue (typical manufacturing/service industry levels)
            da_estimate = revenue * 0.03 if revenue is not None else 0

            # CapEx = Δ(fix_assets) + D&A (Approximately)
            cur_fa = item.get("fix_assets") or 0
            # Find the previous issue
            prev_fa = None
            for r in records:
                if r.get("year") == year - 1:
                    prev_fa = r.get("fix_assets") or 0
                    break
            if prev_fa is None:
                prev_fa = cur_fa
            delta_fa = cur_fa - prev_fa
            capex = delta_fa + da_estimate if delta_fa >= 0 else da_estimate
            # If capex is negative or abnormal, use 30% of OCF as an estimate
            if capex < 0 and ocf is not None and ocf > 0:
                capex = ocf * 0.3
                warnings.append(f"{year}Annual fixed assets reduction, CapEx estimated at 30% of OCF")

            # ΔWorkingCapital
            cur_ca = item.get("total_cur_assets") or 0
            cur_cl = item.get("total_cur_liab") or 0
            wc = cur_ca - cur_cl
            if prev_wc is not None:
                delta_wc = wc - prev_wc
            else:
                delta_wc = 0
            prev_wc = wc

            # FCFF
            if nopat is not None:
                fcff = nopat + da_estimate - capex - delta_wc
            else:
                fcff = ocf - capex - delta_wc if ocf is not None else None

            # FCFE
            interest = item.get("fin_exp") or 0
            net_borrowing = 0  # Simplified processing
            fcfe = fcff - interest * (1 - tax) + net_borrowing if fcff is not None else None

            trend.append({
                "year": year,
                "nopat": round(nopat, 2) if nopat is not None else None,
                "depreciation_amortization": round(da_estimate, 2),
                "capex": round(capex, 2),
                "delta_working_capital": round(delta_wc, 2),
                "fcff": round(fcff, 2) if fcff is not None else None,
                "interest_expense": round(interest, 2),
                "net_borrowing": net_borrowing,
                "fcfe": round(fcfe, 2) if fcfe is not None else None,
            })

        latest = trend[0] if trend else {}

        payload = {
            "symbol": symbol,
            "method": "FCFF/FCFE计算",
            "latest": {
                "fcff": latest.get("fcff"),
                "fcfe": latest.get("fcfe"),
                "components": {
                    "nopat": latest.get("nopat"),
                    "depreciation_amortization": latest.get("depreciation_amortization"),
                    "capex": latest.get("capex"),
                    "delta_working_capital": latest.get("delta_working_capital"),
                    "interest_expense": latest.get("interest_expense"),
                    "net_borrowing": latest.get("net_borrowing"),
                },
            },
            "trend": trend,
            "data_quality": {
                "years_available": len(records),
                "da_source": "estimated_percent_of_revenue",
                "capex_source": "delta_fixed_assets_plus_da",
                "warnings": warnings,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("FCFF/FCFE Calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ─────────────────────────────────────────────────────────────
# Tool 6: PEG Valuation
# ─────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_peg_valuation",
    name="PEG 估值",
    description="Evaluate the rationality of the valuation of A-share growth stocks based on the PEG indicator, return PE, 3-year net profit CAGR, PEG ratio, valuation judgment and industry comparison, applicable to growth stocks",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "peg", "growth_valuation", "relative_valuation"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["growth_stock_valuation", "peg_analysis"],
    when_to_use="It is suitable for companies with positive profits and clear growth trends, and is used to judge the reasonableness of the valuation of growth stocks.PEG < 1 Usually indicates an underestimation.",
    when_not_to_use="Not suitable for companies with negative net profits (PE cannot be calculated). Not suitable for businesses with extremely volatile growth (CAGR distortion).",
    returns="Returns a JSON string containing PE, 3-year net profit CAGR, PEG ratio and valuation conclusion.",
    example="get_peg_valuation(symbol='600519')",
    related_tools=["get_comparable_company_valuation", "get_growth_quality_metrics"],
)
def get_peg_valuation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
) -> str:
    """PEG = PE / Earnings_Growth_Rate

    Args:
        symbol: A stock stock code, such as 600519

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code

        In case of success, return dict, fields:
            symbol: Stock code
            method: "peg_valuation"
            parameters: parameters dict —
                pe_ttm: rolling price to earnings ratio
                growth_rate_3y_cagr: 3 Annual net profit CAGR (decimal), when it cannot be calculated None
                peg_ratio: PEG Ratio, when it cannot be calculated, it is None
            valuation: Valuation conclusion dict —
                assessment: Assessment conclusion:"underestimate" | "reasonable" | "overestimate" | "Unable to evaluate (growth rate is insufficient or negative)"
                current_price: current stock price
            data_quality: Data quality dict —
                years_of_profit_data: Number of periods with positive profit data
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.data_access import get_stock_basic_info, get_latest_stock_price
        from core.skill_runtime.standard_financial_apis import get_historical_financial_annual_series

        basic_info = get_stock_basic_info(symbol) or {}
        pe_ttm = basic_info.get("pe_ttm") or basic_info.get("pe")
        current_price = get_latest_stock_price(symbol)

        if pe_ttm is None or pe_ttm <= 0:
            return json.dumps(
                {"status": "error", "message": f"无法获取 {symbol} 的有效 PE（市盈率），可能净利润为负", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        # Obtain 3 years of net profit CAGR
        series = get_historical_financial_annual_series(symbol, years=5)
        records = series.get("records") or []
        profit_values = [r.get("net_profit") for r in records if r.get("net_profit") is not None and r.get("net_profit") > 0]

        assessment = None
        growth_rate_3y_cagr = None

        if len(profit_values) >= 3:
            latest_p = profit_values[0]
            earliest_p = profit_values[min(2, len(profit_values) - 1)]
            periods = min(2, len(profit_values) - 1)
            growth_rate_3y_cagr = _extended_valuation_cagr(latest_p, earliest_p, periods)
        elif len(profit_values) >= 2:
            latest_p = profit_values[0]
            earliest_p = profit_values[-1]
            periods = len(profit_values) - 1
            growth_rate_3y_cagr = _extended_valuation_cagr(latest_p, earliest_p, periods)

        if growth_rate_3y_cagr is not None and growth_rate_3y_cagr > 0:
            peg_ratio = pe_ttm / (growth_rate_3y_cagr * 100)
        else:
            peg_ratio = None

        if peg_ratio is not None:
            if peg_ratio < 1:
                assessment = "低估"
            elif peg_ratio <= 2:
                assessment = "合理"
            else:
                assessment = "高估"
        else:
            assessment = "Unable to evaluate (growth rate is insufficient or negative)"

        payload = {
            "symbol": symbol,
            "method": "peg_valuation",
            "parameters": {
                "pe_ttm": round(pe_ttm, 2) if pe_ttm else None,
                "growth_rate_3y_cagr": round(growth_rate_3y_cagr, 4) if growth_rate_3y_cagr is not None else None,
                "peg_ratio": round(peg_ratio, 2) if peg_ratio is not None else None,
            },
            "valuation": {
                "assessment": assessment,
                "current_price": current_price,
            },
            "data_quality": {
                "years_of_profit_data": len(profit_values),
                "warnings": [] if growth_rate_3y_cagr else ["Net profit CAGR cannot be calculated, please check whether the profit data is sufficient"],
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("PEG估值失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ─────────────────────────────────────────────────────────────
# Tool 7: Graham Valuation
# ─────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_graham_valuation",
    name="格雷厄姆估值",
    description="Calculate the intrinsic value and safety margin of A shares based on Graham s formula, return EPS, book value, Graham s number, current stock price, upside potential and safety margin percentage, suitable for value investment",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "graham", "value_investing", "absolute_valuation", "safety_margin"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["value_investing_analysis", "safety_margin_calculation"],
    when_to_use="It is suitable for investors looking for value stocks to determine the safety margin of the stock price relative to the Graham number. Suitable for companies with stable profits and net assets.",
    when_not_to_use="Not suitable for companies with high growth but negative profits. The Graham number may be too conservative for asset-light high-tech companies.",
    returns="Returns a JSON string containing EPS, BVPS, Graham Number, current price, upside, and margin of safety.",
    example="get_graham_valuation(symbol='600519')",
    related_tools=["get_dcf_valuation", "get_comparable_company_valuation", "get_graham_screen"],
)
def get_graham_valuation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
) -> str:
    """Graham Number = √(22.5 × EPS × BVPS)

    Args:
        symbol: A stock stock code, such as 600519

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code

        In case of success, return dict, fields:
            symbol: Stock code
            method: "Graham Valuation"
            parameters: parameters dict —
                eps: earnings per share
                bvps: Net assets per share
                graham_number: Graham number
            valuation: Valuation results dict —
                graham_number: Graham number
                current_price: current stock price
                upside_pct: Percent upside relative to current price
                safety_margin: safety margin percentage
                safety_margin_level: Safety margin level:"high margin of safety" | "medium margin of safety" | "low margin of safety" | "no margin of safety"
            data_quality: Data quality dict —
                shares_source: Source of equity capital:"basic_info" | "estimated"
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.data_access import get_latest_stock_price, get_stock_basic_info, get_stock_financial_periods
        from core.skill_runtime.standard_financial_apis import get_historical_financial_annual_series

        basic_info = get_stock_basic_info(symbol) or {}
        current_price = get_latest_stock_price(symbol)

        series = get_historical_financial_annual_series(symbol, years=3)
        records = series.get("records") or []

        if not records:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的年报数据", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        warnings: list = []
        latest = records[0]

        # Get total share capital
        shares = _resolve_shares(basic_info, current_price, warnings)

        # EPS
        net_profit = latest.get("net_profit")
        eps = _extended_valuation_safe_div(net_profit, shares)

        # BVPS
        total_equity = latest.get("total_equity")
        bvps = _extended_valuation_safe_div(total_equity, shares)

        if eps is None or eps <= 0 or bvps is None or bvps <= 0:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"EPS={eps}, BVPS={bvps}, EPS Or the BVPS is invalid (maybe the net profit is negative or the net assets are negative) and the Graham number cannot be calculated",
                    "symbol": symbol,
                },
                ensure_ascii=False, indent=2, default=str,
            )

        graham_number = (22.5 * eps * bvps) ** 0.5
        upside_pct = ((graham_number - current_price) / current_price * 100) if (current_price and current_price > 0) else None
        safety_margin = ((graham_number - current_price) / graham_number * 100) if (graham_number and graham_number > 0 and current_price and current_price > 0) else None

        if safety_margin is not None:
            if safety_margin > 30:
                margin_level = "高安全边际"
            elif safety_margin > 15:
                margin_level = "中等安全边际"
            elif safety_margin > 0:
                margin_level = "低安全边际"
            else:
                margin_level = "无安全边际"
        else:
            margin_level = None

        payload = {
            "symbol": symbol,
            "method": "格雷厄姆估值",
            "parameters": {
                "eps": round(eps, 4),
                "bvps": round(bvps, 4),
                "graham_number": round(graham_number, 2),
            },
            "valuation": {
                "graham_number": round(graham_number, 2),
                "current_price": current_price,
                "upside_pct": round(upside_pct, 2) if upside_pct is not None else None,
                "safety_margin": round(safety_margin, 2) if safety_margin is not None else None,
                "safety_margin_level": margin_level,
            },
            "data_quality": {
                "shares_source": "basic_info" if (basic_info.get("total_shares") or basic_info.get("total_share")) else "estimated",
                "warnings": warnings,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("格雷厄姆估值失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ─────────────────────────────────────────────────────────────
# Tool 8: CAPM cost of equity
# ─────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_capm_cost_of_equity",
    name="CAPM 股权成本",
    description="Calculate the equity capital cost of A-shares based on the capital asset pricing model (CAPM) and return the risk-free interest rate, Beta, market risk premium, equity cost rate, etc.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "capm", "cost_of_equity", "discount_rate"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["cost_of_equity_calculation", "capm_analysis"],
    when_to_use="Used when estimating the cost of equity capital or providing discount rate parameters for DCF or residual income models.",
    when_not_to_use="Not suitable for newly public companies (less than 60 trading days) without beta data. Not suitable for non-A share targets.",
    returns="Returns a JSON string containing equity cost, beta, risk-free rate, equity risk premium and each component.",
    example="get_capm_cost_of_equity(symbol='600519')",
    related_tools=["get_wacc_calculation", "get_beta_calculation", "get_residual_income_valuation"],
)
def get_capm_cost_of_equity(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    risk_free_rate: Annotated[float, "Risk-free rate (10-year Treasury bond yield), default 2.5%"] = 0.025,
    equity_risk_premium: Annotated[float, "Equity risk premium, default 6%"] = 0.06,
) -> str:
    """CAPM = Rf + β × ERP

    Args:
        symbol: A stock stock code, such as 600519
        risk_free_rate: Risk-free interest rate (in decimal form, such as 0.025 for 2.5%), default 0.025
        equity_risk_premium: Equity risk premium (decimal form), default 0.06

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description

        In case of success, return dict, fields:
            symbol: Stock code
            method: "capm"
            parameters: parameters dict —
                risk_free_rate: Risk-free interest rate (decimal)
                beta: Beta coefficient
                equity_risk_premium: Equity risk premium (decimal)
            cost_of_equity: Cost of equity (decimal)
            components: components dict —
                risk_free_rate: dict — value: risk-free interest rate, description: Description
                beta: dict — value: Beta value, source: Beta Source:"default" | "price_returns_estimated"
                equity_risk_premium: dict — value: ERP value, description: Description
            formula: formula text "cost_of_equity = Rf + β × ERP"
            calculation: Calculation process text
            data_quality: Data quality dict —
                beta_source: Beta Source:"default" | "price_returns_estimated"
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.data_access import get_stock_daily_quotes
        from core.skill_runtime.standard_financial_apis import get_security_master
        import datetime

        rf = risk_free_rate if risk_free_rate is not None else 0.025
        erp = equity_risk_premium if equity_risk_premium is not None else 0.06
        warnings: list = []

        # Calculate Beta
        beta = 1.0
        beta_source = "default"
        try:
            end = datetime.date.today().isoformat()
            start = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
            quotes = get_stock_daily_quotes(symbol, start_date=start, end_date=end, limit=250)
            if quotes and len(quotes) >= 60:
                closes = []
                for q in quotes:
                    c = q.get("close")
                    if c is not None and isinstance(c, (int, float)) and c > 0:
                        closes.append(float(c))
                if len(closes) >= 60:
                    returns = []
                    for i in range(1, len(closes)):
                        if closes[i - 1] > 0:
                            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
                    if len(returns) >= 60:
                        var_ret = np.var(returns)
                        if var_ret > 0:
                            beta = max(0.2, min(2.5, np.sqrt(var_ret) / 0.015))
                            beta_source = "price_returns_estimated"
        except Exception as e:
            warnings.append(f"Beta Calculation failed, default value used 1.0: {e}")

        cost_of_equity = rf + beta * erp

        master = get_security_master(symbol)

        payload = {
            "symbol": symbol,
            "method": "capm",
            "parameters": {
                "risk_free_rate": round(rf, 4),
                "beta": round(beta, 4),
                "equity_risk_premium": round(erp, 4),
            },
            "cost_of_equity": round(cost_of_equity, 4),
            "components": {
                "risk_free_rate": {
                    "value": round(rf, 4),
                    "description": "10 1-year Chinese government bond yield (approximate value)",
                },
                "beta": {
                    "value": round(beta, 4),
                    "source": beta_source,
                },
                "equity_risk_premium": {
                    "value": round(erp, 4),
                    "description": "China equity market risk premium (approximate value)",
                },
            },
            "formula": "cost_of_equity = Rf + β × ERP",
            "calculation": f"{rf:.4f} + {beta:.4f} × {erp:.4f} = {cost_of_equity:.4f}",
            "data_quality": {
                "beta_source": beta_source,
                "warnings": warnings,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("CAPM Equity cost calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ─────────────────────────────────────────────────────────────
# Tool 9: Growth quality adjusted valuation
# ─────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_growth_adjusted_valuation",
    name="增长质量调整估值",
    description="Adjust PE valuation based on growth quality score (revenue robustness, ROIC, cash flow quality) and return quality score, adjusted PE, reasonable valuation range and adjustment factor details",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "growth_quality", "quality_adjusted", "adjusted_pe"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["growth_quality_analysis", "quality_adjusted_valuation"],
    when_to_use="Used when it is necessary to judge whether high growth is sustainable and whether the current PE reasonably reflects the quality of growth.",
    when_not_to_use="It is not suitable for companies whose net profits are negative and PE is invalid. Not suitable for businesses with less than 3 years of data.",
    returns="Returns a JSON string containing raw PE, growth quality score, adjusted PE, fair value, and valuation methodology.",
    example="get_growth_adjusted_valuation(symbol='600519')",
    related_tools=["get_peg_valuation", "get_growth_quality_metrics", "get_cashflow_quality_trend"],
)
def get_growth_adjusted_valuation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
) -> str:
    """Adjustment based on growth quality score PE

    Args:
        symbol: A stock stock code, such as 600519

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code

        In case of success, return dict, fields:
            symbol: Stock code
            method: "Growth quality adjusted valuation"
            parameters: parameters dict —
                raw_pe_ttm: Raw rolling P/E ratio
            growth_quality: Growth quality score dict —
                total_score: Overall rating (0-100)
                quality_label: Quality label:"Excellent" | "good" | "Average" | "Poor" | "Poor"
                components: Rating composition dict —
                    revenue_consistency: revenue consistency score
                    roic_sustainability: ROIC sustainability score
                    cashflow_quality: Cash Flow Quality Score
                detail: Rating details dict —
                    revenue_growth_std: Standard deviation of revenue growth rate (None if data is insufficient)
                    mean_roe: ROE Mean (None if there is insufficient data)
                    mean_ocf_to_net_profit: OCF/Net profit mean (None if there is insufficient data)
            valuation: Valuation results dict —
                pe_adjustment_factor: PE adjustment factor
                adjusted_pe: After adjustment PE
                industry_median_pe: Industry median PE (None if missing)
                fair_pe: fair PE
                fair_value: Fair value (None if EPS cannot be calculated)
                current_price: current stock price
            methodology: Methodology text
            data_quality: Data quality dict —
                industry: Industry
                years_available: Available annual report periods
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.data_access import get_stock_basic_info, get_latest_stock_price
        from core.skill_runtime.standard_financial_apis import (
            get_growth_quality_metrics,
            get_cashflow_quality_trend,
            get_historical_financial_annual_series,
        )

        basic_info = get_stock_basic_info(symbol) or {}
        pe_ttm = basic_info.get("pe_ttm") or basic_info.get("pe")
        current_price = get_latest_stock_price(symbol)

        if pe_ttm is None or pe_ttm <= 0:
            return json.dumps(
                {"status": "error", "message": f"无法获取 {symbol} 的有效 PE，无法进行增长质量调整估值", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        warnings: list = []

        # 1. Revenue Growth Consistency Score
        growth_metrics = get_growth_quality_metrics(symbol, years=5)
        growth_records = growth_metrics.get("annual_growth") or []
        revenue_growth_rates = [g.get("revenue_growth") for g in growth_records if g.get("revenue_growth") is not None]

        if len(revenue_growth_rates) >= 3:
            std_rev_growth = pstdev(revenue_growth_rates) if len(revenue_growth_rates) > 1 else 0
            mean_rev_growth = mean(revenue_growth_rates)
            # low volatility = high rating (std < 0.1 -> Full marks)
            consistency_score = max(0, min(30, 30 * (1 - std_rev_growth / 0.3)))
            if mean_rev_growth <= 0:
                consistency_score *= 0.5
        else:
            consistency_score = 15
            warnings.append(f"营收增长率数据不足（{len(revenue_growth_rates)} 期），一致性评分采用默认值。")

        # 2. ROIC sustainability score
        series = get_historical_financial_annual_series(symbol, years=5)
        records = series.get("records") or []
        roe_values = [r.get("roe") for r in records if r.get("roe") is not None]

        if len(roe_values) >= 3:
            mean_roe = mean(roe_values)
            std_roe = pstdev(roe_values) if len(roe_values) > 1 else 0
            roe_score = min(30, (mean_roe * 100) * 2)  # ROE The higher the score, the higher the score, 20% ROE -> 40 capped at 30
            roe_score = max(0, roe_score)
            # stability factor
            if std_roe > 0.05:
                roe_score *= max(0.5, 1 - (std_roe - 0.05) / 0.1)
        else:
            roe_score = 15
            warnings.append(f"ROE 数据不足（{len(roe_values)} 期），可持续性评分采用默认值。")

        # 3. Cash Flow Quality Score
        cf_quality = get_cashflow_quality_trend(symbol, years=5)
        cf_trend = cf_quality.get("trend") or []
        ocf_to_np_values = [c.get("ocf_to_net_profit") for c in cf_trend if c.get("ocf_to_net_profit") is not None]

        if ocf_to_np_values:
            mean_ocf_np = mean(ocf_to_np_values)
            # OCF/NP > 1.0 = High quality (full score), < 0.5 = low quality
            if mean_ocf_np >= 1.0:
                cf_score = 40
            elif mean_ocf_np >= 0.7:
                cf_score = 30
            elif mean_ocf_np >= 0.5:
                cf_score = 20
            else:
                cf_score = max(0, mean_ocf_np * 40)
        else:
            cf_score = 20
            warnings.append("Insufficient cash flow quality data, the score uses the default value.")

        # total score 0-100
        quality_score = round(consistency_score + roe_score + cf_score, 1)
        quality_score = max(0, min(100, quality_score))

        # PE adjust
        if quality_score >= 80:
            pe_adjustment_factor = 1.3       # high quality: +30% PE premium
            quality_label = "优秀"
        elif quality_score >= 60:
            pe_adjustment_factor = 1.15      # good: +15% premium
            quality_label = "良好"
        elif quality_score >= 40:
            pe_adjustment_factor = 1.0       # Average: No adjustment
            quality_label = "一般"
        elif quality_score >= 20:
            pe_adjustment_factor = 0.85      # Poor: -15% Discount
            quality_label = "较差"
        else:
            pe_adjustment_factor = 0.7       # Poor: -30% Discount
            quality_label = "差"

        adjusted_pe = pe_ttm * pe_adjustment_factor

        # Fair Value Estimate: Industry Average PE × quality adjustment factor
        # Use the industry average PE as a reference benchmark
        from core.skill_runtime.data_access import summarize_industry_valuation

        master = series if isinstance(series, dict) else {}
        industry = None
        if isinstance(master, dict):
            from core.skill_runtime.standard_financial_apis import get_security_master
            sec_master = get_security_master(symbol)
            industry = sec_master.get("industry")

        industry_pe = None
        if industry:
            ind_stats = summarize_industry_valuation(industry, metric="pe", exclude_symbol=symbol)
            industry_pe = ind_stats.get("median")

        # fair PE = Industry median PE × quality adjustment factor
        fair_pe = industry_pe * pe_adjustment_factor if industry_pe and industry_pe > 0 else adjusted_pe

        # Deriving fair value from EPS
        eps = None
        if records:
            net_profit = records[0].get("net_profit")
            shares = _resolve_shares(basic_info, current_price)
            if net_profit and shares and shares > 0:
                eps = net_profit / shares

        fair_value = eps * fair_pe if eps is not None and fair_pe is not None else None

        payload = {
            "symbol": symbol,
            "method": "增长质量调整估值",
            "parameters": {
                "raw_pe_ttm": round(pe_ttm, 2) if pe_ttm else None,
            },
            "growth_quality": {
                "total_score": quality_score,
                "quality_label": quality_label,
                "components": {
                    "revenue_consistency": round(consistency_score, 1),
                    "roic_sustainability": round(roe_score, 1),
                    "cashflow_quality": round(cf_score, 1),
                },
                "detail": {
                    "revenue_growth_std": round(std_rev_growth, 4) if len(revenue_growth_rates) >= 3 else None,
                    "mean_roe": round(mean_roe, 4) if len(roe_values) >= 3 else None,
                    "mean_ocf_to_net_profit": round(mean_ocf_np, 4) if ocf_to_np_values else None,
                },
            },
            "valuation": {
                "pe_adjustment_factor": pe_adjustment_factor,
                "adjusted_pe": round(adjusted_pe, 2) if adjusted_pe else None,
                "industry_median_pe": round(industry_pe, 2) if industry_pe else None,
                "fair_pe": round(fair_pe, 2) if fair_pe else None,
                "fair_value": round(fair_value, 2) if fair_value is not None else None,
                "current_price": current_price,
            },
            "methodology": "Based on revenue growth consistency(30%), ROIC sustainability(30%), cash flow quality(40%)Comprehensive rating adjustment PE",
            "data_quality": {
                "industry": industry,
                "years_available": len(records),
                "warnings": warnings,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("Growth quality adjustment valuation fails: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_dcf_three_stage_valuation",
    "get_ddm_valuation",
    "get_residual_income_valuation",
    "get_eva_valuation",
    "get_fcff_fcfe_calculation",
    "get_peg_valuation",
    "get_graham_valuation",
    "get_capm_cost_of_equity",
    "get_growth_adjusted_valuation",
]

# === valuation.wacc_calculator ===
"""WACC Weighted average cost of capital calculator"""

import json
import logging
from typing import Annotated, Optional

import numpy as np
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="get_wacc_calculation",
    name="WACC 计算器",
    description="Calculate the weighted average cost of capital WACC for A-share companies, return equity weight, debt weight, equity cost, debt cost, tax rate and WACC details, and provide a discount rate for DCF valuation",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["wacc", "cost_of_capital", "valuation", "discount_rate"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["discount_rate_estimation", "cost_of_capital_calculation"],
    when_to_use="Used when you need to calculate discount rates, estimate cost of capital, provide WACC parameters for DCF or absolute valuation.",
    when_not_to_use="Not suitable for direct use in valuation conclusions (only parameters are provided). Not suitable for targets without financial data.",
    returns="Returns a JSON string containing capital structure, cost of equity, cost of debt, WACC, and data quality description.",
    example="get_wacc_calculation(symbol='600519')",
    related_tools=["get_dcf_valuation", "get_dcf_three_stage_valuation", "get_capm_cost_of_equity"],
)
def get_wacc_calculation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    risk_free_rate: Annotated[Optional[float], "Risk-free rate, default 2.5%"] = 0.025,
    equity_risk_premium: Annotated[Optional[float], "Equity risk premium, default 6%"] = 0.06,
    tax_rate: Annotated[Optional[float], "Corporate income tax rate, default 25%"] = 0.25,
) -> str:
    """WACC Weighted average cost of capital calculation

    Args:
        symbol: A stock stock code, such as 600519
        risk_free_rate: Risk-free interest rate (in decimal form, such as 0.025 for 2.5%), default 0.025
        equity_risk_premium: Equity risk premium (decimal form), default 0.06
        tax_rate: Corporate income tax rate (decimal form), default 0.25

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code

        In case of success, return dict, fields:
            symbol: Stock code
            parameters: input parameters dict —
                risk_free_rate: Risk-free interest rate (decimal)
                equity_risk_premium: Equity risk premium (decimal)
                tax_rate: Income tax rate (decimal)
            capital_structure: capital structure dict —
                market_cap: Market value
                total_debt: total debt
                total_capital: total capital
                equity_weight: Equity weight (decimal)
                debt_weight: Debt weight (decimal)
                debt_to_equity: Debt to equity ratio (decimal, None if missing)
            cost_of_equity: cost of equity dict —
                beta: Beta coefficient
                risk_free_rate: Risk-free interest rate (decimal)
                equity_risk_premium: Equity risk premium (decimal)
                cost_of_equity: Cost of equity (decimal)
            cost_of_debt: cost of debt dict —
                interest_expense: interest expense
                total_debt: total debt
                pre_tax_cost: Cost of debt before tax (decimal)
                after_tax_cost: After-tax debt cost (decimal)
            wacc: Weighted average cost of capital (decimal)
            data_quality: Data quality dict —
                beta_source: Beta Source:"default" | "price_returns_estimated"
                debt_cost_source: Source of debt cost:"financial_expense_based" | "default_proxy"
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.data_access import get_stock_financial_periods, get_stock_daily_quotes
        from core.skill_runtime.standard_financial_apis import get_security_master
        import datetime

        warnings: list = []
        beta_source = "default"

        # 1. Get market capitalization
        master = get_security_master(symbol)
        market_cap = master.get("market_cap")
        if market_cap is None or market_cap <= 0:
            return json.dumps(
                {"status": "error", "message": f"无法获取 {symbol} 的有效市值", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        # 2. Get the latest financial data
        periods = get_stock_financial_periods(symbol, limit=1)
        if not periods:
            # Fallback to get_security_master with possible financial information
            total_liab = 0.0
            total_equity = (master.get("total_equity") or 0.0)
            fin_exp = 0.0
            warnings.append("No financial period data is obtained, and default values are used for debt and interest expenses.")
        else:
            latest_fin = periods[0]
            total_liab = latest_fin.get("total_liab") or 0.0
            total_equity = latest_fin.get("total_equity") or 0.0
            fin_exp = latest_fin.get("fin_exp") or 0.0

            # 🔑 Test the reporting period caliber and annualize the cumulative value of the income statement
            from core.tools.implementations.risk.extended_risk_models import (
                _detect_period_type, _annualize_factor, _PERIOD_LABELS,
            )
            cur_period = _detect_period_type(latest_fin)
            if cur_period != "annual" and cur_period != "unknown":
                factor = _annualize_factor(cur_period)
                fin_exp_annualized = fin_exp * factor
                warnings.append(
                    f"当期为{_PERIOD_LABELS.get(cur_period, cur_period)}数据，"
                    f"Financial expenses have been annualized ({fin_exp:.2f}→{fin_exp_annualized:.2f}) "
                )
                fin_exp = fin_exp_annualized

        # 3. Calculate Beta (simplified: calculated from daily returns, or default 1.0)
        beta = 1.0
        try:
            end = datetime.date.today().isoformat()
            start = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
            quotes = get_stock_daily_quotes(symbol, start_date=start, end_date=end, limit=250)
            if quotes and len(quotes) >= 60:
                closes = []
                for q in quotes:
                    c = q.get("close")
                    if c is not None and isinstance(c, (int, float)) and c > 0:
                        closes.append(float(c))
                if len(closes) >= 60:
                    returns = []
                    for i in range(1, len(closes)):
                        if closes[i - 1] > 0:
                            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
                    if len(returns) >= 60:
                        var_ret = np.var(returns)
                        if var_ret > 0:
                            # Using its own variance approximation, it is assumed that the market volatility is approximately 0.015 daily
                            market_var_proxy = 0.015 ** 2
                            cov_proxy = np.mean(returns) * np.mean(returns) if np.mean(returns) > 0 else 0
                            # Simplify:beta = Own volatility/market volatility
                            beta = max(0.2, min(2.5, np.sqrt(var_ret) / 0.015))
                            beta_source = "price_returns_estimated"
        except Exception as e:
            warnings.append(f"Beta Calculation failed, default value used 1.0: {e}")

        # 4. cost calculation
        rf = risk_free_rate if risk_free_rate is not None else 0.025
        erp = equity_risk_premium if equity_risk_premium is not None else 0.06
        tax = tax_rate if tax_rate is not None else 0.25

        cost_of_equity = rf + beta * erp

        # cost of debt
        if total_liab > 0 and fin_exp > 0:
            pre_tax_cost_of_debt = fin_exp / total_liab
            pre_tax_cost_of_debt = max(0.01, min(0.15, pre_tax_cost_of_debt))
            debt_cost_source = "financial_expense_based"
        else:
            pre_tax_cost_of_debt = 0.04
            debt_cost_source = "default_proxy"
            if total_liab == 0:
                warnings.append("Total debt is 0, and the default cost of debt is 4%.")
            if fin_exp == 0:
                warnings.append("The finance charge is 0 or missing and the debt cost uses the default 4%.")

        after_tax_cost_of_debt = pre_tax_cost_of_debt * (1 - tax)

        # 5. capital structure
        total_capital = market_cap + total_liab
        equity_weight = market_cap / total_capital if total_capital > 0 else 0.5
        debt_weight = total_liab / total_capital if total_capital > 0 else 0.5
        debt_to_equity = total_liab / total_equity if total_equity and total_equity > 0 else None

        # 6. WACC
        wacc_value = equity_weight * cost_of_equity + debt_weight * after_tax_cost_of_debt

        payload = {
            "symbol": symbol,
            "parameters": {
                "risk_free_rate": round(rf, 4),
                "equity_risk_premium": round(erp, 4),
                "tax_rate": round(tax, 4),
            },
            "capital_structure": {
                "market_cap": round(market_cap, 2),
                "total_debt": round(total_liab, 2),
                "total_capital": round(total_capital, 2),
                "equity_weight": round(equity_weight, 4),
                "debt_weight": round(debt_weight, 4),
                "debt_to_equity": round(debt_to_equity, 4) if debt_to_equity is not None else None,
            },
            "cost_of_equity": {
                "beta": round(beta, 4),
                "risk_free_rate": round(rf, 4),
                "equity_risk_premium": round(erp, 4),
                "cost_of_equity": round(cost_of_equity, 4),
            },
            "cost_of_debt": {
                "interest_expense": round(fin_exp, 2),
                "total_debt": round(total_liab, 2),
                "pre_tax_cost": round(pre_tax_cost_of_debt, 4),
                "after_tax_cost": round(after_tax_cost_of_debt, 4),
            },
            "wacc": round(wacc_value, 4),
            "data_quality": {
                "beta_source": beta_source,
                "debt_cost_source": debt_cost_source,
                "warnings": warnings,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("WACC计算失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_wacc_calculation"]

# === valuation_excel_tool ===
"""Valuation calculation form generation tool (A10-D2)

Declaratively callable deterministic deliverable tools for smart assistants:
  Data automatic assembly (valuation_bundle_builder)
  → LLM Generate model specifications (valuation_spec_generator)
  → Excel rendering + File verification (valuation_excel)

The fixed analysis process has zero changes; the tool returns Markdown (including download link and data source statement).
"""

import logging
import time
from typing import Annotated

from langchain_core.tools import tool

from core.deliverables.valuation_bundle_builder import ValuationDataError, build_valuation_bundle
try:
    from core.deliverables.valuation_excel import ValuationExcelInput, build_valuation_excel_artifact
except ImportError:
    ValuationExcelInput = build_valuation_excel_artifact = None
from core.deliverables.valuation_spec_generator import generate_valuation_spec
from core.tools.base import register_tool

logger = logging.getLogger(__name__)

_OUTPUT_DIR = "data/deliverables"


def _resolve_spec_llm():
    """Build specifications to generate LLM (model parsing chain is consistent with agent_executor, openai compatible access)"""
    from app.core.database import get_mongo_db_sync
    from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
    from core.llm.models import LLMConfig, LLMProvider
    from core.llm.unified_client import UnifiedLLMClient

    db = get_mongo_db_sync()
    config_doc = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)]) or {}
    default_models = config_doc.get("default_models") or {}
    system_settings = config_doc.get("system_settings") or {}

    target_model = (
        default_models.get("deep_reasoning_model")
        or system_settings.get("deep_reasoning_model")
        or default_models.get("deep_analysis_model")
        or system_settings.get("deep_analysis_model")
    )
    if not target_model:
        raise RuntimeError("The system is not configured with a deep analysis model (deep_reasoning_model / deep_analysis_model)")

    provider_info = get_provider_and_url_by_model_sync(target_model)
    if not provider_info:
        raise RuntimeError(f"无法获取模型 {target_model} 的供应商配置")

    # Valuation specification JSON structured output: unified access via OpenAI compatible adapter (all compatible with Volcano Ark/Bai Lian, etc.)
    llm = UnifiedLLMClient.from_config(
        LLMConfig(
            provider=LLMProvider.OPENAI,
            model=target_model,
            api_key=provider_info.get("api_key"),
            base_url=provider_info.get("backend_url"),
            temperature=0.2,
            max_tokens=4096,
            timeout=300,
        )
    )
    return target_model, llm


def _format_failure(title: str, detail: str) -> str:
    return f"### Valuation calculation sheet generation failed\n\n**{title}**\n\n{detail}\n\n*Please complete data synchronization or adjust requirements before trying again.*"


@tool
@register_tool(
    tool_id="generate_valuation_excel_tool",
    name="估值测算表格生成",
    description=(
        "Based on local synchronized annual report financial data and the latest market conditions, generate profit deduction and PE valuation scenario calculation tables for the next 1-3 years"
        " (xlsx file with real Excel formulas and editable hypothetical grids)."
        "When the user explicitly requests'Valuation calculation form''Profit Calculation Sheet''Valuation model Excel'Called when waiting for file deliverables."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="heavy",
    capability_tags=[
        "valuation_excel", "earnings_forecast", "pe_valuation",
        "financial_modeling", "target_price_scenario", "deliverable_generation",
    ],
    tool_role_hint="specialized",
    output_shape="structured_markdown",
    when_to_use=(
        "Called when the user explicitly requests to generate valuation calculation tables, profit deduction models, valuation scenario Excel and other document deliverables;"
        "The system will automatically verify whether the annual report/market/equity data has been synchronized before generation."
    ),
    when_not_to_use=(
        "Do not call in the following situations:1) Users only ask about valuation indicators (PE/PB/market capitalization) or general valuation knowledge,"
        "Answer directly or use the market/financial inquiry tool;2) User requirements**Data, tables, and"
        "Prediction results** (Such as sales forecast, revenue calculation and other non-valuation models) are made/exported Excel——This does not require modeling,"
        "You must use export_table_excel_tool instead (second-level export, this tool will take several minutes to re-model)."
    ),
    returns=(
        "Markdown Text: Generation results, valuation scenario target price summary table, file download link, data source description;"
        "A clear failure reason is returned when the data is not synchronized or specification verification fails."
    ),
    example="generate_valuation_excel_tool(symbol='601127', forecast_years=2)",
    related_tools=["get_historical_financial_annual_series_tool"],
)
def generate_valuation_excel_tool(
    symbol: Annotated[str, "A Stock stock code, 6 digits, such as 601127"],
    context_notes: Annotated[str, "Optional: Summary of research conclusions/profit expectations in the current analysis as a reference for calculating assumptions"] = "",
    forecast_years: Annotated[int, "Number of forecast years, 1-3, default 2"] = 2,
) -> str:
    """Generate valuation calculation Excel sheet (profit deduction + valuation scenario).

    Args:
        symbol: A Stock code, 6 digits
        context_notes: Optional summary of research conclusions
        forecast_years: Number of forecast years (1-3)

    Returns:
        Markdown text(result summary + Download link, or clear explanation of failure)
    """
    t0 = time.time()
    try:
        # 1. Data is automatically assembled (if missing, an error will be clearly reported, and replacement will not be estimated)
        try:
            bundle = build_valuation_bundle(symbol, context_notes=context_notes, forecast_years=forecast_years)
        except ValuationDataError as exc:
            return _format_failure("必需数据未同步", str(exc))

        # 2. LLM Generate model specifications (automatic feedback and retry if verification fails)
        try:
            model_name, llm = _resolve_spec_llm()
        except Exception as exc:  # noqa: BLE001
            logger.error("[ValuationExcelTool] LLM Build failed: %s", exc, exc_info=True)
            return _format_failure("模型配置不可用", str(exc))

        spec_result = generate_valuation_spec(bundle, llm, max_attempts=3)
        if not spec_result.get("passed"):
            errors = "\n".join(f"- {e}" for e in (spec_result.get("errors") or ["未知原因"]))
            return _format_failure(
                f"模型规格生成未通过校验（{spec_result.get('attempts')} 次尝试）", errors
            )
        spec = spec_result["spec"]

        # 3. rendering Excel
        from datetime import datetime

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"valuation_{bundle['ticker']}_{stamp}.xlsx"
        output_path = f"{_OUTPUT_DIR}/{filename}"
        try:
            render_valuation_excel(spec, output_path)
        except ValuationSpecError as exc:
            return _format_failure("规格渲染被阻断", str(exc))

        # 4. Restart file verification
        check = validate_valuation_excel(spec, output_path)
        if not check.get("passed"):
            errors = "\n".join(f"- {e}" for e in (check.get("errors") or ["未知原因"]))
            return _format_failure("生成文件校验未通过", errors)

        # Signed download link: The browser clicks directly without JWT header and must use presigned URL for authentication.
        from core.deliverables.download_links import sign_deliverable_query

        download_url = f"/api/assistant/deliverables/{filename}?{sign_deliverable_query(filename)}"

        # 5. Assembly result Markdown
        scenarios = check.get("summary", {}).get("scenarios", {})
        scenario_rows = "\n".join(
            f"| {name} | PE | {scen['eps']:.3f} | {scen['target_price']:.2f} |"
            for name, scen in scenarios.items()
        )
        elapsed = time.time() - t0
        data_notes = "；".join(bundle.get("data_notes") or []) or "Data source: Local synchronized annual report (Tushare/AKShare) and latest market prices"
        warnings = check.get("warnings") or []
        warning_lines = ""
        if warnings:
            warning_lines = "\n\n**Tips**: \n" + "\n".join(f"- {w}" for w in warnings)

        return (
            f"### 估值测算表已生成 ✅\n\n"
            f"**{bundle['stock_name']} ({bundle['ticker']}) ** · Current price {bundle['current_price']:.2f} Yuan"
            f" · total share capital {bundle['share_count']:.2f} 100 million shares · Time consuming to generate {elapsed:.0f} seconds\n\n"
            f"**Valuation Scenario (EPS Benchmark → target price)**\n\n"
            f"| Scenario | method | EPS (Yuan) | Target price (yuan) |\n"
            f"|------|------|-----------|--------------|\n"
            f"{scenario_rows}\n\n"
            f"📎 [Download Valuation Calculation Sheet]({download_url})\n\n"
            f"The table contains two sheets: profit deduction (revenue/net interest rate assumptions can be edited, and the formulas are automatically linked) and valuation scenarios (PE multiples can be adjusted)."
            f"{warning_lines}\n\n"
            f"**Data caliber**: {data_notes}\n\n"
            f"*This table is generated by AI (model:{model_name}) , It is for research reference only and does not constitute investment advice.*"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[ValuationExcelTool] Build failed: %s", exc, exc_info=True)
        return _format_failure("执行异常", str(exc))


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


def _fetch_china_yield_curve() -> dict:
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


def _fetch_zh_us_rate() -> dict:
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
        curve = _fetch_china_yield_curve()
        zh_us = _fetch_zh_us_rate()

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
            curve = _fetch_china_yield_curve()
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
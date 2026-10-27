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

def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _safe_float(value) -> Optional[float]:
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


def _json_response(payload: dict) -> str:
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
            return _json_response({"status": "error", "message": "无效股票代码"})

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
            current_price = _safe_float(basic.get("close") or basic.get("current_price"))

        total_mv = _safe_float(basic.get("total_mv") or basic.get("market_cap")) if (basic := get_stock_basic_info(normalized_symbol)) else None

        # 4. Calculate FCF (taken directly from the annual report series; take the latest year)
        fcf = None
        fcf_yield = None
        if trend:
            latest_trend = trend[0]
            fcf = _safe_float(latest_trend.get("free_cashflow"))
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

        return _json_response({
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
        return _json_response({"status": "error", "message": f"Failed to obtain in-depth analysis of cash flow quality: {exc}"})


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
            return _json_response({"status": "error", "message": "无效股票代码"})

        # 1. Get financial period data (last 16 periods to ensure 8 quarters)
        periods = get_stock_financial_periods(normalized_symbol, limit=16) or []

        if not periods:
            return _json_response({"status": "no_data", "message": "未获取到财务期间数据", "symbol": normalized_symbol})

        # 2. Extract quarterly net profit data and perform caliber processing
        # 🔑 Key: Net profits in different reporting periods (annual reports/quarterly reports) are cumulative values and cannot be directly compared on a month-on-month basis.
        # Strategy: Prioritize data of the same caliber (such as taking all annual reports), and if insufficient, group them by caliber.
        quarterly_data: List[Dict[str, Any]] = []
        caliber_warnings: List[str] = []
        for p in periods:
            period_label = str(p.get("report_period") or p.get("report_date") or "")
            net_profit = _safe_float(p.get("net_profit") or p.get("net_income") or p.get("n_income_attr_p"))
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
            return _json_response({
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

        return _json_response({
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
        return _json_response({"status": "error", "message": f"业绩预告分析获取失败: {exc}"})


__all__ = [
    "get_cashflow_quality_deep",
    "get_earnings_surprise_analysis",
]
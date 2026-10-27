"""Extended risk model tools: Ohlson O-Score, receivables quality, inventory quality, liquidity stress testing, debt structure analysis"""

import json
import logging
import math
from typing import Annotated, Optional, Any

import numpy as np
from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_financial_periods
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_div(numerator, denominator) -> float | None:
    n = _safe_float(numerator)
    d = _safe_float(denominator)
    if n is None or d is None or d == 0:
        return None
    return n / d


def _pct_change(current, previous) -> float | None:
    c = _safe_float(current)
    p = _safe_float(previous)
    if c is None or p is None or p == 0:
        return None
    return (c - p) / abs(p)


# ============================================================================
# Reporting period caliber detection (avoiding erroneous comparisons of quarterly reports vs. annual reports)
# ============================================================================

_PERIOD_LABELS = {"q1": "一季报", "h1": "半年报", "q3": "三季报", "annual": "年报", "unknown": "未知"}


def _detect_period_type(fin: dict) -> str:
    """Return period_type: annual / q1 / h1 / q3 / unknown"""
    rp = str(fin.get("report_period") or fin.get("report_date") or fin.get("end_date") or "").strip()
    if not rp:
        return "unknown"
    # Extract month: supported "2025-03-31" and "20250331" two formats
    digits = "".join(ch for ch in rp[:10] if ch.isdigit())
    if len(digits) >= 6:
        month_part = digits[4:6]
    elif "-" in rp and len(rp) >= 7:
        month_part = rp[:10].split("-")[1]
    else:
        month_part = ""
    return {"03": "q1", "06": "h1", "09": "q3", "12": "annual"}.get(month_part, "unknown")


def _annualize_factor(period_type: str) -> float:
    """Annualization Factor: Annual Report=1, First quarter report=4, semi-annual report=2, third quarter report=4/3"""
    return {"annual": 1.0, "q1": 4.0, "h1": 2.0, "q3": 4.0 / 3.0}.get(period_type, 1.0)


def _find_same_period_prev(fin_data_list: list, cur_period_type: str) -> tuple:
    """Find the previous period s data of the same caliber and make a year-on-year comparison. Return (fin_prev, prev_period_type, period_mismatch)"""
    for candidate in fin_data_list[1:]:
        if _detect_period_type(candidate) == cur_period_type:
            return candidate, cur_period_type, False
    # The next best thing is to use the latest issue.
    if len(fin_data_list) > 1:
        fin_prev = fin_data_list[1]
        prev_type = _detect_period_type(fin_prev)
        mismatch = (prev_type != cur_period_type and cur_period_type != "unknown")
        return fin_prev, prev_type, mismatch
    return None, "unknown", False


def _period_caliber_payload(cur_type: str, prev_type: str, mismatch: bool) -> dict:
    """Generate caliber information payload"""
    return {
        "current": cur_type,
        "previous": prev_type,
        "period_mismatch": mismatch,
        "annualized": cur_type != "annual" and cur_type != "unknown",
    }


# ============================================================================
# Tool 1:  Ohlson O-Score bankruptcy prediction
# ============================================================================

@tool
@register_tool(
    tool_id="get_ohlson_oscore",
    name="Ohlson O-Score bankruptcy prediction",
    description="The probability of bankruptcy of A-share companies is predicted based on the Ohlson O-Score logit model, taking into account six dimensions including company size, debt level, liquidity, and profitability.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["bankruptcy_risk", "financial_distress"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["bankruptcy_probability_prediction"],
    when_to_use="It is used when it is necessary to quantitatively assess the probability of a company s bankruptcy and identify the risk of financial distress. It is especially suitable for manufacturing and mature companies.",
    when_not_to_use="Not applicable to companies in the financial industry (financial statement structures are different); O-Score has limited accuracy for high-growth technology companies.",
    returns="Returns a JSON string, including o_score, probability, risk_level, components and data_quality.",
    example="get_ohlson_oscore(symbol='600519')",
    related_tools=["get_altman_zscore", "get_piotroski_fscore"],
)
def get_ohlson_oscore(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Calculate the Ohlson O-Score probability of bankruptcy. Based on the logit model, the probability of bankruptcy is predicted based on dimensions such as company size, liabilities, liquidity, and profitability.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            o_score: O-Score Score (the higher the score, the greater the probability of bankruptcy)
            probability: Probability of bankruptcy (0-1, obtained by logit transformation of O-Score)
            risk_level: risk level,"high" (>0.5)  | "medium" (>0.15)  | "low"
            components: dict, Six servings——
                — x1_log_assets: log(total assets)
                — x2_debt_ratio: Total Liabilities/Total Assets
                — x3_wc_to_assets: working capital/total assets
                — x4_cl_to_ca: Current liabilities / current assets
                — x5_liab_exceeds_assets: Insolvency dummy variable (1.0 or 0.0)
                — x6_ni_change: Net profit change rate (None if the caliber is inconsistent or data is missing)
            interpretation: dict, Interpretation——
                — o_score: O-Score
                — probability: bankruptcy probability
                — risk_level: risk level
            data_quality: dict, Data quality——
                — warnings: list[str], Alarm information
            message: When status is "error" error description when
    """
    try:
        # Obtain multi-period financial data (the same caliber is required to calculate net profit changes)
        fin_data_list = get_stock_financial_periods(symbol, limit=4)
        if not fin_data_list:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的财务数据", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        fin_t = fin_data_list[0]
        # 🔑 Find data from the previous period of the same caliber (to avoid erroneous comparisons of quarterly reports vs. annual reports)
        cur_period_type = _detect_period_type(fin_t)
        fin_t1, prev_period_type, period_mismatch = _find_same_period_prev(fin_data_list, cur_period_type)

        # Extract current period data
        total_assets = _safe_float(fin_t.get("total_assets"))
        total_liab = _safe_float(fin_t.get("total_liab"))
        total_cur_assets = _safe_float(fin_t.get("total_cur_assets"))
        total_cur_liab = _safe_float(fin_t.get("total_cur_liab"))
        net_profit_t = _safe_float(fin_t.get("net_profit"))

        # Withdraw the net profit of the previous period
        net_profit_t1 = _safe_float(fin_t1.get("net_profit")) if fin_t1 else None

        warnings: list[str] = []
        components: dict[str, Optional[float]] = {}

        if period_mismatch:
            warnings.append(f"口径不一致：当期{_PERIOD_LABELS.get(cur_period_type, cur_period_type)} vs 上期{_PERIOD_LABELS.get(prev_period_type, prev_period_type)}，净利润变化率(X6)已跳过")

        # X1 = log(total assets)
        x1 = math.log(total_assets) if total_assets is not None and total_assets > 0 else None
        components["x1_log_assets"] = x1
        if x1 is None:
            warnings.append("The total assets data is missing or incorrect, and the X1 component is invalid")

        # X2 = Total Liabilities/Total Assets
        x2 = _safe_div(total_liab, total_assets)
        components["x2_debt_ratio"] = x2
        if x2 is None:
            warnings.append("Liability or asset data is missing, and the X2 component is invalid")

        # X3 = working capital/total assets
        working_capital = (
            total_cur_assets - total_cur_liab
            if total_cur_assets is not None and total_cur_liab is not None
            else None
        )
        x3 = _safe_div(working_capital, total_assets)
        components["x3_wc_to_assets"] = x3
        if x3 is None:
            warnings.append("Working capital data is missing and X3 component is invalid")

        # X4 = Current liabilities / current assets
        x4 = _safe_div(total_cur_liab, total_cur_assets)
        components["x4_cl_to_ca"] = x4
        if x4 is None:
            warnings.append("Current liabilities or current assets data are missing, and the X4 component is invalid")

        # X5 = Dummy variable: total liabilities > Total assets is 1 (insolvent)
        x5 = 1.0 if (total_liab is not None and total_assets is not None and total_liab > total_assets) else 0.0
        components["x5_liab_exceeds_assets"] = x5

        # X6 = Net profit change rate: (NI_t - NI_{t-1}) / (|NI_t| + |NI_{t-1}|)
        # 🔑 Skip if the caliber is inconsistent (net profit comparison between quarterly report vs annual report is meaningless)
        x6 = None
        if not period_mismatch and net_profit_t is not None and net_profit_t1 is not None:
            denom = abs(net_profit_t) + abs(net_profit_t1)
            if denom != 0:
                x6 = (net_profit_t - net_profit_t1) / denom
        components["x6_ni_change"] = x6
        if x6 is None and not period_mismatch:
            warnings.append("Insufficient net profit historical data, X6 component is invalid")

        # Calculate O-Score
        valid_components = {k: v for k, v in components.items() if v is not None}
        if len(valid_components) < 4:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"有效数据不足，仅 {len(valid_components)}/6 个分量可用",
                    "symbol": symbol,
                },
                ensure_ascii=False, indent=2, default=str,
            )

        o_score = round(
            -1.32
            - 0.407 * (x1 or 0.0)
            + 6.03 * (x2 or 0.0)
            - 1.43 * (x3 or 0.0)
            + 0.0757 * (x4 or 0.0)
            - 1.72 * x5
            - 0.521 * (x6 or 0.0),
            4,
        )

        # Probability transformation
        probability = round(math.exp(o_score) / (1 + math.exp(o_score)), 4)

        # risk level
        if probability > 0.5:
            risk_level = "high"
        elif probability > 0.15:
            risk_level = "medium"
        else:
            risk_level = "low"

        if len(valid_components) < 6:
            missing = [k for k, v in components.items() if v is None]
            warnings.append(f"部分分量缺失: {missing}，O-Score仅供参考")

        payload = {
            "symbol": symbol,
            "o_score": o_score,
            "probability": probability,
            "risk_level": risk_level,
            "components": components,
            "interpretation": {
                "o_score": o_score,
                "probability": probability,
                "risk_level": risk_level,
            },
            "data_quality": {"warnings": warnings},
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Ohlson O-Score Calculation failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ============================================================================
# Tool 2:  Accounts receivable quality
# ============================================================================

@tool
@register_tool(
    tool_id="get_receivables_quality",
    name="应收账款质量评分",
    description=(
        "Assess the quality of accounts receivable of A-share companies, using a comprehensive score of 0-100 points based on DSO, receivables/revenue ratio, receivables/total assets ratio and year-on-year changes."
        "Here s Quality/Risk It specifically refers to the quality of accounts receivable collection, customer credit risk and asset quality abnormalities, not cash flow quality, earnings quality, data quality or technical signal quality."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["receivables_quality", "asset_quality"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["accounts_receivable_quality_assessment"],
    when_to_use="Used when it is necessary to evaluate the company s ability to collect payments, accounts receivable anomalies, aging/turnover risk, customer credit risk, or the receivable portion of asset quality.",
    when_not_to_use="Not suitable for industries with no accounts receivable or a very high proportion of cash transactions (such as retail supermarkets); not used for cash flow deterioration, earnings quality, inventory quality, data quality or technical trading signal analysis.",
    returns="Returns a JSON string, including metrics, score, flags and data_quality.",
    example="get_receivables_quality(symbol='600519')",
    related_tools=["get_inventory_quality", "get_liquidity_stress_test"],
)
def get_receivables_quality(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Assess the quality of accounts receivable. Comprehensive score of 0-100 points through DSO, receivables/revenue ratio, receivables/total assets ratio and year-on-year change.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            period_type: Current reporting period type,"annual" | "interim" | "q1" | "q3" | "unknown"
            period_caliber: dict, Reporting period caliber information——
                — current: Type of current period
                — previous: Last period type
                — period_mismatch: Is there any inconsistency in caliber?
                — annualized: Whether annualization has been performed
            metrics: dict, Accounts Receivable Metrics——
                — dso_days: Accounts receivable turnover days
                — dso_previous_days: Last issue DSO
                — dso_change_pct: DSO Year-on-year change percentage
                — receivables_to_revenue_pct: Receivables/revenue ratio (percentage)
                — receivables_to_assets_pct: Receivables/Total Assets Ratio (Percent)
                — receivables_growth_pct: Year-on-year growth percentage of receivables
                — revenue_growth_pct: Revenue growth percentage year-on-year
            score: Accounts receivable quality score (0-100, the higher the better; when the caliber is inconsistent, the year-on-year related indicators are None)
            flags: list[str], Triggered bad signal description
            data_quality: dict, Data quality——
                — warnings: list[str], Alarm information
            message: When status is "error" error description when
    """
    try:
        fin_data_list = get_stock_financial_periods(symbol, limit=4)
        if not fin_data_list:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的财务数据", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        fin_cur = fin_data_list[0]

        # 🔑 Test the reporting period caliber to avoid erroneous comparisons of quarterly reports vs. annual reports
        cur_period_type = _detect_period_type(fin_cur)
        cur_factor = _annualize_factor(cur_period_type)
        fin_prev, prev_period_type, period_mismatch = _find_same_period_prev(fin_data_list, cur_period_type)

        warnings: list[str] = []
        flags: list[str] = []

        if cur_period_type != "annual" and cur_period_type != "unknown":
            warnings.append(f"当期为{_PERIOD_LABELS.get(cur_period_type, cur_period_type)}数据，营收已年化处理以消除口径差异")

        if period_mismatch:
            warnings.append(f"口径不一致：当期{_PERIOD_LABELS.get(cur_period_type, cur_period_type)} vs 上期{_PERIOD_LABELS.get(prev_period_type, prev_period_type)}，同比指标已标注口径失真")

        # Extract current period data
        accounts_receiv = _safe_float(fin_cur.get("accounts_receiv"))
        revenue = _safe_float(fin_cur.get("revenue"))
        total_assets = _safe_float(fin_cur.get("total_assets"))

        # 🔑 Annualized revenue (for DSO and receivables/revenue ratio)
        revenue_annualized = revenue * cur_factor if revenue is not None else None

        # Extract previous period data
        ar_prev = _safe_float(fin_prev.get("accounts_receiv")) if fin_prev else None
        rev_prev = _safe_float(fin_prev.get("revenue")) if fin_prev else None
        prev_factor = _annualize_factor(prev_period_type)
        rev_prev_annualized = rev_prev * prev_factor if rev_prev is not None else None

        # DSO (Days Sales Outstanding) — Use annualized revenue
        dso = _safe_div(accounts_receiv, _safe_div(revenue_annualized, 365)) if accounts_receiv is not None and revenue_annualized is not None else None
        dso_prev = _safe_div(ar_prev, _safe_div(rev_prev_annualized, 365)) if ar_prev is not None and rev_prev_annualized is not None else None

        # Receivables/revenue ratio — Use annualized revenue
        receivables_to_revenue = _safe_div(accounts_receiv, revenue_annualized)

        # Receivables/total assets ratio (not affected by revenue caliber)
        receivables_to_assets = _safe_div(accounts_receiv, total_assets)

        # Year-on-year change (only meaningful if the caliber is consistent)
        if period_mismatch:
            # The caliber is inconsistent and the year-on-year calculation is not performed.
            dso_change = None
            ar_growth = None
            rev_growth = None
            warnings.append("Due to inconsistent calibers during the reporting period, year-on-year indicators such as DSO year-on-year growth, receivable growth, and revenue growth have been skipped.")
        else:
            ar_growth = _pct_change(accounts_receiv, ar_prev)
            rev_growth = _pct_change(revenue, rev_prev)  # Compare with original values (same caliber for the same period)
            dso_change = _pct_change(dso, dso_prev) if dso is not None and dso_prev is not None else None

        # Rating (0-100)
        score = 50.0  # Basic points

        if dso is not None:
            if dso > 180:
                score -= 20
                flags.append(f"DSO高达{dso:.1f}天，回款周期极长")
            elif dso > 90:
                score -= 10
                flags.append(f"DSO={dso:.1f}God, the payment is too slow.")
            elif dso > 60:
                score -= 5
            elif dso < 30:
                score += 10
                flags.append(f"DSO仅{dso:.1f}天，回款能力优秀")
        else:
            warnings.append("无法计算DSO")
            score -= 10

        if dso_change is not None:
            if dso_change > 0.20:
                score -= 20
                flags.append(f"DSO同比上升{dso_change*100:.1f}%（>{'20%'}），回款严重恶化")
            elif dso_change > 0.10:
                score -= 10
                flags.append(f"DSO同比上升{dso_change*100:.1f}%，回款趋紧")
            elif dso_change < -0.10:
                score += 5
                flags.append(f"DSO同比下降{abs(dso_change)*100:.1f}%，回款改善")
        else:
            warnings.append("无法计算DSO同比变化")

        if receivables_to_revenue is not None:
            if receivables_to_revenue > 0.5:
                score -= 15
                flags.append(f"应收/营收比高达{receivables_to_revenue*100:.1f}%，营收质量风险高")
            elif receivables_to_revenue > 0.3:
                score -= 8
                flags.append(f"应收/营收比为{receivables_to_revenue*100:.1f}%，偏高")
            elif receivables_to_revenue < 0.1:
                score += 10
                flags.append(f"应收/营收比仅{receivables_to_revenue*100:.1f}%，营收质量优秀")
        else:
            warnings.append("无法计算应收/营收比")

        if ar_growth is not None and rev_growth is not None:
            gap = ar_growth - rev_growth
            if gap > 0.20:
                score -= 15
                flags.append(f"应收增长({ar_growth*100:.1f}%)远超营收增长({rev_growth*100:.1f}%)，信用政策过度宽松")
            elif gap > 0.10:
                score -= 5
                flags.append(f"Receivables are growing faster than revenue, so you need to pay attention")
        elif ar_growth is not None:
            flags.append(f"应收账款同比变动{ar_growth*100:.1f}%（无营收对比）")

        if receivables_to_assets is not None:
            if receivables_to_assets > 0.3:
                score -= 10
                flags.append(f"应收/总资产比{receivables_to_assets*100:.1f}%，资产占压严重")
            elif receivables_to_assets > 0.15:
                score -= 3

        score = max(0.0, min(100.0, score))

        metrics = {
            "dso_days": round(dso, 1) if dso is not None else None,
            "dso_previous_days": round(dso_prev, 1) if dso_prev is not None else None,
            "dso_change_pct": round(dso_change * 100, 1) if dso_change is not None else None,
            "receivables_to_revenue_pct": round(receivables_to_revenue * 100, 1) if receivables_to_revenue is not None else None,
            "receivables_to_assets_pct": round(receivables_to_assets * 100, 1) if receivables_to_assets is not None else None,
            "receivables_growth_pct": round(ar_growth * 100, 1) if ar_growth is not None else None,
            "revenue_growth_pct": round(rev_growth * 100, 1) if rev_growth is not None else None,
        }

        payload = {
            "symbol": symbol,
            "period_type": cur_period_type,
            "period_caliber": {
                "current": cur_period_type,
                "previous": prev_period_type,
                "period_mismatch": period_mismatch,
                "annualized": cur_period_type != "annual" and cur_period_type != "unknown",
            },
            "metrics": metrics,
            "score": round(score, 1),
            "flags": flags,
            "data_quality": {"warnings": warnings},
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Accounts receivable quality assessment failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ============================================================================
# Tool 3:  Inventory quality
# ============================================================================

@tool
@register_tool(
    tool_id="get_inventory_quality",
    name="存货质量评分",
    description="Assess the inventory quality of A-share companies, using a comprehensive score of 0-100 points based on inventory turnover rate, DIO, inventory/revenue ratio and year-on-year changes.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["inventory_quality", "asset_quality"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["inventory_quality_assessment"],
    when_to_use="Used when there is a need to evaluate a company s inventory management efficiency, inventory overstock risk, or working capital efficiency.",
    when_not_to_use="Not applicable to service-oriented businesses or financial companies without inventory.",
    returns="Returns a JSON string, including metrics, score, flags and data_quality.",
    example="get_inventory_quality(symbol='600519')",
    related_tools=["get_receivables_quality", "get_liquidity_stress_test"],
)
def get_inventory_quality(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Assess inventory quality. Comprehensive score of 0-100 points through inventory turnover rate, DIO, inventory/revenue ratio and year-on-year change.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            period_type: Current reporting period type,"annual" | "interim" | "q1" | "q3" | "unknown"
            period_caliber: dict, Reporting period caliber information——
                — current: Type of current period
                — previous: Last period type
                — period_mismatch: Is there any inconsistency in caliber?
                — annualized: Whether annualization has been performed
            metrics: dict, Inventory indicators——
                — inventory_turnover: Inventory turnover rate (times/year)
                — dio_days: Inventory turnover days
                — inventory_to_revenue_pct: Inventory/revenue ratio (percentage)
                — inventory_to_assets_pct: Inventory/total assets ratio (percentage)
                — inventory_to_current_assets_pct: Inventory/current assets ratio (percentage)
                — inventory_growth_pct: Inventory growth percentage year-on-year
                — revenue_growth_pct: Revenue growth percentage year-on-year
            score: Inventory quality score (0-100, higher is better)
            flags: list[str], Triggered bad signal description
            data_quality: dict, Data quality——
                — warnings: list[str], Alarm information
            message: When status is "error" error description when
    """
    try:
        fin_data_list = get_stock_financial_periods(symbol, limit=4)
        if not fin_data_list:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的财务数据", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        fin_cur = fin_data_list[0]

        # 🔑 Test report period caliber
        cur_period_type = _detect_period_type(fin_cur)
        cur_factor = _annualize_factor(cur_period_type)
        fin_prev, prev_period_type, period_mismatch = _find_same_period_prev(fin_data_list, cur_period_type)

        warnings: list[str] = []
        flags: list[str] = []

        if cur_period_type != "annual" and cur_period_type != "unknown":
            warnings.append(f"当期为{_PERIOD_LABELS.get(cur_period_type, cur_period_type)}数据，营收和成本已年化处理")
        if period_mismatch:
            warnings.append(f"口径不一致：当期{_PERIOD_LABELS.get(cur_period_type, cur_period_type)} vs 上期{_PERIOD_LABELS.get(prev_period_type, prev_period_type)}，同比指标已跳过")

        # Extract data
        inventories = _safe_float(fin_cur.get("inventories"))
        revenue = _safe_float(fin_cur.get("revenue"))
        total_assets = _safe_float(fin_cur.get("total_assets"))
        total_cur_assets = _safe_float(fin_cur.get("total_cur_assets"))

        # 🔑 annualized revenue
        revenue_annualized = revenue * cur_factor if revenue is not None else None

        # Operating Costs (Used Revenue - Gross Profit Approximate)
        gross_margin = _safe_float(fin_cur.get("gross_margin"))
        cogs = revenue_annualized * (1 - gross_margin / 100) if revenue_annualized is not None and gross_margin is not None and gross_margin > 1 else None

        # Last period data
        inv_prev = _safe_float(fin_prev.get("inventories")) if fin_prev else None
        rev_prev = _safe_float(fin_prev.get("revenue")) if fin_prev else None
        gm_prev = _safe_float(fin_prev.get("gross_margin")) if fin_prev else None
        prev_factor = _annualize_factor(prev_period_type)
        rev_prev_annualized = rev_prev * prev_factor if rev_prev is not None else None
        cogs_prev = rev_prev_annualized * (1 - gm_prev / 100) if rev_prev_annualized is not None and gm_prev is not None and gm_prev > 1 else None

        # Inventory turnover (using annualized cost)
        inventory_turnover = _safe_div(cogs, inventories) if cogs is not None and inventories is not None else None

        # DIO (Days Inventory Outstanding)
        dio = _safe_div(365, inventory_turnover) if inventory_turnover is not None and inventory_turnover > 0 else None

        # inventory/revenue ratio — Use annualized revenue
        inventory_to_revenue = _safe_div(inventories, revenue_annualized)

        # Inventory/total assets ratio (not affected by revenue caliber)
        inventory_to_assets = _safe_div(inventories, total_assets)

        # Inventory/Current Assets Ratio
        inventory_to_ca = _safe_div(inventories, total_cur_assets)

        # Year-on-year change (only calculated when the caliber is the same)
        if period_mismatch:
            inv_growth = None
            rev_growth = None
        else:
            inv_growth = _pct_change(inventories, inv_prev)
            rev_growth = _pct_change(revenue, rev_prev)

        # Rating (0-100)
        score = 50.0

        if inventory_turnover is not None:
            if inventory_turnover < 1:
                score -= 20
                flags.append(f"存货周转率仅{inventory_turnover:.2f}次/年，周转极慢")
            elif inventory_turnover < 3:
                score -= 10
                flags.append(f"存货周转率为{inventory_turnover:.2f}次/年，偏慢")
            elif inventory_turnover > 10:
                score += 10
                flags.append(f"存货周转率达{inventory_turnover:.2f}次/年，周转优秀")
            elif inventory_turnover > 5:
                score += 5
        else:
            warnings.append("Unable to calculate inventory turnover (insufficient operating cost data)")

        if dio is not None:
            if dio > 365:
                flags.append(f"DIO高达{dio:.1f}天，存货积压超过一年")
            elif dio > 180:
                flags.append(f"DIO={dio:.1f}days, the inventory backlog is heavy")
        else:
            warnings.append("无法计算DIO")

        if inv_growth is not None and rev_growth is not None:
            if inv_growth > rev_growth + 0.20:
                score -= 20
                flags.append(f"存货增长({inv_growth*100:.1f}%)远超营收增长({rev_growth*100:.1f}%)，可能存在滞销")
            elif inv_growth > rev_growth + 0.10:
                score -= 8
                flags.append(f"存货增长快于营收增长")
            elif inv_growth < rev_growth - 0.10:
                score += 5
                flags.append(f"Inventory growth is lower than revenue growth, well managed")
        elif inv_growth is not None:
            flags.append(f"存货同比变动{inv_growth*100:.1f}%（无营收对比）")

        if inventory_to_revenue is not None:
            if inventory_to_revenue > 0.5:
                score -= 15
                flags.append(f"存货/营收比高达{inventory_to_revenue*100:.1f}%, 占压严重")
            elif inventory_to_revenue > 0.25:
                score -= 5
            elif inventory_to_revenue < 0.1:
                score += 10
                flags.append(f"存货/营收比仅{inventory_to_revenue*100:.1f}%，存货管理优秀")
        else:
            warnings.append("无法计算存货/营收比")

        if inventory_to_assets is not None and inventory_to_assets > 0.3:
            score -= 5
            flags.append(f"存货占总资产{inventory_to_assets*100:.1f}%，占比偏高")

        if inventory_to_ca is not None and inventory_to_ca > 0.5:
            score -= 5
            flags.append(f"存货占流动资产{inventory_to_ca*100:.1f}%，流动性风险")

        score = max(0.0, min(100.0, score))

        metrics = {
            "inventory_turnover": round(inventory_turnover, 2) if inventory_turnover is not None else None,
            "dio_days": round(dio, 1) if dio is not None else None,
            "inventory_to_revenue_pct": round(inventory_to_revenue * 100, 1) if inventory_to_revenue is not None else None,
            "inventory_to_assets_pct": round(inventory_to_assets * 100, 1) if inventory_to_assets is not None else None,
            "inventory_to_current_assets_pct": round(inventory_to_ca * 100, 1) if inventory_to_ca is not None else None,
            "inventory_growth_pct": round(inv_growth * 100, 1) if inv_growth is not None else None,
            "revenue_growth_pct": round(rev_growth * 100, 1) if rev_growth is not None else None,
        }

        payload = {
            "symbol": symbol,
            "period_type": cur_period_type,
            "period_caliber": _period_caliber_payload(cur_period_type, prev_period_type, period_mismatch),
            "metrics": metrics,
            "score": round(score, 1),
            "flags": flags,
            "data_quality": {"warnings": warnings},
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("存货质量评估失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ============================================================================
# Tool 4:  Liquidity Stress Test
# ============================================================================

@tool
@register_tool(
    tool_id="get_liquidity_stress_test",
    name="流动性压力测试",
    description="Conduct liquidity stress tests on A-share companies, and simulate liquidity risks under different revenue decline scenarios through indicators such as current ratio, quick ratio, and days of cash coverage.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["liquidity_risk", "stress_testing"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["liquidity_stress_testing"],
    when_to_use="It is used when it is necessary to assess the company s liquidity risk under adverse scenarios such as revenue decline and market tightening.",
    when_not_to_use="Not applicable to companies in the financial industry (different asset and liability structures); the stress test is a simulation analysis and does not constitute an actual forecast.",
    returns="Returns a JSON string containing liquidity_metrics, stress_scenarios and data_quality.",
    example="get_liquidity_stress_test(symbol='600519', revenue_decline_pcts='0.1,0.2,0.3')",
    related_tools=["get_debt_structure_analysis", "get_receivables_quality"],
)
def get_liquidity_stress_test(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    revenue_decline_pcts: Annotated[str, "Revenue decline percentage (comma separated), such as'0.1,0.2,0.3' express 10%/20%/30%"] = "0.1,0.2,0.3",
) -> str:
    """Perform liquidity stress testing. Simulate liquidity risks under different revenue decline scenarios.

    Args:
        symbol: A stock code, such as 600519,000001
        revenue_decline_pcts: Revenue decline percentage (comma separated), default "0.1,0.2,0.3"; 
            Each value will be clamped to [0, 1]; Fallback to default value when parsing fails

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            period_type: Current reporting period type,"annual" | "interim" | "q1" | "q3" | "unknown"
            period_caliber: dict, Reporting period caliber information——
                — current: Type of current period
                — previous: Type of last period (Heng is "unknown") 
                — period_mismatch: Whether there is inconsistency in caliber (always False)
                — annualized: Whether annualization has been performed
            liquidity_metrics: dict, Basic liquidity indicator——
                — current_ratio: current ratio
                — quick_ratio: quick ratio
                — cash_coverage_days: cash coverage days
            stress_scenarios: list[dict], Stressful scenario results, element structure——
                — revenue_decline_pct: Revenue decline ratio
                — stressed_revenue: Pressured revenue
                — stressed_oper_profit: Pressured operating profit
                — stressed_net_profit: Net profit under pressure
                — stressed_current_ratio: stressed current ratio
                — stressed_cash_coverage_days: Days of stressed cash coverage
            data_quality: dict, Data quality——
                — warnings: list[str], Alarm information
            message: When status is "error" error description when
    """
    try:
        fin_data_list = get_stock_financial_periods(symbol, limit=1)
        if not fin_data_list:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的财务数据", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        fin = fin_data_list[0]
        warnings: list[str] = []

        # 🔑 Test report period caliber
        cur_period_type = _detect_period_type(fin)
        cur_factor = _annualize_factor(cur_period_type)
        if cur_period_type != "annual" and cur_period_type != "unknown":
            warnings.append(f"当期为{_PERIOD_LABELS.get(cur_period_type, cur_period_type)}数据，营收已年化处理")

        # Extract data
        total_cur_assets = _safe_float(fin.get("total_cur_assets"))
        total_cur_liab = _safe_float(fin.get("total_cur_liab"))
        total_assets = _safe_float(fin.get("total_assets"))
        total_liab = _safe_float(fin.get("total_liab"))
        inventories = _safe_float(fin.get("inventories"))
        money_cap = _safe_float(fin.get("money_cap"))
        revenue = _safe_float(fin.get("revenue"))
        net_profit = _safe_float(fin.get("net_profit"))
        oper_profit = _safe_float(fin.get("oper_profit"))

        # 🔑 annualized revenue
        revenue_annualized = revenue * cur_factor if revenue is not None else None

        # liquidity indicator
        current_ratio = _safe_div(total_cur_assets, total_cur_liab)

        # quick ratio = (Current assets - inventories) / current liabilities
        quick_assets = (
            total_cur_assets - inventories
            if total_cur_assets is not None and inventories is not None
            else None
        )
        quick_ratio = _safe_div(quick_assets, total_cur_liab)

        # cash coverage days — Use annualized revenue
        daily_opex = _safe_div(revenue_annualized * 0.7, 365) if revenue_annualized is not None else None  # Assuming that operating expenses account for approximately 70%
        cash_coverage_days = _safe_div(money_cap, daily_opex) if money_cap is not None and daily_opex is not None and daily_opex > 0 else None

        if daily_opex is None:
            warnings.append("Average daily operating expenses cannot be calculated, and the number of cash coverage days may be inaccurate")

        liquidity_metrics = {
            "current_ratio": round(current_ratio, 2) if current_ratio is not None else None,
            "quick_ratio": round(quick_ratio, 2) if quick_ratio is not None else None,
            "cash_coverage_days": round(cash_coverage_days, 1) if cash_coverage_days is not None else None,
        }

        # Analyze revenue decline percentage
        try:
            declines = [float(x.strip()) for x in revenue_decline_pcts.split(",") if x.strip()]
            declines = [max(0.0, min(1.0, d)) for d in declines]
        except (ValueError, AttributeError):
            declines = [0.1, 0.2, 0.3]
            warnings.append(f"Failed to parse revenue decline parameter, use default value: {revenue_decline_pcts}")

        if not declines:
            declines = [0.1, 0.2, 0.3]
            warnings.append("The revenue decline parameter is empty and the default value is used.")

        # Stress Scenario Analysis
        stress_scenarios = []
        for pct in sorted(declines):
            # Revenue after revenue decline (based on annualized revenue)
            stressed_revenue = revenue_annualized * (1 - pct) if revenue_annualized is not None else None

            # Assume that fixed costs account for 50% of revenue and variable costs change linearly with revenue.
            # Simulate Cost Structure: Total Cost = 0.5*Original revenue(Fixed) + 0.5*Original revenue*(1-decline rate) = Original revenue*(1 - 0.5*decline rate)
            cost_ratio_after = 1.0 - 0.5 * pct  # Cost to original revenue ratio
            stressed_oper_profit = stressed_revenue - (revenue_annualized * cost_ratio_after) if stressed_revenue is not None and revenue_annualized is not None else None

            # Simulated net profit (assuming tax rate of 25%)
            stressed_net_profit = stressed_oper_profit * 0.75 if stressed_oper_profit is not None else None

            # Simulated current ratio (assuming current assets decline with revenue and current liabilities remain unchanged)
            # Assume that 50% of current assets change with revenue
            if total_cur_assets is not None:
                stressed_ca = total_cur_assets * (1 - 0.5 * pct)
            else:
                stressed_ca = None
            stressed_cr = _safe_div(stressed_ca, total_cur_liab)

            # Cash Coverage Days After Simulation — Use annualized revenue
            stressed_daily_opex = _safe_div(stressed_revenue * 0.7, 365) if stressed_revenue is not None else None
            stressed_cash_coverage = _safe_div(money_cap, stressed_daily_opex) if money_cap is not None and stressed_daily_opex is not None and stressed_daily_opex > 0 else None

            scenario = {
                "revenue_decline_pct": pct,
                "stressed_revenue": round(stressed_revenue, 2) if stressed_revenue is not None else None,
                "stressed_oper_profit": round(stressed_oper_profit, 2) if stressed_oper_profit is not None else None,
                "stressed_net_profit": round(stressed_net_profit, 2) if stressed_net_profit is not None else None,
                "stressed_current_ratio": round(stressed_cr, 2) if stressed_cr is not None else None,
                "stressed_cash_coverage_days": round(stressed_cash_coverage, 1) if stressed_cash_coverage is not None else None,
            }
            stress_scenarios.append(scenario)

        payload = {
            "symbol": symbol,
            "period_type": cur_period_type,
            "period_caliber": _period_caliber_payload(cur_period_type, "unknown", False),
            "liquidity_metrics": liquidity_metrics,
            "stress_scenarios": stress_scenarios,
            "data_quality": {"warnings": warnings},
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Liquidity stress test failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ============================================================================
# Tool 5:  Debt structure analysis
# ============================================================================

@tool
@register_tool(
    tool_id="get_debt_structure_analysis",
    name="债务结构分析",
    description="Analyze the debt structure of A-share companies and give a comprehensive score of 0-100 through indicators such as debt/equity ratio, debt/asset ratio, interest coverage multiple, and short-term debt ratio.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["debt_structure", "solvency_risk"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["debt_structure_analysis"],
    when_to_use="Used when it is necessary to evaluate the company s solvency, debt risk or capital structure rationality.",
    when_not_to_use="Not applicable to companies in the financial industry (high leverage is an industry characteristic); not applicable to insolvent companies (debt ratio>100%) . ",
    returns="Returns a JSON string, including ratios, score, interpretation and data_quality.",
    example="get_debt_structure_analysis(symbol='600519')",
    related_tools=["get_liquidity_stress_test", "get_ohlson_oscore"],
)
def get_debt_structure_analysis(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Analyze debt structure. A comprehensive score of 0-100 is obtained through indicators such as debt/equity ratio, debt/asset ratio, interest coverage ratio, and short-term debt ratio.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            period_type: Current reporting period type,"annual" | "interim" | "q1" | "q3" | "unknown"
            period_caliber: dict, Reporting period caliber information——
                — current: Type of current period
                — previous: Last period type
                — period_mismatch: Is there any inconsistency in caliber?
                — annualized: Whether annualization has been performed
            ratios: dict, debt structure indicator——
                — debt_to_equity: debt/equity ratio
                — debt_to_equity_previous: Last period debt/equity ratio
                — debt_to_equity_change_pct: Year-on-year percentage change in debt/equity ratio
                — debt_to_assets_pct: Debt/total assets ratio (percentage)
                — interest_coverage: Interest coverage multiple (string when infinity) "inf") 
                — short_term_debt_ratio_pct: Short-term debt ratio (percentage)
            score: Debt structure score (0-100, higher is better)
            interpretation: Debt structure interpretation copy
            data_quality: dict, Data quality——
                — warnings: list[str], Alarm information
            message: When status is "error" error description when
    """
    try:
        fin_data_list = get_stock_financial_periods(symbol, limit=4)
        if not fin_data_list:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的财务数据", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        fin_cur = fin_data_list[0]

        # 🔑 Test report period caliber
        cur_period_type = _detect_period_type(fin_cur)
        fin_prev, prev_period_type, period_mismatch = _find_same_period_prev(fin_data_list, cur_period_type)

        warnings: list[str] = []
        if period_mismatch:
            warnings.append(f"口径不一致：当期{_PERIOD_LABELS.get(cur_period_type, cur_period_type)} vs 上期{_PERIOD_LABELS.get(prev_period_type, prev_period_type)}，D/E 同比已跳过")

        # Extract current period data
        total_liab = _safe_float(fin_cur.get("total_liab"))
        total_equity = _safe_float(fin_cur.get("total_equity"))
        total_assets = _safe_float(fin_cur.get("total_assets"))
        total_cur_liab = _safe_float(fin_cur.get("total_cur_liab"))
        oper_profit = _safe_float(fin_cur.get("oper_profit"))
        fin_exp = _safe_float(fin_cur.get("fin_exp"))

        # Extract previous period data for trending
        tl_prev = _safe_float(fin_prev.get("total_liab")) if fin_prev else None
        te_prev = _safe_float(fin_prev.get("total_equity")) if fin_prev else None

        # debt/equity ratio
        debt_to_equity = _safe_div(total_liab, total_equity)

        # Debt/Asset Ratio
        debt_to_assets = _safe_div(total_liab, total_assets)

        # interest coverage ratio = Operating profit / financial expenses
        interest_coverage = _safe_div(oper_profit, fin_exp) if fin_exp is not None and fin_exp != 0 else None
        if fin_exp is not None and fin_exp == 0:
            interest_coverage = float("inf")
            warnings.append("The financial cost is 0 and the interest coverage ratio is considered to be infinite.")

        # Short-term debt ratio (use current liabilities/total liabilities as an approximation)
        short_term_debt_ratio = _safe_div(total_cur_liab, total_liab)

        # Trend — If the caliber is inconsistent, the year-on-year comparison will be skipped.
        if period_mismatch:
            de_change = None
            debt_to_equity_prev = None
        else:
            debt_to_equity_prev = _safe_div(tl_prev, te_prev) if tl_prev is not None and te_prev is not None else None
            de_change = _pct_change(debt_to_equity, debt_to_equity_prev) if debt_to_equity is not None and debt_to_equity_prev is not None else None

        # Rating (0-100)
        score = 50.0

        if debt_to_equity is not None:
            if debt_to_equity > 2.0:
                score -= 20
                warnings.append(f"负债/权益比高达{debt_to_equity:.2f}，杠杆风险极高")
            elif debt_to_equity > 1.0:
                score -= 10
                warnings.append(f"负债/权益比为{debt_to_equity:.2f}，偏高")
            elif debt_to_equity < 0.3:
                score += 10
                warnings.append(f"负债/权益比仅{debt_to_equity:.2f}，杠杆保守")
            else:
                score += 5
        else:
            warnings.append("无法计算负债/权益比")

        if debt_to_assets is not None:
            if debt_to_assets > 0.7:
                score -= 15
            elif debt_to_assets > 0.5:
                score -= 5
            elif debt_to_assets < 0.3:
                score += 10
        else:
            warnings.append("无法计算负债/资产比")

        if interest_coverage is not None and interest_coverage != float("inf"):
            if interest_coverage < 1.0:
                score -= 25
                warnings.append(f"利息覆盖倍数仅{interest_coverage:.2f}，利润不足以覆盖利息支出")
            elif interest_coverage < 2.0:
                score -= 15
                warnings.append(f"利息覆盖倍数={interest_coverage:.2f}，偿债能力偏弱")
            elif interest_coverage > 5.0:
                score += 10
                warnings.append(f"利息覆盖倍数达{interest_coverage:.2f}，偿债能力优秀")
            elif interest_coverage > 3.0:
                score += 5
        elif interest_coverage is None:
            warnings.append("无法计算利息覆盖倍数")

        if short_term_debt_ratio is not None:
            if short_term_debt_ratio > 0.8:
                score -= 15
                warnings.append(f"短期债务占比{short_term_debt_ratio*100:.1f}%，流动性压力大")
            elif short_term_debt_ratio > 0.6:
                score -= 5
                warnings.append(f"短期债务占比{short_term_debt_ratio*100:.1f}%，偏高")
            elif short_term_debt_ratio < 0.3:
                score += 10
            else:
                score += 5
        else:
            warnings.append("无法计算短期债务占比")

        if de_change is not None:
            if de_change > 0.20:
                score -= 10
                warnings.append(f"负债/权益比同比上升{de_change*100:.1f}%，杠杆加速")
            elif de_change < -0.10:
                score += 5
                warnings.append(f"负债/权益比同比下降{abs(de_change)*100:.1f}%，杠杆改善")

        score = max(0.0, min(100.0, score))

        # Interpretation
        if score >= 80:
            interpretation = "The debt structure is very healthy and the debt repayment ability is strong"
        elif score >= 60:
            interpretation = "The debt structure is reasonable and risks are controllable"
        elif score >= 40:
            interpretation = "The debt structure requires attention, as there are certain debt repayment risks."
        elif score >= 20:
            interpretation = "Poor debt structure and high debt repayment pressure"
        else:
            interpretation = "The debt structure is dangerous and may face a debt repayment crisis"

        ratios = {
            "debt_to_equity": round(debt_to_equity, 2) if debt_to_equity is not None else None,
            "debt_to_equity_previous": round(debt_to_equity_prev, 2) if debt_to_equity_prev is not None else None,
            "debt_to_equity_change_pct": round(de_change * 100, 1) if de_change is not None else None,
            "debt_to_assets_pct": round(debt_to_assets * 100, 1) if debt_to_assets is not None else None,
            "interest_coverage": round(interest_coverage, 2) if interest_coverage is not None and interest_coverage != float("inf") else ("inf" if interest_coverage == float("inf") else None),
            "short_term_debt_ratio_pct": round(short_term_debt_ratio * 100, 1) if short_term_debt_ratio is not None else None,
        }

        payload = {
            "symbol": symbol,
            "period_type": cur_period_type,
            "period_caliber": _period_caliber_payload(cur_period_type, prev_period_type, period_mismatch),
            "ratios": ratios,
            "score": round(score, 1),
            "interpretation": interpretation,
            "data_quality": {"warnings": warnings},
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("债务结构分析失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = [
    "get_ohlson_oscore",
    "get_receivables_quality",
    "get_inventory_quality",
    "get_liquidity_stress_test",
    "get_debt_structure_analysis",
]
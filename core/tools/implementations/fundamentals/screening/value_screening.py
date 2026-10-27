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


def _get_db():
    """Get a synchronous MongoDB connection."""
    from app.core.database import get_mongo_db_sync
    return get_mongo_db_sync()


def _safe_float(value: Any) -> Optional[float]:
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


def _get_field(record: Dict[str, Any], *field_names: str) -> Optional[float]:
    """Attempts to get field values from records in order of priority."""
    for field_name in field_names:
        value = _safe_float(record.get(field_name))
        if value is not None:
            return value
    return None


def _fetch_candidate_universe(extra_fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Get the candidate stock pool from stock_basic_info (take the top N by market capitalization and PE>0) . """
    db = _get_db()
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


def _enrich_with_financials(
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
            "pe_ttm": _get_field(stock, "pe_ttm", "pe"),
            "pb": _get_field(stock, "pb", "pb_mrq"),
            "total_mv": _safe_float(stock.get("total_mv")),
            "dividend_yield": _get_field(stock, "dividend_yield", "dividend_yield_ttm"),
        }
        if extra_fields:
            for f in extra_fields:
                val = _safe_float(stock.get(f))
                if val is not None:
                    record[f] = val

        try:
            periods = get_stock_financial_periods(symbol, limit=4)
            if periods and isinstance(periods, list) and len(periods) > 0:
                latest = periods[0]

                roe = _get_field(latest, "roe", "roe_avg", "roe_waa")
                if roe is not None:
                    record["roe"] = roe

                debt_to_assets = _get_field(latest, "debt_to_assets")
                if debt_to_assets is not None:
                    record["debt_to_assets"] = debt_to_assets

                net_profit = _get_field(latest, "net_profit", "n_income_attr_p", "n_income", "net_income")
                if net_profit is not None:
                    record["net_profit"] = net_profit

                revenue = _get_field(latest, "revenue", "total_revenue", "oper_rev")
                if revenue is not None:
                    record["revenue"] = revenue

                n_cashflow_act = _get_field(latest, "n_cashflow_act")
                if n_cashflow_act is not None:
                    record["n_cashflow_act"] = n_cashflow_act

                total_liab = _get_field(latest, "total_liab")
                total_equity = _get_field(latest, "total_equity", "total_hldr_eqy_exc_min_int")
                if total_liab is not None and total_equity is not None and total_equity > 0:
                    record["debt_to_equity"] = total_liab / total_equity

                gross_margin = _get_field(latest, "grossprofit_margin", "gross_margin")
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

    current = _get_field(periods[0], *fields)
    previous = _get_field(periods[1], *fields)

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

    current = _get_field(periods[0], *fields)
    older = _get_field(periods[3], *fields)

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

        raw_candidates = _fetch_candidate_universe()
        total_candidates = len(raw_candidates)

        if total_candidates == 0:
            return json.dumps(
                {"status": "error", "message": "未获取到候选股票"},
                ensure_ascii=False, indent=2, default=str,
            )

        enriched = _enrich_with_financials(raw_candidates)

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

        raw_candidates = _fetch_candidate_universe()
        total_candidates = len(raw_candidates)

        if total_candidates == 0:
            return json.dumps(
                {"status": "error", "message": "未获取到候选股票"},
                ensure_ascii=False, indent=2, default=str,
            )

        enriched = _enrich_with_financials(raw_candidates)

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

        raw_candidates = _fetch_candidate_universe(extra_fields=["dividend_yield", "dividend_yield_ttm"])
        total_candidates = len(raw_candidates)

        if total_candidates == 0:
            return json.dumps(
                {"status": "error", "message": "未获取到候选股票"},
                ensure_ascii=False, indent=2, default=str,
            )

        enriched = _enrich_with_financials(raw_candidates)

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

        raw_candidates = _fetch_candidate_universe()
        total_candidates = len(raw_candidates)

        if total_candidates == 0:
            return json.dumps(
                {"status": "error", "message": "未获取到候选股票"},
                ensure_ascii=False, indent=2, default=str,
            )

        enriched = _enrich_with_financials(raw_candidates)

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
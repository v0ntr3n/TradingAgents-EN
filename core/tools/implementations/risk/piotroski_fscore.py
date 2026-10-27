"""Piotroski F-Score Fundamental Quality Scoring Tool"""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from core.skill_runtime.standard_financial_apis import get_historical_financial_annual_series
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


@tool
@register_tool(
    tool_id="get_piotroski_fscore",
    name="Piotroski F-Score Fundamental Quality Score",
    description="Based on the Piotroski F-Score model, the company s fundamental quality is evaluated from three dimensions: profitability, leveraged liquidity, and operating efficiency (a total of 9 points).",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["fundamental_quality", "value_investing"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["fundamental_quality_screening"],
    when_to_use="Use when you need to assess the strength of a company s fundamentals, screen for value investing, or identify signs of financial improvement/deterioration.",
    when_not_to_use="Not used for short-term trading signals; F-Score evaluates fundamental quality rather than short-term momentum.",
    returns="Returns a JSON string containing f_score, rating, categories, comparison and data_quality.",
    example="get_piotroski_fscore(symbol='600519')",
    related_tools=["get_altman_zscore", "get_beneish_mscore"],
)
def get_piotroski_fscore(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Calculate the Piotroski F-Score fundamental quality score. Evaluated from three dimensions: profitability, leveraged liquidity and operational efficiency (out of 9 points).

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, field description——
            status: "error" exists; this field is not included when successful
            symbol: Underlying stock code
            f_score: F-Score Overall score (out of 9)
            rating: rating,"high quality" (≥7)  | "Neutral" (4-6)  | "Weak" (≤3) 
            categories: dict, Three categories of ratings——
                — profitability: dict, Profitability (out of 4)——
                    — score: score
                    — max: Full marks 4
                    — details: dict, 4 Boolean items——
                        — p1_roa_positive: current period ROA > 0
                        — p2_ocf_positive: Current operating cash flow > 0
                        — p3_delta_roa_positive: ROA Year-on-year increase
                        — p4_ocf_gt_netprofit: operating cash flow > net profit
                — leverage_liquidity: dict, Leverage/Liquidity (out of 3)——
                    — score / max
                    — details: dict, 3 Boolean items——
                        — p5_deleveraging: Asset-liability ratio decreases
                        — p6_liquidity_improving: Current ratio rises
                        — p7_no_dilution: No equity dilution
                — operating_efficiency: dict, Operational efficiency (out of 2)——
                    — score / max
                    — details: dict, 2 Boolean items——
                        — p8_gross_margin_improving: Gross profit margin increased
                        — p9_asset_turnover_improving: Asset turnover rate rises
            comparison: dict, Compare years——
                — current_year: current year
                — prior_year: Last issue year
            data_quality: dict, Data quality——
                — warnings: list[str], Alarm information
            message: When status is "error" error description when
    """
    try:
        # Obtain annual report data for the past three years (requires the current year + At least 1 year before)
        annual_data = get_historical_financial_annual_series(symbol, years=3)
        records = annual_data.get("records") or []

        if len(records) < 2:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"There is insufficient data in the annual report and only the {len(records)} Annual data, at least 2 years required",
                    "symbol": symbol,
                },
                ensure_ascii=False, indent=2, default=str,
            )

        # records Sort by year in descending order (newest first)
        current = records[0]
        prior = records[1]

        warnings: list[str] = list(annual_data.get("warnings") or [])

        current_year = current.get("year")
        prior_year = prior.get("year")

        # =========== Profitability (4 points) ===========
        profitability_details = {}

        # P1: ROA > 0 (current year)
        roa_cur = _safe_float(current.get("roa"))
        p1_roa_positive = (roa_cur or 0) > 0
        profitability_details["p1_roa_positive"] = p1_roa_positive

        # P2: Operating Cash Flow > 0 (current year)
        ocf_cur = _safe_float(current.get("operating_cashflow"))
        p2_ocf_positive = (ocf_cur or 0) > 0
        profitability_details["p2_ocf_positive"] = p2_ocf_positive

        # P3: ΔROA > 0 (current - prior)
        roa_prior = _safe_float(prior.get("roa"))
        delta_roa = (roa_cur - roa_prior) if roa_cur is not None and roa_prior is not None else None
        p3_delta_roa = (delta_roa or 0) > 0
        profitability_details["p3_delta_roa_positive"] = p3_delta_roa

        # P4: Operating Cash Flow > Net Profit (accrual quality)
        net_profit_cur = _safe_float(current.get("net_profit"))
        p4_ocf_gt_np = (ocf_cur or 0) > (net_profit_cur or 0) if ocf_cur is not None and net_profit_cur is not None else False
        profitability_details["p4_ocf_gt_netprofit"] = p4_ocf_gt_np

        profitability_score = sum(
            [p1_roa_positive, p2_ocf_positive, p3_delta_roa, p4_ocf_gt_np]
        )

        # =========== Leverage/Liquidity (3 points) ===========
        leverage_details = {}

        # P5: Δ(debt_to_assets) < 0 (deleveraging)
        debt_cur = _safe_float(current.get("debt_to_assets"))
        debt_prior = _safe_float(prior.get("debt_to_assets"))
        delta_debt = (debt_cur - debt_prior) if debt_cur is not None and debt_prior is not None else None
        p5_delta_debt = (delta_debt or 0) < 0
        leverage_details["p5_deleveraging"] = p5_delta_debt

        # P6: Δ(current_ratio) > 0 (liquidity improving)
        cr_cur = _safe_float(current.get("current_ratio"))
        cr_prior = _safe_float(prior.get("current_ratio"))
        delta_cr = (cr_cur - cr_prior) if cr_cur is not None and cr_prior is not None else None
        p6_delta_cr = (delta_cr or 0) > 0
        leverage_details["p6_liquidity_improving"] = p6_delta_cr

        # P7: No new shares issued → total_equity growth <= revenue growth
        equity_cur = _safe_float(current.get("total_equity"))
        equity_prior = _safe_float(prior.get("total_equity"))
        revenue_cur = _safe_float(current.get("revenue"))
        revenue_prior = _safe_float(prior.get("revenue"))

        equity_growth = _safe_div(equity_cur, equity_prior) if equity_cur is not None and equity_prior is not None else None
        revenue_growth = _safe_div(revenue_cur, revenue_prior) if revenue_cur is not None and revenue_prior is not None else None
        p7_no_dilution = (
            (equity_growth or 0) <= (revenue_growth or 0)
            if equity_growth is not None and revenue_growth is not None
            else False
        )
        leverage_details["p7_no_dilution"] = p7_no_dilution

        leverage_score = sum([p5_delta_debt, p6_delta_cr, p7_no_dilution])

        # =========== operational efficiency (2 points) ===========
        efficiency_details = {}

        # P8: Δ(gross_margin) > 0
        gm_cur = _safe_float(current.get("gross_margin"))
        gm_prior = _safe_float(prior.get("gross_margin"))
        delta_gm = (gm_cur - gm_prior) if gm_cur is not None and gm_prior is not None else None
        p8_delta_gm = (delta_gm or 0) > 0
        efficiency_details["p8_gross_margin_improving"] = p8_delta_gm

        # P9: Δ(asset_turnover) > 0 (revenue / total_assets)
        ta_cur = _safe_float(current.get("total_assets"))
        ta_prior = _safe_float(prior.get("total_assets"))
        at_cur = _safe_div(revenue_cur, ta_cur)
        at_prior = _safe_div(revenue_prior, ta_prior)
        delta_at = (at_cur - at_prior) if at_cur is not None and at_prior is not None else None
        p9_delta_at = (delta_at or 0) > 0
        efficiency_details["p9_asset_turnover_improving"] = p9_delta_at

        efficiency_score = sum([p8_delta_gm, p9_delta_at])

        # =========== Overall score and rating ===========
        total_score = profitability_score + leverage_score + efficiency_score

        if total_score >= 7:
            rating = "优质"
        elif total_score >= 4:
            rating = "中性"
        else:
            rating = "弱势"

        if len(records) < 3:
            warnings.append(f"仅获取到 {len(records)} 年数据，评分可能不够稳健")

        payload = {
            "symbol": symbol,
            "f_score": total_score,
            "rating": rating,
            "categories": {
                "profitability": {
                    "score": profitability_score,
                    "max": 4,
                    "details": profitability_details,
                },
                "leverage_liquidity": {
                    "score": leverage_score,
                    "max": 3,
                    "details": leverage_details,
                },
                "operating_efficiency": {
                    "score": efficiency_score,
                    "max": 2,
                    "details": efficiency_details,
                },
            },
            "comparison": {
                "current_year": current_year,
                "prior_year": prior_year,
            },
            "data_quality": {"warnings": warnings},
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Piotroski F-Score Calculation failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = ["get_piotroski_fscore"]

"""盈利质量评分工具"""

import json
import logging
from typing import Annotated

import numpy as np

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
    tool_id="get_earnings_quality_score",
    name="盈利质量评分",
    description=(
        "The company s profitability quality is evaluated from five dimensions: accrual quality, cash flow stability, profitability sustainability, free cash flow coverage and the impact of one-time items, with a total score of 100 points."
        "Here s quality It refers to earnings authenticity, sustainability and accounting quality, not data quality, reporting quality, product quality, technical signal quality or pure cash flow statement analysis."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["earnings_quality", "accounting_quality"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["earnings_quality_assessment"],
    when_to_use="Used when it is necessary to evaluate the authenticity of the company s earnings, earnings sustainability, accounting quality, accrual risk, and cash flow coverage of earnings.",
    when_not_to_use="Not used for short-term earnings forecasts; not used for data quality checks, report quality reviews, technical signals, or trading capital flow analysis; earnings quality scores measure historical quality rather than future earnings.",
    returns="Returns a JSON string containing total_score, rating, dimensions and data_quality.",
    example="get_earnings_quality_score(symbol='600519')",
    related_tools=["get_beneish_mscore", "get_piotroski_fscore"],
)
def get_earnings_quality_score(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Assess the quality of company earnings. Scores are scored from five dimensions: accrual quality, cash flow stability, profitability sustainability, free cash flow coverage and the impact of one-time items.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, field description——
            status: "error" exists; this field is not included when successful
            symbol: Underlying stock code
            total_score: Total score (out of 100)
            rating: rating,"high quality" | "good" | "Average" | "Poor" | "Poor"
            dimensions: dict, Rating across five dimensions (maximum score 20 for each dimension)——
                — accrual_quality: dict, Accrual quality——
                    — score: score
                    — max: Full marks 20
                    — value: Accrual ratio mean (None if insufficient data)
                — cashflow_stability: dict, cash flow stability——
                    — score: score
                    — max: Full marks 20
                    — value: Operating cash flow coefficient of variation (None if data is insufficient)
                — earnings_persistence: dict, Profitability sustainability——
                    — score: score
                    — max: Full marks 20
                    — detail: Proportion of positive growth years copywriting
                — fcf_coverage: dict, free cash flow coverage——
                    — score: score
                    — max: Full marks 20
                    — value: Free cash flow / net profit mean (None if data is insufficient)
                — recurring_quality: dict, Impact of one-time items (net interest rate stability)——
                    — score: score
                    — max: Full marks 20
                    — value: Standard deviation of net interest rate (None if data is insufficient)
            data_quality: dict, Data quality——
                — years_available: Number of years of annual reports available
                — warnings: list[str], Alarm information
            message: When status is "error" error description when
    """
    try:
        # Get 5-year annual report data
        annual_data = get_historical_financial_annual_series(symbol, years=5)
        records = annual_data.get("records") or []
        warnings: list[str] = list(annual_data.get("warnings") or [])

        if len(records) < 2:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"There is insufficient data in the annual report and only the {len(records)} Annual data, at least 2 years required",
                    "symbol": symbol,
                },
                ensure_ascii=False, indent=2, default=str,
            )

        if len(records) < 5:
            warnings.append(f"Ideally, 5 years of data are required, currently only{len(records)}Years later, scoring reliability decreased")

        # Sort records in ascending order by year (facilitates calculation of growth rate)
        sorted_records = sorted(records, key=lambda r: r.get("year") or 0)

        n = len(sorted_records)

        # Extract key fields
        net_profits = [_safe_float(r.get("net_profit")) for r in sorted_records]
        operating_cashflows = [_safe_float(r.get("operating_cashflow")) for r in sorted_records]
        free_cashflows = [_safe_float(r.get("free_cashflow")) for r in sorted_records]
        netprofit_margins = [_safe_float(r.get("netprofit_margin")) for r in sorted_records]

        # ===== D1: Accrual quality (20pts) =====
        # mean(abs(net_profit - operating_cashflow) / abs(net_profit))
        accrual_ratios = []
        for np_val, ocf_val in zip(net_profits, operating_cashflows):
            if np_val is not None and ocf_val is not None and np_val != 0:
                accrual_ratios.append(abs(np_val - ocf_val) / abs(np_val))

        if accrual_ratios:
            mean_accrual_ratio = float(np.mean(accrual_ratios))
            d1_score = max(0.0, min(20.0, 20.0 - mean_accrual_ratio * 20.0))
        else:
            mean_accrual_ratio = None
            d1_score = 10.0
            warnings.append("Accrual quality cannot be calculated, intermediate points have been assigned")

        # ===== D2: cash flow stability (20pts) =====
        valid_ocfs = [v for v in operating_cashflows if v is not None]
        if len(valid_ocfs) >= 2:
            mean_ocf = float(np.mean(valid_ocfs))
            if mean_ocf != 0:
                cv_ocf = float(np.std(valid_ocfs, ddof=1)) / abs(mean_ocf)
            else:
                cv_ocf = float(np.std(valid_ocfs, ddof=1))
            d2_score = max(0.0, min(20.0, 20.0 - cv_ocf * 40.0))
        else:
            cv_ocf = None
            d2_score = 10.0
            warnings.append("Insufficient data on cash flow stability, an intermediate score has been assigned")

        # ===== D3: Profitability sustainability (20pts) =====
        positive_growth_years = 0
        total_growth_years = 0
        for i in range(1, n):
            cur_np = net_profits[i]
            prev_np = net_profits[i - 1]
            if cur_np is not None and prev_np is not None:
                total_growth_years += 1
                if cur_np > prev_np:
                    positive_growth_years += 1

        if total_growth_years > 0:
            d3_score = (positive_growth_years / total_growth_years) * 20.0
        else:
            d3_score = 10.0

        # ===== D4: free cash flow coverage (20pts) =====
        fcf_coverage_ratios = []
        for fcf_val, np_val in zip(free_cashflows, net_profits):
            if fcf_val is not None and np_val is not None and np_val > 0:
                fcf_coverage_ratios.append(fcf_val / np_val)

        if fcf_coverage_ratios:
            mean_fcf_coverage = float(np.mean(fcf_coverage_ratios))
            # >0.8 = full marks
            d4_score = max(0.0, min(20.0, (mean_fcf_coverage / 0.8) * 20.0))
        else:
            mean_fcf_coverage = None
            d4_score = 10.0
            warnings.append("Insufficient free cash flow coverage data, middle points have been assigned")

        # ===== D5: One-time project impact (20pts) =====
        valid_margins = [v for v in netprofit_margins if v is not None]
        if len(valid_margins) >= 2:
            # netprofit_margin It is already a percentage (for example, 30 means 30%), and the decimal form is processed here.
            # First determine the value range: if most of the values > 1 is treated as a percentage
            if float(np.mean(valid_margins)) > 1:
                # Percentage form, converted to decimal
                valid_margins_dec = [v / 100.0 for v in valid_margins]
            else:
                valid_margins_dec = valid_margins
            std_margin = float(np.std(valid_margins_dec, ddof=1))
            d5_score = max(0.0, min(20.0, 20.0 - std_margin * 200.0))
        else:
            std_margin = None
            d5_score = 10.0
            warnings.append("Insufficient net interest rate data, an intermediate score has been assigned")

        # ===== Overall score and rating =====
        total_score = round(d1_score + d2_score + d3_score + d4_score + d5_score, 1)

        if total_score >= 80:
            rating = "优质"
        elif total_score >= 60:
            rating = "良好"
        elif total_score >= 40:
            rating = "一般"
        elif total_score >= 20:
            rating = "较差"
        else:
            rating = "差"

        payload = {
            "symbol": symbol,
            "total_score": total_score,
            "rating": rating,
            "dimensions": {
                "accrual_quality": {
                    "score": round(d1_score, 1),
                    "max": 20,
                    "value": round(mean_accrual_ratio, 4) if mean_accrual_ratio is not None else None,
                },
                "cashflow_stability": {
                    "score": round(d2_score, 1),
                    "max": 20,
                    "value": round(cv_ocf, 4) if cv_ocf is not None else None,
                },
                "earnings_persistence": {
                    "score": round(d3_score, 1),
                    "max": 20,
                    "detail": f"{positive_growth_years}/{total_growth_years} years growth",
                },
                "fcf_coverage": {
                    "score": round(d4_score, 1),
                    "max": 20,
                    "value": round(mean_fcf_coverage, 4) if mean_fcf_coverage is not None else None,
                },
                "recurring_quality": {
                    "score": round(d5_score, 1),
                    "max": 20,
                    "value": round(std_margin, 4) if std_margin is not None else None,
                },
            },
            "data_quality": {
                "years_available": n,
                "warnings": warnings,
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Earnings quality score calculation failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = ["get_earnings_quality_score"]

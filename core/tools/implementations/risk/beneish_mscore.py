"""Beneish M-Score Earnings Manipulation Probability Assessment Tool"""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_financial_periods
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


def _match_financial_period_by_year(
    fin_periods: list[dict], year: int
) -> dict | None:
    """Match annual report records for a specified year from financial period data"""
    for record in fin_periods:
        report_period = str(record.get("report_period") or record.get("report_date") or "")
        report_type = str(record.get("report_type") or "").lower()
        # Annual report type filter
        if report_type and report_type not in ("annual", "yearly", "年报"):
            continue
        # Extract the year from report_period (format such as 20231231)
        clean = report_period.replace("-", "").replace("/", "")
        if len(clean) >= 8 and clean[:4] == str(year):
            return record
    return None


@tool
@register_tool(
    tool_id="get_beneish_mscore",
    name="Beneish M-Score Probability of earnings manipulation",
    description="Evaluate the company s earnings manipulation probability based on the Beneish M-Score model, and detect potential earnings management behavior through changes in eight financial ratios.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["earnings_manipulation", "accounting_quality"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["accounting_fraud_detection"],
    when_to_use="Used when it is necessary to evaluate the company s earnings quality and identify potential accounting manipulation or financial fraud risks.",
    when_not_to_use="M-Score It cannot replace in-depth due diligence; a high score only indicates a higher probability of manipulation, which requires comprehensive judgment combined with other information.",
    returns="Returns a JSON string, including m_score, interpretation, threshold, components and data_quality.",
    example="get_beneish_mscore(symbol='600519')",
    related_tools=["get_altman_zscore", "get_piotroski_fscore"],
)
def get_beneish_mscore(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Calculate the Beneish M-Score probability of earnings manipulation. Detect potential earnings management behavior through changes in 8 financial ratios.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, field description——
            status: "error" exists; this field is not included when successful
            symbol: Underlying stock code
            m_score: M-Score Score (above threshold -1.78 indicates higher probability of manipulation)
            interpretation: Interpret the text,"The probability of earnings manipulation is high" | "The probability of earnings manipulation is low"
            threshold: Decision threshold (-1.78)
            components: dict, 8 components, each component is {value, weight, contribution}——
                — dsri: Accounts receivable turnover days index
                — gmi: gross profit index
                — aqi: Asset Quality Index
                — sgi: sales growth index
                — depi: Depreciation index (default 1.0)
                — sgai: Sales and administrative expense index (default 1.0)
                — tata: Total accruals/total assets
                — lvgi: Leverage Index
            data_quality: dict, Data quality——
                — years_available: Number of years of annual reports available
                — depi_defaulted: Whether to use the default value for the depreciation index
                — sgai_defaulted: Whether to use the default value for the sales and management expense index
                — warnings: list[str], Alarm information
            message: When status is "error" error description when
    """
    try:
        warnings: list[str] = []

        # Get the annual report sequence (requires the current year + previous year)
        annual_data = get_historical_financial_annual_series(symbol, years=3)
        records = annual_data.get("records") or []
        warnings.extend(annual_data.get("warnings") or [])

        if len(records) < 2:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"There is insufficient data in the annual report and only the {len(records)} Annual data, at least 2 years required",
                    "symbol": symbol,
                },
                ensure_ascii=False, indent=2, default=str,
            )

        current = records[0]
        prior = records[1]

        current_year = current.get("year")
        prior_year = prior.get("year")

        # Get financial period data (for accounts_receiv and total_cur_assets)
        fin_periods = get_stock_financial_periods(symbol, limit=30)

        fin_cur = _match_financial_period_by_year(fin_periods, current_year) if current_year else None
        fin_prior = _match_financial_period_by_year(fin_periods, prior_year) if prior_year else None

        # Extract basic fields from annual report sequence
        revenue_cur = _safe_float(current.get("revenue"))
        revenue_prior = _safe_float(prior.get("revenue"))
        net_profit_cur = _safe_float(current.get("net_profit"))
        ocf_cur = _safe_float(current.get("operating_cashflow"))
        ta_cur = _safe_float(current.get("total_assets"))
        ta_prior = _safe_float(prior.get("total_assets"))
        tl_cur = _safe_float(current.get("total_liab"))
        tl_prior = _safe_float(prior.get("total_liab"))
        gm_cur = _safe_float(current.get("gross_margin"))
        gm_prior = _safe_float(prior.get("gross_margin"))

        # Extract accounts_receiv and total_cur_assets
        ar_cur = _safe_float(fin_cur.get("accounts_receiv")) if fin_cur else None
        ar_prior = _safe_float(fin_prior.get("accounts_receiv")) if fin_prior else None
        tca_cur = _safe_float(fin_cur.get("total_cur_assets")) if fin_cur else None
        tca_prior = _safe_float(fin_prior.get("total_cur_assets")) if fin_prior else None

        if ar_cur is None or ar_prior is None:
            warnings.append("Accounts receivable data is missing, DSRI uses default values 1.0")
        if tca_cur is None or tca_prior is None:
            warnings.append("Current asset data is missing and AQI uses default values.1.0")

        # ---- DSRI: Days Sales in Receivables Index ----
        dsri_ratio_cur = _safe_div(ar_cur, revenue_cur)
        dsri_ratio_prior = _safe_div(ar_prior, revenue_prior)
        dsri = _safe_div(dsri_ratio_cur, dsri_ratio_prior) if dsri_ratio_cur is not None and dsri_ratio_prior is not None else 1.0

        # ---- GMI: Gross Margin Index (inverse) ----
        gmi = _safe_div(gm_prior, gm_cur) if gm_cur is not None and gm_prior is not None else 1.0

        # ---- AQI: Asset Quality Index ----
        # Approximately: (non_current / total_assets)_t / (non_current / total_assets)_t-1
        nc_ratio_cur = (
            _safe_div((ta_cur or 0) - (tca_cur or 0), ta_cur)
            if ta_cur is not None and tca_cur is not None
            else None
        )
        nc_ratio_prior = (
            _safe_div((ta_prior or 0) - (tca_prior or 0), ta_prior)
            if ta_prior is not None and tca_prior is not None
            else None
        )
        aqi = _safe_div(nc_ratio_cur, nc_ratio_prior) if nc_ratio_cur is not None and nc_ratio_prior is not None else 1.0

        # ---- SGI: Sales Growth Index ----
        sgi = _safe_div(revenue_cur, revenue_prior) if revenue_cur is not None and revenue_prior is not None else 1.0

        # ---- DEPI: Depreciation Index ----
        depi = 1.0
        depi_defaulted = True
        if depi_defaulted:
            warnings.append("depreciation index(DEPI)Use the default value of 1.0 due to lack of depreciation data")

        # ---- SGAI: SG&A Index ----
        # Lack of admin_exp data, default 1.0
        sgai = 1.0
        warnings.append("Sales and administrative expense index(SGAI)Use the default value of 1.0 due to lack of overhead data")

        # ---- TATA: Total Accruals to Total Assets ----
        tata = _safe_div(
            (net_profit_cur or 0) - (ocf_cur or 0),
            ta_cur,
        ) if net_profit_cur is not None and ocf_cur is not None and ta_cur is not None else 0.0

        # ---- LVGI: Leverage Index ----
        lvgi_ratio_cur = _safe_div(tl_cur, ta_cur)
        lvgi_ratio_prior = _safe_div(tl_prior, ta_prior)
        lvgi = _safe_div(lvgi_ratio_cur, lvgi_ratio_prior) if lvgi_ratio_cur is not None and lvgi_ratio_prior is not None else 1.0

        # 8 variables and weights
        variables = {
            "dsri": {"value": dsri or 0.0, "weight": 0.92},
            "gmi": {"value": gmi or 0.0, "weight": 0.528},
            "aqi": {"value": aqi or 0.0, "weight": 0.404},
            "sgi": {"value": sgi or 0.0, "weight": 0.892},
            "depi": {"value": depi or 0.0, "weight": 0.115},
            "sgai": {"value": sgai or 0.0, "weight": -0.172},
            "tata": {"value": tata or 0.0, "weight": 4.679},
            "lvgi": {"value": lvgi or 0.0, "weight": -0.327},
        }

        # Calculate M-Score
        m_score = -4.84
        components = {}
        for key, item in variables.items():
            contribution = round(item["value"] * item["weight"], 4)
            m_score += contribution
            components[key] = {
                "value": round(item["value"], 4),
                "weight": item["weight"],
                "contribution": contribution,
            }

        m_score = round(m_score, 4)

        threshold = -1.78
        if m_score > threshold:
            interpretation = "盈余操纵概率较高"
        else:
            interpretation = "盈余操纵概率较低"

        payload = {
            "symbol": symbol,
            "m_score": m_score,
            "interpretation": interpretation,
            "threshold": threshold,
            "components": components,
            "data_quality": {
                "years_available": len(records),
                "depi_defaulted": depi_defaulted,
                "sgai_defaulted": True,
                "warnings": warnings,
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Beneish M-Score Calculation failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = ["get_beneish_mscore"]

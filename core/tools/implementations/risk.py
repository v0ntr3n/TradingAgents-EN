from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['altman_zscore', 'beneish_mscore', 'earnings_quality', 'extended_risk_models', 'fraud_signals', 'piotroski_fscore']:
    _sys.modules[f"{__name__}.{_sub}"] = _self_mod
    _top = _sub.split(".")[0]
    setattr(_self_mod, _top, _self_mod)

# === altman_zscore ===
"""Altman Z-Score Bankruptcy Risk Scoring Tool"""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_financial_periods
from core.skill_runtime.standard_financial_apis import get_security_master
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _altman_zscore_safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _altman_zscore_safe_div(numerator, denominator) -> float | None:
    n = _altman_zscore_safe_float(numerator)
    d = _altman_zscore_safe_float(denominator)
    if n is None or d is None or d == 0:
        return None
    return n / d


@tool
@register_tool(
    tool_id="get_altman_zscore",
    name="Altman Z-Score Bankruptcy Risk Score",
    description="Evaluate the bankruptcy risk of A-share companies based on the Altman Z-Score model, comprehensively considering the five dimensions of working capital, retained earnings, EBIT, market value and sales revenue.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["bankruptcy_risk", "financial_health"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["bankruptcy_risk_assessment"],
    when_to_use="Used when there is a need to assess a company s bankruptcy risk, financial health, or identify signs of financial distress.",
    when_not_to_use="Not used for short-term trading decisions; Z-Score only reflects long-term financial risk.",
    returns="Returns a JSON string, including z_score, zone, components, raw_data, interpretation and data_quality.",
    example="get_altman_zscore(symbol='600519')",
    related_tools=["get_piotroski_fscore", "get_beneish_mscore"],
)
def get_altman_zscore(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Calculate the Altman Z-Score bankruptcy risk score. Comprehensively consider the five dimensions of working capital, retained earnings, EBIT, market value and sales revenue.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            period_type: Current reporting period type,"annual" | "interim" | "q1" | "q3" | "unknown"
            period_caliber: Reporting period caliber information
            z_score: Z-Score Rating
            zone: risk zoning,"safe zone" | "gray area" | "bankruptcy risk area"
            components: dict, five servings——
                — x1_wc_to_ta: working capital/total assets
                — x2_re_to_ta: Retained earnings / total assets (approximate)
                — x3_ebit_to_ta: EBIT / total assets
                — x4_mve_to_tl: Market capitalization/total liabilities
                — x5_sales_to_ta: Annualized revenue/total assets
            raw_data: dict, raw data——
                — working_capital: working capital
                — total_assets: total assets
                — ebit: Operating Profit (EBIT Proxy)
                — market_cap: Market value
                — total_liabilities: total liabilities
                — revenue: Revenue during the reporting period (not annualized)
            interpretation: dict, Rating interpretation——
                — score: Z-Score
                — zone: risk zoning
                — bankruptcy_risk: bankruptcy risk level,"low" | "medium" | "high"
            data_quality: dict, Data quality——
                — warnings: list[str], Alarm information
            message: When status is "error" error description when
    """
    try:
        # Get the latest financial data
        fin_data_list = get_stock_financial_periods(symbol, limit=1)
        if not fin_data_list:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的财务数据", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        fin = fin_data_list[0]

        # 🔑 Test report period caliber
        cur_period_type = _detect_period_type(fin)
        cur_factor = _annualize_factor(cur_period_type)

        # Get market capitalization
        master = get_security_master(symbol)
        market_cap = _altman_zscore_safe_float(master.get("market_cap"))

        # Extract raw data
        total_cur_assets = _altman_zscore_safe_float(fin.get("total_cur_assets"))
        total_cur_liab = _altman_zscore_safe_float(fin.get("total_cur_liab"))
        total_assets = _altman_zscore_safe_float(fin.get("total_assets"))
        total_equity = _altman_zscore_safe_float(fin.get("total_equity"))
        total_liab = _altman_zscore_safe_float(fin.get("total_liab"))
        oper_profit = _altman_zscore_safe_float(fin.get("oper_profit"))
        revenue = _altman_zscore_safe_float(fin.get("revenue"))

        # 🔑 Annualized revenue (X5 component requires annual revenue)
        revenue_annualized = revenue * cur_factor if revenue is not None else None

        # Calculate working capital
        working_capital = (
            total_cur_assets - total_cur_liab
            if total_cur_assets is not None and total_cur_liab is not None
            else None
        )

        warnings: list[str] = []

        if cur_period_type != "annual" and cur_period_type != "unknown":
            warnings.append(f"当期为{_PERIOD_LABELS.get(cur_period_type, cur_period_type)}数据，营收已年化处理以消除口径差异")

        # X1 = working capital/total assets
        x1_wc_to_ta = _altman_zscore_safe_div(working_capital, total_assets)

        # X2 = Retained earnings / total assets (approximately: total_equity / total_assets * 0.5) 
        equity_to_assets = _altman_zscore_safe_div(total_equity, total_assets)
        x2_re_to_ta = equity_to_assets * 0.5 if equity_to_assets is not None else None
        if equity_to_assets is not None:
            warnings.append("X2 Retained earnings use approximation (net assets/total assets×0.5) , Unreal retained earnings data")

        # X3 = EBIT / Total assets (using operating profit as a proxy for EBIT)
        x3_ebit_to_ta = _altman_zscore_safe_div(oper_profit, total_assets)
        if oper_profit is not None:
            warnings.append("X3 Using operating profit as a proxy for EBIT")

        # X4 = Market capitalization/total liabilities
        x4_mve_to_tl = _altman_zscore_safe_div(market_cap, total_liab)

        # X5 = sales revenue/total assets — Use annualized revenue
        x5_sales_to_ta = _altman_zscore_safe_div(revenue_annualized, total_assets)

        # Calculate Z-Score
        components = {
            "x1_wc_to_ta": x1_wc_to_ta,
            "x2_re_to_ta": x2_re_to_ta,
            "x3_ebit_to_ta": x3_ebit_to_ta,
            "x4_mve_to_tl": x4_mve_to_tl,
            "x5_sales_to_ta": x5_sales_to_ta,
        }

        valid_components = {k: v for k, v in components.items() if v is not None}
        if len(valid_components) < 3:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"有效数据不足，仅 {len(valid_components)}/5 个分量可用",
                    "symbol": symbol,
                },
                ensure_ascii=False, indent=2, default=str,
            )

        z_score = round(
            (1.2 * (x1_wc_to_ta or 0.0))
            + (1.4 * (x2_re_to_ta or 0.0))
            + (3.3 * (x3_ebit_to_ta or 0.0))
            + (0.6 * (x4_mve_to_tl or 0.0))
            + (1.0 * (x5_sales_to_ta or 0.0)),
            2,
        )

        if z_score > 3.0:
            zone = "安全区"
            bankruptcy_risk = "low"
        elif z_score >= 1.8:
            zone = "灰色区"
            bankruptcy_risk = "medium"
        else:
            zone = "破产风险区"
            bankruptcy_risk = "high"

        if len(valid_components) < 5:
            missing = [k for k, v in components.items() if v is None]
            warnings.append(f"部分分量缺失: {missing}，Z-Score仅供参考")

        payload = {
            "symbol": symbol,
            "period_type": cur_period_type,
            "period_caliber": _period_caliber_payload(cur_period_type, "unknown", False),
            "z_score": z_score,
            "zone": zone,
            "components": components,
            "raw_data": {
                "working_capital": working_capital,
                "total_assets": total_assets,
                "ebit": oper_profit,
                "market_cap": market_cap,
                "total_liabilities": total_liab,
                "revenue": revenue,
            },
            "interpretation": {
                "score": z_score,
                "zone": zone,
                "bankruptcy_risk": bankruptcy_risk,
            },
            "data_quality": {"warnings": warnings},
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Altman Z-Score Calculation failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = ["get_altman_zscore"]

# === beneish_mscore ===
"""Beneish M-Score Earnings Manipulation Probability Assessment Tool"""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_financial_periods
from core.skill_runtime.standard_financial_apis import get_historical_financial_annual_series
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _beneish_mscore_safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _beneish_mscore_safe_div(numerator, denominator) -> float | None:
    n = _beneish_mscore_safe_float(numerator)
    d = _beneish_mscore_safe_float(denominator)
    if n is None or d is None or d == 0:
        return None
    return n / d


def _beneish_mscore_match_financial_period_by_year(
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

        fin_cur = _beneish_mscore_match_financial_period_by_year(fin_periods, current_year) if current_year else None
        fin_prior = _beneish_mscore_match_financial_period_by_year(fin_periods, prior_year) if prior_year else None

        # Extract basic fields from annual report sequence
        revenue_cur = _beneish_mscore_safe_float(current.get("revenue"))
        revenue_prior = _beneish_mscore_safe_float(prior.get("revenue"))
        net_profit_cur = _beneish_mscore_safe_float(current.get("net_profit"))
        ocf_cur = _beneish_mscore_safe_float(current.get("operating_cashflow"))
        ta_cur = _beneish_mscore_safe_float(current.get("total_assets"))
        ta_prior = _beneish_mscore_safe_float(prior.get("total_assets"))
        tl_cur = _beneish_mscore_safe_float(current.get("total_liab"))
        tl_prior = _beneish_mscore_safe_float(prior.get("total_liab"))
        gm_cur = _beneish_mscore_safe_float(current.get("gross_margin"))
        gm_prior = _beneish_mscore_safe_float(prior.get("gross_margin"))

        # Extract accounts_receiv and total_cur_assets
        ar_cur = _beneish_mscore_safe_float(fin_cur.get("accounts_receiv")) if fin_cur else None
        ar_prior = _beneish_mscore_safe_float(fin_prior.get("accounts_receiv")) if fin_prior else None
        tca_cur = _beneish_mscore_safe_float(fin_cur.get("total_cur_assets")) if fin_cur else None
        tca_prior = _beneish_mscore_safe_float(fin_prior.get("total_cur_assets")) if fin_prior else None

        if ar_cur is None or ar_prior is None:
            warnings.append("Accounts receivable data is missing, DSRI uses default values 1.0")
        if tca_cur is None or tca_prior is None:
            warnings.append("Current asset data is missing and AQI uses default values.1.0")

        # ---- DSRI: Days Sales in Receivables Index ----
        dsri_ratio_cur = _beneish_mscore_safe_div(ar_cur, revenue_cur)
        dsri_ratio_prior = _beneish_mscore_safe_div(ar_prior, revenue_prior)
        dsri = _beneish_mscore_safe_div(dsri_ratio_cur, dsri_ratio_prior) if dsri_ratio_cur is not None and dsri_ratio_prior is not None else 1.0

        # ---- GMI: Gross Margin Index (inverse) ----
        gmi = _beneish_mscore_safe_div(gm_prior, gm_cur) if gm_cur is not None and gm_prior is not None else 1.0

        # ---- AQI: Asset Quality Index ----
        # Approximately: (non_current / total_assets)_t / (non_current / total_assets)_t-1
        nc_ratio_cur = (
            _beneish_mscore_safe_div((ta_cur or 0) - (tca_cur or 0), ta_cur)
            if ta_cur is not None and tca_cur is not None
            else None
        )
        nc_ratio_prior = (
            _beneish_mscore_safe_div((ta_prior or 0) - (tca_prior or 0), ta_prior)
            if ta_prior is not None and tca_prior is not None
            else None
        )
        aqi = _beneish_mscore_safe_div(nc_ratio_cur, nc_ratio_prior) if nc_ratio_cur is not None and nc_ratio_prior is not None else 1.0

        # ---- SGI: Sales Growth Index ----
        sgi = _beneish_mscore_safe_div(revenue_cur, revenue_prior) if revenue_cur is not None and revenue_prior is not None else 1.0

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
        tata = _beneish_mscore_safe_div(
            (net_profit_cur or 0) - (ocf_cur or 0),
            ta_cur,
        ) if net_profit_cur is not None and ocf_cur is not None and ta_cur is not None else 0.0

        # ---- LVGI: Leverage Index ----
        lvgi_ratio_cur = _beneish_mscore_safe_div(tl_cur, ta_cur)
        lvgi_ratio_prior = _beneish_mscore_safe_div(tl_prior, ta_prior)
        lvgi = _beneish_mscore_safe_div(lvgi_ratio_cur, lvgi_ratio_prior) if lvgi_ratio_cur is not None and lvgi_ratio_prior is not None else 1.0

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

# === earnings_quality ===
"""盈利质量评分工具"""

import json
import logging
from typing import Annotated

import numpy as np

from langchain_core.tools import tool

from core.skill_runtime.standard_financial_apis import get_historical_financial_annual_series
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _earnings_quality_safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _earnings_quality_safe_div(numerator, denominator) -> float | None:
    n = _earnings_quality_safe_float(numerator)
    d = _earnings_quality_safe_float(denominator)
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
        net_profits = [_earnings_quality_safe_float(r.get("net_profit")) for r in sorted_records]
        operating_cashflows = [_earnings_quality_safe_float(r.get("operating_cashflow")) for r in sorted_records]
        free_cashflows = [_earnings_quality_safe_float(r.get("free_cashflow")) for r in sorted_records]
        netprofit_margins = [_earnings_quality_safe_float(r.get("netprofit_margin")) for r in sorted_records]

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

# === extended_risk_models ===
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


def _extended_risk_models_safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _extended_risk_models_safe_div(numerator, denominator) -> float | None:
    n = _extended_risk_models_safe_float(numerator)
    d = _extended_risk_models_safe_float(denominator)
    if n is None or d is None or d == 0:
        return None
    return n / d


def _extended_risk_models_pct_change(current, previous) -> float | None:
    c = _extended_risk_models_safe_float(current)
    p = _extended_risk_models_safe_float(previous)
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
        total_assets = _extended_risk_models_safe_float(fin_t.get("total_assets"))
        total_liab = _extended_risk_models_safe_float(fin_t.get("total_liab"))
        total_cur_assets = _extended_risk_models_safe_float(fin_t.get("total_cur_assets"))
        total_cur_liab = _extended_risk_models_safe_float(fin_t.get("total_cur_liab"))
        net_profit_t = _extended_risk_models_safe_float(fin_t.get("net_profit"))

        # Withdraw the net profit of the previous period
        net_profit_t1 = _extended_risk_models_safe_float(fin_t1.get("net_profit")) if fin_t1 else None

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
        x2 = _extended_risk_models_safe_div(total_liab, total_assets)
        components["x2_debt_ratio"] = x2
        if x2 is None:
            warnings.append("Liability or asset data is missing, and the X2 component is invalid")

        # X3 = working capital/total assets
        working_capital = (
            total_cur_assets - total_cur_liab
            if total_cur_assets is not None and total_cur_liab is not None
            else None
        )
        x3 = _extended_risk_models_safe_div(working_capital, total_assets)
        components["x3_wc_to_assets"] = x3
        if x3 is None:
            warnings.append("Working capital data is missing and X3 component is invalid")

        # X4 = Current liabilities / current assets
        x4 = _extended_risk_models_safe_div(total_cur_liab, total_cur_assets)
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
        accounts_receiv = _extended_risk_models_safe_float(fin_cur.get("accounts_receiv"))
        revenue = _extended_risk_models_safe_float(fin_cur.get("revenue"))
        total_assets = _extended_risk_models_safe_float(fin_cur.get("total_assets"))

        # 🔑 Annualized revenue (for DSO and receivables/revenue ratio)
        revenue_annualized = revenue * cur_factor if revenue is not None else None

        # Extract previous period data
        ar_prev = _extended_risk_models_safe_float(fin_prev.get("accounts_receiv")) if fin_prev else None
        rev_prev = _extended_risk_models_safe_float(fin_prev.get("revenue")) if fin_prev else None
        prev_factor = _annualize_factor(prev_period_type)
        rev_prev_annualized = rev_prev * prev_factor if rev_prev is not None else None

        # DSO (Days Sales Outstanding) — Use annualized revenue
        dso = _extended_risk_models_safe_div(accounts_receiv, _extended_risk_models_safe_div(revenue_annualized, 365)) if accounts_receiv is not None and revenue_annualized is not None else None
        dso_prev = _extended_risk_models_safe_div(ar_prev, _extended_risk_models_safe_div(rev_prev_annualized, 365)) if ar_prev is not None and rev_prev_annualized is not None else None

        # Receivables/revenue ratio — Use annualized revenue
        receivables_to_revenue = _extended_risk_models_safe_div(accounts_receiv, revenue_annualized)

        # Receivables/total assets ratio (not affected by revenue caliber)
        receivables_to_assets = _extended_risk_models_safe_div(accounts_receiv, total_assets)

        # Year-on-year change (only meaningful if the caliber is consistent)
        if period_mismatch:
            # The caliber is inconsistent and the year-on-year calculation is not performed.
            dso_change = None
            ar_growth = None
            rev_growth = None
            warnings.append("Due to inconsistent calibers during the reporting period, year-on-year indicators such as DSO year-on-year growth, receivable growth, and revenue growth have been skipped.")
        else:
            ar_growth = _extended_risk_models_pct_change(accounts_receiv, ar_prev)
            rev_growth = _extended_risk_models_pct_change(revenue, rev_prev)  # Compare with original values (same caliber for the same period)
            dso_change = _extended_risk_models_pct_change(dso, dso_prev) if dso is not None and dso_prev is not None else None

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
                flags.append("Receivables are growing faster than revenue, so you need to pay attention")
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
        inventories = _extended_risk_models_safe_float(fin_cur.get("inventories"))
        revenue = _extended_risk_models_safe_float(fin_cur.get("revenue"))
        total_assets = _extended_risk_models_safe_float(fin_cur.get("total_assets"))
        total_cur_assets = _extended_risk_models_safe_float(fin_cur.get("total_cur_assets"))

        # 🔑 annualized revenue
        revenue_annualized = revenue * cur_factor if revenue is not None else None

        # Operating Costs (Used Revenue - Gross Profit Approximate)
        gross_margin = _extended_risk_models_safe_float(fin_cur.get("gross_margin"))
        cogs = revenue_annualized * (1 - gross_margin / 100) if revenue_annualized is not None and gross_margin is not None and gross_margin > 1 else None

        # Last period data
        inv_prev = _extended_risk_models_safe_float(fin_prev.get("inventories")) if fin_prev else None
        rev_prev = _extended_risk_models_safe_float(fin_prev.get("revenue")) if fin_prev else None
        gm_prev = _extended_risk_models_safe_float(fin_prev.get("gross_margin")) if fin_prev else None
        prev_factor = _annualize_factor(prev_period_type)
        rev_prev_annualized = rev_prev * prev_factor if rev_prev is not None else None
        cogs_prev = rev_prev_annualized * (1 - gm_prev / 100) if rev_prev_annualized is not None and gm_prev is not None and gm_prev > 1 else None

        # Inventory turnover (using annualized cost)
        inventory_turnover = _extended_risk_models_safe_div(cogs, inventories) if cogs is not None and inventories is not None else None

        # DIO (Days Inventory Outstanding)
        dio = _extended_risk_models_safe_div(365, inventory_turnover) if inventory_turnover is not None and inventory_turnover > 0 else None

        # inventory/revenue ratio — Use annualized revenue
        inventory_to_revenue = _extended_risk_models_safe_div(inventories, revenue_annualized)

        # Inventory/total assets ratio (not affected by revenue caliber)
        inventory_to_assets = _extended_risk_models_safe_div(inventories, total_assets)

        # Inventory/Current Assets Ratio
        inventory_to_ca = _extended_risk_models_safe_div(inventories, total_cur_assets)

        # Year-on-year change (only calculated when the caliber is the same)
        if period_mismatch:
            inv_growth = None
            rev_growth = None
        else:
            inv_growth = _extended_risk_models_pct_change(inventories, inv_prev)
            rev_growth = _extended_risk_models_pct_change(revenue, rev_prev)

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
                flags.append("存货增长快于营收增长")
            elif inv_growth < rev_growth - 0.10:
                score += 5
                flags.append("Inventory growth is lower than revenue growth, well managed")
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
        total_cur_assets = _extended_risk_models_safe_float(fin.get("total_cur_assets"))
        total_cur_liab = _extended_risk_models_safe_float(fin.get("total_cur_liab"))
        total_assets = _extended_risk_models_safe_float(fin.get("total_assets"))
        total_liab = _extended_risk_models_safe_float(fin.get("total_liab"))
        inventories = _extended_risk_models_safe_float(fin.get("inventories"))
        money_cap = _extended_risk_models_safe_float(fin.get("money_cap"))
        revenue = _extended_risk_models_safe_float(fin.get("revenue"))
        net_profit = _extended_risk_models_safe_float(fin.get("net_profit"))
        oper_profit = _extended_risk_models_safe_float(fin.get("oper_profit"))

        # 🔑 annualized revenue
        revenue_annualized = revenue * cur_factor if revenue is not None else None

        # liquidity indicator
        current_ratio = _extended_risk_models_safe_div(total_cur_assets, total_cur_liab)

        # quick ratio = (Current assets - inventories) / current liabilities
        quick_assets = (
            total_cur_assets - inventories
            if total_cur_assets is not None and inventories is not None
            else None
        )
        quick_ratio = _extended_risk_models_safe_div(quick_assets, total_cur_liab)

        # cash coverage days — Use annualized revenue
        daily_opex = _extended_risk_models_safe_div(revenue_annualized * 0.7, 365) if revenue_annualized is not None else None  # Assuming that operating expenses account for approximately 70%
        cash_coverage_days = _extended_risk_models_safe_div(money_cap, daily_opex) if money_cap is not None and daily_opex is not None and daily_opex > 0 else None

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
            stressed_cr = _extended_risk_models_safe_div(stressed_ca, total_cur_liab)

            # Cash Coverage Days After Simulation — Use annualized revenue
            stressed_daily_opex = _extended_risk_models_safe_div(stressed_revenue * 0.7, 365) if stressed_revenue is not None else None
            stressed_cash_coverage = _extended_risk_models_safe_div(money_cap, stressed_daily_opex) if money_cap is not None and stressed_daily_opex is not None and stressed_daily_opex > 0 else None

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
        total_liab = _extended_risk_models_safe_float(fin_cur.get("total_liab"))
        total_equity = _extended_risk_models_safe_float(fin_cur.get("total_equity"))
        total_assets = _extended_risk_models_safe_float(fin_cur.get("total_assets"))
        total_cur_liab = _extended_risk_models_safe_float(fin_cur.get("total_cur_liab"))
        oper_profit = _extended_risk_models_safe_float(fin_cur.get("oper_profit"))
        fin_exp = _extended_risk_models_safe_float(fin_cur.get("fin_exp"))

        # Extract previous period data for trending
        tl_prev = _extended_risk_models_safe_float(fin_prev.get("total_liab")) if fin_prev else None
        te_prev = _extended_risk_models_safe_float(fin_prev.get("total_equity")) if fin_prev else None

        # debt/equity ratio
        debt_to_equity = _extended_risk_models_safe_div(total_liab, total_equity)

        # Debt/Asset Ratio
        debt_to_assets = _extended_risk_models_safe_div(total_liab, total_assets)

        # interest coverage ratio = Operating profit / financial expenses
        interest_coverage = _extended_risk_models_safe_div(oper_profit, fin_exp) if fin_exp is not None and fin_exp != 0 else None
        if fin_exp is not None and fin_exp == 0:
            interest_coverage = float("inf")
            warnings.append("The financial cost is 0 and the interest coverage ratio is considered to be infinite.")

        # Short-term debt ratio (use current liabilities/total liabilities as an approximation)
        short_term_debt_ratio = _extended_risk_models_safe_div(total_cur_liab, total_liab)

        # Trend — If the caliber is inconsistent, the year-on-year comparison will be skipped.
        if period_mismatch:
            de_change = None
            debt_to_equity_prev = None
        else:
            debt_to_equity_prev = _extended_risk_models_safe_div(tl_prev, te_prev) if tl_prev is not None and te_prev is not None else None
            de_change = _extended_risk_models_pct_change(debt_to_equity, debt_to_equity_prev) if debt_to_equity is not None and debt_to_equity_prev is not None else None

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

# === fraud_signals ===
"""财务造假信号检测工具"""

import json
import logging
from typing import Annotated

import numpy as np
from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_financial_periods
from core.skill_runtime.standard_financial_apis import (
    get_cashflow_quality_trend,
    get_historical_financial_annual_series,
)
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _fraud_signals_safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _fraud_signals_safe_div(numerator, denominator) -> float | None:
    n = _fraud_signals_safe_float(numerator)
    d = _fraud_signals_safe_float(denominator)
    if n is None or d is None or d == 0:
        return None
    return n / d


def _fraud_signals_pct_change(current, previous) -> float | None:
    c = _fraud_signals_safe_float(current)
    p = _fraud_signals_safe_float(previous)
    if c is None or p is None or p == 0:
        return None
    return (c - p) / abs(p)


def _fraud_signals_match_financial_period_by_year(fin_periods: list[dict], year: int) -> dict | None:
    """Match financial period data by year, giving priority to annual reports (reporting periods ending on December 31)."""
    # First round: look for annual reports first (report_period ends with 12-31)
    for record in fin_periods:
        report_period = str(record.get("report_period") or record.get("report_date") or "")
        clean = report_period.replace("-", "").replace("/", "")
        if len(clean) >= 8 and clean[:4] == str(year) and clean[4:8] == "1231":
            return record
    # Round 2: Check the report_type field
    for record in fin_periods:
        report_period = str(record.get("report_period") or record.get("report_date") or "")
        clean = report_period.replace("-", "").replace("/", "")
        report_type = str(record.get("report_type") or record.get("statement_type") or "").lower()
        if len(clean) >= 8 and clean[:4] == str(year) and report_type in ("annual", "yearly", "年报"):
            return record
    # The third round: the next best thing is to find any reporting period in that year (but it may be marked as not an annual report)
    for record in fin_periods:
        report_period = str(record.get("report_period") or record.get("report_date") or "")
        clean = report_period.replace("-", "").replace("/", "")
        if len(clean) >= 8 and clean[:4] == str(year):
            return record
    return None


@tool
@register_tool(
    tool_id="get_financial_fraud_signals",
    name="财务造假信号检测",
    description="Detect financial fraud signals from seven dimensions: revenue recognition, profit quality, asset abnormalities, related transactions, cash flow, gross profit margin and expense capitalization, with a comprehensive score of 0-100 points.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["fraud_detection", "accounting_quality", "financial_risk", "cashflow_deterioration", "cashflow_quality"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["financial_fraud_screening", "financial_risk_signal_detection", "cashflow_quality_analysis"],
    when_to_use="Use it when you need to screen for financial fraud risks, discover accounting abnormal signals, identify cash flow abnormalities/deterioration, or assess the credibility of financial reports.",
    when_not_to_use="Not applicable to companies that do not disclose full annual reports; scoring is based on public financial data and is not a substitute for in-depth due diligence.",
    returns="Returns a JSON string, including total_score, rating, categories sub-scores and signals, data_quality.",
    example="get_financial_fraud_signals(symbol='600519')",
    related_tools=["get_earnings_quality_score", "get_beneish_mscore"],
)
def get_financial_fraud_signals(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Detecting signs of financial fraud. Comprehensive scoring from seven dimensions: revenue recognition, profit quality, asset abnormalities, related transactions, cash flow, gross profit margin and expense capitalization.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, field description——
            status: "error" exists; this field is not included when successful
            symbol: Underlying stock code
            total_score: Total score (out of 100, the higher the score, the more suspicious)
            rating: risk rating,"normal" | "Need attention" | "suspicious" | "highly suspicious"
            categories: dict, Seven Dimensions Scores and Signals——
                — revenue_recognition: dict, Revenue recognition anomalies (out of 20 points)——
                    — score: score
                    — max: Full marks 20
                    — signals: list[str], Signal description
                — earnings_quality: dict, Abnormal profit quality (full score 20)——
                    — score / max / signals
                — asset_irregularities: dict, Asset anomalies (out of 15 points)——
                    — score / max / signals
                — related_party: dict, Related transaction signals (out of 15 points)——
                    — score / max / signals
                — cash_flow: dict, Cash flow anomalies (out of 15 points)——
                    — score / max / signals
                — margin_anomalies: dict, Abnormal gross profit margin (out of 10)——
                    — score / max / signals
                — capitalization: dict, Expense Capitalization Signal (out of 5)——
                    — score / max / signals
            warnings: list[str], Alarm information generated during the process
            data_quality: dict, Data quality——
                — years_available: Number of years of annual reports available
            message: When status is "error" error description when
    """
    try:
        warnings: list[str] = []

        # Get annual report series (at least 2 years required)
        annual_data = get_historical_financial_annual_series(symbol, years=5)
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

        if len(records) < 3:
            warnings.append("With only 2 annual report data, some year-on-year indicators cannot be calculated, and the reliability of the scores is limited.")

        # Sort by year in ascending order for easy calculation
        sorted_records = sorted(records, key=lambda r: r.get("year") or 0)
        n = len(sorted_records)
        latest = sorted_records[-1]
        latest_year = latest.get("year")
        prior = sorted_records[-2] if n >= 2 else None
        prior_year = prior.get("year") if prior else None

        # Get financial period data (for accounts_receiv, inventories, total_cur_assets etc.)
        fin_periods = get_stock_financial_periods(symbol, limit=30)
        fin_cur = _fraud_signals_match_financial_period_by_year(fin_periods, latest_year) if latest_year else None
        fin_prior = _fraud_signals_match_financial_period_by_year(fin_periods, prior_year) if prior_year else None

        # 🔑 Check whether the matching period is the annual report caliber
        def _is_annual_period(fin: dict | None) -> bool:
            if not fin:
                return True  # No alarm when there is no data
            rp = str(fin.get("report_period") or fin.get("report_date") or "")
            return rp[:10].endswith("12-31") or rp.replace("-", "").endswith("1231")

        if fin_cur and not _is_annual_period(fin_cur):
            warnings.append(f"当期({latest_year})匹配到非年报期间数据，DSO等指标可能存在口径偏差")
        if fin_prior and not _is_annual_period(fin_prior):
            warnings.append(f"上期({prior_year})匹配到非年报期间数据，同比比较可能存在口径偏差")

        # Get cash flow quality trends
        cf_trend_data = get_cashflow_quality_trend(symbol, years=5)
        cf_trend = cf_trend_data.get("trend") or []

        # ===== Extract basic fields =====
        rev_cur = _fraud_signals_safe_float(latest.get("revenue"))
        rev_prior = _fraud_signals_safe_float(prior.get("revenue")) if prior else None
        np_cur = _fraud_signals_safe_float(latest.get("net_profit"))
        np_prior = _fraud_signals_safe_float(prior.get("net_profit")) if prior else None
        ocf_cur = _fraud_signals_safe_float(latest.get("operating_cashflow"))
        ocf_prior = _fraud_signals_safe_float(prior.get("operating_cashflow")) if prior else None
        ta_cur = _fraud_signals_safe_float(latest.get("total_assets"))
        ta_prior = _fraud_signals_safe_float(prior.get("total_assets")) if prior else None
        tl_cur = _fraud_signals_safe_float(latest.get("total_liab"))
        te_cur = _fraud_signals_safe_float(latest.get("total_equity"))
        gm_cur = _fraud_signals_safe_float(latest.get("gross_margin"))
        gm_prior = _fraud_signals_safe_float(prior.get("gross_margin")) if prior else None
        npm_cur = _fraud_signals_safe_float(latest.get("netprofit_margin"))

        # financial period fields
        ar_cur = _fraud_signals_safe_float(fin_cur.get("accounts_receiv")) if fin_cur else None
        ar_prior = _fraud_signals_safe_float(fin_prior.get("accounts_receiv")) if fin_prior else None
        inv_cur = _fraud_signals_safe_float(fin_cur.get("inventories")) if fin_cur else None
        inv_prior = _fraud_signals_safe_float(fin_prior.get("inventories")) if fin_prior else None
        tca_cur = _fraud_signals_safe_float(fin_cur.get("total_cur_assets")) if fin_cur else None
        tca_prior = _fraud_signals_safe_float(fin_prior.get("total_cur_assets")) if fin_prior else None
        tcl_cur = _fraud_signals_safe_float(fin_cur.get("total_cur_liab")) if fin_cur else None
        fe_cur = _fraud_signals_safe_float(fin_cur.get("fin_exp")) if fin_cur else None

        # ======================================================================
        # D1: Revenue recognition exception (20pts)
        # ======================================================================
        d1_score = 0.0
        d1_signals: list[str] = []

        revenue_growth = _fraud_signals_pct_change(rev_cur, rev_prior) if rev_cur is not None and rev_prior is not None else None
        ocf_growth = _fraud_signals_pct_change(ocf_cur, ocf_prior) if ocf_cur is not None and ocf_prior is not None else None

        # 1a: Revenue growing much faster than OCF
        if revenue_growth is not None and ocf_growth is not None:
            divergence = revenue_growth - ocf_growth
            if divergence > 0.30:
                severity = min(1.0, (divergence - 0.30) / 0.50)
                d1_score += 10.0 * severity
                d1_signals.append(f"营收增长({revenue_growth*100:.1f}%)远超经营现金流增长({ocf_growth*100:.1f}%)， divergence={divergence*100:.1f}%")
            elif divergence > 0.15:
                d1_score += 5.0
                d1_signals.append(f"The difference between revenue and operating cash flow growth is too large({divergence*100:.1f}%)")
            else:
                d1_signals.append(f"Revenue and operating cash flow growth basically match(divergence={divergence*100:.1f}%)")

        # 1b: DSO (Days Sales Outstanding) change
        # 🔑 Annualized revenue: Quarterly reported revenue is a cumulative value, which needs to be annualized before it can be used for DSO calculations.
        cur_period = _detect_period_type(fin_cur) if fin_cur else "unknown"
        prev_period = _detect_period_type(fin_prior) if fin_prior else "unknown"
        cur_factor = _annualize_factor(cur_period)
        prev_factor = _annualize_factor(prev_period)
        rev_cur_ann = rev_cur * cur_factor if rev_cur is not None else None
        rev_prior_ann = rev_prior * prev_factor if rev_prior is not None else None

        if cur_period != "annual" and cur_period != "unknown":
            warnings.append(f"当期利润表为{_PERIOD_LABELS.get(cur_period, cur_period)}口径，DSO计算已使用年化营收")
        if prev_period != "annual" and prev_period != "unknown":
            warnings.append(f"上期利润表为{_PERIOD_LABELS.get(prev_period, prev_period)}口径，DSO计算已使用年化营收")

        dso_cur = _fraud_signals_safe_div(ar_cur, _fraud_signals_safe_div(rev_cur_ann, 365)) if ar_cur is not None and rev_cur_ann is not None else None
        dso_prior = _fraud_signals_safe_div(ar_prior, _fraud_signals_safe_div(rev_prior_ann, 365)) if ar_prior is not None and rev_prior_ann is not None else None
        if dso_cur is not None and dso_prior is not None and dso_prior > 0:
            dso_change = (dso_cur - dso_prior) / dso_prior
            if dso_change > 0.20:
                severity = min(1.0, (dso_change - 0.20) / 0.40)
                d1_score += 10.0 * severity
                d1_signals.append(f"DSO 同比增加 {dso_change*100:.1f}%（{dso_prior:.1f}→{dso_cur:.1f}天），回款显著恶化")
            elif dso_change > 0.10:
                d1_score += 4.0
                d1_signals.append(f"DSO 同比增加 {dso_change*100:.1f}%，回款趋紧")
            else:
                d1_signals.append(f"DSO 同比变化 {dso_change*100:.1f}%，回款稳定")
        elif dso_cur is not None:
            d1_signals.append(f"当前 DSO={dso_cur:.1f}天（无上年可比）")
        else:
            warnings.append("Accounts receivable or revenue data missing, DSO signal skipped")

        d1_score = min(d1_score, 20.0)

        # ======================================================================
        # D2: Abnormal profit quality (20pts)
        # ======================================================================
        d2_score = 0.0
        d2_signals: list[str] = []

        # 2a: Net profit growing but OCF declining
        np_growth = _fraud_signals_pct_change(np_cur, np_prior) if np_cur is not None and np_prior is not None else None
        if np_growth is not None and np_growth > 0 and ocf_growth is not None and ocf_growth < 0:
            gap = np_growth - ocf_growth
            severity = min(1.0, gap / 0.50)
            d2_score += 12.0 * severity
            d2_signals.append(f"净利润增长({np_growth*100:.1f}%)但经营现金流下降({ocf_growth*100:.1f}%)，利润含金量低")
        elif np_growth is not None and ocf_growth is not None:
            gap = abs(np_growth - ocf_growth)
            if gap > 0.30:
                d2_score += 4.0
                d2_signals.append(f"净利润增长({np_growth*100:.1f}%)与现金流增长({ocf_growth*100:.1f}%)差距较大")
            else:
                d2_signals.append(f"Net profit and cash flow growth trends are consistent(gap={gap*100:.1f}%)")

        # 2b: Accruals ratio
        accrual_ratios = []
        for i in range(1, n):
            np_val = _fraud_signals_safe_float(sorted_records[i].get("net_profit"))
            ocf_val = _fraud_signals_safe_float(sorted_records[i].get("operating_cashflow"))
            ta_val = _fraud_signals_safe_float(sorted_records[i].get("total_assets"))
            if np_val is not None and ocf_val is not None and ta_val is not None and ta_val > 0:
                accrual_ratios.append((np_val - ocf_val) / ta_val)

        if accrual_ratios:
            mean_accrual = float(np.mean(accrual_ratios))
            if abs(mean_accrual) > 0.1:
                severity = min(1.0, (abs(mean_accrual) - 0.1) / 0.20)
                d2_score += 8.0 * severity
                d2_signals.append(f"应计比率 {mean_accrual:.4f}（绝对值>{abs(mean_accrual):.4f}），利润与现金流偏离较大")
            else:
                d2_signals.append(f"应计比率 {mean_accrual:.4f}，利润质量正常")
        else:
            warnings.append("应计比率无法计算")

        d2_score = min(d2_score, 20.0)

        # ======================================================================
        # D3: Abnormal assets (15pts)
        # ======================================================================
        d3_score = 0.0
        d3_signals: list[str] = []

        # 3a: Total assets growing much faster than revenue (asset inflation)
        ta_growth = _fraud_signals_pct_change(ta_cur, ta_prior) if ta_cur is not None and ta_prior is not None else None
        if revenue_growth is not None and ta_growth is not None and ta_growth > 0:
            asset_rev_gap = ta_growth - revenue_growth
            if asset_rev_gap > 0.30:
                severity = min(1.0, (asset_rev_gap - 0.30) / 0.50)
                d3_score += 6.0 * severity
                d3_signals.append(f"总资产增长({ta_growth*100:.1f}%)远超营收增长({revenue_growth*100:.1f}%)，资产膨胀")
            elif asset_rev_gap > 0.15:
                d3_score += 3.0
                d3_signals.append(f"总资产增长({ta_growth*100:.1f}%)快于营收，资产效率下降")
            else:
                d3_signals.append(f"Total assets match revenue growth(gap={asset_rev_gap*100:.1f}%)")

        # 3b: Receivables growing much faster than revenue
        ar_growth = _fraud_signals_pct_change(ar_cur, ar_prior) if ar_cur is not None and ar_prior is not None else None
        if ar_growth is not None and revenue_growth is not None and ar_growth > 0:
            ar_rev_gap = ar_growth - revenue_growth
            if ar_rev_gap > 0.30:
                severity = min(1.0, (ar_rev_gap - 0.30) / 0.50)
                d3_score += 5.0 * severity
                d3_signals.append(f"应收账款增长({ar_growth*100:.1f}%)远超营收增长({revenue_growth*100:.1f}%)，信用政策过度宽松")
            elif ar_rev_gap > 0.15:
                d3_score += 2.0
                d3_signals.append(f"应收账款增长({ar_growth*100:.1f}%)快于营收")
            else:
                d3_signals.append("应收账款与营收增长匹配")

        # 3c: Inventory growing much faster than COGS
        # Approximate COGS as revenue - gross_profit, or check directly
        if inv_cur is not None and inv_prior is not None:
            inv_growth = _fraud_signals_pct_change(inv_cur, inv_prior)
            cogs_cur = rev_cur * (1 - gm_cur / 100) if rev_cur is not None and gm_cur is not None and gm_cur > 1 else None
            cogs_prior = rev_prior * (1 - gm_prior / 100) if rev_prior is not None and gm_prior is not None and gm_prior > 1 else None
            cogs_growth = _fraud_signals_pct_change(cogs_cur, cogs_prior) if cogs_cur is not None and cogs_prior is not None else None
            if inv_growth is not None and cogs_growth is not None and cogs_growth > 0:
                inv_cogs_gap = inv_growth - cogs_growth
                if inv_cogs_gap > 0.30:
                    severity = min(1.0, (inv_cogs_gap - 0.30) / 0.50)
                    d3_score += 4.0 * severity
                    d3_signals.append(f"存货增长({inv_growth*100:.1f}%)远超营业成本增长({cogs_growth*100:.1f}%)，可能存在滞销")
                elif inv_cogs_gap > 0.15:
                    d3_score += 2.0
                    d3_signals.append("存货增长快于营业成本")
                else:
                    d3_signals.append("存货与营业成本增长匹配")
        else:
            warnings.append("Inventory data is missing and inventory signal is skipped")

        d3_score = min(d3_score, 15.0)

        # ======================================================================
        # D4: Related trading signals (15pts)
        # ======================================================================
        d4_score = 0.0
        d4_signals: list[str] = []

        # 4a: Other receivables ratio > 10% of total assets (proxy for related party)
        # Use total_cur_assets - accounts_receiv - inventories - money_cap as rough "other receivables"
        money_cap_cur = _fraud_signals_safe_float(fin_cur.get("money_cap")) if fin_cur else None
        if tca_cur is not None and ar_cur is not None and inv_cur is not None:
            other_receivables = tca_cur - (ar_cur or 0) - (inv_cur or 0) - (money_cap_cur or 0)
            if ta_cur is not None and ta_cur > 0:
                other_rec_ratio = other_receivables / ta_cur
                if other_rec_ratio > 0.10:
                    severity = min(1.0, (other_rec_ratio - 0.10) / 0.20)
                    d4_score += 8.0 * severity
                    d4_signals.append(f"其他应收类资产占总资产 {other_rec_ratio*100:.1f}%（>10%），关联交易风险较高")
                elif other_rec_ratio > 0.05:
                    d4_score += 3.0
                    d4_signals.append(f"其他应收类资产占总资产 {other_rec_ratio*100:.1f}%，需关注")
                else:
                    d4_signals.append(f"其他应收类资产占比 {other_rec_ratio*100:.1f}%，正常")
        else:
            warnings.append("Insufficient current asset data, other receivable signals are skipped")

        # 4b: Significant changes in non-current assets
        nca_cur = _fraud_signals_safe_float(fin_cur.get("total_nca")) if fin_cur else None
        nca_prior = _fraud_signals_safe_float(fin_prior.get("total_nca")) if fin_prior else None
        if nca_cur is not None and nca_prior is not None and nca_prior > 0:
            nca_change = (nca_cur - nca_prior) / nca_prior
            if abs(nca_change) > 0.50:
                severity = min(1.0, (abs(nca_change) - 0.50) / 0.50)
                d4_score += 7.0 * severity
                d4_signals.append(f"非流动资产同比变动 {nca_change*100:.1f}%，幅度异常")
            elif abs(nca_change) > 0.30:
                d4_score += 3.0
                d4_signals.append(f"非流动资产同比变动 {nca_change*100:.1f}%，偏大")
            else:
                d4_signals.append(f"非流动资产同比变动 {nca_change*100:.1f}%，正常")
        else:
            warnings.append("非流动资产数据不足")

        d4_score = min(d4_score, 15.0)

        # ======================================================================
        # D5: Abnormal cash flow (15pts)
        # ======================================================================
        d5_score = 0.0
        d5_signals: list[str] = []

        # 5a: Net profit positive but operating cashflow negative
        if np_cur is not None and np_cur > 0 and ocf_cur is not None and ocf_cur < 0:
            d5_score += 10.0
            d5_signals.append("Net profit is positive but operating cash flow is negative, a serious warning sign")
        elif np_cur is not None and ocf_cur is not None and ocf_cur < 0:
            d5_signals.append("Operating cash flow is negative (net profit is also negative)")
        elif np_cur is not None and ocf_cur is not None and ocf_cur / np_cur < 0.5:
            d5_score += 5.0
            d5_signals.append(f"经营现金流仅为净利润的 {ocf_cur/np_cur*100:.1f}%，含金量偏低")
        elif np_cur is not None and ocf_cur is not None:
            d5_signals.append(f"经营现金流覆盖净利润 {ocf_cur/np_cur*100:.1f}%，现金流正常")

        # 5b: Large positive financing cashflow while operations generate cash
        ncf_fin_cur = _fraud_signals_safe_float(fin_cur.get("n_cashflow_fin_act")) if fin_cur else None
        if ncf_fin_cur is not None and ocf_cur is not None and ncf_fin_cur > 0 and ocf_cur > 0:
            ratio = ncf_fin_cur / abs(ocf_cur) if ocf_cur != 0 else 0
            if ratio > 0.50:
                d5_score += 5.0
                d5_signals.append(f"While operating cash flow is positive, financing cash flow inflows are substantial.(={ratio*100:.1f}% of OCF), Abnormal")
            else:
                d5_signals.append("筹资与经营现金流关系正常")
        elif ncf_fin_cur is not None:
            d5_signals.append(f"筹资现金流={ncf_fin_cur:.0f}")

        d5_score = min(d5_score, 15.0)

        # ======================================================================
        # D6: Abnormal gross profit margin (10pts)
        # ======================================================================
        d6_score = 0.0
        d6_signals: list[str] = []

        # 6a: Gross margin significantly above typical range
        # Typical A-share gross margins: most companies between 10%-60%
        # Above 90% or below -20% is suspicious
        if gm_cur is not None:
            if gm_cur > 95:
                d6_score += 5.0
                d6_signals.append(f"毛利率高达 {gm_cur:.1f}%，远超正常水平")
            elif gm_cur > 85:
                d6_score += 2.0
                d6_signals.append(f"毛利率较高({gm_cur:.1f}%)，需结合行业判断")
            elif gm_cur < -10:
                d6_score += 5.0
                d6_signals.append(f"毛利率为负({gm_cur:.1f}%)，经营异常")
            else:
                d6_signals.append(f"毛利率 {gm_cur:.1f}%")
        else:
            warnings.append("毛利率数据缺失")

        # 6b: Gross margin improving while revenue declining
        if gm_cur is not None and gm_prior is not None and rev_cur is not None and rev_prior is not None:
            gm_change = _fraud_signals_pct_change(gm_cur, gm_prior)
            if gm_change is not None and gm_change > 0.05 and revenue_growth is not None and revenue_growth < -0.05:
                d6_score += 5.0
                d6_signals.append(f"营收下降({revenue_growth*100:.1f}%)但毛利率上升({gm_change*100:.1f}%)，趋势异常")
            elif gm_change is not None:
                d6_signals.append(f"毛利率同比变动 {gm_change*100:.1f}%")

        d6_score = min(d6_score, 10.0)

        # ======================================================================
        # D7: Expense Capitalization Signal (5pts)
        # ======================================================================
        d7_score = 0.0
        d7_signals: list[str] = []

        # 7a: Asset turnover declining while assets growing
        asset_turnover_cur = _fraud_signals_safe_div(rev_cur, ta_cur) if rev_cur is not None and ta_cur is not None else None
        asset_turnover_prior = _fraud_signals_safe_div(rev_prior, ta_prior) if rev_prior is not None and ta_prior is not None and prior else None
        if asset_turnover_cur is not None and asset_turnover_prior is not None:
            at_change = (asset_turnover_cur - asset_turnover_prior) / asset_turnover_prior
            ta_growth = _fraud_signals_pct_change(ta_cur, ta_prior)
            if at_change is not None and at_change < -0.15 and ta_growth is not None and ta_growth > 0.10:
                d7_score += 3.0
                d7_signals.append(f"总资产周转率下降({at_change*100:.1f}%)而资产增长({ta_growth*100:.1f}%)，收入确认可能偏慢")
            else:
                d7_signals.append(f"资产周转率同比变动 {at_change*100:.1f}%")
        else:
            warnings.append("资产周转率无法计算")

        # 7b: Fixed assets growing but revenue flat
        fix_assets_cur = _fraud_signals_safe_float(fin_cur.get("fix_assets")) if fin_cur else None
        fix_assets_prior = _fraud_signals_safe_float(fin_prior.get("fix_assets")) if fin_prior else None
        if fix_assets_cur is not None and fix_assets_prior is not None and rev_cur is not None and rev_prior is not None:
            fa_growth = _fraud_signals_pct_change(fix_assets_cur, fix_assets_prior)
            if fa_growth is not None and fa_growth > 0.20 and revenue_growth is not None and revenue_growth < 0.05:
                d7_score += 2.0
                d7_signals.append(f"固定资产增长({fa_growth*100:.1f}%)但营收未同步增长({revenue_growth*100:.1f}%)，费用资本化可能")
            elif fa_growth is not None:
                d7_signals.append(f"固定资产同比变动 {fa_growth*100:.1f}%")

        d7_score = min(d7_score, 5.0)

        # ======================================================================
        # Overall score and rating
        # ======================================================================
        total_score = round(d1_score + d2_score + d3_score + d4_score + d5_score + d6_score + d7_score, 1)

        if total_score <= 30:
            rating = "正常"
        elif total_score <= 50:
            rating = "需关注"
        elif total_score <= 70:
            rating = "可疑"
        else:
            rating = "高度可疑"

        # Additional remarks
        warnings.append("Note: The industry average gross profit margin is not available, and the abnormal gross profit margin judgment is based on the absolute threshold.")

        payload = {
            "symbol": symbol,
            "total_score": total_score,
            "rating": rating,
            "categories": {
                "revenue_recognition": {
                    "score": round(d1_score, 1),
                    "max": 20,
                    "signals": d1_signals,
                },
                "earnings_quality": {
                    "score": round(d2_score, 1),
                    "max": 20,
                    "signals": d2_signals,
                },
                "asset_irregularities": {
                    "score": round(d3_score, 1),
                    "max": 15,
                    "signals": d3_signals,
                },
                "related_party": {
                    "score": round(d4_score, 1),
                    "max": 15,
                    "signals": d4_signals,
                },
                "cash_flow": {
                    "score": round(d5_score, 1),
                    "max": 15,
                    "signals": d5_signals,
                },
                "margin_anomalies": {
                    "score": round(d6_score, 1),
                    "max": 10,
                    "signals": d6_signals,
                },
                "capitalization": {
                    "score": round(d7_score, 1),
                    "max": 5,
                    "signals": d7_signals,
                },
            },
            "warnings": warnings,
            "data_quality": {
                "years_available": n,
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Financial fraud signal detection failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = ["get_financial_fraud_signals"]

# === piotroski_fscore ===
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


"""Expanded set of valuation model tools: DCF three-stage, DDM, residual income, EVA, FCFF/FCFE, PEG, Graham, CAPM, growth quality adjusted valuation"""

import json
import logging
from statistics import mean, pstdev
from typing import Annotated, Optional

import numpy as np
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _safe_div(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _cagr(latest, earliest, periods):
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
        bvps = _safe_div(latest.get("total_equity"), None)
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
                warnings.append(f"ROE For missing data, the 8% imputation was used by default.")

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
            nopat = _safe_div(item.get("oper_profit") or item.get("operating_profit"), None)
            if nopat is None:
                nopat = _safe_div(item.get("net_profit"), None)
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
                debt_w = _safe_div(total_liab, total_liab + total_equity) if (total_liab + total_equity) > 0 else 0.4
            debt_w = max(0, min(1, debt_w if debt_w else 0.4))
            eq_w = 1.0 - debt_w
            wacc_val = eq_w * cost_of_equity + debt_w * cost_of_debt * (1 - tax)

            eva_val = nopat - wacc_val * invested_capital if nopat is not None else None
            eva_spread = _safe_div(eva_val, invested_capital)

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
            growth_rate_3y_cagr = _cagr(latest_p, earliest_p, periods)
        elif len(profit_values) >= 2:
            latest_p = profit_values[0]
            earliest_p = profit_values[-1]
            periods = len(profit_values) - 1
            growth_rate_3y_cagr = _cagr(latest_p, earliest_p, periods)

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
        eps = _safe_div(net_profit, shares)

        # BVPS
        total_equity = latest.get("total_equity")
        bvps = _safe_div(total_equity, shares)

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
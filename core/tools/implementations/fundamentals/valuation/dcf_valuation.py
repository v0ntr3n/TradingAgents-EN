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

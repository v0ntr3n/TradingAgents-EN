"""WACC Weighted average cost of capital calculator"""

import json
import logging
from typing import Annotated, Optional

import numpy as np
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="get_wacc_calculation",
    name="WACC 计算器",
    description="Calculate the weighted average cost of capital WACC for A-share companies, return equity weight, debt weight, equity cost, debt cost, tax rate and WACC details, and provide a discount rate for DCF valuation",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["wacc", "cost_of_capital", "valuation", "discount_rate"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["discount_rate_estimation", "cost_of_capital_calculation"],
    when_to_use="Used when you need to calculate discount rates, estimate cost of capital, provide WACC parameters for DCF or absolute valuation.",
    when_not_to_use="Not suitable for direct use in valuation conclusions (only parameters are provided). Not suitable for targets without financial data.",
    returns="Returns a JSON string containing capital structure, cost of equity, cost of debt, WACC, and data quality description.",
    example="get_wacc_calculation(symbol='600519')",
    related_tools=["get_dcf_valuation", "get_dcf_three_stage_valuation", "get_capm_cost_of_equity"],
)
def get_wacc_calculation(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    risk_free_rate: Annotated[Optional[float], "Risk-free rate, default 2.5%"] = 0.025,
    equity_risk_premium: Annotated[Optional[float], "Equity risk premium, default 6%"] = 0.06,
    tax_rate: Annotated[Optional[float], "Corporate income tax rate, default 25%"] = 0.25,
) -> str:
    """WACC Weighted average cost of capital calculation

    Args:
        symbol: A stock stock code, such as 600519
        risk_free_rate: Risk-free interest rate (in decimal form, such as 0.025 for 2.5%), default 0.025
        equity_risk_premium: Equity risk premium (decimal form), default 0.06
        tax_rate: Corporate income tax rate (decimal form), default 0.25

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code

        In case of success, return dict, fields:
            symbol: Stock code
            parameters: input parameters dict —
                risk_free_rate: Risk-free interest rate (decimal)
                equity_risk_premium: Equity risk premium (decimal)
                tax_rate: Income tax rate (decimal)
            capital_structure: capital structure dict —
                market_cap: Market value
                total_debt: total debt
                total_capital: total capital
                equity_weight: Equity weight (decimal)
                debt_weight: Debt weight (decimal)
                debt_to_equity: Debt to equity ratio (decimal, None if missing)
            cost_of_equity: cost of equity dict —
                beta: Beta coefficient
                risk_free_rate: Risk-free interest rate (decimal)
                equity_risk_premium: Equity risk premium (decimal)
                cost_of_equity: Cost of equity (decimal)
            cost_of_debt: cost of debt dict —
                interest_expense: interest expense
                total_debt: total debt
                pre_tax_cost: Cost of debt before tax (decimal)
                after_tax_cost: After-tax debt cost (decimal)
            wacc: Weighted average cost of capital (decimal)
            data_quality: Data quality dict —
                beta_source: Beta Source:"default" | "price_returns_estimated"
                debt_cost_source: Source of debt cost:"financial_expense_based" | "default_proxy"
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        from core.skill_runtime.data_access import get_stock_financial_periods, get_stock_daily_quotes
        from core.skill_runtime.standard_financial_apis import get_security_master
        import datetime

        warnings: list = []
        beta_source = "default"

        # 1. Get market capitalization
        master = get_security_master(symbol)
        market_cap = master.get("market_cap")
        if market_cap is None or market_cap <= 0:
            return json.dumps(
                {"status": "error", "message": f"无法获取 {symbol} 的有效市值", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        # 2. Get the latest financial data
        periods = get_stock_financial_periods(symbol, limit=1)
        if not periods:
            # Fallback to get_security_master with possible financial information
            total_liab = 0.0
            total_equity = (master.get("total_equity") or 0.0)
            fin_exp = 0.0
            warnings.append("No financial period data is obtained, and default values are used for debt and interest expenses.")
        else:
            latest_fin = periods[0]
            total_liab = latest_fin.get("total_liab") or 0.0
            total_equity = latest_fin.get("total_equity") or 0.0
            fin_exp = latest_fin.get("fin_exp") or 0.0

            # 🔑 Test the reporting period caliber and annualize the cumulative value of the income statement
            from core.tools.implementations.risk.extended_risk_models import (
                _detect_period_type, _annualize_factor, _PERIOD_LABELS,
            )
            cur_period = _detect_period_type(latest_fin)
            if cur_period != "annual" and cur_period != "unknown":
                factor = _annualize_factor(cur_period)
                fin_exp_annualized = fin_exp * factor
                warnings.append(
                    f"当期为{_PERIOD_LABELS.get(cur_period, cur_period)}数据，"
                    f"Financial expenses have been annualized ({fin_exp:.2f}→{fin_exp_annualized:.2f}) "
                )
                fin_exp = fin_exp_annualized

        # 3. Calculate Beta (simplified: calculated from daily returns, or default 1.0)
        beta = 1.0
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
                            # Using its own variance approximation, it is assumed that the market volatility is approximately 0.015 daily
                            market_var_proxy = 0.015 ** 2
                            cov_proxy = np.mean(returns) * np.mean(returns) if np.mean(returns) > 0 else 0
                            # Simplify:beta = Own volatility/market volatility
                            beta = max(0.2, min(2.5, np.sqrt(var_ret) / 0.015))
                            beta_source = "price_returns_estimated"
        except Exception as e:
            warnings.append(f"Beta Calculation failed, default value used 1.0: {e}")

        # 4. cost calculation
        rf = risk_free_rate if risk_free_rate is not None else 0.025
        erp = equity_risk_premium if equity_risk_premium is not None else 0.06
        tax = tax_rate if tax_rate is not None else 0.25

        cost_of_equity = rf + beta * erp

        # cost of debt
        if total_liab > 0 and fin_exp > 0:
            pre_tax_cost_of_debt = fin_exp / total_liab
            pre_tax_cost_of_debt = max(0.01, min(0.15, pre_tax_cost_of_debt))
            debt_cost_source = "financial_expense_based"
        else:
            pre_tax_cost_of_debt = 0.04
            debt_cost_source = "default_proxy"
            if total_liab == 0:
                warnings.append("Total debt is 0, and the default cost of debt is 4%.")
            if fin_exp == 0:
                warnings.append("The finance charge is 0 or missing and the debt cost uses the default 4%.")

        after_tax_cost_of_debt = pre_tax_cost_of_debt * (1 - tax)

        # 5. capital structure
        total_capital = market_cap + total_liab
        equity_weight = market_cap / total_capital if total_capital > 0 else 0.5
        debt_weight = total_liab / total_capital if total_capital > 0 else 0.5
        debt_to_equity = total_liab / total_equity if total_equity and total_equity > 0 else None

        # 6. WACC
        wacc_value = equity_weight * cost_of_equity + debt_weight * after_tax_cost_of_debt

        payload = {
            "symbol": symbol,
            "parameters": {
                "risk_free_rate": round(rf, 4),
                "equity_risk_premium": round(erp, 4),
                "tax_rate": round(tax, 4),
            },
            "capital_structure": {
                "market_cap": round(market_cap, 2),
                "total_debt": round(total_liab, 2),
                "total_capital": round(total_capital, 2),
                "equity_weight": round(equity_weight, 4),
                "debt_weight": round(debt_weight, 4),
                "debt_to_equity": round(debt_to_equity, 4) if debt_to_equity is not None else None,
            },
            "cost_of_equity": {
                "beta": round(beta, 4),
                "risk_free_rate": round(rf, 4),
                "equity_risk_premium": round(erp, 4),
                "cost_of_equity": round(cost_of_equity, 4),
            },
            "cost_of_debt": {
                "interest_expense": round(fin_exp, 2),
                "total_debt": round(total_liab, 2),
                "pre_tax_cost": round(pre_tax_cost_of_debt, 4),
                "after_tax_cost": round(after_tax_cost_of_debt, 4),
            },
            "wacc": round(wacc_value, 4),
            "data_quality": {
                "beta_source": beta_source,
                "debt_cost_source": debt_cost_source,
                "warnings": warnings,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("WACC计算失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_wacc_calculation"]

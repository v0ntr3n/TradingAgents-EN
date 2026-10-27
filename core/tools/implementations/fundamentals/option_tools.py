"""Options and derivatives pricing tools."""

import json
import logging
import math
from typing import Annotated, Optional

import numpy as np
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)

# ── scipy availability check ────────────────────────────────────────

try:
    from scipy import stats as _stats

    def _norm_cdf(x: float) -> float:
        """Standard normal distribution CDF, scipy first, fallback math.erf."""
        return float(_stats.norm.cdf(x))

    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

    def _norm_cdf(x: float) -> float:
        """standard normal distribution CDF —— math.erf Approximately."""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard Normal Distribution PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# ── Black-Scholes Internal calculation ─────────────────────────────────────────

def _bs_d1(
    spot: float, strike: float, t: float, r: float, sigma: float
) -> float:
    return (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t) / (
        sigma * math.sqrt(t)
    )


def _bs_price(
    spot: float, strike: float, t: float, r: float, sigma: float, opt_type: str
) -> dict:
    """Calculate Black-Scholes prices and intermediate variables.

    Returns
        dict with: price, d1, d2, delta, intrinsic_value, time_value
    """
    d1 = _bs_d1(spot, strike, t, r, sigma)
    d2 = d1 - sigma * math.sqrt(t)

    n1 = _norm_cdf(d1)
    n2 = _norm_cdf(d2)
    nm1 = _norm_cdf(-d1)
    nm2 = _norm_cdf(-d2)

    disc = strike * math.exp(-r * t)

    if opt_type == "call":
        price = spot * n1 - disc * n2
        delta = n1
        intrinsic = max(spot - strike, 0.0)
    else:
        price = disc * nm2 - spot * nm1
        delta = n1 - 1.0
        intrinsic = max(strike - spot, 0.0)

    time_value = price - intrinsic
    return {
        "price": round(price, 6),
        "d1": round(d1, 6),
        "d2": round(d2, 6),
        "delta": round(delta, 6),
        "intrinsic_value": round(intrinsic, 6),
        "time_value": round(time_value, 6),
    }


def _bs_vega(
    spot: float, strike: float, t: float, r: float, sigma: float
) -> float:
    """Calculate Vega = S * N'(d1) * sqrt(T)"""
    d1 = _bs_d1(spot, strike, t, r, sigma)
    return spot * _norm_pdf(d1) * math.sqrt(t)


# ── Tool 1: Black-Scholes option pricing ─────────────────────────────────

@tool
@register_tool(
    tool_id="get_black_scholes_price",
    name="Black-Scholes option pricing",
    description=(
        "Calculate the theoretical price of European options based on the Black-Scholes model, and return d1, d2, Delta,"
        "Intrinsic value and time value. Use scipy.stats.norm.cdf to calculate the normal distribution cumulative function;"
        "Fallback to math.erf approximation if scipy is not available."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["derivatives", "option_pricing", "black_scholes"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["欧式期权理论定价", "Black-Scholes Model calculation"],
    when_to_use=(
        "It is used when users need to calculate the theoretical price, d1/d2, Delta, intrinsic value or time value of European options."
        "Suitable for standardized European call/put option pricing."
    ),
    when_not_to_use=(
        "Not suitable for American options (early exercise needs to be considered);"
        "Not suitable for exotic options (such as barrier options, Asian options, etc.);"
        "Not suitable for implied volatility calculations (use get_implied_volatility instead)."
    ),
    returns=(
        "Returns a JSON string containing option_price (option price), d1, d2, delta,"
        "intrinsic_value (intrinsic value), time_value (time value), parameters_used (use parameters),"
        "methodology (calculation instructions)."
    ),
    example="get_black_scholes_price(spot_price=100, strike_price=100, time_to_expiry=0.5)",
    related_tools=["get_implied_volatility", "get_option_greeks", "get_option_strategy_pnl"],
)
def get_black_scholes_price(
    spot_price: Annotated[float, "标的资产当前价格"],
    strike_price: Annotated[float, "行权价"],
    time_to_expiry: Annotated[float, "Expiration time (year), for example, 0.5 means half a year"],
    risk_free_rate: Annotated[float, "无风险利率"] = 0.025,
    volatility: Annotated[float, "波动率（年化）"] = 0.25,
    option_type: Annotated[str, "Option type: call or put"] = "call",
) -> str:
    """Calculate the Black-Scholes theoretical price of a European option.

    Args:
        spot_price: Current price of the underlying asset
        strike_price: exercise price
        time_to_expiry: Expiration time (year), for example, 0.5 means half a year
        risk_free_rate: Risk-free rate (decimal), default 0.025
        volatility: Volatility (annualized decimal), default 0.25
        option_type: Option type: "call" (bullish) or "put" (bearish), default "call"

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            option_type: Option type: "call" | "put"
            option_price: option theoretical price
            d1: BS in the formula d1
            d2: BS in the formula d2
            delta: Delta value
            intrinsic_value: intrinsic value
            time_value: time value
            moneyness: In-the-money status: "In price" | "At-the-money or out-of-the-money"
            parameters_used: dict Parameters used——
                — spot_price: target price
                — strike_price: exercise price
                — time_to_expiry_years: Expiration time (year)
                — risk_free_rate: risk-free rate
                — volatility: Volatility
                — option_type: Option type
            methodology: Calculation method description
            message: Error message (only status="error" exist)
    """
    try:
        opt_type = option_type.lower()
        if opt_type not in ("call", "put"):
            return json.dumps({
                "status": "error",
                "message": "option_type must be 'call' or 'put'",
            }, ensure_ascii=False, indent=2, default=str)

        if spot_price <= 0 or strike_price <= 0:
            return json.dumps({
                "status": "error",
                "message": "spot_price and strike_price must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if time_to_expiry <= 0:
            return json.dumps({
                "status": "error",
                "message": "time_to_expiry must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if volatility <= 0:
            return json.dumps({
                "status": "error",
                "message": "volatility must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        result = _bs_price(
            spot=spot_price,
            strike=strike_price,
            t=time_to_expiry,
            r=risk_free_rate,
            sigma=volatility,
            opt_type=opt_type,
        )

        payload = {
            "status": "ok",
            "option_type": opt_type,
            "option_price": result["price"],
            "d1": result["d1"],
            "d2": result["d2"],
            "delta": result["delta"],
            "intrinsic_value": result["intrinsic_value"],
            "time_value": result["time_value"],
            "moneyness": "价内" if result["intrinsic_value"] > 0 else "价平或价外",
            "parameters_used": {
                "spot_price": spot_price,
                "strike_price": strike_price,
                "time_to_expiry_years": time_to_expiry,
                "risk_free_rate": risk_free_rate,
                "volatility": volatility,
                "option_type": opt_type,
            },
            "methodology": (
                "Black-Scholes European option pricing model:"
                "d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)；"
                "d2 = d1 - σ√T；"
                "Call = S·N(d1) - K·e^(-rT)·N(d2)；"
                "Put = K·e^(-rT)·N(-d2) - S·N(-d1)。"
                f"{'Calculated using scipy.stats.norm.cdf N(·). ' if _HAS_SCIPY else 'Approximate calculations using math.erf N(·) (scipy Not available).'}"
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Black-Scholes Pricing failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ── Tool 2: Implied volatility ─────────────────────────────────────────────

@tool
@register_tool(
    tool_id="get_implied_volatility",
    name="隐含波动率计算",
    description=(
        "Implied volatility is deduced from option market prices using the Newton-Raphson iteration method."
        "Iteration formula:σ_new = σ - (BS(σ) - market_price) / vega(σ), "
        "Maximum iterations 100, convergence tolerance 0.0001."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["derivatives", "implied_volatility", "option_pricing"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["Deducing implied volatility from option market prices"],
    when_to_use=(
        "It is used when the user knows the option market price and needs to derive the corresponding implied volatility."
        "Commonly used in volatility trading and option pricing verification."
    ),
    when_not_to_use=(
        "Not suitable for theoretical pricing (please use get_black_scholes_price);"
        "Not suitable for historical volatility calculations (please use statistical tools);"
        "Not suitable for deeply out-of-the-money options (iterations may not converge)."
    ),
    returns=(
        "Returns a JSON string containing implied_volatility,"
        "iterations (number of iterations), convergence_status (convergence status),"
        "initial_guess (Initial guess value), price_at_iv (BS price corresponding to IV)."
    ),
    example="get_implied_volatility(spot_price=100, strike_price=100, time_to_expiry=0.5, option_price=10)",
    related_tools=["get_black_scholes_price", "get_option_greeks", "get_option_strategy_pnl"],
)
def get_implied_volatility(
    spot_price: Annotated[float, "标的资产当前价格"],
    strike_price: Annotated[float, "行权价"],
    time_to_expiry: Annotated[float, "到期时间（年）"],
    option_price: Annotated[float, "期权市场价"],
    risk_free_rate: Annotated[float, "无风险利率"] = 0.025,
    option_type: Annotated[str, "Option type: call or put"] = "call",
) -> str:
    """Implied volatility is deduced from market prices via Newton-Raphson iterations.

    Args:
        spot_price: Current price of the underlying asset
        strike_price: exercise price
        time_to_expiry: Expiration time (year)
        option_price: option market price
        risk_free_rate: Risk-free rate (decimal), default 0.025
        option_type: Option type: "call" or "put", Default "call"

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            implied_volatility: Implied volatility (decimal)
            implied_volatility_pct: Implied volatility (%)
            iterations: Number of iterations
            convergence_status: convergence state: "Converged" | "Not converged"
            initial_guess: Initial guess value (0.3)
            price_at_iv: IV Corresponding BS price (only status="ok" exist)
            target_price: Target option market price (only status="ok" exist)
            price_error: Price error (only status="ok" exist)
            parameters_used: dict Parameters used (only status="ok" exist)——
                — spot_price: target price
                — strike_price: exercise price
                — time_to_expiry_years: Expiration time (year)
                — risk_free_rate: risk-free rate
                — option_price: option market price
                — option_type: Option type
            methodology: Description of calculation method (only status="ok" exist)
            message: Error message (only status="error" exist)
    """
    try:
        opt_type = option_type.lower()
        if opt_type not in ("call", "put"):
            return json.dumps({
                "status": "error",
                "message": "option_type must be 'call' or 'put'",
            }, ensure_ascii=False, indent=2, default=str)

        if spot_price <= 0 or strike_price <= 0:
            return json.dumps({
                "status": "error",
                "message": "spot_price and strike_price must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if time_to_expiry <= 0:
            return json.dumps({
                "status": "error",
                "message": "time_to_expiry must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if option_price <= 0:
            return json.dumps({
                "status": "error",
                "message": "option_price must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        # Determine the upper limit of intrinsic value
        intrinsic = max(spot_price - strike_price, 0.0) if opt_type == "call" else max(strike_price - spot_price, 0.0)
        if option_price < intrinsic:
            return json.dumps({
                "status": "error",
                "message": (
                    f"期权价格 {option_price} 低于内在价值 {intrinsic}，"
                    "Risk-free arbitrage opportunities exist and meaningful implied volatility cannot be calculated"
                ),
            }, ensure_ascii=False, indent=2, default=str)

        sigma = 0.3  # initial guess
        max_iter = 100
        tolerance = 0.0001

        for i in range(max_iter):
            bs = _bs_price(spot_price, strike_price, time_to_expiry, risk_free_rate, sigma, opt_type)
            price_diff = bs["price"] - option_price

            if abs(price_diff) < tolerance:
                payload = {
                    "status": "ok",
                    "implied_volatility": round(sigma, 6),
                    "implied_volatility_pct": round(sigma * 100, 4),
                    "iterations": i + 1,
                    "convergence_status": "已收敛",
                    "initial_guess": 0.3,
                    "price_at_iv": bs["price"],
                    "target_price": option_price,
                    "price_error": round(price_diff, 8),
                    "parameters_used": {
                        "spot_price": spot_price,
                        "strike_price": strike_price,
                        "time_to_expiry_years": time_to_expiry,
                        "risk_free_rate": risk_free_rate,
                        "option_price": option_price,
                        "option_type": opt_type,
                    },
                    "methodology": (
                        "Newton-Raphson Iterative method:σ_new = σ - (BS(σ) - market_price) / vega(σ). "
                        + ("Calculated using scipy.stats.norm N(·) and N'(·). " if _HAS_SCIPY else "Approximate calculations using math.erf N(·) (scipy Not available).")
                    ),
                }
                return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

            vega = _bs_vega(spot_price, strike_price, time_to_expiry, risk_free_rate, sigma)
            if abs(vega) < 1e-12:
                break  # vega Too small to continue iterating

            sigma = sigma - price_diff / vega
            sigma = max(sigma, 0.001)  # Volatility floor

        return json.dumps({
            "status": "error",
            "message": f"迭代 {max_iter} 次未收敛，请检查输入参数或尝试不同的初始猜测",
            "implied_volatility": round(sigma, 6) if sigma > 0 else None,
            "iterations": max_iter,
            "convergence_status": "未收敛",
            "initial_guess": 0.3,
        }, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Implied volatility calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ── Tool 3: greek letter calculation ───────────────────────────────────────────

@tool
@register_tool(
    tool_id="get_option_greeks",
    name="期权希腊字母计算",
    description=(
        "Calculate Greeks (Delta, Gamma, Theta, Vega, Rho) for European options,"
        "And give the meaning of each Greek letter. Gamma and Vega are the same for call/put options."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["derivatives", "option_greeks", "risk_management"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["Calculate option Greek letters (Delta, Gamma, Theta, Vega, Rho)"],
    when_to_use=(
        "Used when the user needs to calculate the risk indicators (Delta/Gamma/Theta/Vega/Rho) of European options."
        "Suitable for risk management and hedging strategy analysis."
    ),
    when_not_to_use=(
        "Not suitable for American options Greek letter calculation;"
        "Not suitable for exotic options;"
        "Not suitable for option pricing itself (use get_black_scholes_price)."
    ),
    returns=(
        "Returns a JSON string, including delta, gamma, theta (annualized), vega (1% volatility change),"
        "rho (1%interest rate changes), and the meaning of each Greek letter."
    ),
    example="get_option_greeks(spot_price=100, strike_price=100, time_to_expiry=0.5)",
    related_tools=["get_black_scholes_price", "get_implied_volatility", "get_option_strategy_pnl"],
)
def get_option_greeks(
    spot_price: Annotated[float, "标的资产当前价格"],
    strike_price: Annotated[float, "行权价"],
    time_to_expiry: Annotated[float, "到期时间（年）"],
    risk_free_rate: Annotated[float, "无风险利率"] = 0.025,
    volatility: Annotated[float, "波动率（年化）"] = 0.25,
    option_type: Annotated[str, "Option type: call or put"] = "call",
) -> str:
    """Calculate Delta, Gamma, Theta, Vega, Rho for European options.

    Args:
        spot_price: Current price of the underlying asset
        strike_price: exercise price
        time_to_expiry: Expiration time (year)
        risk_free_rate: Risk-free rate (decimal), default 0.025
        volatility: Volatility (annualized decimal), default 0.25
        option_type: Option type: "call" or "put", Default "call"

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            option_type: Option type: "call" | "put"
            spot_price_used: underlying price used
            delta: dict Delta——
                — value: Delta value
                — description: Explanation of meaning
                — interpretation: Explanation (directional exposure)
            gamma: dict Gamma——
                — value: Gamma value
                — description: Explanation of meaning
                — interpretation: Interpretation (Delta Sensitivity/Convexity Risk)
            theta: dict Theta (annualized)——
                — value: Theta Value (annualized)
                — description: Meaning (including daily average Theta)
                — interpretation: Interpretation (time decay)
            vega: dict Vega (per 1% change in volatility)——
                — value: Vega value
                — description: Explanation of meaning
                — interpretation: Explanation (Volatility Risk Exposure)
            rho: dict Rho (per 1% interest rate change)——
                — value: Rho value
                — description: Explanation of meaning
                — interpretation: Explanation (interest rate risk exposure)
            parameters_used: dict Parameters used
            methodology: Calculation method description
            message: Error message (only status="error" exist)
    """
    try:
        opt_type = option_type.lower()
        if opt_type not in ("call", "put"):
            return json.dumps({
                "status": "error",
                "message": "option_type must be 'call' or 'put'",
            }, ensure_ascii=False, indent=2, default=str)

        if spot_price <= 0 or strike_price <= 0:
            return json.dumps({
                "status": "error",
                "message": "spot_price and strike_price must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if time_to_expiry <= 0:
            return json.dumps({
                "status": "error",
                "message": "time_to_expiry must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        if volatility <= 0:
            return json.dumps({
                "status": "error",
                "message": "volatility must be greater than 0",
            }, ensure_ascii=False, indent=2, default=str)

        d1 = _bs_d1(spot_price, strike_price, time_to_expiry, risk_free_rate, volatility)
        d2 = d1 - volatility * math.sqrt(time_to_expiry)

        n1 = _norm_cdf(d1)
        nd1_pdf = _norm_pdf(d1)  # N'(d1)

        sqrt_t = math.sqrt(time_to_expiry)
        disc = strike_price * math.exp(-risk_free_rate * time_to_expiry)

        # Delta
        if opt_type == "call":
            delta = n1
        else:
            delta = n1 - 1.0

        # Gamma (call/put same)
        gamma = nd1_pdf / (spot_price * volatility * sqrt_t)

        # Theta (annualized)
        theta_common = -(spot_price * nd1_pdf * volatility) / (2.0 * sqrt_t)
        if opt_type == "call":
            theta = theta_common - risk_free_rate * disc * _norm_cdf(d2)
        else:
            theta = theta_common + risk_free_rate * disc * _norm_cdf(-d2)

        # Vega (call/put same)
        vega = spot_price * nd1_pdf * sqrt_t

        # Rho
        if opt_type == "call":
            rho = disc * time_to_expiry * _norm_cdf(d2)
        else:
            rho = -disc * time_to_expiry * _norm_cdf(-d2)

        payload = {
            "status": "ok",
            "option_type": opt_type,
            "spot_price_used": spot_price,
            "delta": {
                "value": round(delta, 6),
                "description": (
                    "Changes in underlying asset prices $1 The amount of change in the option price at that time."
                    f"call option Delta={round(delta, 4)}, "
                    f"It means that the underlying price increases $1, Approximate change in option price {round(delta, 4)}. "
                ),
                "interpretation": "方向性风险敞口" if opt_type == "call" else "方向性风险敞口（负值）",
            },
            "gamma": {
                "value": round(gamma, 6),
                "description": (
                    f"Changes in underlying asset prices $1 The amount of change in Delta.Gamma={round(gamma, 6)}, "
                    "Gamma The larger the delta is, the more sensitive it is to price changes."
                ),
                "interpretation": "Delta sensitivity (convexity risk)",
            },
            "theta": {
                "value": round(theta, 6),
                "description": (
                    f"The amount of change in the option price every time one day passes (annualized/365)."
                    f"Theta (annualized)={round(theta, 6)}, "
                    f"Daily average Theta ≈ {round(theta / 365.0, 6)}. "
                ),
                "interpretation": "Time decay (Theta is usually negative, indicating loss of time value)",
            },
            "vega": {
                "value": round(vega / 100.0, 6),
                "description": (
                    f"The amount by which the option price changes for every 1% (or 0.01) increase in volatility."
                    f"Vega (per 1% volatility)≈ {round(vega / 100.0, 6)}. "
                ),
                "interpretation": "波动率风险敞口",
            },
            "rho": {
                "value": round(rho / 100.0, 6),
                "description": (
                    f"The amount by which the option price changes for every 1% (i.e., 0.01) increase in the risk-free interest rate."
                    f"Rho (per 1% interest rate change)≈ {round(rho / 100.0, 6)}. "
                ),
                "interpretation": "Interest rate risk exposure (generally less impact on short-dated options)",
            },
            "parameters_used": {
                "spot_price": spot_price,
                "strike_price": strike_price,
                "time_to_expiry_years": time_to_expiry,
                "risk_free_rate": risk_free_rate,
                "volatility": volatility,
                "option_type": opt_type,
            },
            "methodology": (
                "Delta = N(d1) (call) or N(d1)-1 (put) ; "
                "Gamma = N'(d1) / (S·σ·√T)；"
                "Theta(call) = -(S·N'(d1)·σ)/(2√T) - r·K·e^(-rT)·N(d2)；"
                "Vega = S·N'(d1)·√T；"
                "Rho(call) = K·T·e^(-rT)·N(d2)。"
                + ("Calculated using scipy.stats.norm N(·) and N'(·). " if _HAS_SCIPY else "Approximate calculations using math.erf N(·) (scipy Not available).")
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("希腊字母计算失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ── Tool 4: Options Strategy Profit and Loss Chart ─────────────────────────────────────────

def _covered_call_pnl(
    spot_range: np.ndarray, spot_0: float, k1: float, prem1: float
) -> np.ndarray:
    """covered_call: long stock + short call at k1"""
    call_intrinsic = np.maximum(spot_range - k1, 0.0)
    stock_pnl = spot_range - spot_0
    return stock_pnl + prem1 - call_intrinsic


def _protective_put_pnl(
    spot_range: np.ndarray, spot_0: float, k1: float, prem1: float
) -> np.ndarray:
    """protective_put: long stock + long put at k1"""
    put_intrinsic = np.maximum(k1 - spot_range, 0.0)
    stock_pnl = spot_range - spot_0
    return stock_pnl - prem1 + put_intrinsic


def _straddle_pnl(
    spot_range: np.ndarray, k: float, prem1: float
) -> np.ndarray:
    """straddle: long call + long put at same strike; total_prem = 2*prem1"""
    return np.abs(spot_range - k) - 2.0 * prem1


def _strangle_pnl(
    spot_range: np.ndarray, k1: float, k2: float, prem1: float, prem2: float
) -> np.ndarray:
    """strangle: long put at k1 (< spot) + long call at k2 (> spot)"""
    put_pnl = np.maximum(k1 - spot_range, 0.0) - prem1
    call_pnl = np.maximum(spot_range - k2, 0.0) - prem2
    return put_pnl + call_pnl


def _bull_spread_pnl(
    spot_range: np.ndarray, k1: float, k2: float, prem1: float, prem2: float
) -> np.ndarray:
    """bull_spread: long call at k1 + short call at k2 (k2 > k1)"""
    long_call = np.maximum(spot_range - k1, 0.0) - prem1
    short_call = prem2 - np.maximum(spot_range - k2, 0.0)
    return long_call + short_call


def _bear_spread_pnl(
    spot_range: np.ndarray, k1: float, k2: float, prem1: float, prem2: float
) -> np.ndarray:
    """bear_spread: long put at k1 + short put at k2 (k1 > k2)"""
    long_put = np.maximum(k1 - spot_range, 0.0) - prem1
    short_put = prem2 - np.maximum(k2 - spot_range, 0.0)
    return long_put + short_put


def _iron_condor_pnl(
    spot_range: np.ndarray,
    k1: float, k2: float, k3: float, k4: float,
    prem1: float, prem2: float, prem3: float, prem4: float,
) -> np.ndarray:
    """iron_condor: bear put spread (k1>k2) + bull call spread (k3<k4)"""
    # Bear put spread: long put at k1, short put at k2
    long_put = np.maximum(k1 - spot_range, 0.0) - prem1
    short_put = prem2 - np.maximum(k2 - spot_range, 0.0)
    # Bull call spread: long call at k3, short call at k4
    long_call = np.maximum(spot_range - k3, 0.0) - prem3
    short_call = prem4 - np.maximum(spot_range - k4, 0.0)
    return long_put + short_put + long_call + short_call


_STRATEGIES = {
    "covered_call": {
        "label": "Covered Call",
        "description": "Hold the underlying asset + Selling call options. Suitable for mildly bullish or neutral expectations to enhance returns through premiums.",
        "legs": 2,
    },
    "protective_put": {
        "label": "Protective Put",
        "description": "Hold the underlying asset + Buy put options. It is suitable for those who are bullish but worried about the downside risk, which is equivalent to buying insurance for the position.",
        "legs": 2,
    },
    "straddle": {
        "label": "Straddle",
        "description": "Buy both call and put options at the same price. Applicable to situations where the underlying asset is expected to fluctuate significantly but the direction is uncertain.",
        "legs": 2,
    },
    "strangle": {
        "label": "Strangle combination",
        "description": "Buy out-of-the-money put (K1<S) and out-of-the-money calls (K2>S) . Suitable for large swings expected and costs less than straddle.",
        "legs": 2,
    },
    "bull_spread": {
        "label": "Bull Spread",
        "description": "Buy low strike price call + Sell the high strike price to call. Suitable for mild bullishness and cost reduction.",
        "legs": 2,
    },
    "bear_spread": {
        "label": "Bear Spread",
        "description": "Buy high strike price put + Sell low strike price put. Suitable for mild bearish, cost reduction.",
        "legs": 2,
    },
    "iron_condor": {
        "label": "Iron Condor",
        "description": "Bear Put Spread + Bullish Call Spread (4 legs total). It is suitable for the expected target to fluctuate within a narrow range.",
        "legs": 4,
    },
}


@tool
@register_tool(
    tool_id="get_option_strategy_pnl",
    name="期权策略盈亏图",
    description=(
        "Calculate the profit and loss curves of common option strategies on the expiration date, including maximum profit, maximum loss,"
        "break-even point, and a breakdown of the profit and loss for about 20 price points."
        "Support strategies: covered_call (covered opening), protective_put (protective put),"
        "straddle (straddle), strangle (wide straddle), bull_spread (bull spread),"
        "bear_spread (Bear spread), iron_condor (Iron Eagle style)."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["derivatives", "option_strategy", "pnl_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["期权策略盈亏分析", "策略对比", "盈亏平衡点计算"],
    when_to_use=(
        "When users need to analyze the profit and loss of option portfolio strategies on the expiration date, calculate the maximum profit/loss,"
        "Break-even point, or used when profit and loss visualization data is needed."
    ),
    when_not_to_use=(
        "Not suitable for single-leg option pricing (use get_black_scholes_price);"
        "Not suitable for Greek letter calculations (please use get_option_greeks);"
        "Not suitable for implied volatility calculations (use get_implied_volatility instead)."
    ),
    returns=(
        "Returns a JSON string, including strategy (strategy name and description), max_profit (maximum profit),"
        "max_loss (maximum loss), break_even_points (break-even point list),"
        "pnl_table (Price-P&L array, about 20 points)."
    ),
    example="get_option_strategy_pnl(strategy_type='covered_call', spot_price=100, strike1=100)",
    related_tools=["get_black_scholes_price", "get_option_greeks", "get_implied_volatility"],
)
def get_option_strategy_pnl(
    strategy_type: Annotated[str, "策略类型"] = "covered_call",
    spot_price: Annotated[float, "标的当前价格"] = 100.0,
    strike1: Annotated[float, "主行权价（第一腿）"] = 100.0,
    strike2: Annotated[Optional[float], "Second strike price (used by spread strategy)"] = None,
    premium1: Annotated[float, "第一腿权利金（收/付）"] = 5.0,
    premium2: Annotated[Optional[float], "第二腿权利金（收/付）"] = None,
    volatility: Annotated[float, "Volatility (for ATM options reference)"] = 0.25,
    time_to_expiry: Annotated[float, "到期时间（年）"] = 0.25,
    risk_free_rate: Annotated[float, "无风险利率"] = 0.025,
) -> str:
    """Calculate the profit and loss distribution of the option strategy on the expiration date.

    Args:
        strategy_type: Policy type, optional "covered_call" / "protective_put" / "straddle" /
            "strangle" / "bull_spread" / "bear_spread" / "iron_condor", Default "covered_call"
        spot_price: Current price of the underlying, default 100.0
        strike1: Main strike price (first leg), default 100.0
        strike2: The second exercise price (used by spread strategy) is automatically calculated according to the strategy when it is None. The default is None
        premium1: First leg royalty, default 5.0
        premium2: The second leg premium is automatically calculated according to the strategy when it is None. The default value is None
        volatility: Volatility (for ATM options reference), default 0.25
        time_to_expiry: Expiration time (year), default 0.25
        risk_free_rate: Risk-free rate, default 0.025

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            strategy: Strategy Chinese name
            strategy_description: Strategy description
            legs: Description text for each leg combination
            max_profit: Maximum profit (numeric value or "Infinity (theoretical upper limit)") 
            max_loss: Maximum loss (numeric value or "Infinity (theoretical lower limit)") 
            break_even_points: list[float] Break-even point list
            pnl_table: list[dict] Profit and loss statement (approx. 21 points), element structure——
                — spot_price_at_expiry: Expiration price
                — pnl: Profit and loss at this price
            visualization_note: Visual illustration
            parameters_used: dict Parameters used——
                — strategy_type: Strategy type
                — spot_price: target price
                — strike1: Main strike price
                — strike2: Second exercise price
                — premium1: first leg royalty
                — premium2: second leg royalty
                — time_to_expiry_years: Expiration time (year)
                — volatility: Volatility
            methodology: Calculation method description
            message: Error message (only status="error" exist)
    """
    try:
        strategy = strategy_type.lower()
        if strategy not in _STRATEGIES:
            return json.dumps({
                "status": "error",
                "message": (
                    f"不支持的策略类型 '{strategy_type}'。"
                    f"Support:{', '.join(_STRATEGIES.keys())}"
                ),
            }, ensure_ascii=False, indent=2, default=str)

        s0 = spot_price
        k1 = strike1

        # Generate price range:0 ~ 2*s0, about 20 points
        price_points = 21
        spot_range = np.linspace(0.0, 2.0 * s0, price_points)

        # Calculate profit and loss based on strategy type
        strategy_info = _STRATEGIES[strategy]

        if strategy == "covered_call":
            k2 = strike2 if strike2 is not None else k1
            pnl = _covered_call_pnl(spot_range, s0, k1, premium1)
            legs_desc = f"Long stock @ {s0} + Short call @ {k1}（权利金收入 {premium1}）"
            # max profit = k1 - s0 + premium (capped at k1)
            max_profit = k1 - s0 + premium1
            # max loss = s0 - 0 + (-premium when deep ITM) -- actually at S_T=0, stock loses all, keep premium
            # Actually: max loss = s0 (stock goes to 0, loss S_0) + keep premium
            # Wait: profit = S_T - S_0 + prem - max(S_T-K, 0)
            # If S_T=0: profit = 0 - S0 + prem - 0 = prem - S0
            # If S_T=inf: profit = S_T - S0 + prem - (S_T-K) = K - S0 + prem
            max_loss = premium1 - s0
            be1 = s0 - premium1
            be_points = sorted({round(p, 2) for p in [be1] if p >= 0})

        elif strategy == "protective_put":
            k2 = strike2 if strike2 is not None else k1
            pnl = _protective_put_pnl(spot_range, s0, k1, premium1)
            legs_desc = f"Long stock @ {s0} + Long put @ {k1}（权利金支出 {premium1}）"
            # profit = S_T - S_0 - prem + max(K-S_T, 0)
            # if S_T >= K: profit = S_T - S_0 - prem, unlimited upside
            # if S_T < K: profit = K - S_0 - prem (floor)
            max_profit = None  # unlimited upside
            max_loss = premium1 - (k1 - s0)  # = s0 + prem - k1
            if s0 + premium1 > k1:
                max_loss = s0 + premium1 - k1
            else:
                max_loss = premium1 + s0 - k1
            # Wait: floor is when S_T=0: profit = 0 - s0 - prem + (K-0) = K - s0 - prem
            max_loss = k1 - s0 - premium1  # this is negative if k1 < s0+prem
            be1 = s0 + premium1
            be_points = sorted({round(p, 2) for p in [be1] if p >= 0})

        elif strategy == "straddle":
            k2 = strike2 if strike2 is not None else k1
            pnl = _straddle_pnl(spot_range, k1, premium1)
            legs_desc = f"Long call @ {k1} + Long put @ {k1}（总权利金支出 {2 * premium1}）"
            max_profit = None  # unlimited upside
            max_loss = -2.0 * premium1
            be_low = k1 - 2.0 * premium1
            be_high = k1 + 2.0 * premium1
            be_points = sorted({round(p, 2) for p in [be_low, be_high] if p >= 0})

        elif strategy == "strangle":
            k2 = strike2 if strike2 is not None else s0 * 1.1
            p2 = premium2 if premium2 is not None else premium1 * 0.8
            pnl = _strangle_pnl(spot_range, k1, k2, premium1, p2)
            legs_desc = f"Long put @ {k1}（权利金 {premium1}）+ Long call @ {k2}（权利金 {p2}）"
            total_prem = premium1 + p2
            max_loss = -total_prem
            be_low = k1 - total_prem
            be_high = k2 + total_prem
            max_profit = None  # unlimited upside
            be_points = sorted({round(p, 2) for p in [be_low, be_high] if p >= 0})

        elif strategy == "bull_spread":
            k2 = strike2 if strike2 is not None else k1 * 1.1
            p2 = premium2 if premium2 is not None else premium1 * 0.6
            pnl = _bull_spread_pnl(spot_range, k1, k2, premium1, p2)
            legs_desc = f"Long call @ {k1}（权利金 {premium1}）+ Short call @ {k2}（权利金 {p2}）"
            net_prem = premium1 - p2
            max_loss = -net_prem
            max_profit = (k2 - k1) - net_prem
            be1 = k1 + net_prem
            be_points = sorted({round(p, 2) for p in [be1] if p >= 0})

        elif strategy == "bear_spread":
            k2 = strike2 if strike2 is not None else k1 * 0.9
            p2 = premium2 if premium2 is not None else premium1 * 0.6
            pnl = _bear_spread_pnl(spot_range, k1, k2, premium1, p2)
            legs_desc = f"Long put @ {k1}（权利金 {premium1}）+ Short put @ {k2}（权利金 {p2}）"
            net_prem = premium1 - p2
            max_loss = -net_prem
            max_profit = (k1 - k2) - net_prem
            be1 = k1 - net_prem
            be_points = sorted({round(p, 2) for p in [be1] if p >= 0})

        elif strategy == "iron_condor":
            # Bear put spread: long put at k1, short put at k2
            # Bull call spread: long call at k3, short call at k4
            # Default: k1=s0*1.1, k2=s0*1.05, k3=s0*0.95, k4=s0*0.9
            k2_val = strike2 if strike2 is not None else s0 * 1.05
            k3 = s0 * 0.95
            k4 = s0 * 0.90
            p2_val = premium2 if premium2 is not None else premium1 * 0.7
            p3 = premium1 * 0.7
            p4 = premium1 * 0.5
            pnl = _iron_condor_pnl(spot_range, k1, k2_val, k3, k4, premium1, p2_val, p3, p4)
            legs_desc = (
                f"Bear put spread: long put @ {k1}（{premium1}）+ short put @ {k2_val}（{p2_val}）；"
                f"Bull call spread: long call @ {k3}（{p3}）+ short call @ {k4}（{p4}）"
            )
            net_prem = (p2_val + p4) - (premium1 + p3)
            max_profit = net_prem
            max_loss = (k1 - k2_val) - net_prem  # width of put spread minus net credit
            be_low = k1 + net_prem
            be_high = k4 - net_prem
            be_points = sorted({round(p, 2) for p in [be_low, be_high] if p >= 0})
            # Fix: iron_condor max profit/loss logic
            # Net credit = credit received - debit paid
            # Put spread: sell k2 (higher credit), buy k1 (lower debit)
            # In iron condor: bear put spread = sell put at k2, buy put at k1 (k1 > k2)
            # Bull call spread = buy call at k3, sell call at k4 (k3 < k4)
            # If we receive net credit: max profit = net credit
            # Width = k1 - k2 (put spread width) or k4 - k3 (call spread width)
            # Max loss = width - net credit
            width_put = k1 - k2_val
            width_call = k4 - k3
            width = min(width_put, width_call)
            max_loss = width - net_prem if net_prem < width else 0.0

        # Build PnL table
        pnl_list = []
        for i in range(len(spot_range)):
            pnl_list.append({
                "spot_price_at_expiry": round(float(spot_range[i]), 4),
                "pnl": round(float(pnl[i]), 4),
            })

        # Break-even point filter (make sure it's within price range and reasonable)
        be_points = [p for p in be_points if 0 <= p <= 2 * s0]

        payload = {
            "status": "ok",
            "strategy": strategy_info["label"],
            "strategy_description": strategy_info["description"],
            "legs": legs_desc,
            "max_profit": round(max_profit, 4) if max_profit is not None else "无穷（理论上限）",
            "max_loss": round(max_loss, 4) if max_loss is not None else "无穷（理论下限）",
            "break_even_points": be_points,
            "pnl_table": pnl_list,
            "visualization_note": (
                "The above profit and loss are the profit and loss on the maturity date (time value is not considered)."
                "PnL Tables can be imported into Excel/matplotlib for visualization."
            ),
            "parameters_used": {
                "strategy_type": strategy,
                "spot_price": s0,
                "strike1": k1,
                "strike2": strike2 if strike2 is not None else k2 if strategy in ("covered_call", "protective_put", "straddle") else k2 if strategy in ("strangle", "bull_spread", "bear_spread") else k2_val if strategy == "iron_condor" else None,
                "premium1": premium1,
                "premium2": premium2,
                "time_to_expiry_years": time_to_expiry,
                "volatility": volatility,
            },
            "methodology": (
                "Calculation of profit and loss on maturity date:PnL = Sum of intrinsic value of each leg – net royalty payout (+ net royalty income)."
                "covered_call: PnL = (S_T - S_0) + premium - max(S_T - K, 0)；"
                "protective_put: PnL = (S_T - S_0) - premium + max(K - S_T, 0)；"
                "straddle: PnL = |S_T - K| - 2×premium；"
                "strangle: PnL = max(K1 - S_T, 0) + max(S_T - K2, 0) - (prem1 + prem2)；"
                "bull_spread: PnL = max(S_T-K1,0) - max(S_T-K2,0) - prem1 + prem2；"
                "bear_spread: PnL = max(K1-S_T,0) - max(K2-S_T,0) - prem1 + prem2；"
                "iron_condor: 4 Leg combination = bear put spread + bull call spread. "
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Option strategy profit and loss analysis failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_black_scholes_price",
    "get_implied_volatility",
    "get_option_greeks",
    "get_option_strategy_pnl",
]
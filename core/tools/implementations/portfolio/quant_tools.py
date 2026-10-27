"""
Portfolio Quantitative Analysis Tools

Provides professional quantitative analysis functions such as efficient frontier, Monte Carlo simulation, and factor attribution.
All calculations are based on purely mathematical methods without the involvement of LLM.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional

import numpy as np
import pandas as pd
from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_daily_quotes, get_stock_basic_info
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


# ============================================================
#  Helper function
# ============================================================

def _safe_float(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")


def _load_returns_for_symbol(symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
    """Get the return series of a single stock."""
    end_date = _today()
    start_date = _days_ago(int(lookback_days) * 2 + 50)
    quotes = get_stock_daily_quotes(
        str(symbol), start_date, end_date, limit=int(lookback_days) + 100
    )
    if not quotes:
        return None
    df = pd.DataFrame(quotes)
    df["close"] = df["close"].apply(_safe_float)
    df["trade_date"] = df["trade_date"].astype(str)
    df = df.dropna(subset=["close"]).sort_values("trade_date")
    df["return"] = df["close"].pct_change()
    df = df.dropna(subset=["return"])
    df["symbol"] = str(symbol)
    return df[["trade_date", "return", "symbol"]]


# ============================================================
#  Tool 1: efficient frontier
# ============================================================

@tool
@register_tool(
    tool_id="get_efficient_frontier",
    name="有效前沿分析",
    description="Based on the Markowitz mean-variance model, calculate the efficient frontier curve of the investment portfolio, the maximum Sharpe ratio portfolio (cut point portfolio) and the minimum volatility portfolio.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["portfolio_analysis", "risk_management"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["efficient_frontier", "portfolio_optimization"],
    when_to_use="Use it when you need to analyze the risk-return characteristics of a multi-asset portfolio and find the optimal asset allocation ratio.",
    when_not_to_use="It cannot be calculated when there is insufficient data (at least 2 stocks with valid data and each of at least 30 trading days are required).",
    returns="Returns JSON, containing max_sharpe (return, volatility, Sharpe ratio, weight), min_vol (return, volatility, weight), frontier_points, portfolio_stats.",
    example="get_efficient_frontier(symbols='600519,000001,300750', lookback_days=252, risk_free_rate=0.025, num_portfolios=5000)",
    related_tools=["get_monte_carlo_simulation", "get_sharpe_ratio"],
)
def get_efficient_frontier(
    symbols: Annotated[str, "List of stock symbols, separated by commas, such as '600519,000001,300750'"],
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
    risk_free_rate: Annotated[float, "Risk-free interest rate, default 0.025 (2.5%)"] = 0.025,
    num_portfolios: Annotated[int, "Number of combinations for Monte Carlo simulation, default 5000"] = 5000,
) -> str:
    """Calculate the portfolio efficient frontier. Based on the Markowitz mean-variance model, the maximum Sharpe combination, the minimum fluctuation combination and the frontier curve are given.

    Args:
        symbols: List of stock symbols, separated by commas, such as "600519,000001,300750" (At least 2)
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)
        risk_free_rate: Risk-free interest rate, default 0.025 (2.5%)
        num_portfolios: Number of random combinations for Monte Carlo simulation, default 5000

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            max_sharpe: dict, Maximum Sharpe Ratio Combination——
                — return: annualized income
                — volatility: annualized volatility
                — sharpe_ratio: Sharpe ratio
                — weights: dict[str, float], Weight of each stock
            min_vol: dict, minimum volatility portfolio——
                — return: annualized income
                — volatility: annualized volatility
                — weights: dict[str, float], Weight of each stock
            frontier_points: list[dict], Efficient frontier curve point, element structure——
                — return: target income
                — volatility: Corresponds to the minimum volatility
            portfolio_stats: dict, Combination statistics——
                — num_assets: Number of assets
                — valid_symbols: list[str], The actual valid stock symbol used
                — num_portfolios_simulated: Number of simulation combinations
                — overlapping_trading_days: Number of overlapping trading days
                — risk_free_rate: risk-free rate
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        symbol_list = [s.strip() for s in str(symbols).split(",") if s.strip()]
        if len(symbol_list) < 2:
            return json.dumps(
                {"status": "error", "message": "At least 2 stocks are required for efficient frontier analysis."},
                ensure_ascii=False, indent=2, default=str,
            )

        rf = float(risk_free_rate) if risk_free_rate is not None else 0.025

        # Obtain the return data of each stock and merge it
        returns_dfs = []
        valid_symbols = []
        for sym in symbol_list:
            df = _load_returns_for_symbol(sym, int(lookback_days))
            if df is not None and len(df) >= 30:
                returns_dfs.append(df.rename(columns={"return": sym})[[sym, "trade_date"]])
                valid_symbols.append(sym)
            else:
                warnings.append(f"{sym} Insufficient data (requires at least 30 trading days), excluded.")

        if len(valid_symbols) < 2:
            return json.dumps(
                {"status": "error", "message": "There are less than 2 stocks with at least data, so efficient frontier analysis cannot be performed.", "warnings": warnings},
                ensure_ascii=False, indent=2, default=str,
            )

        # Consolidated return data
        merged = returns_dfs[0]
        for df in returns_dfs[1:]:
            merged = pd.merge(merged, df, on="trade_date", how="inner")
        merged = merged.dropna()
        merged = merged.set_index("trade_date")

        if len(merged) < 20:
            return json.dumps(
                {"status": "error", "message": f"股票间重叠交易日仅 {len(merged)} 天，不足20天。", "warnings": warnings},
                ensure_ascii=False, indent=2, default=str,
            )

        returns_matrix = merged.values
        n_assets = len(valid_symbols)
        mean_returns = np.mean(returns_matrix, axis=0)
        cov_matrix = np.cov(returns_matrix, rowvar=False)

        # Monte Carlo simulation of random combinations
        np.random.seed(42)
        results = np.zeros((3, int(num_portfolios)))
        weights_record = []

        for i in range(int(num_portfolios)):
            weights = np.random.random(n_assets)
            weights = weights / np.sum(weights)
            weights_record.append(weights)

            port_return = np.sum(mean_returns * weights) * 252
            port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(252)
            sharpe = (port_return - rf) / port_vol if port_vol > 0 else 0

            results[0, i] = port_return
            results[1, i] = port_vol
            results[2, i] = sharpe

        # Maximum Sharpe Ratio Combination
        max_sharpe_idx = np.argmax(results[2])
        max_sharpe_weights = weights_record[max_sharpe_idx]
        max_sharpe_portfolio = {
            "return": float(round(results[0, max_sharpe_idx], 6)),
            "volatility": float(round(results[1, max_sharpe_idx], 6)),
            "sharpe_ratio": float(round(results[2, max_sharpe_idx], 4)),
            "weights": {sym: float(round(w, 6)) for sym, w in zip(valid_symbols, max_sharpe_weights)},
        }

        # minimum volatility portfolio
        min_vol_idx = np.argmin(results[1])
        min_vol_weights = weights_record[min_vol_idx]
        min_vol_portfolio = {
            "return": float(round(results[0, min_vol_idx], 6)),
            "volatility": float(round(results[1, min_vol_idx], 6)),
            "weights": {sym: float(round(w, 6)) for sym, w in zip(valid_symbols, min_vol_weights)},
        }

        # Efficient frontier curve (try using scipy.optimize to calculate the theoretical frontier)
        frontier_points = []
        try:
            from scipy.optimize import minimize

            def portfolio_stats(weights):
                weights = np.array(weights)
                port_return = np.sum(mean_returns * weights) * 252
                port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(252)
                return port_return, port_vol

            constraints = {"type": "eq", "fun": lambda x: np.sum(x) - 1}
            bounds = tuple((0, 1) for _ in range(n_assets))

            target_returns = np.linspace(
                min_vol_portfolio["return"],
                max(results[0]) * 0.95,
                50,
            )

            for target in target_returns:
                cons = [constraints, {"type": "eq", "fun": lambda x, t=target: np.sum(mean_returns * x) * 252 - t}]
                init_guess = np.array([1.0 / n_assets] * n_assets)
                result = minimize(
                    lambda w: np.sqrt(np.dot(w.T, np.dot(cov_matrix, w))) * np.sqrt(252),
                    init_guess,
                    method="SLSQP",
                    bounds=bounds,
                    constraints=cons,
                )
                if result.success:
                    opt_weights = result.x
                    opt_vol = np.sqrt(np.dot(opt_weights.T, np.dot(cov_matrix, opt_weights))) * np.sqrt(252)
                    frontier_points.append({
                        "return": float(round(target, 6)),
                        "volatility": float(round(opt_vol, 6)),
                    })
        except ImportError:
            # scipy Not available, uses front point from Monte Carlo simulation results
            # Sort by volatility and take the Pareto optimal of each return interval
            df_results = pd.DataFrame({
                "return": results[0],
                "volatility": results[1],
            }).sort_values("volatility")
            best_by_return = {}
            for _, row in df_results.iterrows():
                ret_key = round(row["return"], 4)
                if ret_key not in best_by_return or row["volatility"] < best_by_return[ret_key]["volatility"]:
                    best_by_return[ret_key] = {"return": row["return"], "volatility": row["volatility"]}
            frontier_points = sorted(best_by_return.values(), key=lambda x: x["return"])
            warnings.append("scipy Uninstalled, approximate results of the efficient frontier using Monte Carlo simulations.")

        # Combined statistical summary
        portfolio_stats_data = {
            "num_assets": n_assets,
            "valid_symbols": valid_symbols,
            "num_portfolios_simulated": int(num_portfolios),
            "overlapping_trading_days": len(merged),
            "risk_free_rate": rf,
        }

        payload = {
            "status": "success",
            "max_sharpe": max_sharpe_portfolio,
            "min_vol": min_vol_portfolio,
            "frontier_points": frontier_points,
            "portfolio_stats": portfolio_stats_data,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("有效前沿分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 2: Monte Carlo simulation
# ============================================================

@tool
@register_tool(
    tool_id="get_monte_carlo_simulation",
    name="蒙特卡洛模拟",
    description="Carry out Monte Carlo price path simulation for a single stock based on the geometric Brownian motion model, and return the simulation path, terminal value distribution, VaR, CVaR, expected return and confidence interval, etc.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["portfolio_analysis", "risk_management"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["price_simulation", "monte_carlo"],
    when_to_use="It is used when it is necessary to evaluate the possible distribution range of future stock prices or to measure risk.",
    when_not_to_use="When there is insufficient data (less than 30 trading days), the simulation results have limited reference value.",
    returns="Returns JSON, including parameters, simulation_count, stats (median, p5, p95, mean, std, prob_loss), sample_paths, current_price.",
    example="get_monte_carlo_simulation(symbol='600519', days=252, simulations=1000)",
    related_tools=["get_efficient_frontier", "get_var_calculation"],
)
def get_monte_carlo_simulation(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    days: Annotated[int, "Number of simulated trading days, default 252 (about 1 year)"] = 252,
    simulations: Annotated[int, "Number of simulation paths, default 1000"] = 1000,
    mu: Annotated[Optional[float], "Annualized rate of return expectations, if not specified, estimate from historical data"] = None,
    sigma: Annotated[Optional[float], "Annualized volatility, if not passed, it is estimated from historical data."] = None,
) -> str:
    """Monte Carlo price simulation based on geometric Brownian motion. Predict future price distribution and risk indicators.

    Args:
        symbol: A stock code, such as 600519,000001
        days: Number of trading days to simulate, default 252 (approximately 1 year)
        simulations: Number of simulation paths, default 1000 (actual will be limited to 10000)
        mu: Annualized rate of return expectation; estimated from historical data when None
        sigma: Annualized volatility; estimated from historical data when None

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            current_price: Current price (simulation starting point)
            parameters: dict, Simulation parameters——
                — mu_annual: Annualized rate of return expectations
                — sigma_annual: annualized volatility
                — mu_source: "user_provided" | "estimated"
                — sigma_source: "user_provided" | "estimated"
                — days: Simulated trading days
            simulation_count: Actual number of simulation paths
            stats: dict, final price statistics——
                — median: median
                — mean: mean
                — std: standard deviation
                — p5: 5 Quantile
                — p95: 95 Quantile
                — prob_loss: Probability of loss (the proportion of the final price lower than the current price)
                — min: minimum value
                — max: maximum value
            sample_paths: list[dict], Sample paths (up to 100), element structure——
                — simulation_id: Analog number
                — final_price: final price
                — path: list[float], daily price series
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        end_date = _today()
        start_date = _days_ago(int(days) * 2 + 50)

        quotes = get_stock_daily_quotes(
            str(symbol), start_date, end_date, limit=int(days) + 100
        )

        if not quotes:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        df["close"] = df["close"].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["close"]).sort_values("trade_date")
        df["return"] = df["close"].pct_change()
        df = df.dropna(subset=["return"])

        returns = df["return"].values
        current_price = float(df["close"].iloc[-1])

        if len(returns) < 30:
            warnings.append(f"有效收益率数据仅 {len(returns)} 天，不足30天，模拟结果参考价值有限。")

        # estimated parameters
        estimated_mu = float(np.mean(returns) * 252) if mu is None else float(mu)
        estimated_sigma = float(np.std(returns, ddof=1) * np.sqrt(252)) if sigma is None else float(sigma)

        if estimated_sigma <= 0:
            return json.dumps(
                {"status": "error", "message": "Volatility is estimated to be zero and cannot be simulated."},
                ensure_ascii=False, indent=2, default=str,
            )

        n_days = int(days)
        n_sim = min(int(simulations), 10000)  # Limit the maximum number of simulations
        dt = 1.0 / 252

        # Monte Carlo simulation
        np.random.seed(42)
        random_matrix = np.random.standard_normal((n_days, n_sim))

        # Geometric Brownian motion:S_t = S_0 * exp((mu - 0.5*sigma^2)*t + sigma * sqrt(t) * Z)
        drift = (estimated_mu - 0.5 * estimated_sigma ** 2) * dt
        diffusion = estimated_sigma * np.sqrt(dt) * random_matrix
        price_paths = np.exp(np.cumsum(drift + diffusion, axis=0))
        price_paths = current_price * price_paths

        # final price array
        final_prices = price_paths[-1, :]

        # Statistical indicators
        median_price = float(np.median(final_prices))
        p5_price = float(np.percentile(final_prices, 5))
        p95_price = float(np.percentile(final_prices, 95))
        mean_price = float(np.mean(final_prices))
        std_price = float(np.std(final_prices, ddof=1))
        prob_loss = float(np.mean(final_prices < current_price))

        # Extract sample paths (up to 100 for display)
        sample_indices = np.linspace(0, n_sim - 1, min(100, n_sim), dtype=int)
        sample_paths_list = []
        for idx in sample_indices:
            path = price_paths[:, idx]
            sample_paths_list.append({
                "simulation_id": int(idx),
                "final_price": float(round(path[-1], 3)),
                "path": [float(round(p, 3)) for p in path],
            })

        payload = {
            "status": "success",
            "symbol": str(symbol),
            "current_price": float(round(current_price, 3)),
            "parameters": {
                "mu_annual": float(round(estimated_mu, 6)),
                "sigma_annual": float(round(estimated_sigma, 6)),
                "mu_source": "user_provided" if mu is not None else "estimated",
                "sigma_source": "user_provided" if sigma is not None else "estimated",
                "days": n_days,
            },
            "simulation_count": n_sim,
            "stats": {
                "median": float(round(median_price, 3)),
                "mean": float(round(mean_price, 3)),
                "std": float(round(std_price, 3)),
                "p5": float(round(p5_price, 3)),
                "p95": float(round(p95_price, 3)),
                "prob_loss": float(round(prob_loss, 6)),
                "min": float(round(float(np.min(final_prices)), 3)),
                "max": float(round(float(np.max(final_prices)), 3)),
            },
            "sample_paths": sample_paths_list,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("蒙特卡洛模拟失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 3: factor attribution
# ============================================================

@tool
@register_tool(
    tool_id="get_factor_attribution",
    name="因子归因分析",
    description="Perform simplified factor attribution analysis on individual stocks and calculate Alpha, Beta,R² and market factor explanation, return factor contribution, residual income and attribution conclusions, and identify income sources.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["factor_analysis", "risk_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["factor_attribution", "return_decomposition"],
    when_to_use="Use it when you need to analyze the source of returns of individual stocks and distinguish between Alpha (excess returns) and Beta (market returns).",
    when_not_to_use="Analytical results are limited when there is insufficient data (less than 30 trading days) or market portfolio data is missing.",
    returns="Returns JSON containing factor_model, alpha, beta, r_squared, explained_by_market_pct, stock_specific_pct, data_quality.",
    example="get_factor_attribution(symbol='600519', lookback_days=252)",
    related_tools=["get_beta_calculation", "get_efficient_frontier"],
)
def get_factor_attribution(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
) -> str:
    """Perform simplified factor attribution analysis on individual stocks. Based on the single-factor CAPM model to decompose Alpha, Beta,R² and market interpretability.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            factor_model: factor model name,"single_factor_capm" or "single_factor_simplified"
            alpha: Annualized Alpha (0.0 in simplified model)
            beta: Beta Coefficient (1.0 under simplified model)
            r_squared: coefficient of determination R² (None in the simplified model)
            explained_by_market_pct: Market factor explanation percentage (None in simplified model)
            stock_specific_pct: The percentage of individual stock idiosyncratic returns (None in the simplified model)
            annualized_return: annualized income
            annualized_volatility: annualized volatility
            residual_std: Residual standard deviation (returned for full CAPM model only)
            skewness: Skewness
            kurtosis: kurtosis
            pe_ttm: Rolling price-to-earnings ratio (None when basic information is missing)
            pb: Price-to-book ratio (None when basic information is missing)
            data_quality: dict, Data quality——
                — return_data_points: Return sample number
                — overlapping_days: Number of trading days overlapped with benchmark (full model only)
                — has_benchmark: Are there any benchmarks available?
                — benchmark_symbol: Base code ("000300") 
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        sym = str(symbol)
        end_date = _today()
        start_date = _days_ago(int(lookback_days) * 2 + 50)

        # Get basic information
        basic_info = get_stock_basic_info(sym) or {}

        # Get daily data
        quotes = get_stock_daily_quotes(
            sym, start_date, end_date, limit=int(lookback_days) + 100
        )

        if not quotes:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {sym} 的日线数据。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        df["close"] = df["close"].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["close"]).sort_values("trade_date")
        df["return"] = df["close"].pct_change()
        df = df.dropna(subset=["return"])

        stock_returns = df["return"].values

        if len(stock_returns) < 30:
            return json.dumps(
                {"status": "error", "message": f"{sym} The effective return data is less than 30 trading days, and factor attribution cannot be reliably performed.",
                 "warnings": warnings},
                ensure_ascii=False, indent=2, default=str,
            )

        # Constructing Market Portfolio Agents: Using Own Earnings + Other available data
        # Try to get CSI 300 (000300) as market benchmark
        market_symbol = "000300"
        market_quotes = get_stock_daily_quotes(
            market_symbol, start_date, end_date, limit=int(lookback_days) + 100
        )

        use_market_proxy = False
        if market_quotes and len(market_quotes) > 20:
            mkt_df = pd.DataFrame(market_quotes)
            mkt_df["close"] = mkt_df["close"].apply(_safe_float)
            mkt_df["trade_date"] = mkt_df["trade_date"].astype(str)
            mkt_df = mkt_df.dropna(subset=["close"]).sort_values("trade_date")
            mkt_df["return"] = mkt_df["close"].pct_change()
            mkt_df = mkt_df.dropna(subset=["return"])

            # Align dates
            merged = pd.merge(
                df[["trade_date", "return"]],
                mkt_df[["trade_date", "return"]],
                on="trade_date",
                how="inner",
                suffixes=("_stock", "_market"),
            )

            if len(merged) >= 30:
                stock_r = merged["return_stock"].values
                market_r = merged["return_market"].values
                use_market_proxy = True
        else:
            warnings.append(f"未获取到基准指数 {market_symbol} 数据。")

        if not use_market_proxy:
            # Unable to obtain market benchmark, use simplified model
            # Using the stock's own return as a market proxy,beta=1
            payload = {
                "status": "success",
                "symbol": sym,
                "factor_model": "single_factor_simplified",
                "alpha": 0.0,
                "beta": 1.0,
                "r_squared": None,
                "explained_by_market_pct": None,
                "stock_specific_pct": None,
                "annualized_return": float(round(float(np.mean(stock_returns) * 252), 6)),
                "annualized_volatility": float(round(float(np.std(stock_returns, ddof=1) * np.sqrt(252)), 6)),
                "skewness": float(round(float(pd.Series(stock_returns).skew()), 4)),
                "kurtosis": float(round(float(pd.Series(stock_returns).kurtosis()), 4)),
                "pe_ttm": _safe_float(basic_info.get("pe_ttm")),
                "pb": _safe_float(basic_info.get("pb")),
                "data_quality": {
                    "return_data_points": len(stock_returns),
                    "has_benchmark": False,
                    "benchmark_symbol": market_symbol,
                },
                "warnings": warnings + ["Without benchmark index data, a simplified model is used (beta=1.0) . "],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

        # OLS Return:stock_return = alpha + beta * market_return + epsilon
        X = np.column_stack([np.ones(len(market_r)), market_r])
        y = stock_r

        try:
            coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return json.dumps(
                {"status": "error", "message": "OLS Regression calculation failed."},
                ensure_ascii=False, indent=2, default=str,
            )

        alpha_daily = coeffs[0]
        beta = coeffs[1]

        # annualized Alpha
        alpha_annualized = alpha_daily * 252

        # R²
        y_pred = X @ coeffs
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # market interpretability
        market_contribution = beta * market_r
        total_explained = y_pred - alpha_daily  # exclude alpha
        explained_by_market = np.var(market_contribution, ddof=1)
        total_return_var = np.var(y, ddof=1)
        if total_return_var > 0:
            explained_by_market_pct = explained_by_market / total_return_var * 100
            stock_specific_pct = (1.0 - r_squared) * 100
        else:
            explained_by_market_pct = 0.0
            stock_specific_pct = 0.0

        # statistical characteristics
        residuals = y - y_pred
        annualized_return = float(np.mean(stock_returns) * 252)
        annualized_vol = float(np.std(stock_returns, ddof=1) * np.sqrt(252))

        payload = {
            "status": "success",
            "symbol": sym,
            "factor_model": "single_factor_capm",
            "alpha": float(round(alpha_annualized, 6)),
            "beta": float(round(beta, 4)),
            "r_squared": float(round(r_squared, 4)),
            "explained_by_market_pct": float(round(explained_by_market_pct, 2)),
            "stock_specific_pct": float(round(stock_specific_pct, 2)),
            "annualized_return": float(round(annualized_return, 6)),
            "annualized_volatility": float(round(annualized_vol, 6)),
            "residual_std": float(round(float(np.std(residuals, ddof=1)), 6)),
            "skewness": float(round(float(pd.Series(stock_returns).skew()), 4)),
            "kurtosis": float(round(float(pd.Series(stock_returns).kurtosis()), 4)),
            "pe_ttm": _safe_float(basic_info.get("pe_ttm")),
            "pb": _safe_float(basic_info.get("pb")),
            "data_quality": {
                "return_data_points": len(stock_returns),
                "overlapping_days": len(market_r),
                "has_benchmark": True,
                "benchmark_symbol": market_symbol,
            },
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("因子归因分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_efficient_frontier", "get_monte_carlo_simulation", "get_factor_attribution"]

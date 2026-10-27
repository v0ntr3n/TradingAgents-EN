"""Dividend yield valuation enhancement and industry valuation distribution tools.

Provided by:
1. get_dividend_valuation_context — Dividend yield valuation strengthens
2. get_industry_valuation_distribution — Industry valuation distribution
"""

import json
import logging
from statistics import mean, median
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool

from core.skill_runtime.data_access import (
    get_latest_stock_price,
    get_stock_basic_info,
)
from core.skill_runtime.standard_financial_apis import (
    get_historical_financial_annual_series,
    get_shareholder_return_metrics,
)
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


# ==================== Inside the tool helper ====================

def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _safe_float(value) -> Optional[float]:
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


def _cagr(values: List[Optional[float]]) -> Optional[float]:
    """Calculate the 3-year CAGR (Compound Annual Growth Rate)."""
    valid = [v for v in values if v is not None and v > 0]
    if len(valid) < 2:
        return None
    n = len(valid)
    return (valid[0] / valid[-1]) ** (1.0 / max(n - 1, 1)) - 1.0


def _json_response(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _fetch_akshare_dividend_yield(symbol: str) -> Optional[Dict[str, Any]]:
    """Try using AKShare Oriental Wealth Dividend Data to find out."""
    try:
        import akshare as ak
        df = ak.stock_dividents_cninfo(symbol=symbol)
        if df is None or df.empty:
            return None
        # Get only implemented records
        df = df[df["实施进度"] == "实施"]
        if df.empty:
            return None
        df = df.sort_values("股权登记日", ascending=False)
        records = df.head(5).to_dict("records")
        return {"source": "akshare", "records": records}
    except Exception as exc:
        logger.warning("AKShare dividend fallback failed: %s", exc)
        return None


# ==================== Tool 1: Dividend yield valuation strengthens ====================

@tool
@register_tool(
    tool_id="get_dividend_valuation_context",
    name="股息率估值增强",
    description=(
        "Calculate the current dividend rate, 5-year average dividend rate, and historical dividend rate quantile based on dividend records."
        "Payout ratio, dividend growth rate (3-year CAGR), and give a valuation signal (below average=underestimated)."
        "When local data is insufficient, use AKShare to take care of the problem."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "dividend", "dividend_yield", "payout_ratio", "dividend_growth"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["分红估值分析", "股息率历史分位", "派息率评估"],
    when_to_use="Use when dividend rate valuation, dividend return analysis, dividend rate historical quantile or dividend growth rate are required.",
    when_not_to_use="Not suitable for companies with no dividend record (no_dividend_data will be returned). Not suitable for high growth non-dividend paying companies.",
    returns="Returns a JSON string containing current_yield, avg_5y_yield, yield_percentile, payout_ratio, divided_growth, evaluation_signal, divided_history, data_quality.",
    example="get_dividend_valuation_context(symbol='600519')",
    related_tools=["get_ddm_valuation", "get_dividend_data"],
)
def get_dividend_valuation_context(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
) -> str:
    """Get dividend yield valuation enhancement context.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: Status: "success" | "error"
            symbol: Standardized 6-digit stock code
            current_price: current stock price
            current_yield: Current Dividend Yield (Decimal)
            current_yield_pct: Current dividend yield (%)
            avg_5y_yield: 5 Average annual dividend rate (decimal)
            avg_5y_yield_pct: 5 Annual average dividend rate (%)
            yield_percentile: Current dividend yield historical quantile (0-100)
            payout_ratio: Payout ratio (decimal)
            payout_ratio_pct: Dividend payout rate (%)
            dividend_growth: Dividend 3-year CAGR (decimal)
            dividend_growth_pct: Dividend 3-year CAGR (%)
            valuation_signal: valuation signal: "underestimate" | "Neutral" | "overestimate"
            dividend_history: list[dict] Dividend history (last 5 years), element structure——
                — year: Year
                — cash_dividend_per_share: Cash dividend per share
                — dividend_yield: Dividend rate (decimal)
                — dividend_yield_pct: Dividend yield (%)
            data_quality: Data quality: "Sufficient data" | "Data is limited" | "Not enough data"
            data_source: Data source identification
            warnings: list[str] warning list
            message: Error message (only status="error" exist)
    """
    try:
        normalized_symbol = str(symbol).strip().upper()
        for prefix in ("SH", "SZ", "SS", "BJ"):
            normalized_symbol = normalized_symbol.replace(prefix, "")
        normalized_symbol = "".join(ch for ch in normalized_symbol if ch.isdigit())[-6:].zfill(6)
        if not normalized_symbol:
            return _json_response({"status": "error", "message": "无效股票代码"})

        # 1. Get current price
        current_price = get_latest_stock_price(normalized_symbol)
        if current_price is None or current_price <= 0:
            basic = get_stock_basic_info(normalized_symbol) or {}
            current_price = _safe_float(basic.get("close") or basic.get("current_price"))

        if current_price is None or current_price <= 0:
            return _json_response({"status": "error", "message": "未获取到有效现价", "symbol": normalized_symbol})

        # 2. Get shareholder return/dividend data
        shareholder = get_shareholder_return_metrics(normalized_symbol, years=5)
        dividend_annual = shareholder.get("annual") or []
        dividend_records = shareholder.get("records") or []
        data_source = shareholder.get("data_source") or "local"

        # If the local dividend data is insufficient, try AKShare to find out.
        if not dividend_annual and not dividend_records:
            akshare_data = _fetch_akshare_dividend_yield(normalized_symbol)
            if akshare_data:
                data_source = akshare_data.get("source", "akshare")

        # 3. Calculate dividend rate for each year
        annual_yields: List[Dict[str, Any]] = []
        for entry in dividend_annual:
            year = entry.get("year")
            cash = _safe_float(entry.get("cash_dividend_per_share"))
            if year and cash is not None:
                yield_val = cash / current_price
                annual_yields.append({
                    "year": year,
                    "cash_dividend_per_share": cash,
                    "dividend_yield": yield_val,
                    "dividend_yield_pct": round(yield_val * 100, 4),
                })

        # 4. core indicators
        current_yield = annual_yields[0]["dividend_yield"] if annual_yields else None
        yield_values = [item["dividend_yield"] for item in annual_yields if item["dividend_yield"] is not None]
        avg_5y_yield = mean(yield_values) if yield_values else None

        # Dividend rate historical quantile (the position of the current yield in the historical queue)
        yield_percentile = None
        if current_yield is not None and yield_values:
            sorted_yields = sorted(yield_values)
            yield_percentile = sum(1 for y in sorted_yields if y <= current_yield) / len(sorted_yields) * 100

        # 5. Dividend payout rate (latest period)
        payout_ratio = None
        financial = get_historical_financial_annual_series(normalized_symbol, years=3)
        financial_records = financial.get("records") or []
        latest_cash = annual_yields[0].get("cash_dividend_per_share") if annual_yields else None
        if financial_records and latest_cash is not None:
            latest_financial = financial_records[0]
            net_profit = _safe_float(latest_financial.get("net_profit"))
            if net_profit is not None and net_profit > 0:
                basic_info = get_stock_basic_info(normalized_symbol) or {}
                # total_share/total_shares The unit is "10,000 shares" and requires ×1e4 Converted into "shares",
                # Otherwise, net_profit (yuan)/10,000 shares will amplify EPS by 1e4 times.
                # As a result, the dividend payout ratio is reduced by 1e4 times (for example, Moutai will calculate 0.03%, but the actual ratio is about 50%).
                raw_shares = _safe_float(basic_info.get("total_share") or basic_info.get("total_shares"))
                total_shares = raw_shares * 1e4 if raw_shares is not None and raw_shares > 0 else None
                if total_shares is not None and total_shares > 0:
                    eps_approximate = net_profit / total_shares
                    payout_ratio = latest_cash / eps_approximate if eps_approximate > 0 else None

        # 6. Dividend growth rate (3-year CAGR)
        cash_values = [item["cash_dividend_per_share"] for item in annual_yields[:3]]
        dividend_growth = _cagr(cash_values) if len(cash_values) >= 2 else None

        # 7. valuation signal
        valuation_signal = "中性"
        if current_yield is not None and avg_5y_yield is not None:
            if current_yield > avg_5y_yield:
                valuation_signal = "低估"
            else:
                valuation_signal = "高估"

        # 8. Data quality
        data_quality = "数据充足" if len(annual_yields) >= 3 else "数据有限" if annual_yields else "数据不足"

        return _json_response({
            "status": "success",
            "symbol": normalized_symbol,
            "current_price": current_price,
            "current_yield": round(current_yield, 6) if current_yield is not None else None,
            "current_yield_pct": round(current_yield * 100, 4) if current_yield is not None else None,
            "avg_5y_yield": round(avg_5y_yield, 6) if avg_5y_yield is not None else None,
            "avg_5y_yield_pct": round(avg_5y_yield * 100, 4) if avg_5y_yield is not None else None,
            "yield_percentile": round(yield_percentile, 2) if yield_percentile is not None else None,
            "payout_ratio": round(payout_ratio, 4) if payout_ratio is not None else None,
            "payout_ratio_pct": round(payout_ratio * 100, 2) if payout_ratio is not None else None,
            "dividend_growth": round(dividend_growth, 6) if dividend_growth is not None else None,
            "dividend_growth_pct": round(dividend_growth * 100, 4) if dividend_growth is not None else None,
            "valuation_signal": valuation_signal,
            "dividend_history": annual_yields[:5],
            "data_quality": data_quality,
            "data_source": data_source,
            "warnings": [] if annual_yields else ["Dividend data not found, dividend yield valuation cannot be calculated."],
        })
    except Exception as exc:
        logger.error("Dividend yield valuation enhancement acquisition failed: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"股息率估值增强获取失败: {exc}"})


# ==================== Tool 2: Industry valuation distribution ====================

@tool
@register_tool(
    tool_id="get_industry_valuation_distribution",
    name="行业估值分布",
    description=(
        "Statistical PE/PB distribution by industry (count, mean, median, P25, P75, minimum, maximum),"
        "and returns the Top 10 cheapest and most expensive stocks in each sector."
        "If industry is specified, only this industry will be analyzed, otherwise all industries will be traversed."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need industry valuation distribution, industry PE/PB statistics, or looking for undervalued/overvalued stocks in the industry.",
    returns="Returns a JSON string containing distribution_stats, cheapest_stocks, priciest_stocks, data_quality.",
    example="get_industry_valuation_distribution(industry='Liquor')",
)
def get_industry_valuation_distribution(
    industry: Annotated[str, "Industry name, such as 'Liquor', 'bank'; Analyze all industries for space time"] = "",
) -> str:
    """Get the industry valuation distribution.

    Args:
        industry: Industry name (e.g. "Liquor", "bank") , When it is an empty string, all industries are analyzed, default ""

    Returns:
        str: JSON String, field description——
            status: Status: "success" | "no_data" | "error"
            industries_covered: Number of industries covered
            total_stocks_analyzed: Total number of stocks analyzed
            distribution_stats: dict Industry valuation statistics, key is the industry name, value structure——
                — pe: dict PE Distribution (count/mean/median/p25/p75/min/max)
                — pb: dict PB Distribution (count/mean/median/p25/p75/min/max)
                — sample_count: Number of samples
            cheapest_stocks: dict List of Top 10 stocks with the lowest PE in various industries, element structure——
                — symbol: Stock code
                — name: Stock name
                — pe: PE value
                — pb: PB value
                — total_mv: Total market capitalization
            priciest_stocks: dict List of Top 10 stocks with the highest PE in each industry (structure is the same as above)
            data_quality: Data quality: "Sufficient data" | "Not enough data"
            warnings: list[str] warning list
            message: Error or prompt information (only status is "no_data"/"error" exist)
    """
    try:
        # Get full data from stock_basic_info
        # Aggregation via project_access or direct query
        from core.skill_runtime.project_access import query_stock_collection

        target_industry = str(industry).strip() if industry else None

        # Construct filter conditions
        filters: Dict[str, Any] = {}
        if target_industry:
            filters["industry"] = target_industry
        else:
            filters["industry"] = {"$ne": None, "$ne": ""}

        # Query all stocks with industry affiliation
        stocks = query_stock_collection(
            "stock_basic_info",
            filters=filters,
            projection={
                "_id": 0, "symbol": 1, "name": 1, "industry": 1,
                "pe": 1, "pe_ttm": 1, "pb": 1, "pb_mrq": 1,
                "total_mv": 1, "market_cap": 1,
            },
            limit=500,
        )

        if not stocks:
            msg = f"未找到行业 '{target_industry}' 的股票数据" if target_industry else "No stock data with industry affiliation found"
            return _json_response({"status": "no_data", "message": msg})

        # Group by industry, or use target industry directly
        industry_groups: Dict[str, List[Dict[str, Any]]] = {}
        for stock in stocks:
            ind = str(stock.get("industry") or "").strip()
            if not ind:
                continue
            industry_groups.setdefault(ind, []).append(stock)

        distribution_stats: Dict[str, Dict[str, Any]] = {}
        cheapest_stocks: Dict[str, List[Dict[str, Any]]] = {}
        priciest_stocks: Dict[str, List[Dict[str, Any]]] = {}

        for ind, group in industry_groups.items():
            pe_values = [
                _safe_float(s.get("pe") or s.get("pe_ttm"))
                for s in group
                if _safe_float(s.get("pe") or s.get("pe_ttm")) is not None and _safe_float(s.get("pe") or s.get("pe_ttm")) > 0
            ]
            pb_values = [
                _safe_float(s.get("pb") or s.get("pb_mrq"))
                for s in group
                if _safe_float(s.get("pb") or s.get("pb_mrq")) is not None and _safe_float(s.get("pb") or s.get("pb_mrq")) > 0
            ]

            def _dist(vals: List[float]) -> Dict[str, Any]:
                if not vals:
                    return {"count": 0, "mean": None, "median": None, "p25": None, "p75": None, "min": None, "max": None}
                sorted_vals = sorted(vals)
                n = len(sorted_vals)
                return {
                    "count": n,
                    "mean": round(mean(sorted_vals), 4),
                    "median": round(median(sorted_vals), 4),
                    "p25": round(sorted_vals[n // 4], 4),
                    "p75": round(sorted_vals[3 * n // 4], 4),
                    "min": round(sorted_vals[0], 4),
                    "max": round(sorted_vals[-1], 4),
                }

            distribution_stats[ind] = {
                "pe": _dist(pe_values),
                "pb": _dist(pb_values),
                "sample_count": len(group),
            }

            # Top 10 cheapest / priciest by PE
            pe_stocks = [
                {"symbol": s.get("symbol"), "name": s.get("name"), "pe": _safe_float(s.get("pe") or s.get("pe_ttm")), "pb": _safe_float(s.get("pb") or s.get("pb_mrq")), "total_mv": _safe_float(s.get("total_mv") or s.get("market_cap"))}
                for s in group
                if _safe_float(s.get("pe") or s.get("pe_ttm")) is not None and _safe_float(s.get("pe") or s.get("pe_ttm")) > 0
            ]
            pe_sorted = sorted(pe_stocks, key=lambda x: x["pe"])
            cheapest_stocks[ind] = pe_sorted[:10]
            priciest_stocks[ind] = list(reversed(pe_sorted[-10:])) if len(pe_sorted) >= 10 else list(reversed(pe_sorted))

        # If an industry is specified, only data for that industry will be returned.
        if target_industry and target_industry in distribution_stats:
            result_stats = {target_industry: distribution_stats[target_industry]}
            result_cheapest = {target_industry: cheapest_stocks.get(target_industry, [])}
            result_priciest = {target_industry: priciest_stocks.get(target_industry, [])}
        else:
            result_stats = distribution_stats
            result_cheapest = cheapest_stocks
            result_priciest = priciest_stocks

        total_stocks = sum(v.get("sample_count", 0) for v in result_stats.values())
        industries_covered = len(result_stats)

        return _json_response({
            "status": "success",
            "industries_covered": industries_covered,
            "total_stocks_analyzed": total_stocks,
            "distribution_stats": result_stats,
            "cheapest_stocks": result_cheapest,
            "priciest_stocks": result_priciest,
            "data_quality": "数据充足" if total_stocks > 0 else "数据不足",
            "warnings": [] if total_stocks > 0 else ["No valid data was obtained."],
        })
    except Exception as exc:
        logger.error("Failed to obtain industry valuation distribution: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"行业估值分布获取失败: {exc}"})


__all__ = [
    "get_dividend_valuation_context",
    "get_industry_valuation_distribution",
]
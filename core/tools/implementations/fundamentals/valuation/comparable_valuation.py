"""可比公司估值工具"""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from core.skill_runtime.data_access import (
    get_industry_peer_basic_info,
    get_latest_stock_price,
    get_stock_basic_info,
    summarize_industry_valuation,
)
from core.skill_runtime.standard_financial_apis import get_security_master
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _calc_percentile(values: list[float], current: float) -> float | None:
    valid = [v for v in values if v is not None and v > 0]
    if not valid:
        return None
    return round(sum(1 for v in valid if v <= current) / len(valid) * 100, 1)


@tool
@register_tool(
    tool_id="get_comparable_company_valuation",
    name="可比公司估值",
    description="By comparing with companies in the same industry on PE, PB, and PS valuation indicators, the current stock valuation level is evaluated, and the valuation premium/discount and implied fair value are calculated.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["valuation", "peer_comparison", "relative_valuation"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["relative_valuation", "peer_valuation_comparison"],
    when_to_use="Use it when you need to know the valuation level of a stock in the same industry and judge whether the valuation is too high or too low.",
    when_not_to_use="Not suitable for cross-industry comparisons; not suitable for companies with negative net profits (PE cannot be calculated, but PB/PS is still available).",
    returns="Returns a JSON string, including evaluation_comparison (PE/PB/PS comparison), overall_assessment and fair_value_estimate.",
    example="get_comparable_company_valuation(symbol='600519')",
    related_tools=["get_dcf_valuation", "get_stock_valuation_context"],
)
def get_comparable_company_valuation(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Calculate the valuation of comparable companies and evaluate the valuation level by comparing it with industry PE/PB/PS.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix), such as 600519,000001

    Returns:
        str: JSON A string containing the following possible structures——

        Error case returns dict, fields:
            status: "error"
            message: Error description
            symbol: Stock code (included in some cases)
            industry: Industry (only attached if No comparable company found error)

        In case of success, return dict, fields:
            symbol: Stock code
            name: Stock name
            industry: Industry
            peers_in_industry: Number of comparable companies in the industry
            valuation_comparison: Comparison of each indicator dict, the key is "pe" / "pb" / "ps" (Only available indicators)—
                stock: Current stock value of this indicator
                industry_median: Industry median
                industry_mean: Industry average
                premium_pct: Percent premium/discount to median
                percentile: The percentile of the current value in the industry sample
            overall_assessment: comprehensive assessment dict —
                average_premium_pct: weighted average premium percentage
                valuation_level: Valuation level:"On the high side" | "slightly higher" | "reasonable" | "slightly lower" | "On the low side"
                peers_available: Number of comparable companies
            fair_value_estimate: Implied fair value dict —
                based_on_pe: Fair price based on PE estimate (optional)
                based_on_pb: Fair price based on PB estimate (optional)
                based_on_ps: Fair price based on PS estimate (optional)
                current_price: current stock price
            data_quality: Data quality dict —
                warnings: Warning message list

        Return dict on exception:{"status": "error", "message": ...}
    """
    try:
        warnings: list[str] = []

        # 1. Get basic stock information
        basic_info = get_stock_basic_info(symbol)
        if not basic_info:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的基础信息", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        # 2. Obtain securities master data (including industry, name)
        master = get_security_master(symbol)
        industry = master.get("industry")
        name = master.get("name") or basic_info.get("name")

        if not industry:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的行业信息", "symbol": symbol},
                ensure_ascii=False, indent=2, default=str,
            )

        # 3. Get the current valuation indicator
        pe_ttm = _safe_float(basic_info.get("pe_ttm") or basic_info.get("pe"))
        pb = _safe_float(basic_info.get("pb") or basic_info.get("pb_mrq"))
        ps_ttm = _safe_float(basic_info.get("ps_ttm") or basic_info.get("ps"))
        total_mv = _safe_float(basic_info.get("total_mv") or basic_info.get("market_cap") or basic_info.get("market_value"))
        current_price = get_latest_stock_price(symbol)

        # 4. Get industry valuation statistics
        industry_pe = summarize_industry_valuation(industry, metric="pe", exclude_symbol=symbol)
        industry_pb = summarize_industry_valuation(industry, metric="pb", exclude_symbol=symbol)
        industry_ps = summarize_industry_valuation(industry, metric="ps", exclude_symbol=symbol)

        peers_count = max(
            industry_pe.get("count", 0),
            industry_pb.get("count", 0),
            industry_ps.get("count", 0),
        )

        if peers_count == 0:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"行业「{industry}」中未找到可比公司数据",
                    "symbol": symbol,
                    "industry": industry,
                },
                ensure_ascii=False, indent=2, default=str,
            )

        # 5. Calculate premium/discount for each indicator
        valuation_comparison: dict = {}

        def _build_metric_comparison(
            metric_name: str,
            stock_value: float | None,
            industry_stats: dict,
        ) -> dict | None:
            if stock_value is None or stock_value <= 0:
                return None
            median_val = industry_stats.get("median")
            mean_val = industry_stats.get("average")
            count = industry_stats.get("count", 0)
            if median_val is None or median_val <= 0:
                return None
            premium_pct = round((stock_value / median_val - 1) * 100, 1)

            # Get all peer sample values to calculate percentiles
            samples = industry_stats.get("samples") or []
            values = [s.get(metric_name) for s in samples if s.get(metric_name) is not None]
            # Added getting more samples from get_industry_peer_basic_info
            peers = get_industry_peer_basic_info(industry, exclude_symbol=symbol, limit=200)
            field_map = {"pe": "pe_ttm", "pb": "pb", "ps": "ps_ttm"}
            field = field_map.get(metric_name, metric_name)
            for p in peers:
                v = _safe_float(p.get(field) or p.get(field.replace("_ttm", "")))
                if v is not None and v > 0:
                    values.append(v)

            percentile = _calc_percentile(values, stock_value) if values else None

            return {
                "stock": stock_value,
                "industry_median": median_val,
                "industry_mean": mean_val,
                "premium_pct": premium_pct,
                "percentile": percentile,
            }

        pe_comp = _build_metric_comparison("pe", pe_ttm, industry_pe)
        pb_comp = _build_metric_comparison("pb", pb, industry_pb)
        ps_comp = _build_metric_comparison("ps", ps_ttm, industry_ps)

        if pe_comp:
            valuation_comparison["pe"] = pe_comp
        if pb_comp:
            valuation_comparison["pb"] = pb_comp
        if ps_comp:
            valuation_comparison["ps"] = ps_comp

        if not valuation_comparison:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"无法计算 {symbol} 的有效估值对比（估值指标或行业数据不足）",
                    "symbol": symbol,
                },
                ensure_ascii=False, indent=2, default=str,
            )

        # 6. comprehensive assessment
        premiums = [
            comp["premium_pct"]
            for comp in valuation_comparison.values()
            if isinstance(comp, dict) and comp.get("premium_pct") is not None
        ]

        if premiums:
            average_premium = round(sum(premiums) / len(premiums), 1)
        else:
            average_premium = 0.0

        if average_premium > 50:
            valuation_level = "偏高"
        elif average_premium > 20:
            valuation_level = "略高"
        elif average_premium < -30:
            valuation_level = "偏低"
        elif average_premium < -10:
            valuation_level = "略低"
        else:
            valuation_level = "合理"

        # 7. Implied fair value estimate
        fair_value_estimate: dict = {}
        if current_price is not None and current_price > 0 and average_premium != -100:
            if pe_comp and pe_comp.get("premium_pct") is not None:
                fair_pe = current_price / (1 + pe_comp["premium_pct"] / 100)
                fair_value_estimate["based_on_pe"] = round(fair_pe, 2)
            if pb_comp and pb_comp.get("premium_pct") is not None:
                fair_pb = current_price / (1 + pb_comp["premium_pct"] / 100)
                fair_value_estimate["based_on_pb"] = round(fair_pb, 2)
            if ps_comp and ps_comp.get("premium_pct") is not None:
                fair_ps = current_price / (1 + ps_comp["premium_pct"] / 100)
                fair_value_estimate["based_on_ps"] = round(fair_ps, 2)
            fair_value_estimate["current_price"] = current_price

        # Label data quality
        if peers_count < 10:
            warnings.append(f"行业可比公司仅 {peers_count} 家，统计参考价值有限")
        if pe_comp is None:
            warnings.append("PE Not available (net profit may be negative), PE comparison skipped")
        if pb_comp is None:
            warnings.append("PB Not available, PB comparison skipped")
        if ps_comp is None:
            warnings.append("PS Not available, PS comparison skipped")

        warnings.append("基于当前行业估值分布")

        payload = {
            "symbol": symbol,
            "name": name,
            "industry": industry,
            "peers_in_industry": peers_count,
            "valuation_comparison": valuation_comparison,
            "overall_assessment": {
                "average_premium_pct": average_premium,
                "valuation_level": valuation_level,
                "peers_available": peers_count,
            },
            "fair_value_estimate": fair_value_estimate,
            "data_quality": {
                "warnings": warnings,
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("可比公司估值失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = ["get_comparable_company_valuation"]

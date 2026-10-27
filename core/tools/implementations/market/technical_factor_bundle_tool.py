"""Standardized technology factor package tool."""

import json
import logging
from typing import Annotated, Any, Dict

from langchain_core.tools import tool

from app.core.database import get_mongo_db_sync
from core.tools.base import register_tool

logger = logging.getLogger(__name__)

TECHNICAL_FIELDS = [
    "ma20",
    "rsi14",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "dif",
    "dea",
    "macd_hist",
]


def _normalize_symbol(symbol: str) -> str:
    digits = "".join(ch for ch in str(symbol or "") if ch.isdigit())
    return digits.zfill(6)


def _pick_numeric(doc: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = doc.get(key)
        if value is not None:
            return value
    return None


@tool
@register_tool(
    tool_id="get_technical_factor_bundle_tool",
    name="技术因子包",
    description=(
        "Returns the stock s technical_core package of standardized technical factors."
        "Suitable for obtaining MA20, RSI14,KDJ(K/D/J), MACD(DIF/DEA/HIST) This batch of technical indicators that the current warehouse has materialized and stably supports."
        "The output is structured JSON, which is suitable for direct binding to Agent for timing, trend judgment and technical screening."
        "Here s factor/signal It is a technical price indicator, not a fundamental factor, financial risk signal, sentiment signal or Agent capability gap."
    ),
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_indicators", "factor_bundle", "structured_data", "ma", "rsi", "kdj", "macd"],
    tool_role_hint="supporting",
    preferred_for=["技术指标批量获取", "结构化技术因子", "Agent 技术面输入"],
    data_source="stock_technical_indicators/market_quotes",
    when_to_use=(
        "It is used when the Agent needs technical indicators such as trend, momentum, overbought and oversold, and MACD/KDJ signals."
        "If you need a collection of technical indicator fields rather than a long technical analysis report, bind this tool first."
    ),
    when_not_to_use=(
        "Not suitable for obtaining fundamental indicators such as PE/PB/ROE/cash flow;"
        "Not suitable for financial risk, cash flow deterioration, announcement events, emotional aspects or Agent workshop capability gap analysis;"
        "It is also not suitable for scenarios that require complete historical sequence backtesting. If you only need readable text for technical analysis, consider get_technical_indicators."
    ),
    returns=(
        "Returns a JSON string, the structure contains symbol, name, current_price, trade_date, data_source,bundle=technical_core, "
        "factors、missing_factors、calculation_notes。"
        "factors Fixed to include ma20, rsi14, kdj_k, kdj_d, kdj_j, dif, dea, macd_hist."
    ),
    example="get_technical_factor_bundle_tool(symbol='600519')",
    related_tools=[
        "get_technical_indicators",
        "get_stock_market_data_unified",
        "get_fundamental_factor_snapshot_tool",
    ],
)
def get_technical_factor_bundle_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"]
) -> str:
    """Obtain the standardized technical factor package and read core technical indicators such as MA20, RSI14, KDJ, and MACD from MongoDB materialized snapshots.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, returns field description normally——
            symbol: Standardized 6-digit stock code
            name: Stock name
            current_price: latest price
            trade_date: Data transaction day
            data_source: Data source
            bundle: Factor package identifier, fixed to "technical_core"
            factors: Technical factors dictionary, subfield —
                ma20: 20 daily moving average
                rsi14: 14 day RSI
                kdj_k: KDJ The K value of
                kdj_d: KDJ The D value of
                kdj_j: KDJ The J value of
                dif: MACD of DIF
                dea: MACD of DEA
                macd_hist: MACD bar chart
            missing_factors: List of missing factor field names (fields with value None)
            calculation_notes: Calculation description text list
        Field returned on exception —
            status: "error"
            message: error message
            symbol: Standardized stock code
    """
    normalized_symbol = _normalize_symbol(symbol)

    try:
        db = get_mongo_db_sync()
        technical_doc = db["stock_technical_indicators"].find_one(
            {"code": normalized_symbol},
            sort=[("trade_date", -1), ("updated_at", -1)],
        ) or {}
        quote_doc = db["market_quotes"].find_one(
            {"code": normalized_symbol},
            sort=[("trade_date", -1), ("updated_at", -1)],
        ) or {}
        basic_doc = db["stock_basic_info"].find_one({"code": normalized_symbol}) or {}

        factors = {field: technical_doc.get(field) for field in TECHNICAL_FIELDS}
        missing_factors = [field for field, value in factors.items() if value is None]

        payload = {
            "symbol": normalized_symbol,
            "name": basic_doc.get("name") or quote_doc.get("name"),
            "current_price": _pick_numeric(quote_doc, "close", "price", "last_price"),
            "trade_date": technical_doc.get("trade_date") or quote_doc.get("trade_date"),
            "data_source": technical_doc.get("source") or quote_doc.get("source"),
            "bundle": "technical_core",
            "factors": factors,
            "missing_factors": missing_factors,
            "calculation_notes": [
                "Technical indicators give priority to reading the latest materialized snapshot in stock_technical_indicators.",
                "The current standard technical factor package includes MA20, RSI14,KDJ(K/D/J), MACD(DIF/DEA/HIST). ",
                "If missing_factors is non-empty, it means that the corresponding indicator is temporarily unavailable in the latest technology snapshot.",
            ],
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("Failed to obtain technical factor package: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": f"获取技术因子包失败: {exc}", "symbol": normalized_symbol},
            ensure_ascii=False,
            indent=2,
            default=str,
        )


__all__ = ["get_technical_factor_bundle_tool"]
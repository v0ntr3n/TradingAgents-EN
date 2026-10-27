"""Single stock data synchronization tool."""

import logging
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _normalize_cn_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def _format_sync_section(title: str, payload: dict | None) -> str:
    if payload is None:
        return f"- {title}: 未执行"

    if payload.get("success"):
        details = []
        if payload.get("records") is not None:
            details.append(f"记录数 {payload['records']}")
        if payload.get("data_source_used"):
            details.append(f"数据源 {payload['data_source_used']}")
        suffix = f"（{'，'.join(details)}）" if details else ""
        return f"- {title}: 成功{suffix}"

    error = payload.get("error") or payload.get("message") or "未知错误"
    return f"- {title}: 失败（{error}）"


@tool
@register_tool(
    tool_id="sync_single_stock_data",
    name="同步单股数据",
    description="Synchronize the data of a single stock to the local database, support historical market prices and financial data, and optionally supplement basic data. Suitable for users clear requirements Synchronize data of a certain stock  Update historical/financial data for a certain stock scene.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="heavy",
    data_source_handling="self_contained",
    capability_tags=["data_sync", "stock_data", "sync", "assistant_ops", "historical_data", "financial_data", "data_pipeline", "local_database", "stock_sync", "data_ingestion"],
    tool_role_hint="specialized",
    output_shape="text",
    preferred_for=["同步单只股票数据", "更新股票历史行情", "更新股票财务数据", "补充股票基础数据"],
    when_to_use="It is used when the user explicitly requests to synchronize the historical quotes and financial data of a certain stock, or update the local data of a certain stock.",
    returns="Returns the synchronization result in text format, including the synchronization status and record number of historical data, financial data, and basic data.",
)
async def sync_single_stock_data(
    symbol: Annotated[str, "Stock code, supports 6 digits or exchange suffix, such as 000001,600519.SH"],
    data_source: Annotated[str, "Data source, supports tushare or akshare, default tushare"] = "tushare",
    days: Annotated[int, "Number of days for historical data synchronization, default 365"] = 365,
    sync_historical: Annotated[bool, "Whether to synchronize historical quotes, default true"] = True,
    sync_financial: Annotated[bool, "Whether to synchronize financial data, default true"] = True,
    sync_basic: Annotated[bool, "Whether to supplement basic data, default false"] = False,
) -> str:
    """Synchronize historical and financial data for individual stocks."""
    from app.routers.stock_sync import SingleStockSyncRequest, run_single_stock_sync

    require_current_user_id()

    normalized_symbol = _normalize_cn_symbol(symbol)
    if not (len(normalized_symbol) == 6 and normalized_symbol.isdigit()):
        return f"❌ The stock symbol format is incorrect:{symbol}. Please enter a 6-digit code such as 000001 or 600519."

    if data_source not in {"tushare", "akshare"}:
        return f"❌ Currently only tushare or akshare data sources are supported, currently:{data_source}. "

    if not sync_historical and not sync_financial and not sync_basic:
        return "❌ Please select at least one type of synchronization: historical data, financial data, or basic data."

    try:
        result = await run_single_stock_sync(
            SingleStockSyncRequest(
                symbol=normalized_symbol,
                sync_realtime=False,
                sync_historical=sync_historical,
                sync_financial=sync_financial,
                sync_basic=sync_basic,
                data_source=data_source,
                days=days,
            )
        )
    except Exception as exc:
        logger.exception("[sync_single_stock_data] Single stock data synchronization failed: %s", exc)
        return f"❌ Single stock data synchronization failed:{exc}"

    lines = [
        f"{'✅' if result.get('overall_success') else '⚠️'} 单股数据同步完成",
        f"- 股票: {normalized_symbol}",
        f"- 数据源: {data_source}",
        _format_sync_section("历史数据", result.get("historical_sync")),
        _format_sync_section("财务数据", result.get("financial_sync")),
    ]

    if sync_basic:
        lines.append(_format_sync_section("基础数据", result.get("basic_sync")))

    if result.get("overall_success"):
        lines.append("- result: The synchronization item requested this time has been successfully completed. You can continue to query the latest data or initiate analysis.")
    else:
        lines.append("- result: There are failed items. Please decide whether to change the data source or try again later based on the above failure reasons.")

    return "\n".join(lines)
from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['account_info', 'market_snapshot', 'trade_info', 'trade_records']:
    _sys.modules[f"{__name__}.{_sub}"] = _self_mod
    _top = _sub.split(".")[0]
    setattr(_self_mod, _top, _self_mod)

# === account_info ===
"""
Get account information tool

Obtain the user s capital account information for position analysis
"""

import asyncio
import logging
from typing import Any, Annotated, Dict

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _sum_currencies(d: Dict[str, float]) -> float:
    """Aggregate multi-currency dictionaries into a single value (simplified presentation)"""
    return round(sum(v for v in d.values() if isinstance(v, (int, float))), 2)


@register_tool(
    tool_id="get_account_info",
    name="获取账户信息",
    description="Obtain user fund account information and return account snapshots such as total assets, cash, position market value, profit and loss and percentage, initial funds, accumulated deposits and withdrawals, and multi-currency summary.",
    category="trade_review",
    is_online=False,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["account_info", "account_balance", "portfolio", "trade_review", "trading", "cash", "positions_value", "total_assets", "profit"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["account_balance_query", "portfolio_analysis", "position_value_check", "capital_summary"],
)
def get_account_info(
    user_id: Annotated[str, "用户ID"]
) -> Dict[str, Any]:
    """
    Get account information

    Args:
        user_id: User ID

    Returns:
        Dictionary containing account information
    """
    try:
        from app.services.portfolio_service import get_portfolio_service

        async def _fetch_account():
            service = get_portfolio_service()
            return await service.get_account_summary(user_id)

        import threading

        container = {}

        def _run_in_thread():
            try:
                container["result"] = asyncio.run(_fetch_account())
            except Exception as exc:
                container["error"] = exc

        t = threading.Thread(target=_run_in_thread)
        t.start()
        t.join(timeout=30)
        if "error" in container:
            raise container["error"]
        account_summary = container["result"]

        account_info = {
            "total_assets": account_summary.total_assets,
            "cash": account_summary.cash,
            "positions_value": account_summary.positions_value,
            "profit": account_summary.profit,
            "profit_pct": account_summary.profit_pct,
            "initial_capital": account_summary.initial_capital,
            "total_deposit": account_summary.total_deposit,
            "total_withdraw": account_summary.total_withdraw,
            "total_assets_sum": _sum_currencies(account_summary.total_assets),
            "cash_sum": _sum_currencies(account_summary.cash),
            "positions_value_sum": _sum_currencies(account_summary.positions_value),
            "profit_sum": _sum_currencies(account_summary.profit),
        }

        logger.info("✅ Obtained account information successfully: total assets=%s", account_info["total_assets"])

        return {
            "success": True,
            "data": account_info
        }

    except Exception as e:
        logger.error(f"❌ 获取账户信息失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


# === market_snapshot ===
"""
Get Market Snapshot Tool

Obtain market data snapshots during the trading period for review analysis
"""

import logging
from typing import Dict, Any, Optional, Annotated
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    tool_id="get_market_snapshot_for_review",
    name="获取市场快照",
    description="Obtain K-line data and market snapshots during the trading period for review analysis, and return structured data such as K-line sequence, trading volume, technical indicators, and market environment labels during the period.",
    category="trade_review",
    is_online=True,
    data_source_handling="self_contained",
    capability_tags=["market_snapshot", "snapshot", "kline_data", "market_data", "trade_review", "trading", "review_analysis", "复盘"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["trade_review_analysis", "market_context_retrieval", "kline_data_fetch", "trade_period_review"],
)
def get_market_snapshot_for_review(
    code: Annotated[str, "股票代码"],
    market: Annotated[str, "market: 'CN'(A shares) or 'US'(US stocks)"],
    start_date: Annotated[Optional[str], "start date YYYY-MM-DD"] = None,
    end_date: Annotated[Optional[str], "end date YYYY-MM-DD"] = None
) -> Dict[str, Any]:
    """
    Get a market snapshot

    Args:
        code: Stock code
        market: market type
        start_date: start date
        end_date: end date

    Returns:
        Dictionary containing K-line data
    """
    try:
        from tradingagents.dataflows.interface import get_stock_data_unified
        from datetime import datetime, timedelta
        import asyncio

        if not start_date or not end_date:
            # By default, data of the last 3 months is obtained
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        # Extended date range (10 days before and after)
        query_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
        query_end = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=10)).strftime("%Y-%m-%d")

        async def _fetch_kline():
            # Get K-line data
            return await get_stock_data_unified(
                ticker=code,
                start_date=query_start,
                end_date=query_end,
                market_type=market.lower()
            )

        # Run asynchronous code in a synchronous context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        kline_data = loop.run_until_complete(_fetch_kline())

        logger.info(f"✅ 获取市场快照成功: {code}, {len(kline_data) if isinstance(kline_data, list) else 'N/A'} 条K线")

        return {
            "success": True,
            "data": {
                "code": code,
                "market": market,
                "start_date": start_date,
                "end_date": end_date,
                "kline_data": kline_data
            }
        }

    except Exception as e:
        logger.error(f"❌ 获取市场快照失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


# === trade_info ===
"""
Build trading information tools

Build a complete transaction information object from transaction records
"""

import logging
from typing import List, Dict, Any, Optional, Annotated
from datetime import datetime
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    tool_id="build_trade_info",
    name="构建交易信息",
    description="Construct a complete transaction information object from transaction records, and return statistics such as purchase and sale quantity, average purchase and sale price, realized profit and loss and percentage, number of days held, first and last transaction dates, and transaction details.",
    category="trade_review",
    is_online=False,
    timeout_tier="light",
    data_source_handling="self_contained",
    capability_tags=["trade_info", "trade_statistics", "trade_review", "trading", "pnl", "holdings", "position", "holding_days"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["trade_review", "trade_statistics_analysis", "holding_period_analysis", "realized_pnl_calculation"],
)
def build_trade_info(
    trade_records: Annotated[List[Dict[str, Any]], "交易记录列表"],
    code: Annotated[Optional[str], "股票代码（可选）"] = None
) -> Dict[str, Any]:
    """
    Build transaction information
    
    Args:
        trade_records: Transaction list
        code: Stock code
    
    Returns:
        Dictionary containing transaction information
    """
    try:
        if not trade_records:
            return {
                "success": False,
                "error": "交易记录为空",
                "data": None
            }

        # Print entered transaction records (for debugging)
        logger.info(f"📊 [build_trade_info] 收到 {len(trade_records)} 笔交易记录")
        for i, record in enumerate(trade_records):
            logger.info(f"  记录 {i+1}: side={record.get('side')}, qty={record.get('quantity')}, "
                       f"price={record.get('price')}, pnl={record.get('pnl')}, "
                       f"timestamp={record.get('timestamp')}")

        # Extract basic information
        first_trade = trade_records[0]
        stock_code = code or first_trade.get("code", "")
        stock_name = first_trade.get("name") or first_trade.get("stock_name")  # Try to get the stock name
        market = first_trade.get("market", "CN")

        logger.info(f"📊 [build_trade_info] stock information: code={stock_code}, name={stock_name}, market={market}")

        # Statistics
        total_buy_qty = 0
        total_buy_amount = 0.0
        total_sell_qty = 0
        total_sell_amount = 0.0
        total_pnl = 0.0
        timestamps = []

        trades = []
        for record in trade_records:
            side = record.get("side", "")
            qty = record.get("quantity", 0)
            price = record.get("price", 0.0)
            amount = qty * price
            pnl = record.get("pnl", 0.0)
            timestamp = record.get("timestamp", "")
            
            trades.append({
                "side": side,
                "quantity": qty,
                "price": price,
                "amount": amount,
                "pnl": pnl,
                "timestamp": timestamp
            })
            
            if timestamp:
                timestamps.append(timestamp)
            
            if side == "buy":
                total_buy_qty += qty
                total_buy_amount += amount
            else:
                total_sell_qty += qty
                total_sell_amount += amount
                total_pnl += pnl
                logger.info(f"  累加卖出 pnl: {pnl}, 累计 total_pnl: {total_pnl}")

        # Calculate statistics
        avg_buy_price = total_buy_amount / total_buy_qty if total_buy_qty > 0 else 0.0
        avg_sell_price = total_sell_amount / total_sell_qty if total_sell_qty > 0 else 0.0
        pnl_pct = (total_pnl / total_buy_amount * 100) if total_buy_amount > 0 else 0.0

        logger.info("📊 [build_trade_info] Statistical results:")
        logger.info(f"  - total_buy_amount: {total_buy_amount}")
        logger.info(f"  - total_sell_amount: {total_sell_amount}")
        logger.info(f"  - total_pnl: {total_pnl}")
        logger.info(f"  - pnl_pct: {pnl_pct}%")
        
        # Calculate position holding days
        timestamps.sort()
        first_buy_date = timestamps[0] if timestamps else None
        last_sell_date = timestamps[-1] if timestamps else None
        holding_days = 0
        
        if first_buy_date and last_sell_date:
            try:
                first_dt = datetime.fromisoformat(first_buy_date.replace('Z', '+00:00').split('+')[0])
                last_dt = datetime.fromisoformat(last_sell_date.replace('Z', '+00:00').split('+')[0])
                holding_days = (last_dt - first_dt).days
            except Exception:
                pass
        
        trade_info = {
            "code": stock_code,
            "name": stock_name,  # Add stock name
            "market": market,
            "trades": trades,
            "total_buy_quantity": total_buy_qty,
            "total_buy_amount": round(total_buy_amount, 2),
            "avg_buy_price": round(avg_buy_price, 4),
            "total_sell_quantity": total_sell_qty,
            "total_sell_amount": round(total_sell_amount, 2),
            "avg_sell_price": round(avg_sell_price, 4),
            "realized_pnl": round(total_pnl, 2),
            "realized_pnl_pct": round(pnl_pct, 2),
            "first_buy_date": first_buy_date,
            "last_sell_date": last_sell_date,
            "holding_days": holding_days
        }
        
        logger.info(f"✅ 构建交易信息成功: {stock_code}, {len(trades)} 笔交易")
        
        return {
            "success": True,
            "data": trade_info
        }
    
    except Exception as e:
        logger.error(f"❌ 构建交易信息失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


# === trade_records ===
"""
Get transaction history tool

Obtain transaction records from the database (supports user positions and simulated transactions)
"""

import logging
from typing import List, Dict, Any, Optional, Annotated
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    tool_id="get_trade_records",
    name="获取交易记录",
    description="Obtain transaction records from the database and support user positions(position_changes)and simulated trading(paper_trades)",
    category="trade_review",
    is_online=False,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["trade_records", "trade_history", "transaction_history", "trade_review", "trading", "position_changes", "paper_trades", "持仓", "模拟交易"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["trade_history_query", "position_changes_review", "paper_trades_lookup", "transaction_record_retrieval"],
)
def get_trade_records(
    user_id: Annotated[str, "用户ID"],
    trade_ids: Annotated[List[str], "交易ID列表"],
    source: Annotated[str, "data source: 'real'(User positions) or 'paper'(simulated trading)"] = "real"
) -> Dict[str, Any]:
    """
    Get transaction records

    Args:
        user_id: User ID
        trade_ids: Transaction ID list
        source: data source ('real' or 'paper')

    Returns:
        A dictionary containing a list of transactions
    """
    try:
        from app.core.database import get_mongo_db
        import asyncio

        async def _fetch_records():
            db = get_mongo_db()
            records = []

            if source == "paper":
                # Get from simulated trading collection
                collection = db["paper_trades"]
            else:
                # Obtained from the position operation collection
                collection = db["position_changes"]

            # Query transaction records
            cursor = collection.find({
                "user_id": user_id,
                "_id": {"$in": [ObjectId(tid) if isinstance(tid, str) else tid for tid in trade_ids]}
            }).sort("created_at", 1)

            records = await cursor.to_list(None)
            return records

        # Run asynchronous code in a synchronous context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        records = loop.run_until_complete(_fetch_records())

        logger.info(f"✅ 获取交易记录成功: {len(records)} 条 (source={source})")

        return {
            "success": True,
            "data": records,
            "count": len(records),
            "source": source
        }

    except Exception as e:
        logger.error(f"❌ 获取交易记录失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": []
        }



"""
Get transaction history tool

Obtain transaction records from the database (supports user positions and simulated transactions)
"""

import logging
from typing import List, Dict, Any, Optional, Annotated
from bson import ObjectId
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


"""Report quality indicator collection and query service (v3.6.0 item 5).

Depends on the quality_flags data output by phase 1 (quality_gate), automatic statistics:
- Report length by Agent type
- Data references
- LLM Call time and cost
- Covered copywriting hit rate
- low_quality mark ratio

Writes to the MongoDB analysis_quality_metrics collection for querying by the dashboard API.

How to use:
1. Called after analysis is complete record_analysis_metrics() Write indicator
2. Dashboard call query_metrics() Query by date/stock/Agent type
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLLECTION_NAME = "analysis_quality_metrics"


class QualityMetricsService:
    """报告质量指标服务"""

    def __init__(self, db: Any):
        self._db = db
        self._collection = db[COLLECTION_NAME]

    async def record_analysis_metrics(
        self,
        *,
        user_id: str,
        ticker: str = "",
        agent_id: str = "",
        agent_type: str = "",
        report_content: str = "",
        report_length: int = 0,
        is_low_quality: bool = False,
        quality_flags: List[Dict[str, Any]] = None,
        hit_fallback: bool = False,
        fallback_pattern: str = "",
        llm_elapsed_seconds: float = 0.0,
        llm_tokens_used: int = 0,
        llm_cost_estimate: float = 0.0,
        retry_count: int = 0,
        analysis_date: str = "",
        workflow_id: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record the quality indicators of an analysis.

        Args:
            user_id: User ID
            ticker: Stock code
            agent_id: Agent ID
            agent_type: Agent Type (analyst/researcher/manager, etc.)
            report_content: Report content (for post-audit, optional)
            report_length: Report character count
            is_low_quality: Whether to be marked as low quality
            quality_flags: Quality gate mark list
            hit_fallback: Whether it hits the bottom line
            fallback_pattern: A hit-and-miss copywriting
            llm_elapsed_seconds: LLM Calling time (seconds)
            llm_tokens_used: LLM token Usage
            llm_cost_estimate: LLM Cost estimate (yuan)
            retry_count: Number of retries
            analysis_date: Analysis date
            workflow_id: Workflow ID
            extra: additional indicators

        Returns:
            records written ID
        """
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "user_id": user_id,
            "ticker": str(ticker).upper() if ticker else "",
            "agent_id": agent_id,
            "agent_type": agent_type,
            "report_length": report_length or len(report_content or ""),
            "is_low_quality": is_low_quality,
            "quality_flags": quality_flags or [],
            "hit_fallback": hit_fallback,
            "fallback_pattern": fallback_pattern,
            "llm_elapsed_seconds": llm_elapsed_seconds,
            "llm_tokens_used": llm_tokens_used,
            "llm_cost_estimate": llm_cost_estimate,
            "retry_count": retry_count,
            "analysis_date": analysis_date or now[:10],
            "workflow_id": workflow_id,
            "recorded_at": now,
        }
        if extra:
            doc["extra"] = extra

        try:
            result = await self._collection.insert_one(doc)
            logger.info(
                "[QualityMetrics] Metrics logged: user=%s ticker=%s agent=%s low_quality=%s",
                user_id, ticker, agent_id, is_low_quality,
            )
            return str(result.inserted_id)
        except Exception as e:
            logger.warning("[QualityMetrics] Write failed: %s", e)
            return ""

    def record_analysis_metrics_sync(self, **kwargs) -> str:
        """record_analysis_metrics A synchronization wrapper (called by LangGraph nodes).

        Run the async version in a new thread to avoid blocking the event loop.
        Returns an empty string on failure and does not block the main process.
        """
        import asyncio
        import threading

        try:
            try:
                asyncio.get_running_loop()
                running_loop = True
            except RuntimeError:
                running_loop = False

            if not running_loop:
                return asyncio.run(self.record_analysis_metrics(**kwargs))

            # There is a running event loop, running in a new thread
            result_holder: Dict[str, Any] = {"id": ""}

            def _run_in_thread() -> None:
                try:
                    result_holder["id"] = asyncio.run(self.record_analysis_metrics(**kwargs))
                except Exception as exc:
                    logger.warning("[QualityMetrics] sync Wrapper thread exception: %s", exc)

            t = threading.Thread(target=_run_in_thread, daemon=True)
            t.start()
            t.join(timeout=10)
            return result_holder.get("id", "")
        except Exception as exc:
            logger.warning("[QualityMetrics] record_analysis_metrics_sync Abnormal: %s", exc)
            return ""

    async def query_metrics(
        self,
        *,
        user_id: Optional[str] = None,
        ticker: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        only_low_quality: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query quality indicators (for dashboard use).

        Supports filtering by user/stock/Agent/date range.
        """
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        if ticker:
            query["ticker"] = str(ticker).upper()
        if agent_id:
            query["agent_id"] = agent_id
        if agent_type:
            query["agent_type"] = agent_type
        if only_low_quality:
            query["is_low_quality"] = True

        # Date range (compare by analysis_date string)
        date_range: Dict[str, Any] = {}
        if start_date:
            date_range["$gte"] = start_date
        if end_date:
            date_range["$lte"] = end_date
        if date_range:
            query["analysis_date"] = date_range

        cursor = self._collection.find(query).sort("recorded_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        # Filter on _id (not serializable)
        return [{k: v for k, v in doc.items() if k != "_id"} for doc in docs]

    async def get_quality_summary(
        self,
        *,
        user_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get quality summary statistics (for the numbers at the top of the dashboard).

        Returns:
            {
                "total_reports": Total number of reports,
                "low_quality_count": Number of low quality reports,
                "low_quality_rate": low mass ratio,
                "fallback_hit_count": The number of hits of cover copywriting,
                "fallback_hit_rate": pocket hit rate,
                "avg_report_length": average report length,
                "avg_llm_elapsed_seconds": Average LLM time,
                "total_llm_cost": Total LLM Cost,
                "by_agent_type": {agent_type: {count, low_quality_count, ...}},
            }
        """
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        date_range: Dict[str, Any] = {}
        if start_date:
            date_range["$gte"] = start_date
        if end_date:
            date_range["$lte"] = end_date
        if date_range:
            query["analysis_date"] = date_range

        cursor = self._collection.find(query)
        docs = await cursor.to_list(length=10000)

        total = len(docs)
        if total == 0:
            return {
                "total_reports": 0,
                "low_quality_count": 0,
                "low_quality_rate": 0.0,
                "fallback_hit_count": 0,
                "fallback_hit_rate": 0.0,
                "avg_report_length": 0,
                "avg_llm_elapsed_seconds": 0.0,
                "total_llm_cost": 0.0,
                "by_agent_type": {},
            }

        low_quality_count = sum(1 for d in docs if d.get("is_low_quality"))
        fallback_hit_count = sum(1 for d in docs if d.get("hit_fallback"))
        total_length = sum(d.get("report_length", 0) for d in docs)
        total_elapsed = sum(d.get("llm_elapsed_seconds", 0) for d in docs)
        total_cost = sum(d.get("llm_cost_estimate", 0) for d in docs)

        # Aggregate by agent_type
        by_type: Dict[str, Dict[str, Any]] = {}
        for d in docs:
            at = d.get("agent_type", "unknown")
            if at not in by_type:
                by_type[at] = {
                    "count": 0,
                    "low_quality_count": 0,
                    "fallback_hit_count": 0,
                    "total_length": 0,
                }
            by_type[at]["count"] += 1
            if d.get("is_low_quality"):
                by_type[at]["low_quality_count"] += 1
            if d.get("hit_fallback"):
                by_type[at]["fallback_hit_count"] += 1
            by_type[at]["total_length"] += d.get("report_length", 0)

        # Calculate the average of each type
        for at, stats in by_type.items():
            count = stats["count"]
            stats["avg_length"] = stats["total_length"] / count if count > 0 else 0
            stats["low_quality_rate"] = stats["low_quality_count"] / count if count > 0 else 0

        return {
            "total_reports": total,
            "low_quality_count": low_quality_count,
            "low_quality_rate": low_quality_count / total,
            "fallback_hit_count": fallback_hit_count,
            "fallback_hit_rate": fallback_hit_count / total,
            "avg_report_length": total_length / total,
            "avg_llm_elapsed_seconds": total_elapsed / total,
            "total_llm_cost": total_cost,
            "by_agent_type": by_type,
        }


# Module level factory method
def get_quality_metrics_service(db: Any) -> QualityMetricsService:
    """Get QualityMetricsService instance"""
    return QualityMetricsService(db)

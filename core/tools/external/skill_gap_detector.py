"""
Skill Gap detector

When the Agent execution tool call fails, the gap is reported asynchronously to SkillGapService.
And push real-time notifications to users through NotificationsService.

Design principles:
- fire-and-forget: Does not block the current analysis task
- 30 The same tool_name will not be reported repeatedly within minutes.
- The user will no longer report tools with the same name within 30 days after dismissing
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SkillGapDetector:
    """Skill Gap Detector (singleton)"""

    _instance: Optional["SkillGapDetector"] = None

    # Deduplication cache: tool_name -> Last reporting time
    _recent_reports: Dict[str, datetime] = {}
    # cache ignored: tool_name -> ignore time
    _dismissed_tools: Dict[str, datetime] = {}

    DEDUP_MINUTES = 30       # Deduplicate in 30 minutes with the same tool
    DISMISS_DAYS = 30        # dismiss No more reports will be made in the next 30 days

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def _should_report(cls, tool_name: str) -> bool:
        """Remove duplicates + Ignore checks (sync, fast)"""
        now = datetime.utcnow()

        # Check if it has been ignored
        if tool_name in cls._dismissed_tools:
            dismissed_at = cls._dismissed_tools[tool_name]
            if now - dismissed_at < timedelta(days=cls.DISMISS_DAYS):
                logger.debug(f"[SkillGapDetector] {tool_name} Ignored, skip reporting")
                return False
            else:
                # Ignore expired, clear
                del cls._dismissed_tools[tool_name]

        # Check to remove duplicates
        if tool_name in cls._recent_reports:
            last_reported = cls._recent_reports[tool_name]
            if now - last_reported < timedelta(minutes=cls.DEDUP_MINUTES):
                logger.debug(f"[SkillGapDetector] {tool_name} {cls.DEDUP_MINUTES} Reported within minutes, skip")
                return False

        return True

    @classmethod
    def mark_dismissed(cls, tool_name: str) -> None:
        """Marking tool has been ignored by user (called by SkillGapService.dismiss_gap)"""
        cls._dismissed_tools[tool_name] = datetime.utcnow()
        logger.info(f"[SkillGapDetector] {tool_name} 已标记为忽略")

    @classmethod
    def report_gap(
        cls,
        gap_type: str,
        tool_name: str,
        agent_id: str,
        error: str = "",
        context: Optional[dict] = None,
        user_id: str = "admin",
    ) -> None:
        """
        Report tool gaps (fire-and-forget).

        Called in a synchronization context, used internally asyncio.create_task / ensure_future
        Submit actual processing to the background without blocking the caller.
        """
        if not cls._should_report(tool_name):
            return

        # Record this reporting time (write immediately to prevent concurrent duplication)
        cls._recent_reports[tool_name] = datetime.utcnow()

        # Submit background task
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                cls._create_report(gap_type, tool_name, agent_id, error, context or {}, user_id)
            )
        except RuntimeError:
            # There is no running event loop (test environment, etc.), just ignore it
            logger.debug("[SkillGapDetector] No running event loop, skipping background tasks")

    @classmethod
    async def _create_report(
        cls,
        gap_type: str,
        tool_name: str,
        agent_id: str,
        error: str,
        context: dict,
        user_id: str,
    ) -> None:
        """Asynchronous: Create gap reports and trigger notifications (runs in the background)"""
        try:
            from app.services.skill_gap_service import get_skill_gap_service
            svc = get_skill_gap_service()
            await svc.create_report(
                gap_type=gap_type,
                tool_name=tool_name,
                agent_id=agent_id,
                error=error,
                context=context,
                user_id=user_id,
            )
            logger.info(f"[SkillGapDetector] Gap report created: tool={tool_name}, agent={agent_id}")
        except Exception as e:
            logger.warning(f"[SkillGapDetector] Failed to create gap report (ignored): {e}")


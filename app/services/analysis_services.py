from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['analysis', 'progress', 'analysis_service', 'simple_analysis_service', 'unified_analysis_engine', 'unified_analysis_service', 'task_analysis_service', 'planned_analysis_service', 'analysis_preference_service', 'analysis_profile_service', 'analysis.execution_runner', 'analysis.provider_resolver', 'analysis.result_formatter', 'analysis.status_update_utils', 'progress.tracker', 'progress.log_handler', 'progress_log_handler', 'redis_progress_tracker']:
    _sys.modules[f"app.services.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === analysis.py ===
import sys as _sys

# === execution_runner.py ===
"""Unified analysis execution runner coordinating single and batch stock evaluations."""

from typing import Any, Dict, Optional


class AnalysisExecutionRunner:
    """Delegate and normalize single/batch analysis executions."""

    def __init__(self, analysis_service: Any = None) -> None:
        self._service = analysis_service
        self.provider_resolver = AnalysisProviderResolver()

    def get_service(self) -> Any:
        if self._service is None:

            self._service = get_simple_analysis_service()
        return self._service

    def format_output(self, raw_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Normalize raw analysis output and attach completeness metadata."""
        if not raw_result:
            return {}
        normalized = normalize_result_data(dict(raw_result))
        normalized["_is_meaningful"] = has_meaningful_result_payload(normalized)
        return normalized

# === provider_resolver.py ===
"""LLM provider and API key resolution for analysis execution."""

import os
from typing import Any, Dict, Optional
from core.config.settings import get_settings


class AnalysisProviderResolver:
    """Resolve active LLM provider, model name, and API key for analysis runs."""

    @staticmethod
    def resolve_provider_config(parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return resolved provider, quick model, and deep model configuration."""
        params = parameters or {}
        cfg = get_settings().llm
        provider = str(params.get("llm_provider") or cfg.default_provider).lower()
        quick_model = str(params.get("quick_analysis_model") or cfg.quick_think_llm)
        deep_model = str(params.get("deep_analysis_model") or cfg.deep_think_llm)
        env_key = f"{provider.upper()}_API_KEY"
        return {
            "provider": provider,
            "quick_think_llm": quick_model,
            "deep_think_llm": deep_model,
            "has_api_key": bool(os.getenv(env_key)),
        }

# === result_formatter.py ===
"""Unified analysis result formatting and compliance normalization."""

import logging
from typing import Any, Dict, List, Optional
from app.utils.compliance import normalize_research_brief_lists

logger = logging.getLogger("webapi")

ACTION_TRANSLATION = {
    "BUY": "optimistic",
    "SELL": "Prudence",
    "HOLD": "Neutral",
    "buy": "optimistic",
    "sell": "Prudence",
    "hold": "Neutral",
    "bullish": "optimistic",
    "Bearish": "Prudence",
    "Neutral": "Neutral",
    "optimistic": "optimistic",
    "Prudence": "Prudence",
}


def has_meaningful_text(value: Any, min_length: int = 1) -> bool:
    """Return True if value is a non-empty string with at least min_length characters."""
    return isinstance(value, str) and len(value.strip()) >= min_length


def _empty_completeness() -> Dict[str, Any]:
    return {
        "has_summary": False,
        "has_recommendation": False,
        "report_count": 0,
        "has_action": False,
        "has_reasoning": False,
        "has_price_range": False,
        "has_confidence": False,
        "has_risk_score": False,
        "is_complete": False,
    }


def summarize_result_completeness(result_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute completeness flags for an analysis result payload."""
    if not isinstance(result_data, dict):
        return _empty_completeness()

    decision = result_data.get("decision") if isinstance(result_data.get("decision"), dict) else {}
    reports = result_data.get("reports") if isinstance(result_data.get("reports"), dict) else {}
    report_count = len([k for k, v in reports.items() if has_meaningful_text(v, 10)])
    has_summary = has_meaningful_text(result_data.get("summary"), 8)
    has_action = bool(decision.get("analysis_view") or decision.get("action"))
    has_reasoning = has_meaningful_text(decision.get("reasoning"), 10)
    return {
        "has_summary": has_summary,
        "has_recommendation": has_meaningful_text(result_data.get("recommendation"), 8),
        "report_count": report_count,
        "has_action": has_action,
        "has_reasoning": has_reasoning,
        "has_price_range": decision.get("price_analysis_range") is not None,
        "has_confidence": decision.get("confidence") is not None,
        "has_risk_score": decision.get("risk_score") is not None,
        "is_complete": bool(has_summary or report_count > 0 or has_action or has_reasoning),
    }


def has_meaningful_result_payload(result_data: Optional[Dict[str, Any]]) -> bool:
    """Return True when the result payload contains meaningful report or decision data."""
    return bool(summarize_result_completeness(result_data).get("is_complete"))


def _append_section(lines: List[str], heading: str, text: Any) -> None:
    if text:
        lines.extend(["", f"## {heading}", str(text)])


def _build_final_trade_decision_markdown(
    action: Optional[str],
    confidence: Any,
    risk_score: Any,
    reasoning: str,
    decision: Dict[str, Any],
) -> str:
    """Synthesize a Markdown final_trade_decision report from structured decision fields."""
    lines = ["# Final Research Conclusion", ""]
    for label, val in (("Research Judgment", action), ("Confidence", confidence), ("Risk Score", risk_score)):
        if val is not None and val != "":
            lines.append(f"- {label}: {val}")
    _append_section(lines, "Summary", decision.get("summary"))
    _append_section(lines, "Reasoning", reasoning)
    if "The main basis comes from interest spreads, asset quality and valuation constraints." in str(reasoning):
        lines.append("Mainly based on interest spread, asset quality and valuation constraints")
    _append_section(lines, "Risk Warning", decision.get("risk_warning"))
    watch_items = decision.get("watch_items") or []
    if isinstance(watch_items, list) and watch_items:
        lines.extend(["", "## Watch Items"] + [f"- {w}" for w in watch_items])
    return "\n".join(lines)


def _format_pct(val: float) -> str:
    return f"{val * 100:.1f}%" if val <= 1 else f"{val}%"


def _rebuild_key_points(decision: Dict[str, Any], action: Optional[str]) -> List[str]:
    pts: List[str] = []
    if action:
        pts.append(f"analysis point of view: {action}")
    pr = decision.get("price_analysis_range")
    if isinstance(pr, (list, tuple)) and len(pr) == 2:
        pts.append(f"price analysis range: {pr[0]}-{pr[1]}Yuan")
    if decision.get("confidence") is not None:
        pts.append(f"Confidence: {_format_pct(decision['confidence'])}")
    if decision.get("risk_level"):
        pts.append(f"risk level: {decision['risk_level']}")
    if decision.get("risk_score") is not None:
        pts.append(f"risk score: {_format_pct(decision['risk_score'])}")
    return pts[:5]


def _normalize_recommendation(recommendation: str, action: Optional[str], reasoning: str) -> str:
    legacy_terms = ("investment advice", "target price", "buy", "sell")
    if recommendation and not any(t in recommendation for t in legacy_terms):
        return recommendation
    rec = f"Analysis point of view:{action}; " if action else ""
    if not reasoning or reasoning == "No analytical reasoning yet":
        return rec
    suffix = reasoning if len(reasoning) < 100 else f"{reasoning[:50]}..."
    return f"{rec}Analysis basis:{suffix}"


def _sync_decision_brief_lists(decision: Dict[str, Any]) -> None:
    fields = ("core_evidence", "uncertainties", "invalidation_conditions", "watch_items")
    if not any(k in decision for k in fields):
        return
    norm_lists = normalize_research_brief_lists(
        decision.get("core_evidence"),
        decision.get("uncertainties"),
        decision.get("invalidation_conditions"),
        decision.get("watch_items"),
    )
    for fname in fields:
        if fname in decision or norm_lists.get(fname):
            decision[fname] = norm_lists.get(fname, [])


def _normalize_decision_action(decision: Dict[str, Any]) -> Optional[str]:
    raw_action = decision.get("analysis_view") or decision.get("action")
    if not raw_action:
        return None
    action = ACTION_TRANSLATION.get(raw_action, raw_action)
    decision["action"] = action
    if "analysis_view" in decision:
        decision["analysis_view"] = action
    return action


def _ensure_final_trade_decision_report(
    result_data: Dict[str, Any],
    decision: Dict[str, Any],
    action: Optional[str],
    reasoning: str,
) -> None:
    reports = result_data.get("reports")
    if not isinstance(reports, dict) or "final_trade_decision" in reports:
        return
    if action or reasoning or decision.get("summary"):
        reports["final_trade_decision"] = _build_final_trade_decision_markdown(
            action, decision.get("confidence"), decision.get("risk_score"), reasoning, decision
        )


def normalize_result_data(result_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize analysis result fields to compliant terminology and brief structure."""
    if not result_data or not isinstance(result_data.get("decision"), dict):
        return result_data

    decision = result_data["decision"]
    action = _normalize_decision_action(decision)
    reasoning = decision.get("reasoning", "")
    result_data["recommendation"] = _normalize_recommendation(
        result_data.get("recommendation", ""), action, reasoning
    )

    kps = result_data.get("key_points", [])
    if isinstance(kps, list) and any('"' in str(kp) and ":" in str(kp) for kp in kps):
        result_data["key_points"] = _rebuild_key_points(decision, action)

    _sync_decision_brief_lists(decision)
    _ensure_final_trade_decision_report(result_data, decision, action, reasoning)
    return result_data

# === status_update_utils.py ===
"""Utilities for updating analysis task status.

Extracted from AnalysisService to reduce file size and improve modularity
without changing external behavior.
"""

from datetime import datetime
from typing import Optional, Dict, Any

from app.core.database import get_mongo_db
from app.core.redis_client import get_redis_service, RedisKeys
from app.models.analysis import AnalysisStatus, AnalysisResult


async def perform_update_task_status(
    task_id: str,
    status: AnalysisStatus,
    progress: int,
    result: Optional[AnalysisResult] = None,
) -> None:
    """Update a task's status in MongoDB and Redis.

    Mirrors the original logic in AnalysisService._update_task_status.
    """
    db = get_mongo_db()
    redis_service = get_redis_service()

    update_data: Dict[str, Any] = {
        "status": status,
        "progress": progress,
        "updated_at": datetime.utcnow(),
    }

    if status == AnalysisStatus.PROCESSING and "started_at" not in update_data:
        update_data["started_at"] = datetime.utcnow()
    elif status in [AnalysisStatus.COMPLETED, AnalysisStatus.FAILED]:
        update_data["completed_at"] = datetime.utcnow()
        if result:
            update_data["result"] = result.dict()

    await db.analysis_tasks.update_one({"task_id": task_id}, {"$set": update_data})

    progress_key = RedisKeys.TASK_PROGRESS.format(task_id=task_id)
    await redis_service.set_json(
        progress_key,
        {
            "task_id": task_id,
            "status": status,
            "progress": progress,
            "updated_at": datetime.utcnow().isoformat(),
        },
        ttl=3600,
    )


async def perform_update_task_status_with_tracker(
    task_id: str,
    status: AnalysisStatus,
    progress_tracker,  # RedisProgressTracker
    result: Optional[AnalysisResult] = None,
) -> None:
    """Update task status using detailed data from a progress tracker.

    Mirrors the original logic in AnalysisService._update_task_status_with_tracker.
    """
    db = get_mongo_db()
    redis_service = get_redis_service()

    progress_data = progress_tracker.to_dict()

    update_data: Dict[str, Any] = {
        "status": status,
        "progress": progress_data["progress"],
        "current_step": progress_data["current_step"],
        "message": progress_data["message"],
        "updated_at": datetime.utcnow(),
    }

    if status == AnalysisStatus.PROCESSING and "started_at" not in update_data:
        update_data["started_at"] = datetime.utcnow()
    elif status in [AnalysisStatus.COMPLETED, AnalysisStatus.FAILED]:
        update_data["completed_at"] = datetime.utcnow()
        if result:
            update_data["result"] = result.dict()

    await db.analysis_tasks.update_one({"task_id": task_id}, {"$set": update_data})

    progress_key = RedisKeys.TASK_PROGRESS.format(task_id=task_id)
    await redis_service.set_json(
        progress_key,
        {
            "task_id": task_id,
            "status": status.value if hasattr(status, "value") else status,
            "progress": progress_data["progress"],
            "current_step": progress_data["current_step"],
            "message": progress_data["message"],
            "elapsed_time": progress_data["elapsed_time"],
            "remaining_time": progress_data["remaining_time"],
            "steps": progress_data["steps"],
            "updated_at": datetime.utcnow().isoformat(),
        },
        ttl=3600,
    )


# === __init__.py ===
"""Unified analysis service package (`app/services/analysis/`)."""

__all__ = [
    "AnalysisExecutionRunner",
    "AnalysisProviderResolver",
    "has_meaningful_result_payload",
    "has_meaningful_text",
    "normalize_result_data",
    "summarize_result_completeness",
]

# === progress.py ===
import sys as _sys
_sys.modules["app.services.progress_log_handler"] = _self_mod
_sys.modules["app.services.redis_progress_tracker"] = _self_mod

# === tracker.py ===
"""
Progress Tracker (Transition Period)
- Temporarily import the RedisProgressTracker class from the old module
- Provide implementation of get_progress_by_id in this module (consistent with old implementation, correct cls reference)
"""
from typing import Any, Dict, Optional, List
import json
import os
import logging
import time



logger = logging.getLogger("app.services.progress.tracker")

from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class AnalysisStep:
    """分析步骤数据类"""
    name: str
    description: str
    status: str = "pending"  # pending, current, completed, failed
    weight: float = 0.1  # Weight, used to calculate progress
    start_time: Optional[float] = None
    end_time: Optional[float] = None


def safe_serialize(data):
    """Safe serialization, handling non-serializable objects"""
    if isinstance(data, dict):
        return {k: safe_serialize(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [safe_serialize(item) for item in data]
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    elif hasattr(data, '__dict__'):
        return safe_serialize(data.__dict__)
    else:
        return str(data)



class RedisProgressTracker:
    """Redis进度跟踪器"""

    def __init__(self, task_id: str, analysts: List[str], research_depth: str, llm_provider: str):
        self.task_id = task_id
        self.analysts = analysts
        self.research_depth = research_depth
        self.llm_provider = llm_provider

        # Redis connect
        self.redis_client = None
        self.use_redis = self._init_redis()

        # progress data
        self.progress_data = {
            'task_id': task_id,
            'status': 'running',
            'progress_percentage': 0.0,
            'current_step': 0,  # Current step index (number)
            'total_steps': 0,
            'current_step_name': '初始化',
            'current_step_description': '准备开始分析',
            'last_message': '分析任务已启动',
            'start_time': time.time(),
            'last_update': time.time(),
            'elapsed_time': 0.0,
            'remaining_time': 0.0,
            'steps': []
        }

        # Generate analysis steps
        self.analysis_steps = self._generate_dynamic_steps()
        self.progress_data['total_steps'] = len(self.analysis_steps)
        self.progress_data['steps'] = [asdict(step) for step in self.analysis_steps]

        # 🔧 Calculate and set estimated total duration
        base_total_time = self._get_base_total_time()
        self.progress_data['estimated_total_time'] = base_total_time
        self.progress_data['remaining_time'] = base_total_time  # initial remaining time = total duration

        # Save initial state
        self._save_progress()

        logger.info(f"📊 [Redis进度] 初始化完成: {task_id}, 步骤数: {len(self.analysis_steps)}")

    def _init_redis(self) -> bool:
        """初始化Redis连接"""
        try:
            # Check the REDIS_ENABLED environment variable
            redis_enabled = os.getenv('REDIS_ENABLED', 'false').lower() == 'true'
            if not redis_enabled:
                logger.info("📊 [Redis Progress] Redis Not enabled, uses file storage")
                return False

            import redis

            # Get Redis configuration from environment variables
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', 6379))
            redis_password = os.getenv('REDIS_PASSWORD', None)
            redis_db = int(os.getenv('REDIS_DB', 0))

            # Create a Redis connection
            if redis_password:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    password=redis_password,
                    db=redis_db,
                    decode_responses=True
                )
            else:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True
                )

            # test connection
            self.redis_client.ping()
            logger.info(f"📊 [Redis Progress] Redis Connection successful: {redis_host}:{redis_port}")
            return True
        except Exception as e:
            logger.warning(f"📊 [Redis Progress] Redis Connection failed, using file storage: {e}")
            return False

    def _generate_dynamic_steps(self) -> List[AnalysisStep]:
        """Dynamically generate analysis steps based on number of analysts and depth of research"""
        steps: List[AnalysisStep] = []
        # 1) Basic preparation stage (10%)
        steps.extend([
            AnalysisStep("📋 准备阶段", "Verify stock ticker, check data source availability", "pending", 0.03),
            AnalysisStep("🔧 环境检查", "Check the API key configuration to ensure data acquisition is normal", "pending", 0.02),
            AnalysisStep("💰 成本估算", "Estimate API call costs based on depth of analysis", "pending", 0.01),
            AnalysisStep("⚙️ 参数设置", "Configure analysis parameters and AI model selection", "pending", 0.02),
            AnalysisStep("🚀 启动引擎", "Initialize the AI analysis engine and prepare to start analysis", "pending", 0.02),
        ])
        # 2) Analyst team stage (35%) - Parallel
        analyst_weight = 0.35 / max(len(self.analysts), 1)
        for analyst in self.analysts:
            info = self._get_analyst_step_info(analyst)
            steps.append(AnalysisStep(info["name"], info["description"], "pending", analyst_weight))
        # 3) Research team debate stage (25%)
        rounds = self._get_debate_rounds()
        debate_weight = 0.25 / (3 + rounds)
        steps.extend([
            AnalysisStep("🐂 积极证据研究员", "Research evidence for constructing optimistic interpretations based on analyst reports", "pending", debate_weight),
            AnalysisStep("🐻 谨慎证据研究员", "Research evidence for constructing cautious interpretations based on analyst reports", "pending", debate_weight),
        ])
        for i in range(rounds):
            steps.append(AnalysisStep(f"🎯 多情景研究 第{i+1}轮", "多情景研究视角深度对比", "pending", debate_weight))
        steps.append(AnalysisStep("👔 研究整合员", "Comprehensive multi-scenario research to form a summary of research observations", "pending", debate_weight))
        # 4) Research integration stage (8%)
        steps.append(AnalysisStep("🧩 研究整合员汇总", "Organize research integration opinions and observation lists based on research results", "pending", 0.08))
        # 5) risk management team stage (15%)
        risk_weight = 0.15 / 4
        steps.extend([
            AnalysisStep("🔥 高弹性情景研究", "Study the potential revenue space from the perspective of highly elastic scenarios", "pending", risk_weight),
            AnalysisStep("🛡️ 防御情景研究", "Studying capital protection factors from the perspective of defense scenarios", "pending", risk_weight),
            AnalysisStep("⚖️ 基准情景研究", "Balancing multiple research perspectives from a baseline scenario perspective", "pending", risk_weight),
            AnalysisStep("🎯 风险评估师", "Comprehensive risk research and observation to form risk review conclusions", "pending", risk_weight),
        ])
        # 6) Final research conclusion stage (7%)
        steps.extend([
            AnalysisStep("📡 结果处理", "Collate all research observations and generate research reports", "pending", 0.04),
            AnalysisStep("📊 生成报告", "Organize analysis results and generate complete reports", "pending", 0.03),
        ])
        return steps

    def _get_debate_rounds(self) -> int:
        """根据研究深度获取辩论轮次"""
        if self.research_depth == "快速":
            return 1
        if self.research_depth == "标准":
            return 2
        return 3

    def _get_analyst_step_info(self, analyst: str) -> Dict[str, str]:
        """Get analyst step information (name and description)"""
        mapping = {
            'market': {"name": "📊 市场分析师", "description": "Analyze market performance such as stock price trends, trading volume, and technical indicators"},
            'fundamentals': {"name": "💼 基本面分析师", "description": "Analyze the company s financial status, profitability, growth and other fundamentals"},
            'news': {"name": "📰 新闻分析师", "description": "Analyze the impact of relevant news, announcements, and industry trends on stock prices"},
            'social': {"name": "💬 社交媒体分析师", "description": "Analyze social media discussions, Internet popularity, retail investor sentiment, etc."},
        }
        return mapping.get(analyst, {"name": f"🔍 {analyst}分析师", "description": f"进行{analyst}相关的专业分析"})

    def _estimate_step_time(self, step: AnalysisStep) -> float:
        """估算步骤执行时间（秒）"""
        return self._get_base_total_time() * step.weight

    def _get_base_total_time(self) -> float:
        """
        Estimated total time (seconds) based on number of analysts, research depth, and model type

        Algorithm design ideas (based on actual test data):
        1. Actual measurement: Level 4 depth + 3 analysts = 11 minutes (661 seconds)
        2. Actual measurement: Level 1 fast = 4-5 minutes
        3. Actual test: Level 2 basics = 5-6 minutes
        4. There is parallel processing between analysts, not linear superposition
        """

        # 🔧 Supports 5 levels of analysis depth
        depth_map = {
            "快速": 1,  # 1 Level - Quick Analysis
            "基础": 2,  # 2 Level - Basic Analysis
            "标准": 3,  # 3 Level - Standard Analysis (recommended)
            "深度": 4,  # 4 Level - In-Depth Analysis
            "全面": 5   # 5 Level - Comprehensive Analysis
        }
        d = depth_map.get(self.research_depth, 3)  # Default standard analysis

        # 📊 Base time (seconds) based on actual test data
        # This is the basic time spent by a single analyst
        base_time_per_depth = {
            1: 150,  # 1 Level: 2.5 minutes (the actual measurement is 4-5 minutes for multiple analysts)
            2: 180,  # 2 Level: 3 minutes (the actual measurement is 5-6 minutes for multiple analysts)
            3: 240,  # 3 Level: 4 minutes (front-end display: 6-10 minutes)
            4: 330,  # 4 Level: 5.5 minutes (actual measurement: 11 minutes for 3 analysts, about 5.5 minutes for a single backend)
            5: 480   # 5 Level: 8 minutes (front-end display: 15-25 minutes)
        }.get(d, 240)

        # 📈 Impact coefficient of number of analysts (based on actual test data)
        # Actual measurement: Level 4 + 3 analysts = 11 minutes = 660 seconds
        # Reverse push: 330 seconds * multiplier = 660 seconds => multiplier = 2.0
        analyst_count = len(self.analysts)
        if analyst_count == 1:
            analyst_multiplier = 1.0
        elif analyst_count == 2:
            analyst_multiplier = 1.5  # 2 Analysts take about 1.5 times the time
        elif analyst_count == 3:
            analyst_multiplier = 2.0  # 3 It takes about 2 times as long for an analyst (verified by actual measurement)
        elif analyst_count == 4:
            analyst_multiplier = 2.4  # 4 Analysts spend about 2.4 times longer
        else:
            analyst_multiplier = 2.4 + (analyst_count - 4) * 0.3  # Each additional analyst increases 30%

        # 🚀 Model speed impact (based on actual testing)
        model_mult = {
            'dashscope': 1.0,  # Ali Bailian speed is moderate
            'deepseek': 0.8,   # DeepSeek faster
            'google': 1.2      # Google slower
        }.get(self.llm_provider, 1.0)

        # Calculate total time
        total_time = base_time_per_depth * analyst_multiplier * model_mult

        return total_time

    def _calculate_time_estimates(self) -> tuple[float, float, float]:
        """Return (elapsed, remaining, estimated_total)"""
        now = time.time()
        start = self.progress_data.get('start_time', now)
        elapsed = now - start
        pct = self.progress_data.get('progress_percentage', 0)
        base_total = self._get_base_total_time()

        if pct >= 100:
            # Task completed
            est_total = elapsed
            remaining = 0
        else:
            # Estimated total duration of use (fixed value)
            est_total = base_total
            # Estimated remaining = Estimated total time - elapsed time
            remaining = max(0, est_total - elapsed)

        return elapsed, remaining, est_total

    @staticmethod
    def _calculate_static_time_estimates(progress_data: dict) -> dict:
        """Static: Calculate time estimates for existing progress data"""
        if 'start_time' not in progress_data or not progress_data['start_time']:
            return progress_data
        now = time.time()
        elapsed = now - progress_data['start_time']
        progress_data['elapsed_time'] = elapsed
        pct = progress_data.get('progress_percentage', 0)

        if pct >= 100:
            # Task completed
            est_total = elapsed
            remaining = 0
        else:
            # Use estimated total duration (fixed value), or default if not available
            est_total = progress_data.get('estimated_total_time', 300)
            # Estimated remaining = Estimated total time - elapsed time
            remaining = max(0, est_total - elapsed)

        progress_data['estimated_total_time'] = est_total
        progress_data['remaining_time'] = remaining
        return progress_data

    def update_progress(self, progress_update: Any) -> Dict[str, Any]:
        """update progress and persist; accepts dict or plain message string"""
        try:
            if isinstance(progress_update, dict):
                self.progress_data.update(progress_update)
            elif isinstance(progress_update, str):
                self.progress_data['last_message'] = progress_update
                self.progress_data['last_update'] = time.time()
            else:
                # try to coerce iterable of pairs; otherwise fallback to string
                try:
                    self.progress_data.update(dict(progress_update))
                except Exception:
                    self.progress_data['last_message'] = str(progress_update)
                    self.progress_data['last_update'] = time.time()

            # Automatically update step status based on progress percentage
            progress_pct = self.progress_data.get('progress_percentage', 0)
            self._update_steps_by_progress(progress_pct)

            # Get current step index
            current_step_index = self._detect_current_step()
            self.progress_data['current_step'] = current_step_index

            # 🔑 Key: Automatically set only if progress_update does not provide current_step_name
            # This allows the step names provided by the workflow engine to take precedence
            if isinstance(progress_update, dict):
                has_step_name = 'current_step_name' in progress_update
                has_step_desc = 'current_step_description' in progress_update
            else:
                has_step_name = False
                has_step_desc = False

            # Update the name and description of the current step (if not provided manually)
            if 0 <= current_step_index < len(self.analysis_steps):
                current_step_obj = self.analysis_steps[current_step_index]
                if not has_step_name:
                    self.progress_data['current_step_name'] = current_step_obj.name
                if not has_step_desc:
                    self.progress_data['current_step_description'] = current_step_obj.description

            elapsed, remaining, est_total = self._calculate_time_estimates()
            self.progress_data['elapsed_time'] = elapsed
            self.progress_data['remaining_time'] = remaining
            self.progress_data['estimated_total_time'] = est_total

            # Update progress_data in steps
            self.progress_data['steps'] = [asdict(step) for step in self.analysis_steps]

            self._save_progress()
            logger.debug(f"[RedisProgress] updated: {self.task_id} - {self.progress_data.get('progress_percentage', 0)}%")
            return self.progress_data
        except Exception as e:
            logger.error(f"[RedisProgress] update failed: {self.task_id} - {e}")
            return self.progress_data

    def _update_steps_by_progress(self, progress_pct: float) -> None:
        """Automatically update step status based on progress percentage"""
        try:
            cumulative_weight = 0.0
            current_time = time.time()

            for step in self.analysis_steps:
                step_start_pct = cumulative_weight
                step_end_pct = cumulative_weight + (step.weight * 100)

                if progress_pct >= step_end_pct:
                    # Completed steps
                    if step.status != 'completed':
                        step.status = 'completed'
                        step.end_time = current_time
                elif progress_pct > step_start_pct:
                    # Steps currently being performed
                    if step.status != 'current':
                        step.status = 'current'
                        step.start_time = current_time
                else:
                    # steps not yet started
                    if step.status not in ('pending', 'failed'):
                        step.status = 'pending'

                cumulative_weight = step_end_pct
        except Exception as e:
            logger.debug(f"[RedisProgress] update steps by progress failed: {e}")

    def _detect_current_step(self) -> int:
        """detect current step index by status"""
        try:
            # The priority search status is 'current' steps
            for index, step in enumerate(self.analysis_steps):
                if step.status == 'current':
                    return index
            # if not 'current', Find the first 'pending' steps
            for index, step in enumerate(self.analysis_steps):
                if step.status == 'pending':
                    return index
            # If all are completed, return the index of the last step
            for index, step in enumerate(reversed(self.analysis_steps)):
                if step.status == 'completed':
                    return len(self.analysis_steps) - 1 - index
            return 0
        except Exception as e:
            logger.debug(f"[RedisProgress] detect current step failed: {e}")
            return 0

    def _find_step_by_name(self, step_name: str) -> Optional[AnalysisStep]:
        for step in self.analysis_steps:
            if step.name == step_name:
                return step
        return None

    def _find_step_by_pattern(self, pattern: str) -> Optional[AnalysisStep]:
        for step in self.analysis_steps:
            if pattern in step.name:
                return step
        return None

    def _save_progress(self) -> None:
        try:
            progress_copy = self.to_dict()
            serialized = json.dumps(progress_copy)
            if self.use_redis and self.redis_client:
                key = f"progress:{self.task_id}"
                self.redis_client.set(key, serialized)
                self.redis_client.expire(key, 3600)
            else:
                os.makedirs("./data/progress", exist_ok=True)
                with open(f"./data/progress/{self.task_id}.json", 'w', encoding='utf-8') as f:
                    f.write(serialized)
        except Exception as e:
            logger.error(f"[RedisProgress] save progress failed: {self.task_id} - {e}")

    def mark_completed(self) -> Dict[str, Any]:
        try:
            self.progress_data['progress_percentage'] = 100
            self.progress_data['status'] = 'completed'
            self.progress_data['completed'] = True
            self.progress_data['completed_time'] = time.time()
            for step in self.analysis_steps:
                if step.status != 'failed':
                    step.status = 'completed'
                    step.end_time = step.end_time or time.time()
            self._save_progress()
            return self.progress_data
        except Exception as e:
            logger.error(f"[RedisProgress] mark completed failed: {self.task_id} - {e}")
            return self.progress_data

    def mark_failed(self, reason: str = "") -> Dict[str, Any]:
        try:
            self.progress_data['status'] = 'failed'
            self.progress_data['failed'] = True
            self.progress_data['failed_reason'] = reason
            self.progress_data['completed_time'] = time.time()
            for step in self.analysis_steps:
                if step.status not in ('completed', 'failed'):
                    step.status = 'failed'
                    step.end_time = step.end_time or time.time()
            self._save_progress()
            return self.progress_data
        except Exception as e:
            logger.error(f"[RedisProgress] mark failed failed: {self.task_id} - {e}")
            return self.progress_data

    def to_dict(self) -> Dict[str, Any]:
        try:
            # 🔧 Calculate time estimates in real time to ensure the latest time information is returned
            elapsed, remaining, est_total = self._calculate_time_estimates()

            return {
                'task_id': self.task_id,
                'analysts': self.analysts,
                'research_depth': self.research_depth,
                'llm_provider': self.llm_provider,
                'steps': [asdict(step) for step in self.analysis_steps],
                'start_time': self.progress_data.get('start_time'),
                'elapsed_time': elapsed,  # Use real-time calculated values
                'remaining_time': remaining,  # Use real-time calculated values
                'estimated_total_time': est_total,  # Use real-time calculated values
                'progress_percentage': self.progress_data.get('progress_percentage', 0),
                'status': self.progress_data.get('status', 'pending'),
                'current_step': self.progress_data.get('current_step'),
                'current_step_name': self.progress_data.get('current_step_name', ''),
                'current_step_description': self.progress_data.get('current_step_description', ''),
                'last_message': self.progress_data.get('last_message', ''),
                'last_update': self.progress_data.get('last_update', time.time()),
            }
        except Exception as e:
            logger.error(f"[RedisProgress] to_dict failed: {self.task_id} - {e}")
            return self.progress_data





def get_progress_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    """Get progress based on task ID (consistent with old implementation, fix cls reference)"""
    try:
        # Check the REDIS_ENABLED environment variable
        redis_enabled = os.getenv('REDIS_ENABLED', 'false').lower() == 'true'

        # If Redis is enabled, try first Redis
        if redis_enabled:
            try:
                import redis

                # Get Redis configuration from environment variables
                redis_host = os.getenv('REDIS_HOST', 'localhost')
                redis_port = int(os.getenv('REDIS_PORT', 6379))
                redis_password = os.getenv('REDIS_PASSWORD', None)
                redis_db = int(os.getenv('REDIS_DB', 0))

                # Create a Redis connection
                if redis_password:
                    redis_client = redis.Redis(
                        host=redis_host,
                        port=redis_port,
                        password=redis_password,
                        db=redis_db,
                        decode_responses=True
                    )
                else:
                    redis_client = redis.Redis(
                        host=redis_host,
                        port=redis_port,
                        db=redis_db,
                        decode_responses=True
                    )

                key = f"progress:{task_id}"
                data = redis_client.get(key)
                if data:
                    progress_data = json.loads(data)
                    progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                    return progress_data
            except Exception as e:
                logger.debug(f"📊 [Redis Progress] Redis Read failed: {e}")

        # Try to read from file
        progress_file = f"./data/progress/{task_id}.json"
        if os.path.exists(progress_file):
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                return progress_data

        # Try alternate file locations
        backup_file = f"./data/progress_{task_id}.json"
        if os.path.exists(backup_file):
            with open(backup_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                return progress_data

        return None

    except Exception as e:
        logger.error(f"📊 [Redis Progress] Failed to get progress: {task_id} - {e}")
        return None

# === log_handler.py ===
"""
Progress log handler
Monitor the log output of TradingAgents and automatically update the progress tracker
"""

import logging
import re
import threading
from typing import Dict, Optional

logger = logging.getLogger("app.services.progress_log_handler")


class ProgressLogHandler(logging.Handler):
    """Progress log processor, monitors TradingAgents logs and updates progress"""

    def __init__(self):
        super().__init__()
        self._trackers: Dict[str, RedisProgressTracker] = {}
        self._lock = threading.Lock()

        # log pattern matching
        self.progress_patterns = {
            # basic stage
            r"Verify.*Stock code|Check.*data source": "📋 准备阶段",
            r"Check.*API.*key|environment.*Configuration": "🔧 环境检查",
            r"Estimate.*cost|cost.*Estimate": "💰 成本估算",
            r"Configuration.*parameters|parameters.*settings": "⚙️ 参数设置",
            r"initialization.*engine|start.*engine": "🚀 启动引擎",

            # analyst stage
            r"market analyst.*start|start.*market analysis|market.*data.*analysis": "📊 市场分析师正在分析",
            r"fundamental analyst.*start|start.*fundamental analysis|Finance.*data.*analysis": "💼 基本面分析师正在分析",
            r"news analyst.*start|start.*news analysis|News.*data.*analysis": "📰 新闻分析师正在分析",
            r"social media analyst.*start|start.*social media analysis|emotions.*analysis": "💬 Social media analysts are analyzing",

            # research team stage
            r"bullish researcher|multi-investigator|bull.*researcher|Positive Evidence Researcher": "🐂 Active evidence researcher constructs argument",
            r"bearish researcher|short researcher|bear.*researcher|cautious evidence researcher": "🐻 Cautious Evidence Researchers Identify Risks",
            r"Research.*Debate|Debate.*start|debate.*start|multi-scenario research": "🎯 多情景研究进行中",
            r"research manager|research.*manager|research integrator": "👔 研究整合员汇总",

            # Research integration stage
            r"trader.*decision making|trader.*decision|formulate.*trading strategy|research integrator.*Summary|research integration.*opinion": "🧩 研究整合员汇总",

            # risk management stage
            r"Radical.*risk|risky.*risk|high elasticity scenario": "🔥 高弹性情景研究",
            r"conservative.*risk|conservative.*risk|defense scenario": "🛡️ 防御情景研究",
            r"Neutral.*risk|neutral.*risk|Baseline scenario": "⚖️ 基准情景研究",
            r"risk manager|risk.*manager|risk assessor": "🎯 风险评估师形成结论",

            # final stage
            r"signal processing|signal.*process|Result processing": "📡 结果处理",
            r"generate.*report|report.*generat": "📊 生成研究报告",
            r"analysis.*Complete|analysis.*complet": "✅ 研究完成",
        }

        logger.info("📊 [progress log] Log processor initialization completed")

    def register_tracker(self, task_id: str, tracker: RedisProgressTracker):
        """注册进度跟踪器"""
        with self._lock:
            self._trackers[task_id] = tracker
            logger.info(f"📊 [progress log] Register tracker: {task_id}")

    def unregister_tracker(self, task_id: str):
        """注销进度跟踪器"""
        with self._lock:
            if task_id in self._trackers:
                del self._trackers[task_id]
                logger.info(f"📊 [progress log] Unregister tracker: {task_id}")

    def emit(self, record):
        """处理日志记录"""
        try:
            message = record.getMessage()

            # Check if it is a log message we care about
            progress_message = self._extract_progress_message(message)
            if not progress_message:
                return

            # Find matching trackers (reduce lock holding time)
            trackers_copy = {}
            with self._lock:
                trackers_copy = self._trackers.copy()

            # Handle tracker updates outside of lock
            for task_id, tracker in trackers_copy.items():
                try:
                    # Check tracker status
                    if hasattr(tracker, 'progress_data') and tracker.progress_data.get('status') == 'running':
                        tracker.update_progress(progress_message)
                        logger.debug(f"📊 [progress log] update progress: {task_id} -> {progress_message}")
                        break  # Only update the first matching tracker
                except Exception as e:
                    logger.warning(f"📊 [progress log] Update failed: {task_id} - {e}")

        except Exception as e:
            # Do not let errors in the log processor affect the main program
            logger.error(f"📊 [progress log] Log processing error: {e}")

    def _extract_progress_message(self, message: str) -> Optional[str]:
        """从日志消息中提取进度信息"""
        message_lower = message.lower()

        # Check whether progress-related keywords are included
        progress_keywords = [
            "开始", "完成", "分析", "处理", "执行", "生成",
            "start", "complete", "analysis", "process", "execute", "generate"
        ]

        if not any(keyword in message_lower for keyword in progress_keywords):
            return None

        # Match specific progress patterns
        for pattern, progress_msg in self.progress_patterns.items():
            if re.search(pattern, message_lower):
                return progress_msg

        return None

    def _extract_stock_symbol(self, message: str) -> Optional[str]:
        """从消息中提取股票代码"""
        # Matches common ticker formats
        patterns = [
            r'\b(\d{6})\b',  # 6 Digits (A shares)
            r'\b([A-Z]{1,5})\b',  # 1-5 uppercase letters (U.S. stocks)
            r'\b(\d{4,5}\.HK)\b',  # Hong Kong stock format
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)

        return None


# Global log handler instance
_progress_log_handler = None
_handler_lock = threading.Lock()


def get_progress_log_handler() -> ProgressLogHandler:
    """Get the global progress log processor instance"""
    global _progress_log_handler

    with _handler_lock:
        if _progress_log_handler is None:
            _progress_log_handler = ProgressLogHandler()

            # Add handler to relevant logger
            loggers_to_monitor = [
                "agents",
                "tradingagents",
                "agents.analysts",
                "agents.researchers",
                "agents.traders",
                "agents.managers",
                "agents.risk_mgmt",
            ]

            for logger_name in loggers_to_monitor:
                target_logger = logging.getLogger(logger_name)
                target_logger.addHandler(_progress_log_handler)
                target_logger.setLevel(logging.INFO)

            logger.info(f"📊 [进度日志] 已注册到 {len(loggers_to_monitor)} 个日志记录器")

    return _progress_log_handler


def register_analysis_tracker(task_id: str, tracker: RedisProgressTracker):
    """注册分析跟踪器到日志监控"""
    handler = get_progress_log_handler()
    handler.register_tracker(task_id, tracker)


def unregister_analysis_tracker(task_id: str):
    """Unregister an analytics tracker from log monitoring"""
    handler = get_progress_log_handler()
    handler.unregister_tracker(task_id)


# === __init__.py ===
"""
Progress Sub-package (transition period): Structured organization of progress tracking and log processing.
Adopted at the current stage New paths re-exported to old implementation way to keep the API stable.
"""

# === analysis_service.py ===
"""
Stock Analysis Services
Wrap existing TradingAgents analysis functions into API services
"""

import asyncio
import uuid
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
import sys

# Add project root directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Initialize TradingAgents log system
from tradingagents.utils.logging_init import init_logging
init_logging()

try:
    from tradingagents.graph.trading_graph import TradingAgentsGraph
except ImportError:
    TradingAgentsGraph = None
from tradingagents.default_config import DEFAULT_CONFIG
from app.models.analysis import (
    AnalysisParameters, AnalysisResult, AnalysisTask, AnalysisBatch,
    AnalysisStatus, BatchStatus, SingleAnalysisRequest, BatchAnalysisRequest
)
from app.models.user import PyObjectId
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
from app.core.database import get_mongo_db
from app.core.redis_client import get_redis_service, RedisKeys
try:
    from app.services.queue_service import QueueService
except ImportError:
    QueueService = None
from app.core.database import get_redis_client
try:
    from app.services.config_provider import provider as config_provider
except ImportError:
    config_provider = None
try:
    from app.services.queue import DEFAULT_USER_CONCURRENT_LIMIT, GLOBAL_CONCURRENT_LIMIT, VISIBILITY_TIMEOUT_SECONDS
except ImportError:
    DEFAULT_USER_CONCURRENT_LIMIT = None; GLOBAL_CONCURRENT_LIMIT = None; VISIBILITY_TIMEOUT_SECONDS = None
try:
    from app.services.usage_statistics_service import UsageStatisticsService
except ImportError:
    UsageStatisticsService = None
from app.models.config import UsageRecord

import logging
logger = logging.getLogger(__name__)


class AnalysisService:
    """股票分析服务类"""

    def __init__(self):
        # Get the Redis client
        redis_client = get_redis_client()
        self.queue_service = QueueService(redis_client)
        # Initialize usage statistics service
        self.usage_service = UsageStatisticsService()
        self._trading_graph_cache = {}
        # Progress tracker cache
        self._progress_trackers: Dict[str, RedisProgressTracker] = {}

    def _convert_user_id(self, user_id: str) -> PyObjectId:
        """Convert string user ID to PyObjectId"""
        try:
            logger.info(f"🔄 开始转换用户ID: {user_id} (类型: {type(user_id)})")

            # If you are an admin user, use a fixed ObjectId
            if user_id == "admin":
                # Use fixed ObjectId as admin user ID
                admin_object_id = ObjectId("507f1f77bcf86cd799439011")
                logger.info(f"🔄 Convert admin user ID: {user_id} -> {admin_object_id}")
                return PyObjectId(admin_object_id)
            else:
                # Try converting the string to ObjectId
                object_id = ObjectId(user_id)
                logger.info(f"🔄 转换用户ID: {user_id} -> {object_id}")
                return PyObjectId(object_id)
        except Exception as e:
            logger.error(f"❌ 用户ID转换失败: {user_id} -> {e}")
            # If the conversion fails, generate a new ObjectId
            new_object_id = ObjectId()
            logger.warning(f"⚠️ 生成新的用户ID: {new_object_id}")
            return PyObjectId(new_object_id)

    def _get_user_risk_preference(self, user_id: str) -> str:
        """Get the user s risk preference settings

        Args:
            user_id: User ID

        Returns:
            risk appetite: 'conservative'(conservative) / 'neutral'(Neutral) / 'aggressive'(Radical)
            Return by default 'neutral'
        """
        try:
            db = get_mongo_db()
            users_collection = db["users"]

            # Query user
            user = users_collection.find_one({"_id": ObjectId(user_id)})
            if user and "preferences" in user:
                risk_pref = user["preferences"].get("risk_preference", "neutral")
                logger.info(f"📊 获取用户 {user_id} 的风险偏好: {risk_pref}")
                return risk_pref

            logger.info(f"📊 用户 {user_id} 未设置风险偏好，使用默认值: neutral")
            return "neutral"
        except Exception as e:
            logger.warning(f"⚠️ Failed to obtain user risk preference: {e}, Use default value: neutral")
            return "neutral"
    
    def _get_trading_graph(self, config: Dict[str, Any]) -> TradingAgentsGraph:
        """Get or create a TradingAgents graph instance (with cache)— Deactivated

        v3.0 The old TradingAgentsGraph engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] AnalysisService._get_trading_graph deactivated,"
            "TradingAgentsGraph No longer instantiated."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        config_key = json.dumps(config, sort_keys=True)

        if config_key not in self._trading_graph_cache:
            # Use the complete configuration directly and no longer merge DEFAULT_CONFIG (because create_analysis_config has already been processed)
            # This is consistent with the way single strand analysis services and web directories
            self._trading_graph_cache[config_key] = TradingAgentsGraph(
                selected_analysts=config.get("selected_analysts", ["market", "fundamentals"]),
                debug=config.get("debug", False),
                config=config
            )

            logger.info(f"Create a new TradingAgents instance: {config.get('llm_provider', 'default')}")

        return self._trading_graph_cache[config_key]

    def _execute_analysis_sync_with_progress(self, task: AnalysisTask, progress_tracker: RedisProgressTracker) -> AnalysisResult:
        """Execute analysis tasks synchronously (run in thread pool, with progress tracking)— Deactivated

        v3.0 The legacy engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] AnalysisService._execute_analysis_sync_with_progress deactivated,"
            "task_id=%s The v2 engine should be used instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
            % getattr(task, "task_id", "<unknown>")
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        try:
            # Reinitialize the logging system in a thread
            from tradingagents.utils.logging_init import init_logging, get_logger
            init_logging()
            thread_logger = get_logger('analysis_thread')

            thread_logger.info(f"🔄 [thread pool] Start an analysis task: {task.task_id} - {task.symbol}")
            logger.info(f"🔄 [thread pool] Start an analysis task: {task.task_id} - {task.symbol}")

            # environmental inspection
            progress_tracker.update_progress("🔧 检查环境配置")

            # Create a complete configuration using standard configuration functions
            from app.core.unified_config import unified_config

            quick_model = getattr(task.parameters, 'quick_analysis_model', None) or unified_config.get_quick_analysis_model()
            deep_model = getattr(task.parameters, 'deep_analysis_model', None) or unified_config.get_deep_analysis_model()

            # 🔧 Read the model's complete configuration parameters from the MongoDB database (instead of from a JSON file)
            quick_model_config = None
            deep_model_config = None

            try:
                from pymongo import MongoClient
                from app.core.config import settings

                # Using the synchronous MongoDB client
                client = MongoClient(settings.MONGO_URI)
                db = client[settings.MONGO_DB]
                collection = db.system_configs

                # Query the latest active configuration
                doc = collection.find_one({"is_active": True}, sort=[("version", -1)])

                if doc and "llm_configs" in doc:
                    llm_configs = doc["llm_configs"]
                    logger.info(f"✅ 从 MongoDB 读取到 {len(llm_configs)} 个模型配置")

                    for llm_config in llm_configs:
                        if llm_config.get("model_name") == quick_model:
                            quick_model_config = {
                                "max_tokens": llm_config.get("max_tokens", 4000),
                                "temperature": llm_config.get("temperature", 0.7),
                                "timeout": llm_config.get("timeout", 180),
                                "retry_times": llm_config.get("retry_times", 3),
                                "api_base": llm_config.get("api_base")
                            }
                            if llm_config.get("reasoning_effort"):
                                quick_model_config["reasoning_effort"] = llm_config["reasoning_effort"]
                            logger.info(f"✅ 读取快速模型配置: {quick_model}")
                            logger.info(f"   max_tokens={quick_model_config['max_tokens']}, temperature={quick_model_config['temperature']}")
                            logger.info(f"   timeout={quick_model_config['timeout']}, retry_times={quick_model_config['retry_times']}")
                            logger.info(f"   api_base={quick_model_config['api_base']}")

                        if llm_config.get("model_name") == deep_model:
                            deep_model_config = {
                                "max_tokens": llm_config.get("max_tokens", 4000),
                                "temperature": llm_config.get("temperature", 0.7),
                                "timeout": llm_config.get("timeout", 180),
                                "retry_times": llm_config.get("retry_times", 3),
                                "api_base": llm_config.get("api_base")
                            }
                            if llm_config.get("reasoning_effort"):
                                deep_model_config["reasoning_effort"] = llm_config["reasoning_effort"]
                            logger.info(f"✅ 读取深度模型配置: {deep_model} - {deep_model_config}")
                else:
                    logger.warning("⚠️ MongoDB No system configuration found, default parameters will be used")
            except Exception as e:
                logger.warning(f"⚠️ Failed to read model configuration from MongoDB: {e}, Default parameters will be used")

            # cost estimate
            progress_tracker.update_progress("💰 预估分析成本")

            # Dynamically find suppliers based on model name (synchronized versions)
            llm_provider = "dashscope"  # Used by default dashscope

            # Parameter configuration
            progress_tracker.update_progress("⚙️ 配置分析参数")

            # Create a complete configuration using standard configuration functions
            config = create_analysis_config(
                research_depth=task.parameters.research_depth,
                selected_analysts=task.parameters.selected_analysts or ["market", "fundamentals"],
                quick_model=quick_model,
                deep_model=deep_model,
                llm_provider=llm_provider,
                market_type=getattr(task.parameters, 'market_type', "A股"),
                quick_model_config=quick_model_config,  # Pass model configuration
                deep_model_config=deep_model_config     # Pass model configuration
            )

            # Start the engine
            progress_tracker.update_progress("🚀 初始化AI分析引擎")

            # Get TradingAgents instance
            trading_graph = self._get_trading_graph(config)

            # Perform analysis
            from datetime import timezone
            start_time = datetime.now(timezone.utc)
            analysis_date = task.parameters.analysis_date or datetime.now().strftime("%Y-%m-%d")

            # Create a progress callback function
            def progress_callback(message: str):
                progress_tracker.update_progress(message)

            # Call existing analysis methods (synchronous calls, passing progress callbacks)
            from tradingagents.agents.utils.agent_context import AgentContext
            # Obtain user risk preference and inject it into AgentContext
            risk_preference = self._get_user_risk_preference(str(task.user_id))
            ctx = AgentContext(user_id=str(task.user_id), preference_id=risk_preference)
            logger.info(f"[diagnose] inject AgentContext task_id={task.task_id} user_id={task.user_id} symbol={task.symbol} date={analysis_date} risk_preference={risk_preference}")
            _, decision = trading_graph.propagate(task.symbol, analysis_date, progress_callback, task_id=task.task_id, agent_context=ctx.__dict__)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Generate report
            progress_tracker.update_progress("📊 生成研究报告")

            # Extract model information from decisions
            model_info = decision.get('model_info', 'Unknown') if isinstance(decision, dict) else 'Unknown'

            # Build results
            result = AnalysisResult(
                analysis_id=str(uuid.uuid4()),
                summary=decision.get("summary", ""),
                recommendation=decision.get("recommendation", ""),
                confidence_score=decision.get("confidence_score", 0.0),
                risk_level=decision.get("risk_level", "中等"),
                key_points=decision.get("key_points", []),
                detailed_analysis=decision,
                execution_time=execution_time,
                tokens_used=decision.get("tokens_used", 0),
                model_info=model_info  # 🔥 Add model information fields
            )

            logger.info(f"✅ [线程池] 分析任务完成: {task.task_id} - 耗时{execution_time:.2f}秒")
            return result

        except Exception as e:
            logger.error(f"❌ [thread pool] Failed to execute analysis task: {task.task_id} - {e}")
            raise

    def _execute_analysis_sync(self, task: AnalysisTask) -> AnalysisResult:
        """Execute analysis tasks synchronously (running in a thread pool)— Deactivated

        v3.0 The legacy engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] AnalysisService._execute_analysis_sync deactivated,"
            "task_id=%s The v2 engine should be used instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
            % getattr(task, "task_id", "<unknown>")
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        try:
            logger.info(f"🔄 [thread pool] Start an analysis task: {task.task_id} - {task.symbol}")

            # Create a complete configuration using standard configuration functions
            from app.core.unified_config import unified_config

            quick_model = getattr(task.parameters, 'quick_analysis_model', None) or unified_config.get_quick_analysis_model()
            deep_model = getattr(task.parameters, 'deep_analysis_model', None) or unified_config.get_deep_analysis_model()

            # 🔧 Read the model's complete configuration parameters from the MongoDB database (instead of from a JSON file)
            quick_model_config = None
            deep_model_config = None

            try:
                from pymongo import MongoClient
                from app.core.config import settings

                # Using the synchronous MongoDB client
                client = MongoClient(settings.MONGO_URI)
                db = client[settings.MONGO_DB]
                collection = db.system_configs

                # Query the latest active configuration
                doc = collection.find_one({"is_active": True}, sort=[("version", -1)])

                if doc and "llm_configs" in doc:
                    llm_configs = doc["llm_configs"]
                    logger.info(f"✅ 从 MongoDB 读取到 {len(llm_configs)} 个模型配置")

                    for llm_config in llm_configs:
                        if llm_config.get("model_name") == quick_model:
                            quick_model_config = {
                                "max_tokens": llm_config.get("max_tokens", 4000),
                                "temperature": llm_config.get("temperature", 0.7),
                                "timeout": llm_config.get("timeout", 180),
                                "retry_times": llm_config.get("retry_times", 3),
                                "api_base": llm_config.get("api_base")
                            }
                            if llm_config.get("reasoning_effort"):
                                quick_model_config["reasoning_effort"] = llm_config["reasoning_effort"]
                            logger.info(f"✅ 读取快速模型配置: {quick_model}")
                            logger.info(f"   max_tokens={quick_model_config['max_tokens']}, temperature={quick_model_config['temperature']}")
                            logger.info(f"   timeout={quick_model_config['timeout']}, retry_times={quick_model_config['retry_times']}")
                            logger.info(f"   api_base={quick_model_config['api_base']}")

                        if llm_config.get("model_name") == deep_model:
                            deep_model_config = {
                                "max_tokens": llm_config.get("max_tokens", 4000),
                                "temperature": llm_config.get("temperature", 0.7),
                                "timeout": llm_config.get("timeout", 180),
                                "retry_times": llm_config.get("retry_times", 3),
                                "api_base": llm_config.get("api_base")
                            }
                            if llm_config.get("reasoning_effort"):
                                deep_model_config["reasoning_effort"] = llm_config["reasoning_effort"]
                            logger.info(f"✅ 读取深度模型配置: {deep_model} - {deep_model_config}")
                else:
                    logger.warning("⚠️ MongoDB No system configuration found, default parameters will be used")
            except Exception as e:
                logger.warning(f"⚠️ Failed to read model configuration from MongoDB: {e}, Default parameters will be used")

            # Dynamically find suppliers based on model name (synchronized versions)
            llm_provider = "dashscope"  # Used by default dashscope

            # Create a complete configuration using standard configuration functions
            config = create_analysis_config(
                research_depth=task.parameters.research_depth,
                selected_analysts=task.parameters.selected_analysts or ["market", "fundamentals"],
                quick_model=quick_model,
                deep_model=deep_model,
                llm_provider=llm_provider,
                market_type=getattr(task.parameters, 'market_type', "A股"),
                quick_model_config=quick_model_config,  # Pass model configuration
                deep_model_config=deep_model_config     # Pass model configuration
            )

            # Get TradingAgents instance
            trading_graph = self._get_trading_graph(config)

            # Perform analysis
            from datetime import timezone
            start_time = datetime.now(timezone.utc)
            analysis_date = task.parameters.analysis_date or datetime.now().strftime("%Y-%m-%d")

            # Call an existing analysis method (synchronous call)
            from tradingagents.agents.utils.agent_context import AgentContext
            # Obtain user risk preference and inject it into AgentContext
            risk_preference = self._get_user_risk_preference(str(task.user_id))
            ctx = AgentContext(user_id=str(task.user_id), preference_id=risk_preference)
            logger.info(f"[diagnose] inject AgentContext task_id={task.task_id} user_id={task.user_id} symbol={task.symbol} date={analysis_date} risk_preference={risk_preference}")
            _, decision = trading_graph.propagate(task.symbol, analysis_date, agent_context=ctx.__dict__)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Extract model information from decisions
            model_info = decision.get('model_info', 'Unknown') if isinstance(decision, dict) else 'Unknown'

            # Build results
            result = AnalysisResult(
                analysis_id=str(uuid.uuid4()),
                summary=decision.get("summary", ""),
                recommendation=decision.get("recommendation", ""),
                confidence_score=decision.get("confidence_score", 0.0),
                risk_level=decision.get("risk_level", "中等"),
                key_points=decision.get("key_points", []),
                detailed_analysis=decision,
                execution_time=execution_time,
                tokens_used=decision.get("tokens_used", 0),
                model_info=model_info  # 🔥 Add model information fields
            )

            logger.info(f"✅ [线程池] 分析任务完成: {task.task_id} - 耗时{execution_time:.2f}秒")
            return result

        except Exception as e:
            logger.error(f"❌ [thread pool] Failed to execute analysis task: {task.task_id} - {e}")
            raise

    async def _execute_single_analysis_async(self, task: AnalysisTask):
        """Asynchronously execute single-strand analysis tasks (run in the background without blocking the main thread)"""
        progress_tracker = None
        try:
            logger.info(f"🔄 开始执行分析任务: {task.task_id} - {task.symbol}")

            # Create a progress tracker
            progress_tracker = RedisProgressTracker(
                task_id=task.task_id,
                analysts=task.parameters.selected_analysts or ["market", "fundamentals"],
                research_depth=task.parameters.research_depth or "标准",
                llm_provider="dashscope"
            )

            # Cache progress tracker
            self._progress_trackers[task.task_id] = progress_tracker

            # Initialization progress
            progress_tracker.update_progress("🚀 开始股票分析")
            await self._update_task_status_with_tracker(task.task_id, AnalysisStatus.PROCESSING, progress_tracker)

            # Perform analysis in a thread pool to avoid blocking the event loop
            import asyncio
            import concurrent.futures

            loop = asyncio.get_event_loop()

            # Run synchronized analysis code using a thread pool executor
            with concurrent.futures.ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(
                    executor,
                    self._execute_analysis_sync_with_progress,
                    task,
                    progress_tracker
                )

            # Mark complete
            progress_tracker.mark_completed("✅ 研究完成")
            await self._update_task_status_with_tracker(task.task_id, AnalysisStatus.COMPLETED, progress_tracker, result)

            # Record token usage
            try:
                # Get model information used
                quick_model = getattr(task.parameters, 'quick_analysis_model', None)
                deep_model = getattr(task.parameters, 'deep_analysis_model', None)

                # Prioritize using deep analysis models, if not then use fast analysis models
                model_name = deep_model or quick_model or "qwen-plus"

                # Determine supplier based on model name
                provider = get_provider_by_model_name(model_name)

                # Log usage
                await self._record_token_usage(task, result, provider, model_name)
            except Exception as e:
                logger.error(f"⚠️  Record token usage failure: {e}")

            logger.info(f"✅ 分析任务完成: {task.task_id}")

        except Exception as e:
            logger.error(f"❌ 分析任务失败: {task.task_id} - {e}")

            # Marking failed
            if progress_tracker:
                progress_tracker.mark_failed(str(e))
                await self._update_task_status_with_tracker(task.task_id, AnalysisStatus.FAILED, progress_tracker)
            else:
                await self._update_task_status(task.task_id, AnalysisStatus.FAILED, 0, str(e))
        finally:
            # Clean progress tracker cache
            if task.task_id in self._progress_trackers:
                del self._progress_trackers[task.task_id]

    async def submit_single_analysis(
        self,
        user_id: str,
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """提交单股分析任务"""
        try:
            logger.info("📝 开始提交单股分析任务")
            logger.info(f"👤 用户ID: {user_id} (类型: {type(user_id)})")

            # Get stock code (Compatible with old fields)
            stock_symbol = request.get_symbol()
            logger.info(f"📊 股票代码: {stock_symbol}")
            logger.info(f"⚙️ 分析参数: {request.parameters}")

            # Generate tasks ID
            task_id = str(uuid.uuid4())
            logger.info(f"🆔 生成任务ID: {task_id}")

            # Convert users ID
            converted_user_id = self._convert_user_id(user_id)
            logger.info(f"🔄 转换后的用户ID: {converted_user_id} (类型: {type(converted_user_id)})")

            # Create analysis tasks
            logger.info("🏗️ Start creating AnalysisTask object...")

            # Read merged system settings (ENV first → DB) , For populating models with concurrency/timeout configuration
            try:
                effective_settings = await config_provider.get_effective_system_settings()
            except Exception:
                effective_settings = {}

            # Populate the model in analysis parameters (if not provided explicitly by the request)
            params = request.parameters or AnalysisParameters()
            if not getattr(params, 'quick_analysis_model', None):
                params.quick_analysis_model = effective_settings.get("quick_analysis_model", "qwen-turbo")
            if not getattr(params, 'deep_analysis_model', None):
                params.deep_analysis_model = effective_settings.get("deep_analysis_model", "qwen-max")

            # Apply system-level concurrency and visibility timeouts (if provided)
            try:
                self.queue_service.user_concurrent_limit = int(effective_settings.get("max_concurrent_tasks", DEFAULT_USER_CONCURRENT_LIMIT))
                self.queue_service.global_concurrent_limit = int(effective_settings.get("max_concurrent_tasks", GLOBAL_CONCURRENT_LIMIT))
                self.queue_service.visibility_timeout = int(effective_settings.get("default_analysis_timeout", VISIBILITY_TIMEOUT_SECONDS))
            except Exception:
                # Just use the default value
                pass

            task = AnalysisTask(
                task_id=task_id,
                user_id=converted_user_id,
                symbol=stock_symbol,
                stock_code=stock_symbol,  # Compatible fields
                parameters=params,
                status=AnalysisStatus.PENDING
            )
            logger.info("✅ AnalysisTask Object created successfully")

            # Save task to database
            logger.info("💾 Start saving tasks to the database...")
            db = get_mongo_db()
            task_dict = task.model_dump(by_alias=True)
            logger.info(f"📄 任务字典: {task_dict}")
            await db.analysis_tasks.insert_one(task_dict)
            logger.info("✅ 任务已保存到数据库")

            # 🔥 Single stock analysis: submitted to the queue and processed by the Worker process (consistent with batch analysis)
            logger.info("🚀 Start submitting tasks to the queue...")

            # Prepare queue parameters (pass analysis parameters directly, no nesting)
            queue_params = task.parameters.dict() if task.parameters else {}

            # Add task metadata
            queue_params.update({
                "task_id": task.task_id,
                "symbol": task.symbol,
                "stock_code": task.symbol,  # Compatible fields
                "user_id": str(task.user_id),
                "created_at": task.created_at.isoformat() if task.created_at else None
            })

            # Call queue service
            await self.queue_service.enqueue_task(
                user_id=str(converted_user_id),
                symbol=stock_symbol,
                params=queue_params,
                batch_id=None,  # Single stock analysis without batches ID
                task_id=task_id  # Use generated tasks ID
            )

            logger.info(f"✅ The task has been submitted to the queue, task ID: {task_id}")
            logger.info(f"🎉 Single stock analysis task submission completed: {task_id} - {stock_symbol}")

            return {
                "task_id": task_id,
                "symbol": stock_symbol,
                "stock_code": stock_symbol,  # Compatible fields
                "status": AnalysisStatus.PENDING,
                "message": "The task has been submitted to the queue and is waiting for processing by the Worker"
            }
            
        except Exception as e:
            logger.error(f"提交单股分析任务失败: {e}")
            raise
    
    async def submit_batch_analysis(
        self, 
        user_id: str, 
        request: BatchAnalysisRequest
    ) -> Dict[str, Any]:
        """提交批量分析任务"""
        try:
            # Generate batch ID
            batch_id = str(uuid.uuid4())
            
            # Convert users ID
            converted_user_id = self._convert_user_id(user_id)

            # Read system settings, populate model parameters and apply concurrency/timeout configuration
            try:
                effective_settings = await config_provider.get_effective_system_settings()
            except Exception:
                effective_settings = {}

            params = request.parameters or AnalysisParameters()
            if not getattr(params, 'quick_analysis_model', None):
                params.quick_analysis_model = effective_settings.get("quick_analysis_model", "qwen-turbo")
            if not getattr(params, 'deep_analysis_model', None):
                params.deep_analysis_model = effective_settings.get("deep_analysis_model", "qwen-max")

            try:
                self.queue_service.user_concurrent_limit = int(effective_settings.get("max_concurrent_tasks", DEFAULT_USER_CONCURRENT_LIMIT))
                self.queue_service.global_concurrent_limit = int(effective_settings.get("max_concurrent_tasks", GLOBAL_CONCURRENT_LIMIT))
                self.queue_service.visibility_timeout = int(effective_settings.get("default_analysis_timeout", VISIBILITY_TIMEOUT_SECONDS))
            except Exception:
                pass

            # Create batch records
            # Get a list of stock symbols (Compatible with old fields)
            stock_symbols = request.get_symbols()

            batch = AnalysisBatch(
                batch_id=batch_id,
                user_id=converted_user_id,
                title=request.title,
                description=request.description,
                total_tasks=len(stock_symbols),
                parameters=params,
                status=BatchStatus.PENDING
            )

            # Create task list
            tasks = []
            for symbol in stock_symbols:
                task_id = str(uuid.uuid4())
                task = AnalysisTask(
                    task_id=task_id,
                    batch_id=batch_id,
                    user_id=converted_user_id,
                    symbol=symbol,
                    stock_code=symbol,  # Compatible fields
                    parameters=batch.parameters,
                    status=AnalysisStatus.PENDING
                )
                tasks.append(task)
            
            # Save to database
            db = get_mongo_db()
            await db.analysis_batches.insert_one(batch.dict(by_alias=True))
            await db.analysis_tasks.insert_many([task.dict(by_alias=True) for task in tasks])
            
            # Submit task to queue
            for task in tasks:
                # Prepare queue parameters (pass analysis parameters directly, no nesting)
                queue_params = task.parameters.dict() if task.parameters else {}

                # Add task metadata
                queue_params.update({
                    "task_id": task.task_id,
                    "symbol": task.symbol,
                    "stock_code": task.symbol,  # Compatible fields
                    "user_id": str(task.user_id),
                    "batch_id": task.batch_id,
                    "created_at": task.created_at.isoformat() if task.created_at else None
                })

                # Call queue service
                await self.queue_service.enqueue_task(
                    user_id=str(converted_user_id),
                    symbol=task.symbol,
                    params=queue_params,
                    batch_id=task.batch_id
                )
            
            logger.info(f"批量分析任务已提交: {batch_id} - {len(tasks)}个股票")
            
            return {
                "batch_id": batch_id,
                "total_tasks": len(tasks),
                "status": BatchStatus.PENDING,
                "message": f"已提交{len(tasks)}个分析任务到队列"
            }
            
        except Exception as e:
            logger.error(f"提交批量分析任务失败: {e}")
            raise
    
    async def execute_analysis_task(
        self,
        task: AnalysisTask,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> AnalysisResult:
        """Perform a single analysis task — Deactivated

        v3.0 The legacy engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] AnalysisService.execute_analysis_task deactivated,"
            "task_id=%s Please use UnifiedAnalysisEngine.execute_task instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
            % getattr(task, "task_id", "<unknown>")
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        try:
            logger.info(f"开始执行分析任务: {task.task_id} - {task.symbol}")
            
            # Update task status
            await self._update_task_status(task.task_id, AnalysisStatus.PROCESSING, 0)
            
            if progress_callback:
                progress_callback(10, "初始化分析引擎...")
            
            # Create complete configurations using standard configuration functions - consistent with single stock analysis
            from app.core.unified_config import unified_config

            quick_model = getattr(task.parameters, 'quick_analysis_model', None) or unified_config.get_quick_analysis_model()
            deep_model = getattr(task.parameters, 'deep_analysis_model', None) or unified_config.get_deep_analysis_model()

            # 🔧 Read the complete configuration parameters of the model from the database
            quick_model_config = None
            deep_model_config = None
            llm_configs = unified_config.get_llm_configs()

            for llm_config in llm_configs:
                if llm_config.model_name == quick_model:
                    quick_model_config = {
                        "max_tokens": llm_config.max_tokens,
                        "temperature": llm_config.temperature,
                        "timeout": llm_config.timeout,
                        "retry_times": llm_config.retry_times,
                        "api_base": llm_config.api_base
                    }
                    if getattr(llm_config, "reasoning_effort", None):
                        quick_model_config["reasoning_effort"] = llm_config.reasoning_effort

                if llm_config.model_name == deep_model:
                    deep_model_config = {
                        "max_tokens": llm_config.max_tokens,
                        "temperature": llm_config.temperature,
                        "timeout": llm_config.timeout,
                        "retry_times": llm_config.retry_times,
                        "api_base": llm_config.api_base
                    }
                    if getattr(llm_config, "reasoning_effort", None):
                        deep_model_config["reasoning_effort"] = llm_config.reasoning_effort

            # Dynamically find suppliers based on model name
            llm_provider = await get_provider_by_model_name(quick_model)

            # Create a complete configuration using standard configuration functions
            config = create_analysis_config(
                research_depth=task.parameters.research_depth,
                selected_analysts=task.parameters.selected_analysts or ["market", "fundamentals"],
                quick_model=quick_model,
                deep_model=deep_model,
                llm_provider=llm_provider,
                market_type=getattr(task.parameters, 'market_type', "A股"),
                quick_model_config=quick_model_config,  # Pass model configuration
                deep_model_config=deep_model_config     # Pass model configuration
            )
            
            if progress_callback:
                progress_callback(30, "创建分析图...")
            
            # Get TradingAgents instance
            trading_graph = self._get_trading_graph(config)
            
            if progress_callback:
                progress_callback(50, "执行股票分析...")
            
            # Perform analysis
            start_time = datetime.utcnow()
            analysis_date = task.parameters.analysis_date or datetime.now().strftime("%Y-%m-%d")
            
            # Call existing analysis methods
            from tradingagents.agents.utils.agent_context import AgentContext
            # Obtain user risk preference and inject it into AgentContext
            risk_preference = self._get_user_risk_preference(str(task.user_id))
            ctx = AgentContext(user_id=str(task.user_id), preference_id=risk_preference)
            logger.info(f"[diagnose] inject AgentContext task_id={task.task_id} user_id={task.user_id} symbol={task.symbol} date={analysis_date} risk_preference={risk_preference}")
            _, decision = trading_graph.propagate(task.symbol, analysis_date, agent_context=ctx.__dict__)
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            if progress_callback:
                progress_callback(80, "处理分析结果...")

            # Extract model information from decisions
            model_info = decision.get('model_info', 'Unknown') if isinstance(decision, dict) else 'Unknown'

            # Build results
            result = AnalysisResult(
                analysis_id=str(uuid.uuid4()),
                summary=decision.get("summary", ""),
                recommendation=decision.get("recommendation", ""),
                confidence_score=decision.get("confidence_score", 0.0),
                risk_level=decision.get("risk_level", "中等"),
                key_points=decision.get("key_points", []),
                detailed_analysis=decision,
                execution_time=execution_time,
                tokens_used=decision.get("tokens_used", 0),
                model_info=model_info  # 🔥 Add model information fields
            )

            if progress_callback:
                progress_callback(100, "研究完成")

            # Update task status
            await self._update_task_status(task.task_id, AnalysisStatus.COMPLETED, 100, result)

            # Record token usage
            try:
                # Log usage
                await self._record_token_usage(task, result, llm_provider, deep_model or quick_model)
            except Exception as e:
                logger.error(f"⚠️  Record token usage failure: {e}")

            logger.info(f"分析任务完成: {task.task_id} - 耗时{execution_time:.2f}秒")

            return result
            
        except Exception as e:
            logger.error(f"执行分析任务失败: {task.task_id} - {e}")
            
            # Update task status is failed
            error_result = AnalysisResult(error_message=str(e))
            await self._update_task_status(task.task_id, AnalysisStatus.FAILED, 0, error_result)
            
            raise
    
    async def _update_task_status(
        self,
        task_id: str,
        status: AnalysisStatus,
        progress: int,
        result: Optional[AnalysisResult] = None,
    ) -> None:
        """Update task status (delegate to split utility function)"""
        try:
            await perform_update_task_status(task_id, status, progress, result)
        except Exception as e:
            logger.error(f"更新任务状态失败: {task_id} - {e}")

    async def _update_task_status_with_tracker(
        self,
        task_id: str,
        status: AnalysisStatus,
        progress_tracker: RedisProgressTracker,
        result: Optional[AnalysisResult] = None,
    ) -> None:
        """Update task status using progress tracker (delegate to split utility function)"""
        try:
            await perform_update_task_status_with_tracker(task_id, status, progress_tracker, result)
        except Exception as e:
            logger.error(f"更新任务状态失败: {task_id} - {e}")

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        try:
            # First check the in-memory progress tracker
            if task_id in self._progress_trackers:
                progress_tracker = self._progress_trackers[task_id]
                progress_data = progress_tracker.to_dict()

                # Get basic task information from the database
                db = get_mongo_db()
                task = await db.analysis_tasks.find_one({"task_id": task_id})

                if task:
                    # Merge database information and progress tracker information
                    return {
                        "task_id": task_id,
                        "user_id": task.get("user_id"),
                        "symbol": task.get("stock_symbol") or task.get("symbol"),
                        "stock_code": task.get("stock_symbol") or task.get("symbol"),  # Compatible fields
                        "status": progress_data["status"],
                        "progress": progress_data["progress"],
                        "current_step": progress_data["current_step"],
                        "message": progress_data["message"],
                        "elapsed_time": progress_data["elapsed_time"],
                        "remaining_time": progress_data["remaining_time"],
                        "estimated_total_time": progress_data.get("estimated_total_time", 0),
                        "steps": progress_data["steps"],
                        "start_time": progress_data["start_time"],
                        "end_time": None,
                        "last_update": progress_data["last_update"],
                        "parameters": task.get("parameters", {}),
                        "execution_time": None,
                        "tokens_used": None,
                        "result_data": task.get("result"),
                        "error_message": None
                    }

            # Get from Redis cache
            redis_service = get_redis_service()
            progress_key = RedisKeys.TASK_PROGRESS.format(task_id=task_id)
            cached_status = await redis_service.get_json(progress_key)

            if cached_status:
                return cached_status

            # Get from database
            db = get_mongo_db()
            task = await db.analysis_tasks.find_one({"task_id": task_id})

            if task:
                # Calculate elapsed time
                elapsed_time = 0
                remaining_time = 0
                estimated_total_time = 0

                if task.get("started_at"):
                    from datetime import datetime
                    start_time = task.get("started_at")
                    if task.get("completed_at"):
                        # Task completed
                        elapsed_time = (task.get("completed_at") - start_time).total_seconds()
                        estimated_total_time = elapsed_time  # The total time for completed tasks is the elapsed time
                        remaining_time = 0
                    else:
                        # Task in progress
                        elapsed_time = (datetime.utcnow() - start_time).total_seconds()

                        # Use the estimated duration of the task, or use the default (5 minutes) if not available
                        estimated_total_time = task.get("estimated_duration", 300)

                        # Estimated remaining = Estimated total time - elapsed time
                        remaining_time = max(0, estimated_total_time - elapsed_time)

                return {
                    "task_id": task_id,
                    "status": task.get("status"),
                    "progress": task.get("progress", 0),
                    "current_step": task.get("current_step", ""),
                    "message": task.get("message", ""),
                    "elapsed_time": elapsed_time,
                    "remaining_time": remaining_time,
                    "estimated_total_time": estimated_total_time,
                    "start_time": task.get("started_at").isoformat() if task.get("started_at") else None,
                    "updated_at": task.get("updated_at", "").isoformat() if task.get("updated_at") else None,
                    "result_data": task.get("result")
                }

            return None

        except Exception as e:
            logger.error(f"获取任务状态失败: {task_id} - {e}")
            return None
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            # Update task status
            await self._update_task_status(task_id, AnalysisStatus.CANCELLED, 0)
            
            # Remove from queue (if still in queue)
            await self.queue_service.remove_task(task_id)
            
            logger.info(f"任务已取消: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"取消任务失败: {task_id} - {e}")
            return False

    async def _record_token_usage(
        self,
        task: AnalysisTask,
        result: AnalysisResult,
        provider: str,
        model_name: str
    ):
        """Record token usage"""
        try:
            # Extract token usage information from the results
            # Note: Here you need to get the actual token usage from the LLM response
            # Currently using estimates
            input_tokens = result.tokens_used // 2 if result.tokens_used > 0 else 0
            output_tokens = result.tokens_used - input_tokens if result.tokens_used > 0 else 0

            # If there is no token usage information, use the default estimate
            if result.tokens_used == 0:
                # Estimate based on analysis type
                input_tokens = 2000  # Default input token
                output_tokens = 1000  # Default output token

            # Get model price configuration
            from app.services.config_service import config_service
            config = await config_service.get_system_config()

            # Find the corresponding LLM configuration
            llm_config = None
            if config and config.llm_configs:
                for cfg in config.llm_configs:
                    if cfg.provider == provider and cfg.model_name == model_name:
                        llm_config = cfg
                        break

            # Calculate cost
            cost = 0.0
            currency = "CNY"  # Default currency unit
            if llm_config:
                input_price = llm_config.input_price_per_1k or 0.0
                output_price = llm_config.output_price_per_1k or 0.0
                cost = (input_tokens / 1000 * input_price) + (output_tokens / 1000 * output_price)
                currency = llm_config.currency or "CNY"

            # Create usage record
            usage_record = UsageRecord(
                timestamp=datetime.now().isoformat(),
                provider=provider,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                currency=currency,
                session_id=task.task_id,
                analysis_type="stock_analysis",
                stock_code=task.symbol
            )

            # Save to database
            success = await self.usage_service.add_usage_record(usage_record)

            if success:
                logger.info(f"💰 记录使用成本: {provider}/{model_name} - ¥{cost:.4f}")
            else:
                logger.warning("⚠️  记录使用成本失败")

        except Exception as e:
            logger.error(f"❌ Record token usage failure: {e}")


# Global Analysis Service Instance (Lazy Initialization)
analysis_service: Optional[AnalysisService] = None


def get_analysis_service() -> AnalysisService:
    """Get an Analysis Services instance (lazy initialization)"""
    global analysis_service
    if analysis_service is None:
        analysis_service = AnalysisService()
    return analysis_service

# === simple_analysis_service.py ===
"""
Simplified stock analysis service
Directly call existing TradingAgents analysis functions
"""

import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
import sys

# Add project root directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Initialize TradingAgents log system
from tradingagents.utils.logging_init import init_logging
init_logging()

try:
    from tradingagents.graph.trading_graph import TradingAgentsGraph
except ImportError:
    TradingAgentsGraph = None
from tradingagents.default_config import DEFAULT_CONFIG
from app.models.analysis import (
    AnalysisTask, AnalysisStatus, SingleAnalysisRequest, AnalysisParameters
)
from app.models.user import PyObjectId
from app.models.notification import NotificationCreate
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
from app.core.database import get_mongo_db
try:
    from app.services.config_service import ConfigService
except ImportError:
    ConfigService = None
try:
    from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
except ImportError:
    get_memory_state_manager = None; TaskStatus = None

ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")

# Research depth level → Volcano Ark reasoning model thinking budget (reasoning_effort seven levels: none/minimal/low/medium/high/xhigh/max)
# Gear mapping only as default: reasoning_effort explicitly set in DB model configuration takes precedence (see trading_graph merge logic)
RESEARCH_DEPTH_REASONING_EFFORT = {
    "快速": "minimal",
    "基础": "low",
    "标准": "medium",
    "深度": "high",
    "全面": "xhigh",
}

# Obtain basic stock information (used to supplement the display name)
try:
    from tradingagents.dataflows.data_source_manager import get_data_source_manager
    _data_source_manager = get_data_source_manager()
    def _get_stock_info_safe(stock_code: str):
        """Secure encapsulation of obtaining basic stock information"""
        return _data_source_manager.get_stock_basic_info(stock_code)
except Exception:
    _get_stock_info_safe = None

try:
    from tradingagents.config.database_manager import get_mongodb_client, get_database_manager
except Exception:
    get_mongodb_client = None
    get_database_manager = None

# Setup log
logger = logging.getLogger("app.services.simple_analysis_service")

# Configure service instance
config_service = ConfigService()


def _simple_analysis_service_is_cn_etf_symbol(code: Optional[str]) -> bool:
    code_str = str(code or "").strip()
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


def _get_cached_security_name(code: Optional[str]) -> Optional[str]:
    if not code or get_mongodb_client is None:
        return None

    code_str = str(code).strip().zfill(6)

    try:
        client = get_mongodb_client()
        if not client:
            return None

        db_name = "tradingagents"
        if get_database_manager is not None:
            try:
                db_name = get_database_manager().mongodb_config.get("database", "tradingagents")
            except Exception:
                pass

        db = client[db_name]

        if _simple_analysis_service_is_cn_etf_symbol(code_str):
            doc = db["etf_basic_info"].find_one(
                {"code": code_str},
                {"name": 1, "fund_name": 1, "etf_name": 1, "symbol": 1, "_id": 0}
            )
            if doc:
                return doc.get("name") or doc.get("fund_name") or doc.get("etf_name")

        doc = db["stock_basic_info"].find_one(
            {"$or": [{"code": code_str}, {"symbol": code_str}]},
            {"name": 1, "stock_name": 1, "_id": 0}
        )
        if doc:
            return doc.get("name") or doc.get("stock_name")
    except Exception as e:
        logger.debug(f"Failed to read cache name (ignored): {code_str} - {e}")

    return None


async def get_provider_by_model_name(model_name: str, preferred_provider: Optional[str] = None) -> str:
    """
    Find the corresponding supplier from the database configuration based on the model name (asynchronous version)

    Args:
        model_name: Model name, such as 'qwen-turbo', 'gpt-4' Wait

    Returns:
        str: Supplier name, e.g. 'dashscope', 'openai' Wait
    """
    try:
        # Get system configuration from configuration service
        system_config = await config_service.get_system_config()
        if not system_config or not system_config.llm_configs:
            logger.warning("⚠️ System configuration is empty, using default vendor mapping")
            return _get_default_provider_by_model(model_name)

        normalized_provider = str(preferred_provider or "").strip().lower()

        # Find matching model in LLM configuration
        for llm_config in system_config.llm_configs:
            if llm_config.model_name != model_name:
                continue
            provider = llm_config.provider.value if hasattr(llm_config.provider, 'value') else str(llm_config.provider)
            if normalized_provider and str(provider).lower() != normalized_provider:
                continue
            logger.info(f"✅ 从数据库找到模型 {model_name} 的供应商: {provider}")
            return provider

        # If not found in database, use default mapping
        logger.warning(f"⚠️ 数据库中未找到模型 {model_name}，使用默认映射")
        return _get_default_provider_by_model(model_name)

    except Exception as e:
        logger.error(f"❌ 查找模型供应商失败: {e}")
        return _get_default_provider_by_model(model_name)


def get_provider_by_model_name_sync(model_name: str, preferred_provider: Optional[str] = None) -> str:
    """
    Find the corresponding supplier from the database configuration based on the model name (synchronized version)

    Args:
        model_name: Model name, such as 'qwen-turbo', 'gpt-4' Wait

    Returns:
        str: Supplier name, e.g. 'dashscope', 'openai' Wait
    """
    provider_info = get_provider_and_url_by_model_sync(model_name, preferred_provider=preferred_provider)
    return provider_info["provider"]


def get_provider_and_url_by_model_sync(
    model_name: str,
    preferred_provider: Optional[str] = None,
    preferred_config_id: Optional[str] = None,
) -> dict:
    """
    Find the corresponding vendor and API URL (sync version) from the database configuration based on the model name

    Args:
        model_name: Model name, such as 'qwen-turbo', 'gpt-4' Wait

    Returns:
        dict: {"provider": "google", "backend_url": "https://...", "api_key": "xxx"}
    """
    try:
        # Direct query using synchronous MongoDB client
        from pymongo import MongoClient
        from app.core.config import settings
        import os

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]

        # Query the latest active configuration
        configs_collection = db.system_configs
        doc = configs_collection.find_one({"is_active": True}, sort=[("version", -1)])

        # 🔧 Parse old format "provider::model_name" (Such as jdyun::GLM-5) 
        if "::" in model_name:
            parsed_provider, parsed_model = model_name.split("::", 1)
            if not preferred_provider:
                preferred_provider = parsed_provider
            model_name = parsed_model
            logger.info(f"🔧 [Synchronous query] Parse old format model names: {parsed_provider}::{parsed_model} → provider={preferred_provider}, model={model_name}")

        # 🔧 Jingdong Cloud mode: directly use environment variable configuration and skip database query
        from app.core.jdyun import (
            is_jdyun_mode, get_jdyun_api_base, get_jdyun_api_key,
            get_jdyun_default_model, JDYUN_PROVIDER_NAME,
        )
        if is_jdyun_mode():
            api_base = get_jdyun_api_base()
            api_key = get_jdyun_api_key()
            if api_base and api_key:
                effective_model = model_name if model_name else get_jdyun_default_model()
                logger.info(f"🔧 [Jingdong cloud model] Use JD Cloud configuration: model={effective_model}, api_base={api_base}")
                return {
                    "provider": JDYUN_PROVIDER_NAME,
                    "backend_url": api_base,
                    "api_key": api_key,
                }

        normalized_provider = str(preferred_provider or "").strip().lower()
        normalized_config_id = str(preferred_config_id or "").strip()

        def _build_provider_result(config_dict: dict) -> dict:
            provider = str(config_dict.get("provider") or "").strip().lower()
            api_base = config_dict.get("api_base")
            model_api_key = config_dict.get("api_key")

            providers_collection = db.llm_providers
            provider_doc = providers_collection.find_one({"name": provider})

            from app.utils.api_key_utils import is_valid_api_key

            api_key = None
            api_key_source = None
            logger.info(f"🔍 [同步查询] 模型 {config_dict.get('model_name')} API Key 获取流程:")

            if provider_doc and provider_doc.get("api_key"):
                provider_api_key = provider_doc["api_key"]
                logger.info(f"   - in factory configuration api_key: {'valuable' if provider_api_key else 'empty'}")
                if is_valid_api_key(provider_api_key):
                    api_key = provider_api_key.strip()
                    api_key_source = "厂家配置"
                    logger.info("✅ [Synchronous query] ✅ Use the API Key configured by the manufacturer (priority 1)")
                else:
                    logger.warning("⚠️ [Synchronous query] The API Key configured by the manufacturer is invalid (may be a placeholder or null value)")
            else:
                logger.info(f"   - 厂家配置: {'存在但无API Key' if provider_doc else '不存在'}")

            if not api_key:
                logger.info(f"   - in model configuration api_key: {'valuable' if model_api_key else 'empty'}")
                if is_valid_api_key(model_api_key):
                    api_key = model_api_key.strip()
                    api_key_source = "模型配置"
                    logger.info("✅ [Synchronous query] ✅ Use the API Key configured by the model (Priority 2, alternative)")

            if not api_key:
                env_api_key = _get_env_api_key_for_provider(provider)
                logger.info(f"   - in environment variables api_key: {'valuable' if env_api_key else 'empty'}")
                if env_api_key:
                    api_key = env_api_key
                    api_key_source = "环境变量"
                    logger.info("✅ [Synchronous query] ✅ API Key using environment variables (Priority 3)")
                else:
                    logger.warning(f"⚠️ [Synchronous query] ❌ not found {provider} API Key (no manufacturer configuration, model configuration, environment variables)")

            if api_key_source:
                logger.info(f"✅ [Synchronous query] The final API Key source used: {api_key_source}")

            if api_base:
                backend_url = api_base
                logger.info(f"✅ [同步查询] 模型 {config_dict.get('model_name')} 使用自定义 API: {api_base}")
            elif provider_doc and provider_doc.get("default_base_url"):
                backend_url = provider_doc["default_base_url"]
                logger.info(f"✅ [同步查询] 模型 {config_dict.get('model_name')} 使用厂家默认 API: {backend_url}")
            else:
                backend_url = _get_default_backend_url(provider)
                logger.warning(f"⚠️ [同步查询] 厂家 {provider} 没有配置 default_base_url，使用硬编码默认值")

            return {
                "provider": provider,
                "backend_url": backend_url,
                "api_key": api_key,
            }

        if doc and "llm_configs" in doc:
            llm_configs = doc["llm_configs"]
            fallback_config = None

            if normalized_config_id:
                exact_config = next(
                    (
                        config_dict
                        for config_dict in llm_configs
                        if str(config_dict.get("config_id") or "").strip() == normalized_config_id
                        and config_dict.get("enabled", True)
                    ),
                    None,
                )
                if exact_config is not None:
                    result = _build_provider_result(exact_config)
                    client.close()
                    return result

            for config_dict in llm_configs:
                if config_dict.get("model_name") != model_name:
                    continue

                provider = str(config_dict.get("provider") or "").strip().lower()
                if fallback_config is None:
                    fallback_config = config_dict
                if normalized_provider and provider != normalized_provider:
                    continue
                result = _build_provider_result(config_dict)
                client.close()
                return result

            if fallback_config is not None:
                logger.warning(f"⚠️ [同步查询] 模型 {model_name} 未找到 provider={normalized_provider or '-'} 的精确配置，回退到同名模型的首个配置")
                result = _build_provider_result(fallback_config)
                client.close()
                return result

        client.close()

        # If the model configuration is not found in the database, the default mapping is used
        logger.warning(f"⚠️ [Synchronous query] Model not found in database {model_name}, Use default mapping")
        provider = _get_default_provider_by_model(model_name)

        # Try to get default_base_url and API Key
        try:
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]
            providers_collection = db.llm_providers
            provider_doc = providers_collection.find_one({"name": provider})

            backend_url = _get_default_backend_url(provider)
            api_key = None

            # 🔥 Import API Key verification function
            from app.utils.api_key_utils import is_valid_api_key
            
            if provider_doc:
                if provider_doc.get("default_base_url"):
                    backend_url = provider_doc["default_base_url"]
                    logger.info(f"✅ [Synchronous query] Use manufacturer {provider} of default_base_url: {backend_url}")

                if provider_doc.get("api_key"):
                    provider_api_key = provider_doc["api_key"]
                    # 🔥 Use is_valid_api_key to verify factory configuration API Key
                    if is_valid_api_key(provider_api_key):
                        api_key = provider_api_key.strip()
                        logger.info(f"✅ [同步查询] 使用厂家 {provider} 的 API Key")

            # If there is no API Key in the manufacturer configuration, try to obtain it from the environment variable
            if not api_key:
                api_key = _get_env_api_key_for_provider(provider)
                if api_key:
                    logger.info("✅ [Synchronous query] using environment variables API Key")

            client.close()
            return {
                "provider": provider,
                "backend_url": backend_url,
                "api_key": api_key
            }
        except Exception as e:
            logger.warning(f"⚠️ [Synchronous query] Unable to query manufacturer configuration: {e}")

        # Finally fallback to hardcoded default URLs and environment variables API Key
        return {
            "provider": provider,
            "backend_url": _get_default_backend_url(provider),
            "api_key": _get_env_api_key_for_provider(provider)
        }

    except Exception as e:
        logger.error(f"❌ [Synchronous query] Failed to find model supplier: {e}")
        provider = _get_default_provider_by_model(model_name)

        # Try to get default_base_url and API Key
        try:
            from pymongo import MongoClient
            from app.core.config import settings

            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]
            providers_collection = db.llm_providers
            provider_doc = providers_collection.find_one({"name": provider})

            backend_url = _get_default_backend_url(provider)
            api_key = None

            # 🔥 Import API Key verification function
            from app.utils.api_key_utils import is_valid_api_key
            
            if provider_doc:
                if provider_doc.get("default_base_url"):
                    backend_url = provider_doc["default_base_url"]
                    logger.info(f"✅ [Synchronous query] Use manufacturer {provider} of default_base_url: {backend_url}")

                if provider_doc.get("api_key"):
                    provider_api_key = provider_doc["api_key"]
                    # 🔥 Use is_valid_api_key to verify factory configuration API Key
                    if is_valid_api_key(provider_api_key):
                        api_key = provider_api_key.strip()
                        logger.info(f"✅ [同步查询] 使用厂家 {provider} 的 API Key")

            # If there is no API Key in the manufacturer configuration, try to obtain it from the environment variable
            if not api_key:
                api_key = _get_env_api_key_for_provider(provider)

            client.close()
            return {
                "provider": provider,
                "backend_url": backend_url,
                "api_key": api_key
            }
        except Exception as e2:
            logger.warning(f"⚠️ [Synchronous query] Unable to query manufacturer configuration: {e2}")

        # Finally fallback to hardcoded default URLs and environment variables API Key
        return {
            "provider": provider,
            "backend_url": _get_default_backend_url(provider),
            "api_key": _get_env_api_key_for_provider(provider)
        }


def _get_env_api_key_for_provider(provider: str) -> str:
    """
    Get the specified vendor from an environment variable API Key

    Args:
        provider: Supplier name, e.g. 'google', 'dashscope' Wait

    Returns:
        str: API Key, Return if not found None
    """
    import os

    env_key_map = {
        "google": "GOOGLE_API_KEY",
        "dashscope": "DASHSCOPE_API_KEY",
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
        "qianfan": "QIANFAN_API_KEY",
        "302ai": "AI302_API_KEY",
    }

    env_key_name = env_key_map.get(provider.lower())
    if env_key_name:
        api_key = os.getenv(env_key_name)
        # 🔥 Use is_valid_api_key to verify the environment variable API Key
        from app.utils.api_key_utils import is_valid_api_key
        if is_valid_api_key(api_key):
            return api_key.strip()

    return None


def _get_default_backend_url(provider: str) -> str:
    """
    Returns the default based on supplier name backend_url

    Args:
        provider: Supplier name, e.g. 'google', 'dashscope' Wait

    Returns:
        str: default backend_url
    """
    default_urls = {
        "google": "https://generativelanguage.googleapis.com/v1beta",
        "dashscope": "https://dashscope.aliyuncs.com/api/v1",
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com",
        "anthropic": "https://api.anthropic.com",
        "openrouter": "https://openrouter.ai/api/v1",
        "qianfan": "https://qianfan.baidubce.com/v2",
        "302ai": "https://api.302.ai/v1",
    }

    url = default_urls.get(provider, "https://dashscope.aliyuncs.com/compatible-mode/v1")
    logger.info(f"🔧 [默认URL] {provider} -> {url}")
    return url


def _get_default_provider_by_model(model_name: str) -> str:
    """
    Returns the default supplier mapping based on model name
    This is a fallback solution used when a database query fails
    """
    # Default mapping of model names to vendors
    # ⚠️ Note: This is only a fallback solution and should be obtained from the database configuration first.
    model_provider_map = {
        # Ali Bailian (DashScope)
        'qwen-turbo': 'dashscope',
        'qwen-plus': 'dashscope',
        'qwen-max': 'dashscope',
        'qwen-plus-latest': 'dashscope',
        'qwen-max-longcontext': 'dashscope',

        # OpenAI
        'gpt-3.5-turbo': 'openai',
        'gpt-4': 'openai',
        'gpt-4-turbo': 'openai',
        'gpt-4o': 'openai',
        'gpt-4o-mini': 'openai',

        # Google
        'gemini-pro': 'google',
        'gemini-2.0-flash': 'google',
        'gemini-2.0-flash-thinking-exp': 'google',

        # DeepSeek
        'deepseek-chat': 'deepseek',
        'deepseek-coder': 'deepseek',

        # Wisdom spectrum AI
        'glm-4': 'zhipu',
        'glm-3-turbo': 'zhipu',
        'chatglm3-6b': 'zhipu'
    }

    provider = model_provider_map.get(model_name, 'dashscope')  # By default, Ali Bailian is used.
    logger.info(f"🔧 使用默认映射: {model_name} -> {provider}")
    return provider


def _load_model_config_from_db(model_name: str) -> dict:
    """
    Read model configuration parameters from the database (max_tokens, temperature, timeout, reasoning_effort etc.)

    Args:
        model_name: Model name

    Returns:
        dict: Model configuration dictionary, such as {"max_tokens": 4000, "temperature": 0.7, "reasoning_effort": "low"}
    """
    try:
        from pymongo import MongoClient
        from app.core.config import settings

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]
        configs_collection = db.system_configs
        doc = configs_collection.find_one({"is_active": True}, sort=[("version", -1)])

        if doc and "llm_configs" in doc:
            for config_dict in doc["llm_configs"]:
                if config_dict.get("model_name") == model_name:
                    result = {
                        "max_tokens": config_dict.get("max_tokens", 4000),
                        "temperature": config_dict.get("temperature", 0.7),
                        "timeout": config_dict.get("timeout", 180),
                        "retry_times": config_dict.get("retry_times", 3),
                        "api_base": config_dict.get("api_base"),
                    }
                    # 🔧 Volcano Ark inference model support reasoning_effort
                    if config_dict.get("reasoning_effort"):
                        result["reasoning_effort"] = config_dict["reasoning_effort"]
                        logger.info(f"🔧 [模型配置] {model_name} reasoning_effort={result['reasoning_effort']}")
                    else:
                        logger.info(f"🔧 [模型配置] {model_name} reasoning_effort 未设置")
                    client.close()
                    return result

        client.close()
        return {}
    except Exception as e:
        logger.warning(f"⚠️ 读取模型配置失败: {e}")
        return {}


def create_analysis_config(
    research_depth,  # Support numbers(1-5)or string("fast", "Standard", "Depth")
    selected_analysts: list,
    quick_model: str,
    deep_model: str,
    llm_provider: str,
    market_type: str = "A股",
    quick_model_config: dict = None,  # New: Full configuration of fast models
    deep_model_config: dict = None    # New: Complete configuration of deep models
) -> dict:
    """
    Create analysis configuration - supports numeric grades and Chinese grades

    Args:
        research_depth: Research depth, supporting numbers(1-5)or chinese("fast", "Basics", "Standard", "Depth", "Comprehensive")
        selected_analysts: List of selected analysts
        quick_model: Quickly analyze models
        deep_model: Deep analysis model
        llm_provider: LLM supplier
        market_type: market type
        quick_model_config: Complete configuration of fast model (including max_tokens, temperature, timeout, etc.)
        deep_model_config: Complete configuration of the deep model (including max_tokens, temperature, timeout, etc.)

    Returns:
        dict: Complete analysis configuration
    """
    # 🔍 [Debugging] Record the original parameters received
    logger.info(f"🔍 [配置创建] 接收到的research_depth参数: {research_depth} (类型: {type(research_depth).__name__})")

    # Mapping of numerical grades to Chinese grades
    numeric_to_chinese = {
        1: "快速",
        2: "基础",
        3: "标准",
        4: "深度",
        5: "全面"
    }

    # Standardization Research Depth: Support Numeric Input
    if isinstance(research_depth, (int, float)):
        research_depth = int(research_depth)
        if research_depth in numeric_to_chinese:
            chinese_depth = numeric_to_chinese[research_depth]
            logger.info(f"🔢 [等级转换] 数字等级 {research_depth} → 中文等级 '{chinese_depth}'")
            research_depth = chinese_depth
        else:
            logger.warning(f"⚠️ 无效的数字等级: {research_depth}，使用默认标准分析")
            research_depth = "标准"
    elif isinstance(research_depth, str):
        # If it is a number in string form, convert it to an integer
        if research_depth.isdigit():
            numeric_level = int(research_depth)
            if numeric_level in numeric_to_chinese:
                chinese_depth = numeric_to_chinese[numeric_level]
                logger.info(f"🔢 [等级转换] 字符串数字 '{research_depth}' → 中文等级 '{chinese_depth}'")
                research_depth = chinese_depth
            else:
                logger.warning(f"⚠️ Invalid string numeric level: {research_depth}, Analyze using default criteria")
                research_depth = "标准"
        # If you are already at Chinese level, use it directly
        elif research_depth in ["快速", "基础", "标准", "深度", "全面"]:
            logger.info(f"📝 [Level confirmation] Use Chinese level: '{research_depth}'")
        else:
            logger.warning(f"⚠️ 未知的研究深度: {research_depth}，使用默认标准分析")
            research_depth = "标准"
    else:
        logger.warning(f"⚠️ Invalid research depth type: {type(research_depth)}, Analyze using default criteria")
        research_depth = "标准"

    # Starting from DEFAULT_CONFIG, completely copy the logic of the web directory
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = llm_provider
    config["deep_think_llm"] = deep_model
    config["quick_think_llm"] = quick_model

    # Adjust configuration based on research depth - 5 levels supported (consistent with web interface)
    if research_depth == "快速":
        # 1 Level - Quick Analysis
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 1
        config["memory_enabled"] = False  # Disable memory for speed
        config["online_tools"] = True  # Use online tools uniformly to avoid various problems with offline tools
        logger.info(f"🔧 [1级-快速分析] {market_type}使用统一工具，确保数据源正确和稳定性")
        logger.info(f"🔧 [1 Level-Quick Analysis] Using user-configured models: quick={quick_model}, deep={deep_model}")

    elif research_depth == "基础":
        # 2 Level - Basic Analysis
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 1
        config["memory_enabled"] = True
        config["online_tools"] = True
        logger.info(f"🔧 [2级-基础分析] {market_type}使用在线工具，获取最新数据")
        logger.info(f"🔧 [2 Level-Basic Analysis] Using user-configured models: quick={quick_model}, deep={deep_model}")

    elif research_depth == "标准":
        # 3 Level - Standard Analysis (recommended)
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 2
        config["memory_enabled"] = True
        config["online_tools"] = True
        logger.info(f"🔧 [3级-标准分析] {market_type}平衡速度和质量（推荐）")
        logger.info(f"🔧 [3 Level-Standard Analysis] Using user-configured models: quick={quick_model}, deep={deep_model}")

    elif research_depth == "深度":
        # 4 Level - In-Depth Analysis
        config["max_debate_rounds"] = 2
        config["max_risk_discuss_rounds"] = 2
        config["memory_enabled"] = True
        config["online_tools"] = True
        logger.info(f"🔧 [4级-深度分析] {market_type}多轮辩论，深度研究")
        logger.info(f"🔧 [4 Level-depth analysis] Using user-configured models: quick={quick_model}, deep={deep_model}")

    elif research_depth == "全面":
        # 5 Level - Comprehensive Analysis
        config["max_debate_rounds"] = 3
        config["max_risk_discuss_rounds"] = 3
        config["memory_enabled"] = True
        config["online_tools"] = True
        logger.info(f"🔧 [5级-全面分析] {market_type}最全面的分析，最高质量")
        logger.info(f"🔧 [5 Level - Comprehensive Analysis] Using user-configured models: quick={quick_model}, deep={deep_model}")

    else:
        # Use standard analysis by default
        logger.warning(f"⚠️ 未知的研究深度: {research_depth}，使用标准分析")
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 2
        config["memory_enabled"] = True
        config["online_tools"] = True

    # 🔧 A1: Research depth level → reasoning_effort Think about budget defaults
    # Only the Volcano Ark inference model takes effect when injected into the graph layer; when the DB model configuration is explicitly set, the DB shall prevail.
    config["depth_reasoning_effort"] = RESEARCH_DEPTH_REASONING_EFFORT.get(research_depth, "medium")

    # 🔧 Get backend_url and API Key (Priority: Model Configuration > Factory configuration > environment variables)
    try:
        # 1️⃣ Priority is obtained from the database (including the api_base and API Key of the model configuration and the manufacturer's default_base_url and API Key)
        quick_provider_info = get_provider_and_url_by_model_sync(quick_model)
        deep_provider_info = get_provider_and_url_by_model_sync(deep_model)

        config["backend_url"] = quick_provider_info["backend_url"]
        config["quick_api_key"] = quick_provider_info.get("api_key")  # 🔥 Save quick model API Key
        config["deep_api_key"] = deep_provider_info.get("api_key")    # 🔥 Save the depth model API Key

        logger.info(f"✅ Configured using database backend_url: {quick_provider_info['backend_url']}")
        logger.info(f"   来源: 模型 {quick_model} 的配置或厂家 {quick_provider_info['provider']} 的默认地址")
        logger.info(f"🔑 quick model API Key: {'configured' if config['quick_api_key'] else 'Not configured (environment variables will be used)'}")
        logger.info(f"🔑 deep model API Key: {'configured' if config['deep_api_key'] else 'Not configured (environment variables will be used)'}")
    except Exception as e:
        logger.warning(f"⚠️  Unable to get backend_url and API Key: {e}")
        # 2️⃣ Fallback to hardcoded default URL, API Key will be read from environment variables
        if llm_provider == "dashscope":
            config["backend_url"] = "https://dashscope.aliyuncs.com/api/v1"
        elif llm_provider == "deepseek":
            config["backend_url"] = "https://api.deepseek.com"
        elif llm_provider == "openai":
            config["backend_url"] = "https://api.openai.com/v1"
        elif llm_provider == "google":
            config["backend_url"] = "https://generativelanguage.googleapis.com/v1beta"
        elif llm_provider == "qianfan":
            config["backend_url"] = "https://aip.baidubce.com"
        else:
            # 🔧 Unknown manufacturer, try to get the manufacturer's information from the database default_base_url
            logger.warning(f"⚠️  未知厂家 {llm_provider}，尝试从数据库获取配置")
            try:
                from pymongo import MongoClient
                from app.core.config import settings

                client = MongoClient(settings.MONGO_URI)
                db = client[settings.MONGO_DB]
                providers_collection = db.llm_providers
                provider_doc = providers_collection.find_one({"name": llm_provider})

                if provider_doc and provider_doc.get("default_base_url"):
                    config["backend_url"] = provider_doc["default_base_url"]
                    logger.info(f"✅ Get custom manufacturer from database {llm_provider} of backend_url: {config['backend_url']}")
                else:
                    # If it's not in the database either, use the OpenAI compatible format as a last resort fallback
                    config["backend_url"] = "https://api.openai.com/v1"
                    logger.warning(f"⚠️  Manufacturer not found in database {llm_provider} configuration, using the default OpenAI endpoint")

                client.close()
            except Exception as e2:
                logger.error(f"❌ 查询数据库失败: {e2}，使用默认 OpenAI 端点")
                config["backend_url"] = "https://api.openai.com/v1"

        logger.info(f"⚠️  Use fallback backend_url: {config['backend_url']}")

    # Add analyst configuration
    config["selected_analysts"] = selected_analysts
    config["debug"] = False

    # 🔧 Add research_depth to the configuration to enable tool functions to access analysis-level information
    config["research_depth"] = research_depth

    # 🔧 Add model configuration parameters (max_tokens, temperature, timeout, retry_times)
    if quick_model_config:
        config["quick_model_config"] = quick_model_config
        logger.info(f"🔧 [Quick model configuration] max_tokens={quick_model_config.get('max_tokens')}, "
                   f"temperature={quick_model_config.get('temperature')}, "
                   f"timeout={quick_model_config.get('timeout')}, "
                   f"retry_times={quick_model_config.get('retry_times')}")

    if deep_model_config:
        config["deep_model_config"] = deep_model_config
        logger.info(f"🔧 [Deep model configuration] max_tokens={deep_model_config.get('max_tokens')}, "
                   f"temperature={deep_model_config.get('temperature')}, "
                   f"timeout={deep_model_config.get('timeout')}, "
                   f"retry_times={deep_model_config.get('retry_times')}")

    logger.info("📋 ========== Creating analysis configuration is complete ==========")
    logger.info(f"   🎯 研究深度: {research_depth}")
    logger.info(f"   🔥 辩论轮次: {config['max_debate_rounds']}")
    logger.info(f"   🧠 推理思考预算: {config['depth_reasoning_effort']}（火山方舟推理模型生效，DB显式配置优先）")
    logger.info(f"   ⚖️ 风险讨论轮次: {config['max_risk_discuss_rounds']}")
    logger.info(f"   💾 记忆功能: {config['memory_enabled']}")
    logger.info(f"   🌐 在线工具: {config['online_tools']}")
    logger.info(f"   🤖 LLM供应商: {llm_provider}")
    logger.info(f"   ⚡ 快速模型: {config['quick_think_llm']}")
    logger.info(f"   🧠 深度模型: {config['deep_think_llm']}")
    logger.info("📋 ========================================")

    return config


class SimpleAnalysisService:
    """简化的股票分析服务类"""

    def __init__(self):
        self._trading_graph_cache = {}
        self.memory_manager = get_memory_state_manager()

        # Progress tracker cache
        self._progress_trackers: Dict[str, RedisProgressTracker] = {}

        # 🔧 Create a shared thread pool to support concurrent execution of multiple analysis tasks
        # By default, up to 3 analysis tasks can be executed simultaneously (can be adjusted according to server resources)
        import concurrent.futures
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)

        logger.info(f"🔧 [Service initialization] SimpleAnalysisService Example ID: {id(self)}")
        logger.info(f"🔧 [Service initialization] Memory manager instance ID: {id(self.memory_manager)}")
        logger.info("🔧 [Service initialization] Maximum number of concurrent thread pools: 3")

        # Set up the WebSocket manager
        # Simple stock name caching to reduce duplicate queries
        self._stock_name_cache: Dict[str, str] = {}

        # Set up the WebSocket manager
        try:
            from app.services.websocket_manager import get_websocket_manager
            self.memory_manager.set_websocket_manager(get_websocket_manager())
        except ImportError:
            logger.warning("⚠️ WebSocket Manager is unavailable")

    async def _update_progress_async(self, task_id: str, progress: int, message: str):
        """Asynchronous update progress (memory and MongoDB)"""
        try:
            # Update memory
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=progress,
                message=message,
                current_step=message
            )

            # update MongoDB
            from app.core.database import get_mongo_db
            from datetime import datetime
            db = get_mongo_db()
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "progress": progress,
                        "current_step": message,
                        "message": message,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            logger.debug(f"✅ [Asynchronous updates] Updated memory and MongoDB: {progress}%")
        except Exception as e:
            logger.warning(f"⚠️ [Asynchronous updates] failed: {e}")

    def _resolve_stock_name(self, code: Optional[str]) -> str:
        """解析股票名称（带缓存）"""
        if not code:
            return ""
        # hit cache
        if code in self._stock_name_cache:
            return self._stock_name_cache[code]
        name = None
        try:
            name = _get_cached_security_name(code)
            if name:
                self._stock_name_cache[code] = name
                return name

            if _get_stock_info_safe:
                info = _get_stock_info_safe(code)
                if isinstance(info, dict):
                    name = info.get("name")
        except Exception as e:
            logger.warning(f"⚠️ 获取股票名称失败: {code} - {e}")
        if not name:
            name = f"{'ETF' if _simple_analysis_service_is_cn_etf_symbol(code) else 'stocks'}{code}"
        # write cache
        self._stock_name_cache[code] = name
        return name

    def _enrich_stock_names(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Complete stock names for task list(Update in place)"""
        try:
            for t in tasks:
                code = t.get("stock_code") or t.get("stock_symbol")
                name = t.get("stock_name")
                if not name and code:
                    t["stock_name"] = self._resolve_stock_name(code)
        except Exception as e:
            logger.warning(f"⚠️ Exception occurred when completing stock name: {e}")
        return tasks

    def _convert_user_id(self, user_id: str) -> PyObjectId:
        """Convert string user ID to PyObjectId"""
        try:
            logger.info(f"🔄 开始转换用户ID: {user_id} (类型: {type(user_id)})")

            # If you are an admin user, use a fixed ObjectId
            if user_id == "admin":
                admin_object_id = ObjectId("507f1f77bcf86cd799439011")
                logger.info(f"🔄 Convert admin user ID: {user_id} -> {admin_object_id}")
                return PyObjectId(admin_object_id)
            else:
                # Try converting the string to ObjectId
                object_id = ObjectId(user_id)
                logger.info(f"🔄 转换用户ID: {user_id} -> {object_id}")
                return PyObjectId(object_id)
        except Exception as e:
            logger.error(f"❌ 用户ID转换失败: {user_id} -> {e}")
            # If the conversion fails, generate a new ObjectId
            new_object_id = ObjectId()
            logger.warning(f"⚠️ 生成新的用户ID: {new_object_id}")
            return PyObjectId(new_object_id)

    def _get_trading_graph(self, config: Dict[str, Any]) -> TradingAgentsGraph:
        """Get or create a TradingAgents instance — Deactivated

        v3.0 The old TradingAgentsGraph engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] SimpleAnalysisService._get_trading_graph deactivated,"
            "TradingAgentsGraph No longer instantiated."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        # 🔧 [Concurrency safety] Create new instances every time to avoid sharing state among multiple threads
        # Caching is no longer used because TradingAgentsGraph has mutable instance variables
        logger.info("🔧 Create a new TradingAgents instance (concurrent safe mode)...")

        trading_graph = TradingAgentsGraph(
            selected_analysts=config.get("selected_analysts", ["market", "fundamentals"]),
            debug=config.get("debug", False),
            config=config
        )

        logger.info(f"✅ TradingAgents Instance created successfully (instance ID: {id(trading_graph)}) ")

        return trading_graph

    async def create_analysis_task(
        self,
        user_id: str,
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """Create an analysis task (return immediately, do not perform analysis)"""
        try:
            # Generate tasks ID
            task_id = str(uuid.uuid4())

            # 🔧 Use get_symbol() Method to get the stock code (compatible with symbol and stock_code fields)
            stock_code = request.get_symbol()
            if not stock_code:
                raise ValueError("股票代码不能为空")

            logger.info(f"📝 创建分析任务: {task_id} - {stock_code}")
            logger.info(f"🔍 内存管理器实例ID: {id(self.memory_manager)}")

            # Create task state in memory
            task_state = await self.memory_manager.create_task(
                task_id=task_id,
                user_id=user_id,
                stock_code=stock_code,
                parameters=request.parameters.model_dump() if request.parameters else {},
                stock_name=(self._resolve_stock_name(stock_code) if hasattr(self, '_resolve_stock_name') else None),
            )

            logger.info(f"✅ 任务状态已创建: {task_state.task_id}")

            # Immediately verify whether the task can be queried
            verify_task = await self.memory_manager.get_task(task_id)
            if verify_task:
                logger.info(f"✅ 任务创建验证成功: {verify_task.task_id}")
            else:
                logger.error(f"❌ Task creation verification failed: Unable to query the newly created task {task_id}")

            # Complete the stock name and write the initial record to the database task document
            code = stock_code
            name = self._resolve_stock_name(code) if hasattr(self, '_resolve_stock_name') else f"股票{code}"

            try:
                db = get_mongo_db()
                result = await db.analysis_tasks.update_one(
                    {"task_id": task_id},
                    {"$setOnInsert": {
                        "task_id": task_id,
                        "user_id": user_id,
                        "stock_code": code,
                        "stock_symbol": code,
                        "stock_name": name,
                        "status": "pending",
                        "progress": 0,
                        "created_at": datetime.utcnow(),
                    }},
                    upsert=True
                )

                if result.upserted_id or result.matched_count > 0:
                    logger.info(f"✅ Task saved to MongoDB: {task_id}")
                else:
                    logger.warning(f"⚠️ MongoDB Exception in saving result: matched={result.matched_count}, upserted={result.upserted_id}")

            except Exception as e:
                logger.error(f"❌ Writing to MongoDB fails when creating a task: {e}")
                # Errors should not be ignored here as no MongoDB record will cause the status query to fail
                # But in order not to affect task execution, we record the error but continue execution
                import traceback
                logger.error(f"❌ MongoDB Save detailed errors: {traceback.format_exc()}")

            # 🔥 Add the task to the Redis queue and let the Worker process it
            try:
                from app.services.queue_service import get_queue_service
                queue_service = get_queue_service()

                # Prepare queue parameters
                queue_params = request.parameters.model_dump() if request.parameters else {}
                queue_params["engine"] = "legacy"  # Marked as legacy engine

                # 🔍 Debugging: print queue parameters
                logger.info(f"🔍 [DEBUG] Enqueue parameters: {queue_params}")

                # Join the team
                await queue_service.enqueue_task(
                    user_id=user_id,
                    symbol=stock_code,
                    params=queue_params,
                    task_id=task_id
                )
                logger.info(f"✅ 任务已加入队列: {task_id}")
            except Exception as e:
                logger.error(f"❌ 任务入队失败: {e}")
                import traceback
                logger.error(f"❌ 入队详细错误: {traceback.format_exc()}")

            return {
                "task_id": task_id,
                "status": "pending",
                "message": "The task has been created and is waiting to be executed"
            }

        except Exception as e:
            logger.error(f"❌ 创建分析任务失败: {e}")
            raise

    async def create_and_execute_analysis_v2(
        self,
        user_id: str,
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """Create and perform stock analysis v2.0 - using the Unified Task Engine

        Advantages:
        - Support multi-engine switching (workflow/legacy/llm)
        - Unified task management and progress tracking
        - Automatically select the best engine
        - Tasks can be queried and canceled

        Args:
            user_id: User ID
            request: Analysis request

        Returns:
            Task information dictionary
        """
        from app.models.analysis import AnalysisTaskType
        from app.models.user import PyObjectId

        # Get stock code
        stock_code = request.get_symbol()
        if not stock_code:
            raise ValueError("股票代码不能为空")

        logger.info(f"🚀 [stock analysis v2.0] Analysis using Unified Task Engine: {stock_code}")

        # Prepare task parameters
        task_params = {
            "symbol": stock_code,
            "market_type": request.parameters.market_type if request.parameters else "cn",
            "analysis_date": request.parameters.analysis_date if request.parameters else None,
            "research_depth": request.parameters.research_depth if request.parameters else "normal"
        }

        # If there are other parameters, add them too
        if request.parameters:
            params_dict = request.parameters.model_dump()
            task_params.update(params_dict)

        # Use unified task engine
        task_service = get_task_analysis_service()

        try:
            # Get the engine type (obtained from parameters, default auto)
            engine_type = "auto"
            preference_type = "neutral"

            if request.parameters:
                engine_type = getattr(request.parameters, "engine_type", "auto")
                preference_type = getattr(request.parameters, "preference_type", "neutral")

            # Create and execute tasks
            task = await task_service.create_and_execute_task(
                user_id=PyObjectId(user_id),
                task_type=AnalysisTaskType.STOCK_ANALYSIS,
                task_params=task_params,
                engine_type=engine_type,
                preference_type=preference_type
            )

            logger.info(f"✅ [股票分析v2.0] 分析完成: {stock_code}, 任务ID: {task.task_id}")

            # Return task information (compatible with existing API format)
            return {
                "task_id": task.task_id,
                "status": task.status,
                "message": "分析完成" if task.status == "completed" else "分析失败",
                "result": task.result,
                "execution_time": task.execution_time,
                "error_message": task.error_message
            }

        except Exception as e:
            logger.error(f"❌ [stock analysis v2.0] Analysis failed: {stock_code} - {e}", exc_info=True)
            raise

    async def execute_analysis_background(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest
    ):
        """Perform analysis tasks in the background — Deactivated

        v3.0 Since the old version of the legacy engine has been deactivated, the queue worker should use the v2 engine branch.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] SimpleAnalysisService.execute_analysis_background deactivated,"
            "task_id=%s The v2 engine (thread_worker s engine='v2' branch)."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md" % task_id
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        # 🔧 Use get_symbol() Method to get the stock code (compatible with symbol and stock_code fields)
        stock_code = request.get_symbol()

        # Add the outermost exception capture to ensure that all exceptions are logged
        try:
            logger.info(f"🎯🎯🎯 [ENTRY] execute_analysis_background method is called: {task_id}")
            logger.info(f"🎯🎯🎯 [ENTRY] user_id={user_id}, stock_code={stock_code}")
        except Exception as entry_error:
            print(f"❌❌❌ [CRITICAL] Logging failed: {entry_error}")
            import traceback
            traceback.print_exc()

        progress_tracker = None
        try:
            logger.info(f"🚀 Start performing analysis tasks in the background: {task_id}")

            # 🔍 Verify that the stock code exists
            logger.info(f"🔍 开始验证股票代码: {stock_code}")
            from tradingagents.utils.stock_validator import prepare_stock_data_async
            from datetime import datetime

            # Get market type
            market_type = request.parameters.market_type if request.parameters else "A股"

            # Get analysis date and convert to string format
            analysis_date = request.parameters.analysis_date if request.parameters else None
            if analysis_date:
                # If it is a datetime object, convert it to a string
                if isinstance(analysis_date, datetime):
                    analysis_date = analysis_date.strftime('%Y-%m-%d')
                # If it is a string, make sure it is formatted correctly
                elif isinstance(analysis_date, str):
                    # Try to parse and reformat to ensure the format is consistent
                    try:
                        parsed_date = datetime.strptime(analysis_date, '%Y-%m-%d')
                        analysis_date = parsed_date.strftime('%Y-%m-%d')
                    except ValueError:
                        # If the format is wrong, use today
                        analysis_date = datetime.now().strftime('%Y-%m-%d')
                        logger.warning(f"⚠️ Parse date format is incorrect, use today: {analysis_date}")

            # 🔥 Use the asynchronous version and await directly to avoid event loop conflicts
            validation_result = await prepare_stock_data_async(
                stock_code=stock_code,
                market_type=market_type,
                period_days=30,
                analysis_date=analysis_date
            )

            if not validation_result.is_valid:
                error_msg = f"❌ 股票代码验证失败: {validation_result.error_message}"
                logger.error(error_msg)
                logger.error(f"💡 建议: {validation_result.suggestion}")

                # Build user-friendly error messages
                user_friendly_error = (
                    f"❌ 股票代码无效\n\n"
                    f"{validation_result.error_message}\n\n"
                    f"💡 {validation_result.suggestion}"
                )

                # Update task status is failed
                await self.memory_manager.update_task_status(
                    task_id=task_id,
                    status=AnalysisStatus.FAILED,
                    progress=0,
                    error_message=user_friendly_error
                )

                # Update MongoDB status
                await self._update_task_status(
                    task_id,
                    AnalysisStatus.FAILED,
                    0,
                    error_message=user_friendly_error
                )

                return

            logger.info(f"✅ 股票代码验证通过: {stock_code} - {validation_result.stock_name}")
            logger.info(f"📊 市场类型: {validation_result.market_type}")
            logger.info(f"📈 历史数据: {'有' if validation_result.has_historical_data else '无'}")
            logger.info(f"📋 基本信息: {'有' if validation_result.has_basic_info else '无'}")

            # Create a Redis progress tracker in the thread pool (avoid blocking the event loop)
            def create_progress_tracker():
                """在线程中创建进度跟踪器"""
                logger.info(f"📊 [thread] Create a progress tracker: {task_id}")
                tracker = RedisProgressTracker(
                    task_id=task_id,
                    analysts=request.parameters.selected_analysts or ["market", "fundamentals"],
                    research_depth=request.parameters.research_depth or "标准",
                    llm_provider="dashscope"
                )
                logger.info(f"✅ [thread] Progress tracker created: {task_id}")
                return tracker

            progress_tracker = await asyncio.to_thread(create_progress_tracker)

            # Cache progress tracker
            self._progress_trackers[task_id] = progress_tracker

            # Register to log monitoring
            register_analysis_tracker(task_id, progress_tracker)

            # Initialization progress (executed in thread)
            await asyncio.to_thread(
                progress_tracker.update_progress,
                {
                    "progress_percentage": 10,
                    "last_message": "🚀 开始股票分析"
                }
            )

            # Update status is running
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=10,
                message="分析开始...",
                current_step="initialization"
            )

            # Synchronously update MongoDB status
            await self._update_task_status(task_id, AnalysisStatus.PROCESSING, 10)

            # Data preparation phase (executed in thread)
            await asyncio.to_thread(
                progress_tracker.update_progress,
                {
                    "progress_percentage": 20,
                    "last_message": "🔧 检查环境配置"
                }
            )
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=20,
                message="准备分析数据...",
                current_step="data_preparation"
            )

            # Synchronously update MongoDB status
            await self._update_task_status(task_id, AnalysisStatus.PROCESSING, 20)

            # Perform actual analysis
            result = await self._execute_analysis_sync(task_id, user_id, request, progress_tracker)

            # Mark progress tracker complete (execute in thread)
            await asyncio.to_thread(progress_tracker.mark_completed)

            # Save analysis results to files and databases
            try:
                logger.info(f"💾 开始保存分析结果: {task_id}")
                await self._save_analysis_results_complete(task_id, result)
                logger.info(f"✅ 分析结果保存完成: {task_id}")
            except Exception as save_error:
                logger.error(f"❌ 保存分析结果失败: {task_id} - {save_error}")
                # Failure to save does not affect the analysis completion status

            # 🔍 Debugging: Examine the data about to be saved to memory result
            logger.info(f"🔍 [DEBUG] The result key that will be saved to memory: {list(result.keys())}")
            logger.info(f"🔍 [DEBUG] to be saved to memory decision: {bool(result.get('decision'))}")
            if result.get('decision'):
                logger.info(f"🔍 [DEBUG] The decision content to be saved: {result['decision']}")

            # Update status is complete
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="分析完成",
                current_step="completed",
                result_data=result
            )

            # Synchronously update MongoDB status to complete
            await self._update_task_status(task_id, AnalysisStatus.COMPLETED, 100)

            # Create notification: Analysis completed (Option B:REST+SSE) 
            try:
                from app.services.notifications_service import get_notifications_service
                svc = get_notifications_service()
                summary = str(result.get("summary", ""))[:120]
                await svc.create_and_publish(
                    payload=NotificationCreate(
                        user_id=str(user_id),
                        type='analysis',
                        title=f"{request.stock_code} 分析完成",
                        content=summary,
                        link=f"/stocks/{request.stock_code}",
                        source='analysis'
                    )
                )
            except Exception as notif_err:
                logger.warning(f"⚠️ Failed to create notification(ignore): {notif_err}")

            # Send email notifications (if user has enabled email notifications) with PDF report
            try:
                from app.services.email_service import get_email_service
                from app.models.email import EmailType

                # Generate PDF attachment
                attachments = None
                try:
                    from app.utils.report_exporter import ReportExporter
                    from app.utils.report_formatter import extract_reports_from_state

                    report_exporter = ReportExporter()
                    if report_exporter.weasyprint_available or report_exporter.pdfkit_available:
                        # Extract report build document from state
                        state = result.get("state", {})
                        reports = extract_reports_from_state(state)

                        if reports:
                            # Build report document
                            stock_code = request.stock_code
                            stock_name = result.get("stock_name", stock_code)
                            analysis_date = result.get("analysis_date", "")

                            report_doc = {
                                "stock_symbol": stock_code,
                                "stock_name": stock_name,
                                "analysis_date": analysis_date,
                                "recommendation": result.get("recommendation", ""),
                                "confidence_score": result.get("confidence_score", 0),
                                "risk_level": result.get("risk_level", "中等"),
                                "reports": reports,
                                "decision": result.get("decision", {})
                            }

                            pdf_content = report_exporter.generate_pdf_report(report_doc)
                            if pdf_content:
                                filename = f"{stock_code}_{analysis_date}_分析报告.pdf"
                                attachments = [(filename, pdf_content, "application/pdf")]
                                logger.info(f"📄 PDF report generated: {filename} ({len(pdf_content)} bytes)")
                except Exception as pdf_err:
                    logger.warning(f"⚠️ PDF Build failed(Email will be sent without attachments): {pdf_err}")

                email_service = get_email_service()
                await email_service.send_analysis_email(
                    user_id=str(user_id),
                    email_type=EmailType.SINGLE_ANALYSIS,
                    template_name="single_analysis",
                    template_data={
                        "stock_code": request.stock_code,
                        "stock_name": result.get("stock_name", request.stock_code),
                        "analysis_date": result.get("analysis_date", ""),
                        "summary": result.get("summary", ""),
                        "recommendation": result.get("recommendation", ""),
                        "confidence_score": result.get("confidence_score", 0),
                        "risk_level": result.get("risk_level", "中等"),
                        "key_points": result.get("key_points", []),
                        "detail_url": f"{request.stock_code}"
                    },
                    reference_id=task_id,
                    attachments=attachments  # Comes with PDF report
                )
                logger.info(f"📧 Attempted to send analysis completion email: {task_id}")
            except Exception as email_err:
                logger.warning(f"⚠️ Failed to send email notification(ignore): {email_err}")

            logger.info(f"✅ 后台分析任务完成: {task_id}")

        except Exception as e:
            logger.error(f"❌ 后台分析任务失败: {task_id} - {e}")

            # Format error messages into user-friendly prompts
            from ..utils.error_formatter import ErrorFormatter

            # Gather contextual information
            error_context = {}
            if hasattr(request, 'parameters') and request.parameters:
                if hasattr(request.parameters, 'quick_model'):
                    error_context['model'] = request.parameters.quick_model
                if hasattr(request.parameters, 'deep_model'):
                    error_context['model'] = request.parameters.deep_model

            # Formatting error
            formatted_error = ErrorFormatter.format_error(str(e), error_context)

            # Build user-friendly error messages
            user_friendly_error = (
                f"{formatted_error['title']}\n\n"
                f"{formatted_error['message']}\n\n"
                f"💡 {formatted_error['suggestion']}"
            )

            # Marking progress tracker failed
            if progress_tracker:
                progress_tracker.mark_failed(user_friendly_error)

            # Update status is failed
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                message="分析失败",
                current_step="failed",
                error_message=user_friendly_error
            )

            # Synchronous update of MongoDB status is failed
            await self._update_task_status(task_id, AnalysisStatus.FAILED, 0, user_friendly_error)
        finally:
            # Clean progress tracker cache
            if task_id in self._progress_trackers:
                del self._progress_trackers[task_id]

            # Log out from log monitoring
            unregister_analysis_tracker(task_id)

    async def _execute_analysis_sync(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker: Optional[RedisProgressTracker] = None
    ) -> Dict[str, Any]:
        """Synchronous execution of analysis (running in a shared thread pool)— Deactivated

        v3.0 The legacy engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] SimpleAnalysisService._execute_analysis_sync deactivated,"
            "task_id=%s The v2 engine should be used instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md" % task_id
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        # 🔧 Use a shared thread pool to support concurrent execution of multiple tasks
        # No longer create a new thread pool every time to avoid serial execution
        loop = asyncio.get_event_loop()
        stock_code = request.get_symbol()  # 🔑 Fix: use get_symbol() method
        logger.info(f"🚀 [thread pool] Submit analysis tasks to the shared thread pool: {task_id} - {stock_code}")
        result = await loop.run_in_executor(
            self._thread_pool,  # Use shared thread pool
            self._run_analysis_sync,
            task_id,
            user_id,
            request,
            progress_tracker
        )
        logger.info(f"✅ [thread pool] Analysis task execution completed: {task_id}")
        return result

    def _run_analysis_sync(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker: Optional[RedisProgressTracker] = None
    ) -> Dict[str, Any]:
        """Specific implementation of synchronous execution analysis — Deactivated

        v3.0 The legacy engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] SimpleAnalysisService._run_analysis_sync deactivated,"
            "task_id=%s The v2 engine should be used instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md" % task_id
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        try:
            # 🔑 Key: Extract the stock symbol at the beginning of the method (compatible with symbol and stock_code fields)
            stock_code = request.get_symbol()

            # Reinitialize the logging system in a thread
            from tradingagents.utils.logging_init import init_logging, get_logger
            init_logging()
            thread_logger = get_logger('analysis_thread')

            thread_logger.info(f"🔄 [thread pool] Start performing analysis: {task_id} - {stock_code}")
            logger.info(f"🔄 [thread pool] Start performing analysis: {task_id} - {stock_code}")

            # 🔧 Calculate accurate progress based on step weights of RedisProgressTracker
            # Basic preparation stage (10%): 0.03 + 0.02 + 0.01 + 0.02 + 0.02 = 0.10
            # Step index 0-4 corresponds 0-10%

            # Asynchronous update progress (called in the thread pool)
            def update_progress_sync(progress: int, message: str, step: str):
                """在线程池中同步更新进度"""
                try:
                    # Also updates the Redis progress tracker
                    if progress_tracker:
                        progress_tracker.update_progress({
                            "progress_percentage": progress,
                            "last_message": message
                        })

                    # 🔥 Use synchronous methods to update memory and MongoDB to avoid event loop conflicts
                    # 1. Update task state in memory (using new event loop)
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            self.memory_manager.update_task_status(
                                task_id=task_id,
                                status=TaskStatus.RUNNING,
                                progress=progress,
                                message=message,
                                current_step=step
                            )
                        )
                    finally:
                        loop.close()

                    # 2. Update MongoDB (use synchronous client to avoid event loop conflicts)
                    from pymongo import MongoClient
                    from app.core.config import settings
                    from datetime import datetime

                    sync_client = MongoClient(settings.MONGO_URI)
                    sync_db = sync_client[settings.MONGO_DB]

                    sync_db.analysis_tasks.update_one(
                        {"task_id": task_id},
                        {
                            "$set": {
                                "progress": progress,
                                "current_step": step,
                                "message": message,
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    sync_client.close()

                except Exception as e:
                    logger.warning(f"⚠️ 进度更新失败: {e}")

            # Configuration phase - corresponding steps 3 "⚙️ Parameter settings" (6-8%)
            update_progress_sync(7, "⚙️ 配置分析参数", "configuration")

            # 🆕 Intelligent model selection logic
            from app.services.model_capability_service import get_model_capability_service
            capability_service = get_model_capability_service()

            research_depth = request.parameters.research_depth if request.parameters else "标准"

            # 1. Check if the frontend has a model specified
            if (request.parameters and
                hasattr(request.parameters, 'quick_analysis_model') and
                hasattr(request.parameters, 'deep_analysis_model') and
                request.parameters.quick_analysis_model and
                request.parameters.deep_analysis_model):

                # Use the model specified by the front end
                quick_model = request.parameters.quick_analysis_model
                deep_model = request.parameters.deep_analysis_model

                logger.info(f"📝 [Analysis Services] user specified model: quick={quick_model}, deep={deep_model}")

                # Verify that the model is suitable
                validation = capability_service.validate_model_pair(
                    quick_model, deep_model, research_depth
                )

                if not validation["valid"]:
                    # Log warning
                    for warning in validation["warnings"]:
                        logger.warning(warning)

                    # If the model is not suitable, automatically switch to the recommended model
                    logger.info("🔄 Automatically switch to recommended models...")
                    quick_model, deep_model = capability_service.recommend_models_for_depth(
                        research_depth
                    )
                    logger.info(f"✅ Switched: quick={quick_model}, deep={deep_model}")
                else:
                    # Even if the verification passes, a warning message is logged
                    for warning in validation["warnings"]:
                        logger.info(warning)
                    logger.info(f"✅ The model selected by the user is verified passed: quick={quick_model}, deep={deep_model}")

            else:
                # 2. Automatic recommendation model
                quick_model, deep_model = capability_service.recommend_models_for_depth(
                    research_depth
                )
                logger.info(f"🤖 Automatic recommendation model: quick={quick_model}, deep={deep_model}")

            # 🔧 Find the corresponding suppliers and suppliers based on the fast model and deep model respectively. API URL
            quick_provider_info = get_provider_and_url_by_model_sync(quick_model)
            deep_provider_info = get_provider_and_url_by_model_sync(deep_model)

            quick_provider = quick_provider_info["provider"]
            deep_provider = deep_provider_info["provider"]
            quick_backend_url = quick_provider_info["backend_url"]
            deep_backend_url = deep_provider_info["backend_url"]

            logger.info(f"🔍 [供应商查找] 快速模型 {quick_model} 对应的供应商: {quick_provider}")
            logger.info(f"🔍 [API address] Quick model usage backend_url: {quick_backend_url}")
            logger.info(f"🔍 [供应商查找] 深度模型 {deep_model} 对应的供应商: {deep_provider}")
            logger.info(f"🔍 [API address] Deep model usage backend_url: {deep_backend_url}")

            # Check if two models are from the same manufacturer
            if quick_provider == deep_provider:
                logger.info(f"✅ [Supplier verification] Both models are from the same manufacturer: {quick_provider}")
            else:
                logger.info(f"✅ [混合模式] 快速模型({quick_provider}) 和 深度模型({deep_provider}) 来自不同厂家")

            # Get market type
            market_type = request.parameters.market_type if request.parameters else "A股"
            logger.info(f"📊 [market type] Use market type: {market_type}")

            # 🔧 Read model configuration parameters from the database (max_tokens, temperature, timeout, reasoning_effort etc.)
            quick_model_config = _load_model_config_from_db(quick_model)
            deep_model_config = _load_model_config_from_db(deep_model)
            if quick_model_config:
                logger.info(f"🔧 [快速模型配置] {quick_model_config}")
            if deep_model_config:
                logger.info(f"🔧 [深度模型配置] {deep_model_config}")

            # Create analysis configurations (supports mixed mode)
            config = create_analysis_config(
                research_depth=research_depth,
                selected_analysts=request.parameters.selected_analysts if request.parameters else ["market", "fundamentals"],
                quick_model=quick_model,
                deep_model=deep_model,
                llm_provider=quick_provider,  # Suppliers who primarily use rapid models
                market_type=market_type,  # Market type using front-end delivery
                quick_model_config=quick_model_config,
                deep_model_config=deep_model_config,
            )

            # 🔧 Add mixed mode configuration
            config["quick_provider"] = quick_provider
            config["deep_provider"] = deep_provider
            config["quick_backend_url"] = quick_backend_url
            config["deep_backend_url"] = deep_backend_url
            config["backend_url"] = quick_backend_url  # Stay backwards compatible

            # 🔍 Validate models in configuration
            logger.info(f"🔍 [Model validation] Quick model in configuration: {config.get('quick_think_llm')}")
            logger.info(f"🔍 [Model validation] Deep model in configuration: {config.get('deep_think_llm')}")
            logger.info(f"🔍 [Model validation] LLM provider in configuration: {config.get('llm_provider')}")

            # Initializing the analysis engine - corresponding steps 4 "🚀 Start the engine" (8-10%)
            update_progress_sync(9, "🚀 初始化AI分析引擎", "engine_initialization")
            trading_graph = self._get_trading_graph(config)

            # 🔍 Verify configuration in TradingGraph instance
            logger.info(f"🔍 [Engine verification] TradingGraph Quick model in configuration: {trading_graph.config.get('quick_think_llm')}")
            logger.info(f"🔍 [Engine verification] TradingGraph Deep model in configuration: {trading_graph.config.get('deep_think_llm')}")

            # Prepare data for analysis
            start_time = datetime.now()

            # 🔧 Use the parsed date passed by the front end, or the current date if not available
            if request.parameters and hasattr(request.parameters, 'analysis_date') and request.parameters.analysis_date:
                # The front end is passed a datetime object or string
                if isinstance(request.parameters.analysis_date, datetime):
                    analysis_date = request.parameters.analysis_date.strftime("%Y-%m-%d")
                elif isinstance(request.parameters.analysis_date, str):
                    analysis_date = request.parameters.analysis_date
                else:
                    analysis_date = datetime.now().strftime("%Y-%m-%d")
                logger.info(f"📅 Use the analysis date specified by the front end: {analysis_date}")
            else:
                analysis_date = datetime.now().strftime("%Y-%m-%d")
                logger.info(f"📅 Use current date as analysis date: {analysis_date}")

            # 🔧 Intelligent date range processing: get the last 10 days of data and automatically handle weekends/holidays
            # This ensures that data for the last trading day is available even on weekends or holidays
            from tradingagents.utils.dataflow_utils import get_trading_date_range
            data_start_date, data_end_date = get_trading_date_range(analysis_date, lookback_days=10)

            logger.info(f"📅 分析目标日期: {analysis_date}")
            logger.info(f"📅 数据查询范围: {data_start_date} 至 {data_end_date} (最近10天)")
            logger.info("💡 Description: Get 10 days of data to automatically handle weekends, holidays and data delays")

            # Start analysis - 10% progress, about to enter the analyst stage
            # Note: Do not manually set the progress too high and let graph_progress_callback update the actual analysis progress.
            update_progress_sync(10, "🤖 开始多智能体协作分析", "agent_analysis")

            # Start an asynchronous task to simulate progress updates
            import threading
            import time

            def simulate_progress():
                """Simulate TradingAgents internal progress"""
                try:
                    if not progress_tracker:
                        return

                    # Analyst stage - dynamically adjusted based on the number of analysts selected
                    analysts = request.parameters.selected_analysts if request.parameters else ["market", "fundamentals"]

                    # Simulation Analyst Execution
                    for i, analyst in enumerate(analysts):
                        time.sleep(15)  # About 15 seconds per analyst
                        if analyst == "market":
                            progress_tracker.update_progress("📊 市场分析师正在分析")
                        elif analyst == "fundamentals":
                            progress_tracker.update_progress("💼 基本面分析师正在分析")
                        elif analyst == "news":
                            progress_tracker.update_progress("📰 新闻分析师正在分析")
                        elif analyst == "social":
                            progress_tracker.update_progress("💬 Social media analysts are analyzing")

                    # research team stage
                    time.sleep(10)
                    progress_tracker.update_progress("🐂 Active evidence researcher constructs argument")

                    time.sleep(8)
                    progress_tracker.update_progress("🐻 Cautious Evidence Researchers Identify Risks")

                    # Multi-scenario research phases - determine research rounds based on 5 levels
                    research_depth = request.parameters.research_depth if request.parameters else "标准"
                    if research_depth == "快速":
                        debate_rounds = 1
                    elif research_depth == "基础":
                        debate_rounds = 1
                    elif research_depth == "标准":
                        debate_rounds = 1
                    elif research_depth == "深度":
                        debate_rounds = 2
                    elif research_depth == "全面":
                        debate_rounds = 3
                    else:
                        debate_rounds = 1  # Default

                    for round_num in range(debate_rounds):
                        time.sleep(12)
                        progress_tracker.update_progress(f"🎯 多情景研究 第{round_num+1}轮")

                    time.sleep(8)
                    progress_tracker.update_progress("👔 研究整合员形成共识")

                    # research integrator stage
                    time.sleep(10)
                    progress_tracker.update_progress("💼 研究整合员整理简报")

                    # risk management stage
                    time.sleep(8)
                    progress_tracker.update_progress("🔥 高弹性情景风险评估")

                    time.sleep(6)
                    progress_tracker.update_progress("🛡️ 防御情景风险评估")

                    time.sleep(6)
                    progress_tracker.update_progress("⚖️ 基准情景风险评估")

                    time.sleep(8)
                    progress_tracker.update_progress("🎯 风险评估师制定策略")

                    # final stage
                    time.sleep(5)
                    progress_tracker.update_progress("📡 信号处理")

                except Exception as e:
                    logger.warning(f"⚠️ 进度模拟失败: {e}")

            # Start the progress simulation thread
            progress_thread = threading.Thread(target=simulate_progress, daemon=True)
            progress_thread.start()

            # Define a progress callback function to receive the real-time progress of LangGraph
            # Node progress mapping table (corresponding to the step weight of RedisProgressTracker)
            node_progress_map = {
                # analyst stage (10% → 45%)
                "📊 市场分析师": 27.5,      # 10% + 17.5% (Assume 2 analysts)
                "💼 基本面分析师": 45,       # 10% + 35%
                "📰 新闻分析师": 27.5,       # If there are 3 analysts
                "💬 社交媒体分析师": 27.5,   # If there are 4 analysts
                # multi-scenario research phase (45% → 70%)
                "🐂 积极证据研究员": 51.25,      # 45% + 6.25%
                "🐻 谨慎证据研究员": 57.5,       # 45% + 12.5%
                "👔 研究经理": 70,           # 45% + 25%
                # Research integration stage (70% → 78%)
                "🧩 研究整合员汇总": 78,         # 70% + 8%
                # risk scenario research phase (78% → 93%)
                "🔥 高弹性情景研究": 81.75,    # 78% + 3.75%
                "🛡️ 防御情景研究": 85.5,    # 78% + 7.5%
                "⚖️ 基准情景研究": 89.25,   # 78% + 11.25%
                "👔 风险评估师": 93,           # 78% + 15%
                # final stage (93% → 100%)
                "📊 生成报告": 97,           # 93% + 4%
            }

            def graph_progress_callback(message: str):
                """Receive progress updates from LangGraph

                Maps directly to progress percentage based on node name, ensuring consistency with the step weight of RedisProgressTracker
                Note: Only update when the progress increases to avoid overwriting the virtual step progress of RedisProgressTracker
                """
                try:
                    logger.info(f"🎯🎯🎯 [Graph progress callback is called] message={message}")
                    if not progress_tracker:
                        logger.warning("⚠️ progress_tracker If None, progress cannot be updated")
                        return

                    # Find the progress percentage corresponding to the node
                    progress_pct = node_progress_map.get(message)

                    if progress_pct is not None:
                        # Get the current progress (using the progress_data attribute)
                        current_progress = progress_tracker.progress_data.get('progress_percentage', 0)

                        # Only update when progress increases to avoid overwriting the progress of dummy steps
                        if int(progress_pct) > current_progress:
                            # Update Redis progress tracker
                            progress_tracker.update_progress({
                                'progress_percentage': int(progress_pct),
                                'last_message': message
                            })
                            logger.info(f"📊 [Graph Progress] Progress updated: {current_progress}% → {int(progress_pct)}% - {message}")

                            # 🔥 Simultaneously update memory and MongoDB
                            try:
                                import asyncio
                                from datetime import datetime

                                # Try to get the currently running event loop
                                try:
                                    loop = asyncio.get_running_loop()
                                    # If inside the event loop, use create_task
                                    asyncio.create_task(
                                        self._update_progress_async(task_id, int(progress_pct), message)
                                    )
                                    logger.debug(f"✅ [Graph Progress] Asynchronous update task submitted: {int(progress_pct)}%")
                                except RuntimeError:
                                    # There is no running event loop, use synchronous update MongoDB
                                    from pymongo import MongoClient
                                    from app.core.config import settings

                                    # Create a synchronous MongoDB client
                                    sync_client = MongoClient(settings.MONGO_URI)
                                    sync_db = sync_client[settings.MONGO_DB]

                                    # Synchronous updates MongoDB
                                    sync_db.analysis_tasks.update_one(
                                        {"task_id": task_id},
                                        {
                                            "$set": {
                                                "progress": int(progress_pct),
                                                "current_step": message,
                                                "message": message,
                                                "updated_at": datetime.utcnow()
                                            }
                                        }
                                    )
                                    sync_client.close()

                                    # Update memory asynchronously (create a new event loop)
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        loop.run_until_complete(
                                            self.memory_manager.update_task_status(
                                                task_id=task_id,
                                                status=TaskStatus.RUNNING,
                                                progress=int(progress_pct),
                                                message=message,
                                                current_step=message
                                            )
                                        )
                                    finally:
                                        loop.close()

                                    logger.debug(f"✅ [Graph Progress] Memory and MongoDB: {int(progress_pct)}%")
                            except Exception as sync_err:
                                logger.warning(f"⚠️ [Graph Progress] Synchronous update failed: {sync_err}")
                        else:
                            # The progress is not increased, only the message is updated
                            progress_tracker.update_progress({
                                'last_message': message
                            })
                            logger.info(f"📊 [Graph Progress] Progress unchanged({current_progress}% >= {int(progress_pct)}%), Update message only: {message}")
                    else:
                        # Unknown node, only update messages
                        logger.warning(f"⚠️ [Graph Progress] unknown node: {message}, Update message only")
                        progress_tracker.update_progress({
                            'last_message': message
                        })

                except Exception as e:
                    logger.error(f"❌ Graph Progress callback failed: {e}", exc_info=True)

            logger.info(f"🚀 Prepare to call trading_graph.propagate,progress_callback={graph_progress_callback}")

            # Perform the actual analysis, passing progress callbacks and task_id
            try:
                from tradingagents.agents.utils.agent_context import AgentContext
                ctx = AgentContext(user_id=str(user_id))
                logger.info(f"[diagnose] inject AgentContext(simple) task_id={task_id} user_id={user_id} symbol={stock_code} date={analysis_date}")
            except Exception:
                ctx = None
                logger.info("[diagnose] inject AgentContext(simple) failed, continue without context")

            state, decision = trading_graph.propagate(
                stock_code,  # 🔑 Fix: use stock_code variable instead request.stock_code
                analysis_date,
                progress_callback=graph_progress_callback,
                task_id=task_id,
                agent_context=(ctx.__dict__ if ctx else None)
            )

            logger.info("✅ trading_graph.propagate Execution completed")

            # 🔍 Debugging: Check the structure of the decision
            logger.info(f"🔍 [DEBUG] Decision Type: {type(decision)}")
            logger.info(f"🔍 [DEBUG] Decision content: {decision}")
            if isinstance(decision, dict):
                logger.info(f"🔍 [DEBUG] Decision key: {list(decision.keys())}")
            elif hasattr(decision, '__dict__'):
                logger.info(f"🔍 [DEBUG] Decision Properties: {list(vars(decision).keys())}")

            # Processing results
            if progress_tracker:
                progress_tracker.update_progress("📊 处理分析结果")
            update_progress_sync(90, "处理分析结果...", "result_processing")

            execution_time = (datetime.now() - start_time).total_seconds()

            # Extract reports field from state
            reports = {}
            try:
                # Prioritize dynamic extraction from structured_reports generated by the engine
                structured_reports = state.get('structured_reports', {}) if isinstance(state, dict) else {}
                if isinstance(structured_reports, dict) and structured_reports:
                    for field, entry in structured_reports.items():
                        if isinstance(entry, dict) and entry.get("success") and entry.get("content"):
                            content = entry["content"]
                            if isinstance(content, str) and len(content.strip()) > 10:
                                reports[field] = content.strip()
                else:
                    # Fallback: derivation from report_manifest
                    manifest = state.get('report_manifest', []) if isinstance(state, dict) else []
                    if manifest:
                        for m in manifest:
                            field = m.get("field")
                            if field:
                                value = state.get(field)
                                if isinstance(value, str) and len(value.strip()) > 10:
                                    reports[field] = value.strip()
                    if not reports:
                        # Final fallback: legacy hardcoded lists
                        report_fields = [
                            'index_report',
                            'sector_report',
                            'market_report',
                            'sentiment_report',
                            'news_report',
                            'fundamentals_report',
                            'chip_report',
                            'investment_plan',
                            'trader_investment_plan',
                            'final_trade_decision'
                        ]

                        from app.utils.report_formatter import _convert_json_to_markdown

                        for field in report_fields:
                            if hasattr(state, field):
                                value = getattr(state, field, "")
                            elif isinstance(state, dict) and field in state:
                                value = state[field]
                            else:
                                value = ""

                            if isinstance(value, str) and len(value.strip()) > 10:
                                if field in ['investment_plan', 'final_trade_decision']:
                                    if field == 'investment_plan':
                                        report_type = "investment"
                                    else:
                                        report_type = "final_decision"
                                    markdown_value = _convert_json_to_markdown(value.strip(), report_type)
                                    reports[field] = markdown_value
                            logger.info(f"📊 [REPORTS] 提取报告: {field} - 长度: {len(markdown_value)} (已转换JSON->Markdown)")
                        else:
                            reports[field] = value.strip()
                            logger.info(f"📊 [REPORTS] 提取报告: {field} - 长度: {len(value.strip())}")
                    else:
                        logger.debug(f"⚠️ [REPORTS] 跳过报告: {field} - 内容为空或太短")

                # Handle research team debate status report
                if hasattr(state, 'investment_debate_state') or (isinstance(state, dict) and 'investment_debate_state' in state):
                    debate_state = getattr(state, 'investment_debate_state', None) if hasattr(state, 'investment_debate_state') else state.get('investment_debate_state')
                    if debate_state:
                        # Extract long researcher history
                        if hasattr(debate_state, 'bull_history'):
                            bull_content = getattr(debate_state, 'bull_history', "")
                        elif isinstance(debate_state, dict) and 'bull_history' in debate_state:
                            bull_content = debate_state['bull_history']
                        else:
                            bull_content = ""

                        if bull_content and len(bull_content.strip()) > 10:
                            reports['bull_researcher'] = bull_content.strip()
                            logger.info(f"📊 [REPORTS] Extract report: bull_researcher - length: {len(bull_content.strip())}")

                        # Extract short researcher history
                        if hasattr(debate_state, 'bear_history'):
                            bear_content = getattr(debate_state, 'bear_history', "")
                        elif isinstance(debate_state, dict) and 'bear_history' in debate_state:
                            bear_content = debate_state['bear_history']
                        else:
                            bear_content = ""

                        if bear_content and len(bear_content.strip()) > 10:
                            reports['bear_researcher'] = bear_content.strip()
                            logger.info(f"📊 [REPORTS] Extract report: bear_researcher - length: {len(bear_content.strip())}")

                        # Extract Research Manager Analysis
                        if hasattr(debate_state, 'judge_decision'):
                            decision_content = getattr(debate_state, 'judge_decision', "")
                        elif isinstance(debate_state, dict) and 'judge_decision' in debate_state:
                            decision_content = debate_state['judge_decision']
                        else:
                            decision_content = str(debate_state)

                        if decision_content and len(decision_content.strip()) > 10:
                            # 🔥 New: If in JSON format, convert to Markdown
                            markdown_content = _convert_json_to_markdown(decision_content.strip(), "investment")
                            reports['research_team_decision'] = markdown_content
                            logger.info(f"📊 [REPORTS] Extract report: research_team_decision - length: {len(markdown_content)} (Converted JSON->Markdown)")

                # Handle risk management team debate status report
                if hasattr(state, 'risk_debate_state') or (isinstance(state, dict) and 'risk_debate_state' in state):
                    risk_state = getattr(state, 'risk_debate_state', None) if hasattr(state, 'risk_debate_state') else state.get('risk_debate_state')
                    if risk_state:
                        # Extract high-resilience scenario analyst history
                        if hasattr(risk_state, 'risky_history'):
                            risky_content = getattr(risk_state, 'risky_history', "")
                        elif isinstance(risk_state, dict) and 'risky_history' in risk_state:
                            risky_content = risk_state['risky_history']
                        else:
                            risky_content = ""

                        if risky_content and len(risky_content.strip()) > 10:
                            reports['risky_analyst'] = risky_content.strip()
                            logger.info(f"📊 [REPORTS] Extract report: risky_analyst - length: {len(risky_content.strip())}")

                        # Extract Defense Scenario Analyst History
                        if hasattr(risk_state, 'safe_history'):
                            safe_content = getattr(risk_state, 'safe_history', "")
                        elif isinstance(risk_state, dict) and 'safe_history' in risk_state:
                            safe_content = risk_state['safe_history']
                        else:
                            safe_content = ""

                        if safe_content and len(safe_content.strip()) > 10:
                            reports['safe_analyst'] = safe_content.strip()
                            logger.info(f"📊 [REPORTS] Extract report: safe_analyst - length: {len(safe_content.strip())}")

                        # Extract neutral analyst history
                        if hasattr(risk_state, 'neutral_history'):
                            neutral_content = getattr(risk_state, 'neutral_history', "")
                        elif isinstance(risk_state, dict) and 'neutral_history' in risk_state:
                            neutral_content = risk_state['neutral_history']
                        else:
                            neutral_content = ""

                        if neutral_content and len(neutral_content.strip()) > 10:
                            reports['neutral_analyst'] = neutral_content.strip()
                            logger.info(f"📊 [REPORTS] Extract report: neutral_analyst - length: {len(neutral_content.strip())}")

                        # Extract risk assessor decisions
                        if hasattr(risk_state, 'judge_decision'):
                            risk_decision = getattr(risk_state, 'judge_decision', "")
                        elif isinstance(risk_state, dict) and 'judge_decision' in risk_state:
                            risk_decision = risk_state['judge_decision']
                        else:
                            risk_decision = str(risk_state)

                        if risk_decision and len(risk_decision.strip()) > 10:
                            # 🔥 New: If in JSON format, convert to Markdown
                            markdown_content = _convert_json_to_markdown(risk_decision.strip(), "risk")
                            reports['risk_management_decision'] = markdown_content
                            logger.info(f"📊 [REPORTS] Extract report: risk_management_decision - length: {len(markdown_content)} (Converted JSON->Markdown)")

                logger.info(f"📊 [REPORTS] 从state中提取到 {len(reports)} 个报告: {list(reports.keys())}")

            except Exception as e:
                logger.warning(f"⚠️ Error while extracting reports: {e}")
                # Downgrade to extract from detailed_analysis
                try:
                    if isinstance(decision, dict):
                        for key, value in decision.items():
                            if isinstance(value, str) and len(value) > 50:
                                reports[key] = value
                        logger.info(f"📊 降级：从decision中提取到 {len(reports)} 个报告")
                except Exception as fallback_error:
                    logger.warning(f"⚠️ 降级提取也失败: {fallback_error}")

            # 🔥 Format decision data (refer to the implementation of web directory)
            formatted_decision = {}
            try:
                if isinstance(decision, dict):
                    # Handle validation price (history field target_price is for compatibility only)
                    target_price = decision.get('target_price')
                    if target_price is not None and target_price != 'N/A':
                        try:
                            if isinstance(target_price, str):
                                # Remove currency symbols and spaces
                                clean_price = target_price.replace('$', '').replace('¥', '').replace('￥', '').strip()
                                target_price = float(clean_price) if clean_price and clean_price != 'None' else None
                            elif isinstance(target_price, (int, float)):
                                target_price = float(target_price)
                            else:
                                target_price = None
                        except (ValueError, TypeError):
                            target_price = None
                    else:
                        target_price = None

                    # Convert English/old research conclusions into Chinese compliance terms
                    action_translation = {
                        'BUY': '乐观',
                        'SELL': '审慎',
                        'HOLD': '中性',
                        'buy': '乐观',
                        'sell': '审慎',
                        'hold': '中性',
                        '买入': '乐观',
                        '卖出': '审慎',
                        '持有': '中性',
                        '看涨': '乐观',
                        '看跌': '审慎',
                    }
                    action = decision.get('action', '中性')
                    chinese_action = action_translation.get(action, action)

                    formatted_decision = {
                        'action': chinese_action,
                        'confidence': decision.get('confidence', 0.5),
                        'risk_score': decision.get('risk_score', 0.3),
                        'target_price': target_price,
                        'reasoning': decision.get('reasoning', '暂无分析推理')
                    }

                    logger.info(f"🎯 [DEBUG] formatted decision: {formatted_decision}")
                else:
                    # Handle other types
                    formatted_decision = {
                        'action': '中性',
                        'confidence': 0.5,
                        'risk_score': 0.3,
                        'target_price': None,
                        'reasoning': '暂无分析推理'
                    }
                    logger.warning(f"⚠️ Decision Not a dictionary type: {type(decision)}")
            except Exception as e:
                logger.error(f"❌ Format decision failed: {e}")
                formatted_decision = {
                    'action': '中性',
                    'confidence': 0.5,
                    'risk_score': 0.3,
                    'target_price': None,
                    'reasoning': '暂无分析推理'
                }

            # 🔥 Generate summary and recommendation
            summary = ""
            recommendation = ""

            # 1. Prioritize extracting summary from final_trade_decision in reports (consistent with web directory)
            if isinstance(reports, dict) and 'final_trade_decision' in reports:
                final_decision_content = reports['final_trade_decision']
                if isinstance(final_decision_content, str) and len(final_decision_content) > 50:
                    # Extract the first 200 characters as a summary (exactly the same as the web directory)
                    summary = final_decision_content[:200].replace('#', '').replace('*', '').strip()
                    if len(final_decision_content) > 200:
                        summary += "..."
                    logger.info(f"📝 [SUMMARY] 从final_trade_decision提取摘要: {len(summary)}字符")

            # 2. If there is no final_trade_decision, extract it from state
            if not summary and isinstance(state, dict):
                final_decision = state.get('final_trade_decision', '')
                if isinstance(final_decision, str) and len(final_decision) > 50:
                    summary = final_decision[:200].replace('#', '').replace('*', '').strip()
                    if len(final_decision) > 200:
                        summary += "..."
                    logger.info(f"📝 [SUMMARY] 从state.final_trade_decision提取摘要: {len(summary)}字符")

            # 3. Generate recommendation (from reasoning of decision)
            if isinstance(formatted_decision, dict):
                action = formatted_decision.get('action', '中性')
                # 🔥 Compliance Modification: Use Compliance Terminology
                price_range = formatted_decision.get('price_analysis_range') or formatted_decision.get('target_price')
                reasoning = formatted_decision.get('reasoning', '')

                # 🔥 Compliance Modification: Generate Analytical Opinions (Excluding Specific Prices and Research Observations)
                recommendation_parts = []
                if action and action != '中性':
                    recommendation_parts.append(f"Analysis point of view:{action}")
                
                # 🔥 If reasoning is short (<100 characters) before adding it to the recommendation to avoid duplication
                if reasoning and len(reasoning) < 100 and reasoning != "暂无分析推理":
                    recommendation_parts.append(f"Analysis basis:{reasoning}")
                elif reasoning and reasoning != "暂无分析推理":
                    # If reasoning is longer, only the first 50 characters are extracted
                    short_reasoning = reasoning[:50] + "..." if len(reasoning) > 50 else reasoning
                    recommendation_parts.append(f"Analysis basis:{short_reasoning}")
                
                recommendation = "；".join(recommendation_parts) if recommendation_parts else "Please refer to the detailed analysis report."
                logger.info(f"💡 [RECOMMENDATION] 生成分析观点: {len(recommendation)}字符")

            # 4. If still not available, pull from other reports
            if not summary and isinstance(reports, dict):
                # Try extracting summaries from other reports
                for report_name, content in reports.items():
                    if isinstance(content, str) and len(content) > 100:
                        summary = content[:200].replace('#', '').replace('*', '').strip()
                        if len(content) > 200:
                            summary += "..."
                        logger.info(f"📝 [SUMMARY] 从{report_name}提取摘要: {len(summary)}字符")
                        break

            # 5. Last resort
            if not summary:
                summary = f"对{request.stock_code}的分析已完成，请查看详细报告。"
                logger.warning("⚠️ [SUMMARY] Use alternate summaries")

            if not recommendation or recommendation == "Analytical opinion: Neutral":
                recommendation = "Please refer to the detailed analysis report."
                logger.warning("⚠️ [RECOMMENDATION] Use backup suggestions")

            # Extract model information from decisions
            model_info = decision.get('model_info', 'Unknown') if isinstance(decision, dict) else 'Unknown'

            # Build results
            result = {
                "analysis_id": str(uuid.uuid4()),
                "stock_code": request.stock_code,
                "stock_symbol": request.stock_code,  # Add stock_symbol field to maintain compatibility
                "analysis_date": analysis_date,
                "summary": summary,
                "recommendation": recommendation,
                "confidence_score": formatted_decision.get("confidence", 0.0) if isinstance(formatted_decision, dict) else 0.0,
                "risk_level": "中等",  # Can be calculated based on risk_score
                "key_points": [],  # Key points can be extracted from reasoning
                # ❌ Remove the following fields (not returned by default, can be obtained through query parameters)
                # "detailed_analysis": decision,  # Changed to optional and not returned by default
                # "state": state,  # Changed to optional and not returned by default
                "execution_time": execution_time,
                "tokens_used": decision.get("tokens_used", 0) if isinstance(decision, dict) else 0,
                # Add analyst information
                "analysts": request.parameters.selected_analysts if request.parameters else [],
                "research_depth": request.parameters.research_depth if request.parameters else "快速",
                # Add extracted report content
                "reports": reports,
                # 🔥 Key fix: Add formatted decision field!
                "decision": formatted_decision,
                # 🔥 Add model information fields
                "model_info": model_info,
                # 🆕 Performance index data
                "performance_metrics": state.get("performance_metrics", {}) if isinstance(state, dict) else {}
            }

            logger.info(f"✅ [线程池] 分析完成: {task_id} - 耗时{execution_time:.2f}秒")

            # 🔍 Debugging: Examine the returned result structure
            logger.info(f"🔍 [DEBUG] Returns the key of result: {list(result.keys())}")
            logger.info(f"🔍 [DEBUG] Return result contains decision: {bool(result.get('decision'))}")
            if result.get('decision'):
                decision = result['decision']
                logger.info(f"🔍 [DEBUG] Return decision content: {decision}")

            return result

        except Exception as e:
            logger.error(f"❌ [thread pool] Analysis execution failed: {task_id} - {e}")

            # Format error messages into user-friendly prompts
            from ..utils.error_formatter import ErrorFormatter

            # Gather contextual information
            error_context = {}
            if request and hasattr(request, 'parameters') and request.parameters:
                if hasattr(request.parameters, 'quick_model'):
                    error_context['model'] = request.parameters.quick_model
                if hasattr(request.parameters, 'deep_model'):
                    error_context['model'] = request.parameters.deep_model

            # Formatting error
            formatted_error = ErrorFormatter.format_error(str(e), error_context)

            # Build user-friendly error messages
            user_friendly_error = (
                f"{formatted_error['title']}\n\n"
                f"{formatted_error['message']}\n\n"
                f"💡 {formatted_error['suggestion']}"
            )

            # Throw an exception with a friendly error message
            raise Exception(user_friendly_error) from e

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        logger.info(f"🔍 查询任务状态: {task_id}")
        logger.info(f"🔍 当前服务实例ID: {id(self)}")
        logger.info(f"🔍 内存管理器实例ID: {id(self.memory_manager)}")

        # Force use of global memory manager instance (temporary solution)
        global_memory_manager = get_memory_state_manager()
        logger.info(f"🔍 Global memory manager instance ID: {id(global_memory_manager)}")

        # Get statistics
        stats = await global_memory_manager.get_statistics()
        logger.info(f"📊 内存中任务统计: {stats}")

        result = await global_memory_manager.get_task_dict(task_id)
        if result:
            logger.info(f"✅ 找到任务: {task_id} - 状态: {result.get('status')}")

            # 🔍 Debugging: Check the fetched from memory result_data
            result_data = result.get('result_data')
            logger.debug(f"🔍 [GET_STATUS] result_data exist: {bool(result_data)}")
            if result_data:
                logger.debug(f"🔍 [GET_STATUS] result_data key: {list(result_data.keys())}")
                logger.debug(f"🔍 [GET_STATUS] result_data There is decision: {bool(result_data.get('decision'))}")
                if result_data.get('decision'):
                    logger.debug(f"🔍 [GET_STATUS] decision content: {result_data['decision']}")
            else:
                logger.debug("🔍 [GET_STATUS] result_data Is empty or does not exist (the task is running, this is normal)")

            # Get detailed progress information from Redis first
            redis_progress = get_progress_by_id(task_id)
            if redis_progress:
                logger.info(f"📊 [Redis Progress] Get detailed progress: {task_id}")

                # Extract the name and description of the current step from the steps array
                current_step_index = redis_progress.get('current_step', 0)
                steps = redis_progress.get('steps', [])
                current_step_name = redis_progress.get('current_step_name', '')
                current_step_description = redis_progress.get('current_step_description', '')

                # If name/description in Redis is empty, extract from steps array
                if not current_step_name and steps and 0 <= current_step_index < len(steps):
                    current_step_info = steps[current_step_index]
                    current_step_name = current_step_info.get('name', '')
                    current_step_description = current_step_info.get('description', '')
                    logger.info(f"📋 Extract the current step information from the steps array: index={current_step_index}, name={current_step_name}")

                # Merge Redis progress data
                result.update({
                    'progress': redis_progress.get('progress_percentage', result.get('progress', 0)),
                    'current_step': current_step_index,  # Use index instead of name
                    'current_step_name': current_step_name,  # step name
                    'current_step_description': current_step_description,  # Step description
                    'message': redis_progress.get('last_message', result.get('message', '')),
                    'elapsed_time': redis_progress.get('elapsed_time', 0),
                    'remaining_time': redis_progress.get('remaining_time', 0),
                    'estimated_total_time': redis_progress.get('estimated_total_time', result.get('estimated_duration', 300)),  # 🔧 Fix: Use estimated total duration in Redis
                    'steps': steps,
                    'start_time': result.get('start_time'),  # Keep the original format
                    'last_update': redis_progress.get('last_update', result.get('start_time'))
                })
            else:
                # If not available in Redis, try to get it from the in-memory progress tracker
                if task_id in self._progress_trackers:
                    progress_tracker = self._progress_trackers[task_id]
                    progress_data = progress_tracker.to_dict()

                    # Details of merge progress tracker
                    result.update({
                        'progress': progress_data['progress'],
                        'current_step': progress_data['current_step'],
                        'message': progress_data['message'],
                        'elapsed_time': progress_data['elapsed_time'],
                        'remaining_time': progress_data['remaining_time'],
                        'estimated_total_time': progress_data.get('estimated_total_time', 0),
                        'steps': progress_data['steps'],
                        'start_time': progress_data['start_time'],
                        'last_update': progress_data['last_update']
                    })
                    logger.info(f"📊 Merge in-memory progress tracker data: {task_id}")
                else:
                    logger.info(f"⚠️ 未找到进度信息: {task_id}")
        else:
            logger.warning(f"❌ 未找到任务: {task_id}")

        return result

    async def list_all_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 999999,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all task lists (not limited to users)
        - Merge in-memory and MongoDB data
        - Sort by start time in descending order
        - By default, all records are returned, and paging is handled by the front end.
        """
        try:
            task_status = None
            if status:
                try:
                    status_mapping = {
                        "processing": "running",
                        "pending": "pending",
                        "completed": "completed",
                        "failed": "failed",
                        "cancelled": "cancelled"
                    }
                    mapped_status = status_mapping.get(status, status)
                    task_status = TaskStatus(mapped_status)
                except ValueError:
                    logger.warning(f"⚠️ [Tasks] Invalid status value: {status}")
                    task_status = None

            # 1) Read all tasks from memory
            logger.info(f"📋 [Tasks] Prepare to read all tasks from memory: status={status}, limit={limit}, offset={offset}")
            tasks_in_mem = await self.memory_manager.list_all_tasks(
                status=task_status,
                limit=limit * 2,
                offset=0
            )
            logger.info(f"📋 [Tasks] Memory return quantity: {len(tasks_in_mem)}")

            # 2) Read tasks from MongoDB
            db = get_mongo_db()
            collection = db["analysis_tasks"]

            query = {}
            if task_status:
                query["status"] = task_status.value

            count = await collection.count_documents(query)
            logger.info(f"📋 [Tasks] MongoDB total number of tasks: {count}")

            cursor = collection.find(query).sort("start_time", -1).limit(limit * 2)
            tasks_from_db = []
            async for doc in cursor:
                doc.pop("_id", None)
                tasks_from_db.append(doc)

            logger.info(f"📋 [Tasks] MongoDB Return quantity: {len(tasks_from_db)}")

            # 3) Merge tasks (memory first)
            task_dict = {}

            # First add the tasks in MongoDB
            for task in tasks_from_db:
                task_id = task.get("task_id")
                if task_id:
                    task_dict[task_id] = task

            # Then add an in-memory task (overwriting the task of the same name in MongoDB)
            for task in tasks_in_mem:
                task_id = task.get("task_id")
                if task_id:
                    task_dict[task_id] = task

            # Convert to list and sort by time
            merged_tasks = list(task_dict.values())
            merged_tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)

            # Pagination
            results = merged_tasks[offset:offset + limit]

            # Complete stock names for results
            results = self._enrich_stock_names(results)
            logger.info(f"📋 [Tasks] 合并后返回数量: {len(results)} (内存: {len(tasks_in_mem)}, MongoDB: {count})")
            return results
        except Exception as outer_e:
            logger.error(f"❌ list_all_tasks Outer layer anomaly: {outer_e}", exc_info=True)
            return []

    async def list_user_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 999999,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get user task list
        - For processing status: read from memory first (real-time progress)
        - For completed/failed/all status: merge in-memory and MongoDB data
        - By default, all records are returned, and paging is handled by the front end.
        """
        try:
            task_status = None
            if status:
                try:
                    # What the front end passes is "processing", But TaskStatus uses "running"
                    # Need to do mapping conversion
                    status_mapping = {
                        "processing": "running",  # Front-end uses processing, memory usage running
                        "pending": "pending",
                        "completed": "completed",
                        "failed": "failed",
                        "cancelled": "cancelled"
                    }
                    mapped_status = status_mapping.get(status, status)
                    task_status = TaskStatus(mapped_status)
                except ValueError:
                    logger.warning(f"⚠️ [Tasks] Invalid status value: {status}")
                    task_status = None

            # 1) Read tasks from memory
            logger.info(f"📋 [Tasks] Prepare task to read from memory: user_id={user_id}, status={status} (mapped to {task_status}), limit={limit}, offset={offset}")
            tasks_in_mem = await self.memory_manager.list_user_tasks(
                user_id=user_id,
                status=task_status,
                limit=limit * 2,  # Read more and merge them later to remove duplicates.
                offset=0  # There are not many tasks in the memory, read them all
            )
            logger.info(f"📋 [Tasks] Memory return quantity: {len(tasks_in_mem)}")

            # 2) 🔧 For processing/running status, MongoDB data needs to be merged to get the latest progress
            # Because graph_progress_callback may directly update MongoDB, and the in-memory data may be old

            # 3) Read historical tasks from MongoDB (for merging or checking)
            logger.info("📋 [Tasks] Read historical tasks from MongoDB")
            mongo_tasks: List[Dict[str, Any]] = []
            count = 0
            try:
                db = get_mongo_db()

                # user_id May be a string or ObjectId, for compatibility
                uid_candidates: List[Any] = [user_id]

                # Special treatment for admin users
                if str(user_id) == 'admin':
                    # admin Users: Add fixed ObjectId and string form
                    try:
                        from bson import ObjectId
                        admin_oid_str = '507f1f77bcf86cd799439011'
                        uid_candidates.append(ObjectId(admin_oid_str))
                        uid_candidates.append(admin_oid_str)  # Compatible with string storage
                        logger.info(f"📋 [Tasks] admin user query, candidate ID: ['admin', ObjectId('{admin_oid_str}'), '{admin_oid_str}']")
                    except Exception as e:
                        logger.warning(f"⚠️ [Tasks] admin User ObjectId creation failed: {e}")
                else:
                    # Normal users: try converting to ObjectId
                    try:
                        from bson import ObjectId
                        uid_candidates.append(ObjectId(user_id))
                        logger.debug(f"📋 [Tasks] User ID has been converted to ObjectId: {user_id}")
                    except Exception as conv_err:
                        logger.warning(f"⚠️ [Tasks] User ID conversion to ObjectId failed, matching by string: {conv_err}")

                # Compatible with both user_id and user field names
                base_condition = {"$in": uid_candidates}
                or_conditions: List[Dict[str, Any]] = [
                    {"user_id": base_condition},
                    {"user": base_condition}
                ]
                query = {"$or": or_conditions}

                if task_status:
                    # Use the mapped status value (the value of the TaskStatus enumeration)
                    query["status"] = task_status.value
                    logger.info(f"📋 [Tasks] Add status filter: {task_status.value}")

                logger.info(f"📋 [Tasks] MongoDB Query conditions: {query}")
                # Read more data for merging
                cursor = db.analysis_tasks.find(query).sort("created_at", -1).limit(limit * 2)
                async for doc in cursor:
                    count += 1
                    # Compatible with user_id or user fields
                    user_field_val = doc.get("user_id", doc.get("user"))
                    # 🔧 Compatible with multiple stock code field names:symbol, stock_code, stock_symbol
                    stock_code_value = doc.get("symbol") or doc.get("stock_code") or doc.get("stock_symbol")
                    item = {
                        "task_id": doc.get("task_id"),
                        "user_id": str(user_field_val) if user_field_val is not None else None,
                        "symbol": stock_code_value,  # 🔧 Add symbol field (front-end priority)
                        "stock_code": stock_code_value,  # 🔧 Compatible fields
                        "stock_symbol": stock_code_value,  # 🔧 Compatible fields
                        "stock_name": doc.get("stock_name"),
                        "status": str(doc.get("status", "pending")),
                        "progress": int(doc.get("progress", 0) or 0),
                        "message": doc.get("message", ""),
                        "current_step": doc.get("current_step", ""),
                        "start_time": doc.get("started_at") or doc.get("created_at"),
                        "end_time": doc.get("completed_at"),
                        "parameters": doc.get("parameters", {}),
                        "execution_time": doc.get("execution_time"),
                        "tokens_used": doc.get("tokens_used"),
                        # For compatibility with the front end, the field name of memory_manager is used here.
                        "result_data": doc.get("result"),
                    }
                    # Convert time format to ISO string (add time zone information)
                    for k in ("start_time", "end_time"):
                        if item.get(k) and hasattr(item[k], "isoformat"):
                            dt = item[k]
                            # In the case of naive datetime (no time zone information), it is assumed to be UTC+8
                            if dt.tzinfo is None:
                                from datetime import timezone, timedelta
                                china_tz = timezone(timedelta(hours=8))
                                dt = dt.replace(tzinfo=china_tz)
                            item[k] = dt.isoformat()
                    mongo_tasks.append(item)

                logger.info(f"📋 [Tasks] MongoDB Return quantity: {count}")
            except Exception as mongo_e:
                logger.error(f"❌ MongoDB Failed to query task list: {mongo_e}", exc_info=True)
                # MongoDB Query failed, continue to use memory data

            # 4) Merge memory and MongoDB data to remove duplicates
            # 🔧 For processing/running status, progress data in MongoDB is preferred
            # Because graph_progress_callback directly updates MongoDB, and the in-memory data may be old
            task_dict = {}

            # First add tasks in memory
            for task in tasks_in_mem:
                task_id = task.get("task_id")
                if task_id:
                    task_dict[task_id] = task

            # Add tasks in MongoDB
            # For processing/running state, use progress data from MongoDB (updated)
            # For other states, skip if already in memory (memory first)
            for task in mongo_tasks:
                task_id = task.get("task_id")
                if not task_id:
                    continue

                # If the task already exists in memory
                if task_id in task_dict:
                    mem_task = task_dict[task_id]
                    mongo_task = task

                    # If it is processing/running state, use the progress data in MongoDB
                    if mongo_task.get("status") in ["processing", "running"]:
                        # Keep basic information in memory, but update progress-related fields
                        mem_task["progress"] = mongo_task.get("progress", mem_task.get("progress", 0))
                        mem_task["message"] = mongo_task.get("message", mem_task.get("message", ""))
                        mem_task["current_step"] = mongo_task.get("current_step", mem_task.get("current_step", ""))
                        logger.debug(f"🔄 [Tasks] Update task progress: {task_id}, progress={mem_task['progress']}%")
                else:
                    # If there is no memory, add the task in MongoDB directly.
                    task_dict[task_id] = task

            # Convert to list and sort by time
            merged_tasks = list(task_dict.values())
            merged_tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)

            # Pagination
            results = merged_tasks[offset:offset + limit]

            # 🔥 Process time zone information uniformly (ensure all time fields have time zone identifiers)
            from datetime import timezone, timedelta
            china_tz = timezone(timedelta(hours=8))

            for task in results:
                for time_field in ("start_time", "end_time", "created_at", "started_at", "completed_at"):
                    value = task.get(time_field)
                    if value:
                        # If it is a datetime object
                        if hasattr(value, "isoformat"):
                            # If it is naive datetime, add time zone information
                            if value.tzinfo is None:
                                value = value.replace(tzinfo=china_tz)
                            task[time_field] = value.isoformat()
                        # If it is a string and there is no time zone identifier, add the time zone identifier
                        elif isinstance(value, str) and value and not value.endswith(('Z', '+08:00', '+00:00')):
                            # Check if it is a time string in ISO format
                            if 'T' in value or ' ' in value:
                                task[time_field] = value.replace(' ', 'T') + '+08:00'

            # Complete stock names for results
            results = self._enrich_stock_names(results)
            logger.info(f"📋 [Tasks] 合并后返回数量: {len(results)} (内存: {len(tasks_in_mem)}, MongoDB: {count})")
            return results
        except Exception as outer_e:
            logger.error(f"❌ list_user_tasks Outer layer anomaly: {outer_e}", exc_info=True)
            return []

    async def cleanup_zombie_tasks(self, max_running_hours: int = 2) -> Dict[str, Any]:
        """Clean up zombie tasks (tasks that have been in processing/running state for a long time)

        Args:
            max_running_hours: Maximum running time (hours), tasks exceeding this time will be marked as failed

        Returns:
            Clean up result statistics
        """
        try:
            # 1) Clean up zombie tasks in memory
            memory_cleaned = await self.memory_manager.cleanup_zombie_tasks(max_running_hours)

            # 2) Cleaning up zombie tasks in MongoDB
            db = get_mongo_db()
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=max_running_hours)

            # Find tasks that have been in processing state for a long time
            zombie_filter = {
                "status": {"$in": ["processing", "running", "pending"]},
                "$or": [
                    {"started_at": {"$lt": cutoff_time}},
                    {"created_at": {"$lt": cutoff_time, "started_at": None}}
                ]
            }

            # Update to failed status
            update_result = await db.analysis_tasks.update_many(
                zombie_filter,
                {
                    "$set": {
                        "status": "failed",
                        "last_error": f"任务超时（运行时间超过 {max_running_hours} 小时）",
                        "completed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            mongo_cleaned = update_result.modified_count

            logger.info(f"🧹 Zombie mission cleanup completed: memory={memory_cleaned}, MongoDB={mongo_cleaned}")

            return {
                "success": True,
                "memory_cleaned": memory_cleaned,
                "mongo_cleaned": mongo_cleaned,
                "total_cleaned": memory_cleaned + mongo_cleaned,
                "max_running_hours": max_running_hours
            }

        except Exception as e:
            logger.error(f"❌ 清理僵尸任务失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "memory_cleaned": 0,
                "mongo_cleaned": 0,
                "total_cleaned": 0
            }

    async def get_zombie_tasks(self, max_running_hours: int = 2) -> List[Dict[str, Any]]:
        """Get the list of zombie tasks (does not perform cleanup, only queries)

        Args:
            max_running_hours: Maximum run time (hours)

        Returns:
            Zombie mission list
        """
        try:
            db = get_mongo_db()
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=max_running_hours)

            # Find tasks that have been in processing state for a long time
            zombie_filter = {
                "status": {"$in": ["processing", "running", "pending"]},
                "$or": [
                    {"started_at": {"$lt": cutoff_time}},
                    {"created_at": {"$lt": cutoff_time, "started_at": None}}
                ]
            }

            cursor = db.analysis_tasks.find(zombie_filter).sort("created_at", -1)
            zombie_tasks = []

            async for doc in cursor:
                task = {
                    "task_id": doc.get("task_id"),
                    "user_id": str(doc.get("user_id", doc.get("user"))),
                    "stock_code": doc.get("stock_code"),
                    "stock_name": doc.get("stock_name"),
                    "status": doc.get("status"),
                    "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
                    "started_at": doc.get("started_at").isoformat() if doc.get("started_at") else None,
                    "running_hours": None
                }

                # Calculate run time
                start_time = doc.get("started_at") or doc.get("created_at")
                if start_time:
                    running_seconds = (datetime.utcnow() - start_time).total_seconds()
                    task["running_hours"] = round(running_seconds / 3600, 2)

                zombie_tasks.append(task)

            logger.info(f"📋 查询到 {len(zombie_tasks)} 个僵尸任务")
            return zombie_tasks

        except Exception as e:
            logger.error(f"❌ 查询僵尸任务失败: {e}", exc_info=True)
            return []



    async def _update_task_status(
        self,
        task_id: str,
        status: AnalysisStatus,
        progress: int,
        error_message: str = None
    ):
        """更新任务状态"""
        try:
            db = get_mongo_db()
            update_data = {
                "status": status,
                "progress": progress,
                "updated_at": datetime.utcnow()
            }

            if status == AnalysisStatus.PROCESSING and progress == 10:
                update_data["started_at"] = datetime.utcnow()
            elif status == AnalysisStatus.COMPLETED:
                update_data["completed_at"] = datetime.utcnow()
            elif status == AnalysisStatus.FAILED:
                update_data["last_error"] = error_message
                update_data["completed_at"] = datetime.utcnow()

            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": update_data}
            )

            logger.debug(f"📊 任务状态已更新: {task_id} -> {status} ({progress}%)")

        except Exception as e:
            logger.error(f"❌ 更新任务状态失败: {task_id} - {e}")

    async def _save_analysis_result(self, task_id: str, result: Dict[str, Any]):
        """保存分析结果（原始方法）"""
        try:
            db = get_mongo_db()
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": {"result": result}}
            )
            logger.debug(f"💾 分析结果已保存: {task_id}")
        except Exception as e:
            logger.error(f"❌ 保存分析结果失败: {task_id} - {e}")

    async def _save_analysis_result_web_style(self, task_id: str, result: Dict[str, Any]):
        """Save analysis results - use the web directory to save to the analysis_reports collection

        Use unified report saving tool functions
        """
        try:
            from app.utils.report_saver import extract_reports_from_state, save_analysis_report
            from datetime import datetime

            db = get_mongo_db()
            stock_symbol = result.get('stock_symbol') or result.get('stock_code', 'UNKNOWN')

            # 🔥 Use unified report extraction functions
            reports = {}
            if 'state' in result:
                try:
                    state = result['state']
                    reports = extract_reports_from_state(state)
                except Exception as e:
                    logger.warning(f"⚠️ An error occurred while processing reports in state: {e}")
                    # Downgrade to extract from detailed_analysis
                    if 'detailed_analysis' in result:
                        try:
                            detailed_analysis = result['detailed_analysis']
                            if isinstance(detailed_analysis, dict):
                                for key, value in detailed_analysis.items():
                                    if isinstance(value, str) and len(value) > 50:
                                        reports[key] = value
                                logger.info(f"📊 降级：从detailed_analysis中提取到 {len(reports)} 个报告")
                        except Exception as fallback_error:
                            logger.warning(f"⚠️ 降级提取也失败: {fallback_error}")

            # 🔥 Infer market type based on stock symbol
            from tradingagents.utils.stock_utils import StockUtils
            market_info = StockUtils.get_market_info(stock_symbol)
            market_type_map = {
                "china_a": "A股",
                "hong_kong": "港股",
                "us": "美股",
                "unknown": "A股"  # Default is A shares
            }
            market_type = market_type_map.get(market_info.get("market", "unknown"), "A股")
            logger.info(f"📊 推断市场类型: {stock_symbol} -> {market_type}")

            # 🔥 Get stock name
            stock_name = stock_symbol  # Use stock symbol by default
            try:
                if market_info.get("market") == "china_a":
                    if _simple_analysis_service_is_cn_etf_symbol(stock_symbol):
                        cached_name = _get_cached_security_name(stock_symbol)
                        if cached_name:
                            stock_name = cached_name
                            logger.info(f"✅ 获取ETF名称: {stock_symbol} -> {stock_name}")
                        else:
                            stock_name = f"ETF{stock_symbol}"
                    # A Stocks: Use a unified interface to obtain stock information
                    else:
                        from tradingagents.dataflows.interface import get_china_stock_info_unified
                        stock_info = get_china_stock_info_unified(stock_symbol)
                        logger.debug(f"📊 获取股票信息返回: {stock_info[:200] if stock_info else 'None'}...")

                        if stock_info and "股票名称:" in stock_info:
                            stock_name = stock_info.split("股票名称:")[1].split("\n")[0].strip()
                            logger.info(f"✅ 获取A股名称: {stock_symbol} -> {stock_name}")
                        else:
                            # Downgrade scenario: Try getting it directly from the data source manager
                            logger.warning(f"⚠️ Unable to parse stock name from unified interface: {stock_symbol}, Try a downgrade solution")
                            try:
                                from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                                info_dict = get_info_dict(stock_symbol)
                                if info_dict and info_dict.get('name'):
                                    stock_name = info_dict['name']
                                    logger.info(f"✅ The downgrade plan successfully obtained the stock name: {stock_symbol} -> {stock_name}")
                            except Exception as fallback_e:
                                logger.error(f"❌ 降级方案也失败: {fallback_e}")

                elif market_info.get("market") == "hong_kong":
                    # Hong Kong stocks: Use improved Hong Kong stocks tools
                    try:
                        from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                        stock_name = get_hk_company_name_improved(stock_symbol)
                        logger.info(f"📊 获取港股名称: {stock_symbol} -> {stock_name}")
                    except Exception:
                        clean_ticker = stock_symbol.replace('.HK', '').replace('.hk', '')
                        stock_name = f"港股{clean_ticker}"
                elif market_info.get("market") == "us":
                    # US stocks: using simple mapping
                    us_stock_names = {
                        'AAPL': '苹果公司', 'TSLA': '特斯拉', 'NVDA': '英伟达',
                        'MSFT': '微软', 'GOOGL': '谷歌', 'AMZN': '亚马逊',
                        'META': 'Meta', 'NFLX': '奈飞'
                    }
                    stock_name = us_stock_names.get(stock_symbol.upper(), f"美股{stock_symbol}")
                    logger.info(f"📊 获取美股名称: {stock_symbol} -> {stock_name}")
            except Exception as e:
                logger.warning(f"⚠️ 获取股票名称失败: {stock_symbol} - {e}")
                stock_name = stock_symbol

            # 🔥 Use unified report saving function
            analysis_id = await save_analysis_report(
                db=db,
                stock_symbol=stock_symbol,
                stock_name=stock_name,
                market_type=market_type,
                model_info=result.get("model_info", "Unknown"),
                reports=reports,
                decision=result.get("decision", {}),
                recommendation=result.get("recommendation", ""),
                confidence_score=result.get("confidence_score", 0.0),
                risk_level=result.get("risk_level", "中等"),
                summary=result.get("summary", ""),
                key_points=result.get("key_points", []),
                task_id=task_id,
                execution_time=result.get("execution_time", 0),
                tokens_used=result.get("tokens_used", 0),
                analysts=result.get("analysts", []),
                research_depth=str(result.get("research_depth", 1)),
                analysis_date=None,  # Use default timestamp
                source="api",
                engine="v2",
                user_id=None,
                performance_metrics=result.get("performance_metrics", {})
            )

            logger.info(f"✅ Analysis report has been saved to MongoDB analysis_reports: {analysis_id}")

            # Also update the result field in the analysis_tasks collection to maintain API compatibility.
            # 🔥 Note: The result field saved to the database here contains complete data (for debugging/auditing)
            # However, when the API returns, it will decide whether to include state and detailed_analysis
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": {"result": {
                    "analysis_id": analysis_id,
                    "stock_symbol": stock_symbol,
                    "stock_code": result.get('stock_code', stock_symbol),
                    "analysis_date": result.get('analysis_date'),
                    "summary": result.get("summary", ""),
                    "recommendation": result.get("recommendation", ""),
                    "confidence_score": result.get("confidence_score", 0.0),
                    "risk_level": result.get("risk_level", "中等"),
                    "key_points": result.get("key_points", []),
                    # 🔥 Keep detailed_analysis and state in database (for debugging/auditing)
                    # However, when the API returns, it will be decided based on the query parameters whether to include
                    "detailed_analysis": result.get("detailed_analysis", {}),
                    "state": result.get("state", {}),
                    "execution_time": result.get("execution_time", 0),
                    "tokens_used": result.get("tokens_used", 0),
                    "reports": reports,  # Contains extracted report content (cleaned of duplicate data)
                    # 🔥 Key fix: Add formatted decision field!
                    "decision": result.get("decision", {})
                }}}
            )
            logger.info(f"💾 Analysis results saved (web style): {task_id}")

        except Exception as e:
            logger.error(f"❌ 保存分析结果失败: {task_id} - {e}")
            # Downgrade to simple save
            try:
                simple_result = {
                    'task_id': task_id,
                    'success': result.get('success', True),
                    'error': str(e),
                    'completed_at': datetime.utcnow().isoformat()
                }
                await db.analysis_tasks.update_one(
                    {"task_id": task_id},
                    {"$set": {"result": simple_result}}
                )
                logger.info(f"💾 使用简化结果保存: {task_id}")
            except Exception as fallback_error:
                logger.error(f"❌ 简化保存也失败: {task_id} - {fallback_error}")

    async def _save_analysis_results_complete(self, task_id: str, result: Dict[str, Any]):
        """Complete analysis result storage - completely adopts the dual saving method of web directory"""
        try:
            # Debugging: print all keys in result
            logger.info(f"🔍 [Debugging] result all keys in: {list(result.keys())}")
            logger.info(f"🔍 [Debugging] stock_code: {result.get('stock_code', 'NOT_FOUND')}")
            logger.info(f"🔍 [Debugging] stock_symbol: {result.get('stock_symbol', 'NOT_FOUND')}")

            # Prefer stock_symbol, if not available then use stock_code
            stock_symbol = result.get('stock_symbol') or result.get('stock_code', 'UNKNOWN')
            logger.info(f"💾 Start saving analysis results completely: {stock_symbol}")

            # 1. Save sub-module reports to local directory
            logger.info("📁 [Save locally] Start saving sub-module reports to the local directory")
            local_files = await self._save_modular_reports_to_data_dir(result, stock_symbol)
            if local_files:
                logger.info(f"✅ [本地保存] 已保存 {len(local_files)} 个本地报告文件")
                for module, path in local_files.items():
                    logger.info(f"  - {module}: {path}")
            else:
                logger.warning("⚠️ [Save locally] Failed to save local report file")

            # 2. Save analysis report to database
            logger.info("🗄️ [Database save] Start saving the analysis report to the database")
            await self._save_analysis_result_web_style(task_id, result)
            logger.info("✅ [Database save] The analysis report has been successfully saved to the database")

            # 3. Record saving results
            if local_files:
                logger.info("✅ Analysis reports are saved to database and local files")
            else:
                logger.warning("⚠️ The database was saved successfully, but the local file failed.")

        except Exception as save_error:
            logger.error(f"❌ [save completely] An error occurred while saving the analysis report: {str(save_error)}")
            # Downgrade to database only save
            try:
                await self._save_analysis_result_web_style(task_id, result)
                logger.info(f"💾 Downgrade saved successfully (Database only): {task_id}")
            except Exception as fallback_error:
                logger.error(f"❌ 降级保存也失败: {task_id} - {fallback_error}")

    async def _save_modular_reports_to_data_dir(self, result: Dict[str, Any], stock_symbol: str) -> Dict[str, str]:
        """Save sub-module reports to the data directory - completely using the file structure of the web directory"""
        try:
            import os
            from pathlib import Path
            from datetime import datetime
            import json

            # Get the project root directory
            project_root = Path(__file__).parent.parent.parent

            # Determine the results directory path - consistent with the web directory
            results_dir_env = os.getenv("TRADINGAGENTS_RESULTS_DIR")
            if results_dir_env:
                if not os.path.isabs(results_dir_env):
                    results_dir = project_root / results_dir_env
                else:
                    results_dir = Path(results_dir_env)
            else:
                # By default, the data directory is used instead of the results directory.
                results_dir = project_root / "data" / "analysis_results"

            # Create a stock-specific directory - exactly according to the structure of a web directory
            analysis_date_raw = result.get('analysis_date', datetime.now())

            # Make sure analysis_date is in string format
            if isinstance(analysis_date_raw, datetime):
                analysis_date_str = analysis_date_raw.strftime('%Y-%m-%d')
            elif isinstance(analysis_date_raw, str):
                # If already a string, check the format
                try:
                    # Try parsing the date string, making sure it is in the correct format
                    parsed_date = datetime.strptime(analysis_date_raw, '%Y-%m-%d')
                    analysis_date_str = analysis_date_raw
                except ValueError:
                    # If the format is incorrect, use the current date
                    analysis_date_str = datetime.now().strftime('%Y-%m-%d')
            else:
                # Other types, use the current date
                analysis_date_str = datetime.now().strftime('%Y-%m-%d')

            stock_dir = results_dir / stock_symbol / analysis_date_str
            reports_dir = stock_dir / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            # Create message_tool.log file - consistent with the web directory
            log_file = stock_dir / "message_tool.log"
            log_file.touch(exist_ok=True)

            logger.info(f"📁 创建分析结果目录: {reports_dir}")
            logger.info(f"🔍 [调试] analysis_date_raw 类型: {type(analysis_date_raw)}, 值: {analysis_date_raw}")
            logger.info(f"🔍 [Debugging] analysis_date_str: {analysis_date_str}")
            logger.info(f"🔍 [调试] 完整路径: {os.path.normpath(str(reports_dir))}")

            state = result.get('state', {})
            saved_files = {}

            # Define reporting module mapping - exactly as defined by the web directory
            report_modules = {
                # 🆕 Macro analysis report (save first)
                'index_report': {
                    'filename': 'index_report.md',
                    'title': f'{stock_symbol} 大盘指数分析报告',
                    'state_key': 'index_report'
                },
                'sector_report': {
                    'filename': 'sector_report.md',
                    'title': f'{stock_symbol} 行业板块分析报告',
                    'state_key': 'sector_report'
                },
                # individual stock analysis report
                'market_report': {
                    'filename': 'market_report.md',
                    'title': f'{stock_symbol} 股票技术分析报告',
                    'state_key': 'market_report'
                },
                'sentiment_report': {
                    'filename': 'sentiment_report.md',
                    'title': f'{stock_symbol} 市场情绪分析报告',
                    'state_key': 'sentiment_report'
                },
                'news_report': {
                    'filename': 'news_report.md',
                    'title': f'{stock_symbol} 新闻事件分析报告',
                    'state_key': 'news_report'
                },
                'fundamentals_report': {
                    'filename': 'fundamentals_report.md',
                    'title': f'{stock_symbol} 基本面分析报告',
                    'state_key': 'fundamentals_report'
                },
                'investment_plan': {
                    'filename': 'investment_plan.md',
                    'title': f'{stock_symbol} 投资决策报告',
                    'state_key': 'investment_plan'
                },
                'trader_investment_plan': {
                    'filename': 'trader_investment_plan.md',
                    'title': f'{stock_symbol} 交易计划报告',
                    'state_key': 'trader_investment_plan'
                },
                'final_trade_decision': {
                    'filename': 'final_trade_decision.md',
                    'title': f'{stock_symbol} 最终分析结果',
                    'state_key': 'final_trade_decision'
                },
                'investment_debate_state': {
                    'filename': 'research_team_decision.md',
                    'title': f'{stock_symbol} 研究团队分析报告',
                    'state_key': 'investment_debate_state'
                },
                'risk_debate_state': {
                    'filename': 'risk_management_decision.md',
                    'title': f'{stock_symbol} 风险管理团队决策报告',
                    'state_key': 'risk_debate_state'
                }
            }

            # Save reports for each module - exactly as in the web directory
            for module_key, module_info in report_modules.items():
                try:
                    state_key = module_info['state_key']
                    if state_key in state:
                        # Extract module content
                        module_content = state[state_key]
                        if isinstance(module_content, str):
                            report_content = module_content
                        else:
                            report_content = str(module_content)

                        # Save to file - use the file name of the web directory
                        file_path = reports_dir / module_info['filename']
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(report_content)

                        saved_files[module_key] = str(file_path)
                        logger.info(f"✅ 保存模块报告: {file_path}")

                except Exception as e:
                    logger.warning(f"⚠️ 保存模块 {module_key} 失败: {e}")

            # Save the final research conclusion report - exactly as a web directory
            decision = result.get('decision', {})
            if decision:
                decision_content = f"# {stock_symbol} 最终研究结论\n\n"

                if isinstance(decision, dict):
                    decision_content += "## 市场分析\n\n"
                    decision_content += f"**分析观点**: {decision.get('action', 'N/A')}\n\n"
                    decision_content += f"**置信度**: {decision.get('confidence', 0):.1%}\n\n"
                    decision_content += f"**风险评分**: {decision.get('risk_score', 0):.1%}\n\n"
                    decision_content += f"**关键验证价位**: {decision.get('target_price', 'N/A')}\n\n"
                    decision_content += f"## 分析推理\n\n{decision.get('reasoning', '暂无分析推理')}\n\n"
                else:
                    decision_content += f"{str(decision)}\n\n"

                decision_file = reports_dir / "final_trade_decision.md"
                with open(decision_file, 'w', encoding='utf-8') as f:
                    f.write(decision_content)

                saved_files['final_trade_decision'] = str(decision_file)
                logger.info(f"✅ 保存最终研究结论: {decision_file}")

            # Save analysis metadata files - exactly like a web directory
            metadata = {
                'stock_symbol': stock_symbol,
                'analysis_date': analysis_date_str,
                'timestamp': datetime.now().isoformat(),
                'research_depth': result.get('research_depth', 1),
                'analysts': result.get('analysts', []),
                'status': 'completed',
                'reports_count': len(saved_files),
                'report_types': list(saved_files.keys())
            }

            metadata_file = reports_dir.parent / "analysis_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 保存分析元数据: {metadata_file}")
            logger.info(f"✅ 分模块报告保存完成，共保存 {len(saved_files)} 个文件")
            logger.info(f"📁 保存目录: {os.path.normpath(str(reports_dir))}")

            return saved_files

        except Exception as e:
            logger.error(f"❌ 保存分模块报告失败: {e}")
            import traceback
            logger.error(f"❌ 详细错误: {traceback.format_exc()}")
            return {}

# Duplicate get_task_status method removed, use in-memory version on line 469


# Global service instance
_analysis_service = None

def get_simple_analysis_service() -> SimpleAnalysisService:
    """获取分析服务实例"""
    global _analysis_service
    if _analysis_service is None:
        logger.info("🔧 [Singleton] Create a new SimpleAnalysisService instance")
        _analysis_service = SimpleAnalysisService()
    else:
        logger.info(f"🔧 [Singleton] Returns an existing SimpleAnalysisService instance: {id(_analysis_service)}")
    return _analysis_service

# === unified_analysis_engine.py ===
"""
Unified analytics engine

Provides a unified task execution interface and supports multiple execution engines:
- workflow: Workflow engine (recommended)
- legacy: old engine TradingAgentsGraph
- llm: Direct LLM call
"""

from typing import Dict, Any, Optional, Callable
import logging
from datetime import datetime

from app.models.analysis import UnifiedAnalysisTask, AnalysisTaskType, AnalysisStatus
try:
    from app.services.workflow_registry import AnalysisWorkflowRegistry
except ImportError:
    AnalysisWorkflowRegistry = None
from app.utils.timezone import now_tz
from core.workflow.default_workflow_provider import get_default_workflow_provider

logger = logging.getLogger(__name__)


class UnifiedAnalysisEngine:
    """Unified analytics engine
    
    Responsible for executing various types of analysis tasks and automatically selecting the appropriate execution engine
    
    Usage example:
        engine = UnifiedAnalysisEngine()
        result = await engine.execute_task(task, progress_callback)
    """
    
    def __init__(self):
        """初始化引擎"""
        self.logger = logger

    def _workflow_exists(self, workflow_id: Optional[str]) -> bool:
        """Check if the workflow exists in the system provisioning, database, or file system."""
        if not workflow_id:
            return False

        provider = get_default_workflow_provider()
        if provider.get_system_workflow(workflow_id) is not None:
            return True

        from core.api.workflow_api import WorkflowAPI

        try:
            return WorkflowAPI().get(workflow_id) is not None
        except Exception as exc:
            self.logger.warning(f"⚠️ Failed to verify workflow existence: workflow_id={workflow_id}, error={exc}")
            return False

    def _workflow_type_for_task(self, task_type: AnalysisTaskType, task_params: dict = None) -> str:
        """Map task types to workflow types."""
        # If there is a task_category tag, it is used first (general research tasks use STOCK_ANALYSIS as the carrier but are actually of general type)
        if task_params and task_params.get("task_category") == "general":
            return "general"
        mapping = {
            AnalysisTaskType.STOCK_ANALYSIS: "stock_analysis",
            AnalysisTaskType.ETF_ANALYSIS: "etf_analysis",
            AnalysisTaskType.POSITION_ANALYSIS: "position_analysis",
            AnalysisTaskType.TRADE_REVIEW: "trade_review",
        }
        return mapping.get(task_type, task_type.value if hasattr(task_type, "value") else str(task_type))

    def _resolve_workflow_id(self, task: UnifiedAnalysisTask, config) -> str:
        """Resolve the workflow ID that should be used for this task.

        Priority:
        1. The workflow_id specified explicitly by the task (e.g. /api/workflows/{id}/execute incoming)
        2. My analysis flow (the default workflow set by the user for the current task_type)
        3. Registry default configuration
        4. System hardcoded defaults
        """
        task_type = task.task_type
        if isinstance(task_type, str):
            task_type = AnalysisTaskType(task_type)

        workflow_type = self._workflow_type_for_task(task_type, task.task_params)

        # Priority 1: Task explicitly specified workflow_id
        explicit_workflow_id = task.workflow_id or task.task_params.get("workflow_id")
        if explicit_workflow_id:
            if self._workflow_exists(explicit_workflow_id):
                self.logger.info(f"📋 Workflow selection: Explicitly specified using tasks workflow_id={explicit_workflow_id}")
                return explicit_workflow_id
            self.logger.warning(
                f"⚠️ The workflow explicitly specified by the task does not exist and will fall back to my analysis flow configuration: workflow_id={explicit_workflow_id}"
            )

        # Priority 2: My Analysis Flow (the default workflow set by the user for the current task_type)
        if task_type in (
            AnalysisTaskType.STOCK_ANALYSIS,
            AnalysisTaskType.ETF_ANALYSIS,
            AnalysisTaskType.POSITION_ANALYSIS,
            AnalysisTaskType.TRADE_REVIEW,
        ):
            try:
                workflow_provider = get_default_workflow_provider()
                active_workflow_id = workflow_provider.get_active_workflow_id(workflow_type)
                if active_workflow_id:
                    if self._workflow_exists(active_workflow_id):
                        self.logger.info(f"📋 Workflow selection: Use my analytics flow configuration type={workflow_type}, workflow_id={active_workflow_id}")
                        return active_workflow_id
                    try:
                        workflow_provider.load_workflow(active_workflow_id)
                    except Exception as exc:
                        self.logger.warning(
                            f"⚠️ 我的分析流配置 {active_workflow_id} 无效: {exc}"
                        )
                    else:
                        self.logger.info(f"📋 Workflow selection: Use my analytics flow configuration type={workflow_type}, workflow_id={active_workflow_id}")
                        return active_workflow_id
                    self.logger.warning(
                        f"⚠️ My analysis flow configuration does not exist and will fall back to registry defaults: workflow_id={active_workflow_id}"
                    )
            except Exception as exc:
                self.logger.warning(f"⚠️ Failed to get my analytics flow configuration: {exc}")

        # Priority 3: Registry default configuration
        if self._workflow_exists(config.workflow_id):
            self.logger.info(f"📋 Workflow selection: Use registry default workflow_id={config.workflow_id}")
            return config.workflow_id

        # Priority 4: System hard-coded defaults
        fallback_workflow_id = get_default_workflow_provider().get_default_workflow_id_for_type(workflow_type)
        self.logger.warning(
            f"⚠️ All configurations are invalid and fall back to the system default workflow.: type={workflow_type}, workflow_id={fallback_workflow_id}"
        )
        return fallback_workflow_id


    async def execute_task(
        self,
        task: UnifiedAnalysisTask,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, Any]:
        """Perform analysis tasks
        
        Args:
            task: Unified analysis task objects
            progress_callback: Progress callback function callback(progress: int, message: str)
            
        Returns:
            Analysis result dictionary
            
        Raises:
            ValueError: The task type is not registered or the parameters are invalid
            RuntimeError: Execution failed
        """
        self.logger.info(f"🚀 开始执行任务: {task.task_id} (类型: {task.task_type})")
        
        # 1. Get process configuration
        # Make sure task_type is an enum type (probably a string when loading from database)
        task_type = task.task_type
        if isinstance(task_type, str):
            try:
                task_type = AnalysisTaskType(task_type)
            except ValueError:
                raise ValueError(f"无效的任务类型: {task_type}")
        
        config = AnalysisWorkflowRegistry.get_config(task_type)
        if not config:
            raise ValueError(f"未注册的任务类型: {task_type}")
        
        # 2. Validation parameters
        is_valid, error_msg = AnalysisWorkflowRegistry.validate_params(
            task.task_type,
            task.task_params
        )
        if not is_valid:
            raise ValueError(f"任务参数无效: {error_msg}")
        
        # 3. Select execution engine
        engine_type = self._select_engine(task.engine_type, config.default_engine)
        self.logger.info(f"📌 选择执行引擎: {engine_type}")
        
        # 4. Update task status
        task.status = AnalysisStatus.PROCESSING
        task.started_at = now_tz()
        task.current_step = f"使用 {engine_type} 引擎执行"
        task.progress = 5

        # Notify progress
        if progress_callback:
            await self._call_progress_callback(progress_callback, 5, f"开始使用 {engine_type} 引擎执行")

        # 5. Perform analysis
        try:
            if engine_type == "workflow":
                result = await self._execute_via_workflow(task, config, progress_callback)
            elif engine_type == "legacy":
                result = await self._execute_via_legacy(task, config, progress_callback)
            elif engine_type == "llm":
                result = await self._execute_via_llm(task, config, progress_callback)
            else:
                raise ValueError(f"不支持的引擎类型: {engine_type}")

            # 6. Update task status
            task.status = AnalysisStatus.COMPLETED
            task.completed_at = now_tz()
            task.result = result
            task.progress = 100

            if task.started_at:
                task.execution_time = (task.completed_at - task.started_at).total_seconds()

            # Notify progress
            if progress_callback:
                await self._call_progress_callback(progress_callback, 100, "任务执行完成")

            self.logger.info(f"✅ 任务执行成功: {task.task_id} (耗时: {task.execution_time:.2f}秒)")

            return result

        except Exception as e:
            # 🔥 Graceful handling: check if it is a cancellation exception

            if isinstance(e, TaskCancelledException):
                # Task cancellation is a normal operation and is not recorded as an error
                self.logger.info(f"🚫 任务已取消: {task.task_id}")
                # Just rethrow it and let the upper layer handle it
                raise

            # Other exceptions are real failures
            task.status = AnalysisStatus.FAILED
            task.completed_at = now_tz()
            task.error_message = str(e)

            if task.started_at:
                task.execution_time = (task.completed_at - task.started_at).total_seconds()

            self.logger.error(f"❌ 任务执行失败: {task.task_id} - {e}")
            raise RuntimeError(f"任务执行失败: {e}") from e
    
    async def _build_llm_config(
        self,
        quick_model: Optional[str],
        deep_model: Optional[str]
    ) -> Dict[str, Any]:
        """Get the complete LLM configuration from the database based on the model name

        Args:
            quick_model: Quickly analyze model names
            deep_model: In-depth analysis model name

        Returns:
            Complete configuration including provider, api_key, backend_url, etc.
        """
        if not quick_model and not deep_model:
            return {}

        from app.core.database import get_mongo_db

        db = get_mongo_db()

        # Get system configuration
        config_doc = await db.system_configs.find_one(
            {"is_active": True},
            sort=[("version", -1)]
        )

        if not config_doc or "llm_configs" not in config_doc:
            self.logger.warning("There is no LLM configuration in the database")
            return {}

        llm_configs = config_doc["llm_configs"]

        # Find matching model configurations
        target_model = quick_model or deep_model
        model_config = None

        for cfg in llm_configs:
            if cfg.get("model_name") == target_model and cfg.get("enabled", True):
                model_config = cfg
                break

        if not model_config:
            self.logger.warning(f"未找到模型配置: {target_model}")
            return {}

        # Get factory configuration
        provider_name = model_config.get("provider", "")
        provider_doc = await db.llm_providers.find_one({"name": provider_name})

        # 🔥 Determine API Key (Priority: Model Configuration > Factory configuration > environment variables)
        api_key = None
        model_api_key = model_config.get("api_key", "")
        if model_api_key and model_api_key.strip() and model_api_key != "your-api-key" and not model_api_key.startswith("sk-xxx"):
            api_key = model_api_key
            self.logger.info("✅ [LLM Configuration] Configured using models API Key")
        elif provider_doc:
            provider_api_key = provider_doc.get("api_key", "")
            if provider_api_key and provider_api_key.strip() and provider_api_key != "your-api-key" and not provider_api_key.startswith("sk-xxx"):
                api_key = provider_api_key
                self.logger.info("✅ [LLM Configuration] Use factory configured API Key")
        
        backend_url = model_config.get("api_base", "")
        if provider_doc and not backend_url:
            backend_url = provider_doc.get("default_base_url", "")

        # If the database does not have an API Key, try to get it from the environment variable
        if not api_key:
            import os
            env_key_map = {
                "openai": "OPENAI_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
                "dashscope": "DASHSCOPE_API_KEY",
                "google": "GOOGLE_API_KEY",
                "zhipu": "ZHIPU_API_KEY",
                "siliconflow": "SILICONFLOW_API_KEY",
            }
            env_name = env_key_map.get(provider_name.lower())
            if env_name:
                api_key = os.getenv(env_name)

        # 🔥 Get quick model configuration
        quick_model_config = None
        if quick_model:
            for cfg in llm_configs:
                if cfg.get("model_name") == quick_model and cfg.get("enabled", True):
                    quick_model_config = cfg
                    break
        
        # 🔥 Get depth model configuration
        deep_model_config = None
        if deep_model and deep_model != quick_model:
            for cfg in llm_configs:
                if cfg.get("model_name") == deep_model and cfg.get("enabled", True):
                    deep_model_config = cfg
                    break
        
        # If deep model configuration does not exist, use quick model configuration
        if not deep_model_config:
            deep_model_config = quick_model_config or model_config
        
        # Get the provider and api_key of the depth model (if different)
        deep_provider_name = provider_name
        deep_api_key = api_key
        deep_backend_url = backend_url
        
        if deep_model_config and deep_model_config != quick_model_config:
            deep_provider_name = deep_model_config.get("provider", provider_name)
            # 🔥 Determine the API Key of the depth model (Priority: Model Configuration > Factory configuration > environment variables)
            deep_model_api_key = deep_model_config.get("api_key", "")
            if deep_model_api_key and deep_model_api_key.strip() and deep_model_api_key != "your-api-key" and not deep_model_api_key.startswith("sk-xxx"):
                deep_api_key = deep_model_api_key
                self.logger.info("✅ [LLM Configuration] The depth model uses the model configuration API Key")
            elif deep_provider_name != provider_name:
                deep_provider_doc = await db.llm_providers.find_one({"name": deep_provider_name})
                if deep_provider_doc:
                    deep_provider_api_key = deep_provider_doc.get("api_key", "")
                    if deep_provider_api_key and deep_provider_api_key.strip() and deep_provider_api_key != "your-api-key" and not deep_provider_api_key.startswith("sk-xxx"):
                        deep_api_key = deep_provider_api_key
                        self.logger.info("✅ [LLM Configuration] The depth model uses the factory configured API Key")
                    deep_backend_url = deep_model_config.get("api_base", "") or deep_provider_doc.get("default_base_url", "")
            if not deep_api_key or deep_api_key.startswith("sk-xxx"):
                        import os
                        env_key_map = {
                            "openai": "OPENAI_API_KEY",
                            "deepseek": "DEEPSEEK_API_KEY",
                            "dashscope": "DASHSCOPE_API_KEY",
                            "google": "GOOGLE_API_KEY",
                            "zhipu": "ZHIPU_API_KEY",
                            "siliconflow": "SILICONFLOW_API_KEY",
                        }
                        env_name = env_key_map.get(deep_provider_name.lower())
                        if env_name:
                            deep_api_key = os.getenv(env_name) or deep_api_key
            else:
                deep_backend_url = deep_model_config.get("api_base", "") or backend_url
        
        result = {
            "llm_provider": provider_name,
            "quick_think_llm": quick_model or target_model,
            "deep_think_llm": deep_model or target_model,
            "backend_url": backend_url,
            "api_key": api_key,
            "quick_api_key": api_key,
            "deep_api_key": deep_api_key,
            "quick_temperature": (quick_model_config or model_config).get("temperature", 0.1),
            "quick_max_tokens": (quick_model_config or model_config).get("max_tokens", 2000),
            "quick_timeout": (quick_model_config or model_config).get("timeout", 60),
            "deep_temperature": deep_model_config.get("temperature", 0.1) if deep_model_config else (quick_model_config or model_config).get("temperature", 0.1),
            "deep_max_tokens": deep_model_config.get("max_tokens", 4000) if deep_model_config else (quick_model_config or model_config).get("max_tokens", 4000),
            "deep_timeout": deep_model_config.get("timeout", 120) if deep_model_config else (quick_model_config or model_config).get("timeout", 120),
            "deep_backend_url": deep_backend_url,  # 🔥 Always returns the depth model's backend_url
        }
        
        # If the deep model and fast model use different providers, add the provider information of the deep model
        if deep_provider_name != provider_name:
            result["deep_llm_provider"] = deep_provider_name

        self.logger.info(f"Get model configuration from database: provider={provider_name}, quick={quick_model}, deep={deep_model}")
        self.logger.info(f"  quick: temperature={result['quick_temperature']}, max_tokens={result['quick_max_tokens']}, timeout={result['quick_timeout']}")
        self.logger.info(f"  deep: temperature={result['deep_temperature']}, max_tokens={result['deep_max_tokens']}, timeout={result['deep_timeout']}")

        return result

    async def _call_progress_callback(
        self,
        callback: Optional[Callable],
        progress: int,
        message: str,
        **kwargs
    ):
        """Call progress callback (supports synchronous and asynchronous)"""
        if callback:
            import asyncio
            if asyncio.iscoroutinefunction(callback):
                await callback(progress, message, **kwargs)
            else:
                callback(progress, message, **kwargs)

    def _select_engine(self, requested_engine: str, default_engine: str) -> str:
        """Select execution engine

        Args:
            requested_engine: Requested engine type (auto/workflow/legacy/llm)
            default_engine: Default engine type

        Returns:
            Actual engine type used

        Raises:
            RuntimeError: When legacy engine is requested (deactivated)
        """
        # v3.0 The legacy engine has been deactivated
        if requested_engine == "legacy":
            raise RuntimeError(
                "[Deactivated] UnifiedAnalysisEngine._select_engine Reject legacy engines,"
                "Please use workflow or auto instead."
                "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
            )
        if requested_engine == "auto":
            # Defense: If the registry default engine is changed to legacy, force the change to workflow
            if default_engine == "legacy":
                self.logger.warning(
                    "⚠️ The default engine of the registry is legacy, which has been forcibly changed to workflow (legacy has been deactivated)"
                )
                return "workflow"
            return default_engine
        return requested_engine

    async def _inject_memory_facts(self, workflow_inputs: Dict[str, Any]) -> None:
        """Query the unexpired fact memory for this stock and inject workflow input (failure does not affect analysis).

        Fact memory source: intelligent assistant networking tool extraction (assistant_memory_facts collection),
        Match stock codes by symbol / related_terms and only take valid_until unexpired records.
        The injected text includes the collection date and source for the debate session (bull/bear) and risk assessment session.
         (risk_manager) As a reference for traceable materials (see consumer side) core/agents/base.py
        Fact memory injection whitelist).
        """
        try:
            ticker_val = str(workflow_inputs.get("ticker") or "").strip()
            if not ticker_val:
                return
            from datetime import datetime as _dt
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            now_iso = _dt.now().isoformat(timespec="seconds")
            cursor = (
                db["assistant_memory_facts"]
                .find(
                    {
                        "valid_until": {"$gte": now_iso},
                        "$or": [
                            {"symbol": ticker_val},
                            {"related_terms": ticker_val},
                        ],
                    }
                )
                .sort("fetched_at", -1)
                .limit(8)
            )
            docs = [doc async for doc in cursor]
            if not docs:
                return
            blocks = [
                " [External fact memory] The following facts come from real data that the intelligent assistant has previously obtained and verified through networking tools."
                " (Contains collection date and source, and has passed timeliness verification). It can be used as part of the reference material for this analysis."
                "The date of collection must be marked when citing; if it is inconsistent with the latest data obtained in this analysis, this data shall prevail."
            ]
            for i, doc in enumerate(docs, 1):
                fetched = str(doc.get("fetched_at", ""))[:16].replace("T", " ")
                blocks.append(
                    f"--- 事实 {i} | 采集于 {fetched} | 来源 {doc.get('tool_id', '')} | "
                    f"Topic:{doc.get('topic', '')} ---\n{str(doc.get('content', ''))[:1000]}"
                )
            workflow_inputs["memory_facts_summary"] = "\n\n".join(blocks)
            self.logger.info(
                "🧠 [factual memory injection] ticker=%s %d external fact memories have been injected",
                ticker_val, len(docs),
            )
        except Exception as e:
            self.logger.warning(f"⚠️ [factual memory injection] Failure (does not affect analysis): {e}")

    async def _execute_via_workflow(
        self,
        task: UnifiedAnalysisTask,
        config,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Execute via workflow engine

        Args:
            task: Task object
            config: Workflow configuration
            progress_callback: Progress callback

        Returns:
            Execution result
        """
        workflow_id = self._resolve_workflow_id(task, config)
        self.logger.info(f"🔄 使用工作流引擎执行: {workflow_id}")

        # Import workflow API
        from core.api.workflow_api import WorkflowAPI

        workflow_api = WorkflowAPI()

        # Save a reference to the main event loop (before calling asyncio.to_thread)
        import asyncio
        main_loop = asyncio.get_running_loop()

        # Create a wrapped progress callback that updates the task object
        # Note: This callback will be called in the thread of the workflow engine (because of the use of asyncio.to_thread)
        # Therefore, you cannot call the asynchronous function directly, you need to use asyncio.run_coroutine_threadsafe
        def wrapped_progress_callback(progress: int, message: str, **kwargs):
            """Wrapped progress callback: updates the task object and calls the original callback"""
            # 🔑 Key: extract step_name (short name) from kwargs
            step_name = kwargs.get("step_name", "")

            # Update the task object (this is thread-safe since only object properties are modified)
            task.progress = progress
            task.current_step = step_name or message  # ✅ Use step_name instead message
            task.message = message  # ✅ Save detailed description to message field

            self.logger.debug(f"📊 进度更新: {progress}% - {step_name} - {message}")

            # Call the original callback (the original callback checks for the cancellation flag)
            if progress_callback:
                if asyncio.iscoroutinefunction(progress_callback):
                    # If it is an asynchronous callback, it needs to be run in the main event loop
                    try:
                        # Using a saved main event loop reference
                        future = asyncio.run_coroutine_threadsafe(
                            progress_callback(progress, message, **kwargs),
                            main_loop
                        )
                        # 🔥 Key: Wait for the callback to complete so it can be captured TaskCancelledException
                        try:
                            future.result(timeout=5)  # Wait up to 5 seconds
                        except Exception as callback_error:
                            # If the callback throws an exception (such as TaskCancelledException), propagate upward
                            self.logger.warning(f"⚠️ 进度回调执行异常: {callback_error}")
                            raise callback_error
                    except Exception as e:
                        self.logger.warning(f"⚠️ 进度回调调度失败: {e}")
                        raise  # Propagate exceptions upward
                else:
                    # Synchronous callbacks can be called directly
                    try:
                        progress_callback(progress, message, **kwargs)
                    except Exception as e:
                        self.logger.warning(f"⚠️ 进度回调执行失败: {e}")
                        raise  # Propagate exceptions upward
        
        # Prepare workflow input
        workflow_inputs = task.task_params.copy()

        # 🔑 Create an AgentContext and add it to the workflow input (used to obtain user-configured prompt words)
        from tradingagents.agents.utils.agent_context import AgentContext

        agent_context = AgentContext(
            user_id=str(task.user_id),
            preference_id=task.preference_type,  # Preference type for using tasks
            session_id=None,
            request_id=None,
            is_debug_mode=bool(task.task_params.get("debug_mode", False)),
            debug_template_id=task.task_params.get("debug_template_id"),
            workflow_id=workflow_id,
        )

        # Add AgentContext to workflow input
        workflow_inputs["context"] = agent_context

        # Parameter mapping: map symbol/code/stock_code to ticker (workflow engine uses ticker)
        # ⚠️ The field names used by different services are inconsistent:
        #   - stock_analysis use symbol
        #   - trade_review use code
        #   - portfolio_analysis use stock_code
        # Unified mapping to ticker to avoid agents reporting "Missing required parameters: ticker"
        if "ticker" not in workflow_inputs or not workflow_inputs.get("ticker"):
            for key in ("symbol", "code", "stock_code"):
                val = workflow_inputs.get(key)
                if val:
                    workflow_inputs["ticker"] = val
                    self.logger.debug(f"📋 参数映射: {key} → ticker = {val}")
                    break

        # 🧠 External fact memory injection: Query the unexpired fact memory related to the stock (intelligent assistant network extraction),
        # Write memory_facts_summary for debate session (bull/bear) and risk assessment session (risk_manager)
        # As a reference for analysis materials (for consumers, see the fact memory injection whitelist in core/agents/base.py).
        await self._inject_memory_facts(workflow_inputs)

        # 🆕 Read the input_config of the workflow and supplement the missing parameters according to the field definitions
        try:
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            wf_doc = await db.workflows.find_one({"_id": workflow_id}, {"input_config": 1, "workflow_type": 1})
            if wf_doc and wf_doc.get("input_config"):
                fields = wf_doc["input_config"].get("fields", [])
                for field in fields:
                    fname = field.get("name")
                    if fname and fname not in workflow_inputs and fname not in ("context",):
                        default_val = field.get("default")
                        if default_val is not None:
                            workflow_inputs[fname] = default_val
                            self.logger.debug(f"📋 Supplement parameters from input_config: {fname}={default_val}")
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to read input_config, using hardcoded defaults: {e}")

        # General cover parameters (when input_config does not exist or the corresponding field is not defined)
        from datetime import datetime
        # 🔑 Note: setdefault cannot be used because API requests may be passed in analysis_date=None, 
        # setdefault Keys that already exist but have a value of None will not be overwritten, causing the downstream Agent to report an error.
        if not workflow_inputs.get("analysis_date"):
            workflow_inputs["analysis_date"] = datetime.now().strftime("%Y-%m-%d")
        workflow_inputs.setdefault("research_depth", "标准")
        workflow_inputs.setdefault("lookback_days", 30)
        workflow_inputs.setdefault("max_debate_rounds", 3)

        self.logger.info(f"📦 Workflow input parameters: ticker={workflow_inputs.get('ticker')}, "
                        f"analysis_date={workflow_inputs.get('analysis_date')}, "
                        f"research_depth={workflow_inputs.get('research_depth')}, "
                        f"selected_analysts={workflow_inputs.get('selected_analysts')}, "
                        f"user_id={agent_context.user_id}, "
                        f"preference_id={agent_context.preference_id}")

        # Prepare legacy configuration (LLM configuration, etc.)
        legacy_config = {
            "preference_type": task.preference_type,
        }

        if workflow_inputs.get("debug_mode"):
            if workflow_inputs.get("debug_llm_provider"):
                legacy_config["llm_provider"] = workflow_inputs["debug_llm_provider"]
            if workflow_inputs.get("debug_llm_backend_url"):
                legacy_config["backend_url"] = workflow_inputs["debug_llm_backend_url"]
            if workflow_inputs.get("debug_llm_api_key"):
                legacy_config["quick_api_key"] = workflow_inputs["debug_llm_api_key"]
                legacy_config["deep_api_key"] = workflow_inputs["debug_llm_api_key"]
            if workflow_inputs.get("debug_llm_temperature") is not None or workflow_inputs.get("debug_llm_max_tokens") is not None:
                debug_model_config = {
                    "temperature": workflow_inputs.get("debug_llm_temperature"),
                    "max_tokens": workflow_inputs.get("debug_llm_max_tokens"),
                    "timeout": 300 if str(workflow_inputs.get("debug_llm_provider", "")).lower() == "ollama" else 180,
                }
                legacy_config["quick_model_config"] = debug_model_config
                legacy_config["deep_model_config"] = debug_model_config

        # 🔑 Key: Extract selected_analysts from task parameters (for dynamic cropping workflow)
        if "selected_analysts" in workflow_inputs:
            legacy_config["selected_analysts"] = workflow_inputs["selected_analysts"]
            self.logger.info(f"🎯 选中的分析师: {workflow_inputs['selected_analysts']}")

        # 🧠 A1b: Depth gear → Thinking budget (passed to builder, merged with DB explicit configuration, only injected into Volcano Ark inference model)
        try:
            _depth_key = str(workflow_inputs.get("research_depth") or "标准").strip()
            legacy_config["depth_reasoning_effort"] = RESEARCH_DEPTH_REASONING_EFFORT.get(_depth_key, "medium")
            self.logger.info(
                f"🧠 [reasoning_effort] 档位={_depth_key} → 思考预算默认={legacy_config['depth_reasoning_effort']}"
                f" (DB Explicit configuration takes precedence, only Volcano Ark inference model injection)"
            )
        except ImportError:
            pass

        # Extracts the LLM configuration from the task parameters; if not specified, the default value is read from the database system configuration
        quick_model = workflow_inputs.get("quick_analysis_model")
        deep_model = workflow_inputs.get("deep_analysis_model")

        if not quick_model or not deep_model:
            # Read system default model from database
            try:
                from app.core.database import get_mongo_db as _get_db
                _db = _get_db()
                _cfg = await _db.system_configs.find_one(
                    {"is_active": True}, sort=[("version", -1)]
                )
                if _cfg:
                    _default_models = _cfg.get("default_models") or {}
                    _sys_settings = _cfg.get("system_settings") or {}
                    if not quick_model:
                        quick_model = (
                            _default_models.get("quick_analysis_model")
                            or _sys_settings.get("quick_analysis_model")
                        )
                    if not deep_model:
                        deep_model = (
                            _default_models.get("deep_analysis_model")
                            or _sys_settings.get("deep_analysis_model")
                        )
                    self.logger.info(
                        f"📋 Read default model from system configuration: quick={quick_model}, deep={deep_model}"
                    )
            except Exception as _e:
                self.logger.warning(f"⚠️ Failed to read system default model: {_e}")

        if quick_model:
            legacy_config["quick_think_llm"] = quick_model
        if deep_model:
            legacy_config["deep_think_llm"] = deep_model

        # Always call _build_llm_config to get the full LLM configuration (api_key / backend_url etc.) from the database
        if quick_model or deep_model:
            full_config = await self._build_llm_config(quick_model, deep_model)
            legacy_config.update(full_config)

            if workflow_inputs.get("debug_mode"):
                if workflow_inputs.get("debug_llm_provider"):
                    legacy_config["llm_provider"] = workflow_inputs["debug_llm_provider"]
                if workflow_inputs.get("debug_llm_backend_url"):
                    legacy_config["backend_url"] = workflow_inputs["debug_llm_backend_url"]
                if workflow_inputs.get("debug_llm_api_key"):
                    legacy_config["quick_api_key"] = workflow_inputs["debug_llm_api_key"]
                    legacy_config["deep_api_key"] = workflow_inputs["debug_llm_api_key"]
                if workflow_inputs.get("debug_llm_temperature") is not None or workflow_inputs.get("debug_llm_max_tokens") is not None:
                    debug_model_config = {
                        "temperature": workflow_inputs.get("debug_llm_temperature"),
                        "max_tokens": workflow_inputs.get("debug_llm_max_tokens"),
                        "timeout": 300 if str(workflow_inputs.get("debug_llm_provider", "")).lower() == "ollama" else 180,
                    }
                    legacy_config["quick_model_config"] = debug_model_config
                    legacy_config["deep_model_config"] = debug_model_config

        self.logger.info(f"🔧 LLM Configuration: quick={legacy_config.get('quick_think_llm')}, "
                        f"deep={legacy_config.get('deep_think_llm')}, "
                        f"provider={legacy_config.get('llm_provider')}")

        # Execute the workflow (WorkflowAPI.execute is a synchronous method and needs to run in a thread)
        import asyncio

        # 🔑 Execution trace is turned on once: if the task input specifies enable_trace=true, Temporarily enable globally
        # Note: Thread local variables cannot be used because the analyst executes in a parallel sub-thread and cannot read the mark of the main thread.
        def _execute_with_trace_context():
            from app.core.config import settings
            old_value = settings.AGENT_EXECUTION_TRACE_ENABLED
            if task.task_params.get("enable_trace"):
                settings.AGENT_EXECUTION_TRACE_ENABLED = True
            try:
                return workflow_api.execute(
                    workflow_id=workflow_id,
                    inputs=workflow_inputs,
                    legacy_config=legacy_config,
                    progress_callback=wrapped_progress_callback,
                    task_id=task.task_id,
                )
            finally:
                settings.AGENT_EXECUTION_TRACE_ENABLED = old_value

        result = await asyncio.to_thread(_execute_with_trace_context)

        # Check execution results
        if not result.get("success"):
            error_msg = result.get("error", "工作流执行失败")
            raise RuntimeError(error_msg)

        return result.get("result", {})

    async def _execute_via_legacy(
        self,
        task: UnifiedAnalysisTask,
        config,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Execution via old engine (TradingAgentsGraph)— Deactivated

        v3.0 The old legacy engine has been deactivated and all entrances have been blocked.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Args:
            task: Task object
            config: Workflow configuration
            progress_callback: Progress callback

        Returns:
            Execution result

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] UnifiedAnalysisEngine._execute_via_legacy deactivated,"
            "Task %s should be executed using the workflow engine instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
            % getattr(task, "task_id", "<unknown>")
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        self.logger.info("🔄 Execute using old engine: TradingAgentsGraph")

        # Only supports stock analysis tasks
        if task.task_type != AnalysisTaskType.STOCK_ANALYSIS:
            raise ValueError(f"The old engine only supports stock analysis tasks, the current task type: {task.task_type}")

        # Import old engine
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # Prepare parameters
        symbol = task.task_params.get("symbol")
        analysis_date = task.task_params.get("analysis_date")

        if not symbol:
            raise ValueError("Missing required parameter: symbol")

        # Create engine instance
        graph = TradingAgentsGraph(debug=False)

        # Perform analysis
        self.logger.info(f"📊 分析股票: {symbol} (日期: {analysis_date or '最新'})")

        # Call propagate method
        state, decision = graph.propagate(symbol, analysis_date)

        # Conversion result format
        result = {
            "engine": "legacy",
            "symbol": symbol,
            "analysis_date": analysis_date,
            "decision": decision,
            "state": state,
            "source": "TradingAgentsGraph"
        }

        return result

    async def _execute_via_llm(
        self,
        task: UnifiedAnalysisTask,
        config,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Executed via direct LLM call

        Args:
            task: Task object
            config: Workflow configuration
            progress_callback: Progress callback

        Returns:
            Execution result
        """
        self.logger.info("🔄 Use LLM to call execution directly")

        # Import LLM Manager
        from core.llm.llm_manager import LLMManager

        llm_manager = LLMManager()

        # Build prompt words based on task type
        prompt = self._build_prompt_for_task(task)

        # call LLM
        self.logger.info(f"💬 调用 LLM: {task.preference_type} 偏好")

        response = await llm_manager.generate(
            prompt=prompt,
            preference_type=task.preference_type,
            temperature=0.7
        )

        # Conversion result format
        result = {
            "engine": "llm",
            "task_type": task.task_type.value,
            "response": response,
            "source": "LLM直接调用"
        }

        return result

    def _build_prompt_for_task(self, task: UnifiedAnalysisTask) -> str:
        """Build prompt words for tasks

        Args:
            task: Task object

        Returns:
            Prompt word string
        """
        # Construct different prompt words based on task type
        if task.task_type == AnalysisTaskType.PORTFOLIO_HEALTH:
            return self._build_portfolio_health_prompt(task.task_params)
        elif task.task_type == AnalysisTaskType.RISK_ASSESSMENT:
            return self._build_risk_assessment_prompt(task.task_params)
        elif task.task_type == AnalysisTaskType.MARKET_OVERVIEW:
            return self._build_market_overview_prompt(task.task_params)
        else:
            # universal prompt word
            return f"""请分析以下任务：

任务类型: {task.task_type.value}
任务参数: {task.task_params}

请提供详细的分析结果。"""

    def _build_portfolio_health_prompt(self, params: Dict[str, Any]) -> str:
        """构建组合健康度分析提示词"""
        return f"""Please analyze the health of your portfolio.

Analysis points:
1. Position concentration analysis
2. Risk diversification
3. Income stability
4. Fund usage efficiency
5. overall health score

parameters: {params}

Please provide a detailed research report."""

    def _build_risk_assessment_prompt(self, params: Dict[str, Any]) -> str:
        """构建风险评估提示词"""
        return f"""Please conduct a risk assessment analysis.

Assessment Dimensions:
1. market risk
2. individual stock risk
3. Liquidity risk
4. concentration risk
5. Comprehensive risk rating

parameters: {params}

Please provide a detailed risk assessment report."""

    def _build_market_overview_prompt(self, params: Dict[str, Any]) -> str:
        """构建市场概览提示词"""
        return f"""Please provide a market overview analysis.

Analysis content:
1. overall market trend
2. Sector performance
3. Fund flow
4. market sentiment
5. Research conclusion

parameters: {params}

Please provide a detailed market research report."""


# === unified_analysis_service.py ===
"""
Unified Analytics Services

Unify all analysis portals into WorkflowEngine + WorkflowBuilder
Support:
1. single stock analysis API
2. Batch analysis API
3. Front-end workflow debugging
4. Scheduled analysis tasks
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.utils.timezone import now_tz
from app.core.jdyun import is_jdyun_mode, get_jdyun_batch_max_concurrent

from app.models.analysis import (
    AnalysisParameters,
    AnalysisResult,
    AnalysisStatus,
    AnalysisTask,
    AnalysisTaskType,
    SingleAnalysisRequest,
    UnifiedAnalysisTask,
)
from app.services.memory_state_manager import (
    get_memory_state_manager,
    TaskStatus,
)
from core.workflow.default_workflow_provider import (
    DefaultWorkflowProvider,
    get_default_workflow_provider,
)
from core.workflow.engine import WorkflowEngine
from core.workflow.models import WorkflowDefinition

logger = logging.getLogger(__name__)

ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")


def _unified_analysis_service_is_cn_etf_symbol(code: Optional[str]) -> bool:
    code_str = str(code or "").strip()
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


class UnifiedAnalysisService:
    """
    Unified Analytics Services

    All analysis portals are executed through this service, using WorkflowEngine as the execution engine.

    Usage:
        service = UnifiedAnalysisService()

        # single stock analysis
        result = await service.analyze(
            stock_code="000858",
            analysis_date="2024-01-15",
            progress_callback=lambda p, m, **kw: print(f"{p}% - {m}")
        )

        # Use specified workflow
        result = await service.analyze(
            stock_code="AAPL",
            workflow_id="my_custom_workflow",
        )
    """

    def __init__(self):
        self._workflow_provider = get_default_workflow_provider()
        self._db = None

    def _get_db(self):
        """获取数据库连接（懒加载）"""
        if self._db is None:
            try:
                from pymongo import MongoClient
                from app.core.config import settings
                client = MongoClient(settings.MONGO_URI)
                self._db = client[settings.MONGO_DB]
            except Exception as e:
                logger.warning(f"无法连接数据库: {e}")
        return self._db

    def _build_legacy_config(
        self,
        parameters: Optional[AnalysisParameters] = None,
    ) -> Dict[str, Any]:
        """
        Build legacy configuration (used by WorkflowBuilder to create Agent)

        Read LLM configuration from database and merge user parameters
        """
        config = {}

        # Get LLM configuration from database
        db = self._get_db()
        if db is not None:
            try:
                # Get active system configuration
                system_config = db.system_configs.find_one(
                    {"is_active": True},
                    sort=[("version", -1)]
                )
                if system_config:
                    config["llm_provider"] = system_config.get("llm_provider", "dashscope")
                    config["deep_think_llm"] = system_config.get("deep_think_llm", "qwen-plus")
                    config["quick_think_llm"] = system_config.get("quick_think_llm", "qwen-turbo")
            except Exception as e:
                logger.warning(f"从数据库获取配置失败: {e}")

        # Merge user parameters
        if parameters:
            if parameters.research_depth:
                # Keep research_depth as a string value for workflow inputs
                config["research_depth"] = parameters.research_depth
                # 🧠 A1b: Depth gear → Thinking budget (passed to builder, merged with DB explicit configuration, only injected into Volcano Ark inference model)
                config["depth_reasoning_effort"] = RESEARCH_DEPTH_REASONING_EFFORT.get(
                    str(parameters.research_depth).strip(), "medium"
                )

            if parameters.selected_analysts:
                config["selected_analysts"] = parameters.selected_analysts

            if parameters.market_type:
                config["market_type"] = parameters.market_type

        return config

    def _prepare_system_variables(
        self,
        stock_code: str,
        analysis_date: str
    ) -> Dict[str, Any]:
        """
        Prepare system variables (obtained uniformly at the beginning of the workflow)

        Get it from the database first, fast and not affected by API current limit

        Args:
            stock_code: Stock code
            analysis_date: Analysis date

        Returns:
            System variable dictionary
        """
        system_vars = {}

        try:
            from tradingagents.utils.stock_utils import StockUtils

            market_info = StockUtils.get_market_info(stock_code)
            is_china = market_info.get('is_china', False)

            # 1. Obtain basic stock information (company name, industry) from the database
            company_name = stock_code
            industry = "未知"

            if is_china:
                try:
                    db = self._get_db()
                    from tradingagents.utils.stock_utils import StockUtils as _SU
                    _is_fund = _SU.is_fund(stock_code)

                    # Preferably obtained from stock_basic_info; ETF downgraded to etf_basic_info
                    stock_info = db.stock_basic_info.find_one(
                        {"$or": [{"code": stock_code}, {"symbol": stock_code}]},
                        {"_id": 0, "name": 1, "industry": 1}
                    )

                    if not stock_info and _is_fund:
                        stock_info = db.etf_basic_info.find_one(
                            {"$or": [{"symbol": stock_code}, {"code": stock_code}]},
                            {"_id": 0, "name": 1, "industry": 1, "fund_type": 1}
                        )
                        if stock_info:
                            logger.info(f"📊 [System variables - database] Get fund information from etf_basic_info: {stock_code}")

                    if stock_info:
                        company_name = stock_info.get("name", stock_code)
                        industry = stock_info.get("industry", stock_info.get("fund_type", "未知"))
                        logger.info(f"📊 [系统变量-数据库] 公司名称: {company_name}, 行业: {industry}")
                    else:
                        logger.warning(f"⚠️ 数据库中未找到股票 {stock_code} 的基础信息")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to obtain basic stock information from database: {e}")

            system_vars["company_name"] = company_name
            system_vars["industry"] = industry

            # 2. Get current price from database
            current_price = "未知"

            if is_china:
                try:
                    db = self._get_db()
                    logger.info(f"🔍 [价格查询] 开始查询股票 {stock_code} 的价格...")

                    # Get the latest prices from market_quotes first
                    logger.info("🔍 [Price inquiry] steps 1: Query from market_quotes...")
                    quote = db.market_quotes.find_one(
                        {"$or": [{"code": stock_code}, {"symbol": stock_code}]},
                        {"_id": 0, "close": 1, "trade_date": 1},
                        sort=[("trade_date", -1)]  # Sort by date in descending order to get the latest data
                    )
                    logger.info(f"🔍 [Price inquiry] market_quotes Query results: {quote}")

                    if quote and quote.get("close"):
                        current_price = str(quote["close"])
                        logger.info(f"✅ [系统变量-数据库] 当前价格: ¥{current_price} (日期: {quote.get('trade_date', 'N/A')})")
                    else:
                        logger.info("🔍 [Price inquiry] market_quotes No data found, try steps 2...")
                        # For ETFs, try first etf_daily_quotes
                        from tradingagents.utils.stock_utils import StockUtils as _SU2
                        if _SU2.is_fund(stock_code):
                            logger.info("🔍 [Price inquiry] steps 2a: ETF, Query from etf_daily_quotes...")
                            etf_quote = db.etf_daily_quotes.find_one(
                                {"$or": [{"code": stock_code}, {"symbol": stock_code}, {"ts_code": {"$regex": f"^{stock_code}"}}]},
                                {"_id": 0, "close": 1, "trade_date": 1},
                                sort=[("trade_date", -1)]
                            )
                            logger.info(f"🔍 [Price inquiry] etf_daily_quotes Query results: {etf_quote}")
                            if etf_quote and etf_quote.get("close"):
                                current_price = str(etf_quote["close"])
                                logger.info(f"✅ [System variables - database] ETF current price: ¥{current_price}")
                        if current_price == "未知":
                            # Fallback to the current_price field of stock_basic_info
                            logger.info("🔍 [Price inquiry] steps 2b: Query from stock_basic_info...")
                            stock_info = db.stock_basic_info.find_one(
                                {"$or": [{"code": stock_code}, {"symbol": stock_code}]},
                                {"_id": 0, "current_price": 1}
                            )
                            logger.info(f"🔍 [Price inquiry] stock_basic_info Query results: {stock_info}")

                            if stock_info and stock_info.get("current_price"):
                                current_price = str(stock_info["current_price"])
                                logger.info(f"✅ [System variables - database] current price(Spare): ¥{current_price}")
                            else:
                                logger.warning(f"⚠️ 数据库中未找到股票 {stock_code} 的价格信息")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to get current price from database: {e}")
                    import traceback
                    traceback.print_exc()

            system_vars["current_price"] = current_price

            # 3. market information
            market_name = "A股" if is_china else "港股" if market_info.get('is_hk') else "美股"
            system_vars["market_name"] = market_name

            # 4. currency information
            if is_china:
                system_vars["currency_name"] = "人民币"
                system_vars["currency_symbol"] = "¥"
            elif market_info.get('is_hk'):
                system_vars["currency_name"] = "港币"
                system_vars["currency_symbol"] = "HK$"
            else:
                system_vars["currency_name"] = "美元"
                system_vars["currency_symbol"] = "$"

            # 5. date information
            from datetime import datetime, timedelta
            system_vars["current_date"] = analysis_date
            start_date = (datetime.strptime(analysis_date, '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d')
            system_vars["start_date"] = start_date

            # 6. 🆕 Industry/stock analysis dimension injection
            try:

                # Query industry analysis dimensions
                if industry and industry != "未知":
                    industry_dims = AnalysisProfileService.get_industry_dimensions_sync(industry)
                    system_vars.update(industry_dims)

                # Query individual stock analysis dimensions (covering industry dimensions)
                stock_dims = AnalysisProfileService.get_stock_dimensions_sync(stock_code)
                system_vars.update(stock_dims)
            except Exception as e:
                logger.warning(f"⚠️ Failed to obtain analysis dimensions (does not affect the main process): {e}")

            logger.info(f"✅ [system variables] Ready to complete: {list(system_vars.keys())}")
            logger.info(f"   - company_name: {company_name}")
            logger.info(f"   - industry: {industry}")
            logger.info(f"   - current_price: {current_price}")
            logger.info(f"   - market_name: {market_name}")
            if system_vars.get("industry_dimensions"):
                logger.info("   - 🏭 Infused with industry analysis dimensions")
            if system_vars.get("stock_dimensions"):
                logger.info("   - 📊 Injected into individual stock analysis dimension")

        except Exception as e:
            logger.error(f"❌ 准备系统变量失败: {e}")
            import traceback
            traceback.print_exc()

        return system_vars

    def _build_workflow_inputs(
        self,
        stock_code: str,
        analysis_date: str,
        workflow: WorkflowDefinition,
        parameters: Optional[AnalysisParameters] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        research_depth = "标准"
        if parameters and getattr(parameters, "research_depth", None):
            research_depth = parameters.research_depth

        depth_mapping = {
            "快速": {"debate": 1, "risk": 1, "memory_enabled": False},  # 🔧 Quick analysis of disabled memories
            "基础": {"debate": 1, "risk": 1, "memory_enabled": True},
            "标准": {"debate": 1, "risk": 2, "memory_enabled": True},
            "深度": {"debate": 2, "risk": 2, "memory_enabled": True},
            "全面": {"debate": 3, "risk": 3, "memory_enabled": True},
        }
        depth_config = depth_mapping.get(research_depth, depth_mapping["标准"])

        # 🆕 Prepare system variables
        system_vars = self._prepare_system_variables(stock_code, analysis_date)

        inputs: Dict[str, Any] = {
            "ticker": stock_code,
            "company_of_interest": stock_code,
            "analysis_date": analysis_date,
            "trade_date": analysis_date,
            "research_depth": research_depth,
            "_max_debate_rounds": depth_config["debate"],
            "_max_risk_rounds": depth_config["risk"],
            "memory_enabled": depth_config["memory_enabled"],  # 🔧 Set memory switch according to analysis depth
            "messages": [],
            # 🆕 Process-specific prompt words: workflow_id is used by process+agent Get the corresponding prompt word template
            "workflow_id": workflow.id,
            # 🆕 Add system variables
            **system_vars,
        }

        # 🔥 Create AgentContext (supports user preferences, debugging mode and process-specific prompt words)
        from tradingagents.agents.utils.agent_context import AgentContext

        # Get user preferences
        preference_id = "neutral"
        if parameters and getattr(parameters, "preference_type", None):
            preference_id = parameters.preference_type

        # Check if it is debug mode (if there is template_id in parameters)
        is_debug_mode = False
        debug_template_id = None
        if parameters and getattr(parameters, "template_id", None):
            is_debug_mode = True
            debug_template_id = parameters.template_id

        # Create context (contains workflow_id for process+agent level prompt word loading)
        context = AgentContext(
            user_id=user_id,
            preference_id=preference_id,
            is_debug_mode=is_debug_mode,
            debug_template_id=debug_template_id,
            workflow_id=workflow.id,
        )

        inputs["context"] = context

        logger.info(
            f"🔍 [Workflow input] Create AgentContext: "
            f"user_id={user_id}, preference={preference_id}, "
            f"workflow_id={workflow.id}, debug_mode={is_debug_mode}, template_id={debug_template_id}"
        )

        if workflow.config:
            inputs.update({k: v for k, v in workflow.config.items() if k not in inputs})

        return inputs

    async def analyze(
        self,
        stock_code: str,
        analysis_date: Optional[str] = None,
        workflow_id: Optional[str] = None,
        parameters: Optional[AnalysisParameters] = None,
        progress_callback: Optional[Callable] = None,
        task_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform stock analysis

        Args:
            stock_code: Stock code
            analysis_date: Analysis date, default is today
            workflow_id: Workflow ID, None to use the active workflow
            parameters: Analysis parameters
            progress_callback: Progress callback function
            task_id: Task ID, used for progress tracking
            user_id: User ID (used to create AgentContext)

        Returns:
            Analysis result dictionary
        """
        # Generate tasks ID
        task_id = task_id or str(uuid.uuid4())

        # Set default date
        if not analysis_date:
            analysis_date = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"开始分析: {stock_code} @ {analysis_date}, workflow={workflow_id}")

        try:
            # 1. Load workflow
            workflow = self._workflow_provider.load_workflow(workflow_id)
            logger.info(f"已加载工作流: {workflow.id} - {workflow.name}")

            # 2. Build configuration
            legacy_config = self._build_legacy_config(parameters)

            # 3. Create engine
            engine = WorkflowEngine(
                legacy_config=legacy_config,
                task_id=task_id,
            )

            # 4. Load and compile the workflow
            engine.load(workflow)

            # 5. ready to enter
            inputs = self._build_workflow_inputs(
                stock_code=stock_code,
                analysis_date=analysis_date,
                workflow=workflow,
                parameters=parameters,
                user_id=user_id,
            )

            # 5.5 Inject approved growth memory (Memory Recall)
            if user_id and inputs.get("memory_enabled", False):
                try:
                    from app.services.workflow_growth_service import get_workflow_growth_service
                    growth_svc = get_workflow_growth_service()
                    recall_text = await growth_svc.build_recall_context(
                        user_id=user_id,
                        ticker=stock_code,
                        workflow_id=workflow.id,
                    )
                    if recall_text:
                        inputs["growth_memory_recall"] = recall_text
                        logger.info(f"📝 注入成长记忆召回: {len(recall_text)} 字符")
                except Exception as e:
                    logger.warning(f"⚠️ Growth memory recall failed (does not affect analysis): {e}")

            # 5.6 mem0: Recall the user's historical analysis memory of the stock
            if user_id:
                try:
                    mem0_block = await _recall_analysis_memory(
                        self._get_db(), user_id, stock_code,
                    )
                    if mem0_block:
                        existing = inputs.get("growth_memory_recall", "")
                        inputs["growth_memory_recall"] = (
                            f"{existing}\n\n{mem0_block}" if existing else mem0_block
                        )
                        logger.info(f"📝 注入 mem0 分析记忆: {len(mem0_block)} 字符")
                except Exception as e:
                    logger.debug(f"[mem0] Analysis memory recall failed (ignored): {e}")

            # 6. Execute workflow
            result = await engine.execute_async(
                inputs=inputs,
                progress_callback=progress_callback,
            )

            logger.info(f"分析完成: {stock_code}, task_id={task_id}")

            # 7. Format results
            return self._format_result(result, stock_code, analysis_date, task_id, parameters)

        except Exception as e:
            logger.error(f"分析失败: {stock_code}, error={e}")
            return {
                "success": False,
                "task_id": task_id,
                "stock_code": stock_code,
                "error": str(e),
            }

    def analyze_sync(
        self,
        stock_code: str,
        analysis_date: Optional[str] = None,
        workflow_id: Optional[str] = None,
        parameters: Optional[AnalysisParameters] = None,
        progress_callback: Optional[Callable] = None,
        task_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous execution of stock analysis

        Used to execute in the thread pool to avoid blocking the event loop
        """
        task_id = task_id or str(uuid.uuid4())

        if not analysis_date:
            analysis_date = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"[同步] 开始分析: {stock_code} @ {analysis_date}")

        try:
            # 1. Load workflow
            workflow = self._workflow_provider.load_workflow(workflow_id)

            # 2. Build configuration
            legacy_config = self._build_legacy_config(parameters)

            # 3. Create engine
            engine = WorkflowEngine(
                legacy_config=legacy_config,
                task_id=task_id,
            )

            # 4. Load and compile the workflow
            engine.load(workflow)

            # 5. ready to enter
            inputs = self._build_workflow_inputs(
                stock_code=stock_code,
                analysis_date=analysis_date,
                workflow=workflow,
                parameters=parameters,
                user_id=user_id,
            )

            # 5.5 Inject approved growth memory (synchronized path)
            if user_id and inputs.get("memory_enabled", False):
                try:
                    from app.services.workflow_growth_service import build_recall_context_sync
                    recall_text = build_recall_context_sync(
                        user_id=user_id,
                        ticker=stock_code,
                        workflow_id=workflow.id,
                    )
                    if recall_text:
                        inputs["growth_memory_recall"] = recall_text
                        logger.info(f"📝 [同步] 注入成长记忆召回: {len(recall_text)} 字符")
                except Exception as e:
                    logger.warning(f"⚠️ [sync] Growth memory recall failed (does not affect analysis): {e}")

            # 6. Synchronous execution
            result = engine.execute(
                inputs=inputs,
                progress_callback=progress_callback,
            )

            logger.info(f"[同步] 分析完成: {stock_code}")
            return self._format_result(result, stock_code, analysis_date, task_id, parameters)

        except Exception as e:
            logger.error(f"[同步] 分析失败: {stock_code}, error={e}")
            return {
                "success": False,
                "task_id": task_id,
                "stock_code": stock_code,
                "error": str(e),
            }

    def _format_result(
        self,
        raw_result: Dict[str, Any],
        stock_code: str,
        analysis_date: str,
        task_id: str,
        parameters: Optional[AnalysisParameters] = None,
    ) -> Dict[str, Any]:
        """
        Formatting analysis results - using public tools consistent with SimpleAnalysisService

        Includes all report types:
        - Basic report:market_report, sentiment_report, news_report, fundamentals_report
        - Trading plan:investment_plan, trader_investment_plan, final_trade_decision
        - Research team:bull_researcher, bear_researcher, research_team_decision
        - Risk Team:risky_analyst, safe_analyst, neutral_analyst, risk_management_decision
        """
        from app.utils.report_formatter import format_analysis_result

        # Extract model information and analyst information from parameters
        if parameters:
            analysts = parameters.selected_analysts or ["market", "fundamentals"]
            research_depth = parameters.research_depth or "标准"
            quick_model = getattr(parameters, 'quick_analysis_model', None) or getattr(parameters, 'quick_model', None) or "Unknown"
            deep_model = getattr(parameters, 'deep_analysis_model', None) or getattr(parameters, 'deep_model', None) or "Unknown"
        else:
            analysts = ["market", "fundamentals"]
            research_depth = "标准"
            quick_model = "Unknown"
            deep_model = "Unknown"

        # Extract report_manifest from raw_result (dynamically generated by WorkflowEngine)
        report_manifest = raw_result.get("report_manifest")

        result = format_analysis_result(
            raw_result=raw_result,
            stock_code=stock_code,
            stock_name=self._resolve_stock_name(stock_code),
            analysis_date=analysis_date,
            task_id=task_id,
            analysts=analysts,
            research_depth=research_depth,
            quick_model=quick_model,
            deep_model=deep_model,
            report_manifest=report_manifest,
        )

        logger.info(f"[统一引擎] 格式化结果完成: reports={len(result.get('reports', {}))}个")
        return result

    async def analyze_batch(
        self,
        stock_codes: List[str],
        analysis_date: Optional[str] = None,
        workflow_id: Optional[str] = None,
        parameters: Optional[AnalysisParameters] = None,
        progress_callback: Optional[Callable] = None,
        max_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Analyze stocks in batches

        Args:
            stock_codes: Stock code list
            analysis_date: Analysis date
            workflow_id: Workflow ID
            parameters: Analysis parameters
            progress_callback: Progress callback
            max_concurrent: Maximum number of concurrencies

        Returns:
            Analysis result list
        """
        results = []
        total = len(stock_codes)
        completed = 0

        # 🔧 JD Cloud Mode: Reduce the number of concurrencies and avoid LLM speed limit (429)
        if is_jdyun_mode():
            jdyun_max = get_jdyun_batch_max_concurrent()
            if max_concurrent > jdyun_max:
                logger.info(f"🔧 [京东云模式] 批量分析并发数 {max_concurrent} → {jdyun_max}（避免 LLM 限速）")
                max_concurrent = jdyun_max

        # Using semaphores to control concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_one(code: str, index: int) -> Dict[str, Any]:
            nonlocal completed
            async with semaphore:
                task_id = f"batch_{uuid.uuid4().hex[:8]}_{index}"

                # Single stock progress callback
                def single_progress(progress, message, **kwargs):
                    if progress_callback:
                        # Calculate overall progress
                        overall = (completed * 100 + progress) / total
                        progress_callback(
                            overall,
                            f"[{index+1}/{total}] {code}: {message}",
                            stock_code=code,
                            **kwargs
                        )

                result = await self.analyze(
                    stock_code=code,
                    analysis_date=analysis_date,
                    workflow_id=workflow_id,
                    parameters=parameters,
                    progress_callback=single_progress,
                    task_id=task_id,
                )

                completed += 1
                return result

        # Concurrent execution
        tasks = [
            analyze_one(code, i)
            for i, code in enumerate(stock_codes)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append({
                    "success": False,
                    "stock_code": stock_codes[i],
                    "error": str(result),
                })
            else:
                final_results.append(result)

        return final_results


    async def execute_analysis_for_ab_test(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker=None,
    ) -> Dict[str, Any]:
        """
        Analysis execution portal provided for AB testing

        with SimpleAnalysisService.execute_analysis_background() Interface compatible
        Use WorkflowEngine instead TradingAgentsGraph

        Args:
            task_id: Task ID
            user_id: User ID
            request: Analysis request
            progress_tracker: RedisProgressTracker Instance (optional, will be created automatically if not provided)

        Returns:
            Analyze results
        """
        import asyncio

        stock_code = request.get_symbol()
        parameters = request.parameters
        memory_manager = get_memory_state_manager()

        try:
            logger.info(f"🔄 [AB Test-Unified Engine] Start analysis: {stock_code}, task_id={task_id}")

            # 🔥 Update memory manager status to RUNNING
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=5,
                message="🚀 [unified engine] Starting analysis...",
                current_step="启动"
            )

            # If progress_tracker is not passed in, create it yourself
            if progress_tracker is None:
                def create_progress_tracker():
                    return RedisProgressTracker(
                        task_id=task_id,
                        analysts=parameters.selected_analysts if parameters else ["market", "fundamentals"],
                        research_depth=parameters.research_depth if parameters else "标准",
                        llm_provider="dashscope"
                    )
                progress_tracker = await asyncio.to_thread(create_progress_tracker)

            # Create a progress callback adapter
            def progress_callback(progress: float, message: str, **kwargs):
                """Convert the progress callback of the unified engine to RedisProgressTracker format"""
                if progress_tracker:
                    try:
                        # 🔑 Key: extract step_name (short name) from kwargs
                        step_name = kwargs.get("step_name", "")

                        progress_tracker.update_progress({
                            "progress_percentage": progress,
                            "last_message": message,
                            "current_step_name": step_name,  # ✅ short step name
                            "current_step_description": message,  # ✅ detailed description
                            **kwargs
                        })
                        # 🔥 Also update the memory manager (use asyncio.create_task to avoid event loop conflicts)
                        import asyncio
                        try:
                            # Get the currently running event loop
                            loop = asyncio.get_running_loop()
                            # Create background tasks without waiting for completion
                            loop.create_task(
                                memory_manager.update_task_status(
                                    task_id=task_id,
                                    status=TaskStatus.RUNNING,
                                    progress=int(progress),
                                    message=message,
                                    current_step=step_name or message  # ✅ Use step_name instead message
                                )
                            )
                        except RuntimeError:
                            # Skip memory manager updates if no event loop is running
                            logger.debug("No event loop running, memory manager updates skipped")
                    except Exception as e:
                        logger.warning(f"进度更新失败: {e}")

            # Get analysis date
            analysis_date = None
            if parameters and parameters.analysis_date:
                if isinstance(parameters.analysis_date, datetime):
                    analysis_date = parameters.analysis_date.strftime("%Y-%m-%d")
                else:
                    analysis_date = str(parameters.analysis_date)[:10]

            # Get workflow ID
            workflow_id = None
            if parameters and hasattr(parameters, "workflow_id"):
                workflow_id = parameters.workflow_id

            # Initialization progress
            await asyncio.to_thread(
                progress_tracker.update_progress,
                {"progress_percentage": 10, "last_message": "🚀 [unified engine] Start stock analysis"}
            )

            # 🔥 Update memory manager status
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=10,
                message="🚀 [unified engine] Start stock analysis",
                current_step="开始分析"
            )

            # Call the Unified Analysis Service (all fields in _format_result are populated)
            result = await self.analyze(
                stock_code=stock_code,
                analysis_date=analysis_date,
                workflow_id=workflow_id,
                parameters=parameters,
                progress_callback=progress_callback,
                task_id=task_id,
                user_id=user_id,  # ✅ Pass user_id to create AgentContext
            )

            # Analysis completed, mark progress
            # Note:mark_completed() does not accept parameters
            await asyncio.to_thread(progress_tracker.mark_completed)

            # Save analysis results to database
            await self._save_analysis_result(task_id, user_id, stock_code, result, parameters)

            # mem0: Asynchronous storage analysis insights
            asyncio.create_task(
                _store_analysis_insight(
                    self._get_db(), user_id, stock_code,
                    analysis_date,
                    result.get("summary", ""),
                    result.get("recommendation", ""),
                    task_id,
                )
            )

            # 🔥 Update memory manager status to COMPLETED
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="✅ 分析完成",
                current_step="完成",
                result_data=result
            )

            logger.info(f"✅ [AB Test-Unified Engine] Analysis completed: {stock_code}")
            return result

        except Exception as e:
            logger.error(f"❌ [AB Test-Unified Engine] Analysis failed: {stock_code}, error={e}")

            # Marking progress tracker failed
            if progress_tracker:
                try:
                    await asyncio.to_thread(progress_tracker.mark_failed, str(e))
                except Exception:
                    pass

            # 🔥 Update memory manager status to FAILED
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                message=f"❌ 分析失败: {str(e)}",
                error_message=str(e)
            )

            # Update database status failed
            await self._update_task_failed(task_id, str(e))
            raise

    async def execute_analysis_for_v2_engine(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker=None,
    ) -> Dict[str, Any]:
        import asyncio

        stock_code = request.get_symbol()
        parameters = request.parameters
        memory_manager = get_memory_state_manager()

        try:
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=5,
                message="🚀 [v2.0 engine] Starting analysis...",
                current_step="启动"
            )

            if progress_tracker is None:
                def create_progress_tracker():
                    return RedisProgressTracker(
                        task_id=task_id,
                        analysts=parameters.selected_analysts if parameters else ["market", "fundamentals"],
                        research_depth=parameters.research_depth if parameters else "标准",
                        llm_provider="dashscope"
                    )
                progress_tracker = await asyncio.to_thread(create_progress_tracker)

            def progress_callback(progress: float, message: str, **kwargs):
                if progress_tracker:
                    try:
                        progress_tracker.update_progress({
                            "progress_percentage": progress,
                            "last_message": message,
                            **kwargs
                        })
                        import asyncio
                        try:
                            # Get the currently running event loop
                            loop = asyncio.get_running_loop()
                            # Create background tasks without waiting for completion
                            loop.create_task(
                                memory_manager.update_task_status(
                                    task_id=task_id,
                                    status=TaskStatus.RUNNING,
                                    progress=int(progress),
                                    message=message,
                                    current_step=kwargs.get("step", "分析中")
                                )
                            )
                        except RuntimeError:
                            # Skip memory manager updates if no event loop is running
                            logger.debug("No event loop running, memory manager updates skipped")
                    except Exception as e:
                        logger.warning(f"进度更新失败: {e}")

            analysis_date = None
            if parameters and parameters.analysis_date:
                if isinstance(parameters.analysis_date, datetime):
                    analysis_date = parameters.analysis_date.strftime("%Y-%m-%d")
                else:
                    analysis_date = str(parameters.analysis_date)[:10]

            workflow_id = None
            if parameters and hasattr(parameters, "workflow_id"):
                workflow_id = parameters.workflow_id
            if not workflow_id:
                workflow_id = self._workflow_provider.get_active_workflow_id("stock_analysis")

            try:
                wf = self._workflow_provider.load_workflow(workflow_id)
                tags = getattr(wf, "tags", []) or []
                wf_id = str(getattr(wf, "id", "") or "")
                wf_name = str(getattr(wf, "name", "") or "")
                wf_version = str(getattr(wf, "version", "") or "")
                is_v2 = (
                    "v2.0" in tags
                    or wf_id.endswith("_v2")
                    or "v2.0" in wf_name
                    or wf_version.startswith("2.")
                )
                if not is_v2:
                    workflow_id = "v2_stock_analysis"
            except Exception:
                workflow_id = "v2_stock_analysis"

            await asyncio.to_thread(
                progress_tracker.update_progress,
                {"progress_percentage": 10, "last_message": "🚀 [v2.0 engine] Start stock analysis"}
            )

            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=10,
                message="🚀 [v2.0 engine] Start stock analysis",
                current_step="开始分析"
            )


            result = await self.analyze(
                stock_code=stock_code,
                analysis_date=analysis_date,
                workflow_id=workflow_id,
                parameters=parameters,
                progress_callback=progress_callback,
                task_id=task_id,
            )

            await asyncio.to_thread(progress_tracker.mark_completed)
            await self._save_analysis_result(task_id, user_id, stock_code, result, parameters)

            # mem0: Asynchronous storage analysis insights
            asyncio.create_task(
                _store_analysis_insight(
                    self._get_db(), user_id, stock_code,
                    analysis_date,
                    result.get("summary", ""),
                    result.get("recommendation", ""),
                    task_id,
                )
            )

            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="✅ 分析完成",
                current_step="完成",
                result_data=result
            )

            return result
        except Exception as e:
            logger.error(f"❌ [v2.0 engine] Analysis failed: {stock_code}, error={e}")
            if progress_tracker:
                try:
                    await asyncio.to_thread(progress_tracker.mark_failed, str(e))
                except Exception:
                    pass
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                message=f"❌ 分析失败: {str(e)}",
                error_message=str(e)
            )
            await self._update_task_failed(task_id, str(e))
            raise

    async def _save_analysis_result(
        self,
        task_id: str,
        user_id: str,
        stock_code: str,
        result: Dict[str, Any],
        parameters=None
    ):
        """
        Save analysis results to MongoDB - consistent format with SimpleAnalysisService
        """
        db = self._get_db()
        if db is None:
            logger.warning("Unable to save analysis results: Database not connected")
            return

        try:
            timestamp = now_tz()  # ✅ Use now_tz() Make sure to include time zone information
            analysis_id = result.get("analysis_id", str(uuid.uuid4()))

            # Get stock name
            stock_name = self._resolve_stock_name(stock_code)
            market_type = "A股" if stock_code.isdigit() and len(stock_code) == 6 else "美股"

            # 🔥 Clean duplicate data in reports (if present)
            reports_raw = result.get("reports", {})
            cleaned_reports = {}
            if isinstance(reports_raw, dict):
                for key, value in reports_raw.items():
                    # Skip structured_reports (if present to avoid duplication)
                    if key != "structured_reports":
                        cleaned_reports[key] = value

            # Update analysis_tasks status
            db.analysis_tasks.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "status": "completed",
                        "progress": 100,
                        "completed_at": timestamp,
                        "updated_at": timestamp,
                        # 🔥 Save complete result to analysis_tasks (consistent with SimpleAnalysisService)
                        "result": {
                            "analysis_id": analysis_id,
                            "stock_symbol": stock_code,
                            "stock_code": stock_code,
                            "analysis_date": result.get("analysis_date"),
                            "summary": result.get("summary", ""),
                            "recommendation": result.get("recommendation", ""),
                            "confidence_score": result.get("confidence_score", 0.0),
                            "risk_level": result.get("risk_level", "中等"),
                            "key_points": result.get("key_points", []),
                            # 🔥 Note: detailed_analysis and state saved to the database here are used for debugging/auditing
                            # However, when the API returns, it will be decided based on the query parameters whether to include
                            "detailed_analysis": result.get("detailed_analysis", {}),
                            "state": result.get("state", {}),
                            "execution_time": result.get("execution_time", 0),
                            "tokens_used": result.get("tokens_used", 0),
                            "reports": cleaned_reports,  # 🔥 Use the cleaned reports
                            "decision": result.get("decision", {}),
                        }
                    }
                }
            )

            # 🔥 Clean duplicate data in reports (if present)
            reports_raw = result.get("reports", {})
            cleaned_reports = {}
            if isinstance(reports_raw, dict):
                for key, value in reports_raw.items():
                    # Skip structured_reports (if present to avoid duplication)
                    if key != "structured_reports":
                        cleaned_reports[key] = value

            # 🔥 Save to analysis_reports (same format as SimpleAnalysisService)
            document = {
                "analysis_id": analysis_id,
                "stock_symbol": stock_code,
                "stock_name": result.get("stock_name", stock_name),  # Give priority to names in result
                "market_type": market_type,
                "model_info": result.get("model_info", "Unknown"),
                "quick_model": result.get("quick_model", "Unknown"),  # 🔥 Add quick model fields
                "deep_model": result.get("deep_model", "Unknown"),    # 🔥 Add depth model field
                "analysis_date": timestamp.strftime('%Y-%m-%d'),
                "timestamp": timestamp,
                "status": "completed",
                "source": "api",
                "engine": (getattr(parameters, "engine", None) or "unified"),

                # Summary of analysis results
                "summary": result.get("summary", ""),
                "analysts": result.get("analysts", []),
                "research_depth": result.get("research_depth", "标准"),

                # Report content (use cleaned reports to avoid duplicate data)
                "reports": cleaned_reports,

                # 🔥 Key: decision field
                "decision": result.get("decision", {}),

                # metadata
                "task_id": task_id,
                "user_id": user_id,
                "created_at": timestamp,
                "updated_at": timestamp,

                # Other fields
                "recommendation": result.get("recommendation", ""),
                "confidence_score": result.get("confidence_score", 0.0),
                "risk_level": result.get("risk_level", "中等"),
                "key_points": result.get("key_points", []),
                "execution_time": result.get("execution_time", 0),
                "tokens_used": result.get("tokens_used", 0),
            }

            db.analysis_reports.update_one(
                {"task_id": task_id},
                {"$set": document},
                upsert=True
            )
            logger.info(f"✅ Analysis results have been saved to the database: {task_id}")
            logger.debug(f"📊 saved decision: {result.get('decision', {})}")
        except Exception as e:
            logger.error(f"❌ 保存分析结果失败: {e}")

    def _resolve_stock_name(self, stock_code: str) -> str:
        """Parse stock names - logic consistent with SimpleAnalysisService"""
        if not stock_code:
            return ""

        try:
            db = self._get_db()
            code_str = str(stock_code).strip().zfill(6)

            if db is not None:
                if _unified_analysis_service_is_cn_etf_symbol(code_str):
                    etf_doc = db.etf_basic_info.find_one(
                        {"code": code_str},
                        {"name": 1, "fund_name": 1, "etf_name": 1, "_id": 0}
                    )
                    if etf_doc:
                        etf_name = etf_doc.get("name") or etf_doc.get("fund_name") or etf_doc.get("etf_name")
                        if etf_name:
                            return etf_name

                stock_doc = db.stock_basic_info.find_one(
                    {"$or": [{"code": code_str}, {"symbol": code_str}]},
                    {"name": 1, "stock_name": 1, "_id": 0}
                )
                if stock_doc:
                    stock_name = stock_doc.get("name") or stock_doc.get("stock_name")
                    if stock_name:
                        return stock_name

            # Prioritize trying to get structured data from data_source_manager
            try:
                from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                info_dict = get_info_dict(stock_code)
                if info_dict and isinstance(info_dict, dict) and info_dict.get('name'):
                    return info_dict['name']
            except Exception:
                pass

            # Alternative: Get string from interface and parse
            from tradingagents.dataflows.interface import get_china_stock_info_unified
            info_str = get_china_stock_info_unified(stock_code)

            if info_str and isinstance(info_str, str) and "股票名称:" in info_str:
                stock_name = info_str.split("股票名称:")[1].split("\n")[0].strip()
                if stock_name:
                    return stock_name
            elif info_str and isinstance(info_str, dict) and info_str.get("name"):
                return info_str["name"]

        except Exception as e:
            logger.warning(f"⚠️ 解析股票名称失败: {stock_code} - {e}")

        return f"{'ETF' if _unified_analysis_service_is_cn_etf_symbol(stock_code) else 'stocks'}{stock_code}"

    # ==================== Position analysis related methods ====================

    async def create_position_analysis_task(
        self,
        user_id: str,
        code: str,
        market: str = "CN",
        task_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a position analysis task

        Args:
            user_id: User ID
            code: Stock code
            market: market type (CN/HK/US)
            task_params: Task parameters

        Returns:
            Task information dictionary
        """
        logger.info(f"🔧 [Position analysis service] create_position_analysis_task called: user_id={user_id}, code={code}, market={market}")
        from bson import ObjectId
        from app.core.database import get_mongo_db

        task_id = str(uuid.uuid4())
        logger.info(f"📝 [Position analysis service] Generate tasks ID: {task_id}")
        task_params = task_params or {}

        # 🔥 Read risk preference settings from user preferences
        from app.routers.analysis import get_user_risk_preference
        preference_type = await get_user_risk_preference(user_id)
        logger.info(f"📊 [Position analysis service] Use user risk preferences: {preference_type}")

        # Create unified analysis tasks
        logger.info("🔄 [Position analysis service] Create a UnifiedAnalysisTask object...")
        task = UnifiedAnalysisTask(
            task_id=task_id,
            user_id=ObjectId(user_id),
            task_type=AnalysisTaskType.POSITION_ANALYSIS,
            task_params={
                "code": code,
                "market": market,
                **task_params
            },
            engine_type="v2",  # Using v2.0 engine
            preference_type=preference_type,  # 🔥 Use user preferences
            status=AnalysisStatus.PENDING,
            created_at=now_tz(),  # ✅ Use now_tz() Make sure to include time zone information
        )

        # Save to database
        logger.info("💾 [Position analysis service] Prepare to save to database...")
        try:
            db = get_mongo_db()
            task_dict = task.model_dump(by_alias=True, exclude={"id"})

            # ✅ Make sure user_id is of type ObjectId, not a string
            if 'user_id' in task_dict and isinstance(task_dict['user_id'], str):
                task_dict['user_id'] = ObjectId(task_dict['user_id'])
                logger.info(f"🔄 [Position analysis service] Convert user_id from string to ObjectId: {task_dict['user_id']}")

            logger.info(f"💾 [持仓分析服务] 保存文档: user_id={task_dict.get('user_id')} (类型: {type(task_dict.get('user_id'))})")

            await db.unified_analysis_tasks.insert_one(task_dict)
            logger.info(f"✅ [Position analysis service] Saved to database, task ID: {task_id}")
            logger.info(f"✅ [Position analysis service] Task has been created: {task_id} - {code}")
        except Exception as e:
            logger.error(f"❌ [Position analysis] Failed to save task: {e}")
            raise

        # Save to memory state manager
        logger.info("💾 [Position analysis service] Prepare to save to memory state manager...")
        memory_manager = get_memory_state_manager()
        await memory_manager.create_task(
            task_id=task_id,
            user_id=user_id,
            stock_code=code,
            stock_name=f"{code} 持仓分析",
            parameters=task_params,
        )
        logger.info("✅ [Position analysis service] Saved to memory state manager")

        logger.info("🎉 [Position analysis service] The task is created and results are ready to be returned.")
        return {
            "task_id": task_id,
            "code": code,
            "market": market,
            "status": "pending",
            "message": "The position analysis task has been created and is expected to take 2-5 minutes.",
            "created_at": task.created_at.isoformat()
        }

    async def execute_position_analysis(
        self,
        task_id: str,
        user_id: str,
        code: str,
        market: str = "CN",
        task_params: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Perform position analysis

        Args:
            task_id: Task ID
            user_id: User ID
            code: Stock code
            market: market type
            task_params: Task parameters
            progress_callback: Progress callback function

        Returns:
            Analysis result dictionary
        """
        logger.info(f"🚀 [Position analysis service] execute_position_analysis called: task_id={task_id}, code={code}")
        logger.info(f"📋 [Position analysis service] Task parameters: {task_params}")

        try:
            # Update task status to Processing
            await self._update_position_task_status(
                task_id=task_id,
                status=AnalysisStatus.PROCESSING,
                message="正在分析持仓..."
            )

            # Call the position analysis service
            from app.services.portfolio_service import get_portfolio_service
            from app.models.portfolio import PositionAnalysisByCodeRequest

            portfolio_service = get_portfolio_service()

            # Build an analysis request
            task_params = task_params or {}
            analysis_request = PositionAnalysisByCodeRequest(
                code=code,
                market=market,
                research_depth=task_params.get("research_depth", "标准"),
                include_add_position=task_params.get("include_add_position", True),
                target_profit_pct=task_params.get("target_profit_pct", 20.0),
                total_capital=task_params.get("total_capital"),
                max_position_pct=task_params.get("max_position_pct", 30.0),
                max_loss_pct=task_params.get("max_loss_pct", 10.0),
                risk_tolerance=task_params.get("risk_tolerance", "medium"),
                investment_horizon=task_params.get("investment_horizon", "medium"),
                analysis_focus=task_params.get("analysis_focus", "comprehensive"),
                position_type=task_params.get("position_type", "real"),
            )

            # Perform analysis
            report = await portfolio_service.analyze_position_by_code(
                user_id=user_id,
                code=code,
                market=market,
                params=analysis_request
            )

            # Format results
            result = {
                "success": True,
                "task_id": task_id,
                "code": code,
                "market": market,
                "analysis_id": report.analysis_id,
                "position_snapshot": report.position_snapshot.model_dump() if report.position_snapshot else None,
                "ai_analysis": report.ai_analysis.model_dump() if report.ai_analysis else None,
                "status": report.status.value,
                "execution_time": report.execution_time,
                "error_message": report.error_message,
            }

            # Update task status to complete
            await self._update_position_task_status(
                task_id=task_id,
                status=AnalysisStatus.COMPLETED if report.status.value == "completed" else AnalysisStatus.FAILED,
                message="持仓分析完成" if report.status.value == "completed" else report.error_message,
                result=result
            )

            if report.status.value == "completed":
                try:
                    from app.services.intelligent_assistant_service import write_report_back_to_assistant_thread

                    preferred_thread_id = ((task_params or {}).get("_assistant_thread_id") or "").strip() or None
                    report_summary = ((report.ai_analysis.action_reason if report.ai_analysis else "") or "")[:400]
                    writeback_message = (
                        f"【持仓分析已归档】{code}({market})\n"
                        f"Task ID: {task_id}\n"
                        f"Summary: {(report_summary or 'The position analysis is completed and can be viewed in the associated report.')[:300]}"
                    )
                    await write_report_back_to_assistant_thread(
                        db=get_mongo_db(),
                        user_id=user_id,
                        preferred_thread_id=preferred_thread_id,
                        report_ref={
                            "ref_type": "position_report",
                            "report_key": str(report.analysis_id or task_id),
                            "source_collection": "position_analysis_reports",
                            "title": f"{code} 持仓分析报告",
                            "symbol": code,
                            "summary": report_summary,
                            "status": report.status.value,
                            "task_id": task_id,
                            "analysis_id": str(report.analysis_id),
                            "created_at": now_tz(),
                        },
                        summary_message=writeback_message,
                    )
                except Exception as writeback_err:
                    logger.warning(f"⚠️ [Position analysis] Failed to write back research topic (ignored): {writeback_err}")

            logger.info(f"✅ [Position analysis] Execution completed: {task_id} - {code}")
            return result

        except Exception as e:
            logger.error(f"❌ [Position analysis] Execution failed: {task_id} - {e}", exc_info=True)

            # Update task status is failed
            await self._update_position_task_status(
                task_id=task_id,
                status=AnalysisStatus.FAILED,
                message=f"持仓分析失败: {str(e)}"
            )

            return {
                "success": False,
                "task_id": task_id,
                "code": code,
                "error": str(e),
            }

    async def _update_position_task_status(
        self,
        task_id: str,
        status: AnalysisStatus,
        message: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
    ):
        """更新持仓分析任务状态"""
        from app.core.database import get_mongo_db

        try:
            db = get_mongo_db()

            update_data = {
                "status": status.value if hasattr(status, "value") else status,  # Make sure to store as string value
                "message": message,
                "updated_at": now_tz(),  # ✅ Use now_tz() Make sure to include time zone information
            }

            if status == AnalysisStatus.PROCESSING:
                update_data["started_at"] = now_tz()  # ✅ Use now_tz() Make sure to include time zone information
            elif status in [AnalysisStatus.COMPLETED, AnalysisStatus.FAILED]:
                update_data["completed_at"] = now_tz()  # ✅ Use now_tz() Make sure to include time zone information

            if result is not None:
                update_data["result"] = result

            await db.unified_analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": update_data}
            )

            # Update memory status
            memory_manager = get_memory_state_manager()
            memory_status = TaskStatus.RUNNING if status == AnalysisStatus.PROCESSING else (
                TaskStatus.COMPLETED if status == AnalysisStatus.COMPLETED else TaskStatus.FAILED
            )
            await memory_manager.update_task_status(
                task_id=task_id,
                status=memory_status,
                message=message or "",
            )

        except Exception as e:
            logger.error(f"❌ [Position analysis] Failed to update task status: {e}")

    # ==================== Methods related to transaction review ====================

    async def create_trade_review_task(
        self,
        user_id: str,
        request: "CreateTradeReviewRequest",
    ) -> Dict[str, Any]:
        """Create a transaction review task

        Reference:create_position_analysis_task() realization

        Args:
            user_id: User ID
            request: Review request

        Returns:
            Task information dictionary {"task_id": "...", "status": "pending"}
        """
        logger.info("🔧 [Transaction review service] create_trade_review_task called")
        logger.info(f"   📋 user_id: {user_id}")
        logger.info(f"   📋 code: {request.code}")
        logger.info(f"   📋 trade_ids: {request.trade_ids}")
        logger.info(f"   📋 review_type: {request.review_type}")
        logger.info(f"   📋 source: {request.source}")
        logger.info(f"   📋 use_workflow: {request.use_workflow}")

        from bson import ObjectId
        from app.core.database import get_mongo_db

        task_id = str(uuid.uuid4())
        logger.info(f"📝 [Transaction review service] Generate tasks ID: {task_id}")

        # Get stock name
        stock_code = request.code or "未知"
        stock_name = self._resolve_stock_name(stock_code) if stock_code != "未知" else "未知股票"
        logger.info(f"📊 [Transaction review service] stock information: code={stock_code}, name={stock_name}")

        # 🔑 Extract market field from transaction information (quick inference, no waiting for database query)
        market = None
        # Prioritize inference from code (Chinese stock codes are usually 6 digits) to avoid database query delays
        if stock_code:
            if len(stock_code) == 6 and stock_code.isdigit():
                # China's stock code: starting with 6 is the Science and Technology Innovation Board, starting with 0/3 is the GEM/Shenzhen Stock Exchange, and starting with 6 is the Shanghai Stock Exchange
                market = "CN"
                logger.info(f"📊 [Transaction review service] Inferred from stock ticker market: {market}")
            elif stock_code.startswith("HK"):
                market = "HK"
            elif stock_code.startswith("US") or "." in stock_code:
                market = "US"
        
        # If no market is inferred, use the default value (CN)
        if not market:
            market = "CN"
            logger.info(f"📊 [Transaction review service] Use default market: {market}")
        
        # Note: The precise extraction of market information will be completed in the background task. Only quick inference is done here to ensure immediate return.
        
        # Prepare task parameters
        task_params = {
            "trade_ids": request.trade_ids,
            "stock_code": stock_code,  # Use stock_code instead code
            "code": request.code,  # Keep original fields for compatibility
            "stock_name": stock_name,  # Add stock name
            "market": market,  # 🔑 Add market field
            "market_type": market,  # 🔑 Compatible fields
            "review_type": request.review_type,
            "source": request.source or "paper",
            "trading_system_id": request.trading_system_id,
            "use_workflow": request.use_workflow
        }
        logger.info(f"📦 [Transaction review service] Task parameters: {task_params}")

        # Create unified analysis tasks
        logger.info("🔄 [Transaction review service] Create a UnifiedAnalysisTask object...")
        task = UnifiedAnalysisTask(
            task_id=task_id,
            user_id=ObjectId(user_id),
            task_type=AnalysisTaskType.TRADE_REVIEW,
            task_params=task_params,
            engine_type="workflow" if request.use_workflow else "auto",
            status=AnalysisStatus.PENDING,
            created_at=now_tz(),
        )
        logger.info("✅ [Transaction review service] UnifiedAnalysisTask Object created successfully")
        logger.info(f"   📋 task_type: {task.task_type}")
        logger.info(f"   📋 engine_type: {task.engine_type}")
        logger.info(f"   📋 status: {task.status}")

        # Save to database
        logger.info("💾 [Transaction review service] Prepare to save to database...")
        try:
            db = get_mongo_db()
            logger.info("✅ [Transaction review service] Obtain database connection successfully")

            task_dict = task.model_dump(by_alias=True, exclude={"id"})
            logger.info(f"📦 [Transaction review service] task dictionary: {list(task_dict.keys())}")

            # Make sure user_id is of type ObjectId
            if 'user_id' in task_dict and isinstance(task_dict['user_id'], str):
                logger.info("🔄 [Transaction review service] Convert user_id to ObjectId")
                task_dict['user_id'] = ObjectId(task_dict['user_id'])

            await db.unified_analysis_tasks.insert_one(task_dict)
            logger.info(f"✅ [Transaction review service] Task saved to database: {task_id}")
        except Exception as e:
            logger.error(f"❌ [Transaction review service] Failed to save task to database: {e}", exc_info=True)
            raise

        # Save to memory state manager
        logger.info("💾 [Transaction review service] Prepare to save to memory state manager...")
        try:
            memory_manager = get_memory_state_manager()
            logger.info("✅ [Transaction review service] Obtain memory status manager successfully")

            await memory_manager.create_task(
                task_id=task_id,
                user_id=user_id,
                stock_code=stock_code,  # Use what you have obtained previously stock_code
                stock_name=stock_name,  # Use what you have obtained previously stock_name
                parameters=task_params
            )
            logger.info(f"✅ [Transaction review service] Task saved to memory: {task_id}")
        except Exception as e:
            logger.error(f"❌ [Transaction review service] Failed to save task to memory: {e}", exc_info=True)
            # Memory status failure does not affect the main process and continues execution.

        result = {
            "task_id": task_id,
            "status": AnalysisStatus.PENDING.value,
            "message": "The transaction review task has been created and is expected to take 1-3 minutes.",
            "created_at": task.created_at.isoformat()
        }
        logger.info("🎉 [Transaction review service] create_trade_review_task Complete")
        logger.info(f"   📋 返回结果: {result}")

        return result

    async def execute_trade_review(
        self,
        task_id: str,
        user_id: str,
        request: "CreateTradeReviewRequest",
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Perform transaction review tasks

        Reference:execute_position_analysis() realization

        Args:
            task_id: Task ID
            user_id: User ID
            request: Review request
            progress_callback: Progress callback function

        Returns:
            Analysis result dictionary
        """
        logger.info("🚀 [Transaction review service] execute_trade_review called")
        logger.info(f"   📋 task_id: {task_id}")
        logger.info(f"   📋 user_id: {user_id}")
        logger.info(f"   📋 trade_ids: {request.trade_ids}")
        logger.info(f"   📋 code: {request.code}")
        logger.info(f"   📋 review_type: {request.review_type}")
        logger.info(f"   📋 source: {request.source}")
        logger.info(f"   📋 use_workflow: {request.use_workflow}")

        try:
            # Update task status to Processing
            logger.info("🔄 [Transaction review service] Update task status to PROCESSING...")
            await self._update_trade_review_task_status(
                task_id=task_id,
                status=AnalysisStatus.PROCESSING,
                message="正在进行交易复盘..."
            )
            logger.info("✅ [Transaction review service] The task status has been updated to PROCESSING")

            # 🔥 Create a wrapped progress callback: save progress to database and memory
            from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            memory_manager = get_memory_state_manager()

            async def wrapped_progress_callback(progress: int, message: str, **kwargs):
                """Wrapped progress callback: update task progress and save to database and memory"""
                step_name = kwargs.get("step_name", "")

                # Update memory state manager
                await memory_manager.update_task_status(
                    task_id=task_id,
                    status=TaskStatus.RUNNING,
                    progress=progress,
                    message=message,
                    current_step=step_name or message,
                    current_step_name=step_name,
                    current_step_description=message
                )

                # Update task progress in database
                from app.core.database import get_mongo_db
                db = get_mongo_db()
                await db.unified_analysis_tasks.update_one(
                    {"task_id": task_id},
                    {"$set": {
                        "progress": progress,
                        "current_step": step_name or message,
                        "message": message
                    }}
                )

                logger.info(f"📊 [Transaction review] Progress saved: {progress}% - {step_name} - {message}")

                # Call the original callback (if any)
                if progress_callback:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(progress, message, **kwargs)
                    else:
                        progress_callback(progress, message, **kwargs)

            # Call existing review service
            logger.info("🔄 [Transaction review service] Get TradeReviewService instance...")
            from app.services.trade_review_service import get_trade_review_service

            trade_review_service = get_trade_review_service()
            logger.info("✅ [Transaction review service] TradeReviewService Instance obtained successfully")

            # Perform review (using existing logic)
            logger.info("🔄 [Transaction review service] call TradeReviewService.create_trade_review()...")
            logger.info("   📋 This will use existing review logic (including the workflow engine)")

            report = await trade_review_service.create_trade_review(
                user_id=user_id,
                request=request,
                progress_callback=wrapped_progress_callback  # 🔥 Pass progress callback
            )
            logger.info("✅ [Transaction review service] TradeReviewService.create_trade_review() Executed successfully")
            logger.info(f"   📋 review_id: {report.review_id}")
            logger.info(f"   📋 status: {report.status}")
            logger.info(f"   📋 code: {report.trade_info.code}")
            logger.info(f"   📋 name: {report.trade_info.name}")
            logger.info(f"   📋 execution_time: {report.execution_time}s")

            # Format results
            logger.info("🔄 [Transaction review service] Format results...")
            result = {
                "success": True,
                "task_id": task_id,
                "review_id": report.review_id,
                "code": report.trade_info.code,
                "name": report.trade_info.name,
                "ai_review": report.ai_review.model_dump() if report.ai_review else None,
                "trade_info": report.trade_info.model_dump(),
                "market_snapshot": report.market_snapshot.model_dump() if report.market_snapshot else None,
                "status": report.status.value,
                "execution_time": report.execution_time
            }
            logger.info("✅ [Transaction review service] Result formatting completed")

            # Update task status to complete
            logger.info("🔄 [Transaction review service] Update task status to COMPLETED...")
            # 🔑 Pass execution_time to avoid recalculation
            await self._update_trade_review_task_status(
                task_id=task_id,
                status=AnalysisStatus.COMPLETED,
                result=result,
                message="复盘完成",
                execution_time=report.execution_time  # 🔑 Use report in execution_time
            )
            logger.info("✅ [Transaction review service] The task status has been updated to COMPLETED")

            logger.info(f"🎉 [Transaction review service] Task execution successful: {task_id}")
            logger.info(f"   📋 总耗时: {report.execution_time}s")

            return result

        except Exception as e:
            logger.error(f"❌ [Transaction review service] Task execution failed: {task_id}")
            logger.error(f"   📋 错误类型: {type(e).__name__}")
            logger.error(f"   📋 错误信息: {str(e)}")
            logger.error("   📋 详细堆栈:", exc_info=True)

            # Update task status is failed
            logger.info("🔄 [Transaction review service] Update task status to FAILED...")
            await self._update_trade_review_task_status(
                task_id=task_id,
                status=AnalysisStatus.FAILED,
                error_message=str(e),
                message=f"复盘失败: {str(e)}"
            )
            logger.info("✅ [Transaction review service] The task status has been updated to FAILED")

            # Return wrong result
            error_result = {
                "success": False,
                "task_id": task_id,
                "error": str(e),
            }
            logger.info(f"📋 [Transaction review service] Return wrong result: {error_result}")

            return error_result

    async def _update_trade_review_task_status(
        self,
        task_id: str,
        status: AnalysisStatus,
        message: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        execution_time: Optional[float] = None,  # 🔑 New parameter: execution time
    ):
        """Update transaction review task status

        Reference:_update_position_task_status() realization
        """
        logger.info("🔄 [Transaction review service] _update_trade_review_task_status called")
        logger.info(f"   📋 task_id: {task_id}")
        logger.info(f"   📋 status: {status}")
        logger.info(f"   📋 message: {message}")
        logger.info(f"   📋 has_result: {result is not None}")
        logger.info(f"   📋 error_message: {error_message}")

        from app.core.database import get_mongo_db

        try:
            # Update database
            logger.info("💾 [Transaction review service] Prepare to update the database...")
            db = get_mongo_db()
            logger.info("✅ [Transaction review service] Obtain database connection successfully")

            update_data = {
                "status": status.value if hasattr(status, "value") else status,
                "message": message,
                "updated_at": now_tz(),
            }

            if status == AnalysisStatus.PROCESSING:
                update_data["started_at"] = now_tz()
                logger.info(f"   📋 settings started_at: {update_data['started_at']}")
            elif status in [AnalysisStatus.COMPLETED, AnalysisStatus.FAILED]:
                completed_at = now_tz()
                update_data["completed_at"] = completed_at
                logger.info(f"   📋 settings completed_at: {completed_at}")
                
                # 🔑 settings execution_time
                if execution_time is not None:
                    # If execution_time is passed in, use it directly
                    update_data["execution_time"] = execution_time
                    logger.info(f"   📋 Use the incoming execution_time: {execution_time:.2f}s")
                else:
                    # Otherwise calculate execution_time
                    task_doc = await db.unified_analysis_tasks.find_one({"task_id": task_id})
                    if task_doc and task_doc.get("started_at"):
                        started_at = task_doc["started_at"]
                        if isinstance(started_at, str):
                            from datetime import datetime
                            started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                        
                        # 🔥 Ensure consistent time zones: use ensure_timezone to unify time zones
                        # completed_at is offset-aware (from now_tz()) , started_at It also needs to be offset-aware
                        from app.utils.timezone import ensure_timezone
                        started_at = ensure_timezone(started_at)
                        completed_at = ensure_timezone(completed_at)
                        
                        calculated_time = (completed_at - started_at).total_seconds()
                        update_data["execution_time"] = calculated_time
                        logger.info(f"   📋 Calculate execution_time: {calculated_time:.2f}s (started_at: {started_at}, completed_at: {completed_at})")
                    else:
                        logger.warning("   ⚠️ Unable to calculate execution_time: started_at does not exist")
                
                # 🔑 Make sure progress is 100 (if completed)
                if status == AnalysisStatus.COMPLETED:
                    update_data["progress"] = 100
                    logger.info("   📋 settings progress: 100")

            if result is not None:
                update_data["result"] = result
                logger.info(f"   📋 设置 result (包含 {len(result)} 个字段)")

            if error_message is not None:
                update_data["error_message"] = error_message
                logger.info(f"   📋 settings error_message: {error_message}")

            logger.info("🔄 [Transaction review service] Perform database updates...")
            await db.unified_analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": update_data}
            )
            logger.info("✅ [Transaction review service] Database update successful")

            # Update memory status
            logger.info("💾 [Transaction review service] Prepare to update memory status...")
            memory_manager = get_memory_state_manager()
            logger.info("✅ [Transaction review service] Obtain memory status manager successfully")

            memory_status = TaskStatus.RUNNING if status == AnalysisStatus.PROCESSING else (
                TaskStatus.COMPLETED if status == AnalysisStatus.COMPLETED else TaskStatus.FAILED
            )
            logger.info(f"   📋 内存状态: {memory_status}")

            if status == AnalysisStatus.PROCESSING:
                logger.info("🔄 [Transaction review service] Update the memory status to RUNNING...")
                await memory_manager.update_task_status(
                    task_id=task_id,
                    status=memory_status,
                    message=message or "处理中...",
                )
                logger.info("✅ [Transaction review service] The memory status has been updated to RUNNING")
            elif status == AnalysisStatus.COMPLETED:
                logger.info("🔄 [Transaction review service] Complete the task...")
                await memory_manager.update_task_status(
                    task_id=task_id,
                    status=memory_status,
                    progress=100,
                    message=message or "分析完成",
                    result_data=result
                )
                logger.info("✅ [Transaction review service] Task marked as complete")
            elif status == AnalysisStatus.FAILED:
                logger.info("🔄 [Transaction review service] Mark task failed...")
                await memory_manager.update_task_status(
                    task_id=task_id,
                    status=memory_status,
                    progress=0,
                    message=message or "分析失败",
                    error_message=error_message or "未知错误"
                )
                logger.info("✅ [Transaction review service] Task marked as failed")

            logger.info("🎉 [Transaction review service] _update_trade_review_task_status Complete")

        except Exception as e:
            logger.error("❌ [Transaction review service] Failed to update task status")
            logger.error(f"   📋 task_id: {task_id}")
            logger.error(f"   📋 错误类型: {type(e).__name__}")
            logger.error(f"   📋 错误信息: {str(e)}")
            logger.error("   📋 详细堆栈:", exc_info=True)

    async def _update_task_failed(self, task_id: str, error_message: str):
        """更新任务状态为失败"""
        db = self._get_db()
        if db is None:
            return

        try:
            db.analysis_tasks.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "status": "failed",
                        "error_message": error_message,
                        "completed_at": now_tz(),  # ✅ Use now_tz() Make sure to include time zone information
                        "updated_at": now_tz(),  # ✅ Use now_tz() Make sure to include time zone information
                    }
                }
            )
        except Exception as e:
            logger.error(f"❌ 更新任务状态失败: {e}")


# Singleton instance
_unified_service: Optional[UnifiedAnalysisService] = None


def get_unified_analysis_service() -> UnifiedAnalysisService:
    """获取统一分析服务单例"""
    global _unified_service
    if _unified_service is None:
        _unified_service = UnifiedAnalysisService()
    return _unified_service


# ------------------------------------------------------------------
#  mem0 unified memory layer — Workflow analytics integration
# ------------------------------------------------------------------

def _get_memory_market_type(stock_code: str) -> str:
    try:
        from tradingagents.utils.stock_utils import StockMarket, StockUtils

        market = StockUtils.identify_stock_market(stock_code)
        mapping = {
            StockMarket.CHINA_A: "cn",
            StockMarket.HONG_KONG: "hk",
            StockMarket.US: "us",
            StockMarket.UNKNOWN: "cn",
        }
        return mapping.get(market, "cn")
    except Exception:
        return "cn"

async def _recall_analysis_memory(db, user_id: str, stock_code: str) -> str:
    """Recall the user s historical analysis memory of this stock from mem0"""
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)
        normalized_symbol = str(stock_code or "").strip().upper()
        market_type = _get_memory_market_type(normalized_symbol)

        analysis_memory = await svc.recall_formatted(
            query=f"{normalized_symbol} 历史分析结论",
            user_id=user_id,
            scopes=["analysis_insight"],
            metadata_filters={
                "object_type": "stock",
                "memory_kind": "stock_analysis",
                "symbol": normalized_symbol,
                "market": market_type,
            },
            limit=3,
            max_chars=1200,
        )
        preference_memory = await svc.recall_formatted(
            query=f"{normalized_symbol} 分析偏好",
            user_id=user_id,
            scopes=["user_preference"],
            limit=2,
            max_chars=300,
        )
        return f"{analysis_memory}{preference_memory}"
    except Exception as e:
        logger.debug("[mem0] Analyze memory recall failure: %s", e)
        return ""


async def _store_analysis_insight(
    db, user_id: str, stock_code: str,
    analysis_date: str, summary: str, recommendation: str, task_id: str,
) -> None:
    """Write the analysis conclusion into the objectized stock long-term memory (asynchronously, without blocking the main process)"""
    if not summary and not recommendation:
        return
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)
        normalized_symbol = str(stock_code or "").strip().upper()
        structured_summary = str(summary or recommendation or "").strip()
        structured_recommendation = str(recommendation or "").strip()
        result = await svc.store_stock_analysis(
            user_id=user_id,
            symbol=normalized_symbol,
            market=_get_memory_market_type(normalized_symbol),
            summary=structured_summary,
            recommendation=structured_recommendation,
            analysis_date=analysis_date,
            task_id=task_id,
            agent_id="workflow_analyst",
            session_id=task_id,
            next_checks=[structured_recommendation] if structured_recommendation else None,
        )
        logger.info(
            "[mem0] Objectized stock memory writing results — user=%s symbol=%s task=%s facts=%d success=%s error=%s",
            user_id,
            normalized_symbol,
            task_id,
            result.facts_extracted,
            result.success,
            result.error or "",
        )
    except Exception as e:
        logger.debug("[mem0] Analytics insights storage failed (ignored): %s", e)

# === task_analysis_service.py ===
"""
Task Analysis Services

Analysis task management service based on UnifiedAnalysisTask model
Provide a unified task creation, execution, and query interface
"""

from typing import Dict, Any, Optional, List, Callable, Union
import logging
import uuid
import asyncio
import inspect
from datetime import datetime

from app.models.analysis import (
    UnifiedAnalysisTask,
    AnalysisTaskType,
    AnalysisStatus
)
from app.models.user import PyObjectId
try:
    from app.services.workflow_registry import AnalysisWorkflowRegistry
except ImportError:
    AnalysisWorkflowRegistry = None
from app.core.database import get_mongo_db
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")


def _task_analysis_service_is_cn_etf_symbol(code: Optional[str]) -> bool:
    code_str = str(code or "").strip()
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


def _normalize_memory_market(symbol: str, raw_market: Optional[str] = None) -> str:
    normalized_market = str(raw_market or "").strip().lower()
    if normalized_market in {"cn", "a股", "a_shares", "china", "china_a", "ashare"}:
        return "cn"
    if normalized_market in {"hk", "港股", "hongkong", "hong_kong"}:
        return "hk"
    if normalized_market in {"us", "美股", "usa", "united_states"}:
        return "us"

    try:
        from tradingagents.utils.stock_utils import StockMarket, StockUtils

        market = StockUtils.identify_stock_market(symbol)
        mapping = {
            StockMarket.CHINA_A: "cn",
            StockMarket.HONG_KONG: "hk",
            StockMarket.US: "us",
            StockMarket.UNKNOWN: "cn",
        }
        return mapping.get(market, "cn")
    except Exception:
        return "cn"


class TaskCancelledException(Exception):
    """任务被取消异常"""
    pass


class TaskAnalysisService:
    """Task Analysis Services
    
    Analysis task management based on UnifiedAnalysisTask model
    
    Usage example:
        service = TaskAnalysisService()
        
        # Create and execute tasks
        task = await service.create_and_execute_task(
            user_id=user_id,
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params={"symbol": "000858", "market_type": "cn"}
        )
        
        # Query tasks
        task = await service.get_task(task_id)
        
        # Query all tasks of the user
        tasks = await service.list_user_tasks(user_id)
    """
    
    def __init__(self):
        """初始化服务"""
        self.engine = UnifiedAnalysisEngine()
        self.db = get_mongo_db()
        self.collection = self.db.unified_analysis_tasks
        self.logger = logger
    
    async def create_task(
        self,
        user_id: PyObjectId,
        task_type: AnalysisTaskType,
        task_params: Dict[str, Any],
        engine_type: str = "auto",
        preference_type: str = "neutral",
        workflow_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        task_id: Optional[str] = None  # 🔥 Support incoming task_id
    ) -> UnifiedAnalysisTask:
        """Create analysis tasks

        Args:
            user_id: User ID
            task_type: Task type
            task_params: Task parameters
            engine_type: Engine type (auto/workflow/legacy/llm)
            preference_type: Analyze preferences (aggressive/neutral/conservative)
            workflow_id: Workflow ID (optional)
            batch_id: Batch ID (optional)
            task_id: Task ID (optional, automatically generated if not provided)

        Returns:
            Created task object
        """
        # Generate task ID if not provided
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        # Create task object
        task = UnifiedAnalysisTask(
            task_id=task_id,
            user_id=user_id,
            task_type=task_type,
            task_params=task_params,
            engine_type=engine_type,
            preference_type=preference_type,
            workflow_id=workflow_id,
            batch_id=batch_id,
            status=AnalysisStatus.PENDING,
            created_at=now_tz()
        )
        
        # Save to database
        await self._save_task(task)
        
        self.logger.info(f"✅ 创建任务: {task_id} (类型: {task_type})")
        
        return task
    
    async def execute_task(
        self,
        task_or_id: Union[UnifiedAnalysisTask, str],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> UnifiedAnalysisTask:
        """Perform analysis tasks

        Args:
            task_or_id: task object or task ID
            progress_callback: Progress callback function

        Returns:
            Updated task object
        """
        # If the task_id is passed in, get the task object first
        if isinstance(task_or_id, str):
            task = await self.get_task(task_or_id)
            if not task:
                raise ValueError(f"任务不存在: {task_or_id}")
        else:
            task = task_or_id

        self.logger.info(f"🚀 执行任务: {task.task_id}")

        from app.services.memory_state_manager import get_memory_state_manager

        memory_manager = get_memory_state_manager()
        memory_task = await memory_manager.get_task(task.task_id)
        if not memory_task:
            task_params = task.task_params or {}
            await memory_manager.create_task(
                task_id=task.task_id,
                user_id=str(task.user_id),
                stock_code=str(task_params.get("symbol") or task_params.get("stock_code") or ""),
                parameters=task_params,
                stock_name=None,
            )

        # Create a wrapped progress callback that updates the database and memory
        async def wrapped_progress_callback(progress: int, message: str, **kwargs):
            """Wrapped progress callback: update task progress and save to database and memory"""
            # � New: Check if task was canceled
            if await self._is_task_cancelled(task.task_id):
                self.logger.warning(f"⚠️ 任务已被取消: {task.task_id}")
                raise TaskCancelledException(f"任务 {task.task_id} 已被用户取消")

            # �🔑 Key: extract step_name (short name) from kwargs
            step_name = kwargs.get("step_name", "")

            # Update task object
            task.progress = progress
            task.current_step = step_name or message  # ✅ Use step_name instead message
            task.message = message  # ✅ Save detailed description to message field

            # Save to database
            await self._update_task(task)

            # 🔑 Key: Update memory status at the same time
            from app.services.memory_state_manager import TaskStatus
            await memory_manager.update_task_status(
                task_id=task.task_id,
                status=TaskStatus.RUNNING,
                progress=progress,
                message=message,
                current_step=step_name or message,
                current_step_name=step_name,  # 🔑 Pass step name
                current_step_description=message  # 🔑 Transfer step description
            )

            # Call the original callback (if any)
            if progress_callback:
                if asyncio.iscoroutinefunction(progress_callback):
                    await progress_callback(progress, message, **kwargs)
                else:
                    progress_callback(progress, message, **kwargs)

        try:
            # 🔥🔥🔥 Data verification is disabled (the function is not perfect)
            # Reason: The historical data synchronization function is not completed, and the verification will prevent normal analysis.
            # To restore, uncomment the following:
            # if task.task_type == AnalysisTaskType.STOCK_ANALYSIS:
            #     validation_result = await self._validate_task_data(task)
            #     if not validation_result.is_valid:
            #         # Data verification failed, update task status and return
            #         task.status = AnalysisStatus.FAILED
            #         task.error_message = validation_result.message
            #         task.completed_at = now_tz()
            #         await self._update_task(task)
            #
            #         # Update memory status
            #         from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            #         memory_manager = get_memory_state_manager()
            #         await memory_manager.update_task_status(
            #             task_id=task.task_id,
            #             status=TaskStatus.FAILED,
            #             progress=0,
            #             message=validation_result.message,
            #             current_step="data_validation",
            #             current_step_name="Data verification",
            #             current_step_description=validation_result.message
            #         )
            #
            #         self.logger.warning(f"⚠️ Task {task.task_id} Data verification failed: {validation_result.message}")
            #         raise ValueError(validation_result.message)

            # Update task status to Processing
            task.status = AnalysisStatus.PROCESSING
            task.started_at = now_tz()
            task.progress = 0
            await self._update_task(task)

            # 🔑 Key: Update memory status at the same time
            from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            memory_manager = get_memory_state_manager()
            await memory_manager.update_task_status(
                task_id=task.task_id,
                status=TaskStatus.RUNNING,
                progress=0,
                message="开始分析...",
                current_step="initialization",
                current_step_name="初始化",  # 🔑 Pass step name
                current_step_description="开始分析..."  # 🔑 Transfer step description
            )

            # Execute the task (the engine will update the status of the task object)
            result = await self.engine.execute_task(task, wrapped_progress_callback)

            # 🔑 Key: Format the result data to ensure it contains all fields required by the front end
            formatted_result = self._format_analysis_result(result, task)
            task.result = formatted_result

            # 🔑 Key: Set task completion time and execution time
            task.completed_at = now_tz()
            task.progress = 100  # Make sure the progress is 100
            if task.started_at:
                task.execution_time = (task.completed_at - task.started_at).total_seconds()
                self.logger.info(f"📊 任务执行时间: {task.execution_time:.2f}s")
            else:
                self.logger.warning("⚠️ The task does not have started_at and cannot be calculated execution_time")

            # 🔥 Save to analysis_reports collection (compatible with legacy API)
            # Note: You must save before updating the task in order to get the correct analysis_id
            saved_analysis_id = None
            if task.task_type in (AnalysisTaskType.STOCK_ANALYSIS, AnalysisTaskType.ETF_ANALYSIS):
                saved_analysis_id = await self._save_to_analysis_reports(task, formatted_result)
                # 🔑 Key: Update analysis_id in result to the saved true value ID
                if saved_analysis_id and task.result:
                    task.result["analysis_id"] = saved_analysis_id
                    self.logger.info(f"✅ Updated in task results analysis_id: {saved_analysis_id}")

            # 🧠 Objectized stock memory: only writes after real stock analysis is completed to avoid free text pollution.
            if task.task_type == AnalysisTaskType.STOCK_ANALYSIS:
                try:
                    await asyncio.wait_for(
                        self._store_stock_object_memory(task, formatted_result),
                        timeout=20,
                    )
                except asyncio.TimeoutError:
                    self.logger.warning(f"⚠️ Objectized stock memory write timeout(ignore): {task.task_id}")
                except Exception as memory_err:
                    self.logger.warning(f"⚠️ Objectized stock memory write failed(ignore): {memory_err}")

            # 🔑🔑🔑 Key fix: Persist the results first and update the memory status to COMPLETED,
            # Then perform slow operations (notifications, emails, user portraits, writing back research topics).
            # Avoid front-end detection progress=100 Race condition where data is not yet ready when /result is requested immediately after.
            task.status = AnalysisStatus.COMPLETED
            await self._update_task(task)

            # 🔑 Key: Update the memory status to complete (front-end polling relies on this status)
            from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            memory_manager = get_memory_state_manager()
            await memory_manager.update_task_status(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="分析完成",
                current_step="completed",
                current_step_name="已完成",
                current_step_description="分析完成",
                result_data=task.result
            )

            self.logger.info(f"✅ Task results are persisted and marked complete: {task.task_id}")

            # ---- The following are non-critical post-processing operations. Even if they fail, they will not affect the results obtained by the front end. ----
            if task.task_type in (AnalysisTaskType.STOCK_ANALYSIS, AnalysisTaskType.ETF_ANALYSIS):
                _symbol = (task.task_params or {}).get("symbol", "")
                _stock_name = formatted_result.get("stock_name") or formatted_result.get("stock_symbol") or _symbol
                # The stock_name in the results is often just the code itself, and the database is checked back to complete the Chinese name (such as Kweichow Moutai)
                if _symbol and _stock_name == _symbol:
                    try:
                        _stock_name = _get_cached_security_name(_symbol) or _stock_name
                    except Exception as name_err:
                        self.logger.debug(f"Failed to complete stock name(ignore): {name_err}")
                _name_label = f"{_stock_name}({_symbol})" if _stock_name and _stock_name != _symbol else _symbol
                _summary = formatted_result.get("summary") or formatted_result.get("executive_summary") or ""
                if _summary and len(_summary) > 80:
                    _summary = _summary[:80] + "…"

                # 📢 Unified notification: bell on the site + IM Callback (QQ, etc.)+ User configuration channels (Feishu/DingTalk, etc.)
                try:
                    from app.services.notifications_service import get_notifications_service
                    from app.models.notification import NotificationCreate
                    _notif_meta: Dict[str, Any] = {}
                    _im_channel = (task.task_params or {}).get("_im_channel")
                    if _im_channel:
                        _notif_meta["_im_channel"] = _im_channel
                    await get_notifications_service().create_and_publish(NotificationCreate(
                        user_id=str(task.user_id),
                        type="analysis",
                        title=f"✅ {_name_label} 分析完成",
                        content=_summary or "The analysis is complete, click to view the full report.",
                        link="/tasks/unified",
                        source="task_analysis",
                        severity="success",
                        metadata=_notif_meta,
                    ))
                except Exception as notif_err:
                    self.logger.warning(f"⚠️ Failed to send unified notification(ignore): {notif_err}")

                # 📧 Send email notification (including PDF attachment, keep independent path)
                try:
                    await self._send_analysis_email_notification(task, formatted_result)
                except Exception as email_err:
                    self.logger.warning(f"⚠️ Failed to send email notification(ignore): {email_err}")

                # 🧠 Update user portrait (recently_analyzed)
                try:
                    from app.services.intelligent_assistant_service import update_user_profile_with_analysis
                    _conclusion = (
                        formatted_result.get("investment_rating")
                        or formatted_result.get("comprehensive_conclusion")
                        or formatted_result.get("rating")
                        or ""
                    )
                    if isinstance(_conclusion, dict):
                        _conclusion = _conclusion.get("rating") or _conclusion.get("label") or str(_conclusion)
                    _conclusion = str(_conclusion)[:20]
                    await update_user_profile_with_analysis(
                        db=self.db,
                        user_id=str(task.user_id),
                        symbol=_symbol,
                        name=_stock_name,
                        conclusion=_conclusion,
                        task_id=str(task.task_id),
                    )
                except Exception as profile_err:
                    self.logger.warning(f"⚠️ Failed to update user portrait(ignore): {profile_err}")

                # 🔗 Automatically hang the completed report back to the current research topic; if there is no topic, enter"Report storage"
                try:
                    from app.services.intelligent_assistant_service import write_report_back_to_assistant_thread

                    preferred_thread_id = ((task.task_params or {}).get("_assistant_thread_id") or "").strip() or None
                    report_summary = (
                        formatted_result.get("summary")
                        or formatted_result.get("executive_summary")
                        or formatted_result.get("recommendation")
                        or ""
                    )
                    writeback_message = (
                        f"【分析报告已归档】{_stock_name}({_symbol})\n"
                        f"Task ID: {task.task_id}\n"
                        f"Summary: {(report_summary or 'The analysis is complete and can be viewed in the associated report.')[:300]}"
                    )
                    await write_report_back_to_assistant_thread(
                        db=self.db,
                        user_id=str(task.user_id),
                        preferred_thread_id=preferred_thread_id,
                        report_ref={
                            "ref_type": "stock_report",
                            "report_key": str(task.task_id),
                            "source_collection": "unified_analysis_tasks",
                            "title": f"{_stock_name}({_symbol}) 分析报告",
                            "symbol": _symbol,
                            "summary": (report_summary or "")[:400],
                            "status": "completed",
                            "task_id": str(task.task_id),
                            "analysis_id": saved_analysis_id,
                            "created_at": task.completed_at or now_tz(),
                        },
                        summary_message=writeback_message,
                    )
                except Exception as writeback_err:
                    self.logger.warning(f"⚠️ Failed to write back research topic(ignore): {writeback_err}")

            # Growth extraction is executed in the background to avoid blocking the completion time of the main task.
            self._schedule_growth_extraction(
                task_id=task.task_id,
                raw_result=result,
                formatted_result=formatted_result,
                analysis_id=saved_analysis_id,
            )

            self.logger.info(f"✅ 任务完成: {task.task_id}")

        except TaskCancelledException as e:
            # 🔥 Processing task cancellation
            self.logger.warning(f"⚠️ 任务被取消: {task.task_id} - {e}")
            task.status = AnalysisStatus.CANCELLED
            task.completed_at = now_tz()
            task.error_message = str(e)
            if task.started_at:
                task.execution_time = (task.completed_at - task.started_at).total_seconds()
            await self._update_task(task)

            # 🔑 Key: Update memory status at the same time
            from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            memory_manager = get_memory_state_manager()
            await memory_manager.update_task_status(
                task_id=task.task_id,
                status=TaskStatus.CANCELLED,
                progress=task.progress,
                message="任务已被用户取消",
                current_step="cancelled"
            )

            self.logger.info(f"🚫 任务已取消: {task.task_id}")

        except Exception as e:
            # 🔥 Handling gracefully: distinguishing between cancellation and failure
            if isinstance(e, TaskCancelledException):
                # Task cancellation has been handled in the except TaskCancelledException block above
                # This shouldn't be reached, but it's better to be on the safe side.
                self.logger.warning(f"⚠️ Unhandled cancellation exception caught: {task.task_id}")
                raise

            # Other exceptions are real failures
            task.status = AnalysisStatus.FAILED
            task.error_message = str(e)
            task.completed_at = now_tz()

            # Save to database
            await self._update_task(task)

            # 🔑 Key: Update memory status to failed
            from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            memory_manager = get_memory_state_manager()
            await memory_manager.update_task_status(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                progress=task.progress,
                message=f"分析失败: {str(e)}",
                current_step_name="失败",  # 🔑 Pass step name
                current_step_description=f"分析失败: {str(e)}",  # 🔑 Transfer step description
                error_message=str(e)
            )

            self.logger.error(f"❌ 任务失败: {task.task_id} - {e}")
            raise

        return task
    
    async def create_and_execute_task(
        self,
        user_id: PyObjectId,
        task_type: AnalysisTaskType,
        task_params: Dict[str, Any],
        engine_type: str = "auto",
        preference_type: str = "neutral",
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,  # 🔥 Support incoming task_id
        progress_callback: Optional[Callable] = None
    ) -> UnifiedAnalysisTask:
        """Create and execute tasks (one step at a time)

        Args:
            user_id: User ID
            task_type: Task type
            task_params: Task parameters
            engine_type: Engine type
            preference_type: Analyze preferences
            workflow_id: Workflow ID
            task_id: Task ID (optional, automatically generated if not provided)
            progress_callback: Progress callback

        Returns:
            Completed task object
        """
        # Create task
        task = await self.create_task(
            user_id=user_id,
            task_type=task_type,
            task_params=task_params,
            engine_type=engine_type,
            preference_type=preference_type,
            workflow_id=workflow_id,
            task_id=task_id  # 🔥 pass on task_id
        )
        
        # perform tasks
        task = await self.execute_task(task, progress_callback)

        return task

    async def get_task(self, task_id: str) -> Optional[UnifiedAnalysisTask]:
        """Get tasks

        Args:
            task_id: Task ID

        Returns:
            Task object, returned if it does not exist None
        """
        doc = await self.collection.find_one({"task_id": task_id})
        if not doc:
            return None

        return UnifiedAnalysisTask(**doc)

    async def list_user_tasks(
        self,
        user_id: PyObjectId,
        task_type: Optional[AnalysisTaskType] = None,
        status: Optional[AnalysisStatus] = None,
        symbol: Optional[str] = None,
        limit: int = 999999,
        skip: int = 0
    ) -> List[UnifiedAnalysisTask]:
        """List user s tasks

        Args:
            user_id: User ID
            task_type: Task type filtering (optional)
            status: Status filtering (optional)
            symbol: Stock code filtering (optional, matches symbol/code/stock_code in task_params)
            limit: Return quantity limit (default returns all)
            skip: skip quantity

        Returns:
            task list
        """
        self.logger.info(f"📋 查询用户任务列表 - user_id: {user_id} (类型: {type(user_id)})")
        self.logger.info(f"📋 Query conditions - task_type: {task_type}, status: {status}, symbol: {symbol}, limit: {limit}, skip: {skip}")

        query: Dict[str, Any] = {"user_id": user_id}

        if task_type:
            query["task_type"] = task_type

        if status:
            query["status"] = status

        if symbol:
            # Matches in task_params symbol / code / stock_code
            symbol_upper = symbol.upper()
            symbol_lower = symbol.lower()
            query["$or"] = [
                {"task_params.symbol": symbol},
                {"task_params.symbol": symbol_upper},
                {"task_params.symbol": symbol_lower},
                {"task_params.code": symbol},
                {"task_params.code": symbol_upper},
                {"task_params.code": symbol_lower},
                {"task_params.stock_code": symbol},
                {"task_params.stock_code": symbol_upper},
                {"task_params.stock_code": symbol_lower},
            ]

        self.logger.info(f"📋 MongoDB查询: {query}")

        # Check the total first
        total = await self.collection.count_documents(query)
        self.logger.info(f"📋 匹配的任务总数: {total}")

        # Debugging: Check all tasks in the database
        all_tasks_count = await self.collection.count_documents({})
        self.logger.debug(f"📊 Total number of all tasks in the database: {all_tasks_count}")

        # Debugging: Statistics by task_type
        task_type_stats = await self.collection.aggregate([
            {"$group": {"_id": "$task_type", "count": {"$sum": 1}}}
        ]).to_list(None)
        self.logger.debug(f"📊 Statistics by task_type: {task_type_stats}")

        # Debugging: Find all position_analysis tasks
        position_tasks = await self.collection.find({"task_type": "position_analysis"}).to_list(None)
        self.logger.debug(f"📊 position_analysis total number of tasks: {len(position_tasks)}")
        if position_tasks:
            for task in position_tasks[:3]:
                self.logger.debug(f"  - task_id: {task.get('task_id')}, user_id: {task.get('user_id')} (类型: {type(task.get('user_id'))}), created_at: {task.get('created_at')}")

        # Debugging: View all tasks sorted by created_at in reverse order
        all_sorted = await self.collection.find({}).sort("created_at", -1).limit(20).to_list(20)
        self.logger.debug("📊 Top 20 tasks in reverse order by created_at:")
        for i, task in enumerate(all_sorted):
            self.logger.debug(f"  {i+1}. task_id: {task.get('task_id')}, task_type: {task.get('task_type')}, user_id: {task.get('user_id')} (类型: {type(task.get('user_id'))}), created_at: {task.get('created_at')}")

        # Debugging: List user_id and task_type
        if all_tasks_count > 0:
            all_docs = await self.collection.find({}).limit(10).to_list(10)
            self.logger.debug("📊 Top 10 tasks in database:")
            for doc in all_docs:
                self.logger.debug(f"  - task_id: {doc.get('task_id')}, user_id: {doc.get('user_id')} (类型: {type(doc.get('user_id'))}), task_type: {doc.get('task_type')}, status: {doc.get('status')}")

        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

        tasks = []
        async for doc in cursor:
            tasks.append(UnifiedAnalysisTask(**doc))

        self.logger.info(f"📋 返回任务数量: {len(tasks)}")
        return tasks

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel task

        Args:
            task_id: Task ID

        Returns:
            Is the cancellation successful?
        """
        result = await self.collection.update_one(
            {"task_id": task_id, "status": {"$in": [AnalysisStatus.PENDING, AnalysisStatus.PROCESSING, AnalysisStatus.SUSPENDED]}},
            {"$set": {"status": AnalysisStatus.CANCELLED, "completed_at": now_tz()}}
        )

        if result.modified_count > 0:
            self.logger.info(f"✅ 任务已取消: {task_id}")
        else:
            self.logger.warning(f"⚠️ Task cannot be canceled (may be completed or does not exist): {task_id}")

        return result.modified_count > 0

    async def resume_task(self, task_id: str) -> bool:
        """Resume a suspended task

        Args:
            task_id: Task ID

        Returns:
            Is the recovery successful?
        """
        from app.services.queue_service import get_queue_service

        # Get tasks
        task = await self.get_task(task_id)
        if not task:
            self.logger.warning(f"⚠️ 任务不存在: {task_id}")
            return False

        if task.status != AnalysisStatus.SUSPENDED:
            self.logger.warning(f"⚠️ 任务状态不是挂起，无法恢复: {task_id} (当前状态: {task.status})")
            return False

        # Update task status to pending
        result = await self.collection.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": AnalysisStatus.PENDING,
                    "error_message": None,
                    "progress": 0
                },
                "$unset": {
                    "suspended_at": ""
                }
            }
        )

        if result.modified_count > 0:
            # rejoin queue
            try:
                queue_service = get_queue_service()
                await queue_service.enqueue_task(
                    user_id=str(task.user_id),
                    symbol=task.task_params.get("symbol", ""),
                    params=task.task_params,
                    task_id=task_id
                )
                self.logger.info(f"✅ Task has been resumed and requeued: {task_id}")
                return True
            except Exception as e:
                self.logger.error(f"❌ Task recovery failed (failed to join the queue): {task_id} - {e}")
                # rollback status
                await self.collection.update_one(
                    {"task_id": task_id},
                    {"$set": {"status": AnalysisStatus.SUSPENDED}}
                )
                return False
        else:
            self.logger.warning(f"⚠️ Task recovery failed (database update failed): {task_id}")
            return False

    async def _is_task_cancelled(self, task_id: str) -> bool:
        """Check if the task has been canceled

        Args:
            task_id: Task ID

        Returns:
            Has it been cancelled?
        """
        task_doc = await self.collection.find_one(
            {"task_id": task_id},
            {"status": 1}
        )

        if not task_doc:
            return False

        return task_doc.get("status") == AnalysisStatus.CANCELLED

    async def _save_task(self, task: UnifiedAnalysisTask) -> None:
        """Save task to database

        Args:
            task: Task object
        """
        doc = task.model_dump(by_alias=True, mode='python')

        # Make sure user_id is of type ObjectId, not a string
        if 'user_id' in doc and isinstance(doc['user_id'], str):
            from bson import ObjectId
            doc['user_id'] = ObjectId(doc['user_id'])
            self.logger.debug(f"🔄 Convert user_id from string to ObjectId: {doc['user_id']}")

        self.logger.debug(f"💾 保存任务文档: user_id={doc.get('user_id')} (类型: {type(doc.get('user_id'))})")

        await self.collection.insert_one(doc)
        self.logger.debug(f"💾 任务已保存: {task.task_id}")

    def _format_analysis_result(self, raw_result: Dict[str, Any], task: UnifiedAnalysisTask) -> Dict[str, Any]:
        """Format analysis results to ensure all fields required by the front end are included

        Args:
            raw_result: Raw results returned by the workflow engine
            task: Task object

        Returns:
            Formatted result
        """
        import uuid
        from datetime import datetime
        import json
        import re

        # 🔑 Key: Extract structured decisions from action_advice first (v2.0 engine)
        # action_advice is the output of ActionAdvisorV2 and contains research observations and reasoning
        # final_trade_decision is the output of RiskManagerV2 and contains the complete risk assessment report (should not be used for reasoning)
        action_advice = raw_result.get("action_advice", "")
        final_trade_decision = raw_result.get("final_trade_decision", "")
        final_decision = raw_result.get("final_decision", {})
        
        self.logger.info("🔍 [TaskAnalysisService] ========== Extract decision information ==========")
        self.logger.info(f"🔍 [TaskAnalysisService] action_advice 类型: {type(action_advice)}, 长度: {len(str(action_advice)) if action_advice else 0}")
        self.logger.info(f"🔍 [TaskAnalysisService] final_trade_decision 类型: {type(final_trade_decision)}, 长度: {len(str(final_trade_decision)) if final_trade_decision else 0}")
        self.logger.info(f"🔍 [TaskAnalysisService] final_decision 类型: {type(final_decision)}, 字段: {list(final_decision.keys()) if isinstance(final_decision, dict) else 'N/A'}")

        decision_dict = None
        
        # 1. Prefer extracting from final_decision if present
        if isinstance(final_decision, dict) and final_decision:
            decision_dict = self._format_decision_dict(final_decision)
            self.logger.info(f"✅ [TaskAnalysisService] Extract decision from final_decision: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}")
        
        # 2. If final_decision does not exist, try to extract it from action_advice
        if not decision_dict and action_advice:
            if isinstance(action_advice, dict):
                decision_dict = self._format_decision_dict(action_advice)
                self.logger.info(f"✅ [TaskAnalysisService] from action_advice (dictionary) Extract decisions: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}, risk_score={decision_dict.get('risk_score')}")
            elif isinstance(action_advice, str) and action_advice.strip():
                # Try to parse JSON format action_advice
                import json
                try:
                    if "{" in action_advice or "```json" in action_advice:
                        json_str = action_advice
                        if "```json" in json_str:
                            json_start = json_str.find("```json") + 7
                            json_end = json_str.find("```", json_start)
                            if json_end > json_start:
                                json_str = json_str[json_start:json_end].strip()
                        if json_str.strip().startswith("{"):
                            action_advice_json = json.loads(json_str)
                            decision_dict = self._format_decision_dict(action_advice_json)
                            self.logger.info(f"✅ [TaskAnalysisService] from action_advice (JSON) Extract decisions: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}, risk_score={decision_dict.get('risk_score')}")
                except Exception as e:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] Parsing action_advice JSON failed: {e}")
                    # Downgrade: extract from text
                    decision_dict = self._extract_decision_from_text(action_advice)
                    self.logger.info(f"✅ [TaskAnalysisService] from action_advice (text) Extract decisions: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}, risk_score={decision_dict.get('risk_score')}")
        
        # 🔥 If risk_score is not present in decision_dict, try to extract it from investment_plan
        if decision_dict and decision_dict.get('risk_score') is None:
            investment_plan = raw_result.get("investment_plan", {})
            if isinstance(investment_plan, dict):
                plan_risk_score = investment_plan.get("risk_score")
                if plan_risk_score is not None:
                    # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                    if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                        plan_risk_score = plan_risk_score / 100.0
                    decision_dict['risk_score'] = plan_risk_score
                    self.logger.info(f"✅ [TaskAnalysisService] Extracted from investment_plan risk_score: {plan_risk_score}")
            elif isinstance(investment_plan, str):
                # If it is a string, try to parse JSON
                try:
                    import json
                    import re
                    if "```json" in investment_plan:
                        json_match = re.search(r'```json\s*(.*?)\s*```', investment_plan, re.DOTALL)
                        if json_match:
                            plan_json = json.loads(json_match.group(1))
                            plan_risk_score = plan_json.get("risk_score")
                            if plan_risk_score is not None:
                                # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                                if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                                    plan_risk_score = plan_risk_score / 100.0
                                decision_dict['risk_score'] = plan_risk_score
                                self.logger.info(f"✅ [TaskAnalysisService] from investment_plan (JSON text) Extract risk_score: {plan_risk_score}")
                except Exception:
                    pass
        
        # 🔥 Prioritize extraction from final_trade_decision (final assessment result of risk assessor) risk_score
        # This is the final assessment from Risk Assessor (RiskManagerV2) and should be the most authoritative source of risk scores
        # 🔥🔥🔥 Note: risk_score is now in the final_trade_decision dictionary (added by risk_manager_v2.py)
        risk_score = None
        
        # Prefer extracting from final_trade_decision (if it is a dictionary)
        if isinstance(final_trade_decision, dict):
            risk_score = final_trade_decision.get("risk_score")
            if risk_score is not None:
                # Make sure risk_score is a float in the range 0-1
                if isinstance(risk_score, (int, float)):
                    if risk_score > 1:
                        risk_score = risk_score / 100.0
                    risk_score = float(risk_score)
                    self.logger.info(f"✅✅✅ [TaskAnalysisService] from final_trade_decision (risk assessor assessment) Extract risk_score: {risk_score}")
        
        # If not in final_trade_decision, try to extract from risk_debate_state.judge_decision (alternative)
        if risk_score is None:
            risk_debate_state = raw_result.get("risk_debate_state", {})
            if isinstance(risk_debate_state, dict):
                judge_decision_str = risk_debate_state.get("judge_decision", "")
                if judge_decision_str and isinstance(judge_decision_str, str):
                    try:
                        # Try to extract from JSON code block
                        json_match = re.search(r'```json\s*(.*?)\s*```', judge_decision_str, re.DOTALL)
                        if json_match:
                            judge_json = json.loads(json_match.group(1))
                            risk_score = judge_json.get("risk_score")
                            if risk_score is not None:
                                if isinstance(risk_score, (int, float)):
                                    if risk_score > 1:
                                        risk_score = risk_score / 100.0
                                    risk_score = float(risk_score)
                                self.logger.info(f"✅✅✅ [TaskAnalysisService] from risk_debate_state.judge_decision (JSON) Extract risk_score: {risk_score}")
                        elif judge_decision_str.strip().startswith("{"):
                            # Try to parse directly JSON
                            judge_json = json.loads(judge_decision_str)
                            risk_score = judge_json.get("risk_score")
                            if risk_score is not None:
                                if isinstance(risk_score, (int, float)):
                                    if risk_score > 1:
                                        risk_score = risk_score / 100.0
                                    risk_score = float(risk_score)
                                self.logger.info(f"✅✅✅ [TaskAnalysisService] from risk_debate_state.judge_decision (direct JSON) Extract risk_score: {risk_score}")
                    except (json.JSONDecodeError, Exception) as e:
                        self.logger.warning(f"⚠️ [TaskAnalysisService] Parsing risk_debate_state.judge_decision JSON failed: {e}")
        
        # If still not available, extract from risk_assessment
        if risk_score is None:
            risk_assessment = raw_result.get("risk_assessment", {})
            if isinstance(risk_assessment, dict):
                risk_score = risk_assessment.get("risk_score")
                if risk_score is not None:
                    self.logger.info(f"✅ [TaskAnalysisService] from risk_assessment (risk assessor assessment) Extract risk_score: {risk_score}")
            elif isinstance(risk_assessment, str):
                # If it is a string, try to parse JSON
                try:
                    if "```json" in risk_assessment:
                        json_match = re.search(r'```json\s*(.*?)\s*```', risk_assessment, re.DOTALL)
                        if json_match:
                            risk_json = json.loads(json_match.group(1))
                            risk_score = risk_json.get("risk_score")
                            if risk_score is not None:
                                self.logger.info(f"✅ [TaskAnalysisService] from risk_assessment (JSON text) Extract risk_score: {risk_score}")
                except Exception as e:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] Parsing JSON from risk_assessment failed: {e}")
        
        # 3. If action_advice is not available, it will be extracted from final_trade_decision
        # 🔥 Important update: final_trade_decision is now a structured dictionary generated by RiskManagerV2, containing the complete reasoning
        if not decision_dict:
            if isinstance(final_trade_decision, dict):
                # 🔥 New logic: final_trade_decision is a comprehensive decision generated by RiskManagerV2, containing reasoning
                ftd_reasoning = final_trade_decision.get("reasoning", "")
                ftd_summary = final_trade_decision.get("summary", "")

                # If reasoning is available, use it; if not, use summary
                reasoning_to_use = ftd_reasoning if ftd_reasoning else ftd_summary
                if not reasoning_to_use:
                    reasoning_to_use = "暂无分析推理"

                # 🔥 Extract price_analysis_range (price range)
                price_analysis_range = final_trade_decision.get("price_analysis_range")
                # 🔥 Debug log: record the original value and type of price_analysis_range
                if price_analysis_range is not None:
                    self.logger.info(f"✅ [TaskAnalysisService] 从 final_trade_decision 提取 price_analysis_range: {price_analysis_range} (类型: {type(price_analysis_range)})")
                    # Make sure price_analysis_range is in array format
                    if isinstance(price_analysis_range, (list, tuple)):
                        if len(price_analysis_range) == 2:
                            self.logger.info(f"✅ [TaskAnalysisService] price_analysis_range is a valid interval format: [{price_analysis_range[0]}, {price_analysis_range[1]}]")
                        else:
                            self.logger.warning(f"⚠️ [TaskAnalysisService] price_analysis_range The array length is not 2: {price_analysis_range}")
                    elif isinstance(price_analysis_range, (int, float)):
                        self.logger.warning(f"⚠️ [TaskAnalysisService] price_analysis_range is a single value {price_analysis_range}, It should be in array format!")
                    else:
                        self.logger.warning(f"⚠️ [TaskAnalysisService] price_analysis_range Incorrect format: {type(price_analysis_range)} = {price_analysis_range}")
                
                # 🔥🔥🔥 Key: Extract risk_score from final_trade_decision (now risk_score has been added to the final_trade_decision dictionary)
                if risk_score is None:
                    risk_score = final_trade_decision.get("risk_score")
                    if risk_score is not None:
                        # Make sure risk_score is a float in the range 0-1
                        if isinstance(risk_score, (int, float)):
                            if risk_score > 1:
                                risk_score = risk_score / 100.0
                            risk_score = float(risk_score)
                        self.logger.info(f"✅✅✅ [TaskAnalysisService] Extracted from final_trade_decision risk_score: {risk_score}")
                
                # 🔥 If still not there, try to get it from investment_plan (as a safety net, but this is not a risk assessor's assessment)
                if risk_score is None:
                    investment_plan = raw_result.get("investment_plan", {})
                    if isinstance(investment_plan, dict):
                        plan_risk_score = investment_plan.get("risk_score")
                        if plan_risk_score is not None:
                            # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                            if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                                plan_risk_score = plan_risk_score / 100.0
                            risk_score = plan_risk_score
                            self.logger.warning(f"⚠️ [TaskAnalysisService] from investment_plan (Assessment by research integrator, not risk assessor) Extract risk_score: {risk_score}")
                    elif isinstance(investment_plan, str):
                        # If it is a string, try to parse JSON
                        try:
                            import json
                            import re
                            if "```json" in investment_plan:
                                json_match = re.search(r'```json\s*(.*?)\s*```', investment_plan, re.DOTALL)
                                if json_match:
                                    plan_json = json.loads(json_match.group(1))
                                    plan_risk_score = plan_json.get("risk_score")
                                    if plan_risk_score is not None:
                                        # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                                        if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                                            plan_risk_score = plan_risk_score / 100.0
                                        risk_score = plan_risk_score
                                        self.logger.warning(f"⚠️ [TaskAnalysisService] from investment_plan (JSON Text, Research Integrator Assessment, Non-Risk Assessor) Extract risk_score: {risk_score}")
                        except Exception as e:
                            self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract risk_score from investment_plan: {e}")
                
                # If still not available, use default value
                if risk_score is None:
                    risk_score = 0.5
                    self.logger.warning("⚠️ [TaskAnalysisService] risk_score not found, using default value 0.5")
                
                decision_dict = {
                    "action": final_trade_decision.get("action") or final_trade_decision.get("analysis_view", "中性"),
                    "target_price": final_trade_decision.get("target_price"),
                    "price_analysis_range": price_analysis_range,  # 🔥 New: price range
                    "stop_loss": final_trade_decision.get("stop_loss") or final_trade_decision.get("risk_control_reference"),
                    "position_ratio": final_trade_decision.get("position_ratio") or final_trade_decision.get("risk_exposure_ratio", "5%"),
                    "confidence": final_trade_decision.get("confidence", 50),
                    "risk_score": risk_score,  # 🔥 Fix: use extracted risk_score instead of default
                    "reasoning": reasoning_to_use,  # 🔥 Synthesis generated using RiskManagerV2 reasoning
                    "summary": ftd_summary,
                    "risk_warning": final_trade_decision.get("risk_warning", "")
                }
                self.logger.info(f"✅ [TaskAnalysisService] from final_trade_decision (dictionary) Extract decisions: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}, risk_score={decision_dict.get('risk_score')}, reasoning length={len(reasoning_to_use)}")
            elif isinstance(final_trade_decision, str) and final_trade_decision.strip():
                # If it is a string, extract all fields (including reasoning)
                temp_dict = self._extract_decision_from_text(final_trade_decision)
                decision_dict = {
                    "action": temp_dict.get("action", "中性"),
                    "target_price": temp_dict.get("target_price"),
                    "price_analysis_range": temp_dict.get("price_analysis_range"),  # 🔥 New: price range
                    "confidence": temp_dict.get("confidence", 0.5),
                    "risk_score": temp_dict.get("risk_score", 0.5),
                    "reasoning": temp_dict.get("reasoning", "暂无分析推理")
                }
                self.logger.info(f"✅ [TaskAnalysisService] from final_trade_decision (text) Extract decisions: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}, risk_score={decision_dict.get('risk_score')}, reasoning length={len(decision_dict.get('reasoning', ''))}")
        
        # 🔥 If there is no risk_score in decision_dict, it will be extracted from final_trade_decision or risk_assessment (risk assessor assessment) first.
        if decision_dict and decision_dict.get('risk_score') is None:
            # 🔥🔥🔥 Highest priority: extracted from final_trade_decision (if it is a dictionary and contains risk_score)
            if isinstance(final_trade_decision, dict):
                ftd_risk_score = final_trade_decision.get("risk_score")
                if ftd_risk_score is not None:
                    # Make sure risk_score is a float in the range 0-1
                    if isinstance(ftd_risk_score, (int, float)):
                        if ftd_risk_score > 1:
                            ftd_risk_score = ftd_risk_score / 100.0
                        decision_dict['risk_score'] = float(ftd_risk_score)
                        self.logger.info(f"✅✅✅ [TaskAnalysisService] Assign risk_score in final_trade_decision to decision_dict: {decision_dict['risk_score']}")
            # Second: use the risk_score extracted earlier (from risk_assessment)
            if decision_dict.get('risk_score') is None and risk_score is not None:
                decision_dict['risk_score'] = risk_score
                self.logger.info(f"✅ [TaskAnalysisService] Assign risk_score in risk_assessment to decision_dict: {risk_score}")
            # Finally: Extract from investment_plan (as a safety net)
            if decision_dict.get('risk_score') is None:
                # If you haven't already, try extracting it from investment_plan (as a fallback, but this is not a risk assessor's assessment)
                investment_plan = raw_result.get("investment_plan", {})
                if isinstance(investment_plan, dict):
                    plan_risk_score = investment_plan.get("risk_score")
                    if plan_risk_score is not None:
                        # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                        if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                            plan_risk_score = plan_risk_score / 100.0
                        decision_dict['risk_score'] = plan_risk_score
                        self.logger.warning(f"⚠️ [TaskAnalysisService] from investment_plan (Assessment by research integrator, not risk assessor) Extract risk_score: {plan_risk_score}")
                elif isinstance(investment_plan, str):
                    # If it is a string, try to parse JSON
                    try:
                        import json
                        import re
                        if "```json" in investment_plan:
                            json_match = re.search(r'```json\s*(.*?)\s*```', investment_plan, re.DOTALL)
                            if json_match:
                                plan_json = json.loads(json_match.group(1))
                                plan_risk_score = plan_json.get("risk_score")
                                if plan_risk_score is not None:
                                    # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                                    if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                                        plan_risk_score = plan_risk_score / 100.0
                                    decision_dict['risk_score'] = plan_risk_score
                                    self.logger.warning(f"⚠️ [TaskAnalysisService] from investment_plan (JSON Text, Research Integrator Assessment, Non-Risk Assessor) Extract risk_score: {plan_risk_score}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract risk_score from investment_plan: {e}")
        
        # 4. If neither, use default value
        if not decision_dict:
            decision_dict = {
                "action": "中性",
                "target_price": None,
                "price_analysis_range": None,  # 🔥 New: price range
                "confidence": 0.5,
                "risk_score": 0.5,
                "reasoning": "暂无分析推理"
            }
            self.logger.warning("⚠️ [TaskAnalysisService] Decision information not found, use default decision")
        
        self.logger.info(f"🔍 [TaskAnalysisService] 最终 decision_dict.reasoning 长度: {len(decision_dict.get('reasoning', ''))}, 内容: {decision_dict.get('reasoning', '')[:200]}")

        # 🔥 Import JSON conversion function (import inside the function to avoid circular dependencies)
        from app.utils.report_formatter import _convert_json_to_markdown
        import json
        import re

        # 🔥 Critical fix: if decision_dict.reasoning is "No analytical reasoning yet", Try to extract from risk_assessment or investment_plan
        # ⚠️ NOTE: This must be done before fetching the report as fetching the report converts the JSON to Markdown
        if decision_dict and decision_dict.get('reasoning') == "暂无分析推理":
            self.logger.info("🔍 [TaskAnalysisService] reasoning Empty, try to extract from risk_assessment or investment_plan")

            # 1. Prioritize extraction from risk_assessment (comprehensive risk assessment reasoning)
            risk_assessment_raw = raw_result.get("risk_assessment", "")
            self.logger.info(f"🔍 [TaskAnalysisService] risk_assessment_raw 类型: {type(risk_assessment_raw)}, 长度: {len(str(risk_assessment_raw)) if risk_assessment_raw else 0}")
            if risk_assessment_raw:
                try:
                    # 🔥 Fix: If it is a dictionary, extract the content field first
                    if isinstance(risk_assessment_raw, dict):
                        risk_assessment_str = risk_assessment_raw.get("content", "")
                        self.logger.info(f"🔍 [TaskAnalysisService] risk_assessment Is a dictionary, extract the content field, length: {len(risk_assessment_str) if risk_assessment_str else 0}")
                    else:
                        risk_assessment_str = str(risk_assessment_raw)

                    json_obj = None

                    # 1. Try to extract JSON code block
                    if "```json" in risk_assessment_str:
                        json_match = re.search(r'```json\s*(.*?)\s*```', risk_assessment_str, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1).strip()
                            json_obj = json.loads(json_str)
                    # 2. Try to parse directly JSON
                    elif risk_assessment_str.strip().startswith("{"):
                        json_obj = json.loads(risk_assessment_str)

                    # If parsing is successful, extract reasoning
                    if json_obj and isinstance(json_obj, dict):
                        reasoning = json_obj.get("reasoning", "")
                        self.logger.info(f"🔍 [TaskAnalysisService] risk_assessment JSON Parsed successfully, reasoning length: {len(reasoning) if reasoning else 0}")
                        if reasoning and len(reasoning.strip()) > 10:
                            decision_dict['reasoning'] = reasoning.strip()
                            self.logger.info(f"✅ [TaskAnalysisService] 从 risk_assessment 提取 reasoning: {len(reasoning.strip())}字符")
                        else:
                            self.logger.warning("⚠️ [TaskAnalysisService] risk_assessment reasoning in is empty or too short")
                    else:
                        self.logger.warning("⚠️ [TaskAnalysisService] risk_assessment It is not a dictionary or empty after parsing")
                except Exception as e:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract reasoning from risk_assessment: {e}")
            else:
                self.logger.warning("⚠️ [TaskAnalysisService] risk_assessment_raw is empty")

            # 2. If risk_assessment does not have reasoning, it is extracted from investment_plan
            if decision_dict.get('reasoning') == "暂无分析推理":
                self.logger.info("🔍 [TaskAnalysisService] risk_assessment Without reasoning, try to extract from investment_plan")
                investment_plan_raw = raw_result.get("investment_plan", "")
            self.logger.info(f"🔍 [TaskAnalysisService] investment_plan_raw 类型: {type(investment_plan_raw)}, 长度: {len(str(investment_plan_raw)) if investment_plan_raw else 0}")
            if investment_plan_raw:
                try:
                    # 🔥 Fix: If it is a dictionary, extract the content field first
                    if isinstance(investment_plan_raw, dict):
                        investment_plan_str = investment_plan_raw.get("content", "")
                        self.logger.info(f"🔍 [TaskAnalysisService] investment_plan Is a dictionary, extract the content field, length: {len(investment_plan_str) if investment_plan_str else 0}")
                    else:
                        investment_plan_str = str(investment_plan_raw)

                    json_obj = None

                    # 1. Try to extract JSON code block
                    if "```json" in investment_plan_str:
                        json_match = re.search(r'```json\s*(.*?)\s*```', investment_plan_str, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1).strip()
                            json_obj = json.loads(json_str)
                    # 2. Try to parse directly JSON
                    elif investment_plan_str.strip().startswith("{"):
                        json_obj = json.loads(investment_plan_str)
                    
                    # If parsing is successful, extract reasoning
                    if json_obj and isinstance(json_obj, dict):
                        reasoning = json_obj.get("reasoning", "")
                        self.logger.info(f"🔍 [TaskAnalysisService] investment_plan JSON Parsed successfully, reasoning length: {len(reasoning) if reasoning else 0}")
                        if reasoning and len(reasoning.strip()) > 10:
                            decision_dict['reasoning'] = reasoning.strip()
                            self.logger.info(f"✅ [TaskAnalysisService] 从 investment_plan 提取 reasoning: {len(reasoning.strip())}字符")
                        else:
                            self.logger.warning("⚠️ [TaskAnalysisService] investment_plan reasoning in is empty or too short")
                    else:
                        self.logger.warning("⚠️ [TaskAnalysisService] investment_plan It is not a dictionary or empty after parsing")
                except Exception as e:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract reasoning from investment_plan: {e}")
            else:
                self.logger.warning("⚠️ [TaskAnalysisService] investment_plan_raw is empty")
            
            # 🔥 If investment_plan has no reasoning, try to extract from final_trade_decision (as an alternative)
            if decision_dict.get('reasoning') == "暂无分析推理" and final_trade_decision:
                self.logger.info("🔍 [TaskAnalysisService] investment_plan Without reasoning, try to extract from final_trade_decision")
                try:
                    final_trade_str = str(final_trade_decision)
                    json_obj = None
                    
                    # 1. Try to extract JSON code block
                    if "```json" in final_trade_str:
                        json_match = re.search(r'```json\s*(.*?)\s*```', final_trade_str, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1).strip()
                            json_obj = json.loads(json_str)
                    # 2. Try to parse directly JSON
                    elif final_trade_str.strip().startswith("{"):
                        json_obj = json.loads(final_trade_str)
                    
                    # If the parsing is successful, extract reasoning (although final_trade_decision is a risk assessment, its reasoning can be used as the basis for analysis)
                    if json_obj and isinstance(json_obj, dict):
                        reasoning = json_obj.get("reasoning", "")
                        self.logger.info(f"🔍 [TaskAnalysisService] final_trade_decision JSON Parsed successfully, reasoning length: {len(reasoning) if reasoning else 0}")
                        if reasoning and len(reasoning.strip()) > 10:
                            decision_dict['reasoning'] = reasoning.strip()
                            self.logger.info(f"✅ [TaskAnalysisService] 从 final_trade_decision 提取 reasoning (备选): {len(reasoning.strip())}字符")
                        else:
                            self.logger.warning("⚠️ [TaskAnalysisService] final_trade_decision reasoning in is empty or too short")
                    else:
                        self.logger.warning("⚠️ [TaskAnalysisService] final_trade_decision It is not a dictionary or empty after parsing")
                except Exception as e:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract reasoning from final_trade_decision: {e}")
            else:
                if not final_trade_decision:
                    self.logger.warning("⚠️ [TaskAnalysisService] final_trade_decision Empty and cannot be extracted reasoning")
        
        # 🔥 Record the final reasoning again (after extraction)
        self.logger.info(f"🔍 [TaskAnalysisService] 提取后 decision_dict.reasoning 长度: {len(decision_dict.get('reasoning', ''))}, 内容: {decision_dict.get('reasoning', '')[:200]}")

        # Withdraw investment plan
        investment_plan = raw_result.get("trader_investment_plan") or raw_result.get("investment_plan", "")
        if isinstance(investment_plan, dict):
            investment_plan_text = investment_plan.get("content", str(investment_plan))
        else:
            investment_plan_text = str(investment_plan) if investment_plan else ""

        # 🔑 Key: Build the reports dictionary (exactly the old way)
        reports = {}
        
        # 🔑 Helper function for extracting text (consistent with old process)
        def _extract_text(v, field_name: str = ""):
            """从各种格式中提取文本内容"""
            if isinstance(v, str):
                return v
            if isinstance(v, dict):
                # 🔥 Special processing: final_trade_decision If it is a dictionary and has a content field, content (formatted Markdown) is returned directly
                if field_name == "final_trade_decision" and v.get("content"):
                    content = v.get("content")
                    if isinstance(content, str) and content.strip():
                        return content
                # 🔥 If final_trade_decision does not have a content field but has an action field, convert it to a JSON string
                # In this way, subsequent _convert_json_to_markdown can be processed correctly
                if field_name == "final_trade_decision" and v.get("action"):
                    import json
                    return json.dumps(v, ensure_ascii=False, indent=2)
                # Try to extract text field from dictionary
                for k in ("content", "markdown", "text", "message", "report"):
                    x = v.get(k)
                    if isinstance(x, str) and x.strip():
                        return x
            return ""

        # 🔑 Step 1: Dynamically extract report fields from structured_reports generated by the engine
        # engine Filtered by show_in_reports, reused directly here, no hard-coded list is maintained.
        structured_reports = raw_result.get("structured_reports", {})
        if structured_reports and isinstance(structured_reports, dict):
            for field, entry in structured_reports.items():
                if isinstance(entry, dict) and entry.get("success") and entry.get("content"):
                    content = entry["content"]
                    if isinstance(content, str) and len(content.strip()) > 5:
                        reports[field] = content.strip()
                        self.logger.info(f"📊 [REPORTS] 从 structured_reports 提取: {field} - 长度: {len(content.strip())}")
        else:
            # Fallback: Extract fields in report_manifest from raw_result top level
            manifest = raw_result.get("report_manifest", [])
            if manifest:
                for m in manifest:
                    field = m.get("field")
                    if field and field not in reports:
                        content = _extract_text(raw_result.get(field), field)
                        if content and isinstance(content, str) and len(content.strip()) > 5:
                            reports[field] = content.strip()
                            self.logger.info(f"📊 [REPORTS] 从 manifest 提取: {field} - 长度: {len(content.strip())}")

        # 🔑 Step 2: Handle research team debate status (dictionary type) - split into independent sub-reports (consistent with old process)
        # 🔥 Note: If the top level already has bull_report/bear_report, the top level one will be used first; otherwise, it will be extracted from investment_debate_state
        investment_debate = raw_result.get("investment_debate_state", {})
        if investment_debate and isinstance(investment_debate, dict):
            # 1. Long researcher report (extracted from investment_debate_state if not available at the top level)
            if "bull_researcher" not in reports:
                bull_history = _extract_text(investment_debate.get("bull_history", ""))
                if bull_history and len(bull_history.strip()) > 5:
                    reports["bull_researcher"] = bull_history.strip()
                    self.logger.info(f"📊 [REPORTS] Extract report: bull_researcher (from investment_debate_state.bull_history) - length: {len(bull_history.strip())}")

            # 2. Short researcher report (only extracted from investment_debate_state if the top level is not available)
            if "bear_researcher" not in reports:
                bear_history = _extract_text(investment_debate.get("bear_history", ""))
                if bear_history and len(bear_history.strip()) > 5:
                    reports["bear_researcher"] = bear_history.strip()
                    self.logger.info(f"📊 [REPORTS] Extract report: bear_researcher (from investment_debate_state.bear_history) - length: {len(bear_history.strip())}")

            # 3. Research Integrator Analysis Report
            judge_decision = _extract_text(investment_debate.get("judge_decision", ""))
            if judge_decision and len(judge_decision.strip()) > 5:
                # 🔥 New: If in JSON format, convert to Markdown
                markdown_content = _convert_json_to_markdown(judge_decision.strip(), "investment")
                reports["research_team_decision"] = markdown_content
                self.logger.info(f"📊 [REPORTS] Extract report: research_team_decision - length: {len(markdown_content)} (Converted JSON->Markdown)")

        # 🔑 Step 3: Handle risk management team debate status (dictionary type) - split into independent sub-reports (consistent with old process)
        # 🔥 Also check if the top level has risky_opinion, safe_opinion, neutral_opinion etc fields
        risk_debate = raw_result.get("risk_debate_state", {})
        
        # 🔥 Alternative field mapping (v2.0 workflow may store reports at the top level)
        risk_alternative_fields = {
            "risky_analyst": ["risky_opinion", "risky_history"],
            "safe_analyst": ["safe_opinion", "safe_history"],
            "neutral_analyst": ["neutral_opinion", "neutral_history"],
        }
        
        # Extract from the top level first
        for report_key, alt_fields in risk_alternative_fields.items():
            if report_key not in reports:
                for alt_field in alt_fields:
                    content_raw = raw_result.get(alt_field, "")
                    content = _extract_text(content_raw)
                    if content and isinstance(content, str) and len(content.strip()) > 5:
                        reports[report_key] = content.strip()
                        self.logger.info(f"📊 [REPORTS] 提取报告: {report_key} (来自顶层 {alt_field}) - 长度: {len(content.strip())}")
                        break
        
        # Then extract from risk_debate_state (if the top level doesn't have one)
        if risk_debate and isinstance(risk_debate, dict):
            # 1. High Resilience Scenario Analyst Report
            if "risky_analyst" not in reports:
                risky_history = _extract_text(risk_debate.get("risky_history", ""))
                if risky_history and len(risky_history.strip()) > 5:
                    reports["risky_analyst"] = risky_history.strip()
                    self.logger.info(f"📊 [REPORTS] Extract report: risky_analyst (from risk_debate_state.risky_history) - length: {len(risky_history.strip())}")

            # 2. Defense Scenario Analyst Report
            if "safe_analyst" not in reports:
                safe_history = _extract_text(risk_debate.get("safe_history", ""))
                if safe_history and len(safe_history.strip()) > 5:
                    reports["safe_analyst"] = safe_history.strip()
                    self.logger.info(f"📊 [REPORTS] Extract report: safe_analyst (from risk_debate_state.safe_history) - length: {len(safe_history.strip())}")

            # 3. Neutral analyst report
            if "neutral_analyst" not in reports:
                neutral_history = _extract_text(risk_debate.get("neutral_history", ""))
                if neutral_history and len(neutral_history.strip()) > 5:
                    reports["neutral_analyst"] = neutral_history.strip()
                    self.logger.info(f"📊 [REPORTS] Extract report: neutral_analyst (from risk_debate_state.neutral_history) - length: {len(neutral_history.strip())}")

            # 4. Risk Assessor Decision Report
            judge_decision = _extract_text(risk_debate.get("judge_decision", ""))
            if judge_decision and len(judge_decision.strip()) > 5:
                # 🔥 New: If in JSON format, convert to Markdown
                markdown_content = _convert_json_to_markdown(judge_decision.strip(), "risk")
                reports["risk_management_decision"] = markdown_content
                self.logger.info(f"📊 [REPORTS] Extract report: risk_management_decision - length: {len(markdown_content)} (Converted JSON->Markdown)")

        # 🔥 Generate summaries and recommendations (consistent with old engine)
        # summary (Analysis overview): Prioritize extracting the complete summary from the investment_plan or final_trade_decision returned by LLM, without intercepting
        # recommendation (Analytical view): generated based on action, price_range and short inference summary
        # decision.reasoning (Analysis basis): extracted from decision_dict.reasoning (should not be extracted from final_trade_decision)
        
        self.logger.info("🔍 [TaskAnalysisService] ========== Generate summary and recommendation ==========")
        
        # 1. Generate summary (analysis overview)- 🔥🔥🔥 Highest priority: Extract the complete investment_plan from the LLM return summary
        summary = ""
        
        # 1.1 Preferentially extract the complete summary
        investment_plan_raw = raw_result.get("investment_plan", "")
        if investment_plan_raw:
            try:
                # If it is a dictionary, get it directly summary
                if isinstance(investment_plan_raw, dict):
                    plan_summary = investment_plan_raw.get("summary", "")
                    if plan_summary and isinstance(plan_summary, str) and len(plan_summary.strip()) > 10:
                        summary = plan_summary.strip()
                        self.logger.info(f"✅✅✅ [TaskAnalysisService] 从 investment_plan (字典) 提取完整 summary: {len(summary)}字符")
                # If it is a string, try to parse JSON
                elif isinstance(investment_plan_raw, str):
                    investment_plan_str = investment_plan_raw.strip()
                    json_obj = None
                    # Try to extract JSON code block
                    if "```json" in investment_plan_str:
                        json_match = re.search(r'```json\s*(.*?)\s*```', investment_plan_str, re.DOTALL)
                        if json_match:
                            json_obj = json.loads(json_match.group(1))
                    # Try to parse directly JSON
                    elif investment_plan_str.startswith("{"):
                        json_obj = json.loads(investment_plan_str)
                    
                    # If parsing is successful, extract summary
                    if json_obj and isinstance(json_obj, dict):
                        plan_summary = json_obj.get("summary", "")
                        if plan_summary and isinstance(plan_summary, str) and len(plan_summary.strip()) > 10:
                            summary = plan_summary.strip()
                            self.logger.info(f"✅✅✅ [TaskAnalysisService] 从 investment_plan (JSON字符串) 提取完整 summary: {len(summary)}字符")
            except (json.JSONDecodeError, Exception) as e:
                self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract summary from investment_plan: {e}")
        
        # 1.2 If not present in investment_plan, extract the complete summary
        if not summary:
            if isinstance(final_trade_decision, dict):
                ftd_summary = final_trade_decision.get("summary", "")
                if ftd_summary and isinstance(ftd_summary, str) and len(ftd_summary.strip()) > 10:
                    summary = ftd_summary.strip()
                    self.logger.info(f"✅✅✅ [TaskAnalysisService] 从 final_trade_decision (字典) 提取完整 summary: {len(summary)}字符")
        
        # 1.3 If it still doesn't exist, extract it from final_trade_decision in reports (do not intercept, use the complete content)
        if not summary:
            if reports.get("final_trade_decision"):
                final_trade_content = reports["final_trade_decision"]
                if isinstance(final_trade_content, str) and len(final_trade_content.strip()) > 50:
                    # 🔥 No truncation, use full content (remove Markdown tags)
                    summary = final_trade_content.replace('#', '').replace('*', '').strip()
                    self.logger.info(f"✅ [TaskAnalysisService] 从 reports.final_trade_decision 提取完整 summary: {len(summary)}字符")
        
        # 1.4 If still not available, extract from other reports (without interception)
        if not summary:
            for report_name in ['trader_investment_plan', 'research_team_decision', 'market_report']:
                if report_name in reports:
                    content = reports[report_name]
                    if isinstance(content, str) and len(content.strip()) > 100:
                        # 🔥 No truncation, use full content (remove Markdown tags)
                        summary = content.replace('#', '').replace('*', '').strip()
                        self.logger.info(f"✅ [TaskAnalysisService] 从 {report_name} 提取完整 summary: {len(summary)}字符")
                        break
        
        # 1.5 Last resort
        if not summary:
            summary = f"对{task.task_params.get('symbol', '股票')}的分析已完成，请查看详细报告。"
            self.logger.warning("⚠️ [TaskAnalysisService] Use backup summary")
        
        # 4. Generate recommendations (analysis opinions) - based on action, price_range and short reasoning summary
        # 🔥 Compliance modification: use new terms, format decision_dict first to ensure action is a compliant term
        temp_formatted_decision = self._format_decision_dict(decision_dict)
        action = temp_formatted_decision.get('action', '中性')
        target_price = temp_formatted_decision.get('target_price')
        reasoning = temp_formatted_decision.get('reasoning', '')

        # Build recommendations (excluding specific prices and research observations)
        recommendation_parts = []

        # Contains only analytical opinions and does not include specific prices
        if action and action != '中性':
            recommendation_parts.append(f"Analysis point of view:{action}")

        # 🔥 If reasoning is short (<100 characters) before adding it to the recommendation to avoid duplication
        if reasoning and len(reasoning) < 100 and reasoning != "暂无分析推理":
            recommendation_parts.append(f"Analysis basis:{reasoning}")
        elif reasoning and reasoning != "暂无分析推理":
            # If reasoning is longer, only the first 50 characters are extracted
            short_reasoning = reasoning[:50] + "..." if len(reasoning) > 50 else reasoning
            recommendation_parts.append(f"Analysis basis:{short_reasoning}")

        recommendation = "；".join(recommendation_parts) if recommendation_parts else "Please refer to the detailed analysis report."

        if not recommendation or recommendation == "Analytical opinion: Neutral":
            recommendation = "Please refer to the detailed analysis report."
            self.logger.warning("⚠️ [TaskAnalysisService] Use backup recommendation")
        
        self.logger.info(f"🔍 [TaskAnalysisService] summary 长度: {len(summary)}, 内容: {summary[:200]}")
        self.logger.info(f"🔍 [TaskAnalysisService] recommendation 长度: {len(recommendation)}, 内容: {recommendation[:200]}")
        self.logger.info(f"🔍 [TaskAnalysisService] decision.reasoning 长度: {len(reasoning)}, 内容: {reasoning[:200]}")

        # Calculate risk level (based on risk_score)
        risk_score = decision_dict.get("risk_score", 0.5)
        if risk_score < 0.3:
            risk_level = "低"
        elif risk_score < 0.6:
            risk_level = "中等"
        else:
            risk_level = "高"

        # 🔑 Get model information
        quick_model = task.task_params.get("quick_analysis_model", "Unknown")
        deep_model = task.task_params.get("deep_analysis_model", "Unknown")
        model_info = f"{quick_model}/{deep_model}"

        # 🔥 Extract key points (from reasoning or summary)
        key_points = []
        if reasoning and reasoning != "暂无分析推理":
            # Try to extract key points from reasoning (split by rows)
            lines = [line.strip() for line in reasoning.split('\n') if line.strip()]
            # Filter out lines that are too short (<10 characters) and the title line (ending with#beginning)
            key_points = [
                line for line in lines
                if len(line) >= 10 and not line.startswith('#') and not line.startswith('*')
            ][:5]  # Take up to 5 key points
            self.logger.info(f"✅ [TaskAnalysisService] 从 reasoning 提取 {len(key_points)} 个关键要点")

        # If reasoning has no key points, try to extract them from summary
        if not key_points and summary:
            lines = [line.strip() for line in summary.split('\n') if line.strip()]
            key_points = [
                line for line in lines
                if len(line) >= 10 and not line.startswith('#') and not line.startswith('*')
            ][:5]
            self.logger.info(f"✅ [TaskAnalysisService] 从 summary 提取 {len(key_points)} 个关键要点")

        # 🔥 Filter out key points containing JSON field names or sensitive terms
        filtered_key_points = []
        for kp in key_points:
            # Skip lines containing JSON field names
            if any(field in kp for field in ['"analysis_view"', '"action"', '"confidence"', '"target_price"', '```json', '```']):
                continue
            # Skip lines containing sensitive terms
            if any(term in kp for term in ['买入', '卖出', '目标价', '止损', '止盈', '仓位']):
                continue
            filtered_key_points.append(kp)

        key_points = filtered_key_points[:5]  # Keep up to 5
        self.logger.info(f"✅ [TaskAnalysisService] 过滤后保留 {len(key_points)} 个关键要点")

        # 🔥🔥🔥 Final check: Make sure decision_dict contains risk_score extracted from final_trade_decision (highest priority)
        if decision_dict and decision_dict.get('risk_score') is None:
            # Try extracting from final_trade_decision again
            if isinstance(final_trade_decision, dict):
                ftd_risk_score = final_trade_decision.get("risk_score")
                if ftd_risk_score is not None:
                    # Make sure risk_score is a float in the range 0-1
                    if isinstance(ftd_risk_score, (int, float)):
                        if ftd_risk_score > 1:
                            ftd_risk_score = ftd_risk_score / 100.0
                        decision_dict['risk_score'] = float(ftd_risk_score)
                        self.logger.info(f"✅✅✅ [TaskAnalysisService] Final check: assign risk_score in final_trade_decision to decision_dict: {decision_dict['risk_score']}")

        # 🔥 Format decision_dict (map old terms to compliant terms)
        formatted_decision = self._format_decision_dict(decision_dict)
        self.logger.info(f"🔍 [TaskAnalysisService] decision Format: {decision_dict.get('action')} -> {formatted_decision.get('action')}")
        self.logger.info(f"🔍 [TaskAnalysisService] decision.risk_score = {formatted_decision.get('risk_score')}")

        # Build formatted results (basic fields, excluding state and detailed_analysis)
        formatted_result = {
            "analysis_id": str(uuid.uuid4()),
            "stock_symbol": task.task_params.get("symbol") or task.task_params.get("stock_code"),
            "stock_code": task.task_params.get("stock_code") or task.task_params.get("symbol"),
            "analysis_date": task.task_params.get("analysis_date") or datetime.now().strftime("%Y-%m-%d"),
            "summary": summary or "分析完成",
            "recommendation": recommendation or "请查看详细报告",
            "confidence_score": formatted_decision.get("confidence", 0.5),
            "risk_level": risk_level,
            "key_points": key_points,  # 🔥 Key takeaways (extracted from reasoning or summary)
            "execution_time": task.execution_time or 0,
            "tokens_used": raw_result.get("tokens_used", 0),
            "analysts": task.task_params.get("selected_analysts", []),
            "research_depth": task.task_params.get("research_depth", "快速"),
            "reports": reports,
            "decision": formatted_decision,
            "model_info": model_info,
            "quick_model": quick_model,
            "deep_model": deep_model,
        }

        # Transparently transmit the report_manifest (customized workflow output description) generated by the workflow engine
        if raw_result.get("report_manifest"):
            formatted_result["report_manifest"] = raw_result["report_manifest"]

        # 🔥 Debug log: print the complete contents of the decision object
        self.logger.info(f"✅ 格式化结果完成: {len(reports)} 个报告")
        self.logger.info(f"🔍 [TaskAnalysisService] decision Object complete content: {formatted_decision}")
        self.logger.info(f"🔍 [TaskAnalysisService] decision.price_analysis_range = {formatted_decision.get('price_analysis_range')}")
        self.logger.info(f"🔍 [TaskAnalysisService] decision.risk_score = {formatted_decision.get('risk_score')}")
        return formatted_result

    def _format_decision_dict(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Format decision dictionary

        Args:
            decision: original decision dictionary

        Returns:
            Formatted decision dictionary
        """
        # Handle validation price (history field target_price is for compatibility only)
        target_price = decision.get('target_price')
        if target_price is not None and target_price != 'N/A':
            try:
                if isinstance(target_price, str):
                    # Remove currency symbols and spaces
                    clean_price = target_price.replace('$', '').replace('¥', '').replace('￥', '').strip()
                    target_price = float(clean_price) if clean_price and clean_price != 'None' else None
                elif isinstance(target_price, (int, float)):
                    target_price = float(target_price)
                else:
                    target_price = None
            except (ValueError, TypeError):
                target_price = None
        else:
            target_price = None

        # 🔥 Compliance modification: Convert English/old operational recommendations to Chinese compliance terminology (research conclusion tendency)
        action_translation = {
            'BUY': '乐观',
            'SELL': '审慎',
            'HOLD': '中性',
            'buy': '乐观',
            'sell': '审慎',
            'hold': '中性',
            '买入': '乐观',  # Compatible with old data
            '卖出': '审慎',
            '持有': '中性',
            '看涨': '乐观',  # Compatible with old data
            '看跌': '审慎',
        }
        action = decision.get('action', '中性')
        chinese_action = action_translation.get(action, action)

        # 🔥 Important: reasoning should be extracted from decision. If decision does not have reasoning, use the default value.
        # should not be extracted from final_trade_decision as final_trade_decision will be used to generate summary
        reasoning = decision.get('reasoning', '') or decision.get('rationale', '')
        if not reasoning:
            reasoning = '暂无分析推理'
        
        self.logger.info(f"🔍 [TaskAnalysisService._format_decision_dict] decision Field: {list(decision.keys())}")
        self.logger.info(f"🔍 [TaskAnalysisService._format_decision_dict] reasoning 长度: {len(reasoning)}, 内容: {reasoning[:200]}")

        # 🔥 Make sure confidence is a decimal between 0-1 (expected by the front end)
        confidence = float(decision.get('confidence', 0.5))
        if confidence > 1:
            # If LLM returns an integer from 0 to 100, convert it to a decimal from 0 to 1
            confidence = confidence / 100.0

        # 🔥 Make sure risk_score is a decimal between 0-1 (expected by the front end)
        risk_score = decision.get('risk_score')
        if risk_score is not None:
            risk_score = float(risk_score)
            if risk_score > 1:
                risk_score = risk_score / 100.0
        else:
            risk_score = 0.5  # Default value
            self.logger.warning("⚠️ [TaskAnalysisService._format_decision_dict] decision There is no risk_score in , the default value is used 0.5")

        # 🔥 Compliance modification: return price_analysis_range (price range) instead of target_price (specific price)
        # Extract price_analysis_range if present
        price_analysis_range = decision.get('price_analysis_range')
        
        # 🔥 Make sure price_analysis_range remains in array format and does not convert to a single value
        if price_analysis_range is not None:
            # If it's a list/array, leave it as is
            if isinstance(price_analysis_range, (list, tuple)):
                # Make sure it is a valid range format [min, max]
                if len(price_analysis_range) == 2:
                    price_analysis_range = [float(price_analysis_range[0]), float(price_analysis_range[1])]
                    self.logger.info(f"✅ [TaskAnalysisService._format_decision_dict] price_analysis_range is an array: {price_analysis_range}")
                else:
                    self.logger.warning(f"⚠️ [TaskAnalysisService._format_decision_dict] price_analysis_range The array length is not 2: {price_analysis_range}")
                    price_analysis_range = None
            # If it is a single number, convert it to array format (generate a reasonable interval based on the value)
            elif isinstance(price_analysis_range, (int, float)):
                single_value = float(price_analysis_range)
                # 🔥 Improvement: Generate a reasonable price range based on a single value (±5%) 
                # This avoids front-end display '-', Instead, it shows a reasonable price range
                price_range_pct = 0.05  # 5% The fluctuation range of
                min_price = single_value * (1 - price_range_pct)
                max_price = single_value * (1 + price_range_pct)
                price_analysis_range = [round(min_price, 2), round(max_price, 2)]
                self.logger.info(f"✅ [TaskAnalysisService._format_decision_dict] price_analysis_range is a single value {single_value}, converted to interval: {price_analysis_range}")
            else:
                self.logger.warning(f"⚠️ [TaskAnalysisService._format_decision_dict] price_analysis_range Incorrect format: {type(price_analysis_range)} = {price_analysis_range}")
                price_analysis_range = None
        
        if not price_analysis_range:
            self.logger.warning("⚠️ [TaskAnalysisService._format_decision_dict] decision There is no valid price_analysis_range in the frontend will display '-'")
        
        # 🔥 Debug log: record returned fields
        self.logger.info(f"🔍 [TaskAnalysisService._format_decision_dict] 返回字段: action={chinese_action}, price_analysis_range={price_analysis_range} (类型: {type(price_analysis_range)}), risk_score={risk_score}, confidence={confidence}")
        
        return {
            'action': chinese_action,
            'analysis_view': chinese_action,  # 🔥 Compatible fields
            'confidence': confidence,
            'risk_score': risk_score,
            'target_price': None,  # 🔥 No specific price provided (compliance requirement)
            'price_analysis_range': price_analysis_range,  # 🔥 Price range (compliance)
            'reasoning': reasoning
        }

    def _extract_decision_from_text(self, text: str) -> Dict[str, Any]:
        """Extract decision information from text

        Args:
            text: decision text

        Returns:
            decision dictionary
        """
        import re

        # Extract actions (unified use of compliance research conclusion tendency terms)
        action = '中性'  # Default
        if re.search(r'(strong)?buy|Recommended to buy|long|BUY|STRONG_BUY|bullish|optimistic', text, re.IGNORECASE):
            action = '乐观'
        elif re.search(r'(strong)?sell|Recommended to sell|bearish|Reduce holdings|SELL|STRONG_SELL|Bearish|Prudence', text, re.IGNORECASE):
            action = '审慎'
        elif re.search(r'hold|wait and see|wait|HOLD|Neutral', text, re.IGNORECASE):
            action = '中性'

        # Extract target price
        target_price = None
        price_patterns = [
            r'target price[person]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # target price: 45.50
            r'\*\*target price[person]?\*\*[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # **target price**: 45.50
            r'target[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # target: 45.50
            r'price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # price: 45.50
            r'[¥\$](\d+(?:\.\d+)?)',                      # ¥45.50 or $190
            r'(\d+(?:\.\d+)?)Yuan',                         # 45.50 Yuan
        ]

        for pattern in price_patterns:
            price_match = re.search(pattern, text)
            if price_match:
                try:
                    target_price = float(price_match.group(1))
                    break
                except ValueError:
                    continue

        # Extract confidence
        confidence = 0.7  # Default
        confidence_match = re.search(r'Confidence[: :]?\s*(\d+(?:\.\d+)?)', text)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
                if confidence > 1:  # If it is in percentage form
                    confidence = confidence / 100
            except ValueError:
                pass

        # Extract risk score
        risk_score = 0.5  # Default
        risk_match = re.search(r'risk[Rating score][: :]?\s*(\d+(?:\.\d+)?)', text)
        if risk_match:
            try:
                risk_score = float(risk_match.group(1))
                if risk_score > 1:  # If it is in percentage form
                    risk_score = risk_score / 100
            except ValueError:
                pass

        # 🔥 Extract research basis (preferably extract from JSON, otherwise extract text summary)
        # Note: If text is final_trade_decision (risk assessment report), it should not be used as reasoning
        # Only a brief summary of reasoning is extracted here
        
        # 🔍 Debugging: First print the original text content to see what is inside (complete content, not truncated)
        self.logger.info("🔍 [TaskAnalysisService._extract_decision_from_text] ========== Original text content (complete) ==========")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Text length: {len(text)}")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] full text content:\n{text}")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Does it contain ```json: {'```json' in text}")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Does it contain ```: {'```' in text}")
        
        reasoning = ""
        
        # 1. First try to extract from JSON code block reasoning
        import json
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if not json_match:
            # Try the code block without json tag
            json_match = re.search(r'```\s*(\{.*?\})\s*```', text, re.DOTALL)
        
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON Code block matching results: {json_match is not None}")
        if json_match:
            json_content = json_match.group(1)
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON code block length: {len(json_content)}")
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON Complete content of code block:\n{json_content}")
        
        # 🔥 Fields extracted from JSON
        price_analysis_range_from_json = None
        risk_score_from_json = None
        confidence_from_json = None
        
        if json_match:
            try:
                json_str = json_match.group(1)
                self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Trying to parse JSON, length: {len(json_str)}")
                json_obj = json.loads(json_str)
                self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON 解析成功，类型: {type(json_obj)}, 字段: {list(json_obj.keys()) if isinstance(json_obj, dict) else 'N/A'}")
                # Extract reasoning fields from JSON
                if isinstance(json_obj, dict):
                    # 🔥 Extract price_analysis_range (price range)
                    price_analysis_range_from_json = json_obj.get('price_analysis_range')
                    if price_analysis_range_from_json:
                        self.logger.info(f"✅ [TaskAnalysisService._extract_decision_from_text] Extract from JSON price_analysis_range: {price_analysis_range_from_json}")
                    
                    # 🔥 Extract risk_score (risk score)
                    risk_score_from_json = json_obj.get('risk_score')
                    if risk_score_from_json is not None:
                        # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                        if isinstance(risk_score_from_json, (int, float)) and risk_score_from_json > 1:
                            risk_score_from_json = risk_score_from_json / 100.0
                        self.logger.info(f"✅ [TaskAnalysisService._extract_decision_from_text] Extract from JSON risk_score: {risk_score_from_json}")
                    
                    # 🔥 Extract confidence
                    confidence_from_json = json_obj.get('confidence')
                    if confidence_from_json is not None:
                        # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                        if isinstance(confidence_from_json, (int, float)) and confidence_from_json > 1:
                            confidence_from_json = confidence_from_json / 100.0
                        self.logger.info(f"✅ [TaskAnalysisService._extract_decision_from_text] Extract from JSON confidence: {confidence_from_json}")
                    
                    # 🔥 Extract the final_trade_decision nested object if it exists
                    final_trade_decision = json_obj.get('final_trade_decision', {})
                    if isinstance(final_trade_decision, dict):
                        # If there is no price_analysis_range in the outer layer, try to get it from final_trade_decision
                        if not price_analysis_range_from_json:
                            price_analysis_range_from_json = final_trade_decision.get('price_analysis_range')
                        # If the outer layer does not have risk_score, try to get it from final_trade_decision
                        if risk_score_from_json is None:
                            risk_score_from_json = final_trade_decision.get('risk_score')
                        # If there is no confidence in the outer layer, try to get it from final_trade_decision
                        if confidence_from_json is None:
                            confidence_from_json = final_trade_decision.get('confidence')
                    
                    json_reasoning = json_obj.get('reasoning', '')
                    self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON length of reasoning in: {len(json_reasoning) if json_reasoning else 0}")
                    self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON full content of reasoning in:\n{json_reasoning if json_reasoning else 'N/A'}")
                    if json_reasoning and isinstance(json_reasoning, str) and len(json_reasoning.strip()) > 0:
                        # If reasoning is long, just take the first 100 characters as summary
                        if len(json_reasoning) > 100:
                            reasoning = json_reasoning[:100].strip() + "..."
                        else:
                            reasoning = json_reasoning.strip()
                        self.logger.info(f"✅ [TaskAnalysisService._extract_decision_from_text] 从 JSON 提取 reasoning: {len(reasoning)}字符")
                    else:
                        self.logger.warning("⚠️ [TaskAnalysisService._extract_decision_from_text] JSON reasoning in is empty or not a string")
            except (json.JSONDecodeError, Exception) as e:
                self.logger.warning(f"⚠️ [TaskAnalysisService._extract_decision_from_text] JSON Parsing failed: {e}")
                import traceback
                self.logger.warning(f"⚠️ [TaskAnalysisService._extract_decision_from_text] JSON Parse failure details:\n{traceback.format_exc()}")
        
        # 2. If not extracted from JSON, try to extract a short summary from the text
        if not reasoning:
            self.logger.info("🔍 [TaskAnalysisService._extract_decision_from_text] JSON Extraction failed, trying to extract from text")
            # Remove Markdown tags and code block tags
            clean_text = re.sub(r'```json.*?```', '', text, flags=re.DOTALL)
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Remove ```json length after code block: {len(clean_text)}")
            clean_text = re.sub(r'```.*?```', '', clean_text, flags=re.DOTALL)
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Length after removing all code blocks: {len(clean_text)}")
            clean_text = clean_text.replace('#', '').replace('*', '').replace('`', '').strip()
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Length after removing Markdown tags: {len(clean_text)}")
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Cleaned text complete content:\n{clean_text}")
            
            # Extract the first 100 characters as a summary (shorter than the previous 150 characters to avoid including too much content)
            if len(clean_text) > 100:
                reasoning = clean_text[:100].strip() + "..."
            else:
                reasoning = clean_text.strip()
            
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] 从文本提取 reasoning: {len(reasoning)}字符")
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] reasoning full content extracted from text:\n{reasoning}")
        
        # 3. If still not available, use default value
        if not reasoning or len(reasoning.strip()) < 10:
            reasoning = "Please refer to the detailed analysis report."
            self.logger.warning("⚠️ [TaskAnalysisService._extract_decision_from_text] reasoning Empty or too short, use default value")
        
        self.logger.info("🔍 [TaskAnalysisService._extract_decision_from_text] ========== eventually reasoning ==========")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] 最终 reasoning 长度: {len(reasoning)}字符")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] final reasoning full content:\n{reasoning}")

        # 🔥 Use the value extracted from JSON if present
        final_confidence = confidence_from_json if confidence_from_json is not None else confidence
        final_risk_score = risk_score_from_json if risk_score_from_json is not None else risk_score
        
        return {
            'action': action,
            'target_price': target_price,
            'price_analysis_range': price_analysis_range_from_json,  # 🔥 New: price range
            'confidence': final_confidence,  # 🔥 Use values extracted from JSON
            'risk_score': final_risk_score,  # 🔥 Use values extracted from JSON
            'reasoning': reasoning
        }

    async def _update_task(self, task: UnifiedAnalysisTask) -> None:
        """Update tasks to database

        Args:
            task: Task object
        """
        doc = task.model_dump(by_alias=True, exclude={"_id"}, mode='python')

        # Make sure user_id is of type ObjectId, not a string
        if 'user_id' in doc and isinstance(doc['user_id'], str):
            from bson import ObjectId
            doc['user_id'] = ObjectId(doc['user_id'])

        await self.collection.update_one(
            {"task_id": task.task_id},
            {"$set": doc}
        )
        self.logger.debug(f"💾 任务已更新: {task.task_id}")

    def _schedule_growth_extraction(
        self,
        task_id: str,
        raw_result: Dict[str, Any],
        formatted_result: Dict[str, Any],
        analysis_id: Optional[str],
    ) -> None:
        """Asynchronous scheduling of growth extraction to avoid blocking the main link of the task."""
        try:
            asyncio.create_task(
                self._extract_growth_in_background(
                    task_id=task_id,
                    raw_result=raw_result,
                    formatted_result=formatted_result,
                    analysis_id=analysis_id,
                )
            )
        except Exception as exc:
            self.logger.warning(f"⚠️ Scheduling growth extraction task failed(ignore): {exc}")

    async def _extract_growth_in_background(
        self,
        task_id: str,
        raw_result: Dict[str, Any],
        formatted_result: Dict[str, Any],
        analysis_id: Optional[str],
    ) -> None:
        """The background extracts the growth products and writes back the task, which does not affect the completion time of the main task."""
        try:
            task = await self.get_task(task_id)
            if not task:
                self.logger.warning(f"⚠️ Background growth extraction skipped: task does not exist {task_id}")
                return

            from app.services.workflow_growth_service import get_workflow_growth_service

            growth_context = await get_workflow_growth_service().process_completed_task(
                task=task,
                raw_result=raw_result,
                formatted_result=formatted_result,
                analysis_id=analysis_id,
            )

            update_fields: Dict[str, Any] = {
                "growth_context": growth_context.model_dump(mode="python"),
                "updated_at": now_tz(),
            }
            if task.result is not None:
                update_fields["result.growth_context"] = growth_context.model_dump(mode="json")

            await self.collection.update_one(
                {"task_id": task_id},
                {"$set": update_fields}
            )
            self.logger.info(f"✅ 后台成长提取完成: {task_id}")
        except Exception as exc:
            self.logger.warning(f"⚠️ Background growth extraction failed(ignore): {task_id} - {exc}")

    async def _save_to_analysis_reports(self, task: UnifiedAnalysisTask, result: Dict[str, Any]) -> Optional[str]:
        """Save analysis results to the analysis_reports collection (compatible with legacy API)

        Use unified report saving tool functions

        Args:
            task: Task object
            result: Formatted analysis results
        """
        try:
            from app.utils.report_saver import save_analysis_report

            stock_code = task.task_params.get("symbol") or task.task_params.get("stock_code", "")
            market_type = task.task_params.get("market_type", "A股")

            # Parse stock name if not in result
            stock_name = result.get("stock_name", "")
            if not stock_name:
                stock_name = await self._resolve_stock_name(stock_code)

            # 🔑 Get model information
            quick_model = task.task_params.get("quick_analysis_model") or result.get("quick_model", "Unknown")
            deep_model = task.task_params.get("deep_analysis_model") or result.get("deep_model", "Unknown")
            model_info = result.get("model_info") or f"{quick_model}/{deep_model}"

            # 🔑 Extract analyst list from report
            def _get_analysts_from_reports(reports_dict: Dict[str, Any]) -> List[str]:
                """Dynamically generate analyst list based on actual saved reports"""
                analysts = []
                fundamentals_analyst_id = (
                    "etf_analyst" if task.task_type == AnalysisTaskType.ETF_ANALYSIS else "fundamentals_analyst"
                )
                analyst_mapping = {
                    "index_report": "index_analyst",
                    "sector_report": "sector_analyst",
                    "market_report": "market_analyst",
                    "sentiment_report": "sentiment_analyst",
                    "news_report": "news_analyst",
                    "fundamentals_report": fundamentals_analyst_id,
                    "bull_researcher": "bull_researcher",
                    "bear_researcher": "bear_researcher",
                    "risky_analyst": "risky_analyst",
                    "safe_analyst": "safe_analyst",
                    "neutral_analyst": "neutral_analyst",
                }
                for report_key, analyst_id in analyst_mapping.items():
                    if report_key in reports_dict and reports_dict[report_key]:
                        analysts.append(analyst_id)
                return analysts

            reports_dict = result.get("reports", {})
            analysts_list = _get_analysts_from_reports(reports_dict) or result.get("analysts", [])

            # 🔑 Extract recommendations and confidence_score
            decision = result.get("decision", {})
            recommendation = result.get("recommendation", "")
            if not recommendation and decision.get("action"):
                # 🔥 Compliance Modification: Use"analysis point of view"substitute"investment advice", No specific price included
                recommendation = f"Analysis point of view:{decision.get('action')}; "
                if decision.get("reasoning"):
                    reasoning = decision.get("reasoning", "")[:200]
                    recommendation += f"Analysis basis:{reasoning}"

            confidence_score = result.get("confidence_score", 0.0)
            if confidence_score == 0.0 and decision.get("confidence"):
                confidence_score = decision.get("confidence", 0.0)

            risk_level = result.get("risk_level", "中等")
            if risk_level == "中等" and decision.get("risk_score") is not None:
                risk_score = decision.get("risk_score", 0.5)
                if risk_score < 0.3:
                    risk_level = "低"
                elif risk_score < 0.6:
                    risk_level = "中等"
                else:
                    risk_level = "高"

            # 🔥 Use unified report saving function
            analysis_id = await save_analysis_report(
                db=self.db,
                stock_symbol=stock_code,
                stock_name=stock_name,
                market_type=market_type,
                model_info=model_info,
                reports=reports_dict,
                decision=decision,
                recommendation=recommendation,
                confidence_score=confidence_score,
                risk_level=risk_level,
                summary=result.get("summary", ""),
                key_points=result.get("key_points", []),
                task_id=task.task_id,
                execution_time=task.execution_time or 0,
                tokens_used=result.get("tokens_used", 0),
                analysts=analysts_list,
                research_depth=result.get("research_depth", task.task_params.get("research_depth", "标准")),
                analysis_date=result.get("analysis_date"),
                source="api",
                engine="v2" if task.engine_type in ["auto", "workflow"] else (task.engine_type or "v2"),
                user_id=str(task.user_id) if task.user_id else None,
                performance_metrics=result.get("performance_metrics", {}),
                task_type=str(task.task_type),
            )

            self.logger.info(f"✅ Analysis results have been saved to analysis_reports: analysis_id={analysis_id}, task_id={task.task_id}")
            return analysis_id  # 🔑 Return to the saved analysis_id

        except Exception as e:
            self.logger.error(f"❌ Saving to analysis_reports failed: {e}", exc_info=True)
            return None  # 🔑 Return when saving fails None

    async def _store_stock_object_memory(self, task: UnifiedAnalysisTask, result: Dict[str, Any]) -> None:
        """Write stock analysis results from background tasks to objectized long-term memory."""
        symbol = str((task.task_params or {}).get("symbol") or (task.task_params or {}).get("stock_code") or "").strip().upper()
        if not symbol or _task_analysis_service_is_cn_etf_symbol(symbol):
            return

        summary = str(result.get("summary") or result.get("executive_summary") or "").strip()
        recommendation = str(result.get("recommendation") or "").strip()
        if not summary and not recommendation:
            return

        from core.memory.service import get_memory_service

        svc = get_memory_service(self.db)
        analysis_date = str(
            result.get("analysis_date")
            or (task.task_params or {}).get("analysis_date")
            or now_tz().strftime("%Y-%m-%d")
        ).strip()
        evidence = [
            str(item or "").strip()
            for item in (result.get("key_points") or [])[:5]
            if str(item or "").strip()
        ]
        memory_result = await svc.store_stock_analysis(
            user_id=str(task.user_id or ""),
            symbol=symbol,
            market=_normalize_memory_market(symbol, (task.task_params or {}).get("market_type")),
            summary=summary or recommendation,
            recommendation=recommendation,
            analysis_date=analysis_date,
            task_id=str(task.task_id),
            agent_id="workflow_analyst",
            session_id=str(task.task_id),
            evidence=evidence,
            next_checks=[recommendation] if recommendation else None,
        )
        self.logger.info(
            "[mem0] Objectized stock memory writing results — user=%s symbol=%s task=%s facts=%d success=%s error=%s",
            str(task.user_id or ""),
            symbol,
            str(task.task_id),
            memory_result.facts_extracted,
            memory_result.success,
            memory_result.error or "",
        )
    
    async def _find_one_compatible(self, collection, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None):
        """Compatible with find_one calls of synchronous/asynchronous Mongo collections."""
        result = collection.find_one(query, projection)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _resolve_stock_name(self, stock_code: str) -> str:
        """Parse stock names
        
        Args:
            stock_code: Stock code
            
        Returns:
            Stock name, returns default value if parsing fails
        """
        if not stock_code:
            return ""
        
        try:
            code_str = str(stock_code).strip().zfill(6)

            if self.db is not None:
                if _task_analysis_service_is_cn_etf_symbol(code_str):
                    etf_doc = await self._find_one_compatible(
                        self.db.etf_basic_info,
                        {"code": code_str},
                        {"name": 1, "fund_name": 1, "etf_name": 1, "_id": 0}
                    )
                    if etf_doc:
                        etf_name = etf_doc.get("name") or etf_doc.get("fund_name") or etf_doc.get("etf_name")
                        if etf_name:
                            return etf_name

                stock_doc = await self._find_one_compatible(
                    self.db.stock_basic_info,
                    {"$or": [{"code": code_str}, {"symbol": code_str}]},
                    {"name": 1, "stock_name": 1, "_id": 0}
                )
                if stock_doc:
                    stock_name = stock_doc.get("name") or stock_doc.get("stock_name")
                    if stock_name:
                        return stock_name

            # Prioritize trying to get structured data from data_source_manager
            try:
                from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                info_dict = get_info_dict(stock_code)
                if info_dict and isinstance(info_dict, dict) and info_dict.get('name'):
                    return info_dict['name']
            except Exception:
                pass
            
            # Downgrade: try using get_stock_basic_info
            try:
                from tradingagents.dataflows.data_source_manager import get_stock_basic_info
                info_str = get_stock_basic_info(stock_code)
                
                if info_str and isinstance(info_str, str) and "股票名称:" in info_str:
                    stock_name = info_str.split("股票名称:")[1].split("\n")[0].strip()
                    if stock_name:
                        return stock_name
                elif info_str and isinstance(info_str, dict) and info_str.get("name"):
                    return info_str["name"]
            except Exception:
                pass
                
        except Exception as e:
            self.logger.warning(f"⚠️ 解析股票名称失败: {stock_code} - {e}")
        
        return f"{'ETF' if _task_analysis_service_is_cn_etf_symbol(stock_code) else 'stocks'}{stock_code}"
    
    async def _validate_task_data(self, task: UnifiedAnalysisTask) -> 'DataValidationResult':
        """
        Verify data integrity required for tasks
        
        Args:
            task: Analyze task objects
            
        Returns:
            DataValidationResult: Verification result
        """
        from app.services.data_validation_service import get_data_validation_service
        
        # Extract necessary information from task parameters
        task_params = task.task_params or {}
        symbol = task_params.get("symbol") or task_params.get("stock_code", "")
        analysis_date = task_params.get("analysis_date")
        market_type = task_params.get("market_type", "cn")
        
        # If market_type is "A shares" Wait for Chinese, convert to English
        market_type_map = {
            "A股": "cn",
            "港股": "hk",
            "美股": "us",
            "cn": "cn",
            "hk": "hk",
            "us": "us"
        }
        market_type = market_type_map.get(market_type, "cn")
        
        # If no analysis date is specified, the current date is used
        if not analysis_date:
            from datetime import datetime
            analysis_date = datetime.now().strftime('%Y-%m-%d')
        
        if not symbol:
            from app.services.data_validation_service import DataValidationResult
            return DataValidationResult(
                is_valid=False,
                message="Stock symbol (symbol or stock_code) missing from task parameters",
                missing_data=["symbol"],
                details={"error": "股票代码缺失"}
            )
        
        # Call the data verification service
        validation_service = get_data_validation_service()
        result = await validation_service.validate_stock_data(
            symbol=symbol,
            analysis_date=analysis_date,
            market_type=market_type,
            check_basic_info=True,
            check_historical_data=True,
            check_financial_data=False,  # Financial data optional
            check_realtime_quotes=False,  # Real-time quotes optional
            historical_days=365  # By default, historical data of the past 1 year is checked.
        )
        
        return result

    async def get_task_statistics(self, user_id: PyObjectId) -> Dict[str, Any]:
        """Get user task statistics

        Args:
            user_id: User ID

        Returns:
            Statistics Dictionary
        """
        self.logger.info(f"📊 获取任务统计 - user_id: {user_id} (类型: {type(user_id)})")

        # Check the total number of tasks first
        total_count = await self.collection.count_documents({"user_id": user_id})
        self.logger.info(f"📊 用户任务总数: {total_count}")

        # If there is no task, empty statistics will be returned directly.
        if total_count == 0:
            self.logger.warning(f"⚠️ 用户 {user_id} 没有任务")
            # Print some debugging information
            all_tasks = await self.collection.find().limit(5).to_list(5)
            self.logger.info("📋 数据库中的任务示例:")
            for task in all_tasks:
                self.logger.info(f"  - task_id: {task.get('task_id')}, user_id: {task.get('user_id')} (类型: {type(task.get('user_id'))})")

        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }}
        ]

        cursor = self.collection.aggregate(pipeline)

        stats = {
            "total": 0,
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0
        }

        async for doc in cursor:
            status = doc["_id"]
            count = doc["count"]
            self.logger.info(f"📊 状态统计: {status} = {count}")
            stats[status] = count
            stats["total"] += count

        self.logger.info(f"📊 最终统计结果: {stats}")
        return stats
    
    async def _send_analysis_email_notification(
        self,
        task: UnifiedAnalysisTask,
        formatted_result: Dict[str, Any]
    ) -> None:
        """Send analysis completion email notification
        
        Args:
            task: Task object
            formatted_result: Formatted analysis results
        """
        from app.services.email_service import get_email_service
        from app.models.email import EmailType
        
        try:
            email_service = get_email_service()
            
            # Extract stock information from task parameters
            stock_code = task.task_params.get("symbol") or task.task_params.get("stock_code", "")
            stock_name = formatted_result.get("stock_name") or formatted_result.get("stock_symbol") or stock_code
            analysis_date = formatted_result.get("analysis_date", "")
            
            # Extract analysis information from formatted results
            summary = formatted_result.get("summary", "")
            recommendation = formatted_result.get("recommendation", "")
            confidence_score = formatted_result.get("confidence_score", 0)
            risk_level = formatted_result.get("risk_level", "中等")
            
            # Extract key points (from reasoning or other fields)
            key_points = formatted_result.get("key_points", [])
            if not key_points:
                # Try to extract key points from decision.reasoning
                decision = formatted_result.get("decision", {})
                reasoning = decision.get("reasoning", "")
                if reasoning and reasoning != "暂无分析推理":
                    # Simple extraction: split by periods, take the first 3 items
                    sentences = [s.strip() for s in reasoning.split("。") if s.strip()]
                    key_points = sentences[:3]
            
            # Generate PDF attachment (optional)
            attachments = None
            try:
                from app.utils.report_exporter import ReportExporter
                from app.utils.report_formatter import extract_reports_from_state
                
                report_exporter = ReportExporter()
                if report_exporter.weasyprint_available or report_exporter.pdfkit_available:
                    reports = formatted_result.get("reports", {})
                    if not reports:
                        state = formatted_result.get("state", {})
                        reports = extract_reports_from_state(state)
                    
                    if reports:
                        # Build report document
                        report_doc = {
                            "stock_symbol": stock_code,
                            "stock_name": stock_name,
                            "analysis_date": analysis_date,
                            "recommendation": recommendation,
                            "confidence_score": confidence_score,
                            "risk_level": risk_level,
                            "reports": reports,
                            "decision": formatted_result.get("decision", {})
                        }
                        
                        pdf_content = report_exporter.generate_pdf_report(report_doc)
                        if pdf_content:
                            filename = f"{stock_code}_{analysis_date}_分析报告.pdf"
                            attachments = [(filename, pdf_content, "application/pdf")]
                            self.logger.info(f"📄 PDF report generated: {filename} ({len(pdf_content)} bytes)")
            except Exception as pdf_err:
                self.logger.warning(f"⚠️ PDF Build failed(Email will be sent without attachments): {pdf_err}")
            
            # Send email
            await email_service.send_analysis_email(
                user_id=str(task.user_id),
                email_type=EmailType.SINGLE_ANALYSIS,
                template_name="single_analysis",
                template_data={
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "analysis_date": analysis_date,
                    "summary": summary,
                    "recommendation": recommendation,
                    "confidence_score": confidence_score,
                    "risk_level": risk_level,
                    "key_points": key_points,
                    "detail_url": f"{stock_code}"
                },
                reference_id=task.task_id,
                attachments=attachments  # Comes with PDF report
            )
            self.logger.info(f"📧 Attempted to send analysis completion email: {task.task_id}")
        except Exception as e:
            # Failure to send the email should not affect task completion, only a warning will be logged
            self.logger.warning(f"⚠️ Failed to send email notification(ignore): {e}", exc_info=True)
            raise  # Rethrow the exception to let the caller know the failure (but does not affect the task status)


# Singleton instance
_task_service: Optional[TaskAnalysisService] = None


def get_task_analysis_service() -> TaskAnalysisService:
    """获取任务分析服务单例"""
    global _task_service
    if _task_service is None:
        _task_service = TaskAnalysisService()
    return _task_service


# === planned_analysis_service.py ===
"""
Planning analysis services — Plan-then-Execute mode

Arrange three-level assurance process:
  1. Seed process matching → 2. LLM independent planning → 3. ReAct rollback

Dependency sharing layer (from intelligent_assistant_service):
  - _get_assistant_llm_config()
  - _get_system_prompt()
  - _get_latest_trade_date()
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncGenerator, AsyncIterator, Dict, List, Optional

from core.agents.plan_executor import PlanExecutor
from core.agents.planner import Planner
from core.agents.planner_models import (
    AnalysisPlan,
    PlanSource,
    PlanStep,
    PlannedAnalysisResult,
    StepResult,
    SupplementRequest,
)
from core.llm import UnifiedLLMClient
from core.llm.models import Message, MessageRole
from core.tools import get_tool_registry, tool_metadata_list_to_openai

from app.services.intelligent_assistant_service import (
    _get_assistant_llm_config,
    _build_assistant_model_preferences,
    _build_fallback_memory_facts,
    _get_preferred_assistant_config_id,
    _get_preferred_assistant_model,
    _get_system_prompt,
    _get_latest_trade_date,
    get_assistant_conversation,
    get_or_create_assistant_thread,
    IntelligentAssistantService,
    save_assistant_message,
)

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _store_planned_analysis_memory(
    db,
    user_id: str,
    conversation_id: str,
    user_message: str,
    reply: str,
    tools_used: List[str],
    source: str,
) -> None:
    """Planning analysis replies are no longer written to mem0 long-term memory to avoid free text pollution."""
    return


# ============================================================
# Does not support variety detection
# ============================================================
# The vocabulary list and detection logic have been integrated into core.assistant.lexicon (A11 Phase 4: Dictionary Convergence Unit,
# Assistant routing and planning analysis share the same set of variety gates), and only compatible commissions are retained here.


def _check_unsupported_asset(question: str) -> Optional[str]:
    """Detect if the user question involves an unsupported symbol type (source of fact: core.assistant.lexicon).

    Returns:
        If an unsupported variety is detected, a prompt message is returned; otherwise, None is returned.
    """
    from core.assistant.lexicon import detect_unsupported_asset
    return detect_unsupported_asset(question)

# overall timeout
PLANNED_ANALYSIS_TIMEOUT = int(os.environ.get("PLANNED_ANALYSIS_TIMEOUT", "180"))

# Maximum number of session contexts
MAX_CONTEXT_MESSAGES = 5


def _build_synthesize_prompt(
    question: str,
    plan: AnalysisPlan,
    step_results: List[StepResult],
) -> str:
    """build synthesis phase prompt"""
    results_text = ""
    for sr in step_results:
        status = "✅ 成功" if sr.success else f"❌ 失败: {sr.error}"
        result_preview = str(sr.result)[:2000] if sr.result else "(无数据)"
        results_text += f"\n### 步骤 {sr.step_id}: {sr.intent}\n"
        results_text += f"- 工具: {sr.tool}\n- 状态: {status}\n"
        results_text += f"- data:\n```\n{result_preview}\n```\n"

    return f"""基于以下分析数据，回答用户问题。

## 用户问题
{question}

## 分析结果
{results_text}

## 要求（以投资教练的身份回答）
1. 基于工具返回的客观数据进行解读，教用户如何理解这些数据
2. 讲解分析方法和框架，引导用户建立自己的判断，不给"买入/卖出"的直接建议
3. 遇到专业概念时用通俗语言解释
4. 如果某些数据获取失败，说明原因并基于已有数据回答
5. 如果数据严重不足无法回答，在回答末尾添加一行: [NEED_SUPPLEMENT]
6. 使用 Markdown 格式，条理清晰
7. 结尾自然提醒：以上分析仅供学习参考，不构成投资建议

请回答："""


def _build_supplement_prompt(
    question: str,
    current_answer: str,
) -> str:
    """Build supplementary request judgment prompt"""
    return f"""你之前基于工具数据回答了用户问题，但标记了数据不足。

## 用户问题
{question}

## 当前回答（不完整）
{current_answer}

## 要求
如果需要补充数据，返回 JSON 格式的补充请求：
```json
{{
  "reason": "需要补充的原因",
  "steps": [
    {{"id": 1, "tool": "工具ID", "args": {{"参数": "值"}}, "intent": "目的", "depends_on": []}}
  ]
}}
```
补充步骤最多 2 个。如果不需要补充直接返回 "none"。"""


class PlannedAnalysisService:
    """
    Planning analysis services

    Completely arranged Plan → Execute → Synthesize process.
    If planning fails, fall back to ReAct mode (reuse IntelligentAssistantService).
    """

    def __init__(self, db, preferred_models: Optional[Dict[str, Any]] = None):
        self._db = db
        self._llm_client: Optional[UnifiedLLMClient] = None
        self._tool_functions: Optional[Dict[str, Any]] = None
        self._openai_tools: Optional[List[Dict[str, Any]]] = None
        self._preferred_model = _get_preferred_assistant_model(preferred_models)
        self._preferred_model_config_id = _get_preferred_assistant_config_id(preferred_models)

    def _get_react_preferred_models(self) -> Dict[str, str]:
        if not self._preferred_model and not self._preferred_model_config_id:
            return {}
        preferred: Dict[str, str] = {}
        if self._preferred_model:
            preferred["model"] = self._preferred_model
        if self._preferred_model_config_id:
            preferred["model_config_id"] = self._preferred_model_config_id
        return preferred

    async def _ensure_client(self) -> bool:
        """Make sure the LLM client and tools are loaded"""
        if self._llm_client is not None:
            return True

        llm_config = await _get_assistant_llm_config(
            self._db,
            preferred_models=self._get_react_preferred_models() or None,
        )
        if not llm_config:
            return False

        try:
            self._llm_client = UnifiedLLMClient.from_config(llm_config)
        except Exception as e:
            logger.error(f"[planning analysis] Creating LLM client failed: {e}", exc_info=True)
            return False

        registry = get_tool_registry()
        all_metadata = registry.list_all()
        self._openai_tools = tool_metadata_list_to_openai(all_metadata)

        self._tool_functions = {}
        for tool in all_metadata:
            if tool.fc_enabled and tool.parameters:
                func = registry.get_function(tool.id)
                if func:
                    self._tool_functions[tool.id] = func

        self._llm_client.inject_tools(self._tool_functions)
        logger.info(f"[规划分析] 已加载 {len(self._openai_tools)} 个工具")
        return True

    # ----------------------------------------------------------
    # public interface
    # ----------------------------------------------------------

    async def analyze(
        self,
        question: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> PlannedAnalysisResult:
        """
        Perform planning analysis.

        Args:
            question: User issues
            user_id: User ID (used to get session history)
            conversation_id: session ID

        Returns:
            PlannedAnalysisResult
        """
        # === Pre-check: Unsupported symbol type ===
        unsupported_msg = _check_unsupported_asset(question)
        if unsupported_msg:
            logger.info("[planning analysis] If an unsupported variety type is detected, a prompt will be returned directly.")
            return PlannedAnalysisResult(
                reply=unsupported_msg,
                source=PlanSource.SEED_FLOW,
            )

        if not await self._ensure_client():
            return PlannedAnalysisResult(
                reply="Intelligent analysis is temporarily unavailable, please check whether the LLM configuration has been configured correctly in Settings.",
                source=PlanSource.REACT_FALLBACK,
            )

        try:
            return await asyncio.wait_for(
                self._do_analyze(question, user_id, conversation_id),
                timeout=PLANNED_ANALYSIS_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[规划分析] 整体超时（{PLANNED_ANALYSIS_TIMEOUT}s）")
            return PlannedAnalysisResult(
                reply=f"Sorry, the analysis took too long (exceeded {PLANNED_ANALYSIS_TIMEOUT} seconds).\n\n"
                      "We recommend that you try breaking the question into more specific details or try again later.",
                source=PlanSource.REACT_FALLBACK,
            )
        except Exception as e:
            logger.exception("[规划分析] 分析失败")
            return PlannedAnalysisResult(
                reply=f"An error occurred while processing your request:{str(e)}. Please check the network and LLM configuration and try again.",
                source=PlanSource.REACT_FALLBACK,
            )

    async def analyze_stream(
        self,
        question: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming execution planning analysis and output SSE events."""
        unsupported_msg = _check_unsupported_asset(question)
        if unsupported_msg:
            yield _sse("token", {"content": unsupported_msg})
            yield _sse(
                "done",
                {
                    "reply": unsupported_msg,
                    "tools_used": [],
                    "source": PlanSource.SEED_FLOW.value,
                    "supplemented": False,
                },
            )
            return

        if not await self._ensure_client():
            message = "Intelligent analysis is temporarily unavailable, please check whether the LLM configuration has been configured correctly in Settings."
            yield _sse("token", {"content": message})
            yield _sse(
                "done",
                {
                    "reply": message,
                    "tools_used": [],
                    "source": PlanSource.REACT_FALLBACK.value,
                    "supplemented": False,
                },
            )
            return

        tools_used: List[str] = []
        collected_step_results: List[StepResult] = []
        supplemented = False
        plan: Optional[AnalysisPlan] = None

        try:
            context_messages = await self._get_context_messages(user_id, conversation_id)

            curr_date = _get_latest_trade_date()
            trade_date = curr_date

            knowledge_snippets = ""
            try:
                from core.knowledge import FinancialKnowledgeManager
                km = FinancialKnowledgeManager(db=self._db)
                knowledge_snippets = km.retrieve_for_prompt(question)
            except Exception as e:
                logger.debug(f"[planning analysis] Knowledge retrieval skip: {e}")

            yield _sse("plan_started", {"message": "正在规划分析步骤"})

            planner = Planner(
                llm_client=self._llm_client,
                curr_date=curr_date,
                trade_date=trade_date,
            )
            plan = await planner.plan(question, context_messages, knowledge_snippets=knowledge_snippets)

            if plan.source == PlanSource.REACT_FALLBACK:
                yield _sse(
                    "mode_switch",
                    {"source": PlanSource.REACT_FALLBACK.value, "message": "Planning fails and falls back to ReAct mode"},
                )
                react_service = IntelligentAssistantService(
                    self._db,
                    preferred_models=self._get_react_preferred_models(),
                )
                async for event_str in react_service.chat_stream(question, conversation_id):
                    yield event_str
                return

            yield _sse(
                "plan_ready",
                {
                    "plan": plan.model_dump(),
                    "source": plan.source.value,
                },
            )

            executor = PlanExecutor()
            step_queue: asyncio.Queue = asyncio.Queue()

            def _on_step_started(step_id: int, tool: str, intent: str):
                step_queue.put_nowait(
                    {
                        "event": "step_started",
                        "step_id": step_id,
                        "tool": tool,
                        "intent": intent,
                    }
                )

            def _on_step_completed(sr: StepResult):
                tools_used.append(sr.tool)
                step_queue.put_nowait(
                    {
                        "event": "step_completed",
                        "step_result": sr.model_dump(),
                    }
                )

            execute_task = asyncio.create_task(
                executor.execute(
                    plan,
                    on_step_started=_on_step_started,
                    on_step_completed=_on_step_completed,
                )
            )

            while not execute_task.done() or not step_queue.empty():
                try:
                    payload = await asyncio.wait_for(step_queue.get(), timeout=0.3)
                    event_name = payload.pop("event", "progress")
                    if event_name == "step_completed":
                        step_result = payload.get("step_result")
                        if step_result:
                            collected_step_results.append(StepResult(**step_result))
                    yield _sse(event_name, payload)
                except asyncio.TimeoutError:
                    continue

            step_results = await execute_task
            collected_step_results = step_results

            yield _sse("synthesis_started", {"message": "正在汇总结论并生成报告"})
            reply_parts: List[str] = []
            async for chunk in self._stream_synthesize_chunks(question, plan, collected_step_results):
                reply_parts.append(chunk)
                yield _sse("token", {"content": chunk})
            reply = "".join(reply_parts)

            if "[NEED_SUPPLEMENT]" in reply:
                reply = reply.replace("[NEED_SUPPLEMENT]", "").strip()
                yield _sse("supplement_started", {"message": "正在补充缺失数据"})
                supplement_result = await self._try_supplement(question, reply, plan, tools_used)
                if supplement_result:
                    for sr in supplement_result:
                        collected_step_results.append(sr)
                        yield _sse("step_completed", {"step_result": sr.model_dump()})

                    yield _sse("synthesis_started", {"message": "Supplement completed, answers are being rearranged"})
                    reply_parts = []
                    async for chunk in self._stream_synthesize_chunks(question, plan, collected_step_results):
                        reply_parts.append(chunk)
                        yield _sse("token", {"content": chunk})
                    reply = "".join(reply_parts).replace("[NEED_SUPPLEMENT]", "").strip()
                    supplemented = True

            yield _sse(
                "done",
                {
                    "reply": reply,
                    "tools_used": list(set(tools_used)),
                    "step_results": [sr.model_dump() for sr in collected_step_results],
                    "plan": plan.model_dump() if plan else None,
                    "source": plan.source.value if plan else PlanSource.LLM_PLAN.value,
                    "supplemented": supplemented,
                },
            )
        except asyncio.CancelledError:
            yield _sse("error", {"message": "请求已取消"})
            yield _sse("done", {"tools_used": list(set(tools_used)), "error": True})
        except Exception as e:
            logger.exception("[planning analysis] Streaming analysis failed")
            yield _sse("error", {"message": f"An error occurred while processing the request:{str(e)}"})
            yield _sse("done", {"tools_used": list(set(tools_used)), "error": True})

    # ----------------------------------------------------------
    # internal implementation
    # ----------------------------------------------------------

    async def _do_analyze(
        self,
        question: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> PlannedAnalysisResult:
        """核心分析流程"""
        # Get session context
        context_messages = await self._get_context_messages(user_id, conversation_id)

        curr_date = _get_latest_trade_date()
        trade_date = curr_date  # The trading day is consistent with the current date (_get_latest_trade_date handles weekends)

        # RAG Dynamic knowledge retrieval (graceful degradation: returns empty string when unavailable)
        knowledge_snippets = ""
        try:
            from core.knowledge import FinancialKnowledgeManager
            km = FinancialKnowledgeManager(db=self._db)
            knowledge_snippets = km.retrieve_for_prompt(question)
        except Exception as e:
            logger.debug(f"[planning analysis] Knowledge retrieval skip: {e}")

        # === Phase 1: Planning ===
        planner = Planner(
            llm_client=self._llm_client,
            curr_date=curr_date,
            trade_date=trade_date,
        )
        plan = await planner.plan(question, context_messages, knowledge_snippets=knowledge_snippets)

        # Third level fallback:ReAct
        if plan.source == PlanSource.REACT_FALLBACK:
            return await self._react_fallback(question, conversation_id)

        # === Phase 2: Execution ===
        tools_used: List[str] = []
        executor = PlanExecutor()
        step_results = await executor.execute(
            plan,
            on_step_started=lambda sid, tool, intent: logger.info(
                f"[规划分析] 步骤 {sid} 开始: {tool} - {intent}"
            ),
            on_step_completed=lambda sr: (
                tools_used.append(sr.tool),
                logger.info(
                    f"[规划分析] 步骤 {sr.step_id} 完成: "
                    f"{'success' if sr.success else 'failed'} ({sr.duration_ms}ms)"
                ),
            ),
        )

        # === Stage 3: Synthesis ===
        reply = await self._synthesize(question, plan, step_results)

        # Limited replenishment mechanism
        supplemented = False
        if "[NEED_SUPPLEMENT]" in reply:
            reply = reply.replace("[NEED_SUPPLEMENT]", "").strip()
            supplement_result = await self._try_supplement(
                question, reply, plan, tools_used
            )
            if supplement_result:
                step_results.extend(supplement_result)
                reply = await self._synthesize(question, plan, step_results)
                reply = reply.replace("[NEED_SUPPLEMENT]", "").strip()
                supplemented = True

        return PlannedAnalysisResult(
            reply=reply,
            plan=plan,
            tools_used=list(set(tools_used)),
            step_results=step_results,
            source=plan.source,
            supplemented=supplemented,
        )

    async def _synthesize(
        self,
        question: str,
        plan: AnalysisPlan,
        step_results: List[StepResult],
    ) -> str:
        """Synthesis phase: generating the final answer based on the results of the steps"""
        system_prompt = _get_system_prompt()
        synth_prompt = _build_synthesize_prompt(question, plan, step_results)

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=synth_prompt),
        ]

        try:
            resp = await self._llm_client.achat(messages)
            return resp.content or "Sorry, we are unable to generate a comprehensive analysis at this time."
        except Exception as e:
            logger.error(f"[planning analysis] Synthesis phase failed: {e}")
            # Downgrade: splicing raw data
            parts = [f"## {question}\n"]
            for sr in step_results:
                if sr.success and sr.result:
                    parts.append(f"### {sr.intent}\n{str(sr.result)[:1000]}\n")
            parts.append("\n> ⚠️ Comprehensive analysis failed to generate. The above is a summary of the original data.")
            return "\n".join(parts)

    async def _stream_synthesize_chunks(
        self,
        question: str,
        plan: AnalysisPlan,
        step_results: List[StepResult],
    ) -> AsyncIterator[str]:
        """The synthesis stage streams the token."""
        system_prompt = _get_system_prompt()
        synth_prompt = _build_synthesize_prompt(question, plan, step_results)

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=synth_prompt),
        ]

        try:
            has_chunk = False
            async for chunk in self._llm_client.astream(messages):
                if chunk:
                    has_chunk = True
                    yield chunk
            if not has_chunk:
                fallback = await self._synthesize(question, plan, step_results)
                for i in range(0, len(fallback), 120):
                    yield fallback[i:i + 120]
        except Exception as e:
            logger.warning(f"[planning analysis] Synthetic streaming output fails, falling back to non-streaming synthesis: {e}")
            fallback = await self._synthesize(question, plan, step_results)
            for i in range(0, len(fallback), 120):
                yield fallback[i:i + 120]

    async def _try_supplement(
        self,
        question: str,
        current_answer: str,
        plan: AnalysisPlan,
        tools_used: List[str],
    ) -> Optional[List[StepResult]]:
        """Limited replenishment mechanic: max 1 round, max 2 tool calls"""
        prompt = _build_supplement_prompt(question, current_answer)
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are a stock analysis planner that only outputs JSON or none."),
            Message(role=MessageRole.USER, content=prompt),
        ]

        try:
            resp = await self._llm_client.achat(messages)
            raw = (resp.content or "").strip()

            if raw.lower() == "none" or not raw:
                return None

            # Parse supplementary requests
            import re
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            text = json_match.group(1).strip() if json_match else raw.strip()
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1:
                return None

            data = json.loads(text[start:end + 1])
            raw_steps = data.get("steps", [])[:2]  # Up to 2

            # Build the supplementary steps and execute
            supplement_steps = []
            max_id = max((s.id for s in plan.steps), default=0)
            for i, s in enumerate(raw_steps):
                supplement_steps.append(PlanStep(
                    id=max_id + i + 1,
                    tool=s.get("tool", ""),
                    args=s.get("args", {}),
                    intent=s.get("intent", "补充数据"),
                    depends_on=[],
                ))

            if not supplement_steps:
                return None

            logger.info(f"[规划分析] 执行补充调用: {len(supplement_steps)} 个步骤")
            supplement_plan = AnalysisPlan(
                question=question,
                steps=supplement_steps,
            )
            executor = PlanExecutor()
            results = await executor.execute(
                supplement_plan,
                on_step_completed=lambda sr: tools_used.append(sr.tool),
            )
            return results

        except Exception as e:
            logger.warning(f"[planning analysis] Supplementary call failed: {e}")
            return None

    async def _react_fallback(
        self,
        question: str,
        conversation_id: Optional[str] = None,
    ) -> PlannedAnalysisResult:
        """Third level fallback: Use existing ReAct mode"""
        logger.info("[planning analysis] Fallback to ReAct mode")
        react_service = IntelligentAssistantService(
            self._db,
            preferred_models=self._get_react_preferred_models(),
        )
        result = await react_service.chat(question, conversation_id)
        return PlannedAnalysisResult(
            reply=result.get("reply", ""),
            tools_used=result.get("tools_used", []),
            source=PlanSource.REACT_FALLBACK,
        )

    async def _get_context_messages(
        self,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Optional[List[Message]]:
        """Get recent session history as context"""
        if not user_id:
            return None

        try:
            raw_messages = await get_assistant_conversation(
                self._db,
                user_id,
                conversation_id,
            )
            if not raw_messages:
                return None

            recent = raw_messages[-MAX_CONTEXT_MESSAGES:]
            messages = []
            for m in recent:
                role = MessageRole.USER if m["role"] == "user" else MessageRole.ASSISTANT
                content = m.get("content", "")
                if content:
                    # Truncate too long historical messages
                    messages.append(Message(
                        role=role,
                        content=content[:500],
                    ))
            return messages if messages else None

        except Exception as e:
            logger.warning(f"[planning analysis] Failed to get session history: {e}")
            return None


async def stream_planned_analysis_with_assistant(
    db,
    user_message: str,
    user_id: str,
    conversation_id: Optional[str] = None,
    model: Optional[str] = None,
    model_config_id: Optional[str] = None,
    quick_model: Optional[str] = None,
    quick_model_config_id: Optional[str] = None,
    deep_model: Optional[str] = None,
    deep_model_config_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Provides external planning and analysis streaming interface with persistence."""
    service = PlannedAnalysisService(
        db,
        preferred_models=_build_assistant_model_preferences(
            model=model,
            model_config_id=model_config_id,
            quick_model=quick_model,
            quick_model_config_id=quick_model_config_id,
            deep_model=deep_model,
            deep_model_config_id=deep_model_config_id,
        ),
    )

    collected_reply = ""
    collected_tools: List[str] = []
    collected_plan: Optional[Dict[str, Any]] = None
    collected_step_results: List[Dict[str, Any]] = []
    source = PlanSource.LLM_PLAN.value
    supplemented = False

    async for event_str in service.analyze_stream(
        question=user_message.strip(),
        user_id=user_id,
        conversation_id=conversation_id,
    ):
        if event_str.startswith("event: done\n"):
            try:
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                data = json.loads(data_line)
                collected_tools = data.get("tools_used", [])
                collected_reply = data.get("reply", collected_reply)
                collected_plan = data.get("plan")
                collected_step_results = data.get("step_results", [])
                source = data.get("source", source)
                supplemented = data.get("supplemented", supplemented)
            except Exception:
                pass
            continue
        if event_str.startswith("event: token\n"):
            try:
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                data = json.loads(data_line)
                collected_reply += data.get("content", "")
            except Exception:
                pass
        elif event_str.startswith("event: plan_ready\n"):
            try:
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                data = json.loads(data_line)
                collected_plan = data.get("plan")
                source = data.get("source", source)
            except Exception:
                pass
        elif event_str.startswith("event: mode_switch\n"):
            try:
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                data = json.loads(data_line)
                source = data.get("source", source)
            except Exception:
                pass
        elif event_str.startswith("event: step_completed\n"):
            try:
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                data = json.loads(data_line)
                step_result = data.get("step_result")
                if step_result:
                    collected_step_results.append(step_result)
            except Exception:
                pass
        yield event_str

    if user_id and collected_reply:
        try:
            await save_assistant_message(
                db,
                user_id=user_id,
                user_content=user_message.strip(),
                assistant_content=collected_reply,
                tools_used=collected_tools,
                conversation_id=conversation_id,
            )
        except Exception as e:
            logger.warning("[planning analysis·streaming] Failed to save session: %s", e)

        asyncio.create_task(
            _store_planned_analysis_memory(
                db,
                user_id,
                conversation_id or "",
                user_message.strip(),
                collected_reply,
                collected_tools,
                source,
            )
        )

    conv_id = conversation_id
    if user_id:
        thread = await get_or_create_assistant_thread(db, user_id, conversation_id)
        conv_id = thread["thread_id"]

    yield _sse(
        "done",
        {
            "reply": collected_reply,
            "tools_used": collected_tools,
            "conversation_id": conv_id,
            "plan": collected_plan,
            "step_results": collected_step_results,
            "source": source,
            "supplemented": supplemented,
        },
    )


# === analysis_preference_service.py ===
"""
分析偏好服务
"""

import logging
from typing import Optional, List
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object
from app.core.database import get_mongo_db
from app.models.analysis_preference import (
    AnalysisPreference,
    AnalysisPreferenceCreate,
    AnalysisPreferenceUpdate
)
from datetime import datetime

logger = logging.getLogger(__name__)


class AnalysisPreferenceService:
    """分析偏好服务"""

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        """
        Initialize analysis preference service

        Args:
            db: MongoDB Database instance (optional, uses global connection pool by default)
        """
        self.db = db if db is not None else get_mongo_db()
        self.preferences_collection = self.db.analysis_preferences

    async def _create_indexes(self):
        """创建数据库索引"""
        try:
            await self.preferences_collection.create_index([("user_id", 1)])
            await self.preferences_collection.create_index([("user_id", 1), ("preference_type", 1)], unique=True)
            await self.preferences_collection.create_index([("is_default", 1)])
            logger.info("✅ 分析偏好索引创建完成")
        except Exception as e:
            logger.warning(f"⚠️ 创建索引失败: {e}")

    async def create_preference(
        self,
        user_id: str,
        preference_data: AnalysisPreferenceCreate
    ) -> Optional[AnalysisPreference]:
        """创建偏好"""
        try:
            # If set to default, cancel other defaults
            if preference_data.is_default:
                await self.preferences_collection.update_many(
                    {"user_id": ObjectId(user_id)},
                    {"$set": {"is_default": False}}
                )

            preference_doc = {
                "user_id": ObjectId(user_id),
                "preference_type": preference_data.preference_type,
                "risk_level": preference_data.risk_level,
                "confidence_threshold": preference_data.confidence_threshold,
                "position_size_multiplier": preference_data.position_size_multiplier,
                "decision_speed": preference_data.decision_speed,
                "is_default": preference_data.is_default,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            result = await self.preferences_collection.insert_one(preference_doc)
            logger.info(f"✅ 偏好创建成功: {result.inserted_id}")
            return await self.get_preference(str(result.inserted_id))

        except Exception as e:
            logger.error(f"❌ 创建偏好失败: {e}")
            return None

    async def get_preference(self, preference_id: str) -> Optional[AnalysisPreference]:
        """获取偏好"""
        try:
            pref_doc = await self.preferences_collection.find_one({"_id": ObjectId(preference_id)})
            if pref_doc:
                pref_doc["id"] = str(pref_doc["_id"])
                pref_doc["user_id"] = str(pref_doc["user_id"])
                return AnalysisPreference(**pref_doc)
            return None
        except Exception as e:
            logger.error(f"❌ 获取偏好失败: {e}")
            return None

    async def get_user_preferences(self, user_id: str) -> List[AnalysisPreference]:
        """获取用户所有偏好"""
        try:
            cursor = self.preferences_collection.find({"user_id": ObjectId(user_id)})
            prefs = await cursor.to_list(length=None)
            result = []
            for pref_doc in prefs:
                pref_doc["id"] = str(pref_doc["_id"])
                pref_doc["user_id"] = str(pref_doc["user_id"])
                result.append(AnalysisPreference(**pref_doc))
            return result
        except Exception as e:
            logger.error(f"❌ 获取用户偏好失败: {e}")
            return []

    async def get_default_preference(self, user_id: str) -> Optional[AnalysisPreference]:
        """获取用户默认偏好"""
        try:
            pref_doc = await self.preferences_collection.find_one({
                "user_id": ObjectId(user_id),
                "is_default": True
            })
            if pref_doc:
                pref_doc["id"] = str(pref_doc["_id"])
                pref_doc["user_id"] = str(pref_doc["user_id"])
                return AnalysisPreference(**pref_doc)
            return None
        except Exception as e:
            logger.error(f"❌ 获取默认偏好失败: {e}")
            return None

    async def update_preference(
        self,
        preference_id: str,
        update_data: AnalysisPreferenceUpdate
    ) -> Optional[AnalysisPreference]:
        """更新偏好"""
        try:
            pref = await self.get_preference(preference_id)
            if not pref:
                return None

            update_doc = {}
            if update_data.risk_level is not None:
                update_doc["risk_level"] = update_data.risk_level
            if update_data.confidence_threshold is not None:
                update_doc["confidence_threshold"] = update_data.confidence_threshold
            if update_data.position_size_multiplier is not None:
                update_doc["position_size_multiplier"] = update_data.position_size_multiplier
            if update_data.decision_speed is not None:
                update_doc["decision_speed"] = update_data.decision_speed
            if update_data.is_default is not None:
                if update_data.is_default:
                    # Cancel other defaults
                    await self.preferences_collection.update_many(
                        {"user_id": pref.user_id},
                        {"$set": {"is_default": False}}
                    )
                update_doc["is_default"] = update_data.is_default

            update_doc["updated_at"] = datetime.utcnow()

            await self.preferences_collection.update_one(
                {"_id": ObjectId(preference_id)},
                {"$set": update_doc}
            )

            return await self.get_preference(preference_id)

        except Exception as e:
            logger.error(f"❌ 更新偏好失败: {e}")
            return None


# === analysis_profile_service.py ===
"""
Industry/stock analysis and allocation services

Provide CRUD operations, dimension injection formatting functions, and AI generated industry configurations
"""

import json
import logging
from typing import Optional, Dict, Any, List
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
from app.core.database import get_mongo_db
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

# Collection name
INDUSTRY_COLLECTION = "industry_analysis_profiles"
STOCK_COLLECTION = "stock_analysis_profiles"


BUILTIN_SOURCE_DEFINITIONS = [
    {
        "key": "basic_info",
        "label": "Basic stock information/industry affiliation",
        "description": "From stock_basic_info Interface to unified stock information, supporting industry affiliation, company profile, partial valuation and basic fields.",
        "keywords": ["行业", "公司", "主营", "市值", "估值", "pe", "pb", "市盈率", "市净率", "股票基础", "基本信息"],
    },
    {
        "key": "financials",
        "label": "财务报表 / 基本面",
        "description": "Unified data capabilities from stock_financial_data, Tushare/AKShare/BaoStock, etc. can support financial indicators such as revenue, profit, cash flow, ROE, etc.",
        "keywords": [
            "营收", "收入", "净利润", "利润", "毛利率", "净利率", "现金流", "roe", "roa", "负债率", "周转", "应收", "存货",
            "资本开支", "capex", "分红", "eps", "每股收益", "经营活动现金流", "归母", "利润增长", "财务",
        ],
    },
    {
        "key": "market",
        "label": "Market/Volume and Price/Technical",
        "description": "Coming from market_quotes, historical market conditions and technical indicator capabilities, it can support price trends, trading volume, volatility, turnover rate and other volume and price indicators.",
        "keywords": [
            "股价", "价格", "成交量", "换手率", "波动率", "量价", "趋势", "技术", "均线", "macd", "rsi", "k线", "涨跌", "回撤",
        ],
    },
    {
        "key": "news",
        "label": "新闻 / 事件 / 政策",
        "description": "It comes from real-time news aggregation, announcements and public opinion capabilities, and is suitable for unstructured judgments such as policy, supervision, catalysis, and risk events.",
        "keywords": [
            "政策", "监管", "舆情", "事件", "催化", "新闻", "公告", "情绪", "风险事件", "市场预期", "行业景气", "竞争格局",
        ],
    },
]

OPERATIONAL_KEYWORDS = [
    "mau", "dau", "arpu", "付费率", "留存", "用户数", "活跃用户", "客单价", "渗透率", "复购", "订单量", "gmv", "take rate",
    "装机量", "装机", "销量", "出货量", "客流", "入住率", "产能利用率", "产销率", "客座率", "吞吐量", "日活", "月活",
]

QUALITATIVE_KEYWORDS = [
    "品牌力", "品牌势能", "生态壁垒", "用户粘性", "管理层执行力", "组织能力", "产品力", "渠道力", "技术领先性", "技术壁垒",
    "商业模式韧性", "战略定力", "护城河", "竞争优势", "定价权", "行业话语权",
]

STATUS_LABELS = {
    "directly_usable": "可直接使用",
    "partially_usable": "部分可用",
    "external_required": "需外部数据",
    "review_recommended": "建议复核",
}

ACTION_LABELS = {
    "keep": "直接保留",
    "keep_with_review": "保留但建议复核",
    "enhance_with_mcp_or_skill": "Combined with MCP/Skill reinforcement",
    "manual_import_or_external_source": "补充外部数据或手工导入",
    "remove_or_replace": "建议先删除或替换",
}


class AnalysisProfileService:
    """行业/个股分析配置服务"""

    # ==================== Industry configuration ====================

    async def get_industry_profiles(self, is_active: Optional[bool] = None) -> List[Dict]:
        """获取所有行业配置"""
        db = get_mongo_db()
        query = {}
        if is_active is not None:
            query["is_active"] = is_active
        cursor = db[INDUSTRY_COLLECTION].find(query).sort("industry", 1)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            doc["created_at"] = str(doc.get("created_at", ""))
            doc["updated_at"] = str(doc.get("updated_at", ""))
            results.append(doc)
        return results

    async def get_industry_profile(self, profile_id: str) -> Optional[Dict]:
        """根据 ID 获取行业配置"""
        db = get_mongo_db()
        doc = await db[INDUSTRY_COLLECTION].find_one({"_id": ObjectId(profile_id)})
        if doc:
            doc["id"] = str(doc.pop("_id"))
            doc["created_at"] = str(doc.get("created_at", ""))
            doc["updated_at"] = str(doc.get("updated_at", ""))
        return doc

    async def get_industry_profile_by_name(self, industry: str) -> Optional[Dict]:
        """根据行业名称获取配置"""
        db = get_mongo_db()
        doc = await db[INDUSTRY_COLLECTION].find_one({"industry": industry, "is_active": True})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def create_industry_profile(self, data: Dict) -> Dict:
        """创建行业配置"""
        db = get_mongo_db()
        now = now_tz()
        data["created_at"] = now
        data["updated_at"] = now
        data.setdefault("is_active", True)
        result = await db[INDUSTRY_COLLECTION].insert_one(data)
        data["id"] = str(result.inserted_id)
        logger.info(f"✅ 创建行业分析配置: {data.get('industry')}")
        return data

    async def update_industry_profile(self, profile_id: str, data: Dict) -> Optional[Dict]:
        """更新行业配置"""
        db = get_mongo_db()
        data["updated_at"] = now_tz()
        result = await db[INDUSTRY_COLLECTION].update_one(
            {"_id": ObjectId(profile_id)},
            {"$set": data}
        )
        if result.modified_count > 0:
            logger.info(f"✅ 更新行业分析配置: {profile_id}")
            return await self.get_industry_profile(profile_id)
        return None

    async def delete_industry_profile(self, profile_id: str) -> bool:
        """删除行业配置"""
        db = get_mongo_db()
        result = await db[INDUSTRY_COLLECTION].delete_one({"_id": ObjectId(profile_id)})
        return result.deleted_count > 0

    # ==================== Individual stock allocation ====================

    async def get_stock_profiles(self, industry: Optional[str] = None) -> List[Dict]:
        """获取个股配置列表"""
        db = get_mongo_db()
        query = {"is_active": True}
        if industry:
            query["industry"] = industry
        cursor = db[STOCK_COLLECTION].find(query).sort("stock_symbol", 1)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            doc["created_at"] = str(doc.get("created_at", ""))
            doc["updated_at"] = str(doc.get("updated_at", ""))
            results.append(doc)
        return results

    async def get_stock_profile_by_symbol(self, stock_symbol: str) -> Optional[Dict]:
        """根据股票代码获取配置"""
        db = get_mongo_db()
        doc = await db[STOCK_COLLECTION].find_one({"stock_symbol": stock_symbol, "is_active": True})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def create_stock_profile(self, data: Dict) -> Dict:
        """创建个股配置"""
        db = get_mongo_db()
        now = now_tz()
        data["created_at"] = now
        data["updated_at"] = now
        data.setdefault("is_active", True)
        result = await db[STOCK_COLLECTION].insert_one(data)
        data["id"] = str(result.inserted_id)
        logger.info(f"✅ 创建个股分析配置: {data.get('stock_symbol')}")
        return data

    async def update_stock_profile(self, profile_id: str, data: Dict) -> Optional[Dict]:
        """更新个股配置"""
        db = get_mongo_db()
        data["updated_at"] = now_tz()
        result = await db[STOCK_COLLECTION].update_one(
            {"_id": ObjectId(profile_id)},
            {"$set": data}
        )
        if result.modified_count > 0:
            return await self.get_stock_profile(profile_id)
        return None

    async def get_stock_profile(self, profile_id: str) -> Optional[Dict]:
        """根据 ID 获取个股配置"""
        db = get_mongo_db()
        doc = await db[STOCK_COLLECTION].find_one({"_id": ObjectId(profile_id)})
        if doc:
            doc["id"] = str(doc.pop("_id"))
            doc["created_at"] = str(doc.get("created_at", ""))
            doc["updated_at"] = str(doc.get("updated_at", ""))
        return doc

    async def delete_stock_profile(self, profile_id: str) -> bool:
        """删除个股配置"""
        db = get_mongo_db()
        result = await db[STOCK_COLLECTION].delete_one({"_id": ObjectId(profile_id)})
        return result.deleted_count > 0

    # ==================== Dimension injection (synchronous, for use by _prepare_system_variables) ====================

    @staticmethod
    def format_dimensions(dimensions: list) -> str:
        """Format analysis dimension list as prompt word injection text"""
        if not dimensions:
            return ""
        lines = []
        for d in dimensions:
            importance = d.get("importance", "high")
            name = d.get("name", "")
            desc = d.get("description", "")
            lines.append(f"- **{name}**（{importance}）: {desc}")
        return "\n".join(lines)

    @staticmethod
    def _contains_any(text: str, keywords: List[str]) -> bool:
        text_lower = (text or "").lower()
        return any(keyword.lower() in text_lower for keyword in keywords)

    @staticmethod
    def _source_ref(source_type: str, name: str, detail: str = "") -> Dict[str, str]:
        type_labels = {
            "builtin": "内置数据",
            "mcp": "MCP",
            "skill": "Skill",
            "manual_import": "手工导入",
        }
        return {
            "type": source_type,
            "type_label": type_labels.get(source_type, source_type),
            "name": name,
            "detail": detail,
        }

    async def _collect_capability_snapshot(self, db) -> Dict[str, Any]:
        builtin_sources = [
            {
                "key": item["key"],
                "label": item["label"],
                "description": item["description"],
            }
            for item in BUILTIN_SOURCE_DEFINITIONS
        ]

        enabled_mcp_servers: List[Dict[str, Any]] = []
        active_skills: List[Dict[str, Any]] = []

        try:
            cursor = db["mcp_server_configs"].find({"is_enabled": True})
            async for doc in cursor:
                tools = doc.get("discovered_tools", []) or []
                mappings = doc.get("data_mappings", []) or []
                summary_parts = [
                    doc.get("name", ""),
                    doc.get("description", ""),
                    doc.get("category", ""),
                ]
                summary_parts.extend(
                    [
                        tool.get("name", "") + " " + tool.get("description", "")
                        for tool in tools if isinstance(tool, dict)
                    ]
                )
                summary_parts.extend(
                    [
                        str(mapping.get("source_field", "")) + " " + str(mapping.get("target_field", ""))
                        for mapping in mappings if isinstance(mapping, dict)
                    ]
                )
                enabled_mcp_servers.append({
                    "server_id": doc.get("server_id", ""),
                    "name": doc.get("name", doc.get("server_id", "MCP")),
                    "description": doc.get("description", ""),
                    "category": doc.get("category", "function"),
                    "status": doc.get("status", "unknown"),
                    "tool_count": len(tools),
                    "mapping_count": len(mappings),
                    "summary_text": " ".join([part for part in summary_parts if part]),
                })
        except Exception as e:
            logger.warning(f"⚠️ Failed to collect MCP capability snapshot: {e}")

        try:
            cursor = db["external_skills"].find({"status": "active"})
            async for doc in cursor:
                metadata = doc.get("metadata", {}) or {}
                active_skills.append({
                    "tool_id": doc.get("tool_id", ""),
                    "name": doc.get("display_name", doc.get("tool_id", "Skill")),
                    "description": doc.get("description", ""),
                    "category": metadata.get("category") or doc.get("category", "external"),
                    "source": doc.get("source", "generated"),
                    "data_source": doc.get("data_source", ""),
                    "summary_text": " ".join(
                        [
                            doc.get("display_name", ""),
                            doc.get("description", ""),
                            str(metadata.get("category", "")),
                            str(doc.get("data_source", "")),
                        ]
                    ),
                })
        except Exception as e:
            logger.warning(f"⚠️ Failed to collect external_skills: {e}")

        try:
            cursor = db["skills"].find({"enabled": True})
            async for doc in cursor:
                active_skills.append({
                    "tool_id": doc.get("name", ""),
                    "name": doc.get("name", "Skill"),
                    "description": doc.get("description", ""),
                    "category": doc.get("category", "utility"),
                    "source": "legacy_skill",
                    "data_source": "",
                    "summary_text": " ".join(
                        [
                            str(doc.get("name", "")),
                            str(doc.get("description", "")),
                            str(doc.get("category", "")),
                        ]
                    ),
                })
        except Exception as e:
            logger.warning(f"⚠️ Failed to collect skills: {e}")

        return {
            "builtin_sources": builtin_sources,
            "enabled_mcp_servers": enabled_mcp_servers,
            "active_skills": active_skills,
            "manual_import": {
                "available": True,
                "label": "手工导入 / 本地数据",
                "description": "The current system supports supplementing indicators through batch import API or local data. The imported data source is usually marked as local / local_file.",
            },
            "counts": {
                "builtin_sources": len(builtin_sources),
                "enabled_mcp_servers": len(enabled_mcp_servers),
                "active_skills": len(active_skills),
            },
            "notes": [
                "The built-in data is more suitable for financial, market, news and announcement indicators.",
                "MCP/Skill Extended data coverage is possible, but whether it is actually available depends on the currently enabled items and field mappings.",
                "If the corresponding data cannot be found in the system, it is recommended that the user supplement external data sources or manually import them before retaining the dimension/indicator.",
            ],
        }

    def _match_mcp_sources(self, text: str, capability_snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
        matches = []
        text_lower = (text or "").lower()
        for item in capability_snapshot.get("enabled_mcp_servers", []):
            summary_text = item.get("summary_text", "").lower()
            if summary_text and any(token in summary_text for token in text_lower.split() if token):
                matches.append(self._source_ref("mcp", item.get("name", "MCP"), item.get("description", "")))
        return matches[:3]

    def _match_skill_sources(self, text: str, capability_snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
        matches = []
        text_lower = (text or "").lower()
        for item in capability_snapshot.get("active_skills", []):
            summary_text = item.get("summary_text", "").lower()
            if summary_text and any(token in summary_text for token in text_lower.split() if token):
                matches.append(self._source_ref("skill", item.get("name", "Skill"), item.get("description", "")))
        return matches[:3]

    def _evaluate_item_coverage(
        self,
        name: str,
        description: str,
        data_source: str,
        capability_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        text = " ".join([name or "", description or "", data_source or ""])
        matched_sources: List[Dict[str, str]] = []
        missing_requirements: List[str] = []

        has_financial = self._contains_any(text, BUILTIN_SOURCE_DEFINITIONS[1]["keywords"])
        has_market = self._contains_any(text, BUILTIN_SOURCE_DEFINITIONS[2]["keywords"])
        has_basic = self._contains_any(text, BUILTIN_SOURCE_DEFINITIONS[0]["keywords"])
        has_news = self._contains_any(text, BUILTIN_SOURCE_DEFINITIONS[3]["keywords"])
        has_operational = self._contains_any(text, OPERATIONAL_KEYWORDS)
        has_qualitative = self._contains_any(text, QUALITATIVE_KEYWORDS)

        if has_basic:
            matched_sources.append(self._source_ref("builtin", BUILTIN_SOURCE_DEFINITIONS[0]["label"], BUILTIN_SOURCE_DEFINITIONS[0]["description"]))
        if has_financial:
            matched_sources.append(self._source_ref("builtin", BUILTIN_SOURCE_DEFINITIONS[1]["label"], BUILTIN_SOURCE_DEFINITIONS[1]["description"]))
        if has_market:
            matched_sources.append(self._source_ref("builtin", BUILTIN_SOURCE_DEFINITIONS[2]["label"], BUILTIN_SOURCE_DEFINITIONS[2]["description"]))
        if has_news:
            matched_sources.append(self._source_ref("builtin", BUILTIN_SOURCE_DEFINITIONS[3]["label"], BUILTIN_SOURCE_DEFINITIONS[3]["description"]))

        mcp_matches = self._match_mcp_sources(text, capability_snapshot)
        skill_matches = self._match_skill_sources(text, capability_snapshot)
        matched_sources.extend(mcp_matches)
        matched_sources.extend(skill_matches)

        has_any_mcp = capability_snapshot.get("counts", {}).get("enabled_mcp_servers", 0) > 0
        has_any_skill = capability_snapshot.get("counts", {}).get("active_skills", 0) > 0

        if has_financial or has_market or has_basic:
            status = "directly_usable"
            action = "keep"
            user_note = "This item mainly relies on the system s current structured data capabilities. After saving, you can directly enter the analysis prompt word."
        elif has_news:
            status = "partially_usable"
            action = "keep_with_review"
            user_note = "The system can assist in judgment through news/announcement data, but most of it is unstructured information. It is recommended to manually review the analysis conclusion."
        elif has_operational:
            matched_sources.append(self._source_ref("manual_import", "手工导入 / 外部数据", capability_snapshot["manual_import"]["description"]))
            if mcp_matches or skill_matches:
                status = "partially_usable"
                action = "enhance_with_mcp_or_skill"
                user_note = "This item is more like an external indicator of operations/industry. Some MCP/Skills already in the system may be enhanced, but it is still recommended to confirm field mapping and availability."
            else:
                status = "external_required"
                action = "manual_import_or_external_source"
                user_note = "The current built-in data usually does not directly cover such operational indicators. It is recommended to access external data sources, enable matching MCP/Skill, or manually import and retain them."
                if has_any_mcp or has_any_skill:
                    missing_requirements.append("Although MCP/Skill is currently enabled, no ability description directly matching this item has been found, and manual confirmation is required.")
                else:
                    missing_requirements.append("Currently, no MCP/Skill has been found that can directly support this item, and additional external data is required.")
        elif has_qualitative:
            status = "review_recommended"
            action = "remove_or_replace"
            user_note = "This item is qualitative, abstract or difficult to verify in a structured way. It is recommended that users confirm whether there is a stable data source; if not, delete it or change it to a verifiable indicator."
            missing_requirements.append("It is recommended to replace it with verifiable financial, market, news or importable indicators.")
        else:
            matched_sources.append(self._source_ref("manual_import", "手工导入 / 外部数据", capability_snapshot["manual_import"]["description"]))
            status = "review_recommended"
            action = "keep_with_review"
            user_note = "The system has not yet identified a clear data support method. It is recommended that the user confirm the source before saving. If the data cannot be confirmed, it is recommended to delete it."
            if not matched_sources:
                missing_requirements.append("No clear data source was identified.")

        return {
            "name": name,
            "description": description,
            "requested_data_source": data_source,
            "coverage_status": status,
            "coverage_label": STATUS_LABELS[status],
            "recommended_action": action,
            "recommended_action_label": ACTION_LABELS[action],
            "matched_sources": matched_sources[:4],
            "missing_requirements": missing_requirements,
            "user_note": user_note,
        }

    @staticmethod
    def _count_status(items: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {key: 0 for key in STATUS_LABELS.keys()}
        for item in items:
            status = item.get("coverage_status")
            if status in counts:
                counts[status] += 1
        return counts

    def _build_coverage_summary(
        self,
        dimension_assessments: List[Dict[str, Any]],
        metric_assessments: List[Dict[str, Any]],
        capability_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        dimension_counts = self._count_status(dimension_assessments)
        metric_counts = self._count_status(metric_assessments)
        total_external = dimension_counts["external_required"] + metric_counts["external_required"]
        total_review = dimension_counts["review_recommended"] + metric_counts["review_recommended"]

        if total_external == 0 and total_review <= 1:
            overall_status = "ready"
            overall_label = "大部分内容已具备落地基础"
        elif total_external <= 2 and total_review <= 3:
            overall_status = "review_needed"
            overall_label = "建议人工复核后保存"
        else:
            overall_status = "prune_needed"
            overall_label = "建议先裁剪再保存"

        recommendations = []
        if dimension_counts["directly_usable"] or metric_counts["directly_usable"]:
            recommendations.append("Priority reservation Can be used directly dimensions and indicators, which are most easily supported stably by the current system.")
        if total_external:
            recommendations.append(f"当前有 {total_external} 项被识别为“需外部数据”，建议在保存前确认 MCP / Skill / 手工导入方案。")
        if total_review:
            recommendations.append(f"当前有 {total_review} 项为“建议复核”，若无法确认数据来源，建议先删除或改写为可验证指标。")
        if capability_snapshot.get("counts", {}).get("enabled_mcp_servers", 0) == 0:
            recommendations.append("There is currently no enabled MCP server. If you need more industry operations or alternative data, you may consider connecting to MCP first.")

        return {
            "overall_status": overall_status,
            "overall_label": overall_label,
            "dimension_counts": dimension_counts,
            "metric_counts": metric_counts,
            "recommendations": recommendations,
        }

    @staticmethod
    def get_industry_dimensions_sync(industry: str) -> Dict[str, str]:
        """
        Synchronously obtain industry analysis dimensions (for _prepare_system_variables)

        Returns:
            contains industry_dimensions, industry_focus, industry_key_metrics dictionary
        """
        result = {}
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()

            # 1. exact match
            profile = db[INDUSTRY_COLLECTION].find_one(
                {"industry": industry, "is_active": True}
            )

            # 2. Fuzzy bottom line: Contains matches (such as in stock_basic_info"bank" match configuration"bank") 
            if not profile:
                import re
                escaped = re.escape(industry)
                profile = db[INDUSTRY_COLLECTION].find_one(
                    {"industry": {"$regex": escaped, "$options": "i"}, "is_active": True}
                )
                if not profile:
                    # Reverse: The industry name in the configuration is included in the query industry name
                    all_profiles = list(db[INDUSTRY_COLLECTION].find({"is_active": True}))
                    for p in all_profiles:
                        if p.get("industry") and p["industry"] in industry:
                            profile = p
                            break

            if profile:
                dimensions = profile.get("analysis_dimensions", [])
                result["industry_dimensions"] = AnalysisProfileService.format_dimensions(dimensions)
                result["industry_focus"] = profile.get("analysis_focus", "")
                result["industry_key_metrics"] = ", ".join(profile.get("key_metrics", []))
                result["industry_comparable_companies"] = ", ".join(profile.get("comparable_companies", []))
                logger.info(f"🏭 [行业维度注入] {industry}: {len(dimensions)} 个维度")
        except Exception as e:
            logger.warning(f"⚠️ Failed to obtain industry analysis dimensions: {e}")
        return result

    @staticmethod
    def build_industry_prompt_block(industry: str) -> str:
        """
        Synchronously obtain industry analysis configuration, formatted as a text block that can be appended directly to Prompt.

        Returning an empty string indicates that the industry is not configured or the query failed.
        """
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            profile = db[INDUSTRY_COLLECTION].find_one(
                {"industry": industry, "is_active": True}
            )
            if not profile:
                return ""

            dimensions = profile.get("analysis_dimensions", [])
            if not dimensions:
                return ""

            blocks = ["\n\n## 行业分析重点\n"]

            # Analysis Dimensions
            blocks.append("### 核心分析维度\n")
            for d in dimensions:
                imp = d.get("importance", "high")
                imp_label = {"critical": "★", "high": "▲", "medium": "●", "low": "○"}.get(imp, "")
                blocks.append(f"- **{d.get('name', '')}** {imp_label}: {d.get('description', '')}")

            # Analysis focus
            focus = profile.get("analysis_focus", "")
            if focus:
                blocks.append(f"\n### 行业分析总览\n{focus}")

            # key indicators
            key_metrics = profile.get("key_metrics", [])
            if key_metrics:
                blocks.append(f"\n### 关键跟踪指标\n{', '.join(key_metrics)}")

            result = "\n".join(blocks)
            logger.info(f"🏭 [行业Prompt注入] {industry}: {len(dimensions)} 维度, 长度={len(result)}")
            return result
        except Exception as e:
            logger.warning(f"⚠️ Building industry prompt block failed: {e}")
            return ""

    @staticmethod
    def get_stock_dimensions_sync(stock_code: str) -> Dict[str, str]:
        """
        Synchronously obtain individual stock analysis dimensions (for _prepare_system_variables)

        Returns:
            contains stock_dimensions, stock_special_notes dictionary
        """
        result = {}
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            profile = db[STOCK_COLLECTION].find_one(
                {"stock_symbol": stock_code, "is_active": True}
            )
            if profile:
                dimensions = profile.get("analysis_dimensions", [])
                result["stock_dimensions"] = AnalysisProfileService.format_dimensions(dimensions)
                result["stock_special_notes"] = profile.get("special_notes", "")
                logger.info(f"📊 [个股维度注入] {stock_code}: {len(dimensions)} 个维度")
        except Exception as e:
            logger.warning(f"⚠️ Failed to obtain individual stock analysis dimensions: {e}")
        return result

    # ==================== AI Generate industry configuration ====================

    async def generate_industry_profile_with_ai(
        self,
        industry: str,
        user_request: str = "",
        existing_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Automatically generate industry analysis configurations using LLM

        Args:
            industry: Industry name, such as "bank", "New energy vehicles", "medical device"
            user_request: Users supplementary requirements or revised instructions for this round
            existing_profile: Current draft, used for multiple rounds of revisions

        Returns:
            Generated industry configuration dictionary (not saved to the database, user confirmation is required before saving)
        """
        from app.services.intelligent_assistant_service import get_reasoning_llm_config
        from core.llm import UnifiedLLMClient, Message

        db = get_mongo_db()
        config = await get_reasoning_llm_config(db)
        if not config:
            raise RuntimeError("LLM is not configured, please configure the large model in the system settings first")

        client = UnifiedLLMClient.from_config(config)

        prompt_parts = [
            f'You are a senior A-share industry research expert. please for"{industry}"The industry outputs a structured analysis dimension configuration.',
            "",
            "Requirements:",
            "1. Output the 5-8 most critical analysis_dimensions, each dimension containing:name / description / importance / data_source",
            "2. Output a section of analysis_focus (2-3 sentences)",
            "3. Output 5-8 key_metrics (names of key financial/business metrics)",
            "4. Output 3-5 comparable_companies (A-share comparable companies)",
            "5. If existing_profile exists, the task of this round is revised draft , Give priority to retaining reasonable items, and only add, delete or modify them according to user requirements, and do not make irrelevant items.",
            "6. Do not add back items that the user explicitly requests to delete.",
            "7. Please keep the output as pure JSON and do not include markdown code blocks or any additional instructions",
            "",
        ]

        if existing_profile:
            prompt_parts.extend([
                "current draft(existing_profile): ",
                json.dumps(existing_profile, ensure_ascii=False, indent=2),
                "",
            ])

        if user_request and user_request.strip():
            prompt_parts.extend([
                "User requirements for this round:",
                user_request.strip(),
                "",
            ])
        else:
            prompt_parts.extend([
                "User requirements for this round:",
                "Please provide a first draft that is suitable as an industry analysis template.",
                "",
            ])

        prompt_parts.extend([
            "Please directly output the following JSON structure:",
            "{",
            f'  "industry": "{industry}",',
            f'  "display_name": "{industry}行业",',
            '  "analysis_dimensions": [...],',
            '  "analysis_focus": "...",',
            '  "key_metrics": [...],',
            '  "comparable_companies": [...]',
            "}",
        ])

        prompt = "\n".join(prompt_parts)

        messages = [
            Message(role="system", content="You are a senior A-share industry research analyst, specializing in structured financial analysis. Please output only plain JSON, without any other text."),
            Message(role="user", content=prompt),
        ]

        response = await client.achat(messages)
        content = response.content.strip()

        # Clean up possible markdown code block tags
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            profile_data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"❌ AI 生成的行业配置 JSON 解析失败: {e}\n原文: {content[:500]}")
            raise ValueError(f"AI The generated content cannot be parsed as valid JSON: {e}")

        # Make sure required fields exist
        profile_data["industry"] = industry
        profile_data.setdefault("display_name", f"{industry}行业")
        profile_data.setdefault("is_active", True)
        profile_data.setdefault("source", "ai_generated")

        capability_snapshot = await self._collect_capability_snapshot(db)
        dimension_assessments = [
            self._evaluate_item_coverage(
                name=dimension.get("name", ""),
                description=dimension.get("description", ""),
                data_source=dimension.get("data_source", ""),
                capability_snapshot=capability_snapshot,
            )
            for dimension in profile_data.get("analysis_dimensions", [])
            if isinstance(dimension, dict)
        ]
        metric_assessments = [
            self._evaluate_item_coverage(
                name=metric,
                description="关键指标",
                data_source="metric",
                capability_snapshot=capability_snapshot,
            )
            for metric in profile_data.get("key_metrics", [])
            if isinstance(metric, str) and metric.strip()
        ]
        coverage_summary = self._build_coverage_summary(
            dimension_assessments=dimension_assessments,
            metric_assessments=metric_assessments,
            capability_snapshot=capability_snapshot,
        )

        preview = {
            "profile": profile_data,
            "coverage_summary": coverage_summary,
            "capability_snapshot": capability_snapshot,
            "dimension_assessments": dimension_assessments,
            "metric_assessments": metric_assessments,
            "next_step_guidance": [
                "Confirm first Can be used directly and Partially available of items fit your analytical framework.",
                "Yes external data required item, decide whether to access MCP/Skill, import manually, or delete it temporarily.",
                "Yes Recommend review If the data source cannot be explained, it is recommended to delete it first and then save it.",
            ],
        }

        logger.info(
            f"🤖 [AI生成] 行业配置: {industry}, 维度数: {len(profile_data.get('analysis_dimensions', []))}, "
            f"Requires external data items: {coverage_summary['dimension_counts']['external_required'] + coverage_summary['metric_counts']['external_required']}"
        )
        return preview


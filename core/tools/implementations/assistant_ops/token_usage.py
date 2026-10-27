"""Use the Q&A robot tool: Query Token usage statistics.

Allows using Q&A Assistant to"see"The user s current Token usage and quota usage,
This allows JD Cloud users to understand the rate of quota consumption in real time and avoid exceeding the quota.

Data source:
- Direct reuse UsageStatisticsService.get_usage_statistics() Get detailed statistics
- Read the quota upper limit from the environment variable JDYUN_TOKEN_QUOTA (valid only for JD Cloud version)
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _format_tokens(value: Optional[int]) -> str:
    """Format the token number as a human-readable string."""
    if value is None:
        return "未知"
    try:
        v = int(value)
        if v >= 1_000_000:
            return f"{v / 1_000_000:.2f} M"
        if v >= 1_000:
            return f"{v / 1_000:.2f} K"
        return f"{v}"
    except Exception:
        return str(value)


def _resolve_token_quota() -> int:
    """Read the Token quota limit (valid only for JD Cloud version)."""
    if os.getenv("JDYUN_MODE", "").strip().lower() in ("true", "1", "yes"):
        return int(os.getenv("JDYUN_TOKEN_QUOTA", "0") or "0")
    return 0


@tool
@register_tool(
    tool_id="get_token_usage",
    name="Query Token usage statistics",
    description="Query token usage statistics: number of used tokens today/this week/month, quota limit, remaining quota, consumption grouped by model, consumption grouped by task. When the user asks'How much did you use today? token''How much quota is left?''Which model consumes the most''Token Usage trends'when used.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "token_usage", "quota", "cost", "llm_usage", "api_usage"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=[
        "今天用了多少 token",
        "还剩多少配额",
        "Token 用量",
        "本周 Token 消耗",
        "哪个模型消耗最多",
        "Token 用量趋势",
        "配额什么时候重置",
        "还能用多少次分析",
    ],
    when_to_use="Used when users ask about token usage, quota usage, model consumption, and API call costs. Supports days parameter to specify statistical period (default 7 days).",
    returns="Returns a Token usage summary in text format, including used/quota/remaining/percentage/consumption grouped by model/trend by date.",
)
async def get_token_usage(
    days: Annotated[
        Optional[int],
        "Number of days in the statistical period (default 7 days, optional 1/7/30,1=Today,7=This week,30=this month). JD Cloud version recommends passing 1 or 7."
    ] = 7,
) -> str:
    """Query Token usage statistics."""
    from app.core.database import get_mongo_db
    from app.services.usage_statistics_service import usage_statistics_service

    # Trigger user context (although the service side presses global statistics, maintain consistency)
    require_current_user_id()

    # Standardize days
    try:
        days_int = int(days) if days else 7
    except (TypeError, ValueError):
        days_int = 7
    if days_int < 1:
        days_int = 1
    if days_int > 365:
        days_int = 365

    db = get_mongo_db()
    is_jdyun = os.getenv("JDYUN_MODE", "").strip().lower() in ("true", "1", "yes")

    # Reuse existing services to get detailed statistics
    try:
        stats = await usage_statistics_service.get_usage_statistics(days=days_int)
    except Exception as exc:
        logger.warning("[get_token_usage] Failed to query statistics: %s", exc)
        return (
            "📊 Token Usage statistics\n"
            "\n"
            f"❌ Query failed: {exc}\n"
            "\n"
            "Please try again later, or check the backend logs."
        )

    used_tokens = (stats.total_input_tokens or 0) + (stats.total_output_tokens or 0)
    input_tokens = stats.total_input_tokens or 0
    output_tokens = stats.total_output_tokens or 0
    total_requests = stats.total_requests or 0
    quota_tokens = _resolve_token_quota()
    percentage = round((used_tokens / quota_tokens) * 100, 2) if quota_tokens > 0 else 0.0
    remaining_tokens = max(0, quota_tokens - used_tokens) if quota_tokens > 0 else 0

    # Quota reset time
    reset_at = (datetime.utcnow() + timedelta(days=days_int)).strftime("%Y-%m-%d %H:%M UTC")

    # Group consumption by model (stats.by_model is dict: {model_name: {requests, input_tokens, output_tokens, cost, ...}}) 
    by_model_dict = getattr(stats, "by_model", None) or {}
    # Group consumption by provider (stats.by_provider is a dict)
    by_provider_dict = getattr(stats, "by_provider", None) or {}
    # Trend by date (stats.by_date is dict: {date_str: {...}}) 
    by_date_dict = getattr(stats, "by_date", None) or {}

    lines = ["📊 Token 用量统计"]
    period_label = {1: "今日", 7: "本周", 30: "本月"}.get(days_int, f"近 {days_int} 天")
    lines.append(f"- 统计周期: {period_label}（{days_int} 天）")
    lines.append("")

    # 1) Overview
    lines.append("【1】用量总览")
    lines.append(f"- 已用 Token: {_format_tokens(used_tokens)}（输入 {_format_tokens(input_tokens)} + 输出 {_format_tokens(output_tokens)}）")
    lines.append(f"- 总请求数: {total_requests}")

    if quota_tokens > 0:
        lines.append(f"- 配额上限: {_format_tokens(quota_tokens)}")
        lines.append(f"- 剩余配额: {_format_tokens(remaining_tokens)}")
        lines.append(f"- 使用率: {percentage}%")
        lines.append(f"- 配额重置时间: {reset_at}")

        # Quota warning
        if percentage >= 90:
            lines.append("- 🔴 The quota is about to be exhausted. It is recommended to reduce the analysis tasks or wait for reset.")
        elif percentage >= 70:
            lines.append("- 🟡 The quota is consumed quickly, so it is recommended to pay attention to the usage.")
        elif percentage >= 50:
            lines.append("- 🟢 More than half of the quota is used, which is normal.")
        else:
            lines.append("- 🟢 配额充足")
    else:
        lines.append("- Quota cap: Unlimited (standard version default)")

    # 2) Consumption grouped by model
    lines.append("")
    lines.append("【2】按模型分组消耗")
    if by_model_dict:
        # Sort by total_tokens in descending order, take TOP 5
        sorted_models = sorted(
            by_model_dict.items(),
            key=lambda kv: (kv[1].get("input_tokens", 0) + kv[1].get("output_tokens", 0)),
            reverse=True,
        )
        for model_name, m_data in sorted_models[:5]:
            m_input = m_data.get("input_tokens", 0)
            m_output = m_data.get("output_tokens", 0)
            m_tokens = m_input + m_output
            m_requests = m_data.get("requests", 0)
            lines.append(f"  • {model_name}: {_format_tokens(m_tokens)} ({m_requests} 次)")
    else:
        lines.append("  - 无数据")

    # 3) Consumption grouped by supplier
    lines.append("")
    lines.append("【3】按供应商分组消耗")
    if by_provider_dict:
        sorted_providers = sorted(
            by_provider_dict.items(),
            key=lambda kv: (kv[1].get("input_tokens", 0) + kv[1].get("output_tokens", 0)),
            reverse=True,
        )
        for provider_name, p_data in sorted_providers[:3]:
            p_tokens = p_data.get("input_tokens", 0) + p_data.get("output_tokens", 0)
            lines.append(f"  • {provider_name}: {_format_tokens(p_tokens)}")
    else:
        lines.append("  - 无数据")

    # 4) Trend by date
    lines.append("")
    lines.append("【4】每日用量趋势")
    if by_date_dict:
        # Sort by date in ascending order, take the last 7 days
        sorted_dates = sorted(by_date_dict.items(), key=lambda kv: kv[0], reverse=False)
        recent_dates = sorted_dates[-7:] if len(sorted_dates) > 7 else sorted_dates
        for date_str, d_data in recent_dates:
            d_tokens = d_data.get("input_tokens", 0) + d_data.get("output_tokens", 0)
            lines.append(f"  • {date_str}: {_format_tokens(d_tokens)}")
    else:
        lines.append("  - 无数据")

    # 5) Comprehensive judgment
    lines.append("")
    lines.append("💡 综合判断")
    if total_requests == 0:
        lines.append(f"- 近 {days_int} 天没有 LLM 调用记录，可能是分析任务未运行或统计未生效")
    else:
        avg_per_request = used_tokens // max(total_requests, 1)
        lines.append(f"- 平均每次请求消耗 {_format_tokens(avg_per_request)} Token")

        if is_jdyun:
            # JD Cloud Edition: Estimate how many more analyzes can be run
            avg_analysis_cost = 50_000  # A single single stock analysis is about 50,000 token
            if quota_tokens > 0:
                remaining_analyses = remaining_tokens // avg_analysis_cost
                lines.append(f"- 按单次分析约 5 万 Token 估算，剩余可执行约 {remaining_analyses} 次单股分析")
            else:
                lines.append("- JD Cloud version has no quota limit configured, please pay attention to the console usage alarm.")

        # Trend observation by date
        if by_date_dict:
            sorted_dates = sorted(by_date_dict.items(), key=lambda kv: kv[0], reverse=False)
            if len(sorted_dates) >= 2:
                last_date, last_data = sorted_dates[-1]
                prev_date, prev_data = sorted_dates[-2]
                last_tokens = last_data.get("input_tokens", 0) + last_data.get("output_tokens", 0)
                prev_tokens = prev_data.get("input_tokens", 0) + prev_data.get("output_tokens", 0)
                if prev_tokens > 0:
                    change_pct = ((last_tokens - prev_tokens) / prev_tokens) * 100
                    trend = "上升" if change_pct > 0 else "下降" if change_pct < 0 else "持平"
                    lines.append(f"- 最近一天用量 {_format_tokens(last_tokens)}，较前一日{trend} {abs(change_pct):.1f}%")

    if is_jdyun:
        lines.append("")
        lines.append("📌 Note: JD Cloud version only supports GLM series models, forcing single concurrency, and a single single stock analysis consumes about 50,000-100,000 Token")

    return "\n".join(lines)

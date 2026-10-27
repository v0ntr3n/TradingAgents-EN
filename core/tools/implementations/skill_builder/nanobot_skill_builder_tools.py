"""Nanobot Friendly reusable skill generation tool."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from langchain_core.tools import tool

from app.core.database import get_mongo_db
from app.services.skill_generation_service import SkillGenerationService
from core.tools.base import register_tool
from core.tools.context import get_current_user_id

logger = logging.getLogger(__name__)


def _json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _parse_optional_json_dict(raw: str, field_name: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{field_name} 必须是 JSON 对象")
    return data


def _get_skill_generation_service() -> SkillGenerationService:
    return SkillGenerationService(db=get_mongo_db())


def _recommend_start_next_step(start_result: dict[str, Any]) -> str:
    clarity = str(start_result.get("clarity_level") or "").strip().lower()
    return "preview_external_skill_spec" if clarity == "high" else "respond_to_external_skill_generation_session"


def _recommend_follow_up_next_step(result: dict[str, Any]) -> str:
    if result.get("is_final_round"):
        return "preview_external_skill_spec"
    return "respond_to_external_skill_generation_session"


def _summarize_session_doc(session_doc: dict[str, Any]) -> dict[str, Any]:
    pipeline_result = session_doc.get("pipeline_result") or {}
    summary: dict[str, Any] = {
        "session_id": session_doc.get("session_id"),
        "user_id": session_doc.get("user_id"),
        "status": session_doc.get("status"),
        "current_round": session_doc.get("current_round"),
        "spec_confirmed": session_doc.get("spec_confirmed"),
        "updated_at": session_doc.get("updated_at"),
        "pipeline_stage": session_doc.get("pipeline_stage"),
        "pipeline_message": session_doc.get("pipeline_message"),
        "pipeline_iteration": session_doc.get("pipeline_iteration"),
        "pipeline_progress": session_doc.get("pipeline_progress"),
        "recommendations": session_doc.get("recommendations"),
        "spec": session_doc.get("spec"),
        "fact_report": session_doc.get("fact_report"),
    }
    if pipeline_result:
        summary["pipeline_result"] = {
            "success": pipeline_result.get("success"),
            "error": pipeline_result.get("error"),
            "total_rounds": pipeline_result.get("total_rounds"),
            "total_time": pipeline_result.get("total_time"),
            "final_score": pipeline_result.get("final_score"),
            "final_code_present": bool(pipeline_result.get("final_code")),
        }
    return summary


@tool
@register_tool(
    tool_id="start_external_skill_generation_session",
    name="Start an External Skill build session",
    description="When Nanobot determines that the current gap is a reusable capability, start the real SkillGenerationService session instead of stopping at the temp script.",
    category="external",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    when_to_use="Used when existing capabilities are missing, but the target is obviously a reusable, parameterizable capability, such as DuPont analysis, valuation sub-module, and financial ratio analysis.",
    when_not_to_use="Do not use it when the task is only one-time debugging, temporary detection, or short-term data verification; in that case, the temp script should be used first.",
    returns="Returns a JSON string, including session_id, AI first round demand communication message, clarity judgment, and recommended next steps.",
    example='start_external_skill_generation_session(description="Create a reusable A-share DuPont analysis skill, input symbol, and output structured three-factor decomposition and trend summary")',
    related_tools=["respond_to_external_skill_generation_session", "preview_external_skill_spec", "generate_confirmed_external_skill", "inspect_external_skill_generation_session"],
    data_source_handling="local_only",
)
async def start_external_skill_generation_session(
    description: Annotated[str, "Skill Natural language requirement description, it must be clear that this is a reusable capability rather than a one-time script"],
    handoff_context_json: Annotated[str, "Optional JSON object to supplement the upstream handover context, such as the original goal, retained capability boundaries, and prohibitive narrowing constraints"] = "",
) -> str:
    """Start an external skill to generate a session."""
    try:
        clean_description = str(description or "").strip()
        if not clean_description:
            return _json_response({"status": "error", "message": "description cannot be empty"})

        handoff_context = _parse_optional_json_dict(handoff_context_json, "handoff_context_json")
        service = _get_skill_generation_service()
        user_id = (get_current_user_id() or "").strip()
        start_result = await service.start_session(
            description=clean_description,
            user_id=user_id,
            handoff_context=handoff_context,
        )
        return _json_response({
            "status": "ok",
            "session_id": start_result.get("session_id"),
            "user_id": user_id or None,
            "description": clean_description,
            "handoff_context": handoff_context,
            "start_result": start_result,
            "recommended_next_step": _recommend_start_next_step(start_result),
            "available_next_steps": [
                "respond_to_external_skill_generation_session",
                "preview_external_skill_spec",
            ],
        })
    except Exception as exc:
        logger.error("Failed to start external skill to generate session: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to start external skill to generate session: {exc}"})


@tool
@register_tool(
    tool_id="respond_to_external_skill_generation_session",
    name="Reply to External Skill Generate Conversation",
    description="Continue to answer Skill requirement clarification questions and let the SkillGenerationService converge the natural language requirements into a stable SkillSpec.",
    category="external",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    when_to_use="Used when a skill generation session already exists and the AI is still asking about responsibility boundaries, input and output, data sources, and non-targets.",
    when_not_to_use="You don t have to call it again when the session is clear enough and you re ready to preview the spec or confirm the build.",
    returns="Returns a JSON string containing the AI s new round of responses, the current round, and suggested next steps.",
    example="respond_to_external_skill_generation_session(session_id='abc123', user_message='Only symbols are input, structured JSON is output, and no trading advice is given.')",
    related_tools=["start_external_skill_generation_session", "preview_external_skill_spec"],
    data_source_handling="local_only",
)
async def respond_to_external_skill_generation_session(
    session_id: Annotated[str, "There is already a Skill created session ID"],
    user_message: Annotated[str, "Responses to Skill Requirements Clarification Questions"] = "确认按可复用能力来设计",
) -> str:
    """Continue to communicate external skill needs."""
    try:
        clean_session_id = str(session_id or "").strip()
        clean_user_message = str(user_message or "").strip()
        if not clean_session_id:
            return _json_response({"status": "error", "message": "session_id cannot be empty"})
        if not clean_user_message:
            return _json_response({"status": "error", "message": "user_message cannot be empty"})

        service = _get_skill_generation_service()
        result = await service.respond_to_session(clean_session_id, clean_user_message)
        return _json_response({
            "status": "ok",
            "session_id": clean_session_id,
            "response": result,
            "recommended_next_step": _recommend_follow_up_next_step(result),
            "available_next_steps": [
                "respond_to_external_skill_generation_session",
                "preview_external_skill_spec",
            ],
        })
    except Exception as exc:
        logger.error("Reply external skill failed to generate session: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Reply external skill failed to generate session: {exc}"})


@tool
@register_tool(
    tool_id="preview_external_skill_spec",
    name="Preview External Skill specifications",
    description="Generate SkillSpec preview and recon reports based on the current skill session to confirm if this is the correct reusable capability shape.",
    category="external",
    is_online=True,
    auto_register=True,
    timeout_tier="heavy",
    when_to_use="Use it when the requirements are basically clear and you need to look at the structured SkillSpec, parameters, output contracts and reconnaissance conclusions before deciding whether to actually generate the skill.",
    when_not_to_use="When the requirements are still clearly ambiguous, continue with respond_to_external_skill_generation_session in preference.",
    returns="Returns a JSON string containing the spec preview, recon fact_report, recommended build context, and recommended next steps.",
    example="preview_external_skill_spec(session_id='abc123')",
    related_tools=["respond_to_external_skill_generation_session", "generate_confirmed_external_skill"],
    data_source_handling="local_only",
)
async def preview_external_skill_spec(
    session_id: Annotated[str, "There is already a Skill created session ID"],
    user_message: Annotated[str, "Optional confirmation, default is confirmation"] = "确认",
) -> str:
    """Preview the SkillSpec of the external skill."""
    try:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return _json_response({"status": "error", "message": "session_id cannot be empty"})

        service = _get_skill_generation_service()
        preview = await service.preview_spec(clean_session_id, str(user_message or "确认").strip() or "确认")
        if not preview:
            return _json_response({"status": "error", "message": "No usable SkillSpec preview generated"})
        return _json_response({
            "status": "ok",
            "session_id": clean_session_id,
            "preview": preview,
            "recommended_next_step": "generate_confirmed_external_skill",
            "available_next_steps": [
                "respond_to_external_skill_generation_session",
                "generate_confirmed_external_skill",
            ],
        })
    except Exception as exc:
        logger.error("Failed to preview external skill specifications: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to preview external skill specifications: {exc}"})


@tool
@register_tool(
    tool_id="generate_confirmed_external_skill",
    name="Generate after confirmation External Skill",
    description="After the user confirms that this is indeed a reusable capability, call the real SkillGenerationService to enter the external skill generation pipeline.",
    category="external",
    is_online=True,
    auto_register=True,
    timeout_tier="heavy",
    when_to_use="Used when the spec preview has been confirmed and the target is not a one-time temp script but a reusable skill.",
    when_not_to_use="Do not call without confirmation; it does not apply to temporary detection scripts.",
    returns="Returns a JSON string containing the build task s startup status, spec summary, and subsequent status query suggestions.",
    example="generate_confirmed_external_skill(session_id='abc123', confirmed=true)",
    related_tools=["preview_external_skill_spec", "inspect_external_skill_generation_session"],
    data_source_handling="local_only",
)
async def generate_confirmed_external_skill(
    session_id: Annotated[str, "There is already a Skill created session ID"],
    confirmed: Annotated[bool, "Whether explicit confirmation of the SkillSpec has been obtained from the user"] = False,
    user_message: Annotated[str, "Confirmation message, default to confirm"] = "确认",
) -> str:
    """Trigger external skill generation after confirmation."""
    try:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return _json_response({"status": "error", "message": "session_id cannot be empty"})
        if not confirmed:
            return _json_response({
                "status": "error",
                "message": "Without explicit confirmation from the user, the external skill generation is refused to be triggered. Please preview the spec first and confirm.",
            })

        service = _get_skill_generation_service()
        result = await service.confirm_spec(clean_session_id, str(user_message or "确认").strip() or "确认")
        return _json_response({
            "status": "ok",
            "session_id": clean_session_id,
            "generation": result,
            "recommended_next_step": "inspect_external_skill_generation_session",
            "available_next_steps": ["inspect_external_skill_generation_session"],
        })
    except Exception as exc:
        logger.error("Failed to generate external skill after confirmation: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to generate external skill after confirmation: {exc}"})


@tool
@register_tool(
    tool_id="inspect_external_skill_generation_session",
    name="View External Skill generation session",
    description="View the current status, spec, scout summary, and build progress of an external skill build session to easily track asynchronous build results.",
    category="external",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when external skill generation has been triggered, or you need to check which stage the current session is in: gathering, confirmed, generating, completed, or failed.",
    when_not_to_use="If you are just continuing to replenish your needs, respond_to_external_skill_generation_session should be used.",
    returns="Returns a JSON string containing session summary, pipeline stage, spec, and recommendation build context.",
    example="inspect_external_skill_generation_session(session_id='abc123')",
    related_tools=["generate_confirmed_external_skill", "respond_to_external_skill_generation_session"],
    data_source_handling="local_only",
)
async def inspect_external_skill_generation_session(
    session_id: Annotated[str, "Skill Create session ID"],
) -> str:
    """View external skill generated session status."""
    try:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return _json_response({"status": "error", "message": "session_id cannot be empty"})

        service = _get_skill_generation_service()
        session_doc = await service.get_session(clean_session_id)
        if not session_doc:
            return _json_response({"status": "error", "message": f"会话 {clean_session_id} 不存在"})
        return _json_response({
            "status": "ok",
            "session": _summarize_session_doc(session_doc),
        })
    except Exception as exc:
        logger.error("View external skill failed to generate session: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"View external skill failed to generate session: {exc}"})
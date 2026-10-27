"""
prompt word generator — Generate exclusive prompt words for Agents in the workflow

Analyze results based on gaps in the blueprint (gap_analysis.agent_reshaping), 
Generate workflow-specific prompt words for the Agent that needs to be customized and save them to the prompt_templates collection.

Loading mechanism (existing, no need to modify):
    Debug Template > Workflow-specific templates(workflow_id) > User template > System default template

Reference: docs/05-design/v3.0/ai-workflow-generation.md §4.3
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.llm import UnifiedLLMClient, Message
from .workflow_spec import AgentReshapingPlan, WorkflowBlueprint

logger = logging.getLogger(__name__)

# Agent category → prompt_templates The agent_type mapping
_CATEGORY_TO_AGENT_TYPE = {
    "analyst": "analysts",
    "researcher": "researchers",
    "trader": "trader",
    "risk": "risk",
    "manager": "managers",
    "post_processor": "post_processor",
}

# Prompt word generation prompt — Generate complete based on reshaping direction information TemplateContent
EXPAND_PROMPT = """\
You are a professional prompt word engineer. Please use the following information to generate a complete workflow-specific prompt word for Agent.

## Agent information
- Agent ID: {agent_id}
- original character: {original_role}
- New roles (this workflow): {new_role}
- Workflow name: {workflow_name}
- Workflow description: {workflow_description}

## Original prompt word (reference baseline)
{original_prompt}

## Customized direction
{reshaping_direction}

## Key analytical dimensions
{key_focus_areas}

## Output requirements

Please generate workflow-specific prompt words based on the original prompt words and the above customization directions. Requirements:
- Make incremental changes based on the original prompt word rather than rewriting it from scratch
- Preserve tool usage conventions, output field conventions, and core constraints in the original prompt word
- Adjust analysis focus and role positioning according to customized direction
- Supplement new analysis requirements based on key analysis dimensions

Output a complete prompt word configuration, including the following 6 fields:

1. **system_prompt** — System prompt words, defining AI role and core code of conduct (200-500 words)
2. **user_prompt** — User prompt word template, use {{stock_symbol}} equal variables (can be left blank)
3. **tool_guidance** — Tool usage guide, explaining which tools should be used first and parameter precautions (100-300 words)
4. **analysis_requirements** — Analysis requirements, combined with key analysis dimensions, list the specific dimensions that need attention (100-300 words)
5. **output_format** — Output format template, using markdown to define the report structure
6. **constraints** — Constraints, limitations and considerations (50-200 words)

Please output strictly in the following JSON format (do not include other text):
{{
    "system_prompt": "...",
    "user_prompt": "",
    "tool_guidance": "...",
    "analysis_requirements": "...",
    "output_format": "...",
    "constraints": "..."
}}
"""


class PromptGenerator:
    """
    prompt word generator

    According to gap_analysis.agent_reshaping in the blueprint,
    Generate workflow-specific prompt words in batches for Agents who need customized prompt words.
    """

    def __init__(self, db, llm_client: Optional[UnifiedLLMClient] = None):
        """
        Args:
            db: MongoDB Database instance (synchronous or asynchronous)
            llm_client: LLM Client (for extending prompt word draft)
        """
        self._db = db
        self._llm_client = llm_client

    async def generate_prompts(
        self,
        workflow_id: str,
        blueprint: WorkflowBlueprint,
    ) -> List[str]:
        """
        Batch generate workflow-specific prompt words for Agents who need customized prompt words

        Args:
            workflow_id: Workflow ID
            blueprint: AI generated blueprint

        Returns:
            Successfully created prompt_template ID list
        """
        if not blueprint.gap_analysis:
            logger.info("[PromptGenerator] Gap-free analysis, skip prompt word generation")
            return []

        reshaping_list = blueprint.gap_analysis.agent_reshaping
        if not reshaping_list:
            logger.info("[PromptGenerator] No need to customize prompt words Agent")
            return []

        created_ids: List[str] = []
        for plan in reshaping_list:
            try:
                template_id = await self._generate_one_prompt(
                    workflow_id=workflow_id,
                    plan=plan,
                    blueprint=blueprint,
                )
                if template_id:
                    created_ids.append(template_id)
                    logger.info(
                        f"[PromptGenerator] ✅ {plan.agent_id} Prompt word has been created: {template_id}"
                    )
            except Exception as e:
                logger.error(
                    f"[PromptGenerator] ❌ {plan.agent_id} Prompt word generation failed: {e}",
                    exc_info=True,
                )

        # Update blueprint creation progress
        blueprint.creation_progress["prompts_completed"] = len(created_ids)

        return created_ids

    async def _generate_one_prompt(
        self,
        workflow_id: str,
        plan: AgentReshapingPlan,
        blueprint: WorkflowBlueprint,
    ) -> Optional[str]:
        """
        Generate workflow-specific prompt words for a single Agent

        Based on reshaping_direction and key_focus_areas in the blueprint,
        Call LLM to generate the complete TemplateContent.
        If prompt_changes already contains complete content (compatible with old formats), use it directly.
        """
        # Compatible with old formats: If prompt_changes already has complete content, use it directly
        draft = plan.prompt_changes
        required_keys = {"system_prompt", "tool_guidance", "analysis_requirements", "output_format"}
        has_full_draft = required_keys.issubset(draft.keys()) and all(
            len(draft.get(k, "")) > 20 for k in required_keys
        )

        if has_full_draft:
            content = self._normalize_content(draft)
        elif self._llm_client:
            content = await self._expand_prompt_from_reshaping(plan, blueprint)
        else:
            # No LLM: Use prompt_changes to get the full story
            content = self._normalize_content(draft)

        if not content:
            return None

        # Query Agent metadata to determine agent_type
        agent_type = await self._resolve_agent_type(plan.agent_id)

        # Save to prompt_templates collection
        template_doc = {
            "agent_type": agent_type,
            "agent_name": plan.agent_id,
            "template_name": plan.new_role or f"{plan.agent_id} - Workflow specific",
            "workflow_id": workflow_id,
            "node_id": plan.node_id or "",  # 🆕 Node ID (the same agent is used to distinguish when different nodes have different prompt words)
            "preference_type": "workflow",
            "content": content,
            "remark": f"Automatically generated by AI Workflow Architect (workflow: {blueprint.name})",
            "is_system": False,
            "created_by": None,
            "status": "draft",  # Draft status, changed to after publishing active
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "version": 1,
        }

        result = await self._db.prompt_templates.insert_one(template_doc)
        return str(result.inserted_id)

    async def _expand_prompt_from_reshaping(
        self,
        plan: AgentReshapingPlan,
        blueprint: WorkflowBlueprint,
    ) -> Optional[Dict[str, str]]:
        """Call LLM based on the reshaping direction information to generate a complete TemplateContent"""

        # Construct key analysis dimension text
        if plan.key_focus_areas:
            focus_text = "\n".join(f"- {area}" for area in plan.key_focus_areas)
        else:
            focus_text = " (Not specified, please plan according to role needs)"

        # Read the Agent's system default prompt word from the database as a baseline
        original_prompt = await self._fetch_original_prompt(plan.agent_id)

        prompt = EXPAND_PROMPT.format(
            agent_id=plan.agent_id,
            original_role=plan.original_role,
            new_role=plan.new_role,
            workflow_name=blueprint.name,
            workflow_description=blueprint.description,
            reshaping_direction=plan.reshaping_direction or "Generate exclusive prompt words based on new role positioning",
            key_focus_areas=focus_text,
            original_prompt=original_prompt,
        )

        messages = [
            Message(role="system", content="You are a prompt word engineer, please strictly output in JSON format."),
            Message(role="user", content=prompt),
        ]

        try:
            response = self._llm_client.chat(messages)
            raw = response.content or ""
            # Try to extract JSON
            from .workflow_planner import WorkflowPlanner
            data = WorkflowPlanner._try_parse_json(raw.strip())
            if data is None:
                # try ```json``` code block
                import re
                match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
                if match:
                    data = WorkflowPlanner._try_parse_json(match.group(1).strip())
            if data and isinstance(data, dict):
                return self._normalize_content(data)
        except Exception as e:
            logger.error(f"[PromptGenerator] LLM Prompt word generation failed: {e}", exc_info=True)

        # Keep everything in mind: Return empty template
        return self._normalize_content({})

    @staticmethod
    def _normalize_content(data: Dict[str, str]) -> Dict[str, str]:
        """Make sure content contains all fields required by TemplateContent"""
        return {
            "system_prompt": data.get("system_prompt", ""),
            "user_prompt": data.get("user_prompt", ""),
            "tool_guidance": data.get("tool_guidance", ""),
            "analysis_requirements": data.get("analysis_requirements", ""),
            "output_format": data.get("output_format", ""),
            "constraints": data.get("constraints", ""),
        }

    async def _fetch_original_prompt(self, agent_id: str) -> str:
        """Read the Agent s system default prompt word from the database as a baseline"""
        if self._db is None:
            return " (There is no database connection and the original prompt word cannot be obtained)"
        try:
            agent_type = await self._resolve_agent_type(agent_id)
            doc = await self._db.prompt_templates.find_one({
                "agent_type": agent_type,
                "agent_name": agent_id,
                "is_system": True,
                "workflow_id": None,
                "status": "active",
                "$or": [
                    {"node_id": {"$exists": False}},
                    {"node_id": None},
                    {"node_id": ""},
                ],
            })
            if doc and doc.get("content"):
                content = doc["content"]
                parts = []
                if content.get("system_prompt"):
                    parts.append(f"### system_prompt\n{content['system_prompt']}")
                if content.get("tool_guidance"):
                    parts.append(f"### tool_guidance\n{content['tool_guidance']}")
                if content.get("analysis_requirements"):
                    parts.append(f"### analysis_requirements\n{content['analysis_requirements']}")
                if content.get("output_format"):
                    parts.append(f"### output_format\n{content['output_format']}")
                if content.get("constraints"):
                    parts.append(f"### constraints\n{content['constraints']}")
                return "\n\n".join(parts) if parts else " (The system default prompt word was not found in the database)"
            return " (The system default prompt word was not found in the database)"
        except Exception as e:
            logger.warning(f"[PromptGenerator] Failed to read original prompt word: {e}")
            return f" (Read failed: {e}) "

    async def _resolve_agent_type(self, agent_id: str) -> str:
        """Determine the prompt_templates in prompt_templates based on agent_id agent_type"""
        # First check from the database agent_configs
        if self._db is not None:
            try:
                agent_doc = await self._db.agent_configs.find_one({"agent_id": agent_id})
                if agent_doc and "category" in agent_doc:
                    cat = agent_doc["category"]
                    return _CATEGORY_TO_AGENT_TYPE.get(cat, cat)
            except Exception:
                pass

        # rollback: Check from BUILTIN_AGENTS
        try:
            from core.agents.config import BUILTIN_AGENTS
            meta = BUILTIN_AGENTS.get(agent_id)
            if meta:
                cat = meta.category if hasattr(meta, "category") else "analyst"
                cat_str = cat.value if hasattr(cat, "value") else str(cat)
                return _CATEGORY_TO_AGENT_TYPE.get(cat_str, cat_str)
        except Exception:
            pass

        # Finally get the bottom of things
        return "analysts"


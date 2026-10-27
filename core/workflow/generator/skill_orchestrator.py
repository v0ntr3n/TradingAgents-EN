"""
Skill Orchestrator — Automatically create and bind missing tools based on Skill gaps in blueprints

process:
1. Traverse blueprint.gap_analysis.missing_skills
2. for each SkillCreationRequest:
   a. call SkillGenerationService.start_session(description)
   b. automatic confirm_spec → Trigger code generation + Verify
   c. success → backfill generated_skill_id + bind to target_agent_id
   d. failed → mark status=failed, Log errors
3. Bind all newly created Skills to the corresponding Agent

Reference: docs/05-design/v3.0/ai-workflow-generation.md §4.4
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .workflow_spec import SkillCreationRequest, WorkflowBlueprint

logger = logging.getLogger(__name__)

# The upper limit of the timeout for creating a single Skill (seconds). If it exceeds the limit, it will be marked as failed
SKILL_CREATION_TIMEOUT = 120


class SkillOrchestrator:
    """
    Skill Orchestrator

    According to gap_analysis.missing_skills in the blueprint,
    Batch calling the SkillGenerationService pipeline to create missing tools,
    And bind it to the corresponding Agent.
    """

    def __init__(self, db, skill_generation_service=None):
        """
        Args:
            db: MongoDB Asynchronous database instance (motor)
            skill_generation_service: SkillGenerationService Example
                If not passed, it will be created on demand when first used.
        """
        self._db = db
        self._skill_service = skill_generation_service

    def _ensure_service(self):
        """Lazy initialization SkillGenerationService"""
        if self._skill_service is None:
            from app.services.skill_generation_service import SkillGenerationService
            self._skill_service = SkillGenerationService(db=self._db)

    # ================================================================
    # public method
    # ================================================================

    async def create_missing_skills(
        self,
        blueprint: WorkflowBlueprint,
        user_id: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Marked as missing in batch creation blueprints Skill

        Args:
            blueprint: AI Generated workflow blueprint (including gap_analysis.missing_skills)
            user_id: initiator ID

        Returns:
            List of creation results for each Skill:
            [{"skill_name", "status", "skill_id"?, "error"?}]
        """
        if not blueprint.gap_analysis:
            logger.info("[SkillOrchestrator] No gap analysis, skip skill creation")
            return []

        missing = blueprint.gap_analysis.missing_skills
        if not missing:
            logger.info("[SkillOrchestrator] Nothing missing Skill")
            return []

        self._ensure_service()

        results: List[Dict[str, Any]] = []
        for req in missing:
            result = await self._create_one_skill(req, user_id, blueprint)
            results.append(result)

        # Update blueprint progress
        completed = sum(1 for r in results if r["status"] == "completed")
        blueprint.creation_progress["skills_completed"] = completed

        return results

    async def bind_skills_to_agents(
        self,
        workflow_id: str,
        blueprint: WorkflowBlueprint,
    ) -> int:
        """
        Bind the newly created Skill to the corresponding Agent (via tool_agent_bindings)

        only handle status=completed And there is a Skill with generated_skill_id.
        Binding level: Agent level (no node_id), as the default guarantee.

        Args:
            workflow_id: Workflow ID (for logs)
            blueprint: blueprint

        Returns:
            The number of successful bindings
        """
        if not blueprint.gap_analysis:
            return 0

        bound_count = 0
        for req in blueprint.gap_analysis.missing_skills:
            if req.status != "completed" or not req.generated_skill_id:
                continue
            if not req.target_agent_id:
                continue

            try:
                await self._bind_one(req.target_agent_id, req.generated_skill_id)
                bound_count += 1
                logger.info(
                    f"[SkillOrchestrator] ✅ Bound {req.generated_skill_id} → {req.target_agent_id}"
                )
            except Exception as e:
                logger.error(
                    f"[SkillOrchestrator] ❌ Binding failed {req.generated_skill_id} → {req.target_agent_id}: {e}",
                    exc_info=True,
                )

        return bound_count

    async def bind_additional_tools_to_nodes(
        self,
        workflow_id: str,
        blueprint: WorkflowBlueprint,
        is_active: bool = False,
    ) -> int:
        """
        Create node-level tool bindings for additional_tools in agent_reshaping.

        For scenarios where the same Agent appears on different nodes, use workflow_id + node_id precise binding,
        Avoid tools polluting other nodes.

        Args:
            workflow_id: Workflow ID
            blueprint: Blueprint (with agent_reshaping list)
            is_active: Whether to activate binding (False=draft,True=production)

        Returns:
            The number of successfully created bindings
        """
        if not blueprint.gap_analysis or not blueprint.gap_analysis.agent_reshaping:
            return 0

        bound_count = 0
        now = datetime.utcnow().isoformat()

        for reshaping in blueprint.gap_analysis.agent_reshaping:
            if not reshaping.additional_tools:
                continue
            if not reshaping.node_id:
                logger.warning(
                    f"[SkillOrchestrator] ⚠️ agent_reshaping in {reshaping.agent_id} node_id is missing,"
                    f"Skip node-level tool binding (additional_tools={reshaping.additional_tools}) "
                )
                continue

            for tool_id in reshaping.additional_tools:
                try:
                    await self._db.tool_agent_bindings.update_one(
                        {
                            "agent_id": reshaping.agent_id,
                            "tool_id": tool_id,
                            "workflow_id": workflow_id,
                            "node_id": reshaping.node_id,
                        },
                        {
                            "$set": {
                                "agent_id": reshaping.agent_id,
                                "tool_id": tool_id,
                                "workflow_id": workflow_id,
                                "node_id": reshaping.node_id,
                                "priority": 10,
                                "is_active": is_active,
                                "updated_at": now,
                            },
                            "$setOnInsert": {
                                "created_at": now,
                            },
                        },
                        upsert=True,
                    )
                    bound_count += 1
                    logger.info(
                        f"[SkillOrchestrator] ✅ Node-level tool binding: "
                        f"{tool_id} → {reshaping.agent_id} "
                        f"(workflow={workflow_id}, node={reshaping.node_id}, active={is_active})"
                    )
                except Exception as e:
                    logger.error(
                        f"[SkillOrchestrator] ❌ Node level tool binding failed: "
                        f"{tool_id} → {reshaping.agent_id}: {e}",
                        exc_info=True,
                    )

        return bound_count

    # ================================================================
    # internal method
    # ================================================================

    async def _create_one_skill(
        self,
        req: SkillCreationRequest,
        user_id: str,
        blueprint: WorkflowBlueprint,
    ) -> Dict[str, Any]:
        """
        Create a single Skill

        process:
        1. Check whether the Skill with the same name already exists → skip
        2. start_session(description) → Start creating a session
        3. confirm_spec(session_id) → Trigger code generation
        4. success → Backfill req.generated_skill_id, modify req.status
        5. failed → mark req.status='failed', record req.error
        """
        skill_name = req.skill_name

        # 1. Check whether the Skill with the same name already exists
        existing = await self._db.external_skills.find_one(
            {"tool_id": skill_name, "status": "active"}
        )
        if existing:
            req.generated_skill_id = existing["tool_id"]
            req.status = "completed"
            logger.info(
                f"[SkillOrchestrator] ⏭️ Skill '{skill_name}' Already exists, skip creation"
            )
            return {
                "skill_name": skill_name,
                "status": "completed",
                "skill_id": existing["tool_id"],
                "skipped": True,
            }

        # 2. Start creating a session (pass in the blueprint context to let the Skill Workshop understand the big picture)
        req.status = "creating"
        description = self._build_skill_description(req, blueprint)

        try:
            start_result = await self._skill_service.start_session(
                description=description,
                user_id=user_id,
            )
            session_id = start_result.get("session_id")
            if not session_id:
                raise ValueError("start_session Not returned session_id")

            logger.info(
                f"[SkillOrchestrator] 🚀 Start creating Skill '{skill_name}' (session: {session_id})"
            )

            # 3. Automatically confirm and generate codes
            confirm_result = await self._skill_service.confirm_spec(
                session_id=session_id,
                user_message="Confirm, please generate code directly",
            )

            if confirm_result.get("success"):
                skill_id = confirm_result.get("skill_id", "")
                req.generated_skill_id = skill_id
                req.status = "completed"

                # Mark the newly created Skill as draft status to avoid contaminating production data
                # When publishing, switch to active
                try:
                    await self._db.external_skills.update_one(
                        {"tool_id": skill_id},
                        {"$set": {"status": "draft"}},
                    )
                except Exception as draft_err:
                    logger.warning(
                        f"[SkillOrchestrator] mark Skill '{skill_id}' failed for draft: {draft_err}"
                    )

                logger.info(
                    f"[SkillOrchestrator] ✅ Skill '{skill_name}' Created successfully(draft): {skill_id}"
                )
                return {
                    "skill_name": skill_name,
                    "status": "completed",
                    "skill_id": skill_id,
                }
            else:
                error = confirm_result.get("error", "Code generation failed")
                req.status = "failed"
                req.error = error
                logger.warning(
                    f"[SkillOrchestrator] ⚠️ Skill '{skill_name}' Build failed: {error}"
                )
                return {
                    "skill_name": skill_name,
                    "status": "failed",
                    "error": error,
                }

        except Exception as e:
            req.status = "failed"
            req.error = str(e)
            logger.error(
                f"[SkillOrchestrator] ❌ Skill '{skill_name}' Create exception: {e}",
                exc_info=True,
            )
            return {
                "skill_name": skill_name,
                "status": "failed",
                "error": str(e),
            }

    async def _bind_one(self, agent_id: str, tool_id: str, *, is_active: bool = False) -> None:
        """
        Bind a Skill to an Agent (upsert to tool_agent_bindings)

        Args:
            agent_id: target Agent ID
            tool_id: Skill/tool to be bound ID
            is_active: Whether to activate immediately (default False is draft status, activated after release)
        """
        now = datetime.utcnow().isoformat()
        await self._db.tool_agent_bindings.update_one(
            {"agent_id": agent_id, "tool_id": tool_id},
            {
                "$set": {
                    "agent_id": agent_id,
                    "tool_id": tool_id,
                    "is_active": is_active,
                    "priority": 99,  # Newly created Skills have lower priority
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

    @staticmethod
    def _build_skill_description(req: SkillCreationRequest, blueprint: WorkflowBlueprint) -> str:
        """
        Convert SkillCreationRequest into a usable natural language description for SkillGenerationService

        Contains full context: Workflow background + Agent role + tool requirements,
        Make sure Skill Workshop s code generation pipeline understands the bigger picture.
        """
        parts = []

        # ── workflow background ──
        wf_name = blueprint.name or ""
        wf_desc = blueprint.description or blueprint.summary or ""
        if wf_name or wf_desc:
            parts.append("## workflow background")
            if wf_name:
                parts.append(f"- Workflow name: {wf_name}")
            if wf_desc:
                parts.append(f"- Workflow purpose: {wf_desc}")

        # ── The role of the target agent in this workflow ──
        agent_context_parts = SkillOrchestrator._find_agent_context(req, blueprint)
        if agent_context_parts:
            parts.append("")
            parts.append("## The role of the target agent in this workflow")
            parts.append(f"- Agent ID: {req.target_agent_id}")
            for line in agent_context_parts:
                parts.append(f"- {line}")

        # ── Tool requirements themselves ──
        parts.append("")
        parts.append("## Tools needed to create")
        parts.append(f"- Tool name: {req.skill_name}")
        if req.skill_description:
            parts.append(f"- Function description: {req.skill_description}")
        parts.append(f"- Usage scenarios: supply {req.target_agent_id} Agent Used in the above workflow")

        result = "\n".join(parts)
        logger.info(
            f"[SkillOrchestrator] 📝 Skill Create description ({req.skill_name}, "
            f"length={len(result)} character)"
        )
        return result

    @staticmethod
    def _find_agent_context(
        req: SkillCreationRequest, blueprint: WorkflowBlueprint
    ) -> List[str]:
        """
        Extract the target Agent s role context in this workflow from the blueprint

        Priority:
        1. agent_reshaping (LLM The generated character reshaping plan is the most informative)
        2. nodes (node label and description)
        """
        context: List[str] = []

        # 1. Get role reshaping information from agent_reshaping
        if blueprint.gap_analysis:
            for reshaping in blueprint.gap_analysis.agent_reshaping:
                if reshaping.agent_id == req.target_agent_id:
                    if reshaping.new_role:
                        context.append(f"role positioning: {reshaping.new_role}")
                    if reshaping.reshaping_direction:
                        context.append(f"Customized direction: {reshaping.reshaping_direction}")
                    if reshaping.key_focus_areas:
                        areas = ", ".join(reshaping.key_focus_areas)
                        context.append(f"Key analytical dimensions: {areas}")
                    break

        # 2. Supplement node-level information from nodes
        for node in blueprint.nodes:
            if node.agent_id == req.target_agent_id:
                if node.label:
                    # Avoid duplication (agent_reshaping may already have similar information)
                    if not any("Node name" in c for c in context):
                        context.insert(0, f"Node name: {node.label}")
                if node.description:
                    context.append(f"Node description: {node.description}")
                break

        return context


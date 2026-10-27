"""
resource collector — Collect available resources from the system for use by AI planning

Collection content:
1. BUILTIN_AGENTS — Built-in Agent list (id, name, description, category, tools) 
2. BUILTIN_TOOLS — List of built-in tools (id, name, description, category) 
3. skills/external_skills — MongoDB Standard Skills in and external Skill
4. agent_configs — MongoDB Agent configuration in (may include user-defined Agent)
5. prompt_templates — Prompt word template summary (used to understand the Agent s default capabilities)

Reference: docs/05-design/v3.0/ai-workflow-generation.md §4.1
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Universal Agent: required for any process (report generation, data preparation)
_UNIVERSAL_AGENT_IDS = {"report_generator_v2", "data_preparer_v2"}

# Relevance filtering: upper limit of Agent number (search top-K most relevant ones)
_MAX_RELEVANT_AGENTS = 15


class ResourceCollector:
    """
    resource collector

    Collect all available resources from code configuration and MongoDB,
    Construct contextual text understandable by LLM (controlled in ~4000-6000 tokens) . 
    """

    def __init__(self, db=None):
        """
        Args:
            db: MongoDB Database instance (optional, if not passed, only the built-in configuration will be used)
        """
        self._db = db

    def set_database(self, db) -> None:
        self._db = db

    async def collect_all(
        self, user_query: Optional[str] = None,
        capability_index=None
    ) -> Dict[str, Any]:
        """
        Gather all available resources

        Args:
            user_query: User s workflow requirement description, used for Agent relevance filtering.
                       Passing None returns all Agents.
            capability_index: CapabilityIndexService Instance (optional).
                             Enables vector semantic search filtering agent when provided.

        Returns:
            {
                "agents": [...],
                "tools": [...],
                "external_skills": [...],
                "prompt_summaries": [...],
                "node_types": [...],
                "context_text": "..."   # Summary text description
            }
        """
        agents = await self._collect_agents()

        # 🎯 Vector Semantic Search Filtering: Find the Most Relevant by CapabilityIndex Agent
        if user_query and capability_index and agents:
            agents = await self._filter_agents_via_capability_index(
                agents, user_query, capability_index
            )

        tools = self._collect_tools()
        skills = await self._collect_external_skills()
        prompt_summaries = await self._collect_prompt_summaries()
        node_types = self._get_node_types()

        context_text = self._build_context_text(
            agents, prompt_summaries, node_types
        )

        return {
            "agents": agents,
            "tools": tools,
            "external_skills": skills,
            "prompt_summaries": prompt_summaries,
            "node_types": node_types,
            "context_text": context_text,
        }

    async def _filter_agents_via_capability_index(
        self, agents: List[Dict[str, Any]], user_query: str,
        capability_index
    ) -> List[Dict[str, Any]]:
        """
        Filter the most relevant ones via vector semantic search of CapabilityIndex Agent

        Rules:
        1. Search with user_query source_type="agent" ability items
        2. source=database Custom Agents are always retained (those explicitly created by the user)
        3. Always keep the generic Agent (report_generator_v2, data_preparer_v2) 
        """
        # Separate built-in and custom Agent
        builtin = [a for a in agents if a.get("source") != "database"]
        custom = [a for a in agents if a.get("source") == "database"]

        if not builtin:
            return custom  # There is no built-in Agent, and the customized one is returned directly.

        try:
            hits = await capability_index.search_capabilities(
                query=user_query,
                top_k=max(_MAX_RELEVANT_AGENTS - len(custom), 5),
                source_types=["agent"],
            )
        except Exception as e:
            logger.warning(
                f"[ResourceCollector] CapabilityIndex Agent Search failed, fallback to all Agent: {e}"
            )
            return agents

        if not hits:
            logger.info("[ResourceCollector] CapabilityIndex No relevant Agent found, use all")
            return agents

        # Build a collection of search result IDs
        hit_ids = {h.capability.capability_id for h in hits}
        hit_scores = {h.capability.capability_id: h.score for h in hits}

        # 🔍 Debugging: Print CapabilityIndex search hits Agent
        logger.info(
            f"🔍 [ResourceCollector] CapabilityIndex Vector search results (top_k={max(_MAX_RELEVANT_AGENTS - len(custom), 5)}): "
            f"{[(cid, round(score, 3)) for cid, score in sorted(hit_scores.items(), key=lambda x: -x[1])]}"
        )

        # Always join the universal Agent
        hit_ids.update(_UNIVERSAL_AGENT_IDS)

        # Match built-in by ID Agent
        matched_builtin = [a for a in builtin if a["id"] in hit_ids]
        matched_ids = {a["id"] for a in matched_builtin}
        filtered_out = [a["id"] for a in builtin if a["id"] not in hit_ids]

        # Merge: Custom Agent (keep all) + Matched built-in Agent
        result = custom + matched_builtin

        total_in = len(builtin) + len(custom)
        total_out = len(result)
        logger.info(
            f"🎯 [ResourceCollector] CapabilityIndex Vector filtering: "
            f"{total_in} → {total_out} Agent "
            f"(Built-in: {len(builtin)}→{len(matched_builtin)}, "
            f"Customize: {len(custom)} keep all, "
            f"Query='{user_query[:80]}')"
        )
        logger.info(
            f"   ✅ reserved built-in: {sorted(matched_ids)}"
        )
        if filtered_out and len(filtered_out) <= 30:
            logger.info(f"   ❌ Filtered out built-in: {sorted(filtered_out)}")

        return result

    async def _collect_agents(self) -> List[Dict[str, Any]]:
        """Collect available Agent list (MAINTANED status only, filter out DEPRECATED/UNMAINTAINED)"""
        agents = []

        # 1. Collect from built-in configuration (MAINTAINED only)
        try:
            from core.agents.config import BUILTIN_AGENTS, AgentMaintenanceStatus
            for agent_id, meta in BUILTIN_AGENTS.items():
                # 🛡️ Filter out abandoned Agents to prevent LLM from getting lost in overly large lists
                if meta.maintenance_status == AgentMaintenanceStatus.DEPRECATED:
                    continue
                if meta.maintenance_status == AgentMaintenanceStatus.UNMAINTAINED:
                    continue
                agents.append({
                    "id": meta.id,
                    "name": meta.name,
                    "description": meta.description,
                    "category": meta.category.value if hasattr(meta.category, 'value') else str(meta.category),
                    "default_tools": list(meta.default_tools),
                    "output_field": meta.output_field or "",
                    "report_label": meta.report_label or "",
                    "maintenance_status": meta.maintenance_status.value if hasattr(meta.maintenance_status, 'value') else str(meta.maintenance_status),
                    "source": "builtin",
                })
        except Exception as e:
            logger.warning(f"Failed to load built-in Agent: {e}")

        # 2. Supplemented from MongoDB (user may have created a custom Agent)
        if self._db is not None:
            try:
                builtin_ids = {a["id"] for a in agents}

                # 🛡️ build v1→v2 Blocklist: Filter out old versions remaining in the database v1 Agent
                #    For example market_analyst (v1) Already market_analyst_v2 (v2) substitute
                v1_to_block: set = set()
                for builtin_id in builtin_ids:
                    if builtin_id.endswith("_v2"):
                        base = builtin_id[:-3]  # Remove the _v2 suffix
                        if base not in builtin_ids:
                            v1_to_block.add(base)

                db_agents = self._db.agent_configs.find({"enabled": True})
                blocked_count = 0
                async for doc in db_agents:
                    aid = doc.get("agent_id", "")
                    if aid and aid not in builtin_ids:
                        # Filter out old version v1 Agent in the database (has been replaced by v2)
                        if aid in v1_to_block:
                            blocked_count += 1
                            logger.debug(f"🚫 [ResourceCollector] Filter old version of database Agent: {aid} (Already v2)")
                            continue
                        agents.append({
                            "id": aid,
                            "name": doc.get("name", aid),
                            "description": doc.get("description", ""),
                            "category": doc.get("category", "custom"),
                            "default_tools": doc.get("default_tools", []),
                            "output_field": doc.get("output_field") or doc.get("result_field", ""),
                            "report_label": doc.get("report_label", ""),
                            "source": "database",
                        })
                if blocked_count > 0:
                    logger.info(
                        f"🛡️ [ResourceCollector] filtered {blocked_count} database old version Agent"
                        f" (Already replaced by v2 built-in version)"
                    )
            except Exception as e:
                logger.warning(f"Failed to load Agent configuration from database: {e}")

        return agents

    def _collect_tools(self) -> List[Dict[str, Any]]:
        """Collect a list of available tools"""
        tools = []
        try:
            from core.tools.config import BUILTIN_TOOLS
            for tool_id, meta in BUILTIN_TOOLS.items():
                tools.append({
                    "id": meta.id,
                    "name": meta.name,
                    "description": meta.description,
                    "category": meta.category.value if hasattr(meta.category, 'value') else str(meta.category),
                    "source": "builtin",
                })
        except Exception as e:
            logger.warning(f"Failed to load built-in tools: {e}")
        return tools

    async def _collect_external_skills(self) -> List[Dict[str, Any]]:
        """Collect standard skills and external Skill"""
        skills = []
        if self._db is None:
            return skills
        try:
            standard_docs = self._db.skills.find({"enabled": True})
            async for doc in standard_docs:
                name = doc.get("name", "")
                skills.append({
                    "id": name.replace("-", "_"),
                    "name": name,
                    "description": doc.get("description", ""),
                    "category": doc.get("category", "standard"),
                    "source": "standard_skill",
                })

            external_docs = self._db.external_skills.find({"status": "active"})
            async for doc in external_docs:
                skills.append({
                    "id": doc.get("tool_id", ""),
                    "name": doc.get("display_name") or doc.get("name", ""),
                    "description": doc.get("description", ""),
                    "category": doc.get("metadata", {}).get("category", "external"),
                    "source": "external_skill",
                })
        except Exception as e:
            logger.warning(f"Failed to load Skill from database: {e}")
        return skills

    async def _collect_prompt_summaries(self) -> List[Dict[str, str]]:
        """
        Collection prompt word template summary

        Get whether each Agent has a custom template and read the content summary of the system s default prompt words.
        Help AI judge based on actual prompt word content"Reuse vs optimization". 
        """
        summaries = []
        if self._db is None:
            return summaries
        try:
            # Get a summary of the system's default prompt words (including the first 800 words of system_prompt content)
            pipeline = [
                {"$match": {"status": "active", "is_system": True, "workflow_id": None}},
                {"$group": {
                    "_id": {"agent_type": "$agent_type", "agent_name": "$agent_name"},
                    "template_names": {"$push": "$template_name"},
                    "has_workflow_specific": {
                        "$sum": {"$cond": [{"$ne": ["$workflow_id", None]}, 1, 0]}
                    },
                    "count": {"$sum": 1},
                    # Read the system_prompt content of the first template (first 800 words as summary)
                    "system_prompt_preview": {"$first": "$content.system_prompt"},
                }},
            ]
            results = await self._db.prompt_templates.aggregate(pipeline).to_list(length=500)
            for r in results:
                preview = r.get("system_prompt_preview") or ""
                # Extract the first 800 words as a preview to avoid too long context
                if len(preview) > 800:
                    preview = preview[:800] + "...(Truncate)"
                summaries.append({
                    "agent_type": r["_id"]["agent_type"],
                    "agent_name": r["_id"]["agent_name"],
                    "template_count": r["count"],
                    "has_workflow_specific": r["has_workflow_specific"] > 0,
                    "template_names": r["template_names"][:3],  # Display up to 3
                    "system_prompt_preview": preview,
                })
        except Exception as e:
            logger.warning(f"Failed to collect prompt word template summary: {e}")
        return summaries

    def _get_node_types(self) -> List[Dict[str, str]]:
        """Get descriptions of available node types"""
        return [
            {"type": "start", "description": "Workflow starting node, each workflow must have one and only one"},
            {"type": "end", "description": "Workflow end node, each workflow must have and only one"},
            {"type": "analyst", "description": "Analyst nodes perform specific analysis tasks (technical analysis, fundamentals, news, etc.) and need to be associated agent_id"},
            {"type": "researcher", "description": "Researcher node, comprehensive analysis report for research (long/short), need to be associated agent_id"},
            {"type": "trader", "description": "Research integrator node, generates user version of research briefing, needs to be associated agent_id"},
            {"type": "risk", "description": "Risk analysis node, assess risk (high resilience/defense/baseline), need to be associated agent_id"},
            {"type": "manager", "description": "Manager node, integrating multiple perspectives to form research conclusions, requires correlation agent_id"},
            {"type": "parallel", "description": "Start nodes in parallel, and then execute multiple branches in parallel"},
            {"type": "merge", "description": "Merge nodes in parallel, waiting for multiple branches to complete"},
            {"type": "debate", "description": "Multi-scenario research node, multiple Agents conduct multiple rounds of scenario research (such as proactive/cautious scenario research, risk scenario research)"},
            {"type": "post_processor", "description": "Post-processing nodes summarize or format analysis results"},
            {"type": "condition", "description": "Conditional nodes, select different branches based on conditions"},
        ]

    def _build_context_text(
        self,
        agents: List[Dict[str, Any]],
        prompt_summaries: List[Dict[str, str]],
        node_types: List[Dict[str, str]],
    ) -> str:
        """
        Build contextual text that LLM understands

        Compression strategy:
        - Agent: Pass only id, name, description, category (Not sending the complete tools list)
        - prompt word: Only the summary is transmitted (which agents have custom templates)
        - Group by category
        - Do not upload tool/skill list (replaced by CapabilityIndex precise search)
        """
        sections = []

        # Agent list
        prompt_map = {s["agent_name"]: s for s in prompt_summaries}

        # 🔍 Debugging: Print the complete list of Agents passed to LLM
        agent_ids = [a["id"] for a in agents]
        logger.info(
            f"📋 [ResourceCollector] Agent list passed to LLM (total {len(agents)} a): "
            f"{agent_ids}"
        )

        sections.append("## Available Agents\n")
        categories: Dict[str, List] = {}
        for a in agents:
            cat = a.get("category", "other")
            categories.setdefault(cat, []).append(a)
        for cat, items in sorted(categories.items()):
            sections.append(f"### {cat}")
            for a in items:
                line = f"- **{a['id']}** ({a['name']}): {a['description']}"
                # Maintenance status flag (warn LLM when not MAINTAINED)
                status = a.get("maintenance_status", "maintained")
                if status and status != "maintained":
                    line += f"  ⚠️ [Status: {status}]"
                # Output fields (help LLM understand data flow and collaboration between agents)
                output_field = a.get("output_field", "")
                if output_field:
                    line += f"  [→ output field: `{output_field}`]"
                # Additional prompt word summary and actual content preview
                ps = prompt_map.get(a["id"])
                if ps:
                    line += f"  [Default prompt word: Yes{ps['template_count']}templates]"
                    preview = ps.get("system_prompt_preview", "")
                    if preview:
                        line += f"\n  <Prompt word preview>\n{preview}\n  </Prompt word preview>"
                else:
                    line += "  [Default prompt word: Universal]"
                sections.append(line)
            sections.append("")

        # Node type
        sections.append("## Available workflow node types\n")
        for nt in node_types:
            sections.append(f"- **{nt['type']}**: {nt['description']}")
        sections.append("")

        return "\n".join(sections)


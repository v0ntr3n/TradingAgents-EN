"""
Workflow planner — LLM Driven conversational workflow design

Understand user needs through multiple rounds of dialogue and generate inclusion structures + gap analysis + A complete blueprint for prompt word assessment.

Three core methods:
- chat()                — Multiple rounds of dialogue (including draft plan + prompt word evaluation + tool inspection)
- generate_blueprint()  — Make conversations structured WorkflowBlueprint JSON
- generate_optimization() — iterative optimization phase

Reference: docs/05-design/v3.0/ai-workflow-generation.md §4.2
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.llm import UnifiedLLMClient, Message
from .workflow_spec import (
    ConversationRound,
    GenerationSessionStatus,
    WorkflowBlueprint,
    WorkflowGenerationSession,
    GapAnalysisResult,
    AgentReshapingPlan,
    SkillCreationRequest,
    PlannedNode,
    PlannedEdge,
)

logger = logging.getLogger(__name__)

# ── dialogue stage System Prompt ──────────────────────────────────────────────

SYSTEM_PROMPT_CHAT = """\
You are an AI workflow architect who is good at designing multi-agent collaborative analysis processes based on user needs.

## your task

Design a complete analysis workflow solution based on user needs. There are three levels you need to consider:

### Level 1: Workflow structure
Design nodes (Agents) and edges (connection relationships) to determine the topology of the analysis process.

### Level 2: Agent ability assessment and prompt word customization
For each selected Agent, evaluate its**Default prompt word**Is it sufficient to meet the needs of the current process:
- ✅ The default is sufficient: the general role of the Agent matches the needs of this process and does not require customization.
- ⚠️ Needs customization: The Agent s role in this process deviates from its default positioning, and workflow-specific prompts need to be generated.

For example:
- "Standard A-share analysis flow" in market_analyst → The default prompt word is enough ✅
- "Convertible bond analysis flow" in market_analyst → Need to be customized as"Convertible bond market analyst" ⚠️

### Level 3: Tool/Skill Gap
Check whether the selected Agent has sufficient tool support and identify missing tools.

## ⚠️ Key constraints: Agent selection rules (strictly observed)

1. **You can only choose from the Agents listed in Available Resources below**, It is prohibited to fabricate, associate or fabricate things that do not exist agent_id
2. **Carefully read each Agent s description**, Find the one that best matches your abilities. For example:
   - Need valuation analysis → use `valuation_analyst_v2`, Don t make it up `buffett_valuation_analyst`
   - Need moat/competitive advantage analysis → use `fundamentals_analyst_v2` (Fundamental analysis covers competitive advantages/moats), don t make it up `moat_analyst`
   - Requires management evaluation → Use the same `fundamentals_analyst_v2` (Fundamental analysis covers management assessment), don t make it up `management_analyst`
3. **If there is indeed no suitable Agent that can meet the user s needs, clearly inform the user in the reply**, rather than making up a name that sounds reasonable
4. **Agent Names are just labels**, The real analysis direction is realized through prompt word customization (level 2), and there is no need to create a new one for each segmentation direction. Agent
5. **agent_id Must be copied exactly verbatim**, include `_v2`, `_v1` etc. suffix. For example `fundamentals_analyst_v2` cannot be written as `fundamentals_analyst`, `valuation_analyst_v2` cannot be written as `valuation_analyst`

## Available resources

{resource_context}

## Workflow structure rules

1. There must be one and only one start node and one end node
2. All nodes must be reachable (reachable from start and end)
3. Analysts that require parallel execution should be placed between parallel and merge nodes
4. Roles that need to debate should use the debate node
5. Each analyst/researcher/trader/risk/manager/post_processor node must specify a valid agent_id
6. agent_id Must come strictly from the Agent ID listed in Available Resources above (copy directly, don t change it)
7. Use lowercase letters for node IDs+Underline, such as market_node, parallel_1
8. The node positions are arranged horizontally from top to bottom and in parallel.

## Conversation rules

The first round of responses must contain the following three parts:

📊 **draft plan** — Process structure and steps
📋 **prompt word evaluation** — Which Agents use default prompt words and which ones need to be customized
🔧 **Tool inspection** — Are there any missing tools that need to be created?

Subsequent rounds will be adjusted based on user feedback. Don t output JSON in conversations.
"""

# ── Blueprint generation System Prompt ──────────────────────────────────────────────

SYSTEM_PROMPT_BLUEPRINT = """\
Generate a complete workflow blueprint JSON based on the following conversation history.

## Conversation history
{conversation_history}

## Available resources
{resource_context}

## Output requirements

Please output strictly according to the following JSON format (do not include other text, only output a JSON object):

{{
    "name": "Workflow name",
    "description": "Workflow description",
    "tags": ["label 1"],
    "nodes": [
        {{"id": "start", "type": "start", "label": "start", "position_x": 400, "position_y": 0}},
        {{"id": "xxx", "type": "analyst", "agent_id": "market_analyst", "label": "market analyst", "position_x": 200, "position_y": 150, "description": "Node description"}},
        {{"id": "end", "type": "end", "label": "end", "position_x": 400, "position_y": 800}}
    ],
    "edges": [
        {{"id": "e1", "source": "start", "target": "parallel_1", "type": "normal", "condition": null}}
    ],
    "config": {{"analysis_depth": 3, "debate_rounds": "auto"}},
    "input_config": {{
        "fields": [
            {{
                "name": "ticker",
                "label": "Stock code",
                "type": "string",
                "required": true,
                "default": null,
                "description": "The stock symbol to be analyzed, e.g. 600519.SH",
                "placeholder": "Such as: 600519.SH",
                "options": null,
                "option_labels": null,
                "min": null,
                "max": null,
                "group": "Basic parameters",
                "order": 1
            }},
            {{
                "name": "research_depth",
                "label": "Analysis depth",
                "type": "select",
                "required": false,
                "default": "Standard",
                "description": "Analysis depth level",
                "placeholder": "",
                "options": ["fast", "Basics", "Standard", "Depth", "Comprehensive"],
                "option_labels": ["fast (2-4 minutes)", "Basics (4-6 minutes)", "Standard (6-10 minutes)", "Depth (10-15 minutes)", "Comprehensive (15-25 minutes)"],
                "min": null,
                "max": null,
                "group": "Basic parameters",
                "order": 2
            }}
        ]
    }},
    "summary": "Program overview",
    "rationale": "design ideas",
    "agent_reshaping": [
        {{
            "agent_id": "market_analyst",
            "node_id": "cb_market_node",
            "original_role": "market analyst",
            "new_role": "Convertible bond market analyst",
            "reshaping_direction": "Shift from general market analysis to special analysis of convertible bonds, paying attention to indicators such as conversion premium rate and bond value.",
            "key_focus_areas": [
                "Trend analysis of stock conversion premium rate",
                "Comparison of pure debt value and equity conversion value",
                "Forced redemption risk monitoring",
                "Estimates revised downwards"
            ],
            "additional_tools": [
                "convertible_bond_data_fetcher",
                "premium_rate_calculator"
            ]
        }}
    ],
    "agents_using_default": [
        {{"agent_id": "news_analyst", "name": "news analyst", "reason": "News analysis is highly versatile and the default prompt words are sufficient"}}
    ],
    "analysis_summary": "4 Agents need to customize prompt words, and 3 agents use the default"
}}

## input_config Field description
input_config.fields Define the input parameters required for workflow execution, and the front end will automatically generate a form based on these definitions:
- name: Parameter name (key passed to the backend, such as ticker / analysis_date / analysis_target)
- label: form display label
- type: Control type, optional values: string (single line text)/textarea (multiple lines of text)/number (number)/boolean (switch)/date (date)/select (drop-down single selection)/multiselect (drop-down multiple selection)
- required: Is it required?
- default: Default value (null means no default value)
- description: Parameter description/tips
- placeholder: Input box placeholder prompt
- options: Option list (only used for select/multiselect, fill in null for other types)
- option_labels: Option display name (one-to-one correspondence with options, allowing users to see more friendly option names)
- min/max: Numeric range (only used by number type, fill in null for other types)
- group: grouping labels (e.g."Basic parameters"/"Advanced parameters", Parameters in the same group will be displayed together)
- order: Sorting number (the smaller the number, the higher it is)

Examples of input_config for different workflow types:
- Stock analysis:ticker(string,Required) / analysis_date(date) / research_depth(select) / quick_analysis_model(string) / deep_analysis_model(string)
- General research:analysis_target(textarea,Required) / research_depth(select) / quick_analysis_model(select) / deep_analysis_model(select) + Custom parameters specific to this process
- ETF Analysis:ticker(string,Required) / analysis_date(date) / research_depth(select)
- Position analysis:portfolio_data(textarea,Required) / analysis_date(date)

## conditional branch
When user requirements contain conditional logic (e.g."if...then...else...") , Use conditional edges:
- The edge type is set to "conditional"
- condition set to "true" or "false"
- The two edges starting from the conditional node are labeled true and false
- Write a judgment expression in the condition_expr field of the condition node

Example:
Node: check_risk(CONDITION type,condition_expr: "state.get('risk_score', 0) > 80") 
Side:check_risk -> deep_analysis (type: conditional, condition: "true") 
Side:check_risk -> simple_decision (type: conditional, condition: "false") 

## Important rules
1. Output only a JSON object, do not add markdown code block tags or other text
2. All agent_ids must be an exact copy, verbatim, of the IDs in the list of available resources, including `_v2`/`_v1` suffixes, abbreviations or omissions are prohibited
3. Node locations are laid out from top to bottom, and parallel nodes are distributed horizontally.
4. agent_reshaping Only contains prompt words that need to be customized Agent
5. agents_using_default Contains the use of default prompt words Agent
6. agent_reshaping In reshaping_direction, you only need to write one sentence to briefly describe the customization direction, do not write the complete prompt word
7. key_focus_areas Just list 3-6 key analysis dimensions
8. agent_reshaping Each entry in must contain node_id, which is consistent with the id field of the corresponding node in the nodes array.
9. The same agent_id can appear on multiple nodes. In this case, each node requires a separate agent_reshaping entry (different node_id, different customization direction)
10. There is no need to fill in available_agents / available_tools / missing_skills, the system will automatically complete the tool matching
11. agent_reshaping The additional_tools field in (optional): When the Agent s analysis tasks require special tools and there are no corresponding tools in the available resources, list the names of these tools (snake_case naming). Omit this field if the tools in the available resources adequately cover the analysis needs
12. input_config.fields All input parameters required for execution of the workflow must be listed, and the name of each parameter must be consistent with the field name used in the back-end code (such as ticker / analysis_date / analysis_target)
13. For common research processes (workflow_type=general) , At least include analysis_target(textarea, Required) parameters
14. For the stock analysis process, at least ticker (string, Required) parameters
15. input_config.fields Can be an empty array (meaning no additional input parameters are required)"""

# ── Optimization stage System Prompt ──────────────────────────────────────────────

SYSTEM_PROMPT_OPTIMIZE = """\
You are an AI workflow architect. The user has created a workflow, run it, and now provides feedback.
Please make optimization suggestions based on feedback.

## Current workflow blueprint
{blueprint_summary}

## User feedback
{feedback}

## Available resources
{resource_context}

Please analyze the problem and give specific optimization suggestions, including:
1. Structural adjustment (adding, deleting, or modifying nodes or connections)
2. Prompt word adjustment (which Agents need to modify the prompt word)
3. Tool adjustment (whether new tools are needed)

Use natural language descriptions, do not output JSON.
"""

MAX_DIALOGUE_ROUNDS = 10


class WorkflowPlanner:
    """
    Workflow planner

    core scheduling: LLM Driven three-stage workflow design
    1. dialogue stage — Multiple rounds of communication to understand needs
    2. blueprint stage — Output structured JSON
    3. Optimization stage — Adjust based on feedback
    """

    def __init__(self, llm_client: Optional[UnifiedLLMClient] = None):
        self._llm_client = llm_client
        # Structured list of available Agents (id/name/description/category/source),
        # by ResourceCollector.collect_all() Provided for whitelist verification in the blueprint stage.
        self._available_agents: List[Dict[str, Any]] = []
        # 🛡️ Retry counter: records the total number of retries triggered by agent_id illusion when generating blueprints (used to monitor LLM quality)
        self._hallucination_retry_count: int = 0

    def set_available_agents(self, agents: List[Dict[str, Any]]) -> None:
        """
        Inject a structured list of available Agents (for post-whitelist verification)

        Injected by workflow_generation_service before calling chat/generate_blueprint.
        """
        self._available_agents = list(agents or [])

    @property
    def available_agent_ids(self) -> set:
        """Legal agent_id set (whitelist)"""
        return {a.get("id") for a in self._available_agents if a.get("id")}

    # ── stage 1: dialogue ────────────────────────────────────────────────

    def chat(
        self,
        session: WorkflowGenerationSession,
        user_message: str,
        resource_context: str,
    ) -> Tuple[WorkflowGenerationSession, str]:
        """
        Process user messages and advance conversations

        The conversation included:
        - Workflow structure suggestions
        - Gap analysis (whether the Agent role needs to be reshaped, whether tools are missing)
        - Prompt word evaluation (which Agents need customized prompt words)

        Args:
            session: current session
            user_message: User messages
            resource_context: ResourceCollector Generated resource context text

        Returns:
            (Updated session, AI Reply to message)
        """
        if not self._llm_client:
            raise RuntimeError("LLM The client is not initialized, please set it first llm_client")

        # 🔍 Debugging: Print the currently available Agent whitelist
        whitelist_ids = sorted(self.available_agent_ids)
        logger.info(
            f"📋 [WorkflowPlanner.chat] whitelist Agent ({len(whitelist_ids)} a): "
            f"{whitelist_ids}"
        )

        # Build message history
        messages = self._build_chat_messages(session, user_message, resource_context)

        # call LLM
        try:
            response = self._llm_client.chat(messages)
            ai_message = response.content or "Sorry, the AI is temporarily unable to reply, please try again."
        except Exception as e:
            logger.error(f"[WorkflowPlanner] LLM call failed: {e}", exc_info=True)
            ai_message = f"AI call failed: {e}"

        # update session
        session.current_round += 1
        session.rounds.append(ConversationRound(
            round_num=session.current_round,
            user_message=user_message,
            ai_message=ai_message,
            phase="gathering",
            timestamp=datetime.utcnow(),
        ))
        session.updated_at = datetime.utcnow()

        # 🔍 Debugging: Check if the LLM reply contains something that is not in the whitelist agent_id
        mentioned_ids = set(re.findall(r'\b([a-z_]+_v[12]|[a-z_]+_analyst|[a-z_]+_assistant[a-z0-9_]*)\b', ai_message))
        whitelist_set = self.available_agent_ids
        hallucinated_in_chat = mentioned_ids - whitelist_set
        if hallucinated_in_chat:
            logger.warning(
                f"⚠️ [WorkflowPlanner.chat] LLM The reply mentioned that it is not in the whitelist agent_id: "
                f"{sorted(hallucinated_in_chat)}"
            )

        return session, ai_message

    def _build_chat_messages(
        self,
        session: WorkflowGenerationSession,
        user_message: str,
        resource_context: str,
    ) -> List[Message]:
        """Build LLM message list for conversation phase"""
        messages: List[Message] = []

        # System prompt (Contains resource context)
        system_content = SYSTEM_PROMPT_CHAT.format(resource_context=resource_context)
        messages.append(Message(role="system", content=system_content))

        # historical dialogue
        for r in session.rounds:
            if r.user_message:
                messages.append(Message(role="user", content=r.user_message))
            if r.ai_message:
                messages.append(Message(role="assistant", content=r.ai_message))

        # Current user message
        messages.append(Message(role="user", content=user_message))

        return messages

    # ── stage 2: Blueprint generation ────────────────────────────────────────────

    def generate_blueprint(
        self,
        session: WorkflowGenerationSession,
        resource_context: str,
    ) -> Tuple[WorkflowGenerationSession, Optional[WorkflowBlueprint]]:
        """
        Generate a complete WorkflowBlueprint based on conversation history (including gap analysis + prompt word evaluation)

        Called after the user confirms the scheme, asking LLM to output structured JSON.

        Args:
            session: Current conversation (should contain at least 1 round of dialogue)
            resource_context: resource context

        Returns:
            (Updated session, WorkflowBlueprint or None)
        """
        if not self._llm_client:
            raise RuntimeError("LLM The client is not initialized, please set it first llm_client")

        session.status = GenerationSessionStatus.PLANNING
        session.updated_at = datetime.utcnow()

        # 🔍 Debugging: Print the Agent whitelist when generating blueprints
        whitelist_ids = sorted(self.available_agent_ids)
        logger.info(
            f"📋 [WorkflowPlanner.generate_blueprint] whitelist Agent ({len(whitelist_ids)} a): "
            f"{whitelist_ids}"
        )

        # Splice conversation history
        conversation_history = self._format_conversation_history(session)

        # 1st generation
        blueprint = self._call_llm_for_blueprint(conversation_history, resource_context, None)

        # 🛡️ If agent_id hallucination is detected, retry 1 time after injecting suggestions
        if (
            blueprint is not None
            and self._available_agents
            and blueprint._invalid_agent_ids
        ):
            invalid_map = dict(blueprint._invalid_agent_ids)
            retry_hint = self._build_retry_hint(invalid_map)
            self._hallucination_retry_count += 1
            logger.info(
                f"🔁 [WorkflowPlanner] detected {len(invalid_map)} hallucination agent_id,"
                f"Legal replacement has been automatically suggested and retried 1 times (cumulative retries: {self._hallucination_retry_count}) "
            )
            retry_bp = self._call_llm_for_blueprint(
                conversation_history, resource_context, retry_hint
            )
            if retry_bp is not None:
                blueprint = retry_bp

        if blueprint:
            session.blueprint = blueprint
            session.status = GenerationSessionStatus.BLUEPRINT_READY
            logger.info(
                f"[WorkflowPlanner] Blueprint generated successfully: {blueprint.name}, "
                f"node={len(blueprint.nodes)}, side={len(blueprint.edges)}"
            )
        else:
            session.status = GenerationSessionStatus.GATHERING
            session.error = "Blueprint JSON parsing failed, please continue the conversation to complete the requirements"
            logger.warning("[WorkflowPlanner] Blueprint JSON parsing failed")

        session.updated_at = datetime.utcnow()
        return session, session.blueprint

    def _call_llm_for_blueprint(
        self,
        conversation_history: str,
        resource_context: str,
        retry_hint: Optional[str],
    ) -> Optional[WorkflowBlueprint]:
        """Call LLM to generate a blueprint and parse it, optionally adding a retry prompt"""
        system_content = SYSTEM_PROMPT_BLUEPRINT.format(
            conversation_history=conversation_history,
            resource_context=resource_context,
        )
        messages: List[Message] = [Message(role="system", content=system_content)]
        if retry_hint:
            messages.append(Message(
                role="user",
                content=(
                    "The blueprint generated in the previous round contains a non-existent agent_id. Please replace it with the legal ID suggested below and re-output the complete JSON.\n"
                    f"{retry_hint}\n\n"
                    "Please output the complete workflow blueprint JSON."
                ),
            ))
        else:
            messages.append(Message(role="user", content="Please generate the complete workflow blueprint JSON based on the conversation history above."))

        try:
            response = self._llm_client.chat(messages)
            raw_content = response.content or ""
            logger.debug(f"[WorkflowPlanner] LLM Original return content (length={len(raw_content)}) ")
            return self._parse_blueprint_json(raw_content)
        except Exception as e:
            logger.error(f"[WorkflowPlanner] LLM call failed: {e}", exc_info=True)
            return None

    def _build_retry_hint(self, invalid_map: Dict[str, str]) -> str:
        """Construct retry prompt: illegal listing ID → Recommended mapping of legal IDs"""
        lines = ["## ⚠️ agent_id illusion that must be corrected"]
        for bad, good in invalid_map.items():
            if good:
                lines.append(f"- ❌ `{bad}` does not exist → ✅ Please change to `{good}`")
            else:
                lines.append(
                    f"- ❌ `{bad}` does not exist → There is no completely equivalent Agent in the list, please select the closest one from [Available Agents]"
                )
        # emphasize"You must choose from the list above"
        lines.append("")
        lines.append(
            "**important**: agent_id You must strictly use the IDs listed in [Available Agents] above."
            "It is prohibited to make up or associate any ID that is not on the list."
        )
        return "\n".join(lines)

    def _format_conversation_history(self, session: WorkflowGenerationSession) -> str:
        """Format conversation history as text"""
        lines = []
        for r in session.rounds:
            lines.append(f"User: {r.user_message}")
            lines.append(f"AI: {r.ai_message}")
            lines.append("")
        return "\n".join(lines)

    def _parse_blueprint_json(self, raw: str) -> Optional[WorkflowBlueprint]:
        """
        Extract and parse blueprints from LLM output JSON

        Try multiple strategies to extract JSON:
        1. Directly parse the entire text
        2. Extract ```json ... ``` code block
        3. Extract the first { ... } object
        """
        json_str = raw.strip()

        # Strategy 1: Direct analysis
        data = self._try_parse_json(json_str)

        # Strategy 2: Extract markdown code blocks
        if data is None:
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", json_str, re.DOTALL)
            if match:
                data = self._try_parse_json(match.group(1).strip())

        # Strategy 3: Extract the first complete JSON object
        if data is None:
            brace_start = json_str.find("{")
            if brace_start >= 0:
                # Find the last matching }
                depth = 0
                for i in range(brace_start, len(json_str)):
                    if json_str[i] == "{":
                        depth += 1
                    elif json_str[i] == "}":
                        depth -= 1
                        if depth == 0:
                            data = self._try_parse_json(json_str[brace_start:i + 1])
                            break

        if data is None:
            logger.warning(f"[WorkflowPlanner] Unable to extract JSON from LLM output, length={len(json_str)}")
            return None

        return self._build_blueprint_from_dict(data)


    @staticmethod
    def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
        """Try to parse JSON and return if failed None"""
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _build_blueprint_from_dict(self, data: Dict[str, Any]) -> Optional[WorkflowBlueprint]:
        """Convert parsed dict to WorkflowBlueprint object"""
        try:
            # parse node
            nodes = []
            for nd in data.get("nodes", []):
                nodes.append(PlannedNode(
                    id=nd.get("id", ""),
                    type=nd.get("type", ""),
                    agent_id=nd.get("agent_id"),
                    label=nd.get("label", ""),
                    position_x=nd.get("position_x", 0),
                    position_y=nd.get("position_y", 0),
                    config=nd.get("config", {}),
                    description=nd.get("description", ""),
                ))

            # parse edge
            edges = []
            for ed in data.get("edges", []):
                edges.append(PlannedEdge(
                    id=ed.get("id", ""),
                    source=ed.get("source", ""),
                    target=ed.get("target", ""),
                    label=ed.get("label"),
                    animated=ed.get("animated", False),
                ))

            # Analytic Gap Analysis (provided by LLM agent_reshaping + agents_using_default, 
            # available_tools / missing_skills Populated by subsequent CapabilityIndex searches)
            gap_data = data.get("gap_analysis")
            agent_reshaping_raw = data.get("agent_reshaping", [])
            agents_using_default_raw = data.get("agents_using_default", [])
            analysis_summary = data.get("analysis_summary", "")

            # Compatible with old formats: if there is gap_analysis nested, extract it from it
            if gap_data and isinstance(gap_data, dict):
                if not agent_reshaping_raw:
                    agent_reshaping_raw = gap_data.get("agent_reshaping", [])
                if not agents_using_default_raw:
                    agents_using_default_raw = gap_data.get("agents_using_default", [])
                if not analysis_summary:
                    analysis_summary = gap_data.get("analysis_summary", "")

            reshaping_fields = set(AgentReshapingPlan.__fields__.keys())
            reshaping = [
                AgentReshapingPlan(**{k: v for k, v in r.items() if k in reshaping_fields})
                for r in agent_reshaping_raw
            ]

            gap_analysis = GapAnalysisResult(
                agent_reshaping=reshaping,
                agents_using_default=agents_using_default_raw,
                missing_skills=[],  # Populated by CapabilityIndex search
                available_agents=[],  # Populated by CapabilityIndex search
                available_tools=[],  # Populated by CapabilityIndex search
                analysis_summary=analysis_summary,
            )

            blueprint = WorkflowBlueprint(
                name=data.get("name", ""),
                description=data.get("description", ""),
                tags=data.get("tags", []),
                nodes=nodes,
                edges=edges,
                config=data.get("config", {}),
                input_config=data.get("input_config") or {"fields": []},
                summary=data.get("summary", ""),
                rationale=data.get("rationale", ""),
                gap_analysis=gap_analysis,
            )

            # Calculate creation progress
            if gap_analysis:
                blueprint.creation_progress = {
                    "skills_total": len(gap_analysis.missing_skills),
                    "skills_completed": 0,
                    "prompts_total": len(gap_analysis.agent_reshaping),
                    "prompts_completed": 0,
                    "workflow_created": False,
                }

            # 🛡️ Anti-hallucination: agent_id whitelist verification (refer to the agent workshop gap_analysis method)
            if self._available_agents:
                self._enforce_agent_whitelist(blueprint)

            return blueprint

        except Exception as e:
            logger.error(f"[WorkflowPlanner] Blueprint structure parsing failed: {e}", exc_info=True)
            return None

    # ── stage 2.5: Anti-hallucination whitelist verification ────────────────────────────────

    def _enforce_agent_whitelist(self, blueprint: WorkflowBlueprint) -> None:
        """
        To perform whitelist verification on the agent_id in the blueprint, refer to the agent workshop gap_analysis anti-hallucination logic.

        Verification range:
        - nodes[].agent_id      — Runtime execution nodes, hallucinations can cause runtime crashes
        - agent_reshaping[].agent_id — Prompt word generation target, hallucination will generate isolated prompt word resources

        Behavior:
        1. nodes illegal in agent_id → Set to None (the node becomes an Agent-less placeholder node)
        2. agent_reshaping illegal in agent_id → record warning + Keep the original value (not blocked, handled by PromptGenerator itself)
        3. Record to blueprint._invalid_agent_ids to facilitate retry by the upper layer
        """
        whitelist = self.available_agent_ids
        invalid_map: Dict[str, str] = {}  # invalid_id -> Suggestions are legal ID

        # 1. Verification nodes[].agent_id
        for node in blueprint.nodes:
            if not node.agent_id:
                continue
            if node.agent_id in whitelist:
                continue
            # agent_id illegal
            suggested = self._suggest_similar_agent(node.agent_id)
            invalid_map[node.agent_id] = suggested or ""
            logger.warning(
                f"🛡️ [WorkflowPlanner] LLM hallucination agent_id filtered (node): "
                f"node_id={node.id}, agent_id='{node.agent_id}', "
                f"It is recommended to replace with='{suggested or '(None)'}', "
                f"Node type={node.type}"
            )
            # Empty the illegal agent_id and let AgentFactory take the lead (to avoid crashes when the agent cannot be found during runtime)
            node.agent_id = None

        # 2. Verification agent_reshaping[].agent_id (Prompt word generation target)
        if blueprint.gap_analysis and blueprint.gap_analysis.agent_reshaping:
            for plan in blueprint.gap_analysis.agent_reshaping:
                if not plan.agent_id or plan.agent_id in whitelist:
                    continue
                suggested = self._suggest_similar_agent(plan.agent_id)
                logger.warning(
                    f"🛡️ [WorkflowPlanner] LLM hallucination agent_id tagged (agent_reshaping): "
                    f"agent_id='{plan.agent_id}', "
                    f"new_role='{plan.new_role}', "
                    f"It is recommended to replace with='{suggested or '(None)'}'"
                )
                if plan.agent_id not in invalid_map:
                    invalid_map[plan.agent_id] = suggested or ""

        # 3. Writing blueprint private properties (dynamic setattr is no longer used)
        if invalid_map:
            blueprint._invalid_agent_ids.update(invalid_map)

            # Write summary to inform the user which hallucinations are automatically filtered this time agent
            note = "\n\n> ⚠️ Automatic verification filters out non-existent Agent: " + ", ".join(
                f"`{bad}` → `{good or '(None)'}`" for bad, good in invalid_map.items()
            )
            if blueprint.summary:
                blueprint.summary = blueprint.summary + note
            else:
                blueprint.summary = note.lstrip("\n")

    def _suggest_similar_agent(self, invalid_id: str) -> Optional[str]:
        """
        Find the legal ID in the whitelist that is most similar to the invalid_id string (simple edit distance heuristic).
        """
        if not self._available_agents or not invalid_id:
            return None
        invalid_lower = invalid_id.lower().replace("-", "_")
        best_id: Optional[str] = None
        best_score = 0
        for a in self._available_agents:
            aid = a.get("id", "")
            if not aid:
                continue
            aid_lower = aid.lower()
            # 1) substring contains direct hit
            if invalid_lower in aid_lower or aid_lower in invalid_lower:
                return aid
            # 2) Simple word set similarity
            score = self._token_overlap(invalid_lower, aid_lower)
            if score > best_score:
                best_score = score
                best_id = aid
        # Add a lower limit to avoid mismatches
        if best_score >= 0.4:
            return best_id
        return None

    @staticmethod
    def _token_overlap(a: str, b: str) -> float:
        """Rough token overlap ratio: split by _ and - to find intersection/union"""
        import re as _re
        ta = {t for t in _re.split(r"[_\-]", a) if t}
        tb = {t for t in _re.split(r"[_\-]", b) if t}
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    # ── stage 3: iterative optimization ────────────────────────────────────────────

    def generate_optimization(
        self,
        session: WorkflowGenerationSession,
        feedback: str,
        resource_context: str,
    ) -> Tuple[WorkflowGenerationSession, str]:
        """
        Generate optimization suggestions based on user feedback

        Args:
            session: Current session (should already have blueprint and workflow_id)
            feedback: User feedback on running results
            resource_context: resource context

        Returns:
            (Updated session, AI Optimization suggestions)
        """
        if not self._llm_client:
            raise RuntimeError("LLM The client is not initialized, please set it first llm_client")

        # Build blueprint summary
        blueprint_summary = self._format_blueprint_summary(session.blueprint)

        # Build message
        system_content = SYSTEM_PROMPT_OPTIMIZE.format(
            blueprint_summary=blueprint_summary,
            feedback=feedback,
            resource_context=resource_context,
        )

        # Contains optimized conversation history
        messages: List[Message] = [Message(role="system", content=system_content)]
        for r in session.optimize_rounds:
            if r.user_message:
                messages.append(Message(role="user", content=r.user_message))
            if r.ai_message:
                messages.append(Message(role="assistant", content=r.ai_message))
        messages.append(Message(role="user", content=feedback))

        try:
            response = self._llm_client.chat(messages)
            ai_message = response.content or "Sorry, the AI is temporarily unable to reply, please try again."
        except Exception as e:
            logger.error(f"[WorkflowPlanner] Optimization suggestion generation failed: {e}", exc_info=True)
            ai_message = f"AI call failed: {e}"

        # update session
        session.optimize_count += 1
        session.optimize_rounds.append(ConversationRound(
            round_num=session.optimize_count,
            user_message=feedback,
            ai_message=ai_message,
            phase="optimizing",
            timestamp=datetime.utcnow(),
        ))
        session.status = GenerationSessionStatus.OPTIMIZING
        session.updated_at = datetime.utcnow()

        return session, ai_message

    @staticmethod
    def _format_blueprint_summary(blueprint: Optional[WorkflowBlueprint]) -> str:
        """Format blueprint as summary text"""
        if not blueprint:
            return "(No blueprint information)"

        lines = [
            f"**Name**: {blueprint.name}",
            f"**Description**: {blueprint.description}",
            f"**node**: {len(blueprint.nodes)} a",
        ]

        for n in blueprint.nodes:
            agent_info = f" ({n.agent_id})" if n.agent_id else ""
            lines.append(f"  - {n.id}: {n.label}{agent_info} [{n.type}]")

        lines.append(f"**side**: {len(blueprint.edges)} Article")
        for e in blueprint.edges:
            lines.append(f"  - {e.source} → {e.target}")

        if blueprint.gap_analysis:
            ga = blueprint.gap_analysis
            if ga.agent_reshaping:
                lines.append(f"**Prompt word customization**: {len(ga.agent_reshaping)} a Agent")
            if ga.agents_using_default:
                lines.append(f"**Use default prompt word**: {len(ga.agents_using_default)} a Agent")
            if ga.missing_skills:
                lines.append(f"**Missing tools**: {len(ga.missing_skills)} a")

        return "\n".join(lines)
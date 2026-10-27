"""
Analysis Planner

The planning logic to realize the three-level guarantee mechanism:
1. LLM Semantic matching seed process (most reliable)
2. LLM Autonomous planning based on tool list (more reliable)
3. Mark fallback to ReAct (guaranteed) when planning fails

Dependencies:
- core/agents/seed_flows.py — Seed process definition
- core/agents/planner_models.py — data model
- core/llm/unified_client.py — LLM call
- core/tools/registry.py — Tool registry
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

from core.llm import UnifiedLLMClient
from core.llm.models import Message, MessageRole
from core.tools import get_tool_registry

from .planner_models import AnalysisPlan, PlanSource, PlanStep
from .seed_flows import SeedFlow, list_seed_flows, get_seed_flow

logger = logging.getLogger(__name__)


# ============================================================
# Prompt Template
# ============================================================

def _build_seed_match_prompt(question: str, seed_flows: List[SeedFlow]) -> str:
    """Build seed process semantic matching prompt"""
    flow_list = "\n".join(
        f"{i + 1}. {sf.id}: {sf.description}"
        for i, sf in enumerate(seed_flows)
    )
    return f"""You are a stock analysis planner. The following are the available analysis templates:

{flow_list}

User questions:{question}

Please select the template number that best matches (1-{len(seed_flows)}) , If none of them match, return "none". 
Return only the number or "none", Don t explain."""


def _build_plan_prompt(
    question: str,
    tool_descriptions: str,
    curr_date: str,
    trade_date: str,
    knowledge_snippets: str = "",
) -> str:
    """Build LLM autonomous planning prompt

    Args:
        knowledge_snippets: RAG Retrieved dynamic knowledge fragments
    """
    # Build optional dynamic knowledge paragraphs
    knowledge_section = f"\n{knowledge_snippets}\n" if knowledge_snippets else ""

    return f"""You are a stock analysis planner. Develop a precise analysis plan based on user issues.

## Available tools

{tool_descriptions}

## Current date information
- current date: {curr_date}
- Last trading day: {trade_date}

## User issues
{question}
{knowledge_section}
## Important note
- This system only supports **A Stocks (Shanghai and Shenzhen Stock Exchanges)** Analysis of individual stocks and sectors
- **Not supported**: ETF, Funds, Hong Kong stocks, US stocks, etc.

## Financial Literacy - Question Classification and Recommended Tool Packages

**A. Section/Industry/Concept Category** (User asked"XX plate", "XX concept stocks", "XX Industry prospects") : 
- core tools: analyze_sector_by_name (One-stop comprehensive sector analysis, parameters sector_name=Sector keywords)
- Supplementary tools: get_sector_constituents (Check the leading constituent stocks), get_sector_daily (check the sector trend), search_sector (search the sector)
- Note: "XX concept stocks"Refers to the Flush concept section(S Type)Component stocks, use the sector tool to query, no need ticker

**B. Individual stock analysis** (User asked"XX How is the stock?", "Help me analyze XX") : 
- Fundamentals: get_stock_fundamentals_unified (PE/PB/ROE/financial data)
- Quotes: get_stock_market_data_unified (price movement/volume)
- technical aspect: get_technical_indicators (MACD/RSI/KDJ/BOLL) 
- news side: get_stock_news_unified (News)
- It is recommended to obtain fundamentals in parallel+Quotes+technical aspect+News

**C. Macro/Large Cap Category** (User asked"How is the market?", "market environment") : 
- Quick overview: get_china_market_overview or get_market_overview
- In-depth analysis: get_index_data + get_market_breadth + get_limit_stats
- Funding: get_north_flow (Northbound funds), get_margin_trading (two financings), get_fund_flow_data (sector fund flow)

**D. Contrast category** (User asked"XX Which one is better with YY?", "Comparison with the same industry") : 
- core tools: get_peer_comparison (Comparison with peers)
- supplement: get_stock_fundamentals_unified (Details of each company s fundamentals)

## request
1. Generate an analysis plan in JSON format
2. Each step must specify a specific tool (tool ID) and args (arguments)
3. **args Only the parameter names listed in the tool definition above can be used, and you cannot create your own parameters.**
4. Use depends_on to mark dependencies between steps (steps without dependencies can be executed in parallel)
5. intent Field briefly describes the purpose of this step
6. Keep the number of steps to 2-5
7. All parameters that require a date use the current date {curr_date} or trading day {trade_date}
8. **For sector/industry/conceptual questions, sector-level tools are preferred.** (analyze_sector_by_name etc.), they accept sector_name (sector name keyword) without ticker
9. Only use tools that require the ticker parameter when referring to specific stocks. The ticker must be a 6-digit stock code (such as 601012)
10. First determine which category of the above A/B/C/D the problem belongs to, and then select the corresponding recommended tool combination

## Output format (strictly JSON)
```json
{{
  "steps": [
    {{
      "id": 1,
      "tool": "Tools ID",
      "args": {{"Parameter name": "Parameter value"}},
      "intent": "step intention",
      "depends_on": []
    }}
  ]
}}
```

Return only JSON, no other text."""


def _build_tool_descriptions(tool_ids: Set[str]) -> str:
    """Build tool description list (used for planning prompts)"""
    registry = get_tool_registry()
    lines = []
    for meta in registry.list_all():
        if meta.id not in tool_ids:
            continue
        params = ", ".join(
            f"{p.name}({'required' if p.required else 'Optional'}): {p.description}"
            for p in meta.parameters
        )
        line = f"- **{meta.id}**: {meta.description}"
        if meta.when_to_use:
            line += f"\n  When to use: {meta.when_to_use}"
        if params:
            line += f"\n  parameters: {params}"
        lines.append(line)
    return "\n".join(lines)


def _build_simplified_tool_descriptions(tool_ids: Set[str]) -> str:
    """Build a simplified tool description (only ID + Description, used to fix the retry prompt)

    Fixed the problem that in the retry scenario, too detailed parameter description may cause LLM to fall into the trap again."Difficulty in parameter selection", 
    Therefore, only the tool ID and one-sentence description are exposed, allowing LLM to first"what tools to use"Choose the right layer.
    """
    registry = get_tool_registry()
    lines = []
    for meta in registry.list_all():
        if meta.id not in tool_ids:
            continue
        # Only keep the parameter name list (do not expand the description) to reduce prompt complexity
        param_names = ", ".join(p.name for p in meta.parameters) if meta.parameters else "None"
        lines.append(f"- {meta.id}: {meta.description} (parameters: {param_names}) ")
    return "\n".join(lines)


def _build_correction_plan_prompt(
    question: str,
    simplified_tool_desc: str,
    curr_date: str,
    trade_date: str,
    failure_hint: str = "",
) -> str:
    """Build fix retry prompt (v3.6.0 item 7)

    Difference from _build_plan_prompt:
    1. Number of steps limit tightened from 2-5 to 1-3 (reduced complexity)
    2. Remove the financial knowledge paragraph (to avoid LLM wasting tokens on classification)
    3. explicit prompt"The last planning failed", Encourage LLM to re-plan in the simplest way
    4. The tool description uses a simplified version (only ID + Description + parameter name)
    """
    hint_section = f"\n## Reason for last failure\n{failure_hint}\n" if failure_hint else ""

    return f"""The last planning failed, please try again in a simpler way.{hint_section}
## Available tools (simplified version)

{simplified_tool_desc}

## Current date information
- current date: {curr_date}
- Last trading day: {trade_date}

## User issues
{question}

## request
1. Generate an analysis plan in JSON format
2. The number of steps is controlled at **1-3 a** (Up to 3, simpler the better)
3. Prioritize the use of the most common tool combinations: fundamentals/markets/technical/news
4. Each step must specify a specific tool (tool ID) and args (arguments)
5. args Only the parameter names listed in the tool definition above can be used in
6. Use depends_on to mark dependencies between steps (steps without dependencies can be executed in parallel)
7. intent Field briefly describes the purpose of this step
8. All parameters that require a date use the current date {curr_date} or trading day {trade_date}
9. ticker Must be a 6-digit stock code (e.g. 601012)

## Output format (strictly JSON)
```json
{{
  "steps": [
    {{
      "id": 1,
      "tool": "Tools ID",
      "args": {{"Parameter name": "Parameter value"}},
      "intent": "step intention",
      "depends_on": []
    }}
  ]
}}
```

Return only JSON, no other text."""


# ============================================================
# Planner class
# ============================================================

class Planner:
    """
    Analysis Planner

    Implement three-level assurance planning logic:
      1. Seed process semantic matching
      2. LLM independent planning
      3. Flag ReAct fallback
    """

    def __init__(
        self,
        llm_client: UnifiedLLMClient,
        curr_date: str,
        trade_date: str,
    ):
        self._llm = llm_client
        self._curr_date = curr_date
        self._trade_date = trade_date

        # Collect available tool IDs (only fc_enabled with parameters)
        registry = get_tool_registry()
        self._valid_tool_ids: Set[str] = {
            m.id for m in registry.list_all()
            if m.fc_enabled and m.parameters
        }

    # ----------------------------------------------------------
    # public interface
    # ----------------------------------------------------------

    async def plan(
        self,
        question: str,
        context_messages: Optional[List[Message]] = None,
        knowledge_snippets: str = "",
    ) -> AnalysisPlan:
        """
        Generate analysis plan.

        Args:
            knowledge_snippets: RAG Retrieved dynamic knowledge fragments

        Returns:
            AnalysisPlan — If source == REACT_FALLBACK Indicates that planning failed and should be rolled back ReAct
        """
        # First level: Seed process semantic matching
        seed_plan = await self._try_seed_match(question, context_messages)
        if seed_plan is not None:
            logger.info(f"[Planner] Seed process matching successful: {seed_plan.template_id}")
            return seed_plan

        # Level 2: LLM independent planning
        llm_plan = await self._try_llm_plan(question, context_messages, knowledge_snippets)
        if llm_plan is not None:
            logger.info(f"[Planner] LLM Independent planning is successful,{len(llm_plan.steps)} steps")
            return llm_plan

        # Second level patch: planning failure fix retry 1 time (v3.6.0 item 7)
        # Retry generating a valid plan with a simpler prompt to avoid direct downgrade ReAct
        corrected_plan = await self._try_llm_plan_with_correction(question, context_messages)
        if corrected_plan is not None:
            logger.info(f"[Planner] Fixed retry planning success,{len(corrected_plan.steps)} steps")
            return corrected_plan

        # Level 3: Mark ReAct fallback
        logger.warning("[Planner] Planning failed (including corrective retry), marked ReAct rollback")
        return AnalysisPlan(
            question=question,
            source=PlanSource.REACT_FALLBACK,
            steps=[],
        )

    # ----------------------------------------------------------
    # First level: Seed process semantic matching
    # ----------------------------------------------------------

    async def _try_seed_match(
        self,
        question: str,
        context_messages: Optional[List[Message]] = None,
    ) -> Optional[AnalysisPlan]:
        """Use LLM semantics to match the seed process, and fill in the template parameters if the match is successful."""
        seed_flows = list_seed_flows()
        if not seed_flows:
            return None

        prompt = _build_seed_match_prompt(question, seed_flows)
        messages: List[Message] = []
        if context_messages:
            messages.extend(context_messages)
        messages.append(Message(role=MessageRole.USER, content=prompt))

        try:
            resp = await self._llm.achat(messages)
            answer = (resp.content or "").strip().lower()
            logger.info(f"[Planner] Seed match LLM return: {answer}")

            # parse return value
            if answer == "none" or not answer:
                return None

            # Extract numbers
            match = re.search(r"(\d+)", answer)
            if not match:
                return None

            idx = int(match.group(1)) - 1
            if idx < 0 or idx >= len(seed_flows):
                return None

            selected = seed_flows[idx]
            return await self._fill_seed_flow_async(question, selected)

        except Exception as e:
            logger.warning(f"[Planner] Seed matching failed: {e}")
            return None

    def _fill_seed_flow(self, question: str, flow: SeedFlow) -> AnalysisPlan:
        """Populate the seed process template with specific AnalysisPlan"""
        ticker = self._extract_ticker(question)
        sector_name = self._extract_sector_name(question)

        steps: List[PlanStep] = []
        for i, seed_step in enumerate(flow.steps):
            args = {}
            for k, v in seed_step.args_template.items():
                args[k] = (
                    v.replace("{ticker}", ticker)
                    .replace("{curr_date}", self._curr_date)
                    .replace("{trade_date}", self._trade_date)
                    .replace("{sector_name}", sector_name)
                )
            # depends_on Convert from 0-based to 1-based step id
            deps = [d + 1 for d in seed_step.depends_on]
            steps.append(PlanStep(
                id=i + 1,
                tool=seed_step.tool,
                args=args,
                intent=seed_step.intent,
                depends_on=deps,
            ))

        return AnalysisPlan(
            question=question,
            template_id=flow.id,
            source=PlanSource.SEED_FLOW,
            steps=steps,
        )

    async def _fill_seed_flow_async(self, question: str, flow: SeedFlow) -> AnalysisPlan:
        """Fill the seed process template with a specific AnalysisPlan (asynchronous version, supports LLM to extract ticker and section name)"""
        ticker = self._extract_ticker(question)

        # If simple extraction fails, use LLM extraction
        if not ticker:
            ticker = await self._extract_ticker_by_llm(question)
            logger.info(f"[Planner] LLM Extract ticker: '{ticker}'")

        # Extract section name (for {sector_name} placeholder)
        sector_name = self._extract_sector_name(question)
        logger.info(f"[Planner] Extract sector_name: '{sector_name}'")

        steps: List[PlanStep] = []
        for i, seed_step in enumerate(flow.steps):
            args = {}
            for k, v in seed_step.args_template.items():
                args[k] = (
                    v.replace("{ticker}", ticker)
                    .replace("{curr_date}", self._curr_date)
                    .replace("{trade_date}", self._trade_date)
                    .replace("{sector_name}", sector_name)
                )
            deps = [d + 1 for d in seed_step.depends_on]
            steps.append(PlanStep(
                id=i + 1,
                tool=seed_step.tool,
                args=args,
                intent=seed_step.intent,
                depends_on=deps,
            ))

        return AnalysisPlan(
            question=question,
            template_id=flow.id,
            source=PlanSource.SEED_FLOW,
            steps=steps,
        )

    @staticmethod
    def _extract_sector_name(question: str) -> str:
        """
        Extract the sector/industry name from the question.
        Rules:
        - match "XX plate", "XX Industry", "XX concept", "XX Industry" in XX
        - Also matches common sector keywords
        """
        # First try to match known sector keywords + Suffix mode (more precise)
        known_sectors = [
            "photovoltaic", "solar energy", "new energy", "Lithium battery", "Lithium battery", "energy storage",
            "Semiconductor", "chip", "integrated circuit", "consumer electronics",
            "Liquor", "food and beverage", "Medicine", "biomedicine", "Chinese medicine",
            "artificial intelligence", "AI", "large model", "Computing power", "data center",
            "New energy vehicles", "Intelligent driving", "Auto parts",
            "real estate", "architecture", "Building materials", "steel", "Coal", "colored",
            "bank", "securities", "insurance", "Finance",
            "Military industry", "national defense", "aerospace", "ship",
            "Agriculture", "Breeding", "Seed industry",
            "5G", "communication", "Internet of Things",
            "robot", "Industrial mother machine", "High-end equipment",
        ]
        # Prioritize matching of known section names (from long to short to avoid mismatching short names)
        for sector in sorted(known_sectors, key=len, reverse=True):
            if sector in question:
                return sector

        # match "XX plate", "XX Industry", "XX concept", "XX Industry" mode
        # Use {1,6} Limit the length to avoid greedy matching of too many Chinese characters
        patterns = [
            r"([\u4e00-\u9fa5A-Za-z0-9]{1,6})\s*(?:plate|Industry|concept|Industry|track|field)",
            r"(?:plate|Industry|concept|Industry|track|field)\s*([\u4e00-\u9fa5A-Za-z0-9]{1,6})",
        ]
        for p in patterns:
            m = re.search(p, question)
            if m:
                return m.group(1).strip()

        # If there is no match, use the core keywords of the entire question
        # Remove common question words and modifiers
        q = re.sub(r"(help me|analysis|take a look|What are there|How is it|how|Recently|investment|opportunity|Worth it|Follow|Recommended|what|Which|Excuse me)", "", question)
        q = q.strip()
        if 2 <= len(q) <= 8:
            return q

        return question[:8] if question else ""

    @staticmethod
    def _extract_ticker(question: str) -> str:
        """
        Extract the stock symbol from the question.
        Simple rule: match 6 digits. If no match is found, an empty string is returned.
        """
        match = re.search(r"\b(\d{6})\b", question)
        return match.group(1) if match else ""

    async def _extract_ticker_by_llm(self, question: str) -> str:
        """
        Extract or infer stock symbols from problems using LLM.
        Support:
        - Chinese stock name → code (such as"Moutai" → "600519") 
        - Sector/industry name → Leading stock code (such as"Photovoltaic sector" → "601012") 
        """
        prompt = f"""Extract the most relevant A-share stock code (6 digits) from the following user questions.

Rules:
- If the question mentions a specific stock name (e.g."Moutai", "BYD") , Return the stock code
- If the question mentions a sector or industry (e.g."Photovoltaic sector", "Semiconductor", "new energy") , Returns the most representative leading stock code in the sector
- If unsure, return "000001" (Ping An Bank, as default)

References to common sector leaders:
- Photovoltaic/Solar: 601012 (Longi Green Energy)
- New energy vehicles: 002594 (BYD)
- Liquor: 600519 (Kweichow Moutai)
- Semiconductor/chip: 002371 (Northern Huachuang)
- artificial intelligence/AI: 002230 (iFlytek)
- Lithium battery: 300750 (Ningde era)
- Medicine: 600276 (Hengrui Medicine)
- bank: 601398 (Industrial and Commercial Bank of China)
- real estate: 001979 (China Merchants Shekou)
- Brokerage firm: 601211 (Guotai Junan)

User questions:{question}

Only return the 6-digit stock code, no other text."""

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            resp = await self._llm.achat(messages)
            raw = (resp.content or "").strip()
            # Extract 6 digits
            match = re.search(r"(\d{6})", raw)
            if match:
                return match.group(1)
        except Exception as e:
            logger.warning(f"[Planner] LLM Failed to extract ticker: {e}")

        return "000001"  # Default value

    # ----------------------------------------------------------
    # Level 2: LLM independent planning
    # ----------------------------------------------------------

    async def _try_llm_plan(
        self,
        question: str,
        context_messages: Optional[List[Message]] = None,
        knowledge_snippets: str = "",
    ) -> Optional[AnalysisPlan]:
        """Let LLM generate a complete plan based on the tool list"""
        tool_desc = _build_tool_descriptions(self._valid_tool_ids)
        prompt = _build_plan_prompt(
            question=question,
            tool_descriptions=tool_desc,
            curr_date=self._curr_date,
            trade_date=self._trade_date,
            knowledge_snippets=knowledge_snippets,
        )

        messages: List[Message] = [
            Message(role=MessageRole.SYSTEM, content="You are a professional stock analysis planner that only outputs JSON."),
        ]
        if context_messages:
            messages.extend(context_messages)
        messages.append(Message(role=MessageRole.USER, content=prompt))

        try:
            resp = await self._llm.achat(messages)
            raw = resp.content or ""
            plan_data = self._parse_plan_json(raw)
            if plan_data is None:
                return None

            steps = self._validate_steps(plan_data.get("steps", []))
            if not steps:
                return None

            return AnalysisPlan(
                question=question,
                template_id=None,
                source=PlanSource.LLM_PLAN,
                steps=steps,
            )

        except Exception as e:
            logger.warning(f"[Planner] LLM Planning failed: {e}")
            return None

    async def _try_llm_plan_with_correction(
        self,
        question: str,
        context_messages: Optional[List[Message]] = None,
        failure_hint: str = "",
    ) -> Optional[AnalysisPlan]:
        """Fix retry planning (v3.6.0 item 7)

        Called after _try_llm_plan returns None, try again using a simpler prompt:
        - The number of steps is limited to 1-3
        - Tool description only retains ID + Description + Parameter name
        - explicit prompt"The last planning failed"

        Failure hint is optional and is used to help LLM understand why it failed last time (e.g."Not returned valid JSON", "Step is empty") . 
        """
        simplified_tool_desc = _build_simplified_tool_descriptions(self._valid_tool_ids)
        prompt = _build_correction_plan_prompt(
            question=question,
            simplified_tool_desc=simplified_tool_desc,
            curr_date=self._curr_date,
            trade_date=self._trade_date,
            failure_hint=failure_hint,
        )

        messages: List[Message] = [
            Message(
                role=MessageRole.SYSTEM,
                content="You are a stock analysis planner. The last planning failed. Please use the simplest way to plan again and only output JSON.",
            ),
        ]
        if context_messages:
            messages.extend(context_messages)
        messages.append(Message(role=MessageRole.USER, content=prompt))

        try:
            resp = await self._llm.achat(messages)
            raw = resp.content or ""
            plan_data = self._parse_plan_json(raw)
            if plan_data is None:
                # _parse_plan_json Specific reasons have been documented (JSON not found/JSON parsing exception/invalid structure)
                return None

            steps = self._validate_steps(plan_data.get("steps", []))
            if not steps:
                logger.warning("[Planner] Fixed retry: steps are empty or all invalid")
                return None

            # The tag source is LLM_PLAN (fixed retry success plans are treated the same as normal LLM plans)
            return AnalysisPlan(
                question=question,
                template_id=None,
                source=PlanSource.LLM_PLAN,
                steps=steps,
            )

        except Exception as e:
            logger.warning(f"[Planner] Fixed retry planning failure: {e}")
            return None

    @staticmethod
    def _parse_plan_json(raw: str) -> Optional[Dict[str, Any]]:
        """Parse from LLM output JSON"""
        # Try to extract ```json ... ``` block
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        text = json_match.group(1).strip() if json_match else raw.strip()

        # Try to find the JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            logger.warning("[Planner] JSON object not found")
            return None

        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            logger.warning(f"[Planner] JSON Parsing failed: {e}")
            return None

    def _validate_steps(self, raw_steps: List[Dict[str, Any]]) -> List[PlanStep]:
        """Verify and convert the step list to filter out illegal steps"""
        valid: List[PlanStep] = []
        for s in raw_steps:
            tool_id = s.get("tool", "")
            if tool_id not in self._valid_tool_ids:
                logger.warning(f"[Planner] Tools '{tool_id}' Not in the registry, skip")
                continue
            try:
                step = PlanStep(
                    id=s.get("id", len(valid) + 1),
                    tool=tool_id,
                    args=s.get("args", {}),
                    intent=s.get("intent", ""),
                    depends_on=s.get("depends_on", []),
                )
                valid.append(step)
            except Exception as e:
                logger.warning(f"[Planner] Step verification failed: {e}")
        return valid


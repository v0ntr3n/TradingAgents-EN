"""
Risk Self Debate Analyst v2.0 (A9-P1)

Complete the position statement and cross-examination from the three risk review perspectives of high elasticity/defense/baseline within a single node.
Alternative risk triangle (risky/safe/neutral_analyst_v2) multiple rounds of debate,
Changed LLM calls for deep/full profile risk debate sessions from rounds×3 times reduced to 1 time.

Design points:
- only if state["_risk_self_debate"]=True (depth/full range and the switch is on) is routed to,
  The fast/basic/standard files continue to follow the original risk triangle multi-agent path without affecting each other.
- The output is fully compatible with the original risk triangle:
  * risky_opinion / safe_opinion / neutral_opinion Three state fields
  * risk_debate_state structure (histories / current_*_response / count) 
  Render layer has zero changes from risk_manager_v2.
- Parse LLM output through three-part markup; when parsing fails, the full text is downgraded and filled to ensure that the field is not empty.
"""

import logging
import re
from typing import Any, Dict, List, Tuple

from langchain_core.messages import SystemMessage, HumanMessage

from ..researcher import ResearcherAgent
from ..registry import register_agent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput

logger = logging.getLogger(__name__)

# Three-perspective section markers (for output parsing, the order is the expected output order)
_SECTION_LABELS: Tuple[str, str, str] = ("Highly resilient scenario perspective", "defensive situational view", "base case view")

# Strict mode: Markers occupy one line ([X]/ ## X / **X** and other variants)
_MARKER_STRICT_RE = re.compile(
    r"(?m)^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*)?[【\[]?\s*"
    r"(Highly resilient scenario perspective|defensive situational view|base case view)"
    r"\s*[】\]]?(?:\*\*)?[ \t]*[:：]?\s*$"
)

# Relaxed mode: mark at the beginning of the line, allow peers and content (enabled when strict mode parsing fails)
_MARKER_LOOSE_RE = re.compile(
    r"(?m)^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*)?[【\[]?\s*"
    r"(Highly resilient scenario perspective|defensive situational view|base case view)"
    r"\s*[】\]]?(?:\*\*)?[ \t]*[:：]?"
)


def _extract_sections(text: str, marker_re: re.Pattern) -> Dict[str, str]:
    """Split text by mark and return {label: Section content} (Only the first occurrence of each tag is taken)"""
    matches = list(marker_re.finditer(text))
    sections: Dict[str, str] = {}
    for i, m in enumerate(matches):
        label = m.group(1)
        if label in sections:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[label] = text[start:end].strip()
    return sections


def parse_self_debate_response(response: str) -> Tuple[str, str, str]:
    """
    The output of parsing self-argument is (risky, safe, neutral) Three paragraphs of opinion.

    Parsing strategy: strict (marks occupy one line)→ Loose (peer content)→ Full text downgraded.
    When downgrading the full text, three fields are filled with complete output to ensure downstream risk_manager and report rendering.
    Get non-empty content (a guaranteed behavior in extreme cases, it will not be triggered normally).
    """
    if not response or not response.strip():
        return "", "", ""

    sections = _extract_sections(response, _MARKER_STRICT_RE)
    if len(sections) < 3:
        sections = _extract_sections(response, _MARKER_LOOSE_RE)

    risky = sections.get(_SECTION_LABELS[0], "")
    safe = sections.get(_SECTION_LABELS[1], "")
    neutral = sections.get(_SECTION_LABELS[2], "")

    if risky and safe and neutral:
        return risky, safe, neutral

    logger.warning(
        f"[RiskSelfDebateV2] Output is not fully segmented by three segment markers "
        f"(risky={bool(risky)}, safe={bool(safe)}, neutral={bool(neutral)}), Downgrade to full text padding"
    )
    full = response.strip()
    return full, full, full


@register_agent
class RiskSelfDebateV2(ResearcherAgent):
    """
    risk self debate analyst v2.0

    Workflow:
    1. Read comprehensive research conclusions (investment_plan) and all upstream analysis reports
    2. Complete three-perspective self-debate in a single LLM call:
       position statement → Cross-examination → final output
    3. Parsed into risky/safe/neutral three-part view
    4. update risk_debate_state(histories / current_*_response / count) 

    The output is fully compatible with the original risk triangle (risky/safe/neutral_analyst_v2).
    """

    metadata = AgentMetadata(
        id="risk_self_debate_v2",
        name="risk self debate analyst v2.0",
        description="Single node completes risk review and cross-examination from three perspectives of high elasticity/defense/baseline (A9-P1 in-depth file path)",
        category=AgentCategory.RISK,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion", source="state", state_field="investment_plan", source_state_fields=["trader_investment_plan"], producer_hint="research_manager_v2"),
            AgentInput(name="bull_opinion", type="string", description="optimistic scenario view", required=False, source="state", state_field="bull_report", producer_hint="bull_researcher_v2"),
            AgentInput(name="bear_opinion", type="string", description="prudent situational view", required=False, source="state", state_field="bear_report", producer_hint="bear_researcher_v2"),
            AgentInput(name="market_report", type="string", description="Market analysis report", required=False, source="state", state_field="market_report", producer_hint="market_analyst_v2"),
            AgentInput(name="fundamentals_report", type="string", description="Fundamental Analysis Report", required=False, source="state", state_field="fundamentals_report", producer_hint="fundamentals_analyst_v2"),
            AgentInput(name="news_report", type="string", description="News analysis report", required=False, source="state", state_field="news_report", producer_hint="news_analyst_v2"),
            AgentInput(name="sentiment_report", type="string", description="Sentiment Analysis Report", required=False, source="state", state_field="sentiment_report", producer_hint="social_analyst_v2"),
            AgentInput(name="index_report", type="string", description="Market analysis report", required=False, source="state", state_field="index_report", producer_hint="index_analyst_v2"),
            AgentInput(name="sector_report", type="string", description="Sector analysis report", required=False, source="state", state_field="sector_report", producer_hint="sector_analyst_v2"),
        ],
        outputs=[
            AgentOutput(name="risky_opinion", type="string", description="Highly resilient scenario perspective"),
            AgentOutput(name="safe_opinion", type="string", description="defensive situational view"),
            AgentOutput(name="neutral_opinion", type="string", description="base case view"),
            AgentOutput(name="risk_debate_state", type="dict", description="Updated status of the risk debate"),
        ],
        requires_tools=False,
        output_field="risky_opinion",
        report_label=" [Self-debate from three perspectives of risk]",
        workflow_stage="risk",
        growth_role="reviewer",
        growth_outputs=["risky_opinion", "safe_opinion", "neutral_opinion"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="experimental",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["workflow"],
    )

    # Self-debate does not take a single position
    stance = "self_debate"

    # Output field name (for status display, three opinion fields are actually output)
    output_field = "risky_opinion"

    debate_state_field = "risk_debate_state"

    # ==================== prompt word ====================

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """Build system prompt word (template system takes priority, failure downgrade is hard-coded)"""
        prompt = self._get_prompt_from_template(
            agent_type="debators_v2",
            agent_name="risk_self_debate_v2",
            variables={},
            state=state,
            context=state.get("context") if state else None,
            fallback_prompt=None,
            prompt_type="system",
        )
        if prompt:
            logger.debug("✅ Obtain risk self-debate system prompt words from the template system")
            return prompt

        return """You are a senior risk research expert. Your task: In an in-depth thinking, complete the self-debate from three risk review perspectives and output only three final opinions.

Thinking method (completed during the thinking process, strictly prohibited from being written into the text):
1. Independently review the comprehensive research conclusions from three perspectives in turn and form judgments respectively;
2. Cross-examination: The high-resilience perspective points out where the defensive perspective is overly conservative and ignores proven positive signals; the defensive perspective points out which unverified assumptions the high-resilience perspective relies on and which evidence is flawed; the baseline perspective evaluates the evidence strength of both sides arguments and points out which disagreements stem from information gaps;
3. After absorbing reasonable doubts from the other party, a finalized view from three perspectives is formed.

Three perspectives (the name is fixed and cannot be changed)"Optimistic/cautious"and other names):
1. Highly elastic scenario: strengthening conditions, catalytic evidence, and high-requirement premise that upward revision of conclusions depends on
2. Defensive Scenario: Conclusion s weakest premises, key sources of risk, and failure conditions
3. Baseline scenario: Comparison of the quality of evidence for both sides arguments, information gaps and the current most reliable baseline scenario

Output requirements (highest priority, followed verbatim):
- The body of the text must and can only contain the following three sections, each beginning with the specified tag line
- Output is strictly prohibited"position statement""Cross-examination""final output"Any procedural title, number or content
- The three tags must occupy one line and be output as they are (retain [ ])

Output format (strictly follow this structure):
 [Highly elastic scenario perspective]
 (Final opinions from this perspective, 300-500 words: the strengthening conditions and catalysts on which the upward revision of the conclusion depends; what high-requirement prerequisites need to be met in order to be more positive; the evidence in the current materials that most supports the upward revision)
 [Defense Scenario Perspective]
 (Final opinions from this perspective, 300-500 words: the most fragile premise of the conclusion and key risk sources; failure conditions; which evidence is insufficient to support the current conclusion)
 [Baseline Scenario View]
 (Final opinions from this perspective, 300-500 words: Comparison of the evidence quality of both sides arguments; information gaps; the current most reliable baseline scenario and verification signals that need to be tracked)

Other requirements:
- The three perspectives must reflect the differences in conclusions after cross-examination and must not simply repeat the same conclusion.
- Does not output positions, target prices, profit margins or trading recommendations
- Written in Chinese"""

    @staticmethod
    def _report_text(value: Any) -> str:
        """Extract the plain text of the report (researcher output is dict{'content': ...}, compatible with str)"""
        if isinstance(value, dict):
            return str(value.get("content") or value.get("markdown") or "")
        return str(value) if value else ""

    def _build_user_prompt(self, ticker: str, analysis_date: str, state: Dict[str, Any]) -> str:
        """Construct user prompt words (template system takes priority, failure downgrade is hard-coded)"""
        investment_plan = state.get("investment_plan", "") or state.get("trader_investment_plan", "")
        # 🔑 Upstream bull/bear_researcher_v2 writes bull_report/bear_report (dict contains content);
        # state bull_opinion/bear_opinion are historical fields and are always empty.
        bull_opinion = self._report_text(state.get("bull_report"))
        bear_opinion = self._report_text(state.get("bear_report"))
        template_variables = {
            "ticker": ticker,
            "analysis_date": analysis_date,
            "investment_plan": investment_plan,
            "bull_opinion": bull_opinion,
            "bear_opinion": bear_opinion,
            "market_report": state.get("market_report", ""),
            "fundamentals_report": state.get("fundamentals_report", ""),
            "news_report": state.get("news_report", ""),
            "sentiment_report": state.get("sentiment_report", ""),
            "index_report": state.get("index_report", ""),
            "sector_report": state.get("sector_report", ""),
        }

        logger.info(
            f"📊 [RiskSelfDebate] Input data length: "
            f"investment_plan={len(template_variables['investment_plan']):,}, "
            f"bull_opinion={len(template_variables['bull_opinion']):,}, "
            f"bear_opinion={len(template_variables['bear_opinion']):,}, "
            f"market_report={len(template_variables['market_report']):,}, "
            f"news_report={len(template_variables['news_report']):,}, "
            f"fundamentals_report={len(template_variables['fundamentals_report']):,} character"
        )

        fallback_prompt = f"""Please complete the self-debate from the three perspectives of risk in an in-depth thinking, and directly output the three final opinions (the process content is only left in the thinking).

Analysis objects:{ticker or 'unspecified'} @ {analysis_date or 'unspecified'}

 [Comprehensive research conclusion]
{investment_plan or 'No comprehensive research conclusion'}

 [Optimistic researcher report]
{template_variables['bull_opinion'] or 'No optimistic researcher report'}

 [Prudential Researcher Report]
{template_variables['bear_opinion'] or 'No Prudential Researcher Report'}

 [Market analysis report]
{template_variables['market_report'] or 'No market analysis report'}

 [News analysis report]
{template_variables['news_report'] or 'No news analysis report'}

 [Fundamental analysis report]
{template_variables['fundamentals_report'] or 'No fundamental analysis report'}

 [Social Media Sentiment Report]
{template_variables['sentiment_report'] or 'No sentiment analysis report'}

 [Market analysis report]
{template_variables['index_report'] or 'No market analysis report'}

 [Sector analysis report]
{template_variables['sector_report'] or 'No sector analysis report'}

Please output strictly according to the three-paragraph mark format specified by the system prompt words: the main text only contains three final opinion sections ([Highly elastic scenario perspective]/[Defense scenario perspective]/[Baseline scenario perspective] each have their own line). Do not output any process content such as position statements, cross-examinations, etc."""

        prompt = self._get_prompt_from_template(
            agent_type="debators_v2",
            agent_name="risk_self_debate_v2",
            variables=template_variables,
            state=state,
            context=state.get("context") if isinstance(state, dict) else state,
            fallback_prompt=fallback_prompt,
            prompt_type="user",
        )
        if prompt:
            logger.info(f"✅ Obtain risk self-debate user prompt words from the template system (length: {len(prompt)})")
            return prompt
        logger.info(f"📝 [RiskSelfDebate] Use demotion prompts (length: {len(fallback_prompt)})")
        return fallback_prompt

    def _get_required_reports(self) -> list:
        return [
            "investment_plan",
            "bull_report",
            "bear_report",
            "market_report",
            "fundamentals_report",
            "news_report",
            "sentiment_report",
            "index_report",
            "sector_report",
        ]

    # ==================== execute ====================

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execution risk three-perspective self-debate (single LLM call)

        Returns:
            The updated status includes:
                - risky_opinion / safe_opinion / neutral_opinion: tripartite perspective
                - risk_debate_state: Updated debate status
        """
        ticker = state.get("ticker", "") or state.get("company_of_interest", "")
        analysis_date = state.get("analysis_date", "") or state.get("trade_date", "")

        logger.info(f"🧠 Risk Self Debate Analyst Begins Assessment {ticker} @ {analysis_date}")

        risk_debate_state = state.get("risk_debate_state", {}) or {}

        try:
            system_prompt = self._apply_global_trading_advice_guard(
                self._build_system_prompt(state)
            )
            user_prompt = self._build_user_prompt(ticker, analysis_date, state)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            import time
            llm_start_time = time.time()
            logger.info("⏱️ [RiskSelfDebate] Start calling LLM (single call instead of multiple rounds of risk triangle debate)...")

            if self._llm:
                response = self._invoke_llm_with_trace(messages)
                raw = response.content
            else:
                raise ValueError("LLM not initialized")

            # Some models return segmented content lists
            if isinstance(raw, list):
                raw = "".join(str(c) for c in raw)
            raw = str(raw)

            llm_elapsed = time.time() - llm_start_time
            logger.info(
                f"⏱️ [RiskSelfDebate] LLM The call is completed and takes time: {llm_elapsed:.2f}seconds,"
                f"Output length: {len(raw):,} character"
            )

            risky, safe, neutral = parse_self_debate_response(raw)
            logger.info(
                f"✅ Three-perspective analysis completed: risky={len(risky):,}, safe={len(safe):,}, "
                f"neutral={len(neutral):,} character"
            )

            # Updated debate status (compatible with original Risk Triangle)
            risky_arg = f"Risky Analyst: {risky}"
            safe_arg = f"Safe Analyst: {safe}"
            neutral_arg = f"Neutral Analyst: {neutral}"
            full_history = "\n".join([risky_arg, safe_arg, neutral_arg])
            old_history = risk_debate_state.get("history", "")
            old_count = risk_debate_state.get("count", 0)

            new_risk_debate_state = {
                "history": (old_history + "\n" + full_history).strip("\n"),
                "risky_history": (risk_debate_state.get("risky_history", "") + "\n" + risky_arg).strip("\n"),
                "safe_history": (risk_debate_state.get("safe_history", "") + "\n" + safe_arg).strip("\n"),
                "neutral_history": (risk_debate_state.get("neutral_history", "") + "\n" + neutral_arg).strip("\n"),
                "latest_speaker": "SelfDebate",
                "current_risky_response": risky_arg,
                "current_safe_response": safe_arg,
                "current_neutral_response": neutral_arg,
                "count": old_count + 3,  # Each of the three perspectives counts as one speech.
            }

            logger.info("✅ Risk self-debate completed (single node replaces risk triangle multi-round debate)")

            return {
                "risky_opinion": risky,
                "safe_opinion": safe,
                "neutral_opinion": neutral,
                "risk_debate_state": new_risk_debate_state,
            }

        except Exception as e:
            logger.error(f"❌ risk self debate failure: {e}", exc_info=True)
            error_text = f"risk self debate failure: {str(e)}"
            return {
                "risky_opinion": error_text,
                "safe_opinion": error_text,
                "neutral_opinion": error_text,
                "risk_debate_state": risk_debate_state,  # Keep it as it is
            }

"""
research integrator v2.0

Research integrator implemented based on ManagerAgent base class
Comprehensive research on optimistic and cautious scenarios to form balanced research conclusions
"""

import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from ..manager import ManagerAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)


# ==================== Schema contract definition ====================
# Purpose: Let LLM start from"discretionary decision output format"downgraded to"Translate a predefined schema", 
# Eliminate format inconsistencies at the source (refer to Bridgewater Pat's"Specification driven"Idea, isomorphic to risk_manager_v2).
# Compliance requirements: analysis_view can only take values "optimistic"/"Prudence"/"Neutral", 
# Prohibited use"Call/Put/Buy/Sell"Such as trading instructions or market view terms.


class ResearchManagerOutput(BaseModel):
    """Research integrator balances research conclusions schema"""
    # Compliance Terms: Optimistic/Cautious/Neutral (Prohibited"Call/Put/Buy/Sell"such as trading instructions or market view terms)
    analysis_view: Literal["乐观", "审慎", "中性"]
    confidence: float = Field(ge=0, le=1)
    risk_score: float = Field(ge=0, le=1)
    summary: str
    reasoning: str
    core_evidence: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    invalidation_conditions: List[str] = Field(default_factory=list)
    watch_items: List[str] = Field(default_factory=list)
    risk_warning: str = ""


# Research Integrator Output Format Contract.
# According to hard constraints"system prompt Formatting requirements must be placed first", This constant will be prepended to
# _build_system_prompt Returning the value first ensures that LLM sees formatting and compliance constraints first.
RESEARCH_MANAGER_SCHEMA_PROMPT = """ [output format contract·Must be strictly followed]
Your output must be a JSON object with the following fields. Just output JSON, don t wrap it in a markdown block, don t have any extra text.

{
  "analysis_view": "optimistic" | "Prudence" | "Neutral",
  "confidence": 0.0-1.0 floating point number between,
  "risk_score": 0.0-1.0 floating point number between,
  "summary": "50-120 Summary of the conclusion of the word, indicating which side is currently more preferred and the main reasons",
  "reasoning": "200-500 words, it is recommended to explain how to weigh the evidence according to the strongest basis for the optimistic scenario, the strongest basis for the cautious scenario, points of consensus, sources of disagreement, and final judgment.",
  "core_evidence": ["core basis 1", "core basis 2", "core basis 3"],
  "uncertainties": ["key uncertainties 1", "key uncertainties 2"],
  "invalidation_conditions": ["Judgment of downward revision or failure premise 1", "Judgment of downward revision or failure premise 2"],
  "watch_items": ["Follow-up observations 1", "Follow-up observations 2", "Follow-up observations 3"],
  "risk_warning": "100 Key risk warnings or major counter-evidence within 1 word"
}

 [Compliance Constraints·Must comply]
1. analysis_view Fields can only take values "optimistic" / "Prudence" / "Neutral". 
2. Prohibited use "bullish" / "Bearish" / "buy" / "sell" / "Add to position" / "Reduce positions" / "hold" / "Clearance" Such as trading instructions or market view terms.
3. "Optimistic/cautious/neutral" The opinions expressed are the tendencies of research conclusions and do not constitute any trading advice or operating instructions.
4. It is prohibited to give specific target prices or stop-loss prices, and may not extend to price ranges, upside/downside spaces, risk-benefit ratios or operational recommendations.
5. It is prohibited to promise profits or guarantee profits, and risks must be disclosed.
6. All conclusions must be strictly based on the content of the report provided and no falsification of information is allowed.

Field constraints:
- analysis_view: The tendency of research conclusions can only be"optimistic"/"Prudence"/"Neutral"
- confidence: 0-1 Floating point number between (do not write 0-100)
- risk_score: 0-1 Floating point number between (do not write 0-100)
- core_evidence / uncertainties / invalidation_conditions / watch_items: String array, try to provide 2-5 items
- reasoning It should be clearly reflected: the strongest basis for the optimistic scenario, the strongest basis for the cautious scenario, the consensus between both parties, the key sources of disagreement, and why the current judgment is biased towards one side or remains neutral.
- All fields must serve research and judgment, and transaction execution language cannot appear.

The output must be valid JSON, do not add any text or code block tags before or after the JSON.

"""

# Try importing utility functions
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None

try:
    from tradingagents.utils.template_client import get_agent_prompt, get_user_prompt
except (ImportError, KeyError):
    logger.warning("Unable to import get_agent_prompt/get_user_prompt, the default prompt word will be used")
    get_agent_prompt = None
    get_user_prompt = None

# It is no longer necessary to import get_agent_prompt/get_user_prompt directly, use the _get_prompt_from_template method of the base class


@register_agent
class ResearchManagerV2(ManagerAgent):
    """
    research integrator v2.0
    
    Function:
    - Comprehensive optimistic and cautious scenario research
    - Moderate debate (optional)
    - Make balanced research conclusions
    - Generate comprehensive research conclusions
    
    Workflow:
    1. Read the Optimistic and Cautious Scenario Research Report
    2. Moderate debate (optional)
    3. Comprehensive research and judgment
    4. Generate balanced research conclusions and key observations
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("research_manager_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15",
            "bull_report": "...",
            "bear_report": "..."
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="research_manager_v2",
        name="research integrator v2.0",
        description="Comprehensive research on optimistic and cautious scenarios to form balanced research conclusions and key observations",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # Managers don't need tools
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="bull_report", type="string", description="Optimistic Scenario Research Report", source="state", state_field="bull_report", producer_hint="bull_researcher_v2"),
            AgentInput(name="bear_report", type="string", description="Prudential Scenario Research Report", source="state", state_field="bear_report", producer_hint="bear_researcher_v2"),
        ],
        outputs=[
            AgentOutput(name="investment_advice", type="string", description="Balanced Study Conclusions"),
        ],
        requires_tools=False,
        output_field="investment_advice",
        report_label=" [Balanced research conclusion v2]",
        workflow_stage="manager",
        growth_role="optimizer",
        growth_outputs=["investment_plan", "investment_debate_state"],
        memory_scope_hint="research_asset",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )
    
    # manager type
    manager_type = "research"
    
    # Output field name
    output_field = "investment_plan"

    # Whether to enable debate
    enable_debate = True

    def _run_delegated_research_agents(self, state: Dict[str, Any]) -> Dict[str, Any]:
        node_config = state.get("node_config") or {}
        delegated_agent_ids = node_config.get("delegated_agent_ids") or []
        if not isinstance(delegated_agent_ids, list):
            return {}

        delegated_outputs: Dict[str, Any] = {}
        for target_agent_id in delegated_agent_ids:
            normalized_target = str(target_agent_id or "").strip()
            if not normalized_target or normalized_target == self.agent_id:
                continue

            if normalized_target == "chip_distribution_analyst_v2" and (state.get("chip_report") or delegated_outputs.get("chip_report")):
                logger.info("[ResearchManagerV2] chip_report already exists, skip delegation chip_distribution_analyst_v2")
                continue

            logger.info("[ResearchManagerV2] Commission additional research Agent: %s", normalized_target)
            delegate_result = self.delegate_to_agent(
                normalized_target,
                {**state, **delegated_outputs},
                payload={
                    "task_description": "Supplement the context of chip distribution and position cost structure for research integrators to make comprehensive research judgments",
                },
                metadata={
                    "delegation_role": "research_enrichment",
                },
            )
            if isinstance(delegate_result, dict):
                delegated_outputs.update(delegate_result)

        return delegated_outputs

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform research integrator analysis

        Override the parent class method to add investment_debate_state output,
        Ensure compatibility with report formatters
        """
        logger.info("=" * 80)
        logger.info("🔍 [ResearchManagerV2] Start executing investment decisions")
        logger.info("=" * 80)

        # 🔍 Check input data
        ticker = state.get("ticker", "unknown")
        bull_report = state.get("bull_report", "")
        bear_report = state.get("bear_report", "")

        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📈 Positive Evidence Report Type: {type(bull_report)}, length: {len(str(bull_report))} character")
        logger.info(f"📉 Cautionary Evidence Report Type: {type(bear_report)}, length: {len(str(bear_report))} character")

        # Convert to string if not
        bull_report_str = str(bull_report) if bull_report else ""
        bear_report_str = str(bear_report) if bear_report else ""

        if bull_report_str and len(bull_report_str) > 10:
            logger.info(f"📈 First 200 characters of positive evidence report: {bull_report_str[:200]}...")
        else:
            logger.warning("⚠️ Positive evidence report is empty or too short!")

        if bear_report_str and len(bear_report_str) > 10:
            logger.info(f"📉 Be careful with the first 200 characters of your evidence report: {bear_report_str[:200]}...")
        else:
            logger.warning("⚠️ Be careful if the evidence report is empty or too short!")

        # 🔥 ETF Workflow summary: If there is no debate report, synthesize three analyst reports into research materials
        if not bull_report_str and not bear_report_str:
            market_report = state.get("market_report", "")
            news_report = state.get("news_report", "")
            fundamentals_report = state.get("fundamentals_report", "")
            parts = []
            if fundamentals_report:
                parts.append(f"### ETF/fundamental analysis\n{fundamentals_report}")
            if market_report:
                parts.append(f"### Market and technical analysis\n{market_report}")
            if news_report:
                parts.append(f"### News analysis\n{news_report}")
            if parts:
                combined = "\n\n".join(parts)
                state = {
                    **state,
                    "bull_report": combined,
                    "bear_report": (
                        " (This workflow is a debate-free single-channel analysis mode."
                        "From the above comprehensive analysis materials, please identify factors supporting the upward trend and factors supporting the downward trend at the same time, and make a balanced judgment. )"
                    ),
                }
                logger.info(
                    f"[ResearchManagerV2] No debate report, analyst reports have been synthesized into research materials ({len(combined)} character)"
                )

        delegated_outputs = self._run_delegated_research_agents(state)
        if delegated_outputs:
            logger.info(f"🔗 [ResearchManagerV2] Delegate result field received: {list(delegated_outputs.keys())}")
            state = {**state, **delegated_outputs}

        # Call the parent class method to get basic output
        logger.info("🚀 Call the parent class execute method...")
        result = super().execute(state)
        logger.info("✅ The execution of the parent class execute method is completed")

        # Extract decision content
        decision_value = result.get(self.output_field, "")
        logger.info(f"📝 Decision output fields: {self.output_field}")
        logger.info(f"📝 Decision content type: {type(decision_value)}")
        logger.info(f"📝 Decision content length: {len(str(decision_value))} character")

        # Extract plain text for verification (compatible with both dictionary/string output formats)
        if isinstance(decision_value, dict):
            decision_text = decision_value.get("content", "") or decision_value.get("markdown", "") or str(decision_value)
        else:
            decision_text = str(decision_value) if decision_value else ""

        # 🔥 New: schema verification (make errors explicit, no longer silently cover up)
        import json
        validated_dict, validation_error = self._validate_research_output(decision_text)

        if validation_error is None:
            # ✅ Verification passed: stored as JSON string (keep type=string Compatible with downstream consumers)
            logger.info("✅ [ResearchManagerV2] schema Verification passed")
            result[self.output_field] = json.dumps(validated_dict, ensure_ascii=False)

            # 🔥 P2: Execute the assertion (non-blocking) and merge the results into validation_status
            assertion_result = self._run_assertions(
                raw_text=decision_text, parsed=validated_dict
            )
            assertion_violations_dump = [v.model_dump() for v in assertion_result.violations]
            if assertion_violations_dump:
                result["investment_plan_assertion_violations"] = assertion_violations_dump

            if assertion_result.has_error_violation:
                logger.warning(
                    f"⚠️ [ResearchManagerV2] Assert error violation {assertion_result.error_count} article, downgrade validation_status"
                )
                result["investment_plan_validation_status"] = "failed"
                result["investment_plan_validation_error"] = (
                    f"assert violation: {assertion_result.error_count} Article error"
                )
                self._record_trace_validation(
                    validation_status="failed",
                    validation_error=result["investment_plan_validation_error"],
                    validation_details={
                        "analysis_view": validated_dict.get("analysis_view"),
                        "confidence": validated_dict.get("confidence"),
                        "assertion_violations": assertion_violations_dump,
                    },
                )
            else:
                result["investment_plan_validation_status"] = "passed"
                self._record_trace_validation(
                    validation_status="passed",
                    validation_details={
                        "analysis_view": validated_dict.get("analysis_view"),
                        "confidence": validated_dict.get("confidence"),
                        "assertion_violations": assertion_violations_dump,
                    },
                )
            decision_content = result[self.output_field]
        else:
            # ❌ Verification failure: report explicitly (not silently report), retain the original output for troubleshooting
            logger.error(f"❌ [ResearchManagerV2] schema Verification failed: {validation_error}")
            logger.error(f"❌ [ResearchManagerV2] First 500 characters of raw output: {decision_text[:500]}")
            result[self.output_field] = decision_text
            result["investment_plan_validation_status"] = "failed"
            result["investment_plan_validation_error"] = validation_error

            # 🔥 P2: Assertions are also executed when verification fails (used to accumulate hit statistics)
            assertion_result = self._run_assertions(
                raw_text=decision_text, parsed=None
            )
            assertion_violations_dump = [v.model_dump() for v in assertion_result.violations]
            self._record_trace_validation(
                validation_status="failed",
                validation_error=validation_error,
                validation_details={
                    "raw_output_preview": decision_text[:500],
                    "assertion_violations": assertion_violations_dump,
                },
            )
            decision_content = decision_text

        # Get the existing investment_debate_state from state (if any)
        existing_debate_state = state.get("investment_debate_state", {})

        # Build a new investment_debate_state containing judge_decision
        new_debate_state = {
            "judge_decision": decision_content,  # ✅ Key: Preserve LLM output (JSON string or raw text)
            "history": existing_debate_state.get("history", ""),
            "bull_history": existing_debate_state.get("bull_history", ""),
            "bear_history": existing_debate_state.get("bear_history", ""),
            "current_response": decision_content,
            "count": existing_debate_state.get("count", 0),
        }

        logger.info("✅ [ResearchManagerV2] Investment decision execution completed")
        logger.info("=" * 80)

        # Return results containing investment_debate_state
        return {
            **delegated_outputs,
            **result,
            "investment_debate_state": new_debate_state,
        }

    def _validate_research_output(self, text: str) -> tuple:
        """
        Verify that the LLM output conforms to the ResearchManagerOutput schema.

        Args:
            text: LLM Output research conclusion text (may be plain JSON, JSON wrapped in markdown code blocks, or plain text)

        Returns:
            (validated_dict, None): If the verification passes, dict can be directly serialized as JSON
            (None, error_msg): Verification failed, error_msg describes the reason for the failure
        """
        import json
        import re

        if not text or not text.strip():
            return None, "Output is empty"

        # Compatible with JSON wrapped in markdown code blocks (```json ... ``` or ``` ... ```) 
        text = text.strip()
        json_str = text
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()

        # parse JSON
        try:
            json_obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            return None, f"JSON Parsing failed: {e}"

        if not isinstance(json_obj, dict):
            return None, f"JSON The top level is not an object, the actual type: {type(json_obj).__name__}"

        # pydantic schema Verification (including compliance term enumeration constraints and numerical range constraints)
        try:
            validated = ResearchManagerOutput(**json_obj)
            return validated.model_dump(), None
        except ValidationError as e:
            return None, f"Schema Verification failed: {e}"

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (refer to the implementation of fundamentals_analyst_v2)

        Args:
            state: Workflow status (used to extract template variables)

        Returns:
            System prompt word
        """
        logger.info("🔍 [ResearchManagerV2] Start building system prompt words")
        
        if state is None:
            state = {}
        
        # Extract the necessary variables from state (if required by the system prompt word template)
        # Note: Although system prompt words usually do not require variables, some templates may require ticker, current_date, etc.
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        template_variables = {}
        
        # If there are ticker and analysis_date in state, extract them (the system prompt word template may be required)
        if "ticker" in state:
            template_variables["ticker"] = state["ticker"]
        if "analysis_date" in state or "trade_date" in state:
            analysis_date = state.get("analysis_date") or state.get("trade_date")
            if analysis_date:
                # Make sure the date is in the correct format
                if isinstance(analysis_date, str) and len(analysis_date) > 10:
                    analysis_date = analysis_date.split()[0]
                template_variables["current_date"] = analysis_date
                template_variables["analysis_date"] = analysis_date

        # Use the base class's general method to get the prompt word from the template system
        prompt = self._get_prompt_from_template(
            agent_type="managers_v2",  # ✅ Fix: use v2 types
            agent_name="research_manager_v2",  # ✅ Fix: use v2 names
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # ✅ Key: Specify to obtain system prompt words (including output_format)
        )

        # Check whether the prompt word was successfully obtained
        if prompt:
            # 🔥 According to hard constraints"system prompt Formatting requirements must be placed first", 
            # Place the schema contract at the front of prompt to ensure that LLM sees the format and compliance constraints first.
            # It takes effect immediately without relying on database migration.
            prompt = RESEARCH_MANAGER_SCHEMA_PROMPT + prompt
            logger.info(f"📝 System prompt word length: {len(prompt)} Character (including schema contract)")
            logger.info(f"📝 The first 500 characters of the system prompt word:\n{prompt[:500]}...")

            # Check if new research brief structure guidance is included
            if "core_evidence" in prompt or "Follow-up observations" in prompt:
                logger.info("✅ The system prompt includes [Research Briefing Structure] guidance.")
            else:
                logger.warning("⚠️ The system prompt words do not contain [Research Briefing Structure] guidance (old version of the prompt words may be used)")

            logger.debug(f"✅ Obtain research integrator system prompt words from the template system")
            return prompt
        else:
            logger.warning("⚠️ Failed to obtain the system prompt word from the template system, use the default prompt word")

        # Default prompt word (compliant version)— Also prefix the schema contract to ensure that the fallback path is also constrained
        return RESEARCH_MANAGER_SCHEMA_PROMPT + """You are a neutral research integrator, responsible for organizing optimistic and cautious scenario research into balanced research conclusions.

    **Analytical style**: Be objective, restrained, and evidence-based, emphasizing strongest case comparisons, sources of disagreement, information gaps, and follow-up observations.

    **Core responsibilities**:
    1. First use the strongest establishment logic of both parties to understand the two types of arguments, optimistic and cautious, and then form the current research judgment.
    2. Explain the consensus, key differences, and sources of disagreement between the two parties, rather than just labeling the outcome.
    3. Point out the core basis supporting the judgment, key uncertainties, conditions under which the judgment may fail, and key points for subsequent observation.
    4. Output balanced research conclusions for downstream integration and risk review to help subsequent nodes understand Why do you think so and What to observe next . 

    **Analysis principles**:
    - The strongest arguments of both parties should be reviewed first with equal weight, and then the current tendency should be determined based on the quality of the evidence without presupposing conclusions.
    - Only research judgments are output, but buying, selling, holding, adding or subtracting positions, position ratio, target price, stop loss and profit or execution rhythm are not output.
    - Upward or downward drivers can be described, but only as research hypotheses, weights of evidence, and matters to be verified.
    - If the material involves current prices, valuations, or market expectations, it can explain how this information affects research judgment, but it cannot be extended to target prices, price ranges, upside/downsides, risk-benefit ratios, or operational recommendations.
    - All conclusions must be strictly based on the content of the report provided and no falsification of information is allowed.
    - Use Chinese output.

    **Output target**:
    - Allow users to understand which judgment is more supported by the current evidence and why the other side is not currently dominant.
    - Let users know the key basis, key risks, prerequisites for upgrading or downgrading, and follow-up observations.
    - Provide clear, reusable input to research conclusions to research integrators and risk teams.

    **Disclaimer**: 
    This research briefing is for informational purposes only and does not constitute trading advice or investment commitment. Please make independent judgment based on your own situation."""

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        inputs: Dict[str, Any],
        debate_summary: Optional[str],
        state: Dict[str, Any]
    ) -> str:
        """
        Build user prompt words

        Args:
            ticker: Stock code
            analysis_date: Analysis date
            inputs: Collection of input dictionaries
            debate_summary: Debate summary
            state: Workflow status

        Returns:
            User prompt words
        """
        logger.info("🔍 [ResearchManagerV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {analysis_date}")
        logger.info(f"📝 input field: {list(inputs.keys())}")

        # Check positive and caution reports
        bull_report = inputs.get("bull_report", "")
        bear_report = inputs.get("bear_report", "")

        # Convert to string if not
        bull_report_str = str(bull_report) if bull_report else ""
        bear_report_str = str(bear_report) if bear_report else ""

        logger.info(f"📈 Positive Evidence Report Type: {type(bull_report)}, length: {len(bull_report_str)} character")
        logger.info(f"📉 Cautionary Evidence Report Type: {type(bear_report)}, length: {len(bear_report_str)} character")

        if bull_report_str and len(bull_report_str) > 10:
            # Check if price information is included
            if "price" in bull_report_str or "price" in bull_report_str or "¥" in bull_report_str:
                logger.info("✅ Positive evidence reports contain pricing information")
            else:
                logger.warning("⚠️ Positive evidence reports may not contain pricing information")
        else:
            logger.warning("⚠️ Positive evidence report is empty or too short!")

        if bear_report_str and len(bear_report_str) > 10:
            # Check if price information is included
            if "price" in bear_report_str or "price" in bear_report_str or "¥" in bear_report_str:
                logger.info("✅ Prudence Evidence reports contain pricing information")
            else:
                logger.warning("⚠️ Cautionary evidence reports may not contain pricing information")
        else:
            logger.warning("⚠️ Be careful if the evidence report is empty or too short!")

        # Get company name
        if StockUtils:
            market_info = StockUtils.get_market_info(ticker)
            company_name = self._get_company_name(ticker, market_info)
        else:
            company_name = ticker
        
        # Get the current price from state
        current_price = state.get("current_price", "unknown")
        logger.info(f"💰 current price: {current_price} (Source: state)")

        # 🆕 Extract the report content (if it is a dictionary, take the content field)
        def extract_content(report):
            """Extract plain text content from reports"""
            if isinstance(report, dict):
                return report.get('content', str(report))
            return str(report) if report else "None"

        bull_report_content = extract_content(inputs.get("bull_report"))
        bear_report_content = extract_content(inputs.get("bear_report"))

        logger.info(f"📈 Positive Evidence Report Content Length: {len(bull_report_content)} character")
        logger.info(f"📉 Be careful about the length of evidence report content: {len(bear_report_content)} character")

        # 🆕 Detect debate patterns and get debate history
        debate_history = ""
        is_debate_mode = "investment_debate_state" in state and isinstance(state.get("investment_debate_state"), dict)

        if is_debate_mode:
            debate_state = state.get("investment_debate_state", {})
            full_history = debate_state.get("history", "")
            bull_history = debate_state.get("bull_history", "")
            bear_history = debate_state.get("bear_history", "")

            if full_history:
                debate_history = f"\n [Full debate history]\n{full_history}\n"
                logger.info(f"💬 [debate mode] Read debate history, length: {len(full_history)} character")
            else:
                logger.info("💬 [debate mode] Debate history is empty")
        else:
            logger.info("📝 [Single analysis mode] No debate history")

        # Prepare template variables
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "analysis_date": analysis_date,
            "current_price": current_price,  # ✅ Add current price
            "bull_report": bull_report_content,  # ✅ Only the content is passed, not the dictionary
            "bear_report": bear_report_content,  # ✅ Only the content is passed, not the dictionary
            "debate_summary": debate_summary or "No debate summary",
            "debate_history": debate_history,  # 🆕 Add debate history
        }

        # Add other inputs to template variables
        for key, value in inputs.items():
            if key not in ["bull_report", "bear_report"]:
                template_variables[key] = str(value) if value else ""

        # Use the general method of the base class to obtain the user prompt word (the base class will automatically extract system variables from state)
        prompt = self._get_prompt_from_template(
            agent_type="managers_v2",  # ✅ Fix: use v2 types
            agent_name="research_manager_v2",  # ✅ Fix: use v2 names
            variables=template_variables,
            state=state,  # 🆕 Pass state and the base class will automatically extract system variables
            context=state,
            fallback_prompt=None,
            prompt_type="user"  # 🆕 Specify to obtain user prompt words
        )
        if prompt:
            logger.info(f"✅ Get research integrator user prompt words from template system (length: {len(prompt)})")
            return prompt
        
        market_name = state.get("market_name", "")
        currency_name = state.get("currency_name", "")
        currency_symbol = state.get("currency_symbol", "")

        target_line = f"{company_name}（{ticker}）"
        if market_name:
            target_line = f"{company_name}（{ticker}，{market_name}）"

        prompt = (
            "Make comprehensive research judgments based on the research materials provided.\n"
            "Available resources:\n"
            f"- Analysis goals:{target_line}\n"
            f"- Analysis date:{analysis_date}\n"
            f"- Currency unit:{currency_name} ({currency_symbol}) \n"
            f"- Current price context:{current_price}\n"
            f"- Optimistic scenario view:{bull_report_content}\n"
            f"- Prudent Scenario View:{bear_report_content}\n"
            f"- Debate summary:{debate_summary or 'Material not provided'}\n"
        )

        for key, value in inputs.items():
            if key not in ["bull_report", "bear_report"]:
                prompt += f"- Supplementary material {key}: {value}\n"

        prompt += f"""

Mission focus:
- Use the strongest version to summarize the reasons for the optimistic scenario first, and then use the strongest version to summarize the reasons for the cautious scenario. Don t write either side out as a straw man.
- Objectively weigh optimistic and cautious views, summarize the consensus first, and then write down the most critical disagreements to form the current research judgment: optimistic / cautious / neutral.
- Make it clear which content is the consensus of both parties and which is the key disagreement, and whether the disagreement mainly comes from data interpretation, premise assumptions, time dimension or the degree of market pricing reflection.
- Indicate the side that currently has more support; if remaining neutral, explain why the evidence on both sides is still balanced or has not been fully verified.
- Refining the core evidence supporting the judgment, highlighting the most critical evidence rather than listing all the information.
- Identify key uncertainties and which additional facts would revise up, downgrade or invalidate current judgments.
- List matters for follow-up observation, giving priority to verifiable matters such as financial reports, announcements, operating indicators, industry data, policy changes, etc.
- If the material involves current prices or valuations, it can state whether the market has factored in some optimistic/pessimistic expectations, but it cannot be written as target price, price range, upside/downside, or risk-benefit ratio.
- If any material is empty or the evidence is insufficient, you must explicitly write Material not provided or Still to be verified , Model memory completion must not be used.
- If you mention waiting for financial or annual reports, don t specify the year out of date, just write Waiting for the next financial report or Waiting for the annual report to be released . 

Strictly prohibited:
- Action suggestions such as buying, selling, holding, adding positions, reducing positions, clearing positions, etc. are not allowed.
- Target prices, price ranges, key prices, risk control reference prices, position ratios, and profit expectations are not allowed to be output.
- Observation conditions must not be written as execution actions after the price is triggered.

Output format:
Please use JSON output with the following fields:
```json
{{
    "analysis_view": "optimistic|Prudence|Neutral",
    "confidence": 0.0-1.0,
    "risk_score": 0.0-1.0,
    "summary": "50-120 Summary of the conclusion of the word, indicating which side is currently more preferred and the main reasons",
    "reasoning": "200-500 words, it is recommended to explain how to weigh the evidence according to the strongest basis for the optimistic scenario, the strongest basis for the cautious scenario, points of consensus, sources of disagreement, and final judgment.",
    "core_evidence": ["core basis 1", "core basis 2", "core basis 3"],
    "uncertainties": ["key uncertainties 1", "key uncertainties 2"],
    "invalidation_conditions": ["Judgment of downward revision or failure premise 1", "Judgment of downward revision or failure premise 2"],
    "watch_items": ["Follow-up observations 1", "Follow-up observations 2", "Follow-up observations 3"],
    "risk_warning": "100 Key risk warnings or major counter-evidence within 1 word"
}}
```

Field requirements:
- `analysis_view`, `confidence`, `summary`, `reasoning` is required.
- `core_evidence`, `uncertainties`, `invalidation_conditions`, `watch_items` For arrays, try to provide 2-5 items.
- `analysis_view` Can only take value"optimistic"/"Prudence"/"Neutral", Prohibited use"Call/Put/Buy/Sell"and other terms.
- `reasoning` It should be clearly reflected: the strongest basis for the optimistic scenario, the strongest basis for the cautious scenario, the consensus of both parties, the key sources of disagreement, and why the current judgment is biased towards one side or remains neutral.
- All fields must serve research judgment, and transaction execution language cannot appear.
"""

        logger.info(f"📝 Total length of user prompt words: {len(prompt)} character")
        logger.info(f"📝 The first 500 characters of the user prompt word:\n{prompt[:500]}...")

        if "Available resources" in prompt and "Mission focus" in prompt:
            logger.info("✅ The user prompt words include [Available Resources] and [Task Focus] guidance.")
        else:
            logger.warning("⚠️ The user prompt words do not include [Available Resources] and [Task Focus] guidance.")

        return prompt
    
    def _get_required_inputs(self) -> List[str]:
        """
        Get the required input list
        
        Returns:
            Enter a list of field names
        """
        return [
            "bull_report",
            "bear_report",
            "chip_report",
        ]
    
    def _get_company_name(self, ticker: str, market_info: dict) -> str:
        """Get company name"""
        try:
            if market_info['is_china']:
                from tradingagents.dataflows.interface import get_china_stock_info_unified
                stock_info = get_china_stock_info_unified(ticker)
                if stock_info and "Stock name:" in stock_info:
                    return stock_info.split("Stock name:")[1].split("\n")[0].strip()
            elif market_info['is_hk']:
                from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                return get_hk_company_name_improved(ticker)
            elif market_info['is_us']:
                us_stock_names = {
                    'AAPL': 'apple inc.', 'TSLA': 'Tesla', 'NVDA': 'NVIDIA',
                    'MSFT': 'Microsoft', 'GOOGL': 'Google', 'AMZN': 'Amazon',
                }
                return us_stock_names.get(ticker.upper(), f"US stocks{ticker}")
        except Exception as e:
            logger.warning(f"Failed to get company name: {e}")
        
        return f"stocks{ticker}"


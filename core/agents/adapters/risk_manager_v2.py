"""
risk assessor v2.0

Risk assessor implemented based on ManagerAgent base class
"""

import logging
from typing import Dict, Any, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from core.agents.manager import ManagerAgent
from core.agents.config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from core.agents.registry import register_agent

logger = logging.getLogger(__name__)


# ==================== Schema contract definition ====================
# Purpose: Let LLM start from"discretionary decision output format"downgraded to"Translate a predefined schema", 
# Eliminate format inconsistencies at the source (refer to Bridgewater Pat's"Specification driven"ideas).
# Compliance requirements: action/investment_adjustment can only take values "optimistic"/"Prudence"/"Neutral", 
# Prohibited use"Call/Put/Buy/Sell"Such as trading instructions or market view terms.


class FinalTradeDecision(BaseModel):
    """final research conclusion schema"""
    # Compliance Terms: Optimistic/Cautious/Neutral (Prohibited"Call/Put/Buy/Sell"such as trading instructions or market view terms)
    action: Literal["乐观", "审慎", "中性"]
    confidence: float = Field(ge=0, le=1)
    price_analysis_range: Optional[str] = None
    risk_reference_price: Optional[str] = None
    risk_exposure_ratio: Optional[str] = None
    reasoning: str = ""
    summary: str = ""
    risk_warning: str = ""


class RiskAssessmentOutput(BaseModel):
    """Risk review conclusion schema"""
    risk_level: Literal["低", "中", "高"]
    risk_score: float = Field(ge=0, le=1)
    reasoning: str
    key_risks: List[str] = Field(default_factory=list)
    risk_control: str = ""
    # Compliance terms: optimistic/cautious/neutral (same as action field)
    investment_adjustment: Literal["乐观", "审慎", "中性"]
    final_trade_decision: FinalTradeDecision


# Risk review conclusion output format contract.
# According to hard constraints"system prompt Formatting requirements must be placed first", This constant will be prepended to
# _build_system_prompt Returning the value first ensures that LLM sees formatting and compliance constraints first.
RISK_ASSESSMENT_SCHEMA_PROMPT = """ [output format contract·Must be strictly followed]
Your output must be a JSON object with the following fields. Just output JSON, don t wrap it in a markdown block, don t have any extra text.

{
  "risk_level": "low" | "in" | "high",
  "risk_score": 0.0-1.0 floating point number between,
  "reasoning": "Evaluation conclusion (string)",
  "key_risks": ["core risk 1", "core risk 2"],
  "risk_control": "Risk control suggestions (string)",
  "investment_adjustment": "optimistic" | "Prudence" | "Neutral",
  "final_trade_decision": {
    "action": "optimistic" | "Prudence" | "Neutral",
    "confidence": 0.0-1.0 floating point number between,
    "price_analysis_range": "Price analysis range (optional, fill in null if not available)",
    "risk_reference_price": "Risk control reference price (optional, fill in null if not available)",
    "risk_exposure_ratio": "Risk exposure analysis (optional, fill in null if not)",
    "reasoning": "analytical reasoning",
    "summary": "Analysis summary",
    "risk_warning": "Risk warning"
  }
}

 [Compliance Constraints·Must comply]
1. investment_adjustment and action fields can only take values "optimistic" / "Prudence" / "Neutral". 
2. Prohibited use "bullish" / "Bearish" / "buy" / "sell" / "Add to position" / "Reduce positions" / "hold" / "Clearance" Such as trading instructions or market view terms.
3. "Optimistic/cautious/neutral" The opinions expressed are the tendencies of research conclusions and do not constitute any trading advice or operating instructions.
4. It is forbidden to give a specific target price or stop loss price, and it can be output. "price analysis range" and label uncertainty.
5. It is prohibited to promise profits or guarantee profits, and risks must be disclosed.
6. All conclusions must be based on obtained data and no fabricated data or indicators are allowed.

Field constraints:
- risk_level: The risk level can only be"low"/"in"/"high"one of the three
- risk_score: 0-1 Floating point number between (do not write 0-100)
- investment_adjustment / action: can only be"optimistic"/"Prudence"/"Neutral"
- confidence: 0-1 Floating point number between (do not write 0-100)
- key_risks: String array, each item is a core risk
- If the optional field has no content, fill in null and do not omit the field name.

The output must be valid JSON, do not add any text or code block tags before or after the JSON.

"""

# Try importing the template system
try:
    from tradingagents.utils.template_client import get_agent_prompt
except (ImportError, KeyError) as e:
    logger.warning(f"Unable to import template system: {e}")
    get_agent_prompt = None

# It is no longer necessary to import get_agent_prompt directly, use the _get_prompt_from_template method of the base class

# Try importing stock tools
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None


@register_agent
class RiskManagerV2(ManagerAgent):
    """
    risk assessor v2.0
    
    Function:
    - Host risk robustness review
    - Comprehensive risk research evidence
    - Form a summary of risk research observations (does not constitute investment advice)
    
    Workflow:
    1. Read research plans and risk perspectives from all parties
    2. Host risk scenario review (optional)
    3. Comprehensive risk analysis and judgment
    4. Generate risk study observation reports
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("risk_manager_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15",
            "investment_plan": "...",
            "risky_opinion": "...",
            "safe_opinion": "..."
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="risk_manager_v2",
        name="risk assessor v2.0",
        description="Host the robustness review, integrate multiple perspectives, and formulate comprehensive research conclusions after the risk review (outputting research observations does not constitute investment advice)",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # Managers don't need tools
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion", source="state", state_field="investment_plan", producer_hint="research_manager_v2"),
            AgentInput(name="risky_opinion", type="string", description="Highly elastic scenario research observations", required=False, source="state", state_field="risky_opinion", producer_hint="risky_analyst_v2"),
            AgentInput(name="safe_opinion", type="string", description="Defense Scenario Research Observations", required=False, source="state", state_field="safe_opinion", producer_hint="safe_analyst_v2"),
            AgentInput(name="neutral_opinion", type="string", description="Baseline Scenario Research Observations", required=False, source="state", state_field="neutral_opinion", producer_hint="neutral_analyst_v2"),
        ],
        outputs=[
            AgentOutput(name="risk_assessment", type="string", description="Robustness review and risk review report"),
            AgentOutput(name="risk_debate_state", type="dict", description="Risk multi-scenario research status (including judge_decision)"),
        ],
        requires_tools=False,
        output_field="risk_assessment",
        report_label=" [Risk review conclusion v2] ",
        workflow_stage="manager",
        growth_role="optimizer",
        growth_outputs=["risk_assessment", "risk_debate_state", "final_trade_decision"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )

    # manager type
    manager_type = "risk"
    
    # Output field name
    output_field = "risk_assessment"
    
    # Is it necessary to debate
    enable_debate = True

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (refer to the implementation of fundamentals_analyst_v2)
        
        Args:
            state: Workflow status (used to extract template variables)
        
        Returns:
            System prompt word
        """
        logger.info("🔍 [RiskManagerV2] Start building system prompt words")
        
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
            agent_type="managers_v2",
            agent_name="risk_manager_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # ✅ Key: Specify to obtain system prompt words (including output_format)
        )

        if prompt:
            # 🔥 According to hard constraints"system prompt Formatting requirements must be placed first", 
            # Place the schema contract at the front of prompt to ensure that LLM sees the format and compliance constraints first.
            # It takes effect immediately without relying on database migration.
            prompt = RISK_ASSESSMENT_SCHEMA_PROMPT + prompt
            logger.info(f"📝 System prompt word length: {len(prompt)} Character (including schema contract)")
            logger.info(f"📝 The first 500 characters of the system prompt word:\n{prompt[:500]}...")

            # Check if output format requirements are included
            if "output_format" in prompt.lower() or "JSON Format" in prompt or "json" in prompt.lower():
                logger.info("✅ The system prompt includes [output format requirements]")
            else:
                logger.warning("⚠️ The system prompt word may not contain [output format requirements] (old version of the prompt word may be used)")

            logger.debug(f"✅ Get the risk assessor system prompt words from the template system")
            return prompt

        logger.warning("⚠️ Failed to obtain the system prompt word from the template system, use the default prompt word")

        # Default prompt word (compliant version)— Also prefix the schema contract to ensure that the fallback path is also constrained
        return RISK_ASSESSMENT_SCHEMA_PROMPT + """You are a risk assessor responsible for integrating the robustness reviews of all parties and forming risk review conclusions.

    **Analytical style**: Objectivity, restraint, and robustness as the core, emphasizing judgment boundaries, constraints, failure triggers, and follow-up observations.

**Core responsibilities**:
    1. Comprehensive review of the robustness of high resilience, defense, and baseline scenarios.
    2. Identify key risks, vulnerabilities, and information gaps in current research conclusions.
    3. Explain what conditions would support an upward revision, maintenance, or downward revision of the conclusion.
    4. Form risk review conclusions and follow-up observation points.
    5. Give judgment constraints rather than specific operation suggestions.

**Analysis principles**:
    - Objectively synthesize the views of three parties and explain whether the current conclusion is robust enough based on evidence.
    - It does not output buying and selling, adding or subtracting positions, position ratio, target price, price range, stop loss and profit or execution rhythm.
    - Risk sources, observation signals, and conclusion invalidation conditions may be described, but shall not be extended to operational recommendations.
    - All conclusions must be strictly based on the materials provided and information must not be fabricated.
    - Use Chinese output.

**Tool usage guide**:

    Conduct a risk review review based on the risk perspective provided and comprehensive research conclusions.
    Evaluate all risk information from a robustness perspective.

**Disclaimer**: 
    This risk review conclusion is for information purposes only and does not constitute investment advice or transaction commitment. Please make independent judgment based on your own situation."""

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
            inputs: Enter data (investment plan, views of various parties, etc.)
            debate_summary: Debate summary
            state: Current status
            
        Returns:
            User prompt words
        """
        logger.info("🔍 [RiskManagerV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {analysis_date}")
        logger.info(f"📝 input field: {list(inputs.keys())}")
        
        # Examine all parties' risk perspectives
        risky_opinion = inputs.get("risky_opinion", "")
        safe_opinion = inputs.get("safe_opinion", "")
        neutral_opinion = inputs.get("neutral_opinion", "")
        investment_plan = inputs.get("investment_plan", "")
        
        # Convert to string if not
        risky_opinion_str = str(risky_opinion) if risky_opinion else ""
        safe_opinion_str = str(safe_opinion) if safe_opinion else ""
        neutral_opinion_str = str(neutral_opinion) if neutral_opinion else ""
        investment_plan_str = str(investment_plan) if investment_plan else ""
        
        logger.info(f"🔥 Highly elastic scenario perspective type: {type(risky_opinion)}, length: {len(risky_opinion_str)} character")
        logger.info(f"🛡️ Defense Scenario View Type: {type(safe_opinion)}, length: {len(safe_opinion_str)} character")
        logger.info(f"⚖️ Baseline scenario perspective type: {type(neutral_opinion)}, length: {len(neutral_opinion_str)} character")
        logger.info(f"📋 Investment plan type: {type(investment_plan)}, length: {len(investment_plan_str)} character")
        
        # Get company name
        company_name = self._get_company_name(ticker, state)
        logger.info(f"🏢 Company name: {company_name}")
        
        # 🆕 Extract the report content (if it is a dictionary, take the content field)
        def extract_content(report):
            """Extract plain text content from reports"""
            if isinstance(report, dict):
                return report.get('content', str(report))
            return str(report) if report else ""
        
        risky_opinion_content = extract_content(inputs.get("risky_opinion"))
        safe_opinion_content = extract_content(inputs.get("safe_opinion"))
        neutral_opinion_content = extract_content(inputs.get("neutral_opinion"))
        investment_plan_content = extract_content(inputs.get("investment_plan"))
        
        logger.info(f"🔥 Highly elastic situational viewpoint content length: {len(risky_opinion_content)} character")
        logger.info(f"🛡️ Defense Scenario Viewpoint Content Length: {len(safe_opinion_content)} character")
        logger.info(f"⚖️ Baseline Scenario Viewpoint Content Length: {len(neutral_opinion_content)} character")
        logger.info(f"📋 Investment plan content length: {len(investment_plan_content)} character")
        
        # Prepare template variables
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "analysis_date": analysis_date,
            "investment_plan": investment_plan_content,  # ✅ Only the content is passed, not the dictionary
            "risky_opinion": risky_opinion_content,  # ✅ Only the content is passed, not the dictionary
            "safe_opinion": safe_opinion_content,  # ✅ Only the content is passed, not the dictionary
            "neutral_opinion": neutral_opinion_content,  # ✅ Only the content is passed, not the dictionary
            "debate_summary": debate_summary or "",
        }
        
        # Add other inputs to template variables
        for key, value in inputs.items():
            if key not in ["investment_plan", "risky_opinion", "safe_opinion", "neutral_opinion"]:
                template_variables[key] = extract_content(value) if value else ""
        
        # Use the general method of the base class to obtain the user prompt word (the base class will automatically extract system variables from state)
        prompt = self._get_prompt_from_template(
            agent_type="managers_v2",
            agent_name="risk_manager_v2",
            variables=template_variables,
            state=state,  # 🆕 Pass state and the base class will automatically extract system variables
            context=state,
            fallback_prompt=None,
            prompt_type="user"  # 🆕 Specify to obtain user prompt words
        )
        
        if prompt:
            logger.info(f"✅ Obtain risk assessor user prompt words from the template system (length: {len(prompt)})")
            return prompt
        
        # Downgrade: Use default user prompt word
        logger.info("⚠️ Use downgraded user prompt words")
        return f"""Please base on {company_name} ({ticker}) The comprehensive research conclusions and the three-party robustness review opinions form a risk review conclusion:

📊 **Basic information**: 
- Stock code:{ticker}
- Company name:{company_name}
- Analysis date:{analysis_date}

     [Comprehensive research conclusion after risk review]
{investment_plan_content}

 [Highly elastic scenario research observation] 
{risky_opinion_content}

 [Defense Scenario Research Observation]
{safe_opinion_content}

 [Baseline Scenario Research Observation]
{neutral_opinion_content}

 [Summary of multi-scenario research]
{debate_summary or ''}

Based on the above information please:

1. Refining whether the current research conclusions are robust enough.
2. Explain key risks, judgment boundaries, and trigger conditions for upward or downward revisions of conclusions.
3. Follow-up observations and data gaps are given.
4. Make it clear not to directly give specific operation suggestions, position arrangements, target prices, price ranges, stop losses and profits, or execution rhythms.

The output goal is to formulate risk review conclusions rather than specific operational recommendations."""

    def _get_required_inputs(self) -> List[str]:
        """
        Get the required input list
        
        Returns:
            Enter a list of field names
        """
        return [
            "investment_plan",
            "risky_opinion",
            "safe_opinion",
            "neutral_opinion"
        ]

    def _get_company_name(self, ticker: str, state: Dict[str, Any]) -> str:
        """Get company name"""
        # Get it from state first
        if "company_name" in state:
            return state["company_name"]
        
        # Get using StockUtils
        if StockUtils:
            try:
                market_info = StockUtils.get_market_info(ticker)
                if market_info.get('is_china'):
                    from tradingagents.dataflows.interface import get_china_stock_info_unified
                    stock_info = get_china_stock_info_unified(ticker)
                    if "Stock name:" in stock_info:
                        return stock_info.split("Stock name:")[1].split("\n")[0].strip()
            except Exception as e:
                logger.debug(f"Failed to get company name: {e}")
        
        return f"stocks{ticker}"

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute risk management decisions (including schema validation)

        Override parent class methods to add risk_debate_state and final_trade_decision outputs.
        This method uses RiskAssessmentOutput schema to verify the LLM output immediately after the parent class outputs:
        - Verification passed: Serialize the dict into a JSON string and store it in risk_assessment (the downstream consumer remains unchanged),
          And take final_trade_decision directly from validated dict (skipping _extract_final_trade_decision).
        - Validation failed: keep the original text as risk_assessment while writing
          risk_assessment_validation_status / risk_assessment_validation_error Fields are reported explicitly,
          final_trade_decision Use _extract_final_trade_decision to ensure logical compatibility.
        """
        import json

        # Call the parent class method to get basic output
        result = super().execute(state)

        # 🛡️ Q1: When the execution of the parent class fails (except exception packaging dict such as timeout/null response), it is directly transmitted transparently.
        # No schema verification and textualization——Otherwise {'error','success':False} will be _extract_text
        # After stringification, write back the state, and finally mix it into the report in the form of bare dict (see the failure form processing of engine/report_formatter)
        _raw_output = result.get(self.output_field)
        if isinstance(_raw_output, dict) and (
            _raw_output.get("success") is False
            or (
                _raw_output.get("success") is True
                and not str(_raw_output.get("content") or "").strip()
            )
        ):
            logger.warning(
                f"⚠️ [RiskManagerV2] The execution of the parent class failed ({_raw_output.get('error')}) , "
                f"Skip schema verification, and the failure status is directly transmitted to the downstream rendering layer"
            )
            return result

        # Extract the original text of the risk assessment
        risk_assessment_raw = result.get(self.output_field)
        risk_assessment_text = self._extract_text(risk_assessment_raw)

        # 🔥 New: schema verification (make errors explicit, no longer silently cover up)
        validated_dict, validation_error = self._validate_risk_assessment(risk_assessment_text)

        if validation_error is None:
            # ✅ Verification passed: stored as JSON string (keep type=string Compatible with downstream consumers)
            logger.info("✅ [RiskManagerV2] schema Verification passed")
            result[self.output_field] = json.dumps(validated_dict, ensure_ascii=False)
            # Take final_trade_decision directly from validated dict (schema has ensured that the field exists and is compliant)
            final_trade_decision_dict = validated_dict.get("final_trade_decision", {})
            final_trade_decision_markdown = self._format_final_trade_decision_markdown(final_trade_decision_dict)
            # risk_score At the top level of JSON, hang it to final_trade_decision for front-end display
            final_trade_decision = {
                **final_trade_decision_dict,
                "risk_score": validated_dict.get("risk_score"),
                "content": final_trade_decision_markdown,
            }

            # 🔥 P2: Execute the assertion (non-blocking) and merge the results into validation_status
            assertion_result = self._run_assertions(
                raw_text=risk_assessment_text, parsed=validated_dict
            )
            assertion_violations_dump = [v.model_dump() for v in assertion_result.violations]
            if assertion_violations_dump:
                result["risk_assessment_assertion_violations"] = assertion_violations_dump

            if assertion_result.has_error_violation:
                # error Level assertion violation → Downgrade validation_status to failed
                logger.warning(
                    f"⚠️ [RiskManagerV2] Assert error violation {assertion_result.error_count} article, downgrade validation_status"
                )
                result["risk_assessment_validation_status"] = "failed"
                result["risk_assessment_validation_error"] = (
                    f"assert violation: {assertion_result.error_count} Article error"
                )
                self._record_trace_validation(
                    validation_status="failed",
                    validation_error=result["risk_assessment_validation_error"],
                    validation_details={
                        "risk_level": validated_dict.get("risk_level"),
                        "risk_score": validated_dict.get("risk_score"),
                        "assertion_violations": assertion_violations_dump,
                    },
                )
            else:
                # only warning or no violation → keep passed
                result["risk_assessment_validation_status"] = "passed"
                self._record_trace_validation(
                    validation_status="passed",
                    validation_details={
                        "risk_level": validated_dict.get("risk_level"),
                        "risk_score": validated_dict.get("risk_score"),
                        "assertion_violations": assertion_violations_dump,
                    },
                )
        else:
            # ❌ Verification failure: report explicitly (not silently report), retain the original output for troubleshooting
            logger.error(f"❌ [RiskManagerV2] schema Verification failed: {validation_error}")
            logger.error(f"❌ [RiskManagerV2] First 500 characters of raw output: {risk_assessment_text[:500]}")
            result[self.output_field] = risk_assessment_text
            result["risk_assessment_validation_status"] = "failed"
            result["risk_assessment_validation_error"] = validation_error

            # 🔥 P2: Assertion is also executed when verification fails (used to accumulate hit statistics, but does not change the failed status)
            assertion_result = self._run_assertions(
                raw_text=risk_assessment_text, parsed=None
            )
            assertion_violations_dump = [v.model_dump() for v in assertion_result.violations]
            self._record_trace_validation(
                validation_status="failed",
                validation_error=validation_error,
                validation_details={
                    "raw_output_preview": risk_assessment_text[:500],
                    "assertion_violations": assertion_violations_dump,
                },
            )
            # Follow the original _extract_final_trade_decision logic (compatible with historical LLM output format)
            final_trade_decision_dict = self._extract_final_trade_decision(risk_assessment_text)
            final_trade_decision_markdown = self._format_final_trade_decision_markdown(final_trade_decision_dict)
            final_trade_decision = {
                **final_trade_decision_dict,
                "content": final_trade_decision_markdown,
            }

        # Get the existing risk_debate_state from state (keep the original logic unchanged)
        existing_risk_state = state.get("risk_debate_state", {})

        # Build a new risk_debate_state containing judge_decision
        new_risk_state = {
            "judge_decision": risk_assessment_text,  # ✅ Key: Preserve original LLM output text
            "history": existing_risk_state.get("history", ""),
            "risky_history": existing_risk_state.get("risky_history", ""),
            "safe_history": existing_risk_state.get("safe_history", ""),
            "neutral_history": existing_risk_state.get("neutral_history", ""),
            "latest_speaker": "Judge",
            "current_risky_response": existing_risk_state.get("current_risky_response", ""),
            "current_safe_response": existing_risk_state.get("current_safe_response", ""),
            "current_neutral_response": existing_risk_state.get("current_neutral_response", ""),
            "count": existing_risk_state.get("count", 0),
        }

        return {
            **result,
            "risk_debate_state": new_risk_state,
            "final_trade_decision": final_trade_decision,  # ✅ Final research conclusion (including dictionary fields + Markdown content) 
        }

    def _validate_risk_assessment(self, text: str) -> tuple:
        """
        Verify that the LLM output conforms to the RiskAssessmentOutput schema.

        Args:
            text: LLM Output risk assessment text (may be plain JSON, JSON wrapped in markdown code blocks, or plain text)

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
            validated = RiskAssessmentOutput(**json_obj)
            return validated.model_dump(), None
        except ValidationError as e:
            return None, f"Schema Verification failed: {e}"

    def _extract_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for k in ("content", "markdown", "text", "message", "report"):
                v = value.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return str(value).strip()

    def _extract_final_trade_decision(self, risk_assessment_text: str) -> Dict[str, Any]:
        """
        Extract final_trade_decision field from LLM output JSON

        Args:
            risk_assessment_text: LLM Output risk assessment text (may contain JSON)

        Returns:
            final_trade_decision Dictionary, returning default value if extraction fails
        """
        import json
        import re

        if not risk_assessment_text:
            logger.warning("⚠️ [RiskManagerV2] risk_assessment_text Empty and cannot be extracted final_trade_decision")
            return self._get_default_final_decision()

        try:
            # Try to extract JSON code block
            json_obj = None

            if "```json" in risk_assessment_text:
                json_match = re.search(r'```json\s*(.*?)\s*```', risk_assessment_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1).strip()
                    json_obj = json.loads(json_str)
            elif risk_assessment_text.strip().startswith("{"):
                json_obj = json.loads(risk_assessment_text)

            if json_obj and isinstance(json_obj, dict):
                # Extract final_trade_decision field
                final_decision = json_obj.get("final_trade_decision", {})

                if final_decision and isinstance(final_decision, dict):
                    # Make sure confidence is a decimal between 0-1 (expected by the front end)
                    confidence = final_decision.get("confidence", 0.5)
                    if isinstance(confidence, (int, float)) and confidence > 1:
                        # If LLM returns an integer from 0 to 100, convert it to a decimal from 0 to 1
                        final_decision["confidence"] = confidence / 100.0
                    
                    # 🔥🔥🔥 Key fix: Extract risk_score from top-level JSON and add to final_decision
                    # risk_score At the top level of JSON, not in final_trade_decision
                    risk_score = json_obj.get("risk_score")
                    if risk_score is not None:
                        # Make sure risk_score is a float in the range 0-1
                        if isinstance(risk_score, (int, float)):
                            if risk_score > 1:
                                # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                                risk_score = risk_score / 100.0
                            final_decision["risk_score"] = float(risk_score)
                            logger.info(f"✅✅✅ [RiskManagerV2] Extract risk_score from top-level JSON and add to final_trade_decision: {final_decision['risk_score']}")
                        else:
                            logger.warning(f"⚠️ [RiskManagerV2] risk_score Incorrect format: {risk_score}")
                    else:
                        logger.warning("⚠️ [RiskManagerV2] There is no risk_score field in the top-level JSON")
                    
                    # 🔥 Fix: Get it from the action field first, if not, get it from the analysis_view field
                    action = final_decision.get("action")
                    if not action:
                        # If action does not exist, try to get it from analysis_view
                        analysis_view = final_decision.get("analysis_view", "")
                        if analysis_view:
                            # analysis_view May be old terms (bullish/put/neutral) or compliance terms, which are uniformly mapped by action_mapping below when used directly
                            action = analysis_view
                            final_decision["action"] = action
                            logger.info(f"📝 [RiskManagerV2] Extract from analysis_view field action: {action}")
                    
                    if action:
                        # Compliance term mapping: unified mapping to"Optimistic/cautious/neutral"
                        # Prohibited use"Call/Put/Buy/Sell"Terms such as trading instructions or market views
                        action_mapping = {
                            "buy": "optimistic",
                            "sell": "Prudence",
                            "hold": "Neutral",
                            "Add to position": "optimistic",
                            "Reduce positions": "Prudence",
                            "Clearance": "Prudence",
                            "bullish": "optimistic",  # Compatible LLM may still output old terms
                            "Bearish": "Prudence",
                            "optimistic": "optimistic",  # Already a compliance term and remains unchanged
                            "Prudence": "Prudence",
                            "Neutral": "Neutral",
                        }
                        # Make sure to use compliant research conclusion terminology
                        if action in action_mapping:
                            final_decision["action"] = action_mapping[action]
                            logger.info(f"📝 [RiskManagerV2] mapping action: {action} -> {action_mapping[action]}")
                        # If already a compliance term (optimistic/cautious/neutral), leave it unchanged
                    else:
                        # If neither, use default value
                        final_decision["action"] = "Neutral"
                        logger.warning("⚠️ [RiskManagerV2] final_trade_decision There is no action or analysis_view field, use the default value'Neutral'")
                    
                    logger.info(f"✅ [RiskManagerV2] successfully extracted final_trade_decision: action={final_decision.get('action')}, confidence={final_decision.get('confidence')}, risk_score={final_decision.get('risk_score')}")
                    return final_decision
                else:
                    # If there is no final_trade_decision field, build from top-level fields
                    logger.warning("⚠️ [RiskManagerV2] JSON There is no final_trade_decision field in , built from top-level fields")
                    # confidence Returns a decimal between 0-1 (expected by the front end)
                    risk_score = json_obj.get("risk_score", 0.5)
                    investment_adjustment = json_obj.get("investment_adjustment", "Neutral")
                    # Compliance term mapping: unified mapping to"Optimistic/cautious/neutral"
                    action_mapping = {
                        "buy": "optimistic",
                        "sell": "Prudence",
                        "hold": "Neutral",
                        "bullish": "optimistic",
                        "Bearish": "Prudence",
                        "optimistic": "optimistic",
                        "Prudence": "Prudence",
                        "Neutral": "Neutral",
                    }
                    market_view = action_mapping.get(investment_adjustment, investment_adjustment)
                    return {
                        "action": market_view,  # Use Compliance Study Conclusion Terminology
                        "confidence": 1.0 - risk_score if risk_score <= 1 else (100 - risk_score) / 100.0,
                        "price_analysis_range": None,
                        "risk_reference_price": None,
                        "risk_exposure_ratio": "5%",
                        "reasoning": json_obj.get("reasoning", ""),
                        "summary": f"risk level: {json_obj.get('risk_level', 'in')}",
                        "risk_warning": ", ".join(json_obj.get("key_risks", [])[:3]) if json_obj.get("key_risks") else ""
                    }
            else:
                logger.warning("⚠️ [RiskManagerV2] Unable to parse JSON, return to default final_trade_decision")
                return self._get_default_final_decision()

        except Exception as e:
            logger.warning(f"⚠️ [RiskManagerV2] Failed to extract final_trade_decision: {e}")
            return self._get_default_final_decision()

    def _get_default_final_decision(self) -> Dict[str, Any]:
        """Returns the default final_trade_decision (compliant version)"""
        return {
            "action": "Neutral",  # Compliance Study Conclusion Terminology
            "confidence": 0.5,  # 0-1 of decimals (expected by the front end)
            "price_analysis_range": None,
            "risk_reference_price": None,
            "risk_exposure_ratio": "5%",
            "reasoning": "Insufficient risk assessment data, it is recommended to wait and see with caution",
            "summary": "Insufficient data, it is recommended to wait and see",
            "risk_warning": "Please wait for more analysis data"
        }
    
    def _format_final_trade_decision_markdown(self, decision: Dict[str, Any]) -> str:
        """
        Format final_trade_decision dictionary into Markdown format
        
        Args:
            decision: final_trade_decision dictionary
            
        Returns:
            Formatted Markdown string, each field is displayed on a separate line
        """
        if not decision:
            return "## final research conclusion\n\n Insufficient data are available to generate research conclusions."
        
        lines = ["## final research conclusion\n"]
        
        # Field mapping (Chinese name, compliance version)
        field_names = {
            "action": "**research conclusion tendency**",
            "confidence": "**Confidence**",
            "price_analysis_range": "**price analysis range**",
            "risk_reference_price": "**Risk control reference price**",
            "risk_exposure_ratio": "**Risk exposure analysis**",
            "reasoning": "**analytical reasoning**",
            "summary": "**Analysis summary**",
            "risk_warning": "**Risk warning**"
        }

        # Format each field
        action = decision.get("action", "")
        if action:
            # Compliance term mapping: unified mapping to"Optimistic/cautious/neutral", Prohibited use"Call/Put/Buy/Sell"terms such as
            action_mapping = {
                "buy": "optimistic",
                "sell": "Prudence",
                "hold": "Neutral",
                "bullish": "optimistic",
                "Bearish": "Prudence",
                "optimistic": "optimistic",
                "Prudence": "Prudence",
                "Neutral": "Neutral",
            }
            market_view = action_mapping.get(action, action)
            lines.append(f"{field_names.get('action', '**research conclusion tendency**')}: {market_view} (For reference only and does not constitute trading advice)")
        
        confidence = decision.get("confidence")
        if confidence is not None:
            # If it is a decimal between 0 and 1, convert it to a percentage and display it.
            if isinstance(confidence, float) and 0 <= confidence <= 1:
                confidence_display = f"{confidence * 100:.0f}%"
            elif isinstance(confidence, (int, float)) and confidence > 1:
                # If it is an integer from 0 to 100, the percentage is displayed directly.
                confidence_display = f"{int(confidence)}%"
            else:
                confidence_display = str(confidence)
            lines.append(f"{field_names.get('confidence', '**Confidence**')}: {confidence_display}")
        
        price_analysis_range = decision.get("price_analysis_range") or decision.get("target_price")
        if price_analysis_range is not None:
            lines.append(f"{field_names.get('price_analysis_range', '**price analysis range**')}: ¥{price_analysis_range} (For reference only and does not constitute a price prediction)")

        risk_reference_price = decision.get("risk_reference_price") or decision.get("stop_loss")
        if risk_reference_price is not None:
            lines.append(f"{field_names.get('risk_reference_price', '**Risk control reference price**')}: ¥{risk_reference_price} (For reference only and does not constitute trading advice)")

        risk_exposure_ratio = decision.get("risk_exposure_ratio") or decision.get("position_ratio")
        if risk_exposure_ratio:
            lines.append(f"{field_names.get('risk_exposure_ratio', '**Risk exposure analysis**')}: {risk_exposure_ratio} (For reference only and does not constitute trading advice)")
        
        reasoning = decision.get("reasoning")
        if reasoning:
            lines.append(f"\n{field_names.get('reasoning', '**analytical reasoning**')}:\n\n{reasoning}")
        
        summary = decision.get("summary")
        if summary:
            lines.append(f"\n{field_names.get('summary', '**Analysis summary**')}:\n\n{summary}")
        
        risk_warning = decision.get("risk_warning")
        if risk_warning:
            lines.append(f"\n{field_names.get('risk_warning', '**Risk warning**')}:\n\n{risk_warning}")
        
        # Add disclaimer
        lines.append("\n**Disclaimer**: ")
        lines.append("This analysis report is for reference only and does not constitute trading advice. All market views, price ranges, and risk assessments are for analysis reference only.")
        lines.append("It does not constitute specific operational recommendations. Investment is risky and decisions need to be made with caution. Investors should consider the following based on their own circumstances:")
        lines.append("Professional investment consultant opinions and independent investment judgments.")
        
        return "\n".join(lines)

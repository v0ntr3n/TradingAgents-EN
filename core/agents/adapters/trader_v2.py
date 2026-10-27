"""
research integrator v2.0

Research integrator implemented based on TraderAgent base class
Generate user-friendly research briefs based on comprehensive research evidence
 (System output is a summary of research observations and does not constitute investment advice)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..trader import TraderAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)


# ==================== Compliance constraints & Verify contract definition ====================
# Purpose: to form isomorphism with risk_manager_v2 / research_manager_v2"Specification driven"closed loop,
# Let LLM output from"free decision making"downgraded to"Translate according to predefined structure", Eliminate compliance risks at the source.
# Since the trader_v2 output is a user-readable Markdown presentation (unstructured JSON decision),
# Used here"Compliance constraints prompt prefix + term scan verification"lightweight mode,
# JSON schema is not enforced, but compliance violations are reported explicitly to facilitate monitoring and troubleshooting.


# Research Integrator Compliance Constraints & Briefing Structure Contract.
# According to hard constraints"system prompt Formatting requirements must be placed first", This constant will be prepended to
# _build_system_prompt Returning values first ensures that LLM sees compliance and structural constraints first.
TRADER_COMPLIANCE_PROMPT = """ [Compliance Constraints·Must be strictly followed]
1. Prohibited use "bullish" / "Bearish" / "buy" / "sell" / "Add to position" / "Reduce positions" / "hold" / "Clearance" Such as trading instructions or market view terms.
2. Use uniformly "optimistic" / "Prudence" / "Neutral" Express the tendency of research conclusions ("Optimistic/cautious/neutral" It expresses research tendencies and does not constitute trading advice).
3. It is prohibited to give a specific target price or risk attention price, and it cannot be extended to price range, upside/downside space, risk-benefit ratio or operation suggestions.
4. It is prohibited to promise profits or guarantee profits, and risks must be disclosed.
5. All conclusions must be strictly based on the content of the report provided, and no artificial information or internal knowledge of the model may be introduced.

 [Briefing Structure Contract·Must comply]
Please output the Markdown user version of the research report according to the following structure. Each chapter title must appear in the same order:

## One sentence conclusion
 (Summarize the current research judgment in one sentence, using"Optimistic/cautious/neutral"expression tendency)

## Why do you think so
 (Summarize the most critical 2-4 pieces of evidence, each on its own line)

## Limitations of current judgment
 (Explain information gaps, fragile premises, and conclusion boundaries)

## Follow up
 (List the public signals that are most worth following)

## Data boundary description
 (If the report does not provide key information, this must be clearly stated)

## Disclaimer
This research briefing is for informational purposes only and does not constitute investment advice or a trading commitment. Please make independent judgment based on your own situation.

"""


# Compliance disabled glossary (validation pipeline usage, consistent with prompt constraints)
TRADER_FORBIDDEN_TERMS: Tuple[str, ...] = (
    "bullish", "Bearish", "buy", "sell", "Add to position", "Reduce positions", "Clearance",
)

# Note:"hold" May appear in presentations at"hold this view"In non-trading contexts, separate verification will produce false positives.
# Therefore, the forced disable table is not placed, and the constraint is only at the prompt level. If you need more stringent verification, you can add it here.

# Necessary chapter mark for the briefing (used by the verification pipeline, consistent with the chapter name of the database template version 14)
TRADER_REQUIRED_SECTIONS: Tuple[str, ...] = (
    "One sentence conclusion", "Why do you think so",
)


# Try importing utility functions
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None

try:
    from tradingagents.utils.template_client import get_agent_prompt
except (ImportError, KeyError):
    logger.warning("Unable to import get_agent_prompt, default prompt word will be used")
    get_agent_prompt = None

# It is no longer necessary to import get_agent_prompt directly, use the _get_prompt_from_template method of the base class


@register_agent
class TraderV2(TraderAgent):
    """
    research integrator v2.0
    
    Function:
    - Generate user version of research briefing based on comprehensive research conclusions
    - Refining core basis, judgment boundaries and follow-up observations
    - Unify user-readable representations of upstream reports
    
    Workflow:
    1. Read comprehensive research conclusions and all analysis reports
    2. Refining the core information that users care about most
    3. Generate a user version of the research brief
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("trader_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15",
            "investment_plan": {...},
            "market_report": "...",
            "risk_assessment": "..."
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="trader_v2",
        name="research integrator v2.0",
        description="Generate user version of research briefing based on comprehensive research conclusions after risk review",
        category=AgentCategory.TRADER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # Research integrators don't need tools
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion", source="state", state_field="investment_advice", source_state_fields=["investment_plan"], producer_hint="research_manager_v2"),
            AgentInput(name="market_report", type="string", description="Market analysis report", required=False, source="state", state_field="market_report", producer_hint="market_analyst_v2"),
            AgentInput(name="fundamentals_report", type="string", description="Fundamental Analysis Report", required=False, source="state", state_field="fundamentals_report", producer_hint="fundamentals_analyst_v2"),
            AgentInput(name="news_report", type="string", description="News analysis report", required=False, source="state", state_field="news_report", producer_hint="news_analyst_v2"),
            AgentInput(name="sentiment_report", type="string", description="Sentiment Analysis Report", required=False, source="state", state_field="sentiment_report", producer_hint="social_analyst_v2"),
            AgentInput(name="index_report", type="string", description="Market analysis report", required=False, source="state", state_field="index_report", producer_hint="index_analyst_v2"),
            AgentInput(name="sector_report", type="string", description="Sector analysis report", required=False, source="state", state_field="sector_report", producer_hint="sector_analyst_v2"),
            AgentInput(name="bull_report", type="string", description="Optimistic Scenario Research Report", required=False, source="state", state_field="bull_report", producer_hint="bull_researcher_v2"),
            AgentInput(name="bear_report", type="string", description="Prudential Scenario Research Report", required=False, source="state", state_field="bear_report", producer_hint="bear_researcher_v2"),
        ],
        outputs=[
            AgentOutput(name="trader_investment_plan", type="string", description="User version research briefing"),
        ],
        requires_tools=False,
        output_field="trader_investment_plan",
        report_label=" [User version research briefing v2]",
        workflow_stage="trader",
        growth_role="optimizer",
        growth_outputs=["trader_investment_plan"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )

    # Output field names (consistent with field names expected by the report formatter)
    output_field = "trader_investment_plan"
    
    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (refer to the implementation of fundamentals_analyst_v2)
        
        Args:
            state: Workflow status (used to extract template variables)
        
        Returns:
            System prompt word
        """
        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
        logger.info("🔍 [TraderV2] Start building system prompt words")
        
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
        
        prompt = self._get_prompt_from_template(
            agent_type="trader_v2",
            agent_name="trader_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )

        # 🔥 According to hard constraints"system prompt Formatting requirements must be placed first", 
        # constrain compliance & The briefing structure contract is placed at the front of prompt to ensure that LLM sees the compliance constraints first.
        # It takes effect immediately without relying on database migration.
        if prompt:
            prompt = TRADER_COMPLIANCE_PROMPT + prompt
            logger.info(f"📝 System prompt word length: {len(prompt)} Characters (including compliance constraints)")
            logger.debug("✅ Obtain research integrator system prompt words from the template system (compliance constraints are preset)")
            return prompt

        logger.warning("⚠️ Failed to obtain the system prompt word from the template system, use the default prompt word")

        # Default system prompt word (compliant version)— Also pre-compliance constraints ensure that the fallback path is also subject to constraints
        return TRADER_COMPLIANCE_PROMPT + """You are a research integrator responsible for generating user-generated research briefs based on comprehensive research findings from risk reviews.

## your responsibilities

    1. **Integrating research conclusions**: Translate comprehensive research findings into a presentation readable by ordinary users
    2. **Refining key information**: Summarize why we think so, key differences, uncertainties and follow-up concerns
    3. **Preserve research boundaries**: Explain the prerequisites for the current judgment to be established and the conditions under which it may fail.
    4. **unified expression caliber**: Organize multiple upstream reports into a consistent, clear, and readable final brief

## Analysis principles

    - **Based on research conclusions**: Organize content based on the research manager s comprehensive research conclusions and risk review conclusions.
    - **Does not extend to trading plan**: It is not allowed to output buying and selling, adding or subtracting positions, position ratio, target price, price range, risk focus and return focus price or execution rhythm.
    - **Objective presentation of evidence**: Clearly explain the basis supporting the judgment, key uncertainties and follow-up observations.
    - **Maintain user readability**: Use concise Chinese, do not stack jargon, and do not create information that is not provided

## Important note

    - **Based on existing data**: You can only use the provided analysis reports and upstream research conclusions to generate a user version of the research briefing
    - **Risk review is completed upstream**: This stage is responsible for integrating expressions and no longer regenerating trading plans or risk control plans.
    - **No external inferences are introduced**: Do not use internal knowledge of the model, information outside the material, or additional price deductions to supplement conclusions.

**Disclaimer**: 
    This research briefing is for informational purposes only and does not constitute investment advice or a trading commitment. Please make independent judgment based on your own situation."""

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the generation of research briefings and add explicit reporting of compliance verification.

        Override parent class method to add compliance term scanning and structural integrity check after LLM output,
        Make errors explicit (see risk_manager_v2 / research_manager_v2 s validation pipeline mode).

        Verification strategy:
        - Verification passed: Settings trader_plan_validation_status="passed"
        - Verification failed: retain the original output (the user-readable briefing is not automatically modified to avoid introducing errors),
          settings trader_plan_validation_status="failed" + trader_plan_validation_warning
        """
        logger.info("=" * 80)
        logger.info("📝 [TraderV2] Start executing user version research briefing generation")
        logger.info("=" * 80)

        # P1: Start execution trace collection (TraderV2 manages it by itself, because the parent class TraderAgent is not within the scope of ManagerAgent transformation)
        from core.agents.execution_trace_recorder import (
            start_execution_trace, is_trace_enabled
        )
        recorder = None
        if is_trace_enabled():
            try:
                recorder = start_execution_trace(self, state)
            except Exception as e:
                logger.warning(f"⚠️ [TraderV2] Failed to start trajectory collection: {e}")

        try:
            # record input
            if recorder:
                _input_keys = [
                    "investment_plan", "market_report", "fundamentals_report",
                    "news_report", "sentiment_report", "index_report", "sector_report",
                    "bull_report", "bear_report", "risk_assessment",
                ]
                _inputs = {k: state.get(k) for k in _input_keys if state.get(k)}
                recorder.record_inputs(_inputs)

            # Call the parent class method to get basic output
            import time as _time
            _t0 = _time.time()
            result = super().execute(state)
            _llm_duration_ms = int((_time.time() - _t0) * 1000)

            # Extract briefing content (compatible with both dictionary/string output formats)
            decision_value = result.get(self.output_field, "")
            if isinstance(decision_value, dict):
                decision_text = (
                    decision_value.get("content", "")
                    or decision_value.get("markdown", "")
                    or str(decision_value)
                )
            else:
                decision_text = str(decision_value) if decision_value else ""

            # P1: Logging output snapshot and token_usage (extracted from TraderAgent stash's _last_llm_response)
            if recorder:
                _llm_response = getattr(self, "_last_llm_response", None)
                if _llm_response is not None:
                    recorder.record_llm_response(_llm_response, llm_duration_ms=_llm_duration_ms)
                else:
                    # response When unreachable, only output snapshots are recorded (no token_usage)
                    from app.pro.models.execution_trace import OutputSnapshot
                    recorder.trace.output = OutputSnapshot(
                        output_raw_length=len(decision_text),
                        output_raw_preview=decision_text[:500] if decision_text else None,
                        output_parsed_keys=list(decision_value.keys()) if isinstance(decision_value, dict) else [],
                        output_parsed_success=decision_value.get("success", True) if isinstance(decision_value, dict) else True,
                        output_parsed_type="dict" if isinstance(decision_value, dict) else type(decision_value).__name__,
                    )
                    recorder.trace.llm_duration_ms = _llm_duration_ms
                recorder.record_parsed_output(decision_value if isinstance(decision_value, dict) else decision_text)

            # 🔥 Compliance verification (make errors explicit, don't hide behind them silently)
            validation_warning = self._validate_trader_output(decision_text)

            # 🔥 P2: Execution assertion (non-blocking). TraderV2 inherits TraderAgent (not ManagerAgent),
            # Directly call the assertion_executor singleton (parsed=None, Because the output is Markdown).
            from app.core.config import settings as _settings
            assertion_violations_dump: list = []
            assertion_has_error = False
            assertion_error_count = 0
            if getattr(_settings, "AGENT_ASSERTION_ENABLED", True):
                try:
                    from core.agents.assertion_executor import assertion_executor
                    assertion_result = assertion_executor.run_assertions_sync(
                        agent_id=self.agent_id,
                        raw_text=decision_text,
                        parsed=None,
                    )
                    assertion_violations_dump = [v.model_dump() for v in assertion_result.violations]
                    assertion_has_error = assertion_result.has_error_violation
                    assertion_error_count = assertion_result.error_count
                    if assertion_violations_dump:
                        result["trader_plan_assertion_violations"] = assertion_violations_dump
                except Exception as assertion_exc:
                    logger.warning(f"⚠️ [TraderV2] Assertion execution failed (does not affect agent): {assertion_exc}")

            # Merge assertion results into validation_status
            if validation_warning is None and not assertion_has_error:
                logger.info("✅ [TraderV2] Compliance verification passed")
                result["trader_plan_validation_status"] = "passed"
                if recorder:
                    # Update the memory object with set_validation, ensuring finish() The insert carries validation
                    #  (trader_v2 The finish is later than this call in finally, if using record_trace_validation
                    #  The DB update will be no-op because the document is not inserted, and then overwritten by finish to None)
                    recorder.set_validation(
                        validation_status="passed",
                        validation_details={"assertion_violations": assertion_violations_dump},
                    )
            else:
                # Either compliance check or assertion error or violation fails. → failed
                if validation_warning:
                    logger.warning(f"⚠️ [TraderV2] Compliance verification found problems: {validation_warning}")
                    logger.warning(f"⚠️ [TraderV2] First 500 characters of raw output: {decision_text[:500]}")
                if assertion_has_error:
                    logger.warning(
                        f"⚠️ [TraderV2] Assert error violation {assertion_error_count} Article"
                    )
                result["trader_plan_validation_status"] = "failed"
                if validation_warning:
                    result["trader_plan_validation_warning"] = validation_warning
                if assertion_has_error:
                    result["trader_plan_validation_error"] = (
                        f"assert violation: {assertion_error_count} Article error"
                    )
                if recorder:
                    recorder.set_validation(
                        validation_status="failed",
                        validation_error=validation_warning or f"assert violation: {assertion_error_count} Article error",
                        validation_details={
                            "raw_output_preview": decision_text[:500],
                            "assertion_violations": assertion_violations_dump,
                        },
                    )

            logger.info("✅ [TraderV2] The user version of the research briefing is generated")
            logger.info("=" * 80)
            return result

        except Exception as e:
            if recorder:
                recorder.record_error(e)
            raise
        finally:
            if recorder:
                recorder.finish()

    def _validate_trader_output(self, text: str) -> Optional[str]:
        """
        Verify LLM output for compliance and structural integrity.

        Since the trader_v2 output is a user-readable Markdown presentation (unstructured JSON),
        This method uses"Compliance terminology scan + Structural integrity check"lightweight mode,
        Returns a warning string (preserving the original output) if a violation is detected, or None if a violation is detected.

        Args:
            text: LLM Output research briefing text

        Returns:
            None: Verification passed
            str: Verification warning description (including violation details) for explicit reporting
        """
        if not text or not text.strip():
            return "Output is empty"

        warnings: List[str] = []

        # 1. Compliance term scanning (detecting trading order or market opinion terms)
        found_forbidden = [term for term in TRADER_FORBIDDEN_TERMS if term in text]
        if found_forbidden:
            warnings.append(f"Non-compliant term detected: {found_forbidden}")

        # 2. Structural integrity checks (required section markers)
        missing_sections = [s for s in TRADER_REQUIRED_SECTIONS if s not in text]
        if missing_sections:
            warnings.append(f"Missing required chapters: {missing_sections}")

        if warnings:
            return "; ".join(warnings)
        return None

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        investment_plan: Dict[str, Any],
        all_reports: Dict[str, Any],
        historical_trades: Optional[List[Dict[str, Any]]],
        state: Dict[str, Any]
    ) -> str:
        """
        Construct user prompt words (refer to the implementation of research_manager_v2)
        
        Args:
            ticker: Stock code
            analysis_date: Analysis date
            investment_plan: investment plan
            all_reports: All report dictionaries
            historical_trades: Historical transaction records
            state: Workflow status
            
        Returns:
            User prompt words
        """
        logger.info("🔍 [TraderV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {analysis_date}")
        
        if state is None:
            state = {}
        
        # Get company name and market information
        company_name = ticker
        currency_name = "RMB"
        currency_symbol = "¥"
        
        if StockUtils and ticker:
            try:
                market_info = StockUtils.get_market_info(ticker)
                company_name = self._get_company_name(ticker, market_info)
                currency_name = market_info.get('currency_name', "RMB")
                currency_symbol = market_info.get('currency_symbol', "¥")
            except Exception as e:
                logger.warning(f"Failed to obtain market information: {e}")
        
        # 🆕 Extract the report content (if it is a dictionary, take the content field)
        def extract_content(report):
            """Extract plain text content from reports"""
            if isinstance(report, dict):
                return report.get('content', str(report))
            return str(report) if report else ""
        
        # Prepare template variables (refer to the implementation of research_manager_v2)
        # 🔑 Note: The risk review has been completed upstream, and this stage is responsible for integrating and presenting comprehensive research conclusions.
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "analysis_date": analysis_date,
            "current_date": analysis_date,
            "currency_name": currency_name,
            "currency_symbol": currency_symbol,
            # Investment plan (convert to string)
            "investment_plan": extract_content(investment_plan) if investment_plan else "",
            # 🔑 Available analysis reports (excluding risk_assessment)
            "market_report": extract_content(all_reports.get("market_report", "")),
            "fundamentals_report": extract_content(all_reports.get("fundamentals_report", "")),
            "news_report": extract_content(all_reports.get("news_report", "")),
            "sentiment_report": extract_content(all_reports.get("sentiment_report", "")),
            # Historical transaction records (converted to string)
            "historical_trades": "\n".join([str(trade) for trade in historical_trades[:3]]) if historical_trades else "",
        }
        
        # 🔑 Add other reports to template variables (excluding risk_assessment)
        # These reports include:sector_report, index_report, bull_report, bear_report Wait
        excluded_keys = ["risk_assessment", "market_report", "fundamentals_report", "news_report", "sentiment_report"]
        for key, value in all_reports.items():
            if key not in excluded_keys:
                template_variables[f"report_{key}"] = extract_content(value)
        
        # Use the general method of the base class to obtain user prompt words (refer to research_manager_v2)
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        prompt = self._get_prompt_from_template(
            agent_type="trader_v2",
            agent_name="trader_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        
        if prompt:
            logger.info(f"✅ Get research integrator v2.0 user prompt words from the template system (length: {len(prompt)})")
            logger.info(f"📝 The first 500 characters of the user prompt word:\n{prompt[:500]}...")
            return prompt
        
        # Downgrade: Use default user prompt word
        logger.warning("⚠️ The user prompt word is not obtained from the template system, and the default prompt word is used.")

        summary_source = extract_content(all_reports.get("final_trade_decision", "")) or extract_content(all_reports.get("risk_management_decision", "")) or extract_content(investment_plan)
        prompt = f"""please for {company_name} ({ticker}) Generate a user version of the research brief:

## Basic information
- **Stock code**: {ticker}
- **Company name**: {company_name}
- **Analysis date**: {analysis_date}
- **currency unit**: {currency_name} ({currency_symbol}) 

    ## Comprehensive research conclusion after risk review

    {extract_content(investment_plan) if investment_plan else "No comprehensive research conclusion"}

    ## One sentence conclusion

    {summary_source or "Please refine a conclusion based on the following materials."}

## Available analysis reports

### 1. Market analysis report
{extract_content(all_reports.get("market_report", "")) or "No market analysis report"}

### 2. Fundamental Analysis Report
{extract_content(all_reports.get("fundamentals_report", "")) or "No fundamental analysis report"}

### 3. News analysis report
{extract_content(all_reports.get("news_report", "")) or "No news analysis report"}

### 4. Sector analysis report
{extract_content(all_reports.get("sector_report", "")) or "No sector analysis report"}

### 5. Market analysis report
{extract_content(all_reports.get("index_report", "")) or "No market analysis report"}

### 6. Optimistic Scenario Research Report
{extract_content(all_reports.get("bull_report", "")) or "No optimistic scenario research report"}

### 7. Prudential Scenario Research Report
{extract_content(all_reports.get("bear_report", "")) or "No prudent scenario research report"}

## Historical transaction records (if any)

{chr(10).join([str(trade) for trade in historical_trades[:3]]) if historical_trades else "No historical transaction record"}

## Mission requirements

Please generate a user-readable research briefing based on the above comprehensive research conclusions and various analysis reports, preferably including the following structure:

1. **One sentence conclusion**: Summarize the current research judgment in one sentence.
2. **Why do you think so**: Summarize the most critical 2-4 pieces of evidence.
3. **Limitations of current judgment**: Explain information gaps, fragile premises, and conclusion boundaries.
4. **Follow up**: Make a list of the public signals that are most worth continuing to track.
5. **Data boundary description**: If the report does not provide critical information, this must be clearly stated.

**Important tips**: 
- It is not allowed to output buying and selling, adding or subtracting positions, position ratio, target price, price range, risk focus and return focus price or execution rhythm.
- Can explain how prices, valuations and financial data influence research judgments, but may not extend to operational recommendations
- Must use {currency_name} ({currency_symbol}) as a monetary unit
- The language must be understandable by ordinary users, and information outside of the material must not be reproduced.

**Disclaimer**: 
This research briefing is for informational purposes only and does not constitute investment advice or a trading commitment. Please make independent judgment based on your own situation."""
        
        return prompt
    
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


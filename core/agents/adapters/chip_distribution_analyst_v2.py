"""
Chip distribution analyst Agent v2.0

A chip distribution analyst implemented based on the AnalystAgent base class.
Analyze the distribution of stock chips and evaluate the profit ratio, average cost and chip concentration.
The prompt words are configured in the database template and can be modified by the user.
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from ..analyst import AnalystAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)

# Try importing utility functions
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None


@register_agent
class ChipDistributionAnalystV2(AnalystAgent):
    """
    Chip distribution analyst v2.0

    Function:
    - Get stock chip distribution data
    - Analyze profit ratio (floating profit/floating loss situation)
    - Analyze average holding costs
    - Assess chip concentration (90%/70% range)
    - Generate chip distribution analysis report

    Workflow:
    1. Call the chip distribution tool to obtain data (AkShare is preferred, Tushare is used as backup)
    2. Use LLM to deeply analyze the meaning of chip distribution
    3. Generate chip distribution analysis report
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="chip_distribution_analyst_v2",
        name="Chip distribution analyst v2.0",
        description="Analyze stock chip distribution, evaluate profit ratio, average cost and chip concentration, and generate chip distribution analysis report",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        icon="🧮",
        color="#e74c3c",
        tags=["Chip distribution", "Holding cost", "Profit ratio", "v2.0"],
        default_tools=["get_chip_distribution"],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="chip_report", type="string", description="Chip distribution analysis report"),
        ],
        requires_tools=True,
        output_field="chip_report",
        report_label=" [Chip distribution analysis v2]",
        workflow_stage="analyst",
        execution_order=15,
    )

    # Analyst type
    analyst_type = "chip_distribution"

    # Output field name
    output_field = "chip_report"

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Perform chip distribution analysis"""
        try:
            ticker, analysis_date = self._extract_common_params(state)
            context = state.get("context")
            overrides = state.get("prompt_overrides") or {}
            system_override = overrides.get("system")
            user_override = overrides.get("user")
            analysis_override = overrides.get("analysis")

            if not ticker:
                raise ValueError("Missing required parameters: ticker")

            # Build system prompt words
            system_prompt = system_override
            if not system_prompt:
                template_variables = {
                    "ticker": ticker,
                    "analysis_date": analysis_date,
                    "current_date": analysis_date,
                    "tool_names": ", ".join([t.name for t in self._langchain_tools]) if self._langchain_tools else "",
                }
                # Inject company name
                company_name = state.get("company_name", "")
                if not company_name and StockUtils and ticker:
                    try:
                        market_info = StockUtils.get_market_info(ticker)
                        template_variables["company_name"] = market_info.get("company_name", ticker)
                        template_variables["market_name"] = market_info.get("market_name", "China A shares")
                    except Exception:
                        template_variables["company_name"] = ticker
                        template_variables["market_name"] = "China A shares"
                else:
                    template_variables["company_name"] = company_name or ticker
                    template_variables["market_name"] = state.get("market_name", "China A shares")

                system_prompt = self._get_prompt_from_template(
                    agent_type="analysts_v2",
                    agent_name="chip_distribution_analyst_v2",
                    variables=template_variables,
                    state=state,
                    context=context,
                    fallback_prompt=None,
                    prompt_type="system"
                )

            if not system_prompt:
                system_prompt = self._build_system_prompt(state=state)

            # Build user prompt words
            user_prompt = user_override
            if not user_prompt:
                user_prompt = self._build_user_prompt(ticker, analysis_date, state)

            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            if self._llm:
                if self._langchain_tools:
                    analysis_prompt = analysis_override or self._build_analysis_prompt(ticker, analysis_date)
                    report = self.invoke_with_tools(messages, analysis_prompt=analysis_prompt)
                    tool_summary = self._format_tool_call_summary()
                    if self._chip_tool_unavailable():
                        report = self._build_unavailable_report(ticker, analysis_date)
                else:
                    response = self._invoke_llm_with_trace(messages)
                    report = response.content if hasattr(response, "content") else str(response)
                    tool_summary = ""
            else:
                raise ValueError("LLM not initialized")

            result = {self.output_field: report}
            if tool_summary:
                result["tool_call_summaries"] = {self.analyst_type: tool_summary}
            return result

        except Exception as e:
            logger.error(f"[{self.agent_id}] Execution failed: {e}", exc_info=True)
            return {self.output_field: f"Chip distribution analysis failed: {str(e)}"}

    def _chip_tool_unavailable(self) -> bool:
        summaries = getattr(self, "_tool_call_summaries_collected", []) or []
        chip_calls = [s for s in summaries if s.get("tool_name") == "get_chip_distribution"]
        if not chip_calls:
            return False

        last_call = chip_calls[-1]
        result = str(last_call.get("result_preview") or "")
        error_markers = ("❌", "Tool execution failed", "Unable to obtain", "Failed to obtain")
        return (not last_call.get("success")) or any(marker in result for marker in error_markers)

    def _build_unavailable_report(self, ticker: str, analysis_date: str) -> str:
        summaries = getattr(self, "_tool_call_summaries_collected", []) or []
        chip_calls = [s for s in summaries if s.get("tool_name") == "get_chip_distribution"]
        reason = "The chip distribution tool did not return valid data"
        if chip_calls:
            last_call = chip_calls[-1]
            reason = last_call.get("error") or last_call.get("result_preview") or reason

        return f"""⚠️ **Chip distribution data is temporarily unavailable**

Stock code:{ticker}  
Analysis date:{analysis_date}

A valid chip distribution analysis report could not be generated this time because the chip distribution tool did not return analyzable data.

**Tool return information**: {reason}

In order to avoid misleading conclusions, this node does not guess or fill in the chip structure, profit ratio, average cost, support pressure level and other indicators based on the model. Please try again later, or check the AkShare/Tushare data source, network connection, and native socket resource status."""

    def _build_analysis_prompt(self, ticker: str, analysis_date: str) -> str:
        return f"""Based on the real data returned by the chip distribution tool, generate {ticker} in {analysis_date} Chip distribution analysis report.

Requirements:
1. Only the data actually returned in the ToolMessage can be used, and model knowledge must not be used to determine whether the current year or date exists.
2. If the tool returns with ❌ begins, or contains Tool execution failed  Unable to obtain  Failed to obtain , Please explain directly Chip distribution data is temporarily unavailable , And cite the reason why the tool failed.
3. When a tool fails, it is prohibited to make up profit ratios, average costs, chip ranges, and support pressure levels, and do not make inferences that future dates cannot be analyzed.
4. When the tool is successful, analysis will be conducted around the profit ratio, average cost, 90%/70% chip range, concentration, and support and pressure relationships.
5. Use Chinese Markdown output."""

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """Build default system prompt words (database template takes priority)"""
        if state is None:
            state = {}

        template_variables = {}
        if "ticker" in state:
            template_variables["ticker"] = state["ticker"]
        analysis_date = state.get("analysis_date") or state.get("trade_date")
        if analysis_date:
            if isinstance(analysis_date, str) and len(analysis_date) > 10:
                analysis_date = analysis_date.split()[0]
            template_variables["current_date"] = analysis_date
            template_variables["analysis_date"] = analysis_date

        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="chip_distribution_analyst_v2",
            variables=template_variables,
            state=state,
            context=state.get("context"),
            fallback_prompt=None,
            prompt_type="system"
        )
        if prompt:
            return prompt

        return """You are a professional A-share chip distribution analyst who is good at gaining insight into the market game pattern through chip distribution data.

Your responsibilities:
1. Interpret the profit ratio of chips (the proportion of chips with floating profit under the current price)
2. Analyze the relationship between average holding costs and current prices
3. Evaluate the 90%/70% chip concentration range and concentration ratio
4. Determine the upper pressure and lower support
5. Comprehensive study and judgment of main position intentions and trends

Analysis requirements:
- Objectively interpret chip data to avoid subjective assumptions
- Determine the severity of selling pressure based on profit ratio
- Judging trend stability based on concentration
- Provide clear support/pressure level judgments
- Use Chinese output

Output format:
Please output the chip distribution analysis report in a structured manner, including:
- Chip profit status
- cost structure analysis
- Chip concentration assessment
- Support pressure level analysis
- Comprehensive research and judgment
"""

    def _build_user_prompt(self, ticker: str, analysis_date: str, state: Dict[str, Any]) -> str:
        """Construct user prompt words (database template is preferred)"""
        if state is None:
            state = {}

        company_name = state.get("company_name", ticker)
        market_name = state.get("market_name", "China A shares")

        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "market_name": market_name,
            "analysis_date": analysis_date,
            "current_date": analysis_date,
            "tool_names": ", ".join([t.name for t in self._langchain_tools]) if self._langchain_tools else "",
        }

        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="chip_distribution_analyst_v2",
            variables=template_variables,
            state=state,
            context=state.get("context"),
            fallback_prompt=None,
            prompt_type="user"
        )
        if prompt:
            return prompt

        return f"""Please analyze {company_name} ({ticker}) in {analysis_date} Distribution of chips:

Stock code:{ticker}
Company name:{company_name}
Analysis date:{analysis_date}
Market:{market_name}

Please call the chip distribution tool to obtain data, and then generate a detailed chip distribution analysis report.
Key analysis: profit ratio, average cost, chip concentration, support and pressure level."""


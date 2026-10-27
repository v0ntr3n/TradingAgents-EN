"""
ETF Analyst Agent v2.0

Analyze ETF net value, size, fee rate, tracking error, etc. (ETF has no PE/PB/ROE)
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from ..base import BaseAgent
from ..config import AgentConfig, AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class EtfAnalystAgentV2(BaseAgent):
    """
    ETF Analyst Agent v2.0

    Analyze ETF s net value, size, expense ratio, tracking index, tracking error, etc.
    ETF No PE/PB/ROE, use proprietary metrics.
    """

    metadata = AgentMetadata(
        id="etf_analyst_v2",
        name="ETF analyst v2.0",
        description="Analyze ETF net worth, size, expense ratio, tracking error, and more. ETFs have no PE/PB/ROE.",
        category=AgentCategory.ANALYST,
        license_tier=LicenseTier.FREE,
        default_tools=["get_etf_fundamentals"],
        version="2.0.0",
        inputs=[
            AgentInput(name="ticker", type="string", description="ETF code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="fundamentals_report", type="string", description="ETF analysis report"),
        ],
        requires_tools=True,
        output_field="fundamentals_report",
        report_label=" [ETF Analysis v2]",
        workflow_stage="analyst",
        growth_role="extractor",
        growth_outputs=["fundamentals_report"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    )

    def __init__(
        self,
        config: Optional[Any] = None,
        llm: Optional[BaseChatModel] = None,
        tool_ids: Optional[list] = None
    ):
        super().__init__(config=config, llm=llm, tool_ids=tool_ids)
        if tool_ids is None and llm is not None:
            tool_ids = self.load_tools_from_config()
            if tool_ids:
                self._load_tools_v2(tool_ids)

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state.get("ticker") or state.get("company_of_interest")
        trade_date = state.get("trade_date") or state.get("end_date") or state.get("analysis_date")

        if not ticker:
            raise ValueError("Missing required parameter: ticker")

        logger.info(f"Start ETF Analysis: {ticker} (Date: {trade_date})")

        system_prompt = self._build_system_prompt(state)
        user_prompt = self._build_user_prompt(ticker, trade_date, state)

        system_prompt = self._apply_global_trading_advice_guard(system_prompt)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        if self._llm and self.tools:
            analysis = self.invoke_with_tools(messages, analysis_prompt=self._build_analysis_prompt(ticker))
        else:
            logger.warning("Without LLM or tools configured, simulation results are returned")
            analysis = self._generate_mock_report(ticker, trade_date)

        return {"fundamentals_report": analysis}

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        template_variables = {}
        if state:
            template_variables["ticker"] = state.get("ticker", "")
            template_variables["company_name"] = state.get("company_name", "")
            analysis_date = state.get("analysis_date") or state.get("trade_date")
            if analysis_date:
                template_variables["current_date"] = str(analysis_date)[:10]
                template_variables["analysis_date"] = str(analysis_date)[:10]

        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="etf_analyst_v2",
            variables=template_variables,
            state=state or {},
            context=state.get("context") if state else None,
            fallback_prompt=None,
            prompt_type="system"
        )

        if prompt:
            return prompt

        return """You are a professional ETF analyst. ETFs are funds that track indexes and do not have individual stock valuation indicators such as PE/PB/ROE.

Your task:
1. Call get_etf_fundamentals to get ETF data
2. Analyze net worth, size, tracking index, rise and fall
3. Assess tracking error, liquidity risk
4. Provide research observations

The use of PE/PB/ROE to analyze ETFs is prohibited."""

    def _build_user_prompt(self, ticker: str, trade_date: str, state: Dict[str, Any] = None) -> str:
        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="etf_analyst_v2",
            variables={"ticker": ticker, "analysis_date": trade_date or "", "current_date": trade_date or ""},
            state=state or {},
            context=state.get("context") if state else None,
            fallback_prompt=None,
            prompt_type="user"
        )
        if prompt:
            return prompt
        return f"Please analyze ETF {ticker}. Analysis date:{trade_date}. Please call the tool to obtain data and generate a report."

    def _build_analysis_prompt(self, ticker: str) -> str:
        return f"""Based on the obtained data, generate {ticker} ETF analysis reports, including:
1. Net worth and size
2. Track index performance
3. Liquidity assessment
4. research observation
Use of PE/PB/ROE is prohibited."""

    def _generate_mock_report(self, ticker: str, trade_date: str) -> str:
        return f"""ETF Analysis Report (Simulation)

code: {ticker}
Date: {trade_date}

Net worth trend: data to be obtained
Scale: data to be obtained
Tracking index: data to be obtained
Suggestion: Please configure the data source and then analyze again."""

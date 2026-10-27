"""
data preparer v2.0

Intelligent data preparation agent understands requirements through LLM and calls tools to obtain data
Store prepared data in context for subsequent use by agents
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..analyst import AnalystAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class DataPreparerV2(AnalystAgent):
    """
    Data Preparer v2.0 - Intelligent Data Preparation Agent

    Function:
    - 🤖 Call LLM to understand data preparation needs
    - 🔧 Bind all technical tools (market data, financial data, news, etc.)
    - 🎯 Intelligently select the tool you need to call based on the prompt word
    - 📦 Store prepared data in context
    - 🔗 Subsequent agents can read data from the context

    Workflow:
    1. Read input parameters (ticker, analysis_date, data_requirements etc.)
    2. LLM Understand what data needs to be prepared
    3. Intelligently select and call relevant tools
    4. Organize data returned by tools
    5. Store data in context field
    6. Returns the prepared context

    Example:
        from core.agents import create_agent
        from core.llm import UnifiedLLMClient

        llm = UnifiedLLMClient(provider="openai", model="gpt-4")
        agent = create_agent("data_preparer_v2", llm=llm)

        result = agent.execute({
            "ticker": "000001",
            "analysis_date": "2026-02-19",
            "data_requirements": "Need to prepare: 1. Basic stock information 2. Quotes in the last 30 days 3. Latest financial data"
        })

        # result contains:
        # - context: Prepared data context (Markdown format)
        # - data_summary: Data summary
        # - tools_used: List of tools used
    """

    metadata = AgentMetadata(
        id="data_preparer_v2",
        name="data preparer v2",
        description="Intelligent data preparation agent understands the requirements through LLM and calls tools to obtain data, which is stored in the context for subsequent use.",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=["market", "fundamentals", "news", "social"],  # All data tools are bound by default
        icon="🔧",
        color="#3498db",
        tags=["data", "Prepare", "Pre-processing", "Smart", "v2.0"],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code", required=True),
            AgentInput(name="analysis_date", type="string", description="Analysis date", required=False),
            AgentInput(name="data_requirements", type="string", description="Data requirement description", required=False),
        ],
        outputs=[
            AgentOutput(name="context", type="string", description="Prepared data context"),
            AgentOutput(name="data_summary", type="string", description="Data summary"),
            AgentOutput(name="tools_used", type="array", description="List of tools used"),
        ],
        requires_tools=True,
        output_field="context",
        report_label=" [Data preparation]",
        execution_order=0,  # executed first
    )

    analyst_type = "data_preparer"
    output_field = "context"

    def __init__(
        self,
        llm: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize data preparer

        Args:
            llm: LLM client
            config: Agent configuration
            **kwargs: Other parameters
        """
        super().__init__(llm=llm, config=config, **kwargs)

        logger.debug(f"DataPreparerV2 Initialization completed")

    def _build_system_prompt(self, state: Dict[str, Any]) -> str:
        """
        Build system prompt words

        Args:
            state: Workflow status

        Returns:
            System prompt word
        """
        # Try to get the prompt word from the template system
        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="data_preparer_v2",
            variables={},
            context=None,
            fallback_prompt=None,
            state=state,
            prompt_type="system"
        )

        if prompt:
            return prompt

        # Default prompt word
        return """You are an intelligent data preparation assistant responsible for preparing the necessary data for stock analysis.

Your task:
1. Understand users data needs
2. Choose the right tool to get your data
3. Organize data and generate structured context

Available tools:
- market: Obtain market data (price, trading volume, rise and fall, etc.)
- fundamentals: Obtain financial data (financial reports, valuation indicators, etc.)
- news: Get news
- social: Get social media sentiment

Output requirements:
- Organize data in Markdown format
- Include clear chapter titles
- Data must be accurate and complete
- Highlight key information

Example output:
```markdown
# Data preparation report

## Basic information
- Stock code: 000001
- Company name: Ping An Bank
- Industry: bank

## market data
- current price: 12.50 Yuan
- Increase or decrease: +2.5%
- Volume: 1000 10,000 shares

## financial data
- P/E ratio: 5.2
- price to book ratio: 0.8
- ROE: 12%
```
"""

    def _build_user_prompt(self, state: Dict[str, Any]) -> str:
        """
        Build user prompt words

        Args:
            state: Workflow status

        Returns:
            User prompt words
        """
        ticker = state.get("ticker") or state.get("stock_code", "")
        analysis_date = state.get("analysis_date") or datetime.now().strftime("%Y-%m-%d")
        data_requirements = state.get("data_requirements", "")

        # Try to get the prompt word from the template system
        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="data_preparer_v2",
            variables={
                "ticker": ticker,
                "analysis_date": analysis_date,
                "data_requirements": data_requirements,
            },
            context=None,
            fallback_prompt=None,
            state=state,
            prompt_type="user"
        )

        if prompt:
            return prompt

        # Default prompt word
        if data_requirements:
            return f"""please for stock {ticker} Prepare the following data (date of analysis:{analysis_date}) : 

{data_requirements}

Please call relevant tools to obtain data and generate structured data context."""
        else:
            return f"""please for stock {ticker} Prepare basic data required for analysis (date of analysis:{analysis_date}) : 

1. Basic stock information (company name, industry, sector)
2. Latest market data (price, market capitalization, PE, PB)
3. Recent market trends
4. Latest financial data (if available)

Please call relevant tools to obtain data and generate structured data context."""


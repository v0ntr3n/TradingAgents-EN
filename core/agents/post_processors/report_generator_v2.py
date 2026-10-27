"""
report generator v2.0

Intelligent report generation Agent understands the analysis results and generates a formatted comprehensive report through LLM
Supports a variety of report styles and formats, which can be customized through prompt word templates
"""

import logging
from typing import Any, Dict, List, Optional
import json
from datetime import datetime

from ..analyst import AnalystAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class ReportGeneratorV2(AnalystAgent):
    """
    Report Generator v2.0 - Intelligent Report Generation Agent

    Function:
    - 🤖 Call LLM to understand analysis results
    - 📝 Generate formatted comprehensive analysis reports
    - 🎨 Supports multiple report styles (concise version, detailed version, investor version, etc.)
    - 🔧 Customize report formats with prompt word templates
    - 📊 Intelligent extraction of key information and data
    - 🔗 Integrate output from all analysts

    Workflow:
    1. Read all analyst reports (market_report, fundamentals_report etc.)
    2. LLM Understand report content and key messages
    3. Generate formatted reports based on prompt word templates
    4. Output structured comprehensive reports
    5. stored in reports field

    Example:
        from core.agents import create_agent
        from core.llm import UnifiedLLMClient

        llm = UnifiedLLMClient(provider="openai", model="gpt-4")
        agent = create_agent("report_generator_v2", llm=llm)

        result = agent.execute({
            "ticker": "000001",
            "analysis_date": "2026-02-19",
            "market_report": "...",
            "fundamentals_report": "...",
            "bull_report": "...",
            "bear_report": "...",
            "investment_plan": {...}
        })

        # result contains:
        # - reports: generated report dictionary
        # - report_summary: Report Summary
        # - report_style: Report style to use
    """

    metadata = AgentMetadata(
        id="report_generator_v2",
        name="report generator v2",
        description="Intelligent report generation Agent understands the analysis results and generates a formatted comprehensive report through LLM",
        category=AgentCategory.ANALYST,  # Changed to ANALYST category (because of calling LLM)
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # No tools required, just process existing data
        icon="📝",
        color="#9b59b6",
        tags=["report", "generate", "Summary", "Smart", "v2.0"],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code", required=False),
            AgentInput(name="analysis_date", type="string", description="Analysis date", required=False),
            AgentInput(name="report_style", type="string", description="Report style (concise/detailed/investor)", required=False),
        ],
        outputs=[
            AgentOutput(name="reports", type="dict", description="generated report dictionary"),
            AgentOutput(name="report_summary", type="string", description="Report Summary"),
        ],
    )

    # Analyst type
    analyst_type = "report_generator"

    # Output field name
    output_field = "reports"
    
    # Report fields that need to be extracted
    REPORT_FIELDS = [
        # macro analysis
        'index_report',
        'sector_report',
        # individual stock analysis
        'market_report',
        'sentiment_report',
        'news_report',
        'fundamentals_report',
        # Researcher Report
        'bull_report',
        'bear_report',
        # investment plan
        'investment_plan',
        'trader_investment_plan',
        'final_trade_decision',
        # risk assessment
        'risk_assessment',
    ]

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        llm: Optional[Any] = None,
        tool_ids: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Initialize report generator

        Args:
            config: Agent Configuration
            llm: LLM Example
            tool_ids: List of tool IDs (tools are not required for the report generator)
            **kwargs: Other parameters
        """
        super().__init__(config=config, llm=llm, tool_ids=tool_ids, **kwargs)

        logger.debug(f"ReportGeneratorV2 Initialization completed")
    
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
            agent_type="post_processors_v2",
            agent_name="report_generator_v2",
            variables={},
            context=None,
            fallback_prompt=None,
            state=state,
            prompt_type="system"
        )

        if prompt:
            return prompt

        # Default prompt word
        return """You are a professional report generator responsible for integrating the output of multiple analysts into structured comprehensive analysis reports.

## Core responsibilities
1. Summarize analysts reports and opinions
2. Extract key information and data
3. Generate formatted output based on report style
4. Ensure that the report content is objective, complete and organized

## Working principles
- Remain objective and neutral and truthfully present the views of all parties
- No subjective judgment or new analysis content added
- Output in the format required by the report style
- Highlight key data and important conclusions

## Output requirements
- Clear structure and distinct layers
- Data is accurate and cited clearly
- The language is concise and the key points are highlighted.
- Organize content using Markdown format

## report style
- **Simple version**: Only include core conclusions and key data
- **Detailed version**: Contains complete analysis process and detailed data
- **Investor Edition**: Professional reports for investors, highlighting summary of research observations and risk warnings
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
        report_style = state.get("report_style", "Detailed version")

        # Extract all available reports
        available_reports = self._extract_reports(state)

        # Try to get the prompt word from the template system
        prompt = self._get_prompt_from_template(
            agent_type="post_processors_v2",
            agent_name="report_generator_v2",
            variables={
                "ticker": ticker,
                "analysis_date": analysis_date,
                "report_style": report_style,
                "available_reports": ", ".join(available_reports.keys()),
            },
            context=None,
            fallback_prompt=None,
            state=state,
            prompt_type="user"
        )

        if prompt:
            return prompt

        # Default prompt word
        reports_summary = "\n".join([
            f"- **{field}**: {len(content)} character"
            for field, content in available_reports.items()
        ])

        return f"""please for stock {ticker} Generate comprehensive analysis report (analysis date:{analysis_date}) 

## report style
{report_style}

## Available analysis reports
{reports_summary}

## Mission requirements
1. Consolidate reports from all analysts
2. Extract key information and data
3. Generate structured comprehensive reports
4. Output using Markdown format

## Report structure (recommended)
1. **executive summary** - One sentence summary
2. **market analysis** - Market conditions and technical aspects
3. **fundamental analysis** - Financial data and valuations
4. **news and sentiment** - News and market sentiment
5. **Summary of research observations** - Comprehensive research observations and risk warnings
6. **key data** - Important indicators and data

Please start generating the report.
"""

    def _extract_reports(self, state: Dict[str, Any]) -> Dict[str, str]:
        """
        Pull all reports from status

        Args:
            state: Workflow status

        Returns:
            report dictionary {field_name: report_content}
        """
        reports = {}

        for field in self.REPORT_FIELDS:
            content = state.get(field)
            if content:
                # Extract text content
                text = self._extract_text(content)
                if text and len(text.strip()) > 5:
                    reports[field] = text.strip()
                    logger.debug(f"📄 [ReportGeneratorV2] Extract report: {field} ({len(text)} character)")

        return reports

    def _extract_text(self, value: Any) -> str:
        """
        Extract text content from various formats

        Args:
            value: May be a string, dictionary or other type

        Returns:
            Extracted text content
        """
        if isinstance(value, str):
            return value

        if isinstance(value, dict):
            # Try to extract text field from dictionary
            for key in ("content", "markdown", "text", "message", "report", "summary"):
                text = value.get(key)
                if isinstance(text, str) and text.strip():
                    return text

            # If it is structured data, convert it to JSON
            try:
                return json.dumps(value, ensure_ascii=False, indent=2)
            except:
                return str(value)

        return str(value) if value else ""

    def _parse_response(self, response: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse LLM response

        Args:
            response: LLM response text
            state: Workflow status

        Returns:
            parsed result dictionary
        """
        # Store reports generated by LLM into the reports field
        result = {
            **state,
            "reports": {
                "integrated reporting": response
            },
            "report_summary": self._extract_summary(response),
            "report_style": state.get("report_style", "Detailed version"),
        }

        logger.info(f"✅ [ReportGeneratorV2] Report generation completed, length: {len(response)} character")
        return result

    def _extract_summary(self, report: str) -> str:
        """
        Extract summary from report

        Args:
            report: full report

        Returns:
            summary text
        """
        # Try to extract the first paragraph or first 200 characters as summary
        lines = report.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and len(line) > 20:
                return line[:200] + "..." if len(line) > 200 else line

        # If no suitable summary is found, return the first 200 characters
        return report[:200] + "..." if len(report) > 200 else report

    # ========== Helper methods ==========

    def _generate_structured_reports(self, reports: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        """
        Generate structured reports (reserved for backward compatibility)

        Args:
            reports: Original report dictionary

        Returns:
            Structured reporting dictionary
        """
        structured = {}

        for field, content in reports.items():
            # Try to parse a report in JSON format
            try:
                if content.strip().startswith("{"):
                    data = json.loads(content)
                    structured[field] = {
                        "type": "json",
                        "data": data,
                        "markdown": self._json_to_markdown(data, field)
                    }
                else:
                    structured[field] = {
                        "type": "markdown",
                        "data": content,
                        "markdown": content
                    }
            except json.JSONDecodeError:
                structured[field] = {
                    "type": "markdown",
                    "data": content,
                    "markdown": content
                }

        return structured

    def _json_to_markdown(self, data: Dict[str, Any], field_name: str) -> str:
        """
        Convert JSON data to Markdown format

        Args:
            data: JSON data
            field_name: Field name

        Returns:
            Markdown formatted text
        """
        lines = []

        # Add title
        title_map = {
            "market_report": "market analysis",
            "fundamentals_report": "fundamental analysis",
            "bull_report": "positive evidence research observation",
            "bear_report": "Cautious Evidence Research and Observation",
            "investment_plan": "Comprehensive research conclusion",
            "risk_assessment": "risk review",
        }
        title = title_map.get(field_name, field_name.replace("_", " ").title())
        lines.append(f"## {title}\n")

        # Extract key fields
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"**{key}**: {value}")
            elif isinstance(value, list):
                lines.append(f"**{key}**:")
                for item in value:
                    lines.append(f"- {item}")
            elif isinstance(value, dict):
                lines.append(f"**{key}**:")
                for sub_key, sub_value in value.items():
                    lines.append(f"  - {sub_key}: {sub_value}")

        return "\n".join(lines)


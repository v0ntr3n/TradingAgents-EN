from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['data_preparer_v2', 'email_notifier', 'report_generator_v2', 'report_saver', 'system_notifier']:
    _sys.modules[f"core.agents.post_processors.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === data_preparer_v2.py ===
"""
data preparer v2.0

Intelligent data preparation agent understands requirements through LLM and calls tools to obtain data
Store prepared data in context for subsequent use by agents
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from .analyst import AnalystAgent
from .config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from .registry import register_agent

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

        logger.debug("DataPreparerV2 Initialization completed")

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


# === email_notifier.py ===
"""
Email notification Agent

Send email notification based on conditions
"""

import logging
from typing import Any, Dict, List, Optional

from .post_processor import PostProcessorAgent, PostProcessorType, OperationConfig, ConditionConfig
from .config import AgentMetadata, AgentCategory, LicenseTier
from .registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class EmailNotifierAgent(PostProcessorAgent):
    """
    Email notification Agent
    
    Function:
    - Send analysis completion notification email
    - Support template rendering
    - Support accessories
    - Optionally use LLM to generate email digests
    """
    
    metadata = AgentMetadata(
        id="email_notifier",
        name="Email Notifier",
        description="Send email notification based on conditions",
        category=AgentCategory.POST_PROCESSOR,
        version="1.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
    )
    
    processor_type = PostProcessorType.SEND_EMAIL
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        operations: Optional[List[OperationConfig]] = None,
        conditions: Optional[List[ConditionConfig]] = None,
        **kwargs
    ):
        """
        Initialize email notification Agent
        
        Args:
            config: Agent Configuration
            operations: Operation configuration list, format:
                [
                    {
                        "type": "send_email",
                        "template": "analysis_complete",
                        "to": "{user.email}",
                        "subject": "{ticker} Analysis completed",
                        "use_llm_summary": true,
                        "attachments": [...]
                    }
                ]
            conditions: Execution condition list
            **kwargs: Other parameters
        """
        super().__init__(config=config, operations=operations, conditions=conditions, **kwargs)
        
        # Initialize mail service (lazy loading)
        self._email_service = None
    
    def _execute_operation(self, operation: OperationConfig, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform mail sending operation
        
        Args:
            operation: Operational configuration
            state: Workflow status
            
        Returns:
            Operation execution result
        """
        operation_type = operation.get("type")
        
        if operation_type == "send_email":
            return self._send_email(operation, state)
        else:
            logger.warning(f"Unknown operation type: {operation_type}")
            return {
                "success": False,
                "operation_type": operation_type,
                "error": f"Unknown operation type: {operation_type}"
            }
    
    def _send_email(self, operation: OperationConfig, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send email
        
        Args:
            operation: Operational configuration
            state: Workflow status
            
        Returns:
            Operation result
        """
        try:
            # Get mail service
            email_service = self._get_email_service()
            
            # Prepare email data
            to_email = self._render_template(operation.get("to", ""), state)
            subject = self._render_template(operation.get("subject", ""), state)
            template_name = operation.get("template", "analysis_complete")
            use_llm_summary = operation.get("use_llm_summary", False)
            
            # Prepare template data
            template_data = self._prepare_template_data(state, use_llm_summary)
            
            # Prepare attachments
            attachments = self._prepare_attachments(operation.get("attachments", []), state)
            
            # Send email (actual email service needs to be integrated here)
            # Temporarily return simulation results
            logger.info(f"Prepare to send email to: {to_email}, Topic: {subject}")
            
            return {
                "success": True,
                "operation_type": "send_email",
                "to": to_email,
                "subject": subject,
                "template": template_name,
                "email_id": "mock_email_id"  # It should actually be returned by the mail service ID
            }
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}", exc_info=True)
            return {
                "success": False,
                "operation_type": "send_email",
                "error": str(e)
            }
    
    def _get_email_service(self):
        """Get mail service instance"""
        if self._email_service is None:
            # Delay import to avoid circular dependencies
            try:
                from app.services.email_service import EmailService
                self._email_service = EmailService()
            except ImportError:
                logger.warning("EmailService not available, using mock")
                self._email_service = None
        return self._email_service
    
    def _render_template(self, template: str, state: Dict[str, Any]) -> str:
        """
        Render template string

        Args:
            template: Template string, such as "{ticker} Analysis completed"
            state: Workflow status

        Returns:
            Rendered string
        """
        # Extract commonly used variables
        variables = {
            "ticker": state.get("ticker", ""),
            "date": state.get("analysis_date", ""),
            "recommendation": self._get_nested_value(state, "investment_plan.recommendation", ""),
            "confidence": self._get_nested_value(state, "investment_plan.confidence_score", ""),
        }

        # render template
        try:
            return template.format(**variables)
        except KeyError as e:
            logger.warning(f"Template variable missing: {e}")
            return template

    def _prepare_template_data(self, state: Dict[str, Any], use_llm_summary: bool = False) -> Dict[str, Any]:
        """
        Prepare email template data

        Args:
            state: Workflow status
            use_llm_summary: Whether to use LLM to generate summaries

        Returns:
            template data dictionary
        """
        template_data = {
            "ticker": state.get("ticker"),
            "analysis_date": state.get("analysis_date"),
            "recommendation": self._get_nested_value(state, "investment_plan.recommendation"),
            "confidence_score": self._get_nested_value(state, "investment_plan.confidence_score"),
            "reports": {
                "market": state.get("market_report"),
                "news": state.get("news_report"),
                "fundamentals": state.get("fundamentals_report"),
            }
        }

        # If LLM summary is required
        if use_llm_summary and self._llm:
            summary = self._generate_llm_summary(state)
            template_data["llm_summary"] = summary

        return template_data

    def _generate_llm_summary(self, state: Dict[str, Any]) -> str:
        """
        Use LLM to generate email digests

        Args:
            state: Workflow status

        Returns:
            summary text
        """
        try:
            from langchain_core.messages import HumanMessage

            # Build prompt words
            prompt = f"""Please use 3 sentences to summarize the core points of the following stock analysis report:

Stock code:{state.get('ticker')}
Research summary:{self._get_nested_value(state, 'investment_plan.recommendation')}
Confidence:{self._get_nested_value(state, 'investment_plan.confidence_score')}

Please summarize key information succinctly and clearly."""

            # call LLM
            response = self._llm.invoke([HumanMessage(content=prompt)])
            return response.content

        except Exception as e:
            logger.error(f"Failed to generate LLM summary: {e}")
            return "Summary generation failed"

    def _prepare_attachments(self, attachments_config: List[Dict], state: Dict[str, Any]) -> List[tuple]:
        """
        Prepare email attachments

        Args:
            attachments_config: Attachment configuration list, format:
                [
                    {
                        "type": "pdf",
                        "source": "state['pdf_report']",
                        "filename": "report.pdf"
                    }
                ]
            state: Workflow status

        Returns:
            Attachment list, format:[(filename, content, content_type), ...]
        """
        attachments = []

        for config in attachments_config:
            try:
                attachment_type = config.get("type")
                source = config.get("source")
                filename = config.get("filename", f"attachment.{attachment_type}")

                # Get attachment content from state
                content = self._get_nested_value(state, source)

                if content:
                    # OK content_type
                    content_type = self._get_content_type(attachment_type)
                    attachments.append((filename, content, content_type))

            except Exception as e:
                logger.error(f"Failed to prepare attachment: {e}")

        return attachments

    def _get_content_type(self, file_type: str) -> str:
        """Get the file content_type"""
        content_types = {
            "pdf": "application/pdf",
            "json": "application/json",
            "csv": "text/csv",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        return content_types.get(file_type, "application/octet-stream")


# === report_generator_v2.py ===
"""
report generator v2.0

Intelligent report generation Agent understands the analysis results and generates a formatted comprehensive report through LLM
Supports a variety of report styles and formats, which can be customized through prompt word templates
"""

import logging
from typing import Any, Dict, List, Optional
import json
from datetime import datetime

from .analyst import AnalystAgent
from .config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from .registry import register_agent

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

        logger.debug("ReportGeneratorV2 Initialization completed")
    
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
            except Exception:
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


# === report_saver.py ===
"""
report save Agent

Save analysis reports to multiple targets (MongoDB, file system, S3, etc.)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .post_processor import PostProcessorAgent, PostProcessorType, OperationConfig, ConditionConfig
from .config import AgentMetadata, AgentCategory, LicenseTier
from .registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class ReportSaverAgent(PostProcessorAgent):
    """
    report save Agent
    
    Supports saving to:
    - MongoDB
    - File system (JSON, YAML, etc.)
    - S3/OSS (future support)
    """
    
    metadata = AgentMetadata(
        id="report_saver",
        name="report saver",
        description="Save analysis reports to multiple targets (MongoDB, file system, etc.)",
        category=AgentCategory.POST_PROCESSOR,
        version="1.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # Post-processing Agent requires no tools
    )
    
    processor_type = PostProcessorType.SAVE_REPORT
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        operations: Optional[List[OperationConfig]] = None,
        conditions: Optional[List[ConditionConfig]] = None,
        **kwargs
    ):
        """
        Initialize report save Agent
        
        Args:
            config: Agent Configuration
            operations: Operation configuration list, format:
                [
                    {
                        "type": "save_to_mongodb",
                        "collection": "analysis_reports",
                        "fields": ["analysis_id", "stock_symbol", "reports"]
                    },
                    {
                        "type": "save_to_file",
                        "path": "data/reports/{ticker}_{date}.json",
                        "format": "json"
                    }
                ]
            conditions: Execution condition list
            **kwargs: Other parameters
        """
        super().__init__(config=config, operations=operations, conditions=conditions, **kwargs)
        
        # Initialize MongoDB connection (lazy loading)
        self._mongodb_client = None
    
    def _execute_operation(self, operation: OperationConfig, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform save operation
        
        Args:
            operation: Operational configuration
            state: Workflow status
            
        Returns:
            Operation execution result
        """
        operation_type = operation.get("type")
        
        if operation_type == "save_to_mongodb":
            return self._save_to_mongodb(operation, state)
        elif operation_type == "save_to_file":
            return self._save_to_file(operation, state)
        elif operation_type == "save_to_s3":
            return self._save_to_s3(operation, state)
        else:
            logger.warning(f"Unknown operation type: {operation_type}")
            return {
                "success": False,
                "operation_type": operation_type,
                "error": f"Unknown operation type: {operation_type}"
            }
    
    def _save_to_mongodb(self, operation: OperationConfig, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        save to MongoDB
        
        Args:
            operation: Operational configuration
            state: Workflow status
            
        Returns:
            Operation result
        """
        try:
            from tradingagents.config.mongodb_storage import MongoDBStorage
            
            collection_name = operation.get("collection", "analysis_reports")
            fields = operation.get("fields", [])
            
            # Build the document to be saved
            document = {}
            for field in fields:
                value = self._get_nested_value(state, field)
                if value is not None:
                    document[field] = value
            
            # Add timestamp
            document["created_at"] = datetime.now()
            document["updated_at"] = datetime.now()
            
            # save to MongoDB
            storage = MongoDBStorage()
            result = storage.save_document(collection_name, document)
            
            logger.info(f"Report saved to MongoDB: {collection_name}")
            
            return {
                "success": True,
                "operation_type": "save_to_mongodb",
                "collection": collection_name,
                "document_id": str(result.inserted_id) if result else None
            }
            
        except Exception as e:
            logger.error(f"Saving to MongoDB failed: {e}", exc_info=True)
            return {
                "success": False,
                "operation_type": "save_to_mongodb",
                "error": str(e)
            }
    
    def _save_to_file(self, operation: OperationConfig, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save to file system

        Args:
            operation: Operation configuration, format:
                {
                    "type": "save_to_file",
                    "path": "data/reports/{ticker}_{date}.json",
                    "format": "json"
                }
            state: Workflow status

        Returns:
            Operation result
        """
        try:
            path_template = operation.get("path")
            file_format = operation.get("format", "json")

            if not path_template:
                raise ValueError("Missing 'path' in operation config")

            # Replace variables in path
            file_path = self._render_path(path_template, state)

            # Make sure the directory exists
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)

            # Prepare data to save
            data = self._prepare_save_data(state)

            # Save according to format
            if file_format == "json":
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            elif file_format == "yaml":
                import yaml
                with open(file_path, 'w', encoding='utf-8') as f:
                    yaml.dump(data, f, allow_unicode=True)
            else:
                raise ValueError(f"Unsupported format: {file_format}")

            logger.info(f"Report saved to file: {file_path}")

            return {
                "success": True,
                "operation_type": "save_to_file",
                "file_path": file_path,
                "format": file_format
            }

        except Exception as e:
            logger.error(f"Saving to file failed: {e}", exc_info=True)
            return {
                "success": False,
                "operation_type": "save_to_file",
                "error": str(e)
            }

    def _render_path(self, path_template: str, state: Dict[str, Any]) -> str:
        """
        Render path template

        Args:
            path_template: Path template, such as "data/reports/{ticker}_{date}.json"
            state: Workflow status

        Returns:
            Rendered path
        """
        # Extract commonly used variables
        variables = {
            "ticker": state.get("ticker", "unknown"),
            "date": state.get("analysis_date", datetime.now().strftime("%Y%m%d")),
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        }

        # rendering path
        try:
            return path_template.format(**variables)
        except KeyError as e:
            logger.warning(f"Path template variable missing: {e}")
            return path_template

    def _prepare_save_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare data to save

        Args:
            state: Workflow status

        Returns:
            data dictionary to save
        """
        # The entire state is saved by default. Subclasses can override this method.
        return {
            "ticker": state.get("ticker"),
            "analysis_date": state.get("analysis_date"),
            "reports": {
                "market_report": state.get("market_report"),
                "news_report": state.get("news_report"),
                "fundamentals_report": state.get("fundamentals_report"),
                "bull_report": state.get("bull_report"),
                "bear_report": state.get("bear_report"),
                "investment_plan": state.get("investment_plan"),
                "trading_plan": state.get("trading_plan"),
            },
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "workflow_id": state.get("workflow_id"),
            }
        }
    
    def _save_to_s3(self, operation: OperationConfig, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        save to S3/OSS
        
        Args:
            operation: Operational configuration
            state: Workflow status
            
        Returns:
            Operation result
        """
        pass  # future realization


# === system_notifier.py ===
"""
System notification Agent

Send in-system notifications
"""

import logging
from typing import Any, Dict, List, Optional

from .post_processor import PostProcessorAgent, PostProcessorType, OperationConfig, ConditionConfig
from .config import AgentMetadata, AgentCategory, LicenseTier
from .registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class SystemNotifierAgent(PostProcessorAgent):
    """
    System notification Agent
    
    Function:
    - Send in-system notifications
    - Support WebSocket real-time push
    - Support notification persistence
    """
    
    metadata = AgentMetadata(
        id="system_notifier",
        name="System Notifier",
        description="Send in-system notifications",
        category=AgentCategory.POST_PROCESSOR,
        version="1.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
    )
    
    processor_type = PostProcessorType.SEND_NOTIFICATION
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        operations: Optional[List[OperationConfig]] = None,
        conditions: Optional[List[ConditionConfig]] = None,
        **kwargs
    ):
        """
        Initialize system notifications Agent
        
        Args:
            config: Agent Configuration
            operations: Operation configuration list, format:
                [
                    {
                        "type": "send_notification",
                        "notification_type": "analysis",
                        "title": "{ticker} Analysis completed",
                        "content": "{summary}",
                        "link": "/analysis/{analysis_id}",
                        "severity": "info"
                    }
                ]
            conditions: Execution condition list
            **kwargs: Other parameters
        """
        super().__init__(config=config, operations=operations, conditions=conditions, **kwargs)
        
        # Initialize notification service (lazy loading)
        self._notification_service = None
    
    def _execute_operation(self, operation: OperationConfig, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform notification sending operation
        
        Args:
            operation: Operational configuration
            state: Workflow status
            
        Returns:
            Operation execution result
        """
        operation_type = operation.get("type")
        
        if operation_type == "send_notification":
            return self._send_notification(operation, state)
        else:
            logger.warning(f"Unknown operation type: {operation_type}")
            return {
                "success": False,
                "operation_type": operation_type,
                "error": f"Unknown operation type: {operation_type}"
            }
    
    def _send_notification(self, operation: OperationConfig, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send system notification
        
        Args:
            operation: Operational configuration
            state: Workflow status
            
        Returns:
            Operation result
        """
        try:
            # Get notification service
            notification_service = self._get_notification_service()
            
            # Prepare notification data
            notification_type = operation.get("notification_type", "analysis")
            title = self._render_template(operation.get("title", ""), state)
            content = self._render_template(operation.get("content", ""), state)
            link = self._render_template(operation.get("link", ""), state)
            severity = operation.get("severity", "info")
            
            # Get user ID
            user_id = state.get("user_id")
            
            if not user_id:
                logger.warning("user_id not found, notification cannot be sent")
                return {
                    "success": False,
                    "operation_type": "send_notification",
                    "error": "Missing user_id"
                }
            
            # Send notifications (actual notification service needs to be integrated here)
            # Temporarily return simulation results
            logger.info(f"Prepare to send notifications to users: {user_id}, Title: {title}")
            
            return {
                "success": True,
                "operation_type": "send_notification",
                "user_id": user_id,
                "title": title,
                "notification_id": "mock_notification_id"  # It should actually be returned by the notification service ID
            }
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}", exc_info=True)
            return {
                "success": False,
                "operation_type": "send_notification",
                "error": str(e)
            }
    
    def _get_notification_service(self):
        """Get notification service instance"""
        if self._notification_service is None:
            # Delay import to avoid circular dependencies
            try:
                from app.services.notifications_service import NotificationsService
                self._notification_service = NotificationsService()
            except ImportError:
                logger.warning("NotificationsService not available, using mock")
                self._notification_service = None
        return self._notification_service
    
    def _render_template(self, template: str, state: Dict[str, Any]) -> str:
        """
        Render template string
        
        Args:
            template: template string
            state: Workflow status
            
        Returns:
            Rendered string
        """
        # Extract commonly used variables
        variables = {
            "ticker": state.get("ticker", ""),
            "date": state.get("analysis_date", ""),
            "analysis_id": state.get("analysis_id", ""),
            "recommendation": self._get_nested_value(state, "investment_plan.recommendation", ""),
            "summary": self._generate_summary(state),
        }
        
        # render template
        try:
            return template.format(**variables)
        except KeyError as e:
            logger.warning(f"Template variable missing: {e}")
            return template
    
    def _generate_summary(self, state: Dict[str, Any]) -> str:
        """
        Generate notification summary
        
        Args:
            state: Workflow status
            
        Returns:
            summary text
        """
        ticker = state.get("ticker", "")
        recommendation = self._get_nested_value(state, "investment_plan.recommendation", "")
        confidence = self._get_nested_value(state, "investment_plan.confidence_score", "")
        
        return f"{ticker} Analysis completed, research summary:{recommendation}, Confidence:{confidence}"


# === __init__.py ===
"""
Post-processing Agent module

Contains the implementation of all post-processing Agents
"""

__all__ = [
    "ReportSaverAgent",
    "EmailNotifierAgent",
    "SystemNotifierAgent",
    "ReportGeneratorV2",
    "DataPreparerV2",
]

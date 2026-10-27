"""
Email notification Agent

Send email notification based on conditions
"""

import logging
from typing import Any, Dict, List, Optional

from ..post_processor import PostProcessorAgent, PostProcessorType, OperationConfig, ConditionConfig
from ..config import AgentMetadata, AgentCategory, LicenseTier
from ..registry import register_agent

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


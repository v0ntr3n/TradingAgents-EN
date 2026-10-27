"""
System notification Agent

Send in-system notifications
"""

import logging
from typing import Any, Dict, List, Optional

from ..post_processor import PostProcessorAgent, PostProcessorType, OperationConfig, ConditionConfig
from ..config import AgentMetadata, AgentCategory, LicenseTier
from ..registry import register_agent

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


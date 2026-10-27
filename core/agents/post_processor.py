"""
Post-processing Agent base class

Used to perform post-processing operations after analysis is completed, such as saving reports, sending notifications, etc.
v2.0 New: Configurable post-processing Agent architecture
"""

import logging
from abc import abstractmethod
from typing import Any, Dict, List, Optional
from enum import Enum

from .base import BaseAgent
from .config import AgentMetadata, AgentCategory

logger = logging.getLogger(__name__)


class PostProcessorType(str, Enum):
    """Postprocessor type"""
    SAVE_REPORT = "save_report"           # save report
    SEND_EMAIL = "send_email"             # Send email
    SEND_NOTIFICATION = "send_notification"  # Send system notification
    TRIGGER_WEBHOOK = "trigger_webhook"   # trigger Webhook
    GENERATE_PDF = "generate_pdf"         # generate PDF
    GENERATE_CHART = "generate_chart"     # Generate chart
    UPDATE_CACHE = "update_cache"         # Update cache
    RECORD_METRICS = "record_metrics"     # Record metrics
    GENERATE_REPORT = "generate_report"   # Generate reports (v2.0)
    PREPARE_DATA = "prepare_data"         # Prepare data (v2.0)


class OperationConfig(dict):
    """
    Post-processing operation configuration
    
    Use dictionary form to support flexible configuration structure
    """
    pass


class ConditionConfig(dict):
    """
    Execution condition configuration
    
    Support field comparison, logical operations, etc.
    """
    pass


class PostProcessorAgent(BaseAgent):
    """
    Post-processing Agent base class
    
    Features:
    - Do not call LLM (or optionally call LLM to generate a summary)
    - Depends on the output of the pre-order Agent
    - Perform external operations (database, email, API, etc.)
    - Output format: execution status
    
    Workflow:
    1. Read analysis results
    2. Check execution conditions
    3. Perform post-processing operations
    4. Return to execution status
    """
    
    # Postprocessor type
    processor_type: PostProcessorType = None
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        operations: Optional[List[OperationConfig]] = None,
        conditions: Optional[List[ConditionConfig]] = None,
        **kwargs
    ):
        """
        Post-initialization processing Agent
        
        Args:
            config: Agent Configuration
            operations: Operation configuration list
            conditions: Execution condition list
            **kwargs: Other parameters passed to BaseAgent
        """
        super().__init__(config=config, **kwargs)
        
        self.operations = operations or []
        self.conditions = conditions or []
        
        logger.debug(f"PostProcessorAgent '{self.agent_id}' Initialization completed")
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform post-processing operations
        
        Args:
            state: Workflow status dictionary
            
        Returns:
            Updated status dictionary containing execution status
        """
        logger.info(f"Start post-processing Agent: {self.agent_id}")
        
        try:
            # 1. Check execution conditions
            if not self._check_conditions(state):
                logger.info(f"Post-processing Agent {self.agent_id} If the condition is not met, execution will be skipped.")
                return self._create_skip_result(state)
            
            # 2. Perform post-processing operations
            results = []
            for operation in self.operations:
                result = self._execute_operation(operation, state)
                results.append(result)
            
            # 3. Return to execution status
            return self._create_success_result(state, results)
            
        except Exception as e:
            logger.error(f"Post-processing Agent {self.agent_id} Execution failed: {e}", exc_info=True)
            return self._create_error_result(state, str(e))
    
    def _check_conditions(self, state: Dict[str, Any]) -> bool:
        """
        Check execution conditions
        
        Args:
            state: Workflow status
            
        Returns:
            Are all conditions met?
        """
        if not self.conditions:
            return True
        
        for condition in self.conditions:
            if not self._evaluate_condition(condition, state):
                return False
        
        return True
    
    def _evaluate_condition(self, condition: ConditionConfig, state: Dict[str, Any]) -> bool:
        """
        Evaluate a single condition

        Args:
            condition: Conditional configuration, format:
                {
                    "field": "recommendation",
                    "operator": "in",
                    "value": ["optimistic", "Prudence"]
                }
            state: Workflow status

        Returns:
            Are the conditions met?
        """
        field = condition.get("field")
        operator = condition.get("operator")
        expected_value = condition.get("value")

        if not field or not operator:
            logger.warning(f"Incomplete condition configuration: {condition}")
            return False

        # Get the actual value (nested paths are supported)
        actual_value = self._get_nested_value(state, field)

        # perform comparison
        try:
            if operator == "equals":
                return actual_value == expected_value
            elif operator == "not_equals":
                return actual_value != expected_value
            elif operator == "in":
                return actual_value in expected_value
            elif operator == "not_in":
                return actual_value not in expected_value
            elif operator == "greater_than":
                return float(actual_value) > float(expected_value)
            elif operator == "less_than":
                return float(actual_value) < float(expected_value)
            elif operator == "greater_or_equal":
                return float(actual_value) >= float(expected_value)
            elif operator == "less_or_equal":
                return float(actual_value) <= float(expected_value)
            elif operator == "contains":
                return expected_value in str(actual_value)
            elif operator == "not_contains":
                return expected_value not in str(actual_value)
            elif operator == "is_true":
                return bool(actual_value)
            elif operator == "is_false":
                return not bool(actual_value)
            elif operator == "exists":
                return actual_value is not None
            elif operator == "not_exists":
                return actual_value is None
            else:
                logger.warning(f"unknown operator: {operator}")
                return False
        except Exception as e:
            logger.error(f"Condition evaluation failed: {e}")
            return False
    
    @abstractmethod
    def _execute_operation(self, operation: OperationConfig, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform a single operation (subclass implementation)

        Args:
            operation: Operational configuration
            state: Workflow status

        Returns:
            Operation execution result
        """
        pass

    def _create_success_result(self, state: Dict[str, Any], results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create successful results

        Args:
            state: original state
            results: Operation result list

        Returns:
            Updated status
        """
        output_key = f"{self.agent_id}_status"
        state[output_key] = {
            "success": True,
            "agent_id": self.agent_id,
            "processor_type": self.processor_type.value if self.processor_type else None,
            "operations_count": len(results),
            "results": results,
            "error": None
        }
        return state

    def _create_skip_result(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create skip results

        Args:
            state: original state

        Returns:
            Updated status
        """
        output_key = f"{self.agent_id}_status"
        state[output_key] = {
            "success": True,
            "agent_id": self.agent_id,
            "processor_type": self.processor_type.value if self.processor_type else None,
            "skipped": True,
            "reason": "Conditions not met",
            "error": None
        }
        return state

    def _create_error_result(self, state: Dict[str, Any], error: str) -> Dict[str, Any]:
        """
        Create error results

        Args:
            state: original state
            error: error message

        Returns:
            Updated status
        """
        output_key = f"{self.agent_id}_status"
        state[output_key] = {
            "success": False,
            "agent_id": self.agent_id,
            "processor_type": self.processor_type.value if self.processor_type else None,
            "error": error
        }
        return state

    @property
    def agent_id(self) -> str:
        """get Agent ID"""
        if self.metadata:
            return self.metadata.id
        return self.__class__.__name__.lower()

    def _get_nested_value(self, data: Dict[str, Any], path: str, default: Any = None) -> Any:
        """
        Get the value of a nested dictionary

        Args:
            data: data dictionary
            path: path, such as "user.email_settings.enabled"
            default: Default value

        Returns:
            value or default
        """
        keys = path.split('.')
        value = data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value


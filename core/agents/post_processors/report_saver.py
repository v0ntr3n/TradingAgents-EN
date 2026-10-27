"""
report save Agent

Save analysis reports to multiple targets (MongoDB, file system, S3, etc.)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..post_processor import PostProcessorAgent, PostProcessorType, OperationConfig, ConditionConfig
from ..config import AgentMetadata, AgentCategory, LicenseTier
from ..registry import register_agent

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


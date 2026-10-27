"""
Workflow configuration manager

Manage workflow definition, configuration, and status
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class WorkflowConfigManager:
    """
    Workflow Configuration Manager (v2.0 new version)
    
    Management:
    1. Workflow enabled/disabled status
    2. Workflow execution mode (sequential/parallel/conditional)
    3. Workflow node and edge definitions
    4. Parallel group configuration for workflows
    
    Priority: Database Configuration > Code default configuration
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._db = None
        self._cache = {}  # workflow_id -> definition
        self._cache_ttl = 300  # 5 minutes cache
        self._cache_time = {}
        self._initialized = True
    
    def set_database(self, db):
        """Set up database connection"""
        self._db = db
        self._clear_cache()
    
    def _clear_cache(self):
        """Clear cache"""
        self._cache = {}
        self._cache_time = {}
    
    def _is_cache_valid(self, workflow_id: str) -> bool:
        """Check if cache is valid"""
        if workflow_id not in self._cache_time:
            return False
        elapsed = (datetime.utcnow() - self._cache_time[workflow_id]).total_seconds()
        return elapsed < self._cache_ttl
    
    def get_workflow_definition(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get workflow definition
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            Workflow definition dictionary, including:
            - workflow_id: Workflow ID
            - name: display name
            - description: Description
            - enabled: Whether to enable
            - execution_mode: execution mode
            - nodes: node list
            - edges: edge list
            - parallel_groups: parallel group
            - config: Other configurations
        """
        # Check cache
        if workflow_id in self._cache and self._is_cache_valid(workflow_id):
            return self._cache[workflow_id]
        
        definition = None
        
        # Load from database
        if self._db is not None:
            try:
                definition = self._db.workflow_definitions.find_one({"workflow_id": workflow_id})
                if definition:
                    # Remove MongoDB's _id field
                    definition.pop("_id", None)
                    # 🔥 Convert datetime object to string (Pydantic validation requires string type)
                    if "created_at" in definition and isinstance(definition["created_at"], datetime):
                        definition["created_at"] = definition["created_at"].isoformat()
                    if "updated_at" in definition and isinstance(definition["updated_at"], datetime):
                        definition["updated_at"] = definition["updated_at"].isoformat()
            except Exception as e:
                logger.warning(f"Failed to load workflow definition from database: {e}")
        
        # Update cache
        if definition:
            self._cache[workflow_id] = definition
            self._cache_time[workflow_id] = datetime.utcnow()
        
        return definition
    
    def save_workflow_definition(self, definition: Dict[str, Any]) -> bool:
        """
        Save workflow definition to database
        
        Args:
            definition: Workflow definition dictionary
            
        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("Database not connected")
            return False
        
        workflow_id = definition.get("workflow_id")
        if not workflow_id:
            logger.error("definition missing workflow_id")
            return False
        
        try:
            definition["updated_at"] = datetime.utcnow().isoformat()
            self._db.workflow_definitions.update_one(
                {"workflow_id": workflow_id},
                {
                    "$set": definition,
                    "$setOnInsert": {"created_at": datetime.utcnow().isoformat()}
                },
                upsert=True
            )
            
            # clear cache
            if workflow_id in self._cache:
                del self._cache[workflow_id]
            if workflow_id in self._cache_time:
                del self._cache_time[workflow_id]
            
            logger.info(f"✅ Workflow definition saved: {workflow_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save workflow definition: {e}")
            return False
    
    def is_workflow_enabled(self, workflow_id: str) -> bool:
        """Check if workflow is enabled"""
        definition = self.get_workflow_definition(workflow_id)
        return definition.get("enabled", False) if definition else False

    def enable_workflow(self, workflow_id: str) -> bool:
        """Enable workflow"""
        return self._set_workflow_enabled(workflow_id, True)

    def disable_workflow(self, workflow_id: str) -> bool:
        """Disable workflow"""
        return self._set_workflow_enabled(workflow_id, False)

    def _set_workflow_enabled(self, workflow_id: str, enabled: bool) -> bool:
        """Set workflow enablement status"""
        if self._db is None:
            logger.error("Database not connected")
            return False

        try:
            self._db.workflow_definitions.update_one(
                {"workflow_id": workflow_id},
                {
                    "$set": {
                        "enabled": enabled,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )

            # clear cache
            if workflow_id in self._cache:
                del self._cache[workflow_id]

            logger.info(f"✅ Workflow {workflow_id} Already{'enable' if enabled else 'Disable'}")
            return True
        except Exception as e:
            logger.error(f"Setting workflow status failed: {e}")
            return False

    def get_all_workflow_definitions(self, category: Optional[str] = None, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get all workflow definitions

        Args:
            category: Optional, filter by category
            enabled_only: Whether to return only enabled workflows

        Returns:
            Workflow definition list
        """
        result = []

        if self._db is not None:
            try:
                query = {}
                if category:
                    query["category"] = category
                if enabled_only:
                    query["enabled"] = True

                result = list(self._db.workflow_definitions.find(query))
                # Remove _id field
                for definition in result:
                    definition.pop("_id", None)
            except Exception as e:
                logger.warning(f"Failed to get list of workflow definitions: {e}")

        return result

    def update_workflow_execution_mode(self, workflow_id: str, execution_mode: str) -> bool:
        """
        Update the execution mode of a workflow

        Args:
            workflow_id: Workflow ID
            execution_mode: Execution mode (sequential/parallel/conditional)

        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("Database not connected")
            return False

        if execution_mode not in ["sequential", "parallel", "conditional"]:
            logger.error(f"Invalid execution mode: {execution_mode}")
            return False

        try:
            self._db.workflow_definitions.update_one(
                {"workflow_id": workflow_id},
                {
                    "$set": {
                        "execution_mode": execution_mode,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )

            # clear cache
            if workflow_id in self._cache:
                del self._cache[workflow_id]

            logger.info(f"✅ Workflow execution mode updated: {workflow_id} -> {execution_mode}")
            return True
        except Exception as e:
            logger.error(f"Failed to update workflow execution mode: {e}")
            return False

    def update_workflow_nodes(self, workflow_id: str, nodes: List[Dict[str, Any]]) -> bool:
        """
        Update a workflow s node definition

        Args:
            workflow_id: Workflow ID
            nodes: node list

        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("Database not connected")
            return False

        try:
            self._db.workflow_definitions.update_one(
                {"workflow_id": workflow_id},
                {
                    "$set": {
                        "nodes": nodes,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )

            # clear cache
            if workflow_id in self._cache:
                del self._cache[workflow_id]

            logger.info(f"✅ Workflow node updated: {workflow_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update workflow node: {e}")
            return False

    def update_workflow_edges(self, workflow_id: str, edges: List[Dict[str, Any]]) -> bool:
        """
        Update workflow edge definitions

        Args:
            workflow_id: Workflow ID
            edges: edge list

        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("Database not connected")
            return False

        try:
            self._db.workflow_definitions.update_one(
                {"workflow_id": workflow_id},
                {
                    "$set": {
                        "edges": edges,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )

            # clear cache
            if workflow_id in self._cache:
                del self._cache[workflow_id]

            logger.info(f"✅ Workflow edge updated: {workflow_id}")
            return True
        except Exception as e:
            logger.error(f"Update workflow failed: {e}")
            return False

    def delete_workflow_definition(self, workflow_id: str) -> bool:
        """
        Delete workflow definition

        Args:
            workflow_id: Workflow ID

        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("Database not connected")
            return False

        try:
            result = self._db.workflow_definitions.delete_one({"workflow_id": workflow_id})

            # clear cache
            if workflow_id in self._cache:
                del self._cache[workflow_id]
            if workflow_id in self._cache_time:
                del self._cache_time[workflow_id]

            if result.deleted_count > 0:
                logger.info(f"✅ Workflow definition deleted: {workflow_id}")
                return True
            else:
                logger.warning(f"⚠️ Workflow definition does not exist: {workflow_id}")
                return False
        except Exception as e:
            logger.error(f"Deletion of workflow definition failed: {e}")
            return False


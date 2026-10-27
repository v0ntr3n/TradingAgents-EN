"""
Default workflow provider

Manage the loading of system default workflows and active workflows
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from .models import WorkflowDefinition
from .templates import v2_stock_analysis_workflow as v2_stock_analysis_workflow_module
from .templates.trade_review_workflow_v2 import TRADE_REVIEW_WORKFLOW_V2
from .templates.position_analysis_workflow_v2 import POSITION_ANALYSIS_WORKFLOW_V2
from .templates.v2_stock_analysis_workflow import V2_STOCK_ANALYSIS_WORKFLOW
from .templates.v2_etf_analysis_workflow import V2_ETF_ANALYSIS_WORKFLOW

logger = logging.getLogger(__name__)

# System default workflow ID
SYSTEM_DEFAULT_WORKFLOW_ID = "v2_stock_analysis"
SYSTEM_TRADE_REVIEW_WORKFLOW_V2_ID = "trade_review_v2"
SYSTEM_POSITION_ANALYSIS_WORKFLOW_V2_ID = "position_analysis_v2"
SYSTEM_V2_STOCK_ANALYSIS_WORKFLOW_ID = "v2_stock_analysis"
SYSTEM_V2_ETF_ANALYSIS_WORKFLOW_ID = "v2_etf_analysis"

WORKFLOW_TYPE_DEFAULTS = {
    "stock_analysis": SYSTEM_V2_STOCK_ANALYSIS_WORKFLOW_ID,
    "etf_analysis": SYSTEM_V2_ETF_ANALYSIS_WORKFLOW_ID,
    "position_analysis": SYSTEM_POSITION_ANALYSIS_WORKFLOW_V2_ID,
    "trade_review": SYSTEM_TRADE_REVIEW_WORKFLOW_V2_ID,
}

WORKFLOW_ID_TO_TYPE = {
    SYSTEM_V2_STOCK_ANALYSIS_WORKFLOW_ID: "stock_analysis",
    SYSTEM_V2_ETF_ANALYSIS_WORKFLOW_ID: "etf_analysis",
    SYSTEM_POSITION_ANALYSIS_WORKFLOW_V2_ID: "position_analysis",
    SYSTEM_TRADE_REVIEW_WORKFLOW_V2_ID: "trade_review",
}

class DefaultWorkflowProvider:
    """
    Default workflow provider

    Responsibilities:
    1. Provide system-preset default workflow
    2. Make sure the default workflow exists in the database
    3. Get the current active workflow
    """

    # System preset workflow (only v2 version reserved)
    SYSTEM_WORKFLOWS = {
        SYSTEM_TRADE_REVIEW_WORKFLOW_V2_ID: TRADE_REVIEW_WORKFLOW_V2,
        SYSTEM_POSITION_ANALYSIS_WORKFLOW_V2_ID: POSITION_ANALYSIS_WORKFLOW_V2,
        SYSTEM_V2_STOCK_ANALYSIS_WORKFLOW_ID: V2_STOCK_ANALYSIS_WORKFLOW,
        SYSTEM_V2_ETF_ANALYSIS_WORKFLOW_ID: V2_ETF_ANALYSIS_WORKFLOW,
    }

    def __init__(self):
        self._db = None
        self._active_workflow_ids: Dict[str, str] = {}

    def _get_db(self):
        """Get database connection (lazy loading)"""
        if self._db is None:
            try:
                import os
                from pymongo import MongoClient

                # Prefer using connection strings in environment variables
                # ⚠️ Security warning: No more using hardcoded credentials as default
                mongo_uri = os.getenv("MONGODB_CONNECTION_STRING")
                
                if not mongo_uri:
                    raise ValueError(
                        "The environment variable MONGODB_CONNECTION_STRING must be set."
                        "Example: mongodb://user:password@host:port/database?authSource=admin"
                    )
                
                db_name = os.getenv("MONGODB_DATABASE_NAME", "tradingagents")

                client = MongoClient(mongo_uri)
                self._db = client[db_name]
                logger.info(f"✅ DefaultWorkflowProvider Database connection successful: {db_name}")
            except Exception as e:
                logger.warning(f"Unable to connect to database: {e}")
                self._db = None
        return self._db

    def get_default_workflow(self) -> WorkflowDefinition:
        """Get the system default workflow (stock analysis uses v2 process by default)"""
        return V2_STOCK_ANALYSIS_WORKFLOW

    def get_simple_workflow(self) -> WorkflowDefinition:
        """Get simple workflow (removed, return to default v2 workflow)"""
        return V2_STOCK_ANALYSIS_WORKFLOW

    def get_system_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Get system preset workflow"""
        return self.SYSTEM_WORKFLOWS.get(workflow_id)

    def infer_workflow_type(self, workflow: Dict[str, Any] | WorkflowDefinition | None = None, workflow_id: str = "") -> str:
        """Infer the analysis type to which the workflow belongs."""
        if workflow is None:
            return WORKFLOW_ID_TO_TYPE.get(workflow_id, "stock_analysis")

        if isinstance(workflow, WorkflowDefinition):
            config = workflow.config or {}
            tags = workflow.tags or []
            wf_id = workflow.id
            name = workflow.name or ""
        else:
            config = workflow.get("config") or {}
            tags = workflow.get("tags") or []
            wf_id = workflow.get("id") or workflow_id
            name = workflow.get("name") or ""

        explicit_type = config.get("workflow_type") or config.get("task_type")
        if explicit_type:
            return str(explicit_type)

        mapped_type = WORKFLOW_ID_TO_TYPE.get(str(wf_id))
        if mapped_type:
            return mapped_type

        text = " ".join([str(wf_id), name, " ".join(map(str, tags))]).lower()
        if "general" in text or "Universal" in text:
            return "general"
        if "etf" in text or "fund" in text:
            return "etf_analysis"
        if "position" in text or "Position" in text:
            return "position_analysis"
        if "trade_review" in text or "Review" in text:
            return "trade_review"
        return "stock_analysis"

    def get_default_workflow_id_for_type(self, workflow_type: str = "stock_analysis") -> str:
        """Gets the system default workflow ID for the specified analysis type."""
        return WORKFLOW_TYPE_DEFAULTS.get(workflow_type, SYSTEM_DEFAULT_WORKFLOW_ID)

    def get_default_workflow_for_type(self, workflow_type: str = "stock_analysis") -> WorkflowDefinition:
        """Get the system default workflow for the specified analysis type."""
        workflow_id = self.get_default_workflow_id_for_type(workflow_type)
        return self.SYSTEM_WORKFLOWS.get(workflow_id, V2_STOCK_ANALYSIS_WORKFLOW)

    def _build_system_workflow_doc(
        self,
        workflow: WorkflowDefinition,
        created_at: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Construct system workflow documents for persistence."""
        timestamp = datetime.utcnow().isoformat()
        doc = workflow.to_dict()
        doc["created_at"] = self._stringify_timestamp(created_at) or timestamp
        doc["updated_at"] = timestamp
        doc["created_by"] = "system"
        doc["is_system"] = True
        doc["workflow_type"] = self.infer_workflow_type(workflow)
        doc.setdefault("is_default", False)
        return doc

    def _normalize_workflow_doc_for_compare(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Removed runtime fields to facilitate comparison of code definitions and database copies for consistency."""
        normalized = dict(doc)
        for key in ("_id", "created_at", "updated_at"):
            normalized.pop(key, None)
        return normalized

    def _stringify_timestamp(self, value: Optional[Any]) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _log_workflow_diagnostics(
        self,
        workflow: WorkflowDefinition,
        source: str,
        source_path: Optional[str] = None,
    ) -> None:
        """Record the workflow source and key edges to facilitate troubleshooting whether the expected version is loaded."""
        nodes = [node.id for node in workflow.nodes]
        edges = [f"{edge.id}:{edge.source}->{edge.target}" for edge in workflow.edges]
        logger.info(f"📋 [Workflow loading] Source: {source}")
        if source_path:
            logger.info(f"📋 [Workflow loading] source file: {source_path}")
        logger.info(f"📋 [Workflow loading] node list: {nodes}")
        logger.info(f"📋 [Workflow loading] edge list: {edges}")

        critical_edge_ids = ("e_to_risk_debate", "e_risk_judge", "e_trader", "e_end")
        critical_edges = {
            edge.id: (edge.source, edge.target)
            for edge in workflow.edges
            if edge.id in critical_edge_ids
        }
        if critical_edges:
            logger.info(f"📋 [Workflow loading] critical edge: {critical_edges}")

    def is_system_workflow(self, workflow_id: str) -> bool:
        """Check whether workflow is preset for the system"""
        return workflow_id in self.SYSTEM_WORKFLOWS

    def get_active_workflow_id(self, workflow_type: str = "stock_analysis") -> str:
        """
        Get the current active workflow ID

        Priority:
        1. workflow_type in database workflows matches and is_default=True workflow
        2. The default workflow of the corresponding type in the database system_configs (compatible with old configurations)
        3. config/settings.json The default workflow of the corresponding type in (local cover)
        4. System v2 default workflow for specified type
        """
        cache_key = workflow_type or "stock_analysis"
        if cache_key in self._active_workflow_ids:
            return self._active_workflow_ids[cache_key]

        db = self._get_db()
        if db is not None:
            try:
                workflow = db.workflows.find_one(
                    {"workflow_type": cache_key, "is_default": True},
                    sort=[("updated_at", -1)]
                )
                if not workflow:
                    workflow = db.workflows.find_one(
                        {"config.workflow_type": cache_key, "is_default": True},
                        sort=[("updated_at", -1)]
                    )
                if workflow and workflow.get("id"):
                    self._active_workflow_ids[cache_key] = workflow["id"]
                    logger.info(
                        f"Get the default analysis flow from database workflows: type={cache_key}, workflow_id={workflow['id']} ({workflow.get('name', '')})"
                    )
                    return workflow["id"]
            except Exception as e:
                logger.warning(f"Failed to get default analysis flow from database workflows: type={cache_key}, error={e}")

        # Compatible with old configurations: Get the corresponding type of activity workflow from system_configs
        if db is not None:
            try:
                config = db.system_configs.find_one(
                    {"is_active": True},
                    sort=[("version", -1)]
                )
                if config:
                    typed_defaults = config.get("default_workflows") or {}
                    typed_config = typed_defaults.get(cache_key) or {}
                    workflow_id = typed_config.get("workflow_id")
                    workflow_name = typed_config.get("workflow_name", "")

                    if not workflow_id and cache_key == "stock_analysis":
                        workflow_id = config.get("active_workflow_id") or config.get("default_workflow_id")
                        workflow_name = config.get("active_workflow_name") or config.get("default_workflow_name") or ""

                    if workflow_id:
                        self._active_workflow_ids[cache_key] = workflow_id
                        logger.info(f"Get active workflow from database: type={cache_key}, workflow_id={workflow_id} ({workflow_name})")
                        return workflow_id
            except Exception as e:
                logger.warning(f"Failed to get active workflow from database: type={cache_key}, error={e}")

        # Then read the local configuration from config/settings.json
        try:
            import json
            from pathlib import Path

            config_path = Path("config/settings.json")
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    typed_defaults = config.get("default_workflows") or {}
                    typed_config = typed_defaults.get(cache_key) or {}
                    workflow_id = typed_config.get("workflow_id")
                    workflow_name = typed_config.get("workflow_name", "")

                    if not workflow_id and cache_key == "stock_analysis":
                        workflow_id = config.get("default_workflow_id")
                        workflow_name = config.get("default_workflow_name", "")

                    if workflow_id:
                        self._active_workflow_ids[cache_key] = workflow_id
                        logger.info(f"Get active workflow from configuration file: type={cache_key}, workflow_id={workflow_id} ({workflow_name})")
                        return workflow_id
        except Exception as e:
            logger.warning(f"Failed to get active workflow from configuration file: type={cache_key}, error={e}")

        default_workflow_id = self.get_default_workflow_id_for_type(cache_key)
        self._active_workflow_ids[cache_key] = default_workflow_id
        logger.info(f"Use system default workflow: type={cache_key}, workflow_id={default_workflow_id}")
        return default_workflow_id

    def set_active_workflow_id(self, workflow_id: str, workflow_name: str = "", workflow_type: str = "stock_analysis") -> bool:
        """Set up activity workflow ID"""
        success = True

        # 🆕 Also update the configuration file (with the frontend"Set as default"functionality remains the same)
        try:
            import json
            from pathlib import Path

            config_path = Path("config/settings.json")
            config = {}
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            config.setdefault("default_workflows", {})
            config["default_workflows"][workflow_type] = {
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
            }
            if workflow_type == "stock_analysis":
                config["default_workflow_id"] = workflow_id
                if workflow_name:
                    config["default_workflow_name"] = workflow_name

            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            logger.info(f"Profile updated: {workflow_id} ({workflow_name})")
        except Exception as e:
            logger.warning(f"Failed to update configuration file: {e}")
            success = False

        # Update database default analysis flow state
        db = self._get_db()
        if db is not None:
            try:
                db.workflows.update_many(
                    {"workflow_type": workflow_type, "is_default": True},
                    {"$set": {"is_default": False, "updated_at": datetime.utcnow()}},
                )
                db.workflows.update_many(
                    {"config.workflow_type": workflow_type, "is_default": True},
                    {"$set": {"is_default": False, "updated_at": datetime.utcnow()}},
                )
                db.workflows.update_one(
                    {"id": workflow_id},
                    {"$set": {"is_default": True, "workflow_type": workflow_type, "updated_at": datetime.utcnow()}},
                )
                db.system_configs.update_one(
                    {"is_active": True},
                    {
                        "$set": {
                            "active_workflow_id": workflow_id,
                            "active_workflow_name": workflow_name,
                            "default_workflow_id": workflow_id,
                            "default_workflow_name": workflow_name,
                            f"default_workflows.{workflow_type}": {
                                "workflow_id": workflow_id,
                                "workflow_name": workflow_name,
                            },
                            "updated_at": datetime.utcnow()
                        },
                        "$setOnInsert": {"created_at": datetime.utcnow()},
                    },
                    upsert=True
                )
                logger.info(f"Database default analysis flow updated: {workflow_id}")
            except Exception as e:
                logger.warning(f"Update database failed: {e}")
                success = False
        else:
            logger.warning("Unable to update database: Connection failed")

        if success:
            self._active_workflow_ids[workflow_type] = workflow_id
            logger.info(f"Activity workflow set up: type={workflow_type}, workflow_id={workflow_id}")

        return success

    def load_workflow(self, workflow_id: Optional[str] = None) -> WorkflowDefinition:
        """
        Load workflow

        Args:
            workflow_id: Workflow ID, None to load the active workflow

        Returns:
            WorkflowDefinition
        """
        import json
        from pathlib import Path

        # If not specified, uses the stock analysis activity workflow
        if workflow_id is None:
            workflow_id = self.get_active_workflow_id("stock_analysis")

        logger.info(f"📋 [Workflow loading] Start loading workflow: {workflow_id}")

        # Check whether workflow is preset for the system
        if self.is_system_workflow(workflow_id):
            workflow = self.SYSTEM_WORKFLOWS[workflow_id]
            logger.info(f"✅ [Workflow loading] Use system preset workflows: {workflow_id} - {workflow.name}")
            source_path = None
            if workflow_id == SYSTEM_V2_STOCK_ANALYSIS_WORKFLOW_ID:
                source_path = getattr(v2_stock_analysis_workflow_module, "__file__", None)
            self._log_workflow_diagnostics(workflow, "system_preset", source_path)
            return workflow

        # 1. Load from database first
        db = self._get_db()
        if db is not None:
            try:
                doc = db.workflows.find_one({"id": workflow_id})
                if doc:
                    # Remove MongoDB's _id field
                    doc.pop("_id", None)
                    # 🔥 Convert datetime object to string (Pydantic validation requires string type)
                    if "created_at" in doc and isinstance(doc["created_at"], datetime):
                        doc["created_at"] = doc["created_at"].isoformat()
                    if "updated_at" in doc and isinstance(doc["updated_at"], datetime):
                        doc["updated_at"] = doc["updated_at"].isoformat()
                    workflow = WorkflowDefinition.from_dict(doc)

                    # Statistical Analyst Node
                    analyst_nodes = [n for n in workflow.nodes if n.type == "analyst"]
                    analyst_ids = [n.agent_id for n in analyst_nodes]

                    logger.info(f"✅ [Workflow loading] Load from database: {workflow_id}")
                    logger.info(f"   Name: {workflow.name}")
                    logger.info(f"   version: {doc.get('version', 1)}")
                    logger.info(f"   Number of analysts: {len(analyst_nodes)}")
                    logger.info(f"   Analyst list: {analyst_ids}")
                    self._log_workflow_diagnostics(workflow, "database")

                    return workflow
                else:
                    logger.debug(f"[Workflow loading] Workflow not found in database: {workflow_id}")
            except Exception as e:
                logger.error(f"❌ [Workflow loading] Loading from database failed: {e}")

        # 2. Try loading from file system
        workflows_dir = Path("data/workflows")
        file_path = workflows_dir / f"{workflow_id}.json"

        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                workflow = WorkflowDefinition.from_dict(data)

                # Statistical Analyst Node
                analyst_nodes = [n for n in workflow.nodes if n.type == "analyst"]
                analyst_ids = [n.agent_id for n in analyst_nodes]

                logger.info(f"✅ [Workflow loading] Load from file system: {workflow_id}")
                logger.info(f"   Name: {workflow.name}")
                logger.info(f"   Number of analysts: {len(analyst_nodes)}")
                logger.info(f"   Analyst list: {analyst_ids}")
                self._log_workflow_diagnostics(workflow, f"filesystem:{file_path}")

                return workflow
            except Exception as e:
                logger.error(f"❌ [Workflow loading] Loading from file system failed: {e}")

        # 3. Fallback to the default workflow for this process type
        fallback_type = self.infer_workflow_type(workflow_id=workflow_id)
        logger.warning(f"⚠️ [Workflow loading] Workflow {workflow_id} Does not exist, use the system default workflow: type={fallback_type}")
        default_workflow = self.get_default_workflow_for_type(fallback_type)
        analyst_nodes = [n for n in default_workflow.nodes if n.type == "analyst"]
        analyst_ids = [n.agent_id for n in analyst_nodes]
        logger.info(f"   Default workflow: {default_workflow.name}")
        logger.info(f"   Number of analysts: {len(analyst_nodes)}")
        logger.info(f"   Analyst list: {analyst_ids}")
        self._log_workflow_diagnostics(default_workflow, "fallback_default")

        return default_workflow

    def ensure_system_workflows_exist(self) -> Dict[str, bool]:
        """
        Ensure that system preset workflows are consistent with code definitions in the database

        Returns:
            Dict[workflow_id, changed]: Whether to create or update
        """
        results = {}
        db = self._get_db()

        if db is None:
            logger.warning("Unable to ensure system workflow exists: Database connection failed")
            return {wf_id: False for wf_id in self.SYSTEM_WORKFLOWS}

        for wf_id, workflow in self.SYSTEM_WORKFLOWS.items():
            try:
                existing = db.workflows.find_one({"id": wf_id})
                desired_doc = self._build_system_workflow_doc(
                    workflow,
                    existing.get("created_at") if existing else None,
                )

                if existing and self._normalize_workflow_doc_for_compare(existing) == self._normalize_workflow_doc_for_compare(desired_doc):
                    results[wf_id] = False
                    logger.debug(f"The system workflow is already the latest version: {wf_id}")
                    continue

                update_doc = dict(desired_doc)
                created_at = update_doc.pop("created_at")
                db.workflows.update_one(
                    {"id": wf_id},
                    {
                        "$set": update_doc,
                        "$setOnInsert": {"created_at": created_at},
                    },
                    upsert=True,
                )
                results[wf_id] = True
                logger.info(f"System workflow synchronized: {wf_id}")
            except Exception as e:
                logger.error(f"Ensure system workflow exists for failure {wf_id}: {e}")
                results[wf_id] = False

        return results


# Singleton instance
_default_provider: Optional[DefaultWorkflowProvider] = None


def get_default_workflow_provider() -> DefaultWorkflowProvider:
    """Get the default workflow provider singleton"""
    global _default_provider
    if _default_provider is None:
        _default_provider = DefaultWorkflowProvider()
    return _default_provider

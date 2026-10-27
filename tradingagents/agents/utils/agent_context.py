from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class AgentContext:
    """Agent execution context

    Contains information about users, sessions, debugging modes, and workflows.
    Passed during Agent execution and used for:
    - Prompt word template loading (based on user_id, preference_id, workflow_id)
    - Debug mode control (is_debug_mode, debug_template_id)
    - Log tracking (session_id, request_id)
    """
    user_id: Optional[str] = None
    preference_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None

    # 🔥 Debug mode related fields
    is_debug_mode: bool = False  # Whether it is debug mode
    debug_template_id: Optional[str] = None  # Templates used in debug mode ID

    # 🆕 Workflow-related fields (used for process-specific prompt word loading)
    workflow_id: Optional[str] = None  # Currently executing workflow ID
    node_id: Optional[str] = None      # 🆕 The currently executing node ID (the same agent loads different prompt words on different nodes)

    extra: Dict[str, Any] = field(default_factory=dict)
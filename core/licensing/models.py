"""
Authorization related data model
"""

from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class LicenseTier(str, Enum):
    """License level"""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class LicenseFeatures(BaseModel):
    """License function definition"""
    
    # Agent limitations
    max_analysts: int = 4          # Maximum number of analysts
    max_researchers: int = 2       # Maximum number of researchers
    allow_custom_agents: bool = False  # Allow custom agents
    
    # Workflow restrictions
    max_workflows: int = 3         # Maximum number of saved workflows
    max_nodes_per_workflow: int = 10  # Maximum number of nodes per workflow
    allow_workflow_export: bool = False  # Allow export workflow
    
    # Advanced features
    allow_sector_analyst: bool = False   # Industry Analyst
    allow_index_analyst: bool = False    # Market Analyst
    allow_parallel_execution: bool = False  # Parallel execution
    allow_memory_persistence: bool = False  # memory persistence
    
    # API Limit
    daily_api_calls: int = 100     # Daily API call limit
    max_concurrent_executions: int = 1  # Maximum number of concurrent executions
    
    # support
    priority_support: bool = False
    custom_branding: bool = False


# Predefined function configuration
TIER_FEATURES = {
    LicenseTier.FREE: LicenseFeatures(
        max_analysts=4,
        max_researchers=2,
        max_workflows=3,
        max_nodes_per_workflow=10,
        daily_api_calls=100,
        max_concurrent_executions=1,
    ),
    LicenseTier.BASIC: LicenseFeatures(
        max_analysts=4,
        max_researchers=2,
        max_workflows=10,
        max_nodes_per_workflow=20,
        allow_workflow_export=True,
        daily_api_calls=500,
        max_concurrent_executions=2,
    ),
    LicenseTier.PRO: LicenseFeatures(
        max_analysts=6,  # contains sector_analyst, index_analyst
        max_researchers=2,
        allow_custom_agents=True,
        max_workflows=50,
        max_nodes_per_workflow=50,
        allow_workflow_export=True,
        allow_sector_analyst=True,
        allow_index_analyst=True,
        allow_parallel_execution=True,
        allow_memory_persistence=True,
        daily_api_calls=2000,
        max_concurrent_executions=5,
        priority_support=True,
    ),
    LicenseTier.ENTERPRISE: LicenseFeatures(
        max_analysts=999,
        max_researchers=999,
        allow_custom_agents=True,
        max_workflows=999,
        max_nodes_per_workflow=999,
        allow_workflow_export=True,
        allow_sector_analyst=True,
        allow_index_analyst=True,
        allow_parallel_execution=True,
        allow_memory_persistence=True,
        daily_api_calls=999999,
        max_concurrent_executions=50,
        priority_support=True,
        custom_branding=True,
    ),
}


class License(BaseModel):
    """license"""
    
    id: str                        # license ID
    tier: LicenseTier              # level
    
    # User information
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    organization: Optional[str] = None
    
    # Validity period
    issued_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    # Function
    features: LicenseFeatures = Field(default_factory=LicenseFeatures)
    
    # Status
    is_active: bool = True
    
    class Config:
        use_enum_values = True
    
    @classmethod
    def create_free(cls) -> "License":
        """Create a free license"""
        return cls(
            id="free",
            tier=LicenseTier.FREE,
            features=TIER_FEATURES[LicenseTier.FREE],
        )
    
    @classmethod
    def create_for_tier(cls, tier: LicenseTier, **kwargs) -> "License":
        """Create a license for a specified level"""
        import uuid
        return cls(
            id=str(uuid.uuid4()),
            tier=tier,
            features=TIER_FEATURES[tier],
            **kwargs
        )
    
    @property
    def is_expired(self) -> bool:
        """Has it expired?"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """Is it valid?"""
        return self.is_active and not self.is_expired


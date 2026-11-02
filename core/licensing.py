from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['models', 'community_stub']:
    _sys.modules[f"core.licensing.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === models.py ===
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


# === community_stub.py ===
"""
Community edition permission gating stub (v3.6.0 community edition open source separation · M1 §7.3) 

Gating replacement implementation when the community version is released: no authorization server, no token verification, no network request.
Publish script (scripts/publish_community.py, scheme §8.1 Step c) Point to this module as follows:

1. app/core/permissions.py → Replace the entire file with a thin shell: from this module re-export
   get_app_token / get_license_info / require_pro / require_feature / PRO_FEATURES
2. app/services/license_service.py → Replace the entire file with a thin shell: from this module re-export
   LicenseInfo / LicenseService(=CommunityLicenseService) / get_license_service / FREE_ACCESS_FEATURES
3. core/licensing/: Delete validator.py / manager.py / features.py, keep models.py and this file,
   __init__.py Change to re-export from this module (the LicenseManager reference of core/api/agent_api.py switches automatically)

Semantic convention:
- require_pro / require_feature (FastAPI Dependence): Allow transparent transmission. Community Edition Pro features rely on release pipeline
  Physical culling (PRO_ROUTERS/views/pro), retaining residual gates in files (e.g. advanced_courses.py
  Routing level dependencies) should not block the community moderator link.
- has_feature: keep free semantics——FREE_ACCESS_FEATURES Pass, rest False.
  Pro sub-function gates (such as trading_plan_check in review.py) in the Community Edition reserved code continue to block.
- is_pro: Heng False (the community version has no payment system, plan Hengwei "free") . 
- Quota: Built-in Free file (analyst 4, researcher 2, single concurrency, API 100/day),
  Numerical and core/licensing/models.py TIER_FEATURES[FREE] Be consistent.

see docs/05-design/v3.0/v3.6.0-community-edition-separation-plan.md §7.3
"""

import logging
from typing import Any, Callable, Optional

from fastapi import Depends, Header
from pydantic import BaseModel, Field

async def get_current_user():
    from app.routers.auth_db import get_current_user as _real_get_current_user
    return await _real_get_current_user()

logger = logging.getLogger("core.licensing.community_stub")


# =============================================================================
# Community edition quota (Free file)
# =============================================================================

COMMUNITY_TIER_FEATURES = LicenseFeatures(
    max_analysts=4,               # Maximum number of analysts
    max_researchers=2,            # Maximum number of researchers
    allow_custom_agents=False,    # Custom agents are not allowed
    max_workflows=3,              # Maximum number of saved workflows
    max_nodes_per_workflow=10,    # Maximum number of nodes per workflow
    allow_workflow_export=False,  # Export workflow not allowed
    allow_sector_analyst=False,   # Industry Analyst
    allow_index_analyst=False,    # Market Analyst
    allow_parallel_execution=False,   # Parallel execution
    allow_memory_persistence=False,   # memory persistence
    daily_api_calls=100,          # Daily API call limit
    max_concurrent_executions=1,  # Maximum number of concurrent executions (single concurrent)
)

# Community version free release function (aligned with FREE_ACCESS_FEATURES in app/services/license_service.py)
FREE_ACCESS_FEATURES = {"portfolio_analysis", "trade_review"}

# The Community Edition does not have Pro exclusive functions (Pro functions are physically removed from the release pipeline and do not rely on runtime gating)
PRO_FEATURES: list[str] = []


# =============================================================================
# LicenseInfo Model (same as app/services/license_service.py field definition)
# =============================================================================

class LicenseInfo(BaseModel):
    """Authorization information (community version: Hengwei free file is validly authorized)"""
    email: str
    plan: str  # Community version Hengwei "free"
    features: list[str] = Field(default_factory=list)
    device_registered: bool = False
    is_valid: bool = True
    error_message: Optional[str] = None
    verified_at: Optional[Any] = None
    # Expiration time
    trial_end_at: Optional[str] = None  # Trial expiration date
    pro_expire_at: Optional[str] = None  # PRO Expiration time
    # Cache related
    cached: bool = False
    cache_expires_at: Optional[Any] = None
    # Offline mode
    offline_mode: bool = False


def _community_license_info(email: str = "") -> LicenseInfo:
    """Construct community version authorization information (free file, valid, no network verification)"""
    return LicenseInfo(email=email, plan="free", is_valid=True, error_message=None)


# =============================================================================
# Authorization service stub (same as app/services/license_service.py entry signature)
# =============================================================================

class CommunityLicenseService:
    """Community Edition Authorization Service: No external verification, only free semantic judgment provided"""

    def get_available_servers(self) -> list[dict[str, str]]:
        """Community Edition without authorized server"""
        return []

    def resolve_auth_server(self, auth_server: Optional[str] = None) -> str:
        """Community Edition without authorized server"""
        return ""

    def get_base_url(self, auth_server: Optional[str] = None) -> str:
        """Community Edition without authorized server"""
        return ""

    async def verify_app_token(self, token: str, auth_server: Optional[str] = None) -> LicenseInfo:
        """The community version does not verify the token (the license route has been eliminated, this method is only a compatible residual call, and defensively returns to the free file)"""
        logger.debug("Community Edition skips App Token verification")
        return _community_license_info()

    def is_pro(self, license_info: LicenseInfo) -> bool:
        """There is no payment system for the community version. PRO"""
        return False

    def has_feature(self, license_info: LicenseInfo, feature: str) -> bool:
        """Free semantics: FREE_ACCESS_FEATURES is released, and the rest are intercepted (the community version plan is always free)"""
        if not license_info.is_valid:
            return False
        if feature in FREE_ACCESS_FEATURES:
            return True
        if feature in license_info.features:
            return True
        return False

    def clear_cache(self, token: Optional[str] = None, auth_server: Optional[str] = None) -> None:
        """Community Edition without caching"""
        pass


# Single instance service (same form as get_license_service)
_license_service: Optional[CommunityLicenseService] = None


def get_license_service() -> CommunityLicenseService:
    """Get community version authorization service instance (single case)"""
    global _license_service
    if _license_service is None:
        _license_service = CommunityLicenseService()
    return _license_service


# =============================================================================
# FastAPI Routing dependencies (same as app/core/permissions.py entry signature)
# =============================================================================

async def get_app_token(
    x_app_token: Optional[str] = Header(None, alias="X-App-Token")
) -> Optional[str]:
    """Obtain the App Token from the request header (not used by the community version, retain signature compatibility)"""
    return x_app_token


async def get_license_info(
    app_token: Optional[str] = Depends(get_app_token),
    user: dict = Depends(get_current_user)
) -> LicenseInfo:
    """
    Obtain the user s authorization information (community version: Hengwei free file is validly authorized, no network verification)

    Same signature as app/core/permissions.py; when the community version is released
    app/routers/auth_db.py To preserve routing, dependency chains can be resolved normally.
    """
    email = user.get("email", "") if isinstance(user, dict) else ""
    return _community_license_info(email)


async def require_pro(
    license_info: LicenseInfo = Depends(get_license_info)
) -> LicenseInfo:
    """
    Dependencies that require PRO permissions (Community Edition: allow transparent transmission)

    The Community Edition Pro route has been physically removed from the release pipeline, and this dependency is only in the residual calls of the retained files.
    Release when it occurs to ensure that the community moderator link is not blocked.
    """
    return license_info


def require_feature(feature: str) -> Callable:
    """
    Dependency factory that requires specific functions (community version: release transparent transmission)

    Usage (exactly the same as app/core/permissions.py):
        @router.get("/feature", dependencies=[Depends(require_feature("xxx"))])
        async def endpoint(...): ...
    """
    async def _check_feature(
        license_info: LicenseInfo = Depends(get_license_info),
    ) -> LicenseInfo:
        return license_info

    return _check_feature


# =============================================================================
# Engine-side license manager stub (same as the LicenseManager signature of core/licensing/manager.py)
# =============================================================================

class CommunityLicenseManager:
    """
    Community version license manager (single case): Hengwei Free file + Built-in community edition quota

    For use by engine-side codes such as core/api/agent_api.py:
    tier Hengwei FREE → Only free agents are visible (consistent with community edition functional boundaries).
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def tier(self) -> LicenseTier:
        """Current level: Hengwei FREE"""
        return LicenseTier.FREE

    @property
    def is_valid(self) -> bool:
        """Community edition is always available"""
        return True

    @property
    def features(self) -> LicenseFeatures:
        """Community edition quota (Free file)"""
        return COMMUNITY_TIER_FEATURES

    def can_use_feature(self, feature_name: str) -> bool:
        """Check whether a certain function can be used (according to Free file quota)"""
        features = self.features
        if hasattr(features, f"allow_{feature_name}"):
            return getattr(features, f"allow_{feature_name}")
        return True

    def check_limit(self, limit_name: str, current_value: int) -> bool:
        """Check whether the limit is exceeded (according to Free file quota)"""
        features = self.features
        if hasattr(features, limit_name):
            max_value = getattr(features, limit_name)
            return current_value < max_value
        return True

    def get_remaining(self, limit_name: str, current_value: int) -> int:
        """Get the remaining quota (according to the Free quota)"""
        features = self.features
        if hasattr(features, limit_name):
            max_value = getattr(features, limit_name)
            return max(0, max_value - current_value)
        return 999999

    def activate(self, license_key: str, prefer_online: bool = True) -> tuple[bool, Optional[str]]:
        """Community edition does not support license activation"""
        return False, "Community edition does not support license activation"

    def deactivate(self) -> None:
        """Community edition without license concept"""
        pass


# LicenseManager Alias: Thin shell is used with __init__.py re-export,
# make `from ..licensing import LicenseManager` The caller (core/api/agent_api.py) switches silently
LicenseManager = CommunityLicenseManager

# === __init__.py ===
"""
Authorization Management Module (Community Edition)

This file is generated by the publish pipeline (scripts/publish_community.py):
Community version deletes validator.py/manager.py/features.py (authorization server verification logic,
Exclusive to the payment system), retain models.py (quota model) and community_stub.py (community version implementation),
And re-export the engine-side dependent LicenseManager from here.
"""

__all__ = [
    "License",
    "LicenseFeatures",
    "LicenseTier",
    "LicenseManager",
]
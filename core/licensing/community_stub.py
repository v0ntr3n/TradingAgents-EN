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

from app.routers.auth_db import get_current_user
from .models import LicenseFeatures, LicenseTier

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

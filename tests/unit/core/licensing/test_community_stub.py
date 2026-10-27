"""
Community edition permission gated stub unit test (v3.6.0 community edition open source separation · M1 §7.3) 

Verify the behavioral contract of core/licensing/community_stub.py:
- require_pro / require_feature (FastAPI Dependence): allow transparent transmission
- has_feature: Free semantics (FREE_ACCESS_FEATURES is released, the rest is intercepted)
- is_pro: constant False
- Quota: Free file (analyst 4, researcher 2, single concurrency, API 100/day)
"""

import asyncio

import pytest

from core.licensing.community_stub import (
    COMMUNITY_TIER_FEATURES,
    CommunityLicenseManager,
    CommunityLicenseService,
    FREE_ACCESS_FEATURES,
    LicenseInfo,
    PRO_FEATURES,
    get_license_service,
    require_feature,
    require_pro,
    _community_license_info,
)


@pytest.fixture
def service() -> CommunityLicenseService:
    return get_license_service()


@pytest.fixture
def free_info() -> LicenseInfo:
    return _community_license_info("user@example.com")


class TestLicenseInfo:
    def test_plan_is_free(self, free_info):
        assert free_info.plan == "free"

    def test_is_valid(self, free_info):
        assert free_info.is_valid is True

    def test_no_error(self, free_info):
        assert free_info.error_message is None


class TestServiceSemantics:
    def test_is_pro_always_false(self, service, free_info):
        assert service.is_pro(free_info) is False

    def test_has_feature_free_access(self, service, free_info):
        for feature in FREE_ACCESS_FEATURES:
            assert service.has_feature(free_info, feature) is True

    def test_has_feature_pro_features_blocked(self, service, free_info):
        # Pro Functions are blocked in the community version (such as trading_plan_check in review.py)
        for feature in ("trading_plan_check", "advanced_courses", "export_reports", "workflow"):
            assert service.has_feature(free_info, feature) is False

    def test_has_feature_invalid_license(self, service):
        invalid = LicenseInfo(email="u@e.com", plan="free", is_valid=False)
        assert service.has_feature(invalid, "portfolio_analysis") is False

    def test_get_available_servers_empty(self, service):
        assert service.get_available_servers() == []

    @pytest.mark.asyncio
    async def test_verify_app_token_returns_free(self, service):
        info = await service.verify_app_token("any-token")
        assert info.plan == "free"
        assert info.is_valid is True

    def test_get_license_service_singleton(self):
        assert get_license_service() is get_license_service()


class TestFastAPIDependencies:
    @pytest.mark.asyncio
    async def test_require_pro_passthrough(self, free_info):
        result = await require_pro(license_info=free_info)
        assert result is free_info

    @pytest.mark.asyncio
    async def test_require_feature_passthrough(self, free_info):
        check = require_feature("advanced_courses")
        result = await check(license_info=free_info)
        assert result is free_info

    def test_pro_features_empty(self):
        # The Community Edition does not have Pro exclusive features (relying on physical culling, not runtime gating)
        assert PRO_FEATURES == []


class TestCommunityQuotas:
    def test_analyst_quota(self):
        assert COMMUNITY_TIER_FEATURES.max_analysts == 4

    def test_researcher_quota(self):
        assert COMMUNITY_TIER_FEATURES.max_researchers == 2

    def test_single_concurrency(self):
        assert COMMUNITY_TIER_FEATURES.max_concurrent_executions == 1

    def test_daily_api_calls(self):
        assert COMMUNITY_TIER_FEATURES.daily_api_calls == 100


class TestCommunityLicenseManager:
    @pytest.fixture
    def manager(self) -> CommunityLicenseManager:
        return CommunityLicenseManager()

    def test_tier_free(self, manager):
        from core.licensing.models import LicenseTier
        assert manager.tier == LicenseTier.FREE

    def test_singleton(self):
        assert CommunityLicenseManager() is CommunityLicenseManager()

    def test_check_limit_within(self, manager):
        # Analyst 4 quota: 3 already available, more can be added
        assert manager.check_limit("max_analysts", 3) is True

    def test_check_limit_exceeded(self, manager):
        # Analyst 4 quota: There are already 4, no more can be added
        assert manager.check_limit("max_analysts", 4) is False

    def test_get_remaining(self, manager):
        assert manager.get_remaining("max_analysts", 1) == 3
        assert manager.get_remaining("daily_api_calls", 60) == 40

    def test_activate_not_supported(self, manager):
        ok, err = manager.activate("any-key")
        assert ok is False
        assert "Not supported" in err

    def test_can_use_feature_respects_quota_flags(self, manager):
        # Boolean function is in Free mode: industry analysts are closed
        assert manager.can_use_feature("sector_analyst") is False
        assert manager.can_use_feature("parallel_execution") is False

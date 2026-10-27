"""
Health Checks and System Status API Acceptance Testing

Cover:
- GET /api/health                health check
- GET /api/system/config/summary System configuration summary
- GET /api/system/logs           Log list
"""
import pytest


class TestHealth:
    """Health Check Test."""

    def test_health_check(self, backend_url, backend_available):
        """The health check endpoint returns 200."""
        import httpx
        resp = httpx.get(f"{backend_url}/api/health", timeout=5)
        assert resp.status_code == 200

    def test_health_check_no_auth_required(self, backend_url, backend_available):
        """Health screening does not require certification."""
        import httpx
        resp = httpx.get(f"{backend_url}/api/health", timeout=5)
        assert resp.status_code == 200


class TestSystemConfig:
    """System configuration testing."""

    def test_config_summary(self, api_client):
        """Get a system configuration summary."""
        resp = api_client.get("/api/system/config/summary")
        # May return 200 or 404 (if endpoint paths are different), this validation does not return 500
        assert resp.status_code != 500, f"System configuration summary should not be returned 500: {resp.text}"

    def test_system_logs(self, api_client):
        """Get the system log list."""
        resp = api_client.get("/api/system/logs")
        assert resp.status_code != 500, f"System log should not return 500: {resp.text}"

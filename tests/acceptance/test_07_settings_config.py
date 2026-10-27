"""
Set up and configure API acceptance testing

Cover:
- GET  /api/config/system          System configuration
- GET  /api/config/llm             LLM Configuration
- GET  /api/config/datasource      Data source configuration
- GET  /api/config/qmt-diagnosis   QMT Diagnosis
- GET  /api/config/datasource-quality Data source quality
- GET  /api/tags/                  tag list
- GET  /api/cache                  Cache management
- GET  /api/mcp/audit-logs         MCP Audit log
- GET  /api/mcp/servers            MCP Server list
"""
import pytest


class TestConfig:
    """Configuration management testing."""

    def test_get_system_config(self, api_client):
        """Get system configuration."""
        resp = api_client.get("/api/config/system")
        assert resp.status_code == 200, f"Failed to obtain system configuration: {resp.text}"

    def test_get_llm_config(self, api_client):
        """Get LLM configuration."""
        resp = api_client.get("/api/config/llm")
        assert resp.status_code == 200, f"Failed to obtain LLM configuration: {resp.text}"

    def test_get_datasource_config(self, api_client):
        """Get the data source configuration."""
        resp = api_client.get("/api/config/datasource")
        assert resp.status_code == 200, f"Failed to obtain data source configuration: {resp.text}"

    def test_get_qmt_diagnosis(self, api_client):
        """QMT Connection diagnostics."""
        resp = api_client.get("/api/config/qmt-diagnosis")
        assert resp.status_code == 200, f"QMT Diagnosis failed: {resp.text}"
        data = resp.json()
        # Diagnostic results should include inspection steps
        assert isinstance(data, dict), f"Abnormal diagnosis result format: {data}"

    def test_get_datasource_quality(self, api_client):
        """Data source quality statistics."""
        resp = api_client.get("/api/config/datasource-quality")
        assert resp.status_code == 200, f"Failed to obtain data source quality: {resp.text}"


class TestTags:
    """Tag management test."""

    def test_get_tags(self, api_client):
        """Get a list of tags."""
        resp = api_client.get("/api/tags/")
        assert resp.status_code == 200, f"Failed to get tag list: {resp.text}"


class TestCache:
    """Cache management testing."""

    def test_get_cache_info(self, api_client):
        """Get cache information."""
        resp = api_client.get("/api/cache")
        assert resp.status_code in (200, 404), f"Exception in obtaining cache information: {resp.status_code}"


class TestMCPAuditLogs:
    """MCP Audit log testing."""

    def test_get_audit_logs(self, api_client):
        """Query the MCP audit log."""
        resp = api_client.get("/api/mcp/audit-logs")
        assert resp.status_code == 200, f"Failed to obtain MCP audit log: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "logs" in data or "data" in data or isinstance(data, list), \
            f"Audit log response structure abnormality: {data}"

    def test_get_audit_logs_with_filters(self, api_client):
        """Query audit logs with filter conditions."""
        resp = api_client.get("/api/mcp/audit-logs", params={
            "limit": 10,
            "offset": 0,
        })
        assert resp.status_code == 200, f"Filter query audit log failed: {resp.status_code}"

    def test_get_mcp_servers(self, api_client):
        """Get a list of MCP servers."""
        resp = api_client.get("/api/mcp/servers")
        assert resp.status_code == 200, f"Failed to obtain MCP server list: {resp.status_code} {resp.text}"

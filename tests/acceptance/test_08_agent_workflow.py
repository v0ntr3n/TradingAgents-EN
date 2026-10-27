"""
Agent Workshop and Workflow API Acceptance Testing

Cover:
- GET  /api/agents                 Agent list
- GET  /api/tools                  Tool list
- GET  /api/workflows              Workflow list
- GET  /api/agent-workshop/specs   Agent Workshop specification list
- POST /api/agent-workshop/specs/{id}/rollback Agent Version rollback
"""
import pytest


class TestAgents:
    """Agent test."""

    def test_get_agents(self, api_client):
        """Get the Agent list."""
        resp = api_client.get("/api/agents")
        assert resp.status_code == 200, f"Failed to obtain Agent list: {resp.text}"

    def test_get_available_agents(self, api_client):
        """Get the list of available Agents."""
        resp = api_client.get("/api/agents/available")
        assert resp.status_code == 200, f"Failed to obtain available Agent list: {resp.text}"

    def test_get_agent_categories(self, api_client):
        """Get the Agent classification."""
        resp = api_client.get("/api/agents/categories")
        assert resp.status_code == 200, f"Failed to obtain Agent classification: {resp.text}"


class TestTools:
    """Tool testing."""

    def test_get_tools(self, api_client):
        """Get a list of tools."""
        resp = api_client.get("/api/tools")
        assert resp.status_code == 200, f"Failed to get tool list: {resp.text}"

    def test_get_tool_categories(self, api_client):
        """Get the tool category."""
        resp = api_client.get("/api/tools/categories")
        assert resp.status_code == 200, f"Failed to obtain tool classification: {resp.text}"


class TestWorkflows:
    """Workflow testing."""

    def test_get_workflows(self, api_client):
        """Get the workflow list."""
        resp = api_client.get("/api/workflows")
        assert resp.status_code == 200, f"Failed to get workflow list: {resp.text}"

    def test_get_workflow_templates(self, api_client):
        """Get the workflow template."""
        resp = api_client.get("/api/workflows/templates")
        assert resp.status_code == 200, f"Failed to obtain workflow template: {resp.text}"


class TestAgentWorkshop:
    """Agent Workshop testing."""

    def test_get_specs(self, api_client):
        """Get the Agent Workshop specs list."""
        resp = api_client.get("/api/agent-workshop/specs")
        assert resp.status_code in (200, 404), f"Exception in obtaining Agent specification list: {resp.status_code} {resp.text}"

    def test_rollback_spec(self, api_client):
        """Version rollback interface usability testing (using non-existent ID)."""
        resp = api_client.post("/api/agent-workshop/specs/nonexistent_spec_id/rollback")
        assert resp.status_code in (200, 404, 400), f"Version rollback interface exception: {resp.status_code} {resp.text}"

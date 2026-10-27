"""
Analysis Task API Acceptance Testing

Cover:
- POST /api/analysis/single         Trigger single stock analysis
- GET  /api/analysis/tasks          User task list
- GET  /api/analysis/tasks/all      All task lists
- GET  /api/analysis/user/history   Analyze history
- GET  /api/v2/tasks/list           Unified task center list
- GET  /api/v2/tasks/statistics     Task statistics
- POST /api/analysis/tasks/{id}/feedback Analyze feedback
"""
import pytest


class TestAnalysisTrigger:
    """Trigger analysis tests."""

    def test_trigger_analysis(self, api_client):
        """Trigger a single stock analysis task."""
        resp = api_client.post("/api/analysis/single", json={
            "stock_code": "000001",
            "market_type": "A",
        })
        # Analysis trigger may return 200 (success) or 400/422 (parameter problem)
        assert resp.status_code in (200, 201, 400, 422), f"Trigger analysis exception: {resp.status_code} {resp.text}"

    def test_trigger_analysis_invalid_code(self, api_client):
        """Analysis triggered by invalid stock symbols should be rejected."""
        resp = api_client.post("/api/analysis/single", json={
            "stock_code": "",
            "market_type": "A",
        })
        assert resp.status_code in (400, 422), f"Invalid code should be rejected: {resp.status_code}"


class TestAnalysisHistory:
    """Analyze historical tests."""

    def test_get_analysis_history(self, api_client):
        """Get the analysis history list."""
        resp = api_client.get("/api/analysis/user/history")
        assert resp.status_code == 200, f"Failed to obtain analysis history: {resp.text}"

    def test_get_analysis_tasks(self, api_client):
        """Get the user task list."""
        resp = api_client.get("/api/analysis/tasks")
        assert resp.status_code == 200, f"Failed to get task list: {resp.text}"


class TestUnifiedTasks:
    """Unified mission center testing."""

    def test_get_tasks_list(self, api_client):
        """Get a unified task list."""
        resp = api_client.get("/api/v2/tasks/list")
        assert resp.status_code == 200, f"Failed to get task list: {resp.text}"
        data = resp.json()
        # Verify that a list or paginated structure is returned
        if isinstance(data, dict):
            assert "data" in data or "items" in data or "tasks" in data or "list" in data, \
                f"Task list response structure exception: {data}"

    def test_get_tasks_statistics(self, api_client):
        """Get task statistics."""
        resp = api_client.get("/api/v2/tasks/statistics")
        assert resp.status_code == 200, f"Failed to obtain task statistics: {resp.text}"

    def test_get_tasks_list_with_filters(self, api_client):
        """Get a task list with filter conditions."""
        resp = api_client.get("/api/v2/tasks/list", params={
            "status": "completed",
            "page": 1,
            "page_size": 10,
        })
        assert resp.status_code == 200


class TestAnalysisFeedback:
    """Analyze feedback testing."""

    def test_submit_feedback(self, api_client):
        """Submit analysis feedback (use a non-existent task_id, verify interface availability)."""
        resp = api_client.post("/api/analysis/tasks/test_task_id/feedback", json={
            "rating": 5,
            "comment": "Acceptance test feedback",
        })
        # The interface should be available and may return 200/201/404 (task does not exist)
        assert resp.status_code in (200, 201, 404), f"Feedback interface exception: {resp.status_code} {resp.text}"

    def test_submit_feedback_invalid_rating(self, api_client):
        """Invalid ratings (outside the 1-5 range) should be rejected."""
        resp = api_client.post("/api/analysis/tasks/test_task_id/feedback", json={
            "rating": 10,
            "comment": "Invalid rating",
        })
        assert resp.status_code in (400, 422), f"Invalid ratings should be rejected: {resp.status_code}"

"""
Reporting and Notification API Acceptance Testing

Cover:
- GET  /api/reports/list           Report list
- GET  /api/notifications          Notification list
- GET  /api/usage/statistics       usage statistics
"""
import pytest


class TestReports:
    """Report the test."""

    def test_get_reports_list(self, api_client):
        """Get a list of reports."""
        resp = api_client.get("/api/reports/list")
        assert resp.status_code == 200, f"Failed to get report list: {resp.text}"

    def test_get_reports_list_with_pagination(self, api_client):
        """Get the report list in pages."""
        resp = api_client.get("/api/reports/list", params={
            "page": 1,
            "page_size": 10,
        })
        assert resp.status_code == 200


class TestNotifications:
    """Notify the test."""

    def test_get_notifications(self, api_client):
        """Get a list of notifications."""
        resp = api_client.get("/api/notifications")
        assert resp.status_code == 200, f"Failed to get notification list: {resp.text}"

    def test_get_unread_count(self, api_client):
        """Get the number of unread notifications."""
        resp = api_client.get("/api/notifications/unread-count")
        assert resp.status_code in (200, 404), f"Get unread count exception: {resp.status_code}"


class TestUsageStatistics:
    """Use statistical tests."""

    def test_get_usage_statistics(self, api_client):
        """Get usage statistics."""
        resp = api_client.get("/api/usage/statistics")
        assert resp.status_code == 200, f"Failed to obtain usage statistics: {resp.text}"

    def test_get_token_statistics(self, api_client):
        """Get Token usage statistics."""
        resp = api_client.get("/api/usage/token-statistics")
        assert resp.status_code in (200, 404), f"Obtaining Token statistics exception: {resp.status_code}"

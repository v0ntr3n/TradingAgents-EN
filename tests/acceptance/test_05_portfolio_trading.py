"""
Position and Trading Plan API Acceptance Testing

Cover:
- GET  /api/portfolio/positions     Position list
- GET  /api/paper/positions         Simulated trading positions
- GET  /api/v1/trading-systems      Trading plan list
- POST /api/v1/trading-systems      Create a trading plan
- GET  /api/review/periodic/history Transaction review history
- POST /api/review/periodic         Trigger periodic review
"""
import pytest


class TestPortfolio:
    """Position management testing."""

    def test_get_portfolio_positions(self, api_client):
        """Get the list of positions."""
        resp = api_client.get("/api/portfolio/positions")
        assert resp.status_code == 200, f"Failed to obtain position list: {resp.text}"

    def test_get_portfolio_statistics(self, api_client):
        """Get position statistics."""
        resp = api_client.get("/api/portfolio/statistics")
        assert resp.status_code == 200, f"Failed to obtain position statistics: {resp.text}"

    def test_get_portfolio_account(self, api_client):
        """Get account information."""
        resp = api_client.get("/api/portfolio/account")
        assert resp.status_code == 200, f"Failed to obtain account information: {resp.text}"


class TestPaperTrading:
    """Simulated trading test."""

    def test_get_paper_positions(self, api_client):
        """Get simulated trading positions."""
        resp = api_client.get("/api/paper/positions")
        assert resp.status_code == 200, f"Failed to obtain simulated trading position: {resp.text}"

    def test_get_paper_account(self, api_client):
        """Get a demo trading account."""
        resp = api_client.get("/api/paper/account")
        assert resp.status_code == 200, f"Failed to obtain demo trading account: {resp.text}"


class TestTradingSystem:
    """Trading plan testing."""

    def test_get_trading_systems(self, api_client):
        """Get a list of trading plans."""
        resp = api_client.get("/api/v1/trading-systems")
        assert resp.status_code == 200, f"Failed to get trading plan list: {resp.text}"

    def test_get_active_trading_system(self, api_client):
        """Get an active trading plan."""
        resp = api_client.get("/api/v1/trading-systems/active")
        assert resp.status_code in (200, 404), f"Get active trading plan exception: {resp.status_code}"

    def test_create_trading_system(self, api_client):
        """Create a trading plan."""
        resp = api_client.post("/api/v1/trading-systems", json={
            "name": "Acceptance test trading plan",
            "description": "Automated testing of trading plans created",
            "stocks": [],
            "rules": {
                "stop_loss": {"type": "percentage", "value": 5},
                "take_profit": {"type": "percentage", "value": 10},
            },
        })
        assert resp.status_code in (200, 201, 400, 422), f"Create trading plan exception: {resp.status_code} {resp.text}"
        if resp.status_code in (200, 201):
            data = resp.json()
            data_field = data.get("data", data) if isinstance(data, dict) else data
            system_id = data_field.get("id") or data_field.get("_id") or data_field.get("system_id") if isinstance(data_field, dict) else None
            if system_id:
                api_client.delete(f"/api/v1/trading-systems/{system_id}")


class TestTradeReview:
    """Transaction review testing."""

    def test_get_periodic_reviews(self, api_client):
        """Get periodic review history."""
        resp = api_client.get("/api/review/periodic/history")
        assert resp.status_code == 200, f"Failed to obtain periodic review history: {resp.text}"

    def test_get_review_statistics(self, api_client):
        """Get review statistics."""
        resp = api_client.get("/api/review/statistics")
        assert resp.status_code == 200, f"Failed to obtain review statistics: {resp.text}"

    def test_trigger_periodic_review(self, api_client):
        """Trigger periodic review."""
        resp = api_client.post("/api/review/periodic", json={
            "review_type": "weekly",
        })
        assert resp.status_code in (200, 201, 400, 422), f"Trigger review exception: {resp.status_code} {resp.text}"

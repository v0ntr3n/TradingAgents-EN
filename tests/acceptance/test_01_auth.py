"""
Certification module API acceptance testing

Cover:
- POST /api/auth/login  Login
- GET  /api/auth/me     Get current user information
- POST /api/auth/logout Log out
- POST /api/auth/login  Bad Credentials Denied

API unified response structure: {success: bool, data: ..., message: str}
"""
import httpx
import pytest


def _unwrap(resp_json):
    """Unpack the unified response structure and return the data field."""
    if isinstance(resp_json, dict) and "data" in resp_json:
        return resp_json["data"]
    return resp_json


class TestLogin:
    """Login interface test."""

    def test_login_success(self, backend_url, backend_available):
        """Log in successfully with correct credentials and return access_token and user information."""
        resp = httpx.post(
            f"{backend_url}/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        assert "access_token" in data, f"Response missing access_token: {data}"
        assert "refresh_token" in data, f"Response missing refresh_token: {data}"
        assert "user" in data, f"Response missing user: {data}"
        assert data["user"]["username"] == "admin"

    def test_login_wrong_password(self, backend_url, backend_available):
        """Login failed with wrong password."""
        resp = httpx.post(
            f"{backend_url}/api/auth/login",
            json={"username": "admin", "password": "wrong_password"},
            timeout=10,
        )
        assert resp.status_code in (401, 403, 400), f"Wrong passwords should be rejected: {resp.status_code}"

    def test_login_nonexistent_user(self, backend_url, backend_available):
        """Login failed for non-existent user."""
        resp = httpx.post(
            f"{backend_url}/api/auth/login",
            json={"username": "nonexistent_user_xyz", "password": "any"},
            timeout=10,
        )
        assert resp.status_code in (401, 403, 400)

    def test_login_missing_fields(self, backend_url, backend_available):
        """Missing required fields return 422."""
        resp = httpx.post(
            f"{backend_url}/api/auth/login",
            json={"username": "admin"},
            timeout=10,
        )
        assert resp.status_code == 422


class TestAuthMe:
    """Get the current user information test."""

    def test_get_me_with_token(self, api_client):
        """Obtaining user information successfully with valid token."""
        resp = api_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        assert "username" in data, f"Response missing username: {data}"

    def test_get_me_without_token(self, backend_url, backend_available):
        """Accessing /me without token returns 401."""
        resp = httpx.get(f"{backend_url}/api/auth/me", timeout=10)
        assert resp.status_code == 401

    def test_get_me_with_invalid_token(self, backend_url, backend_available):
        """Accessing /me with invalid token returns 401."""
        resp = httpx.get(
            f"{backend_url}/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_xyz"},
            timeout=10,
        )
        assert resp.status_code == 401


class TestLogout:
    """Logout interface test."""

    def test_logout_success(self, backend_url, backend_available):
        """Log out successfully after logging in."""
        # Log in first
        login_resp = httpx.post(
            f"{backend_url}/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=10,
        )
        token = _unwrap(login_resp.json())["access_token"]
        # Log out
        resp = httpx.post(
            f"{backend_url}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert resp.status_code == 200

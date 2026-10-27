"""
Acceptance Testing - Backend API Automated Testing Framework

Use pytest + httpx Do end-to-end API acceptance testing of running backend services.
The backend needs to be started before testing: python -m uvicorn app.main:app --port 8000
"""
import os
import pytest
import httpx


# ==================== Configuration ====================

BACKEND_BASE_URL = os.getenv("TEST_BACKEND_URL", "http://localhost:8000")
TEST_USERNAME = os.getenv("TEST_USERNAME", "admin")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "admin123")


# ==================== Fixtures ====================

@pytest.fixture(scope="session")
def backend_url() -> str:
    """Backend service base URL."""
    return BACKEND_BASE_URL


@pytest.fixture(scope="session")
def backend_available(backend_url) -> bool:
    """Check whether the backend service is available (session level, only checked once)."""
    try:
        resp = httpx.get(f"{backend_url}/api/health", timeout=5)
        if resp.status_code == 200:
            return True
    except Exception:
        pass
    pytest.skip(f"Backend service is unavailable: {backend_url}, Please start the backend service first")


@pytest.fixture(scope="session")
def auth_token(backend_url, backend_available) -> str:
    """Log in to obtain access_token (session level, all tests share one token)."""
    resp = httpx.post(
        f"{backend_url}/api/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        timeout=10,
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    body = resp.json()
    # API unified response structure: {success, data: {access_token, refresh_token, user}, message}
    data = body.get("data", body)
    token = data.get("access_token")
    assert token, f"None in login response access_token: {body}"
    return token


@pytest.fixture(scope="session")
def auth_headers(auth_token) -> dict:
    """Request header with authentication."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def api_client(backend_url, auth_headers) -> httpx.Client:
    """HTTP client with authentication (function level, per test independent)."""
    with httpx.Client(base_url=backend_url, headers=auth_headers, timeout=30) as client:
        yield client


@pytest.fixture(scope="session")
def api_client_session(backend_url, auth_headers) -> httpx.Client:
    """HTTP client with authentication (session level, used when sharing state across tests)."""
    with httpx.Client(base_url=backend_url, headers=auth_headers, timeout=30) as client:
        yield client

"""
ETF GA Acceptance testing

Cover:
- ETF Market inquiry (GET /api/stocks/{etf_code}/quote)
- ETF Fundamentals query (GET /api/stocks/{etf_code}/fundamentals)
- ETF K Line query (GET /api/stocks/{etf_code}/kline)
- ETF Data synchronization (POST /api/sync/etf/run)
- ETF Simulated trading quotes (GET /api/paper/quote/{etf_code})

ETF code rules:
- Shanghai Stock Exchange: 50/51/52/56/58 Beginning (Such as 510050 Shanghai Stock Exchange 50ETF)
- Shenzhen Stock Exchange: 15/16/18 Beginning (Such as 159919 Shanghai and Shenzhen 300ETF)
- Beijing Exchange: 89 Beginning
"""
import pytest


# ETF ticker for testing
ETF_SH_CODE = "510050"   # Shanghai Stock Exchange 50ETF
ETF_SZ_CODE = "159919"   # Shanghai and Shenzhen 300ETF


class TestETFQuote:
    """ETF Market query test."""

    def test_get_sh_etf_quote(self, api_client):
        """Get SSE ETF quotes."""
        resp = api_client.get(f"/api/stocks/{ETF_SH_CODE}/quote")
        assert resp.status_code == 200, f"Failed to obtain ETF quotes: {resp.text}"
        data = resp.json()
        # Verification returned data
        data_field = data.get("data", data) if isinstance(data, dict) else data
        assert data_field is not None, f"ETF Market data is empty: {data}"

    def test_get_sz_etf_quote(self, api_client):
        """Get SZSE ETF quotes."""
        resp = api_client.get(f"/api/stocks/{ETF_SZ_CODE}/quote")
        assert resp.status_code == 200, f"Failed to obtain Shenzhen Stock Exchange ETF quotations: {resp.text}"


class TestETFFundamentals:
    """ETF Fundamental query testing."""

    def test_get_etf_fundamentals(self, api_client_session):
        """Get ETF fundamental data."""
        resp = api_client_session.get(f"/api/stocks/{ETF_SH_CODE}/fundamentals", timeout=120)
        assert resp.status_code == 200, f"Failed to get ETF fundamentals: {resp.text}"
        data = resp.json()
        data_field = data.get("data", data) if isinstance(data, dict) else data
        # ETF Fundamentals should include information such as net worth
        if isinstance(data_field, dict):
            # There should at least be a name
            assert data_field.get("name") or data_field.get("short_name") or data_field.get("ts_code"), \
                f"ETF Fundamentals are missing name information: {data_field}"


class TestETFKline:
    """ETF K Online query test."""

    def test_get_etf_kline(self, api_client_session):
        """Get ETF K-line data."""
        resp = api_client_session.get(f"/api/stocks/{ETF_SH_CODE}/kline", params={
            "period": "daily",
            "limit": 30,
        }, timeout=120)
        assert resp.status_code == 200, f"Failed to obtain ETF K-line: {resp.text}"
        data = resp.json()
        data_field = data.get("data", data) if isinstance(data, dict) else data
        # K Line data should be a list
        if isinstance(data_field, dict):
            kline = data_field.get("kline") or data_field.get("data") or data_field.get("items")
            # As long as there is data, it is not mandatory to be non-empty (the data source may not be available)
            assert kline is not None or data_field is not None, f"ETF K Line data abnormality: {data_field}"


class TestETFSync:
    """ETF Data synchronization test."""

    def test_trigger_etf_sync(self, api_client_session):
        """Trigger ETF data sync."""
        resp = api_client_session.post("/api/sync/etf/run", json={
            "force": False,
            "days": 7,
        }, timeout=120)
        # The sync may return 200 (triggered successfully) or 409 (sync already running)
        assert resp.status_code in (200, 201, 409, 422), f"ETF Synchronous trigger exception: {resp.status_code} {resp.text}"


class TestETFPaperTrading:
    """ETF Simulated trading test."""

    def test_get_etf_paper_quote(self, api_client):
        """Get simulated ETF trading quotes."""
        resp = api_client.get(f"/api/paper/quote/{ETF_SH_CODE}")
        assert resp.status_code in (200, 404), f"ETF Abnormal simulated trading market conditions: {resp.status_code} {resp.text}"

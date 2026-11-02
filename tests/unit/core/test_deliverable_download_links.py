# -*- coding: utf-8 -*-
"""Deliverable signature download link test.

Background: If the browser directly clicks the markdown download link without the JWT header, the original route must be 401
 ("Not logged in or your login has expired") . Fix using presigned URL pattern: when tool generates link
Append HMAC signature + Expiration time, routing verification signature release; no signature fallback login authentication.
"""

import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from core.deliverables.download_links import (
    sign_deliverable_query,
    verify_deliverable_signature,
)


class TestSignatureHelper:
    def test_sign_then_verify_roundtrip(self):
        filename = "table_Cyrus (601127) revenue forecast_20260915_174922.xlsx"
        query = sign_deliverable_query(filename)
        assert query.startswith("exp=")
        parts = dict(p.split("=", 1) for p in query.split("&"))
        assert verify_deliverable_signature(filename, parts["exp"], parts["sig"]) is True

    def test_wrong_filename_rejected(self):
        """The signature is bound to the file name: accessing file B with the signature of file A must be denied."""
        query = sign_deliverable_query("table_a.xlsx")
        parts = dict(p.split("=", 1) for p in query.split("&"))
        assert verify_deliverable_signature("table_b.xlsx", parts["exp"], parts["sig"]) is False

    def test_expired_rejected(self):
        exp = str(int(time.time()) - 10)
        with patch("core.deliverables.download_links._compute_sig") as mock_sig:
            mock_sig.return_value = "0" * 32
            assert verify_deliverable_signature("a.xlsx", exp, "0" * 32) is False

    def test_missing_params_rejected(self):
        assert verify_deliverable_signature("a.xlsx", None, None) is False
        assert verify_deliverable_signature("a.xlsx", "123", None) is False
        assert verify_deliverable_signature("a.xlsx", None, "abc") is False

    def test_tampered_sig_rejected(self):
        query = sign_deliverable_query("a.xlsx")
        parts = dict(p.split("=", 1) for p in query.split("&"))
        bad_sig = ("0" if parts["sig"][0] != "0" else "1") + parts["sig"][1:]
        assert verify_deliverable_signature("a.xlsx", parts["exp"], bad_sig) is False

    def test_ascii_filename_also_works(self):
        """The plain ASCII file name of the valuation instrument (valuation_601127_xxx.xlsx) is also signable."""
        query = sign_deliverable_query("valuation_601127_20260915_120000.xlsx")
        parts = dict(p.split("=", 1) for p in query.split("&"))
        assert (
            verify_deliverable_signature("valuation_601127_20260915_120000.xlsx", parts["exp"], parts["sig"])
            is True
        )


class TestDownloadRouteAuth:
    """Dual-channel authentication for download routing: valid signature release / no signature required to log in."""

    @pytest.fixture
    def client_with_file(self):
        """Creates a test file and returns the TestClient factory (settings configured)."""
        import os
        from pathlib import Path

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        filename = "table_Test signature download_20260915_000000.xlsx"
        base_dir = Path.cwd() / "data" / "deliverables"
        base_dir.mkdir(parents=True, exist_ok=True)
        file_path = base_dir / filename
        file_path.write_bytes(b"PK\x03\x04 fake-xlsx")

        import sys

        sys.path.insert(0, ".")
        from starlette.middleware.sessions import SessionMiddleware

        from app.routers.intelligent_assistant import router

        app = FastAPI()
        # get_current_user To access request.session, SessionMiddleware is required (consistent with the main application)
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.include_router(router)
        client = TestClient(app)

        yield client, filename

        try:
            os.remove(file_path)
        except OSError:
            pass

    def test_signed_link_downloads_without_jwt(self, client_with_file):
        """Core regression scenario: The browser directly clicks the signed link (without Authorization header) and should respond to 200."""
        from urllib.parse import quote

        client, filename = client_with_file
        url = f"/api/assistant/deliverables/{quote(filename)}?{sign_deliverable_query(filename)}"
        resp = client.get(url)
        assert resp.status_code == 200, f"The signed link should be released, and the actual {resp.status_code}: {resp.text[:200]}"
        assert resp.content.startswith(b"PK")

    def test_unsigned_link_returns_401(self, client_with_file):
        """No signature and not logged in → 401 (Maintain the original safe behavior)."""
        from urllib.parse import quote

        client, filename = client_with_file
        resp = client.get(f"/api/assistant/deliverables/{quote(filename)}")
        assert resp.status_code == 401

    def test_path_traversal_still_blocked(self):
        """Safe return: path crossing must still be intercepted."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.middleware.sessions import SessionMiddleware

        import sys

        sys.path.insert(0, ".")
        from app.routers.intelligent_assistant import router

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.include_router(router)
        client = TestClient(app)

        # ..%2F The traversal is included after decoding the path param "..", Regular release ".." but explicitly exclude
        resp = client.get("/api/assistant/deliverables/..%2Fsecret.xlsx")
        assert resp.status_code in (400, 404)

    def test_non_xlsx_blocked(self, client_with_file):
        from urllib.parse import quote

        client, _ = client_with_file
        fn = "table_malicious.exe"
        url = f"/api/assistant/deliverables/{quote(fn)}?{sign_deliverable_query(fn)}"
        resp = client.get(url)
        assert resp.status_code == 400


class TestToolLinkGeneration:
    """The markdown link returned by the tool must have signed parameters."""

    def test_export_tool_link_contains_signature(self, monkeypatch, tmp_path):
        from core.tools.implementations.assistant_ops import export_table_excel_tool as mod

        monkeypatch.setattr(mod, "_OUTPUT_DIR", str(tmp_path))

        markdown = (
            "| month | Sales volume | Revenue(billion) |\n|---|---:|---:|\n| 2026-09 | 10,500 | 106.5 |"
        )
        result = mod.export_table_excel_tool.invoke(
            {"markdown_tables": f"## revenue forecast\n{markdown}", "title": "Cyrus (601127) revenue forecast"}
        )
        assert "exp=" in result and "sig=" in result
        # Half-angle brackets must not appear in links (markdown link targets will be truncated)
        assert "(" not in result.split("](")[-1]

    def test_filename_fullwidth_parens(self):
        from core.tools.implementations.assistant_ops.export_table_excel_tool import (
            _sanitize_filename_part,
        )

        assert "(" not in _sanitize_filename_part("Thalys(601127)model")
        assert "（601127）" in _sanitize_filename_part("Thalys(601127)model")

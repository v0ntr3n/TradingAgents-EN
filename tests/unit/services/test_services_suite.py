from __future__ import annotations

# === Merged from test_embedded_nanobot_auth_guard.py ===
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.middleware.auth_guard import AuthGuardMiddleware
from app.schemas.embedded_nanobot import EmbeddedNanobotThreadMessagesResponse


def test_embedded_nanobot_response_schema_accepts_datetime_timestamps() -> None:
    now = datetime(2026, 4, 6, 10, 52, 12, 788000, tzinfo=timezone.utc)

    response = EmbeddedNanobotThreadMessagesResponse(
        thread={
            "thread_id": "thread-001",
            "title": "Nanobot session",
            "session_key": "embedded:test",
            "created_at": now,
            "updated_at": now,
        },
        messages=[
            {
                "message_id": "msg-001",
                "role": "assistant",
                "content": "hello",
                "created_at": now,
            }
        ],
    )

    assert response.thread is not None
    assert response.thread.created_at == now.isoformat()
    assert response.thread.updated_at == now.isoformat()
    assert response.messages[0].created_at == now.isoformat()


def test_auth_guard_does_not_mask_downstream_http_exception(monkeypatch) -> None:
    app = FastAPI()
    app.add_middleware(AuthGuardMiddleware)

    @app.get("/api/protected")
    async def protected_route():
        raise HTTPException(status_code=418, detail="teapot")

    from app.services.auth_service import AuthService

    monkeypatch.setattr(AuthService, "verify_token", staticmethod(lambda _token: {"sub": "user-001"}))

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/protected", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 418
    assert response.json()["detail"] == "teapot"

# === Merged from test_industry_mapping_service.py ===
import pytest
from pymongo import UpdateMany
from unittest.mock import AsyncMock, Mock, patch

from app.services.official_industry_service import (
    sync_industry_to_stock_basic_info,
    upsert_industry_mapping_from_records,
)


@pytest.mark.asyncio
async def test_upsert_industry_mapping_from_records_writes_system_collection():
    mock_collection = Mock()
    mock_collection.bulk_write = AsyncMock(return_value=Mock(modified_count=1, upserted_count=1))
    mock_db = {"stock_industry_mappings": mock_collection}

    records = [
        {"code": "000001", "industry": "bank"},
        {"symbol": "000002", "industry": "Nationwide Real Estate"},
        {"code": "000003", "industry": ""},
    ]

    with patch('app.services.official_industry_service.get_mongo_db', return_value=mock_db):
        result = await upsert_industry_mapping_from_records(records, provider="tushare_fallback")

    assert result["provider"] == "tushare_fallback"
    assert result["total"] == 2
    mock_collection.bulk_write.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_industry_to_stock_basic_info_updates_all_sources_for_same_code():
    mock_collection = Mock()
    mock_collection.bulk_write = AsyncMock(return_value=Mock(modified_count=2))
    mock_db = {"stock_basic_info": mock_collection}

    with patch('app.services.official_industry_service.get_mongo_db', return_value=mock_db), patch(
        'app.services.official_industry_service.fetch_industry_mapping',
        new=AsyncMock(return_value={"000001": "bank"})
    ):
        result = await sync_industry_to_stock_basic_info()

    assert result["updated"] == 2
    assert result["total"] == 1
    mock_collection.bulk_write.assert_awaited_once()

    operations = mock_collection.bulk_write.await_args.args[0]
    assert len(operations) == 1
    assert isinstance(operations[0], UpdateMany)
    assert operations[0]._filter == {"code": "000001"}
    assert operations[0]._doc["$set"]["industry"] == "bank"

# === Merged from test_intelligent_assistant_memory_filters.py ===
import pytest

from app.services.intelligent_assistant_service import (
    _extract_memory_metadata_filters,
    _recall_memory_block,
)


class _FakeMemoryService:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def recall_formatted(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeProjectMemoryService:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def build_prompt_block(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_extract_memory_metadata_filters_reads_symbol_from_topic_title() -> None:
    assert _extract_memory_metadata_filters("Kweichow Moutai(600519) analysis report") == {"symbol": "600519"}
    assert _extract_memory_metadata_filters("Tencent Holdings(HK.00700) analysis report") == {"symbol": "HK.00700"}
    assert _extract_memory_metadata_filters("Macro strategy discussion") is None


def test_extract_memory_metadata_filters_falls_back_to_report_refs() -> None:
    assert _extract_memory_metadata_filters(
        "Macro strategy discussion",
        report_refs=[{"symbol": "sz.000001"}, {"symbol": "600519"}],
    ) == {"symbol": "SZ.000001"}


@pytest.mark.asyncio
async def test_recall_memory_block_passes_symbol_metadata_filters(monkeypatch):
    fake_memory_service = _FakeMemoryService("memory block")

    monkeypatch.setattr("core.memory.service.get_memory_service", lambda db: fake_memory_service)

    result = await _recall_memory_block(
        db=object(),
        user_id="user-1",
        user_message="Help me review the previous analysis conclusions of this target.",
        current_topic_title="Kweichow Moutai(600519) analysis report",
    )

    assert result == "memory block"
    assert len(fake_memory_service.calls) == 1
    call = fake_memory_service.calls[0]
    assert call["metadata_filters"] == {"symbol": "600519"}
    assert call["scopes"] == ["conversation", "user_preference", "analysis_insight", "trade_pattern"]


@pytest.mark.asyncio
async def test_recall_memory_block_skips_metadata_filters_without_symbol(monkeypatch):
    fake_memory_service = _FakeMemoryService("memory block")

    monkeypatch.setattr("core.memory.service.get_memory_service", lambda db: fake_memory_service)

    await _recall_memory_block(
        db=object(),
        user_id="user-1",
        user_message="To summarize my recent preferences",
        current_topic_title="Macro strategy discussion",
    )

    assert len(fake_memory_service.calls) == 1
    assert fake_memory_service.calls[0]["metadata_filters"] is None


@pytest.mark.asyncio
async def test_recall_memory_block_uses_report_ref_symbol_when_title_has_no_symbol(monkeypatch):
    fake_memory_service = _FakeMemoryService("memory block")

    monkeypatch.setattr("core.memory.service.get_memory_service", lambda db: fake_memory_service)

    await _recall_memory_block(
        db=object(),
        user_id="user-1",
        user_message="Review historical analysis of this topic",
        current_topic_title="Macro strategy discussion",
        report_refs=[{"symbol": "hk.00700", "title": "Tencent Holdings(HK.00700) analysis report"}],
    )

    assert len(fake_memory_service.calls) == 1
    assert fake_memory_service.calls[0]["metadata_filters"] == {"symbol": "HK.00700"}


@pytest.mark.asyncio
async def test_recall_memory_block_combines_project_memory_with_mem0(monkeypatch):
    fake_memory_service = _FakeMemoryService(" [Historical preferences]\n- Prefer to read the conclusion first")
    fake_project_memory_service = _FakeProjectMemoryService(" [Project long-term memory]\n- Output constraints\n  - Answer structure: give conclusion first")

    monkeypatch.setattr("core.memory.service.get_memory_service", lambda db: fake_memory_service)
    monkeypatch.setattr(
        "app.services.project_memory_service.get_project_memory_service",
        lambda db: fake_project_memory_service,
    )

    result = await _recall_memory_block(
        db=object(),
        user_id="user-1",
        user_message="continue this theme",
        current_topic_title="Macro strategy discussion",
    )

    assert " [Project long-term memory]" in result
    assert " [Historical preferences]" in result
    assert len(fake_project_memory_service.calls) == 1
    assert fake_project_memory_service.calls[0]["max_items"] == 4

# === Merged from test_multi_source_basics_sync_service.py ===
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd

from app.services.multi_source_basics_sync_service import MultiSourceBasicsSyncService


class _FakeManager:
    def get_available_adapters(self):
        return [SimpleNamespace(name="akshare")]

    def get_stock_list_with_fallback(self, preferred_sources=None, exclude_local=True):
        return pd.DataFrame([
            {
                "ts_code": "300750.SZ",
                "symbol": "300750",
                "name": "Ningde era",
                "industry": "",
                "market": "GEM",
            }
        ]), "akshare"

    def find_latest_trade_date_with_fallback(self, preferred_sources=None):
        return None


def test_run_full_sync_uses_system_industry_mapping_for_batch_docs():
    service = MultiSourceBasicsSyncService()
    captured_operations = []

    async def _capture_bulk_write(db, operations, max_retries=3):
        captured_operations.extend(operations)
        return 0, len(operations)

    service._execute_bulk_write_with_retry = AsyncMock(side_effect=_capture_bulk_write)

    status_collection = MagicMock()
    status_collection.update_one = AsyncMock(return_value=None)
    fake_db = MagicMock()
    fake_db.__getitem__.return_value = status_collection

    with patch("app.services.multi_source_basics_sync_service.get_mongo_db", return_value=fake_db), \
         patch("app.services.data_sources.manager.DataSourceManager", return_value=_FakeManager()), \
         patch("app.services.official_industry_service.fetch_industry_mapping", new=AsyncMock(return_value={"300750": "electrical equipment"})):
        result = asyncio.run(service.run_full_sync(preferred_sources=["akshare"]))

    assert result["status"] == "success"
    assert "industry_mapping:system_industry_mapping" in result["data_sources_used"]
    assert len(captured_operations) == 1

    update_filter = captured_operations[0]._filter
    update_payload = captured_operations[0]._doc["$set"]

    assert update_filter == {"code": "300750", "source": "akshare"}
    assert update_payload["industry"] == "electrical equipment"
    assert update_payload["industry_source"] == "system_industry_mapping"

# === Merged from test_quotes_backfill.py ===
import asyncio


def test_offhours_backfill_when_empty(monkeypatch):
    from app.services.quotes_ingestion_service import QuotesIngestionService
    import app.services.quotes_ingestion_service as qis_mod

    # Fake DataSourceManager to avoid external calls
    class _FakeManager:
        def get_realtime_quotes_with_fallback(self):
            return {
                "000001": {"close": 10.2, "pct_chg": 0.2, "amount": 1.1e8},
                "600000": {"close": 9.7, "pct_chg": -0.4, "amount": 7.1e7},
            }, "fake"

        def find_latest_trade_date_with_fallback(self):
            return "20250102"

    monkeypatch.setattr(qis_mod, "DataSourceManager", _FakeManager, raising=True)

    # Fake DB/collection
    class _FakeResult:
        def __init__(self, upserted):
            self.matched_count = 0
            self.modified_count = 0
            self.upserted_ids = {i: None for i in range(upserted)}

    class _FakeColl:
        def __init__(self):
            self.last_ops = None

        async def create_index(self, *args, **kwargs):
            return "ok"

        async def estimated_document_count(self):
            return 0  # empty -> should trigger backfill

        async def bulk_write(self, ops, ordered=False):
            self.last_ops = ops
            return _FakeResult(len(ops))

    class _FakeDB:
        def __init__(self):
            self._coll = _FakeColl()

        def __getitem__(self, name: str):
            return self._coll

    fake_db = _FakeDB()

    def _fake_get_mongo_db():
        return fake_db

    monkeypatch.setattr(qis_mod, "get_mongo_db", _fake_get_mongo_db, raising=True)

    async def _run():
        svc = QuotesIngestionService()
        # Force off-hours
        monkeypatch.setattr(QuotesIngestionService, "_is_trading_time", lambda self, now=None: False, raising=True)
        await svc.run_once()
        assert fake_db._coll.last_ops is not None
        assert len(fake_db._coll.last_ops) == 2

    asyncio.run(_run())


# === Merged from test_scheduler_quotes_job.py ===
import inspect
from types import SimpleNamespace

from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI


def test_scheduler_adds_quotes_job(monkeypatch):
    # Flags to assert behavior
    state = SimpleNamespace(
        ensure_indexes_called=False,
        create_task_called=False,
    )

    # Fake QuotesIngestionService used by app.main during startup
    class _FakeQuotesIngestion:
        async def ensure_indexes(self):
            state.ensure_indexes_called = True

        async def run_once(self):
            # simple async no-op
            return None

    # Capture added jobs from scheduler
    class _FakeScheduler:
        def __init__(self):
            self.jobs = []

        def add_job(self, func, trigger, *args, **kwargs):
            # record and keep a handle to the callable and trigger
            self.jobs.append({"func": func, "trigger": trigger, "args": args, "kwargs": kwargs})

        def start(self):
            # no-op in tests
            return None

        def shutdown(self, wait=False):
            return None

    # Patch scheduler and service in app.main before startup runs
    import app.main as main_mod

    fake_scheduler = _FakeScheduler()

    def _fake_asyncio_create_task(coro):
        # We don't need a running loop; just record and close the coroutine to avoid warnings
        state.create_task_called = True
        assert inspect.iscoroutine(coro)
        try:
            coro.close()
        except Exception:
            pass
        return None

    # Patch blocking init/close DB and basic sync service
    async def _noop_async(*args, **kwargs):
        return None

    class _FakeBasicsService:
        async def run_full_sync(self, force: bool = False):
            return None

    monkeypatch.setattr(main_mod, "init_db", _noop_async, raising=True)
    monkeypatch.setattr(main_mod, "close_db", _noop_async, raising=True)
    monkeypatch.setattr(main_mod, "get_basics_sync_service", lambda: _FakeBasicsService(), raising=True)

    # Patch scheduler, quotes service and asyncio.create_task
    monkeypatch.setattr(main_mod, "AsyncIOScheduler", lambda *args, **kwargs: fake_scheduler, raising=True)
    monkeypatch.setattr(main_mod, "QuotesIngestionService", _FakeQuotesIngestion, raising=True)
    monkeypatch.setattr(main_mod.asyncio, "create_task", _fake_asyncio_create_task, raising=True)

    # Directly drive the lifespan to avoid importing full router stack
    import asyncio as _asyncio

    async def _run():
        async with main_mod.lifespan(FastAPI()):
            return

    _asyncio.run(_run())

    # Assert a job with IntervalTrigger was scheduled
    assert fake_scheduler.jobs, "No jobs scheduled for quotes ingestion"
    job = None
    for j in fake_scheduler.jobs:
        if isinstance(j["trigger"], IntervalTrigger):
            job = j
            break
    assert job is not None, "Quotes ingestion IntervalTrigger job not found"

    # Ensure ensure_indexes called during startup
    assert state.ensure_indexes_called is True

    # Simulate scheduler tick by invoking the stored func
    job_func = job["func"]
    job_func()  # should call asyncio.create_task(...) with our fake

    assert state.create_task_called is True


# === Merged from test_session_service.py ===
from datetime import datetime, timedelta

from app.services.session_service import SessionService


class _FakeDeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    def create_index(self, *args, **kwargs):
        return None

    def insert_one(self, doc):
        self.docs.append(dict(doc))

    def find_one(self, filter_doc):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in filter_doc.items()):
                return doc
        return None

    def update_one(self, filter_doc, update_doc):
        doc = self.find_one(filter_doc)
        if not doc:
            return None
        if "$set" in update_doc:
            doc.update(update_doc["$set"])
        return None

    def delete_one(self, filter_doc):
        for index, doc in enumerate(self.docs):
            if all(doc.get(key) == value for key, value in filter_doc.items()):
                self.docs.pop(index)
                return _FakeDeleteResult(1)
        return _FakeDeleteResult(0)


class _FakeDb:
    def __init__(self):
        self.user_sessions = _FakeCollection()


def test_verify_session_renews_expiration_for_active_user():
    db = _FakeDb()
    service = SessionService(db)

    session_id = service.create_session(user_id="user-1", expires_in_seconds=60)
    session_doc = db.user_sessions.find_one({"session_id": session_id})
    session_doc["created_at"] = session_doc["created_at"] - timedelta(seconds=30)
    session_doc["last_activity"] = session_doc["created_at"]
    session_doc["expires_at"] = session_doc["created_at"] + timedelta(seconds=60)
    original_expires_at = session_doc["expires_at"]

    service.verify_session(session_id, update_activity=True)

    renewed_doc = db.user_sessions.find_one({"session_id": session_id})
    assert renewed_doc is not None
    assert renewed_doc["expires_at"] > original_expires_at
    assert renewed_doc["last_activity"] >= session_doc["created_at"]


def test_verify_session_uses_inferred_ttl_for_legacy_session_documents():
    db = _FakeDb()
    service = SessionService(db)

    created_at = datetime.utcnow() - timedelta(seconds=90)
    expires_at = created_at + timedelta(seconds=120)
    db.user_sessions.insert_one({
        "session_id": "legacy-session",
        "user_id": "user-legacy",
        "created_at": created_at,
        "expires_at": expires_at,
        "last_activity": created_at,
        "ip_address": None,
        "user_agent": None,
    })

    service.verify_session("legacy-session", update_activity=True)

    renewed_doc = db.user_sessions.find_one({"session_id": "legacy-session"})
    assert renewed_doc is not None
    assert renewed_doc["expires_at"] > expires_at

# === Merged from test_skill_generation_memory_filters.py ===
import pytest

from app.services.skill_generation_service import (
    _build_skill_memory_metadata_filters,
    _recall_skill_lessons,
)
from core.tools.external import SkillSpec


class _FakeMemoryService:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def recall_formatted(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_build_skill_memory_metadata_filters_prefers_category_and_data_source() -> None:
    spec = SkillSpec(
        tool_id="get_stock_news",
        display_name="individual stock news",
        description="Get a list of individual stock news",
        category="news",
        data_source="eastmoney",
    )

    assert _build_skill_memory_metadata_filters(spec) == {
        "category": "news",
        "data_source": "eastmoney",
    }


def test_build_skill_memory_metadata_filters_falls_back_to_tool_id() -> None:
    spec = SkillSpec(
        tool_id="get_custom_payload",
        display_name="Custom payload",
        description="Generate custom payload",
        category="",
        data_source="",
    )

    assert _build_skill_memory_metadata_filters(spec) == {"tool_id": "get_custom_payload"}


@pytest.mark.asyncio
async def test_recall_skill_lessons_passes_metadata_filters(monkeypatch):
    fake_memory_service = _FakeMemoryService("skill lessons")
    spec = SkillSpec(
        tool_id="get_stock_news",
        display_name="individual stock news",
        description="Get a list of individual stock news",
        category="news",
        data_source="eastmoney",
    )

    monkeypatch.setattr("core.memory.service.get_memory_service", lambda db: fake_memory_service)

    result = await _recall_skill_lessons(object(), spec)

    assert result == "skill lessons"
    assert len(fake_memory_service.calls) == 1
    call = fake_memory_service.calls[0]
    assert call["agent_id"] == "skill_generator"
    assert call["scopes"] == ["skill_lesson"]
    assert call["metadata_filters"] == {
        "category": "news",
        "data_source": "eastmoney",
    }

# === Merged from test_stop_gain_alert_service.py ===
import pytest

from app.services.stop_gain_alert_service import StopGainAlertService


class _FakeCursor:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        self._iter = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def to_list(self, length=None):
        if length is None:
            return list(self._items)
        return list(self._items[:length])


class _FakeCollection:
    def __init__(self, docs):
        self._docs = list(docs)

    def find(self, *args, **kwargs):
        return _FakeCursor(self._docs)


class _FakeDb:
    def __init__(self):
        self.users = _FakeCollection([
            {
                "_id": "user_a",
                "favorite_stocks": [
                    {"stock_code": "600519", "stock_name": "Moutai", "market": "A shares", "alert_gain_price": 1800}
                ],
            }
        ])
        self.user_favorites = _FakeCollection([])
        self.market_quotes = _FakeCollection([
            {"code": "600519", "close": 1810.0}
        ])
        self.market_quotes_hk = _FakeCollection([])
        self.market_quotes_us = _FakeCollection([])


@pytest.mark.asyncio
async def test_load_watch_items_fetches_db_per_run(monkeypatch):
    service = StopGainAlertService()
    calls = []

    def _fake_get_db():
        calls.append("db")
        return _FakeDb()

    monkeypatch.setattr(service, "_get_db", staticmethod(_fake_get_db))

    items = await service._load_watch_items_async()

    assert len(calls) == 1
    assert len(items) == 1
    assert items[0]["user_id"] == "user_a"
    assert items[0]["current_price"] == 1810.0


def test_stop_shuts_down_scheduler_when_running():
    service = StopGainAlertService()

    class _FakeScheduler:
        running = True

        def __init__(self):
            self.shutdown_called = False
            self.wait_value = None

        def shutdown(self, wait=False):
            self.shutdown_called = True
            self.wait_value = wait

    fake_scheduler = _FakeScheduler()
    service.scheduler = fake_scheduler
    service._job = object()

    service.stop()

    assert fake_scheduler.shutdown_called is True
    assert fake_scheduler.wait_value is False
    assert service._job is None

# === Merged from test_system_config_summary_sse_queue.py ===
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

# Import the router and its dependency to override
from app.routers import system_config as system_cfg_router
from app.routers.auth import get_current_user


@pytest.fixture()
def app_client():
    app = FastAPI()
    app.include_router(system_cfg_router.router, prefix="/api/system")

    # Admin override
    def _admin_user():
        return {"id": "u1", "is_admin": True}

    app.dependency_overrides[get_current_user] = _admin_user

    client = TestClient(app)
    return client


def test_config_summary_contains_new_settings_fields(app_client: TestClient):
    resp = app_client.get("/api/system/config/summary")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "settings" in data
    s = data["settings"]

    # Queue/Worker
    assert "QUEUE_POLL_INTERVAL_SECONDS" in s
    assert "QUEUE_CLEANUP_INTERVAL_SECONDS" in s
    assert "WORKER_HEARTBEAT_INTERVAL" in s

    # SSE
    assert "SSE_POLL_TIMEOUT_SECONDS" in s
    assert "SSE_HEARTBEAT_INTERVAL_SECONDS" in s
    assert "SSE_TASK_MAX_IDLE_SECONDS" in s
    assert "SSE_BATCH_POLL_INTERVAL_SECONDS" in s
    assert "SSE_BATCH_MAX_IDLE_SECONDS" in s


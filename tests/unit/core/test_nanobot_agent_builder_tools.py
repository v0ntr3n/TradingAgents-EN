import json
import sys
import types

import pytest

from app.models.capability_index import CapabilityDocument, CapabilitySearchHit
from core.llm.models import LLMConfig as CoreLLMConfig
from core.llm.models import LLMProvider
from core.agents.config import AgentCategory, AgentInput, AgentMetadata, AgentOutput, LicenseTier
from core.agents.universal import UniversalAgent
from core.tools.implementations.agent_builder.nanobot_agent_builder_tools import (
    analyze_agent_workshop_gaps,
    bind_agent_tools_and_validate_candidate,
    build_agent_workshop_version,
    create_or_update_agent_workshop_draft,
    create_or_update_runtime_agent_config,
    create_or_update_universal_agent_prompt_template,
    debug_agent_workshop_version,
    evaluate_agent_workshop_version,
    generate_confirmed_candidate_agent,
    generate_agent_workshop_tooling_plan,
    get_current_thread_effective_prompt_template,
    get_effective_prompt_template,
    get_prompt_template_detail,
    get_agent_blueprint_details,
    inspect_agent_blueprints,
    inspect_prompt_templates,
    inspect_agent_workshop_assets,
    inspect_runtime_agent_configs,
    iterate_agent_workshop_version,
    publish_agent_workshop_version,
    prepare_agent_requirement_intake,
    prepare_agent_generation_confirmation,
    resolve_agent_workshop_blocking_gaps,
    process_agent_workshop_gap_resolution_jobs_once,
    start_agent_workshop_gap_resolution,
    inspect_agent_workshop_gap_resolution,
    cancel_agent_workshop_gap_resolution,
    retry_agent_workshop_gap_resolution_item,
    run_agent_workshop_real_data_test,
    search_project_capabilities,
)


class _FakeCapabilityService:
    def __init__(self, db):
        self.db = db

    async def search_capabilities(self, query, top_k, bindable_only, source_types):
        assert query == "A stock valuation"
        assert top_k == 5
        assert bindable_only is True
        assert source_types == ["builtin_tool", "skill"]
        return [
            CapabilitySearchHit(
                capability=CapabilityDocument(
                    capability_id="get_value_factor_bundle_tool",
                    registry_tool_id="get_value_factor_bundle_tool",
                    source_type="builtin_tool",
                    category="fundamentals",
                    name="value factor package",
                    description="Valuation factor set",
                    when_to_use="Valuation analysis",
                    returns="JSON",
                    related_tools=["get_fundamental_factor_snapshot_tool"],
                    coverage_terms=["Valuation", "PE", "PB"],
                    data_source="local",
                    metadata={"parameters": [{"name": "symbol"}]},
                    bindable=True,
                ),
                score=0.91,
            )
        ]


class _FakeRegistry:
    def __init__(self, items):
        self._items = {item.id: item for item in items}

    def list_all(self):
        return list(self._items.values())

    def get_metadata(self, agent_id):
        return self._items.get(agent_id)


class _FakeCursor:
    def __init__(self, items):
        self._items = list(items)

    def sort(self, key, direction):
        reverse = direction == -1
        self._items.sort(key=lambda item: item.get(key) or "", reverse=reverse)
        return self

    async def to_list(self, length=None):
        if length is None:
            return list(self._items)
        return list(self._items[:length])


class _FakeCollection:
    def __init__(self, items):
        self._items = list(items)
        self._next_id = len(self._items) + 1

    def _match(self, item, query):
        query = query or {}
        for key, expected in query.items():
            value = item.get(key)
            if isinstance(expected, dict):
                if "$ne" in expected:
                    if value == expected["$ne"]:
                        return False
                    continue
            if value != expected:
                return False
        return True

    @staticmethod
    def _apply_projection(item, projection):
        if not projection:
            return item
        enabled_values = list(projection.values())
        include_keys = {key for key, enabled in projection.items() if enabled}
        exclude_keys = {key for key, enabled in projection.items() if not enabled}
        if include_keys and not all(enabled == 0 for enabled in enabled_values):
            return {key: item[key] for key in include_keys if key in item}
        return {key: value for key, value in item.items() if key not in exclude_keys}

    def find(self, query=None, projection=None):
        filtered = []
        for item in self._items:
            if self._match(item, query):
                filtered.append(self._apply_projection(item, projection))
        return _FakeCursor(filtered)

    async def find_one(self, query=None, projection=None, sort=None):
        results = self.find(query, projection)
        if sort:
            for key, direction in reversed(sort):
                results.sort(key, direction)
        items = await results.to_list(length=1)
        return items[0] if items else None

    async def update_one(self, query, update, upsert=False):
        target = None
        for item in self._items:
            if self._match(item, query):
                target = item
                break
        if target is None and upsert:
            target = dict(query)
            if "_id" not in target:
                target["_id"] = f"fake_{self._next_id}"
                self._next_id += 1
            self._items.append(target)
        if target is None:
            return None
        if "$set" in update:
            for key, value in update["$set"].items():
                current = target
                parts = key.split(".")
                for part in parts[:-1]:
                    current = current.setdefault(part, {})
                current[parts[-1]] = value
        if "$inc" in update:
            for key, value in update["$inc"].items():
                target[key] = int(target.get(key) or 0) + value
        return None

    async def insert_one(self, doc):
        inserted = dict(doc)
        inserted.setdefault("_id", f"fake_{self._next_id}")
        self._next_id += 1
        self._items.append(inserted)
        return type("InsertOneResult", (), {"inserted_id": inserted["_id"]})()

    async def insert_many(self, docs):
        ids = []
        for doc in docs:
            inserted = dict(doc)
            inserted.setdefault("_id", f"fake_{self._next_id}")
            self._next_id += 1
            self._items.append(inserted)
            ids.append(inserted["_id"])
        return type("InsertManyResult", (), {"inserted_ids": ids})()

    async def delete_many(self, query):
        self._items = [item for item in self._items if not self._match(item, query)]
        return None


class _NestedFakeCollection(_FakeCollection):
    def _match(self, item, query):
        query = query or {}
        for key, expected in query.items():
            current = item
            for part in key.split("."):
                if not isinstance(current, dict) or part not in current:
                    current = None
                    break
                current = current.get(part)
            if isinstance(expected, dict):
                if "$in" in expected:
                    if current not in expected["$in"]:
                        return False
                    continue
                if "$ne" in expected:
                    if current == expected["$ne"]:
                        return False
                    continue
            if current != expected:
                return False
        return True


class _FakeDb:
    def __init__(self, collections):
        self._collections = collections

    def __getattr__(self, name):
        try:
            return self._collections[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __getitem__(self, name):
        return self._collections[name]


def _build_agent(agent_id: str, name: str, description: str, tags: list[str], tools: list[str]) -> AgentMetadata:
    return AgentMetadata(
        id=agent_id,
        name=name,
        description=description,
        category=AgentCategory.ANALYST,
        license_tier=LicenseTier.FREE,
        tags=tags,
        tools=tools,
        default_tools=tools[:1],
        inputs=[AgentInput(name="ticker", type="string", description="Stock code")],
        outputs=[AgentOutput(name="report", type="string", description="Analyze results")],
    )


@pytest.mark.asyncio
async def test_search_project_capabilities_returns_formatted_hits(monkeypatch):
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: object(),
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.CapabilityIndexService",
        _FakeCapabilityService,
    )

    raw = await search_project_capabilities.ainvoke({
        "query": "A stock valuation",
        "top_k": 5,
        "bindable_only": True,
        "source_types": "builtin_tool,skill",
    })
    payload = json.loads(raw)

    assert payload["count"] == 1
    assert payload["results"][0]["capability_id"] == "get_value_factor_bundle_tool"
    assert payload["results"][0]["metadata"]["parameters"][0]["name"] == "symbol"


def test_inspect_agent_blueprints_filters_keyword(monkeypatch):
    registry = _FakeRegistry([
        _build_agent("valuation_analyst_v2", "Valuation Analyst", "Analyze valuation levels", ["Valuation analysis"], ["get_value_factor_bundle_tool"]),
        _build_agent("news_analyst_v2", "news analyst", "Analyze news events", ["News"], ["get_stock_news_unified"]),
    ])
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_registry",
        lambda: registry,
    )

    raw = inspect_agent_blueprints.invoke({"keyword": "Valuation", "limit": 10, "maintained_only": False})
    payload = json.loads(raw)

    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "valuation_analyst_v2"


def test_get_agent_blueprint_details_returns_single_blueprint(monkeypatch):
    registry = _FakeRegistry([
        _build_agent("valuation_analyst_v2", "Valuation Analyst", "Analyze valuation levels", ["Valuation analysis"], ["get_value_factor_bundle_tool"]),
    ])
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_registry",
        lambda: registry,
    )

    raw = get_agent_blueprint_details.invoke({"agent_id": "valuation_analyst_v2"})
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["agent"]["id"] == "valuation_analyst_v2"


@pytest.mark.asyncio
async def test_inspect_runtime_agent_configs_reads_db_defined_agents(monkeypatch):
    registry = _FakeRegistry([
        _build_agent("valuation_analyst_v2", "Valuation Analyst", "Analyze valuation levels", ["Valuation analysis"], ["get_value_factor_bundle_tool"]),
    ])
    fake_db = _FakeDb({
        "agent_configs": _FakeCollection([
            {
                "agent_id": "custom_valuation_agent",
                "name": "Custom valuation Agent",
                "description": "Valuation of database configuration Agent",
                "output_field": "valuation_report",
                "tools": ["get_value_factor_bundle_tool"],
                "default_tools": ["get_stock_valuation_context"],
                "metadata": {"status": "active", "source": "agent_workshop"},
                "updated_at": "2026-04-02T10:00:00",
            },
            {
                "agent_id": "valuation_analyst_v2",
                "name": "Valuation Analyst Coverage",
                "description": "Database coverage of built-in Agent",
                "tools": ["get_value_factor_bundle_tool"],
                "updated_at": "2026-04-01T10:00:00",
            },
        ]),
        "tool_agent_bindings": _FakeCollection([
            {"agent_id": "custom_valuation_agent", "tool_id": "get_value_factor_bundle_tool", "priority": 1, "is_active": True},
            {"agent_id": "custom_valuation_agent", "tool_id": "summarize_industry_valuation", "priority": 2, "is_active": True},
        ]),
    })
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_registry",
        lambda: registry,
    )

    raw = await inspect_runtime_agent_configs.ainvoke({"keyword": "Custom valuation", "limit": 5})
    payload = json.loads(raw)

    assert payload["count"] == 1
    assert payload["results"][0]["agent_id"] == "custom_valuation_agent"
    assert payload["results"][0]["runtime_mode"] == "universal_agent"
    assert payload["results"][0]["effective_tools"] == [
        "get_value_factor_bundle_tool",
        "summarize_industry_valuation",
    ]


@pytest.mark.asyncio
async def test_inspect_runtime_agent_configs_filters_orphaned_nanobot_generated_candidates(monkeypatch):
    fake_db = _FakeDb({
        "agent_configs": _FakeCollection([
            {
                "agent_id": "valuation_analyst_v7",
                "name": "A Stock Valuation Analyst v7",
                "description": "Residual candidates after the workshop assets have been deleted",
                "output_field": "valuation_report",
                "metadata": {
                    "source": "nanobot_generated",
                    "spec_id": "spec_nanobot_valuation_analyst_v7",
                    "session_id": "session_deleted_v7",
                },
                "updated_at": "2026-04-03T11:06:00",
            }
        ]),
        "tool_agent_bindings": _FakeCollection([]),
        "agent_specs": _FakeCollection([]),
        "agent_versions": _FakeCollection([]),
    })
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_registry",
        lambda: _FakeRegistry([]),
    )

    raw = await inspect_runtime_agent_configs.ainvoke({"keyword": "Valuation", "limit": 10})
    payload = json.loads(raw)

    assert payload["count"] == 0


@pytest.mark.asyncio
async def test_inspect_agent_workshop_assets_returns_specs_and_versions(monkeypatch):
    fake_db = _FakeDb({
        "agent_specs": _FakeCollection([
            {
                "spec_id": "spec_valuation_001",
                "name": "Valuation Agent Specifications",
                "domain": "a_share",
                "primary_goal": "Output valuation conclusion",
                "responsibilities": ["Valuation comparison", "Industry comparison"],
                "status": "active",
                "version_count": 2,
                "current_version_id": "ver_valuation_002",
                "updated_at": "2026-04-02T09:00:00",
            }
        ]),
        "agent_versions": _FakeCollection([
            {
                "version_id": "ver_valuation_002",
                "spec_id": "spec_valuation_001",
                "version": 2,
                "status": "testing",
                "agent_metadata": {"id": "custom_valuation_agent", "name": "Custom valuation Agent"},
                "required_tools": ["get_value_factor_bundle_tool"],
                "required_capabilities": ["industry_valuation_compare"],
                "prompt_template_ref": {"template_id": "tpl_001", "status": "active"},
                "updated_at": "2026-04-02T09:30:00",
            }
        ]),
    })
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    raw = await inspect_agent_workshop_assets.ainvoke({"keyword": "Valuation", "limit": 5})
    payload = json.loads(raw)

    assert payload["spec_count"] == 1
    assert payload["version_count"] == 1
    assert payload["specs"][0]["spec_id"] == "spec_valuation_001"
    assert payload["versions"][0]["version_id"] == "ver_valuation_002"
    assert payload["versions"][0]["required_tools"] == ["get_value_factor_bundle_tool"]


@pytest.mark.asyncio
async def test_inspect_agent_workshop_assets_supports_exact_spec_and_version_lookup(monkeypatch):
    fake_db = _FakeDb({
        "agent_specs": _FakeCollection([
            {
                "spec_id": "spec_valuation_001",
                "name": "Valuation Agent Specifications",
                "domain": "a_share",
                "primary_goal": "Output valuation conclusion",
                "responsibilities": ["Valuation comparison"],
                "status": "active",
                "version_count": 2,
                "current_version_id": "ver_valuation_003",
                "updated_at": "2026-04-02T09:00:00",
            },
            {
                "spec_id": "spec_other_001",
                "name": "Other Agent Specifications",
                "domain": "a_share",
                "primary_goal": "Other outputs",
                "responsibilities": ["Others"],
                "status": "active",
                "version_count": 1,
                "current_version_id": "ver_other_001",
                "updated_at": "2026-04-01T09:00:00",
            },
        ]),
        "agent_versions": _FakeCollection([
            {
                "version_id": "ver_valuation_002",
                "spec_id": "spec_valuation_001",
                "version": 2,
                "status": "published",
                "agent_metadata": {"id": "custom_valuation_agent", "name": "Custom valuation Agent"},
                "required_tools": ["get_value_factor_bundle_tool"],
                "required_capabilities": ["industry_valuation_compare"],
                "prompt_template_ref": {"template_id": "tpl_001", "status": "active"},
                "updated_at": "2026-04-02T09:30:00",
            },
            {
                "version_id": "ver_other_001",
                "spec_id": "spec_other_001",
                "version": 1,
                "status": "testing",
                "agent_metadata": {"id": "other_agent", "name": "Others Agent"},
                "required_tools": ["other_tool"],
                "required_capabilities": ["other_capability"],
                "prompt_template_ref": {"template_id": "tpl_other", "status": "active"},
                "updated_at": "2026-04-01T09:30:00",
            },
        ]),
    })
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    raw = await inspect_agent_workshop_assets.ainvoke({
        "spec_id": "spec_valuation_001",
        "version_id": "ver_valuation_002",
        "agent_id": "custom_valuation_agent",
    })
    payload = json.loads(raw)

    assert payload["spec_id"] == "spec_valuation_001"
    assert payload["version_id"] == "ver_valuation_002"
    assert payload["agent_id"] == "custom_valuation_agent"
    assert payload["spec_count"] == 1
    assert payload["version_count"] == 1
    assert payload["specs"][0]["spec_id"] == "spec_valuation_001"
    assert payload["versions"][0]["version_id"] == "ver_valuation_002"
    assert payload["versions"][0]["agent_id"] == "custom_valuation_agent"


@pytest.mark.asyncio
async def test_inspect_agent_workshop_assets_supports_workshop_session_lookup(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_sessions": _FakeCollection([
            {
                "session_id": "session_valuation_001",
                "spec_id": "spec_valuation_001",
                "current_spec_snapshot": {
                    "spec_id": "spec_valuation_001",
                    "current_version_id": "ver_valuation_002",
                },
            }
        ]),
        "agent_specs": _FakeCollection([
            {
                "spec_id": "spec_valuation_001",
                "name": "Valuation Agent Specifications",
                "domain": "a_share",
                "primary_goal": "Output valuation conclusion",
                "responsibilities": ["Valuation comparison"],
                "status": "active",
                "version_count": 2,
                "current_version_id": "ver_valuation_002",
                "updated_at": "2026-04-02T09:00:00",
            }
        ]),
        "agent_versions": _FakeCollection([
            {
                "version_id": "ver_valuation_002",
                "spec_id": "spec_valuation_001",
                "version": 2,
                "status": "testing",
                "agent_metadata": {"id": "custom_valuation_agent", "name": "Custom valuation Agent"},
                "required_tools": ["get_value_factor_bundle_tool"],
                "required_capabilities": ["industry_valuation_compare"],
                "prompt_template_ref": {"template_id": "tpl_001", "status": "active"},
                "updated_at": "2026-04-02T09:30:00",
            }
        ]),
    })
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    raw = await inspect_agent_workshop_assets.ainvoke({"workshop_session_id": "session_valuation_001"})
    payload = json.loads(raw)

    assert payload["workshop_session_id"] == "session_valuation_001"
    assert payload["spec_id"] == "spec_valuation_001"
    assert payload["version_id"] == "ver_valuation_002"
    assert payload["spec_count"] == 1
    assert payload["version_count"] == 1
    assert payload["specs"][0]["spec_id"] == "spec_valuation_001"
    assert payload["versions"][0]["version_id"] == "ver_valuation_002"


@pytest.mark.asyncio
async def test_create_or_update_runtime_agent_config_upserts_candidate(monkeypatch):
    fake_db = _FakeDb({"agent_configs": _FakeCollection([])})
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    raw = await create_or_update_runtime_agent_config.ainvoke({
        "agent_id": "valuation_candidate_v1",
        "agent_name": "Valuation candidates Agent",
        "description": "Output A-share valuation conclusion",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["action"] == "created"
    assert payload["agent"]["agent_id"] == "valuation_candidate_v1"
    assert payload["agent"]["metadata"]["generation_status"] == "candidate"


@pytest.mark.asyncio
async def test_create_or_update_agent_workshop_draft_creates_visible_spec_and_session(monkeypatch):
    fake_db = _FakeDb({
        "agent_specs": _FakeCollection([]),
        "agent_workshop_sessions": _FakeCollection([]),
        "agent_versions": _FakeCollection([]),
    })
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.require_current_user_id",
        lambda: "user_001",
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_current_assistant_thread_id",
        lambda: "thread_valuation",
    )

    raw = await create_or_update_agent_workshop_draft.ainvoke({
        "agent_id": "valuation_candidate_v1",
        "agent_name": "Valuation candidates Agent",
        "target_responsibility": "Output A-share valuation conclusion",
        "output_field": "valuation_report",
        "tool_ids": "get_value_factor_bundle_tool",
        "preferred_methods": "PE,PB,PEG",
        "constraints": "Do not output trading advice",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["spec_id"] == "agent_valuation_candidate"
    assert payload["source"] == "nanobot"
    spec_doc = fake_db["agent_specs"]._items[0]
    assert spec_doc["owner_user_id"] == "user_001"
    assert spec_doc["source"] == "nanobot"
    assert spec_doc["outputs"] == ["valuation_report"]
    session_doc = fake_db["agent_workshop_sessions"]._items[0]
    assert session_doc["spec_id"] == "agent_valuation_candidate"
    assert session_doc["user_id"] == "user_001"


@pytest.mark.asyncio
async def test_create_or_update_agent_workshop_draft_blocks_existing_active_version(monkeypatch):
    fake_db = _FakeDb({
        "agent_specs": _FakeCollection([
            {
                "spec_id": "spec_nanobot_industry_comparison_researcher_v1",
                "current_version_id": "spec_nanobot_industry_comparison_researcher_v1_v1",
            }
        ]),
        "agent_versions": _FakeCollection([
            {
                "version_id": "spec_nanobot_industry_comparison_researcher_v1_v1",
                "spec_id": "spec_nanobot_industry_comparison_researcher_v1",
                "status": "active",
            }
        ]),
        "agent_evaluations": _FakeCollection([]),
        "agent_workshop_sessions": _FakeCollection([]),
    })

    async def _fake_create_nanobot_draft(self, **kwargs):
        del self, kwargs
        raise AssertionError("create_nanobot_draft should not be called for active version ids")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.require_current_user_id",
        lambda: "user_001",
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_current_assistant_thread_id",
        lambda: "thread_industry_compare",
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.create_nanobot_draft",
        _fake_create_nanobot_draft,
    )

    raw = await create_or_update_agent_workshop_draft.ainvoke({
        "agent_id": "spec_nanobot_industry_comparison_researcher_v1_v1",
        "agent_name": "Industry Comparative Researcher v1",
        "target_responsibility": "Output industry comparative analysis",
    })
    payload = json.loads(raw)

    assert payload["status"] == "blocked"
    assert payload["blocked_by"] == "phase_guard"
    assert payload["blocked_code"] == "active_version_requires_iteration"
    assert payload["current_phase"] == "published"
    assert payload["version_id"] == "spec_nanobot_industry_comparison_researcher_v1_v1"
    assert payload["_tool_events"][0]["name"] == "create_or_update_agent_workshop_draft.phase_guard"


@pytest.mark.asyncio
async def test_create_or_update_agent_workshop_draft_blocks_existing_active_spec(monkeypatch):
    fake_db = _FakeDb({
        "agent_specs": _FakeCollection([
            {
                "spec_id": "spec_nanobot_industry_comparison_researcher_v1",
                "current_version_id": "spec_nanobot_industry_comparison_researcher_v1_v1",
            }
        ]),
        "agent_versions": _FakeCollection([
            {
                "version_id": "spec_nanobot_industry_comparison_researcher_v1_v1",
                "spec_id": "spec_nanobot_industry_comparison_researcher_v1",
                "status": "active",
            }
        ]),
        "agent_evaluations": _FakeCollection([]),
        "agent_workshop_sessions": _FakeCollection([]),
    })

    async def _fake_create_nanobot_draft(self, **kwargs):
        del self, kwargs
        raise AssertionError("create_nanobot_draft should not be called for active spec ids")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.require_current_user_id",
        lambda: "user_001",
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_current_assistant_thread_id",
        lambda: "thread_industry_compare",
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.create_nanobot_draft",
        _fake_create_nanobot_draft,
    )

    raw = await create_or_update_agent_workshop_draft.ainvoke({
        "agent_id": "spec_nanobot_industry_comparison_researcher_v1",
        "agent_name": "Industry Comparative Researcher v1",
        "target_responsibility": "Output industry comparative analysis",
    })
    payload = json.loads(raw)

    assert payload["status"] == "blocked"
    assert payload["blocked_by"] == "phase_guard"
    assert payload["blocked_code"] == "active_version_requires_iteration"
    assert payload["current_phase"] == "published"
    assert payload["spec_id"] == "spec_nanobot_industry_comparison_researcher_v1"
    assert payload["version_id"] == "spec_nanobot_industry_comparison_researcher_v1_v1"
    assert payload["_tool_events"][0]["name"] == "create_or_update_agent_workshop_draft.phase_guard"


@pytest.mark.asyncio
async def test_analyze_agent_workshop_gaps_bridges_to_workshop_service(monkeypatch):
    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def analyze_gaps(self, session_id):
            assert session_id == "session_gap_001"
            return {
                "session_id": session_id,
                "spec_id": "spec_nanobot_valuation_candidate_v1",
                "gap_report": {
                    "existing_tools": ["get_value_factor_bundle_tool"],
                    "suggested_tools": ["get_peer_comparison_tool"],
                    "blocking_gaps": ["Lack of industry comparison capabilities"],
                },
            }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: object(),
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )

    raw = await analyze_agent_workshop_gaps.ainvoke({"session_id": "session_gap_001"})
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["spec_id"] == "spec_nanobot_valuation_candidate_v1"
    assert payload["summary"]["existing_tools"] == 1
    assert payload["summary"]["blocking_gaps"] == 1


@pytest.mark.asyncio
async def test_generate_agent_workshop_tooling_plan_bridges_to_workshop_service(monkeypatch):
    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def generate_tooling_plan(self, session_id):
            assert session_id == "session_tooling_001"
            return {
                "session_id": session_id,
                "spec_id": "spec_nanobot_valuation_candidate_v1",
                "tooling_plan": {
                    "missing_capabilities": ["industry_compare", "historical_band"],
                    "tool_suggestions": [{"tool_id": "get_peer_comparison_tool"}],
                },
            }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: object(),
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )

    raw = await generate_agent_workshop_tooling_plan.ainvoke({"session_id": "session_tooling_001"})
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["spec_id"] == "spec_nanobot_valuation_candidate_v1"
    assert payload["summary"]["missing_capabilities"] == 2


@pytest.mark.asyncio
async def test_build_agent_workshop_version_bridges_to_workshop_service(monkeypatch):
    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def build_version(self, session_id):
            assert session_id == "session_version_001"
            return {
                "session_id": session_id,
                "spec_id": "spec_nanobot_valuation_candidate_v1",
                "version": {
                    "version_id": "spec_nanobot_valuation_candidate_v1_v1",
                    "required_tools": ["get_value_factor_bundle_tool", "get_peer_comparison_tool"],
                    "required_capabilities": ["industry_compare"],
                },
            }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: object(),
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )

    raw = await build_agent_workshop_version.ainvoke({"session_id": "session_version_001"})
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["spec_id"] == "spec_nanobot_valuation_candidate_v1"
    assert payload["summary"]["version_id"] == "spec_nanobot_valuation_candidate_v1_v1"
    assert payload["summary"]["required_tools"] == 2
    assert payload["summary"]["required_capabilities"] == 1


@pytest.mark.asyncio
async def test_build_agent_workshop_version_blocks_when_session_not_ready(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_sessions": _FakeCollection([{
            "session_id": "session_pending_001",
            "spec_id": "spec_pending_001",
            "feasibility_status": "need-clarification",
            "completeness_score": 0.52,
            "current_spec_snapshot": {"spec_id": "spec_pending_001"},
        }]),
        "agent_specs": _FakeCollection([{"spec_id": "spec_pending_001", "current_version_id": None}]),
        "agent_versions": _FakeCollection([]),
        "agent_evaluations": _FakeCollection([]),
    })

    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def build_version(self, session_id):
            raise AssertionError(f"build_version should not be called: {session_id}")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )

    raw = await build_agent_workshop_version.ainvoke({"session_id": "session_pending_001"})
    payload = json.loads(raw)

    assert payload["status"] == "blocked"
    assert payload["blocked_by"] == "phase_guard"
    assert payload["blocked_code"] == "phase_not_ready"
    assert payload["current_phase"] == "confirmation"
    assert payload["session_id"] == "session_pending_001"
    assert payload["_tool_events"][0]["name"] == "build_agent_workshop_version.phase_guard"


@pytest.mark.asyncio
async def test_resolve_agent_workshop_blocking_gaps_requires_external_data_confirmation(monkeypatch):
    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_ext_001"
            return types.SimpleNamespace(
                spec_id="spec_ext_001",
                user_id="user_001",
                current_spec_snapshot=types.SimpleNamespace(name="external data Agent", primary_goal="Internet data analysis"),
                gap_report=types.SimpleNamespace(blocking_gaps=["Requires akshare real-time data interface"]),
            )

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: object(),
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )

    raw = await resolve_agent_workshop_blocking_gaps.ainvoke({"session_id": "ws_ext_001"})
    payload = json.loads(raw)

    assert payload["status"] == "blocked"
    assert payload["blocked_by"] == "external_data_risk_confirmation"
    assert payload["workshop_session_id"] == "ws_ext_001"
    assert payload["risky_gaps"]


@pytest.mark.asyncio
async def test_resolve_agent_workshop_blocking_gaps_reuses_high_similarity_skill(monkeypatch):
    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_dedup_high_001"
            return types.SimpleNamespace(
                spec_id="spec_dedup_001",
                user_id="user_001",
                current_spec_snapshot=types.SimpleNamespace(name="Valuation Agent", primary_goal="Valuation output"),
                gap_report=types.SimpleNamespace(blocking_gaps=[]),
            )

    class _FakeCapabilityService:
        def __init__(self, db):
            self.db = db

        async def search_capabilities(self, query, top_k, bindable_only, source_types):
            del query, top_k, bindable_only, source_types
            return [
                CapabilitySearchHit(
                    capability=CapabilityDocument(
                        capability_id="external.skill.longhubang",
                        registry_tool_id="longhubang_query",
                        source_type="external_skill",
                        bindable=True,
                        name="Dragon and Tiger List Inquiry",
                    ),
                    score=0.92,
                )
            ]

    class _FakeSkillService:
        def __init__(self, db):
            self.db = db

        async def start_session(self, *args, **kwargs):
            raise AssertionError("high similarity should reuse existing skill and not start generation session")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: object(),
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.CapabilityIndexService",
        _FakeCapabilityService,
    )
    monkeypatch.setattr(
        "app.services.skill_generation_service.SkillGenerationService",
        _FakeSkillService,
    )

    raw = await resolve_agent_workshop_blocking_gaps.ainvoke({
        "session_id": "ws_dedup_high_001",
        "blocking_gaps_json": json.dumps(["Lack of data query capabilities for Dragon and Tiger rankings"], ensure_ascii=False),
        "auto_continue_build": False,
        "confirm_external_data_risk": True,
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["summary"]["reused"] == 1
    assert payload["summary"]["generated"] == 0
    assert payload["results"][0]["status"] == "reused_existing"
    assert payload["results"][0]["skill_tool_id"] == "longhubang_query"


@pytest.mark.asyncio
async def test_resolve_agent_workshop_blocking_gaps_medium_similarity_needs_confirmation(monkeypatch):
    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_dedup_mid_001"
            return types.SimpleNamespace(
                spec_id="spec_dedup_mid_001",
                user_id="user_001",
                current_spec_snapshot=types.SimpleNamespace(name="Valuation Agent", primary_goal="Valuation output"),
                gap_report=types.SimpleNamespace(blocking_gaps=[]),
            )

    class _FakeCapabilityService:
        def __init__(self, db):
            self.db = db

        async def search_capabilities(self, query, top_k, bindable_only, source_types):
            del query, top_k, bindable_only, source_types
            return [
                CapabilitySearchHit(
                    capability=CapabilityDocument(
                        capability_id="external.skill.industry.compare",
                        registry_tool_id="industry_compare_skill",
                        source_type="external_skill",
                        bindable=True,
                        name="Industry comparison ability",
                    ),
                    score=0.72,
                )
            ]

    class _FakeSkillService:
        def __init__(self, db):
            self.db = db

        async def start_session(self, *args, **kwargs):
            raise AssertionError("medium similarity without explicit allow should not start generation session")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: object(),
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.CapabilityIndexService",
        _FakeCapabilityService,
    )
    monkeypatch.setattr(
        "app.services.skill_generation_service.SkillGenerationService",
        _FakeSkillService,
    )

    raw = await resolve_agent_workshop_blocking_gaps.ainvoke({
        "session_id": "ws_dedup_mid_001",
        "blocking_gaps_json": json.dumps(["Lack of industry comparison capabilities"], ensure_ascii=False),
        "auto_continue_build": False,
        "confirm_external_data_risk": True,
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["summary"]["needs_confirmation"] == 1
    assert payload["results"][0]["status"] == "needs_dedup_confirmation"


@pytest.mark.asyncio
async def test_resolve_agent_workshop_blocking_gaps_medium_similarity_can_autocreate_when_allowed(monkeypatch):
    fake_db = _FakeDb({
        "skill_creation_sessions": _NestedFakeCollection([
            {
                "session_id": "skill_session_allowed_001",
                "status": "completed",
                "pipeline_stage": "registering",
                "pipeline_message": "Complete",
                "spec": {"tool_id": "industry_compare_v2", "display_name": "Industry comparison ability V2"},
            }
        ])
    })

    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_dedup_mid_allow_001"
            return types.SimpleNamespace(
                spec_id="spec_dedup_mid_allow_001",
                user_id="user_001",
                current_spec_snapshot=types.SimpleNamespace(name="Valuation Agent", primary_goal="Valuation output"),
                gap_report=types.SimpleNamespace(blocking_gaps=[]),
            )

    class _FakeCapabilityService:
        def __init__(self, db):
            self.db = db

        async def search_capabilities(self, query, top_k, bindable_only, source_types):
            del query, top_k, bindable_only, source_types
            return [
                CapabilitySearchHit(
                    capability=CapabilityDocument(
                        capability_id="external.skill.industry.compare",
                        registry_tool_id="industry_compare_skill",
                        source_type="external_skill",
                        bindable=True,
                        name="Industry comparison ability",
                    ),
                    score=0.72,
                )
            ]

    class _FakeSkillService:
        def __init__(self, db):
            self.db = db

        async def start_session(self, *args, **kwargs):
            del args, kwargs
            return {"session_id": "skill_session_allowed_001"}

        async def respond_to_session(self, *args, **kwargs):
            del args, kwargs
            return {"status": "ok"}

        async def preview_spec(self, *args, **kwargs):
            del args, kwargs
            return {"preview": "ok"}

        async def confirm_spec(self, *args, **kwargs):
            del args, kwargs
            return {"status": "ok"}

    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.CapabilityIndexService",
        _FakeCapabilityService,
    )
    monkeypatch.setattr(
        "app.services.skill_generation_service.SkillGenerationService",
        _FakeSkillService,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.asyncio.sleep",
        _instant_sleep,
    )

    raw = await resolve_agent_workshop_blocking_gaps.ainvoke({
        "session_id": "ws_dedup_mid_allow_001",
        "blocking_gaps_json": json.dumps(["Lack of industry comparison capabilities"], ensure_ascii=False),
        "auto_continue_build": False,
        "confirm_external_data_risk": True,
        "allow_medium_similarity_autocreate": True,
        "max_wait_seconds": 60,
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["summary"]["generated"] == 1
    assert payload["summary"]["needs_confirmation"] == 0
    assert payload["results"][0]["status"] == "completed"
    assert payload["results"][0]["skill_tool_id"] == "industry_compare_v2"


@pytest.mark.asyncio
async def test_resolve_agent_workshop_blocking_gaps_auto_continue_builds_version(monkeypatch):
    fake_db = _FakeDb({
        "skill_creation_sessions": _FakeCollection([
            {
                "session_id": "skill_session_auto_001",
                "status": "completed",
                "pipeline_stage": "registering",
                "pipeline_message": "Complete",
                "spec": {"tool_id": "auto_gap_skill", "display_name": "Automatically complete skills"},
            }
        ])
    })

    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_auto_continue_001"
            return types.SimpleNamespace(
                spec_id="spec_auto_continue_001",
                user_id="user_001",
                current_spec_snapshot=types.SimpleNamespace(name="Automatic renewal Agent", primary_goal="Output structured research"),
                gap_report=types.SimpleNamespace(blocking_gaps=[]),
            )

        async def analyze_gaps(self, session_id):
            assert session_id == "ws_auto_continue_001"
            return {
                "session_id": session_id,
                "spec_id": "spec_auto_continue_001",
                "gap_report": {"blocking_gaps": []},
            }

        async def generate_tooling_plan(self, session_id):
            assert session_id == "ws_auto_continue_001"
            return {
                "session_id": session_id,
                "spec_id": "spec_auto_continue_001",
                "tooling_plan": {"missing_capabilities": []},
            }

        async def build_version(self, session_id):
            assert session_id == "ws_auto_continue_001"
            return {
                "session_id": session_id,
                "spec_id": "spec_auto_continue_001",
                "version": {
                    "version_id": "spec_auto_continue_001_v1",
                    "required_tools": ["auto_gap_skill"],
                    "required_capabilities": ["auto_gap_capability"],
                },
            }

    class _FakeCapabilityService:
        def __init__(self, db):
            self.db = db

        async def search_capabilities(self, query, top_k, bindable_only, source_types):
            del query, top_k, bindable_only, source_types
            return [
                CapabilitySearchHit(
                    capability=CapabilityDocument(
                        capability_id="external.skill.auto_gap_skill",
                        registry_tool_id="auto_gap_skill",
                        source_type="external_skill",
                        bindable=True,
                        name="Automatically complete skills",
                    ),
                    score=0.55,
                )
            ]

    class _FakeSkillService:
        def __init__(self, db):
            self.db = db

        async def start_session(self, *args, **kwargs):
            del args, kwargs
            return {"session_id": "skill_session_auto_001"}

        async def respond_to_session(self, *args, **kwargs):
            del args, kwargs
            return {"status": "ok"}

        async def preview_spec(self, *args, **kwargs):
            del args, kwargs
            return {"preview": "ok"}

        async def confirm_spec(self, *args, **kwargs):
            del args, kwargs
            return {"status": "ok"}

    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.CapabilityIndexService",
        _FakeCapabilityService,
    )
    monkeypatch.setattr(
        "app.services.skill_generation_service.SkillGenerationService",
        _FakeSkillService,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.asyncio.sleep",
        _instant_sleep,
    )

    raw = await resolve_agent_workshop_blocking_gaps.ainvoke({
        "session_id": "ws_auto_continue_001",
        "blocking_gaps_json": json.dumps(["Lack of auto-complete capabilities"], ensure_ascii=False),
        "confirm_external_data_risk": True,
        "auto_continue_build": True,
        "max_wait_seconds": 60,
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["summary"]["successful"] == 1
    assert payload["auto_continue"]["status"] == "completed"
    assert payload["auto_continue"]["build_version"]["version_id"] == "spec_auto_continue_001_v1"


@pytest.mark.asyncio
async def test_start_agent_workshop_gap_resolution_creates_job(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([]),
    })

    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_job_001"
            return types.SimpleNamespace(
                spec_id="spec_job_001",
                user_id="user_001",
                gap_report=types.SimpleNamespace(blocking_gaps=["Lack of industry comparison capabilities"]),
            )

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )

    raw = await start_agent_workshop_gap_resolution.ainvoke({"session_id": "ws_job_001"})
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["created"] is True
    assert payload["job"]["status"] == "pending"
    assert payload["job"]["summary"]["total"] == 1


@pytest.mark.asyncio
async def test_start_agent_workshop_gap_resolution_is_idempotent(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([]),
    })

    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_job_idempotent_001"
            return types.SimpleNamespace(
                spec_id="spec_job_idempotent_001",
                user_id="user_001",
                gap_report=types.SimpleNamespace(blocking_gaps=["Lack of industry comparison capabilities"]),
            )

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )

    first_raw = await start_agent_workshop_gap_resolution.ainvoke({"session_id": "ws_job_idempotent_001"})
    first_payload = json.loads(first_raw)
    assert first_payload["status"] == "ok"
    assert first_payload["created"] is True

    second_raw = await start_agent_workshop_gap_resolution.ainvoke({"session_id": "ws_job_idempotent_001"})
    second_payload = json.loads(second_raw)
    assert second_payload["status"] == "ok"
    assert second_payload["created"] is False
    assert second_payload["job"]["status"] == "pending"


@pytest.mark.asyncio
async def test_inspect_cancel_retry_gap_resolution_job(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([
            {
                "job_id": "gap_job_manual_001",
                "workshop_session_id": "ws_job_manual_001",
                "spec_id": "spec_job_manual_001",
                "status": "pending",
                "mode": "manual_confirmed",
                "idempotency_key": "idem001",
                "execution": {"runner": "worker_required", "state": "queued"},
                "gaps": [
                    {
                        "gap_id": "gap_1",
                        "description": "Lack of industry comparison capabilities",
                        "status": "failed",
                        "pipeline_stage": "validating",
                        "pipeline_message": "sandbox timeout",
                        "error": "timeout",
                        "retry_count": 0,
                    }
                ],
                "created_at": "2026-06-27T00:00:00",
                "updated_at": "2026-06-27T00:00:00",
            }
        ])
    })

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    inspect_raw = await inspect_agent_workshop_gap_resolution.ainvoke({"job_id": "gap_job_manual_001"})
    inspect_payload = json.loads(inspect_raw)
    assert inspect_payload["status"] == "ok"
    assert inspect_payload["job"]["summary"]["failed"] == 1

    retry_raw = await retry_agent_workshop_gap_resolution_item.ainvoke({
        "job_id": "gap_job_manual_001",
        "gap_id": "gap_1",
        "reason": "try again",
    })
    retry_payload = json.loads(retry_raw)
    assert retry_payload["status"] == "ok"
    assert retry_payload["gap"]["status"] == "pending"
    assert retry_payload["gap"]["retry_count"] == 1

    cancel_raw = await cancel_agent_workshop_gap_resolution.ainvoke({
        "job_id": "gap_job_manual_001",
        "reason": "user stopped",
    })
    cancel_payload = json.loads(cancel_raw)
    assert cancel_payload["status"] == "ok"
    assert cancel_payload["job"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_worker_process_gap_resolution_job_pending_to_running(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([
            {
                "job_id": "gap_job_worker_001",
                "workshop_session_id": "ws_job_worker_001",
                "spec_id": "spec_job_worker_001",
                "user_id": "user_worker_001",
                "status": "pending",
                "mode": "auto",
                "idempotency_key": "idem_worker_001",
                "execution": {"runner": "worker_required", "state": "queued"},
                "gaps": [
                    {
                        "gap_id": "gap_1",
                        "description": "Lack of industry comparison capabilities",
                        "status": "pending",
                        "pipeline_stage": "queued",
                        "pipeline_message": "Wait for worker execution",
                        "retry_count": 0,
                        "created_at": "2026-06-27T00:00:00",
                        "updated_at": "2026-06-27T00:00:00",
                    }
                ],
                "created_at": "2026-06-27T00:00:00",
                "updated_at": "2026-06-27T00:00:00",
            }
        ]),
        "skill_creation_sessions": _FakeCollection([]),
    })

    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_job_worker_001"
            return types.SimpleNamespace(
                spec_id="spec_job_worker_001",
                user_id="user_worker_001",
                current_spec_snapshot=types.SimpleNamespace(name="test Agent", primary_goal="Fill capability gaps"),
            )

    class _FakeCapabilityService:
        def __init__(self, db):
            self.db = db

        async def search_capabilities(self, query, top_k, bindable_only, source_types):
            del query, top_k, bindable_only, source_types
            return []

    class _FakeSkillService:
        def __init__(self, db):
            self.db = db

        async def start_session(self, *args, **kwargs):
            del args, kwargs
            return {"session_id": "skill_session_worker_001"}

        async def respond_to_session(self, *args, **kwargs):
            del args, kwargs
            return {"status": "ok"}

        async def preview_spec(self, *args, **kwargs):
            del args, kwargs
            return {"status": "ok"}

        async def confirm_spec(self, *args, **kwargs):
            del args, kwargs
            return {"status": "ok"}

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.CapabilityIndexService",
        _FakeCapabilityService,
    )
    monkeypatch.setattr(
        "app.services.skill_generation_service.SkillGenerationService",
        _FakeSkillService,
    )

    payload = await process_agent_workshop_gap_resolution_jobs_once(limit=1)
    assert payload["status"] == "ok"
    assert payload["processed"] == 1

    job_doc = fake_db["agent_workshop_gap_resolution_jobs"]._items[0]
    assert job_doc["status"] == "running"
    assert job_doc["execution"]["state"] == "running"
    assert job_doc["gaps"][0]["status"] == "running"
    assert job_doc["gaps"][0]["skill_session_id"] == "skill_session_worker_001"


@pytest.mark.asyncio
async def test_worker_process_gap_resolution_job_running_to_completed(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([
            {
                "job_id": "gap_job_worker_002",
                "workshop_session_id": "ws_job_worker_002",
                "spec_id": "spec_job_worker_002",
                "user_id": "user_worker_002",
                "status": "running",
                "mode": "auto",
                "idempotency_key": "idem_worker_002",
                "execution": {"runner": "worker_required", "state": "running"},
                "gaps": [
                    {
                        "gap_id": "gap_1",
                        "description": "Lack of industry comparison capabilities",
                        "status": "running",
                        "pipeline_stage": "generating",
                        "pipeline_message": "Wait for the build to complete",
                        "skill_session_id": "skill_session_worker_002",
                        "retry_count": 0,
                        "created_at": "2026-06-27T00:00:00",
                        "started_at": "2026-06-27T00:00:00",
                        "updated_at": "2026-06-27T00:00:00",
                    }
                ],
                "created_at": "2026-06-27T00:00:00",
                "updated_at": "2026-06-27T00:00:00",
            }
        ]),
        "skill_creation_sessions": _FakeCollection([
            {
                "session_id": "skill_session_worker_002",
                "status": "completed",
                "pipeline_stage": "completed",
                "pipeline_message": "Complete",
                "spec": {
                    "tool_id": "auto_gap_skill_worker_002",
                    "display_name": "Automatically complete skills#2",
                },
            }
        ]),
    })

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    payload = await process_agent_workshop_gap_resolution_jobs_once(limit=1)
    assert payload["status"] == "ok"
    assert payload["processed"] == 1

    job_doc = fake_db["agent_workshop_gap_resolution_jobs"]._items[0]
    assert job_doc["status"] == "completed"
    assert job_doc["execution"]["state"] == "completed"
    assert job_doc["gaps"][0]["status"] == "completed"
    assert job_doc["gaps"][0]["skill_tool_id"] == "auto_gap_skill_worker_002"


@pytest.mark.asyncio
async def test_worker_process_gap_resolution_job_skips_other_worker_claim(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([
            {
                "job_id": "gap_job_claim_001",
                "workshop_session_id": "ws_claim_001",
                "spec_id": "spec_claim_001",
                "user_id": "user_claim_001",
                "status": "pending",
                "mode": "auto",
                "idempotency_key": "idem_claim_001",
                "execution": {
                    "runner": "worker_required",
                    "state": "queued",
                    "claim": {
                        "owner": "worker-A",
                        "token": "token-A",
                        "expires_at": "2099-01-01T00:00:00",
                    },
                },
                "gaps": [
                    {
                        "gap_id": "gap_1",
                        "description": "Lack of industry comparison capabilities",
                        "status": "pending",
                        "pipeline_stage": "queued",
                        "pipeline_message": "Wait for worker execution",
                    }
                ],
                "created_at": "2026-06-27T00:00:00",
                "updated_at": "2026-06-27T00:00:00",
            }
        ]),
    })

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    payload = await process_agent_workshop_gap_resolution_jobs_once(limit=1, worker_id="worker-B")
    assert payload["status"] == "ok"
    assert payload["processed"] == 0
    assert payload["claim_skipped"] == 1


@pytest.mark.asyncio
async def test_gap_resolution_job_e2e_start_worker_and_inspect(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([]),
        "skill_creation_sessions": _FakeCollection([]),
    })

    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_e2e_001"
            return types.SimpleNamespace(
                spec_id="spec_e2e_001",
                user_id="user_e2e_001",
                gap_report=types.SimpleNamespace(blocking_gaps=["Lack of industry comparison capabilities"]),
                current_spec_snapshot=types.SimpleNamespace(name="test Agent", primary_goal="Fill capability gaps"),
            )

    class _FakeCapabilityService:
        def __init__(self, db):
            self.db = db

        async def search_capabilities(self, query, top_k, bindable_only, source_types):
            del query, top_k, bindable_only, source_types
            return []

    class _FakeSkillService:
        def __init__(self, db):
            self.db = db

        async def start_session(self, *args, **kwargs):
            del args, kwargs
            return {"session_id": "skill_session_e2e_001"}

        async def respond_to_session(self, *args, **kwargs):
            del args, kwargs
            return {"status": "ok"}

        async def preview_spec(self, *args, **kwargs):
            del args, kwargs
            return {"status": "ok"}

        async def confirm_spec(self, *args, **kwargs):
            del args, kwargs
            return {"status": "ok"}

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.CapabilityIndexService",
        _FakeCapabilityService,
    )
    monkeypatch.setattr(
        "app.services.skill_generation_service.SkillGenerationService",
        _FakeSkillService,
    )

    start_raw = await start_agent_workshop_gap_resolution.ainvoke({"session_id": "ws_e2e_001"})
    start_payload = json.loads(start_raw)
    assert start_payload["status"] == "ok"
    job_id = start_payload["job"]["job_id"]

    first_tick = await process_agent_workshop_gap_resolution_jobs_once(limit=1, worker_id="worker-e2e")
    assert first_tick["status"] == "ok"
    assert first_tick["processed"] == 1

    fake_db["skill_creation_sessions"]._items.append({
        "session_id": "skill_session_e2e_001",
        "status": "completed",
        "pipeline_stage": "completed",
        "pipeline_message": "Complete",
        "spec": {
            "tool_id": "auto_gap_skill_e2e_001",
            "display_name": "Automatically complete skills E2E",
        },
    })

    second_tick = await process_agent_workshop_gap_resolution_jobs_once(limit=1, worker_id="worker-e2e")
    assert second_tick["status"] == "ok"
    assert second_tick["processed"] == 1

    inspect_raw = await inspect_agent_workshop_gap_resolution.ainvoke({"job_id": job_id})
    inspect_payload = json.loads(inspect_raw)
    assert inspect_payload["status"] == "ok"
    assert inspect_payload["job"]["status"] == "completed"
    assert inspect_payload["job"]["summary"]["completed"] == 1
    assert inspect_payload["job"]["gaps"][0]["skill_tool_id"] == "auto_gap_skill_e2e_001"


@pytest.mark.asyncio
async def test_worker_auto_retry_backoff_for_failed_skill_session(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([
            {
                "job_id": "gap_job_retry_001",
                "workshop_session_id": "ws_retry_001",
                "spec_id": "spec_retry_001",
                "user_id": "user_retry_001",
                "status": "running",
                "mode": "auto",
                "idempotency_key": "idem_retry_001",
                "execution": {
                    "runner": "worker_required",
                    "state": "running",
                    "retry_policy": {
                        "max_attempts": 2,
                        "base_delay_seconds": 120,
                        "max_delay_seconds": 300,
                    },
                },
                "gaps": [
                    {
                        "gap_id": "gap_1",
                        "description": "Lack of industry comparison capabilities",
                        "status": "running",
                        "pipeline_stage": "generating",
                        "pipeline_message": "Wait for the build to complete",
                        "skill_session_id": "skill_session_retry_001",
                        "retry_count": 0,
                        "auto_retry_count": 0,
                        "created_at": "2026-06-27T00:00:00",
                        "started_at": "2026-06-27T00:00:00",
                        "updated_at": "2026-06-27T00:00:00",
                    }
                ],
                "created_at": "2026-06-27T00:00:00",
                "updated_at": "2026-06-27T00:00:00",
            }
        ]),
        "skill_creation_sessions": _FakeCollection([
            {
                "session_id": "skill_session_retry_001",
                "status": "failed",
                "pipeline_stage": "failed",
                "pipeline_message": "mock failed",
            }
        ]),
    })

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    first_tick = await process_agent_workshop_gap_resolution_jobs_once(limit=1, worker_id="worker-retry")
    assert first_tick["status"] == "ok"
    assert first_tick["processed"] == 1

    job_doc = fake_db["agent_workshop_gap_resolution_jobs"]._items[0]
    gap_doc = job_doc["gaps"][0]
    assert gap_doc["status"] == "pending"
    assert gap_doc["pipeline_stage"] == "retry_backoff"
    assert gap_doc["auto_retry_count"] == 1
    assert gap_doc["next_retry_at"]

    second_tick = await process_agent_workshop_gap_resolution_jobs_once(limit=1, worker_id="worker-retry")
    assert second_tick["status"] == "ok"
    assert second_tick["processed"] == 0


@pytest.mark.asyncio
async def test_worker_dead_letter_after_max_auto_retries(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([
            {
                "job_id": "gap_job_retry_002",
                "workshop_session_id": "ws_retry_002",
                "spec_id": "spec_retry_002",
                "user_id": "user_retry_002",
                "status": "running",
                "mode": "auto",
                "idempotency_key": "idem_retry_002",
                "execution": {
                    "runner": "worker_required",
                    "state": "running",
                    "retry_policy": {
                        "max_attempts": 2,
                        "base_delay_seconds": 30,
                        "max_delay_seconds": 300,
                    },
                },
                "gaps": [
                    {
                        "gap_id": "gap_1",
                        "description": "Lack of industry comparison capabilities",
                        "status": "running",
                        "pipeline_stage": "generating",
                        "pipeline_message": "Wait for the build to complete",
                        "skill_session_id": "skill_session_retry_002",
                        "retry_count": 0,
                        "auto_retry_count": 2,
                        "created_at": "2026-06-27T00:00:00",
                        "started_at": "2026-06-27T00:00:00",
                        "updated_at": "2026-06-27T00:00:00",
                    }
                ],
                "created_at": "2026-06-27T00:00:00",
                "updated_at": "2026-06-27T00:00:00",
            }
        ]),
        "skill_creation_sessions": _FakeCollection([
            {
                "session_id": "skill_session_retry_002",
                "status": "failed",
                "pipeline_stage": "failed",
                "pipeline_message": "mock failed final",
            }
        ]),
    })

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    tick = await process_agent_workshop_gap_resolution_jobs_once(limit=1, worker_id="worker-retry")
    assert tick["status"] == "ok"
    assert tick["processed"] == 1

    job_doc = fake_db["agent_workshop_gap_resolution_jobs"]._items[0]
    gap_doc = job_doc["gaps"][0]
    assert gap_doc["status"] == "failed"
    assert gap_doc["pipeline_stage"] == "dead_letter"
    assert gap_doc["dead_letter"]["reason_code"] == "skill_generation_failed"


@pytest.mark.asyncio
async def test_worker_reuses_active_skill_session_and_passes_rich_handoff(monkeypatch):
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([
            {
                "job_id": "gap_job_reuse_001",
                "workshop_session_id": "ws_reuse_001",
                "spec_id": "spec_reuse_001",
                "user_id": "user_reuse_001",
                "status": "pending",
                "mode": "auto",
                "idempotency_key": "idem_reuse_001",
                "execution": {"runner": "worker_required", "state": "queued"},
                "gaps": [
                    {
                        "gap_id": "gap_1",
                        "description": "Lack of industry comparison capabilities",
                        "status": "pending",
                        "pipeline_stage": "queued",
                        "pipeline_message": "Wait for worker execution",
                    }
                ],
            }
        ]),
        "skill_creation_sessions": _NestedFakeCollection([
            {
                "session_id": "skill_active_reuse_001",
                "status": "generating",
                "pipeline_stage": "agentic_loop",
                "handoff_context": {
                    "source": "agent_studio_gap",
                    "source_spec_id": "spec_reuse_001",
                    "workshop_session_id": "ws_reuse_001",
                    "gap_id": "gap_1",
                    "target_capability": "Lack of industry comparison capabilities",
                },
            }
        ]),
    })

    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_reuse_001"
            return types.SimpleNamespace(
                spec_id="spec_reuse_001",
                user_id="user_reuse_001",
                current_spec_snapshot=types.SimpleNamespace(name="test Agent", primary_goal="Fill capability gaps"),
            )

    class _FakeCapabilityService:
        def __init__(self, db):
            self.db = db

        async def search_capabilities(self, query, top_k, bindable_only, source_types):
            del query, top_k, bindable_only, source_types
            return []

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.CapabilityIndexService",
        _FakeCapabilityService,
    )

    payload = await process_agent_workshop_gap_resolution_jobs_once(limit=1)

    assert payload["status"] == "ok"
    gap_doc = fake_db["agent_workshop_gap_resolution_jobs"]._items[0]["gaps"][0]
    assert gap_doc["status"] == "running"
    assert gap_doc["skill_session_id"] == "skill_active_reuse_001"
    assert "Reuse" in gap_doc["pipeline_message"]


@pytest.mark.asyncio
async def test_worker_passes_known_context_and_rich_handoff_to_new_skill(monkeypatch):
    captured = {}
    fake_db = _FakeDb({
        "agent_workshop_gap_resolution_jobs": _FakeCollection([
            {
                "job_id": "gap_job_context_001",
                "workshop_session_id": "ws_context_001",
                "spec_id": "spec_context_001",
                "user_id": "user_context_001",
                "status": "pending",
                "mode": "auto",
                "idempotency_key": "idem_context_001",
                "execution": {"runner": "worker_required", "state": "queued"},
                "gaps": [
                    {
                        "gap_id": "gap_done",
                        "description": "Lack of valuation data capabilities",
                        "status": "failed",
                        "agentic_failure_summary": "pe_ttm Field does not exist",
                        "agentic_verified_facts": ["valuation helper Return pb_mrq"],
                    },
                    {
                        "gap_id": "gap_2",
                        "description": "Lack of industry comparison capabilities",
                        "status": "pending",
                        "pipeline_stage": "queued",
                        "pipeline_message": "Wait for worker execution",
                    },
                ],
            }
        ]),
        "skill_creation_sessions": _FakeCollection([]),
    })

    class _FakeWorkshopService:
        def __init__(self, db):
            self.db = db

        async def _load_session(self, session_id):
            assert session_id == "ws_context_001"
            return types.SimpleNamespace(
                spec_id="spec_context_001",
                user_id="user_context_001",
                current_spec_snapshot=types.SimpleNamespace(name="test Agent", primary_goal="Fill capability gaps"),
            )

    class _FakeCapabilityService:
        def __init__(self, db):
            self.db = db

        async def search_capabilities(self, query, top_k, bindable_only, source_types):
            del query, top_k, bindable_only, source_types
            return []

    class _FakeSkillService:
        def __init__(self, db):
            self.db = db

        async def start_session(self, *args, **kwargs):
            captured["handoff_context"] = kwargs.get("handoff_context")
            return {"session_id": "skill_session_context_001"}

        async def respond_to_session(self, *args, **kwargs):
            return {"status": "ok"}

        async def preview_spec(self, *args, **kwargs):
            return {"status": "ok"}

        async def confirm_spec(self, *args, **kwargs):
            return {"status": "ok"}

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentWorkshopService",
        _FakeWorkshopService,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.CapabilityIndexService",
        _FakeCapabilityService,
    )
    monkeypatch.setattr(
        "app.services.skill_generation_service.SkillGenerationService",
        _FakeSkillService,
    )

    payload = await process_agent_workshop_gap_resolution_jobs_once(limit=1)

    assert payload["status"] == "ok"
    handoff = captured["handoff_context"]
    assert handoff["known_failure_summaries"]
    assert handoff["known_verified_facts"] == ["valuation helper Return pb_mrq"]
    assert handoff["gap_context"]
    assert "Lack of valuation data capabilities" in handoff["related_gaps"]
    assert handoff["searched_capabilities"]


@pytest.mark.asyncio
async def test_create_or_update_universal_agent_prompt_template_writes_template(monkeypatch):
    fake_db = _FakeDb({
        "prompt_templates": _FakeCollection([]),
        "agent_configs": _FakeCollection([{"agent_id": "valuation_candidate_v1", "metadata": {}}]),
    })
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    raw = await create_or_update_universal_agent_prompt_template.ainvoke({
        "agent_id": "valuation_candidate_v1",
        "template_name": "Valuation candidate template",
        "system_prompt": "You are an A-share valuation analyst.",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["template"]["agent_type"] == "universal"
    assert payload["template"]["agent_name"] == "valuation_candidate_v1"
    template_doc = fake_db["prompt_templates"]._items[0]
    assert "Global iron law: All Agents are prohibited from outputting any trading suggestions." in template_doc["content"]["system_prompt"]
    assert "Global iron law: All Agents are prohibited from outputting any trading suggestions." in template_doc["content"]["constraints"]
    agent_config = fake_db["agent_configs"]._items[0]
    assert agent_config["metadata"]["default_prompt_template_id"]


@pytest.mark.asyncio
async def test_inspect_prompt_templates_reads_database_templates(monkeypatch):
    fake_db = _FakeDb({
        "prompt_templates": _FakeCollection([
            {
                "_id": "tpl_001",
                "agent_type": "universal",
                "agent_name": "valuation_candidate_v1",
                "template_name": "Valuation candidate template",
                "workflow_id": None,
                "node_id": None,
                "status": "active",
                "is_system": True,
                "remark": "nanobot generated candidate template",
                "content": {"system_prompt": "You are a valuation analyst"},
                "updated_at": "2026-04-02T10:00:00",
                "version": 2,
            },
            {
                "_id": "tpl_002",
                "agent_type": "researcher",
                "agent_name": "news_researcher",
                "template_name": "News Research Template",
                "status": "draft",
                "is_system": False,
                "remark": "internal",
                "content": {"system_prompt": "research news"},
                "updated_at": "2026-04-01T10:00:00",
                "version": 1,
            },
        ])
    })
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    raw = await inspect_prompt_templates.ainvoke({
        "agent_type": "universal",
        "keyword": "Valuation",
        "status": "active",
        "limit": 10,
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["templates"][0]["template_id"] == "tpl_001"
    assert payload["templates"][0]["template_name"] == "Valuation candidate template"


@pytest.mark.asyncio
async def test_get_prompt_template_detail_returns_full_content(monkeypatch):
    fake_db = _FakeDb({
        "prompt_templates": _FakeCollection([
            {
                "_id": "tpl_001",
                "agent_type": "universal",
                "agent_name": "valuation_candidate_v1",
                "template_name": "Valuation candidate template",
                "workflow_id": None,
                "node_id": None,
                "status": "active",
                "is_system": True,
                "remark": "nanobot generated candidate template",
                "preference_type": None,
                "content": {
                    "system_prompt": "You are a valuation analyst.",
                    "user_prompt": "Please analyze {ticker}",
                    "tool_guidance": "Prioritize real data tools",
                    "analysis_requirements": "Give key evidence",
                    "output_format": "Structured output",
                    "constraints": "Do not output trading advice",
                },
                "created_at": "2026-04-02T09:00:00",
                "updated_at": "2026-04-02T10:00:00",
                "version": 2,
            }
        ])
    })
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )

    raw = await get_prompt_template_detail.ainvoke({"template_id": "tpl_001"})
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["template"]["template_id"] == "tpl_001"
    assert payload["template"]["content"]["system_prompt"] == "You are a valuation analyst."
    assert payload["template"]["content"]["output_format"] == "Structured output"


@pytest.mark.asyncio
async def test_get_effective_prompt_template_uses_template_client_resolution(monkeypatch):
    captured = {}

    class _FakeTemplateClient:
        def get_effective_template(self, agent_type, agent_name, user_id=None, preference_id=None, context=None, workflow_id=None, node_id=None):
            captured["agent_type"] = agent_type
            captured["agent_name"] = agent_name
            captured["user_id"] = user_id
            captured["preference_id"] = preference_id
            captured["context"] = dict(context or {})
            captured["workflow_id"] = workflow_id
            captured["node_id"] = node_id
            return {
                "template_id": "tpl_debug_001",
                "source": "debug",
                "version": 3,
                "system_prompt": "Current debug template system prompt",
            }

    fake_template_client_module = types.SimpleNamespace(get_template_client=lambda: _FakeTemplateClient())
    monkeypatch.setitem(sys.modules, "tradingagents.utils.template_client", fake_template_client_module)
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.require_current_user_id",
        lambda: "user_001",
    )

    raw = await get_effective_prompt_template.ainvoke({
        "agent_type": "universal",
        "agent_name": "valuation_candidate_v1",
        "preference_id": "neutral",
        "workflow_id": "workflow_debug_001",
        "node_id": "node_prompt_001",
        "is_debug_mode": True,
        "debug_template_id": "69cfdf8db1828a17f6b00cfb",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["template"]["template_id"] == "tpl_debug_001"
    assert payload["template"]["source"] == "debug"
    assert captured["agent_type"] == "universal"
    assert captured["agent_name"] == "valuation_candidate_v1"
    assert captured["user_id"] == "user_001"
    assert captured["preference_id"] == "neutral"
    assert captured["workflow_id"] == "workflow_debug_001"
    assert captured["node_id"] == "node_prompt_001"
    assert captured["context"]["is_debug_mode"] is True
    assert captured["context"]["debug_template_id"] == "69cfdf8db1828a17f6b00cfb"


@pytest.mark.asyncio
async def test_get_current_thread_effective_prompt_template_uses_thread_context(monkeypatch):
    captured = {}

    class _FakeTemplateClient:
        def get_effective_template(self, agent_type, agent_name, user_id=None, preference_id=None, context=None, workflow_id=None, node_id=None):
            captured["agent_type"] = agent_type
            captured["agent_name"] = agent_name
            captured["user_id"] = user_id
            captured["preference_id"] = preference_id
            captured["context"] = dict(context or {})
            captured["workflow_id"] = workflow_id
            captured["node_id"] = node_id
            return {
                "template_id": "tpl_debug_thread_001",
                "source": "debug",
                "version": 5,
                "system_prompt": "Current thread debugging template system prompt",
            }

    fake_db = _FakeDb({
        "embedded_nanobot_threads": _FakeCollection([
            {
                "thread_id": "thread_001",
                "session_key": "thread_001",
                "user_id": "user_001",
                "channel": "agent_workshop",
                "thread_context": {
                    "spec_id": "spec_001",
                    "version_id": "spec_001_v2",
                    "version_status": "testing",
                    "workflow_id": "agent_workshop_debug_from_thread_context",
                    "node_id": "prompt_node_from_thread_context",
                    "preference_id": "growth",
                    "debug_template_id": "tpl_explicit_debug_from_thread_context",
                },
            }
        ]),
        "agent_versions": _FakeCollection([
            {
                "version_id": "spec_001_v2",
                "prompt_template_ref": {
                    "template_id": "tpl_debug_thread_001",
                },
            }
        ]),
        "agent_specs": _FakeCollection([]),
    })
    fake_template_client_module = types.SimpleNamespace(get_template_client=lambda: _FakeTemplateClient())
    monkeypatch.setitem(sys.modules, "tradingagents.utils.template_client", fake_template_client_module)
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.require_current_user_id",
        lambda: "user_001",
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_current_assistant_thread_id",
        lambda: "thread_001",
    )

    raw = await get_current_thread_effective_prompt_template.ainvoke({})
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["thread_id"] == "thread_001"
    assert payload["resolution_input"]["agent_type"] == "universal"
    assert payload["resolution_input"]["agent_name"] == "spec_001_v2"
    assert payload["resolution_input"]["is_debug_mode"] is True
    assert payload["resolution_input"]["debug_template_id"] == "tpl_explicit_debug_from_thread_context"
    assert payload["resolution_input"]["workflow_id"] == "agent_workshop_debug_from_thread_context"
    assert payload["resolution_input"]["node_id"] == "prompt_node_from_thread_context"
    assert payload["resolution_input"]["preference_id"] == "growth"
    assert payload["template"]["template_id"] == "tpl_debug_thread_001"
    assert captured["agent_type"] == "universal"
    assert captured["agent_name"] == "spec_001_v2"
    assert captured["workflow_id"] == "agent_workshop_debug_from_thread_context"
    assert captured["node_id"] == "prompt_node_from_thread_context"
    assert captured["preference_id"] == "growth"
    assert captured["context"]["debug_template_id"] == "tpl_explicit_debug_from_thread_context"
    assert payload["resolution_source"]["used_explicit_workflow_id"] is True
    assert payload["resolution_source"]["used_explicit_node_id"] is True
    assert payload["resolution_source"]["used_explicit_preference_id"] is True
    assert payload["resolution_source"]["used_explicit_debug_template_id"] is True


@pytest.mark.asyncio
async def test_bind_agent_tools_and_validate_candidate_updates_bindings_and_runs_dry_run(monkeypatch):
    fake_db = _FakeDb({
        "tool_agent_bindings": _FakeCollection([]),
        "agent_configs": _FakeCollection([
            {
                "agent_id": "valuation_candidate_v1",
                "name": "Valuation candidates Agent",
                "description": "Output A-share valuation conclusion",
                "metadata": {
                    "spec_id": "spec_valuation_001",
                    "latest_workshop_version_id": "ver_valuation_002",
                },
            }
        ]),
        "agent_specs": _FakeCollection([
            {
                "spec_id": "spec_valuation_001",
                "current_version_id": "ver_valuation_002",
            }
        ]),
        "agent_versions": _FakeCollection([
            {
                "version_id": "ver_valuation_002",
                "spec_id": "spec_valuation_001",
                "status": "testing",
                "required_tools": ["get_old_tool"],
                "agent_metadata": {
                    "tools": ["get_old_tool"],
                    "default_tools": ["get_old_tool"],
                },
            }
        ]),
        "prompt_templates": _FakeCollection([
            {
                "_id": "tpl_001",
                "agent_type": "universal",
                "agent_name": "valuation_candidate_v1",
                "template_name": "Valuation candidate template",
                "workflow_id": None,
                "node_id": None,
                "status": "active",
                "content": {"system_prompt": "x"},
                "updated_at": "2026-04-02T10:00:00",
                "version": 1,
            }
        ]),
    })

    class _FakeFactory:
        def create_with_dynamic_tools(self, agent_id, llm=None):
            return type(
                "FakeAgent",
                (),
                {
                    "agent_id": agent_id,
                    "_langchain_tools": [type("Tool", (), {"name": "get_value_factor_bundle_tool"})()],
                    "_output_field": "analysis_report",
                },
            )()

    class _FakeBindingManager:
        def set_database(self, db):
            self.db = db

    class _FakeToolRegistry:
        def get(self, tool_id):
            if tool_id == "get_value_factor_bundle_tool":
                return object()
            return None

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db_sync",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentFactory",
        _FakeFactory,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.BindingManager",
        _FakeBindingManager,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_tool_registry",
        lambda: _FakeToolRegistry(),
    )

    raw = await bind_agent_tools_and_validate_candidate.ainvoke({
        "agent_id": "valuation_candidate_v1",
        "tool_ids": "get_value_factor_bundle_tool",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["bound_tools"] == ["get_value_factor_bundle_tool"]
    assert payload["workshop_sync"]["synced_version_ids"] == ["ver_valuation_002"]
    assert payload["validation"]["prompt_template_found"] is True
    assert payload["validation"]["dry_run"]["instantiated"] is True
    version_doc = fake_db["agent_versions"]._items[0]
    assert version_doc["required_tools"] == ["get_value_factor_bundle_tool"]
    assert version_doc["agent_metadata"]["tools"] == ["get_value_factor_bundle_tool"]
    assert version_doc["agent_metadata"]["default_tools"] == ["get_value_factor_bundle_tool"]


def test_universal_agent_testing_mode_maps_to_template_debug_mode(monkeypatch):
    captured = []

    class _FakeLlm:
        def invoke(self, _messages):
            return type("Response", (), {"content": "ok"})()

    def _fake_get_prompt(self, agent_type, agent_name, variables, context=None, **kwargs):
        captured.append({
            "agent_type": agent_type,
            "agent_name": agent_name,
            "context": dict(context or {}),
            "variables": dict(variables or {}),
            "kwargs": kwargs,
        })
        return "prompt-body"

    monkeypatch.setattr(UniversalAgent, "_get_prompt_from_template", _fake_get_prompt)

    agent = UniversalAgent(
        llm=_FakeLlm(),
        tool_ids=[],
        agent_id="spec_nanobot_financial_report_risk_tracker_v2_v1",
        agent_name="Financial Reporting Risk Tracking Assistant v2",
        agent_description="Test instructions",
        output_field="risk_report",
        prompt_template_type="custom_agent",
        prompt_template_name="spec_nanobot_financial_report_risk_tracker_v2_v1",
        prompt_template_id="tpl_debug_001",
        prompt_template_status="draft",
        version_status="testing",
    )

    result = agent.execute({
        "stock_symbol": "600519",
        "ticker": "600519",
        "analysis_date": "2026-04-06",
        "workflow_id": "agent_workshop_debug_spec_nanobot_financial_report_risk_tracker_v2_v1",
        "context": {
            "user_id": "user_001",
            "preference_id": "neutral",
        },
    })

    assert result["risk_report"] == "ok"
    assert len(captured) == 2
    assert captured[0]["agent_type"] == "universal"
    assert captured[0]["agent_name"] == "spec_nanobot_financial_report_risk_tracker_v2_v1"
    assert captured[0]["context"]["is_debug_mode"] is True
    assert captured[0]["context"]["debug_template_id"] == "tpl_debug_001"
    assert captured[0]["context"]["workflow_id"] == "agent_workshop_debug_spec_nanobot_financial_report_risk_tracker_v2_v1"


@pytest.mark.asyncio
async def test_bind_agent_tools_and_validate_candidate_skips_active_workshop_version(monkeypatch):
    fake_db = _FakeDb({
        "tool_agent_bindings": _FakeCollection([]),
        "agent_configs": _FakeCollection([
            {
                "agent_id": "valuation_candidate_v1",
                "name": "Valuation candidates Agent",
                "description": "Output A-share valuation conclusion",
                "metadata": {
                    "latest_workshop_version_id": "ver_active_001",
                },
            }
        ]),
        "agent_versions": _FakeCollection([
            {
                "version_id": "ver_active_001",
                "status": "active",
                "required_tools": ["get_old_tool"],
                "agent_metadata": {
                    "tools": ["get_old_tool"],
                    "default_tools": ["get_old_tool"],
                },
            }
        ]),
        "prompt_templates": _FakeCollection([]),
    })

    class _FakeFactory:
        def create_with_dynamic_tools(self, agent_id, llm=None):
            return type("FakeAgent", (), {"agent_id": agent_id, "_langchain_tools": [], "_output_field": "analysis_report"})()

    class _FakeBindingManager:
        def set_database(self, db):
            self.db = db

    class _FakeToolRegistry:
        def get(self, tool_id):
            return object() if tool_id == "get_value_factor_bundle_tool" else None

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db_sync",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentFactory",
        _FakeFactory,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.BindingManager",
        _FakeBindingManager,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_tool_registry",
        lambda: _FakeToolRegistry(),
    )

    raw = await bind_agent_tools_and_validate_candidate.ainvoke({
        "agent_id": "valuation_candidate_v1",
        "tool_ids": "get_value_factor_bundle_tool",
        "validate_runtime": False,
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["workshop_sync"]["synced_version_ids"] == []
    assert payload["workshop_sync"]["skipped"] == [{"version_id": "ver_active_001", "reason": "version_active"}]
    version_doc = fake_db["agent_versions"]._items[0]
    assert version_doc["required_tools"] == ["get_old_tool"]


@pytest.mark.asyncio
async def test_prepare_agent_generation_confirmation_reports_overwrite_risk(monkeypatch):
    fake_db = _FakeDb({
        "agent_configs": _FakeCollection([
            {"agent_id": "valuation_candidate_v1", "name": "Valuation already exists Agent"}
        ]),
        "prompt_templates": _FakeCollection([
            {
                "_id": "tpl_001",
                "agent_type": "universal",
                "agent_name": "valuation_candidate_v1",
                "workflow_id": None,
                "node_id": None,
                "status": "active",
            }
        ]),
        "tool_agent_bindings": _FakeCollection([
            {"agent_id": "valuation_candidate_v1", "tool_id": "get_value_factor_bundle_tool", "is_active": True}
        ]),
    })

    class _FakeToolRegistry:
        def get(self, tool_id):
            return object() if tool_id == "get_value_factor_bundle_tool" else None

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_tool_registry",
        lambda: _FakeToolRegistry(),
    )

    raw = await prepare_agent_generation_confirmation.ainvoke({
        "agent_id": "valuation_candidate_v1",
        "agent_name": "Valuation candidates Agent",
        "target_responsibility": "Output A-share valuation conclusion",
        "tool_ids": "get_value_factor_bundle_tool",
        "non_goals": "No trading advice,Not making position decisions",
        "valuation_method_scope": "Only PE/PB/PEG and relative valuation",
        "test_strategy": "Only perform configuration verification, do not run real stock samples",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["confirmation_required"] is True
    assert payload["confirmation_brief"]["overwrite_risk"]["requires_explicit_overwrite"] is True
    assert "Global iron law: All Agents are prohibited from outputting any trading suggestions." in payload["confirmation_brief"]["recommendation_policy"]


@pytest.mark.asyncio
async def test_generate_confirmed_candidate_agent_rejects_without_confirmation():
    raw = await generate_confirmed_candidate_agent.ainvoke({
        "agent_id": "valuation_candidate_v1",
        "agent_name": "Valuation candidates Agent",
        "target_responsibility": "Output A-share valuation conclusion",
        "tool_ids": "get_value_factor_bundle_tool",
        "system_prompt": "You are a valuation analyst.",
        "confirmed": False,
    })
    payload = json.loads(raw)

    assert payload["status"] == "error"
    assert "No explicit confirmation from the user has been obtained" in payload["message"]


@pytest.mark.asyncio
async def test_generate_confirmed_candidate_agent_runs_one_shot_after_confirmation(monkeypatch):
    fake_db = _FakeDb({
        "agent_configs": _FakeCollection([]),
        "prompt_templates": _FakeCollection([]),
        "tool_agent_bindings": _FakeCollection([]),
        "agent_specs": _FakeCollection([]),
        "agent_workshop_sessions": _FakeCollection([]),
    })

    class _FakeFactory:
        def create_with_dynamic_tools(self, agent_id, llm=None):
            return type(
                "FakeAgent",
                (),
                {
                    "agent_id": agent_id,
                    "_langchain_tools": [type("Tool", (), {"name": "get_value_factor_bundle_tool"})()],
                    "_output_field": "valuation_report",
                },
            )()

    class _FakeBindingManager:
        def set_database(self, db):
            self.db = db

    class _FakeToolRegistry:
        def get(self, tool_id):
            if tool_id == "get_value_factor_bundle_tool":
                return object()
            return None

    async def _fake_build_version(_session_id):
        return {
            "status": "ok",
            "session_id": "fake_session_001",
            "spec_id": "spec_nanobot_valuation_candidate_v1",
            "version": {
                "version_id": "spec_nanobot_valuation_candidate_v1_v1",
                "spec_id": "spec_nanobot_valuation_candidate_v1",
                "version": 1,
                "status": "draft",
            },
        }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db_sync",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.AgentFactory",
        _FakeFactory,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.BindingManager",
        _FakeBindingManager,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_tool_registry",
        lambda: _FakeToolRegistry(),
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.require_current_user_id",
        lambda: "user_001",
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_current_assistant_thread_id",
        lambda: "thread_valuation",
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools._auto_build_workshop_version_result",
        _fake_build_version,
    )

    raw = await generate_confirmed_candidate_agent.ainvoke({
        "agent_id": "valuation_candidate_v1",
        "agent_name": "Valuation candidates Agent",
        "target_responsibility": "Output A-share valuation conclusion",
        "tool_ids": "get_value_factor_bundle_tool",
        "system_prompt": "You are a valuation analyst.",
        "output_field": "valuation_report",
        "confirmed": True,
        "allow_overwrite": False,
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["steps"]["workshop_draft"]["status"] == "ok"
    assert payload["steps"]["agent_config"]["status"] == "ok"
    assert payload["steps"]["prompt_template"]["status"] == "ok"
    assert payload["steps"]["bindings_and_validation"]["validation"]["dry_run"]["instantiated"] is True
    assert payload["steps"]["workshop_version"]["status"] == "ok"
    assert payload["governance_boundary"]["runtime_candidate_validation"]["dry_run_instantiated"] is True
    assert payload["governance_boundary"]["workshop_governance"]["version_generated"] is True
    assert payload["governance_boundary"]["workshop_governance"]["version_id"] == "spec_nanobot_valuation_candidate_v1_v1"
    assert payload["governance_boundary"]["workshop_governance"]["official_acceptance_status"] == "not_started"
    assert "Sample" in payload["governance_boundary"]["warnings"][1]
    saved_agent = fake_db["agent_configs"]._items[0]
    assert saved_agent["metadata"]["spec_id"] == "agent_valuation_candidate"
    assert saved_agent["metadata"]["session_id"]
    assert saved_agent["metadata"]["linked_agent_workshop"] is True
    assert saved_agent["metadata"]["latest_workshop_version_id"] == "spec_nanobot_valuation_candidate_v1_v1"


def test_prepare_agent_requirement_intake_returns_follow_up_questions_for_vague_request():
    raw = prepare_agent_requirement_intake.invoke({
        "user_request": "Help me do a valuation analysis agent",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["can_proceed_to_confirmation"] is False
    assert [item["id"] for item in payload["critical_questions"]] == ["single_responsibility"]
    assert payload["proposed_plan"]["output_shape"]
    assert payload["proposed_plan"]["valuation_method_scope"]
    assert payload["proposed_plan"]["test_strategy"] == "auto_test"
    assert payload["recommended_next_step"] == "present_proposed_plan_and_ask_critical_questions"


def test_prepare_agent_requirement_intake_detects_style_preview_scope_questions():
    raw = prepare_agent_requirement_intake.invoke({
        "user_request": "What is the reporting style of the valuation analysis agent?",
        "target_responsibility": "Output A-share valuation conclusion",
        "desired_output_shape": "Valuation report style preview",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["request_profile"]["output_preview_request"] is True
    assert [item["id"] for item in payload["critical_questions"]] == ["tool_preferences"]
    assert payload["proposed_plan"]["preview_mode"] == "structure_only"
    assert payload["proposed_plan"]["report_section_scope"]
    assert payload["can_proceed_to_confirmation"] is False


@pytest.mark.asyncio
async def test_prepare_agent_generation_confirmation_blocks_stock_agent_when_intake_incomplete(monkeypatch):
    fake_db = _FakeDb({
        "agent_configs": _FakeCollection([]),
        "prompt_templates": _FakeCollection([]),
        "tool_agent_bindings": _FakeCollection([]),
    })

    class _FakeToolRegistry:
        def get(self, tool_id):
            return object() if tool_id == "get_value_factor_bundle_tool" else None

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_tool_registry",
        lambda: _FakeToolRegistry(),
    )

    raw = await prepare_agent_generation_confirmation.ainvoke({
        "agent_id": "valuation_candidate_v1",
        "agent_name": "Valuation candidates Agent",
        "target_responsibility": "Output A-share valuation conclusion",
        "tool_ids": "get_value_factor_bundle_tool",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["confirmation_brief"]["valuation_method_scope"]
    assert payload["confirmation_brief"]["test_strategy"] == "auto_test"
    assert payload["confirmation_required"] is True


@pytest.mark.asyncio
async def test_prepare_agent_generation_confirmation_blocks_style_preview_when_scope_unspecified(monkeypatch):
    fake_db = _FakeDb({
        "agent_configs": _FakeCollection([]),
        "prompt_templates": _FakeCollection([]),
        "tool_agent_bindings": _FakeCollection([]),
    })

    class _FakeToolRegistry:
        def get(self, tool_id):
            return object() if tool_id == "get_value_factor_bundle_tool" else None

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_tool_registry",
        lambda: _FakeToolRegistry(),
    )

    raw = await prepare_agent_generation_confirmation.ainvoke({
        "agent_id": "valuation_candidate_v1",
        "agent_name": "Valuation candidates Agent",
        "target_responsibility": "Output A-share valuation conclusion",
        "tool_ids": "get_value_factor_bundle_tool",
        "desired_output_shape": "Valuation report style preview",
        "non_goals": "No trading advice,Not making position decisions",
        "valuation_method_scope": "Only PE/PB/PEG and relative valuation",
        "test_strategy": "Only perform configuration verification, do not run real stock samples",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["confirmation_brief"]["preview_mode"] == "structure_only"
    assert payload["confirmation_brief"]["report_section_scope"]
    assert payload["confirmation_brief"]["report_contract"]["content_scope"]


@pytest.mark.asyncio
async def test_prepare_agent_generation_confirmation_does_not_treat_structured_report_as_preview(monkeypatch):
    fake_db = _FakeDb({
        "agent_configs": _FakeCollection([]),
        "prompt_templates": _FakeCollection([]),
        "tool_agent_bindings": _FakeCollection([]),
    })

    class _FakeToolRegistry:
        def get(self, tool_id):
            return object() if tool_id == "get_value_factor_bundle_tool" else None

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_tool_registry",
        lambda: _FakeToolRegistry(),
    )

    raw = await prepare_agent_generation_confirmation.ainvoke({
        "agent_id": "valuation_candidate_v2",
        "agent_name": "Valuation candidates Agent",
        "target_responsibility": "Output A-share valuation conclusion",
        "tool_ids": "get_value_factor_bundle_tool",
        "desired_output_shape": "Structured Valuation Report",
        "non_goals": "No trading advice,Not making position decisions",
        "valuation_method_scope": "Only PE/PB/PEG and relative valuation",
        "test_strategy": "Only perform configuration verification, do not run real stock samples",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["confirmation_brief"]["report_contract"]["style_preview_mode"] == "structure_skeleton"
    assert "Only chapters related to currently confirmed responsibilities" in payload["confirmation_brief"]["report_contract"]["content_scope"]
    assert payload["confirmation_brief"]["report_contract_display"]["style_preview_mode"] == "Just look at the structural skeleton"
    assert "If the above content is confirmed to be correct, please reply: Confirm" in payload["confirmation_brief"]["user_confirmation_template"]
    assert "Report content boundaries" in payload["confirmation_brief"]["user_confirmation_template"]


@pytest.mark.asyncio
async def test_debug_agent_workshop_version_calls_service(monkeypatch):
    fake_db = _FakeDb({})

    async def _fake_get_reasoning_llm_config(db=None):
        del db
        return type(
            "FakeLLMConfig",
            (),
            {
                "provider": "dashscope",
                "model_name": "qwen-max",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "fake-api-key",
                "temperature": 0.2,
                "max_tokens": 4000,
            },
        )()

    async def _fake_debug_version(self, version_id, llm, stock, user_goal="", prompt_overrides=None):
        del self
        assert llm["provider"] == "dashscope"
        assert llm["model"] == "qwen-max"
        return {
            "version_id": version_id,
            "spec_id": "spec_financial_risk_v1",
            "symbol": stock["symbol"],
            "analysis_date": stock.get("analysis_date") or "2026-04-03",
            "report": "risk report",
            "report_length": 11,
            "raw_result": {"ok": True},
            "debug_prompt": {"llm_final_response": "risk report"},
            "template": {"template_id": "tpl_001"},
            "metadata": {"required_tools": ["get_quality_factor_bundle_tool"]},
            "llm": llm,
            "user_goal": user_goal,
            "prompt_overrides": prompt_overrides or {},
        }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.debug_version",
        _fake_debug_version,
    )
    monkeypatch.setattr(
        "app.services.intelligent_assistant_service.get_reasoning_llm_config",
        _fake_get_reasoning_llm_config,
    )

    raw = await debug_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
        "stock_symbol": "600519",
        "analysis_date": "2026-04-03",
        "prompt_overrides_json": '{"tone":"strict"}',
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["version_id"] == "spec_financial_risk_v1_v2"
    assert payload["summary"]["symbol"] == "600519"
    assert payload["debug_prompt"]["llm_final_response"] == "risk report"


@pytest.mark.asyncio
async def test_debug_agent_workshop_version_uses_default_reasoning_llm_when_not_provided(monkeypatch):
    fake_db = _FakeDb({})

    async def _fake_get_reasoning_llm_config(db=None):
        del db
        return CoreLLMConfig(
            provider=LLMProvider.DASHSCOPE,
            model="qwen-max",
            api_key="fake-api-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0.15,
            max_tokens=6000,
            timeout=180,
            retry_times=3,
        )

    async def _fake_debug_version(self, version_id, llm, stock, user_goal="", prompt_overrides=None):
        del self, user_goal, prompt_overrides
        assert llm["provider"] == "dashscope"
        assert llm["model"] == "qwen-max"
        assert llm["backend_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert llm["api_key"] == "fake-api-key"
        assert llm["temperature"] == 0.15
        assert llm["max_tokens"] == 6000
        return {
            "version_id": version_id,
            "spec_id": "spec_financial_risk_v1",
            "symbol": stock["symbol"],
            "analysis_date": stock.get("analysis_date") or "2026-04-03",
            "report": "risk report",
            "report_length": 11,
            "raw_result": {"ok": True},
            "debug_prompt": {"llm_final_response": "risk report"},
            "template": {"template_id": "tpl_001"},
            "metadata": {"required_tools": ["get_quality_factor_bundle_tool"]},
        }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.debug_version",
        _fake_debug_version,
    )
    monkeypatch.setattr(
        "app.services.intelligent_assistant_service.get_reasoning_llm_config",
        _fake_get_reasoning_llm_config,
    )

    raw = await debug_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
        "stock_symbol": "600519",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["summary"]["symbol"] == "600519"


@pytest.mark.asyncio
async def test_debug_agent_workshop_version_blocks_non_testing_version(monkeypatch):
    fake_db = _FakeDb({
        "agent_versions": _FakeCollection([{
            "version_id": "spec_financial_risk_v1_v1",
            "spec_id": "spec_financial_risk_v1",
            "status": "draft",
        }]),
        "agent_evaluations": _FakeCollection([]),
    })

    async def _fake_get_reasoning_llm_config(db=None):
        del db
        raise AssertionError("default llm resolution should not be called for non-testing version")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.intelligent_assistant_service.get_reasoning_llm_config",
        _fake_get_reasoning_llm_config,
    )

    raw = await debug_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v1",
        "stock_symbol": "600519",
    })
    payload = json.loads(raw)

    assert payload["status"] == "blocked"
    assert payload["blocked_by"] == "phase_guard"
    assert payload["blocked_code"] == "version_not_testing"
    assert payload["current_phase"] == "generation"
    assert payload["version_id"] == "spec_financial_risk_v1_v1"
    assert payload["_tool_events"][0]["name"] == "debug_agent_workshop_version.phase_guard"


@pytest.mark.asyncio
async def test_run_agent_workshop_real_data_test_records_evaluation(monkeypatch):
    fake_db = _FakeDb({})

    async def _fake_get_reasoning_llm_config(db=None):
        del db
        return CoreLLMConfig(
            provider=LLMProvider.DASHSCOPE,
            model="qwen-max",
            api_key="fake-api-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0.2,
            max_tokens=4000,
            timeout=180,
            retry_times=3,
        )

    async def _fake_debug_version(self, version_id, llm, stock, user_goal="", prompt_overrides=None):
        del self, user_goal, prompt_overrides
        assert llm["provider"] == "dashscope"
        assert llm["model"] == "qwen-max"
        return {
            "version_id": version_id,
            "spec_id": "spec_financial_risk_v1",
            "symbol": stock["symbol"],
            "analysis_date": stock.get("analysis_date") or "2026-04-03",
            "report": "final report",
            "report_length": 12,
            "raw_result": {"tool_trace": []},
            "debug_prompt": {"llm_final_response": "final report"},
            "template": {"template_id": "tpl_001"},
            "metadata": {"required_tools": ["get_quality_factor_bundle_tool"]},
        }

    async def _fake_evaluate_version(self, version_id, evaluation_type="sandbox", sample_set_id=None, user_feedback="", benchmark_outputs=None, runtime_result=None):
        del self, sample_set_id, benchmark_outputs
        return {
            "version_id": version_id,
            "evaluation": {
                "evaluation_id": "eval_001",
                "decision": "pass",
                "evaluation_type": evaluation_type,
                "scores": {"overall": 0.93},
                "issues": [],
                "recommendations": [user_feedback or "can be published"],
                "runtime_result": runtime_result,
            },
        }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.debug_version",
        _fake_debug_version,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.evaluate_version",
        _fake_evaluate_version,
    )
    monkeypatch.setattr(
        "app.services.intelligent_assistant_service.get_reasoning_llm_config",
        _fake_get_reasoning_llm_config,
    )

    raw = await run_agent_workshop_real_data_test.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
        "stock_symbol": "600519",
        "analysis_date": "2026-04-03",
        "user_feedback": "Complete structure",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["test_chain_status"] == "ok"
    assert payload["official_acceptance_decision"] == "pass"
    assert payload["official_acceptance_passed"] is True
    assert payload["summary"]["decision"] == "pass"
    assert payload["summary"]["recorded_in_workshop"] is True
    assert payload["summary"]["official_acceptance_passed"] is True
    assert "It must be manually confirmed by the user before it can be officially released." in payload["message"]
    assert payload["evaluation"]["evaluation_type"] == "production-review"
    assert payload["evaluation"]["runtime_result"]["output_text"] == "final report"
    assert payload["evaluation"]["runtime_result"]["report"] == "final report"
    assert payload["evaluation"]["runtime_result"]["raw_result"] == {"tool_trace": []}
    assert payload["evaluation"]["runtime_result"]["tool_trace"] == []
    assert payload["evaluation"]["runtime_result"]["review_worker_mode"] == "nanobot-assisted"
    assert payload["evaluation"]["runtime_result"]["nanobot_evidence_workers"] is True
    assert [event["name"] for event in payload["_tool_events"]] == [
        "run_agent_workshop_real_data_test.resolve_default_llm",
        "run_agent_workshop_real_data_test.debug_version",
        "run_agent_workshop_real_data_test.evaluate_version",
        "run_agent_workshop_real_data_test",
    ]


@pytest.mark.asyncio
async def test_run_agent_workshop_real_data_test_returns_failed_stage_events(monkeypatch):
    fake_db = _FakeDb({})

    async def _fake_get_reasoning_llm_config(db=None):
        del db
        return CoreLLMConfig(
            provider=LLMProvider.DASHSCOPE,
            model="qwen-max",
            api_key="fake-api-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0.2,
            max_tokens=4000,
            timeout=180,
            retry_times=3,
        )

    async def _fake_debug_version(self, version_id, llm, stock, user_goal="", prompt_overrides=None):
        del self, version_id, llm, stock, user_goal, prompt_overrides
        raise RuntimeError("Default inference model call failed")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.debug_version",
        _fake_debug_version,
    )
    monkeypatch.setattr(
        "app.services.intelligent_assistant_service.get_reasoning_llm_config",
        _fake_get_reasoning_llm_config,
    )

    raw = await run_agent_workshop_real_data_test.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
        "stock_symbol": "600519",
    })
    payload = json.loads(raw)

    assert payload["status"] == "error"
    assert payload["failed_stage"] == "run_agent_workshop_real_data_test.debug_version"
    assert payload["_tool_events"][-1]["name"] == "run_agent_workshop_real_data_test"
    assert payload["_tool_events"][-1]["status"] == "error"


@pytest.mark.asyncio
async def test_run_agent_workshop_real_data_test_exposes_non_pass_acceptance_clearly(monkeypatch):
    fake_db = _FakeDb({})

    async def _fake_get_reasoning_llm_config(db=None):
        del db
        return CoreLLMConfig(
            provider=LLMProvider.DASHSCOPE,
            model="qwen-max",
            api_key="fake-api-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0.2,
            max_tokens=4000,
            timeout=180,
            retry_times=3,
        )

    async def _fake_debug_version(self, version_id, llm, stock, user_goal="", prompt_overrides=None):
        del self, llm, user_goal, prompt_overrides
        return {
            "version_id": version_id,
            "spec_id": "spec_financial_risk_v1",
            "symbol": stock["symbol"],
            "analysis_date": stock.get("analysis_date") or "2026-04-03",
            "report": "final report",
            "report_length": 12,
            "raw_result": {"tool_trace": []},
            "debug_prompt": {"llm_final_response": "final report"},
            "template": {"template_id": "tpl_001"},
            "metadata": {"required_tools": ["get_quality_factor_bundle_tool"]},
        }

    async def _fake_evaluate_version(self, version_id, evaluation_type="sandbox", sample_set_id=None, user_feedback="", benchmark_outputs=None, runtime_result=None):
        del self, sample_set_id, benchmark_outputs, user_feedback
        return {
            "version_id": version_id,
            "evaluation": {
                "evaluation_id": "eval_002",
                "decision": "revise",
                "evaluation_type": evaluation_type,
                "scores": {"overall": 0.68},
                "issues": ["The conclusion is unstable"],
                "recommendations": ["Retest after adding corrections"],
                "runtime_result": runtime_result,
            },
        }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.debug_version",
        _fake_debug_version,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.evaluate_version",
        _fake_evaluate_version,
    )
    monkeypatch.setattr(
        "app.services.intelligent_assistant_service.get_reasoning_llm_config",
        _fake_get_reasoning_llm_config,
    )

    raw = await run_agent_workshop_real_data_test.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
        "stock_symbol": "600519",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["test_chain_status"] == "ok"
    assert payload["official_acceptance_decision"] == "revise"
    assert payload["official_acceptance_passed"] is False
    assert payload["summary"]["decision"] == "revise"
    assert payload["summary"]["official_acceptance_passed"] is False
    assert "Currently cannot be considered passed" in payload["message"]


@pytest.mark.asyncio
async def test_run_agent_workshop_real_data_test_blocks_non_testing_version(monkeypatch):
    fake_db = _FakeDb({
        "agent_versions": _FakeCollection([{
            "version_id": "spec_financial_risk_v1_v1",
            "spec_id": "spec_financial_risk_v1",
            "status": "draft",
        }]),
        "agent_evaluations": _FakeCollection([]),
    })

    async def _fake_debug_version(self, version_id, llm, stock, user_goal="", prompt_overrides=None):
        del self, version_id, llm, stock, user_goal, prompt_overrides
        raise AssertionError("debug_version should not be called for non-testing version")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.debug_version",
        _fake_debug_version,
    )

    raw = await run_agent_workshop_real_data_test.ainvoke({
        "version_id": "spec_financial_risk_v1_v1",
        "stock_symbol": "600519",
    })
    payload = json.loads(raw)

    assert payload["status"] == "blocked"
    assert payload["blocked_by"] == "phase_guard"
    assert payload["blocked_code"] == "version_not_testing"
    assert payload["current_phase"] == "generation"
    assert payload["version_id"] == "spec_financial_risk_v1_v1"
    assert payload["_tool_events"][0]["name"] == "run_agent_workshop_real_data_test.phase_guard"


@pytest.mark.asyncio
async def test_publish_agent_workshop_version_calls_service(monkeypatch):
    fake_db = _FakeDb({})

    async def _fake_publish_version(self, version_id):
        del self
        return {
            "version_id": version_id,
            "spec_id": "spec_financial_risk_v1",
            "status": "active",
            "previous_active_archived": True,
        }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.publish_version",
        _fake_publish_version,
    )

    raw = await publish_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["version_id"] == "spec_financial_risk_v1_v2"
    assert payload["spec_id"] == "spec_financial_risk_v1"


@pytest.mark.asyncio
async def test_publish_agent_workshop_version_blocks_without_pass_evaluation(monkeypatch):
    fake_db = _FakeDb({
        "agent_versions": _FakeCollection([{
            "version_id": "spec_financial_risk_v1_v2",
            "spec_id": "spec_financial_risk_v1",
            "status": "testing",
        }]),
        "agent_evaluations": _FakeCollection([{
            "evaluation_id": "eval_002",
            "version_id": "spec_financial_risk_v1_v2",
            "decision": "revise",
            "created_at": "2026-04-05T10:00:00",
        }]),
    })

    async def _fake_publish_version(self, version_id):
        del self, version_id
        raise AssertionError("publish_version should not be called when latest evaluation is not pass")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.publish_version",
        _fake_publish_version,
    )

    raw = await publish_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
    })
    payload = json.loads(raw)

    assert payload["status"] == "blocked"
    assert payload["blocked_by"] == "phase_guard"
    assert payload["blocked_code"] == "latest_evaluation_not_pass"
    assert payload["current_phase"] == "evaluation"
    assert payload["summary"]["latest_evaluation_decision"] == "revise"
    assert payload["summary"]["blocked_code"] == "latest_evaluation_not_pass"
    assert payload["_tool_events"][0]["name"] == "publish_agent_workshop_version.phase_guard"


@pytest.mark.asyncio
async def test_evaluate_agent_workshop_version_calls_service(monkeypatch):
    fake_db = _FakeDb({
        "agent_versions": _FakeCollection([{
            "version_id": "spec_financial_risk_v1_v2",
            "spec_id": "spec_financial_risk_v1",
            "status": "testing",
        }]),
        "agent_evaluations": _FakeCollection([]),
    })

    async def _fake_evaluate_version(self, version_id, evaluation_type="sandbox", sample_set_id=None, user_feedback="", benchmark_outputs=None, runtime_result=None):
        del self
        assert version_id == "spec_financial_risk_v1_v2"
        assert evaluation_type == "production-review"
        assert sample_set_id == "sample_001"
        assert user_feedback == "Need additional explanation"
        assert benchmark_outputs == [{"case_id": "c1", "output_text": "ok"}]
        assert runtime_result == {
            "output_text": "formal report",
            "review_worker_mode": "nanobot-assisted",
            "nanobot_evidence_workers": True,
        }
        return {
            "version_id": version_id,
            "evaluation": {
                "evaluation_id": "eval_003",
                "evaluation_type": evaluation_type,
                "decision": "revise",
                "scores": {"overall": 0.72},
                "issues": ["Incomplete explanation"],
                "recommendations": ["Supplementary cause analysis"],
            },
        }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.evaluate_version",
        _fake_evaluate_version,
    )

    raw = await evaluate_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
        "evaluation_type": "production-review",
        "sample_set_id": "sample_001",
        "user_feedback": "Need additional explanation",
        "benchmark_outputs_json": '[{"case_id":"c1","output_text":"ok"}]',
        "runtime_result_json": '{"output_text":"formal report"}',
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["version_id"] == "spec_financial_risk_v1_v2"
    assert payload["summary"]["decision"] == "revise"
    assert payload["summary"]["overall_score"] == 0.72
    assert payload["_tool_events"][0]["name"] == "evaluate_agent_workshop_version.evaluate_version"


@pytest.mark.asyncio
async def test_evaluate_agent_workshop_version_blocks_non_testing_version(monkeypatch):
    fake_db = _FakeDb({
        "agent_versions": _FakeCollection([{
            "version_id": "spec_financial_risk_v1_v1",
            "spec_id": "spec_financial_risk_v1",
            "status": "draft",
        }]),
        "agent_evaluations": _FakeCollection([]),
    })

    async def _fake_evaluate_version(self, version_id, evaluation_type="sandbox", sample_set_id=None, user_feedback="", benchmark_outputs=None, runtime_result=None):
        del self, version_id, evaluation_type, sample_set_id, user_feedback, benchmark_outputs, runtime_result
        raise AssertionError("evaluate_version should not be called for non-testing version")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.evaluate_version",
        _fake_evaluate_version,
    )

    raw = await evaluate_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v1",
    })
    payload = json.loads(raw)

    assert payload["status"] == "blocked"
    assert payload["blocked_by"] == "phase_guard"
    assert payload["blocked_code"] == "version_not_testing"
    assert payload["current_phase"] == "generation"
    assert payload["_tool_events"][0]["name"] == "evaluate_agent_workshop_version.phase_guard"


@pytest.mark.asyncio
async def test_evaluate_agent_workshop_version_rejects_missing_runtime_evidence(monkeypatch):
    fake_db = _FakeDb({
        "agent_versions": _FakeCollection([{
            "version_id": "spec_financial_risk_v1_v2",
            "spec_id": "spec_financial_risk_v1",
            "status": "testing",
        }]),
        "agent_evaluations": _FakeCollection([]),
    })

    async def _fake_evaluate_version(self, version_id, evaluation_type="sandbox", sample_set_id=None, user_feedback="", benchmark_outputs=None, runtime_result=None):
        del self, version_id, evaluation_type, sample_set_id, user_feedback, benchmark_outputs, runtime_result
        raise AssertionError("evaluate_version should not be called when runtime evidence is missing")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.evaluate_version",
        _fake_evaluate_version,
    )

    raw = await evaluate_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
        "evaluation_type": "production-review",
        "runtime_result_json": '{"symbol":"600519"}',
    })
    payload = json.loads(raw)

    assert payload["status"] == "error"
    assert "production-review runtime_result_json is provided but lacks available evidence" in payload["message"]


@pytest.mark.asyncio
async def test_evaluate_agent_workshop_version_accepts_debug_shaped_runtime_result(monkeypatch):
    fake_db = _FakeDb({
        "agent_versions": _FakeCollection([{
            "version_id": "spec_financial_risk_v1_v2",
            "spec_id": "spec_financial_risk_v1",
            "status": "testing",
        }]),
        "agent_evaluations": _FakeCollection([]),
    })

    async def _fake_evaluate_version(self, version_id, evaluation_type="sandbox", sample_set_id=None, user_feedback="", benchmark_outputs=None, runtime_result=None):
        del self, sample_set_id, user_feedback, benchmark_outputs
        assert version_id == "spec_financial_risk_v1_v2"
        assert evaluation_type == "production-review"
        assert runtime_result == {
            "report": "formal report",
            "raw_result": {
                "risk_report": "formal report",
                "tool_trace": [{"tool_name": "get_quality_factor_bundle_tool", "success": True}],
            },
            "review_worker_mode": "nanobot-assisted",
            "nanobot_evidence_workers": True,
        }
        return {
            "version_id": version_id,
            "evaluation": {
                "evaluation_id": "eval_004",
                "evaluation_type": evaluation_type,
                "decision": "pass",
                "scores": {"overall": 0.88},
                "issues": [],
                "recommendations": [],
            },
        }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.evaluate_version",
        _fake_evaluate_version,
    )

    raw = await evaluate_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
        "evaluation_type": "production-review",
        "runtime_result_json": '{"report":"formal report","raw_result":{"risk_report":"formal report","tool_trace":[{"tool_name":"get_quality_factor_bundle_tool","success":true}]}}',
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["summary"]["decision"] == "pass"


@pytest.mark.asyncio
async def test_evaluate_agent_workshop_version_allows_service_fallback_when_runtime_result_missing(monkeypatch):
    fake_db = _FakeDb({
        "agent_versions": _FakeCollection([{
            "version_id": "spec_financial_risk_v1_v2",
            "spec_id": "spec_financial_risk_v1",
            "status": "testing",
        }]),
        "agent_evaluations": _FakeCollection([]),
    })

    async def _fake_evaluate_version(self, version_id, evaluation_type="sandbox", sample_set_id=None, user_feedback="", benchmark_outputs=None, runtime_result=None):
        del self, sample_set_id, user_feedback, benchmark_outputs
        assert version_id == "spec_financial_risk_v1_v2"
        assert evaluation_type == "production-review"
        assert runtime_result is None
        return {
            "version_id": version_id,
            "evaluation": {
                "evaluation_id": "eval_005",
                "evaluation_type": evaluation_type,
                "decision": "pass",
                "scores": {"overall": 0.9},
                "issues": [],
                "recommendations": [],
            },
        }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.evaluate_version",
        _fake_evaluate_version,
    )

    raw = await evaluate_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
        "evaluation_type": "production-review",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["summary"]["decision"] == "pass"


@pytest.mark.asyncio
async def test_iterate_agent_workshop_version_calls_service(monkeypatch):
    fake_db = _FakeDb({
        "agent_versions": _FakeCollection([{
            "version_id": "spec_financial_risk_v1_v2",
            "spec_id": "spec_financial_risk_v1",
            "status": "active",
        }]),
        "agent_evaluations": _FakeCollection([]),
    })

    async def _fake_iterate_version(self, version_id, feedback=""):
        del self
        assert version_id == "spec_financial_risk_v1_v2"
        assert feedback == "Supplementary risk stratification"
        return {
            "source_version_id": version_id,
            "session_id": "session_iter_001",
            "spec_id": "spec_financial_risk_v1",
            "version_id": "spec_financial_risk_v1_v3",
            "version_status": "draft",
            "ai_message": "Next round has been created",
        }

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.iterate_version",
        _fake_iterate_version,
    )

    raw = await iterate_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
        "feedback": "Supplementary risk stratification",
    })
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["session_id"] == "session_iter_001"
    assert payload["summary"]["source_version_id"] == "spec_financial_risk_v1_v2"
    assert payload["summary"]["version_id"] == "spec_financial_risk_v1_v3"
    assert payload["summary"]["version_status"] == "draft"
    assert payload["_tool_events"][0]["name"] == "iterate_agent_workshop_version.iterate_version"


@pytest.mark.asyncio
async def test_iterate_agent_workshop_version_blocks_before_evaluation(monkeypatch):
    fake_db = _FakeDb({
        "agent_versions": _FakeCollection([{
            "version_id": "spec_financial_risk_v1_v2",
            "spec_id": "spec_financial_risk_v1",
            "status": "testing",
        }]),
        "agent_evaluations": _FakeCollection([]),
    })

    async def _fake_iterate_version(self, version_id, feedback=""):
        del self, version_id, feedback
        raise AssertionError("iterate_version should not be called before evaluation")

    monkeypatch.setattr(
        "core.tools.implementations.agent_builder.nanobot_agent_builder_tools.get_mongo_db",
        lambda: fake_db,
    )
    monkeypatch.setattr(
        "app.services.agent_workshop_service.AgentWorkshopService.iterate_version",
        _fake_iterate_version,
    )

    raw = await iterate_agent_workshop_version.ainvoke({
        "version_id": "spec_financial_risk_v1_v2",
    })
    payload = json.loads(raw)

    assert payload["status"] == "blocked"
    assert payload["blocked_by"] == "phase_guard"
    assert payload["blocked_code"] == "phase_not_ready"
    assert payload["current_phase"] == "testing"
    assert payload["_tool_events"][0]["name"] == "iterate_agent_workshop_version.phase_guard"
import importlib.util
from pathlib import Path

import pytest

from app.services.project_memory_service import ProjectMemoryService


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULTS_PATH = ROOT_DIR / "app" / "services" / "project_memory_defaults.py"
spec = importlib.util.spec_from_file_location("project_memory_defaults", DEFAULTS_PATH)
defaults_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(defaults_module)


class _FakeUpdateResult:
    def __init__(self, matched_count: int = 1):
        self.matched_count = matched_count


class _FakeCursor:
    def __init__(self, docs):
        self._docs = [dict(doc) for doc in docs]

    def sort(self, sort_spec):
        for field, direction in reversed(sort_spec):
            reverse = direction < 0
            self._docs.sort(key=lambda doc: doc.get(field), reverse=reverse)
        return self

    def limit(self, size):
        self._docs = self._docs[:size]
        return self

    async def to_list(self, length):
        return [dict(doc) for doc in self._docs[:length]]


class _FakeCollection:
    def __init__(self):
        self.docs = []

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _matches(doc, query):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return _FakeUpdateResult()

        if upsert:
            new_doc = dict(query)
            for key, value in update.get("$setOnInsert", {}).items():
                new_doc[key] = value
            for key, value in update.get("$set", {}).items():
                new_doc[key] = value
            self.docs.append(new_doc)
        return _FakeUpdateResult()

    async def find_one(self, query):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    def find(self, query):
        return _FakeCursor([doc for doc in self.docs if _matches(doc, query)])


class _FakeDB:
    def __init__(self):
        self._collection = _FakeCollection()

    def __getitem__(self, name):
        assert name == "project_memory_items"
        return self._collection


def _matches(doc, query):
    for key, value in query.items():
        if isinstance(value, dict) and "$in" in value:
            if doc.get(key) not in value["$in"]:
                return False
            continue
        if doc.get(key) != value:
            return False
    return True


@pytest.mark.asyncio
async def test_project_memory_service_upserts_and_lists_by_priority():
    svc = ProjectMemoryService(_FakeDB())

    await svc.upsert_item(
        memory_key="assistant-output",
        title="The answer must first give a conclusion",
        content="Give the conclusion first, then the evidence and risks.",
        category="analysis_output_constraint",
        priority=20,
        updated_by="user-1",
    )
    await svc.upsert_item(
        memory_key="risk-disclaimer",
        title="Avoid investment advice tone",
        content="Expressing analysis into direct buying and selling orders is prohibited.",
        category="project_rule",
        priority=10,
        updated_by="user-1",
    )

    items = await svc.list_items(limit=10)

    assert [item.memory_key for item in items] == ["risk-disclaimer", "assistant-output"]
    assert items[0].updated_by == "user-1"


@pytest.mark.asyncio
async def test_project_memory_service_builds_grouped_prompt_block():
    svc = ProjectMemoryService(_FakeDB())

    await svc.upsert_item(
        memory_key="assistant-output",
        title="The answer must first give a conclusion",
        content="Give the conclusion first, then the evidence and risks.",
        category="analysis_output_constraint",
        priority=20,
    )
    await svc.upsert_item(
        memory_key="risk-disclaimer",
        title="Avoid investment advice tone",
        content="Expressing analysis into direct buying and selling orders is prohibited.",
        category="project_rule",
        priority=10,
    )

    block = await svc.build_prompt_block(max_items=6, max_chars=500)

    assert " [Project long-term memory]" in block
    assert "- Project rules" in block
    assert "- Output constraints" in block
    assert "Avoid the tone of investment advice: It is forbidden to express analysis as direct buying and selling orders." in block
    assert "The answer should give the conclusion first: give the conclusion first, and then give the evidence and risks." in block


@pytest.mark.asyncio
async def test_project_memory_service_seeds_defaults_idempotently():
    svc = ProjectMemoryService(_FakeDB())

    first = await svc.seed_default_items(updated_by="system_seed")
    second = await svc.seed_default_items(updated_by="system_seed")
    items = await svc.list_items(limit=20)
    default_items = defaults_module.get_default_project_memory_items()

    assert first["count"] == len(default_items)
    assert second["count"] == len(default_items)
    assert len(items) == len(default_items)
    assert items[0].memory_key == "global-no-trading-advice"
    assert any(item.memory_key == "stock-analysis-template" for item in items)
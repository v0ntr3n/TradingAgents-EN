from app.scripts.migrate_legacy_agent_memory_to_mem0 import (
    LegacyMemoryRecord,
    _build_store_metadata,
    _build_store_messages,
    _normalize_collection_rows,
    _normalize_qdrant_scroll_rows,
)


class _FakeQdrantPoint:
    def __init__(self, point_id, payload):
        self.id = point_id
        self.payload = payload


def test_normalize_collection_rows_builds_legacy_records():
    payload = {
        "ids": ["1", "2"],
        "documents": [
            "Kweichow Moutai 600519 fundamentals improving",
            "Tencent Holdings HK.00700 Valuation under pressure",
        ],
        "metadatas": [
            {"recommendation": "Continue to track high-end liquor demand and valuation switching"},
            {"recommendation": "Pay attention to advertising recovery and repair space after valuation compression"},
        ],
    }

    records = _normalize_collection_rows("bull_memory", payload)

    assert len(records) == 2
    assert records[0].memory_name == "bull_memory"
    assert records[0].legacy_doc_id == "1"
    assert records[0].recommendation == "Continue to track high-end liquor demand and valuation switching"
    assert records[1].legacy_doc_id == "2"


def test_build_store_metadata_adds_symbol_object_binding():
    record = LegacyMemoryRecord(
        memory_name="bull_memory",
        legacy_doc_id="7",
        situation="Kweichow Moutai 600519 fundamentals improving",
        recommendation="Continue to track high-end liquor demand and valuation switching",
    )

    metadata = _build_store_metadata(record)

    assert metadata["source"] == "legacy_financial_situation_memory_migration"
    assert metadata["legacy_memory_name"] == "bull_memory"
    assert metadata["legacy_doc_id"] == "7"
    assert metadata["symbol"] == "600519"
    assert metadata["object_type"] == "stock"
    assert metadata["object_key"] == "600519"


def test_build_store_messages_preserves_legacy_payload_shape():
    record = LegacyMemoryRecord(
        memory_name="risk_manager_memory",
        legacy_doc_id="9",
        situation="Position exposure is high in a high volatility environment",
        recommendation="Reduce high beta positions and increase cash ratio",
    )

    messages = _build_store_messages(record)

    assert messages == [
        {
            "role": "user",
            "content": "Legacy situation:\n Position exposure is high in a high volatility environment\n\nRecommendation:\n Reduce high beta positions and increase cash ratio",
        }
    ]


def test_normalize_qdrant_scroll_rows_builds_legacy_records():
    points = [
        _FakeQdrantPoint(
            "abc-1",
            {
                "document": "CATL 300750 research conclusion is too high, focusing on profit restoration.",
                "ticker": "300750",
                "stance": "bull",
                "agent_id": "bull_researcher_v2",
                "provider": "Alibaba Cloud Bailian",
            },
        )
    ]

    records = _normalize_qdrant_scroll_rows("memory_bull_researcher_v2", points)

    assert len(records) == 1
    assert records[0].memory_name == "memory_bull_researcher_v2"
    assert records[0].legacy_doc_id == "abc-1"
    assert records[0].situation == "CATL 300750 research conclusion is too high, focusing on profit restoration."
    assert records[0].legacy_metadata["agent_id"] == "bull_researcher_v2"
    assert records[0].legacy_metadata["ticker"] == "300750"


def test_build_store_metadata_preserves_qdrant_legacy_metadata():
    record = LegacyMemoryRecord(
        memory_name="memory_bear_researcher_v2",
        legacy_doc_id="pt-9",
        situation="Vanke A 000002 s fundamentals are under pressure and sales recovery is slow.",
        legacy_metadata={
            "ticker": "000002",
            "stance": "bear",
            "agent_id": "bear_researcher_v2",
            "timestamp": "2026-04-08T10:00:00",
            "provider": "Alibaba Cloud Bailian",
        },
    )

    metadata = _build_store_metadata(record)

    assert metadata["legacy_content"] == "Vanke A 000002 s fundamentals are under pressure and sales recovery is slow."
    assert metadata["ticker"] == "000002"
    assert metadata["legacy_stance"] == "bear"
    assert metadata["legacy_agent_id"] == "bear_researcher_v2"
    assert metadata["legacy_timestamp"] == "2026-04-08T10:00:00"
    assert metadata["legacy_embedding_provider"] == "Alibaba Cloud Bailian"
    assert metadata["symbol"] == "000002"
    assert metadata["object_key"] == "000002"


def test_build_store_messages_without_recommendation_uses_plain_content():
    record = LegacyMemoryRecord(
        memory_name="memory_pa_risk_v2",
        legacy_doc_id="pt-10",
        situation="The portfolio is highly exposed to high volatility factors and needs to control drawdowns.",
    )

    messages = _build_store_messages(record)

    assert messages == [
        {
            "role": "user",
            "content": "The portfolio is highly exposed to high volatility factors and needs to control drawdowns.",
        }
    ]

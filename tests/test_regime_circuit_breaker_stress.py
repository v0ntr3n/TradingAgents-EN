"""
Adversarial Stress Test Suite for Milestone 3 (CARE-Agents R3):
Regime Circuit Breaker in core/memory/memory_manager.py

Conducted by Challenger M3_1.
Coverage:
1. Boundary Confidences:
   - Exact 0.500000 -> Circuit Breaker ACTIVE (NO contradicting memory leaks)
   - Exact 0.499900 -> Circuit Breaker BYPASSED (Cross-regime memories returned)
   - Exact 0.500100 -> Circuit Breaker ACTIVE
   - Float epsilon boundaries (0.4999999999999999, 0.5000000000000001)
   - Zero confidence (0.0), Negative confidence (-0.5), Over-unity confidence (1.5)
   - String representations ("0.5", "0.4999", "0.5001", "invalid")
   - None / missing confidence
2. 5 Circuit-Breaker Target Agents and Aliases vs Non-Circuit Agents:
   - bull_researcher / bull_researcher_v2
   - bear_researcher / bear_researcher_v2
   - research_manager / research_manager_v2
   - trader / trader_v2
   - risk_manager / risk_manager_v2
   - Non-circuit: 7 analyst types (v1 and v2), judges, arbitrary external agent IDs
3. Absolute Leakage Prevention (Conf >= 0.5):
   - 100+ synthetic memories across Bull, Bear, Sideways
   - Verify 0% contamination for Bull, Bear, Sideways targets
   - Whitespace and case-sensitivity variations in current_regime and stored metadata
4. Cross-Regime Returns (Conf < 0.5):
   - Verify all candidate regimes (Bull, Bear, Sideways) are returned without loss
5. Memory Store Resiliency & Malformed Metadata:
   - Empty memory stores
   - Missing metadata key
   - None metadata
   - Malformed metadata types (strings, lists, ints)
   - None/empty/unknown/malformed market_regime values
   - Clamping and sanitization of volatility_quintile and brier_calibration_error
   - Non-dict memory objects (e.g., custom objects with attributes)
6. Mem0AgentMemory & AgentMemory Integration:
   - Parameter resolution priority (method args > state > filter_metadata)
   - Candidate over-fetching (max(n_results * 3, 15)) to prevent candidate starvation
   - Mocked VectorStore / EmbeddingManager query pipeline
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List

from core.memory.memory_manager import (
    Mem0AgentMemory,
    AgentMemory,
    circuit_breaker_memory_filter,
    _CIRCUIT_BREAKER_AGENTS,
    _AGENT_ID_ALIAS_MAPPING,
)


# ==============================================================================
# Fixtures & Helpers
# ==============================================================================

@pytest.fixture
def rich_memory_store() -> List[Dict[str, Any]]:
    """Generates a rich, heterogeneous pool of memories across all 3 regimes."""
    memories = []
    # 20 Bull memories
    for i in range(20):
        memories.append({
            "id": f"bull_{i}",
            "content": f"Bull trend breakout and momentum trade #{i}",
            "metadata": {
                "market_regime": "bull",
                "volatility_quintile": (i % 5) + 1,
                "brier_calibration_error": round(0.01 * (i % 10), 3),
                "ticker": f"60000{i}.SH",
            },
            "similarity": 0.95 - (i * 0.01),
        })
    # 20 Bear memories
    for i in range(20):
        memories.append({
            "id": f"bear_{i}",
            "content": f"Bear market stop loss and shorting signal #{i}",
            "metadata": {
                "market_regime": "bear",
                "volatility_quintile": (i % 5) + 1,
                "brier_calibration_error": round(0.01 * (i % 10), 3),
                "ticker": f"00000{i}.SZ",
            },
            "similarity": 0.95 - (i * 0.01),
        })
    # 20 Sideways memories
    for i in range(20):
        memories.append({
            "id": f"sideways_{i}",
            "content": f"Sideways oscillation mean reversion #{i}",
            "metadata": {
                "market_regime": "sideways",
                "volatility_quintile": (i % 5) + 1,
                "brier_calibration_error": round(0.01 * (i % 10), 3),
                "ticker": f"30000{i}.SZ",
            },
            "similarity": 0.95 - (i * 0.01),
        })
    return memories


# ==============================================================================
# 1. Boundary Confidence Stress Tests
# ==============================================================================

class TestBoundaryConfidences:
    """Stress tests exact mathematical boundaries for circuit breaker activation."""

    def test_exact_0_5_triggers_circuit_breaker(self, rich_memory_store):
        """Confidence exactly 0.5 must ACTIVATE the circuit breaker (no contradicting leakage)."""
        filtered = circuit_breaker_memory_filter(
            rich_memory_store,
            current_regime="bull",
            regime_confidence=0.5,
            agent_id="trader_v2",
        )
        assert len(filtered) == 20
        assert all(m["metadata"]["market_regime"] == "bull" for m in filtered)
        # Verify 0 bear and 0 sideways
        assert not any(m["metadata"]["market_regime"] == "bear" for m in filtered)
        assert not any(m["metadata"]["market_regime"] == "sideways" for m in filtered)

    def test_exact_0_4999_bypasses_circuit_breaker(self, rich_memory_store):
        """Confidence 0.4999 (< 0.5) must BYPASS the circuit breaker (cross-regime returned)."""
        filtered = circuit_breaker_memory_filter(
            rich_memory_store,
            current_regime="bull",
            regime_confidence=0.4999,
            agent_id="trader_v2",
        )
        assert len(filtered) == 60
        regimes_found = {m["metadata"]["market_regime"] for m in filtered}
        assert regimes_found == {"bull", "bear", "sideways"}

    def test_exact_0_5001_triggers_circuit_breaker(self, rich_memory_store):
        """Confidence 0.5001 (> 0.5) must ACTIVATE the circuit breaker."""
        filtered = circuit_breaker_memory_filter(
            rich_memory_store,
            current_regime="bear",
            regime_confidence=0.5001,
            agent_id="bear_researcher_v2",
        )
        assert len(filtered) == 20
        assert all(m["metadata"]["market_regime"] == "bear" for m in filtered)

    def test_float_epsilon_boundaries(self, rich_memory_store):
        """Epsilon near 0.5 in IEEE 754 float precision."""
        # Just below 0.5
        sub_eps = 0.5 - 1e-15
        filtered_sub = circuit_breaker_memory_filter(
            rich_memory_store,
            current_regime="bear",
            regime_confidence=sub_eps,
            agent_id="bear_researcher_v2",
        )
        assert len(filtered_sub) == 60, "Sub-epsilon below 0.5 should bypass"

        # Just above 0.5
        super_eps = 0.5 + 1e-15
        filtered_super = circuit_breaker_memory_filter(
            rich_memory_store,
            current_regime="bear",
            regime_confidence=super_eps,
            agent_id="bear_researcher_v2",
        )
        assert len(filtered_super) == 20, "Super-epsilon above 0.5 should activate circuit breaker"
        assert all(m["metadata"]["market_regime"] == "bear" for m in filtered_super)

    def test_zero_and_negative_confidence_bypasses(self, rich_memory_store):
        """Zero or negative confidence represents extreme ambiguity; should bypass."""
        for c in [0.0, -0.01, -1.0, -100.0]:
            filtered = circuit_breaker_memory_filter(
                rich_memory_store,
                current_regime="bull",
                regime_confidence=c,
                agent_id="risk_manager_v2",
            )
            assert len(filtered) == 60, f"Confidence {c} failed to bypass"

    def test_over_unity_confidence_activates(self, rich_memory_store):
        """Confidence >= 1.0 (even malformed > 1.0) must activate circuit breaker."""
        for c in [1.0, 1.0001, 2.5, 999.0]:
            filtered = circuit_breaker_memory_filter(
                rich_memory_store,
                current_regime="sideways",
                regime_confidence=c,
                agent_id="research_manager_v2",
            )
            assert len(filtered) == 20
            assert all(m["metadata"]["market_regime"] == "sideways" for m in filtered)

    def test_string_and_invalid_confidence_coercion(self, rich_memory_store):
        """String numbers should be parsed; non-numeric values should default safely to 1.0 (active)."""
        # String numeric values
        assert len(circuit_breaker_memory_filter(rich_memory_store, "bull", "0.5", agent_id="trader_v2")) == 20
        assert len(circuit_breaker_memory_filter(rich_memory_store, "bull", "0.4999", agent_id="trader_v2")) == 60
        assert len(circuit_breaker_memory_filter(rich_memory_store, "bull", "0.5001", agent_id="trader_v2")) == 20

        # Non-numeric string -> default 1.0 -> active
        res_invalid = circuit_breaker_memory_filter(rich_memory_store, "bull", "invalid_conf", agent_id="trader_v2")
        assert len(res_invalid) == 20
        assert all(m["metadata"]["market_regime"] == "bull" for m in res_invalid)

        # None -> default 1.0 -> active
        res_none = circuit_breaker_memory_filter(rich_memory_store, "bull", None, agent_id="trader_v2")
        assert len(res_none) == 20
        assert all(m["metadata"]["market_regime"] == "bull" for m in res_none)


# ==============================================================================
# 2. Target Agent IDs & Aliases vs Non-Circuit Agents
# ==============================================================================

class TestAgentWhitelistingAndAliases:
    """Tests all 5 circuit-breaker agent IDs and their aliases against non-circuit agents."""

    TARGET_CIRCUIT_AGENTS_V2 = [
        "bull_researcher_v2",
        "bear_researcher_v2",
        "research_manager_v2",
        "trader_v2",
        "risk_manager_v2",
    ]

    TARGET_CIRCUIT_AGENTS_V1 = [
        "bull_researcher",
        "bear_researcher",
        "research_manager",
        "trader",
        "risk_manager",
    ]

    NON_CIRCUIT_AGENTS = [
        "index_analyst_v2",
        "sector_analyst_v2",
        "market_analyst_v2",
        "fundamentals_analyst_v2",
        "news_analyst_v2",
        "social_analyst_v2",
        "chip_distribution_analyst_v2",
        "index_analyst",
        "sector_analyst",
        "market_analyst",
        "fundamentals_analyst",
        "news_analyst",
        "social_analyst",
        "chip_distribution_analyst",
        "investment_judge",
        "invest_judge",
        "risk_judge",
        "reflector",
        "random_custom_agent",
    ]

    def test_all_5_v2_circuit_breaker_agents_activate(self, rich_memory_store):
        """All 5 v2 target agents enforce circuit breaker at confidence >= 0.5."""
        for agent_id in self.TARGET_CIRCUIT_AGENTS_V2:
            filtered = circuit_breaker_memory_filter(
                rich_memory_store,
                current_regime="bear",
                regime_confidence=0.85,
                agent_id=agent_id,
            )
            assert len(filtered) == 20, f"Failed for {agent_id}"
            assert all(m["metadata"]["market_regime"] == "bear" for m in filtered)

    def test_all_5_v1_alias_circuit_breaker_agents_activate(self, rich_memory_store):
        """All 5 v1 target agent aliases enforce circuit breaker at confidence >= 0.5."""
        for agent_id in self.TARGET_CIRCUIT_AGENTS_V1:
            filtered = circuit_breaker_memory_filter(
                rich_memory_store,
                current_regime="bull",
                regime_confidence=0.85,
                agent_id=agent_id,
            )
            assert len(filtered) == 20, f"Failed for v1 alias {agent_id}"
            assert all(m["metadata"]["market_regime"] == "bull" for m in filtered)

    def test_alias_mapping_coverage(self):
        """Verify that _AGENT_ID_ALIAS_MAPPING covers both v1 and v2 pairs for all 5 agents."""
        for v2_id, v1_id in zip(self.TARGET_CIRCUIT_AGENTS_V2, self.TARGET_CIRCUIT_AGENTS_V1):
            assert v2_id in _CIRCUIT_BREAKER_AGENTS
            assert v1_id in _CIRCUIT_BREAKER_AGENTS
            assert v1_id in _AGENT_ID_ALIAS_MAPPING[v2_id]
            assert v2_id in _AGENT_ID_ALIAS_MAPPING[v1_id]

    def test_non_circuit_agents_never_filtered_even_at_high_confidence(self, rich_memory_store):
        """Non-circuit agents (analysts, judges, etc.) must NEVER be filtered by regime circuit breaker."""
        for agent_id in self.NON_CIRCUIT_AGENTS:
            filtered = circuit_breaker_memory_filter(
                rich_memory_store,
                current_regime="bull",
                regime_confidence=1.0,
                agent_id=agent_id,
            )
            assert len(filtered) == 60, f"Non-circuit agent {agent_id} was incorrectly filtered"
            regimes = {m["metadata"]["market_regime"] for m in filtered}
            assert regimes == {"bull", "bear", "sideways"}


# ==============================================================================
# 3. Absolute Contradicting Regime Zero-Leakage Tests
# ==============================================================================

class TestZeroLeakageUnderHighConfidence:
    """Empirically verifies that ZERO contradicting regime memories leak when conf >= 0.5."""

    @pytest.mark.parametrize("target_regime,forbidden_regimes", [
        ("bull", {"bear", "sideways"}),
        ("bear", {"bull", "sideways"}),
        ("sideways", {"bull", "bear"}),
    ])
    def test_zero_leakage_all_regimes(self, rich_memory_store, target_regime, forbidden_regimes):
        """When conf >= 0.5, no memory from forbidden regimes may appear in the result."""
        filtered = circuit_breaker_memory_filter(
            rich_memory_store,
            current_regime=target_regime,
            regime_confidence=0.75,
            agent_id="trader_v2",
        )
        assert len(filtered) == 20
        for m in filtered:
            actual = m["metadata"]["market_regime"]
            assert actual == target_regime
            assert actual not in forbidden_regimes, f"Leakage detected: {actual} found in {target_regime} query!"

    def test_case_and_whitespace_insensitivity_leakage_defense(self, rich_memory_store):
        """Queries with uppercase/whitespace regime names must properly match without leaking."""
        variations = [" BULL ", "Bull\n", "BULL", "  bull  "]
        for var in variations:
            filtered = circuit_breaker_memory_filter(
                rich_memory_store,
                current_regime=var,
                regime_confidence=0.9,
                agent_id="bull_researcher_v2",
            )
            assert len(filtered) == 20
            assert all(m["metadata"]["market_regime"] == "bull" for m in filtered)

    def test_memories_with_messy_stored_regimes(self):
        """Memories stored with messy casing or trailing whitespace are matched cleanly."""
        messy_memories = [
            {"id": "m1", "metadata": {"market_regime": " BULL "}},
            {"id": "m2", "metadata": {"market_regime": "bull"}},
            {"id": "m3", "metadata": {"market_regime": "Bear"}},
            {"id": "m4", "metadata": {"market_regime": "SIDEWAYS"}},
        ]
        filtered = circuit_breaker_memory_filter(
            messy_memories,
            current_regime="bull",
            regime_confidence=0.8,
            agent_id="trader_v2",
        )
        assert len(filtered) == 2
        assert {m["id"] for m in filtered} == {"m1", "m2"}


# ==============================================================================
# 4. Cross-Regime Retrieval When Confidence < 0.5
# ==============================================================================

class TestCrossRegimeRetrieval:
    """Verifies that all memories (including cross-regime) are returned when conf < 0.5."""

    @pytest.mark.parametrize("conf", [0.4999, 0.4, 0.25, 0.1, 0.0])
    def test_cross_regime_retained_under_low_confidence(self, rich_memory_store, conf):
        """Circuit breaker is disabled; all 60 memories must be returned intact."""
        filtered = circuit_breaker_memory_filter(
            rich_memory_store,
            current_regime="bull",
            regime_confidence=conf,
            agent_id="research_manager_v2",
        )
        assert len(filtered) == 60
        # Preserves order and all regimes
        assert filtered == rich_memory_store

    def test_cross_regime_returns_copy_not_in_place_mutation(self, rich_memory_store):
        """Bypassed return returns a new list copy to avoid unintended caller mutation."""
        res = circuit_breaker_memory_filter(
            rich_memory_store,
            current_regime="bull",
            regime_confidence=0.3,
            agent_id="trader_v2",
        )
        assert res is not rich_memory_store
        assert res == rich_memory_store


# ==============================================================================
# 5. Empty Stores, Missing Metadata & Malformed Data Stress Tests
# ==============================================================================

class TestMalformedAndEdgeCaseResilience:
    """Stress tests malformed metadata, None objects, empty stores, and corrupt types."""

    def test_empty_memory_list_returns_empty_safely(self):
        """Empty input list returns empty list without error."""
        assert circuit_breaker_memory_filter([], "bull", 0.9, agent_id="trader_v2") == []
        assert circuit_breaker_memory_filter([], "bear", 0.3, agent_id="trader_v2") == []

    def test_missing_metadata_dict(self):
        """Memories lacking a 'metadata' key default to sideways."""
        raw_memories = [
            {"id": "no_meta_1", "content": "Just content"},
            {"id": "no_meta_2", "content": "Another content"},
            {"id": "bull_meta", "content": "Bull content", "metadata": {"market_regime": "bull"}},
        ]
        # In bull market (conf >= 0.5), no-meta items default to sideways and are NOT leaked into bull
        filtered_bull = circuit_breaker_memory_filter(raw_memories, "bull", 0.9, agent_id="trader_v2")
        assert len(filtered_bull) == 1
        assert filtered_bull[0]["id"] == "bull_meta"

        # In sideways market (conf >= 0.5), no-meta items default to sideways and match sideways
        filtered_sideways = circuit_breaker_memory_filter(raw_memories, "sideways", 0.9, agent_id="trader_v2")
        assert len(filtered_sideways) == 2
        assert {m["id"] for m in filtered_sideways} == {"no_meta_1", "no_meta_2"}

    def test_none_or_malformed_metadata_types(self):
        """Memories where metadata is None, string, list, int, etc. don't raise exceptions."""
        malformed = [
            {"id": "m_none", "metadata": None},
            {"id": "m_str", "metadata": "corrupted_string"},
            {"id": "m_list", "metadata": [1, 2, 3]},
            {"id": "m_int", "metadata": 42},
            {"id": "m_bull", "metadata": {"market_regime": "bull"}},
        ]
        # Querying bull with high confidence: only m_bull matches
        res = circuit_breaker_memory_filter(malformed, "bull", 0.8, agent_id="trader_v2")
        assert len(res) == 1
        assert res[0]["id"] == "m_bull"

    def test_malformed_regime_values_inside_metadata(self):
        """Metadata containing invalid, numeric, or empty regimes."""
        weird_regimes = [
            {"id": "w1", "metadata": {"market_regime": None}},
            {"id": "w2", "metadata": {"market_regime": ""}},
            {"id": "w3", "metadata": {"market_regime": "   "}},
            {"id": "w4", "metadata": {"market_regime": 123}},
            {"id": "w5", "metadata": {"market_regime": "crash_apocalypse"}},
            {"id": "w6", "metadata": {"market_regime": "bull"}},
        ]
        res = circuit_breaker_memory_filter(weird_regimes, "bull", 0.8, agent_id="trader_v2")
        assert len(res) == 1
        assert res[0]["id"] == "w6"

    def test_object_with_attributes_rather_than_dict(self):
        """Items that are custom objects with .metadata attribute instead of dict subscript."""
        class MockObj:
            def __init__(self, obj_id, regime):
                self.id = obj_id
                self.metadata = {"market_regime": regime}

        items = [
            MockObj("o1", "bull"),
            MockObj("o2", "bear"),
            MockObj("o3", "bull"),
        ]
        filtered = circuit_breaker_memory_filter(items, "bull", 0.8, agent_id="trader_v2")
        assert len(filtered) == 2
        assert [o.id for o in filtered] == ["o1", "o3"]

    def test_store_metadata_normalization_extreme_resilience(self):
        """Mem0AgentMemory._normalize_store_metadata handles corrupt, extreme, or empty dictionaries."""
        # Extreme negative / positive quintile and brier
        norm = Mem0AgentMemory._normalize_store_metadata({
            "volatility_quintile": -9999,
            "brier_calibration_error": -50.0,
            "market_regime": "UNKNOWN",
        })
        assert norm["volatility_quintile"] == 1
        assert norm["brier_calibration_error"] == 0.0
        assert norm["market_regime"] == "sideways"

        norm_high = Mem0AgentMemory._normalize_store_metadata({
            "volatility_quintile": 9999,
            "brier_calibration_error": 12.345,
            "market_regime": "BEAR",
        })
        assert norm_high["volatility_quintile"] == 5
        assert norm_high["brier_calibration_error"] == 12.345
        assert norm_high["market_regime"] == "bear"

        # None inputs
        assert Mem0AgentMemory._normalize_store_metadata(None)["market_regime"] == "sideways"
        assert Mem0AgentMemory._normalize_recall_filters(None)["market_regime"] == "sideways"


# ==============================================================================
# 6. Mem0AgentMemory & AgentMemory Integration Tests
# ==============================================================================

class TestMemorySearchIntegration:
    """Stress tests Mem0AgentMemory.search_memories and AgentMemory.search_memories."""

    class MockItem:
        def __init__(self, item_id, text, regime):
            self.id = item_id
            self.memory = text
            self.score = 0.92
            self.metadata = {
                "market_regime": regime,
                "volatility_quintile": 3,
                "brier_calibration_error": 0.05,
                "legacy_situation": text,
            }

    def test_mem0_search_priority_resolution(self):
        """Tests that resolution priority for regime & confidence works:
        1. Explicit current_regime/regime_confidence
        2. state dict
        3. filter_metadata dict
        """
        mem = Mem0AgentMemory("trader_v2")
        mock_svc = MagicMock()
        mock_svc.recall.return_value = [
            self.MockItem("1", "Bull note", "bull"),
            self.MockItem("2", "Bear note", "bear"),
        ]

        with patch("core.memory.service.get_memory_service", return_value=mock_svc):
            # Priority 1: explicit arguments override state and filter_metadata
            res1 = mem.search_memories(
                query="test",
                current_regime="bear",
                regime_confidence=0.9,
                state={"market_regime": "bull", "regime_confidence": 0.9},
                filter_metadata={"market_regime": "sideways", "regime_confidence": 0.2},
            )
            assert len(res1) == 1
            assert res1[0]["metadata"]["market_regime"] == "bear"

            # Priority 2: state overrides filter_metadata
            res2 = mem.search_memories(
                query="test",
                state={"market_regime": "bull", "regime_confidence": 0.9},
                filter_metadata={"market_regime": "sideways", "regime_confidence": 0.2},
            )
            assert len(res2) == 1
            assert res2[0]["metadata"]["market_regime"] == "bull"

            # Priority 3: filter_metadata used when state and explicit args absent
            res3 = mem.search_memories(
                query="test",
                filter_metadata={"market_regime": "bear", "regime_confidence": 0.9},
            )
            assert len(res3) == 1
            assert res3[0]["metadata"]["market_regime"] == "bear"

    def test_mem0_candidate_overfetch_prevents_starvation(self):
        """Mem0AgentMemory requests max(n_results * 3, 15) when circuit breaker is active,
        ensuring that filtering out contradictory regimes doesn't prematurely starve candidate results."""
        mem = Mem0AgentMemory("trader_v2")
        mock_svc = MagicMock()
        mock_svc.recall.return_value = []

        with patch("core.memory.service.get_memory_service", return_value=mock_svc):
            # Asking for n_results = 2 in high-confidence bull
            mem.search_memories("query", n_results=2, current_regime="bull", regime_confidence=0.8)
            recall_call_args = mock_svc.recall.call_args[1]
            # Overfetch limit should be max(2*3, 15) = 15
            assert recall_call_args["limit"] == 15

            # In low-confidence regime (conf < 0.5), overfetch is not needed (limit = n_results)
            mem.search_memories("query", n_results=2, current_regime="bull", regime_confidence=0.3)
            recall_call_args_low = mock_svc.recall.call_args[1]
            assert recall_call_args_low["limit"] == 2

    def test_agent_memory_circuit_breaker_integration(self):
        """Tests AgentMemory (vector store backend) circuit breaker integration."""
        mock_embedding_manager = MagicMock()
        mock_embedding_manager.get_embedding.return_value = ([0.1] * 1024, "mock_provider")
        mock_embedding_manager.get_embedding_dimension.return_value = 1024

        with patch("core.memory.memory_manager.VectorStoreManager") as mock_vsm_cls:
            mock_vsm = MagicMock()
            mock_collection = MagicMock()
            mock_vsm.get_or_create_collection.return_value = mock_collection
            mock_vsm_cls.return_value = mock_vsm

            agent_mem = AgentMemory(agent_id="trader_v2", embedding_manager=mock_embedding_manager)

            # Collection has 6 items
            mock_collection.count.return_value = 6
            mock_collection.query.return_value = {
                "documents": [["doc1", "doc2", "doc3", "doc4", "doc5", "doc6"]],
                "metadatas": [[
                    {"market_regime": "bull"},
                    {"market_regime": "bear"},
                    {"market_regime": "bull"},
                    {"market_regime": "bear"},
                    {"market_regime": "sideways"},
                    {"market_regime": "bull"},
                ]],
                "distances": [[0.1, 0.15, 0.2, 0.25, 0.3, 0.35]],
            }

            # Search with conf >= 0.5 in bear regime -> only bear items returned
            results_bear = agent_mem.search_memories(
                query="bearish signal",
                n_results=5,
                current_regime="bear",
                regime_confidence=0.8,
            )
            assert len(results_bear) == 2
            assert all(r["metadata"]["market_regime"] == "bear" for r in results_bear)

            # Search with conf < 0.5 in bear regime -> circuit bypassed, cross-regime returned
            results_bypassed = agent_mem.search_memories(
                query="signal",
                n_results=5,
                current_regime="bear",
                regime_confidence=0.45,
            )
            assert len(results_bypassed) == 5
            regimes = {r["metadata"]["market_regime"] for r in results_bypassed}
            assert len(regimes) > 1

            # Empty collection returns []
            mock_collection.count.return_value = 0
            assert agent_mem.search_memories("query", current_regime="bear") == []

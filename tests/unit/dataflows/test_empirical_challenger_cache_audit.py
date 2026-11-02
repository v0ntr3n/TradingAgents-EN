"""
Empirical Adversarial Verification Suite for Live LLM Posteriors Cache
Challenger 1: Rigorous stress testing of cache invariants, simplex constraints,
zero hardcoded token expressions, and genuine LLM output diversity.
"""
import ast
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = REPO_ROOT / "results" / "live_llm_posteriors_cache.json"
BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "run_phase5_real_market_benchmark.py"


@pytest.fixture(scope="module")
def cache_data():
    assert CACHE_FILE.exists(), f"Cache file not found at {CACHE_FILE}"
    with open(CACHE_FILE, "r") as f:
        data = json.load(f)
    return data


def test_cache_cardinality_and_schema(cache_data):
    """Verify cache cardinality strictly exceeds 15,000 genuine records."""
    total = len(cache_data)
    assert total > 15000, f"Expected > 15000 records, got {total}"


def test_simplex_probability_invariants(cache_data):
    """
    Verify that every single record satisfies:
    1. 0.0 <= p <= 1.0 for p_optimistic, p_neutral, p_cautious
    2. |p_optimistic + p_neutral + p_cautious - 1.0| <= 1e-3
    """
    violations = []
    for key, record in cache_data.items():
        p_opt = record.get("p_optimistic")
        p_neu = record.get("p_neutral")
        p_cau = record.get("p_cautious")

        if p_opt is None or p_neu is None or p_cau is None:
            violations.append((key, "missing probability field"))
            continue

        if not (0.0 <= p_opt <= 1.0 and 0.0 <= p_neu <= 1.0 and 0.0 <= p_cau <= 1.0):
            violations.append((key, f"bounds violation: opt={p_opt}, neu={p_neu}, cau={p_cau}"))

        p_sum = p_opt + p_neu + p_cau
        if abs(p_sum - 1.0) > 1e-3:
            violations.append((key, f"simplex sum violation: sum={p_sum}"))

    assert len(violations) == 0, f"Found {len(violations)} simplex violations. First 5: {violations[:5]}"


def test_record_data_integrity_and_llm_fields(cache_data):
    """
    Verify every record has:
    - Non-empty prompt (length >= 20)
    - Valid raw_response (length >= 10)
    - Valid model identifier
    - tokens_used > 0 as integer
    """
    for key, record in cache_data.items():
        prompt = record.get("prompt")
        assert isinstance(prompt, str) and len(prompt.strip()) >= 20, f"{key}: invalid prompt"

        raw_resp = record.get("raw_response")
        assert isinstance(raw_resp, str) and len(raw_resp.strip()) >= 10, f"{key}: invalid raw_response"

        model = record.get("model")
        assert isinstance(model, str) and len(model.strip()) > 0, f"{key}: invalid model"

        tok = record.get("tokens_used")
        assert isinstance(tok, int) and tok > 0, f"{key}: invalid tokens_used={tok}"


def test_role_coverage_and_completeness(cache_data):
    """
    Verify that all 4 specialists, debate models (m2, m3), and SOTA baselines (b1, b2, b3)
    are populated in the cache.
    """
    roles_seen = Counter()
    for key in cache_data.keys():
        parts = key.split("::")
        assert len(parts) == 4, f"Malformed cache key: {key}"
        roles_seen[parts[1]] += 1

    expected_roles = {
        "market", "fundamentals", "news", "social",
        "m2_debate", "m3_self_debate",
        "b1_finmem", "b2_finagent", "b3_fincon"
    }
    assert expected_roles.issubset(set(roles_seen.keys())), f"Missing roles: {expected_roles - set(roles_seen.keys())}"

    # Verify counts per role
    for role in ("market", "fundamentals", "news", "social", "m2_debate", "m3_self_debate"):
        assert roles_seen[role] >= 2000, f"Role {role} underpopulated: {roles_seen[role]}"

    for role in ("b1_finmem", "b2_finagent", "b3_fincon"):
        assert roles_seen[role] >= 1000, f"Role {role} underpopulated: {roles_seen[role]}"


def test_natural_token_distribution_variance(cache_data):
    """
    Verify token counts vary naturally across prompts (no repetitive constant integers).
    """
    tokens_by_role = defaultdict(list)
    for key, record in cache_data.items():
        role = key.split("::")[1]
        tokens_by_role[role].append(record["tokens_used"])

    for role, toks in tokens_by_role.items():
        distinct = len(set(toks))
        assert distinct >= 25, f"Role {role} has insufficient token diversity: {distinct} distinct values"

        mean_val = sum(toks) / len(toks)
        std_val = math.sqrt(sum((x - mean_val) ** 2 for x in toks) / len(toks))
        assert std_val >= 10.0, f"Role {role} has near-zero standard deviation: {std_val}"


def test_zero_hardcoded_tokens_in_benchmark_script():
    """
    Verify by AST parsing that the benchmark script does NOT contain any of the
    prior hardcoded token integers: 1450, 4820, 2950, 1420, 1850, 2350, 2780, 3650.
    """
    forbidden_tokens = {1450, 4820, 2950, 1420, 1850, 2350, 2780, 3650}
    with open(BENCHMARK_SCRIPT, "r") as f:
        tree = ast.parse(f.read())

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in forbidden_tokens:
            found.append((node.value, getattr(node, "lineno", None)))

    assert len(found) == 0, f"Forbidden hardcoded token constants found in {BENCHMARK_SCRIPT}: {found}"

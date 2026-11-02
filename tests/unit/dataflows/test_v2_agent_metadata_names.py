import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_METADATA = {
    "core/agents/adapters/bull_researcher_v2.py": {
        "id": "bull_researcher_v2",
        "name": "Optimistic Scenario Researcher v2.0",
        "description": "Construct an optimistic but restrained research argument based on existing materials, and refine the premise, evidence chain and observation signals",
        "category": "RESEARCHER",
        "version": "2.0.0",
        "license_tier": "FREE",
        "report_label": " [Optimistic Scenario Study v2]",
    },
    "core/agents/adapters/bear_researcher_v2.py": {
        "id": "bear_researcher_v2",
        "name": "Prudential Scenario Researcher v2.0",
        "description": "Construct a prudent research argument based on existing materials and refine risks, vulnerabilities and boundaries of judgment.",
        "category": "RESEARCHER",
        "version": "2.0.0",
        "license_tier": "FREE",
        "report_label": " [Prudential Scenario Study v2]",
    },
    "core/agents/adapters/index_analyst_v2.py": {
        "id": "index_analyst_v2",
        "name": "Market Analyst v2.0",
        "description": "Analyze market index trends and market environment, and refine systemic risks and key observation signals",
        "category": "ANALYST",
        "version": "2.0.0",
        "license_tier": "FREE",
        "report_label": " [Market analysis v2]",
    },
    "core/agents/adapters/sector_analyst_v2.py": {
        "id": "sector_analyst_v2",
        "name": "Sector Analyst v2.0",
        "description": "Analyze industry trends, sector rotation and peer comparison, and refine structural changes and risk sources",
        "category": "ANALYST",
        "version": "2.0.0",
        "license_tier": "FREE",
        "report_label": " [Sector analysis v2]",
    },
    "core/agents/adapters/research_manager_v2.py": {
        "id": "research_manager_v2",
        "name": "research integrator v2.0",
        "description": "Comprehensive research on optimistic and cautious scenarios to form balanced research conclusions and key observations",
        "category": "MANAGER",
        "version": "2.0.0",
        "license_tier": "FREE",
        "report_label": " [Balanced research conclusion v2]",
    },
    "core/agents/adapters/risk_manager_v2.py": {
        "id": "risk_manager_v2",
        "name": "risk assessor v2.0",
        "description": "Host the robustness review, integrate multiple perspectives, and formulate comprehensive research conclusions after the risk review (outputting research observations does not constitute investment advice)",
        "category": "MANAGER",
        "version": "2.0.0",
        "license_tier": "FREE",
        "report_label": " [Risk review conclusion v2] ",
    },
    "core/agents/adapters/risky_analyst_v2.py": {
        "id": "risky_analyst_v2",
        "name": "Highly Resilient Scenario Analyst v2.0",
        "description": "Review the research conclusions from the perspective of whether they can be revised upward, and identify strengthened catalysts, high-requirement prerequisites and additional verification signals",
        "category": "RISK",
        "version": "2.0.0",
        "license_tier": "FREE",
        "report_label": " [Highly elastic scenario research]",
    },
    "core/agents/adapters/safe_analyst_v2.py": {
        "id": "safe_analyst_v2",
        "name": "Defense Scenario Analyst v2.0",
        "description": "Review the research conclusions from the perspective that are most likely to fail, and identify fragile premises, risk sources and downward revision triggering conditions",
        "category": "RISK",
        "version": "2.0.0",
        "license_tier": "FREE",
        "report_label": " [Defense Scenario Study]",
    },
    "core/agents/adapters/neutral_analyst_v2.py": {
        "id": "neutral_analyst_v2",
        "name": "Baseline Scenario Analyst v2.0",
        "description": "Balance optimistic and cautious materials, determine the most stable baseline scenario at present, and identify consensus, conflict points and information gaps",
        "category": "RISK",
        "version": "2.0.0",
        "license_tier": "FREE",
        "report_label": " [Neutral risk assessment]",
    },
    "core/agents/adapters/trader_v2.py": {
        "id": "trader_v2",
        "name": "research integrator v2.0",
        "description": "Generate user version of research briefing based on comprehensive research conclusions after risk review",
        "category": "TRADER",
        "version": "2.0.0",
        "license_tier": "FREE",
        "report_label": " [User version research briefing v2]",
    },
}


def _extract_metadata(file_path: Path) -> dict[str, str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        if not any(isinstance(target, ast.Name) and target.id == "metadata" for target in node.targets):
            continue

        if not isinstance(node.value, ast.Call):
            continue

        func = node.value.func
        func_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if func_name != "AgentMetadata":
            continue

        extracted = {}
        for keyword in node.value.keywords:
            if keyword.arg not in {"id", "name", "description", "category", "version", "license_tier", "report_label"}:
                continue
            if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                extracted[keyword.arg] = keyword.value.value
            elif isinstance(keyword.value, ast.Attribute):
                extracted[keyword.arg] = keyword.value.attr

        return extracted

    raise AssertionError(f"Not here {file_path} found in AgentMetadata")


@pytest.mark.parametrize("relative_path, expected", EXPECTED_METADATA.items())
def test_v2_agent_metadata_matches_release_names(relative_path: str, expected: dict[str, str]) -> None:
    actual = _extract_metadata(REPO_ROOT / relative_path)

    for key, value in expected.items():
        assert actual.get(key) == value
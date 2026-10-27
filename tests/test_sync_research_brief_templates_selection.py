import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "template_upgrades" / "sync_research_brief_templates_to_mongodb.py"
MODULE_SPEC = importlib.util.spec_from_file_location("sync_research_brief_templates_to_mongodb", MODULE_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)


select_export_template = MODULE.select_export_template
select_db_doc_for_sync = MODULE._select_db_doc_for_sync


def test_select_export_template_prefers_system_template_over_copy() -> None:
    candidates = [
        {
            "agent_name": "market_analyst_v2",
            "preference_type": "neutral",
            "template_name": "Market Analyst v2.0 - Neutral (Copy 2026/01/11 21:34:16) ",
            "is_system": False,
            "status": "active",
            "content": {"analysis_requirements": "📊 **Output format requirements (must be strictly adhered to):**"},
        },
        {
            "agent_name": "market_analyst_v2",
            "preference_type": "neutral",
            "template_name": "Market Analyst v2.0 - Neutral",
            "is_system": True,
            "status": "active",
            "content": {"analysis_requirements": "## 1. Core Observations"},
        },
    ]

    selected = select_export_template(candidates, "market_analyst_v2", "neutral")

    assert selected["is_system"] is True
    assert selected["template_name"] == "Market Analyst v2.0 - Neutral"
    assert selected["content"]["analysis_requirements"] == "## 1. Core Observations"


def test_select_export_template_supports_fundamentals_canonical_name() -> None:
    candidates = [
        {
            "agent_name": "fundamentals_analyst_v2",
            "preference_type": "neutral",
            "template_name": "Fundamental Analyst v2.0 - Neutral (Copy 2026/01/11 21:34:06) ",
            "is_system": False,
            "status": "active",
            "content": {"output_format": "## 📊 Fundamental analysis report (neutral perspective)"},
        },
        {
            "agent_name": "fundamentals_analyst_v2",
            "preference_type": "neutral",
            "template_name": "Fundamental Analyst v2.0 - Neutral",
            "is_system": True,
            "status": "active",
            "content": {"output_format": "Use Markdown to output: 1. Core observations; 2. Financial and operating signals; 3. Valuation background; 4. Impact on the overall research conclusion; 5. Issues to be verified."},
        },
    ]

    selected = select_export_template(candidates, "fundamentals_analyst_v2", "neutral")

    assert selected["is_system"] is True
    assert selected["template_name"] == "Fundamental Analyst v2.0 - Neutral"
    assert "core observation" in selected["content"]["output_format"]


def test_select_export_template_supports_social_and_sector_canonical_names() -> None:
    social_candidates = [
        {
            "agent_name": "social_analyst_v2",
            "preference_type": "neutral",
            "template_name": "Social Analyst v2.0 - Neutral (Copy 2026/01/11 21:33:55) ",
            "is_system": False,
            "status": "active",
            "content": {"analysis_requirements": "Legacy Sentiment Analysis"},
        },
        {
            "agent_name": "social_analyst_v2",
            "preference_type": "neutral",
            "template_name": "Social Analyst v2.0 - Neutral",
            "is_system": True,
            "status": "active",
            "content": {"analysis_requirements": "## Emotional direction and heat"},
        },
    ]
    sector_candidates = [
        {
            "agent_name": "sector_analyst_v2",
            "preference_type": "neutral",
            "template_name": "Industry Analyst v2.0 - Neutral (Copy 2026/01/11 21:33:57) ",
            "is_system": False,
            "status": "active",
            "content": {"analysis_requirements": "Old version industry analysis"},
        },
        {
            "agent_name": "sector_analyst_v2",
            "preference_type": "neutral",
            "template_name": "Industry Analyst v2.0 - Neutral",
            "is_system": True,
            "status": "active",
            "content": {"analysis_requirements": "## Industry prosperity"},
        },
    ]

    social_selected = select_export_template(social_candidates, "social_analyst_v2", "neutral")
    sector_selected = select_export_template(sector_candidates, "sector_analyst_v2", "neutral")

    assert social_selected["template_name"] == "Social Analyst v2.0 - Neutral"
    assert sector_selected["template_name"] == "Industry Analyst v2.0 - Neutral"
    assert "Emotional direction and heat" in social_selected["content"]["analysis_requirements"]
    assert "Industry prosperity" in sector_selected["content"]["analysis_requirements"]


def test_select_db_doc_for_sync_prefers_system_template_and_archives_copy() -> None:
    export_doc = {
        "template_name": "News Analyst v2.0 - Neutral",
        "content": {"analysis_requirements": "## core event"},
    }
    candidates = [
        {
            "_id": "system-id",
            "agent_name": "news_analyst_v2",
            "preference_type": "neutral",
            "template_name": "News Analyst v2.0 - Neutral",
            "is_system": True,
            "status": "active",
            "version": 3,
            "remark": "Formal template",
        },
        {
            "_id": "copy-id",
            "agent_name": "news_analyst_v2",
            "preference_type": "neutral",
            "template_name": "News Analyst v2.0 - Neutral (Copy 2026/02/12 13:51:42) ",
            "is_system": False,
            "status": "active",
            "version": 6,
            "remark": "copy template",
        },
    ]

    selected, duplicates = select_db_doc_for_sync(candidates, export_doc)

    assert selected["_id"] == "system-id"
    assert [item["_id"] for item in duplicates] == ["copy-id"]
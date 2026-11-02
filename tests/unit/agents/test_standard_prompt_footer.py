import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_all_export_templates_include_standard_prompt_footer() -> None:
    templates = json.loads((ROOT / "exports" / "current_db_templates.json").read_text(encoding="utf-8"))

    checked = 0
    for item in templates:
        content = item.get("content")
        if not isinstance(content, dict) or "system_prompt" not in content:
            continue

        checked += 1
        system_prompt = str(content.get("system_prompt") or "")
        assert "Please use Chinese and conduct analysis based on real data." in system_prompt
        assert "This analysis report is for reference only and does not constitute investment advice." in system_prompt

    assert checked > 0


def test_all_export_templates_have_single_disclaimer_block() -> None:
    templates = json.loads((ROOT / "exports" / "current_db_templates.json").read_text(encoding="utf-8"))

    checked = 0
    for item in templates:
        content = item.get("content")
        if not isinstance(content, dict) or "system_prompt" not in content:
            continue

        checked += 1
        system_prompt = str(content.get("system_prompt") or "")
        assert system_prompt.count("**Disclaimer**") == 1
        assert system_prompt.count("This analysis report is for reference only and does not constitute investment advice.") == 1

    assert checked > 0
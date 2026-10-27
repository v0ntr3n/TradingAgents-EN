# -*- coding: utf-8 -*-
"""Recent search fast path vs user generated external skill routing give way test.

Background (Real Flaw): A user asked Ask about the sales changes of various models in the industry in the past six months , and was answered by the stock era
Keywords fast path ("Recently"+"change") Hijack go to web search before LLM tool selection,
The installed sales skill of Knowing Car Emperor has no chance to appear at all.

Repair: After the fast path hits the keyword, first use the registry source=generated Skill metadata
Make way for data-driven domain word matching if it can be taken over by a dedicated Skill.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.services.intelligent_assistant_service import (
    _domain_terms,
    _matches_generated_skill,
    _should_use_recent_search,
)


def _skill(tool_id, name, description, when_to_use="", fc_enabled=True):
    return SimpleNamespace(
        id=tool_id,
        name=name,
        description=description,
        when_to_use=when_to_use,
        fc_enabled=fc_enabled,
    )


_DCD_SKILL = _skill(
    "dongchedi_car_monthly_sales_rank",
    "Inquiry on the national monthly sales list of Undercardi",
    "Call the National Chedi National Monthly Sales List interface to obtain vehicle model sales data by month, list type and other parameters."
    "It also supports filtering monthly sales of each vehicle model by brand (such as Wenjie).",
)


class TestDomainTerms:
    def test_extracts_chinese_bigrams_and_english_tokens(self):
        terms = _domain_terms("Wenjie M9 model sales")
        assert "Ask the world" in terms
        assert "car model" in terms
        assert "Sales volume" in terms
        assert "m9" in terms

    def test_stopgrams_removed(self):
        terms = _domain_terms("Sales data interface")
        assert "Sales volume" in terms
        assert "data" not in terms
        assert "interface" not in terms


class TestGeneratedSkillRouting:
    def _registry(self, skills):
        reg = SimpleNamespace(get_external_skills=lambda: skills)
        return patch("core.tools.get_tool_registry", lambda: reg)

    def test_dongchedi_sales_question_bypasses_fast_search(self):
        """Real Accident Sentence: You must hit the car-savvy Skill and give way to the fast path"""
        # First confirm that the sentence itself will hit the old fast path keyword (otherwise the test is meaningless)
        msg = "Please help me check the sales changes of various models in the industry in the past six months."
        assert _should_use_recent_search(msg)

        with self._registry([_DCD_SKILL]):
            hit = _matches_generated_skill(msg)
        assert hit is not None
        assert hit[0] == "dongchedi_car_monthly_sales_rank"

    def test_stock_holding_question_still_uses_fast_search(self):
        """Original stock scenario: There is no domain overlap with the external Skill and should not give way."""
        msg = "Berkshire Hathaway s latest shareholding changes"
        assert _should_use_recent_search(msg)
        with self._registry([_DCD_SKILL]):
            assert _matches_generated_skill(msg) is None

    def test_single_overlap_not_enough(self):
        """The co-occurrence of only one domain word is not counted as a hit (to prevent misjudgment of accidental co-occurrence)"""
        # Contains only one field intersection word "sales"
        skill = _skill("x", "A certain list", "Count sales of a product")
        with self._registry([skill]):
            # ""Recent Sales"——Only with this skill"Sales volume"an intersection
            assert _matches_generated_skill("How sales have changed recently") is None

    def test_disabled_skill_ignored(self):
        disabled = _skill("x", "Understand car sales", "Ask the world s car sales", fc_enabled=False)
        with self._registry([disabled]):
            assert _matches_generated_skill("Recent sales changes of Wenjie models") is None

    def test_no_external_skills_returns_none(self):
        with self._registry([]):
            assert _matches_generated_skill("Recent sales changes of Wenjie models") is None

    def test_generic_non_sales_question_not_routed_to_dcd(self):
        """Even if a purely news/announcement question mentions the recent past, it should not be mistakenly caught by domain matching."""
        msg = "Are there any new announcements recently?"
        with self._registry([_DCD_SKILL]):
            assert _matches_generated_skill(msg) is None

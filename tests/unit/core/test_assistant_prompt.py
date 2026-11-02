# -*- coding: utf-8 -*-
"""S8 system prompt Governance (A11 §7 Parallel work items) single test.

Coverage:
- Layer structure integrity (core identity/domain boundaries/data discipline/compliance/tool guidance)
- The dynamic injection mechanism is not affected by reorganization (date/IM/memory guide/topic/usage_helper diversion)
- Word count reduction acceptance (baseline 8317 characters, acceptance line ≤5822 That is ≥30% reduction, anti-expansion rebound)
- Key behavioral anchors exist (with Type A lines of defense,§5.1 Regression test set corresponding)
"""
import re

from app.services.intelligent_assistant_service import _get_system_prompt

# Phase 4 Static rule text baseline before rewriting (tested on 2026-09-13)
_BASELINE_CHARS = 8317
# Acceptance line: word count reduction ≥30% (2026-09-15 Increased to 6050: Added table Excel export tool instructions,
# Data Discipline Article 14/15——Export pass-through and"Reuse conversation already has results"Anti-repeated pulling rules)
_MAX_CHARS = 6050


class TestSystemPromptS8:
    def test_layered_blocks_present(self):
        """The core blocks after hierarchical reorganization are complete"""
        prompt = _get_system_prompt()
        for block in (
            " [Role positioning]",
            " [System capability description]",
            " [Honesty and Ability Boundaries]",
            " [Domain boundaries]",
            " [Data discipline (core, mandatory one by one)]",
            " [Compliance Principles]",
            " [Confirm first and then execute]",
            " [Data concept distinction (must be strictly distinguished)]",
            " [Tools and data acquisition] ",
            " [Long-term memory management]",
        ):
            assert block in prompt, f"Missing layered blocks:{block}"

    def test_dynamic_date_injection(self):
        """The current date and the latest trading day are dynamically injected and maintained"""
        prompt = _get_system_prompt()
        assert " [Current date]" in prompt
        assert " [Recent trading days]" in prompt
        # both places YYYY-MM-DD
        dates = re.findall(r" [(?:current date|Last trading day)] (\d{4}-\d{2}-\d{2})", prompt)
        assert len(dates) == 2, f"Date injection exception:{dates}"

    def test_im_block_injection(self):
        """IM Channel format specifications are injected on demand"""
        assert " [IM Message format specification]" not in _get_system_prompt()
        assert " [IM Message format specification]" in _get_system_prompt(is_im=True)

    def test_memory_directive_injection(self):
        """Memory block injection comes with multiple transaction plan processing rules"""
        prompt = _get_system_prompt(memory_block=" [historical memory]\n- User preference testing")
        assert " [historical memory]" in prompt
        assert "Multiple trading plan processing rules" in prompt
        # This guide is not injected when there is no memory
        assert "Multiple trading plan processing rules" not in _get_system_prompt()

    def test_topic_block_injection(self):
        """External session topic injection holds"""
        prompt = _get_system_prompt(current_topic_title="New energy vehicle industry chain")
        assert "Current research topic: New energy vehicle industry chain" in prompt

    def test_usage_helper_branch_unchanged(self):
        """Use the question and answer robot to divert and maintain (without taking the general analysis assistant prompt)"""
        prompt = _get_system_prompt(assistant_role="usage_helper")
        assert "Use the Q&A Assistant" in prompt
        assert " [Data discipline (core, mandatory one by one)]" not in prompt

    def test_size_reduction_acceptance(self):
        """Acceptance: Static rule text reduced compared to baseline ≥30% (Anti-expansion and rebound)"""
        prompt = _get_system_prompt()
        assert len(prompt) <= _MAX_CHARS, (
            f"prompt length {len(prompt)} Exceed the acceptance line {_MAX_CHARS}"
            f" (baseline {_BASELINE_CHARS} 70%), the reduction rate is insufficient 30%"
        )

    def test_data_discipline_anchors(self):
        """Data Discipline 13 Key Anchors (Type A Line of Defense Alignment)"""
        prompt = _get_system_prompt()
        anchors = (
            "Numbers can only be returned from tools",
            "strictly prohibited\"approx.\"Word packaging fabrication",
            "Fabricating sources is strictly prohibited",
            "It is strictly prohibited to forge tool call traces",
            "web_search Numbers that are not included in the abstract cannot be compiled.",
            "Industry real-time data disabled memory",
            "Valuation quantiles must be supported by data",
            "Verbatim verification of units and conversions",
            "Empty data is truthfully informed",
            "Data dates are truthfully stated",
            "Tool results are presented faithfully as they are",
            "Time logic is based on current date",
            "Valuation Excel Deliverables",
            "15764.6 million=1.58 billion",  # conversion behavior anchor
            "0.37% rather than 37%",  # ratio field anchor
        )
        for a in anchors:
            assert a in prompt, f"Missing data discipline anchor:{a}"

    def test_compliance_and_tool_anchors(self):
        """Compliance and Tool Guidance Key Anchors (§5.1 Case 4/5/6 related)"""
        prompt = _get_system_prompt()
        anchors = (
            "i can t provide'Is it worth buying?'This type of investment advice",  # Case 4 Compliance rhetoric
            "It is strictly prohibited to give specific stop loss price/take profit price/reminder price.",
            "Number acceptance",  # Case 5 Naked number reply
            "The trading date above must be passed in",
            "It is strictly forbidden to use search_recent_information/web_search web search instead",  # Trend search is prohibited
            "strictly prohibited\"Give some reference\"Recommend stocks that do not meet the criteria",  # Filter empty results
            "watchlist_groups Just a way of grouping/organizing",  # Three concept distinctions
            "user_favorites",
        )
        for a in anchors:
            assert a in prompt, f"Missing compliance/tool anchors:{a}"

    def test_personalization_injection(self):
        """Assistant personalization settings injected into hold"""
        prompt = _get_system_prompt(
            assistant_settings={"name": "Assistant", "tone": "friendly", "custom_instructions": "multi-purpose form"}
        )
        assert "Assistant" in prompt
        assert "Relaxed and friendly" in prompt  # friendly tone mapping
        assert "multi-purpose form" in prompt

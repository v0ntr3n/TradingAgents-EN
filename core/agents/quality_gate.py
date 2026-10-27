"""
Analyst reports are quality gated.

in invoke_with_tools() After returning,AnalystAgent.execute() Do light verification before returning.
Tiered downgrade on failure: 1st retry → 2nd mark low_quality → Write the alarm set for the third time.

Design principles:
- Not blocking workflow (marking rather than interrupting)
- Not here invoke_with_tools() Internal inspection (keeps tools looping with single responsibility)
- The first edition is only available in length + blacklist + Conclusion keyword, no data reference check (to avoid accidental killing)

Related documents:
- core/agents/analyst.py: caller
- core/agents/base.py:1022-1043: invoke_with_tools The hidden copy (synchronized with the blacklist)
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Blacklist of cover-up copywriting (synchronized with failed copywriting in base.py)
# If any one of them is hit, the report generation failed.
FALLBACK_BLACKLIST = [
    "Tool execution or model generation has not been completed, and the current conclusion still needs to be verified.",
    "Analysis failed to complete (maximum number of iterations reached",
    "Analysis report generation failed: LLM keeps returning tool calls instead of report content",
    "Analysis report generation failed: LLM keeps returning tool calls",
]

# Concluding keywords (the report contains at least one)
# The lack of these keywords indicates that LLM may only list the data without making a judgment.
CONCLUSION_KEYWORDS = [
    "research observation", "Conclusion", "judge", "point of view", "risk", "opportunity",
    "optimistic", "Prudence", "Neutral", "evidence", "Basis",
    "good", "Bad", "growth", "decline", "shock", "Trend",
    "Follow", "Be alert", "Outlook",
]

# Minimum report length (characters)
MIN_REPORT_LENGTH = 50


@dataclass
class QualityCheckResult:
    """Quality gate check results."""

    is_valid: bool
    reason: str
    severity: str = "ok"  # ok / warning / critical

    @property
    def should_retry(self) -> bool:
        """Whether it should be retried (retry only at critical level, warning only marks not to retry)."""
        return self.severity == "critical" and not self.is_valid


def validate_analyst_report(
    content: str,
    agent_id: str = "",
    ticker: str = "",
) -> QualityCheckResult:
    """Analyst reports are quality gated.

    Check dimensions (first version lightweight):
    1. Report length < 50 character → critical
    2. Hit the blacklist of copywriters → critical
    3. Missing concluding keywords → warning (No retries, just marking)

    Args:
        content: Report content
        agent_id: Used for log positioning
        ticker: Used for log positioning

    Returns:
        QualityCheckResult: is_valid=False The caller should retry or mark low_quality
    """
    # Dimension 1: Empty report or too short
    if not content or not content.strip():
        return QualityCheckResult(
            is_valid=False,
            reason="Report content is empty",
            severity="critical",
        )

    stripped_len = len(content.strip())
    if stripped_len < MIN_REPORT_LENGTH:
        return QualityCheckResult(
            is_valid=False,
            reason=f"Report content is too short ({stripped_len} character < {MIN_REPORT_LENGTH}) ",
            severity="critical",
        )

    # Dimension 2: Hit the blacklist of cover-up copywriters
    for pattern in FALLBACK_BLACKLIST:
        if pattern in content:
            return QualityCheckResult(
                is_valid=False,
                reason=f"Hit the blacklist of copywriters: {pattern[:50]}",
                severity="critical",
            )

    # Dimension 3: Lack of concluding keywords (warning level, only marking without retrying)
    if not any(kw in content for kw in CONCLUSION_KEYWORDS):
        return QualityCheckResult(
            is_valid=False,
            reason="The report lacks conclusive keywords (suggestions/conclusions/judgments/risks, etc.)",
            severity="warning",
        )

    return QualityCheckResult(is_valid=True, reason="", severity="ok")

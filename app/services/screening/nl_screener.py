"""Natural-language stock screening condition parser and delegator."""
from __future__ import annotations

import re
from typing import Any, Dict, List


class NaturalLanguageScreener:
    """Parse common natural-language valuation filters into structured screening conditions."""

    _PE_PATTERN = re.compile(r"pe\s*(?:<|less than|under)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
    _ROE_PATTERN = re.compile(r"roe\s*(?:>|greater than|above|over)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

    @classmethod
    def parse_nl_query(cls, query_text: str) -> List[Dict[str, Any]]:
        """Extract basic numericPE/ROE bounds from a natural language query string."""
        conditions: List[Dict[str, Any]] = []
        text = str(query_text or "")
        pe_match = cls._PE_PATTERN.search(text)
        if pe_match:
            conditions.append({"field": "pe", "min": 0.0, "max": float(pe_match.group(1))})
        roe_match = cls._ROE_PATTERN.search(text)
        if roe_match:
            conditions.append({"field": "roe", "min": float(roe_match.group(1))})
        return conditions

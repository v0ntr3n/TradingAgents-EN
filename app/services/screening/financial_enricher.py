"""Financial ratio and valuation metric enrichment for screened equity rows."""
from __future__ import annotations

from typing import Any, Dict, List


class ScreeningFinancialEnricher:
    """Enrich stock screening rows with standardized PE, PB, ROE, and market cap fields."""

    @staticmethod
    def normalize_financial_row(row: Dict[str, Any]) -> Dict[str, Any]:
        """Return a shallow copy with normalized numeric valuation fields."""
        enriched = dict(row)
        for key in ("pe", "pe_ttm", "pb", "roe", "total_mv", "circ_mv", "pct_chg"):
            val = enriched.get(key)
            if val is not None:
                try:
                    enriched[key] = float(val)
                except (TypeError, ValueError):
                    pass
        return enriched

    @classmethod
    def enrich_rows(cls, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize a batch of screened stock records."""
        return [cls.normalize_financial_row(r) for r in (rows or [])]

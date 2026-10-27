"""Intelligent Assistant Quality Architecture (A11)—— Dictionary and Variety Gate (Stage 4, S4).

Routing related"dictionary knowledge"Converging to one source of fact for this module:

1. ``StockDirectory``: A Stock name→Code directory, from ``stock_basic_info`` **full amount**Load
   And with TTL caching (default 6h), replacing hard-coded stock lists scattered everywhere with once-per-request
   Mongo regex Query;
2. A Stock code extraction (Shanghai and Shenzhen Main Board/GEM/Science and Technology Innovation Board), single regular fact source;
3. The vocabulary list and detection of varieties (Hong Kong stocks/US stocks) are not supported: physically collected from planned_analysis_service,
   Assistant routing and planning analysis share the same vocabulary list, and they no longer store one copy in each place.

Note: Recent search fast path/data pre-check**Intent keyword rules**Not in this module——Its going or staying
 (Retention rules/front-end small model/return to main agent tool selection) still needs to be decided after routing data support
 (Design document D6), currently keep the status quo in the service unchanged.

This module does not import service (to avoid circular dependencies); db is passed in as a parameter.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────── A stock code ───────────────────────────

# Shanghai and Shenzhen Main Board/GEM/Science and Technology Innovation Board (consistent with the _STOCK_CODE_RE behavior of the service before reconstruction;
# The North Exchange code is not within the existing coverage of the pre-check link, and the behavioral coverage will not be expanded this time)
A_SHARE_CODE_RE = re.compile(r"\b(00|30|60|68)\d{4}\b")


def extract_a_share_code(text: str) -> Optional[str]:
    """Extract the first 6-digit CSI A-share code from the text."""
    if not text:
        return None
    match = A_SHARE_CODE_RE.search(text)
    return match.group(0) if match else None


# ─────────────────────────── Not supported varieties (Hong Kong stocks/US stocks)───────────────────────────

# Hong Kong stock keywords (market words + Representative company name; stock_basic_info only contains A shares,
# The list of Hong Kong and US stocks does not have a full data table to access, so it is retained as a static vocabulary list and is maintained in a single place in this module)
HK_STOCK_KEYWORDS: Tuple[str, ...] = (
    "Hong Kong stocks", "Hang Seng", "Hang Seng Index", "H shares", "h shares", "Hong Kong Stock Exchange", "Hong Kong dollar",
    "Tencent Holdings", "Meituan", "Xiaomi Group", "Alibaba-SW", "JD Group-SW",
)

# US stock keywords
US_STOCK_KEYWORDS: Tuple[str, ...] = (
    "US stocks", "Nasdaq", "S&P", "Dow Jones", "NYSE", "NASDAQ",
    "apple inc.", "Tesla", "NVIDIA", "Google", "Amazon", "Microsoft",
    "Chinese concept stocks",
)

# Hong Kong stock code (xxxxx.HK)/US stocks ticker
HK_CODE_PATTERN = re.compile(r"\b\d{5}\.HK\b", re.IGNORECASE)
US_TICKER_PATTERN = re.compile(
    r"(?<![A-Za-z])(AAPL|TSLA|NVDA|GOOGL|GOOG|AMZN|MSFT|META|NFLX|AMD|BABA|JD|PDD|NIO|XPEV|LI)"
    r"(?![A-Za-z])",
    re.IGNORECASE,
)

_HK_MESSAGE = (
    "🚫 **Hong Kong stock analysis is not currently supported**\n\n"
    "The current system focuses on **A stock market** (Shanghai and Shenzhen Stock Exchanges), the Hong Kong stock analysis function is still under development.\n\n"
    "You can try:\n"
    "- Analyze A-share stocks (such as Help me analyze BYD )\n"
    "- Analyze industry sectors (such as How is the new energy vehicle sector? )"
)
_US_MESSAGE = (
    "🚫 **U.S. stock analysis is not currently supported**\n\n"
    "The current system focuses on **A stock market** (Shanghai and Shenzhen Stock Exchanges), the U.S. stock analysis function is still under development.\n\n"
    "You can try:\n"
    "- Analyze A-share stocks (such as Help me analyze CATL )\n"
    "- Analyze industry sectors (such as How has the semiconductor sector been trending recently? )"
)
_US_CODE_MESSAGE = (
    "🚫 **U.S. stock analysis is not currently supported**\n\n"
    "It is detected that you entered the US stock code. The current system focuses on **A stock market** (Shanghai and Shenzhen Stock Exchanges).\n\n"
    "You can try to enter the A-share code (such as 600519, 000858) or stock name for analysis."
)
_HK_CODE_MESSAGE = (
    "🚫 **Hong Kong stock analysis is not currently supported**\n\n"
    "It is detected that you entered the Hong Kong stock code. The current system focuses on **A stock market** (Shanghai and Shenzhen Stock Exchanges).\n\n"
    "You can try to enter the A-share code (such as 600519, 000858) or stock name for analysis."
)


def detect_unsupported_asset(question: str) -> Optional[str]:
    """Check whether the problem involves unsupported stocks (Hong Kong stocks/US stocks); return the prompt copy if hit, otherwise None.

    Consistent with planned_analysis_service historical behavior branch by branch (detection order: Hong Kong stock words →
    US stock words → US stocks ticker → Hong Kong stock code).
    """
    q = (question or "").strip()
    if not q:
        return None

    if any(keyword in q for keyword in HK_STOCK_KEYWORDS):
        return _HK_MESSAGE
    if any(keyword in q for keyword in US_STOCK_KEYWORDS):
        return _US_MESSAGE
    if US_TICKER_PATTERN.search(q):
        return _US_CODE_MESSAGE
    if HK_CODE_PATTERN.search(q):
        return _HK_CODE_MESSAGE
    return None


# ─────────────────────────── A Stock name directory (full quantity + TTL) ───────────────────────────

class StockDirectory:
    """stock_basic_info full name→Code directory (in-process singleton, TTL expiration, lazy refresh).

    - Full load (approximately 16,000 items), replacing the hard-coded list and regex query per request;
    - TTL Internal zero database access; after expiration, the next call triggers a refresh (asyncio.Lock anti-penetration);
    - When the refresh fails, the last successful cache (if any) will continue to be used, and routing will not be blocked due to dictionary failure.
    """

    def __init__(self, ttl_seconds: float = 6 * 3600, clock=time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._name_map: Dict[str, str] = {}
        # Names are sorted in descending order of length: long names are given priority when matching substrings ("Thalys Group"Will not be truncated by short names)
        self._names_desc: List[Tuple[str, str]] = []
        self._loaded_at: Optional[float] = None
        self._lock = asyncio.Lock()

    def is_fresh(self) -> bool:
        return self._loaded_at is not None and (self._clock() - self._loaded_at) < self._ttl

    async def get_name_map(self, db, *, force: bool = False) -> Dict[str, str]:
        """return name→Code Mapping; refreshed when TTL expires or is forced."""
        if not force and self.is_fresh():
            return self._name_map
        async with self._lock:
            # Double check: it may have been refreshed by other coroutines while waiting for the lock.
            if not force and self.is_fresh():
                return self._name_map
            previous = dict(self._name_map)
            mapping: Dict[str, str] = {}
            try:
                async for doc in db["stock_basic_info"].find(
                    {}, {"symbol": 1, "name": 1}
                ):
                    name = (doc.get("name") or "").strip()
                    symbol = (doc.get("symbol") or "").strip()
                    # Consistent with the history loading logic:2~6 Character name; the same name retains the code that appears first
                    if name and symbol and 2 <= len(name) <= 6 and name not in mapping:
                        mapping[name] = symbol
                self._name_map = mapping
                self._names_desc = sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)
                self._loaded_at = self._clock()
                logger.info("[Smart Assistant·Dictionary] Stock name directory has been refreshed: %d Article", len(mapping))
            except Exception as exc:
                logger.warning("[Smart Assistant·Dictionary] Failed to refresh the stock name directory, the old cache is used(%d Article): %s",
                               len(previous), exc)
                # Keep old cache; keep empty map if first load fails
                if previous:
                    self._name_map = previous
                    self._names_desc = sorted(
                        previous.items(), key=lambda kv: len(kv[0]), reverse=True
                    )
                    self._loaded_at = self._clock()
            return self._name_map

    async def resolve_symbol(self, text: str, db) -> Optional[str]:
        """Parse A-share codes from natural language text: 6-digit code first, followed by matching the longest substring of the full name.

        No hard-coded lists——The full catalog has covered the abbreviation (Sailis/Moutai) and the full name with suffix.
        """
        if not text:
            return None
        code = extract_a_share_code(text)
        if code:
            return code
        name_map = await self.get_name_map(db)
        if not name_map:
            return None
        # Exact hit priority (the message itself is a stock name)
        stripped = text.strip()
        if stripped in name_map:
            return name_map[stripped]
        # Long-name-first substring contains matches
        for name, symbol in self._names_desc:
            if name in text:
                return symbol
        return None


# Module-level singleton (service and memory link share the same cache)
stock_directory = StockDirectory()

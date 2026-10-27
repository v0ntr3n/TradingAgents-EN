"""
QuotesService: Provides A-share batch real-time snapshot acquisition (AKShare Oriental Fortune spot interface), with memory TTL cache.
- Do not use Tongda Xin (TDX) as a back-up data source.
- Only used to enrich items before filtering and returning.
"""
from __future__ import annotations

import asyncio
import time
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _safe_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        # Handling commas/percent signs/whitespace in strings
        if isinstance(v, str):
            s = v.strip().replace(",", "")
            if s.endswith("%"):
                s = s[:-1]
            if s == "-" or s == "":
                return None
            return float(s)
        # Processing pandas/numpy numerical values
        return float(v)
    except Exception:
        return None


class QuotesService:
    def __init__(self, ttl_seconds: int = 30) -> None:
        self._ttl = ttl_seconds
        self._cache_ts: float = 0.0
        self._cache: Dict[str, Dict[str, Optional[float]]] = {}
        self._lock = asyncio.Lock()

    async def get_quotes(self, codes: List[str]) -> Dict[str, Dict[str, Optional[float]]]:
        """Get a near-real-time snapshot of a batch of stocks (latest price, change, volume).
        - Priority is given to using the cache; if the cache times out or is empty, a full market snapshot will be refreshed.
        - Returns only the requested codes.
        """
        codes = [c.strip() for c in codes if c]
        now = time.time()
        async with self._lock:
            if self._cache and (now - self._cache_ts) < self._ttl:
                return {c: q for c, q in self._cache.items() if c in codes and q}
            # Refresh the cache (block IO and put it on the thread)
            data = await asyncio.to_thread(self._fetch_spot_akshare)
            self._cache = data
            self._cache_ts = time.time()
            return {c: q for c, q in self._cache.items() if c in codes and q}

    def _fetch_spot_akshare(self) -> Dict[str, Dict[str, Optional[float]]]:
        """Pull quotes through the AKShare Oriental Wealth full market snapshot interface and standardize them into a dictionary.
        Expected columns (common): code, name, latest price, increase or decrease, and transaction volume.
        Different versions may have differences and are compatible with multiple column names.
        """
        try:
            import akshare as ak  # Already used in the project, no additional installation required
            df = ak.stock_zh_a_spot_em()
            if df is None or getattr(df, "empty", True):
                logger.warning("AKShare spot Return empty data")
                return {}
            # Compatible with common column names
            code_col = next((c for c in ["代码", "代码code", "symbol", "股票代码"] if c in df.columns), None)
            price_col = next((c for c in ["最新价", "现价", "最新价(元)", "price", "最新"] if c in df.columns), None)
            pct_col = next((c for c in ["涨跌幅", "涨跌幅(%)", "涨幅", "pct_chg"] if c in df.columns), None)
            amount_col = next((c for c in ["成交额", "成交额(元)", "amount", "成交额(万元)"] if c in df.columns), None)

            if not code_col or not price_col:
                logger.error(f"AKShare spot Missing required column: code={code_col}, price={price_col}")
                return {}

            result: Dict[str, Dict[str, Optional[float]]] = {}
            for _, row in df.iterrows():  # type: ignore
                code_raw = row.get(code_col)
                if not code_raw:
                    continue
                # Standardize stock symbols: remove leading 0s, then pad to 6 digits
                code_str = str(code_raw).strip()
                # If it is a pure number, remove the leading 0 and pad it to 6 digits.
                if code_str.isdigit():
                    code_clean = code_str.lstrip('0') or '0'  # Remove leading 0s, if all 0s, keep one 0
                    code = code_clean.zfill(6)  # Complete to 6 digits
                else:
                    code = code_str.zfill(6)
                close = _safe_float(row.get(price_col))
                pct = _safe_float(row.get(pct_col)) if pct_col else None
                amt = _safe_float(row.get(amount_col)) if amount_col else None
                # If the transaction volume unit is 10,000 yuan, it will be uniformly converted into yuan (some interfaces are 10,000 yuan, there is no forced conversion here, the unit will be displayed on the front end as it is)
                result[code] = {"close": close, "pct_chg": pct, "amount": amt}
            logger.info(f"AKShare spot 拉取完成: {len(result)} 条")
            return result
        except Exception as e:
            logger.error(f"Failed to obtain AKShare real-time snapshot: {e}")
            return {}


_quotes_service: Optional[QuotesService] = None


def get_quotes_service() -> QuotesService:
    global _quotes_service
    if _quotes_service is None:
        _quotes_service = QuotesService(ttl_seconds=30)
    return _quotes_service


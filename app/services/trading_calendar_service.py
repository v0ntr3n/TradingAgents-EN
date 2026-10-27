"""
Trading Calendar Service

Query the latest actual trading day of A shares from Tushare/AkShare when the system starts.
The results are cached in Redis for modules such as JIT data synchronization to accurately determine the freshness of the data.

Redis Key: trading_calendar:last_trade_date
cache format:
  {
    "last_trade_date": "2026-02-27",   # YYYY-MM-DD
    "is_today_trade_day": true,
    "fetched_at": "2026-02-27",        # On the day of this inquiry
    "source": "tushare"
  }

TTL: 25 hours (refreshed every day when the system starts, will not exist indefinitely)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_KEY = "trading_calendar:last_trade_date"
CACHE_TTL_SECONDS = 25 * 3600  # 25 hours, guaranteed to be refreshed at startup every day


class TradingCalendarService:
    """A Stock trading calendar service (single case)"""

    # ------------------------------------------------------------------ #
    # internal tools                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _today_str() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _fmt(raw: str) -> str:
        """Uniformly formatted as YYYY-MM-DD (compatible with YYYYMMDD and YYYY-MM-DD input)"""
        raw = raw.strip()
        if len(raw) == 8 and "-" not in raw:
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return raw

    @staticmethod
    def _is_loop_mismatch_error(error: Exception) -> bool:
        error_text = str(error).lower()
        return "attached to a different loop" in error_text or "different loop" in error_text

    @staticmethod
    def _build_cache_payload(last_trade_date: str, is_today: bool, source: str) -> dict:
        return {
            "last_trade_date": last_trade_date,
            "is_today_trade_day": is_today,
            "fetched_at": TradingCalendarService._today_str(),
            "source": source,
        }

    # ------------------------------------------------------------------ #
    # Get last trading day from external API                                            #
    # ------------------------------------------------------------------ #

    async def _fetch_from_tushare(self) -> Optional[str]:
        """Call tushare daily_basic to go back day by day and find the most recent trading day (YYYY-MM-DD)"""
        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            import asyncio

            provider = get_tushare_provider()
            if not provider.is_available() or provider.api is None:
                return None

            today = datetime.now()
            for delta in range(0, 10):
                d = (today - timedelta(days=delta)).strftime("%Y%m%d")
                try:
                    df = await asyncio.to_thread(
                        provider.api.daily_basic,
                        trade_date=d,
                        fields="ts_code",
                        limit=1,
                    )
                    if df is not None and not df.empty:
                        logger.info(f"📅 [TradingCalendar] Tushare Confirm the latest trading day: {d}")
                        return self._fmt(d)
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"⚠️ [TradingCalendar] Tushare Query failed: {e}")
        return None

    async def _fetch_from_akshare(self) -> Optional[str]:
        """Call akshare tool_trade_date_hist_sina to get the recent trading calendar, whichever is more recent ≤ Today s trading day"""
        try:
            import akshare as ak
            import asyncio
            import pandas as pd

            df = await asyncio.to_thread(ak.tool_trade_date_hist_sina)
            if df is None or df.empty:
                return None

            # Column name may be trade_date or column 0
            col = df.columns[0]
            dates = pd.to_datetime(df[col]).dt.date
            today_d = date.today()
            valid = sorted([d for d in dates if d <= today_d], reverse=True)
            if valid:
                result = valid[0].strftime("%Y-%m-%d")
                logger.info(f"📅 [TradingCalendar] AkShare Confirm the latest trading day: {result}")
                return result
        except Exception as e:
            logger.warning(f"⚠️ [TradingCalendar] AkShare Query failed: {e}")
        return None

    async def _fetch_last_trade_date(self) -> tuple[str, str]:
        """
        By priority (tushare → akshare → Simple lookback) to get the most recent trading day.
        Returns: (last_trade_date: YYYY-MM-DD, source: str)
        """
        result = await self._fetch_from_tushare()
        if result:
            return result, "tushare"

        result = await self._fetch_from_akshare()
        if result:
            return result, "akshare"

        # The final tip: look forward to the first Monday from today~Friday (holidays are not guaranteed to be accurate)
        today = datetime.now()
        for delta in range(0, 5):
            d = today - timedelta(days=delta)
            if d.weekday() < 5:
                fallback = d.strftime("%Y-%m-%d")
                logger.warning(f"⚠️ [TradingCalendar] All APIs fail, falling back to the most recent working day: {fallback}")
                return fallback, "fallback"

        return today.strftime("%Y-%m-%d"), "fallback"

    # ------------------------------------------------------------------ #
    # Redis Read and write                                                          #
    # ------------------------------------------------------------------ #

    async def _redis(self):
        # Prefer using app.core.database by init_database() Initialized asynchronous Redis client,
        # Because lifespan only calls init_db()→init_database(), without calling redis_client.init_redis()
        from app.core.database import get_redis_client
        return get_redis_client()

    async def _read_cache(self) -> Optional[dict]:
        try:
            r = await self._redis()
            raw = await r.get(REDIS_KEY)
            if raw:
                return json.loads(raw)
        except Exception as e:
            if self._is_loop_mismatch_error(e):
                logger.debug("[TradingCalendar] Asynchronous Redis client across event loop, fallback to synchronous Redis read")
                return await asyncio.to_thread(self._read_cache_sync)
            logger.debug(f"[TradingCalendar] Failed to read Redis cache: {e}")
        return None

    @staticmethod
    def _read_cache_sync() -> Optional[dict]:
        try:
            from app.core.database import get_redis_sync_client

            redis_sync = get_redis_sync_client()
            raw = redis_sync.get(REDIS_KEY)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.debug(f"[TradingCalendar] Synchronizing Redis read cache failed: {e}")
        return None

    async def _write_cache(self, last_trade_date: str, is_today: bool, source: str):
        payload = self._build_cache_payload(last_trade_date, is_today, source)
        try:
            r = await self._redis()
            await r.setex(REDIS_KEY, CACHE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))
            logger.info(f"✅ [TradingCalendar] Cached to Redis: {payload}")
        except Exception as e:
            if self._is_loop_mismatch_error(e):
                try:
                    await asyncio.to_thread(self._write_cache_sync, payload)
                    logger.info(f"✅ [TradingCalendar] Redis fallback cache synchronized: {payload}")
                    return
                except Exception as sync_error:
                    logger.warning(f"⚠️ [TradingCalendar] Synchronous Redis fallback write failed: {sync_error}")
            logger.warning(f"⚠️ [TradingCalendar] Writing to Redis cache failed: {e}")

    @staticmethod
    def _write_cache_sync(payload: dict) -> None:
        from app.core.database import get_redis_sync_client

        redis_sync = get_redis_sync_client()
        redis_sync.setex(REDIS_KEY, CACHE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))

    # ------------------------------------------------------------------ #
    # public interface                                                            #
    # ------------------------------------------------------------------ #

    async def warm_up(self):
        """Called when the system starts, refresh the transaction calendar cache (always re-query the API, ignore the old cache)"""
        logger.info("🚀 [TradingCalendar] Start initializing the trading calendar cache...")
        try:
            last_trade_date, source = await self._fetch_last_trade_date()
            is_today = last_trade_date == self._today_str()
            await self._write_cache(last_trade_date, is_today, source)
            logger.info(
                f"✅ [TradingCalendar] 初始化完成: 最近交易日={last_trade_date}, "
                f"Is today a trading day?={is_today}, data source={source}"
            )
        except Exception as e:
            logger.error(f"❌ [TradingCalendar] Initialization failed: {e}", exc_info=True)

    async def get_last_trade_date(self) -> Optional[str]:
        """
        Get the latest trading day (YYYY-MM-DD).
        Read the Redis cache first; if the cache does not exist or is not written today, the API will be re-queried.
        """
        cache = await self._read_cache()
        if cache and cache.get("fetched_at") == self._today_str():
            return cache.get("last_trade_date")

        # Cache expired, retrieve again
        last_trade_date, source = await self._fetch_last_trade_date()
        is_today = last_trade_date == self._today_str()
        await self._write_cache(last_trade_date, is_today, source)
        return last_trade_date

    async def is_today_trade_day(self) -> bool:
        """判断今天是否是交易日"""
        cache = await self._read_cache()
        if cache and cache.get("fetched_at") == self._today_str():
            return bool(cache.get("is_today_trade_day", False))

        last = await self.get_last_trade_date()
        return last == self._today_str()


# ------------------------------------------------------------------ #
# Singleton                                                               #
# ------------------------------------------------------------------ #
_instance: Optional[TradingCalendarService] = None


def get_trading_calendar_service() -> TradingCalendarService:
    global _instance
    if _instance is None:
        _instance = TradingCalendarService()
    return _instance


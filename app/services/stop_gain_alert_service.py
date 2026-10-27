# Take profit reminder service
# Periodically scan the take-profit line (alert_gain_price) set by the user, and push notifications when hit

import asyncio
import logging
from typing import Any, Dict, List

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.database import get_mongo_db
from app.models.notification import NotificationCreate
from app.services.notifications_service import get_notifications_service

logger = logging.getLogger(__name__)


class StopGainAlertService:
    def __init__(self, scan_interval_minutes=10):
        self.scan_interval_minutes = scan_interval_minutes
        self.scheduler = BackgroundScheduler()
        self._job = None
        self._loop = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Called by main in lifespan to safely execute asynchronous logic in the scheduler thread."""
        self._loop = loop

    def start(self):
        if not self._job:
            self._job = self.scheduler.add_job(self.run_once, "interval", minutes=self.scan_interval_minutes)
            self.scheduler.start()
            logger.info("The take-profit reminder service is started with an interval of %s minutes.", self.scan_interval_minutes)

    def stop(self):
        if self._job is not None:
            self._job = None
        if getattr(self.scheduler, "running", False):
            self.scheduler.shutdown(wait=False)
            logger.info("止盈提醒服务已停止")

    @staticmethod
    def _get_db():
        return get_mongo_db()

    def run_once(self):
        watch_items = self._load_watch_items()
        if not watch_items:
            logger.info("[Take profit reminder] No configured take profit reminder")
            return

        notified = 0
        for item in watch_items:
            stop_gain = self._extract_stop_gain(item)
            if stop_gain and self._check_and_notify(item, stop_gain):
                notified += 1

        if notified:
            logger.info("[Take profit reminder] Send %s reminders this round", notified)
        else:
            logger.info("[Take profit reminder] No trigger reminder this round")

    def _load_watch_items(self) -> List[Dict[str, Any]]:
        if not self._loop or self._loop.is_closed():
            logger.warning("[Take profit reminder] No available event loop is set, skip this round of scanning")
            return []

        try:
            future = asyncio.run_coroutine_threadsafe(self._load_watch_items_async(), self._loop)
            return future.result(timeout=20)
        except Exception as e:
            logger.warning("[Take profit reminder] Failed to load monitoring items: %s", e)
            return []

    async def _load_watch_items_async(self) -> List[Dict[str, Any]]:
        """Load the profit-taking monitoring items and fill in the current price in batches."""
        items: List[Dict[str, Any]] = []
        db = self._get_db()

        cursor_users = db.users.find(
            {"favorite_stocks.alert_gain_price": {"$ne": None}},
            {"_id": 1, "favorite_stocks": 1},
        )
        async for u in cursor_users:
            user_id = str(u.get("_id"))
            for fav in u.get("favorite_stocks", []) or []:
                gain = fav.get("alert_gain_price")
                code = str(fav.get("stock_code") or "").strip()
                if gain is None or not code:
                    continue
                items.append(
                    {
                        "user_id": user_id,
                        "symbol": code,
                        "stock_name": fav.get("stock_name") or code,
                        "market": self._normalize_market(fav.get("market")),
                        "alert_gain_price": float(gain),
                    }
                )

        cursor_old = db.user_favorites.find(
            {"favorites.alert_gain_price": {"$ne": None}},
            {"user_id": 1, "favorites": 1},
        )
        async for d in cursor_old:
            user_id = str(d.get("user_id") or "").strip()
            if not user_id:
                continue
            for fav in d.get("favorites", []) or []:
                gain = fav.get("alert_gain_price")
                code = str(fav.get("stock_code") or "").strip()
                if gain is None or not code:
                    continue
                items.append(
                    {
                        "user_id": user_id,
                        "symbol": code,
                        "stock_name": fav.get("stock_name") or code,
                        "market": self._normalize_market(fav.get("market")),
                        "alert_gain_price": float(gain),
                    }
                )

        if not items:
            return []

        await self._fill_current_prices(items, db)
        return items

    async def _fill_current_prices(self, items: List[Dict[str, Any]], db) -> None:
        grouped: Dict[str, List[str]] = {"CN": [], "HK": [], "US": []}
        for item in items:
            market = item.get("market", "CN")
            symbol = item.get("symbol")
            if symbol:
                grouped.setdefault(market, []).append(symbol)

        quotes_cn: Dict[str, Dict[str, Any]] = {}
        quotes_hk: Dict[str, Dict[str, Any]] = {}
        quotes_us: Dict[str, Dict[str, Any]] = {}

        if grouped.get("CN"):
            cn_docs = await db.market_quotes.find(
                {"code": {"$in": grouped["CN"]}}, {"code": 1, "close": 1}
            ).to_list(length=None)
            quotes_cn = {str(d.get("code")).zfill(6): d for d in (cn_docs or [])}

        if grouped.get("HK"):
            hk_docs = await db.market_quotes_hk.find(
                {"code": {"$in": grouped["HK"]}}, {"code": 1, "close": 1}
            ).to_list(length=None)
            quotes_hk = {str(d.get("code")): d for d in (hk_docs or [])}

        if grouped.get("US"):
            us_docs = await db.market_quotes_us.find(
                {"code": {"$in": grouped["US"]}}, {"code": 1, "close": 1}
            ).to_list(length=None)
            quotes_us = {str(d.get("code")): d for d in (us_docs or [])}

        for item in items:
            market = item.get("market", "CN")
            symbol = str(item.get("symbol") or "")
            quote = None
            if market == "CN":
                quote = quotes_cn.get(symbol.zfill(6))
            elif market == "HK":
                quote = quotes_hk.get(symbol)
            else:
                quote = quotes_us.get(symbol)
            item["current_price"] = quote.get("close") if quote else None

    @staticmethod
    def _normalize_market(market: str | None) -> str:
        m = (market or "CN").upper().strip()
        if m in ("A股", "CN", "SH", "SZ", "BJ"):
            return "CN"
        if m in ("港股", "HK"):
            return "HK"
        if m in ("美股", "US"):
            return "US"
        return "CN"

    def _extract_stop_gain(self, item):
        if "alert_gain_price" in item and item["alert_gain_price"]:
            return item["alert_gain_price"]
        if "analysis_report" in item and item["analysis_report"]:
            report = item["analysis_report"]
            if isinstance(report, dict) and "stop_gain" in report:
                return report["stop_gain"]
        return None

    def _check_and_notify(self, item, stop_gain) -> bool:
        current_price = item.get("current_price")
        if current_price is None or current_price < stop_gain:
            return False

        user_id = item.get("user_id")
        symbol = item.get("symbol", "")
        stock_name = item.get("stock_name") or symbol
        if not user_id:
            return False

        payload = NotificationCreate(
            user_id=str(user_id),
            type="alert",
            title=f"止盈提醒：{stock_name}({symbol}) 已达到止盈线",
            content=f"当前价格 {current_price:.2f} 已达到止盈线 {stop_gain:.2f}，请关注。",
            source="stop_gain_alert",
            severity="success",
            metadata={
                "stock_code": symbol,
                "current_price": current_price,
                "stop_gain_price": stop_gain,
            },
        )
        if self._loop and not self._loop.is_closed():
            try:
                async def _publish():
                    await get_notifications_service().create_and_publish(payload)

                asyncio.run_coroutine_threadsafe(_publish(), self._loop)
                return True
            except Exception as e:
                logger.warning("Take profit reminder failed to push(ignore): %s", e)
                return False

        logger.debug("Take profit reminder skip push: not set or turned off event_loop")
        return False


stop_gain_alert_service = StopGainAlertService()

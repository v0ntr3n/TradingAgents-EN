"""
股票关注列表服务
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId

from app.core.database import get_mongo_db
from app.models.user import FavoriteStock
# The online market completion function has been removed and only data is read from the database.
# Users can pass"Synchronize real-time quotes"button to update data
# from app.services.quotes_service import get_quotes_service

logger = logging.getLogger("webapi")


class FavoritesService:
    """股票关注列表服务类"""
    
    def __init__(self):
        self.db = None
    
    async def _get_db(self):
        """获取数据库连接"""
        if self.db is None:
            self.db = get_mongo_db()
        return self.db

    async def _ensure_tags_exist(self, user_id: str, tags: Optional[List[str]]) -> List[str]:
        """Make sure that the tags used in the stock watchlist have been synchronized to the user_tags collection."""
        normalized_tags: List[str] = []
        seen = set()
        for item in tags or []:
            tag_name = str(item or "").strip()
            if not tag_name or tag_name in seen:
                continue
            seen.add(tag_name)
            normalized_tags.append(tag_name)

        if not normalized_tags:
            return []

        try:
            from app.services.tags_service import tags_service

            existing_tags = {
                tag.get("name")
                for tag in await tags_service.list_tags(user_id)
                if tag.get("name")
            }
            for tag_name in normalized_tags:
                if tag_name in existing_tags:
                    continue
                try:
                    await tags_service.create_tag(user_id=user_id, name=tag_name)
                    existing_tags.add(tag_name)
                except Exception:
                    logger.debug("[FavoritesService] Failed to create missing tag: %s", tag_name, exc_info=True)
        except Exception:
            logger.warning("[FavoritesService] Automatically adding tags failed, continue to save the stock watch list", exc_info=True)

        return normalized_tags

    def _is_valid_object_id(self, user_id: str) -> bool:
        """
        Check if it is a valid ObjectId format
        Note: Only the format is checked here, it does not mean that the ObjectId type is actually stored in the database.
        For compatibility, we uniformly use the user_favorites collection to store stock watch lists.
        """
        # Forced to return False, uniformly use the user_favorites collection
        return False

    def _format_favorite(self, favorite: Dict[str, Any]) -> Dict[str, Any]:
        """Format collection items (basic information only, not including real-time quotes).
        Quotes will be batch enriched in get_user_favorites.
        """
        added_at = favorite.get("added_at")
        if isinstance(added_at, datetime):
            added_at = added_at.isoformat()
        return {
            "stock_code": favorite.get("stock_code"),
            "stock_name": favorite.get("stock_name"),
            "market": favorite.get("market", "A股"),
            "added_at": added_at,
            "tags": favorite.get("tags", []),
            "notes": favorite.get("notes", ""),
            "alert_price_high": favorite.get("alert_price_high"),
            "alert_price_low": favorite.get("alert_price_low"),
            "alert_gain_price": favorite.get("alert_gain_price"),
            # Market occupancy, will be filled in later
            "current_price": None,
            "change_percent": None,
            "volume": None,
        }
    async def update_alert_gain_price(self, user_id: str, stock_code: str, gain_price: Optional[float]) -> bool:
        """设置或清除止盈提醒价格"""
        db = await self._get_db()
        is_oid = self._is_valid_object_id(user_id)
        prefix = "favorite_stocks.$." if is_oid else "favorites.$."
        update_fields = {prefix + "alert_gain_price": gain_price}
        if is_oid:
            result = await db.users.update_one(
                {"_id": ObjectId(user_id), "favorite_stocks.stock_code": stock_code},
                {"$set": update_fields}
            )
            return result.modified_count > 0
        else:
            result = await db.user_favorites.update_one(
                {"user_id": user_id, "favorites.stock_code": stock_code},
                {"$set": {**update_fields, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0

    async def get_user_favorites(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Obtain the user s stock watch list, and read real-time quotes from the database for enrichment (compatible with string ID and ObjectId).
        
        Note:
        - Only read data from database (market_quotes, market_quotes_hk, market_quotes_us)
        - The online API will not be called to pull the latest prices to avoid interface timeout.
        - Users can pass"Synchronize real-time quotes"button to update data
        - Background scheduled tasks will regularly update the real-time market data in the database
        """
        import time
        start_time = time.time()
        db = await self._get_db()

        logger.info(f"🔍 [get_user_favorites] Start querying user s stock watch list: user_id={user_id}")

        favorites: List[Dict[str, Any]] = []
        if self._is_valid_object_id(user_id):
            # Try using ObjectId query first
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            # If ObjectId query fails, try using string query
            if user is None:
                user = await db.users.find_one({"_id": user_id})
            favorites = (user or {}).get("favorite_stocks", [])
            logger.info(f"✅ [get_user_favorites] 从 users 集合获取到 {len(favorites)} 只股票关注列表")
        else:
            # 🔥 Strict filtering: only query the current user's stock watch list
            # Use exact matching to ensure only fetching data for the current user
            doc = await db.user_favorites.find_one({"user_id": {"$eq": user_id}})
            if doc:
                # 🔥 Two-step verification: Make sure the document's user_id actually matches
                doc_user_id = doc.get("user_id")
                if doc_user_id != user_id:
                    logger.error(f"❌ [get_user_favorites] 用户ID不匹配！查询: {user_id}, 文档: {doc_user_id}")
                    favorites = []
                else:
                    favorites = doc.get("favorites", [])
                    logger.info(f"✅ [get_user_favorites] Obtained from user_favorites collection {len(favorites)} Only stock watch list (user_id={doc_user_id})")
            else:
                logger.warning(f"⚠️ [get_user_favorites] User stock watchlist data not found: user_id={user_id}")
                # 🔥 Debugging: Check if there are other users' documentation (for debugging only)
                all_docs_count = await db.user_favorites.count_documents({})
                logger.info(f"🔍 [get_user_favorites] 数据库中共有 {all_docs_count} 个文档")
                if all_docs_count > 0:
                    # Only query the first 5 documents for debugging
                    all_docs = await db.user_favorites.find({}, {"user_id": 1, "favorites": 1}).limit(5).to_list(length=5)
                    for idx, d in enumerate(all_docs):
                        logger.info(f"  文档 {idx+1}: user_id={d.get('user_id')}, favorites数量={len(d.get('favorites', []))}")
                favorites = []

        # Format the basic fields first
        items = [self._format_favorite(fav) for fav in favorites]

        # Obtain basic stock information in batches (sectors, etc.)
        codes = [it.get("stock_code") for it in items if it.get("stock_code")]
        if codes:
            try:
                # 🔥 Get data source priority configuration
                from app.core.unified_config import UnifiedConfigManager
                config = UnifiedConfigManager()
                data_source_configs = await config.get_data_source_configs_async()

                # Extract enabled data sources, sorted by priority
                enabled_sources = [
                    ds.type.lower() for ds in data_source_configs
                    if ds.enabled and ds.type.lower() in ['tushare', 'akshare', 'baostock']
                ]

                if not enabled_sources:
                    enabled_sources = ['tushare', 'akshare', 'baostock']

                preferred_source = enabled_sources[0] if enabled_sources else 'tushare'

                # Get sector information from stock_basic_info (only query the data source with the highest priority)
                basic_info_coll = db["stock_basic_info"]
                cursor = basic_info_coll.find(
                    {"code": {"$in": codes}, "source": preferred_source},  # 🔥 Add data source filter
                    {"code": 1, "sse": 1, "market": 1, "_id": 0}
                )
                basic_docs = await cursor.to_list(length=None)
                basic_map = {str(d.get("code")).zfill(6): d for d in (basic_docs or [])}

                # Collect the missed codes in stock_basic_info and check later etf_basic_info
                missing_codes = []
                for it in items:
                    code = it.get("stock_code")
                    basic = basic_map.get(code)
                    if basic:
                        it["board"] = basic.get("market", "-")
                        it["exchange"] = basic.get("sse", "-")
                    else:
                        missing_codes.append(code)

                # Supplement ETF sector/exchange information from etf_basic_info
                if missing_codes:
                    etf_coll = db["etf_basic_info"]
                    etf_cursor = etf_coll.find(
                        {"code": {"$in": missing_codes}},
                        {"code": 1, "name": 1, "_id": 0}
                    )
                    etf_docs = await etf_cursor.to_list(length=None)
                    etf_set = {str(d.get("code")).zfill(6) for d in (etf_docs or [])}
                    etf_name_map = {
                        str(d.get("code")).zfill(6): d.get("name")
                        for d in (etf_docs or [])
                    }

                    for it in items:
                        code = it.get("stock_code")
                        if code in basic_map:
                            continue
                        if code in etf_set:
                            it["board"] = "ETF"
                            if code.startswith(("50", "51", "52")):
                                it["exchange"] = "上海证券交易所"
                            elif code.startswith(("15", "16")):
                                it["exchange"] = "深圳证券交易所"
                            else:
                                it["exchange"] = "-"
                            if not it.get("stock_name") or it["stock_name"] == code:
                                it["stock_name"] = etf_name_map.get(code) or it.get("stock_name", code)
                        else:
                            it["board"] = "-"
                            it["exchange"] = "-"
            except Exception as e:
                # Set default value when query fails
                for it in items:
                    it["board"] = "-"
                    it["exchange"] = "-"

        # Obtain market information in batches (processed separately according to market type to avoid unnecessary interface calls)
        if codes:
            try:
                # 🔥 Group by market type
                a_share_items = []  # A shares
                hk_items = []       # Hong Kong stocks
                us_items = []       # US stocks
                
                for it in items:
                    market = it.get("market", "A股")
                    if market == "港股":
                        hk_items.append(it)
                    elif market == "美股":
                        us_items.append(it)
                    else:
                        a_share_items.append(it)
                
                # 1. Processing of A shares: Priority is given to using the market_quotes stored in the database, updated in 30 seconds
                if a_share_items:
                    a_share_codes = [it.get("stock_code") for it in a_share_items if it.get("stock_code")]
                    if a_share_codes:
                        try:
                            coll = db["market_quotes"]
                            cursor = coll.find({"code": {"$in": a_share_codes}}, {"code": 1, "close": 1, "pct_chg": 1, "amount": 1})
                            docs = await cursor.to_list(length=None)
                            quotes_map = {str(d.get("code")).zfill(6): d for d in (docs or [])}
                            for it in a_share_items:
                                code = it.get("stock_code")
                                q = quotes_map.get(code)
                                if q:
                                    it["current_price"] = q.get("close")
                                    it["change_percent"] = q.get("pct_chg")
                                # If there is no data in the database, keep None (do not call the online API)
                                # Users can click"Synchronize real-time quotes"button to update data
                        except Exception as e:
                            logger.warning(f"⚠️ 查询A股行情失败: {e}")
                
                # 2. Process Hong Kong stocks: query from market_quotes_hk
                if hk_items:
                    hk_codes = [it.get("stock_code") for it in hk_items if it.get("stock_code")]
                    if hk_codes:
                        try:
                            coll = db["market_quotes_hk"]
                            cursor = coll.find({"code": {"$in": hk_codes}}, {"code": 1, "close": 1, "pct_chg": 1, "amount": 1})
                            docs = await cursor.to_list(length=None)
                            quotes_map = {str(d.get("code")): d for d in (docs or [])}
                            for it in hk_items:
                                code = it.get("stock_code")
                                q = quotes_map.get(code)
                                if q:
                                    it["current_price"] = q.get("close")
                                    it["change_percent"] = q.get("pct_chg")
                        except Exception as e:
                            logger.warning(f"⚠️ 查询港股行情失败: {e}")
                
                # 3. Processing US stocks: query from market_quotes_us
                if us_items:
                    us_codes = [it.get("stock_code") for it in us_items if it.get("stock_code")]
                    if us_codes:
                        try:
                            coll = db["market_quotes_us"]
                            cursor = coll.find({"code": {"$in": us_codes}}, {"code": 1, "close": 1, "pct_chg": 1, "amount": 1})
                            docs = await cursor.to_list(length=None)
                            quotes_map = {str(d.get("code")): d for d in (docs or [])}
                            for it in us_items:
                                code = it.get("stock_code")
                                q = quotes_map.get(code)
                                if q:
                                    it["current_price"] = q.get("close")
                                    it["change_percent"] = q.get("pct_chg")
                        except Exception as e:
                            logger.warning(f"⚠️ 查询美股行情失败: {e}")
                            
            except Exception as e:
                logger.warning(f"⚠️ 批量获取行情失败: {e}")
                # Keep the placeholder None when the query fails to avoid affecting basic functions.
                pass

        # Record performance logs
        elapsed_time = time.time() - start_time
        logger.info(f"✅ [get_user_favorites] 查询完成: user_id={user_id}, 返回 {len(items)} 只股票关注列表, 耗时 {elapsed_time:.2f}秒")
        if elapsed_time > 5:
            logger.warning(f"⚠️ [get_user_favorites] The interface takes a long time: {elapsed_time:.2f}seconds, there may be a performance issue")

        return items

    async def add_favorite(
        self,
        user_id: str,
        stock_code: str,
        stock_name: str,
        market: str = "A股",
        tags: List[str] = None,
        notes: str = "",
        alert_price_high: Optional[float] = None,
        alert_price_low: Optional[float] = None
    ) -> bool:
        """Add stocks to stock watchlist (compatible with String ID and ObjectId)"""
        import logging
        logger = logging.getLogger("webapi")

        try:
            logger.info(f"🔧 [add_favorite] Start adding to research list: user_id={user_id}, stock_code={stock_code}")

            db = await self._get_db()
            logger.info(f"🔧 [add_favorite] Database connection obtained successfully")

            normalized_tags = await self._ensure_tags_exist(user_id, tags)

            favorite_stock = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "market": market,
                "added_at": datetime.utcnow(),
                "tags": normalized_tags,
                "notes": notes,
                "alert_price_high": alert_price_high,
                "alert_price_low": alert_price_low
            }

            logger.info(f"🔧 [add_favorite] Stock watch list data construction completed: {favorite_stock}")

            is_oid = self._is_valid_object_id(user_id)
            logger.info(f"🔧 [add_favorite] User ID type check: is_valid_object_id={is_oid}")

            if is_oid:
                logger.info(f"🔧 [add_favorite] Add to users collection using ObjectId method")

                # Try using ObjectId query first
                result = await db.users.update_one(
                    {"_id": ObjectId(user_id)},
                    {
                        "$push": {"favorite_stocks": favorite_stock},
                        "$setOnInsert": {"favorite_stocks": []}
                    }
                )
                logger.info(f"🔧 [add_favorite] ObjectId Query results: matched_count={result.matched_count}, modified_count={result.modified_count}")

                # If ObjectId query fails, try using string query
                if result.matched_count == 0:
                    logger.info(f"🔧 [add_favorite] ObjectId Query failed, trying to query using string ID")
                    result = await db.users.update_one(
                        {"_id": user_id},
                        {
                            "$push": {"favorite_stocks": favorite_stock}
                        }
                    )
                    logger.info(f"🔧 [add_favorite] String ID query results: matched_count={result.matched_count}, modified_count={result.modified_count}")

                success = result.matched_count > 0
                logger.info(f"🔧 [add_favorite] Return results: {success}")
                return success
            else:
                logger.info(f"🔧 [add_favorite] Add to user_favorites collection using string ID")
                result = await db.user_favorites.update_one(
                    {"user_id": user_id},
                    {
                        "$setOnInsert": {"user_id": user_id, "created_at": datetime.utcnow()},
                        "$push": {"favorites": favorite_stock},
                        "$set": {"updated_at": datetime.utcnow()}
                    },
                    upsert=True
                )
                logger.info(f"🔧 [add_favorite] Update results: matched_count={result.matched_count}, modified_count={result.modified_count}, upserted_id={result.upserted_id}")
                logger.info(f"🔧 [add_favorite] Return results: True")
                return True
        except Exception as e:
            logger.error(f"❌ [add_favorite] Add to study list exception: {type(e).__name__}: {str(e)}", exc_info=True)
            raise

    async def remove_favorite(self, user_id: str, stock_code: str) -> bool:
        """Remove a stock from the stock watchlist (compatible with String ID and ObjectId)"""
        db = await self._get_db()

        if self._is_valid_object_id(user_id):
            # Try using ObjectId query first
            result = await db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$pull": {"favorite_stocks": {"stock_code": stock_code}}}
            )
            # If ObjectId query fails, try using string query
            if result.matched_count == 0:
                result = await db.users.update_one(
                    {"_id": user_id},
                    {"$pull": {"favorite_stocks": {"stock_code": stock_code}}}
                )
            return result.modified_count > 0
        else:
            result = await db.user_favorites.update_one(
                {"user_id": user_id},
                {
                    "$pull": {"favorites": {"stock_code": stock_code}},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            return result.modified_count > 0

    async def update_favorite(
        self,
        user_id: str,
        stock_code: str,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        alert_price_high: Optional[float] = None,
        alert_price_low: Optional[float] = None,
        clear_alert_price_low: bool = False,
    ) -> bool:
        """Update stock watch list information (compatible with string ID and ObjectId)"""
        db = await self._get_db()

        # Unify the construction of update fields (set prefixes according to the field paths of different collections)
        is_oid = self._is_valid_object_id(user_id)
        prefix = "favorite_stocks.$." if is_oid else "favorites.$."
        update_fields: Dict[str, Any] = {}
        if tags is not None:
            normalized_tags = await self._ensure_tags_exist(user_id, tags)
            update_fields[prefix + "tags"] = normalized_tags
        if notes is not None:
            update_fields[prefix + "notes"] = notes
        if alert_price_high is not None:
            update_fields[prefix + "alert_price_high"] = alert_price_high
        if clear_alert_price_low:
            update_fields[prefix + "alert_price_low"] = None
        elif alert_price_low is not None:
            update_fields[prefix + "alert_price_low"] = alert_price_low

        if not update_fields:
            return True

        if is_oid:
            result = await db.users.update_one(
                {
                    "_id": ObjectId(user_id),
                    "favorite_stocks.stock_code": stock_code
                },
                {"$set": update_fields}
            )
            return result.modified_count > 0
        else:
            result = await db.user_favorites.update_one(
                {
                    "user_id": user_id,
                    "favorites.stock_code": stock_code
                },
                {
                    "$set": {
                        **update_fields,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0

    async def is_favorite(self, user_id: str, stock_code: str) -> bool:
        """Check whether the stock is in the stock watch list (compatible with String ID and ObjectId)"""
        import logging
        logger = logging.getLogger("webapi")

        try:
            logger.info(f"🔧 [is_favorite] Check stock watchlist: user_id={user_id}, stock_code={stock_code}")

            db = await self._get_db()

            is_oid = self._is_valid_object_id(user_id)
            logger.info(f"🔧 [is_favorite] User ID type: is_valid_object_id={is_oid}")

            if is_oid:
                # Try using ObjectId query first
                user = await db.users.find_one(
                    {
                        "_id": ObjectId(user_id),
                        "favorite_stocks.stock_code": stock_code
                    }
                )

                # If ObjectId query fails, try using string query
                if user is None:
                    logger.info(f"🔧 [is_favorite] ObjectId Query not found, try querying using string ID")
                    user = await db.users.find_one(
                        {
                            "_id": user_id,
                            "favorite_stocks.stock_code": stock_code
                        }
                    )

                result = user is not None
                logger.info(f"🔧 [is_favorite] Query results: {result}")
                return result
            else:
                doc = await db.user_favorites.find_one(
                    {
                        "user_id": user_id,
                        "favorites.stock_code": stock_code
                    }
                )
                result = doc is not None
                logger.info(f"🔧 [is_favorite] String ID query results: {result}")
                return result
        except Exception as e:
            logger.error(f"❌ [is_favorite] Check for stock watchlist exceptions: {type(e).__name__}: {str(e)}", exc_info=True)
            raise

    async def get_user_tags(self, user_id: str) -> List[str]:
        """Get all tags used by the user (compatible with string ID and ObjectId)"""
        db = await self._get_db()

        if self._is_valid_object_id(user_id):
            pipeline = [
                {"$match": {"_id": ObjectId(user_id)}},
                {"$unwind": "$favorite_stocks"},
                {"$unwind": "$favorite_stocks.tags"},
                {"$group": {"_id": "$favorite_stocks.tags"}},
                {"$sort": {"_id": 1}}
            ]
            result = await db.users.aggregate(pipeline).to_list(None)
        else:
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$unwind": "$favorites"},
                {"$unwind": "$favorites.tags"},
                {"$group": {"_id": "$favorites.tags"}},
                {"$sort": {"_id": 1}}
            ]
            result = await db.user_favorites.aggregate(pipeline).to_list(None)

        return [item["_id"] for item in result if item.get("_id")]

    def _get_mock_price(self, stock_code: str) -> float:
        """获取模拟股价"""
        # Generate simulated prices based on stock symbols
        base_price = hash(stock_code) % 100 + 10
        return round(base_price + (hash(stock_code) % 1000) / 100, 2)
    
    def _get_mock_change(self, stock_code: str) -> float:
        """获取模拟涨跌幅"""
        # Generate simulated price increases and decreases based on stock codes
        change = (hash(stock_code) % 2000 - 1000) / 100
        return round(change, 2)
    
    def _get_mock_volume(self, stock_code: str) -> int:
        """获取模拟成交量"""
        # Generate simulated trading volume based on stock symbol
        return (hash(stock_code) % 10000 + 1000) * 100


# Create a global instance
favorites_service = FavoritesService()

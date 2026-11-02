from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['channel_senders', 'channel_notifier', 'notifications_service', 'internal_message_service', 'email_service', 'im_topic_digest_service', 'websocket_manager', 'channel_senders.webhook_sender']:
    _sys.modules[f"app.services.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === channel_senders.py ===
import sys as _sys

# === webhook_sender.py ===
"""
Webhook push sender

Supports three webhook robot formats: Feishu, DingTalk, and WeChat Enterprise.
The protocol is the same, only the JSON body format is slightly different.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from app.models.channel_config import ChannelConfig, ChannelType

logger = logging.getLogger("webapi.channel_senders.webhook")

# HTTP Request timeout (seconds)
WEBHOOK_TIMEOUT = 10


def _build_feishu_payload(title: str, content: str) -> Dict[str, Any]:
    """
    Feishu custom robot message format
    https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
    """
    return {
        "msg_type": "text",
        "content": {
            "text": f"【{title}】\n{content}"
        }
    }


def _build_dingtalk_payload(title: str, content: str) -> Dict[str, Any]:
    """
    DingTalk custom robot message format
    https://open.dingtalk.com/document/robots/custom-robot-access
    """
    return {
        "msgtype": "text",
        "text": {
            "content": f"【{title}】\n{content}"
        }
    }


def _build_wechatwork_payload(title: str, content: str) -> Dict[str, Any]:
    """
    Enterprise WeChat custom robot message format
    https://developer.work.weixin.qq.com/document/path/91770
    """
    return {
        "msgtype": "text",
        "text": {
            "content": f"【{title}】\n{content}"
        }
    }


_BUILDERS = {
    ChannelType.FEISHU: _build_feishu_payload,
    ChannelType.DINGTALK: _build_dingtalk_payload,
    ChannelType.WECHATWORK: _build_wechatwork_payload,
}


async def send_webhook(
    channel: ChannelConfig,
    title: str,
    content: str,
) -> bool:
    """
    Send webhook notification

    Returns:
        True  — Sent successfully
        False — Sending failed
    """
    if not channel.webhook_url:
        logger.warning(f"渠道 [{channel.name}] 未配置 Webhook URL，跳过")
        return False

    builder = _BUILDERS.get(channel.type)
    if not builder:
        logger.warning(f"未知渠道类型: {channel.type}，跳过")
        return False

    payload = builder(title, content)

    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            resp = await client.post(
                channel.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            result = resp.json()

            # The success signs of each platform are different, but HTTP 2xx is enough to judge
            logger.info(
                f"✅ Webhook Push successful: [{channel.name}({channel.type})] "
                f"status={resp.status_code}"
            )
            return True

    except httpx.TimeoutException:
        logger.warning(f"⚠️ Webhook timeout: [{channel.name}] url={channel.webhook_url}")
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"⚠️ Webhook HTTP Error: [{channel.name}] status={e.response.status_code} "
            f"body={e.response.text[:200]}"
        )
    except Exception as e:
        logger.error(f"❌ Webhook Push failed: [{channel.name}] {e}")

    return False


# === __init__.py ===
# Channel senders package

# === channel_notifier.py ===
"""
Channel push scheduler (ChannelNotifier)

Core Responsibilities:
1. Read user in MongoDB `user_channel_configs` Channel list configured in
2. Filter: push only enabled channels + This channel is subscribed to channels of this event_type
3. Concurrent fire-and-forget sending without blocking the caller

Integration points:NotificationsService.create_and_publish() Call at the end dispatch()
"""
import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.core.database import get_mongo_db
from app.models.channel_config import ChannelConfig, ChannelType
from app.utils.timezone import now_tz

logger = logging.getLogger("webapi.channel_notifier")

COLLECTION = "user_channel_configs"


class ChannelNotifier:
    """Unified channel push scheduler (single case)"""

    # -------------------------------------------------------------------------
    # MongoDB CRUD helpers
    # -------------------------------------------------------------------------

    async def get_channels(self, user_id: str) -> List[ChannelConfig]:
        """获取用户所有渠道配置"""
        db = get_mongo_db()
        doc = await db[COLLECTION].find_one({"user_id": user_id})
        if not doc:
            return []
        return [ChannelConfig(**ch) for ch in doc.get("channels", [])]

    async def save_channels(self, user_id: str, channels: List[ChannelConfig]) -> None:
        """Save user channel configuration (overwrite)"""
        db = get_mongo_db()
        await db[COLLECTION].update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "channels": [ch.model_dump() for ch in channels],
                "updated_at": now_tz().isoformat(),
            }},
            upsert=True,
        )

    async def add_channel(self, user_id: str, channel: ChannelConfig) -> ChannelConfig:
        channels = await self.get_channels(user_id)
        channel.channel_id = str(uuid.uuid4())
        channel.created_at = now_tz().isoformat()
        channel.updated_at = channel.created_at
        channels.append(channel)
        await self.save_channels(user_id, channels)
        return channel

    async def update_channel(
        self, user_id: str, channel_id: str, updates: Dict[str, Any]
    ) -> Optional[ChannelConfig]:
        channels = await self.get_channels(user_id)
        for ch in channels:
            if ch.channel_id == channel_id:
                for k, v in updates.items():
                    if v is not None and hasattr(ch, k):
                        setattr(ch, k, v)
                ch.updated_at = now_tz().isoformat()
                await self.save_channels(user_id, channels)
                return ch
        return None

    async def delete_channel(self, user_id: str, channel_id: str) -> bool:
        channels = await self.get_channels(user_id)
        new_channels = [ch for ch in channels if ch.channel_id != channel_id]
        if len(new_channels) == len(channels):
            return False
        await self.save_channels(user_id, new_channels)
        return True

    # -------------------------------------------------------------------------
    # Core push logic
    # -------------------------------------------------------------------------

    async def dispatch(
        self,
        user_id: str,
        title: str,
        content: str,
        event_type: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Scheduling pushes to all matching channels for users (fire-and-forget)

        Args:
            user_id:    User ID
            title:      Notification title
            content:    Notification content
            event_type: event type, see channel_config.EVENT_TYPES
            metadata:   Extended metadata. If _im_channel is included, QQ IM notifications will be automatically pushed
        """
        metadata = metadata or {}

        # ① QQ IM Automatic callback channel (determined by the trigger source, no manual configuration required by the user)
        im_channel = metadata.get("_im_channel")
        if im_channel:
            asyncio.ensure_future(self._send_im_notification(im_channel, title, content))

        # ② External channels configured by users (Feishu/DingTalk/Qiwei/Email)
        try:
            channels = await self.get_channels(user_id)
        except Exception as e:
            logger.warning(f"Failed to obtain channel configuration(ignore): {e}")
            return

        # Filtering: enabled + Subscribed to this event type
        matched = [
            ch for ch in channels
            if ch.enabled and event_type in ch.events
        ]

        if not matched:
            return

        # Send concurrently, errors are not propagated
        tasks = [self._send_one(ch, title, content) for ch in matched]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_one(self, channel: ChannelConfig, title: str, content: str) -> None:
        """Send to a single channel and automatically catch exceptions"""
        try:
            if channel.type in (
                ChannelType.FEISHU, ChannelType.DINGTALK, ChannelType.WECHATWORK
            ):
                await send_webhook(channel, title, content)

            elif channel.type == ChannelType.EMAIL:
                await self._send_email(channel, title, content)

        except Exception as e:
            logger.error(f"❌ 渠道推送异常 [{channel.name}]: {e}")

    async def _send_im_notification(
        self, im_channel: Dict[str, Any], title: str, content: str
    ) -> None:
        """Actively push notifications to IM channels through GatewayRouter (QQ / Feishu Bot, etc.)"""
        try:
            from core.gateway.router import get_gateway_router
            gateway_router = get_gateway_router()
            if gateway_router is None:
                logger.warning("[ChannelNotifier] GatewayRouter Not initialized, skip IM push")
                return

            channel_type = im_channel.get("channel_type", "")
            channel_id = im_channel.get("channel_id", "")
            if not channel_type or not channel_id:
                logger.warning("[ChannelNotifier] _im_channel Incomplete format: %s", im_channel)
                return

            text = f"{title}\n{content}" if content else title
            logger.info("[ChannelNotifier] Push IM notifications: %s/%s", channel_type, channel_id)
            await gateway_router.send_im_notification(channel_type, channel_id, text)
        except Exception as e:
            logger.error("[ChannelNotifier] IM Push failed: %s", e)

    async def _send_email(self, channel: ChannelConfig, title: str, content: str) -> None:
        """Send email channel notifications through existing EmailService"""
        if not channel.email_address:
            logger.warning(f"邮件渠道 [{channel.name}] 未配置邮箱地址，跳过")
            return
        from app.models.email import EmailType

        email_service = get_email_service()
        smtp_config = await email_service.get_smtp_config()
        if not smtp_config:
            logger.debug("SMTP Not configured, skip email channel push")
            return

        await email_service._send_smtp(
            to_email=channel.email_address,
            subject=f"[TradingAgents-CN] {title}",
            html_content=f"<p>{content}</p>",
            text_content=content,
            smtp_config=smtp_config,
        )
        logger.info(f"✅ Email channel push successful: [{channel.name}] -> {channel.email_address}")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_channel_notifier: Optional[ChannelNotifier] = None


def get_channel_notifier() -> ChannelNotifier:
    global _channel_notifier
    if _channel_notifier is None:
        _channel_notifier = ChannelNotifier()
    return _channel_notifier


# === notifications_service.py ===
"""
Notification Service: Persistence + list + Read + SSE publish
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

from app.core.database import get_mongo_db, get_redis_client
from app.models.notification import (
    NotificationCreate, NotificationOut, NotificationList
)
from app.utils.timezone import now_tz

logger = logging.getLogger("webapi.notifications")


class NotificationsService:
    def __init__(self):
        self.collection = "notifications"
        self.channel_prefix = "notifications:"
        self.retain_days = 90
        self.max_per_user = 1000

    async def _ensure_indexes(self):
        try:
            db = get_mongo_db()
            await db[self.collection].create_index([("user_id", 1), ("created_at", -1)])
            await db[self.collection].create_index([("user_id", 1), ("status", 1)])
        except Exception as e:
            logger.warning(f"创建索引失败(忽略): {e}")

    async def create_and_publish(self, payload: NotificationCreate) -> str:
        await self._ensure_indexes()
        db = get_mongo_db()
        doc = {
            "user_id": payload.user_id,
            "type": payload.type,
            "title": payload.title,
            "content": payload.content,
            "link": payload.link,
            "source": payload.source,
            "severity": payload.severity or "info",
            "status": "unread",
            "created_at": now_tz(),
            "metadata": payload.metadata or {},
        }
        res = await db[self.collection].insert_one(doc)
        doc_id = str(res.inserted_id)

        payload_to_publish = {
            "id": doc_id,
            "type": doc["type"],
            "title": doc["title"],
            "content": doc.get("content"),
            "link": doc.get("link"),
            "source": doc.get("source"),
            "status": doc.get("status", "unread"),
            "created_at": doc["created_at"].isoformat(),
        }

        # 🔥 Send notifications using WebSocket
        try:
            from app.routers.websocket_notifications import send_notification_via_websocket
            await send_notification_via_websocket(payload.user_id, payload_to_publish)
            logger.debug(f"✅ [WS] Notification sent via WebSocket: user={payload.user_id}")
        except Exception as e:
            logger.warning(f"⚠️ [WS] WebSocket Sending failed: {e}")

        # 📣 Channel push (Feishu/DingTalk/Qiwei/Email),fire-and-forget
        try:
            notifier = get_channel_notifier()
            event_type = payload.type or "system"
            # Map analysis/alert/skill_gap to channel event types
            _type_map = {
                "analysis": "analysis_complete",
                "alert": "alert",
                "skill_gap": "skill_gap",
                "system": "system",
            }
            channel_event = _type_map.get(event_type, "system")
            import asyncio
            asyncio.ensure_future(
                notifier.dispatch(
                    user_id=payload.user_id,
                    title=payload.title or "通知",
                    content=payload.content or "",
                    event_type=channel_event,
                    metadata=payload.metadata,
                )
            )
        except Exception as e:
            logger.warning(f"⚠️ [Channel] Channel push scheduling failed(ignore): {e}")

        # Cleaning strategy: keep the last N days/up to M items
        try:
            await db[self.collection].delete_many({
                "user_id": payload.user_id,
                "created_at": {"$lt": now_tz() - timedelta(days=self.retain_days)}
            })
            # If quota is exceeded, old files will be deleted based on time.
            count = await db[self.collection].count_documents({"user_id": payload.user_id})
            if count > self.max_per_user:
                skip = count - self.max_per_user
                ids = []
                async for d in db[self.collection].find({"user_id": payload.user_id}, {"_id": 1}).sort("created_at", 1).limit(skip):
                    ids.append(d["_id"])
                if ids:
                    await db[self.collection].delete_many({"_id": {"$in": ids}})
        except Exception as e:
            logger.warning(f"通知清理失败(忽略): {e}")

        return doc_id

    async def unread_count(self, user_id: str) -> int:
        db = get_mongo_db()
        return await db[self.collection].count_documents({"user_id": user_id, "status": "unread"})

    async def list(self, user_id: str, *, status: Optional[str] = None, ntype: Optional[str] = None, page: int = 1, page_size: int = 20) -> NotificationList:
        db = get_mongo_db()
        q: Dict[str, Any] = {"user_id": user_id}
        if status in ("read", "unread"):
            q["status"] = status
        if ntype in ("analysis", "alert", "system"):
            q["type"] = ntype
        total = await db[self.collection].count_documents(q)
        cursor = db[self.collection].find(q).sort("created_at", -1).skip((page-1)*page_size).limit(page_size)
        items: List[NotificationOut] = []
        async for d in cursor:
            items.append(NotificationOut(
                id=str(d.get("_id")),
                type=d.get("type"),
                title=d.get("title"),
                content=d.get("content"),
                link=d.get("link"),
                source=d.get("source"),
                status=d.get("status", "unread"),
                created_at=d.get("created_at") or now_tz(),
            ))
        return NotificationList(items=items, total=total, page=page, page_size=page_size)

    async def mark_read(self, user_id: str, notif_id: str) -> bool:
        db = get_mongo_db()
        try:
            oid = ObjectId(notif_id)
        except Exception:
            return False
        res = await db[self.collection].update_one({"_id": oid, "user_id": user_id}, {"$set": {"status": "read"}})
        return res.modified_count > 0

    async def mark_all_read(self, user_id: str) -> int:
        db = get_mongo_db()
        res = await db[self.collection].update_many({"user_id": user_id, "status": "unread"}, {"$set": {"status": "read"}})
        return res.modified_count


_notifications_service: Optional[NotificationsService] = None


def get_notifications_service() -> NotificationsService:
    global _notifications_service
    if _notifications_service is None:
        _notifications_service = NotificationsService()
    return _notifications_service


# === internal_message_service.py ===
"""
Internal message data service
Provide unified internal message storage, query and management functions
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging
try:
    from pymongo import ReplaceOne
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception
try:
    from pymongo.errors import BulkWriteError
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

from app.core.database import get_database

logger = logging.getLogger(__name__)


def convert_objectid_to_str(data: Union[Dict, List[Dict]]) -> Union[Dict, List[Dict]]:
    """
    Convert MongoDB ObjectId to string to avoid JSON serialization errors

    Args:
        data: Single document or list of documents

    Returns:
        converted data
    """
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and '_id' in item:
                item['_id'] = str(item['_id'])
        return data
    elif isinstance(data, dict):
        if '_id' in data:
            data['_id'] = str(data['_id'])
        return data
    return data


@dataclass
class InternalMessageQueryParams:
    """内部消息查询参数"""
    symbol: Optional[str] = None
    symbols: Optional[List[str]] = None
    message_type: Optional[str] = None  # research_report/insider_info/analyst_note/meeting_minutes/internal_analysis
    category: Optional[str] = None  # fundamental_analysis/technical_analysis/market_sentiment/risk_assessment
    source_type: Optional[str] = None  # internal_research/insider/analyst/meeting/system_analysis
    department: Optional[str] = None
    author: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    importance: Optional[str] = None
    access_level: Optional[str] = None  # public/internal/restricted/confidential
    min_confidence: Optional[float] = None
    rating: Optional[str] = None  # strong_buy/buy/hold/sell/strong_sell
    keywords: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    limit: int = 50
    skip: int = 0
    sort_by: str = "created_time"
    sort_order: int = -1  # -1 for desc, 1 for asc


@dataclass
class InternalMessageStats:
    """内部消息统计信息"""
    total_count: int = 0
    message_types: Dict[str, int] = field(default_factory=dict)
    categories: Dict[str, int] = field(default_factory=dict)
    departments: Dict[str, int] = field(default_factory=dict)
    importance_levels: Dict[str, int] = field(default_factory=dict)
    ratings: Dict[str, int] = field(default_factory=dict)
    avg_confidence: float = 0.0
    recent_count: int = 0  # last 24 hours


class InternalMessageService:
    """内部消息数据服务"""
    
    def __init__(self):
        self.db = None
        self.collection = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def initialize(self):
        """初始化服务"""
        try:
            self.db = get_database()
            self.collection = self.db.internal_messages
            self.logger.info("✅ Internal message data service initialization successful")
        except Exception as e:
            self.logger.error(f"❌ Internal message data service initialization failed: {e}")
            raise
    
    async def _get_collection(self):
        """获取集合实例"""
        if self.collection is None:
            await self.initialize()
        return self.collection
    
    async def save_internal_messages(
        self, 
        messages: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Save internal messages in batches
        
        Args:
            messages: Internal message list
            
        Returns:
            Save statistics
        """
        if not messages:
            return {"saved": 0, "failed": 0}
        
        try:
            collection = await self._get_collection()
            
            # Prepare for batch operations
            operations = []
            for message in messages:
                # Add timestamp
                message["created_at"] = datetime.utcnow()
                message["updated_at"] = datetime.utcnow()
                
                # Use message_id as unique identifier
                filter_dict = {
                    "message_id": message.get("message_id")
                }
                
                operations.append(ReplaceOne(filter_dict, message, upsert=True))
            
            # Perform batch operations
            result = await collection.bulk_write(operations, ordered=False)
            
            saved_count = result.upserted_count + result.modified_count
            self.logger.info(f"✅ Internal message batch saving completed: {saved_count}/{len(messages)}")
            
            return {
                "saved": saved_count,
                "failed": len(messages) - saved_count,
                "upserted": result.upserted_count,
                "modified": result.modified_count
            }
            
        except BulkWriteError as e:
            self.logger.error(f"❌ Partial batch saving of internal messages failed: {e.details}")
            return {
                "saved": e.details.get("nUpserted", 0) + e.details.get("nModified", 0),
                "failed": len(e.details.get("writeErrors", [])),
                "errors": e.details.get("writeErrors", [])
            }
        except Exception as e:
            self.logger.error(f"❌ 内部消息保存失败: {e}")
            return {"saved": 0, "failed": len(messages), "error": str(e)}
    
    async def query_internal_messages(
        self, 
        params: InternalMessageQueryParams
    ) -> List[Dict[str, Any]]:
        """
        Check inside information
        
        Args:
            params: query parameters
            
        Returns:
            Internal message list
        """
        try:
            collection = await self._get_collection()
            
            # Build query conditions
            query = {}
            
            if params.symbol:
                query["symbol"] = params.symbol
            elif params.symbols:
                query["symbol"] = {"$in": params.symbols}
            
            if params.message_type:
                query["message_type"] = params.message_type
            
            if params.category:
                query["category"] = params.category
            
            if params.source_type:
                query["source.type"] = params.source_type
            
            if params.department:
                query["source.department"] = params.department
            
            if params.author:
                query["source.author"] = params.author
            
            if params.start_time or params.end_time:
                time_query = {}
                if params.start_time:
                    time_query["$gte"] = params.start_time
                if params.end_time:
                    time_query["$lte"] = params.end_time
                query["created_time"] = time_query
            
            if params.importance:
                query["importance"] = params.importance
            
            if params.access_level:
                query["access_level"] = params.access_level
            
            if params.min_confidence:
                query["confidence_level"] = {"$gte": params.min_confidence}
            
            if params.rating:
                query["related_data.rating"] = params.rating
            
            if params.keywords:
                query["keywords"] = {"$in": params.keywords}
            
            if params.tags:
                query["tags"] = {"$in": params.tags}
            
            # Execute query
            cursor = collection.find(query)
            
            # sort
            cursor = cursor.sort(params.sort_by, params.sort_order)
            
            # Pagination
            cursor = cursor.skip(params.skip).limit(params.limit)
            
            # Get results
            messages = await cursor.to_list(length=params.limit)

            # 🔧 Convert ObjectId to string to avoid JSON serialization errors
            messages = convert_objectid_to_str(messages)

            self.logger.debug(f"📊 查询到 {len(messages)} 条内部消息")
            return messages
            
        except Exception as e:
            self.logger.error(f"❌ 内部消息查询失败: {e}")
            return []
    
    async def get_latest_messages(
        self, 
        symbol: str = None, 
        message_type: str = None,
        access_level: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取最新内部消息"""
        params = InternalMessageQueryParams(
            symbol=symbol,
            message_type=message_type,
            access_level=access_level,
            limit=limit,
            sort_by="created_time",
            sort_order=-1
        )
        return await self.query_internal_messages(params)
    
    async def search_messages(
        self, 
        query: str, 
        symbol: str = None,
        access_level: str = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """全文搜索内部消息"""
        try:
            collection = await self._get_collection()
            
            # Build search criteria
            search_query = {
                "$text": {"$search": query}
            }
            
            if symbol:
                search_query["symbol"] = symbol
            
            if access_level:
                search_query["access_level"] = access_level
            
            # Perform a search
            cursor = collection.find(
                search_query,
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})])
            
            messages = await cursor.limit(limit).to_list(length=limit)
            
            self.logger.debug(f"🔍 搜索到 {len(messages)} 条相关消息")
            return messages
            
        except Exception as e:
            self.logger.error(f"❌ 内部消息搜索失败: {e}")
            return []
    
    async def get_research_reports(
        self, 
        symbol: str = None,
        department: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取研究报告"""
        params = InternalMessageQueryParams(
            symbol=symbol,
            message_type="research_report",
            department=department,
            limit=limit,
            sort_by="created_time",
            sort_order=-1
        )
        return await self.query_internal_messages(params)
    
    async def get_analyst_notes(
        self, 
        symbol: str = None,
        author: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取分析师笔记"""
        params = InternalMessageQueryParams(
            symbol=symbol,
            message_type="analyst_note",
            author=author,
            limit=limit,
            sort_by="created_time",
            sort_order=-1
        )
        return await self.query_internal_messages(params)
    
    async def get_internal_statistics(
        self, 
        symbol: str = None,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> InternalMessageStats:
        """获取内部消息统计信息"""
        try:
            collection = await self._get_collection()
            
            # Build matching conditions
            match_stage = {}
            if symbol:
                match_stage["symbol"] = symbol
            if start_time or end_time:
                time_query = {}
                if start_time:
                    time_query["$gte"] = start_time
                if end_time:
                    time_query["$lte"] = end_time
                match_stage["created_time"] = time_query
            
            # aggregation pipeline
            pipeline = []
            if match_stage:
                pipeline.append({"$match": match_stage})
            
            pipeline.extend([
                {
                    "$group": {
                        "_id": None,
                        "total_count": {"$sum": 1},
                        "avg_confidence": {"$avg": "$confidence_level"},
                        "message_types": {"$push": "$message_type"},
                        "categories": {"$push": "$category"},
                        "departments": {"$push": "$source.department"},
                        "importance_levels": {"$push": "$importance"},
                        "ratings": {"$push": "$related_data.rating"}
                    }
                }
            ])
            
            # Perform aggregation
            result = await collection.aggregate(pipeline).to_list(length=1)
            
            if result:
                stats_data = result[0]
                
                # Count the number of each category
                def count_items(items):
                    counts = {}
                    for item in items:
                        if item:
                            counts[item] = counts.get(item, 0) + 1
                    return counts
                
                return InternalMessageStats(
                    total_count=stats_data.get("total_count", 0),
                    message_types=count_items(stats_data.get("message_types", [])),
                    categories=count_items(stats_data.get("categories", [])),
                    departments=count_items(stats_data.get("departments", [])),
                    importance_levels=count_items(stats_data.get("importance_levels", [])),
                    ratings=count_items(stats_data.get("ratings", [])),
                    avg_confidence=stats_data.get("avg_confidence", 0.0)
                )
            else:
                return InternalMessageStats()
                
        except Exception as e:
            self.logger.error(f"❌ 内部消息统计失败: {e}")
            return InternalMessageStats()


# Global service instance
_internal_message_service = None

async def get_internal_message_service() -> InternalMessageService:
    """获取内部消息数据服务实例"""
    global _internal_message_service
    if _internal_message_service is None:
        _internal_message_service = InternalMessageService()
        await _internal_message_service.initialize()
    return _internal_message_service

# === email_service.py ===
"""
Email notification service
Provides email push function for analysis results
"""

import smtplib
import uuid
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.core.config import settings
from app.core.database import get_mongo_db
from app.models.email import (
    EmailRecord, EmailRecordCreate, EmailStatus, EmailType,
    EmailNotificationSettings, SMTPConfig
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

# SMTP Configuration collection name
SMTP_CONFIG_COLLECTION = "smtp_config"


class EmailService:
    """邮件发送服务"""

    def __init__(self):
        self.collection = "email_records"
        self.user_collection = "users"
        self._smtp_config_cache: Optional[Dict[str, Any]] = None
        # Initialize template engine
        try:
            self.template_env = Environment(
                loader=FileSystemLoader("prompts/email_templates"),
                autoescape=True
            )
        except Exception as e:
            logger.warning(f"Email template directory does not exist, simple text email will be used: {e}")
            self.template_env = None

    async def get_smtp_config(self) -> Optional[Dict[str, Any]]:
        """
        Get SMTP configuration
        Read from the database first, if not, use .env configuration
        """
        db = get_mongo_db()

        # Get configuration from database
        db_config = await db[SMTP_CONFIG_COLLECTION].find_one({"_id": "default"})

        if db_config and db_config.get("enabled"):
            return {
                "enabled": True,
                "host": db_config.get("host"),
                "port": db_config.get("port", 587),
                "username": db_config.get("username"),
                "password": db_config.get("password"),
                "from_email": db_config.get("from_email"),
                "from_name": db_config.get("from_name", "TradingAgents-CN"),
                "use_tls": db_config.get("use_tls", True),
                "use_ssl": db_config.get("use_ssl", False),
                "source": "database"
            }

        # Fallback to .env configuration
        if settings.SMTP_ENABLED and settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            return {
                "enabled": True,
                "host": settings.SMTP_HOST,
                "port": settings.SMTP_PORT,
                "username": settings.SMTP_USERNAME,
                "password": settings.SMTP_PASSWORD,
                "from_email": settings.SMTP_FROM_EMAIL,
                "from_name": settings.SMTP_FROM_NAME,
                "use_tls": settings.SMTP_USE_TLS,
                "use_ssl": settings.SMTP_USE_SSL,
                "source": "env"
            }

        return None

    async def save_smtp_config(self, config: Dict[str, Any]) -> bool:
        """Save SMTP configuration to database"""
        db = get_mongo_db()

        doc = {
            "_id": "default",
            "enabled": config.get("enabled", True),
            "host": config.get("host"),
            "port": config.get("port", 587),
            "username": config.get("username"),
            "password": config.get("password"),
            "from_email": config.get("from_email"),
            "from_name": config.get("from_name", "TradingAgents-CN"),
            "use_tls": config.get("use_tls", True),
            "use_ssl": config.get("use_ssl", False),
            "updated_at": now_tz().isoformat()
        }

        await db[SMTP_CONFIG_COLLECTION].replace_one(
            {"_id": "default"},
            doc,
            upsert=True
        )

        # clear cache
        self._smtp_config_cache = None
        return True

    async def test_smtp_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """测试 SMTP 连接"""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, self._test_smtp_sync, config
        )

    def _test_smtp_sync(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """同步测试 SMTP 连接"""
        try:
            if config.get("use_ssl"):
                server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=10)
            else:
                server = smtplib.SMTP(config["host"], config["port"], timeout=10)
                if config.get("use_tls"):
                    server.starttls()

            server.login(config["username"], config["password"])
            server.quit()

            return {"success": True, "message": "SMTP 连接测试成功"}
        except smtplib.SMTPAuthenticationError:
            return {"success": False, "message": "SMTP Authentication failed, please check username and password"}
        except smtplib.SMTPConnectError:
            return {"success": False, "message": "Unable to connect to SMTP server, please check address and port"}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {str(e)}"}

    async def send_analysis_email(
        self,
        user_id: str,
        email_type: EmailType,
        template_name: str,
        template_data: Dict[str, Any],
        reference_id: Optional[str] = None,
        reference_type: Optional[str] = None,
        attachments: Optional[List[Tuple[str, bytes, str]]] = None
    ) -> Optional[str]:
        """
        Send analysis result email

        Args:
            user_id: User ID
            email_type: Email type
            template_name: Template name
            template_data: template data
            reference_id: association ID
            reference_type: Association type
            attachments: Attachment list, each element is (file name, File content bytes, MIME Type)
        """

        # 1. Get SMTP configuration
        smtp_config = await self.get_smtp_config()
        if not smtp_config:
            logger.debug("SMTP Not configured, skip email sending")
            return None

        # 2. Get user email settings
        user = await self._get_user(user_id)
        if not user:
            logger.warning(f"用户 {user_id} 不存在")
            return None

        email_settings = self._get_email_settings(user)

        if not email_settings.enabled:
            logger.debug(f"用户 {user_id} 未开启邮件通知")
            return None

        # 3. Check whether this type of notification is enabled
        if not self._is_type_enabled(email_settings, email_type):
            logger.debug(f"用户 {user_id} 未开启 {email_type.value} 类型通知")
            return None

        # 4. Check the do not disturb period
        if self._is_quiet_hours(email_settings):
            logger.debug("Currently in do not disturb period, skip email sending")
            return None

        # 5. Frequency limit check
        if not await self._check_rate_limit(user_id, email_type, reference_id):
            logger.debug("Trigger frequency limit, skip sending")
            return None

        # 6. Confirm recipient email
        to_email = email_settings.email_address or user.get("email")
        if not to_email:
            logger.warning(f"用户 {user_id} 没有配置邮箱")
            return None

        # 7. Render email content
        subject, html_content, text_content = self._render_template(
            template_name, template_data, email_settings.language
        )

        # 8. Create email record
        record_id = await self._create_record(
            user_id=user_id,
            to_email=to_email,
            subject=subject,
            template_name=template_name,
            email_type=email_type,
            reference_id=reference_id,
            reference_type=reference_type
        )

        # 9. Send email (with attachment)
        success = await self._send_smtp(
            to_email, subject, html_content, text_content, smtp_config, attachments
        )

        # 10. Update sending status
        if success:
            await self._update_status(record_id, EmailStatus.SENT)
            logger.info(f"✅ 邮件发送成功: {to_email}, 类型: {email_type.value}")
        else:
            await self._update_status(record_id, EmailStatus.FAILED, "SMTP发送失败")
            logger.error(f"❌ 邮件发送失败: {to_email}")

        return record_id
    
    async def send_test_email(self, user_id: str) -> bool:
        """发送测试邮件"""
        result = await self.send_analysis_email(
            user_id=user_id,
            email_type=EmailType.TEST_EMAIL,
            template_name="test_email",
            template_data={
                "test_time": now_tz().strftime("%Y-%m-%d %H:%M:%S"),
                "message": "This is a test email to verify that email notifications are working properly."
            }
        )
        return result is not None
    
    async def get_email_history(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取邮件发送历史"""
        db = get_mongo_db()
        skip = (page - 1) * page_size
        
        query = {"user_id": user_id}
        
        total = await db[self.collection].count_documents(query)
        cursor = db[self.collection].find(query).sort("created_at", -1).skip(skip).limit(page_size)
        records = await cursor.to_list(length=page_size)
        
        # Convert _id to string
        for record in records:
            record["id"] = str(record.pop("_id"))
        
        return {
            "items": records,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    async def _get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        db = get_mongo_db()
        from bson import ObjectId
        try:
            user = await db[self.user_collection].find_one({"_id": ObjectId(user_id)})
            return user
        except Exception:
            return None

    def _get_email_settings(self, user: Dict[str, Any]) -> EmailNotificationSettings:
        """获取用户邮件设置"""
        preferences = user.get("preferences", {})
        email_settings = preferences.get("email_notifications", {})
        return EmailNotificationSettings(**email_settings) if email_settings else EmailNotificationSettings()

    def _is_type_enabled(self, settings: EmailNotificationSettings, email_type: EmailType) -> bool:
        """检查邮件类型是否启用"""
        type_map = {
            EmailType.SINGLE_ANALYSIS: settings.single_analysis,
            EmailType.BATCH_ANALYSIS: settings.batch_analysis,
            EmailType.SCHEDULED_ANALYSIS: settings.scheduled_analysis,
            EmailType.IMPORTANT_SIGNAL: settings.important_signals,
            EmailType.SYSTEM_NOTIFICATION: settings.system_notifications,
            EmailType.TEST_EMAIL: True,  # Test messages are always allowed
        }
        return type_map.get(email_type, False)

    def _is_quiet_hours(self, email_settings: EmailNotificationSettings) -> bool:
        """检查是否在免打扰时段"""
        if not email_settings.quiet_hours_enabled:
            return False

        now = now_tz()
        current_time = now.strftime("%H:%M")
        start = email_settings.quiet_hours_start
        end = email_settings.quiet_hours_end

        # Handle cross-day situations (such as 22:00 - 08:00) 
        if start > end:
            return current_time >= start or current_time < end
        else:
            return start <= current_time < end

    async def _check_rate_limit(
        self,
        user_id: str,
        email_type: EmailType,
        reference_id: Optional[str]
    ) -> bool:
        """检查频率限制"""
        db = get_mongo_db()

        # Define different types of restrictions
        limits = {
            EmailType.SINGLE_ANALYSIS: {"hours": 1, "same_ref": True},
            EmailType.BATCH_ANALYSIS: {"hours": 0, "same_ref": False},
            EmailType.SCHEDULED_ANALYSIS: {"hours": 0, "same_ref": False},
            EmailType.IMPORTANT_SIGNAL: {"hours": 24, "same_ref": True},
            EmailType.SYSTEM_NOTIFICATION: {"hours": 72, "same_ref": True},
            EmailType.TEST_EMAIL: {"hours": 0, "same_ref": False},
        }

        limit_config = limits.get(email_type, {"hours": 1, "same_ref": False})

        if limit_config["hours"] == 0:
            return True

        query = {
            "user_id": user_id,
            "email_type": email_type.value,
            "status": {"$in": [EmailStatus.SENT.value, EmailStatus.PENDING.value, EmailStatus.SENDING.value]},
            "created_at": {
                "$gte": now_tz() - timedelta(hours=limit_config["hours"])
            }
        }

        if limit_config["same_ref"] and reference_id:
            query["reference_id"] = reference_id

        count = await db[self.collection].count_documents(query)
        return count == 0

    def _render_template(
        self,
        template_name: str,
        data: Dict[str, Any],
        language: str = "zh"
    ) -> tuple:
        """渲染邮件模板"""
        subject = data.get("subject", "TradingAgents-CN Notification")

        # Try loading HTML template
        html_content = None
        if self.template_env:
            try:
                html_template = self.template_env.get_template(f"{language}/{template_name}.html")
                html_content = html_template.render(**data)
            except TemplateNotFound:
                logger.debug(f"未找到模板 {language}/{template_name}.html，使用简单格式")

        # If there is no template, it is easy to generate HTML
        if not html_content:
            html_content = self._generate_simple_html(template_name, data)

        # Generate plain text version
        text_content = self._html_to_text(html_content)

        return subject, html_content, text_content

    def _generate_simple_html(self, template_name: str, data: Dict[str, Any]) -> str:
        """Generate simple HTML email content"""
        title = data.get("title", "TradingAgents-CN Notification")
        content = data.get("content", data.get("message", ""))

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"></head>
        <body style="font-family: 'Microsoft YaHei', sans-serif; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto;">
                <h2 style="color: #333;">{title}</h2>
                <div style="color: #555; line-height: 1.6;">{content}</div>
                <hr style="margin: 20px 0; border: none; border-top: 1px solid #eee;">
                <p style="font-size: 12px; color: #999;">
                    This email is automatically sent by TradingAgents-CN<br>
                    ⚠️ Disclaimer: The above content is for reference only and does not constitute investment advice.
                </p>
            </div>
        </body>
        </html>
        """

    def _html_to_text(self, html: str) -> str:
        """将HTML转换为纯文本"""
        import re
        # Simple solution: remove HTML tags
        text = re.sub(r'<[^>]+>', '', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    async def _create_record(
        self,
        user_id: str,
        to_email: str,
        subject: str,
        template_name: str,
        email_type: EmailType,
        reference_id: Optional[str] = None,
        reference_type: Optional[str] = None
    ) -> str:
        """创建邮件发送记录"""
        db = get_mongo_db()

        record_id = str(uuid.uuid4())
        record = {
            "_id": record_id,
            "user_id": user_id,
            "to_email": to_email,
            "subject": subject,
            "template_name": template_name,
            "email_type": email_type.value,
            "reference_id": reference_id,
            "reference_type": reference_type,
            "status": EmailStatus.PENDING.value,
            "retry_count": 0,
            "max_retries": 3,
            "created_at": now_tz().isoformat(),
            "sent_at": None,
            "error_message": None
        }

        await db[self.collection].insert_one(record)
        return record_id

    async def _update_status(
        self,
        record_id: str,
        status: EmailStatus,
        error_message: Optional[str] = None
    ):
        """更新邮件发送状态"""
        db = get_mongo_db()

        update_data = {"status": status.value}
        if status == EmailStatus.SENT:
            update_data["sent_at"] = now_tz().isoformat()
        if error_message:
            update_data["error_message"] = error_message

        await db[self.collection].update_one(
            {"_id": record_id},
            {"$set": update_data}
        )

    async def _send_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
        smtp_config: Dict[str, Any],
        attachments: Optional[List[Tuple[str, bytes, str]]] = None
    ) -> bool:
        """Sending mail via SMTP (performing synchronous operations in a thread pool)"""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self._send_smtp_sync,
            to_email, subject, html_content, text_content, smtp_config, attachments
        )

    def _send_smtp_sync(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
        smtp_config: Dict[str, Any],
        attachments: Optional[List[Tuple[str, bytes, str]]] = None
    ) -> bool:
        """Synchronous SMTP sending (supports attachments)"""
        try:
            # If there are attachments, use mixed type; otherwise use alternative
            if attachments:
                msg = MIMEMultipart("mixed")
                # Create body section
                body_part = MIMEMultipart("alternative")
                body_part.attach(MIMEText(text_content, "plain", "utf-8"))
                body_part.attach(MIMEText(html_content, "html", "utf-8"))
                msg.attach(body_part)

                # Add attachment
                for filename, content, mime_type in attachments:
                    try:
                        main_type, sub_type = mime_type.split("/", 1)
                        attachment = MIMEBase(main_type, sub_type)
                        attachment.set_payload(content)
                        encoders.encode_base64(attachment)
                        attachment.add_header(
                            "Content-Disposition",
                            "attachment",
                            filename=filename
                        )
                        msg.attach(attachment)
                        logger.info(f"📎 添加附件: {filename} ({len(content)} bytes)")
                    except Exception as att_err:
                        logger.warning(f"⚠️ 添加附件 {filename} 失败: {att_err}")
            else:
                msg = MIMEMultipart("alternative")
                msg.attach(MIMEText(text_content, "plain", "utf-8"))
                msg.attach(MIMEText(html_content, "html", "utf-8"))

            msg["Subject"] = subject
            msg["From"] = f"{smtp_config['from_name']} <{smtp_config['from_email']}>"
            msg["To"] = to_email

            # Send email
            if smtp_config.get("use_ssl"):
                server = smtplib.SMTP_SSL(smtp_config["host"], smtp_config["port"])
            else:
                server = smtplib.SMTP(smtp_config["host"], smtp_config["port"])
                if smtp_config.get("use_tls"):
                    server.starttls()

            server.login(smtp_config["username"], smtp_config["password"])
            server.send_message(msg)
            server.quit()

            return True

        except Exception as e:
            logger.error(f"SMTP发送失败: {e}")
            return False


# global instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """获取邮件服务实例"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


# === im_topic_digest_service.py ===
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.intelligent_assistant_service import (
    _build_thread_summary_with_llm,
    append_assistant_message,
    create_assistant_thread,
    summarize_assistant_thread,
)

logger = logging.getLogger(__name__)

DIGEST_FALLBACK_TOPIC_TITLE = "外部沟通沉淀"
DIGEST_TOOL_NAME = "im_topic_digest_sync"


class IMTopicDigestService:
    """Periodically precipitate untopiced external sessions into research topics."""

    def __init__(self, db):
        self.db = db

    async def run_once(
        self,
        min_messages: int = 6,
        lookback_limit: int = 20,
    ) -> Dict[str, Any]:
        stats = {
            "scanned": 0,
            "digested": 0,
            "skipped": 0,
            "failed": 0,
        }

        cursor = self.db.assistant_threads.find({
            "topic_type": "im_session",
            "archived": {"$ne": True},
            "message_count": {"$gte": max(min_messages, 1)},
        }).sort("updated_at", -1)

        async for session_thread in cursor:
            stats["scanned"] += 1
            try:
                digested = await self._digest_session_thread(
                    session_thread,
                    min_messages=min_messages,
                    lookback_limit=lookback_limit,
                )
                if digested:
                    stats["digested"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as exc:
                stats["failed"] += 1
                logger.exception("[IMTopicDigest] Precipitating external session failed: thread=%s err=%s", session_thread.get("thread_id"), exc)

        logger.info("[IMTopicDigest] Complete: %s", stats)
        return stats

    async def _digest_session_thread(
        self,
        session_thread: Dict[str, Any],
        min_messages: int,
        lookback_limit: int,
    ) -> bool:
        user_id = str(session_thread.get("user_id") or "").strip()
        session_key = str(session_thread.get("thread_id") or "").strip()
        if not user_id or not session_key:
            return False

        processed_count = int(session_thread.get("last_digest_message_count") or 0)
        total_count = int(session_thread.get("message_count") or 0)
        unsynced_count = max(total_count - processed_count, 0)
        if unsynced_count < min_messages:
            return False

        messages = await self.db.assistant_thread_messages.find({
            "user_id": user_id,
            "thread_id": session_key,
        }).sort("created_at", 1).skip(processed_count).to_list(length=lookback_limit)
        if len(messages) < min_messages:
            return False

        formatted_messages = [
            {
                "role": doc.get("role", "assistant"),
                "content": doc.get("content", ""),
                "tools_used": doc.get("tools_used") or None,
            }
            for doc in messages
            if (doc.get("content") or "").strip()
        ]
        if len(formatted_messages) < min_messages:
            return False

        summary = await _build_thread_summary_with_llm(self.db, formatted_messages, title="外部会话沉淀")
        summary_text = self._format_digest_message(session_key, formatted_messages, summary)
        target_thread_id = await self._resolve_target_thread_id(user_id, session_key)
        if not target_thread_id:
            return False

        await append_assistant_message(
            self.db,
            user_id=user_id,
            role="assistant",
            content=summary_text,
            conversation_id=target_thread_id,
            tools_used=[DIGEST_TOOL_NAME],
        )
        await summarize_assistant_thread(
            self.db,
            user_id=user_id,
            conversation_id=target_thread_id,
            summary_type="im_digest",
        )

        now = datetime.now(timezone.utc)
        await self.db.assistant_threads.update_one(
            {"user_id": user_id, "thread_id": session_key},
            {
                "$set": {
                    "last_digest_at": now,
                    "last_digest_message_count": total_count,
                    "last_digest_target_thread_id": target_thread_id,
                    "last_digest_summary": summary.get("abstract") or "",
                }
            },
        )
        return True

    async def _resolve_target_thread_id(self, user_id: str, session_key: str) -> Optional[str]:
        session_doc = await self.db.gateway_sessions.find_one(
            {"session_key": session_key},
            {"context.current_topic_id": 1},
        )
        bound_topic_id = ((session_doc or {}).get("context") or {}).get("current_topic_id")
        bound_topic_id = (bound_topic_id or "").strip() or None
        if bound_topic_id:
            topic_doc = await self.db.assistant_threads.find_one({
                "user_id": user_id,
                "thread_id": bound_topic_id,
                "archived": {"$ne": True},
            })
            if topic_doc and topic_doc.get("topic_type") != "im_session":
                return bound_topic_id

        fallback_topic = await create_assistant_thread(
            self.db,
            user_id=user_id,
            title=DIGEST_FALLBACK_TOPIC_TITLE,
            parent_thread_id=None,
        )
        return fallback_topic.get("thread_id")

    def _format_digest_message(
        self,
        session_key: str,
        messages: List[Dict[str, Any]],
        summary: Dict[str, Any],
    ) -> str:
        latest_user = ""
        for message in reversed(messages):
            if message.get("role") == "user" and (message.get("content") or "").strip():
                latest_user = (message.get("content") or "").strip()
                break

        lines = [
            f"【外部沟通沉淀】{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"来源会话: {session_key}",
        ]
        if latest_user:
            lines.append(f"最近用户问题: {latest_user[:80]}")

        abstract = (summary.get("abstract") or "").strip()
        if abstract:
            lines.extend(["", "摘要:", abstract[:200]])

        confirmed_facts = summary.get("confirmed_facts") or []
        if confirmed_facts:
            lines.append("")
            lines.append("已确认信息:")
            lines.extend(f"- {item}" for item in confirmed_facts[:3])

        open_questions = summary.get("open_questions") or []
        if open_questions:
            lines.append("")
            lines.append("待继续跟进:")
            lines.extend(f"- {item}" for item in open_questions[:3])

        next_actions = summary.get("next_actions") or []
        if next_actions:
            lines.append("")
            lines.append("建议动作:")
            lines.extend(f"- {item}" for item in next_actions[:3])

        return "\n".join(lines)

# === websocket_manager.py ===
"""
WebSocket connection manager
Used to push analysis progress updates in real time
"""

import asyncio
import json
import logging
from typing import Dict, Set, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

class WebSocketManager:
    """WebSocket connection manager"""
    
    def __init__(self):
        # Store active connections:{task_id: {websocket1, websocket2, ...}}
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, task_id: str):
        """Establish a WebSocket connection"""
        await websocket.accept()
        
        async with self._lock:
            if task_id not in self.active_connections:
                self.active_connections[task_id] = set()
            self.active_connections[task_id].add(websocket)
        
        logger.info(f"🔌 WebSocket Connection established: {task_id}")
    
    async def disconnect(self, websocket: WebSocket, task_id: str):
        """Disconnect WebSocket"""
        async with self._lock:
            if task_id in self.active_connections:
                self.active_connections[task_id].discard(websocket)
                if not self.active_connections[task_id]:
                    del self.active_connections[task_id]
        
        logger.info(f"🔌 WebSocket Lost connection: {task_id}")
    
    async def send_progress_update(self, task_id: str, message: Dict[str, Any]):
        """Send progress updates to all connections for the specified task"""
        if task_id not in self.active_connections:
            return
        
        # Copy connection collection to avoid modification while iterating
        connections = self.active_connections[task_id].copy()
        
        for connection in connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.warning(f"⚠️ Failed to send WebSocket message: {e}")
                # Remove broken connections
                async with self._lock:
                    if task_id in self.active_connections:
                        self.active_connections[task_id].discard(connection)
    
    async def broadcast_to_user(self, user_id: str, message: Dict[str, Any]):
        """向用户的所有连接广播消息"""
        # This can be extended to manage connections by user ID
        # Currently, the implementation is simplified and only managed by task ID.
        pass
    
    async def get_connection_count(self, task_id: str) -> int:
        """获取指定任务的连接数"""
        async with self._lock:
            return len(self.active_connections.get(task_id, set()))
    
    async def get_total_connections(self) -> int:
        """获取总连接数"""
        async with self._lock:
            total = 0
            for connections in self.active_connections.values():
                total += len(connections)
            return total

# global instance
_websocket_manager = None

def get_websocket_manager() -> WebSocketManager:
    """Get a WebSocket manager instance"""
    global _websocket_manager
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager()
    return _websocket_manager

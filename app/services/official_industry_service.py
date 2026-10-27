"""
System industry mapping services

The system has a built-in stock code -> A mapping collection of industries. All readers draw data from this collection uniformly.
In the future, data can be supplied through the official website interface; currently, when the official website interface is not configured, Tushare is temporarily used as the data supply source.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional

from pymongo import UpdateMany, UpdateOne

from app.core.database import get_mongo_db

logger = logging.getLogger(__name__)

INDUSTRY_MAPPING_COLLECTION = "stock_industry_mappings"
INDUSTRY_SOURCE_SYSTEM = "system_industry_mapping"

_industry_cache: Optional[Dict[str, str]] = None
_cache_time: Optional[datetime] = None
_CACHE_TTL_HOURS = 24


def _normalize_code(code: Any) -> str:
    value = str(code or "").strip()
    if not value:
        return ""
    if "." in value:
        value = value.split(".", 1)[0]
    return value.zfill(6)


def _normalize_mapping_payload(data: Any) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if isinstance(data, dict):
        items = data.items()
        for code, value in items:
            normalized_code = _normalize_code(code)
            if not normalized_code:
                continue
            if isinstance(value, str):
                industry = value.strip()
            elif isinstance(value, dict):
                industry = str(value.get("industry") or value.get("industry_name") or "").strip()
            else:
                industry = ""
            if industry and industry != "未知":
                result[normalized_code] = industry
        return result

    if isinstance(data, list):
        for item in data:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            elif hasattr(item, "dict"):
                item = item.dict()
            if not isinstance(item, dict):
                continue

            normalized_code = _normalize_code(item.get("code") or item.get("symbol") or item.get("ts_code"))
            industry = str(item.get("industry") or item.get("industry_name") or "").strip()
            if normalized_code and industry and industry != "未知":
                result[normalized_code] = industry

    return result


def _invalidate_cache() -> None:
    global _industry_cache, _cache_time
    _industry_cache = None
    _cache_time = None


def get_official_industry_url() -> Optional[str]:
    """Obtain the official website industry data URL from the configuration."""
    try:
        from app.core.config import settings
        url = getattr(settings, "OFFICIAL_INDUSTRY_DATA_URL", None)
        if url and str(url).strip():
            return str(url).strip()
    except Exception:
        pass
    import os
    return os.getenv("OFFICIAL_INDUSTRY_DATA_URL", "").strip() or None


async def _load_mapping_from_collection() -> Dict[str, str]:
    db = get_mongo_db()
    collection = db[INDUSTRY_MAPPING_COLLECTION]
    cursor = collection.find(
        {"industry": {"$nin": [None, "", "未知"]}},
        {"_id": 0, "code": 1, "industry": 1}
    )

    mapping: Dict[str, str] = {}
    async for doc in cursor:
        code = _normalize_code(doc.get("code"))
        industry = str(doc.get("industry") or "").strip()
        if code and industry:
            mapping[code] = industry
    return mapping


async def upsert_industry_mapping(mapping: Dict[str, str], provider: str) -> Dict[str, Any]:
    """Batch write system industry mapping collection."""
    if not mapping:
        return {"provider": provider, "total": 0, "upserted": 0, "modified": 0}

    db = get_mongo_db()
    collection = db[INDUSTRY_MAPPING_COLLECTION]
    now = datetime.utcnow()

    operations = []
    for code, industry in mapping.items():
        normalized_code = _normalize_code(code)
        normalized_industry = str(industry or "").strip()
        if not normalized_code or not normalized_industry or normalized_industry == "未知":
            continue
        operations.append(UpdateOne(
            {"code": normalized_code},
            {
                "$set": {
                    "code": normalized_code,
                    "industry": normalized_industry,
                    "provider": provider,
                    "updated_at": now,
                }
            },
            upsert=True
        ))

    if not operations:
        return {"provider": provider, "total": 0, "upserted": 0, "modified": 0}

    result = await collection.bulk_write(operations, ordered=False)
    _invalidate_cache()
    logger.info(f"✅ Industry mapping collection update completed: provider={provider}, total={len(operations)}, modified={result.modified_count}, upserted={result.upserted_count}")
    return {
        "provider": provider,
        "total": len(operations),
        "upserted": result.upserted_count,
        "modified": result.modified_count,
    }


async def upsert_industry_mapping_from_records(records: Iterable[Any], provider: str = "tushare_fallback") -> Dict[str, Any]:
    """Extract industries from stock list records and write to the system industry map collection."""
    mapping = _normalize_mapping_payload(list(records))
    return await upsert_industry_mapping(mapping, provider=provider)


async def _fetch_mapping_from_official_url() -> Dict[str, str]:
    url = get_official_industry_url()
    if not url:
        return {}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        mapping = _normalize_mapping_payload(data)
        if mapping:
            logger.info(f"✅ 从官网接口获取行业映射成功: {len(mapping)} 只股票")
        return mapping
    except Exception as e:
        logger.warning(f"获取官网行业数据失败: {url}, {e}")
        return {}


async def _fetch_mapping_from_tushare() -> Dict[str, str]:
    try:
        from tradingagents.dataflows.providers.china.tushare import TushareProvider

        provider = TushareProvider()
        connected = await provider.connect()
        if not connected:
            logger.warning("Tushare Connection failed, unable to refresh industry mapping collection")
            return {}

        stock_list = await provider.get_stock_list(market="CN")
        mapping = _normalize_mapping_payload(stock_list)
        if mapping:
            logger.info(f"✅ 从 Tushare 临时供数获取行业映射成功: {len(mapping)} 只股票")
        return mapping
    except Exception as e:
        logger.warning(f"Failed to get industry mapping from Tushare: {e}")
        return {}


async def refresh_industry_mapping(prefer_official: bool = True) -> Dict[str, Any]:
    """Refresh the system industry mapping collection. Prioritize the official website interface and fall back to Tushare if it is not configured."""
    mapping: Dict[str, str] = {}
    provider = "none"

    if prefer_official:
        mapping = await _fetch_mapping_from_official_url()
        if mapping:
            provider = "official_api"

    if not mapping:
        mapping = await _fetch_mapping_from_tushare()
        if mapping:
            provider = "tushare_fallback"

    if not mapping:
        logger.warning("⚠️ No industry mapping data was obtained, and the system industry mapping collection remains unchanged.")
        return {"provider": provider, "total": 0, "upserted": 0, "modified": 0}

    return await upsert_industry_mapping(mapping, provider=provider)


async def fetch_industry_mapping(refresh_if_empty: bool = True) -> Dict[str, str]:
    """Read the system industry mapping collection and automatically refresh it when necessary."""
    global _industry_cache, _cache_time

    if _industry_cache is not None and _cache_time is not None:
        if datetime.utcnow() - _cache_time < timedelta(hours=_CACHE_TTL_HOURS):
            return _industry_cache

    mapping = await _load_mapping_from_collection()
    if not mapping and refresh_if_empty:
        await refresh_industry_mapping(prefer_official=True)
        mapping = await _load_mapping_from_collection()

    _industry_cache = mapping
    _cache_time = datetime.utcnow()
    return mapping


def get_industry_sync(code: str) -> Optional[str]:
    """Synchronously read individual stock sectors from memory cache."""
    global _industry_cache
    if not _industry_cache:
        return None
    return _industry_cache.get(_normalize_code(code))


async def get_industry(code: str) -> Optional[str]:
    """Asynchronously read a single stock industry."""
    mapping = await fetch_industry_mapping(refresh_if_empty=True)
    return mapping.get(_normalize_code(code))


async def sync_industry_to_stock_basic_info(db=None) -> Dict[str, int]:
    """Batch backfill the system industry mapping collection into stock_basic_info."""
    if db is None:
        db = get_mongo_db()

    mapping = await fetch_industry_mapping(refresh_if_empty=True)
    if not mapping:
        return {"updated": 0, "total": 0}

    collection = db["stock_basic_info"]
    operations = []
    now = datetime.utcnow()
    for code, industry in mapping.items():
        operations.append(UpdateMany(
            {"code": code},
            {
                "$set": {
                    "industry": industry,
                    "industry_source": INDUSTRY_SOURCE_SYSTEM,
                    "industry_updated_at": now,
                }
            }
        ))

    if not operations:
        return {"updated": 0, "total": 0}

    result = await collection.bulk_write(operations, ordered=False)
    logger.info(f"✅ 系统行业映射已同步到 stock_basic_info: 更新 {result.modified_count} 条")
    return {"updated": result.modified_count, "total": len(mapping)}

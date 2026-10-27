"""
Community Edition launches bootstrapping service for the first time

Background: The community version is not distributed with the package install/ and scripts/ (the Pro version is called by docker-entrypoint.sh
scripts/import_config_and_create_user.py Complete account creation and configuration import), so when the community version is started for the first time
Empty library has no system configuration——The model directory, prompt word template, Agent configuration, workflow, etc. are all missing, and the functions are unavailable after logging in.

This module imports the minimum system configuration during the application startup phase. It is idempotent: when install/community_bootstrap.json exists,
press"Import only if the collection is empty"Writing, Pro version automatically skips each collection when it is not empty, with zero impact on behavior.

The account is not created here: by app/services/user_service.py::bootstrap_first_admin Responsible (no registration for community version)
interface, create admin based on ADMIN_DEFAULT_PASSWORD when the library is empty).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from bson import ObjectId

logger = logging.getLogger(__name__)

# Start the bootstrap configuration package (built-in community version snapshot: install/community_bootstrap.json)
BOOTSTRAP_FILENAME = "community_bootstrap.json"
INSTALL_DIRNAME = "install"

# Sensitive field mode: Secondary desensitization before import to prevent the configuration package from carrying keys
_SECRET_KEY_PATTERNS = (
    "api_key", "apikey", "api_secret", "secret",
    "password", "access_token", "refresh_token",
)
_SECRET_KEY_SKIP = ("has_api_key", "has_api_secret", "max_tokens")


def _project_root() -> Path:
    """Project root directory (app/services/xxx.py → Go up three levels)"""
    return Path(__file__).resolve().parents[2]


def _sanitize(node: Any) -> Any:
    """Recursively clear sensitive field values (retain field names) to prevent configuration packages from accidentally carrying keys"""
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for key, value in node.items():
            lowered = key.lower()
            if lowered in _SECRET_KEY_SKIP:
                out[key] = _sanitize(value)
                continue
            if any(p in lowered for p in _SECRET_KEY_PATTERNS):
                out[key] = "" if isinstance(value, (str, type(None))) else _sanitize(value)
                continue
            out[key] = _sanitize(value)
        return out
    if isinstance(node, list):
        return [_sanitize(item) for item in node]
    return node


def _convert_to_bson(data: Any) -> Any:
    """JSON → BSON: Restore ObjectId and datetime (same caliber as the Pro version import script)"""
    if isinstance(data, dict):
        result: Dict[str, Any] = {}
        for key, value in data.items():
            if key == "_id" or key.endswith("_id"):
                if isinstance(value, str) and len(value) == 24:
                    try:
                        result[key] = ObjectId(value)
                        continue
                    except Exception:
                        pass
            if key.endswith("_at") or key in ("created_at", "updated_at", "last_login", "added_at"):
                if isinstance(value, str):
                    try:
                        result[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        continue
                    except Exception:
                        pass
            result[key] = _convert_to_bson(value)
        return result
    if isinstance(data, list):
        return [_convert_to_bson(item) for item in data]
    return data


async def import_bootstrap_config() -> int:
    """Import the minimum system configuration of the community version (only import empty collections, idempotent)

    Returns:
        The total number of documents imported this time
    """
    from app.core.database import get_mongo_db

    bootstrap_file = _project_root() / INSTALL_DIRNAME / BOOTSTRAP_FILENAME
    if not bootstrap_file.exists():
        return 0

    try:
        with open(bootstrap_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        logger.error(f"❌ 读取启动配置包失败: {bootstrap_file} ({e})")
        return 0

    data = payload.get("data") or {}
    if not isinstance(data, dict):
        logger.error(f"❌ The startup configuration package format is incorrect (missing data section): {bootstrap_file}")
        return 0

    db = get_mongo_db()
    total_inserted = 0
    imported_collections = []

    for collection_name, documents in data.items():
        if not isinstance(documents, list) or not documents:
            continue
        try:
            if await db[collection_name].count_documents({}) > 0:
                continue
            converted = [_convert_to_bson(_sanitize(doc)) for doc in documents]
            await db[collection_name].insert_many(converted, ordered=False)
            total_inserted += len(converted)
            imported_collections.append(f"{collection_name}({len(converted)})")
        except Exception as e:
            logger.error(f"❌ 导入集合 {collection_name} 失败: {e}")

    if total_inserted:
        logger.info(f"✅ 启动配置导入完成: {total_inserted} 个文档 → {', '.join(imported_collections)}")
        logger.info("📋 The system configuration is ready. After logging in for the first time, please configure the LLM and data source keys in System Settings ")
    return total_inserted
from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['database', 'queue', 'auth_service', 'user_service', 'license_service', 'jdyun_init', 'community_bootstrap_service', 'database_service', 'queue_service', 'scheduler_service', 'thread_worker', 'operation_log_service', 'log_export_service', 'mcp_audit_service', 'quality_metrics_service', 'usage_statistics_service', 'update_service', 'database.serialization', 'database.status_checks', 'database.cleanup', 'database.backups', 'queue.keys', 'queue.helpers']:
    _sys.modules[f"app.services.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === database.py ===
import sys as _sys

# === serialization.py ===
"""
Serialization helpers for MongoDB documents.
"""

from datetime import datetime
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str


def serialize_document(doc: dict) -> dict:
    """Serialize special MongoDB types to JSON-friendly primitives.
    - ObjectId -> str
    - datetime -> ISO string
    - Recurse into nested dict/list
    """
    serialized = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            serialized[key] = str(value)
        elif isinstance(value, datetime):
            serialized[key] = value.isoformat()
        elif isinstance(value, dict):
            serialized[key] = serialize_document(value)
        elif isinstance(value, list):
            out_list = []
            for item in value:
                if isinstance(item, dict):
                    out_list.append(serialize_document(item))
                elif isinstance(item, ObjectId):
                    out_list.append(str(item))
                elif isinstance(item, datetime):
                    out_list.append(item.isoformat())
                else:
                    out_list.append(item)
            serialized[key] = out_list
        else:
            serialized[key] = value
    return serialized


# === status_checks.py ===
"""
Database status and connection checks, extracted from DatabaseService.
"""

from datetime import datetime
from typing import Any, Dict

from app.core.database import get_mongo_db, get_redis_client
from app.core.config import settings


async def get_mongodb_status() -> Dict[str, Any]:
    try:
        db = get_mongo_db()
        await db.command("ping")
        server_info = await db.command("buildInfo")
        server_status = await db.command("serverStatus")
        return {
            "connected": True,
            "host": settings.MONGODB_HOST,
            "port": settings.MONGODB_PORT,
            "database": settings.MONGODB_DATABASE,
            "version": server_info.get("version", "Unknown"),
            "uptime": server_status.get("uptime", 0),
            "connections": server_status.get("connections", {}),
            "memory": server_status.get("mem", {}),
            "connected_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "host": settings.MONGODB_HOST,
            "port": settings.MONGODB_PORT,
            "database": settings.MONGODB_DATABASE,
        }


async def get_redis_status() -> Dict[str, Any]:
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        info = await redis_client.info()
        return {
            "connected": True,
            "host": settings.REDIS_HOST,
            "port": settings.REDIS_PORT,
            "database": settings.REDIS_DB,
            "version": info.get("redis_version", "Unknown"),
            "uptime": info.get("uptime_in_seconds", 0),
            "memory_used": info.get("used_memory", 0),
            "memory_peak": info.get("used_memory_peak", 0),
            "connected_clients": info.get("connected_clients", 0),
            "total_commands": info.get("total_commands_processed", 0),
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "host": settings.REDIS_HOST,
            "port": settings.REDIS_PORT,
            "database": settings.REDIS_DB,
        }


async def get_database_status() -> Dict[str, Any]:
    mongodb_status = await get_mongodb_status()
    redis_status = await get_redis_status()
    return {"mongodb": mongodb_status, "redis": redis_status}


async def test_mongodb_connection() -> Dict[str, Any]:
    try:
        db = get_mongo_db()
        start = datetime.utcnow()
        await db.command("ping")
        took_ms = (datetime.utcnow() - start).total_seconds() * 1000
        return {"success": True, "response_time_ms": round(took_ms, 2), "message": "MongoDB连接正常"}
    except Exception as e:
        return {"success": False, "error": str(e), "message": "MongoDB连接失败"}


async def test_redis_connection() -> Dict[str, Any]:
    try:
        redis_client = get_redis_client()
        start = datetime.utcnow()
        await redis_client.ping()
        took_ms = (datetime.utcnow() - start).total_seconds() * 1000
        return {"success": True, "response_time_ms": round(took_ms, 2), "message": "Redis连接正常"}
    except Exception as e:
        return {"success": False, "error": str(e), "message": "Redis连接失败"}


async def test_connections() -> Dict[str, Any]:
    mongodb = await test_mongodb_connection()
    redis = await test_redis_connection()
    return {"mongodb": mongodb, "redis": redis, "overall": mongodb["success"] and redis["success"]}


# === cleanup.py ===
"""
Cleanup routines extracted from DatabaseService.
"""

from datetime import datetime, timedelta
from typing import Any, Dict

from app.core.database import get_mongo_db


async def cleanup_old_data(days: int) -> Dict[str, Any]:
    db = get_mongo_db()
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    deleted_count = 0
    cleaned_collections = []

    res = await db.analysis_tasks.delete_many({
        "created_at": {"$lt": cutoff_date},
        "status": {"$in": ["completed", "failed"]},
    })
    if res.deleted_count:
        deleted_count += res.deleted_count
        cleaned_collections.append(f"analysis_tasks: {res.deleted_count}")

    res = await db.user_sessions.delete_many({"created_at": {"$lt": cutoff_date}})
    if res.deleted_count:
        deleted_count += res.deleted_count
        cleaned_collections.append(f"user_sessions: {res.deleted_count}")

    res = await db.login_attempts.delete_many({"timestamp": {"$lt": cutoff_date}})
    if res.deleted_count:
        deleted_count += res.deleted_count
        cleaned_collections.append(f"login_attempts: {res.deleted_count}")

    return {
        "deleted_count": deleted_count,
        "cleaned_collections": cleaned_collections,
        "cutoff_date": cutoff_date.isoformat(),
    }


async def cleanup_analysis_results(days: int) -> Dict[str, Any]:
    db = get_mongo_db()
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    deleted_count = 0
    cleaned_collections = []

    res = await db.analysis_tasks.delete_many({
        "created_at": {"$lt": cutoff_date},
        "status": {"$in": ["completed", "failed"]},
    })
    if res.deleted_count:
        deleted_count += res.deleted_count
        cleaned_collections.append(f"analysis_tasks: {res.deleted_count}")

    res = await db.analysis_results.delete_many({"created_at": {"$lt": cutoff_date}})
    if res.deleted_count:
        deleted_count += res.deleted_count
        cleaned_collections.append(f"analysis_results: {res.deleted_count}")

    return {
        "deleted_count": deleted_count,
        "cleaned_collections": cleaned_collections,
        "cutoff_date": cutoff_date.isoformat(),
    }


async def cleanup_operation_logs(days: int) -> Dict[str, Any]:
    db = get_mongo_db()
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    deleted_count = 0
    cleaned_collections = []

    res = await db.user_sessions.delete_many({"created_at": {"$lt": cutoff_date}})
    if res.deleted_count:
        deleted_count += res.deleted_count
        cleaned_collections.append(f"user_sessions: {res.deleted_count}")

    res = await db.login_attempts.delete_many({"timestamp": {"$lt": cutoff_date}})
    if res.deleted_count:
        deleted_count += res.deleted_count
        cleaned_collections.append(f"login_attempts: {res.deleted_count}")

    res = await db.operation_logs.delete_many({"timestamp": {"$lt": cutoff_date}})
    if res.deleted_count:
        deleted_count += res.deleted_count
        cleaned_collections.append(f"operation_logs: {res.deleted_count}")

    return {
        "deleted_count": deleted_count,
        "cleaned_collections": cleaned_collections,
        "cutoff_date": cutoff_date.isoformat(),
    }


# === backups.py ===
"""
Backup, import, and export routines extracted from DatabaseService.
"""

import json
import os
import io
import gzip
import zipfile
import asyncio
import subprocess
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

from app.core.database import get_mongo_db
from app.core.config import settings

logger = logging.getLogger(__name__)


def _check_mongodump_available() -> bool:
    """
    Check if mongodump command is available
    
    Check order:
    1. PATH in environment variables mongodump
    2. vendors/mongodb/*/bin/mongodump.exe (Portable version catalog)
    3. in the application directory tools/mongodb-tools/mongodump.exe
    """
    # 1. Check PATH for mongodump
    if shutil.which("mongodump") is not None:
        return True
    
    # 2. Check the vendors/mongodb directory (portable version)
    # Find the project root directory upward from the current file location
    current_file = os.path.abspath(__file__)
    project_root = current_file
    for _ in range(5):  # Search up to 5 levels upward
        project_root = os.path.dirname(project_root)
        vendors_mongodb = os.path.join(project_root, "vendors", "mongodb")
        if os.path.exists(vendors_mongodb):
            # Find mongodb-* subdirectory
            for item in os.listdir(vendors_mongodb):
                mongodb_dir = os.path.join(vendors_mongodb, item)
                if os.path.isdir(mongodb_dir):
                    mongodump_path = os.path.join(mongodb_dir, "bin", "mongodump.exe")
                    if os.path.exists(mongodump_path):
                        logger.info(f"✅ found MongoDB Database Tools: {mongodump_path}")
                        return True
            break
    
    # 3. Check the application directory tools/mongodb-tools
    app_dir = settings.TRADINGAGENTS_DATA_DIR
    if app_dir:
        # Try multiple possible paths
        possible_paths = [
            os.path.join(app_dir, "..", "tools", "mongodb-tools", "mongodump.exe"),
            os.path.join(app_dir, "tools", "mongodb-tools", "mongodump.exe"),
            os.path.join(os.path.dirname(app_dir), "tools", "mongodb-tools", "mongodump.exe"),
        ]
        for path in possible_paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                logger.info(f"✅ found MongoDB Database Tools: {abs_path}")
                return True
    
    return False


def _get_mongodump_command() -> str:
    """
    Get the full path to the mongodump command
    
    Return:
    - If found, returns the full path (Windows requires .exe extension)
    - If not found, return "mongodump" (depends on PATH)
    """
    # 1. Check PATH for mongodump
    mongodump_path = shutil.which("mongodump")
    if mongodump_path:
        return mongodump_path
    
    # 2. Check the vendors/mongodb directory (portable version)
    current_file = os.path.abspath(__file__)
    project_root = current_file
    for _ in range(5):  # Search up to 5 levels upward
        project_root = os.path.dirname(project_root)
        vendors_mongodb = os.path.join(project_root, "vendors", "mongodb")
        if os.path.exists(vendors_mongodb):
            # Find mongodb-* subdirectory
            for item in os.listdir(vendors_mongodb):
                mongodb_dir = os.path.join(vendors_mongodb, item)
                if os.path.isdir(mongodb_dir):
                    mongodump_path = os.path.join(mongodb_dir, "bin", "mongodump.exe")
                    if os.path.exists(mongodump_path):
                        return mongodump_path
            break
    
    # 3. Check the application directory tools/mongodb-tools
    app_dir = settings.TRADINGAGENTS_DATA_DIR
    if app_dir:
        possible_paths = [
            os.path.join(app_dir, "..", "tools", "mongodb-tools", "mongodump.exe"),
            os.path.join(app_dir, "tools", "mongodb-tools", "mongodump.exe"),
            os.path.join(os.path.dirname(app_dir), "tools", "mongodb-tools", "mongodump.exe"),
        ]
        for path in possible_paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                return abs_path
    
    # 4. If neither is found, return the default command (may fail, but let the caller handle it)
    return "mongodump"


async def create_backup_native(name: str, backup_dir: str, collections: Optional[List[str]] = None, user_id: str | None = None) -> Dict[str, Any]:
    """
    Create a backup using MongoDB s native mongodump command (recommended, fast)

    Advantages:
    - Fast (operate BSON directly, no JSON conversion required)
    - High compression efficiency
    - Support large data volumes
    - Process multiple collections in parallel

    Requirements:
    - Need to be installed in the system MongoDB Database Tools
    - mongodump Commands available in PATH
    
    Note:
    - If mongodump is unavailable, the system will automatically downgrade to the Python implementation (create_backup)
    """
    if not _check_mongodump_available():
        logger.warning("⚠️ mongodump Command is not available, will automatically use Python implementation (slower)")
        logger.warning("💡 Tip: Install MongoDB Database Tools for faster backups")
        logger.warning("   Download address:https://www.mongodb.com/try/download/database-tools")
        raise Exception("mongodump The command is not available, please install MongoDB Database Tools or use create_backup() method")

    db = get_mongo_db()

    backup_id = str(ObjectId())
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_dirname = f"backup_{name}_{timestamp}"
    backup_path = os.path.join(backup_dir, backup_dirname)

    os.makedirs(backup_dir, exist_ok=True)

    # Get mongodump command path
    mongodump_cmd = _get_mongodump_command()
    
    # Build mongodump command
    cmd = [
        mongodump_cmd,
        "--uri", settings.MONGO_URI,
        "--out", backup_path,
        "--gzip"  # Enable compression
    ]

    # If collections are specified, only these collections are backed up
    if collections:
        for collection_name in collections:
            cmd.extend(["--collection", collection_name])

    logger.info(f"🔄 Start performing mongodump backup: {name}")

    # 🔥 Use asyncio.to_thread to perform blocking subprocess calls in the thread pool
    def _run_mongodump():
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        if result.returncode != 0:
            raise Exception(f"mongodump Execution failed: {result.stderr}")
        return result

    try:
        await asyncio.to_thread(_run_mongodump)
        logger.info(f"✅ mongodump Backup completed: {name}")
    except subprocess.TimeoutExpired:
        raise Exception("备份超时（超过1小时）")
    except Exception as e:
        logger.error(f"❌ mongodump Backup failed: {e}")
        # Clean up failed backup directories
        if os.path.exists(backup_path):
            await asyncio.to_thread(shutil.rmtree, backup_path)
        raise

    # Calculate backup size
    def _get_dir_size(path):
        total = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                total += os.path.getsize(filepath)
        return total

    file_size = await asyncio.to_thread(_get_dir_size, backup_path)

    # Get the set list of actual backups
    if not collections:
        collections = await db.list_collection_names()
        collections = [c for c in collections if not c.startswith("system.")]

    backup_meta = {
        "_id": ObjectId(backup_id),
        "name": name,
        "filename": backup_dirname,
        "file_path": backup_path,
        "size": file_size,
        "collections": collections,
        "created_at": datetime.utcnow(),
        "created_by": user_id,
        "backup_type": "mongodump",  # Mark backup type
    }

    await db.database_backups.insert_one(backup_meta)

    return {
        "id": backup_id,
        "name": name,
        "filename": backup_dirname,
        "file_path": backup_path,
        "size": file_size,
        "collections": collections,
        "created_at": backup_meta["created_at"].isoformat(),
        "backup_type": "mongodump",
    }


async def create_backup(name: str, backup_dir: str, collections: Optional[List[str]] = None, user_id: str | None = None) -> Dict[str, Any]:
    """
    Create database backup (implemented in Python, good compatibility but slow)

    For large data volumes (>100MB) , Recommended create_backup_native() method
    """
    db = get_mongo_db()

    backup_id = str(ObjectId())
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_{name}_{timestamp}.json.gz"
    backup_path = os.path.join(backup_dir, backup_filename)

    if not collections:
        collections = await db.list_collection_names()

    backup_data: Dict[str, Any] = {
        "backup_id": backup_id,
        "name": name,
        "created_at": datetime.utcnow().isoformat(),
        "created_by": user_id,
        "collections": collections,
        "data": {},
    }

    for collection_name in collections:
        collection = db[collection_name]
        documents: List[dict] = []
        async for doc in collection.find():
            documents.append(serialize_document(doc))
        backup_data["data"][collection_name] = documents

    os.makedirs(backup_dir, exist_ok=True)

    # 🔥 Use asyncio.to_thread to put blocked file I/O operations into the thread pool for execution
    def _write_backup():
        with gzip.open(backup_path, "wt", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        return os.path.getsize(backup_path)

    file_size = await asyncio.to_thread(_write_backup)

    backup_meta = {
        "_id": ObjectId(backup_id),
        "name": name,
        "filename": backup_filename,
        "file_path": backup_path,
        "size": file_size,
        "collections": collections,
        "created_at": datetime.utcnow(),
        "created_by": user_id,
    }

    await db.database_backups.insert_one(backup_meta)

    return {
        "id": backup_id,
        "name": name,
        "filename": backup_filename,
        "file_path": backup_path,
        "size": file_size,
        "collections": collections,
        "created_at": backup_meta["created_at"].isoformat(),
    }


async def list_backups() -> List[Dict[str, Any]]:
    db = get_mongo_db()
    backups: List[Dict[str, Any]] = []
    async for backup in db.database_backups.find().sort("created_at", -1):
        backups.append({
            "id": str(backup["_id"]),
            "name": backup["name"],
            "filename": backup["filename"],
            "size": backup["size"],
            "collections": backup["collections"],
            "created_at": backup["created_at"].isoformat(),
            "created_by": backup.get("created_by"),
        })
    return backups


async def delete_backup(backup_id: str) -> None:
    db = get_mongo_db()
    backup = await db.database_backups.find_one({"_id": ObjectId(backup_id)})
    if not backup:
        raise Exception("备份不存在")
    if os.path.exists(backup["file_path"]):
        # 🔥 Use asyncio.to_thread to put the blocked file deletion operation into the thread pool for execution
        backup_type = backup.get("backup_type", "python")
        if backup_type == "mongodump":
            # mongodump The backup is a directory and needs to be deleted recursively
            await asyncio.to_thread(shutil.rmtree, backup["file_path"])
        else:
            # Python The backup is a single file
            await asyncio.to_thread(os.remove, backup["file_path"])
    await db.database_backups.delete_one({"_id": ObjectId(backup_id)})


def _convert_date_fields(doc: dict) -> dict:
    """
    Convert date field in document (string -> datetime) 

    Common date fields:
    - created_at, updated_at, completed_at
    - started_at, finished_at
    - analysis_date (Keep the string format since it s a date not a timestamp)
    """
    from dateutil import parser

    date_fields = [
        "created_at", "updated_at", "completed_at",
        "started_at", "finished_at", "deleted_at",
        "last_login", "last_modified", "timestamp"
    ]

    for field in date_fields:
        if field in doc and isinstance(doc[field], str):
            try:
                # Trying to parse a date string
                doc[field] = parser.parse(doc[field])
                logger.debug(f"✅ 转换日期字段 {field}: {doc[field]}")
            except Exception as e:
                logger.warning(f"⚠️ 无法解析日期字段 {field}: {doc[field]}, 错误: {e}")

    return doc


async def import_data(content: bytes, collection: str, *, format: str = "json", overwrite: bool = False, filename: str | None = None) -> Dict[str, Any]:
    """
    Import data into database

    Two import modes are supported:
    1. Single collection mode: import data into the specified collection
    2. Multi-collection mode: Import export files containing multiple collections (auto-detection)
    
    Supported file formats:
    - JSON File(.json)
    - ZIP Compressed file (.zip), automatically decompressed and extracted JSON file
    """
    db = get_mongo_db()

    # Check if it is a ZIP file
    is_zip = False
    if filename and filename.lower().endswith('.zip'):
        is_zip = True
    elif content[:2] == b'PK':  # ZIP File magic number
        is_zip = True
    
    if is_zip:
        logger.info("📦 ZIP file detected, decompression started...")
        # 🔥 Use asyncio.to_thread to put the blocked ZIP decompression operation into the thread pool for execution
        def _extract_zip():
            zip_buffer = io.BytesIO(content)
            with zipfile.ZipFile(zip_buffer, 'r') as zipf:
                # Find JSON files
                json_files = [f for f in zipf.namelist() if f.lower().endswith('.json')]
                if not json_files:
                    raise Exception("ZIP JSON file not found in file")
                if len(json_files) > 1:
                    logger.warning(f"⚠️ ZIP The file contains multiple JSON files, use the first: {json_files[0]}")
                # Read the first JSON file
                json_content = zipf.read(json_files[0])
                return json_content.decode("utf-8")
        
        json_content_str = await asyncio.to_thread(_extract_zip)
        logger.info("✅ ZIP 文件解压成功")
        
        # parse JSON
        def _parse_json():
            return json.loads(json_content_str)
        
        data = await asyncio.to_thread(_parse_json)
    elif format.lower() == "json":
        # 🔥 Use asyncio.to_thread to put blocking JSON parsing into the thread pool for execution
        def _parse_json():
            return json.loads(content.decode("utf-8"))

        data = await asyncio.to_thread(_parse_json)
    else:
        raise Exception(f"不支持的格式: {format}")

    # Detect whether it is a multi-collection export format
    logger.info(f"🔍 [Import detection] data type: {type(data)}")

    # 🔥 New format: dictionary containing export_info and data
    if isinstance(data, dict) and "export_info" in data and "data" in data:
        logger.info("📦 New version of multi-collection export file detected (contains export_info)")
        export_info = data.get("export_info", {})
        logger.info(f"📋 导出信息: 创建时间={export_info.get('created_at')}, 集合数={len(export_info.get('collections', []))}")

        # Extract actual data
        data = data["data"]
        logger.info(f"📦 包含 {len(data)} 个集合: {list(data.keys())}")

    # 🔥 Old format: Direct mapping of collection names to document lists
    if isinstance(data, dict):
        logger.info(f"🔍 [导入检测] 字典包含 {len(data)} 个键")
        logger.info(f"🔍 [Import detection] key list: {list(data.keys())[:10]}")  # Only show the first 10

        # Check the type of each key-value pair
        for k, v in list(data.items())[:5]:  # Only check the first 5
            logger.info(f"🔍 [导入检测] 键 '{k}': 值类型={type(v)}, 是否为列表={isinstance(v, list)}")
            if isinstance(v, list):
                logger.info(f"🔍 [导入检测] 键 '{k}': 列表长度={len(v)}")

    if isinstance(data, dict) and all(isinstance(k, str) and isinstance(v, list) for k, v in data.items()):
        # Multiple collection mode
        logger.info(f"📦 确认为多集合导入模式，包含 {len(data)} 个集合")

        total_inserted = 0
        imported_collections = []

        for coll_name, documents in data.items():
            if not documents:  # skip empty collection
                logger.info(f"⏭️ 跳过空集合: {coll_name}")
                continue

            collection_obj = db[coll_name]

            if overwrite:
                deleted_count = await collection_obj.delete_many({})
                logger.info(f"🗑️ 清空集合 {coll_name}：删除 {deleted_count.deleted_count} 条文档")

            # Handling _id fields and date fields
            for doc in documents:
                # Convert _id
                if "_id" in doc and isinstance(doc["_id"], str):
                    try:
                        doc["_id"] = ObjectId(doc["_id"])
                    except Exception:
                        del doc["_id"]

                # 🔥 Convert date field (string -> datetime) 
                _convert_date_fields(doc)

            # Insert data
            if documents:
                res = await collection_obj.insert_many(documents)
                inserted_count = len(res.inserted_ids)
                total_inserted += inserted_count
                imported_collections.append(coll_name)
                logger.info(f"✅ 导入集合 {coll_name}：{inserted_count} 条文档")

        return {
            "mode": "multi_collection",
            "collections": imported_collections,
            "total_collections": len(imported_collections),
            "total_inserted": total_inserted,
            "filename": filename,
            "format": format,
            "overwrite": overwrite,
        }
    else:
        # Single collection mode (compatible with older versions)
        logger.info(f"📄 Single collection import mode, target collection: {collection}")
        logger.info(f"🔍 [Single collection mode] data type: {type(data)}")

        if isinstance(data, dict):
            logger.info(f"🔍 [单集合模式] 字典包含 {len(data)} 个键")
            logger.info(f"🔍 [Single collection mode] key list: {list(data.keys())[:10]}")

        collection_obj = db[collection]

        if not isinstance(data, list):
            logger.info("🔍 [Single collection mode] Data is not a list, convert to list")
            data = [data]

        logger.info(f"🔍 [单集合模式] 准备插入 {len(data)} 条文档")

        if overwrite:
            deleted_count = await collection_obj.delete_many({})
            logger.info(f"🗑️ 清空集合 {collection}：删除 {deleted_count.deleted_count} 条文档")

        for doc in data:
            # Convert _id
            if "_id" in doc and isinstance(doc["_id"], str):
                try:
                    doc["_id"] = ObjectId(doc["_id"])
                except Exception:
                    del doc["_id"]

            # 🔥 Convert date field (string -> datetime) 
            _convert_date_fields(doc)

        inserted_count = 0
        if data:
            res = await collection_obj.insert_many(data)
            inserted_count = len(res.inserted_ids)

        return {
            "mode": "single_collection",
            "collection": collection,
            "inserted_count": inserted_count,
            "filename": filename,
            "format": format,
            "overwrite": overwrite,
        }


def _sanitize_document(doc: Any) -> Any:
    """
    Recursively clear sensitive fields in documents

    Sensitive field keywords:api_key, api_secret, secret, token, password,
                    client_secret, webhook_secret, private_key

    Exclude fields:max_tokens, timeout, retry_times and other configuration fields (not sensitive information)
    """
    SENSITIVE_KEYWORDS = [
        "api_key", "api_secret", "secret", "token", "password",
        "client_secret", "webhook_secret", "private_key"
    ]

    # Excluded fields (although they contain sensitive keywords, they are not sensitive information)
    EXCLUDED_FIELDS = [
        "max_tokens",      # LLM Configuration: maximum number of tokens
        "timeout",         # timeout
        "retry_times",     # Number of retries
        "context_length",  # context length
    ]

    if isinstance(doc, dict):
        sanitized = {}
        for k, v in doc.items():
            # Check if it is in the exclusion list
            if k.lower() in [f.lower() for f in EXCLUDED_FIELDS]:
                # keep this field
                if isinstance(v, (dict, list)):
                    sanitized[k] = _sanitize_document(v)
                else:
                    sanitized[k] = v
            # Check whether the field name contains sensitive keywords (ignoring case)
            elif any(keyword in k.lower() for keyword in SENSITIVE_KEYWORDS):
                sanitized[k] = ""  # Clear sensitive fields
            elif isinstance(v, (dict, list)):
                sanitized[k] = _sanitize_document(v)  # Recursive processing
            else:
                sanitized[k] = v
        return sanitized
    elif isinstance(doc, list):
        return [_sanitize_document(item) for item in doc]
    else:
        return doc


async def export_data(collections: Optional[List[str]] = None, *, export_dir: str, format: str = "json", sanitize: bool = False) -> str:
    import pandas as pd

    # 🔥 Use an asynchronous database connection
    db = get_mongo_db()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if not collections:
        # 🔥 asynchronous call list_collection_names()
        collections = await db.list_collection_names()
        collections = [c for c in collections if not c.startswith("system.")]

    os.makedirs(export_dir, exist_ok=True)

    all_data: Dict[str, List[dict]] = {}
    for collection_name in collections:
        collection = db[collection_name]
        docs: List[dict] = []

        # users The collection only exports empty arrays in desensitization mode (the structure is retained and the actual user data is not exported)
        if sanitize and collection_name == "users":
            all_data[collection_name] = []
            continue

        # 🔥 Asynchronous iteration of query results
        async for doc in collection.find():
            docs.append(serialize_document(doc))
        all_data[collection_name] = docs

    # If desensitization is enabled, all sensitive fields will be cleared recursively.
    if sanitize:
        all_data = _sanitize_document(all_data)

    if format.lower() == "json":
        filename = f"export_{timestamp}.json"
        file_path = os.path.join(export_dir, filename)
        export_data_dict = {
            "export_info": {
                "created_at": datetime.utcnow().isoformat(),
                "collections": collections,
                "format": format,
            },
            "data": all_data,
        }

        # 🔥 Use asyncio.to_thread to put blocked file I/O operations into the thread pool for execution
        def _write_json():
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data_dict, f, ensure_ascii=False, indent=2)

        await asyncio.to_thread(_write_json)
        
        # compressed file
        zip_filename = f"export_{timestamp}.zip"
        zip_path = os.path.join(export_dir, zip_filename)
        
        def _create_zip():
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(file_path, arcname=filename)
            # Delete temporary JSON files
            os.remove(file_path)
        
        await asyncio.to_thread(_create_zip)
        return zip_path

    if format.lower() == "csv":
        filename = f"export_{timestamp}.csv"
        file_path = os.path.join(export_dir, filename)
        rows: List[dict] = []
        for collection_name, documents in all_data.items():
            for doc in documents:
                row = {**doc}
                row["_collection"] = collection_name
                rows.append(row)

        # 🔥 Use asyncio.to_thread to put blocked file I/O operations into the thread pool for execution
        def _write_csv():
            if rows:
                pd.DataFrame(rows).to_csv(file_path, index=False, encoding="utf-8-sig")
            else:
                pd.DataFrame().to_csv(file_path, index=False, encoding="utf-8-sig")

        await asyncio.to_thread(_write_csv)
        
        # compressed file
        zip_filename = f"export_{timestamp}.zip"
        zip_path = os.path.join(export_dir, zip_filename)
        
        def _create_zip():
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(file_path, arcname=filename)
            # Delete temporary CSV file
            os.remove(file_path)
        
        await asyncio.to_thread(_create_zip)
        return zip_path

    if format.lower() in ["xlsx", "excel"]:
        filename = f"export_{timestamp}.xlsx"
        file_path = os.path.join(export_dir, filename)

        # 🔥 Use asyncio.to_thread to put blocked file I/O operations into the thread pool for execution
        def _write_excel():
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                for collection_name, documents in all_data.items():
                    df = pd.DataFrame(documents) if documents else pd.DataFrame()
                    sheet = collection_name[:31]
                    df.to_excel(writer, sheet_name=sheet, index=False)

        await asyncio.to_thread(_write_excel)
        
        # compressed file
        zip_filename = f"export_{timestamp}.zip"
        zip_path = os.path.join(export_dir, zip_filename)
        
        def _create_zip():
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(file_path, arcname=filename)
            # Delete temporary Excel files
            os.remove(file_path)
        
        await asyncio.to_thread(_create_zip)
        return zip_path

    raise Exception(f"不支持的导出格式: {format}")


# === __init__.py ===
status_checks = backups = cleanup = serialization = _sys.modules[__name__]

__all__ = [
    "status_checks",
    "backups",
    "cleanup",
    "serialization",
]

# === queue.py ===
import sys as _sys

# === keys.py ===
"""
Redis key names and configuration constants used by queue services (centrally defined)
"""

# Redis Key name constant
READY_LIST = "qa:ready"

TASK_PREFIX = "qa:task:"
BATCH_PREFIX = "qa:batch:"
SET_PROCESSING = "qa:processing"
SET_COMPLETED = "qa:completed"
SET_FAILED = "qa:failed"
BATCH_TASKS_PREFIX = "qa:batch_tasks:"

# Concurrency control related
USER_PROCESSING_PREFIX = "qa:user_processing:"
GLOBAL_CONCURRENT_KEY = "qa:global_concurrent"
VISIBILITY_TIMEOUT_PREFIX = "qa:visibility:"

# Configuration Constants - Open Source Edition Limitations
DEFAULT_USER_CONCURRENT_LIMIT = 3
GLOBAL_CONCURRENT_LIMIT = 3  # The global maximum concurrency limit of the open source version is 3
VISIBILITY_TIMEOUT_SECONDS = 300  # 5 minutes


# === helpers.py ===
"""
Auxiliary function for the queue service (related to Redis operations) to facilitate thin delegation in the main service.
"""
import time
from typing import Dict
try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None


async def check_user_concurrent_limit(r: Redis, user_id: str, limit: int) -> bool:
    """检查用户并发限制"""
    user_processing_key = USER_PROCESSING_PREFIX + user_id
    current_count = await r.scard(user_processing_key)
    return current_count < limit


async def check_global_concurrent_limit(r: Redis, limit: int) -> bool:
    """Check global concurrency limit (based on processing collection size)"""
    current_count = await r.scard(SET_PROCESSING)
    return current_count < limit


async def mark_task_processing(r: Redis, task_id: str, user_id: str) -> None:
    """标记任务为处理中"""
    user_processing_key = USER_PROCESSING_PREFIX + user_id
    await r.sadd(user_processing_key, task_id)
    await r.sadd(SET_PROCESSING, task_id)


async def unmark_task_processing(r: Redis, task_id: str, user_id: str) -> None:
    """取消任务处理中标记"""
    user_processing_key = USER_PROCESSING_PREFIX + user_id
    await r.srem(user_processing_key, task_id)
    await r.srem(SET_PROCESSING, task_id)


async def set_visibility_timeout(r: Redis, task_id: str, worker_id: str, visibility_timeout: int) -> None:
    """设置可见性超时"""
    timeout_key = VISIBILITY_TIMEOUT_PREFIX + task_id
    timeout_data: Dict[str, str] = {
        "task_id": task_id,
        "worker_id": worker_id,
        "timeout_at": str(int(time.time()) + visibility_timeout),
    }
    await r.hset(timeout_key, mapping=timeout_data)
    await r.expire(timeout_key, visibility_timeout)


async def clear_visibility_timeout(r: Redis, task_id: str) -> None:
    """清除可见性超时"""
    timeout_key = VISIBILITY_TIMEOUT_PREFIX + task_id
    await r.delete(timeout_key)


# === __init__.py ===
"""
Queue subpackage
- keys: Redis Key names and constants
- helpers: Queue-related Redis operation helper functions
"""

# === auth_service.py ===
import time
from datetime import datetime, timedelta, timezone
from app.utils.timezone import now_tz
from typing import Optional
try:
    import jwt
except ImportError:
    jwt = None
from pydantic import BaseModel
from app.core.config import settings

class TokenData(BaseModel):
    sub: str
    exp: int
    session_id: Optional[str] = None  # add session_id

class AuthService:
    @staticmethod
    def create_access_token(
        sub: str,
        expires_minutes: int | None = None,
        expires_delta: int | None = None,
        session_id: Optional[str] = None  # Add session_id parameter
    ) -> str:
        if expires_delta:
            # If seconds are specified, use seconds
            expire = now_tz() + timedelta(seconds=expires_delta)
        else:
            # Otherwise use minutes
            expire = now_tz() + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        payload = {"sub": sub, "exp": expire}

        # If session_id is provided, add to payload
        if session_id:
            payload["session_id"] = session_id

        token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        return token

    @staticmethod
    def verify_token(token: str) -> Optional[TokenData]:
        import logging
        logger = logging.getLogger(__name__)

        try:
            logger.debug("🔍 开始验证token")
            logger.debug(f"📝 Token长度: {len(token)}")
            logger.debug(f"🔑 JWT密钥: {settings.JWT_SECRET[:10]}...")
            logger.debug(f"🔧 JWT算法: {settings.JWT_ALGORITHM}")

            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            logger.debug("✅ Token解码成功")
            logger.debug(f"📋 Payload: {payload}")

            token_data = TokenData(
                sub=payload.get("sub"),
                exp=int(payload.get("exp", time.time())),
                session_id=payload.get("session_id")  # parse session_id
            )
            logger.debug(f"🎯 Token data: sub={token_data.sub}, exp={token_data.exp}, session_id={token_data.session_id[:16] if token_data.session_id else 'None'}...")

            # Check if expired
            current_time = int(time.time())
            if token_data.exp < current_time:
                logger.warning(f"⏰ Token Expired: exp={token_data.exp}, now={current_time}")
                return None

            logger.debug("✅ Token验证成功")
            return token_data

        except jwt.ExpiredSignatureError:
            logger.warning("⏰ Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"❌ Token无效: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ Token验证异常: {str(e)}")
            return None

# === user_service.py ===
"""
User Services - Database-based user management
"""

import atexit
import hashlib
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
try:
    import bcrypt
except ImportError:
    bcrypt = None
try:
    from pymongo import MongoClient
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

from app.core.config import settings
from app.models.user import User, UserCreate, UserUpdate, UserResponse

# Try importing log manager
try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    # If the import fails, use standard logging
    import logging
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger('user_service')


# Legacy SHA-256 hash prefix used to identify existing passwords that need to be upgraded
# SHA-256 Output is a 64-bit hexadecimal string; the bcrypt hash begins with $2 Beginning
_LEGACY_SHA256_PREFIX = "sha256:"
_BCRYPT_PREFIX = "$2"


class UserService:
    """用户服务类"""

    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI)
        self.db = self.client[settings.MONGO_DB]
        self.users_collection = self.db.users
        self._closed = False
        atexit.register(self._close_at_exit)

    def close(self, log: bool = True):
        """关闭数据库连接"""
        if self._closed:
            return

        if hasattr(self, 'client') and self.client:
            try:
                self.client.close()
            except Exception:
                pass

        self._closed = True

        if log and sys.meta_path is not None:
            try:
                logger.info("UserService MongoDB connection closed")
            except Exception:
                pass

    def _close_at_exit(self):
        """When the interpreter exits normally, the connection is closed and no log is written."""
        try:
            self.close(log=False)
        except Exception:
            pass

    def __del__(self):
        """Destructor, ensuring that the connection is closed and no logs are written during the interpreter shutdown phase."""
        try:
            self.close(log=False)
        except Exception:
            pass
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Password hash (using bcrypt + Automatically add salt)

        The return value is `$2` At the beginning, you can pass `bcrypt.checkpw` verify.
        Compatible with legacy SHA-256 hashes (automatically recognized and upgraded upon verification).
        """
        # bcrypt With built-in salt, the hash result of the same password is different every time, preventing rainbow table attacks.
        # rounds=12 Is the OWASP 2023 recommended value (about 250ms/hash)
        rounds = getattr(settings, "BCRYPT_ROUNDS", 12)
        salt = bcrypt.gensalt(rounds=rounds)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def _hash_legacy_sha256(password: str) -> str:
        """Legacy SHA-256 hash (no salt, only used to verify existing passwords)"""
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_bcrypt_hash(hashed: str) -> bool:
        """Determine whether it is a bcrypt hash (with $2 beginning)"""
        return bool(hashed) and hashed.startswith(_BCRYPT_PREFIX)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password

        Automatically recognizes bcrypt hashes and legacy SHA-256 hashes:
        - bcrypt Hash: Verify using bcrypt.checkpw
        - Legacy SHA-256 hash: Use SHA-256 comparison (caller is responsible for upgrading after successful verification)
        """
        if not hashed_password:
            return False
        if UserService._is_bcrypt_hash(hashed_password):
            try:
                return bcrypt.checkpw(
                    plain_password.encode("utf-8"),
                    hashed_password.encode("utf-8"),
                )
            except (ValueError, TypeError):
                return False
        # Legacy SHA-256 (unsalted) compatible paths
        return UserService._hash_legacy_sha256(plain_password) == hashed_password
    
    async def create_user(self, user_data: UserCreate) -> Optional[User]:
        """创建用户"""
        try:
            # Check if username already exists
            existing_user = self.users_collection.find_one({"username": user_data.username})
            if existing_user:
                logger.warning(f"用户名已存在: {user_data.username}")
                return None
            
            # Check if the mailbox already exists
            existing_email = self.users_collection.find_one({"email": user_data.email})
            if existing_email:
                logger.warning(f"邮箱已存在: {user_data.email}")
                return None
            
            # Create user documentation
            user_doc = {
                "username": user_data.username,
                "email": user_data.email,
                "hashed_password": self.hash_password(user_data.password),
                "is_active": True,
                "is_verified": False,
                "is_admin": False,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_login": None,
                "preferences": {
                    # Analyze preferences
                    "default_market": "A股",
                    "default_depth": "3",  # 1-5 level, level 3 is standard analysis (recommended)
                    "default_analysts": ["市场分析师", "基本面分析师"],
                    "auto_refresh": True,
                    "refresh_interval": 30,
                    # Appearance settings
                    "ui_theme": "light",
                    "sidebar_width": 240,
                    # language and region
                    "language": "zh-CN",
                    # Notification settings
                    "notifications_enabled": True,
                    "email_notifications": False,
                    "desktop_notifications": True,
                    "analysis_complete_notification": True,
                    "system_maintenance_notification": True
                },
                "daily_quota": 1000,
                "concurrent_limit": 3,
                "total_analyses": 0,
                "successful_analyses": 0,
                "failed_analyses": 0,
                "favorite_stocks": []
            }
            
            result = self.users_collection.insert_one(user_doc)
            user_doc["_id"] = result.inserted_id
            
            logger.info(f"✅ 用户创建成功: {user_data.username}")
            return User(**user_doc)
            
        except Exception as e:
            logger.error(f"❌ 创建用户失败: {e}")
            return None
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """用户认证"""
        try:
            logger.info(f"🔍 [authenticate_user] Start authenticating users: {username}")

            # Find users
            user_doc = self.users_collection.find_one({"username": username})
            logger.info(f"🔍 [authenticate_user] Database query results: {'Find user' if user_doc else 'User does not exist'}")

            if not user_doc:
                logger.warning(f"❌ [authenticate_user] User does not exist: {username}")
                return None

            logger.info(f"🔍 [authenticate_user] User information: username={user_doc.get('username')}, email={user_doc.get('email')}, is_active={user_doc.get('is_active')}")

            # Verify password (automatically recognizes bcrypt / legacy SHA-256)
            stored_hash = user_doc.get("hashed_password", "")
            # ⚠️ Security: Do not log any password hashes (even prefixes)
            logger.info(f"🔍 [authenticate_user] Store password hash type: {'bcrypt' if self._is_bcrypt_hash(stored_hash) else 'legacy_sha256' if stored_hash else 'empty'}")

            if not self.verify_password(password, stored_hash):
                logger.warning(f"❌ [authenticate_user] Wrong password: {username}")
                return None

            # 🔐 Older SHA-256 hashes are automatically upgraded to bcrypt (transparent upgrade, no user awareness)
            if not self._is_bcrypt_hash(stored_hash):
                try:
                    new_bcrypt_hash = self.hash_password(password)
                    self.users_collection.update_one(
                        {"_id": user_doc["_id"]},
                        {"$set": {
                            "hashed_password": new_bcrypt_hash,
                            "updated_at": datetime.utcnow(),
                            "password_hash_algo": "bcrypt",
                        }}
                    )
                    logger.info(f"🔐 [authenticate_user] Legacy SHA-256 ciphers have been automatically upgraded to bcrypt: {username}")
                except Exception as upgrade_err:
                    # Failure to upgrade does not affect login, but alarms need to be logged.
                    logger.warning(f"⚠️ [authenticate_user] Password hash upgrade failed (login continues): {username} error={upgrade_err}")

            # Check if user is activated
            if not user_doc.get("is_active", True):
                logger.warning(f"❌ [authenticate_user] User disabled: {username}")
                return None

            # Update last login time
            self.users_collection.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"last_login": datetime.utcnow()}}
            )

            logger.info(f"✅ [authenticate_user] User authentication successful: {username}")
            return User(**user_doc)

        except Exception as e:
            logger.error(f"❌ 用户认证失败: {e}")
            return None
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        try:
            user_doc = self.users_collection.find_one({"username": username})
            if user_doc:
                return User(**user_doc)
            return None
        except Exception as e:
            logger.error(f"❌ 获取用户失败: {e}")
            return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据用户ID获取用户"""
        try:
            if not ObjectId.is_valid(user_id):
                return None
            
            user_doc = self.users_collection.find_one({"_id": ObjectId(user_id)})
            if user_doc:
                return User(**user_doc)
            return None
        except Exception as e:
            logger.error(f"❌ 获取用户失败: {e}")
            return None
    
    async def update_user(self, username: str, user_data: UserUpdate) -> Optional[User]:
        """更新用户信息"""
        try:
            update_data = {"updated_at": datetime.utcnow()}
            
            # Only update provided fields
            if user_data.email:
                # Check if the mailbox is already used by another user
                existing_email = self.users_collection.find_one({
                    "email": user_data.email,
                    "username": {"$ne": username}
                })
                if existing_email:
                    logger.warning(f"邮箱已被使用: {user_data.email}")
                    return None
                update_data["email"] = user_data.email
            
            if user_data.preferences:
                update_data["preferences"] = user_data.preferences.model_dump()
            
            if user_data.daily_quota is not None:
                update_data["daily_quota"] = user_data.daily_quota
            
            if user_data.concurrent_limit is not None:
                update_data["concurrent_limit"] = user_data.concurrent_limit
            
            result = self.users_collection.update_one(
                {"username": username},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 用户信息更新成功: {username}")
                return await self.get_user_by_username(username)
            else:
                logger.warning(f"用户不存在或无需更新: {username}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 更新用户信息失败: {e}")
            return None
    
    async def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """修改密码"""
        try:
            # Verify old password
            user = await self.authenticate_user(username, old_password)
            if not user:
                logger.warning(f"旧密码验证失败: {username}")
                return False
            
            # Update password
            new_hashed_password = self.hash_password(new_password)
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "hashed_password": new_hashed_password,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 密码修改成功: {username}")
                return True
            else:
                logger.error(f"❌ 密码修改失败: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 修改密码失败: {e}")
            return False
    
    async def reset_password(self, username: str, new_password: str) -> bool:
        """重置密码（管理员操作）"""
        try:
            new_hashed_password = self.hash_password(new_password)
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "hashed_password": new_hashed_password,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 密码重置成功: {username}")
                return True
            else:
                logger.error(f"❌ 密码重置失败: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 重置密码失败: {e}")
            return False
    
    async def create_admin_user(
        self,
        username: str = "admin",
        password: Optional[str] = None,  # 🔥 Changed to optional and must be specified via environment variables or parameters
        email: str = "admin@tradingagents.cn"
    ) -> Optional[User]:
        """Create admin user
        
        ⚠️ Security warning: No more hard-coded default passwords.
        The password must be specified in one of the following ways:
        1. Specified by parameter password
        2. Specified through the environment variable ADMIN_DEFAULT_PASSWORD
        
        If neither is specified, ValueError will be thrown.
        """
        # 🔥 Get passwords from environment variables or parameters, no longer using hardcoded defaults
        if password is None:
            import os
            password = os.getenv("ADMIN_DEFAULT_PASSWORD")
        
        if password is None:
            raise ValueError(
                "Creating an administrator user must specify a password. Please set environment variables ADMIN_DEFAULT_PASSWORD "
                "or calling create_admin_user() Pass in the password parameter."
            )
        
        # Check password strength (at least 8 characters)
        if len(password) < 8:
            logger.warning(f"⚠️ The administrator password is not long enough ({len(password)} bits), at least 8 bits recommended")
        
        try:
            # Check if an administrator already exists
            existing_admin = self.users_collection.find_one({"username": username})
            if existing_admin:
                logger.info(f"管理员用户已存在: {username}")
                return User(**existing_admin)
            
            # Create administrator user document
            admin_doc = {
                "username": username,
                "email": email,
                "hashed_password": self.hash_password(password),
                "is_active": True,
                "is_verified": True,
                "is_admin": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_login": None,
                "preferences": {
                    "default_market": "A股",
                    "default_depth": "深度",
                    "ui_theme": "light",
                    "language": "zh-CN",
                    "notifications_enabled": True,
                    "email_notifications": False
                },
                "daily_quota": 10000,  # Higher quota for administrators
                "concurrent_limit": 10,
                "total_analyses": 0,
                "successful_analyses": 0,
                "failed_analyses": 0,
                "favorite_stocks": []
            }
            
            result = self.users_collection.insert_one(admin_doc)
            admin_doc["_id"] = result.inserted_id

            logger.info(f"✅ 管理员用户创建成功: {username}")
            # ⚠️ Security: It is forbidden to output clear text passwords in the log; the password has been passed in through the environment variable, please record it yourself.
            logger.info("   🔐 The password has been encrypted and stored using bcrypt. Please keep the administrator password you set properly.")
            logger.info("   ⚠️  It is recommended to change your password immediately after logging in for the first time!")

            return User(**admin_doc)
            
        except Exception as e:
            logger.error(f"❌ 创建管理员用户失败: {e}")
            return None
    
    async def list_users(self, skip: int = 0, limit: int = 100) -> List[UserResponse]:
        """获取用户列表"""
        try:
            cursor = self.users_collection.find().skip(skip).limit(limit)
            users = []
            
            for user_doc in cursor:
                user = User(**user_doc)
                users.append(UserResponse(
                    id=str(user.id),
                    username=user.username,
                    email=user.email,
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    created_at=user.created_at,
                    last_login=user.last_login,
                    preferences=user.preferences,
                    daily_quota=user.daily_quota,
                    concurrent_limit=user.concurrent_limit,
                    total_analyses=user.total_analyses,
                    successful_analyses=user.successful_analyses,
                    failed_analyses=user.failed_analyses
                ))
            
            return users
            
        except Exception as e:
            logger.error(f"❌ 获取用户列表失败: {e}")
            return []
    
    async def deactivate_user(self, username: str) -> bool:
        """禁用用户"""
        try:
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "is_active": False,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 用户已禁用: {username}")
                return True
            else:
                logger.warning(f"用户不存在: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 禁用用户失败: {e}")
            return False
    
    async def activate_user(self, username: str) -> bool:
        """激活用户"""
        try:
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "is_active": True,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 用户已激活: {username}")
                return True
            else:
                logger.warning(f"用户不存在: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 激活用户失败: {e}")
            return False

    # =========================================================================
    # JD Cloud Basic Auth User — Automatically create files + Old users return
    # =========================================================================

    async def get_or_create_jdyun_user(self, jdyun_username: str, is_admin: bool = True) -> Optional[User]:
        """
        JD Cloud Cooperation Edition: Obtain or create JD Cloud user records.

        Background:
          - Each request of JD Cloud Gateway proxy will bring Authorization: Basic base64(username:token)
          - username It is the unique user identification assigned by JD Cloud platform (such as jcloud-ugidvcp / jdcloud-pid-test)
          - token It is the access token generated by the JD Cloud platform for the user (not the login password, which is decoupled from the user password)
          - We need to maintain a corresponding record in the users collection so that business functions such as tasks/reports/permissions can work properly
             (because 30+ The code needs to be user["id"] Convert to MongoDB ObjectId)

        Logic:
          1. Find in the users collection by username
          2. Found (old users): Update last_login → Return the user (real ObjectId)
          3. Not found (new user): insert a new record (is_admin=true, password hash placeholder,provider=jdyun) 
                      → Returns the user just created (real ObjectId)

        Args:
            jdyun_username: JD Cloud Platform Basic Auth decoded username
            is_admin: JD Cloud users are regarded as administrators by default (default True)

        Returns:
            User Model instance (id is a legal MongoDB ObjectId), returned on failure None
        """
        if not jdyun_username or not jdyun_username.strip():
            return None
        username = jdyun_username.strip()
        try:
            existing = self.users_collection.find_one({"username": username})
            if existing:
                # ===== Old users: Refresh last_login =====
                self.users_collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"last_login": datetime.utcnow(), "updated_at": datetime.utcnow()}},
                )
                existing["last_login"] = datetime.utcnow()
                logger.info(f"✅ [JD Cloud] Old user login: {username} (id={existing['_id']})")
                return User(**existing)

            # ===== New users: automatic profile creation =====
            # Password hash placeholder: The real access token is kept and verified by JD Cloud Gateway, we do not need to store it
            # Use bcrypt to hash a random string as a placeholder (anti-violence, also ensure that the User model hashed_password field is not empty)
            placeholder_password = f"__jdyun__{ObjectId()}__"  # Random and different every time
            hashed_placeholder = self.hash_password(placeholder_password)

            # Email adopts username@jdyun.local (Ensure that the email format is legal and unique)
            safe_email = f"{username.replace('@', '_at_')}@jdyun.local"

            new_user_doc = {
                "username": username,
                "email": safe_email,
                "hashed_password": hashed_placeholder,
                "password_hash_algo": "bcrypt",
                "is_active": True,
                "is_verified": True,          # Those certified by JD Cloud Platform are deemed to have been verified.
                "is_admin": is_admin,
                "provider": "jdyun",          # Source identification: JD Cloud Cooperation Edition
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_login": datetime.utcnow(),
                "preferences": {
                    "assistant_settings": {"name": "分析助理", "tone": "professional", "custom_instructions": ""},
                    "default_market": "A股",
                    "default_depth": "3",
                    "default_analysts": ["市场分析师", "基本面分析师"],
                    "auto_refresh": True,
                    "refresh_interval": 30,
                    "risk_preference": "neutral",
                    "ui_theme": "light",
                    "sidebar_width": 240,
                    "language": "zh-CN",
                    "notifications_enabled": True,
                    "email_notifications": False,
                    "desktop_notifications": True,
                    "analysis_complete_notification": True,
                    "system_maintenance_notification": True,
                },
                "daily_quota": 1000,
                "concurrent_limit": 3,
                "total_analyses": 0,
                "successful_analyses": 0,
                "failed_analyses": 0,
                "favorite_stocks": [],
            }
            result = self.users_collection.insert_one(new_user_doc)
            new_user_doc["_id"] = result.inserted_id
            logger.info(
                f"✅ [JD Cloud] New user automatically created profile successfully: {username} "
                f"(id={result.inserted_id}, admin={is_admin})"
            )
            return User(**new_user_doc)

        except Exception as e:
            logger.error(f"❌ [JD Cloud] User profile failed username={username}: {e}", exc_info=True)
            return None

    def is_existing_jdyun_user(self, jdyun_username: str) -> bool:
        """
        Check whether you are a registered JD Cloud user (old user).

        For Basic Auth hierarchical verification:
          - Already created (old user)→ Only verify username, not token (token is variable)
          - Not created (new user)→ Must be strictly verified username + token (Anti-counterfeiting)

        Args:
            jdyun_username: JD Cloud Platform Basic Auth decoded username

        Returns:
            Returns True if archived, otherwise False
        """
        if not jdyun_username or not jdyun_username.strip():
            return False
        try:
            doc = self.users_collection.find_one({
                "username": jdyun_username.strip(),
                "provider": "jdyun",
            })
            return doc is not None
        except Exception as e:
            logger.error(f"❌ [JD Cloud] Failed to query user username={jdyun_username}: {e}")
            return False


async def bootstrap_first_admin() -> bool:
    """First boot boot: When the users collection is empty, create an initial administrator based on ADMIN_DEFAULT_PASSWORD.

    The community version is not open for registration. The first login account is created by this guide (the password comes from .env
    ADMIN_DEFAULT_PASSWORD, Corresponds to the .env.example annotation). Only triggered when the library is empty,
    No existing accounts will be overwritten or modified.
    """
    try:
        if user_service.users_collection.count_documents({}) > 0:
            return False

        import os
        password = os.getenv("ADMIN_DEFAULT_PASSWORD")
        if not password:
            logger.warning(
                "⚠️ The user collection is empty and ADMIN_DEFAULT_PASSWORD is not set, skipping initial administrator creation."
                "Please set ADMIN_DEFAULT_PASSWORD (at least 8 bits) in .env and then restart the backend to complete the initialization."
            )
            return False

        admin = await user_service.create_admin_user(password=password)
        if admin:
            logger.info("✅ Initial administrator account has been created: admin, Please change your password immediately after logging in for the first time")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ 初始管理员引导失败: {e}")
        return False


# Global user service instance
user_service = UserService()

# === license_service.py ===
"""
Authorization service (community version thin shell)

This file is generated by the publish pipeline (scripts/publish_community.py):
See core/licensing/community_stub.py for the complete implementation, only re-export here.
Keep the external signature of app.services.license_service unchanged, and the community version caller has zero changes.
"""

from core.licensing.community_stub import (  # noqa: F401
    LicenseInfo,
    CommunityLicenseService as LicenseService,
    get_license_service,
    FREE_ACCESS_FEATURES,
)

# === jdyun_init.py ===
"""
JD Cloud Cooperation Edition - Automatic database initialization

When starting for the first time, read the configuration from the environment variables and write it to the database:
- llm_providers: JD Cloud Provider
- system_configs: 4 model configuration + Default model + Tushare data source + Embedding Configuration
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# JD Cloud initialization tag collection (used to avoid repeated initialization)
_JDYUN_INIT_MARKER = "jdyun_init_marker"


def _get_sync_db():
    """Get a synchronous MongoDB connection"""
    try:
        from app.core.database import get_mongo_db_sync
        return get_mongo_db_sync()
    except Exception as e:
        logger.error(f"❌ [JD Cloud initialization] Failed to obtain sync database connection: {e}")
        return None


def _is_jdyun_initialized(db) -> bool:
    """Check whether JD Cloud configuration has been initialized"""
    try:
        marker = db[_JDYUN_INIT_MARKER].find_one({"_id": "jdyun"})
        return marker is not None
    except Exception:
        return False


def _mark_jdyun_initialized(db):
    """标记京东云配置已初始化"""
    db[_JDYUN_INIT_MARKER].update_one(
        {"_id": "jdyun"},
        {"$set": {"initialized_at": datetime.utcnow(), "version": 1}},
        upsert=True,
    )


def _init_jdyun_provider(db, api_base: str, api_key: str, embedding_model: str):
    """Initialize JD Cloud Provider to llm_providers collection"""
    providers_collection = db.llm_providers

    # Check if it already exists
    existing = providers_collection.find_one({"name": "jdyun"})
    if existing:
        # Update existing records
        providers_collection.update_one(
            {"name": "jdyun"},
            {"$set": {
                "display_name": "京东云",
                "description": "JD Cloud Model Service (OpenAI compatible interface)",
                "website": "https://www.jdcloud.com",
                "api_doc_url": "https://docs.jdcloud.com",
                "default_base_url": api_base,
                "api_key": api_key,
                "is_active": True,
                "supported_features": ["chat", "completion", "embedding", "function_calling", "streaming"],
                "embedding_model": embedding_model,
                "updated_at": datetime.utcnow(),
            }},
        )
        logger.info("  ✓ Update JD Cloud Provider configuration")
    else:
        # Insert new record
        providers_collection.insert_one({
            "name": "jdyun",
            "display_name": "京东云",
            "description": "JD Cloud Model Service (OpenAI compatible interface)",
            "website": "https://www.jdcloud.com",
            "api_doc_url": "https://docs.jdcloud.com",
            "default_base_url": api_base,
            "api_key": api_key,
            "is_active": True,
            "supported_features": ["chat", "completion", "embedding", "function_calling", "streaming"],
            "embedding_model": embedding_model,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        logger.info("  ✓ Create JD Cloud Provider configuration")


def _build_jdyun_llm_configs(chat_models: List[str]) -> List[Dict[str, Any]]:
    """Build LLM configurations for 4 JD Cloud models"""
    configs = []
    for i, model_name in enumerate(chat_models):
        configs.append({
            "config_id": f"jdyun_{model_name.lower().replace('-', '_').replace('.', '_')}",
            "provider": "jdyun",
            "model_name": model_name,
            "model_display_name": model_name,
            "api_key": None,  # Use the factory configured API Key
            "api_base": None,  # Use the factory configured default_base_url
            "max_tokens": 8000,
            "temperature": 0.2,
            "timeout": 180,
            "retry_times": 3,
            "enabled": True,
            "description": f"京东云 {model_name} 模型",
            "capability_level": 3,
            "suitable_roles": ["both"],
            "features": ["tool_calling", "function_calling"],
            "recommended_depths": ["快速", "基础", "标准", "深度"],
            "priority": 10 - i,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
    return configs


def _init_system_config(db, chat_models: List[str], default_model: str, embedding_model: str, tushare_token: str):
    """Initialize system configuration to system_configs collection"""
    from app.core.jdyun import JDYUN_EMBEDDING_DIMS

    configs_collection = db.system_configs

    # Build LLM configuration list
    llm_configs = _build_jdyun_llm_configs(chat_models)

    # Build system settings
    system_settings = {
        "quick_analysis_model": default_model,
        "deep_analysis_model": default_model,
        "default_embedding_model": f"jdyun:{embedding_model}",
        "default_embedding_dims": JDYUN_EMBEDDING_DIMS,
    }

    # Build Tushare data source configuration
    data_source_configs = [{
        "name": "tushare",
        "type": "tushare",
        "api_key": tushare_token,
        "enabled": True,
        "priority": 100,
        "timeout": 30,
        "rate_limit": 100,
        "description": "Tushare A Stock data source (unified by JD Cloud)",
        "config_params": {},
        "market_categories": ["china"],
        "display_name": "Tushare",
        "provider": "tushare",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }]

    # Check if there is already an active configuration
    existing_config = configs_collection.find_one({"is_active": True}, sort=[("version", -1)])

    if existing_config:
        # Update existing configuration
        configs_collection.update_one(
            {"_id": existing_config["_id"]},
            {"$set": {
                "llm_configs": llm_configs,
                "system_settings": system_settings,
                "data_source_configs": data_source_configs,
                "updated_at": datetime.utcnow(),
            }},
        )
        logger.info(f"  ✓ 更新系统配置: {len(llm_configs)} 个模型, 默认模型={default_model}")
    else:
        # Create new configuration
        configs_collection.insert_one({
            "config_name": "jdyun_default",
            "config_type": "system",
            "llm_configs": llm_configs,
            "default_llm": default_model,
            "data_source_configs": data_source_configs,
            "database_configs": [],
            "system_settings": system_settings,
            "version": 1,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        logger.info(f"  ✓ 创建系统配置: {len(llm_configs)} 个模型, 默认模型={default_model}")


def init_jdyun_config():
    """
    Synchronize database configuration from environment variables when JD Cloud Edition starts

    Synchronization is performed on every startup (idempotent operation):
    - Update jdyun Provider in llm_providers (base_url/api_key/embedding_model)
    - Update model list in system_configs (parsed from OPENAI_MODEL comma separated) and default model
    - In this way, when changing the model, you only need to modify the OPENAI_MODEL environment variable, and it will take effect after restarting. There is no need to manually change the database.
    """
    from app.core.jdyun import (
        is_jdyun_mode, get_jdyun_api_base, get_jdyun_api_key,
        get_jdyun_default_model, get_jdyun_embedding_model,
        get_jdyun_tushare_token, get_jdyun_chat_models,
    )

    if not is_jdyun_mode():
        return False

    logger.info("🔧 [JD Cloud initialization] Start synchronizing database configuration from environment variables...")

    db = _get_sync_db()
    if db is None:
        logger.error("❌ [JD Cloud initialization] Unable to obtain database connection, skipping initialization")
        return False

    # Read environment variables
    api_base = get_jdyun_api_base()
    api_key = get_jdyun_api_key()
    default_model = get_jdyun_default_model()
    embedding_model = get_jdyun_embedding_model()
    tushare_token = get_jdyun_tushare_token()
    chat_models = get_jdyun_chat_models()

    if not api_base or not api_key:
        logger.error("❌ [JD Cloud initialization] OPENAI_API_BASE or OPENAI_API_KEY not set, skip initialization")
        return False

    if not tushare_token:
        logger.warning("⚠️ [JD Cloud initialization] TUSHARE_TOKEN If not set, data source functionality may not be available")

    try:
        # 1. Synchronization Provider (idempotent updates)
        _init_jdyun_provider(db, api_base, api_key, embedding_model)

        # 2. Synchronize system configuration (model list + Default model + data source)
        _init_system_config(db, chat_models, default_model, embedding_model, tushare_token)

        # 3. Tag is initialized
        _mark_jdyun_initialized(db)

        logger.info("✅ [JD Cloud initialization] Database configuration synchronization completed")
        logger.info(f"  - Provider: jdyun ({api_base})")
        logger.info(f"  - 模型: {', '.join(chat_models)}")
        logger.info(f"  - 默认模型: {default_model}")
        logger.info(f"  - Embedding: {embedding_model}")
        logger.info(f"  - Tushare: {'configured' if tushare_token else 'Not configured'}")
        return True

    except Exception as e:
        logger.error(f"❌ [JD Cloud initialization] Sync failed: {e}", exc_info=True)
        return False

# === community_bootstrap_service.py ===
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

try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

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

# === database_service.py ===
"""
数据库管理服务
"""

import json
import os
import csv
import gzip
import shutil
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
try:
    import motor.motor_asyncio
except ImportError:
    motor = None
try:
    import redis.asyncio as redis
except ImportError:
    redis = None
try:
    from pymongo.errors import ServerSelectionTimeoutError
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception

from app.core.database import get_mongo_db, get_redis_client, db_manager
from app.core.config import settings

logger = logging.getLogger(__name__)


class DatabaseService:
    """数据库管理服务"""

    def __init__(self):
        self.backup_dir = os.path.join(settings.TRADINGAGENTS_DATA_DIR, "backups")
        self.export_dir = os.path.join(settings.TRADINGAGENTS_DATA_DIR, "exports")

        # Make sure the directory exists
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(self.export_dir, exist_ok=True)

    async def get_database_status(self) -> Dict[str, Any]:
        """Get database connection status (delegate submodule)"""
        return await _db_status.get_database_status()

    async def _get_mongodb_status(self) -> Dict[str, Any]:
        """Get MongoDB status (delegate submodule)"""
        return await _db_status.get_mongodb_status()

    async def _get_redis_status(self) -> Dict[str, Any]:
        """Get Redis status (delegate submodule)"""
        return await _db_status.get_redis_status()

    async def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            db = get_mongo_db()

            # 🔑 Key: use list_collections() instead of list_collection_names()
            # This distinguishes between collections and views
            collections_info = []
            total_documents = 0
            total_size = 0
            views_count = 0

            # Get statistics for all collections in parallel
            import asyncio
            from pymongo.errors import OperationFailure

            async def get_collection_stats(collection_info: dict):
                """获取单个集合的统计信息"""
                collection_name = collection_info['name']
                collection_type = collection_info.get('type', 'collection')
                
                # If it is a view, skip statistics (views do not support collStats)
                if collection_type == 'view':
                    return {
                        "name": collection_name,
                        "type": "view",
                        "documents": 0,
                        "size": 0,
                        "storage_size": 0,
                        "indexes": 0,
                        "index_size": 0,
                        "note": "视图不支持统计"
                    }
                
                try:
                    stats = await db.command("collStats", collection_name)
                    # Use the count field in collStats to avoid additional count_documents queries
                    doc_count = stats.get('count', 0)

                    return {
                        "name": collection_name,
                        "type": "collection",
                        "documents": doc_count,
                        "size": stats.get('size', 0),
                        "storage_size": stats.get('storageSize', 0),
                        "indexes": stats.get('nindexes', 0),
                        "index_size": stats.get('totalIndexSize', 0)
                    }
                except OperationFailure as e:
                    # Check whether it is a view error (error code 166)
                    if e.code == 166 or 'view' in str(e).lower() or 'CommandNotSupportedOnView' in str(e):
                        logger.debug(f"跳过视图 {collection_name} 的统计（视图不支持 collStats）")
                        return {
                            "name": collection_name,
                            "type": "view",
                            "documents": 0,
                            "size": 0,
                            "storage_size": 0,
                            "indexes": 0,
                            "index_size": 0,
                            "note": "视图不支持统计"
                        }
                    else:
                        logger.error(f"获取集合 {collection_name} 统计失败: {e}")
                        return {
                            "name": collection_name,
                            "type": "collection",
                            "documents": 0,
                            "size": 0,
                            "storage_size": 0,
                            "indexes": 0,
                            "index_size": 0
                        }
                except Exception as e:
                    logger.error(f"获取集合 {collection_name} 统计失败: {e}")
                    return {
                        "name": collection_name,
                        "type": "collection",
                        "documents": 0,
                        "size": 0,
                        "storage_size": 0,
                        "indexes": 0,
                        "index_size": 0
                    }

            # Get information about all collections and views
            # 🔥 Fix: In Motor,list_collections() Returns CommandCursor, which needs to be called correctly
            try:
                collections_cursor = db.list_collections()
                collections_list = await collections_cursor.to_list(length=None)
            except AttributeError as e:
                # If the to_list method does not exist, the synchronization client may be misused
                logger.error(f"数据库客户端类型错误: {type(db)}, 错误: {e}")
                # Try using list_collection_names as an alternative
                collection_names = await db.list_collection_names()
                collections_list = [{"name": name, "type": "collection"} for name in collection_names]
            
            # Get statistics for all collections in parallel
            collections_info = await asyncio.gather(
                *[get_collection_stats(info) for info in collections_list]
            )
            
            # Number of statistical views
            views_count = sum(1 for info in collections_info if info.get('type') == 'view')

            # Calculate totals (only counts collections, not views)
            for collection_info in collections_info:
                if collection_info.get('type') == 'collection':
                    total_documents += collection_info['documents']
                    total_size += collection_info['storage_size']

            return {
                "total_collections": len([c for c in collections_info if c.get('type') == 'collection']),
                "total_views": views_count,
                "total_documents": total_documents,
                "total_size": total_size,
                "collections": collections_info
            }
        except Exception as e:
            raise Exception(f"获取数据库统计失败: {str(e)}")

    async def test_connections(self) -> Dict[str, Any]:
        """Test database connection (delegation submodule)"""
        return await _db_status.test_connections()

    async def _test_mongodb_connection(self) -> Dict[str, Any]:
        """Test MongoDB connection (delegation submodule)"""
        return await _db_status.test_mongodb_connection()

    async def _test_redis_connection(self) -> Dict[str, Any]:
        """Test Redis connection (delegation submodule)"""
        return await _db_status.test_redis_connection()

    async def create_backup(self, name: str, collections: List[str] = None, user_id: str = None) -> Dict[str, Any]:
        """
        Create database backup (automatically selects the best method)

        - If mongodump is available, use native backup (fast)
        - Otherwise use Python implementation (good compatibility but slower)
        """
        # Check if mongodump is available
        if _db_backups._check_mongodump_available():
            logger.info("✅ Use mongodump native backup (recommended)")
            return await _db_backups.create_backup_native(
                name=name,
                backup_dir=self.backup_dir,
                collections=collections,
                user_id=user_id
            )
        else:
            logger.warning("⚠️ mongodump Not available, use Python backup (slower)")
            logger.warning("💡 It is recommended to install MongoDB Database Tools for faster backup speed")
            return await _db_backups.create_backup(
                name=name,
                backup_dir=self.backup_dir,
                collections=collections,
                user_id=user_id
            )

    async def list_backups(self) -> List[Dict[str, Any]]:
        """Get backup list (delegated submodule)"""
        return await _db_backups.list_backups()

    async def delete_backup(self, backup_id: str) -> None:
        """删除备份（委托子模块）"""
        await _db_backups.delete_backup(backup_id)

    async def cleanup_old_data(self, days: int) -> Dict[str, Any]:
        """清理旧数据（委托子模块）"""
        return await _db_cleanup.cleanup_old_data(days)

    async def cleanup_analysis_results(self, days: int) -> Dict[str, Any]:
        """Clean up expired analysis results (delegation sub-module)"""
        return await _db_cleanup.cleanup_analysis_results(days)

    async def cleanup_operation_logs(self, days: int) -> Dict[str, Any]:
        """Clean operation log (delegation submodule)"""
        return await _db_cleanup.cleanup_operation_logs(days)

    async def import_data(self, content: bytes, collection: str, format: str = "json",
                         overwrite: bool = False, filename: str = None) -> Dict[str, Any]:
        """导入数据（委托子模块）"""
        return await _db_backups.import_data(content, collection, format=format, overwrite=overwrite, filename=filename)

    async def export_data(self, collections: List[str] = None, format: str = "json", sanitize: bool = False) -> str:
        """导出数据（委托子模块）"""
        return await _db_backups.export_data(collections, export_dir=self.export_dir, format=format, sanitize=sanitize)

    def _serialize_document(self, doc: dict) -> dict:
        """Serialize documents, handle special types (delegate submodule)"""
        return _serialize_doc(doc)

# === queue_service.py ===
"""
Enhanced version of queue service
Based on the existing implementation, add concurrency control, priority queue, visibility timeout and other functions
"""

import json
import time
import uuid
import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None

from app.core.database import get_redis_client

logger = logging.getLogger(__name__)

# Redis Key names and configuration constants are provided by app.services.queue.keys (not repeated here)


class QueueService:
    """增强版队列服务类"""

    def __init__(self, redis: Redis):
        self.r = redis
        self.user_concurrent_limit = DEFAULT_USER_CONCURRENT_LIMIT
        self.global_concurrent_limit = GLOBAL_CONCURRENT_LIMIT
        self.visibility_timeout = VISIBILITY_TIMEOUT_SECONDS

    def _clean_params_for_json(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Clean parameters and convert non-serializable objects to serializable format
        
        Args:
            params: Original parameter dictionary
            
        Returns:
            Cleaned parameter dictionary
        """
        cleaned = {}
        for key, value in params.items():
            try:
                if value is None:
                    cleaned[key] = None
                elif isinstance(value, (str, int, float, bool)):
                    # Basic types are retained directly
                    cleaned[key] = value
                elif isinstance(value, datetime):
                    # Convert datetime to ISO format string
                    cleaned[key] = value.isoformat()
                elif isinstance(value, dict):
                    # Recursively process nested dictionaries
                    cleaned[key] = self._clean_params_for_json(value)
                elif isinstance(value, (list, tuple)):
                    # Working with lists and tuples
                    cleaned[key] = [
                        self._clean_single_value(item) for item in value
                    ]
                elif hasattr(value, 'model_dump'):
                    # Pydantic v2 model
                    cleaned[key] = self._clean_params_for_json(value.model_dump())
                elif hasattr(value, 'dict'):
                    # Pydantic v1 model
                    cleaned[key] = self._clean_params_for_json(value.dict())
                elif hasattr(value, '__dict__'):
                    # Other objects, try converting to dictionary
                    try:
                        cleaned[key] = self._clean_params_for_json(value.__dict__)
                    except Exception:
                        cleaned[key] = str(value)
                else:
                    # Other types attempt JSON serialization and convert to string if that fails
                    try:
                        json.dumps(value)  # Test whether it can be serialized
                        cleaned[key] = value
                    except (TypeError, ValueError):
                        cleaned[key] = str(value)
            except Exception as e:
                # If processing fails, log a warning and use a string representation
                logger.warning(f"清理参数 {key} 时出错: {e}, 使用字符串表示")
                cleaned[key] = str(value)
        return cleaned
    
    def _clean_single_value(self, value: Any) -> Any:
        """清理单个值"""
        if value is None:
            return None
        elif isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, dict):
            return self._clean_params_for_json(value)
        elif isinstance(value, (list, tuple)):
            return [self._clean_single_value(item) for item in value]
        elif hasattr(value, 'model_dump'):
            return self._clean_params_for_json(value.model_dump())
        elif hasattr(value, 'dict'):
            return self._clean_params_for_json(value.dict())
        else:
            try:
                json.dumps(value)
                return value
            except (TypeError, ValueError):
                return str(value)

    async def enqueue_task(
        self,
        user_id: str,
        symbol: str,
        params: Dict[str, Any],
        batch_id: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> str:
        """Task enqueue (FIFO queue, no limit on submission concurrency, worker controls processing concurrency)

        Args:
            user_id: User ID
            symbol: Stock code
            params: Task parameters
            batch_id: Batch ID (optional)
            task_id: Task ID (optional, automatically generated if not provided)
        """

        # Comment out the concurrency limit check on submission - let the task be queued
        # Concurrency control is handled by Worker at dequeue_task time
        # if not await self._check_user_concurrent_limit(user_id):
        #     raise ValueError(f"User {user_id} Concurrency limit reached ({self.user_concurrent_limit})")
        # if not await self._check_global_concurrent_limit():
        #     raise ValueError(f"The system reaches the global concurrency limit ({self.global_concurrent_limit})")

        # If task_id is not provided, a new one is generated
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        key = TASK_PREFIX + task_id
        now = int(time.time())

        # 🔥 Clean parameters and convert non-serializable objects to serializable format
        cleaned_params = self._clean_params_for_json(params or {})
        
        mapping = {
            "id": task_id,
            "user": user_id,
            "symbol": symbol,
            "status": "queued",
            "created_at": str(now),
            "params": json.dumps(cleaned_params),
            "enqueued_at": str(now)
        }

        if batch_id:
            mapping["batch_id"] = batch_id

        # Save task data
        await self.r.hset(key, mapping=mapping)

        # Add to FIFO queue
        await self.r.lpush(READY_LIST, task_id)

        if batch_id:
            await self.r.sadd(BATCH_TASKS_PREFIX + batch_id, task_id)

        logger.info(f"任务已入队: {task_id}")
        return task_id

    async def dequeue_task(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """从FIFO队列中取出任务"""
        try:
            # Get tasks from FIFO queue
            task_id = await self.r.rpop(READY_LIST)
            if not task_id:
                return None

            # Get task details
            task_data = await self.get_task(task_id)
            if not task_data:
                logger.warning(f"任务数据不存在: {task_id}")
                return None

            user_id = task_data.get("user")

            # Concurrency limit check when dequeue is commented out - lets the Worker handle all queued tasks
            # Worker The concurrency control is implemented by semaphore, not the user concurrency limit here
            # if not await self._check_user_concurrent_limit(user_id):
            #     await self.r.lpush(READY_LIST, task_id)
            #     logger.warning(f"User {user_id} Concurrency limit, task requeue: {task_id}")
            #     return None

            # Mark task as in progress
            await self._mark_task_processing(task_id, user_id, worker_id)

            # Set visibility timeout
            await self._set_visibility_timeout(task_id, worker_id)

            # Update task status
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": "processing",
                "worker_id": worker_id,
                "started_at": str(int(time.time()))
            })

            logger.info(f"任务已出队: {task_id} -> Worker: {worker_id}")
            return task_data

        except Exception as e:
            logger.error(f"出队失败: {e}")
            return None

    async def ack_task(self, task_id: str, success: bool = True) -> bool:
        """确认任务完成"""
        try:
            task_data = await self.get_task(task_id)
            if not task_data:
                return False

            user_id = task_data.get("user")
            worker_id = task_data.get("worker_id")

            # Remove from processing collection
            await self._unmark_task_processing(task_id, user_id)

            # Clear visibility timeout
            await self._clear_visibility_timeout(task_id)

            # Update task status
            status = "completed" if success else "failed"
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": status,
                "completed_at": str(int(time.time()))
            })

            # Add to corresponding collection
            if success:
                await self.r.sadd(SET_COMPLETED, task_id)
            else:
                await self.r.sadd(SET_FAILED, task_id)

            logger.info(f"任务已确认: {task_id} (成功: {success})")
            return True

        except Exception as e:
            logger.error(f"确认任务失败: {e}")
            return False

    async def create_batch(self, user_id: str, symbols: List[str], params: Dict[str, Any]) -> tuple[str, int]:
        batch_id = str(uuid.uuid4())
        now = int(time.time())
        batch_key = BATCH_PREFIX + batch_id
        await self.r.hset(batch_key, mapping={
            "id": batch_id,
            "user": user_id,
            "status": "queued",
            "submitted": str(len(symbols)),
            "created_at": str(now),
        })
        for s in symbols:
            await self.enqueue_task(user_id=user_id, symbol=s, params=params, batch_id=batch_id)
        return batch_id, len(symbols)

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        key = TASK_PREFIX + task_id
        data = await self.r.hgetall(key)
        if not data:
            return None
        # parse fields
        if "params" in data:
            try:
                data["parameters"] = json.loads(data.pop("params"))
            except Exception:
                data["parameters"] = {}
        if "created_at" in data and data["created_at"].isdigit():
            data["created_at"] = int(data["created_at"])
        if "submitted" in data and str(data["submitted"]).isdigit():
            data["submitted"] = int(data["submitted"])
        return data

    async def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        key = BATCH_PREFIX + batch_id
        data = await self.r.hgetall(key)
        if not data:
            return None
        # enrich with tasks count if set exists
        submitted = data.get("submitted")
        if submitted is not None and str(submitted).isdigit():
            data["submitted"] = int(submitted)
        if "created_at" in data and data["created_at"].isdigit():
            data["created_at"] = int(data["created_at"])
        data["tasks"] = list(await self.r.smembers(BATCH_TASKS_PREFIX + batch_id))
        return data

    async def stats(self) -> Dict[str, int]:
        queued = await self.r.llen(READY_LIST)
        processing = await self.r.scard(SET_PROCESSING)
        completed = await self.r.scard(SET_COMPLETED)
        failed = await self.r.scard(SET_FAILED)
        return {
            "queued": int(queued or 0),
            "processing": int(processing or 0),
            "completed": int(completed or 0),
            "failed": int(failed or 0),
        }

    # New: Concurrency control methods
    async def _check_user_concurrent_limit(self, user_id: str) -> bool:
        """Check user concurrency limits (delegate helpers)"""
        return await check_user_concurrent_limit(self.r, user_id, self.user_concurrent_limit)

    async def _check_global_concurrent_limit(self) -> bool:
        """Check global concurrency limits (delegate helpers)"""
        return await check_global_concurrent_limit(self.r, self.global_concurrent_limit)

    async def _mark_task_processing(self, task_id: str, user_id: str, worker_id: str):
        """Mark a task as being processed (delegate helpers)"""
        await mark_task_processing(self.r, task_id, user_id)

    async def _unmark_task_processing(self, task_id: str, user_id: str):
        """Cancel the task processing mark (delegate helpers)"""
        await unmark_task_processing(self.r, task_id, user_id)

    async def _set_visibility_timeout(self, task_id: str, worker_id: str):
        """Set visibility timeout (delegate helpers)"""
        await set_visibility_timeout(self.r, task_id, worker_id, self.visibility_timeout)

    async def _clear_visibility_timeout(self, task_id: str):
        """清除可见性超时"""
        await clear_visibility_timeout(self.r, task_id)

    async def get_user_queue_status(self, user_id: str) -> Dict[str, int]:
        """获取用户队列状态"""
        user_processing_key = USER_PROCESSING_PREFIX + user_id
        processing_count = await self.r.scard(user_processing_key)

        return {
            "processing": int(processing_count or 0),
            "concurrent_limit": self.user_concurrent_limit,
            "available_slots": max(0, self.user_concurrent_limit - int(processing_count or 0))
        }

    async def cleanup_expired_tasks(self):
        """Clean up expired tasks (visibility timeout)"""
        try:
            # Get all visibility timeout keys
            timeout_keys = await self.r.keys(VISIBILITY_TIMEOUT_PREFIX + "*")

            current_time = int(time.time())
            expired_tasks = []

            for timeout_key in timeout_keys:
                timeout_data = await self.r.hgetall(timeout_key)
                if timeout_data:
                    timeout_at = int(timeout_data.get("timeout_at", 0))
                    if current_time > timeout_at:
                        task_id = timeout_data.get("task_id")
                        if task_id:
                            expired_tasks.append(task_id)

            # Handle overdue tasks
            for task_id in expired_tasks:
                await self._handle_expired_task(task_id)

            if expired_tasks:
                logger.warning(f"处理了 {len(expired_tasks)} 个过期任务")

        except Exception as e:
            logger.error(f"清理过期任务失败: {e}")

    async def _handle_expired_task(self, task_id: str):
        """处理过期任务"""
        try:
            task_data = await self.get_task(task_id)
            if not task_data:
                return

            user_id = task_data.get("user")

            # Remove from processing collection
            await self._unmark_task_processing(task_id, user_id)

            # Clear visibility timeout
            await self._clear_visibility_timeout(task_id)

            # rejoin queue
            await self.r.lpush(READY_LIST, task_id)

            # Update task status
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": "queued",
                "worker_id": "",
                "requeued_at": str(int(time.time()))
            })

            logger.warning(f"过期任务重新入队: {task_id}")

        except Exception as e:
            logger.error(f"处理过期任务失败: {task_id} - {e}")

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            task_data = await self.get_task(task_id)
            if not task_data:
                return False

            status = task_data.get("status")
            user_id = task_data.get("user")

            if status == "processing":
                # If it is being processed, remove it from the processing collection
                await self._unmark_task_processing(task_id, user_id)
                await self._clear_visibility_timeout(task_id)
            elif status == "queued":
                # If in queue, remove from queue
                await self.r.lrem(READY_LIST, 0, task_id)

            # Update task status
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": "cancelled",
                "cancelled_at": str(int(time.time()))
            })

            logger.info(f"任务已取消: {task_id}")
            return True

        except Exception as e:
            logger.error(f"取消任务失败: {e}")
            return False


def get_queue_service() -> QueueService:
    return QueueService(get_redis_client())

# === scheduler_service.py ===
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Scheduled task management service
Provides functions such as query, pause, resume, and manual triggering of scheduled tasks
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ImportError:
    class _DummySched:
        def __init__(self, *a, **kw): pass
        def add_job(self, *a, **kw): pass
        def start(self, *a, **kw): pass
        def shutdown(self, *a, **kw): pass
    BackgroundScheduler = AsyncIOScheduler = CronTrigger = IntervalTrigger = DateTrigger = Job = MemoryJobStore = _DummySched
try:
    from apscheduler.job import Job
except ImportError:
    class _DummySched:
        def __init__(self, *a, **kw): pass
        def add_job(self, *a, **kw): pass
        def start(self, *a, **kw): pass
        def shutdown(self, *a, **kw): pass
    BackgroundScheduler = AsyncIOScheduler = CronTrigger = IntervalTrigger = DateTrigger = Job = MemoryJobStore = _DummySched
try:
    from apscheduler.events import (
        EVENT_JOB_EXECUTED,
        EVENT_JOB_ERROR,
        EVENT_JOB_MISSED,
        JobExecutionEvent
    )
except ImportError:
    EVENT_JOB_EXECUTED = EVENT_JOB_ERROR = EVENT_JOB_MISSED = JobExecutionEvent = object

from app.core.database import get_mongo_db, get_mongo_db_sync
from tradingagents.utils.logging_manager import get_logger
from app.utils.timezone import now_tz

logger = get_logger(__name__)

# UTC+8 time zone
UTC_8 = timezone(timedelta(hours=8))
ACTIVE_EXECUTION_WINDOW_MINUTES = 30
FALLBACK_EXECUTION_WINDOW_MINUTES = 60


def get_utc8_now():
    """
    get UTC+8 Current time (naive datetime)

    Note: Returning a naive datetime (without time zone information), MongoDB will store the local time value as is
    In this way, the front end can be added directly +08:00 Suffix display
    """
    return now_tz().replace(tzinfo=None)


def get_execution_activity_time(execution: Optional[Dict[str, Any]]) -> Optional[datetime]:
    """To obtain the latest activity time of execution records, updated_at is preferred, and is compatible with old data falling back to timestamp."""
    if not execution:
        return None

    return execution.get("updated_at") or execution.get("timestamp") or execution.get("scheduled_time")


def build_active_running_query(job_filter: Optional[Dict[str, Any]] = None, window_minutes: int = ACTIVE_EXECUTION_WINDOW_MINUTES) -> Dict[str, Any]:
    """Build query conditions for running execution records that are still active."""
    active_threshold = get_utc8_now() - timedelta(minutes=window_minutes)
    query: Dict[str, Any] = {
        "status": "running",
        "$or": [
            {"updated_at": {"$gte": active_threshold}},
            {
                "updated_at": {"$exists": False},
                "timestamp": {"$gte": active_threshold}
            }
        ]
    }

    if job_filter:
        query.update(job_filter)

    return query


def build_recent_execution_query(job_filter: Dict[str, Any], statuses: Optional[List[str]] = None, window_minutes: int = ACTIVE_EXECUTION_WINDOW_MINUTES) -> Dict[str, Any]:
    """Construct query conditions for recently active execution records."""
    active_threshold = get_utc8_now() - timedelta(minutes=window_minutes)
    query: Dict[str, Any] = {
        **job_filter,
        "$or": [
            {"updated_at": {"$gte": active_threshold}},
            {
                "updated_at": {"$exists": False},
                "timestamp": {"$gte": active_threshold}
            }
        ]
    }

    if statuses is not None:
        query["status"] = {"$in": statuses} if len(statuses) > 1 else statuses[0]

    return query


class TaskCancelledException(Exception):
    """任务被取消异常"""
    pass


class SchedulerService:
    """定时任务管理服务"""

    def __init__(self, scheduler: AsyncIOScheduler):
        """
        Initialize service

        Args:
            scheduler: APScheduler Scheduler instance
        """
        self.scheduler = scheduler
        self.db = None

        # Add event listener to monitor task execution
        self._setup_event_listeners()
    
    def _get_db(self):
        """获取数据库连接"""
        if self.db is None:
            self.db = get_mongo_db()
        return self.db

    async def _get_active_running_executions(self, job_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Get the latest running execution records that still have heartbeats."""
        db = self._get_db()
        query = build_active_running_query({"job_id": job_id} if job_id else None)

        running_executions = await db.scheduler_executions.find(query).sort("timestamp", -1).to_list(length=100)

        running_by_job: Dict[str, Dict[str, Any]] = {}
        for exec_record in running_executions:
            current_job_id = exec_record.get("job_id")
            if current_job_id and current_job_id not in running_by_job:
                running_by_job[current_job_id] = exec_record

        return running_by_job

    def _build_execution_summary(self, exec_record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Build execution record summaries that can be used directly by the front end."""
        if not exec_record:
            return None

        started_at = exec_record.get("timestamp")
        updated_at = exec_record.get("updated_at")
        return {
            "execution_id": str(exec_record.get("_id")),
            "progress": exec_record.get("progress", 0),
            "processed_items": exec_record.get("processed_items"),
            "total_items": exec_record.get("total_items"),
            "current_item": exec_record.get("current_item"),
            "started_at": started_at.isoformat() if started_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None,
            "message": exec_record.get("progress_message")
        }
    
    async def list_jobs(self) -> List[Dict[str, Any]]:
        """
        Get a list of all scheduled tasks

        Returns:
            Task list (contains pending task information)
        """
        db = self._get_db()
        running_by_job = await self._get_active_running_executions()
        
        # 🔥 Get all suspended execution records (only query the suspended status, excluding the restored running status)
        # Note: Only records whose status is suspended are queried. Records that have been restored to running will not be displayed.
        suspended_executions = await db.scheduler_executions.find({
            "status": "suspended"
        }).sort("timestamp", -1).to_list(length=100)
        
        # 🔥 Debug log: record the number of pending tasks queried
        if suspended_executions:
            logger.debug(f"📊 查询到 {len(suspended_executions)} 个挂起任务: {[str(e.get('_id')) + ':' + e.get('job_id', '') + ':' + e.get('status', '') for e in suspended_executions[:5]]}")
        
        # 🔥 Grouped by job_id, each job_id only retains the latest pending record (for front-end display)
        suspended_by_job = {}
        for exec_record in suspended_executions:
            job_id = exec_record.get("job_id")
            if job_id:
                # 🔥 Only the latest pending record is kept for each job_id (sorted by timestamp, the first one is the latest)
                if job_id not in suspended_by_job:
                    suspended_by_job[job_id] = exec_record  # Only save the latest one
                # If there is already a record, since it is sorted by timestamp in reverse order, the first one is the latest and does not need to be updated.
        
        jobs = []
        for job in self.scheduler.get_jobs():
            job_dict = self._job_to_dict(job)
            # Get task metadata (trigger name and comments)
            metadata = await self._get_job_metadata(job.id)
            if metadata:
                job_dict["display_name"] = metadata.get("display_name")
                job_dict["description"] = metadata.get("description")

            latest_running = running_by_job.get(job.id)
            job_dict["has_running_execution"] = latest_running is not None
            if latest_running:
                job_dict["running_execution"] = self._build_execution_summary(latest_running)
            
            # 🔥 Check for pending execution records
            # Note: Only records whose status is suspended are displayed. Records that have been restored to running will not be displayed.
            # Only the latest pending record is displayed for each job_id
            if job.id in suspended_by_job:
                latest_suspended = suspended_by_job[job.id]  # Already the latest record sorted by timestamp
                # Confirm again that the status is suspended (to prevent data inconsistency)
                if latest_suspended.get("status") == "suspended":
                    job_dict["has_suspended_execution"] = True
                    job_dict["suspended_execution"] = {
                        "execution_id": str(latest_suspended["_id"]),
                        "progress": latest_suspended.get("progress", 0),
                        "processed_items": latest_suspended.get("processed_items"),
                        "total_items": latest_suspended.get("total_items"),
                        "current_item": latest_suspended.get("current_item"),
                        "started_at": latest_suspended.get("timestamp").isoformat() if latest_suspended.get("timestamp") else None,
                        "message": latest_suspended.get("progress_message")
                    }
                else:
                    # If the status is not suspended, no suspension prompt is displayed.
                    job_dict["has_suspended_execution"] = False
            else:
                job_dict["has_suspended_execution"] = False
            
            jobs.append(job_dict)

        logger.info(f"📋 获取到 {len(jobs)} 个定时任务")
        return jobs
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task details

        Args:
            job_id: Task ID

        Returns:
            Task details, returned if they do not exist None
        """
        job = self.scheduler.get_job(job_id)
        if job:
            job_dict = self._job_to_dict(job, include_details=True)
            running_by_job = await self._get_active_running_executions(job_id=job_id)
            # Get task metadata
            metadata = await self._get_job_metadata(job_id)
            if metadata:
                job_dict["display_name"] = metadata.get("display_name")
                job_dict["description"] = metadata.get("description")

            latest_running = running_by_job.get(job_id)
            job_dict["has_running_execution"] = latest_running is not None
            if latest_running:
                job_dict["running_execution"] = self._build_execution_summary(latest_running)
            return job_dict
        return None
    
    async def pause_job(self, job_id: str) -> bool:
        """
        Pause task
        
        Args:
            job_id: Task ID
            
        Returns:
            Is it successful?
        """
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"⏸️ 任务 {job_id} 已暂停")
            
            # Record operation history
            await self._record_job_action(job_id, "pause", "success")
            return True
        except Exception as e:
            logger.error(f"❌ 暂停任务 {job_id} 失败: {e}")
            await self._record_job_action(job_id, "pause", "failed", str(e))
            return False
    
    async def resume_job(self, job_id: str) -> bool:
        """
        recovery task

        Args:
            job_id: Task ID

        Returns:
            Is it successful?
        """
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"▶️ 任务 {job_id} 已恢复")

            # Record operation history
            await self._record_job_action(job_id, "resume", "success")
            return True
        except Exception as e:
            logger.error(f"❌ 恢复任务 {job_id} 失败: {e}")
            await self._record_job_action(job_id, "resume", "failed", str(e))
            return False

    async def reschedule_job(self, job_id: str, cron_expression: str) -> bool:
        """
        Modify the CRON expression of the task

        Args:
            job_id: Task ID
            cron_expression: New CRON expressions such as "0 8 * * 1-5"

        Returns:
            Is it successful?
        """
        from apscheduler.triggers.cron import CronTrigger
        from app.core.config import settings

        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                logger.error(f"❌ 任务 {job_id} 不存在")
                return False

            current_execution_id: Optional[str] = None

            # Validate CRON expression format
            try:
                new_trigger = CronTrigger.from_crontab(cron_expression, timezone=settings.TIMEZONE)
            except Exception as e:
                logger.error(f"❌ Invalid CRON expression '{cron_expression}': {e}")
                return False

            # Logging old trigger information
            old_trigger_str = str(job.trigger)

            # Modify task triggers
            self.scheduler.reschedule_job(job_id, trigger=new_trigger)

            logger.info(f"🔄 任务 {job_id} CRON已更新: {old_trigger_str} -> {cron_expression}")

            # Record operation history
            await self._record_job_action(
                job_id,
                "reschedule",
                "success",
                f"CRON表达式已更新: {cron_expression}"
            )
            return True

        except Exception as e:
            logger.error(f"❌ 修改任务 {job_id} CRON失败: {e}")
            await self._record_job_action(job_id, "reschedule", "failed", str(e))
            return False

    async def trigger_job(self, job_id: str, kwargs: Optional[Dict[str, Any]] = None, force: bool = False) -> bool:
        """
        Manually trigger task execution

        Note: If the task is in a suspended state, the task will be temporarily resumed first and will not be automatically suspended after execution once.

        Args:
            job_id: Task ID
            kwargs: Keyword arguments passed to the task function (optional)
            force: Whether to force execution (execute even if there is a running record), default False

        Returns:
            Is it successful?
            
        Raises:
            HTTPException: If there is a running record and force=False, Throws a 409 status code to prompt the user whether to force execution
        """
        from fastapi import HTTPException
        # 🔥 When triggered manually, add a flag to allow the task function to skip concurrency checks
        if kwargs is None:
            kwargs = {}
        kwargs["_manual_trigger"] = True  # Mark this as a manual trigger and allow execution
        if force:
            kwargs["_force_execute"] = True  # Whether the tag is enforced
        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                logger.error(f"❌ 任务 {job_id} 不存在")
                return False

            # Check whether the task is suspended (next_run_time is None to indicate suspension)
            was_paused = job.next_run_time is None
            if was_paused:
                logger.warning(f"⚠️ 任务 {job_id} 处于暂停状态，临时恢复以执行一次")
                self.scheduler.resume_job(job_id)
                # Reacquire the job object (the status has changed after recovery)
                job = self.scheduler.get_job(job_id)
                logger.info(f"✅ 任务 {job_id} 已临时恢复")

            # If kwargs are provided, merge into the task's kwargs
            # 🔥 Initialize merged_kwargs to avoid being undefined when kwargs is empty
            original_kwargs = job.kwargs.copy() if job.kwargs else {}
            merged_kwargs = original_kwargs.copy()
            
            if kwargs:
                # 🔥 First remove the internal tags (_resume_execution_id), these should not be passed to the task function
                clean_kwargs = {k: v for k, v in kwargs.items() if not k.startswith("_")}
                # Merge new kwargs (containing only parameters that the task function can accept)
                merged_kwargs = {**original_kwargs, **clean_kwargs}
                # Modify the kwargs of the task (so that update_job_progress can read the correct parameters)
                job.modify(kwargs=merged_kwargs)
                logger.info(f"📝 任务 {job_id} 参数已更新: {clean_kwargs} -> 合并后: {merged_kwargs}")

            # 🔥 First create an execution record and save kwargs to ensure that the correct parameters can be read during recovery.
            # In this way, even if the task is executed immediately, update_job_progress can read the correct kwargs
            try:
                db = self._get_db()
                # Get the final kwargs (merged)
                final_kwargs = job.kwargs.copy() if job.kwargs else {}
                if kwargs:
                    final_kwargs.update(kwargs)
                
                # 🔥 Check if it is a recovery operation (marked by _resume_execution_id)
                # Note: _resume_execution_id needs to be passed to the task function so that the task function knows that this is a resume execution and is allowed to execute
                resume_execution_id = final_kwargs.pop("_resume_execution_id", None)
                
                if resume_execution_id:
                    # This is a recovery operation, reusing the pending execution record
                    from bson import ObjectId
                    existing_record = await db.scheduler_executions.find_one({"_id": ObjectId(resume_execution_id)})
                    if existing_record:
                        current_execution_id = str(existing_record["_id"])
                        # 🔥 Read progress information from the execution record and add it to kwargs
                        processed_items = existing_record.get("processed_items")
                        if processed_items is not None:
                            final_kwargs["_resume_from_index"] = processed_items
                            logger.info(f"📊 Recovery operation: Read from execution record processed_items={processed_items}, has been added to kwargs")
                        else:
                            logger.warning("⚠️ There is no processed_items in the execution record and will start from 0")
                        
                        # 🔥 Add _resume_execution_id to final_kwargs as well so that the task function knows this is a resume execution
                        final_kwargs["_resume_execution_id"] = resume_execution_id
                        
                        # Update kwargs and status of existing records (note: final_kwargs contains _resume_from_index and _resume_execution_id)
                        # 🔥 Clear the cancellation mark because the user actively resumed the task and indicated that he wanted to continue execution.
                        await db.scheduler_executions.update_one(
                            {"_id": ObjectId(resume_execution_id)},
                            {
                                "$set": {
                                    "job_kwargs": final_kwargs,  # Save kwargs (contains _resume_from_index and _resume_execution_id)
                                    "status": "running",
                                    "is_manual": True,  # 🔥 When resuming execution, mark it as manual operation
                                    "cancel_requested": False,  # 🔥 Clear cancellation mark
                                    "updated_at": get_utc8_now()
                                }
                            }
                        )
                        
                        # 🔥 Also clears the cancellation marks of all related execution records (including subtasks)
                        related_update_result = await db.scheduler_executions.update_many(
                            {
                                "job_id": {"$regex": f"^{job_id}(_|$)"},  # Matches job_id or starts with job_id
                                "status": {"$in": ["running", "suspended"]}
                            },
                            {
                                "$set": {
                                    "cancel_requested": False,  # 🔥 Clear the cancellation flags of all related execution records
                                    "updated_at": get_utc8_now()
                                }
                            }
                        )
                        if related_update_result.modified_count > 0:
                            logger.info(f"✅ 同时清除了 {related_update_result.modified_count} 个相关执行记录的取消标记 "
                                      f"(job_id match: ^{job_id}(_|$))")
                        logger.info(f"📝 已复用执行记录 {resume_execution_id} 并更新kwargs: {final_kwargs} (is_manual=True)")
                    else:
                        logger.warning(f"⚠️ 指定的执行记录 {resume_execution_id} 不存在，将创建新记录")
                        resume_execution_id = None  # Mark it as None and create new records later.
                
                if not resume_execution_id:
                    # 🔥 It is not a recovery operation. Check whether there are suspended tasks (suspended status, no time limit)
                    # Prioritize the search for records in the suspended state (suspended tasks should resume execution)
                    suspended_record = await db.scheduler_executions.find_one(
                        {
                            "job_id": job_id,
                            "status": "suspended"
                        },
                        sort=[("timestamp", -1)]
                    )
                    
                    # 🔥 If there are no pending tasks, check whether there are still active running records.
                    # Judgment criteria: There is updated_at heartbeat in the last 30 minutes; old data is compatible with fallback to timestamp
                    if not suspended_record:
                        active_threshold = get_utc8_now() - timedelta(minutes=30)
                        running_record = await db.scheduler_executions.find_one(
                            {
                                "job_id": job_id,
                                "status": "running",
                                "$or": [
                                    {"updated_at": {"$gte": active_threshold}},
                                    {
                                        "updated_at": {"$exists": False},
                                        "timestamp": {"$gte": active_threshold}
                                    }
                                ]
                            },
                            sort=[("timestamp", -1)]
                        )
                        existing_record = running_record
                    else:
                        existing_record = suspended_record
                    
                    # 🔥 If no suspended or running records are found, check whether there is a canceled record (within 1 hour)
                    # If there is a canceled record, the user clicks"Execute immediately"A new task should be created and started from scratch
                    if not existing_record:
                        one_hour_ago = get_utc8_now() - timedelta(hours=1)
                        cancelled_record = await db.scheduler_executions.find_one(
                            {
                                "job_id": job_id,
                                "status": "cancelled",
                                "timestamp": {"$gte": one_hour_ago}
                            },
                            sort=[("timestamp", -1)]
                        )
                        # 🔥 If a canceled record is found, do not restore it, but create a new task (from scratch)
                        # So existing_record remains None and new records will be created later.
                        if cancelled_record:
                            logger.info(f"🔄 Canceled records within 1 hour were detected (execution_id={cancelled_record.get('_id')}) , "
                                      f"New tasks will be created from scratch and canceled records will not be restored.")
                    
                    if existing_record:
                        # 🔥 If it is in suspended state, execution will be automatically resumed (when triggered manually)
                        if existing_record.get("status") == "suspended":
                            current_execution_id = str(existing_record["_id"])
                            resume_execution_id = str(existing_record["_id"])
                            # Read progress information from execution records
                            processed_items = existing_record.get("processed_items")
                            if processed_items is not None:
                                final_kwargs["_resume_from_index"] = processed_items
                                logger.info(f"📊 Manually trigger the resumption of pending tasks: Read from execution record processed_items={processed_items}, has been added to kwargs")
                            else:
                                logger.warning("⚠️ There is no processed_items in the execution record and will start from 0")
                            
                            # Add _resume_execution_id to final_kwargs
                            final_kwargs["_resume_execution_id"] = resume_execution_id
                            
                            # Update the status of existing records to running and set is_manual=True (manually trigger recovery)
                            # 🔥 Clear the cancellation mark because the user actively triggered the task and indicated that it wanted to continue execution.
                            await db.scheduler_executions.update_one(
                                {"_id": existing_record["_id"]},
                                {
                                    "$set": {
                                        "job_kwargs": final_kwargs,
                                        "status": "running",
                                        "is_manual": True,  # 🔥 When recovery is triggered manually, it is marked as a manual operation
                                        "cancel_requested": False,  # 🔥 Clear cancellation mark
                                        "updated_at": get_utc8_now()
                                    }
                                }
                            )
                            
                            # 🔥 Also clears the cancellation marks of all related execution records (including subtasks)
                            related_update_result = await db.scheduler_executions.update_many(
                                {
                                    "job_id": {"$regex": f"^{job_id}(_|$)"},  # Matches job_id or starts with job_id
                                    "status": {"$in": ["running", "suspended"]}
                                },
                                {
                                    "$set": {
                                        "cancel_requested": False,  # 🔥 Clear the cancellation flags of all related execution records
                                        "updated_at": get_utc8_now()
                                    }
                                }
                            )
                            if related_update_result.modified_count > 0:
                                logger.info(f"✅ 同时清除了 {related_update_result.modified_count} 个相关执行记录的取消标记 "
                                          f"(job_id match: ^{job_id}(_|$))")
                            logger.info(f"🔄 When manually triggered, a suspended task is detected and execution is automatically resumed.: {resume_execution_id} (is_manual=True)")
                        else:
                            current_execution_id = str(existing_record["_id"])
                            # 🔥 If it is running state, check whether user confirmation is required
                            if not force:
                                # There is a running record and it is not forced. User confirmation is required.
                                running_instance_id = str(existing_record["_id"])
                                running_start_time = existing_record.get("timestamp")
                                running_progress = existing_record.get("progress", 0)
                                
                                logger.warning(f"⚠️ 任务 {job_id} 已有实例在运行（_id={running_instance_id}），需要用户确认是否强制执行")
                                
                                # Throws 409 Conflict, prompting the front end to display a confirmation dialog box
                                raise HTTPException(
                                    status_code=409,
                                    detail={
                                        "code": "TASK_ALREADY_RUNNING",
                                        "message": f"任务 {job_id} 已有实例正在运行中",
                                        "running_instance_id": running_instance_id,
                                        "running_start_time": running_start_time.isoformat() if running_start_time else None,
                                        "running_progress": running_progress,
                                        "suggestion": "Is it enforceable? Forcing execution will skip concurrency checks, potentially causing duplicate executions."
                                    }
                                )
                            
                            # When forcing, update kwargs and continue execution while clearing the cancellation flag
                            await db.scheduler_executions.update_one(
                                {"_id": existing_record["_id"]},
                                {
                                    "$set": {
                                        "job_kwargs": final_kwargs,
                                        "cancel_requested": False  # 🔥 Clear the cancellation mark and the user actively triggers the task
                                    }
                                }
                            )
                            logger.info(f"🔧 强制执行：已更新执行记录 {existing_record['_id']} 的kwargs: {final_kwargs}")
                    else:
                        # Create a new execution record (the task has just started)
                        # 🔥 When triggering manually, set is_manual=True, and clear the cancel flag
                        execution_record = {
                            "job_id": job_id,
                            "job_name": job.name if job else job_id,
                            "status": "running",
                            "timestamp": get_utc8_now(),
                            "scheduled_time": get_utc8_now(),
                            "is_manual": True,  # 🔥 Marked as manual operation when triggered manually
                            "cancel_requested": False,  # 🔥 New tasks are not marked as canceled by default
                            "job_kwargs": final_kwargs  # 🔥 Save kwargs (cleaned, does not contain _resume_execution_id)
                        }
                        insert_result = await db.scheduler_executions.insert_one(execution_record)
                        current_execution_id = str(insert_result.inserted_id)
                        logger.info(f"📝 Execution record created and saved kwargs: {final_kwargs} (is_manual=True)")
                        
                        # 🔥 Clear the old Redis cache immediately to ensure that the front-end does not read old data when querying the progress
                        try:
                            from app.core.database import get_redis_sync_client
                            from app.core.redis_client import RedisKeys
                            redis_sync = get_redis_sync_client()
                            if redis_sync:
                                progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                                redis_sync.delete(progress_key)
                                logger.info(f"🗑️ [手动触发] 已清除旧的Redis进度缓存: {progress_key}（新任务从头开始）")
                        except Exception as redis_error:
                            logger.warning(f"⚠️ [manual trigger] Failed to clear Redis cache (does not affect task execution): {redis_error}")
            except Exception as record_error:
                logger.warning(f"⚠️ Failed to save execution record kwargs (does not affect task execution): {record_error}")
            
            # 🔥 Execute the task immediately (without waiting for APScheduler scheduling)
            # This ensures that the task is executed immediately rather than waiting for the next scheduling cycle
            try:
                import asyncio
                import inspect
                
                # 🔥 Clean up internal tags in kwargs (these should not be passed to task functions)
                # But _resume_from_index, _resume_execution_id, _manual_trigger and _force_execute are retained because the task function needs them to determine whether execution is allowed
                # 🔥 Use final_kwargs instead of merged_kwargs because final_kwargs contains recovery location information
                clean_kwargs_for_execution = {}
                for k, v in final_kwargs.items():
                    if k.startswith("_") and k not in ["_resume_from_index", "_resume_execution_id", "_manual_trigger", "_force_execute"]:
                        # Skip internal tags (except _resume_from_index, _resume_execution_id, _manual_trigger and _force_execute)
                        continue
                    clean_kwargs_for_execution[k] = v
                
                # 🔥 If it is to resume execution, add _resume_execution_id to kwargs as well
                if resume_execution_id:
                    clean_kwargs_for_execution["_resume_execution_id"] = resume_execution_id
                
                # 🔥 Manual trigger flags are already included in final_kwargs (via kwargs["_manual_trigger"] = True) 
                
                logger.info(f"🔍 Build execution parameters: merged_kwargs={merged_kwargs}, final_kwargs={final_kwargs}, clean_kwargs_for_execution={clean_kwargs_for_execution}")

                if current_execution_id:
                    clean_kwargs_for_execution["_trigger_execution_id"] = current_execution_id
                    logger.info(f"🧷 Current manually triggered execution record ID: {current_execution_id}")
                
                # Get task function and parameters
                func = job.func
                
                # 🔥 Check the function signature and only pass parameters accepted by the function
                sig = inspect.signature(func)
                func_params = set(sig.parameters.keys())
                
                # Filter kwargs to only keep parameters accepted by the function
                filtered_kwargs = {}
                for k, v in clean_kwargs_for_execution.items():
                    # If the function has **kwargs parameter, or if the parameter name is in the function signature, it is passed
                    if k in func_params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                        filtered_kwargs[k] = v
                    else:
                        logger.debug(f"⏭️ 跳过参数 {k}（函数 {func.__name__} 不接受此参数）")
                
                # 🔥 Use filtered kwargs (only parameters accepted by the function)
                logger.info(f"⚡ 立即执行任务 {job_id} (协程函数, kwargs={filtered_kwargs})")
                
                # Check if the task function is a coroutine
                if inspect.iscoroutinefunction(func):
                    # Coroutine function, executed immediately (in the background)
                    asyncio.create_task(func(**filtered_kwargs))
                    logger.info(f"✅ 任务 {job_id} 已立即执行（协程函数，后台执行中）")
                else:
                    # Synchronous function, executed using thread pool
                    import concurrent.futures
                    logger.info(f"⚡ 立即执行任务 {job_id} (同步函数, kwargs={filtered_kwargs})")
                    # Use thread pool to execute synchronized functions
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    executor.submit(func, **filtered_kwargs)
                    logger.info(f"✅ 任务 {job_id} 已提交到线程池执行")
                
                # 🔥 Successful execution immediately, no need to call again job.modify(next_run_time=now)
                # Because this will trigger APScheduler to schedule the task again, resulting in repeated execution
                logger.info(f"🚀 任务 {job_id} 已立即执行 (was_paused={was_paused}, kwargs={clean_kwargs_for_execution})")
            except Exception as immediate_exec_error:
                # Immediate execution fails and falls back to APScheduler scheduling
                logger.warning(f"⚠️ 立即执行任务 {job_id} 失败，回退到APScheduler调度: {immediate_exec_error}", exc_info=True)
                # Triggering tasks manually - using current time with time zone
                from datetime import timezone
                now = datetime.now(timezone.utc)
                job.modify(next_run_time=now)
                logger.info(f"🚀 Scheduling tasks through APScheduler {job_id} (next_run_time={now})")

            # Record operation history
            action_note = f"Manually trigger execution (suspended state: {was_paused}"
            if kwargs:
                action_note += f", 参数: {kwargs}"
            action_note += ")"
            await self._record_job_action(job_id, "trigger", "success", action_note)

            # 🔥 NOTE: No longer called here _record_job_execution
            # Reason:
            # 1. The execution record has been created at lines 352-361 if it does not exist
            # 2. If you create it again here, it will result in duplicate records.
            # 3. update_job_progress Records will be created or updated at the start of the task
            # 4. If the record already exists, update_job_progress will update it; if it does not exist, it will create it
            logger.info(f"📝 任务 {job_id} 已触发，执行记录将在任务开始时由 update_job_progress 创建或更新")

            return True
        except Exception as e:
            logger.error(f"❌ 触发任务 {job_id} 失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            await self._record_job_action(job_id, "trigger", "failed", str(e))
            return False
    
    async def get_job_history(
        self,
        job_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get task execution history
        
        Args:
            job_id: Task ID
            limit: Return quantity limit
            offset: offset
            
        Returns:
            execution history
        """
        try:
            db = self._get_db()
            cursor = db.scheduler_history.find(
                {"job_id": job_id}
            ).sort("timestamp", -1).skip(offset).limit(limit)
            
            history = []
            async for doc in cursor:
                doc.pop("_id", None)
                history.append(doc)
            
            return history
        except Exception as e:
            logger.error(f"❌ 获取任务 {job_id} 执行历史失败: {e}")
            return []
    
    async def count_job_history(self, job_id: str) -> int:
        """
        Statistics of task execution history
        
        Args:
            job_id: Task ID
            
        Returns:
            Number of historical records
        """
        try:
            db = self._get_db()
            count = await db.scheduler_history.count_documents({"job_id": job_id})
            return count
        except Exception as e:
            logger.error(f"❌ 统计任务 {job_id} 执行历史失败: {e}")
            return 0
    
    async def get_all_history(
        self,
        limit: int = 50,
        offset: int = 0,
        job_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all task execution history
        
        Args:
            limit: Return quantity limit
            offset: offset
            job_id: Task ID filtering
            status: Status filtering
            
        Returns:
            execution history
        """
        try:
            db = self._get_db()
            
            # Build query conditions
            query = {}
            if job_id:
                query["job_id"] = job_id
            if status:
                query["status"] = status
            
            cursor = db.scheduler_history.find(query).sort("timestamp", -1).skip(offset).limit(limit)
            
            history = []
            async for doc in cursor:
                doc.pop("_id", None)
                history.append(doc)
            
            return history
        except Exception as e:
            logger.error(f"❌ 获取执行历史失败: {e}")
            return []
    
    async def count_all_history(
        self,
        job_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> int:
        """
        Count the execution history of all tasks

        Args:
            job_id: Task ID filtering
            status: Status filtering

        Returns:
            Number of historical records
        """
        try:
            db = self._get_db()

            # Build query conditions
            query = {}
            if job_id:
                query["job_id"] = job_id
            if status:
                query["status"] = status

            count = await db.scheduler_history.count_documents(query)
            return count
        except Exception as e:
            logger.error(f"❌ 统计执行历史失败: {e}")
            return 0

    async def get_job_executions(
        self,
        job_id: Optional[str] = None,
        status: Optional[str] = None,
        is_manual: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get task execution history

        Args:
            job_id: Task ID (optional, if not specified, all tasks will be returned)
            status: Status filtering (success/failed/missed/running)
            is_manual: Whether to trigger manually (True=manual,False=automatic,None=all)
            limit: Return quantity limit
            offset: offset

        Returns:
            Execution history list
        """
        try:
            db = self._get_db()

            # Build query conditions
            query = {}
            if job_id:
                query["job_id"] = job_id
            if status:
                query["status"] = status

            # Handling is_manual filtering
            if is_manual is not None:
                if is_manual:
                    # Manual trigger: is_manual must be true
                    query["is_manual"] = True
                else:
                    # Automatically triggered: is_manual field does not exist or is false
                    # Use $ne (not equal) to exclude is_manual=true records
                    query["is_manual"] = {"$ne": True}

            cursor = db.scheduler_executions.find(query).sort("timestamp", -1).skip(offset).limit(limit)

            executions = []
            async for doc in cursor:
                # Convert _id to string
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])

                # Formatted time (MongoDB stores naive datetime, which represents local time)
                # Directly serialize to ISO format string, the front end will automatically add +08:00 suffix
                for time_field in ["scheduled_time", "timestamp", "updated_at"]:
                    if doc.get(time_field):
                        dt = doc[time_field]
                        # If it is a datetime object, convert it to an ISO format string
                        if hasattr(dt, 'isoformat'):
                            doc[time_field] = dt.isoformat()

                executions.append(doc)

            return executions
        except Exception as e:
            logger.error(f"❌ Failed to obtain task execution history: {e}")
            return []

    async def count_job_executions(
        self,
        job_id: Optional[str] = None,
        status: Optional[str] = None,
        is_manual: Optional[bool] = None
    ) -> int:
        """
        Statistics of task execution history

        Args:
            job_id: Task ID (optional)
            status: Status filtering (optional)
            is_manual: Whether to trigger manually (optional)

        Returns:
            Execution history quantity
        """
        try:
            db = self._get_db()

            # Build query conditions
            query = {}
            if job_id:
                query["job_id"] = job_id
            if status:
                query["status"] = status

            # Handling is_manual filtering
            if is_manual is not None:
                if is_manual:
                    # Manual trigger: is_manual must be true
                    query["is_manual"] = True
                else:
                    # Automatically triggered: is_manual field does not exist or is false
                    query["is_manual"] = {"$ne": True}

            count = await db.scheduler_executions.count_documents(query)
            return count
        except Exception as e:
            logger.error(f"❌ Statistics task execution history failed: {e}")
            return 0

    async def cancel_job_execution(self, execution_id: str) -> bool:
        """
        Cancel/terminate task execution

        For the task being executed, set the cancellation mark;
        For tasks that have exited but are still running in the database, mark them directly as failed

        Args:
            execution_id: Execution record ID (MongoDB _id)

        Returns:
            Is it successful?
        """
        try:
            from bson import ObjectId
            db = self._get_db()

            # Find execution records
            execution = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
            if not execution:
                logger.error(f"❌ 执行记录不存在: {execution_id}")
                return False

            if execution.get("status") != "running":
                logger.warning(f"⚠️ The execution record status is not running: {execution_id} (status={execution.get('status')})")
                return False

            job_id = execution.get("job_id")
            
            # 🔥 Set cancellation mark: update the current execution record and all related execution records (including subtasks) at the same time
            # For example: If you cancel tushare_financial_sync, you must also cancel subtasks such as tushare_financial_sync_tushare
            update_result = await db.scheduler_executions.update_one(
                {"_id": ObjectId(execution_id)},
                {
                    "$set": {
                        "cancel_requested": True,
                        "updated_at": get_utc8_now()
                    }
                }
            )
            
            # 🔥 Also update all execution records starting with the job_id (including subtasks)
            # For example: all subtasks of tushare_financial_sync (tushare_financial_sync_tushare, etc.)
            if job_id:
                related_update_result = await db.scheduler_executions.update_many(
                    {
                        "job_id": {"$regex": f"^{job_id}(_|$)"},  # Matches job_id or starts with job_id
                        "status": {"$in": ["running", "suspended"]},
                        "cancel_requested": {"$ne": True}  # Only update records that have not yet been marked as cancelled.
                    },
                    {
                        "$set": {
                            "cancel_requested": True,
                            "updated_at": get_utc8_now()
                        }
                    }
                )
                if related_update_result.modified_count > 0:
                    logger.info(f"✅ 同时设置了 {related_update_result.modified_count} 个相关执行记录的取消标记 "
                              f"(job_id match: ^{job_id}(_|$))")
            
            # 🔥 Check if the update is successful
            if update_result.modified_count == 0:
                logger.warning(f"⚠️ Failed to set cancellation flag: execution record may not exist or status may have changed (execution_id={execution_id})")
                return False

            # 🔥 Update the Redis cache immediately so the front end can immediately see that the task has been cancelled.
            try:
                from app.core.database import get_redis_sync_client
                from app.core.redis_client import RedisKeys
                import json
                
                redis_sync = get_redis_sync_client()
                if redis_sync and job_id:
                    progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                    
                    # 🔥 Read the current progress data (if it exists)
                    existing_progress_str = redis_sync.get(progress_key)
                    if existing_progress_str:
                        try:
                            progress_data = json.loads(existing_progress_str)
                        except Exception:
                            progress_data = {}
                    else:
                        progress_data = {}
                    
                    # 🔥 The update status is"cancelling" (being canceled) and retain the current progress information
                    progress_data.update({
                        "status": "cancelling",  # 🔥 Mark as canceling
                        "message": "任务正在取消中...",
                        "updated_at": get_utc8_now().isoformat(),
                        "execution_id": execution_id
                    })
                    
                    # 🔥 Save to Redis (set a shorter TTL since the task will be canceled soon)
                    redis_sync.setex(
                        progress_key,
                        3600,  # 1 hours TTL
                        json.dumps(progress_data, ensure_ascii=False, default=str)
                    )
                    logger.info(f"✅ The Redis cache has been updated and the task status is cancelling: job_id={job_id}")
            except Exception as redis_error:
                # Redis Failure to update does not affect the cancellation operation
                logger.warning(f"⚠️ Failed to update Redis cache (does not affect cancellation operation): {redis_error}")

            logger.info(f"✅ 已设置取消标记: {execution.get('job_name', execution.get('job_id'))} "
                       f"(execution_id={execution_id}, job_id={execution.get('job_id')})")
            return True

        except Exception as e:
            logger.error(f"❌ 取消任务执行失败: {e}")
            return False

    async def mark_execution_as_failed(self, execution_id: str, reason: str = "用户手动标记为失败") -> bool:
        """
        Mark execution records as failed

        Used to handle tasks that have exited but are still running in the database

        Args:
            execution_id: Execution record ID (MongoDB _id)
            reason: Reason for failure

        Returns:
            Is it successful?
        """
        try:
            from bson import ObjectId
            db = self._get_db()

            # Find execution records
            execution = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
            if not execution:
                logger.error(f"❌ 执行记录不存在: {execution_id}")
                return False

            # Update to failed status
            await db.scheduler_executions.update_one(
                {"_id": ObjectId(execution_id)},
                {
                    "$set": {
                        "status": "failed",
                        "error_message": reason,
                        "updated_at": get_utc8_now()
                    }
                }
            )

            logger.info(f"✅ 已标记为失败: {execution.get('job_name', execution.get('job_id'))} (execution_id={execution_id}, reason={reason})")
            return True

        except Exception as e:
            logger.error(f"❌ Mark execution record as failed failed: {e}")
            return False

    async def delete_execution(self, execution_id: str) -> bool:
        """
        Delete execution record

        Args:
            execution_id: Execution record ID (MongoDB _id)

        Returns:
            Is it successful?
        """
        try:
            from bson import ObjectId
            db = self._get_db()

            # Find execution records
            execution = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
            if not execution:
                logger.error(f"❌ 执行记录不存在: {execution_id}")
                return False

            # Do not allow deletion of currently executing tasks
            if execution.get("status") == "running":
                logger.error(f"❌ Cannot delete tasks in progress: {execution_id}")
                return False

            # delete record
            result = await db.scheduler_executions.delete_one({"_id": ObjectId(execution_id)})

            if result.deleted_count > 0:
                logger.info(f"✅ 已删除执行记录: {execution.get('job_name', execution.get('job_id'))} (execution_id={execution_id})")
                return True
            else:
                logger.error(f"❌ 删除执行记录失败: {execution_id}")
                return False

        except Exception as e:
            logger.error(f"❌ 删除执行记录失败: {e}")
            return False

    async def get_latest_execution(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest execution record of the task

        Args:
            job_id: Task ID

        Returns:
            The latest execution record, if there is none, return None
        """
        try:
            db = self._get_db()
            execution = await db.scheduler_executions.find_one(
                {"job_id": job_id},
                sort=[("timestamp", -1)]
            )
            
            if execution:
                # Convert _id to string
                if "_id" in execution:
                    execution["_id"] = str(execution["_id"])
                
                # Format time
                for time_field in ["scheduled_time", "timestamp", "updated_at"]:
                    if execution.get(time_field):
                        dt = execution[time_field]
                        if hasattr(dt, 'isoformat'):
                            execution[time_field] = dt.isoformat()
            
            return execution
        except Exception as e:
            logger.error(f"❌ Failed to obtain the latest execution record: {e}")
            return None

    async def get_job_execution_stats(self, job_id: str) -> Dict[str, Any]:
        """
        Get task execution statistics

        Args:
            job_id: Task ID

        Returns:
            Statistics
        """
        try:
            db = self._get_db()

            # Count the execution times of each status
            pipeline = [
                {"$match": {"job_id": job_id}},
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "avg_execution_time": {"$avg": "$execution_time"}
                }}
            ]

            stats = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "missed": 0,
                "avg_execution_time": 0
            }

            async for doc in db.scheduler_executions.aggregate(pipeline):
                status = doc["_id"]
                count = doc["count"]
                stats["total"] += count
                stats[status] = count

                if status == "success" and doc.get("avg_execution_time"):
                    stats["avg_execution_time"] = round(doc["avg_execution_time"], 2)

            # Get the latest execution
            last_execution = await db.scheduler_executions.find_one(
                {"job_id": job_id},
                sort=[("timestamp", -1)]
            )

            if last_execution:
                stats["last_execution"] = {
                    "status": last_execution.get("status"),
                    "timestamp": last_execution.get("timestamp").isoformat() if last_execution.get("timestamp") else None,
                    "execution_time": last_execution.get("execution_time")
                }

            return stats
        except Exception as e:
            logger.error(f"❌ Failed to obtain task execution statistics: {e}")
            return {}
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get scheduler statistics
        
        Returns:
            Statistics
        """
        jobs = self.scheduler.get_jobs()
        
        total = len(jobs)
        running = sum(1 for job in jobs if job.next_run_time is not None)
        paused = total - running
        
        return {
            "total_jobs": total,
            "running_jobs": running,
            "paused_jobs": paused,
            "scheduler_running": self.scheduler.running,
            "scheduler_state": self.scheduler.state
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Scheduler health check
        
        Returns:
            health status
        """
        return {
            "status": "healthy" if self.scheduler.running else "stopped",
            "running": self.scheduler.running,
            "state": self.scheduler.state,
            "timestamp": get_utc8_now().isoformat()
        }
    
    def _job_to_dict(self, job: Job, include_details: bool = False) -> Dict[str, Any]:
        """
        Convert Job object to dictionary
        
        Args:
            job: Job object
            include_details: Whether to include detailed information
            
        Returns:
            Dictionary representation
        """
        result = {
            "id": job.id,
            "name": job.name or job.id,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "paused": job.next_run_time is None,
            "trigger": str(job.trigger),
        }
        
        if include_details:
            result.update({
                "func": f"{job.func.__module__}.{job.func.__name__}",
                "args": job.args,
                "kwargs": job.kwargs,
                "misfire_grace_time": job.misfire_grace_time,
                "max_instances": job.max_instances,
            })
        
        return result
    
    def _setup_event_listeners(self):
        """Set APScheduler event listener"""
        # Listen for task execution success events
        self.scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED
        )

        # Listen for task execution failure events
        self.scheduler.add_listener(
            self._on_job_error,
            EVENT_JOB_ERROR
        )

        # Listening task misses execution event
        self.scheduler.add_listener(
            self._on_job_missed,
            EVENT_JOB_MISSED
        )

        logger.info("✅ APScheduler Event listener is set")

        # Add scheduled tasks and detect zombie tasks (running state for a long time)
        self.scheduler.add_job(
            self._check_zombie_tasks,
            'interval',
            minutes=5,
            id='check_zombie_tasks',
            name='检测僵尸任务',
            replace_existing=True
        )
        logger.info("✅ Zombie task detection scheduled task has been added")

    async def check_suspended_tasks_on_startup(self):
        """
        Detect pending tasks when the service starts (tasks that are being executed before the service restarts)
        
        Mark the remaining running status tasks as suspended and the user can continue execution
        """
        try:
            db = self._get_db()

            # Find all tasks in the running state (these are the tasks that are being executed before the service is restarted)
            suspended_tasks = await db.scheduler_executions.find({
                "status": "running"
            }).to_list(length=100)

            for task in suspended_tasks:
                job_id = task.get("job_id")
                
                # 🔥 Attempt to read progress information from Redis if present
                progress_data = {}
                try:
                    from app.core.database import get_redis_sync_client
                    from app.core.redis_client import RedisKeys
                    redis_sync = get_redis_sync_client()
                    if redis_sync:
                        progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                        progress_str = redis_sync.get(progress_key)
                        if progress_str:
                            import json
                            progress_data = json.loads(progress_str)
                            logger.info(f"📊 从Redis读取到挂起任务的进度: {job_id}, 进度: {progress_data.get('progress', 0)}%, 已处理: {progress_data.get('processed_items', 0)}")
                except Exception as e:
                    logger.warning(f"⚠️ Reading progress from Redis failed: {e}")
                
                # Construct update data, giving priority to using progress information in Redis
                update_data = {
                    "status": "suspended",
                    "error_message": "The service restart causes the task to be interrupted and can continue to be executed.",
                    "updated_at": get_utc8_now()
                }
                
                # 🔥 If there is progress information in Redis, save it to MongoDB execution record
                if progress_data:
                    if "progress" in progress_data:
                        update_data["progress"] = progress_data["progress"]
                    if "processed_items" in progress_data:
                        update_data["processed_items"] = progress_data["processed_items"]
                    if "current_item" in progress_data:
                        update_data["current_item"] = progress_data["current_item"]
                    if "total_items" in progress_data:
                        update_data["total_items"] = progress_data["total_items"]
                    if "message" in progress_data:
                        update_data["progress_message"] = progress_data["message"]
                
                # updated to suspended state (suspended) instead of failed
                await db.scheduler_executions.update_one(
                    {"_id": task["_id"]},
                    {"$set": update_data}
                )
                
                progress_info = progress_data.get("progress", task.get("progress", 0))
                processed_info = progress_data.get("processed_items", task.get("processed_items", 0))
                logger.info(f"⏸️ 检测到挂起任务: {task.get('job_name', task.get('job_id'))} (开始时间: {task.get('timestamp')}, 进度: {progress_info}%, 已处理: {processed_info})")

            if suspended_tasks:
                logger.info(f"✅ 已标记 {len(suspended_tasks)} 个挂起任务（服务重启导致）")

        except Exception as e:
            logger.error(f"❌ 检测挂起任务失败: {e}")

    async def _check_zombie_tasks(self):
        """
        Detect zombie tasks (tasks that are running for a long time and have no progress updates)

        Note: This method only handles real timeout tasks. Suspended tasks caused by service restart are handled by check_suspended_tasks_on_startup.

        Judgment criteria:
        1. The status is running
        2. The last updated time (updated_at) has not been updated for more than 30 minutes
        3. If there is no updated_at field, the start time (timestamp) is used to determine
        """
        try:
            db = self._get_db()

            # Find running tasks that have not been updated for more than 30 minutes
            threshold_time = get_utc8_now() - timedelta(minutes=30)

            # 🔥 Modify query conditions: check updated_at instead timestamp
            zombie_tasks = await db.scheduler_executions.find({
                "status": "running",
                "$or": [
                    # Case 1: There is an updated_at field, and there is no update for more than 30 minutes.
                    {"updated_at": {"$lt": threshold_time}},
                    # Case 2: There is no updated_at field, use timestamp to judge (compatible with old data)
                    {
                        "updated_at": {"$exists": False},
                        "timestamp": {"$lt": threshold_time}
                    }
                ]
            }).to_list(length=100)

            for task in zombie_tasks:
                # Get the last updated time (for logs)
                last_update = task.get('updated_at') or task.get('timestamp')
                start_time = task.get('timestamp')

                # Update to failed status
                await db.scheduler_executions.update_one(
                    {"_id": task["_id"]},
                    {
                        "$set": {
                            "status": "failed",
                            "error_message": "Task execution times out or the process terminates abnormally (no progress update for more than 30 minutes)",
                            "updated_at": get_utc8_now()
                        }
                    }
                )
                logger.warning(
                    f"⚠️ 检测到僵尸任务: {task.get('job_name', task.get('job_id'))} "
                    f"(start time: {start_time}, last updated: {last_update})"
                )

            if zombie_tasks:
                logger.info(f"✅ 已标记 {len(zombie_tasks)} 个僵尸任务为失败状态")

        except Exception as e:
            logger.error(f"❌ 检测僵尸任务失败: {e}")

    def _on_job_executed(self, event: JobExecutionEvent):
        """任务执行成功回调"""
        # Calculate execution time (handling time zone issues)
        execution_time = None
        if event.scheduled_run_time:
            now = datetime.now(event.scheduled_run_time.tzinfo)
            execution_time = (now - event.scheduled_run_time).total_seconds()

        asyncio.create_task(self._record_job_execution(
            job_id=event.job_id,
            status="success",
            scheduled_time=event.scheduled_run_time,
            execution_time=execution_time,
            return_value=str(event.retval) if event.retval else None,
            progress=100  # Task completed, progress 100%
        ))

    def _on_job_error(self, event: JobExecutionEvent):
        """任务执行失败回调"""
        # Calculate execution time (handling time zone issues)
        execution_time = None
        if event.scheduled_run_time:
            now = datetime.now(event.scheduled_run_time.tzinfo)
            execution_time = (now - event.scheduled_run_time).total_seconds()

        asyncio.create_task(self._record_job_execution(
            job_id=event.job_id,
            status="failed",
            scheduled_time=event.scheduled_run_time,
            execution_time=execution_time,
            error_message=str(event.exception) if event.exception else None,
            traceback=event.traceback if hasattr(event, 'traceback') else None,
            progress=None  # Do not set progress on failure
        ))

    def _on_job_missed(self, event: JobExecutionEvent):
        """任务错过执行回调"""
        asyncio.create_task(self._record_job_execution(
            job_id=event.job_id,
            status="missed",
            scheduled_time=event.scheduled_run_time,
            progress=None  # No progress set when missed
        ))

    async def _record_job_execution(
        self,
        job_id: str,
        status: str,
        scheduled_time: datetime = None,
        execution_time: float = None,
        return_value: str = None,
        error_message: str = None,
        traceback: str = None,
        progress: int = None,
        is_manual: bool = False
    ):
        """
        Record task execution history

        Args:
            job_id: Task ID
            status: Status (running/success/failed/missed)
            scheduled_time: Planned execution time
            execution_time: Actual execution time (seconds)
            return_value: return value
            error_message: error message
            traceback: error stack
            progress: Execution progress (0-100)
            is_manual: Whether to trigger manually
        """
        try:
            db = self._get_db()

            # Get the task name and kwargs
            job = self.scheduler.get_job(job_id)
            job_name = job.name if job else job_id
            job_kwargs = job.kwargs.copy() if job and job.kwargs else {}

            # If it is in the completion status (success/failed), first check whether there is a corresponding running record.
            if status in ["success", "failed"]:
                existing_record = await db.scheduler_executions.find_one(
                    build_active_running_query({"job_id": job_id}),
                    sort=[("timestamp", -1)]
                )

                if existing_record:
                    # Update existing record
                    update_data = {
                        "status": status,
                        "execution_time": execution_time,
                        "updated_at": get_utc8_now()
                    }

                    if return_value:
                        update_data["return_value"] = return_value
                    if error_message:
                        update_data["error_message"] = error_message
                    if traceback:
                        update_data["traceback"] = traceback
                    if progress is not None:
                        update_data["progress"] = progress

                    await db.scheduler_executions.update_one(
                        {"_id": existing_record["_id"]},
                        {"$set": update_data}
                    )

                    # logging
                    if status == "success":
                        logger.info(f"✅ [任务执行] {job_name} 执行成功，耗时: {execution_time:.2f}秒")
                    elif status == "failed":
                        logger.error(f"❌ [任务执行] {job_name} 执行失败: {error_message}")

                    # 🔥 Update Redis cache (asynchronous)
                    await self._update_redis_execution_cache(
                        job_id=job_id,
                        status=status,
                        progress=progress,
                        execution_time=execution_time,
                        error_message=error_message,
                        scheduled_time=existing_record.get("scheduled_time")
                    )

                    return

            # If no running record is found, or is in running/missed status, insert a new record
            # scheduled_time Possibly aware datetime (from APScheduler) which needs to be converted to naive datetime
            scheduled_time_naive = None
            if scheduled_time:
                if scheduled_time.tzinfo is not None:
                    # Convert to local time zone and then remove time zone information
                    scheduled_time_naive = scheduled_time.astimezone(UTC_8).replace(tzinfo=None)
                else:
                    scheduled_time_naive = scheduled_time

            execution_record = {
                "job_id": job_id,
                "job_name": job_name,
                "status": status,
                "scheduled_time": scheduled_time_naive,
                "execution_time": execution_time,
                "timestamp": get_utc8_now(),
                "is_manual": is_manual,
                "job_kwargs": job_kwargs  # 🔥 Save the kwargs of the task for passing parameters when restoring
            }

            if return_value:
                execution_record["return_value"] = return_value
            if error_message:
                execution_record["error_message"] = error_message
            if traceback:
                execution_record["traceback"] = traceback
            if progress is not None:
                execution_record["progress"] = progress

            await db.scheduler_executions.insert_one(execution_record)

            # logging
            if status == "success":
                logger.info(f"✅ [任务执行] {job_name} 执行成功，耗时: {execution_time:.2f}秒")
            elif status == "failed":
                logger.error(f"❌ [任务执行] {job_name} 执行失败: {error_message}")
            elif status == "missed":
                logger.warning(f"⚠️ [任务执行] {job_name} 错过执行时间")
            elif status == "running":
                trigger_type = "手动触发" if is_manual else "自动触发"
                logger.info(f"🔄 [任务执行] {job_name} 开始执行 ({trigger_type})，进度: {progress}%")

            # 🔥 Update Redis cache (asynchronous)
            await self._update_redis_execution_cache(
                job_id=job_id,
                status=status,
                progress=progress,
                execution_time=execution_time,
                error_message=error_message,
                scheduled_time=scheduled_time_naive
            )

        except Exception as e:
            logger.error(f"❌ Record task execution history failure: {e}")

    async def _update_redis_execution_cache(
        self,
        job_id: str,
        status: str,
        progress: int = None,
        execution_time: float = None,
        error_message: str = None,
        scheduled_time: datetime = None
    ):
        """
        Update task execution cache in Redis

        Args:
            job_id: Task ID
            status: Status
            progress: Progress
            execution_time: Execution time
            error_message: error message
            scheduled_time: Planned execution time
        """
        try:
            import json
            from app.core.redis_client import RedisKeys
            from app.core.database import get_redis_client
            
            # Use the system's unified asynchronous Redis client
            redis_client = get_redis_client()
            
            # Build execution data
            execution_data = {
                "job_id": job_id,
                "status": status,
                "updated_at": get_utc8_now().isoformat()
            }
            
            if progress is not None:
                execution_data["progress"] = progress
            if execution_time is not None:
                execution_data["execution_time"] = execution_time
            if error_message:
                execution_data["error_message"] = error_message
            if scheduled_time:
                execution_data["scheduled_time"] = scheduled_time.isoformat() if isinstance(scheduled_time, datetime) else str(scheduled_time)
            
            # Store execution records
            execution_key = RedisKeys.SCHEDULER_JOB_EXECUTION.format(job_id=job_id)
            await redis_client.setex(
                execution_key,
                86400,  # 24 hours TTL
                json.dumps(execution_data, ensure_ascii=False, default=str)
            )
            
            # Update status (simplified version)
            status_key = RedisKeys.SCHEDULER_JOB_STATUS.format(job_id=job_id)
            status_data = {
                "job_id": job_id,
                "status": status,
                "updated_at": get_utc8_now().isoformat()
            }
            if progress is not None:
                status_data["progress"] = progress
            
            await redis_client.setex(
                status_key,
                86400,
                json.dumps(status_data, ensure_ascii=False, default=str)
            )
            
            # If the task is completed (success/failed), clear the progress cache
            if status in ["success", "failed"]:
                progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                await redis_client.delete(progress_key)
                
        except Exception as redis_error:
            # Redis Update failure does not affect the main process, only logs are recorded
            logger.debug(f"⚠️ Failed to update Redis execution cache (does not affect the main process): {redis_error}")

    async def _record_job_action(
        self,
        job_id: str,
        action: str,
        status: str,
        error_message: str = None
    ):
        """
        Record task operation history

        Args:
            job_id: Task ID
            action: Operation type (pause/resume/trigger)
            status: Status (success/failed)
            error_message: error message
        """
        try:
            db = self._get_db()
            await db.scheduler_history.insert_one({
                "job_id": job_id,
                "action": action,
                "status": status,
                "error_message": error_message,
                "timestamp": get_utc8_now()
            })
        except Exception as e:
            logger.error(f"❌ Recording task operation history failed: {e}")

    async def _get_job_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task metadata (trigger name and comments)

        Args:
            job_id: Task ID

        Returns:
            Metadata dictionary, returned if it does not exist None
        """
        try:
            db = self._get_db()
            metadata = await db.scheduler_metadata.find_one({"job_id": job_id})
            if metadata:
                metadata.pop("_id", None)
                return metadata
            return None
        except Exception as e:
            logger.error(f"❌ 获取任务 {job_id} 元数据失败: {e}")
            return None

    async def update_job_metadata(
        self,
        job_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool:
        """
        Update task metadata

        Args:
            job_id: Task ID
            display_name: Trigger name
            description: Remarks

        Returns:
            Is it successful?
        """
        try:
            # Check if the task exists
            job = self.scheduler.get_job(job_id)
            if not job:
                logger.error(f"❌ 任务 {job_id} 不存在")
                return False

            db = self._get_db()
            update_data = {
                "job_id": job_id,
                "updated_at": get_utc8_now()
            }

            if display_name is not None:
                update_data["display_name"] = display_name
            if description is not None:
                update_data["description"] = description

            # Update or insert using upsert
            await db.scheduler_metadata.update_one(
                {"job_id": job_id},
                {"$set": update_data},
                upsert=True
            )

            logger.info(f"✅ 任务 {job_id} 元数据已更新")
            return True
        except Exception as e:
            logger.error(f"❌ 更新任务 {job_id} 元数据失败: {e}")
            return False


# Global service instance
_scheduler_service: Optional[SchedulerService] = None
_scheduler_instance: Optional[AsyncIOScheduler] = None


def set_scheduler_instance(scheduler: AsyncIOScheduler):
    """
    Set up scheduler instance
    
    Args:
        scheduler: APScheduler Scheduler instance
    """
    global _scheduler_instance
    _scheduler_instance = scheduler
    logger.info("✅ 调度器实例已设置")


def get_scheduler_service() -> SchedulerService:
    """
    Get scheduler service instance

    Returns:
        Scheduler service instance
    """
    global _scheduler_service, _scheduler_instance

    if _scheduler_instance is None:
        raise RuntimeError("The scheduler instance is not set, please call first set_scheduler_instance()")

    if _scheduler_service is None:
        _scheduler_service = SchedulerService(_scheduler_instance)
        logger.info("✅ 调度器服务实例已创建")

    return _scheduler_service


async def update_job_progress(
    job_id: str,
    progress: int,
    message: str = None,
    current_item: str = None,
    total_items: int = None,
    processed_items: int = None
):
    """
    Update task execution progress (for internal calls by scheduled tasks)

    Args:
        job_id: Task ID
        progress: Progress percentage (0-100)
        message: progress message
        current_item: Current processing item
        total_items: Total number of items
        processed_items: Number of items processed
    """
    try:
        import json
        from app.core.redis_client import RedisKeys

        # Reuse the globally synchronized MongoDB singleton to avoid high-frequency creation/closure of PyMongo background threads.
        sync_db = get_mongo_db_sync()

        # 🔥 Extract the original job_id (if the job_id is tushare_financial_sync_tushare, the original is tushare_financial_sync)
        # Check if job_id ends with data source name (tushare, akshare, baostock)
        original_job_id = job_id
        for data_source in ["tushare", "akshare", "baostock"]:
            if job_id.endswith(f"_{data_source}"):
                original_job_id = job_id[:-len(f"_{data_source}")]
                break

        # 🔥 Find the latest execution record (first look for running/suspended status for recovery)
        # If it is a recovery operation, the pending execution records should be reused
        # First search for records in the running/suspended state (need to be reused during recovery)
        # 🔥 First look for records in the running state (most likely the task currently being executed)
        # 🔥 First search for the record of the current job_id. If it cannot be found, then search for the record of the original job_id.
        latest_execution = sync_db.scheduler_executions.find_one(
            {
                "job_id": job_id,
                "status": "running"  # 🔥 Search for records in running status first
            },
            sort=[("timestamp", -1)]
        )
        
        # 🔥 If the record for the current job_id is not found, try to find the record for the original job_id (using regular expression matching)
        if not latest_execution and original_job_id != job_id:
            latest_execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": {"$regex": f"^{original_job_id}(_|$)"},  # Matches the original job_id or starts with job_id
                    "status": "running"
                },
                sort=[("timestamp", -1)]
            )
        
        # If no running record is found, search for records in other states.
        if not latest_execution:
            latest_execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": job_id,
                    "status": {"$in": ["suspended", "failed", "cancelled"]}
                },
                sort=[("timestamp", -1)]
            )
        
        # 🔥 If still not found, try to find other status records of the original job_id
        if not latest_execution and original_job_id != job_id:
            latest_execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": {"$regex": f"^{original_job_id}(_|$)"},
                    "status": {"$in": ["suspended", "failed", "cancelled"]}
                },
                sort=[("timestamp", -1)]
            )
        
        # If no record in the above status is found, then search for the most recent success record (within 24 hours)
        # This handles tasks that have just been completed but avoids finding records that are too old
        if not latest_execution:
            from datetime import timedelta
            one_day_ago = get_utc8_now() - timedelta(days=1)
            latest_execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": job_id,
                    "status": "success",
                    "timestamp": {"$gte": one_day_ago}
                },
                sort=[("timestamp", -1)]
            )
        
        # 🔥 If it still cannot be found, try to find the success record of the original job_id
        if not latest_execution and original_job_id != job_id:
            from datetime import timedelta
            one_day_ago = get_utc8_now() - timedelta(days=1)
            latest_execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": {"$regex": f"^{original_job_id}(_|$)"},
                    "status": "success",
                    "timestamp": {"$gte": one_day_ago}
                },
                sort=[("timestamp", -1)]
            )

        # 🔥 Determine the start time first for later saving to Redis
        started_at = None
        execution_timestamp = None
        
        if latest_execution:
            # Check if there is a cancellation request
            execution_id = latest_execution.get("_id")
            execution_job_id = latest_execution.get("job_id", "")
            cancel_requested = latest_execution.get("cancel_requested", False)
            
            # 🔥 If the current execution record does not have a cancellation mark, check whether other related execution records have been cancelled.
            # For example: If the cancel flag is set in tushare_financial_sync, also check tushare_financial_sync_tushare
            if not cancel_requested:
                # Extract original job_id
                original_job_id = execution_job_id
                for data_source in ["tushare", "akshare", "baostock"]:
                    if execution_job_id.endswith(f"_{data_source}"):
                        original_job_id = execution_job_id[:-len(f"_{data_source}")]
                        break
                
                # 🔥 Check whether the execution record of the original job_id has a cancellation mark (only the running status is checked, not the suspended status)
                # Because the records in the suspended state may be old tasks, they should not affect new tasks.
                if original_job_id != execution_job_id:
                    original_execution = sync_db.scheduler_executions.find_one(
                        build_active_running_query({
                            "job_id": original_job_id
                        }),
                        sort=[("timestamp", -1)]
                    )
                    # 🔥 If an active running record of the original job_id is found, check whether synchronization of cancellation markers is required
                    if original_execution:
                        execution_time = get_execution_activity_time(original_execution)
                        if execution_time:
                            time_diff = (get_utc8_now() - execution_time).total_seconds()
                            if original_execution.get("cancel_requested", False):
                                # 🔥 Synchronize the cancellation mark to the current execution record
                                sync_db.scheduler_executions.update_one(
                                    {"_id": execution_id},
                                    {
                                        "$set": {
                                            "cancel_requested": True,
                                            "updated_at": get_utc8_now()
                                        }
                                    }
                                )
                                cancel_requested = True
                                logger.info(f"🔄 同步取消标记: 从 {original_job_id} 同步到 {execution_job_id} (时间差: {time_diff:.0f}秒)")
                            else:
                                logger.debug("🔍 The active execution record of the original job_id does not have a cancellation mark set and the cancellation status is not synchronized.")
            
            if cancel_requested:
                logger.warning(f"⚠️ 任务 {job_id} 收到取消请求，即将停止 (execution_job_id={execution_job_id})")
                raise TaskCancelledException(f"任务 {job_id} 已被用户取消")

            # 🔥 Check if the task has been marked as failed or canceled
            current_status = latest_execution.get("status")
            cancel_requested = latest_execution.get("cancel_requested", False)
            
            # 🔥 If the task has been marked as failed, canceled, or canceled request, the status should not be updated as running
            # However, if this is a new task execution (by checking the timestamp) it should be allowed to update the progress
            execution_time = latest_execution.get("timestamp") or latest_execution.get("scheduled_time")
            from datetime import timedelta
            time_diff = None
            if execution_time:
                time_diff = (get_utc8_now() - execution_time).total_seconds()
            
            # 🔥 If the failed/cancelled record is older than 1 hour, it may be an old record, allow new records to be created
            is_old_record = time_diff and time_diff > 3600  # 1 hours
            
            if current_status in ["failed", "cancelled"] and not is_old_record:
                logger.warning(f"⚠️ 任务 {job_id} 状态为 {current_status}，不更新状态为running，保持 {current_status} 状态")
                # Only updates progress, not status
                update_data = {
                    "progress": progress,
                    "updated_at": get_utc8_now()
                }
                # 🔥 Even if the status is failed/cancelled, the progress related fields must be updated.
                if current_item:
                    update_data["current_item"] = current_item
                if total_items is not None:
                    update_data["total_items"] = total_items
                if processed_items is not None:
                    update_data["processed_items"] = processed_items
            elif cancel_requested:
                logger.warning(f"⚠️ 任务 {job_id} 已收到取消请求，不更新状态为running")
                # Only update the progress, not the status (keep running, wait for the task to stop)
                update_data = {
                    "progress": progress,
                    "updated_at": get_utc8_now()
                }
                # 🔥 Update progress related fields
                if current_item:
                    update_data["current_item"] = current_item
                if total_items is not None:
                    update_data["total_items"] = total_items
                if processed_items is not None:
                    update_data["processed_items"] = processed_items
            else:
                # 🔥 Update existing record
                # If the progress is 100%, the status should be success; otherwise it remains running
                status = "success" if progress >= 100 else "running"
                update_data = {
                    "progress": progress,
                    "status": status,
                    "updated_at": get_utc8_now()
                }
                
                # 🔥 If the task is completed, record the completion time
                if progress >= 100:
                    update_data["finished_at"] = get_utc8_now()
                    logger.info(f"✅ 任务 {job_id} 已完成，状态更新为success")

            if message:
                update_data["progress_message"] = message
            if current_item:
                update_data["current_item"] = current_item
            if total_items is not None:
                update_data["total_items"] = total_items
            if processed_items is not None:
                update_data["processed_items"] = processed_items

            result = sync_db.scheduler_executions.update_one(
                {"_id": latest_execution["_id"]},
                {"$set": update_data}
            )
            
            # 🔥 Check if the update is successful
            if result.modified_count == 0 and result.matched_count == 0:
                logger.warning(f"⚠️ 任务 {job_id} 进度更新失败：未找到执行记录 {latest_execution['_id']}")
            elif result.modified_count == 0:
                # 🔥 Log even if data has not changed (for debugging)
                logger.debug(f"📝 任务 {job_id} 进度更新：数据未变化（progress={progress}%, processed={processed_items}/{total_items}）")
            else:
                logger.info(f"📝 任务 {job_id} 更新进度成功: {progress}%, 已处理: {processed_items}/{total_items}, execution_id={latest_execution['_id']}")
            
            # Get start time from existing record (make sure not to reset)
            started_at = latest_execution.get("timestamp") or latest_execution.get("scheduled_time")
        else:
            # 🔥 If no execution records are found, check for recent failure or cancellation records
            # 🔥 Check if there is a recent failed or canceled record
            # However, if it is triggered manually (is_manual=True) , should allow creation of new records
            
            # 🔥 Get the task name and kwargs first (before judging is_manual)
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            job_name = job_id
            job_kwargs = {}
            if _scheduler_instance:
                job = _scheduler_instance.get_job(job_id)
                if job:
                    job_name = job.name
                    job_kwargs = job.kwargs.copy() if job.kwargs else {}
            
            # 🔥 Determine whether it is manually triggered (by checking whether there is a _manual_trigger tag in job_kwargs)
            is_manual = job_kwargs.get("_manual_trigger", False) or job_kwargs.get("_force_execute", False)
            
            from datetime import timedelta
            one_hour_ago = get_utc8_now() - timedelta(hours=1)
            recent_failed_or_cancelled = sync_db.scheduler_executions.find_one(
                {
                    "job_id": job_id,
                    "status": {"$in": ["failed", "cancelled"]},
                    "timestamp": {"$gte": one_hour_ago}
                },
                sort=[("timestamp", -1)]
            )
            
            if recent_failed_or_cancelled and not is_manual:
                # 🔥 Prevent new records from being created only when not manually triggered
                # Allow new records to be created when triggered manually (user explicitly asks to start over)
                logger.warning(f"⚠️ 任务 {job_id} 在1小时内有失败/取消记录 ({recent_failed_or_cancelled.get('status')})，"
                             f"It is not triggered manually and does not create new execution records to prevent the state from reverting to running")
                return  # Don't update progress, keep failed/cancelled status
            elif recent_failed_or_cancelled and is_manual:
                # 🔥 When triggered manually, allows new records to be created (from scratch) even if there are canceled records
                logger.info(f"✅ 任务 {job_id} 在1小时内有取消记录，但这是手动触发，将创建新任务从头开始")
            
            # Create a new execution record (the task has just started)

            # 🔥 Recording start time
            execution_timestamp = get_utc8_now()
            started_at = execution_timestamp

            # 🔥 Determine whether it is manually triggered (by checking whether there is a _manual_trigger tag in job_kwargs)
            # Note: If the judgment has been made above, there is no need to repeat the judgment here, but for the sake of code clarity, the judgment is retained.
            if 'is_manual' not in locals():
                is_manual = job_kwargs.get("_manual_trigger", False) or job_kwargs.get("_force_execute", False)

            # 🔥 When creating a new execution record, first insert it into the database to obtain_id
            # 🔥 Clear the previous cancellation flag (if any) since this is a new task
            execution_record = {
                "job_id": job_id,
                "job_name": job_name,
                "status": "running",
                "progress": progress,
                "scheduled_time": execution_timestamp,
                "timestamp": execution_timestamp,
                "is_manual": is_manual,  # 🔥 Set according to _manual_trigger tag is_manual
                "cancel_requested": False,  # 🔥 New tasks are not marked as canceled by default
                "job_kwargs": job_kwargs  # 🔥 Save the kwargs of the task for passing parameters when restoring
            }

            if message:
                execution_record["progress_message"] = message
            if current_item:
                execution_record["current_item"] = current_item
            if total_items is not None:
                execution_record["total_items"] = total_items
            if processed_items is not None:
                execution_record["processed_items"] = processed_items

            result = sync_db.scheduler_executions.insert_one(execution_record)
            # 🔥 Save the newly created execution_id for subsequent saving to Redis
            new_execution_id = str(result.inserted_id)
            logger.info(f"📝 任务 {job_id} 创建新执行记录，execution_id: {new_execution_id}")

        # 🔥 Update the Redis cache at the same time (using the system's unified synchronous Redis client)
        try:
            from app.core.database import get_redis_sync_client
            from app.core.redis_client import RedisKeys
            
            # Get the unified synchronization Redis client of the system
            redis_sync = get_redis_sync_client()
            
            # 🔥 If it is a newly created execution record (manually triggered), clear the old Redis cache and make sure to start from scratch
            if 'new_execution_id' in locals() and is_manual:
                progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                try:
                    redis_sync.delete(progress_key)
                    logger.info(f"🗑️ 已清除旧的Redis进度缓存: {progress_key}（新任务从头开始）")
                except Exception as delete_error:
                    logger.warning(f"⚠️ Clearing Redis cache failed: {delete_error}")
            
            # 🔥 If the start time has not been obtained yet, try to obtain it from Redis (compatible with old data)
            # This avoids resetting the start time when the MongoDB record is not found
            if not started_at:
                try:
                    from app.core.redis_client import RedisKeys
                    progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                    existing_progress_str = redis_sync.get(progress_key)
                    if existing_progress_str:
                        existing_progress = json.loads(existing_progress_str)
                        if existing_progress.get("started_at"):
                            # started_at obtained from Redis is a string and needs to be parsed
                            started_at_str = existing_progress["started_at"]
                            try:
                                from datetime import datetime
                                # Try parsing ISO format string
                                if isinstance(started_at_str, str):
                                    started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
                                    logger.info(f"📝 任务 {job_id} 从Redis恢复开始时间: {started_at}")
                                else:
                                    started_at = started_at_str
                            except Exception as parse_error:
                                logger.warning(f"⚠️ 解析Redis中的started_at失败: {parse_error}, 使用原始值")
                                started_at = started_at_str
                except Exception as redis_error:
                    logger.debug(f"⚠️ Failed to get started_at from Redis: {redis_error}")
            
            # If still not, use the current time (a covert solution, only for new tasks)
            if not started_at:
                started_at = get_utc8_now()
                logger.info(f"📝 任务 {job_id} 创建新执行记录，开始时间: {started_at}")
            
            # Make sure started_at is in string format
            if hasattr(started_at, 'isoformat'):
                started_at_str = started_at.isoformat()
            elif isinstance(started_at, str):
                started_at_str = started_at
            else:
                started_at_str = str(started_at)
            
            # 🔥 Determine the status according to the progress: if the progress is 100%, the status should be success; otherwise, keep running
            # Note: The same logic as MongoDB is used here to ensure consistency
            redis_status = "success" if progress >= 100 else "running"
            
            progress_data = {
                "job_id": job_id,
                "progress": progress,
                "status": redis_status,  # 🔥 Use the calculated state instead of hardcoding it as running
                "started_at": started_at_str,
                "updated_at": get_utc8_now().isoformat()
            }
            # 🔥 If the execution record is found, save the execution_id to Redis (for front-end termination operation)
            if latest_execution and latest_execution.get("_id"):
                progress_data["execution_id"] = str(latest_execution["_id"])
            elif 'new_execution_id' in locals():
                # 🔥 If it is a newly created execution record, it is also saved.execution_id
                progress_data["execution_id"] = new_execution_id
            if message:
                progress_data["message"] = message
            if current_item:
                progress_data["current_item"] = current_item
            if total_items is not None:
                progress_data["total_items"] = total_items
            if processed_items is not None:
                progress_data["processed_items"] = processed_items
            
            # 🔥 If progress is 100%, add completion time
            if progress >= 100:
                progress_data["finished_at"] = get_utc8_now().isoformat()
            
            # Store in Redis, set to expire in 24 hours (will be cleaned up after the task is completed)
            progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
            try:
                redis_sync.setex(
                    progress_key,
                    86400,  # 24 hours TTL
                    json.dumps(progress_data, ensure_ascii=False)
                )
                logger.debug(f"📝 任务 {job_id} 进度已保存到Redis: {progress}%, 已处理: {processed_items}/{total_items}")
            except Exception as redis_error:
                logger.warning(f"⚠️ 任务 {job_id} 进度保存到Redis失败: {redis_error}，但不影响主流程")
            
            # Also stores state (simplified version for quick querying)
            status_key = RedisKeys.SCHEDULER_JOB_STATUS.format(job_id=job_id)
            status_data = {
                "job_id": job_id,
                "status": redis_status,  # 🔥 Use the calculated state instead of hardcoding it as running
                "progress": progress,
                "updated_at": get_utc8_now().isoformat()
            }
            redis_sync.setex(
                status_key,
                86400,
                json.dumps(status_data, ensure_ascii=False)
            )
            
        except Exception as redis_error:
            # Redis Update failure does not affect the main process, only logs are recorded
            logger.debug(f"⚠️ Failed to update Redis cache (does not affect the main process): {redis_error}")

    except TaskCancelledException:
        # 🔥 TaskCancelledException Must be re-thrown to allow the caller to catch and stop the task
        raise
    except Exception as e:
        logger.error(f"❌ 更新任务进度失败: {e}")


async def mark_job_completed(job_id: str, stats: Optional[Dict[str, Any]] = None, error_message: Optional[str] = None):
    """
    Mark task as completed (general function)
    
    Args:
        job_id: Task ID
        stats: Synchronize statistics (optional)
        error_message: Error message (optional, mark as failed if present)
    """
    try:
        logger.info(f"✅ [任务完成] 开始标记任务 {job_id} 为已完成状态")

        # Reuse the global synchronization MongoDB singleton to avoid creating/closing independent clients every time writeback is completed.
        sync_db = get_mongo_db_sync()

        # 🔥 Improve search logic:
        # 1. Prioritize the search for running records that still have active heartbeats
        # 2. If not, look for suspended/running records within the active window (handling the case of resuming suspended tasks)
        # 3. If not, look for the success record in the active window (handling the situation where update_job_progress has updated the status first)
        # 4. If not, search for any recent status record in the pocket window
        recent_window_minutes = ACTIVE_EXECUTION_WINDOW_MINUTES
        fallback_window_minutes = FALLBACK_EXECUTION_WINDOW_MINUTES
        fallback_threshold = get_utc8_now() - timedelta(minutes=fallback_window_minutes)
        
        # 🔍 Debugging: first query all relevant records
        all_recent_records = list(sync_db.scheduler_executions.find(
            build_recent_execution_query(
                {"job_id": job_id},
                window_minutes=fallback_window_minutes
            ),
            sort=[("timestamp", -1)]
        ).limit(5))
        
        if all_recent_records:
            logger.info(f"🔍 [调试] 找到 {len(all_recent_records)} 条最近{fallback_window_minutes}分钟内的记录:")
            for idx, rec in enumerate(all_recent_records):
                logger.info(f"   [{idx+1}] _id={rec.get('_id')}, status={rec.get('status')}, timestamp={rec.get('timestamp')}, updated_at={rec.get('updated_at')}, progress={rec.get('progress')}")
        else:
            logger.warning(f"🔍 [调试] 未找到任务 {job_id} 最近{fallback_window_minutes}分钟内的任何记录")
        
        # First try to find records in the running state
        execution = sync_db.scheduler_executions.find_one(
            build_active_running_query({"job_id": job_id}),
            sort=[("timestamp", -1)]
        )
        
        # If no running record is found, try to find the most recent suspended or running record (maybe just restored)
        if not execution:
            execution = sync_db.scheduler_executions.find_one(
                build_recent_execution_query(
                    {"job_id": job_id},
                    statuses=["running", "suspended"],
                    window_minutes=recent_window_minutes
                ),
                sort=[("timestamp", -1)]
            )
            if execution:
                logger.info(f"📝 Find the most recent suspended/running record (possibly a resumed task): {execution.get('_id')}, status={execution.get('status')}")
        
        # 🔥 If not found yet, try to find the most recent success record (maybe update_job_progress has updated the status to success)
        if not execution:
            execution = sync_db.scheduler_executions.find_one(
                build_recent_execution_query(
                    {"job_id": job_id},
                    statuses=["success"],
                    window_minutes=recent_window_minutes
                ),
                sort=[("timestamp", -1)]
            )
            if execution:
                logger.info(f"📝 找到最近的 success 记录（可能是 update_job_progress 已更新状态）: {execution.get('_id')}, 将更新为最终状态")
        
        # 🔥 The final solution: Find any records in the recent window (in reverse order by timestamp, take the latest)
        if not execution:
            execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": job_id,
                    "$or": [
                        {"updated_at": {"$gte": fallback_threshold}},
                        {
                            "updated_at": {"$exists": False},
                            "timestamp": {"$gte": fallback_threshold}
                        }
                    ]
                },
                sort=[("timestamp", -1)]
            )
            if execution:
                logger.info(f"📝 [兜底] 找到最近{fallback_window_minutes}分钟内的记录: {execution.get('_id')}, status={execution.get('status')}, timestamp={execution.get('timestamp')}")

        if not execution:
            logger.warning(f"⚠️ 未找到任务 {job_id} 的运行记录，无法标记为已完成")
            return

        # 🔥 Modify the logic: even if there is error_message, if the success rate >= 80%, should also be marked as success
        # 🔥 Because the task has been completed (all stocks have been processed), failed items can be retried individually
        if error_message and stats:
            # Check success rate if >= 80%, Even if there are errors they should be marked as success
            success_count = stats.get("success_count", 0)
            total_processed = stats.get("total_processed", 0)
            if total_processed > 0:
                success_rate = (success_count / total_processed) * 100
                if success_rate >= 80:
                    # success rate >= 80%, Even if there are errors they should be marked as success
                    # Not handled here, let the stats branch below handle it
                    error_message = None
                    logger.info(f"✅ 任务 {job_id} 成功率 {success_rate:.1f}% >= 80%，即使有错误也标记为 success")
        
        # Determine status: If there is an error message and the success rate < 80%, marked as failed
        if error_message:
            status = "failed"
            # 🔥 If the task fails, set the progress according to the actual processing situation
            # 🔥 But if all stocks are processed, the progress should be 100%
            if stats and stats.get("total_processed", 0) > 0:
                total_processed = stats.get("total_processed", 0)
                # All stocks have been processed and the progress should be 100%
                actual_progress = 100
            else:
                # If no data is processed, the progress is set to 0 (the task failed during the initialization phase)
                actual_progress = 0
            
            update_data = {
                "status": status,
                "progress": actual_progress,
                "finished_at": get_utc8_now(),
                "updated_at": get_utc8_now(),
                "error_message": error_message[:500]  # Limit error message length
            }
            
            # 🔥 If there is processing information in stats, the relevant fields will also be updated.
            if stats:
                update_data["processed_items"] = stats.get("total_processed", 0)
                update_data["total_items"] = stats.get("total_processed", 0)
                update_data["success_count"] = stats.get("success_count", 0)
                update_data["error_count"] = stats.get("error_count", 0)
        elif stats:
            error_count = stats.get("error_count", 0)
            success_count = stats.get("success_count", 0)
            total_processed = stats.get("total_processed", 0)
            
            # 🔥 Modify logic: If all stocks are processed (regardless of success or failure), the progress should be 100%
            # 🔥 Because the task has been completed, the failed item can pass"Retry failed items"Functions are handled individually
            if total_processed > 0:
                # All stocks have been processed and the progress should be 100%
                actual_progress = 100
            else:
                # If no data is processed, the progress is 0
                actual_progress = 0
            
            # 🔥 Determine task status based on success rate (more reasonable logic)
            # - success rate >= 80%: Marked as success (partial failure is acceptable, especially for data sources with unstable network)
            # - success rate < 80% But > 0%: Marked as partial (partial success)
            # - success rate = 0%: Marked as failed (complete failure)
            if total_processed > 0:
                success_rate = (success_count / total_processed) * 100
                if success_rate >= 80:
                    status = "success"
                elif success_rate > 0:
                    status = "partial"  # Partially successful
                else:
                    status = "failed"  # complete failure
            else:
                # No data was processed, marked as failed
                status = "failed"
            
            # Calculate success rate
            success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0

            update_data = {
                "status": status,
                "progress": actual_progress,  # 🔥 Use actual calculated progress
                "finished_at": get_utc8_now(),
                "updated_at": get_utc8_now(),
                "progress_message": f"同步完成：成功 {success_count}/{total_processed} 只股票 (成功率: {success_rate:.1f}%)",
                # 🔥 Update processed_items and total_items to ensure that the front end can display correctly
                "processed_items": total_processed,  # Processed (including successful and failed)
                "total_items": total_processed,
                "success_count": success_count,  # successfully processed
                "error_count": error_count  # failed
            }

            # Add corresponding messages based on status
            if status == "success":
                if error_count > 0:
                    # success rate >= 80%, But some failed
                    error_messages = [e.get("error", "") for e in stats.get("errors", [])[:3]]  # Only take the first 3 errors
                    update_data["error_message"] = f"✅ 同步成功 (成功率: {success_rate:.1f}%)，但有 {error_count} 个股票失败: {', '.join(error_messages)}"
                    update_data["errors"] = stats.get("errors", [])
                else:
                    # 100% success
                    update_data["error_message"] = f"✅ 同步完成，所有 {success_count} 只股票均成功"
            elif status == "partial":
                # Partially successful (0% < success rate < 80%)
                failed_count = total_processed - success_count
                error_messages = [e.get("error", "") for e in stats.get("errors", [])[:3]]
                update_data["error_message"] = f"⚠️ Partially successful (success rate: {success_rate:.1f}%): success {success_count}, failed {failed_count}. Major error: {', '.join(error_messages)}"
                update_data["errors"] = stats.get("errors", [])
            elif status == "failed":
                # complete failure (success rate = 0%)
                error_messages = [e.get("error", "") for e in stats.get("errors", [])[:5]]
                update_data["error_message"] = f"❌ Sync failed:{total_processed} All stocks failed. Error: {', '.join(error_messages)}"
                update_data["errors"] = stats.get("errors", [])
        else:
            # No statistics, default marked as success
            status = "success"
            update_data = {
                "status": status,
                "progress": 100,
                "finished_at": get_utc8_now(),
                "updated_at": get_utc8_now(),
                "progress_message": "任务完成"
            }

        result = sync_db.scheduler_executions.update_one(
            {"_id": execution["_id"]},
            {"$set": update_data}
        )

        logger.info(f"✅ [任务完成] 任务 {job_id} 状态已更新为 {status}: matched={result.matched_count}, modified={result.modified_count}")

        # 🔥 Update or delete the Redis cache to ensure that the front end can obtain the latest status
        try:
            from app.core.database import get_redis_sync_client
            from app.core.redis_client import RedisKeys
            import json
            
            redis_sync = get_redis_sync_client()
            if redis_sync:
                # 🔥 Obtain complete information from the execution record to ensure that the front end can obtain all necessary fields
                started_at = execution.get("timestamp") or execution.get("scheduled_time")
                finished_at = update_data.get("finished_at") or execution.get("finished_at")
                
                # Update the progress cache (contains all fields required by the front end)
                progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                progress_data = {
                    "job_id": job_id,
                    "progress": update_data.get("progress", 100),
                    "status": status,
                    "updated_at": get_utc8_now().isoformat(),
                    "started_at": started_at.isoformat() if started_at and hasattr(started_at, 'isoformat') else (str(started_at) if started_at else None)
                }
                if finished_at:
                    progress_data["finished_at"] = finished_at.isoformat() if hasattr(finished_at, 'isoformat') else str(finished_at)
                if update_data.get("progress_message"):
                    progress_data["message"] = update_data["progress_message"]
                if execution.get("current_item"):
                    progress_data["current_item"] = execution.get("current_item")
                
                # 🔥 The information in stats will be used first, if not, the information in execution will be used.
                if stats:
                    total_processed = stats.get("total_processed", 0)
                    success_count = stats.get("success_count", 0)
                    if total_processed > 0:
                        progress_data["total_items"] = total_processed
                        # processed_items should be processed (including success and failure), used here total_processed
                        # But actually the front end may need success_count, so we provide both
                        progress_data["processed_items"] = total_processed  # Processed (including successful and failed)
                        progress_data["success_count"] = success_count  # successfully processed
                else:
                    # If stats are not available, use information from execution
                    if execution.get("total_items"):
                        progress_data["total_items"] = execution.get("total_items")
                    if execution.get("processed_items") is not None:
                        progress_data["processed_items"] = execution.get("processed_items")
                
                redis_sync.setex(
                    progress_key,
                    86400,  # 24 hours TTL
                    json.dumps(progress_data, ensure_ascii=False, default=str)
                )
                
                # Update status cache
                status_key = RedisKeys.SCHEDULER_JOB_STATUS.format(job_id=job_id)
                status_data = {
                    "job_id": job_id,
                    "status": status,
                    "progress": update_data.get("progress", 100),
                    "updated_at": get_utc8_now().isoformat()
                }
                redis_sync.setex(
                    status_key,
                    86400,
                    json.dumps(status_data, ensure_ascii=False, default=str)
                )
                
                logger.info(f"✅ [Mission accomplished] Redis cache updated: job_id={job_id}, status={status}, progress={update_data.get('progress', 100)}")
        except Exception as redis_error:
            logger.warning(f"⚠️ Failed to update Redis cache (does not affect the main process): {redis_error}")

    except Exception as e:
        logger.error(f"❌ 标记任务完成失败: {e}", exc_info=True)


# === thread_worker.py ===
"""
Thread pool task processor
Use ThreadPoolExecutor to process queue tasks within the Backend process
"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.database import get_mongo_db, get_redis_client
def TaskAnalysisService(*a, **kw):
    from app.services.analysis_services import TaskAnalysisService as _TAS
    return _TAS(*a, **kw)
from app.models.analysis import UnifiedAnalysisTask, AnalysisTaskType, AnalysisStatus
from tradingagents.utils.stock_utils import StockUtils, SecurityType

logger = logging.getLogger(__name__)


class ThreadWorker:
    """线程池任务处理器"""
    
    def __init__(self, max_workers: int = 3):
        """
        Initialize thread pool Worker
        
        Args:
            max_workers: Maximum number of concurrent threads (default 3)
        """
        self.max_workers = max_workers
        self.executor: Optional[ThreadPoolExecutor] = None
        self.running = False
        self.worker_id = f"thread-worker-{threading.get_ident()}"
        self.queue_service: Optional[QueueService] = None
        self.task_service: Optional[TaskAnalysisService] = None
        self._loop_task: Optional[asyncio.Task] = None
        self._gap_resolution_poll_interval_seconds = 2.0
        self._gap_resolution_last_poll_at = 0.0
        
        logger.info(f"🔧 ThreadWorker initialization: max_workers={max_workers}")
    
    async def start(self):
        """启动线程池 Worker"""
        if self.running:
            logger.warning("ThreadWorker Already running")
            return
        
        logger.info("=" * 60)
        logger.info("🚀 Start thread pool Worker...")
        logger.info(f"   最大并发数: {self.max_workers}")
        logger.info(f"   Worker ID: {self.worker_id}")
        logger.info("=" * 60)
        
        # Initialize service
        logger.info("⏳ [ThreadWorker] Initialize the Redis client agent")
        redis = get_redis_client()
        logger.info("✅ [ThreadWorker] Redis Client agent initialization completed")
        logger.info("⏳ [ThreadWorker] initialization QueueService")
        self.queue_service = QueueService(redis)
        logger.info("✅ [ThreadWorker] QueueService Initialization completed")
        logger.info("⏳ [ThreadWorker] initialization TaskAnalysisService")
        self.task_service = TaskAnalysisService()
        logger.info("✅ [ThreadWorker] TaskAnalysisService Initialization completed")
        
        # Create thread pool
        logger.info("⏳ [ThreadWorker] Create a thread pool executor")
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="analysis-worker"
        )
        logger.info("✅ [ThreadWorker] The thread pool executor is created")
        
        self.running = True
        
        # Start queue listening loop
        logger.info("⏳ [ThreadWorker] Start queue listening loop")
        self._loop_task = asyncio.create_task(self._queue_loop())
        
        logger.info("✅ Thread pool Worker started successfully")
    
    async def stop(self):
        """停止线程池 Worker"""
        if not self.running:
            return
        
        logger.info("🛑 Stop thread pool Worker...")
        self.running = False
        
        # Cancel queue loop
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        
        # Close thread pool
        if self.executor:
            logger.info("   等待线程池任务完成...")
            self.executor.shutdown(wait=True, cancel_futures=False)
            logger.info("   线程池已关闭")
        
        logger.info("✅ Thread pool worker stopped")
    
    async def _queue_loop(self):
        """队列监听循环"""
        logger.info("📡 队列监听循环启动")

        while self.running:
            try:
                now_ts = time.time()
                if now_ts - self._gap_resolution_last_poll_at >= self._gap_resolution_poll_interval_seconds:
                    await self._tick_gap_resolution_jobs()
                    self._gap_resolution_last_poll_at = now_ts

                # Get tasks from queue
                task_data = await self.queue_service.dequeue_task(self.worker_id)

                if not task_data:
                    # The queue is empty, please wait for a while
                    await asyncio.sleep(1)
                    continue

                # Submit tasks to the thread pool (without waiting for completion)
                task_id = task_data.get("id")
                logger.info(f"📊 收到任务: {task_id}, 提交到线程池...")

                # 🔥 Process tasks directly in the current event loop (without using the thread pool)
                # Because the task itself is I/O intensive, asyncio already provides concurrency capabilities
                asyncio.create_task(self._process_task_async(task_data))

            except asyncio.CancelledError:
                logger.info("队列循环被取消")
                break
            except Exception as e:
                logger.error(f"队列循环错误: {e}", exc_info=True)
                await asyncio.sleep(1)

        logger.info("📡 队列监听循环结束")

    async def _tick_gap_resolution_jobs(self):
        """Poll and advance the Agent workshop gap filling asynchronous job."""
        try:
            from core.tools.implementations.agent_builder.nanobot_agent_builder_tools import (
                process_agent_workshop_gap_resolution_jobs_once,
            )
        except ImportError:
            # The community version does not have the Agent workshop module (manifest excludes app/models/agent_workshop, etc.).
            # Silently disable polling after a one-time prompt to avoid WARNINGs every tick.
            if not getattr(type(self), "_gap_job_unavailable_logged", False):
                type(self)._gap_job_unavailable_logged = True
                logger.info(
                    "[GapJob] Agent Workshop module is unavailable (community edition), gap filling polling is disabled"
                )
            return

        try:
            result = await process_agent_workshop_gap_resolution_jobs_once(
                limit=1,
                worker_id=self.worker_id,
            )
            status = str((result or {}).get("status") or "").strip().lower()
            processed = int((result or {}).get("processed") or 0)
            attempted = int((result or {}).get("attempted") or 0)
            claim_skipped = int((result or {}).get("claim_skipped") or 0)
            active_jobs = int((result or {}).get("active_jobs") or 0)

            if status != "ok":
                logger.debug("[GapJob][Tick] status=%s err=%s", status, result.get("message", ""))
                return

            if processed > 0 or attempted > 0:
                logger.info(
                    "[GapJob][Tick] worker_id=%s active_jobs=%s processed=%s attempted=%s claim_skipped=%s",
                    self.worker_id,
                    active_jobs,
                    processed,
                    attempted,
                    claim_skipped,
                )
        except Exception as exc:
            logger.warning("[GapJob][Tick] worker_id=%s err=%s", self.worker_id, exc)
    


    async def _process_task_async(self, task_data: Dict[str, Any]):
        """
        Asynchronous processing tasks

        Args:
            task_data: mission data
        """
        task_id = task_data.get("id")
        stock_code = task_data.get("symbol")
        user_id = task_data.get("user")

        logger.info(f"🔧 开始处理任务: {task_id} - {stock_code}")

        success = False

        try:
            # Parse task parameters
            # 🔥 Fix:queue_service.get_task() Parse params and store them in the parameters field
            parameters_dict = task_data.get("parameters", {})
            if not parameters_dict:
                # Compatible with older versions: if parameters does not exist, try to read from params
                parameters_dict = task_data.get("params", {})
                if isinstance(parameters_dict, str):
                    import json
                    parameters_dict = json.loads(parameters_dict)

            # 🔍 Debugging: Print parameter content
            logger.info(f"🔍 [DEBUG] Task parameters: {parameters_dict}")

            # Check engine type (default uses v2 engine)
            engine_type = parameters_dict.get("engine", "v2")

            existing_task = None
            if engine_type == "v2":
                existing_task = await self.task_service.get_task(task_id)
                if existing_task:
                    from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
                    from app.utils.timezone import now_tz

                    memory_manager = get_memory_state_manager()
                    memory_task = await memory_manager.get_task(task_id)
                    if not memory_task:
                        await memory_manager.create_task(
                            task_id=task_id,
                            user_id=user_id,
                            stock_code=stock_code,
                            parameters=parameters_dict,
                            stock_name=None,
                        )

                    existing_task.status = AnalysisStatus.PROCESSING
                    if not existing_task.started_at:
                        existing_task.started_at = now_tz()
                    existing_task.progress = max(existing_task.progress or 0, 1)
                    existing_task.current_step = "数据准备"
                    existing_task.message = "Preparing data for analysis..."
                    await self.task_service._update_task(existing_task)

                    await memory_manager.update_task_status(
                        task_id=task_id,
                        status=TaskStatus.RUNNING,
                        progress=existing_task.progress,
                        message=existing_task.message,
                        current_step="data_preparation",
                        current_step_name="数据准备",
                        current_step_description=existing_task.message
                    )

            # 📡 JIT Data synchronization: proactively pull the latest market data before analysis to ensure that stale data is not used
            try:
                from app.worker.analysis_worker import jit_sync_stock_data
                jit_result = await jit_sync_stock_data(stock_code, parameters_dict)
                if not jit_result.is_valid:
                    logger.error(f"❌ [ThreadWorker] JIT Data synchronization failed: {jit_result.message}")
                    raise ValueError(f"数据准备失败: {jit_result.message}")
                logger.info(f"✅ [ThreadWorker] JIT Data synchronization completed: {jit_result.message}")
            except ValueError:
                raise
            except Exception as jit_err:
                logger.warning(f"⚠️ [ThreadWorker] JIT Data synchronization exception (continue analysis): {jit_err}")

            logger.info(f"🔧 使用 {engine_type} 引擎执行任务: {task_id}")

            if engine_type == "v2":
                # Using v2.0 Unified Task Engine
                from bson import ObjectId

                if existing_task:
                    # The task already exists, execute it directly
                    logger.info(f"📋 The task already exists, execute it directly: {task_id} (task_type={existing_task.task_type})")
                    await self.task_service.execute_task(existing_task)
                else:
                    # The task does not exist, create and execute
                    sec_type = StockUtils.identify_security_type(stock_code)
                    requested_market = parameters_dict.get("market_type")
                    if requested_market == "ETF" or sec_type == SecurityType.FUND:
                        inferred_task_type = AnalysisTaskType.ETF_ANALYSIS
                        parameters_dict.setdefault("selected_analysts", ["etf", "market", "news"])
                        logger.info(f"📋 The task does not exist. Rebuild the task according to the ETF process.: {task_id}")
                    else:
                        inferred_task_type = AnalysisTaskType.STOCK_ANALYSIS
                        logger.info(f"📋 The task does not exist. Rebuild the task according to the stock process.: {task_id}")

                    await self.task_service.create_and_execute_task(
                        user_id=ObjectId(user_id) if user_id else ObjectId(),
                        task_type=inferred_task_type,
                        task_params={
                            "symbol": stock_code,
                            "stock_code": stock_code,
                            **parameters_dict
                        },
                        engine_type="v2",
                        task_id=task_id  # 🔥 Pass the task_id parameter directly
                    )

                logger.info(f"✅ [v2 engine] Mission accomplished: {task_id}")

            elif engine_type == "unified":
                # Use unified analytics services
                from app.services.unified_analysis_service import UnifiedAnalysisService

                unified_service = UnifiedAnalysisService()
                await unified_service.analyze_stock(
                    stock_code=stock_code,
                    user_id=user_id,
                    task_id=task_id,
                    **parameters_dict
                )
                logger.info(f"✅ [unified engine] Mission accomplished: {task_id}")

            else:
                # The legacy engine has been retired — Refusal to execute
                logger.error(
                    f"❌ [ThreadWorker] Refuse to execute legacy engine tasks: task_id={task_id}, engine={engine_type}"
                )
                raise RuntimeError(
                    "[Deactivated] thread_worker reject engine=%s task,"
                    "Please change the queue parameter engine to 'v2'. "
                    "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md" % engine_type
                )
                # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
                # Use legacy engine
                from app.services.simple_analysis_service import SimpleAnalysisService
                from app.models.analysis import SingleAnalysisRequest, AnalysisParameters

                # 🔥 Constructs an AnalysisParameters object from a dictionary of parameters
                params = AnalysisParameters(**parameters_dict) if parameters_dict else AnalysisParameters()

                # 🔥 Construct a SingleAnalysisRequest object
                request = SingleAnalysisRequest(
                    symbol=stock_code,
                    stock_code=stock_code,
                    parameters=params
                )

                simple_service = SimpleAnalysisService()
                await simple_service.execute_analysis_background(
                    task_id=task_id,
                    user_id=user_id,
                    request=request
                )
                logger.info(f"✅ [legacy engine] Mission accomplished: {task_id}")

            success = True

        except Exception as e:
            logger.error(f"❌ 任务执行失败: {task_id} - {e}", exc_info=True)
            success = False

        finally:
            # Confirm task completion (either success or failure)
            try:
                await self.queue_service.ack_task(task_id, success)
                logger.info(f"✅ 任务已确认: {task_id} (成功: {success})")
            except Exception as e:
                logger.error(f"❌ 确认任务失败: {task_id} - {e}")


# Global ThreadWorker instance
_thread_worker: Optional[ThreadWorker] = None


async def start_thread_worker(max_workers: int = 3):
    """Start global thread pool Worker"""
    global _thread_worker

    if _thread_worker is not None:
        logger.warning("ThreadWorker Already started")
        return

    _thread_worker = ThreadWorker(max_workers=max_workers)
    await _thread_worker.start()


async def stop_thread_worker():
    """Stop the global thread pool Worker"""
    global _thread_worker

    if _thread_worker is None:
        return

    await _thread_worker.stop()
    _thread_worker = None


def get_thread_worker() -> Optional[ThreadWorker]:
    """Get the global thread pool Worker instance"""
    return _thread_worker


# === operation_log_service.py ===
"""
操作日志服务
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

from app.core.database import get_mongo_db
from app.models.operation_log import (
    OperationLogCreate,
    OperationLogResponse,
    OperationLogQuery,
    OperationLogStats,
    convert_objectid_to_str,
    ActionType
)
from app.utils.timezone import now_tz

logger = logging.getLogger("webapi")


class OperationLogService:
    """操作日志服务"""
    
    def __init__(self):
        self.collection_name = "operation_logs"
    
    async def create_log(
        self,
        user_id: str,
        username: str,
        log_data: OperationLogCreate,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """创建操作日志"""
        try:
            db = get_mongo_db()

            # Build log document
            # 🔥 Using naive datetime (without time zone information), MongoDB stores it as is and does not convert to UTC
            current_time = now_tz().replace(tzinfo=None)  # Remove time zone information and retain local time value
            log_doc = {
                "user_id": user_id,
                "username": username,
                "action_type": log_data.action_type,
                "action": log_data.action,
                "details": log_data.details or {},
                "success": log_data.success,
                "error_message": log_data.error_message,
                "duration_ms": log_data.duration_ms,
                "ip_address": ip_address or log_data.ip_address,
                "user_agent": user_agent or log_data.user_agent,
                "session_id": log_data.session_id,
                "timestamp": current_time,  # naive datetime, MongoDB Store as is
                "created_at": current_time  # naive datetime, MongoDB Store as is
            }
            
            # Insert into database
            result = await db[self.collection_name].insert_one(log_doc)
            
            logger.info(f"📝 操作日志已记录: {username} - {log_data.action}")
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"创建操作日志失败: {e}")
            raise Exception(f"创建操作日志失败: {str(e)}")
    
    async def get_logs(self, query: OperationLogQuery) -> Tuple[List[OperationLogResponse], int]:
        """获取操作日志列表"""
        try:
            db = get_mongo_db()
            
            # Build query conditions
            filter_query = {}
            
            # Time range filter
            if query.start_date or query.end_date:
                time_filter = {}
                if query.start_date:
                    # Handle time zones, remove Z suffix and parse directly
                    start_str = query.start_date.replace('Z', '')
                    time_filter["$gte"] = datetime.fromisoformat(start_str)
                if query.end_date:
                    # Handle time zones, remove Z suffix and parse directly
                    end_str = query.end_date.replace('Z', '')
                    time_filter["$lte"] = datetime.fromisoformat(end_str)
                filter_query["timestamp"] = time_filter
            
            # Operation type filter
            if query.action_type:
                filter_query["action_type"] = query.action_type
            
            # Success status filter
            if query.success is not None:
                filter_query["success"] = query.success
            
            # User filtering
            if query.user_id:
                filter_query["user_id"] = query.user_id
            
            # keyword search
            if query.keyword:
                filter_query["$or"] = [
                    {"action": {"$regex": query.keyword, "$options": "i"}},
                    {"username": {"$regex": query.keyword, "$options": "i"}},
                    {"details.stock_symbol": {"$regex": query.keyword, "$options": "i"}}
                ]
            
            # Get total
            total = await db[self.collection_name].count_documents(filter_query)
            
            # Page query
            skip = (query.page - 1) * query.page_size
            cursor = db[self.collection_name].find(filter_query).sort("timestamp", -1).skip(skip).limit(query.page_size)
            
            logs = []
            async for doc in cursor:
                doc = convert_objectid_to_str(doc)
                logs.append(OperationLogResponse(**doc))

            logger.info(f"📋 获取操作日志: 总数={total}, 返回={len(logs)}")
            return logs, total
            
        except Exception as e:
            logger.error(f"获取操作日志失败: {e}")
            raise Exception(f"获取操作日志失败: {str(e)}")
    
    async def get_stats(self, days: int = 30) -> OperationLogStats:
        """获取操作日志统计"""
        try:
            db = get_mongo_db()
            
            # Time range (using China time zone)
            start_date = now_tz() - timedelta(days=days)
            time_filter = {"timestamp": {"$gte": start_date}}
            
            # basic statistics
            total_logs = await db[self.collection_name].count_documents(time_filter)
            success_logs = await db[self.collection_name].count_documents({**time_filter, "success": True})
            failed_logs = total_logs - success_logs
            success_rate = (success_logs / total_logs * 100) if total_logs > 0 else 0
            
            # Operation type distribution
            action_type_pipeline = [
                {"$match": time_filter},
                {"$group": {"_id": "$action_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            action_type_cursor = db[self.collection_name].aggregate(action_type_pipeline)
            action_type_distribution = {}
            async for doc in action_type_cursor:
                action_type_distribution[doc["_id"]] = doc["count"]
            
            # Hourly distribution statistics
            hourly_pipeline = [
                {"$match": time_filter},
                {
                    "$group": {
                        "_id": {"$hour": "$timestamp"},
                        "count": {"$sum": 1}
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            hourly_cursor = db[self.collection_name].aggregate(hourly_pipeline)
            hourly_distribution = []
            hourly_data = {i: 0 for i in range(24)}  # Initialization 24 hours
            
            async for doc in hourly_cursor:
                hourly_data[doc["_id"]] = doc["count"]
            
            for hour, count in hourly_data.items():
                hourly_distribution.append({
                    "hour": f"{hour:02d}:00",
                    "count": count
                })
            
            stats = OperationLogStats(
                total_logs=total_logs,
                success_logs=success_logs,
                failed_logs=failed_logs,
                success_rate=round(success_rate, 2),
                action_type_distribution=action_type_distribution,
                hourly_distribution=hourly_distribution
            )
            
            logger.info(f"📊 操作日志统计: 总数={total_logs}, 成功率={success_rate:.1f}%")
            return stats
            
        except Exception as e:
            logger.error(f"获取操作日志统计失败: {e}")
            raise Exception(f"获取操作日志统计失败: {str(e)}")
    
    async def clear_logs(self, days: Optional[int] = None, action_type: Optional[str] = None) -> Dict[str, Any]:
        """清空操作日志"""
        try:
            db = get_mongo_db()
            
            # Build deletion conditions
            delete_filter = {}
            
            if days is not None:
                # Only delete logs from N days ago
                cutoff_date = datetime.now() - timedelta(days=days)
                delete_filter["timestamp"] = {"$lt": cutoff_date}
            
            if action_type:
                # Only delete logs of specified types
                delete_filter["action_type"] = action_type
            
            # perform deletion
            result = await db[self.collection_name].delete_many(delete_filter)
            
            logger.info(f"🗑️ 清空操作日志: 删除了 {result.deleted_count} 条记录")
            
            return {
                "deleted_count": result.deleted_count,
                "filter": delete_filter
            }
            
        except Exception as e:
            logger.error(f"清空操作日志失败: {e}")
            raise Exception(f"清空操作日志失败: {str(e)}")
    
    async def get_log_by_id(self, log_id: str) -> Optional[OperationLogResponse]:
        """根据ID获取操作日志"""
        try:
            db = get_mongo_db()

            doc = await db[self.collection_name].find_one({"_id": ObjectId(log_id)})
            if not doc:
                return None

            doc = convert_objectid_to_str(doc)
            return OperationLogResponse(**doc)

        except Exception as e:
            logger.error(f"获取操作日志详情失败: {e}")
            return None


# Global service instance
_operation_log_service: Optional[OperationLogService] = None


def get_operation_log_service() -> OperationLogService:
    """获取操作日志服务实例"""
    global _operation_log_service
    if _operation_log_service is None:
        _operation_log_service = OperationLogService()
    return _operation_log_service


# Convenience function
async def log_operation(
    user_id: str,
    username: str,
    action_type: str,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    session_id: Optional[str] = None
) -> str:
    """记录操作日志的便捷函数"""
    service = get_operation_log_service()
    log_data = OperationLogCreate(
        action_type=action_type,
        action=action,
        details=details,
        success=success,
        error_message=error_message,
        duration_ms=duration_ms,
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=session_id
    )
    return await service.create_log(user_id, username, log_data, ip_address, user_agent)

# === log_export_service.py ===
"""
Log export service
Provides log file query, filtering and export functions
"""

import logging
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import re
import json

logger = logging.getLogger("webapi")


class LogExportService:
    """日志导出服务"""

    def __init__(self, log_dir: str = "./logs"):
        """
        Initialize log export service

        Args:
            log_dir: Log file directory
        """
        self.log_dir = Path(log_dir)
        logger.info("🔍 [LogExportService] Initialize log export service")
        logger.info(f"🔍 [LogExportService] Configured log directory: {log_dir}")
        logger.info(f"🔍 [LogExportService] Parsed log directory: {self.log_dir}")
        logger.info(f"🔍 [LogExportService] absolute path: {self.log_dir.absolute()}")
        logger.info(f"🔍 [LogExportService] Does the directory exist?: {self.log_dir.exists()}")

        if not self.log_dir.exists():
            logger.warning(f"⚠️ [LogExportService] Log directory does not exist: {self.log_dir}")
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"✅ [LogExportService] Log directory created: {self.log_dir}")
            except Exception as e:
                logger.error(f"❌ [LogExportService] Failed to create log directory: {e}")
        else:
            logger.info("✅ [LogExportService] Log directory exists")

    def list_log_files(self) -> List[Dict[str, Any]]:
        """
        List all log files

        Returns:
            Log file list, including file name, size, modification time and other information
        """
        log_files = []

        try:
            logger.info("🔍 [list_log_files] Start listing log files")
            logger.info(f"🔍 [list_log_files] Search catalog: {self.log_dir}")
            logger.info(f"🔍 [list_log_files] absolute path: {self.log_dir.absolute()}")
            logger.info(f"🔍 [list_log_files] Does the directory exist?: {self.log_dir.exists()}")
            logger.info(f"🔍 [list_log_files] Is it a directory?: {self.log_dir.is_dir()}")

            if not self.log_dir.exists():
                logger.error(f"❌ [list_log_files] Log directory does not exist: {self.log_dir}")
                return []

            if not self.log_dir.is_dir():
                logger.error(f"❌ [list_log_files] path is not a directory: {self.log_dir}")
                return []

            # List all files in a directory (for debugging)
            try:
                all_items = list(self.log_dir.iterdir())
                logger.info(f"🔍 [list_log_files] 目录中共有 {len(all_items)} 个项目")
                for item in all_items[:10]:  # Only show the first 10
                    logger.info(f"🔍 [list_log_files]   - {item.name} (is_file: {item.is_file()})")
            except Exception as e:
                logger.error(f"❌ [list_log_files] Failed to list directory contents: {e}")

            # Search log files
            logger.info("🔍 [list_log_files] Search mode: *.log*")
            for file_path in self.log_dir.glob("*.log*"):
                logger.info(f"🔍 [list_log_files] find file: {file_path.name}")
                if file_path.is_file():
                    stat = file_path.stat()
                    log_file_info = {
                        "name": file_path.name,
                        "path": str(file_path),
                        "size": stat.st_size,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type": self._get_log_type(file_path.name)
                    }
                    log_files.append(log_file_info)
                    logger.info(f"✅ [list_log_files] Add log file: {file_path.name} ({log_file_info['size_mb']} MB)")
                else:
                    logger.warning(f"⚠️ [list_log_files] Skip non-file items: {file_path.name}")

            # Sort by modification time in descending order
            log_files.sort(key=lambda x: x["modified_at"], reverse=True)

            logger.info(f"📋 [list_log_files] 最终找到 {len(log_files)} 个日志文件")
            return log_files

        except Exception as e:
            logger.error(f"❌ [list_log_files] Failed to list log files: {e}", exc_info=True)
            return []

    def _get_log_type(self, filename: str) -> str:
        """
        Determine log type based on file name
        
        Args:
            filename: file name
            
        Returns:
            Log type
        """
        if "error" in filename.lower():
            return "error"
        elif "webapi" in filename.lower():
            return "webapi"
        elif "worker" in filename.lower():
            return "worker"
        elif "access" in filename.lower():
            return "access"
        else:
            return "other"

    def read_log_file(
        self,
        filename: str,
        lines: int = 1000,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Read log file content (supports filtering)
        
        Args:
            filename: Log file name
            lines: Number of lines read (starting from the end)
            level: Log level filtering (ERROR, WARNING, INFO, DEBUG) 
            keyword: keyword filter
            start_time: Start time (ISO format)
            end_time: End time (ISO format)
            
        Returns:
            Log content and statistics
        """
        file_path = self.log_dir / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {filename}")
        
        try:
            # Read file contents
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            
            # Read the specified number of lines starting from the end
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            # Apply filter
            filtered_lines = []
            stats = {
                "total_lines": len(all_lines),
                "filtered_lines": 0,
                "error_count": 0,
                "warning_count": 0,
                "info_count": 0,
                "debug_count": 0
            }
            
            for line in recent_lines:
                # Statistics log level
                if "ERROR" in line:
                    stats["error_count"] += 1
                elif "WARNING" in line:
                    stats["warning_count"] += 1
                elif "INFO" in line:
                    stats["info_count"] += 1
                elif "DEBUG" in line:
                    stats["debug_count"] += 1
                
                # Apply filters
                if level and level.upper() not in line:
                    continue
                
                if keyword and keyword.lower() not in line.lower():
                    continue
                
                # Time filtering (simple implementation, assuming the log format is YYYY-MM-DD HH:MM:SS) 
                if start_time or end_time:
                    time_match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', line)
                    if time_match:
                        log_time = time_match.group()
                        if start_time and log_time < start_time:
                            continue
                        if end_time and log_time > end_time:
                            continue
                
                filtered_lines.append(line.rstrip())
            
            stats["filtered_lines"] = len(filtered_lines)
            
            return {
                "filename": filename,
                "lines": filtered_lines,
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"❌ 读取日志文件失败: {e}")
            raise

    def export_logs(
        self,
        filenames: Optional[List[str]] = None,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        format: str = "zip"
    ) -> str:
        """
        Export log file
        
        Args:
            filenames: List of log file names to be exported (None means exporting all)
            level: Log level filtering
            start_time: start time
            end_time: end time
            format: Export format (zip, txt) 
            
        Returns:
            Path to exported file
        """
        try:
            # Determine which files to export
            if filenames:
                files_to_export = [self.log_dir / f for f in filenames if (self.log_dir / f).exists()]
            else:
                files_to_export = list(self.log_dir.glob("*.log*"))
            
            if not files_to_export:
                raise ValueError("没有找到要导出的日志文件")
            
            # Create export directory
            export_dir = Path("./exports/logs")
            export_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate export file name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if format == "zip":
                export_path = export_dir / f"logs_export_{timestamp}.zip"
                
                # Create ZIP file
                with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in files_to_export:
                        # If there are filter conditions, filter first and then add
                        if level or start_time or end_time:
                            filtered_data = self.read_log_file(
                                file_path.name,
                                lines=999999,  # read all lines
                                level=level,
                                start_time=start_time,
                                end_time=end_time
                            )
                            # Write filtered content to temporary file
                            temp_file = export_dir / f"temp_{file_path.name}"
                            with open(temp_file, 'w', encoding='utf-8') as f:
                                f.write('\n'.join(filtered_data['lines']))
                            zipf.write(temp_file, file_path.name)
                            temp_file.unlink()  # Delete temporary files
                        else:
                            zipf.write(file_path, file_path.name)
                
                logger.info(f"✅ 日志导出成功: {export_path}")
                return str(export_path)
            
            elif format == "txt":
                export_path = export_dir / f"logs_export_{timestamp}.txt"
                
                # Merge all logs into one text file
                with open(export_path, 'w', encoding='utf-8') as outf:
                    for file_path in files_to_export:
                        outf.write(f"\n{'='*80}\n")
                        outf.write(f"文件: {file_path.name}\n")
                        outf.write(f"{'='*80}\n\n")
                        
                        if level or start_time or end_time:
                            filtered_data = self.read_log_file(
                                file_path.name,
                                lines=999999,
                                level=level,
                                start_time=start_time,
                                end_time=end_time
                            )
                            outf.write('\n'.join(filtered_data['lines']))
                        else:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as inf:
                                outf.write(inf.read())
                        
                        outf.write('\n\n')
                
                logger.info(f"✅ 日志导出成功: {export_path}")
                return str(export_path)
            
            else:
                raise ValueError(f"不支持的导出格式: {format}")
                
        except Exception as e:
            logger.error(f"❌ 导出日志失败: {e}")
            raise

    def get_log_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get log statistics
        
        Args:
            days: Statistics of logs in recent days
            
        Returns:
            Log statistics
        """
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            stats = {
                "total_files": 0,
                "total_size_mb": 0,
                "error_files": 0,
                "recent_errors": [],
                "log_types": {}
            }
            
            for file_path in self.log_dir.glob("*.log*"):
                if not file_path.is_file():
                    continue
                
                stat = file_path.stat()
                modified_time = datetime.fromtimestamp(stat.st_mtime)
                
                if modified_time < cutoff_time:
                    continue
                
                stats["total_files"] += 1
                stats["total_size_mb"] += stat.st_size / (1024 * 1024)
                
                log_type = self._get_log_type(file_path.name)
                stats["log_types"][log_type] = stats["log_types"].get(log_type, 0) + 1
                
                # Statistics error log
                if log_type == "error":
                    stats["error_files"] += 1
                    # Read recent errors
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                            error_lines = [line for line in lines[-100:] if "ERROR" in line]
                            stats["recent_errors"].extend(error_lines[-10:])
                    except Exception:
                        pass
            
            stats["total_size_mb"] = round(stats["total_size_mb"], 2)
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ 获取日志统计失败: {e}")
            return {}


# Global service instance
_log_export_service: Optional[LogExportService] = None


def get_log_export_service() -> LogExportService:
    """获取日志导出服务实例"""
    global _log_export_service

    if _log_export_service is None:
        # Get the log directory from the log configuration
        log_dir = _get_log_directory()
        _log_export_service = LogExportService(log_dir=log_dir)

    return _log_export_service


def _get_log_directory() -> str:
    """
    Get log directory path
    Priority:
    1. Read from the log configuration file (supports Docker environment)
    2. Read from settings configuration
    3. Use default value ./logs
    """
    import os
    from pathlib import Path

    try:
        logger.info("🔍 [_get_log_directory] Start getting the log directory")

        # Check if it is a Docker environment
        docker_env = os.environ.get("DOCKER", "")
        dockerenv_exists = Path("/.dockerenv").exists()
        is_docker = docker_env.lower() in {"1", "true", "yes"} or dockerenv_exists

        logger.info(f"🔍 [_get_log_directory] DOCKER environment variables: {docker_env}")
        logger.info(f"🔍 [_get_log_directory] /.dockerenv exist: {dockerenv_exists}")
        logger.info(f"🔍 [_get_log_directory] Determined to be a Docker environment: {is_docker}")

        # Try reading from log configuration file
        try:
            import tomllib as toml_loader
            logger.info("🔍 [_get_log_directory] Load using tomllib TOML")
        except ImportError:
            try:
                import tomli as toml_loader
                logger.info("🔍 [_get_log_directory] Load using tomli TOML")
            except ImportError:
                toml_loader = None
                logger.warning("⚠️ [_get_log_directory] Unable to import TOML loader")

        if toml_loader:
            # Choose a configuration file based on your environment
            profile = os.environ.get("LOGGING_PROFILE", "")
            logger.info(f"🔍 [_get_log_directory] LOGGING_PROFILE: {profile}")

            cfg_path = Path("config/logging_docker.toml") if profile.lower() == "docker" or is_docker else Path("config/logging.toml")
            logger.info(f"🔍 [_get_log_directory] Select profile: {cfg_path}")
            logger.info(f"🔍 [_get_log_directory] Configuration file exists: {cfg_path.exists()}")

            if cfg_path.exists():
                try:
                    with cfg_path.open("rb") as f:
                        toml_data = toml_loader.load(f)

                    logger.info("🔍 [_get_log_directory] Configuration file loaded successfully")

                    # Read log directory from configuration file
                    handlers_cfg = toml_data.get("logging", {}).get("handlers", {})
                    file_handler_cfg = handlers_cfg.get("file", {})
                    log_dir = file_handler_cfg.get("directory")

                    logger.info(f"🔍 [_get_log_directory] Log directory in configuration file: {log_dir}")

                    if log_dir:
                        logger.info(f"✅ [_get_log_directory] Read the log directory from the log configuration file: {log_dir}")
                        return log_dir
                except Exception as e:
                    logger.warning(f"⚠️ [_get_log_directory] Failed to read log configuration file: {e}", exc_info=True)

        # Fall back to settings configuration
        try:
            from app.core.config import settings
            log_dir = settings.log_dir
            logger.info(f"🔍 [_get_log_directory] settings.log_dir: {log_dir}")
            if log_dir:
                logger.info(f"✅ [_get_log_directory] Read the log directory from settings: {log_dir}")
                return log_dir
        except Exception as e:
            logger.warning(f"⚠️ [_get_log_directory] Failed to read log directory from settings: {e}", exc_info=True)

        # Docker The environment uses by default /app/logs
        if is_docker:
            logger.info("✅ [_get_log_directory] Docker environment, use the default log directory: /app/logs")
            return "/app/logs"

        # Used by default in non-Docker environments ./logs
        logger.info("✅ [_get_log_directory] Use default log directory: ./logs")
        return "./logs"

    except Exception as e:
        logger.error(f"❌ [_get_log_directory] Failed to obtain log directory: {e}, Use default value ./logs", exc_info=True)
        return "./logs"


# === mcp_audit_service.py ===
"""
MCP Audit log service

All MCP tool calls (data source classes and function classes) are logged to the mcp_audit_logs collection.
Use synchronization interface, suitable for calling in executor closure (synchronization context).
"""

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

COLLECTION = "mcp_audit_logs"


def _write_audit_log(doc: Dict) -> None:
    """Synchronously write audit logs to MongoDB"""
    try:
        from app.core.database import get_mongo_db_sync
        db = get_mongo_db_sync()
        if db is not None:
            db[COLLECTION].insert_one(doc)
    except Exception as e:
        logger.warning(f"⚠️ MCP Audit log writing failed: {e}")


def log_mcp_call_sync(
    server_name: str,
    tool_name: str,
    category: str,
    request_params: Dict,
    response_summary: str,
    persisted_to: Optional[str] = None,
    task_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    """
    Asynchronous (fire-and-forget) writing to the MCP call audit log.

    Write in a background thread without blocking the MCP tool call link.

    Args:
        server_name:      MCP Server name
        tool_name:        Tool name
        category:         Data source type datasource | function
        request_params:   Call parameters
        response_summary: Response summary (e.g. "OK, 10 records") 
        persisted_to:     The name of the target collection written by the data source class (can be None)
        task_id:          Correlation analysis task ID (optional)
        user_id:          Trigger user ID (optional)
    """
    from app.utils.timezone import now_tz

    doc = {
        "task_id": task_id,
        "user_id": user_id,
        "server_name": server_name,
        "tool_name": tool_name,
        "category": category,
        "request_params": request_params,
        "response_summary": response_summary,
        "persisted_to": persisted_to,
        "created_at": now_tz(),
    }

    # fire-and-forget: Background thread writes without blocking executor
    t = threading.Thread(target=_write_audit_log, args=(doc,), daemon=True)
    t.start()


# === quality_metrics_service.py ===
"""Report quality indicator collection and query service (v3.6.0 item 5).

Depends on the quality_flags data output by phase 1 (quality_gate), automatic statistics:
- Report length by Agent type
- Data references
- LLM Call time and cost
- Covered copywriting hit rate
- low_quality mark ratio

Writes to the MongoDB analysis_quality_metrics collection for querying by the dashboard API.

How to use:
1. Called after analysis is complete record_analysis_metrics() Write indicator
2. Dashboard call query_metrics() Query by date/stock/Agent type
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLLECTION_NAME = "analysis_quality_metrics"


class QualityMetricsService:
    """报告质量指标服务"""

    def __init__(self, db: Any):
        self._db = db
        self._collection = db[COLLECTION_NAME]

    async def record_analysis_metrics(
        self,
        *,
        user_id: str,
        ticker: str = "",
        agent_id: str = "",
        agent_type: str = "",
        report_content: str = "",
        report_length: int = 0,
        is_low_quality: bool = False,
        quality_flags: List[Dict[str, Any]] = None,
        hit_fallback: bool = False,
        fallback_pattern: str = "",
        llm_elapsed_seconds: float = 0.0,
        llm_tokens_used: int = 0,
        llm_cost_estimate: float = 0.0,
        retry_count: int = 0,
        analysis_date: str = "",
        workflow_id: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record the quality indicators of an analysis.

        Args:
            user_id: User ID
            ticker: Stock code
            agent_id: Agent ID
            agent_type: Agent Type (analyst/researcher/manager, etc.)
            report_content: Report content (for post-audit, optional)
            report_length: Report character count
            is_low_quality: Whether to be marked as low quality
            quality_flags: Quality gate mark list
            hit_fallback: Whether it hits the bottom line
            fallback_pattern: A hit-and-miss copywriting
            llm_elapsed_seconds: LLM Calling time (seconds)
            llm_tokens_used: LLM token Usage
            llm_cost_estimate: LLM Cost estimate (yuan)
            retry_count: Number of retries
            analysis_date: Analysis date
            workflow_id: Workflow ID
            extra: additional indicators

        Returns:
            records written ID
        """
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "user_id": user_id,
            "ticker": str(ticker).upper() if ticker else "",
            "agent_id": agent_id,
            "agent_type": agent_type,
            "report_length": report_length or len(report_content or ""),
            "is_low_quality": is_low_quality,
            "quality_flags": quality_flags or [],
            "hit_fallback": hit_fallback,
            "fallback_pattern": fallback_pattern,
            "llm_elapsed_seconds": llm_elapsed_seconds,
            "llm_tokens_used": llm_tokens_used,
            "llm_cost_estimate": llm_cost_estimate,
            "retry_count": retry_count,
            "analysis_date": analysis_date or now[:10],
            "workflow_id": workflow_id,
            "recorded_at": now,
        }
        if extra:
            doc["extra"] = extra

        try:
            result = await self._collection.insert_one(doc)
            logger.info(
                "[QualityMetrics] Metrics logged: user=%s ticker=%s agent=%s low_quality=%s",
                user_id, ticker, agent_id, is_low_quality,
            )
            return str(result.inserted_id)
        except Exception as e:
            logger.warning("[QualityMetrics] Write failed: %s", e)
            return ""

    def record_analysis_metrics_sync(self, **kwargs) -> str:
        """record_analysis_metrics A synchronization wrapper (called by LangGraph nodes).

        Run the async version in a new thread to avoid blocking the event loop.
        Returns an empty string on failure and does not block the main process.
        """
        import asyncio
        import threading

        try:
            try:
                asyncio.get_running_loop()
                running_loop = True
            except RuntimeError:
                running_loop = False

            if not running_loop:
                return asyncio.run(self.record_analysis_metrics(**kwargs))

            # There is a running event loop, running in a new thread
            result_holder: Dict[str, Any] = {"id": ""}

            def _run_in_thread() -> None:
                try:
                    result_holder["id"] = asyncio.run(self.record_analysis_metrics(**kwargs))
                except Exception as exc:
                    logger.warning("[QualityMetrics] sync Wrapper thread exception: %s", exc)

            t = threading.Thread(target=_run_in_thread, daemon=True)
            t.start()
            t.join(timeout=10)
            return result_holder.get("id", "")
        except Exception as exc:
            logger.warning("[QualityMetrics] record_analysis_metrics_sync Abnormal: %s", exc)
            return ""

    async def query_metrics(
        self,
        *,
        user_id: Optional[str] = None,
        ticker: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        only_low_quality: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query quality indicators (for dashboard use).

        Supports filtering by user/stock/Agent/date range.
        """
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        if ticker:
            query["ticker"] = str(ticker).upper()
        if agent_id:
            query["agent_id"] = agent_id
        if agent_type:
            query["agent_type"] = agent_type
        if only_low_quality:
            query["is_low_quality"] = True

        # Date range (compare by analysis_date string)
        date_range: Dict[str, Any] = {}
        if start_date:
            date_range["$gte"] = start_date
        if end_date:
            date_range["$lte"] = end_date
        if date_range:
            query["analysis_date"] = date_range

        cursor = self._collection.find(query).sort("recorded_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        # Filter on _id (not serializable)
        return [{k: v for k, v in doc.items() if k != "_id"} for doc in docs]

    async def get_quality_summary(
        self,
        *,
        user_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get quality summary statistics (for the numbers at the top of the dashboard).

        Returns:
            {
                "total_reports": Total number of reports,
                "low_quality_count": Number of low quality reports,
                "low_quality_rate": low mass ratio,
                "fallback_hit_count": The number of hits of cover copywriting,
                "fallback_hit_rate": pocket hit rate,
                "avg_report_length": average report length,
                "avg_llm_elapsed_seconds": Average LLM time,
                "total_llm_cost": Total LLM Cost,
                "by_agent_type": {agent_type: {count, low_quality_count, ...}},
            }
        """
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        date_range: Dict[str, Any] = {}
        if start_date:
            date_range["$gte"] = start_date
        if end_date:
            date_range["$lte"] = end_date
        if date_range:
            query["analysis_date"] = date_range

        cursor = self._collection.find(query)
        docs = await cursor.to_list(length=10000)

        total = len(docs)
        if total == 0:
            return {
                "total_reports": 0,
                "low_quality_count": 0,
                "low_quality_rate": 0.0,
                "fallback_hit_count": 0,
                "fallback_hit_rate": 0.0,
                "avg_report_length": 0,
                "avg_llm_elapsed_seconds": 0.0,
                "total_llm_cost": 0.0,
                "by_agent_type": {},
            }

        low_quality_count = sum(1 for d in docs if d.get("is_low_quality"))
        fallback_hit_count = sum(1 for d in docs if d.get("hit_fallback"))
        total_length = sum(d.get("report_length", 0) for d in docs)
        total_elapsed = sum(d.get("llm_elapsed_seconds", 0) for d in docs)
        total_cost = sum(d.get("llm_cost_estimate", 0) for d in docs)

        # Aggregate by agent_type
        by_type: Dict[str, Dict[str, Any]] = {}
        for d in docs:
            at = d.get("agent_type", "unknown")
            if at not in by_type:
                by_type[at] = {
                    "count": 0,
                    "low_quality_count": 0,
                    "fallback_hit_count": 0,
                    "total_length": 0,
                }
            by_type[at]["count"] += 1
            if d.get("is_low_quality"):
                by_type[at]["low_quality_count"] += 1
            if d.get("hit_fallback"):
                by_type[at]["fallback_hit_count"] += 1
            by_type[at]["total_length"] += d.get("report_length", 0)

        # Calculate the average of each type
        for at, stats in by_type.items():
            count = stats["count"]
            stats["avg_length"] = stats["total_length"] / count if count > 0 else 0
            stats["low_quality_rate"] = stats["low_quality_count"] / count if count > 0 else 0

        return {
            "total_reports": total,
            "low_quality_count": low_quality_count,
            "low_quality_rate": low_quality_count / total,
            "fallback_hit_count": fallback_hit_count,
            "fallback_hit_rate": fallback_hit_count / total,
            "avg_report_length": total_length / total,
            "avg_llm_elapsed_seconds": total_elapsed / total,
            "total_llm_cost": total_cost,
            "by_agent_type": by_type,
        }


# Module level factory method
def get_quality_metrics_service(db: Any) -> QualityMetricsService:
    """Get QualityMetricsService instance"""
    return QualityMetricsService(db)

# === usage_statistics_service.py ===
"""
Usage statistics service
Manage model usage records and cost statistics
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

from app.core.database import get_mongo_db
from app.models.config import UsageRecord, UsageStatistics

logger = logging.getLogger("app.services.usage_statistics_service")


class UsageStatisticsService:
    """使用统计服务"""
    
    def __init__(self):
        # Using the collection name of tradingagents
        self.collection_name = "token_usage"
    
    async def add_usage_record(self, record: UsageRecord) -> bool:
        """添加使用记录"""
        try:
            db = get_mongo_db()
            collection = db[self.collection_name]

            record_dict = record.model_dump(exclude={"id"})
            result = await collection.insert_one(record_dict)

            logger.info(f"✅ 添加使用记录成功: {record.provider}/{record.model_name}")
            return True
        except Exception as e:
            logger.error(f"❌ 添加使用记录失败: {e}")
            return False
    
    async def get_usage_records(
        self,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[UsageRecord]:
        """获取使用记录"""
        try:
            db = get_mongo_db()
            collection = db[self.collection_name]
            
            # Build query conditions
            query = {}
            if provider:
                query["provider"] = provider
            if model_name:
                query["model_name"] = model_name
            if start_date or end_date:
                query["timestamp"] = {}
                if start_date:
                    query["timestamp"]["$gte"] = start_date.isoformat()
                if end_date:
                    query["timestamp"]["$lte"] = end_date.isoformat()
            
            # Query records
            cursor = collection.find(query).sort("timestamp", -1).limit(limit)
            records = []
            
            async for doc in cursor:
                doc["id"] = str(doc.pop("_id"))
                records.append(UsageRecord(**doc))
            
            logger.info(f"✅ 获取使用记录成功: {len(records)} 条")
            return records
        except Exception as e:
            logger.error(f"❌ 获取使用记录失败: {e}")
            return []
    
    async def get_usage_statistics(
        self,
        days: int = 7,
        provider: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> UsageStatistics:
        """获取使用统计"""
        try:
            db = get_mongo_db()
            collection = db[self.collection_name]
            
            # Calculation time range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Build query conditions
            query = {
                "timestamp": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat()
                }
            }
            if provider:
                query["provider"] = provider
            if model_name:
                query["model_name"] = model_name
            
            # Get all records
            cursor = collection.find(query)
            records = []
            async for doc in cursor:
                records.append(doc)
            
            # Statistics
            stats = UsageStatistics()
            stats.total_requests = len(records)

            # Cost by currency
            cost_by_currency = defaultdict(float)

            by_provider = defaultdict(lambda: {
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "cost_by_currency": defaultdict(float)
            })
            by_model = defaultdict(lambda: {
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "cost_by_currency": defaultdict(float)
            })
            by_date = defaultdict(lambda: {
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "cost_by_currency": defaultdict(float)
            })

            for record in records:
                cost = record.get("cost", 0.0)
                currency = record.get("currency", "CNY")

                # total
                stats.total_input_tokens += record.get("input_tokens", 0)
                stats.total_output_tokens += record.get("output_tokens", 0)
                stats.total_cost += cost  # Retain backward compatibility
                cost_by_currency[currency] += cost

                # Statistics by supplier
                provider_key = record.get("provider", "unknown")
                by_provider[provider_key]["requests"] += 1
                by_provider[provider_key]["input_tokens"] += record.get("input_tokens", 0)
                by_provider[provider_key]["output_tokens"] += record.get("output_tokens", 0)
                by_provider[provider_key]["cost"] += cost
                by_provider[provider_key]["cost_by_currency"][currency] += cost

                # Statistics by model
                model_key = f"{record.get('provider', 'unknown')}/{record.get('model_name', 'unknown')}"
                by_model[model_key]["requests"] += 1
                by_model[model_key]["input_tokens"] += record.get("input_tokens", 0)
                by_model[model_key]["output_tokens"] += record.get("output_tokens", 0)
                by_model[model_key]["cost"] += cost
                by_model[model_key]["cost_by_currency"][currency] += cost

                # Statistics by date
                timestamp = record.get("timestamp", "")
                if timestamp:
                    date_key = timestamp[:10]  # YYYY-MM-DD
                    by_date[date_key]["requests"] += 1
                    by_date[date_key]["input_tokens"] += record.get("input_tokens", 0)
                    by_date[date_key]["output_tokens"] += record.get("output_tokens", 0)
                    by_date[date_key]["cost"] += cost
                    by_date[date_key]["cost_by_currency"][currency] += cost

            # Convert defaultdict to plain dict (including nested cost_by_currency)
            stats.cost_by_currency = dict(cost_by_currency)
            stats.by_provider = {k: {**v, "cost_by_currency": dict(v["cost_by_currency"])} for k, v in by_provider.items()}
            stats.by_model = {k: {**v, "cost_by_currency": dict(v["cost_by_currency"])} for k, v in by_model.items()}
            stats.by_date = {k: {**v, "cost_by_currency": dict(v["cost_by_currency"])} for k, v in by_date.items()}
            
            logger.info(f"✅ 获取使用统计成功: {stats.total_requests} 条记录")
            return stats
        except Exception as e:
            logger.error(f"❌ 获取使用统计失败: {e}")
            return UsageStatistics()
    
    async def get_cost_by_provider(self, days: int = 7) -> Dict[str, float]:
        """获取按供应商的成本统计"""
        stats = await self.get_usage_statistics(days=days)
        return {
            provider: data["cost"]
            for provider, data in stats.by_provider.items()
        }
    
    async def get_cost_by_model(self, days: int = 7) -> Dict[str, float]:
        """获取按模型的成本统计"""
        stats = await self.get_usage_statistics(days=days)
        return {
            model: data["cost"]
            for model, data in stats.by_model.items()
        }
    
    async def get_daily_cost(self, days: int = 7) -> Dict[str, float]:
        """获取每日成本统计"""
        stats = await self.get_usage_statistics(days=days)
        return {
            date: data["cost"]
            for date, data in stats.by_date.items()
        }
    
    async def delete_old_records(self, days: int = 90) -> int:
        """删除旧记录"""
        try:
            db = get_mongo_db()
            collection = db[self.collection_name]
            
            # Calculate deadline
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Delete old records
            result = await collection.delete_many({
                "timestamp": {"$lt": cutoff_date.isoformat()}
            })
            
            deleted_count = result.deleted_count
            logger.info(f"✅ 删除旧记录成功: {deleted_count} 条")
            return deleted_count
        except Exception as e:
            logger.error(f"❌ 删除旧记录失败: {e}")
            return 0

    async def record_llm_usage(
        self,
        response,  # LLMResponse or langchain AIMessage
        session_id: str,
        analysis_type: str,
        stock_code: Optional[str] = None
    ) -> bool:
        """
        Record token usage for LLM calls (general method)
        
        Compatible with two LLM response objects:
        - UnifiedLLMClient LLMResponse:response.usage(Dict: prompt_tokens/completion_tokens/total_tokens) 
        - LangChain AIMessage: response.usage_metadata(Dict: input_tokens/output_tokens/token_usage) 
        
        Args:
            response: LLM response object
            session_id: session ID
            analysis_type: Function type
            stock_code: Stock code (optional)
        
        Returns:
            bool: Whether the recording is successful
        """
        try:
            if not response:
                logger.debug(f"LLM Response is empty, skipping records: {analysis_type}")
                return False
            
            # Compatible with LLMResponse (UnifiedLLMClient) and AIMessage (LangChain)
            usage = None
            provider = "unknown"
            model_name = "unknown"
            
            if hasattr(response, 'usage') and response.usage:
                # UnifiedLLMClient of LLMResponse
                usage = response.usage
                provider = response.provider.value if response.provider else "unknown"
                model_name = response.model or "unknown"
            elif hasattr(response, 'usage_metadata') and response.usage_metadata:
                # LangChain of AIMessage
                usage = response.usage_metadata
                # AIMessage No provider field, try to get from response_metadata
                meta = getattr(response, 'response_metadata', {})
                model_name = meta.get('model_name', '') or meta.get('model', '') or "unknown"
            
            if not usage:
                logger.debug(f"LLM Response without usage information, skip recording: {analysis_type}")
                return False
            
            # Unified extraction of token numbers (compatible with both formats)
            input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
            
            if input_tokens == 0 and output_tokens == 0:
                logger.debug(f"Token If the number is 0, the record will be skipped.: {analysis_type}")
                return False
            
            # Get model price configuration
            from app.services.config_service import config_service
            config = await config_service.get_system_config()
            
            # Find the corresponding LLM configuration
            llm_config = None
            if config and config.llm_configs:
                for cfg in config.llm_configs:
                    if cfg.provider == provider and cfg.model_name == model_name:
                        llm_config = cfg
                        break
            
            # Calculate cost
            cost = 0.0
            currency = "CNY"
            if llm_config:
                input_price = llm_config.input_price_per_1k or 0.0
                output_price = llm_config.output_price_per_1k or 0.0
                cost = (input_tokens / 1000 * input_price) + (output_tokens / 1000 * output_price)
                currency = llm_config.currency or "CNY"
            
            # Create usage record
            usage_record = UsageRecord(
                timestamp=datetime.now().isoformat(),
                provider=provider,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                currency=currency,
                session_id=session_id,
                analysis_type=analysis_type,
                stock_code=stock_code
            )
            
            # Save to database
            success = await self.add_usage_record(usage_record)
            
            if success:
                logger.info(f"💰 记录 token 使用: {provider}/{model_name} - 输入:{input_tokens} 输出:{output_tokens} [{analysis_type}]")
            
            return success
        except Exception as e:
            logger.error(f"❌ Log LLM token usage failure: {e}")
            return False


# Create a global instance
usage_statistics_service = UsageStatisticsService()


# === update_service.py ===
"""
Automatic update service

Function:
1. Check the official website to see if there is a new version
2. Download update package (with progress tracking)
3. Verify update package (SHA256)
4. Trigger updater script (standalone process)
"""
import os
import json
import hashlib
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Default update server address (used when configured as empty)
DEFAULT_UPDATE_BASE_URL = "https://www.tradingagentscn.com/api"


class UpdateInfo:
    """更新信息"""

    def __init__(self, data: dict):
        self.has_update: bool = data.get("has_update", False)
        self.latest_version: str = data.get("version", "")
        self.package_type: str = self._normalize_package_type(data.get("package_type"))
        self.download_url: str = data.get("download_url", "")
        self.file_size: int = data.get("file_size", 0)
        self.sha256: str = data.get("sha256", "")
        self.release_notes: str = data.get("release_notes", "")
        self.release_date: str = data.get("release_date", "")
        self.is_mandatory: bool = data.get("is_mandatory", False)
        self.min_version: str = data.get("min_version", "")
        self.check_failed: bool = data.get("check_failed", False)
        self.error_message: str = data.get("error_message", "")

    def to_dict(self) -> dict:
        return {
            "has_update": self.has_update,
            "latest_version": self.latest_version,
            "package_type": self.package_type,
            "download_url": self.download_url,
            "file_size": self.file_size,
            "sha256": self.sha256,
            "release_notes": self.release_notes,
            "release_date": self.release_date,
            "is_mandatory": self.is_mandatory,
            "min_version": self.min_version,
            "check_failed": self.check_failed,
            "error_message": self.error_message,
        }

    @staticmethod
    def _normalize_package_type(package_type: Optional[str]) -> str:
        raw = (package_type or "installer").strip().lower()
        return raw if raw in {"installer", "update"} else "installer"


class UpdateService:
    """自动更新服务"""

    # Update package download directory
    UPDATES_DIR = PROJECT_ROOT / "runtime" / "updates"

    # Backup directory
    BACKUP_DIR = PROJECT_ROOT / "backup"

    def __init__(self):
        # Read update check address from configuration, support UPDATE_CHECK_BASE_URL coverage in .env (for test verification)
        url = (settings.UPDATE_CHECK_BASE_URL or "").strip()
        self.base_url = url if url else DEFAULT_UPDATE_BASE_URL
        self.channel = self._normalize_update_channel(settings.UPDATE_CHECK_CHANNEL)
        self._download_progress: Dict[str, Any] = {}
        # Make sure the directory exists
        self.UPDATES_DIR.mkdir(parents=True, exist_ok=True)

    # ── Version information ──────────────────────────────────────────

    def get_current_version(self) -> str:
        """读取当前版本号"""
        version_file = PROJECT_ROOT / "VERSION"
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except Exception:
            return "0.0.0"

    def get_build_info(self) -> dict:
        """读取构建信息"""
        build_file = PROJECT_ROOT / "BUILD_INFO"
        try:
            raw = build_file.read_text(encoding="utf-8-sig").strip()
            return json.loads(raw)
        except Exception:
            return {}

    def get_update_channel(self) -> str:
        """获取当前更新通道"""
        return self.channel

    # ── Check for updates ──────────────────────────────────────────

    async def check_for_updates(self) -> UpdateInfo:
        """向官网查询是否有新版本"""
        current_version = self.get_current_version()
        build_info = self.get_build_info()

        logger.info(
            f"🔍 检查更新... 当前版本: {current_version}, 通道: {self.channel}"
        )

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.base_url}/app/check-update",
                    params={
                        "version": current_version,
                        "build_type": build_info.get("build_type", "unknown"),
                        "channel": self.channel,
                    },
                    headers={"User-Agent": f"TradingAgentsCN/{current_version}"},
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        info = UpdateInfo(data.get("data", {}))
                        if info.has_update:
                            logger.info(
                                f"📦 发现新版本: {info.latest_version}"
                            )
                        else:
                            logger.info("✅ 已是最新版本")
                        return info

                logger.warning(f"⚠️ Check for updates failed: HTTP {resp.status_code}")
                return UpdateInfo({
                    "has_update": False,
                    "check_failed": True,
                    "error_message": f"Update server returns error (HTTP {resp.status_code})",
                })

        except httpx.ConnectError:
            logger.warning("⚠️ 无法连接更新服务器")
            return UpdateInfo({
                "has_update": False,
                "check_failed": True,
                "error_message": "Unable to connect to update server, please check the network or try again later",
            })
        except httpx.TimeoutException:
            logger.warning("⚠️ 连接更新服务器超时")
            return UpdateInfo({
                "has_update": False,
                "check_failed": True,
                "error_message": "The connection to the update server timed out, please try again later.",
            })
        except Exception as e:
            logger.error(f"❌ 检查更新异常: {e}")
            return UpdateInfo({
                "has_update": False,
                "check_failed": True,
                "error_message": f"检查更新失败: {str(e)}",
            })

    # ── Download update package ────────────────────────────────────────

    async def download_update(self, update_info: UpdateInfo) -> Optional[Path]:
        """Download the update package and return the local file path"""
        if not update_info.download_url:
            logger.error("❌ 下载地址为空")
            return None

        version = update_info.latest_version
        filename = self._build_download_filename(update_info)
        target_path = self.UPDATES_DIR / filename

        # If it has been downloaded and verified, return directly.
        if target_path.exists() and update_info.sha256:
            if self._verify_sha256(target_path, update_info.sha256):
                logger.info(f"✅ The update package already exists and the verification passed.: {filename}")
                return target_path

        logger.info(f"⬇️ 开始下载更新包: {update_info.download_url}")
        self._download_progress = {
            "status": "downloading",
            "version": version,
            "total": update_info.file_size,
            "downloaded": 0,
            "percent": 0,
        }

        try:
            async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
                async with client.stream("GET", update_info.download_url) as resp:
                    if resp.status_code != 200:
                        logger.error(f"❌ 下载失败: HTTP {resp.status_code}")
                        self._download_progress["status"] = "failed"
                        return None

                    total = int(resp.headers.get("content-length", 0)) or update_info.file_size
                    self._download_progress["total"] = total
                    downloaded = 0

                    with open(target_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            downloaded += len(chunk)
                            self._download_progress["downloaded"] = downloaded
                            if total > 0:
                                self._download_progress["percent"] = round(
                                    downloaded * 100 / total, 1
                                )

            # Verification
            if update_info.sha256:
                if not self._verify_sha256(target_path, update_info.sha256):
                    logger.error("❌ Update package verification failed, SHA256 does not match")
                    target_path.unlink(missing_ok=True)
                    self._download_progress["status"] = "verify_failed"
                    return None

            self._download_progress["status"] = "completed"
            self._download_progress["percent"] = 100
            logger.info(f"✅ 更新包下载完成: {filename} ({downloaded} bytes)")
            return target_path

        except Exception as e:
            logger.error(f"❌ 下载更新包异常: {e}")
            self._download_progress["status"] = "failed"
            target_path.unlink(missing_ok=True)
            return None

    def get_download_progress(self) -> dict:
        """获取下载进度"""
        return dict(self._download_progress) if self._download_progress else {
            "status": "idle",
            "percent": 0,
        }

    def get_download_message(self, update_info: UpdateInfo) -> str:
        """Generate download prompts based on package type."""
        if update_info.package_type == "installer":
            return f"发现 v{update_info.latest_version} 安装包，请下载安装后手动升级"
        return f"开始下载 v{update_info.latest_version} 更新包"

    # ── Apply updates ──────────────────────────────────────────

    async def apply_update(self, update_file: Path, version: str) -> dict:
        """
        Starts a standalone updater process and then notifies the caller that the application needs to exit.

        The update process is handled by scripts/updater/apply_update.ps1:
        1. Wait for the backend process to exit
        2. Back up current version
        3. Unzip the update package
        4. Restart all services
        """
        if not update_file.exists():
            return {"success": False, "message": "更新包文件不存在"}

        updater_script = PROJECT_ROOT / "scripts" / "updater" / "apply_update.ps1"
        if not updater_script.exists():
            return {"success": False, "message": "更新器脚本不存在"}

        current_version = self.get_current_version()
        logger.info(f"🚀 启动更新: {current_version} → {version}")

        try:
            # Start a standalone PowerShell updater process
            cmd = [
                "powershell.exe",
                "-ExecutionPolicy", "Bypass",
                "-File", str(updater_script),
                "-UpdateFile", str(update_file),
                "-TargetVersion", version,
                "-CurrentVersion", current_version,
                "-ProjectRoot", str(PROJECT_ROOT),
            ]

            # CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS Make the updater independent of the backend process
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008

            subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            logger.info("✅ The updater process has been started and the backend is about to exit...")
            return {
                "success": True,
                "message": f"更新器已启动，正在从 {current_version} 更新到 {version}",
            }

        except Exception as e:
            logger.error(f"❌ 启动更新器失败: {e}")
            return {"success": False, "message": f"启动更新器失败: {e}"}

    # ── clean up ──────────────────────────────────────────────

    def cleanup_old_packages(self, keep_latest: int = 2):
        """Clean up old update packages and keep the latest N ones"""
        if not self.UPDATES_DIR.exists():
            return

        files = sorted(
            self.UPDATES_DIR.glob("update-*.zip"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        for f in files[keep_latest:]:
            try:
                f.unlink()
                logger.info(f"🗑️ 清理旧更新包: {f.name}")
            except Exception as e:
                logger.warning(f"⚠️ 清理失败: {f.name} - {e}")

    # ── internal method ──────────────────────────────────────────

    @staticmethod
    def _build_download_filename(update_info: UpdateInfo) -> str:
        """Infer local file names based on download address and package type."""
        parsed = httpx.URL(update_info.download_url)
        basename = Path(parsed.path).name.strip()
        if basename:
            return basename
        extension = ".exe" if update_info.package_type == "installer" else ".zip"
        prefix = "installer" if update_info.package_type == "installer" else "update"
        return f"{prefix}-{update_info.latest_version}{extension}"

    @staticmethod
    def _normalize_update_channel(channel: Optional[str]) -> str:
        """Normalize the update channel to avoid server-side distribution inconsistency caused by alias configuration."""
        raw = (channel or "").strip().lower()
        alias_map = {
            "": "stable",
            "stable": "stable",
            "formal": "stable",
            "prod": "stable",
            "production": "stable",
            "release": "stable",
            "official": "stable",
            "正式": "stable",
            "线上": "stable",
            "test": "test",
            "testing": "test",
            "beta": "test",
            "staging": "test",
            "preview": "test",
            "测试": "test",
            "预发": "test",
        }
        normalized = alias_map.get(raw)
        if normalized:
            return normalized

        logger.warning("⚠️ Unrecognized update channel configuration '%s', Reverted to stable", channel)
        return "stable"

    @staticmethod
    def _verify_sha256(file_path: Path, expected_hash: str) -> bool:
        """校验文件 SHA256"""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha256.update(data)
        actual = sha256.hexdigest()
        match = actual.lower() == expected_hash.lower()
        if not match:
            logger.warning(
                f"SHA256 no match: expected={expected_hash[:16]}... actual={actual[:16]}..."
            )
        return match


# Singleton
_update_service: Optional[UpdateService] = None


def get_update_service() -> UpdateService:
    """获取更新服务单例"""
    global _update_service
    if _update_service is None:
        _update_service = UpdateService()
    return _update_service

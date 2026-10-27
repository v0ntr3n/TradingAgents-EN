"""
Backup, import, and export routines extracted from DatabaseService.
"""
from __future__ import annotations

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

from bson import ObjectId

from app.core.database import get_mongo_db
from app.core.config import settings
from .serialization import serialize_document

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
        logger.info(f"📦 New version of multi-collection export file detected (contains export_info)")
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
            logger.info(f"🔍 [Single collection mode] Data is not a list, convert to list")
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


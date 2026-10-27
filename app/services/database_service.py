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
from bson import ObjectId
import motor.motor_asyncio
import redis.asyncio as redis
from pymongo.errors import ServerSelectionTimeoutError

from app.core.database import get_mongo_db, get_redis_client, db_manager
from app.core.config import settings

from app.services.database import status_checks as _db_status
from app.services.database import cleanup as _db_cleanup
from app.services.database import backups as _db_backups
from app.services.database.serialization import serialize_document as _serialize_doc

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

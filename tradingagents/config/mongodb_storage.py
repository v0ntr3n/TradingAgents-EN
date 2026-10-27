#!/usr/bin/env python3
"""
MongoDB storage adapter
Used to store token usage records in the MongoDB database
"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from .usage_models import UsageRecord

# Import log module
from tradingagents.utils.logging_manager import get_logger
from tradingagents.config.runtime_settings import get_timezone_name
logger = get_logger('agents')

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    MongoClient = None


class MongoDBStorage:
    """MongoDB storage adapter"""
    
    def __init__(self, connection_string: str = None, database_name: str = None):
        if not MONGODB_AVAILABLE:
            raise ImportError("pymongo is not installed. Please install it with: pip install pymongo")

        # Build connection strings using unified utility functions
        from .mongodb_utils import build_mongodb_connection_string, get_mongodb_database_name

        self.connection_string = connection_string or build_mongodb_connection_string()
        self.database_name = database_name or get_mongodb_database_name()
        self.collection_name = "token_usage"
        
        self.client = None
        self.db = None
        self.collection = None
        self._connected = False
        
        # try to connect
        self._connect()
    
    def _connect(self):
        """Connect to MongoDB"""
        try:
            # Read timeout configuration from environment variables, using sensible defaults
            import os
            connect_timeout = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "30000"))
            socket_timeout = int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "60000"))
            server_selection_timeout = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000"))

            self.client = MongoClient(
                self.connection_string,
                serverSelectionTimeoutMS=server_selection_timeout,
                connectTimeoutMS=connect_timeout,
                socketTimeoutMS=socket_timeout
            )
            # test connection
            self.client.admin.command('ping')
            
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            
            # Create indexes to improve query performance
            self._create_indexes()
            
            self._connected = True
            logger.info(f"✅ MongoDB Connection successful: {self.database_name}.{self.collection_name}")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"❌ MongoDB Connection failed: {e}")
            logger.info(f"Will use local JSON file storage")
            self._connected = False
        except Exception as e:
            logger.error(f"❌ MongoDB Initialization failed: {e}")
            self._connected = False
    
    def _create_indexes(self):
        """Create database index"""
        try:
            # Create composite index
            self.collection.create_index([
                ("timestamp", -1),  # in reverse chronological order
                ("provider", 1),
                ("model_name", 1)
            ])
            
            # Create session ID index
            self.collection.create_index("session_id")
            
            # Create analysis type index
            self.collection.create_index("analysis_type")
            
        except Exception as e:
            logger.error(f"Creating MongoDB index failed: {e}")
    
    def is_connected(self) -> bool:
        """Check if connected to MongoDB"""
        return self._connected
    
    def save_usage_record(self, record: UsageRecord) -> bool:
        """Save individual usage records to MongoDB"""
        if not self._connected:
            logger.warning(f"⚠️ [MongoDB storage] Not connected, unable to save record")
            return False

        try:
            # Convert to dictionary format
            record_dict = asdict(record)

            # Add MongoDB-specific fields
            record_dict['_created_at'] = datetime.now(ZoneInfo(get_timezone_name()))

            # 🔍 Detailed log
            logger.debug(f"📊 [MongoDB storage] Prepare to insert records: {record.provider}/{record.model_name}, session={record.session_id}")
            logger.debug(f"   database: {self.database_name}, collection: {self.collection_name}")

            # Insert record
            result = self.collection.insert_one(record_dict)

            if result.inserted_id:
                logger.info(f"✅ [MongoDB storage] Record saved: ID={result.inserted_id}, {record.provider}/{record.model_name}, ¥{record.cost:.4f}")
                return True
            else:
                logger.error(f"❌ [MongoDB storage] Insert failed: Insert not returned ID")
                return False

        except Exception as e:
            logger.error(f"❌ [MongoDB storage] Failed to save record: {e}")
            import traceback
            logger.error(f"   stack: {traceback.format_exc()}")
            return False
    
    def load_usage_records(self, limit: int = 10000, days: int = None) -> List[UsageRecord]:
        """Load usage records from MongoDB"""
        if not self._connected:
            return []
        
        try:
            # Build query conditions
            query = {}
            if days:
                from datetime import timedelta
                cutoff_date = datetime.now(ZoneInfo(get_timezone_name())) - timedelta(days=days)
                query['timestamp'] = {'$gte': cutoff_date.isoformat()}
            
            # Query records in reverse chronological order
            cursor = self.collection.find(query).sort('timestamp', -1).limit(limit)
            
            records = []
            for doc in cursor:
                # Remove MongoDB-specific fields
                doc.pop('_id', None)
                doc.pop('_created_at', None)
                
                # Convert to UsageRecord object
                try:
                    record = UsageRecord(**doc)
                    records.append(record)
                except Exception as e:
                    logger.error(f"Failed to parse record: {e}, record: {doc}")
                    continue
            
            return records
            
        except Exception as e:
            logger.error(f"Loading records from MongoDB failed: {e}")
            return []
    
    def get_usage_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Get usage statistics from MongoDB"""
        if not self._connected:
            return {}
        
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Aggregation query
            pipeline = [
                {
                    '$match': {
                        'timestamp': {'$gte': cutoff_date.isoformat()}
                    }
                },
                {
                    '$group': {
                        '_id': None,
                        'total_cost': {'$sum': '$cost'},
                        'total_input_tokens': {'$sum': '$input_tokens'},
                        'total_output_tokens': {'$sum': '$output_tokens'},
                        'total_requests': {'$sum': 1}
                    }
                }
            ]
            
            result = list(self.collection.aggregate(pipeline))
            
            if result:
                stats = result[0]
                return {
                    'period_days': days,
                    'total_cost': round(stats.get('total_cost', 0), 4),
                    'total_input_tokens': stats.get('total_input_tokens', 0),
                    'total_output_tokens': stats.get('total_output_tokens', 0),
                    'total_requests': stats.get('total_requests', 0)
                }
            else:
                return {
                    'period_days': days,
                    'total_cost': 0,
                    'total_input_tokens': 0,
                    'total_output_tokens': 0,
                    'total_requests': 0
                }
                
        except Exception as e:
            logger.error(f"Failed to obtain MongoDB statistics: {e}")
            return {}
    
    def get_provider_statistics(self, days: int = 30) -> Dict[str, Dict[str, Any]]:
        """Get statistics by vendor"""
        if not self._connected:
            return {}
        
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Aggregate by supplier
            pipeline = [
                {
                    '$match': {
                        'timestamp': {'$gte': cutoff_date.isoformat()}
                    }
                },
                {
                    '$group': {
                        '_id': '$provider',
                        'cost': {'$sum': '$cost'},
                        'input_tokens': {'$sum': '$input_tokens'},
                        'output_tokens': {'$sum': '$output_tokens'},
                        'requests': {'$sum': 1}
                    }
                }
            ]
            
            results = list(self.collection.aggregate(pipeline))
            
            provider_stats = {}
            for result in results:
                provider = result['_id']
                provider_stats[provider] = {
                    'cost': round(result.get('cost', 0), 4),
                    'input_tokens': result.get('input_tokens', 0),
                    'output_tokens': result.get('output_tokens', 0),
                    'requests': result.get('requests', 0)
                }
            
            return provider_stats
            
        except Exception as e:
            logger.error(f"Failed to obtain supplier statistics: {e}")
            return {}
    
    def cleanup_old_records(self, days: int = 90) -> int:
        """Clean up old records"""
        if not self._connected:
            return 0
        
        try:
            from datetime import timedelta

            cutoff_date = datetime.now() - timedelta(days=days)
            
            result = self.collection.delete_many({
                'timestamp': {'$lt': cutoff_date.isoformat()}
            })
            
            deleted_count = result.deleted_count
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} more than {days} record of days")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Cleaning old records failed: {e}")
            return 0
    
    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            self._connected = False
            logger.info(f"MongoDB connection closed")
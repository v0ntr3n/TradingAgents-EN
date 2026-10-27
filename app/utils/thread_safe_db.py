"""
Thread-safe database operation tools

Used to safely perform MongoDB operations in the thread pool to avoid event loop conflicts
"""
import threading
import asyncio
import logging
from typing import List, Any
from pymongo.results import BulkWriteResult

logger = logging.getLogger(__name__)


def is_in_thread_pool() -> bool:
    """
    Detect whether it is currently running in the thread pool
    
    Returns:
        True False if in the thread pool, False if in the main thread
    """
    current_thread = threading.current_thread()
    return not isinstance(current_thread, threading._MainThread)


async def safe_bulk_write(
    collection_name: str,
    operations: List,
    ordered: bool = False,
    async_db=None,
    max_retries: int = 3
) -> BulkWriteResult:
    """
    Thread-safe bulk_write operations
    
    Automatically detect the running environment:
    - In the main thread: Using an asynchronous MongoDB client
    - In a thread pool: Using a synchronous MongoDB client
    
    Args:
        collection_name: Collection name
        operations: Bulk operation list
        ordered: Whether to execute in order
        async_db: Asynchronous database instance (used in the main thread)
        max_retries: Maximum number of retries
        
    Returns:
        BulkWriteResult object
        
    Raises:
        Exception: If all retries fail
    """
    in_thread_pool = is_in_thread_pool()
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            if in_thread_pool:
                # 🔥 In a thread pool: Using a synchronous MongoDB client
                logger.debug(f"🔍 [thread pool] Use sync bulk_write: collection={collection_name}, operand={len(operations)}, ordered={ordered}")
                from app.core.database import get_mongo_db_sync
                sync_db = get_mongo_db_sync()
                sync_collection = sync_db[collection_name]
                result = sync_collection.bulk_write(operations, ordered=ordered)
                return result
            else:
                # 🔥 In the main thread: Using an asynchronous MongoDB client
                if async_db is None:
                    from app.core.database import get_mongo_db
                    async_db = get_mongo_db()
                
                logger.debug(f"🔍 [main thread] Use async bulk_write: collection={collection_name}, operand={len(operations)}, ordered={ordered}")
                async_collection = async_db[collection_name]
                result = await async_collection.bulk_write(operations, ordered=ordered)
                return result
                
        except asyncio.TimeoutError as e:
            retry_count += 1
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff: 2 seconds, 4 seconds, 8 seconds
                logger.warning(f"⚠️ Batch write timeout (No.{retry_count}/{max_retries}retries), wait{wait_time}Try again in seconds...")
                
                # 🔥 Choose the sleep mode according to the operating environment
                if in_thread_pool:
                    import time
                    time.sleep(wait_time)
                else:
                    await asyncio.sleep(wait_time)
            else:
                logger.error(f"❌ Batch write failed, retried{max_retries}times: {e}")
                raise
                
        except Exception as e:
            # Check if it is a timeout related error
            error_msg = str(e).lower()
            if 'timeout' in error_msg or 'timed out' in error_msg:
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(f"⚠️ Batch write timeout (No.{retry_count}/{max_retries}retries), wait{wait_time}Try again in seconds... Error: {e}")
                    
                    # 🔥 Choose the sleep mode according to the operating environment
                    if in_thread_pool:
                        import time
                        time.sleep(wait_time)
                    else:
                        await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Batch write failed, retried{max_retries}times: {e}")
                    raise
            else:
                logger.error(f"❌ Batch write failed: {e}")
                raise
    
    raise Exception(f"Batch write failed, retried{max_retries}times")


async def safe_sleep(seconds: float):
    """
    Thread-safe sleep operation
    
    Automatically detect the running environment:
    - In the main thread: use asyncio.sleep
    - In the thread pool: use time.sleep
    
    Args:
        seconds: sleep seconds
    """
    if is_in_thread_pool():
        import time
        time.sleep(seconds)
    else:
        await asyncio.sleep(seconds)


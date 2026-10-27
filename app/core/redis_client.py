"""Redis Compatibility layer.

Historical callers can still import interfaces from this module, but the actual connection life cycle is delegated to app.core.database.
"""

import redis.asyncio as redis
import logging
from typing import Optional

from .database import close_redis_binding, get_redis_client, init_redis_binding

logger = logging.getLogger(__name__)


async def init_redis():
    """Initialize the Redis connection."""
    await init_redis_binding()


async def close_redis():
    """Close the Redis connection."""
    await close_redis_binding()


def get_redis() -> redis.Redis:
    """Get the Redis client instance."""
    return get_redis_client()


class RedisKeys:
    """Redis Key name constant"""
    
    # Queue related
    USER_PENDING_QUEUE = "user:{user_id}:pending"
    USER_PROCESSING_SET = "user:{user_id}:processing"
    GLOBAL_PENDING_QUEUE = "global:pending"
    GLOBAL_PROCESSING_SET = "global:processing"
    
    # Task related
    TASK_PROGRESS = "task:{task_id}:progress"
    TASK_RESULT = "task:{task_id}:result"
    TASK_LOCK = "task:{task_id}:lock"
    
    # Batch related
    BATCH_PROGRESS = "batch:{batch_id}:progress"
    BATCH_TASKS = "batch:{batch_id}:tasks"
    BATCH_LOCK = "batch:{batch_id}:lock"
    
    # User related
    USER_SESSION = "session:{session_id}"
    USER_RATE_LIMIT = "rate_limit:{user_id}:{endpoint}"
    USER_DAILY_QUOTA = "quota:{user_id}:{date}"
    
    # System related
    QUEUE_STATS = "queue:stats"
    SYSTEM_CONFIG = "system:config"
    WORKER_HEARTBEAT = "worker:{worker_id}:heartbeat"
    
    # Cache related
    SCREENING_CACHE = "screening:{cache_key}"
    ANALYSIS_CACHE = "analysis:{cache_key}"
    
    # Related to scheduled tasks
    SCHEDULER_JOB_PROGRESS = "scheduler:job:{job_id}:progress"
    SCHEDULER_JOB_STATUS = "scheduler:job:{job_id}:status"
    SCHEDULER_JOB_EXECUTION = "scheduler:job:{job_id}:execution"


class RedisService:
    """Redis Service encapsulation class"""

    @property
    def redis(self):
        """Delayed acquisition of Redis client"""
        try:
            return get_redis_client()
        except RuntimeError:
            raise RuntimeError("Redis The client is not initialized, please ensure that it is called when the application starts init_redis() or init_database()")

    async def set_with_ttl(self, key: str, value: str, ttl: int = 3600):
        """Set key value with TTL"""
        await self.redis.setex(key, ttl, value)

    async def get_json(self, key: str):
        """Get value in JSON format"""
        import json
        value = await self.redis.get(key)
        if value:
            return json.loads(value)
        return None
    
    async def set_json(self, key: str, value: dict, ttl: int = None):
        """Set value in JSON format"""
        import json
        json_str = json.dumps(value, ensure_ascii=False)
        if ttl:
            await self.redis.setex(key, ttl, json_str)
        else:
            await self.redis.set(key, json_str)
    
    async def increment_with_ttl(self, key: str, ttl: int = 3600):
        """Increment the counter and set TTL"""
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        results = await pipe.execute()
        return results[0]
    
    async def add_to_queue(self, queue_key: str, item: dict):
        """Add item to queue"""
        import json
        await self.redis.lpush(queue_key, json.dumps(item, ensure_ascii=False))
    
    async def pop_from_queue(self, queue_key: str, timeout: int = 1):
        """Pop items from queue"""
        import json
        result = await self.redis.brpop(queue_key, timeout=timeout)
        if result:
            return json.loads(result[1])
        return None
    
    async def get_queue_length(self, queue_key: str):
        """Get queue length"""
        return await self.redis.llen(queue_key)
    
    async def add_to_set(self, set_key: str, value: str):
        """add to collection"""
        await self.redis.sadd(set_key, value)
    
    async def remove_from_set(self, set_key: str, value: str):
        """Remove from collection"""
        await self.redis.srem(set_key, value)
    
    async def is_in_set(self, set_key: str, value: str):
        """Check if it is in the collection"""
        return await self.redis.sismember(set_key, value)
    
    async def get_set_size(self, set_key: str):
        """Get collection size"""
        return await self.redis.scard(set_key)
    
    async def acquire_lock(self, lock_key: str, timeout: int = 30):
        """Get distributed lock"""
        import uuid
        lock_value = str(uuid.uuid4())
        acquired = await self.redis.set(lock_key, lock_value, nx=True, ex=timeout)
        if acquired:
            return lock_value
        return None
    
    async def release_lock(self, lock_key: str, lock_value: str):
        """Release distributed lock"""
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        return await self.redis.eval(lua_script, 1, lock_key, lock_value)


# Global Redis service instance
redis_service: Optional[RedisService] = None


def get_redis_service() -> RedisService:
    """Get Redis service instance"""
    global redis_service
    if redis_service is None:
        redis_service = RedisService()
    return redis_service

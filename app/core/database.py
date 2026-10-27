"""
Database connection management module
Enhanced version with support for connection pooling, health checking and error recovery
"""

import logging
import asyncio
from typing import Callable, Optional, Tuple, Dict
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import MongoClient
from pymongo.database import Database
from redis.asyncio import Redis, ConnectionPool
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import AuthenticationError as RedisAuthenticationError
from .config import settings

# Synchronous Redis client types (lazy import to avoid circular dependencies)
try:
    import redis as redis_sync
except ImportError:
    redis_sync = None

logger = logging.getLogger(__name__)


def _should_retry_redis_without_password(error: Exception) -> bool:
    """Determine whether it should fall back and try again in the local passwordless Redis scenario."""
    if not isinstance(error, RedisAuthenticationError):
        return False

    error_text = str(error).lower()
    return "without any password configured" in error_text


def _build_redis_url_without_password() -> str:
    """Construct a passwordless Redis URL for local passwordless instance fallback."""
    return f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

# Global connection instance
mongo_client: Optional[AsyncIOMotorClient] = None
mongo_db: Optional[AsyncIOMotorDatabase] = None
redis_client: Optional[Redis] = None
redis_pool: Optional[ConnectionPool] = None
_mongo_runtime_loop: Optional[asyncio.AbstractEventLoop] = None
_redis_runtime_loop: Optional[asyncio.AbstractEventLoop] = None
_mongo_db_proxy = None
_mongo_client_proxy = None
_redis_client_proxy = None
_mongo_loop_bindings: Dict[int, Tuple[asyncio.AbstractEventLoop, AsyncIOMotorClient, AsyncIOMotorDatabase]] = {}

# Synchronous MongoDB connection (for non-async context)
_sync_mongo_client: Optional[MongoClient] = None
_sync_mongo_db: Optional[Database] = None


class DatabaseManager:
    """Database connection manager"""

    def __init__(self):
        self.mongo_client: Optional[AsyncIOMotorClient] = None
        self.mongo_db: Optional[AsyncIOMotorDatabase] = None
        self.redis_client: Optional[Redis] = None
        self.redis_pool: Optional[ConnectionPool] = None
        self.redis_url_in_use: Optional[str] = None
        self._mongo_healthy = False
        self._redis_healthy = False

    async def init_mongodb(self):
        """Initialize MongoDB connection"""
        try:
            logger.info("🔄 Initializing MongoDB connection...")

            # Create MongoDB client and configure connection pool
            self.mongo_client = _create_async_mongo_client()

            # Get database instance
            self.mongo_db = self.mongo_client[settings.MONGO_DB]

            # test connection
            await self.mongo_client.admin.command('ping')
            self._mongo_healthy = True

            logger.info("✅ MongoDB Connection established successfully")
            logger.info(f"📊 database: {settings.MONGO_DB}")
            logger.info(f"🔗 connection pool: {settings.MONGO_MIN_CONNECTIONS}-{settings.MONGO_MAX_CONNECTIONS}")
            logger.info(f"⏱️  Timeout configuration: connectTimeout={settings.MONGO_CONNECT_TIMEOUT_MS}ms, socketTimeout={settings.MONGO_SOCKET_TIMEOUT_MS}ms")

        except Exception as e:
            logger.error(f"❌ MongoDB Connection failed: {e}")
            self._mongo_healthy = False
            raise

    async def init_redis(self):
        """Initialize Redis connection"""
        try:
            logger.info("🔄 Initializing Redis connection...")

            async def _connect(redis_url: str) -> tuple[ConnectionPool, Redis]:
                pool = ConnectionPool.from_url(
                    redis_url,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    retry_on_timeout=settings.REDIS_RETRY_ON_TIMEOUT,
                    decode_responses=True,
                    socket_connect_timeout=5,  # 5 Seconds connection timeout
                    socket_timeout=10,  # 10 seconds socket timeout
                )
                client = Redis(connection_pool=pool)
                try:
                    await client.ping()
                    return pool, client
                except Exception:
                    await client.close()
                    await pool.disconnect()
                    raise

            try:
                self.redis_pool, self.redis_client = await _connect(settings.REDIS_URL)
                self.redis_url_in_use = settings.REDIS_URL
            except Exception as e:
                if not (settings.REDIS_PASSWORD and _should_retry_redis_without_password(e)):
                    raise

                logger.warning(
                    "⚠️ The current Redis instance does not have a password configured, but the environment variable provides REDIS_PASSWORD;"
                    "Will automatically fall back to passwordless connection."
                )
                fallback_url = _build_redis_url_without_password()
                self.redis_pool, self.redis_client = await _connect(fallback_url)
                self.redis_url_in_use = fallback_url

            self._redis_healthy = True

            logger.info("✅ Redis Connection established successfully")
            logger.info(f"🔗 Connection pool size: {settings.REDIS_MAX_CONNECTIONS}")

        except Exception as e:
            logger.error(f"❌ Redis Connection failed: {e}")
            self._redis_healthy = False
            raise

    async def close_connections(self):
        """Close all database connections"""
        logger.info("🔄 Closing database connection...")

        # Close MongoDB connection
        try:
            await _close_all_async_mongo_bindings(log_message=False)
            self._mongo_healthy = False
            logger.info("✅ MongoDB connection closed")
        except Exception as e:
            logger.error(f"❌ Error closing MongoDB connection: {e}")

        # Close Redis connection
        if self.redis_client:
            try:
                await self.redis_client.close()
                self._redis_healthy = False
                logger.info("✅ Redis connection closed")
            except Exception as e:
                logger.error(f"❌ Error closing Redis connection: {e}")

        # Close the Redis connection pool
        if self.redis_pool:
            try:
                await self.redis_pool.disconnect()
                logger.info("✅ Redis Connection pool is closed")
            except Exception as e:
                logger.error(f"❌ Error closing Redis connection pool: {e}")

    async def health_check(self) -> dict:
        """Database health check"""
        health_status = {
            "mongodb": {"status": "unknown", "details": None},
            "redis": {"status": "unknown", "details": None}
        }

        # Check MongoDB
        try:
            try:
                mongo = _get_bound_mongo_client()
            except RuntimeError:
                mongo = None

            if mongo:
                result = await mongo.admin.command('ping')
                health_status["mongodb"] = {
                    "status": "healthy",
                    "details": {"ping": result, "database": settings.MONGO_DB}
                }
                self._mongo_healthy = True
            else:
                health_status["mongodb"]["status"] = "disconnected"
        except Exception as e:
            health_status["mongodb"] = {
                "status": "unhealthy",
                "details": {"error": str(e)}
            }
            self._mongo_healthy = False

        # Check Redis
        try:
            if self.redis_client:
                result = await self.redis_client.ping()
                health_status["redis"] = {
                    "status": "healthy",
                    "details": {"ping": result}
                }
                self._redis_healthy = True
            else:
                health_status["redis"]["status"] = "disconnected"
        except Exception as e:
            health_status["redis"] = {
                "status": "unhealthy",
                "details": {"error": str(e)}
            }
            self._redis_healthy = False

        return health_status

    @property
    def is_healthy(self) -> bool:
        """Check whether all database connections are healthy"""
        return self._mongo_healthy and self._redis_healthy


# Global database manager instance
db_manager = DatabaseManager()


def _create_async_mongo_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        settings.MONGO_URI,
        maxPoolSize=settings.MONGO_MAX_CONNECTIONS,
        minPoolSize=settings.MONGO_MIN_CONNECTIONS,
        maxIdleTimeMS=30000,
        serverSelectionTimeoutMS=settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
        connectTimeoutMS=settings.MONGO_CONNECT_TIMEOUT_MS,
        socketTimeoutMS=settings.MONGO_SOCKET_TIMEOUT_MS,
    )


def _is_pymongo_client_closed(client: Optional[MongoClient]) -> bool:
    if client is None:
        return True

    topology = getattr(client, "_topology", None)
    if topology is None:
        return False

    return bool(getattr(topology, "_closed", False))


def _is_async_mongo_client_closed(client: Optional[AsyncIOMotorClient]) -> bool:
    if client is None:
        return True

    delegate = getattr(client, "delegate", None)
    return _is_pymongo_client_closed(delegate)


def _set_active_mongo_binding(
    loop: Optional[asyncio.AbstractEventLoop],
    client: AsyncIOMotorClient,
    db: AsyncIOMotorDatabase,
) -> None:
    global mongo_client, mongo_db, _mongo_runtime_loop

    mongo_client = client
    mongo_db = db
    _mongo_runtime_loop = loop
    db_manager.mongo_client = client
    db_manager.mongo_db = db


def _store_mongo_loop_binding(
    loop: asyncio.AbstractEventLoop,
    client: AsyncIOMotorClient,
    db: AsyncIOMotorDatabase,
) -> None:
    _mongo_loop_bindings[id(loop)] = (loop, client, db)
    _set_active_mongo_binding(loop, client, db)


def _prune_closed_mongo_loop_bindings() -> None:
    stale_loop_ids = []

    for loop_id, (loop, client, _) in list(_mongo_loop_bindings.items()):
        if loop.is_closed() or _is_async_mongo_client_closed(client):
            stale_loop_ids.append(loop_id)

    for loop_id in stale_loop_ids:
        _, client, _ = _mongo_loop_bindings.pop(loop_id)
        if client is not None and not _is_async_mongo_client_closed(client):
            try:
                client.close()
            except Exception as exc:
                logger.warning(f"⚠️ Failed to close dead MongoDB client (ignored): {exc}")


class _LoopSafeMongoCollectionProxy:
    """Collection proxy: Even if the object is cached, it is always forwarded to the collection bound by the current loop."""

    def __init__(self, resolver: Callable[[], AsyncIOMotorCollection]):
        self._resolver = resolver

    def _target(self) -> AsyncIOMotorCollection:
        return self._resolver()

    def __getattr__(self, name: str):
        return getattr(self._target(), name)


class _LoopSafeMongoDatabaseProxy:
    """Database proxy: Avoid callers caching old loop bound AsyncIOMotorDatabase."""

    def __init__(self, resolver: Optional[Callable[[], AsyncIOMotorDatabase]] = None):
        self._resolver = resolver or _get_bound_mongo_db

    def _target(self) -> AsyncIOMotorDatabase:
        return self._resolver()

    def __getitem__(self, name: str):
        return _LoopSafeMongoCollectionProxy(lambda: _get_bound_mongo_db()[name])

    def __getattr__(self, name: str):
        target = getattr(self._target(), name)
        if isinstance(target, AsyncIOMotorCollection):
            return _LoopSafeMongoCollectionProxy(lambda: getattr(_get_bound_mongo_db(), name))
        return target


class _LoopSafeMongoClientProxy:
    """Client Proxy: Avoid caching old loop bound AsyncIOMotorClient."""

    def _target(self) -> AsyncIOMotorClient:
        return _get_bound_mongo_client()

    def __getattr__(self, name: str):
        return getattr(self._target(), name)

    def __getitem__(self, name: str):
        return _LoopSafeMongoDatabaseProxy(lambda name=name: _get_bound_mongo_client()[name])


class _LoopSafeRedisClientProxy:
    """Redis Proxy: Even if the object is cached, it is always forwarded to the Redis client bound to the current loop."""

    def _target(self) -> Redis:
        return _get_bound_redis_client()

    def __getattr__(self, name: str):
        return getattr(self._target(), name)


async def init_database():
    """Initialize database connection"""
    global mongo_client, mongo_db, redis_client, redis_pool, _mongo_runtime_loop, _redis_runtime_loop

    current_loop: Optional[asyncio.AbstractEventLoop]
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    mongo_binding = _get_current_mongo_loop_binding() if current_loop is not None else None

    mongo_ready = mongo_binding is not None and db_manager._mongo_healthy
    redis_ready = redis_client is not None and redis_pool is not None and db_manager._redis_healthy

    if mongo_ready and redis_ready:
        logger.debug("The database connection has been initialized and healthy, skip repeated initialization")
        return

    try:
        if not mongo_ready:
            # initialization MongoDB
            await db_manager.init_mongodb()
            if current_loop is not None and db_manager.mongo_client is not None and db_manager.mongo_db is not None:
                _store_mongo_loop_binding(current_loop, db_manager.mongo_client, db_manager.mongo_db)
            else:
                mongo_client = db_manager.mongo_client
                mongo_db = db_manager.mongo_db
                _mongo_runtime_loop = current_loop

        if not redis_ready:
            # initialization Redis
            await db_manager.init_redis()
            redis_client = db_manager.redis_client
            redis_pool = db_manager.redis_pool
            _redis_runtime_loop = asyncio.get_running_loop()

        logger.info("🎉 All database connections are initialized")

        # 🔥 Initialize database views and indexes
        await init_database_views_and_indexes()

    except Exception as e:
        logger.error(f"💥 Database initialization failed: {e}")
        raise


async def init_redis_binding() -> None:
    """Only Redis bindings are initialized for reuse by compatibility layers and independent components."""
    global redis_client, redis_pool, _redis_runtime_loop

    if redis_client is not None and redis_pool is not None:
        try:
            _ensure_async_redis_binding()
        except RuntimeError:
            pass
        return

    await db_manager.init_redis()
    redis_client = db_manager.redis_client
    redis_pool = db_manager.redis_pool

    try:
        _redis_runtime_loop = asyncio.get_running_loop()
    except RuntimeError:
        _redis_runtime_loop = None


async def init_database_views_and_indexes():
    """Initialize database views and indexes"""
    try:
        db = get_mongo_db()

        # 1. Create a stock screener view
        await create_stock_screening_view(db)

        # 2. Create necessary indexes
        await create_database_indexes(db)

        # 3. Create agent execution trace collection index (P1 machine-readable execution trace)
        # Partial import avoids circular dependencies; service initialization failure does not affect application startup
        try:
            from app.pro.services.execution_trace_service import execution_trace_service
            await execution_trace_service.create_indexes()
        except Exception as trace_exc:
            logger.warning(f"⚠️ Execution track index initialization failed (does not affect application startup): {trace_exc}")

        # 4. Create agent assertion collection index (P2 executable assertion)
        try:
            from app.pro.services.agent_assertion_service import agent_assertion_service
            await agent_assertion_service.create_indexes()
        except Exception as assertion_exc:
            logger.warning(f"⚠️ Assert that index initialization failed (does not affect application startup): {assertion_exc}")

        # 5. Create assistant quality buried point collection index (A11 stage 4 S9)
        try:
            from core.assistant import quality_metrics
            await quality_metrics.create_indexes(db)
        except Exception as metrics_exc:
            logger.warning(f"⚠️ Quality index index initialization failed (does not affect application startup): {metrics_exc}")

        logger.info("✅ Database view and index initialization completed")

    except Exception as e:
        logger.warning(f"⚠️ Database view and index initialization failed: {e}")
        # Do not throw an exception and allow the application to continue launching


async def create_stock_screening_view(db):
    """Create a stock screener view"""
    try:
        # Check if the view already exists
        collections = await db.list_collection_names()
        if "stock_screening_view" in collections:
            logger.info("📋 View stock_screening_view already exists, skip creation")
            return

        # Create a view: Relate stock_basic_info, market_quotes, and stock_financial_data
        pipeline = [
            # Step 1: Correlate real-time market data (market_quotes)
            {
                "$lookup": {
                    "from": "market_quotes",
                    "localField": "code",
                    "foreignField": "code",
                    "as": "quote_data"
                }
            },
            # Step 2: Expand the quote_data array
            {
                "$unwind": {
                    "path": "$quote_data",
                    "preserveNullAndEmptyArrays": True
                }
            },
            # Step Three: Link Financial Data (stock_financial_data)
            {
                "$lookup": {
                    "from": "stock_financial_data",
                    "let": {"stock_code": "$code", "stock_source": "$source"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {"$eq": ["$code", "$$stock_code"]},
                                        {"$eq": ["$data_source", "$$stock_source"]}
                                    ]
                                }
                            }
                        },
                        {"$sort": {"report_period": -1}},
                        {"$limit": 1}
                    ],
                    "as": "financial_data"
                }
            },
            # Step 4: Expand the financial_data array
            {
                "$unwind": {
                    "path": "$financial_data",
                    "preserveNullAndEmptyArrays": True
                }
            },
            # Step 5: Reorganize the field structure
            {
                "$project": {
                    # Basic information fields
                    "code": 1,
                    "name": 1,
                    "industry": 1,
                    "area": 1,
                    "market": 1,
                    "list_date": 1,
                    "source": 1,
                    # Market capitalization information
                    "total_mv": 1,
                    "circ_mv": 1,
                    # Valuation indicators
                    "pe": 1,
                    "pb": 1,
                    "pe_ttm": 1,
                    "pb_mrq": 1,
                    # financial indicators
                    "roe": "$financial_data.roe",
                    "roa": "$financial_data.roa",
                    "netprofit_margin": "$financial_data.netprofit_margin",
                    "gross_margin": "$financial_data.gross_margin",
                    "report_period": "$financial_data.report_period",
                    # trading indicators
                    "turnover_rate": 1,
                    "volume_ratio": 1,
                    # Real-time market data
                    "close": "$quote_data.close",
                    "open": "$quote_data.open",
                    "high": "$quote_data.high",
                    "low": "$quote_data.low",
                    "pre_close": "$quote_data.pre_close",
                    "pct_chg": "$quote_data.pct_chg",
                    "amount": "$quote_data.amount",
                    "volume": "$quote_data.volume",
                    "trade_date": "$quote_data.trade_date",
                    # Timestamp
                    "updated_at": 1,
                    "quote_updated_at": "$quote_data.updated_at",
                    "financial_updated_at": "$financial_data.updated_at"
                }
            }
        ]

        # Create view
        await db.command({
            "create": "stock_screening_view",
            "viewOn": "stock_basic_info",
            "pipeline": pipeline
        })

        logger.info("✅ View stock_screening_view created successfully")

    except Exception as e:
        logger.warning(f"⚠️ Failed to create view: {e}")


async def create_database_indexes(db):
    """Create database index"""
    try:
        # stock_basic_info Index of
        basic_info = db["stock_basic_info"]
        await basic_info.create_index([("code", 1), ("source", 1)], unique=True)
        await basic_info.create_index([("source", 1)])  # 🔥 Separate source index to optimize queries filtered by data source
        await basic_info.create_index([("source", 1), ("total_mv", -1)])  # 🔥 Composite index: Optimize filtering by data source+Market value sorting query (common scenario for view query)
        await basic_info.create_index([("industry", 1)])
        await basic_info.create_index([("total_mv", -1)])
        await basic_info.create_index([("pe", 1)])
        await basic_info.create_index([("pb", 1)])

        # market_quotes Index of
        market_quotes = db["market_quotes"]
        await market_quotes.create_index([("code", 1)], unique=True)
        await market_quotes.create_index([("pct_chg", -1)])
        await market_quotes.create_index([("amount", -1)])
        await market_quotes.create_index([("updated_at", -1)])

        industry_mapping = db["stock_industry_mappings"]
        await industry_mapping.create_index([("code", 1)], unique=True)
        await industry_mapping.create_index([("provider", 1), ("updated_at", -1)])

        logger.info("✅ Database index creation completed")

    except Exception as e:
        logger.warning(f"⚠️ Index creation failed: {e}")


async def close_database():
    """Close database connection"""
    global mongo_client, mongo_db, redis_client, redis_pool, _mongo_runtime_loop, _redis_runtime_loop

    await db_manager.close_connections()

    # Clear global variables
    mongo_client = None
    mongo_db = None
    redis_client = None
    redis_pool = None
    _mongo_runtime_loop = None
    _redis_runtime_loop = None


async def close_redis_binding() -> None:
    """Only the Redis binding is turned off for reuse by the compatibility layer and independent components."""
    global redis_client, redis_pool, _redis_runtime_loop

    if db_manager.redis_client:
        try:
            await db_manager.redis_client.close()
        except Exception as exc:
            logger.error(f"❌ Error closing Redis connection: {exc}")

    if db_manager.redis_pool:
        try:
            await db_manager.redis_pool.disconnect()
        except Exception as exc:
            logger.error(f"❌ Error closing Redis connection pool: {exc}")

    db_manager.redis_client = None
    db_manager.redis_pool = None
    db_manager.redis_url_in_use = None
    db_manager._redis_healthy = False
    redis_client = None
    redis_pool = None
    _redis_runtime_loop = None


def _recreate_async_mongo_binding() -> None:
    """Rebuild asynchronous MongoDB bindings based on the current event loop to avoid reusing old Motor clients across loops."""
    current_loop = asyncio.get_running_loop()
    existing = _get_current_mongo_loop_binding()
    if existing is not None:
        return

    client = _create_async_mongo_client()
    db = client[settings.MONGO_DB]
    _store_mongo_loop_binding(current_loop, client, db)
    db_manager._mongo_healthy = True


def _recreate_async_redis_binding() -> None:
    """Rebuild asynchronous Redis bindings according to the current event loop to avoid reusing old clients across loops."""
    global redis_client, redis_pool, _redis_runtime_loop

    current_loop = asyncio.get_running_loop()
    redis_url = db_manager.redis_url_in_use or settings.REDIS_URL

    redis_pool = ConnectionPool.from_url(
        redis_url,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        retry_on_timeout=settings.REDIS_RETRY_ON_TIMEOUT,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=10,
    )
    redis_client = Redis(connection_pool=redis_pool)
    _redis_runtime_loop = current_loop
    db_manager.redis_pool = redis_pool
    db_manager.redis_client = redis_client


def _ensure_async_redis_binding() -> None:
    """Make sure the returned asynchronous Redis connection is bound to the currently running event loop."""
    global _redis_runtime_loop

    if redis_client is None or redis_pool is None:
        raise RuntimeError("Redis Client not initialized")

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    if _redis_runtime_loop is None:
        _redis_runtime_loop = current_loop
        return

    if _redis_runtime_loop.is_closed() or _redis_runtime_loop is not current_loop:
        logger.warning("⚠️ Detected that the event loop of the asynchronous Redis client binding has changed and the connection is being re-established")
        _recreate_async_redis_binding()


def _ensure_async_mongo_binding() -> None:
    """Ensures that the returned asynchronous MongoDB connection is bound to the currently running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return

    binding = _get_current_mongo_loop_binding()
    if binding is not None:
        return

    if mongo_client is None or mongo_db is None:
        raise RuntimeError("MongoDB Client not initialized")

    if _is_async_mongo_client_closed(mongo_client):
        logger.warning("⚠️ Detected that the asynchronous MongoDB client has closed and the connection is being re-established for the current event loop")
    else:
        logger.warning("⚠️ Detected that the event loop bound to the asynchronous MongoDB client has changed, creating a separate connection for the current event loop")

    _recreate_async_mongo_binding()


def _get_bound_mongo_client() -> AsyncIOMotorClient:
    _ensure_async_mongo_binding()
    assert mongo_client is not None
    return mongo_client


def _get_bound_mongo_db() -> AsyncIOMotorDatabase:
    _ensure_async_mongo_binding()
    assert mongo_db is not None
    return mongo_db


def _get_bound_redis_client() -> Redis:
    _ensure_async_redis_binding()
    assert redis_client is not None
    return redis_client


def get_mongo_client() -> AsyncIOMotorClient:
    """Get the MongoDB client"""
    global _mongo_client_proxy
    if _mongo_client_proxy is None:
        _mongo_client_proxy = _LoopSafeMongoClientProxy()
    return _mongo_client_proxy


def get_mongo_db() -> AsyncIOMotorDatabase:
    """Get a MongoDB database instance"""
    global _mongo_db_proxy
    if _mongo_db_proxy is None:
        _mongo_db_proxy = _LoopSafeMongoDatabaseProxy()
    return _mongo_db_proxy


def bind_loop_safe_mongo_db(target: object, attr_name: str = "db") -> AsyncIOMotorDatabase:
    """Bind loop-safe MongoDB proxy to object properties instead of manually rebuilding AsyncIOMotorClient."""
    db = get_mongo_db()
    setattr(target, attr_name, db)
    return db


def create_isolated_async_mongo_binding() -> Tuple[AsyncIOMotorClient, AsyncIOMotorDatabase]:
    """Creates an asynchronous MongoDB connection independent of the current caller, suitable for thread pools or temporary isolation tasks."""
    client = _create_async_mongo_client()
    return client, client[settings.MONGO_DB]


def _get_current_mongo_loop_binding() -> Optional[Tuple[asyncio.AbstractEventLoop, AsyncIOMotorClient, AsyncIOMotorDatabase]]:
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        return None

    _prune_closed_mongo_loop_bindings()

    binding = _mongo_loop_bindings.get(id(current_loop))
    if binding is not None:
        _, client, db = binding
        _set_active_mongo_binding(current_loop, client, db)
        return binding

    if (
        mongo_client is not None
        and mongo_db is not None
        and not _is_async_mongo_client_closed(mongo_client)
        and (_mongo_runtime_loop is None or _mongo_runtime_loop is current_loop)
    ):
        _store_mongo_loop_binding(current_loop, mongo_client, mongo_db)
        return _mongo_loop_bindings.get(id(current_loop))

    return None


async def _close_all_async_mongo_bindings(log_message: bool = True) -> None:
    global mongo_client, mongo_db, _mongo_runtime_loop

    if log_message:
        logger.info("🔄 Closing all MongoDB event loop bindings...")

    _prune_closed_mongo_loop_bindings()
    closed_client_ids = set()

    for _, client, _ in list(_mongo_loop_bindings.values()):
        if client is None:
            continue

        client_id = id(client)
        if client_id in closed_client_ids or _is_async_mongo_client_closed(client):
            closed_client_ids.add(client_id)
            continue

        try:
            client.close()
        except Exception as exc:
            logger.warning(f"⚠️ Failed to close MongoDB client (ignored): {exc}")

        closed_client_ids.add(client_id)

    _mongo_loop_bindings.clear()
    mongo_client = None
    mongo_db = None
    _mongo_runtime_loop = None
    db_manager.mongo_client = None
    db_manager.mongo_db = None
    db_manager._mongo_healthy = False


def get_mongo_db_sync() -> Database:
    """
    Get a synchronized version of a MongoDB database instance
    For use in non-asynchronous contexts (such as ordinary function calls)
    """
    global _sync_mongo_client, _sync_mongo_db

    if _sync_mongo_db is not None:
        return _sync_mongo_db

    # Create a synchronous MongoDB client
    if _sync_mongo_client is None:
        _sync_mongo_client = MongoClient(
            settings.MONGO_URI,
            maxPoolSize=settings.MONGO_MAX_CONNECTIONS,
            minPoolSize=settings.MONGO_MIN_CONNECTIONS,
            maxIdleTimeMS=30000,
            serverSelectionTimeoutMS=5000
        )

    _sync_mongo_db = _sync_mongo_client[settings.MONGO_DB]
    return _sync_mongo_db


def get_redis_client() -> Redis:
    """Get Redis client (asynchronous)"""
    global _redis_client_proxy
    if _redis_client_proxy is None:
        _redis_client_proxy = _LoopSafeRedisClientProxy()
    return _redis_client_proxy


# Synchronous Redis client (for synchronization context)
_redis_sync_client: Optional[redis_sync.Redis] = None


def get_redis_sync_client() -> redis_sync.Redis:
    """
    Get sync Redis client (for sync context)
    
    Use the system s Redis configuration, but create a synchronous connection to avoid event loop issues
    Use the system s REDIS_URL configuration uniformly
    """
    global _redis_sync_client
    
    if _redis_sync_client is None:
        if redis_sync is None:
            raise RuntimeError("redis The module is not installed and the synchronous Redis client cannot be created.")
        
        redis_url = settings.REDIS_URL
        
        try:
            # Use redis.from_url to automatically parse URLs, using system configuration
            _redis_sync_client = redis_sync.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=10
            )
            # test connection
            _redis_sync_client.ping()
            logger.debug("✅ Synchronous Redis client connection successful (using system configuration)")
        except Exception as e:
            if settings.REDIS_PASSWORD and _should_retry_redis_without_password(e):
                try:
                    fallback_url = _build_redis_url_without_password()
                    logger.warning(
                        "⚠️ The synchronization Redis client detects that the local instance does not have a password configured,"
                        "Will automatically fall back to passwordless connection."
                    )
                    _redis_sync_client = redis_sync.from_url(
                        fallback_url,
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_timeout=10
                    )
                    _redis_sync_client.ping()
                    logger.debug("✅ Synchronous Redis client connection successful (no password fallback)")
                except Exception as fallback_error:
                    logger.warning(f"⚠️ Synchronous Redis client initialization failed: {fallback_error}", exc_info=True)
                    raise RuntimeError(f"Synchronous Redis client initialization failed: {fallback_error}")
            else:
                logger.warning(f"⚠️ Synchronous Redis client initialization failed: {e}", exc_info=True)
                raise RuntimeError(f"Synchronous Redis client initialization failed: {e}")
    
    return _redis_sync_client


async def get_database_health() -> dict:
    """Get database health status"""
    return await db_manager.health_check()


# Compatible gender names
init_db = init_database
close_db = close_database


def get_database():
    """Get database instance"""
    return get_mongo_db()
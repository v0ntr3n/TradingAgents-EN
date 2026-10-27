"""
mem0 unified memory layer — Configuration loading

Directly reuse the existing LLM/Embedding configuration of the system (database system_configs + llm_providers) , 
No additional independent configuration is maintained.

Configure priority:MongoDB system_configs > .env > Code defaults
"""

import logging
import os
import hashlib
import re
import inspect
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_MEM0_COLLECTION_PREFIX = "mem0_memories"

_MEM0_OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "dashscope",
    "siliconflow",
    "302ai",
    "openrouter",
    "localai",
    "lmstudio",
}

_MEM0_DIRECT_PROVIDER_MAP = {
    "google": "gemini",
    "gemini": "gemini",
    "ollama": "ollama",
}

_DEFAULT_EMBEDDING_MODELS = {
    "dashscope": "text-embedding-v3",
    "openai": "text-embedding-3-small",
    "google": "text-embedding-004",
    "gemini": "text-embedding-004",
    "ollama": "nomic-embed-text",
    "zhipu": "embedding-2",
    "siliconflow": "BAAI/bge-large-zh-v1.5",
    "302ai": "text-embedding-3-small",
    "openrouter": "text-embedding-3-small",
    "localai": "text-embedding-3-small",
    "lmstudio": "text-embedding-3-small",
}


def _sanitize_collection_token(value: str, max_length: int = 24) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    if not normalized:
        return "default"
    return normalized[:max_length]


def _build_mem0_collection_name(embedder: Optional[Dict[str, Any]]) -> str:
    embedder = embedder or {}
    embedder_cfg = embedder.get("config") or {}

    provider = _sanitize_collection_token(embedder.get("provider") or "default", max_length=16)
    model = _sanitize_collection_token(embedder_cfg.get("model") or "default", max_length=24)
    dims = int(embedder_cfg.get("embedding_dims") or 0)
    fingerprint_source = f"{provider}:{embedder_cfg.get('model') or ''}:{dims}"
    fingerprint = hashlib.sha1(fingerprint_source.encode("utf-8")).hexdigest()[:8]
    return f"{_MEM0_COLLECTION_PREFIX}_{provider}_{model}_{dims or '0'}_{fingerprint}"


def _backup_collection_payload(client, collection_name: str, base_path: str) -> Optional[str]:
    """[Deprecated] MongoDB Qdrant backup logic is no longer required after migration.

    This function is retained for future use when falling back to Qdrant.
    """
    import json
    from datetime import datetime

    backup_dir = os.path.join(base_path, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"{collection_name}_{timestamp}.json")

    points = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=collection_name,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not batch:
            break
        for p in batch:
            points.append({"id": str(p.id), "payload": p.payload})
        if offset is None:
            break

    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(
            {"collection": collection_name, "count": len(points), "points": points},
            f, ensure_ascii=False, indent=2,
        )
    return backup_file


def _ensure_qdrant_collection_dimension(vector_store_cfg: Dict[str, Any], expected_dims: int) -> None:
    """
    [Deprecated] MongoDB This function is no longer called after migration.

    Reserved for future fallback to Qdrant.
    """
    from qdrant_client import QdrantClient

    path = vector_store_cfg.get("path")
    collection_name = vector_store_cfg.get("collection_name")
    if not path or not collection_name:
        return

    try:
        client = QdrantClient(path=path)
        try:
            collections = client.get_collections().collections

            # Question 5: Scan the legacy old named collection and prompt the user to migrate
            for col in collections:
                name = col.name
                if name == collection_name or not name.startswith(_MEM0_COLLECTION_PREFIX):
                    continue
                logger.info(
                    "mem0 config: History detected collection '%s' (currently in use '%s') . "
                    "To migrate data, please execute:python app/scripts/migrate_mem0_collection.py --source %s",
                    name, collection_name, name,
                )

            # Check the current collection dimensions
            if not any(col.name == collection_name for col in collections):
                return  # collection does not exist, mem0 will be created automatically

            info = client.get_collection(collection_name)
            actual_dims = int(info.config.params.vectors.size)
            if actual_dims == expected_dims:
                return  # Dimension matching, no processing required

            # Issue 3: Dimension mismatch → Back up the payload first, then delete it
            logger.warning(
                "mem0 config: Qdrant collection %s Dimensions do not match (actual %d, Expectation %d), "
                "Back up the payload first, then delete the old collection and rebuild it",
                collection_name, actual_dims, expected_dims,
            )
            backup_path = _backup_collection_payload(client, collection_name, path)
            if backup_path:
                logger.warning(
                    "mem0 config: Old collection payload has been backed up to %s",
                    backup_path,
                )
            else:
                logger.error(
                    "mem0 config: Backup failed, refusing to delete collection %s."
                    "Please restart the service after manual migration.",
                    collection_name,
                )
                return  # If the backup fails, it will not be deleted.

            client.delete_collection(collection_name)
            # mem0 A new collection will be automatically created according to expected_dims during initialization
        finally:
            client.close()
    except Exception as e:
        # File lock conflict (AlreadyLocked) indicates that mem0 has been initialized and is using this collection.
        # The dimensions must match (otherwise a write error would have been reported) and can be safely ignored.
        logger.debug("mem0 config: Error checking/rebuilding Qdrant collection (ignored): %s", e)


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or "").strip() or default


def _get_mongo_connection_info() -> Tuple[str, str]:
    """Get the MongoDB connection URI and database name (for mem0 vector storage).

    Read from app.core.config.settings first and fall back to environment variables.
    """
    try:
        from app.core.config import settings
        return settings.MONGO_URI, settings.MONGO_DB
    except Exception:
        # Fallback: Build from environment variables
        host = _env("MONGODB_HOST", "localhost")
        port = _env("MONGODB_PORT", "27017")
        db_name = _env("MONGODB_DATABASE", "tradingagents")
        username = _env("MONGODB_USERNAME", "")
        password = _env("MONGODB_PASSWORD", "")
        auth_source = _env("MONGODB_AUTH_SOURCE", "admin")
        # It also supports directly passing in the complete connection string.
        conn_str = _env("MONGODB_CONNECTION_STRING", "") or _env("MONGODB_URL", "")
        if conn_str:
            return conn_str, db_name
        if username and password:
            return (
                f"mongodb://{username}:{password}@{host}:{port}/{db_name}?authSource={auth_source}",
                db_name,
            )
        return f"mongodb://{host}:{port}/{db_name}", db_name


def _get_sync_db():
    """Get a synchronous MongoDB connection"""
    try:
        from app.core.database import get_mongo_db_sync
        return get_mongo_db_sync()
    except Exception:
        return None


def _read_active_system_config(db=None) -> Dict[str, Any]:
    """Read the currently effective system_configs document."""
    sync_db = None
    try:
        if db is not None:
            from pymongo.database import Database as SyncDatabase

            if isinstance(db, SyncDatabase):
                sync_db = db
            else:
                sync_db = _get_sync_db()
        else:
            sync_db = _get_sync_db()

        if sync_db is None:
            return {}

        doc = sync_db.system_configs.find_one(
            {"is_active": True}, sort=[("version", -1)]
        )
        if inspect.isawaitable(doc):
            logger.warning("mem0 config: Asynchronous database agent detected, automatic fallback to synchronous configuration reading")
            fallback_db = _get_sync_db()
            if fallback_db is None:
                return {}
            doc = fallback_db.system_configs.find_one(
                {"is_active": True}, sort=[("version", -1)]
            )
        return doc or {}
    except Exception as e:
        logger.debug("mem0 config: Unable to read configuration from database: %s", e)
        return {}


def _read_system_settings(db=None) -> Tuple[dict, list]:
    """Read system_settings and llm_configs"""
    doc = _read_active_system_config(db)
    return doc.get("system_settings") or {}, doc.get("llm_configs") or []


def _get_embedding_dimension(model_name: str) -> int:
    try:
        from core.llm.embedding_manager import EMBEDDING_DIMENSIONS

        model_key = (model_name or "").strip()
        dims = EMBEDDING_DIMENSIONS.get(model_key)
        if dims is not None:
            return int(dims)
        logger.warning(
            "mem0 config: Embedding model '%s' Not in a dimension table, defaults to 1024 dimensions."
            "If the actual dimensions do not match (write to the Times ValueError: shapes not aligned) , "
            "Please supplement the dimensions of the model in EMBEDDING_DIMENSIONS in core/llm/embedding_manager.py.",
            model_key,
        )
        return int(EMBEDDING_DIMENSIONS.get("default", 1024))
    except Exception:
        return 1024


def _normalize_openai_base_url(base_url: str) -> str:
    normalized = (base_url or "").strip()
    if not normalized:
        return ""
    if normalized.rstrip("/").endswith("/v1"):
        return normalized.rstrip("/")
    return f"{normalized.rstrip('/')}/v1"


def _parse_default_embedding_model(db_settings: dict) -> Tuple[str, str]:
    default_emb = str(db_settings.get("default_embedding_model") or "").strip()
    if not default_emb or ":" not in default_emb:
        return "", ""
    provider_name, model_name = default_emb.split(":", 1)
    return provider_name.strip().lower(), model_name.strip()


def _get_embedding_provider_candidates(sync_db) -> list:
    try:
        cursor = sync_db.llm_providers.find(
            {
                "supported_features": "embedding",  # 🔥 direct match, avoid $in Returns empty results on some MongoDB versions
                "is_active": True,
            }
        ).sort("created_at", 1)
        return list(cursor)
    except Exception as e:
        logger.debug("mem0 config: Unable to read embedding provider list: %s", e)
        return []


def _resolve_mem0_provider(provider_name: str) -> Optional[str]:
    normalized = (provider_name or "").strip().lower()
    if normalized in _MEM0_OPENAI_COMPATIBLE_PROVIDERS:
        return "openai"
    return _MEM0_DIRECT_PROVIDER_MAP.get(normalized)


def _build_embedder_config_from_provider_doc(provider_doc: dict, model_name: str) -> dict:
    provider_name = str(provider_doc.get("name") or "").strip().lower()
    mem0_provider = _resolve_mem0_provider(provider_name)
    if not mem0_provider:
        return {}

    selected_model = (model_name or "").strip() or str(provider_doc.get("embedding_model") or "").strip()
    if not selected_model:
        selected_model = _DEFAULT_EMBEDDING_MODELS.get(provider_name, _DEFAULT_EMBEDDING_MODELS.get(mem0_provider, ""))
    if not selected_model:
        return {}

    config: Dict[str, Any] = {
        "model": selected_model,
        "embedding_dims": _get_embedding_dimension(selected_model),
    }

    api_key = str(provider_doc.get("api_key") or "").strip()
    base_url = str(provider_doc.get("default_base_url") or provider_doc.get("base_url") or "").strip()

    if mem0_provider == "openai":
        if not api_key:
            return {}
        config["api_key"] = api_key
        config["openai_base_url"] = _normalize_openai_base_url(base_url)
    elif mem0_provider == "gemini":
        if not api_key:
            return {}
        config["api_key"] = api_key
        if not selected_model.startswith("models/"):
            config["model"] = f"models/{selected_model}"
    elif mem0_provider == "ollama":
        config["ollama_base_url"] = base_url or "http://localhost:11434"

    return {
        "provider": mem0_provider,
        "config": config,
    }


def _build_mem0_llm_config_from_unified_config(llm_config: Any) -> dict:
    """Convert unified LLMConfig to the LLM configuration required for mem0."""
    provider_name = str(getattr(llm_config, "provider", "") or "").strip().lower()
    model_name = str(getattr(llm_config, "model", "") or "").strip() or "deepseek-chat"
    api_key = str(getattr(llm_config, "api_key", "") or "").strip()
    base_url = str(getattr(llm_config, "base_url", "") or "").strip()

    mem0_provider = "openai"
    if provider_name in {"google", "gemini"}:
        mem0_provider = "gemini"
    elif provider_name == "ollama":
        mem0_provider = "ollama"

    config: Dict[str, Any] = {
        "model": model_name,
        "temperature": float(getattr(llm_config, "temperature", 0.1) or 0.1),
        "max_tokens": int(getattr(llm_config, "max_tokens", 2000) or 2000),
    }

    if mem0_provider == "openai":
        config["api_key"] = api_key
        if base_url:
            config["openai_base_url"] = _normalize_openai_base_url(base_url)
    elif mem0_provider == "gemini":
        config["api_key"] = api_key
        if not model_name.startswith("models/"):
            config["model"] = f"models/{model_name}"
    else:
        config["ollama_base_url"] = base_url or "http://localhost:11434"

    return {
        "provider": mem0_provider,
        "config": config,
    }


def _resolve_embedding_from_db(db_settings: dict) -> dict:
    """Parse embedding configuration from database default_embedding_model"""
    preferred_provider_name, preferred_model_name = _parse_default_embedding_model(db_settings)

    sync_db = _get_sync_db()
    if sync_db is None:
        return {}

    try:
        provider_docs = _get_embedding_provider_candidates(sync_db)
        if not provider_docs:
            return {}

        preferred_doc = None
        if preferred_provider_name:
            for provider_doc in provider_docs:
                provider_name = str(provider_doc.get("name") or "").strip().lower()
                if provider_name == preferred_provider_name:
                    preferred_doc = provider_doc
                    break

        if preferred_doc:
            embedder = _build_embedder_config_from_provider_doc(preferred_doc, preferred_model_name)
            if embedder:
                return embedder
            logger.warning(
                "mem0 config: Default Embedding model %s:%s Incompatible with mem0 or missing credentials, try fallback to other available provider",
                preferred_provider_name,
                preferred_model_name,
            )

        for provider_doc in provider_docs:
            provider_name = str(provider_doc.get("name") or "").strip().lower()
            if preferred_provider_name and provider_name == preferred_provider_name:
                continue
            embedder = _build_embedder_config_from_provider_doc(provider_doc, "")
            if embedder:
                logger.info("mem0 config: Embedding provider Fallback to %s", provider_name)
                return embedder

        return {}
    except Exception as e:
        logger.debug("mem0 config: embedding Parsing failed: %s", e)
        return {}


def build_mem0_config(db=None) -> Dict[str, Any]:
    """
    build mem0 Memory.from_config() The complete config dict required.

    LLM / Embedding Configure directly from database system_configs + llm_providers read,
    Use the same models and credentials as the analysis process.
    """
    # 🔧 JD Cloud Mode: Use environment variable configuration and skip database query
    from app.core.jdyun import (
        is_jdyun_mode, get_jdyun_api_base, get_jdyun_api_key,
        get_jdyun_embedding_model, get_jdyun_default_model,
        JDYUN_EMBEDDING_DIMS, JDYUN_PROVIDER_NAME,
    )
    if is_jdyun_mode():
        jdyun_api_base = get_jdyun_api_base()
        jdyun_api_key = get_jdyun_api_key()
        jdyun_embedding_model = get_jdyun_embedding_model()
        jdyun_chat_model = get_jdyun_default_model()

        logger.info(
            "mem0 config: Jingdong cloud model — embedding=%s, chat=%s, api_base=%s",
            jdyun_embedding_model, jdyun_chat_model, jdyun_api_base,
        )

        # Embedder: Use JD Cloud OpenAI compatible interface
        embedder = {
            "provider": "openai",
            "config": {
                "model": jdyun_embedding_model,
                "api_key": jdyun_api_key,
                "openai_base_url": _normalize_openai_base_url(jdyun_api_base),
                "embedding_dims": JDYUN_EMBEDDING_DIMS,
            },
        }
        collection_name = _build_mem0_collection_name(embedder)

        # Vector Store: MongoDB (Unified storage with business data, client cosine similarity)
        mongo_uri, mongo_db_name = _get_mongo_connection_info()
        vector_store = {
            "provider": "mongodb",
            "config": {
                "mongo_uri": mongo_uri,
                "db_name": mongo_db_name,
                "collection_name": collection_name,
                "embedding_model_dims": JDYUN_EMBEDDING_DIMS,
            },
        }

        # LLM: Use JD Cloud OpenAI compatible interface
        llm = {
            "provider": "openai",
            "config": {
                "api_key": jdyun_api_key,
                "model": jdyun_chat_model,
                "openai_base_url": _normalize_openai_base_url(jdyun_api_base),
                "temperature": 0.1,
                "max_tokens": 2000,
            },
        }

        from .prompts import FINANCIAL_FACT_EXTRACTION_PROMPT

        return {
            "vector_store": vector_store,
            "llm": llm,
            "embedder": embedder,
            "custom_prompt": FINANCIAL_FACT_EXTRACTION_PROMPT,
            "version": "v1.1",
        }

    # ===== Non-JD Cloud Model: Original Logic =====
    config_doc = _read_active_system_config(db)
    db_settings = config_doc.get("system_settings") or {}
    llm_configs = config_doc.get("llm_configs") or []

    # --- Embedder: Reuse system default_embedding_model ---
    embedder = _resolve_embedding_from_db(db_settings)
    collection_name = _build_mem0_collection_name(embedder)

    # --- Vector Store: MongoDB (Unified storage with business data, client cosine similarity)---
    # Qdrant is no longer used, vectors and business data are stored uniformly in MongoDB.
    # Dimension mismatches are automatically handled by client cosine (vectors with incompatible dimensions are skipped).
    embedding_dims = 1024
    if embedder:
        embedding_dims = int(embedder.get("config", {}).get("embedding_dims") or embedding_dims)

    mongo_uri, mongo_db_name = _get_mongo_connection_info()
    vector_store = {
        "provider": "mongodb",
        "config": {
            "mongo_uri": mongo_uri,
            "db_name": mongo_db_name,
            "collection_name": collection_name,
            "embedding_model_dims": embedding_dims,
        },
    }

    # --- LLM: Reuse unified system model selection and credential parsing logic ---
    llm = None
    try:
        from app.services.intelligent_assistant_service import get_system_llm_config_from_config_doc

        resolved_llm_config = get_system_llm_config_from_config_doc(
            config_doc,
            model_keys=["quick_analysis_model", "deep_analysis_model"],
        )
        if resolved_llm_config is not None:
            llm = _build_mem0_llm_config_from_unified_config(resolved_llm_config)
    except Exception as e:
        logger.debug("mem0 config: Unified LLM parsing failed: %s", e)

    if llm is None:
        target_model = (
            db_settings.get("quick_analysis_model")
            or db_settings.get("deep_analysis_model")
        )
        if not target_model and llm_configs:
            for cfg in llm_configs:
                if cfg.get("enabled", True) and cfg.get("model_name"):
                    target_model = cfg["model_name"]
                    break

        llm = {
            "provider": "openai",
            "config": {
                "api_key": "",
                "model": target_model or "deepseek-chat",
                "temperature": 0.1,
                "max_tokens": 2000,
            },
        }

    # --- Assemble ---
    from .prompts import FINANCIAL_FACT_EXTRACTION_PROMPT

    config: Dict[str, Any] = {
        "vector_store": vector_store,
        "llm": llm,
        "custom_prompt": FINANCIAL_FACT_EXTRACTION_PROMPT,
        "version": "v1.1",
    }
    if embedder:
        config["embedder"] = embedder

    return config


def summarize_mem0_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Returns the security digest of the mem0 configuration, excluding the plaintext key."""
    vector_store = config.get("vector_store") or {}
    vector_store_cfg = vector_store.get("config") or {}

    llm = config.get("llm") or {}
    llm_cfg = llm.get("config") or {}

    embedder = config.get("embedder") or {}
    embedder_cfg = embedder.get("config") or {}

    return {
        "vector_store": {
            "provider": vector_store.get("provider") or "",
            "collection_name": vector_store_cfg.get("collection_name") or "",
            "db_name": vector_store_cfg.get("db_name") or "",
            "embedding_model_dims": vector_store_cfg.get("embedding_model_dims") or 0,
        },
        "llm": {
            "provider": llm.get("provider") or "",
            "model": llm_cfg.get("model") or "",
            "base_url": llm_cfg.get("openai_base_url") or "",
            "has_api_key": bool(llm_cfg.get("api_key")),
        },
        "embedder": {
            "provider": embedder.get("provider") or "",
            "model": embedder_cfg.get("model") or "",
            "base_url": embedder_cfg.get("openai_base_url") or embedder_cfg.get("ollama_base_url") or "",
            "embedding_dims": embedder_cfg.get("embedding_dims") or 0,
            "has_api_key": bool(embedder_cfg.get("api_key")),
        },
    }


def describe_mem0_config(db=None) -> Dict[str, Any]:
    """Returns the security digest of the currently parsed configuration of mem0, excluding the cleartext key."""
    return summarize_mem0_config(build_mem0_config(db))

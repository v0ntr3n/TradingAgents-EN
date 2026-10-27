# tradingagents/agents/utils/embedding_provider.py
"""
Embedding service provider

Get the list of vendors that support embedding from the database configuration and try to use the available services in order of priority.

Supported vendors (included via supported_features "embedding" Judgment):
- openai: text-embedding-3-small
- google: text-embedding-004
- dashscope: text-embedding-v3
- siliconflow: BAAI/bge-large-zh-v1.5
"""

import os
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger("agents.utils.embedding")


@dataclass
class EmbeddingProviderConfig:
    """Embedding Provider configuration"""
    name: str
    display_name: str
    api_key: str
    base_url: str
    model: str
    is_active: bool
    priority: int = 0  # Priority, the smaller the number, the higher the priority


# Default embedding model mapping
DEFAULT_EMBEDDING_MODELS = {
    "openai": "text-embedding-3-small",
    "google": "text-embedding-004",
    "dashscope": "text-embedding-v3",
    "siliconflow": "BAAI/bge-large-zh-v1.5",
    "alibaba": "text-embedding-v3",  # Ali Bailian alias
}

# Provider priority (the lower the number, the higher the priority)
PROVIDER_PRIORITY = {
    "dashscope": 1,      # Alibaba Bailian is given priority (domestic access is fast)
    "siliconflow": 2,    # Silicon-based flow comes second
    "google": 3,         # Google
    "openai": 4,         # OpenAI (May need to circumvent the wall)
}


class EmbeddingProviderManager:
    """
    Embedding provider manager
    
    Responsible for obtaining vendor configurations that support embedding from the database and providing the ability to try based on priority
    """
    
    _instance = None
    _providers_cache: Optional[List[EmbeddingProviderConfig]] = None
    _cache_timestamp: float = 0
    _cache_ttl: float = 300  # Cache for 5 minutes
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self._initialized = getattr(self, '_initialized', False)
        if not self._initialized:
            self._initialized = True
            logger.info("🔧 [EmbeddingProviderManager] Initialization completed")
    
    def get_available_providers(self, force_refresh: bool = False) -> List[EmbeddingProviderConfig]:
        """
        Get a list of available embedding providers (sorted by priority)
        
        Args:
            force_refresh: Whether to force cache refresh
            
        Returns:
            Provider configuration list sorted by priority
        """
        import time
        current_time = time.time()
        
        # Check if cache is valid
        if (not force_refresh and 
            self._providers_cache is not None and 
            current_time - self._cache_timestamp < self._cache_ttl):
            return self._providers_cache
        
        # Get configuration from database
        providers = self._fetch_providers_from_db()
        
        # Update cache
        self._providers_cache = providers
        self._cache_timestamp = current_time
        
        return providers
    
    def _fetch_providers_from_db(self) -> List[EmbeddingProviderConfig]:
        """Get providers that support embedding from the database"""
        providers = []

        # Prioritize checking the private Embedding environment variables (EMBEDDING_API_KEY + EMBEDDING_API_BASE + EMBEDDING_MODEL) 
        dedicated = self._get_dedicated_embedding_provider()
        if dedicated:
            providers.append(dedicated)

        try:
            # Try to get from MongoDB
            from pymongo import MongoClient
            
            # Get MongoDB connection string
            mongo_uri = os.getenv('MONGODB_CONNECTION_STRING', 'mongodb://localhost:27017')
            db_name = os.getenv('MONGODB_DATABASE_NAME', 'tradingagents')
            
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            db = client[db_name]
            
            # Query active vendors that support embedding
            cursor = db.llm_providers.find({
                "is_active": True,
                "supported_features": "embedding"
            })
            
            for doc in cursor:
                # Check if there is a valid API Key
                api_key = doc.get('api_key')
                if not api_key or api_key.startswith('your_') or api_key == 'placeholder':
                    # Try to get from environment variables
                    api_key = self._get_env_api_key(doc.get('name', ''))
                
                if not api_key:
                    logger.debug(f"⚠️ 厂商 {doc.get('name')} 没有有效的 API Key，跳过")
                    continue
                
                name = doc.get('name', '')
                config = EmbeddingProviderConfig(
                    name=name,
                    display_name=doc.get('display_name', name),
                    api_key=api_key,
                    base_url=doc.get('default_base_url', ''),
                    model=DEFAULT_EMBEDDING_MODELS.get(name, 'text-embedding-3-small'),
                    is_active=True,
                    priority=PROVIDER_PRIORITY.get(name, 99)
                )
                providers.append(config)
            
            client.close()
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to get embedding provider from database: {e}")
        
        # If the database is not configured, try to get it from environment variables
        if not providers:
            providers = self._get_providers_from_env()
        
        # Sort by priority
        providers.sort(key=lambda x: x.priority)

        logger.info(f"📋 [EmbeddingProviderManager] Available embedding providers: {[p.name for p in providers]}")
        return providers

    def _get_dedicated_embedding_provider(self) -> Optional[EmbeddingProviderConfig]:
        """Check the private Embedding environment variable (EMBEDDING_API_KEY + EMBEDDING_API_BASE + EMBEDDING_MODEL) 
        
        If EMBEDDING_API_KEY is set, returns a private embedding provider configuration.
        EMBEDDING_API_BASE Fallback to OPENAI_API_BASE / OPENAI_API_KEY when EMBEDDING_MODEL and EMBEDDING_MODEL are left blank.
        """
        # Take EMBEDDING_API_KEY first, leave it blank and fall back to OPENAI_API_KEY
        api_key = os.getenv("EMBEDDING_API_KEY", "").strip()
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or api_key.startswith("your_"):
            return None

        base_url = os.getenv("EMBEDDING_API_BASE", "").strip()
        if not base_url:
            base_url = os.getenv("OPENAI_API_BASE", "").strip()

        model = os.getenv("EMBEDDING_MODEL", "").strip()
        if not model:
            model = "text-embedding-3-small"

        logger.info(f"✅ Use a dedicated Embedding configuration: base={base_url[:30]}, model={model}")
        return EmbeddingProviderConfig(
            name="embedding_dedicated",
            display_name="Embedding (Dedicated)",
            api_key=api_key,
            base_url=base_url,
            model=model,
            is_active=True,
            priority=0  # highest priority
        )

    def _get_providers_from_env(self) -> List[EmbeddingProviderConfig]:
        """Get embedding provider configuration from environment variables"""
        providers = []

        # Prioritize checking of private Embedding environment variables
        dedicated = self._get_dedicated_embedding_provider()
        if dedicated:
            providers.append(dedicated)

        # Check the environment variables of each manufacturer
        env_mappings = [
            ("dashscope", "DASHSCOPE_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1"),
            ("google", "GOOGLE_API_KEY", "https://generativelanguage.googleapis.com/v1beta"),
            ("siliconflow", "SILICONFLOW_API_KEY", "https://api.siliconflow.cn/v1"),
        ]

        for name, env_var, base_url in env_mappings:
            api_key = os.getenv(env_var)
            if api_key and not api_key.startswith('your_'):
                providers.append(EmbeddingProviderConfig(
                    name=name,
                    display_name=name.title(),
                    api_key=api_key,
                    base_url=base_url,
                    model=DEFAULT_EMBEDDING_MODELS.get(name, 'text-embedding-3-small'),
                    is_active=True,
                    priority=PROVIDER_PRIORITY.get(name, 99)
                ))
                logger.debug(f"✅ 从环境变量获取到 {name} 的 API Key")

        return providers

    def _get_env_api_key(self, provider_name: str) -> Optional[str]:
        """Get the environment variables based on the manufacturer name API Key"""
        env_var_mapping = {
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "alibaba": "DASHSCOPE_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
            "qianfan": "QIANFAN_API_KEY",
        }

        env_var = env_var_mapping.get(provider_name.lower())
        if env_var:
            key = os.getenv(env_var)
            if key and not key.startswith('your_'):
                return key
        return None

    def get_embedding(self, text: str, preferred_provider: Optional[str] = None) -> Tuple[Optional[List[float]], str]:
        """
        Get the embedding vector of the text

        Try each provider in order of priority until success or all fail

        Args:
            text: To get the text of embedding
            preferred_provider: Preferred provider name (optional)

        Returns:
            (embedding_vector, provider_name) or (None, error_message)
        """
        providers = self.get_available_providers()

        if not providers:
            logger.warning("⚠️ No embedding provider available")
            return None, "no_provider_available"

        # If a preferred provider is specified, put it first
        if preferred_provider:
            providers = sorted(providers,
                             key=lambda x: (0 if x.name == preferred_provider else 1, x.priority))

        # Try each provider by priority
        for provider in providers:
            try:
                embedding = self._call_provider(provider, text)
                if embedding:
                    logger.info(f"✅ 使用 {provider.display_name} 获取 embedding 成功")
                    return embedding, provider.name
            except Exception as e:
                logger.warning(f"⚠️ {provider.display_name} Failed to get embedding: {e}")
                continue

        return None, "all_providers_failed"

    def _call_provider(self, provider: EmbeddingProviderConfig, text: str) -> Optional[List[float]]:
        """Call the specified provider to obtain embedding"""

        if provider.name in ("dashscope", "alibaba"):
            return self._call_dashscope(provider, text)
        elif provider.name == "openai":
            return self._call_openai(provider, text)
        elif provider.name == "google":
            return self._call_google(provider, text)
        elif provider.name == "siliconflow":
            return self._call_siliconflow(provider, text)
        else:
            # Try OpenAI compatible interface by default
            return self._call_openai_compatible(provider, text)

    def _call_dashscope(self, provider: EmbeddingProviderConfig, text: str) -> Optional[List[float]]:
        """Call Ali Bailian embedding API"""
        try:
            import dashscope
            from dashscope import TextEmbedding

            dashscope.api_key = provider.api_key

            response = TextEmbedding.call(
                model=provider.model,
                input=text
            )

            if response.status_code == 200:
                return response.output['embeddings'][0]['embedding']
            else:
                logger.warning(f"DashScope API Error: {response.code} - {response.message}")
                return None

        except Exception as e:
            logger.warning(f"DashScope call failed: {e}")
            raise

    def _call_openai(self, provider: EmbeddingProviderConfig, text: str) -> Optional[List[float]]:
        """call OpenAI embedding API"""
        return self._call_openai_compatible(provider, text)

    def _call_openai_compatible(self, provider: EmbeddingProviderConfig, text: str) -> Optional[List[float]]:
        """Call OpenAI compatible embedding API"""
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=provider.api_key,
                base_url=provider.base_url,
                timeout=30.0
            )

            response = client.embeddings.create(
                model=provider.model,
                input=text
            )

            return response.data[0].embedding

        except Exception as e:
            logger.warning(f"OpenAI Compatible API call failed: {e}")
            raise

    def _call_google(self, provider: EmbeddingProviderConfig, text: str) -> Optional[List[float]]:
        """call Google embedding API"""
        try:
            import google.generativeai as genai

            genai.configure(api_key=provider.api_key)

            result = genai.embed_content(
                model=f"models/{provider.model}",
                content=text
            )

            return result['embedding']

        except Exception as e:
            logger.warning(f"Google API call failed: {e}")
            raise

    def _call_siliconflow(self, provider: EmbeddingProviderConfig, text: str) -> Optional[List[float]]:
        """Call Silicone Flow embedding API (OpenAI Compatible)"""
        return self._call_openai_compatible(provider, text)


# Global singleton
_embedding_manager: Optional[EmbeddingProviderManager] = None


def get_embedding_manager() -> EmbeddingProviderManager:
    """Get the Embedding manager singleton"""
    global _embedding_manager
    if _embedding_manager is None:
        _embedding_manager = EmbeddingProviderManager()
    return _embedding_manager


def get_embedding_with_fallback(text: str, preferred_provider: Optional[str] = None) -> Tuple[Optional[List[float]], str]:
    """
    Get the embedding of text (with automatic degradation)

    Convenience function to automatically handle downgrade logic

    Args:
        text: To get the text of embedding
        preferred_provider: Preferred provider name

    Returns:
        (embedding_vector, provider_name) or (None, error_message)
    """
    manager = get_embedding_manager()
    return manager.get_embedding(text, preferred_provider)


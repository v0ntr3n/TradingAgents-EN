"""
Text Embedding Manager v2.0

Supports multiple Embedding providers:
- DashScope (Alibaba Cloud Tongyi Qianwen)
- OpenAI
- DeepSeek
- Google
- Qianfan (Baidu Qianfan)
- Ollama (local model)
- LocalAI (local model)

Features:
- Automatic downgrade (switch to backup service when primary service fails)
- Read from database configuration API Key
- Supports intelligent truncation of long text
- unified interface
- Supports local models (no API key required)
"""

import os
import logging
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


# 🔥 Embedding Model dimension mapping table
EMBEDDING_DIMENSIONS = {
    # DashScope (Alibaba Cloud)
    "text-embedding-v1": 1536,
    "text-embedding-v2": 1536,
    "text-embedding-v3": 1024,  # 🔥 v3 Start changing to 1024
    "text-embedding-v4": 1024,  # 🔥 v4 Also 1024

    # OpenAI
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,

    # DeepSeek
    "deepseek-embedding": 1536,

    # Google
    "embedding-001": 768,
    "text-embedding-004": 768,

    # Qianfan (Baidu)
    "embedding-v1": 384,
    "bge-large-zh": 1024,

    # Zhipu (Wisdom spectrum AI)
    "embedding-2": 1024,  # Zhipu AI embedding-2 model (default)
    "embedding-3": 2048,  # Zhipu AI embedding-3 model (default dimension, supports 256-2048)

    # Ollama (Local model, dimensions depend on the specific model)
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,

    # Default dimensions
    "default": 1024,  # 🔥 Uniformly use 1024 as the default dimension (compatible with more models)
}


class EmbeddingManager:
    """
    Text Embedding Manager
    
    Responsible for calling various Embedding APIs to convert text into vectors
    """
    
    def __init__(self, db=None):
        """
        Initialize the Embedding Manager

        Args:
            db: MongoDB Database connection (for reading configuration)
        """
        self.db = db
        self._providers = []
        self._primary_provider = None
        self._fallback_providers = []

        # 🔥 Circuit breaker mechanism: Return directly after continuous failures exceed the threshold to avoid trying to call each document
        # Failed API (e.g. 300 documents × 2 providers × 1 seconds/call = 10 minutes blocking)
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3  # Fuse after 3 consecutive failures
        self._circuit_broken = False

        # initialization provider
        self._init_providers()
    
    def _init_providers(self):
        """Initialize the Embedding provider from the database or environment variables"""
        # 🔥 Jingdong Cloud mode: Prioritize the use of environment variable configuration (EMBEDDING_*) 
        # The jdyun provider in the database records the old address/old Key, and the environment variables are the latest configuration injected during deployment.
        if os.getenv("JDYUN_MODE", "").lower() in ("true", "1", "yes"):
            if self._init_from_jdyun_env():
                return
        # Original logic: read the configuration from the database first
        if self.db is not None:
            try:
                self._init_from_database()
                if self._providers:
                    logger.info(f"✅ loaded from database {len(self._providers)} Embedding Providers")
                    return
            except Exception as e:
                logger.warning(f"⚠️ Failed to load Embedding configuration from database: {e}")

        # Downgrade: initialize from environment variables
        self._init_from_env()

    @staticmethod
    def _check_provider_available(provider_info: Dict[str, Any]) -> bool:
        """Pre-checks whether the provider is available (without actually calling the embedding API).

        - Cloud model: Check if the API Key is not empty
        - Ollama / LocalAI: Check if the TCP port is reachable
        """
        name = provider_info.get("name", "")
        base_url = provider_info.get("base_url") or ""

        # sentence-transformers Local embedding has been removed and local provider is no longer supported
        if name == "local":
            return False

        # Local HTTP service (Ollama): Check if the /v1/models endpoint returns a valid response
        if name == "ollama" and base_url:
            import urllib.request
            try:
                models_url = base_url.rstrip("/") + "/models"
                req = urllib.request.Request(models_url, method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status != 200:
                        logger.info(f"🔌 {provider_info['display_name']} /v1/models Return {resp.status}, skip")
                        return False
                return True
            except Exception as e:
                logger.info(f"🔌 {provider_info['display_name']} Service unreachable ({base_url}), skip: {e}")
                return False

        # Cloud Model: Check API Key
        api_key = provider_info.get("api_key", "")
        if not api_key:
            logger.info(f"🔑 {provider_info['display_name']} API Key is not configured, skip")
            return False

        return True

    def _init_from_jdyun_env(self) -> bool:
        """JD Cloud mode: Initialize Embedding provider from environment variables

        priority use EMBEDDING_* Environment variable, fallback to when not set OPENAI_*. 
        Returning True indicates successful configuration using environment variables, False indicates incomplete configuration and requires a database.
        """
        api_base = os.getenv("EMBEDDING_API_BASE", "") or os.getenv("OPENAI_API_BASE", "")
        api_key = os.getenv("EMBEDDING_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("EMBEDDING_MODEL", "") or "text-embedding-v3"

        if not api_base or not api_key:
            logger.warning("⚠️ JD Cloud mode: EMBEDDING_API_BASE/EMBEDDING_API_KEY is not configured and falls back to the database.")
            return False

        provider_info = {
            "name": "jdyun",
            "api_key": api_key,
            "base_url": api_base,
            "model": model,
            "display_name": "JD Cloud",
        }
        self._providers = [provider_info]
        self._primary_provider = provider_info
        self._fallback_providers = []
        logger.info(f"✅ JD Cloud Mode: Using environment variables Embedding provider (model: {model}, base: {api_base})")
        return True

    def _init_from_database(self):
        """Read Embedding configuration from database"""
        if self.db is None:
            return
        
        try:
            # 🔥 Check if it is an asynchronous database (AsyncIOMotorDatabase)
            # If it is an asynchronous database, you need to use synchronous query (via get_mongo_db_sync)
            from pymongo.database import Database

            # Only explicit PyMongo synchronization Database is used directly;
            # In other cases (Motor database or loop-safe agent), all are switched to the synchronization view.
            # Avoid using AsyncIOMotorCursor as a synchronous cursor iterator.
            if isinstance(self.db, Database):
                providers_collection = self.db.llm_providers
                system_configs_collection = self.db.system_configs
            else:
                # Asynchronous database or proxy objects: using synchronous client queries
                from app.core.database import get_mongo_db_sync
                sync_db = get_mongo_db_sync()
                providers_collection = sync_db.llm_providers
                system_configs_collection = sync_db.system_configs
            
            # 🔥 New: Prioritize reading the default Embedding model from the system configuration
            default_embedding_model = None
            try:
                system_config = system_configs_collection.find_one(
                    {"is_active": True},
                    sort=[("version", -1)]
                )
                if system_config and system_config.get("system_settings"):
                    default_embedding_model = system_config["system_settings"].get("default_embedding_model")
                    if default_embedding_model:
                        logger.info(f"📋 Read the default Embedding model from the system configuration: {default_embedding_model}")
            except Exception as e:
                logger.debug(f"⚠️ Failed to read system configuration: {e}")
            
            # Check for vendors that support embedding
            # 🔥 Fix: Use supported_features array to check for inclusion "embedding"
            # 🔥 Fix: field name is is_active instead of enabled
            cursor = providers_collection.find({
                "supported_features": "embedding",  # 🔥 direct match, avoid $in Returns empty results on some MongoDB versions
                "is_active": True
            }).sort("created_at", 1)  # Sort by creation time (because priority field does not exist)
            
            provider_docs = list(cursor)
            
            # 🔥 If the default Embedding model is configured, it will be parsed and used first.
            preferred_provider_name = None
            preferred_model = None
            if default_embedding_model and ":" in default_embedding_model:
                parts = default_embedding_model.split(":", 1)
                preferred_provider_name = parts[0].lower()
                preferred_model = parts[1]
                logger.info(f"🎯 Prioritize the use of system-configured Embedding models: {preferred_provider_name}:{preferred_model}")
            
            for provider_doc in provider_docs:
                provider_name = provider_doc.get("name", "").lower()
                api_key = provider_doc.get("api_key", "")
                base_url = provider_doc.get("default_base_url") or provider_doc.get("base_url", "")
                embedding_model = provider_doc.get("embedding_model", "")

                # 🔥 Not required for local HTTP services (ollama/localai) API Key
                is_local_provider = provider_name in ["ollama", "localai"]
                if not api_key and not is_local_provider:
                    logger.debug(f"⚠️ {provider_name} API Key is not configured, skip")
                    continue

                # 🔥 If the system is configured with the manufacturer's model, the system configuration will be used first.
                if preferred_provider_name == provider_name and preferred_model:
                    embedding_model = preferred_model
                    logger.info(f"✅ Embedding model using system configuration: {provider_name}:{embedding_model}")
                # 🔥 If embedding_model is not configured, the default model is used
                elif not embedding_model:
                    # Set default model based on provider
                    default_models = {
                        "dashscope": "text-embedding-v3",
                        "openai": "text-embedding-3-small",
                        "deepseek": "text-embedding-v3",
                        "zhipu": "embedding-2",  # Zhipu AI default embedding model
                    }
                    embedding_model = default_models.get(provider_name, "text-embedding-3-small")
                    logger.debug(f"📝 {provider_name} embedding_model is not configured, use the default model: {embedding_model}")
                
                provider_info = {
                    "name": provider_name,
                    "api_key": api_key,
                    "base_url": base_url,
                    "model": embedding_model,
                    "display_name": provider_doc.get("display_name", provider_name)
                }

                # 🔥 Pre-check: API Key/Port Reachability
                if not self._check_provider_available(provider_info):
                    continue

                # 🔥 If this is the preferred provider for the system configuration, put it first
                if preferred_provider_name == provider_name:
                    self._providers.insert(0, provider_info)
                else:
                    self._providers.append(provider_info)
                logger.debug(f"📋 Load Embedding provider: {provider_info['display_name']} (model: {embedding_model})")
            
            # Set up primary and backup providers
            if self._providers:
                self._primary_provider = self._providers[0]
                self._fallback_providers = self._providers[1:]
                logger.info(f"🎯 Main Embedding Provider: {self._primary_provider['display_name']} (model: {self._primary_provider['model']})")
                if self._fallback_providers:
                    logger.info(f"💡 Alternate provider: {[p['display_name'] for p in self._fallback_providers]}")
        
        except Exception as e:
            logger.error(f"❌ Initializing Embedding provider from database failed: {e}")
            raise
    
    def _init_from_env(self):
        """Initializing the Embedding provider from environment variables"""
        logger.info("📋 Initializing the Embedding provider from environment variables")
        
        # Try each provider in order of priority
        providers_config = [
            {
                "name": "dashscope",
                "env_key": "DASHSCOPE_API_KEY",
                "model": "text-embedding-v3",
                "base_url": "https://dashscope.aliyuncs.com/api/v1",
                "display_name": "Alibaba Cloud Tongyi Qianwen"
            },
            {
                "name": "openai",
                "env_key": "OPENAI_API_KEY",
                "model": "text-embedding-3-small",
                "base_url": "https://api.openai.com/v1",
                "display_name": "OpenAI"
            },
            {
                "name": "deepseek",
                "env_key": "DEEPSEEK_API_KEY",
                "model": "text-embedding-v3",
                "base_url": "https://api.deepseek.com",
                "display_name": "DeepSeek"
            },
            {
                "name": "ollama",
                "env_key": None,  # Not required for local models API Key
                "model": "nomic-embed-text",  # Ollama Default Embedding model
                "base_url": "http://localhost:11434/v1",
                "display_name": "Ollama (local)"
            },
        ]
        
        for config in providers_config:
            # 🔥 Local models (Ollama, LocalAI) do not require API Key, add them directly
            if config["env_key"] is None:
                provider_info = {
                    "name": config["name"],
                    "api_key": "ollama",  # Local models use placeholders
                    "base_url": config["base_url"],
                    "model": config["model"],
                    "display_name": config["display_name"]
                }
                # 🔥 Precheck: port reachability (except local)
                if not self._check_provider_available(provider_info):
                    continue
                self._providers.append(provider_info)
                logger.debug(f"📋 Load Embedding provider: {config['display_name']} (local model)")
            else:
                # Cloud model requires API Key
                api_key = os.getenv(config["env_key"])
                if api_key:
                    provider_info = {
                        "name": config["name"],
                        "api_key": api_key,
                        "base_url": config["base_url"],
                        "model": config["model"],
                        "display_name": config["display_name"]
                    }
                    # 🔥 Precheck passed when api_key is non-null
                    self._providers.append(provider_info)
                    logger.debug(f"📋 Load Embedding provider: {config['display_name']}")
        
        # Set up primary and backup providers
        if self._providers:
            self._primary_provider = self._providers[0]
            self._fallback_providers = self._providers[1:]
            logger.info(f"🎯 Main Embedding Provider: {self._primary_provider['display_name']}")
        else:
            logger.warning("⚠️ No available Embedding provider found, memory functionality will be disabled")

    def get_embedding_dimension(self) -> int:
        """
        Get the vector dimensions of the current Embedding model
        
        🔥 Uniformly use 1024 dimensions as storage dimensions to ensure compatibility
        - All models use 1024-dimensional storage uniformly
        - Avoid the problem of mismatch in different model dimensions
        - Local models may only support a maximum of 1536 dimensions, while cloud models may support 2048 dimensions
        - Uniform use of 1024 dimensions is the best compatibility solution

        Returns:
            Vector dimension (fixed to 1024)
        """
        # 🔥 Returns 1024 dimensions uniformly, no need to dynamically obtain according to the model
        return 1024

    def get_config(self) -> Dict[str, Any]:
        """
        Get the current Embedding configuration information

        Returns:
            A dictionary containing primary and backup provider configurations
        """
        config = {
            "primary_provider": None,
            "fallback_providers": [],
            "total_providers": len(self._providers),
            "has_provider": bool(self._primary_provider)
        }

        if self._primary_provider:
            config["primary_provider"] = {
                "name": self._primary_provider.get("name"),
                "display_name": self._primary_provider.get("display_name"),
                "model": self._primary_provider.get("model"),
                "base_url": self._primary_provider.get("base_url"),
                # Do not return API Key (security consideration)
            }
        
        if self._fallback_providers:
            config["fallback_providers"] = [
                {
                    "name": p.get("name"),
                    "display_name": p.get("display_name"),
                    "model": p.get("model"),
                    "base_url": p.get("base_url"),
                }
                for p in self._fallback_providers
            ]
        
        return config
    
    def get_embedding(self, text: str, max_length: int = 50000) -> Tuple[Optional[List[float]], str]:
        """
        Get the Embedding vector of the text

        Args:
            text: Enter text
            max_length: Maximum text length (truncate if exceeded)

        Returns:
            (embedding vector, Provider name) or (None, error message)
        """
        if not text or not isinstance(text, str):
            logger.warning("⚠️ Input text is empty or invalid")
            return None, "invalid_input"

        # Check text length
        if len(text) > max_length:
            logger.warning(f"⚠️ Text too long ({len(text):,} > {max_length:,}), truncate")
            text = self._smart_truncate(text, max_length)

        # If no provider is available
        if not self._primary_provider:
            logger.warning("⚠️ No Embedding provider available")
            return None, "no_provider"

        # 🔥 Circuit breaker check: Return directly after consecutive failures exceed the threshold and no longer try to call.
        if self._circuit_broken:
            return None, "circuit_broken"

        # Try the main provider
        embedding = self._call_provider(self._primary_provider, text)
        if embedding:
            self._consecutive_failures = 0  # Reset the counter on success
            return embedding, self._primary_provider['display_name']

        # Primary provider failed, cumulative number of consecutive failures
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._max_consecutive_failures:
            self._circuit_broken = True
            logger.warning(
                f"⚠️ Embedding Melted: Continuous failures {self._consecutive_failures} times,"
                f"Subsequent calls will be skipped directly (need to restart the service or repair the API Key to recover)"
            )
            return None, "circuit_broken"

        # Try an alternative provider
        for provider in self._fallback_providers:
            logger.info(f"💡 Try an alternative provider: {provider['display_name']}")
            embedding = self._call_provider(provider, text)
            if embedding:
                self._consecutive_failures = 0  # Reset the counter on success
                return embedding, provider['display_name']

        # All providers fail
        logger.error("❌ All Embedding providers fail")
        return None, "all_failed"

    def _call_provider(self, provider: Dict[str, Any], text: str) -> Optional[List[float]]:
        """
        Call the specified Embedding provider

        Args:
            provider: Provider configuration
            text: Enter text

        Returns:
            embedding vector or None
        """
        provider_name = provider['name']

        try:
            if provider_name == "dashscope":
                return self._call_dashscope(provider, text)
            elif provider_name in ["openai", "deepseek", "zhipu", "ollama", "localai", "jdyun", "volcengine", "volcengine_coding", "siliconflow", "kimi", "aihubmix", "xiaomi"]:
                # 🔥 OpenAI Compatible APIs (including Zhipu AI, DeepSeek, JD Cloud, local models, etc.)
                # Zhipu AI uses OpenAI compatible API,base_url: https://open.bigmodel.cn/api/paas/v4
                return self._call_openai_compatible(provider, text)
            elif provider_name == "google":
                return self._call_google(provider, text)
            elif provider_name == "qianfan":
                return self._call_qianfan(provider, text)
            else:
                logger.warning(f"⚠️ Unknown provider: {provider_name}, Try using OpenAI Compatible API")
                # 🔥 Improvement: For unknown providers, try using OpenAI compatible API (generic way)
                return self._call_openai_compatible(provider, text)
        except Exception as e:
            logger.error(f"❌ {provider['display_name']} Embedding call failed: {e}")
            return None

    def _call_dashscope(self, provider: Dict[str, Any], text: str) -> Optional[List[float]]:
        """call DashScope Embedding API"""
        try:
            import dashscope
            from dashscope import TextEmbedding

            # 🔥 DashScope API Restrictions: The input text length must be within [1, 8192] Token between
            # Note: This is the Token limit, not the character limit
            # For Chinese:1 Token ≈ 1-2 character
            # For English:1 Token ≈ 0.75 word ≈ 3-4 character
            # 8192 Token ≈ 8000-10000 Characters (conservative estimate for mixed text)
            # To be safe, we use 8000 characters as the limit (leave some margin)
            DASHSCOPE_MAX_CHARS = 8000  # Be conservative and make sure not to exceed 8192 Token
            if len(text) > DASHSCOPE_MAX_CHARS:
                logger.warning(f"⚠️ DashScope Text too long ({len(text):,} character > {DASHSCOPE_MAX_CHARS:,} character limit), truncate")
                logger.info(f"   📝 Note: DashScope Embedding API is limited to 8192 Token, currently using character limit {DASHSCOPE_MAX_CHARS} as a conservative estimate")
                text = self._smart_truncate(text, DASHSCOPE_MAX_CHARS)
                logger.info(f"📝 DashScope Length after truncation: {len(text):,} character")

            dashscope.api_key = provider['api_key']

            model_name = provider['model']
            # 🔥 DashScope text-embedding-v3/v4 Support dimensions parameter (default 1024 dimensions)
            # According to official documentation: both v3 and v4 support custom dimensions, and the default is 1024
            supports_dimensions = 'text-embedding-v3' in model_name.lower() or 'text-embedding-v4' in model_name.lower()
            
            if supports_dimensions:
                # 🔥 Models that support the dimensions parameter, specifying 1024 dimensions directly
                # DashScope API Pass additional configuration via parameters parameter
                try:
                    response = TextEmbedding.call(
                        model=model_name,
                        input=text,
                        text_type="document",  # DashScope Required parameters
                        parameters={"dimensions": 1024}  # 🔥 Specify 1024 dimensions
                    )
                    logger.debug(f"✅ DashScope Embedding Success (specified 1024 dimensions), actual dimensions: {len(response.output['embeddings'][0]['embedding']) if response.status_code == 200 else 'N/A'}")
                except Exception as e:
                    # If the parameters method is not supported, try passing dimensions directly (some SDK versions may differ)
                    logger.debug(f"⚠️ Passing dimensions using parameters failed, try another way: {e}")
                    try:
                        response = TextEmbedding.call(
                            model=model_name,
                            input=text,
                            text_type="document",
                            dimensions=1024  # Try passing the dimensions parameter directly
                        )
                        logger.debug(f"✅ DashScope Embedding Success (specified 1024 dimensions), actual dimensions: {len(response.output['embeddings'][0]['embedding']) if response.status_code == 200 else 'N/A'}")
                    except Exception as e2:
                        # If neither is supported, use the default call (the default is 1024 dimensions)
                        logger.debug(f"⚠️ Passing dimensions directly also fails, using the default call (default 1024 dimensions): {e2}")
                        response = TextEmbedding.call(
                            model=model_name,
                            input=text,
                            text_type="document"
                        )
                        logger.debug(f"✅ DashScope Embedding Success (default 1024 dimensions), actual dimensions: {len(response.output['embeddings'][0]['embedding']) if response.status_code == 200 else 'N/A'}")
            else:
                # Models that do not support dimensions parameters (v1/v2)
                response = TextEmbedding.call(
                    model=model_name,
                    input=text
                )
                logger.debug(f"✅ DashScope Embedding success (default dimensions), actual dimensions: {len(response.output['embeddings'][0]['embedding']) if response.status_code == 200 else 'N/A'}")

            if response.status_code == 200:
                embedding = response.output['embeddings'][0]['embedding']
                
                # 🔥 DashScope API The dimensions parameter may not be supported and needs to be adjusted to 1024 dimensions.
                if len(embedding) != 1024:
                    actual_dim = len(embedding)
                    if actual_dim > 1024:
                        embedding = embedding[:1024]
                        logger.debug(f"📏 DashScope Embedding Dimensions {actual_dim} -> 1024 (Truncated)")
                    else:
                        embedding = embedding + [0.0] * (1024 - actual_dim)
                        logger.debug(f"📏 DashScope Embedding Dimensions {actual_dim} -> 1024 (padding)")
                
                return embedding
            else:
                logger.error(f"❌ DashScope API Error: {response.code} - {response.message}")
                return None
        except ImportError:
            logger.error("❌ DashScope The package is not installed, please run: pip install dashscope")
            return None
        except Exception as e:
            logger.error(f"❌ DashScope Embedding Abnormal: {e}")
            return None

    def _call_openai_compatible(self, provider: Dict[str, Any], text: str) -> Optional[List[float]]:
        """Call the OpenAI compatible Embedding API (OpenAI, DeepSeek, Ollama, LocalAI etc.)"""
        try:
            from openai import OpenAI

            # 🔥 OpenAI/DeepSeek API Limitation: Input text length is usually around 8192 tokens
            # For safety, we limit the character length to 8000 (leave some margin)
            OPENAI_MAX_LENGTH = 8000
            if len(text) > OPENAI_MAX_LENGTH:
                logger.warning(f"⚠️ {provider['display_name']} Text too long ({len(text):,} > {OPENAI_MAX_LENGTH:,}), truncate")
                text = self._smart_truncate(text, OPENAI_MAX_LENGTH)
                logger.info(f"📝 {provider['display_name']} Length after truncation: {len(text):,}")

            # 🔥 Local models (Ollama, LocalAI) usually do not require an API Key, use "ollama" or empty string
            api_key = provider.get('api_key') or "ollama"

            # 🔥 Disable SDK automatic retry: 401/Network error will be returned immediately, which will be handled by the upper layer circuit breaker mechanism.
            # Avoid 300 documents × (1 original + 2 Try again) × 1 seconds = 15 minute blocking start
            client = OpenAI(
                api_key=api_key,  # Local models can use arbitrary values or "ollama"
                base_url=provider['base_url'],
                max_retries=0,
            )

            # 🔥 Use 1024 dimensions uniformly. If the model supports the dimensions parameter, specify it directly.
            # OpenAI text-embedding-3 Series, zhipu embedding-3, JD Cloud Qwen3-Embedding support dimensions parameter
            model_name = provider['model']
            supports_dimensions = (
                'embedding-3' in model_name.lower() or  # zhipu embedding-3
                'text-embedding-3' in model_name.lower() or  # OpenAI text-embedding-3
                'qwen3-embedding' in model_name.lower() or  # JD Cloud Qwen3-Embedding
                'embedding' in model_name.lower() and 'jdyun' in provider.get('name', '').lower()  # JD Cloud other Embedding models
            )
            
            if supports_dimensions:
                # Models that support the dimensions parameter, specifying 1024 dimensions directly
                response = client.embeddings.create(
                    model=model_name,
                    input=text,
                    dimensions=1024  # 🔥 Uniformly use 1024 dimensions
                )
                logger.debug(f"✅ {provider['display_name']} Embedding Success (specified 1024 dimensions), actual dimensions: {len(response.data[0].embedding)}")
            else:
                # Models that do not support the dimensions parameter use the default dimensions.
                response = client.embeddings.create(
                    model=model_name,
                    input=text
                )
                logger.debug(f"✅ {provider['display_name']} Embedding success (default dimensions), actual dimensions: {len(response.data[0].embedding)}")

            embedding = response.data[0].embedding
            
            # 🔥 For models that do not support the dimensions parameter, they need to be adjusted to 1024 dimensions.
            if len(embedding) != 1024:
                actual_dim = len(embedding)
                if actual_dim > 1024:
                    # If the dimension is greater than 1024, truncate to 1024
                    embedding = embedding[:1024]
                    logger.debug(f"📏 {provider['display_name']} Embedding Dimensions {actual_dim} -> 1024 (Truncated)")
                else:
                    # If dimension is less than 1024, pad to 1024 (padding with 0s)
                    embedding = embedding + [0.0] * (1024 - actual_dim)
                    logger.debug(f"📏 {provider['display_name']} Embedding Dimensions {actual_dim} -> 1024 (padding)")
            
            return embedding
        except ImportError:
            logger.error("❌ OpenAI The package is not installed, please run: pip install openai")
            return None
        except Exception as e:
            logger.error(f"❌ {provider['display_name']} Embedding Abnormal: {e}")
            return None

    def _call_google(self, provider: Dict[str, Any], text: str) -> Optional[List[float]]:
        """Call Google Embedding API (Google Generative AI)"""
        try:
            import google.generativeai as genai
            
            api_key = provider.get('api_key', '')
            if not api_key:
                logger.warning("⚠️ Google API Key Not configured")
                return None
            
            genai.configure(api_key=api_key)
            
            model_name = provider.get('model', 'text-embedding-004')
            # Make sure the model name is properly formatted (Google API requires models/ prefix)
            if not model_name.startswith('models/'):
                model_name = f'models/{model_name}'
            
            # 🔥 call Google Embedding API
            # Note: Google's embedding API may not support the output_dimensionality parameter (depending on model version)
            # If the model does not support it, the dimensions will be adjusted below.
            result = genai.embed_content(
                model=model_name,
                content=text
            )
            
            embedding = result['embedding']
            
            # 🔥 Unified adjustment to 1024 dimensions
            if len(embedding) != 1024:
                actual_dim = len(embedding)
                if actual_dim > 1024:
                    # If the dimension is greater than 1024, truncate to 1024
                    embedding = embedding[:1024]
                    logger.debug(f"📏 Google Embedding Dimensions {actual_dim} -> 1024 (Truncated)")
                else:
                    # If dimension is less than 1024, pad to 1024 (padding with 0s)
                    embedding = embedding + [0.0] * (1024 - actual_dim)
                    logger.debug(f"📏 Google Embedding Dimensions {actual_dim} -> 1024 (padding)")
            
            logger.debug(f"✅ Google Embedding Success, the ultimate dimension: {len(embedding)}")
            return embedding
            
        except ImportError:
            logger.error("❌ Google Generative AI The package is not installed, please run: pip install google-generativeai")
            return None
        except Exception as e:
            logger.error(f"❌ Google Embedding Abnormal: {e}")
            return None

    def _call_qianfan(self, provider: Dict[str, Any], text: str) -> Optional[List[float]]:
        """call Qianfan Embedding API"""
        # TODO: Implement Qianfan Embedding API call
        logger.warning("⚠️ Qianfan Embedding Not yet implemented")
        return None

    def _smart_truncate(self, text: str, max_length: int) -> str:
        """Intelligently truncate text to maintain semantic integrity"""
        if len(text) <= max_length:
            return text

        # Try truncation at sentence boundaries
        sentences = text.split('。')
        if len(sentences) > 1:
            truncated = ""
            for sentence in sentences:
                if len(truncated + sentence + '。') <= max_length - 50:
                    truncated += sentence + '。'
                else:
                    break
            if len(truncated) > max_length // 2:
                logger.debug(f"📝 Truncate at sentence boundaries, retain {len(truncated)}/{len(text)} character")
                return truncated

        # Simple truncation
        truncated = text[:max_length]
        logger.debug(f"📝 Simply truncate and retain {len(truncated)}/{len(text)} character")
        return truncated


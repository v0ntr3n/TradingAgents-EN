import chromadb
from chromadb.config import Settings
from openai import OpenAI
import dashscope
from dashscope import TextEmbedding
import os
import threading
import hashlib
import warnings
from typing import Dict, Optional

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("agents.utils.memory")


class ChromaDBManager:
    """Singleton ChromaDB manager to avoid conflicts in concurrent collection creation"""

    _instance = None
    _lock = threading.Lock()
    _collections: Dict[str, any] = {}
    _client = None
    _chroma_operation_lock = threading.Lock()  # 🔒 ChromaDB Operation locks (protecting Rust extensions)

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ChromaDBManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            try:
                # v3.6.0: Add environment variable switch to skip ChromaDB initialization when MEM0 is enabled
                # mem0 Migrated to Qdrant, Chromadb only for legacy code paths
                if os.environ.get("MEM0_ENABLED", "").lower() == "true":
                    logger.info("[ChromaDB] MEM0 Enabled, skip ChromaDB initialization (use Qdrant)")
                    self._client = None
                    self._initialized = True
                    return

                # Use a unified configuration module
                from .chromadb_config import get_optimal_chromadb_client, is_windows_11
                import platform

                self._client = get_optimal_chromadb_client()

                # Record initialization information
                system = platform.system()
                if system == "Windows":
                    if is_windows_11():
                        logger.info(f"📚 [ChromaDB] Windows 11 Optimization configuration initialization completed (Build number: {platform.version()})")
                    else:
                        logger.info(f"📚 [ChromaDB] Windows 10 Compatible configuration initialization completed")
                else:
                    logger.info(f"📚 [ChromaDB] {system}标准配置初始化完成")

                self._initialized = True
            except Exception as e:
                logger.error(f"❌ [ChromaDB] Initialization failed: {e}")
                # Use the simplest configuration as a fallback
                try:
                    settings = Settings(
                        allow_reset=True,
                        anonymized_telemetry=False,  # Key: Disable telemetry
                        is_persistent=False
                    )
                    self._client = chromadb.Client(settings)
                    logger.info(f"📚 [ChromaDB] Initialization complete with alternate configuration")
                except Exception as backup_error:
                    # Last resort
                    self._client = chromadb.Client()
                    logger.warning(f"⚠️ [ChromaDB] Initialize with minimal configuration: {backup_error}")
                self._initialized = True

    def get_or_create_collection(self, name: str):
        """线程安全地获取或创建集合"""
        with self._lock:
            if name in self._collections:
                logger.info(f"📚 [ChromaDB] Use cached collections: {name}")
                return self._collections[name]

            try:
                # Try to get an existing collection
                collection = self._client.get_collection(name=name)
                logger.info(f"📚 [ChromaDB] Get existing collection: {name}")
            except Exception:
                try:
                    # Create new collection
                    collection = self._client.create_collection(name=name)
                    logger.info(f"📚 [ChromaDB] Create new collection: {name}")
                except Exception as e:
                    # It may be created concurrently, try to get it again
                    try:
                        collection = self._client.get_collection(name=name)
                        logger.info(f"📚 [ChromaDB] Get collection after concurrent creation: {name}")
                    except Exception as final_error:
                        logger.error(f"❌ [ChromaDB] 集合操作失败: {name}, 错误: {final_error}")
                        raise final_error

            # cache collection
            self._collections[name] = collection
            return collection


class FinancialSituationMemory:
    def __init__(self, name, config):
        warnings.warn(
            "FinancialSituationMemory It has entered legacy-only compatibility mode. Please use mem0 MemoryProvider/MemoryManager for the main path instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.config = config
        self.llm_provider = config.get("llm_provider", "openai").lower()

        # Configure the length limit of the vector cache (the vector cache enables length checking by default)
        self.max_embedding_length = int(os.getenv('MAX_EMBEDDING_CONTENT_LENGTH', '50000'))  # Default 50K characters
        self.enable_embedding_length_check = os.getenv('ENABLE_EMBEDDING_LENGTH_CHECK', 'true').lower() == 'true'  # Vector caching is enabled by default

        # Select embedding model and client based on LLM provider
        # Initialize downgrade option flags
        self.fallback_available = False

        # 🔥 Prioritize obtaining available embedding services from database configuration
        if self._init_from_database_config():
            # Successful initialization from database, skipping traditional initialization logic
            pass
        elif self.llm_provider == "dashscope" or self.llm_provider == "alibaba":
            self.embedding = "text-embedding-v3"
            self.client = None  # DashScope No OpenAI client required

            # Set DashScope API key
            dashscope_key = os.getenv('DASHSCOPE_API_KEY')
            if dashscope_key:
                try:
                    # Try importing and initializing DashScope
                    import dashscope
                    from dashscope import TextEmbedding

                    dashscope.api_key = dashscope_key
                    logger.info(f"✅ DashScope API Key configured, memory function enabled")

                    # Optional: Test API connection (simple verification)
                    # No actual calls are made here, only the import and key settings are verified

                except ImportError as e:
                    # DashScope Package not installed
                    logger.error(f"❌ DashScope Package not installed: {e}")
                    self.client = "DISABLED"
                    logger.warning(f"⚠️ 记忆功能已禁用")

                except Exception as e:
                    # Other initialization errors
                    logger.error(f"❌ DashScope Initialization failed: {e}")
                    self.client = "DISABLED"
                    logger.warning(f"⚠️ 记忆功能已禁用")
            else:
                # Without DashScope key, memory function is disabled
                self.client = "DISABLED"
                logger.warning(f"⚠️ DASHSCOPE_API_KEY not found, memory function disabled")
                logger.info(f"💡 The system will continue to operate but historical memory will not be saved or retrieved")
        elif self.llm_provider == "qianfan":
            # Qianfan (Wen Xinyiyan) embedding configuration
            # Qianfan currently does not have an independent embedding API and uses Alibaba Bailian as a downgrade option.
            dashscope_key = os.getenv('DASHSCOPE_API_KEY')
            if dashscope_key:
                try:
                    # Use Alibaba Bailian embedding service as Qianfan's embedding solution
                    import dashscope
                    from dashscope import TextEmbedding

                    dashscope.api_key = dashscope_key
                    self.embedding = "text-embedding-v3"
                    self.client = None
                    logger.info(f"💡 Qianfan uses Alibaba Bailian embedded service")
                except ImportError as e:
                    logger.error(f"❌ DashScope Package not installed: {e}")
                    self.client = "DISABLED"
                    logger.warning(f"⚠️ 千帆记忆功能已禁用")
                except Exception as e:
                    logger.error(f"❌ 千帆嵌入初始化失败: {e}")
                    self.client = "DISABLED"
                    logger.warning(f"⚠️ 千帆记忆功能已禁用")
            else:
                # Without DashScope key, memory function is disabled
                self.client = "DISABLED"
                logger.warning(f"⚠️ Qianfan did not find DASHSCOPE_API_KEY, the memory function is disabled")
                logger.info(f"💡 The system will continue to operate but historical memory will not be saved or retrieved")
        elif self.llm_provider == "deepseek":
            # Check if OpenAI embedding is forced
            force_openai = os.getenv('FORCE_OPENAI_EMBEDDING', 'false').lower() == 'true'

            if not force_openai:
                # Try using Alibaba Bailian embed
                dashscope_key = os.getenv('DASHSCOPE_API_KEY')
                if dashscope_key:
                    try:
                        # Test whether Ali Bailian is available
                        import dashscope
                        from dashscope import TextEmbedding

                        dashscope.api_key = dashscope_key
                        # Verify TextEmbedding availability (no actual call required)
                        self.embedding = "text-embedding-v3"
                        self.client = None
                        logger.info(f"💡 DeepSeek Use Alibaba Bailian embedded service")
                    except ImportError as e:
                        logger.error(f"⚠️ DashScope Package not installed: {e}")
                        dashscope_key = None  # forced downgrade
                    except Exception as e:
                        logger.error(f"⚠️ Alibaba Bailian embedding initialization failed: {e}")
                        dashscope_key = None  # forced downgrade
            else:
                dashscope_key = None  # Skip Ali Bailian

            if not dashscope_key or force_openai:
                # Downgrade to OpenAI embedding
                self.embedding = "text-embedding-3-small"
                openai_key = os.getenv('OPENAI_API_KEY')
                if openai_key:
                    self.client = OpenAI(
                        api_key=openai_key,
                        base_url=config.get("backend_url", "https://api.openai.com/v1")
                    )
                    logger.warning(f"⚠️ DeepSeek Fallback to OpenAI embedding service")
                else:
                    # Finally try DeepSeek's own embedding
                    deepseek_key = os.getenv('DEEPSEEK_API_KEY')
                    if deepseek_key:
                        try:
                            self.client = OpenAI(
                                api_key=deepseek_key,
                                base_url="https://api.deepseek.com"
                            )
                            logger.info(f"💡 DeepSeek Use your own embed service")
                        except Exception as e:
                            logger.error(f"❌ DeepSeek Embed service is not available: {e}")
                            # Disable memory function
                            self.client = "DISABLED"
                            logger.info(f"🚨 The memory function is disabled, the system will continue to operate without saving historical memory")
                    else:
                        # Disable memory features instead of throwing exceptions
                        self.client = "DISABLED"
                        logger.info(f"🚨 No available embedding service found, memory functionality disabled")
        elif self.llm_provider == "google":
            # Google AI Use Ali Bailian embedding if available, otherwise disable memory function
            dashscope_key = os.getenv('DASHSCOPE_API_KEY')
            openai_key = os.getenv('OPENAI_API_KEY')
            
            if dashscope_key:
                try:
                    # Try to initialize DashScope
                    import dashscope
                    from dashscope import TextEmbedding

                    self.embedding = "text-embedding-v3"
                    self.client = None
                    dashscope.api_key = dashscope_key
                    
                    # Check if OpenAI key is available as downgrade option
                    if openai_key:
                        logger.info(f"💡 Google AI Use Alibaba Bailian embedding service (OpenAI as downgrade option)")
                        self.fallback_available = True
                        self.fallback_client = OpenAI(api_key=openai_key, base_url=config["backend_url"])
                        self.fallback_embedding = "text-embedding-3-small"
                    else:
                        logger.info(f"💡 Google AI Use Alibaba Bailian embedded service (no downgrade option)")
                        self.fallback_available = False
                        
                except ImportError as e:
                    logger.error(f"❌ DashScope Package not installed: {e}")
                    self.client = "DISABLED"
                    logger.warning(f"⚠️ Google AI Memory function disabled")
                except Exception as e:
                    logger.error(f"❌ DashScope Initialization failed: {e}")
                    self.client = "DISABLED"
                    logger.warning(f"⚠️ Google AI Memory function disabled")
            else:
                # Without DashScope key, memory function is disabled
                self.client = "DISABLED"
                self.fallback_available = False
                logger.warning(f"⚠️ Google AI DASHSCOPE_API_KEY not found, memory function disabled")
                logger.info(f"💡 The system will continue to operate but historical memory will not be saved or retrieved")
        elif self.llm_provider in {"openrouter", "aihubmix"}:
            # OpenAI Compatible with aggregation channel support: priority is given to using Alibaba Bailian embedding, otherwise the memory function is disabled
            provider_label = "AIHubMix" if self.llm_provider == "aihubmix" else "OpenRouter"
            dashscope_key = os.getenv('DASHSCOPE_API_KEY')
            if dashscope_key:
                try:
                    # Try using Alibaba Bailian embed
                    import dashscope
                    from dashscope import TextEmbedding

                    self.embedding = "text-embedding-v3"
                    self.client = None
                    dashscope.api_key = dashscope_key
                    logger.info(f"💡 {provider_label}使用阿里百炼嵌入服务")
                except ImportError as e:
                    logger.error(f"❌ DashScope Package not installed: {e}")
                    self.client = "DISABLED"
                    logger.warning(f"⚠️ {provider_label}记忆功能已禁用")
                except Exception as e:
                    logger.error(f"❌ DashScope Initialization failed: {e}")
                    self.client = "DISABLED"
                    logger.warning(f"⚠️ {provider_label}记忆功能已禁用")
            else:
                # Without DashScope key, memory function is disabled
                self.client = "DISABLED"
                logger.warning(f"⚠️ {provider_label}DASHSCOPE_API_KEY not found, memory function disabled")
                logger.info(f"💡 The system will continue to operate but historical memory will not be saved or retrieved")
        elif config["backend_url"] == "http://localhost:11434/v1":
            self.embedding = "nomic-embed-text"
            self.client = OpenAI(base_url=config["backend_url"])
        else:
            self.embedding = "text-embedding-3-small"
            openai_key = os.getenv('OPENAI_API_KEY')
            if openai_key:
                self.client = OpenAI(
                    api_key=openai_key,
                    base_url=config["backend_url"]
                )
            else:
                self.client = "DISABLED"
                logger.warning(f"⚠️ OPENAI_API_KEY not found, memory function disabled")

        # Using the singleton ChromaDB manager
        self.chroma_manager = ChromaDBManager()
        self.situation_collection = self.chroma_manager.get_or_create_collection(name)

    def _smart_text_truncation(self, text, max_length=8192):
        """Intelligent text truncation to maintain semantic integrity and cache compatibility"""
        if len(text) <= max_length:
            return text, False  # Returns the original text and a flag indicating whether to truncate
        
        # Try truncation at sentence boundaries
        sentences = text.split('。')
        if len(sentences) > 1:
            truncated = ""
            for sentence in sentences:
                if len(truncated + sentence + '。') <= max_length - 50:  # Leave 50 characters margin
                    truncated += sentence + '。'
                else:
                    break
            if len(truncated) > max_length // 2:  # Keep at least half of the content
                logger.info(f"📝 智能截断：在句子边界截断，保留{len(truncated)}/{len(text)}字符")
                return truncated, True
        
        # Try truncation at paragraph boundary
        paragraphs = text.split('\n')
        if len(paragraphs) > 1:
            truncated = ""
            for paragraph in paragraphs:
                if len(truncated + paragraph + '\n') <= max_length - 50:
                    truncated += paragraph + '\n'
                else:
                    break
            if len(truncated) > max_length // 2:
                logger.info(f"📝 智能截断：在段落边界截断，保留{len(truncated)}/{len(text)}字符")
                return truncated, True
        
        # Final choice: Keep key information from the first and second halves
        front_part = text[:max_length//2]
        back_part = text[-(max_length//2-100):]  # Leave 100 characters for connectors
        truncated = front_part + "\n...[内容截断]...\n" + back_part
        logger.warning(f"⚠️ 强制截断：保留首尾关键信息，{len(text)}字符截断为{len(truncated)}字符")
        return truncated, True

    def _init_from_database_config(self) -> bool:
        """
        Initialize embedding service from database configuration

        Prioritize the vendors that support embedding and are enabled from the database, and select them according to priority.

        Returns:
            True If initialization is successful, False if you need to fall back to traditional initialization
        """
        try:
            from .embedding_provider import get_embedding_manager, EmbeddingProviderConfig

            manager = get_embedding_manager()
            providers = manager.get_available_providers()

            if not providers:
                logger.debug("📋 No embedding provider available in database, use legacy initialization")
                return False

            # Choose the highest priority provider
            primary_provider = providers[0]
            logger.info(f"✅ Get embedding configuration from database: {primary_provider.display_name} ({primary_provider.name})")

            # Configure embedding parameters
            self.embedding = primary_provider.model
            self.embedding_provider_name = primary_provider.name
            self._embedding_provider_config = primary_provider
            self._embedding_manager = manager

            # Set up client based on provider type
            if primary_provider.name in ("dashscope", "alibaba"):
                # DashScope Uses own SDK, no OpenAI client required
                try:
                    import dashscope
                    dashscope.api_key = primary_provider.api_key
                    self.client = None
                    logger.info(f"✅ 使用 {primary_provider.display_name} embedding 服务（SDK模式）")
                except ImportError:
                    logger.warning("⚠️ DashScope Package not installed, try using OpenAI compatibility mode")
                    self.client = OpenAI(
                        api_key=primary_provider.api_key,
                        base_url=primary_provider.base_url,
                        timeout=30.0
                    )
            else:
                # Other providers use OpenAI compatible clients
                self.client = OpenAI(
                    api_key=primary_provider.api_key,
                    base_url=primary_provider.base_url,
                    timeout=30.0
                )
                logger.info(f"✅ 使用 {primary_provider.display_name} embedding 服务（OpenAI兼容模式）")

            # If there are other providers, tag downgrade is available
            if len(providers) > 1:
                self.fallback_available = True
                logger.info(f"💡 降级选项可用: {[p.name for p in providers[1:]]}")

            # Update llm_provider to reflect the actual provider used
            self.llm_provider = primary_provider.name

            return True

        except ImportError as e:
            logger.debug(f"📋 EmbeddingProviderManager Not available: {e}, Use traditional initialization")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Initializing embedding from database failed: {e}, Use traditional initialization")
            return False

    def get_embedding(self, text):
        """Get embedding for a text using the configured provider"""

        # Check if the memory function is disabled
        if self.client == "DISABLED":
            # Memory feature disabled, returns empty vector
            logger.debug(f"⚠️ Memorization is disabled, returning an empty vector")
            return [0.0] * 1024  # Returns a 1024-dimensional zero vector

        # Validate input text
        if not text or not isinstance(text, str):
            logger.warning(f"⚠️ If the input text is empty or invalid, an empty vector is returned.")
            return [0.0] * 1024

        text_length = len(text)
        if text_length == 0:
            logger.warning(f"⚠️ The input text length is 0 and an empty vector is returned.")
            return [0.0] * 1024
        
        # Check if length limit is enabled
        if self.enable_embedding_length_check and text_length > self.max_embedding_length:
            logger.warning(f"⚠️ 文本过长({text_length:,}字符 > {self.max_embedding_length:,}字符)，跳过向量化")
            # Store skip information
            self._last_text_info = {
                'original_length': text_length,
                'processed_length': 0,
                'was_truncated': False,
                'was_skipped': True,
                'provider': self.llm_provider,
                'strategy': 'length_limit_skip',
                'max_length': self.max_embedding_length
            }
            return [0.0] * 1024
        
        # Record text information (without any truncation)
        if text_length > 8192:
            logger.info(f"📝 处理长文本: {text_length}字符，提供商: {self.llm_provider}")
        
        # Store text processing information
        self._last_text_info = {
            'original_length': text_length,
            'processed_length': text_length,  # No truncation, keep original length
            'was_truncated': False,  # never truncate
            'was_skipped': False,
            'provider': self.llm_provider,
            'strategy': 'no_truncation_with_fallback'  # Marking strategy
        }

        # 🔥 Prefer using database-configured embedding managers
        if hasattr(self, '_embedding_manager') and self._embedding_manager is not None:
            try:
                embedding, provider_name = self._embedding_manager.get_embedding(text)
                if embedding:
                    logger.debug(f"✅ 使用 {provider_name} 获取 embedding，维度: {len(embedding)}")
                    return embedding
                else:
                    logger.warning(f"⚠️ EmbeddingManager Failed to obtain: {provider_name}, Returns an empty vector")
                    return [0.0] * 1024
            except Exception as e:
                logger.warning(f"⚠️ EmbeddingManager Abnormal: {e}, Returns an empty vector")
                return [0.0] * 1024

        if (self.llm_provider == "dashscope" or
            self.llm_provider == "alibaba" or
            self.llm_provider == "qianfan" or
            (self.llm_provider == "google" and self.client is None) or
            (self.llm_provider == "deepseek" and self.client is None) or
            (self.llm_provider in {"openrouter", "aihubmix"} and self.client is None)):
            # Using Alibaba Bailian's embedding model
            try:
                # Import DashScope module
                import dashscope
                from dashscope import TextEmbedding

                # Check if DashScope API key is available
                if not hasattr(dashscope, 'api_key') or not dashscope.api_key:
                    logger.warning(f"⚠️ DashScope API The key is not set and the memory function is degraded")
                    return [0.0] * 1024  # Returns an empty vector

                # Try calling DashScope API
                response = TextEmbedding.call(
                    model=self.embedding,
                    input=text
                )

                # Check response status
                if response.status_code == 200:
                    # successfully obtained embedding
                    embedding = response.output['embeddings'][0]['embedding']
                    logger.debug(f"✅ DashScope embedding success, dimensions: {len(embedding)}")
                    return embedding
                else:
                    # API Return error status code
                    error_msg = f"{response.code} - {response.message}"
                    
                    # Check for length limit errors
                    if any(keyword in error_msg.lower() for keyword in ['length', 'token', 'limit', 'exceed']):
                        logger.warning(f"⚠️ DashScope length limit: {error_msg}")
                        
                        # Check if there is a downgrade option
                        if hasattr(self, 'fallback_available') and self.fallback_available:
                            logger.info(f"💡 Try using OpenAI downgrade to handle long text")
                            try:
                                response = self.fallback_client.embeddings.create(
                                    model=self.fallback_embedding,
                                    input=text
                                )
                                embedding = response.data[0].embedding
                                logger.info(f"✅ OpenAI Downgrade successful, dimension: {len(embedding)}")
                                return embedding
                            except Exception as fallback_error:
                                logger.error(f"❌ OpenAI Downgrade failed: {str(fallback_error)}")
                                logger.info(f"💡 All downgrade options failed, memory function downgraded")
                                return [0.0] * 1024
                        else:
                            logger.info(f"💡 No downgrade option available, memory function downgraded")
                            return [0.0] * 1024
                    else:
                        logger.error(f"❌ DashScope API Error: {error_msg}")
                        return [0.0] * 1024  # Return an empty vector instead of throwing an exception

            except Exception as e:
                error_str = str(e).lower()
                
                # Check for length limit errors
                if any(keyword in error_str for keyword in ['length', 'token', 'limit', 'exceed', 'too long']):
                    logger.warning(f"⚠️ DashScope Length limit exception: {str(e)}")
                    
                    # Check if there is a downgrade option
                    if hasattr(self, 'fallback_available') and self.fallback_available:
                        logger.info(f"💡 Try using OpenAI downgrade to handle long text")
                        try:
                            response = self.fallback_client.embeddings.create(
                                model=self.fallback_embedding,
                                input=text
                            )
                            embedding = response.data[0].embedding
                            logger.info(f"✅ OpenAI Downgrade successful, dimension: {len(embedding)}")
                            return embedding
                        except Exception as fallback_error:
                            logger.error(f"❌ OpenAI Downgrade failed: {str(fallback_error)}")
                            logger.info(f"💡 All downgrade options failed, memory function downgraded")
                            return [0.0] * 1024
                    else:
                        logger.info(f"💡 No downgrade option available, memory function downgraded")
                        return [0.0] * 1024
                elif 'import' in error_str:
                    logger.error(f"❌ DashScope Package not installed: {str(e)}")
                else:
                    # Check if it is a network error and try to downgrade using other available services
                    is_network_error = any(keyword in error_str for keyword in [
                        'timeout', 'timed out', 'connection', 'network', 'refused'
                    ])

                    if is_network_error:
                        logger.warning(f"⚠️ DashScope network error: {str(e)}")
                        # Try downgrading using other configured embedding services (excluding current dashscope)
                        try:
                            from .embedding_provider import get_embedding_manager
                            manager = get_embedding_manager()
                            providers = manager.get_available_providers()
                            # Filter out dashscope and try other services
                            for provider in providers:
                                if provider.name not in ('dashscope', 'alibaba'):
                                    try:
                                        embedding = manager._call_provider(provider, text)
                                        if embedding:
                                            logger.info(f"✅ 使用 {provider.display_name} 降级成功")
                                            return embedding
                                    except Exception:
                                        continue
                        except Exception as fallback_e:
                            logger.debug(f"⚠️ 降级尝试失败: {fallback_e}")
                    else:
                        logger.error(f"❌ DashScope embedding Abnormal: {str(e)}")

                logger.warning(f"⚠️ The memory function is degraded and an empty vector is returned.")
                return [0.0] * 1024
        else:
            # Use OpenAI compatible embedding models
            if self.client is None:
                logger.warning(f"⚠️ Embed client is not initialized, returns empty vector")
                return [0.0] * 1024  # Returns an empty vector
            elif self.client == "DISABLED":
                # Memory feature disabled, returns empty vector
                logger.debug(f"⚠️ Memory feature disabled, returns empty vector")
                return [0.0] * 1024  # Returns a 1024-dimensional zero vector

            # Try calling OpenAI compatible embedding API
            try:
                response = self.client.embeddings.create(
                    model=self.embedding,
                    input=text
                )
                embedding = response.data[0].embedding
                logger.debug(f"✅ {self.llm_provider} embedding success, dimensions: {len(embedding)}")
                return embedding

            except Exception as e:
                error_str = str(e).lower()

                # Check whether it is a timeout or network error, and try to use Alibaba Bailian to downgrade.
                is_network_error = any(keyword in error_str for keyword in [
                    'timeout', 'timed out', 'connection', 'network', 'refused'
                ])

                if is_network_error:
                    logger.warning(f"⚠️ {self.llm_provider} embedding network error: {str(e)}")
                    # Attempt to downgrade (by priority) using the configured embedding service
                    fallback_result = self._try_embedding_fallback(text)
                    if fallback_result is not None:
                        return fallback_result

                # Check for length limit errors
                length_error_keywords = [
                    'token', 'length', 'too long', 'exceed', 'maximum', 'limit',
                    'context', 'input too large', 'request too large'
                ]

                is_length_error = any(keyword in error_str for keyword in length_error_keywords)

                if is_length_error:
                    # Length limit error: downgrade directly, try again without truncation
                    logger.warning(f"⚠️ {self.llm_provider}长度限制: {str(e)}")
                    logger.info(f"💡 In order to ensure the accuracy of analysis, the text is not truncated and the memory function is downgraded.")
                else:
                    # Other types of errors
                    if 'attributeerror' in error_str:
                        logger.error(f"❌ {self.llm_provider} API调用错误: {str(e)}")
                    elif 'connectionerror' in error_str or 'connection' in error_str:
                        logger.error(f"❌ {self.llm_provider}网络连接错误: {str(e)}")
                    elif 'timeout' in error_str:
                        logger.error(f"❌ {self.llm_provider}请求超时: {str(e)}")
                    elif 'keyerror' in error_str:
                        logger.error(f"❌ {self.llm_provider}响应格式错误: {str(e)}")
                    else:
                        logger.error(f"❌ {self.llm_provider} embedding异常: {str(e)}")

                logger.warning(f"⚠️ The memory function is degraded and an empty vector is returned.")
                return [0.0] * 1024

    def _try_dashscope_fallback(self, text):
        """
        Try using Ali Bailian (DashScope) as embedding downgrade option

        This method is called when the main embedding service (such as OpenAI) is unavailable

        Args:
            text: Text to generate embedding

        Returns:
            embedding vector, or None if downgrade also fails
        """
        # Check for DashScope API key
        dashscope_key = os.getenv('DASHSCOPE_API_KEY')
        if not dashscope_key:
            logger.debug("⚠️ DASHSCOPE_API_KEY is not configured, and Alibaba Bailian cannot be used to downgrade.")
            return None

        try:
            import dashscope
            from dashscope import TextEmbedding

            # Make sure the API key is set
            if not hasattr(dashscope, 'api_key') or not dashscope.api_key:
                dashscope.api_key = dashscope_key

            logger.info("💡 Try to use Alibaba Bailian embedding to downgrade...")

            # call DashScope API
            response = TextEmbedding.call(
                model="text-embedding-v3",
                input=text
            )

            if response.status_code == 200:
                embedding = response.output['embeddings'][0]['embedding']
                logger.info(f"✅ Alibaba Bailian was relegated successfully, Dimension: {len(embedding)}")
                return embedding
            else:
                logger.warning(f"⚠️ 阿里百练降级失败: {response.code} - {response.message}")
                return None

        except ImportError:
            logger.debug("⚠️ DashScope The package is not installed and cannot be downgraded using Alibaba Bailian.")
            return None
        except Exception as e:
            logger.warning(f"⚠️ 阿里百练降级异常: {str(e)}")
            return None

    def _try_embedding_fallback(self, text):
        """
        Use EmbeddingProviderManager to try all available embedding services

        Obtain the vendors that support embedding from the database configuration and try according to priority.

        Args:
            text: Text to generate embedding

        Returns:
            embedding vector, or None if all services failed
        """
        try:
            from .embedding_provider import get_embedding_with_fallback

            logger.info("💡 Try downgrading using an available embedding service...")

            # Exclude providers that are currently failing
            embedding, provider_name = get_embedding_with_fallback(
                text,
                preferred_provider=None  # Let managers choose by priority
            )

            if embedding:
                logger.info(f"✅ 使用 {provider_name} embedding 降级成功，维度: {len(embedding)}")
                return embedding
            else:
                logger.warning(f"⚠️ All embedding services failed: {provider_name}")
                return None

        except ImportError as e:
            logger.debug(f"⚠️ EmbeddingProviderManager Not available: {e}")
            # Fallback to original DashScope downgrade
            return self._try_dashscope_fallback(text)
        except Exception as e:
            logger.warning(f"⚠️ embedding Downgrade exception: {str(e)}")
            return None

    def get_embedding_config_status(self):
        """获取向量缓存配置状态"""
        return {
            'enabled': self.enable_embedding_length_check,
            'max_embedding_length': self.max_embedding_length,
            'max_embedding_length_formatted': f"{self.max_embedding_length:,}字符",
            'provider': self.llm_provider,
            'client_status': 'DISABLED' if self.client == "DISABLED" else 'ENABLED'
        }

    def get_last_text_info(self):
        """获取最后处理的文本信息"""
        return getattr(self, '_last_text_info', None)

    def add_situations(self, situations_and_advice, metadata=None):
        """Add financial situations and their corresponding advice. Parameter is a list of tuples (situation, rec)"""

        situations = []
        advice = []
        ids = []
        embeddings = []
        extra_meta = dict(metadata or {})

        # 🔒 Protect ChromaDB operations with thread locks (Rust extensions are not thread-safe)
        logger.debug(f"🔒 [ChromaDB] Prepare to acquire lock - add_memories count (v1.x)")
        with ChromaDBManager._chroma_operation_lock:
            logger.debug(f"🔓 [ChromaDB] Lock acquired - add_memories count (v1.x)")
            offset = self.situation_collection.count()
            logger.debug(f"✅ [ChromaDB] count Operation completed (v1.x, offset={offset})")
        logger.debug(f"🔓 [ChromaDB] Lock released - add_memories count (v1.x)")

        for i, (situation, recommendation) in enumerate(situations_and_advice):
            situations.append(situation)
            advice.append(recommendation)
            ids.append(str(offset + i))
            embeddings.append(self.get_embedding(situation))

        # 🔒 Protect ChromaDB operations with thread locks (Rust extensions are not thread-safe)
        logger.debug(f"🔒 [ChromaDB] Prepare to acquire lock - add_memories add (v1.x, count={len(situations)})")
        with ChromaDBManager._chroma_operation_lock:
            logger.debug(f"🔓 [ChromaDB] Lock acquired - add_memories add (v1.x)")
            self.situation_collection.add(
                documents=situations,
                metadatas=[{**extra_meta, "recommendation": rec} for rec in advice],
                embeddings=embeddings,
                ids=ids,
            )
            logger.debug(f"✅ [ChromaDB] add Operation completed (v1.x, count={len(situations)})")
        logger.debug(f"🔓 [ChromaDB] Lock released - add_memories add (v1.x)")

    def get_memories(self, current_situation, n_matches=1):
        """Find matching recommendations using embeddings with smart truncation handling"""
        
        # Get the current situation embedding
        query_embedding = self.get_embedding(current_situation)
        
        # Check for empty vector (memory disabled or error)
        if all(x == 0.0 for x in query_embedding):
            logger.debug(f"⚠️ Query embedding as an empty vector and return empty results")
            return []

        # 🔒 Protect ChromaDB operations with thread locks (Rust extensions are not thread-safe)
        logger.debug(f"🔒 [ChromaDB] Prepare to acquire lock - get_memories count (v1.x)")
        with ChromaDBManager._chroma_operation_lock:
            logger.debug(f"🔓 [ChromaDB] Lock acquired - get_memories count (v1.x)")
            # Check if there is enough data for query
            collection_count = self.situation_collection.count()
            logger.debug(f"✅ [ChromaDB] count Operation completed (v1.x, count={collection_count})")
            if collection_count == 0:
                logger.debug(f"📭 The memory bank is empty and returns empty results.")
                logger.debug(f"🔓 [ChromaDB] Lock released - get_memories count (v1.x)")
                return []

            # Adjust the number of queries to not exceed the number of documents in the collection
            actual_n_matches = min(n_matches, collection_count)
        logger.debug(f"🔓 [ChromaDB] Lock released - get_memories count (v1.x)")

        try:
            # 🔒 Protect ChromaDB operations with thread locks (Rust extensions are not thread-safe)
            logger.debug(f"🔒 [ChromaDB] Prepare to acquire lock - get_memories query (v1.x, n_results={actual_n_matches})")
            with ChromaDBManager._chroma_operation_lock:
                logger.debug(f"🔓 [ChromaDB] Lock acquired - get_memories query (v1.x)")
                # Perform similarity query
                results = self.situation_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=actual_n_matches
                )
                logger.debug(f"✅ [ChromaDB] query Operation completed (v1.x)")
            logger.debug(f"🔓 [ChromaDB] Lock released - get_memories query (v1.x)")
            
            # Process query results
            memories = []
            if results and 'documents' in results and results['documents']:
                documents = results['documents'][0]
                metadatas = results.get('metadatas', [[]])[0]
                distances = results.get('distances', [[]])[0]
                
                for i, doc in enumerate(documents):
                    metadata = metadatas[i] if i < len(metadatas) else {}
                    distance = distances[i] if i < len(distances) else 1.0
                    
                    memory_item = {
                        'situation': doc,
                        'recommendation': metadata.get('recommendation', ''),
                        'similarity': 1.0 - distance,  # Convert to similarity score
                        'distance': distance
                    }
                    memories.append(memory_item)
                
                # Record query information
                if hasattr(self, '_last_text_info') and self._last_text_info.get('was_truncated'):
                    logger.info(f"🔍 截断文本查询完成，找到{len(memories)}个相关记忆")
                    logger.debug(f"📊 原文长度: {self._last_text_info['original_length']}, "
                               f"length after processing: {self._last_text_info['processed_length']}")
                else:
                    logger.debug(f"🔍 记忆查询完成，找到{len(memories)}个相关记忆")
            
            return memories
            
        except Exception as e:
            logger.error(f"❌ 记忆查询失败: {str(e)}")
            return []

    def get_cache_info(self):
        """Obtain cache-related information for debugging and monitoring"""
        # 🔒 Protect ChromaDB operations with thread locks (Rust extensions are not thread-safe)
        logger.debug(f"🔒 [ChromaDB] Prepare to acquire lock - get_cache_info (v1.x)")
        with ChromaDBManager._chroma_operation_lock:
            logger.debug(f"🔓 [ChromaDB] Lock acquired - get_cache_info (v1.x)")
            collection_count = self.situation_collection.count()
            logger.debug(f"✅ [ChromaDB] count Operation completed (v1.x, count={collection_count})")
        logger.debug(f"🔓 [ChromaDB] Lock released - get_cache_info (v1.x)")

        info = {
            'collection_count': collection_count,
            'client_status': 'enabled' if self.client != "DISABLED" else 'disabled',
            'embedding_model': self.embedding,
            'provider': self.llm_provider
        }
        
        # Add last text processing information
        if hasattr(self, '_last_text_info'):
            info['last_text_processing'] = self._last_text_info
            
        return info


if __name__ == "__main__":
    # Example usage
    matcher = FinancialSituationMemory()

    # Example data
    example_data = [
        (
            "High inflation rate with rising interest rates and declining consumer spending",
            "Consider defensive sectors like consumer staples and utilities. Review fixed-income portfolio duration.",
        ),
        (
            "Tech sector showing high volatility with increasing institutional selling pressure",
            "Reduce exposure to high-growth tech stocks. Look for value opportunities in established tech companies with strong cash flows.",
        ),
        (
            "Strong dollar affecting emerging markets with increasing forex volatility",
            "Hedge currency exposure in international positions. Consider reducing allocation to emerging market debt.",
        ),
        (
            "Market showing signs of sector rotation with rising yields",
            "Rebalance portfolio to maintain target allocations. Consider increasing exposure to sectors benefiting from higher rates.",
        ),
    ]

    # Add the example situations and recommendations
    matcher.add_situations(example_data)

    # Example query
    current_situation = """
    Market showing increased volatility in tech sector, with institutional investors 
    reducing positions and rising interest rates affecting growth stock valuations
    """

    try:
        recommendations = matcher.get_memories(current_situation, n_matches=2)

        for i, rec in enumerate(recommendations, 1):
            logger.info(f"\nMatch {i}:")
            logger.info(f"Similarity Score: {rec.get('similarity', 0):.2f}")
            logger.info(f"Matched Situation: {rec.get('situation', '')}")
            logger.info(f"Recommendation: {rec.get('recommendation', '')}")

    except Exception as e:
        logger.error(f"Error during recommendation: {str(e)}")

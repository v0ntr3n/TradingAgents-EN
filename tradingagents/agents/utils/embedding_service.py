"""
Embedding Service management module

Supports multiple Embedding services, automatically selected according to priority:
1. Ollama (local) - Completely offline, recommended
2. Tongyi Qianwen DashScope - Large free limit
3. OpenAI - The effect is good but needs to be circumvented
4. Disable - graceful degradation

How to use:
    from tradingagents.agents.utils.embedding_service import get_embedding_service
    
    service = get_embedding_service(config)
    vector = service.get_embedding("text to embed")
"""

import os
import requests
from typing import Optional, List
from abc import ABC, abstractmethod

from tradingagents.utils.logging_init import get_logger
logger = get_logger("agents.utils.embedding")


class EmbeddingService(ABC):
    """Embedding Service base class"""
    
    @abstractmethod
    def get_embedding(self, text: str) -> List[float]:
        """获取文本的向量嵌入"""
        pass
    
    @abstractmethod
    def get_service_name(self) -> str:
        """获取服务名称"""
        pass
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return True


class OllamaEmbeddingService(EmbeddingService):
    """Ollama Local Embedding Services"""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "nomic-embed-text"):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self._available = None
    
    def is_available(self) -> bool:
        """Detect whether Ollama is running and the model is available"""
        if self._available is not None:
            return self._available
        
        try:
            # Check if the Ollama service is running
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if response.status_code != 200:
                self._available = False
                return False
            
            # Check if the model has been downloaded
            models = response.json().get("models", [])
            model_names = [m.get("name", "").split(":")[0] for m in models]
            
            if self.model not in model_names and f"{self.model}:latest" not in [m.get("name", "") for m in models]:
                logger.warning(f"⚠️ Ollama 运行中但未找到 {self.model} 模型")
                logger.info(f"💡 Please run: ollama pull {self.model}")
                self._available = False
                return False
            
            self._available = True
            logger.info(f"✅ Ollama Embedding Service available: {self.model}")
            return True
            
        except requests.exceptions.ConnectionError:
            logger.debug(f"Ollama Service is not running ({self.base_url})")
            self._available = False
            return False
        except Exception as e:
            logger.debug(f"Ollama 检测失败: {e}")
            self._available = False
            return False
    
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding vectors via Ollama API"""
        try:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30
            )
            if response.status_code == 200:
                return response.json().get("embedding", [])
            else:
                logger.error(f"Ollama embedding failed: {response.status_code}")
                return [0.0] * 768  # nomic-embed-text Output dimensions
        except Exception as e:
            logger.error(f"Ollama embedding Abnormal: {e}")
            return [0.0] * 768
    
    def get_service_name(self) -> str:
        return f"Ollama ({self.model})"


class DashScopeEmbeddingService(EmbeddingService):
    """Tongyi Qianwen DashScope Embedding Service"""
    
    def __init__(self):
        self.api_key = os.getenv('DASHSCOPE_API_KEY')
        self.model = "text-embedding-v3"
    
    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import dashscope
            dashscope.api_key = self.api_key
            return True
        except ImportError:
            logger.debug("dashscope Package not installed")
            return False
    
    def get_embedding(self, text: str) -> List[float]:
        try:
            from dashscope import TextEmbedding
            response = TextEmbedding.call(
                model=self.model,
                input=text
            )
            if response.status_code == 200:
                return response.output['embeddings'][0]['embedding']
            else:
                logger.error(f"DashScope embedding failed: {response.message}")
                return [0.0] * 1536
        except Exception as e:
            logger.error(f"DashScope embedding Abnormal: {e}")
            return [0.0] * 1536
    
    def get_service_name(self) -> str:
        return f"DashScope ({self.model})"


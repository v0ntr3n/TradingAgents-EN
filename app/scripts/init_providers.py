#!/usr/bin/env python3
"""
Initialize large model manufacturer data script
"""

import asyncio
import sys
import os
from datetime import datetime

# Add project root directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.core.database import init_db, get_mongo_db
from app.models.config import LLMProvider

async def init_providers():
    """Initialize large model manufacturer data"""
    print("🚀 Start initializing large model manufacturer data...")
    
    # Initialize database connection
    await init_db()
    db = get_mongo_db()
    providers_collection = db.llm_providers
    
    # Default manufacturer data
    providers_data = [
        {
            "name": "openai",
            "display_name": "OpenAI",
            "description": "OpenAI Is a leading company in the field of artificial intelligence, providing GPT series models",
            "website": "https://openai.com",
            "api_doc_url": "https://platform.openai.com/docs",
            "default_base_url": "https://api.openai.com/v1",
            "is_active": True,
            "supported_features": ["chat", "completion", "embedding", "image", "vision", "function_calling", "streaming"]
        },
        {
            "name": "anthropic",
            "display_name": "Anthropic",
            "description": "Anthropic Focus on AI security research and provide Claude series models",
            "website": "https://anthropic.com",
            "api_doc_url": "https://docs.anthropic.com",
            "default_base_url": "https://api.anthropic.com",
            "is_active": True,
            "supported_features": ["chat", "completion", "function_calling", "streaming"]
        },
        {
            "name": "google",
            "display_name": "Google AI",
            "description": "Google Artificial intelligence platform, providing Gemini series models",
            "website": "https://ai.google.dev",
            "api_doc_url": "https://ai.google.dev/docs",
            "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
            "is_active": True,
            "supported_features": ["chat", "completion", "embedding", "vision", "function_calling", "streaming"]
        },
        {
            "name": "zhipu",
            "display_name": "Wisdom spectrum AI",
            "description": "Zhipu AI provides GLM series Chinese large models",
            "website": "https://zhipuai.cn",
            "api_doc_url": "https://open.bigmodel.cn/doc",
            "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
            "is_active": True,
            "supported_features": ["chat", "completion", "embedding", "function_calling", "streaming"]
        },
        {
            "name": "deepseek",
            "display_name": "DeepSeek",
            "description": "DeepSeek Provide high-performance AI inference services",
            "website": "https://www.deepseek.com",
            "api_doc_url": "https://platform.deepseek.com/api-docs",
            "default_base_url": "https://api.deepseek.com",
            "is_active": True,
            "supported_features": ["chat", "completion", "function_calling", "streaming"]
        },
        {
            "name": "dashscope",
            "display_name": "Alibaba Cloud Bailian",
            "description": "Alibaba Cloud Bailian large model service platform provides Tongyi Qianwen and other models",
            "website": "https://bailian.console.aliyun.com",
            "api_doc_url": "https://help.aliyun.com/zh/dashscope/",
            "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "is_active": True,
            "supported_features": ["chat", "completion", "embedding", "function_calling", "streaming"]
        },
        {
            "name": "siliconflow",
            "display_name": "silicon based flow",
            "description": "Silicon Flow provides cost-effective AI inference services and supports a variety of open source models",
            "website": "https://siliconflow.cn",
            "api_doc_url": "https://docs.siliconflow.cn",
            "default_base_url": "https://api.siliconflow.cn/v1",
            "is_active": True,
            "supported_features": ["chat", "completion", "embedding", "function_calling", "streaming"]
        },
        {
            "name": "302ai",
            "display_name": "302.AI",
            "description": "302.AI It is an enterprise-level AI aggregation platform that provides unified interfaces for a variety of mainstream large models.",
            "website": "https://302.ai",
            "api_doc_url": "https://doc.302.ai",
            "default_base_url": "https://api.302.ai/v1",
            "is_active": True,
            "supported_features": ["chat", "completion", "embedding", "image", "vision", "function_calling", "streaming"]
        },
        {
            "name": "aihubmix",
            "display_name": "AiHubMix",
            "description": "AiHubMix Aggregation platform, providing OpenAI compatible unified interface",
            "website": "https://aihubmix.com/?aff=2rIi",
            "api_doc_url": "https://docs.aihubmix.com/cn/quick-start",
            "default_base_url": "https://aihubmix.com/v1",
            "is_active": True,
            "supported_features": ["chat", "completion", "embedding", "vision", "function_calling", "streaming"]
        },
        {
            "name": "volcengine",
            "display_name": "Volcano Ark",
            "description": "Volcano Ark Ark API (Agent Plan)",
            "website": "https://www.volcengine.com/solutions/ark",
            "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "test_model": "doubao-seed-2-1-turbo-260628",
            "embedding_model": "doubao-embedding-vision-251215",
            "is_active": True,
            "supported_features": ["chat", "completion", "embedding", "function_calling", "streaming"]
        },
        {
            "name": "volcengine_coding",
            "display_name": "Volcano Ark Programming",
            "description": "Volcano Ark Ark API (Coding Plan)",
            "website": "https://www.volcengine.com/solutions/ark",
            "default_base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
            "test_model": "doubao-seed-2.0-code",
            "embedding_model": "doubao-embedding-vision-251215",
            "is_active": True,
            "supported_features": ["chat", "completion", "function_calling", "streaming"]
        }
    ]
    
    # Clear existing data
    await providers_collection.delete_many({})
    print("🧹 Clear existing manufacturer data")
    
    # Insert new data
    for provider_data in providers_data:
        provider_data["created_at"] = datetime.utcnow()
        provider_data["updated_at"] = datetime.utcnow()
        
        result = await providers_collection.insert_one(provider_data)
        print(f"✅ Add manufacturer: {provider_data['display_name']} (ID: {result.inserted_id})")
    
    print(f"🎉 successful initialization {len(providers_data)} manufacturer data")

if __name__ == "__main__":
    asyncio.run(init_providers())

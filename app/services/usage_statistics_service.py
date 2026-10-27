"""
Usage statistics service
Manage model usage records and cost statistics
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

from app.core.database import get_mongo_db
from app.models.config import UsageRecord, UsageStatistics

logger = logging.getLogger("app.services.usage_statistics_service")


class UsageStatisticsService:
    """使用统计服务"""
    
    def __init__(self):
        # Using the collection name of tradingagents
        self.collection_name = "token_usage"
    
    async def add_usage_record(self, record: UsageRecord) -> bool:
        """添加使用记录"""
        try:
            db = get_mongo_db()
            collection = db[self.collection_name]

            record_dict = record.model_dump(exclude={"id"})
            result = await collection.insert_one(record_dict)

            logger.info(f"✅ 添加使用记录成功: {record.provider}/{record.model_name}")
            return True
        except Exception as e:
            logger.error(f"❌ 添加使用记录失败: {e}")
            return False
    
    async def get_usage_records(
        self,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[UsageRecord]:
        """获取使用记录"""
        try:
            db = get_mongo_db()
            collection = db[self.collection_name]
            
            # Build query conditions
            query = {}
            if provider:
                query["provider"] = provider
            if model_name:
                query["model_name"] = model_name
            if start_date or end_date:
                query["timestamp"] = {}
                if start_date:
                    query["timestamp"]["$gte"] = start_date.isoformat()
                if end_date:
                    query["timestamp"]["$lte"] = end_date.isoformat()
            
            # Query records
            cursor = collection.find(query).sort("timestamp", -1).limit(limit)
            records = []
            
            async for doc in cursor:
                doc["id"] = str(doc.pop("_id"))
                records.append(UsageRecord(**doc))
            
            logger.info(f"✅ 获取使用记录成功: {len(records)} 条")
            return records
        except Exception as e:
            logger.error(f"❌ 获取使用记录失败: {e}")
            return []
    
    async def get_usage_statistics(
        self,
        days: int = 7,
        provider: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> UsageStatistics:
        """获取使用统计"""
        try:
            db = get_mongo_db()
            collection = db[self.collection_name]
            
            # Calculation time range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Build query conditions
            query = {
                "timestamp": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat()
                }
            }
            if provider:
                query["provider"] = provider
            if model_name:
                query["model_name"] = model_name
            
            # Get all records
            cursor = collection.find(query)
            records = []
            async for doc in cursor:
                records.append(doc)
            
            # Statistics
            stats = UsageStatistics()
            stats.total_requests = len(records)

            # Cost by currency
            cost_by_currency = defaultdict(float)

            by_provider = defaultdict(lambda: {
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "cost_by_currency": defaultdict(float)
            })
            by_model = defaultdict(lambda: {
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "cost_by_currency": defaultdict(float)
            })
            by_date = defaultdict(lambda: {
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "cost_by_currency": defaultdict(float)
            })

            for record in records:
                cost = record.get("cost", 0.0)
                currency = record.get("currency", "CNY")

                # total
                stats.total_input_tokens += record.get("input_tokens", 0)
                stats.total_output_tokens += record.get("output_tokens", 0)
                stats.total_cost += cost  # Retain backward compatibility
                cost_by_currency[currency] += cost

                # Statistics by supplier
                provider_key = record.get("provider", "unknown")
                by_provider[provider_key]["requests"] += 1
                by_provider[provider_key]["input_tokens"] += record.get("input_tokens", 0)
                by_provider[provider_key]["output_tokens"] += record.get("output_tokens", 0)
                by_provider[provider_key]["cost"] += cost
                by_provider[provider_key]["cost_by_currency"][currency] += cost

                # Statistics by model
                model_key = f"{record.get('provider', 'unknown')}/{record.get('model_name', 'unknown')}"
                by_model[model_key]["requests"] += 1
                by_model[model_key]["input_tokens"] += record.get("input_tokens", 0)
                by_model[model_key]["output_tokens"] += record.get("output_tokens", 0)
                by_model[model_key]["cost"] += cost
                by_model[model_key]["cost_by_currency"][currency] += cost

                # Statistics by date
                timestamp = record.get("timestamp", "")
                if timestamp:
                    date_key = timestamp[:10]  # YYYY-MM-DD
                    by_date[date_key]["requests"] += 1
                    by_date[date_key]["input_tokens"] += record.get("input_tokens", 0)
                    by_date[date_key]["output_tokens"] += record.get("output_tokens", 0)
                    by_date[date_key]["cost"] += cost
                    by_date[date_key]["cost_by_currency"][currency] += cost

            # Convert defaultdict to plain dict (including nested cost_by_currency)
            stats.cost_by_currency = dict(cost_by_currency)
            stats.by_provider = {k: {**v, "cost_by_currency": dict(v["cost_by_currency"])} for k, v in by_provider.items()}
            stats.by_model = {k: {**v, "cost_by_currency": dict(v["cost_by_currency"])} for k, v in by_model.items()}
            stats.by_date = {k: {**v, "cost_by_currency": dict(v["cost_by_currency"])} for k, v in by_date.items()}
            
            logger.info(f"✅ 获取使用统计成功: {stats.total_requests} 条记录")
            return stats
        except Exception as e:
            logger.error(f"❌ 获取使用统计失败: {e}")
            return UsageStatistics()
    
    async def get_cost_by_provider(self, days: int = 7) -> Dict[str, float]:
        """获取按供应商的成本统计"""
        stats = await self.get_usage_statistics(days=days)
        return {
            provider: data["cost"]
            for provider, data in stats.by_provider.items()
        }
    
    async def get_cost_by_model(self, days: int = 7) -> Dict[str, float]:
        """获取按模型的成本统计"""
        stats = await self.get_usage_statistics(days=days)
        return {
            model: data["cost"]
            for model, data in stats.by_model.items()
        }
    
    async def get_daily_cost(self, days: int = 7) -> Dict[str, float]:
        """获取每日成本统计"""
        stats = await self.get_usage_statistics(days=days)
        return {
            date: data["cost"]
            for date, data in stats.by_date.items()
        }
    
    async def delete_old_records(self, days: int = 90) -> int:
        """删除旧记录"""
        try:
            db = get_mongo_db()
            collection = db[self.collection_name]
            
            # Calculate deadline
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Delete old records
            result = await collection.delete_many({
                "timestamp": {"$lt": cutoff_date.isoformat()}
            })
            
            deleted_count = result.deleted_count
            logger.info(f"✅ 删除旧记录成功: {deleted_count} 条")
            return deleted_count
        except Exception as e:
            logger.error(f"❌ 删除旧记录失败: {e}")
            return 0

    async def record_llm_usage(
        self,
        response,  # LLMResponse or langchain AIMessage
        session_id: str,
        analysis_type: str,
        stock_code: Optional[str] = None
    ) -> bool:
        """
        Record token usage for LLM calls (general method)
        
        Compatible with two LLM response objects:
        - UnifiedLLMClient LLMResponse:response.usage(Dict: prompt_tokens/completion_tokens/total_tokens) 
        - LangChain AIMessage: response.usage_metadata(Dict: input_tokens/output_tokens/token_usage) 
        
        Args:
            response: LLM response object
            session_id: session ID
            analysis_type: Function type
            stock_code: Stock code (optional)
        
        Returns:
            bool: Whether the recording is successful
        """
        try:
            if not response:
                logger.debug(f"LLM Response is empty, skipping records: {analysis_type}")
                return False
            
            # Compatible with LLMResponse (UnifiedLLMClient) and AIMessage (LangChain)
            usage = None
            provider = "unknown"
            model_name = "unknown"
            
            if hasattr(response, 'usage') and response.usage:
                # UnifiedLLMClient of LLMResponse
                usage = response.usage
                provider = response.provider.value if response.provider else "unknown"
                model_name = response.model or "unknown"
            elif hasattr(response, 'usage_metadata') and response.usage_metadata:
                # LangChain of AIMessage
                usage = response.usage_metadata
                # AIMessage No provider field, try to get from response_metadata
                meta = getattr(response, 'response_metadata', {})
                model_name = meta.get('model_name', '') or meta.get('model', '') or "unknown"
            
            if not usage:
                logger.debug(f"LLM Response without usage information, skip recording: {analysis_type}")
                return False
            
            # Unified extraction of token numbers (compatible with both formats)
            input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
            
            if input_tokens == 0 and output_tokens == 0:
                logger.debug(f"Token If the number is 0, the record will be skipped.: {analysis_type}")
                return False
            
            # Get model price configuration
            from app.services.config_service import config_service
            config = await config_service.get_system_config()
            
            # Find the corresponding LLM configuration
            llm_config = None
            if config and config.llm_configs:
                for cfg in config.llm_configs:
                    if cfg.provider == provider and cfg.model_name == model_name:
                        llm_config = cfg
                        break
            
            # Calculate cost
            cost = 0.0
            currency = "CNY"
            if llm_config:
                input_price = llm_config.input_price_per_1k or 0.0
                output_price = llm_config.output_price_per_1k or 0.0
                cost = (input_tokens / 1000 * input_price) + (output_tokens / 1000 * output_price)
                currency = llm_config.currency or "CNY"
            
            # Create usage record
            usage_record = UsageRecord(
                timestamp=datetime.now().isoformat(),
                provider=provider,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                currency=currency,
                session_id=session_id,
                analysis_type=analysis_type,
                stock_code=stock_code
            )
            
            # Save to database
            success = await self.add_usage_record(usage_record)
            
            if success:
                logger.info(f"💰 记录 token 使用: {provider}/{model_name} - 输入:{input_tokens} 输出:{output_tokens} [{analysis_type}]")
            
            return success
        except Exception as e:
            logger.error(f"❌ Log LLM token usage failure: {e}")
            return False


# Create a global instance
usage_statistics_service = UsageStatisticsService()


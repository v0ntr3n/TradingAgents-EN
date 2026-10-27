"""
Model capability management service

Provides model capability evaluation, verification and recommendation functions.
"""

from typing import Tuple, Dict, Optional, List, Any
from app.constants.model_capabilities import (
    ANALYSIS_DEPTH_REQUIREMENTS,
    DEFAULT_MODEL_CAPABILITIES,
    CAPABILITY_DESCRIPTIONS,
    ModelRole,
    ModelFeature
)
from app.core.unified_config import unified_config
import logging
import re

logger = logging.getLogger(__name__)


class ModelCapabilityService:
    """模型能力管理服务"""

    def _parse_aggregator_model_name(self, model_name: str) -> Tuple[Optional[str], str]:
        """
        Resolve model names for aggregation channels

        Args:
            model_name: Model name, which may include a prefix (e.g. openai/gpt-4, anthropic/claude-3-sonnet) 

        Returns:
            (original manufacturer, Original model name) tuple
        """
        # Common aggregation channel model name format:
        # - openai/gpt-4
        # - anthropic/claude-3-sonnet
        # - google/gemini-pro

        if "/" in model_name:
            parts = model_name.split("/", 1)
            if len(parts) == 2:
                provider_hint = parts[0].lower()
                original_model = parts[1]

                # Mapping provider hints to fully qualified names
                provider_map = {
                    "openai": "openai",
                    "anthropic": "anthropic",
                    "google": "google",
                    "deepseek": "deepseek",
                    "alibaba": "qwen",
                    "qwen": "qwen",
                    "zhipu": "zhipu",
                    "baidu": "baidu",
                    "moonshot": "moonshot"
                }

                provider = provider_map.get(provider_hint)
                return provider, original_model

        return None, model_name

    def _get_model_capability_with_mapping(self, model_name: str) -> Tuple[int, Optional[str]]:
        """
        Get model capability level (supports aggregation channel mapping)

        Returns:
            (Ability level, The original model name of the mapping) tuple
        """
        # 1. Try a direct match first
        if model_name in DEFAULT_MODEL_CAPABILITIES:
            return DEFAULT_MODEL_CAPABILITIES[model_name]["capability_level"], None

        # 2. Try to parse the aggregation channel model name
        provider, original_model = self._parse_aggregator_model_name(model_name)

        if original_model and original_model != model_name:
            # Try to search using the original model name
            if original_model in DEFAULT_MODEL_CAPABILITIES:
                logger.info(f"🔄 聚合渠道模型映射: {model_name} -> {original_model}")
                return DEFAULT_MODEL_CAPABILITIES[original_model]["capability_level"], original_model

        # 3. Return to default value
        return 2, None

    def get_model_capability(self, model_name: str) -> int:
        """
        Get the capability level of the model (supports aggregation channel model mapping)

        Args:
            model_name: Model name (may include aggregation channel prefix, such as openai/gpt-4)

        Returns:
            Ability level (1-5)
        """
        # 1. Read from database configuration first
        try:
            llm_configs = unified_config.get_llm_configs()
            for config in llm_configs:
                if config.model_name == model_name:
                    return getattr(config, 'capability_level', 2)
        except Exception as e:
            logger.warning(f"从配置读取模型能力失败: {e}")

        # 2. Read from default mapping table (supports aggregate channel mapping)
        capability, mapped_model = self._get_model_capability_with_mapping(model_name)
        if mapped_model:
            logger.info(f"✅ 使用映射模型 {mapped_model} 的能力等级: {capability}")

        return capability
    
    def get_model_config(self, model_name: str) -> Dict[str, Any]:
        """
        Obtain the complete configuration information of the model (supports aggregation channel model mapping)

        Args:
            model_name: Model name (may include aggregation channel prefix)

        Returns:
            Model configuration dictionary
        """
        # 1. Prefer reading from MongoDB database configuration (using sync client)
        try:
            from pymongo import MongoClient
            from app.core.config import settings
            from app.models.config import SystemConfig

            # Using the synchronous MongoDB client
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]
            collection = db.system_configs  # Note: the collection name is plural

            # Query system configuration (consistent with config_service)
            doc = collection.find_one({"is_active": True}, sort=[("version", -1)])

            logger.info(f"🔍 [MongoDB] Query results: doc={'exist' if doc else 'does not exist'}")
            if doc:
                logger.info(f"🔍 [MongoDB] Document version: {doc.get('version')}, is_active: {doc.get('is_active')}")

            if doc and "llm_configs" in doc:
                llm_configs = doc["llm_configs"]
                logger.info(f"🔍 [MongoDB] llm_configs Quantity: {len(llm_configs)}")

                for config_dict in llm_configs:
                    if config_dict.get("model_name") == model_name:
                        logger.info(f"🔍 [MongoDB] Find model configuration: {model_name}")
                        # 🔧 Convert a list of strings to a list of enumerations
                        features_str = config_dict.get('features', [])
                        features_enum = []
                        for feature_str in features_str:
                            try:
                                # Compatible with older versions function_calling -> tool_calling
                                if feature_str == "function_calling":
                                    feature_str = "tool_calling"
                                features_enum.append(ModelFeature(feature_str))
                            except ValueError:
                                logger.warning(f"⚠️ 未知的特性值: {feature_str}")

                        # 🔧 Convert a list of strings to a list of enumerations
                        roles_str = config_dict.get('suitable_roles', ["both"])
                        roles_enum = []
                        for role_str in roles_str:
                            try:
                                # Convert string to ModelRole enumeration
                                roles_enum.append(ModelRole(role_str))
                            except ValueError:
                                logger.warning(f"⚠️ 未知的角色值: {role_str}")

                        # If there is no role, the default is both
                        if not roles_enum:
                            roles_enum = [ModelRole.BOTH]

                        logger.info(f"📊 [MongoDB Configuration] {model_name}: features={features_enum}, roles={roles_enum}")

                        # close connection
                        client.close()

                        return {
                            "model_name": config_dict.get("model_name"),
                            "capability_level": config_dict.get('capability_level', 2),
                            "suitable_roles": roles_enum,
                            "features": features_enum,
                            "recommended_depths": config_dict.get('recommended_depths', ["快速", "基础", "标准"]),
                            "performance_metrics": config_dict.get('performance_metrics', None)
                        }

            # close connection
            client.close()

        except Exception as e:
            logger.warning(f"Failed to read model information from MongoDB: {e}", exc_info=True)

        # 2. Read from default mapping table (direct match)
        if model_name in DEFAULT_MODEL_CAPABILITIES:
            return DEFAULT_MODEL_CAPABILITIES[model_name]

        # 3. Try aggregate channel model mapping
        provider, original_model = self._parse_aggregator_model_name(model_name)
        if original_model and original_model != model_name:
            if original_model in DEFAULT_MODEL_CAPABILITIES:
                logger.info(f"🔄 聚合渠道模型映射: {model_name} -> {original_model}")
                config = DEFAULT_MODEL_CAPABILITIES[original_model].copy()
                config["model_name"] = model_name  # Keep original model name
                config["_mapped_from"] = original_model  # Record mapping source
                return config

        # 4. Return to default configuration
        logger.warning(f"未找到模型 {model_name} 的配置，使用默认配置")
        return {
            "model_name": model_name,
            "capability_level": 2,
            "suitable_roles": [ModelRole.BOTH],
            "features": [ModelFeature.TOOL_CALLING],
            "recommended_depths": ["快速", "基础", "标准"],
            "performance_metrics": {"speed": 3, "cost": 3, "quality": 3}
        }
    
    def validate_model_pair(
        self,
        quick_model: str,
        deep_model: str,
        research_depth: str
    ) -> Dict[str, Any]:
        """
        Verify that a model pair is appropriate for the current depth of analysis

        Args:
            quick_model: Quickly analyze model names
            deep_model: In-depth analysis model name
            research_depth: Research depth (Quick/Basic/Standard/In-depth/Comprehensive)

        Returns:
            Dictionary of verification results, including valid, warnings, recommendations
        """
        logger.info(f"🔍 Start validating the model pair: quick={quick_model}, deep={deep_model}, depth={research_depth}")

        requirements = ANALYSIS_DEPTH_REQUIREMENTS.get(research_depth, ANALYSIS_DEPTH_REQUIREMENTS["标准"])
        logger.info(f"🔍 分析深度要求: {requirements}")

        quick_config = self.get_model_config(quick_model)
        deep_config = self.get_model_config(deep_model)

        logger.info(f"🔍 快速模型配置: {quick_config}")
        logger.info(f"🔍 深度模型配置: {deep_config}")

        result = {
            "valid": True,
            "warnings": [],
            "recommendations": []
        }
        
        # Check out the quick model
        quick_level = quick_config["capability_level"]
        logger.info(f"🔍 Check Quick Model Capability Level: {quick_level} >= {requirements['quick_model_min']}?")
        if quick_level < requirements["quick_model_min"]:
            warning = f"⚠️ 快速模型 {quick_model} (能力等级{quick_level}) 低于 {research_depth} 分析的建议等级({requirements['quick_model_min']})"
            result["warnings"].append(warning)
            logger.warning(warning)

        # Check out Quick Model Role Adaptation
        quick_roles = quick_config.get("suitable_roles", [])
        logger.info(f"🔍 检查快速模型角色: {quick_roles}")
        if ModelRole.QUICK_ANALYSIS not in quick_roles and ModelRole.BOTH not in quick_roles:
            warning = f"💡 模型 {quick_model} 不是为快速分析优化的，可能影响数据收集效率"
            result["warnings"].append(warning)
            logger.warning(warning)

        # Check if the express model supports tool calls
        quick_features = quick_config.get("features", [])
        logger.info(f"🔍 检查快速模型特性: {quick_features}")
        if ModelFeature.TOOL_CALLING not in quick_features:
            result["valid"] = False
            warning = f"❌ 快速模型 {quick_model} 不支持工具调用，无法完成数据收集任务"
            result["warnings"].append(warning)
            logger.error(warning)

        # Check the deep model
        deep_level = deep_config["capability_level"]
        logger.info(f"🔍 Check deep model capability level: {deep_level} >= {requirements['deep_model_min']}?")
        if deep_level < requirements["deep_model_min"]:
            result["valid"] = False
            warning = f"❌ 深度模型 {deep_model} (能力等级{deep_level}) 不满足 {research_depth} 分析的最低要求(等级{requirements['deep_model_min']})"
            result["warnings"].append(warning)
            logger.error(warning)
            result["recommendations"].append(
                self._recommend_model("deep", requirements["deep_model_min"])
            )

        # Checking Deep Model Role Adaptation
        deep_roles = deep_config.get("suitable_roles", [])
        logger.info(f"🔍 检查深度模型角色: {deep_roles}")
        if ModelRole.DEEP_ANALYSIS not in deep_roles and ModelRole.BOTH not in deep_roles:
            warning = f"💡 模型 {deep_model} 不是为深度推理优化的，可能影响分析质量"
            result["warnings"].append(warning)
            logger.warning(warning)

        # Check required attributes
        logger.info(f"🔍 检查必需特性: {requirements['required_features']}")
        for feature in requirements["required_features"]:
            if feature == ModelFeature.REASONING:
                deep_features = deep_config.get("features", [])
                logger.info(f"🔍 Check deep model inference capabilities: {deep_features}")
                if feature not in deep_features:
                    warning = f"💡 {research_depth} The analysis recommends using deep models with strong inference capabilities"
                    result["warnings"].append(warning)
                    logger.warning(warning)

        logger.info(f"🔍 验证结果: valid={result['valid']}, warnings={len(result['warnings'])}条")
        logger.info(f"🔍 警告详情: {result['warnings']}")

        return result
    
    def recommend_models_for_depth(
        self,
        research_depth: str
    ) -> Tuple[str, str]:
        """
        Recommend appropriate model pairs based on depth of analysis
        
        Args:
            research_depth: Research depth (Quick/Basic/Standard/In-depth/Comprehensive)
            
        Returns:
            (quick_model, deep_model) tuple
        """
        requirements = ANALYSIS_DEPTH_REQUIREMENTS.get(research_depth, ANALYSIS_DEPTH_REQUIREMENTS["标准"])
        
        # Get all enabled models
        try:
            llm_configs = unified_config.get_llm_configs()
            enabled_models = [c for c in llm_configs if c.enabled]
        except Exception as e:
            logger.error(f"获取模型配置失败: {e}")
            # Use default model
            return self._get_default_models()
        
        if not enabled_models:
            logger.warning("No models enabled, use default configuration")
            return self._get_default_models()
        
        # Filter models suitable for rapid analysis
        quick_candidates = []
        for m in enabled_models:
            roles = getattr(m, 'suitable_roles', [ModelRole.BOTH])
            level = getattr(m, 'capability_level', 2)
            features = getattr(m, 'features', [])
            
            if (ModelRole.QUICK_ANALYSIS in roles or ModelRole.BOTH in roles) and \
               level >= requirements["quick_model_min"] and \
               ModelFeature.TOOL_CALLING in features:
                quick_candidates.append(m)
        
        # Screen models suitable for in-depth analysis
        deep_candidates = []
        for m in enabled_models:
            roles = getattr(m, 'suitable_roles', [ModelRole.BOTH])
            level = getattr(m, 'capability_level', 2)
            
            if (ModelRole.DEEP_ANALYSIS in roles or ModelRole.BOTH in roles) and \
               level >= requirements["deep_model_min"]:
                deep_candidates.append(m)
        
        # Sort by cost performance (capability level vs cost)
        quick_candidates.sort(
            key=lambda x: (
                getattr(x, 'capability_level', 2),
                -getattr(x, 'performance_metrics', {}).get("cost", 3) if getattr(x, 'performance_metrics', None) else 0
            ),
            reverse=True
        )
        
        deep_candidates.sort(
            key=lambda x: (
                getattr(x, 'capability_level', 2),
                getattr(x, 'performance_metrics', {}).get("quality", 3) if getattr(x, 'performance_metrics', None) else 0
            ),
            reverse=True
        )
        
        # Choose the best model
        quick_model = quick_candidates[0].model_name if quick_candidates else None
        deep_model = deep_candidates[0].model_name if deep_candidates else None
        
        # If no suitable one is found, use the system default
        if not quick_model or not deep_model:
            return self._get_default_models()
        
        logger.info(
            f"🤖 为 {research_depth} 分析推荐模型: "
            f"quick={quick_model} (role:Quick analysis), "
            f"deep={deep_model} (role:deep reasoning)"
        )
        
        return quick_model, deep_model
    
    def _get_default_models(self) -> Tuple[str, str]:
        """获取默认模型对"""
        try:
            quick_model = unified_config.get_quick_analysis_model()
            deep_model = unified_config.get_deep_analysis_model()
            logger.info(f"Use system default model: quick={quick_model}, deep={deep_model}")
            return quick_model, deep_model
        except Exception as e:
            logger.error(f"获取默认模型失败: {e}")
            return "qwen-turbo", "qwen-plus"
    
    def _recommend_model(self, model_type: str, min_level: int) -> str:
        """推荐满足要求的模型"""
        try:
            llm_configs = unified_config.get_llm_configs()
            for config in llm_configs:
                if config.enabled and getattr(config, 'capability_level', 2) >= min_level:
                    display_name = config.model_display_name or config.model_name
                    return f"建议使用: {display_name}"
        except Exception as e:
            logger.warning(f"推荐模型失败: {e}")
        
        return "建议升级模型配置"


# Singleton
_model_capability_service = None


def get_model_capability_service() -> ModelCapabilityService:
    """获取模型能力服务单例"""
    global _model_capability_service
    if _model_capability_service is None:
        _model_capability_service = ModelCapabilityService()
    return _model_capability_service


"""
Model capability management API routing
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.services.model_capability_service import get_model_capability_service
from app.constants.model_capabilities import (
    DEFAULT_MODEL_CAPABILITIES,
    ANALYSIS_DEPTH_REQUIREMENTS,
    CAPABILITY_DESCRIPTIONS,
    ModelRole,
    ModelFeature,
    get_model_capability_badge,
    get_role_badge,
    get_feature_badge
)
from app.core.unified_config import unified_config
from app.core.response import ok, fail
from app.services.config_service import config_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/model-capabilities", tags=["Model capability management"])


# ==================== request/response model ====================

class ModelCapabilityInfo(BaseModel):
    """Model capability information"""
    model_name: str
    capability_level: int
    suitable_roles: List[str]
    features: List[str]
    recommended_depths: List[str]
    performance_metrics: Optional[Dict[str, Any]] = None
    description: Optional[str] = None


class ModelRecommendationRequest(BaseModel):
    """Model recommendation request"""
    research_depth: str = Field(..., description="Research depth: Quick/Basic/Standard/In-depth/Comprehensive")


class ModelRecommendationResponse(BaseModel):
    """Model recommended response"""
    quick_model: str
    deep_model: str
    quick_model_info: ModelCapabilityInfo
    deep_model_info: ModelCapabilityInfo
    reason: str


class ModelValidationRequest(BaseModel):
    """Model validation request"""
    quick_model: str
    deep_model: str
    research_depth: str


class ModelValidationResponse(BaseModel):
    """Model validation response"""
    valid: bool
    warnings: List[str]
    recommendations: List[str]


class BatchInitRequest(BaseModel):
    """Batch initialization request"""
    overwrite: bool = Field(default=False, description="Whether to overwrite existing configuration")


# ==================== API routing ====================

@router.get("/default-configs")
async def get_default_model_configs():
    """
    Get all default model capability configurations

    Returns predefined common model capability configurations for reference and initialization.
    """
    try:
        # Convert to serializable format
        configs = {}
        for model_name, config in DEFAULT_MODEL_CAPABILITIES.items():
            configs[model_name] = {
                "model_name": model_name,
                "capability_level": config["capability_level"],
                "suitable_roles": [str(role) for role in config["suitable_roles"]],
                "features": [str(feature) for feature in config["features"]],
                "recommended_depths": config["recommended_depths"],
                "performance_metrics": config.get("performance_metrics"),
                "description": config.get("description")
            }

        return {
            "success": True,
            "data": configs,
            "message": "Obtain default model configuration successfully"
        }
    except Exception as e:
        logger.error(f"Failed to get default model configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/depth-requirements", response_model=dict)
async def get_depth_requirements():
    """
    Get analysis depth requirements

    Returns the minimum requirements for the model at each depth of analysis.
    """
    try:
        # Convert to serializable format
        requirements = {}
        for depth, req in ANALYSIS_DEPTH_REQUIREMENTS.items():
            requirements[depth] = {
                "min_capability": req["min_capability"],
                "quick_model_min": req["quick_model_min"],
                "deep_model_min": req["deep_model_min"],
                "required_features": [str(f) for f in req["required_features"]],
                "description": req["description"]
            }

        return ok(requirements, "Obtain analysis depth requirement successfully")
    except Exception as e:
        logger.error(f"Failed to obtain analysis depth requirement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capability-descriptions", response_model=dict)
async def get_capability_descriptions():
    """Get ability level description"""
    try:
        return ok(CAPABILITY_DESCRIPTIONS, "Obtaining ability level description successfully")
    except Exception as e:
        logger.error(f"Failed to obtain ability level description: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/badges", response_model=dict)
async def get_all_badges():
    """
    Get all badge styles

    Returns the badge style configuration of ability level, role, and characteristics.
    """
    try:
        badges = {
            "capability_levels": {
                str(level): get_model_capability_badge(level)
                for level in range(1, 6)
            },
            "roles": {
                str(role): get_role_badge(role)
                for role in ModelRole
            },
            "features": {
                str(feature): get_feature_badge(feature)
                for feature in ModelFeature
            }
        }

        return ok(badges, "Obtaining badge style successfully")
    except Exception as e:
        logger.error(f"Failed to get badge style: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommend", response_model=dict)
async def recommend_models(request: ModelRecommendationRequest):
    """
    Recommended model

    Recommends the most appropriate model pair based on depth of analysis.
    """
    try:
        capability_service = get_model_capability_service()

        # Get recommended models
        quick_model, deep_model = capability_service.recommend_models_for_depth(
            request.research_depth
        )

        logger.info(f"🔍 Recommended model: quick={quick_model}, deep={deep_model}")

        # Get model details
        quick_info = capability_service.get_model_config(quick_model)
        deep_info = capability_service.get_model_config(deep_model)

        logger.info(f"🔍 Model details: quick_info={quick_info}, deep_info={deep_info}")

        # Generate recommendation reasons
        depth_req = ANALYSIS_DEPTH_REQUIREMENTS.get(
            request.research_depth,
            ANALYSIS_DEPTH_REQUIREMENTS["标准"]
        )

        # Get ability level description
        capability_desc = {
            1: "basic level",
            2: "Standard level",
            3: "Advanced",
            4: "Professional grade",
            5: "flagship level"
        }

        quick_level_desc = capability_desc.get(quick_info['capability_level'], "Standard level")
        deep_level_desc = capability_desc.get(deep_info['capability_level'], "Standard level")

        reason = (
            f"• Quick model:{quick_level_desc}, Focus on speed and cost, suitable for data collection\n"
            f"• Deep model:{deep_level_desc}, Focus on quality and reasoning, suitable for analytical decision-making"
        )

        response_data = {
            "quick_model": quick_model,
            "deep_model": deep_model,
            "quick_model_info": quick_info,
            "deep_model_info": deep_info,
            "reason": reason
        }

        logger.info(f"🔍 response data returned: {response_data}")

        return ok(response_data, "Model recommendation successful")
    except Exception as e:
        logger.error(f"Model recommendation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate", response_model=dict)
async def validate_models(request: ModelValidationRequest):
    """
    Verify model pair

    Verify that the selected model pair is appropriate for the specified depth of analysis.
    """
    try:
        capability_service = get_model_capability_service()

        # Verify model pair
        validation = capability_service.validate_model_pair(
            request.quick_model,
            request.deep_model,
            request.research_depth
        )

        return ok(validation, "Model verification completed")
    except Exception as e:
        logger.error(f"Model validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-init", response_model=dict)
async def batch_init_capabilities(request: BatchInitRequest):
    """
    Batch initialization model capability

    Configure autofill capability parameters for models in the database.
    """
    try:
        # Get all LLM configurations
        llm_configs = unified_config.get_llm_configs()

        updated_count = 0
        skipped_count = 0

        for config in llm_configs:
            model_name = config.model_name

            # Check if capabilities have been configured
            has_capability = hasattr(config, 'capability_level') and config.capability_level is not None

            if has_capability and not request.overwrite:
                skipped_count += 1
                continue

            # Get capability parameters from default configuration
            if model_name in DEFAULT_MODEL_CAPABILITIES:
                default_config = DEFAULT_MODEL_CAPABILITIES[model_name]

                # Update configuration
                config.capability_level = default_config["capability_level"]
                config.suitable_roles = [str(role) for role in default_config["suitable_roles"]]
                config.features = [str(feature) for feature in default_config["features"]]
                config.recommended_depths = default_config["recommended_depths"]
                config.performance_metrics = default_config.get("performance_metrics")

                # Save to database
                await config_service.update_llm_config(config)
                updated_count += 1
                logger.info(f"Initialized model {model_name} capability parameters")
            else:
                logger.warning(f"model {model_name} There is no default configuration, skip")
                skipped_count += 1

        return ok(
            {
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "total_count": len(llm_configs)
            },
            f"Batch initialization completed: Update{updated_count}, skip{skipped_count}a"
        )
    except Exception as e:
        logger.error(f"Batch initialization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model/{model_name}", response_model=dict)
async def get_model_capability(model_name: str):
    """
    Get capability information of a specified model

    Args:
        model_name: Model name
    """
    try:
        capability_service = get_model_capability_service()
        config = capability_service.get_model_config(model_name)

        return ok(config, f"Get model {model_name} Capability information success")
    except Exception as e:
        logger.error(f"Failed to obtain model capability information: {e}")
        raise HTTPException(status_code=500, detail=str(e))


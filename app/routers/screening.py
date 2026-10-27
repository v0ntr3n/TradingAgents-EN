
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from bson import ObjectId

from app.core.database import get_mongo_db
from app.core.response import ok, fail
from app.utils.timezone import now_tz
from app.routers.auth_db import get_current_user

from app.services.factor_registry_service import get_factor_registry_service
from app.services.screening_service import ScreeningService, ScreeningParams
from app.services.enhanced_screening_service import get_enhanced_screening_service
from app.models.screening import (
    ScreeningCondition, ScreeningRequest as NewScreeningRequest,
    ScreeningResponse as NewScreeningResponse, FieldInfo
)

router = APIRouter(tags=["screening"])
logger = logging.getLogger("webapi")

# Filter field configuration response model
class FieldConfigResponse(BaseModel):
    """Filter field configuration response"""
    fields: Dict[str, FieldInfo]
    categories: Dict[str, List[str]]

# Traditional request/response model (maintaining backward compatibility)
class OrderByItem(BaseModel):
    field: str
    direction: str = Field("desc", pattern=r"^(?i)(asc|desc)$")

class ScreeningRequest(BaseModel):
    market: str = Field("CN", description="Market:CN")
    date: Optional[str] = Field(None, description="Trading date YYYY-MM-DD, the default is the latest")
    adj: str = Field("qfq", description="Restoration caliber: qfq/hfq/none (P0 occupancy)")
    conditions: Dict[str, Any] = Field(default_factory=dict)
    order_by: Optional[List[OrderByItem]] = None
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)

class ScreeningResponse(BaseModel):
    total: int
    items: List[dict]


class ScreeningPresetPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=100)
    basic_filters: Dict[str, Any] = Field(default_factory=dict, alias="basicFilters")
    field_filters: Dict[str, Any] = Field(default_factory=dict, alias="fieldFilters")

# Service instance
svc = ScreeningService()
enhanced_svc = get_enhanced_screening_service()
factor_registry_svc = get_factor_registry_service()


def _serialize_screening_preset(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc.get("_id")),
        "name": doc.get("name", ""),
        "basicFilters": doc.get("basic_filters", {}),
        "fieldFilters": doc.get("field_filters", {}),
        "createdAt": doc.get("created_at"),
        "updatedAt": doc.get("updated_at"),
    }


@router.get("/fields", response_model=FieldConfigResponse)
async def get_screening_fields(user: dict = Depends(get_current_user)):
    """
    Get filter field configuration
    Returns all available filter fields and their configuration information
    """
    try:
        config = factor_registry_svc.get_legacy_screening_field_config()
        return FieldConfigResponse(**config)

    except Exception as e:
        logger.error(f"[get_screening_fields] Failed to get field configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _convert_legacy_conditions_to_new_format(legacy_conditions: Dict[str, Any]) -> List[ScreeningCondition]:
    """
    Convert traditional format filters to new format

    Traditional format example:
    {
        "logic": "AND",
        "children": [
            {"field": "market_cap", "op": "between", "value": [5000000, 9007199254740991]}
        ]
    }

    new format:
    [
        ScreeningCondition(field="total_mv", operator="between", value=[50, 90071992547])
    ]
    """
    conditions = []

    # Field name mapping (old field names that may be used by the front end -> Unified backend field names)
    field_mapping = {
        "market_cap": "total_mv",      # Market capitalization (compatible with old field names)
        "pe_ratio": "pe",              # P/E ratio (compatible with old field names)
        "pb_ratio": "pb",              # Price to Book Ratio (compatible with old field names)
        "turnover": "turnover_rate",   # Turnover rate (compatible with old field names)
        "change_percent": "pct_chg",   # Increase or decrease (compatible with old field names)
        "price": "close",              # Price (compatible with old field names)
    }

    # operator mapping
    operator_mapping = {
        "between": "between",
        "gt": ">",
        "lt": "<",
        "gte": ">=",
        "lte": "<=",
        "eq": "==",
        "ne": "!=",
        "in": "in",
        "contains": "contains"
    }

    if isinstance(legacy_conditions, dict):
        children = legacy_conditions.get("children", [])

        for child in children:
            if isinstance(child, dict):
                field = child.get("field")
                op = child.get("op")
                value = child.get("value")

                if field and op and value is not None:
                    # Mapping field name
                    mapped_field = field_mapping.get(field, field)

                    # mapping operator
                    mapped_op = operator_mapping.get(op, op)

                    # Process market value unit conversion (the front-end input is 10,000 yuan, and the database stores 100 million yuan)
                    if mapped_field == "total_mv" and isinstance(value, list):
                        # Convert 10,000 yuan to 100 million yuan
                        converted_value = [v / 10000 for v in value if isinstance(v, (int, float))]
                        logger.info(f"[screening] Market capitalization unit conversion: {value} Ten thousand yuan -> {converted_value} billion")
                        value = converted_value
                    elif mapped_field == "total_mv" and isinstance(value, (int, float)):
                        value = value / 10000
                        logger.info(f"[screening] Market capitalization unit conversion: {child.get('value')} Ten thousand yuan -> {value} billion")

                    # Create filters
                    condition = ScreeningCondition(
                        field=mapped_field,
                        operator=mapped_op,
                        value=value
                    )
                    conditions.append(condition)

                    logger.info(f"[screening] Conversion conditions: {field}({op}) -> {mapped_field}({mapped_op}), value: {value}")

    return conditions


# Legacy filtering interface (remains backwards compatible, but uses enhanced services)
@router.post("/run", response_model=ScreeningResponse)
async def run_screening(req: ScreeningRequest, user: dict = Depends(get_current_user)):
    try:
        logger.info(f"[screening] Request conditions: {req.conditions}")
        logger.info(f"[screening] Sorting and paging: order_by={req.order_by}, limit={req.limit}, offset={req.offset}")

        # Convert conditions from legacy format to new format
        conditions = _convert_legacy_conditions_to_new_format(req.conditions)
        logger.info(f"[screening] converted conditions: {conditions}")

        # Use enhanced filtering services
        result = await enhanced_svc.screen_stocks(
            conditions=conditions,
            market=req.market,
            date=req.date,
            adj=req.adj,
            limit=req.limit,
            offset=req.offset,
            order_by=[{"field": o.field, "direction": o.direction} for o in (req.order_by or [])],
            use_database_optimization=True
        )

        logger.info(f"[screening] Screening completed: total={result.get('total')}, "
                   f"took={result.get('took_ms')}ms, optimization={result.get('optimization_used')}")

        if result.get('items'):
            sample = result['items'][:3]
            logger.info(f"[screening] Return sample(Top 3 items): {sample}")

        return ScreeningResponse(total=result["total"], items=result["items"])

    except Exception as e:
        logger.error(f"[screening] Processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# New optimized filtering interface
@router.post("/enhanced", response_model=NewScreeningResponse)
async def enhanced_screening(req: NewScreeningRequest, user: dict = Depends(get_current_user)):
    """
    Enhanced stock screening interface
    - Support richer filter condition formats
    - Automatically select the optimal screening strategy (database optimization vs traditional methods)
    - Provides detailed performance statistics
    """
    try:
        logger.info(f"[enhanced_screening] Filter criteria: {len(req.conditions)}a")
        logger.info(f"[enhanced_screening] Sorting and paging: order_by={req.order_by}, limit={req.limit}, offset={req.offset}")

        # Perform enhanced filtering
        result = await enhanced_svc.screen_stocks(
            conditions=req.conditions,
            market=req.market,
            date=req.date,
            adj=req.adj,
            limit=req.limit,
            offset=req.offset,
            order_by=req.order_by,
            use_database_optimization=req.use_database_optimization
        )

        logger.info(f"[enhanced_screening] Screening completed: total={result.get('total')}, "
                   f"took={result.get('took_ms')}ms, optimization={result.get('optimization_used')}")

        return NewScreeningResponse(
            total=result["total"],
            items=result["items"],
            took_ms=result.get("took_ms"),
            optimization_used=result.get("optimization_used"),
            source=result.get("source")
        )

    except Exception as e:
        logger.error(f"[enhanced_screening] Filtering failed: {e}")
        raise HTTPException(status_code=500, detail=f"Enhanced filtering failed: {str(e)}")


# Get supported field information
@router.get("/supported-fields", response_model=List[Dict[str, Any]])
async def get_supported_fields(user: dict = Depends(get_current_user)):
    """Get all supported filter field information."""
    try:
        fields = await enhanced_svc.get_all_supported_fields()
        return fields
    except Exception as e:
        logger.error(f"[screening] Failed to obtain field information: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain field information: {str(e)}")


# Get details of a single field
@router.get("/fields/{field_name}", response_model=Dict[str, Any])
async def get_field_info(field_name: str, user: dict = Depends(get_current_user)):
    """Get details of a specified field"""
    try:
        field_info = await enhanced_svc.get_field_info(field_name)
        if not field_info:
            raise HTTPException(status_code=404, detail=f"Field '{field_name}' does not exist")
        return field_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[screening] Failed to obtain field information: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain field information: {str(e)}")


@router.get("/factor-registry", response_model=Dict[str, Any])
async def get_factor_registry(
    category: Optional[str] = None,
    governance_scope: str = "all",
    screening_only: bool = False,
    user: dict = Depends(get_current_user),
):
    """Get a registry of governed factors for reuse by front-ends, natural language stock picking, and skills."""
    try:
        if governance_scope not in {"all", "p0", "technical"}:
            raise HTTPException(status_code=400, detail="governance_scope Only supports all/p0/technical")
        return factor_registry_svc.list_registry(
            category=category,
            governance_scope=governance_scope,
            screening_only=screening_only,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[screening] Failed to obtain factor registry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to obtain factor registry: {str(e)}")


@router.get("/factor-registry/{factor_id}", response_model=Dict[str, Any])
async def get_factor_registry_item(factor_id: str, user: dict = Depends(get_current_user)):
    """Get the schema/catalog/runtime semantic contract aggregation information of a single factor."""
    try:
        item = factor_registry_svc.get_registry_item(factor_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"factor '{factor_id}' does not exist")
        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[screening] Failed to get factor registry details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get factor registry details: {str(e)}")


@router.get("/presets", response_model=Dict[str, Any])
async def list_screening_presets(user: dict = Depends(get_current_user)):
    """Get the filtering scheme saved by the current user."""
    db = get_mongo_db()
    user_id = str(user["id"])

    try:
        items: List[Dict[str, Any]] = []
        cursor = db.screening_presets.find({"user_id": user_id}).sort("updated_at", -1)
        async for doc in cursor:
            items.append(_serialize_screening_preset(doc))
        return ok({"items": items})
    except Exception as e:
        logger.error(f"[screening] Failed to obtain filtering scheme: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to obtain filtering scheme: {str(e)}")


@router.post("/presets", response_model=Dict[str, Any])
async def create_screening_preset(
    payload: ScreeningPresetPayload,
    user: dict = Depends(get_current_user),
):
    """Create a new filter scheme."""
    db = get_mongo_db()
    user_id = str(user["id"])

    name = payload.name.strip()
    if not name:
        return fail("Filter scheme name cannot be empty", code=400)

    existing = await db.screening_presets.find_one({"user_id": user_id, "name": name})
    if existing:
        return fail("Filter scheme name already exists", code=400)

    now = now_tz()
    preset_doc = {
        "user_id": user_id,
        "name": name,
        "basic_filters": payload.basic_filters,
        "field_filters": payload.field_filters,
        "created_at": now,
        "updated_at": now,
    }

    try:
        result = await db.screening_presets.insert_one(preset_doc)
        preset_doc["_id"] = result.inserted_id
        return ok({"preset": _serialize_screening_preset(preset_doc)}, message="Screening plan saved successfully")
    except Exception as e:
        logger.error(f"[screening] Failed to create filter scheme: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create filter scheme: {str(e)}")


@router.put("/presets/{preset_id}", response_model=Dict[str, Any])
async def update_screening_preset(
    preset_id: str,
    payload: ScreeningPresetPayload,
    user: dict = Depends(get_current_user),
):
    """Update existing filtering scheme."""
    db = get_mongo_db()
    user_id = str(user["id"])

    try:
        oid = ObjectId(preset_id)
    except Exception:
        return fail("Invalid filter scheme ID", code=400)

    existing = await db.screening_presets.find_one({"_id": oid, "user_id": user_id})
    if not existing:
        return fail("Filter scheme does not exist", code=404)

    name = payload.name.strip()
    if not name:
        return fail("Filter scheme name cannot be empty", code=400)

    conflict = await db.screening_presets.find_one({
        "_id": {"$ne": oid},
        "user_id": user_id,
        "name": name,
    })
    if conflict:
        return fail("Filter scheme name already exists", code=400)

    update_data = {
        "name": name,
        "basic_filters": payload.basic_filters,
        "field_filters": payload.field_filters,
        "updated_at": now_tz(),
    }

    try:
        await db.screening_presets.update_one(
            {"_id": oid, "user_id": user_id},
            {"$set": update_data},
        )
        updated = {**existing, **update_data, "_id": oid}
        return ok({"preset": _serialize_screening_preset(updated)}, message="Screening plan updated successfully")
    except Exception as e:
        logger.error(f"[screening] Failed to update filter scheme: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update filter scheme: {str(e)}")


@router.delete("/presets/{preset_id}", response_model=Dict[str, Any])
async def delete_screening_preset(preset_id: str, user: dict = Depends(get_current_user)):
    """Delete filter scheme."""
    db = get_mongo_db()
    user_id = str(user["id"])

    try:
        oid = ObjectId(preset_id)
    except Exception:
        return fail("Invalid filter scheme ID", code=400)

    try:
        result = await db.screening_presets.delete_one({"_id": oid, "user_id": user_id})
        if result.deleted_count == 0:
            return fail("Filter scheme does not exist", code=404)
        return ok({"id": preset_id}, message="Filtering plan deleted successfully")
    except Exception as e:
        logger.error(f"[screening] Failed to delete filter scheme: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete filter scheme: {str(e)}")


# Validate filters
@router.post("/validate", response_model=Dict[str, Any])
async def validate_conditions(conditions: List[ScreeningCondition], user: dict = Depends(get_current_user)):
    """Verify filter validity"""
    try:
        validation_result = await enhanced_svc.validate_conditions(conditions)
        return validation_result
    except Exception as e:
        logger.error(f"[screening] Validation condition failed: {e}")
        raise HTTPException(status_code=500, detail=f"Validation condition failed: {str(e)}")

# Removal of old endpoints with duplicate definitions (keep the logged version)


@router.get("/industries")
async def get_industries(user: dict = Depends(get_current_user)):
    """
    Get a list of all industries available in the database
    According to the data source priority configured in the system, industry classification data is obtained from the data source with the highest priority.
    Returns a list of industries sorted by number of stocks
    """
    try:
        from app.core.database import get_mongo_db
        from app.core.data_source_priority import get_preferred_data_source_async

        db = get_mongo_db()
        collection = db["stock_basic_info"]

        # 🔥 Use unified data source priority management functions
        preferred_source = await get_preferred_data_source_async(market_category="a_shares")

        # Aggregation query: group by industry and count the number of stocks (only query the specified data source)
        pipeline = [
            {
                "$match": {
                    "source": preferred_source,  # 🔥 Only query the highest priority data source
                    "industry": {"$nin": [None, "", "unknown"]}  # Filter empty industries and unknown industries
                }
            },
            {
                "$group": {
                    "_id": "$industry",
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"count": -1}},  # Sort by stock number in descending order
            {
                "$project": {
                    "industry": "$_id",
                    "count": 1,
                    "_id": 0
                }
            }
        ]

        industries = []
        async for doc in collection.aggregate(pipeline):
            # Clean fields to avoid NaN/Inf causing JSON serialization failure
            raw_industry = doc.get("industry")
            safe_industry = ""
            try:
                if raw_industry is None:
                    safe_industry = ""
                elif isinstance(raw_industry, float):
                    if raw_industry != raw_industry or raw_industry in (float("inf"), float("-inf")):
                        safe_industry = ""
                    else:
                        safe_industry = str(raw_industry)
                else:
                    safe_industry = str(raw_industry)
            except Exception:
                safe_industry = ""

            raw_count = doc.get("count", 0)
            safe_count = 0
            try:
                if isinstance(raw_count, float):
                    if raw_count != raw_count or raw_count in (float("inf"), float("-inf")):
                        safe_count = 0
                    else:
                        safe_count = int(raw_count)
                else:
                    safe_count = int(raw_count)
            except Exception:
                safe_count = 0

            industries.append({
                "value": safe_industry,
                "label": safe_industry,
                "count": safe_count,
            })

        logger.info(f"[get_industries] from data source {preferred_source} Return {len(industries)} industries")

        return {
            "industries": industries,
            "total": len(industries),
            "source": preferred_source  # 🔥 Return data source
        }

    except Exception as e:
        logger.error(f"[get_industries] Failed to obtain industry list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
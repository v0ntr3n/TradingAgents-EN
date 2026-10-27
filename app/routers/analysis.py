"""
Stock Analysis API Routing
Enhanced version, supporting functions such as priority, progress tracking, task management, etc.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import time
import uuid
import asyncio

from app.routers.auth_db import get_current_user
from app.services.queue_service import get_queue_service, QueueService
from app.services.analysis_service import get_analysis_service
from app.services.simple_analysis_service import get_simple_analysis_service
from app.services.unified_analysis_service import get_unified_analysis_service
from app.services.websocket_manager import get_websocket_manager
from app.utils.error_formatter import ErrorFormatter
from app.models.analysis import (
    SingleAnalysisRequest, BatchAnalysisRequest, AnalysisParameters,
    AnalysisTaskResponse, AnalysisBatchResponse, AnalysisHistoryQuery,
    AnalysisEngine,
)
from tradingagents.utils.stock_utils import StockUtils, StockMarket, SecurityType
from app.core.database import get_mongo_db
from app.utils.timezone import now_tz
from bson import ObjectId

router = APIRouter()
logger = logging.getLogger("webapi")


def format_http_error_detail(exc: Exception) -> str:
    return ErrorFormatter.format_user_message(str(exc))


# 🔥 Unified result data formatting functions
def normalize_result_data(result_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Unified formatting of analysis result data to ensure that all interfaces return a consistent format

    Main processing:
    1. recommendation Field: Use compliance terms and do not include specific prices
    2. key_points Field: Convert JSON field name to Chinese description
    3. decision Field: supports old and new field names
    4. action Field: Map old terms (buy/sell/hold) to compliance terms (optimistic/cautious/neutral)
    """
    if not result_data:
        return result_data

    # 🔥 Term Mapping: Converting legacy terms into compliant terms
    ACTION_TRANSLATION = {
        'BUY': 'optimistic', 'SELL': 'Prudence', 'HOLD': 'Neutral',
        'buy': 'optimistic', 'sell': 'Prudence', 'hold': 'Neutral',
        'buy': 'optimistic', 'sell': 'Prudence', 'hold': 'Neutral',  # Compatible with old data
        'bullish': 'optimistic', 'Bearish': 'Prudence', 'Neutral': 'Neutral',  # Compatible with old data
        'optimistic': 'optimistic', 'Prudence': 'Prudence', 'Neutral': 'Neutral',  # keep new terms unchanged
    }

    # 1. Process decision field (supports old and new field names)
    decision = result_data.get('decision', {})
    if isinstance(decision, dict):
        # Support new and old field names
        raw_action = decision.get('analysis_view') or decision.get('action')
        # 🔥 Map to compliance terms
        action = ACTION_TRANSLATION.get(raw_action, raw_action) if raw_action else None

        # 🔥 Update the action field in the decision object to the compliance term
        if action and raw_action != action:
            decision['action'] = action
            # If there is an analysis_view field, update it as well
            if 'analysis_view' in decision:
                decision['analysis_view'] = action

        # 🔥 Prefer price_analysis_range (price range) instead of target_price (single value)
        price_range = decision.get('price_analysis_range')
        # If there is no price_analysis_range, target_price is used (but this is a single value and should not be used for price range display)
        if not price_range:
            target_price = decision.get('target_price')
            if target_price:
                logger.warning(f"⚠️ [normalize_result_data] decision There is no price_analysis_range in , only target_price: {target_price}, The frontend will show '-'")
        
        confidence = decision.get('confidence')
        # 🔥 Prioritize getting risk_score (risk manager's assessment result) from decision
        risk_score = decision.get('risk_score')
        risk_level = decision.get('risk_level')
        reasoning = decision.get('reasoning', '')
        
        # 🔥 Debug log: record decision field
        logger.info(f"🔍 [normalize_result_data] decision Field check: price_analysis_range={price_range}, risk_score={risk_score}, target_price={decision.get('target_price')}")

        # 2. Format recommendation (if empty or contains old terms)
        recommendation = result_data.get('recommendation', '')
        if not recommendation or 'investment advice' in recommendation or 'target price' in recommendation or 'buy' in recommendation or 'sell' in recommendation:
            # Regenerate compliant recommendation
            recommendation = f"Analysis point of view:{action}; " if action else ""
            if reasoning and len(reasoning) < 100:
                recommendation += f"Analysis basis:{reasoning}"
            elif reasoning and reasoning != "No analytical reasoning yet":
                short_reasoning = reasoning[:50] + "..." if len(reasoning) > 50 else reasoning
                recommendation += f"Analysis basis:{short_reasoning}"
            result_data['recommendation'] = recommendation

        # 3. Format key_points (if containing JSON field names)
        key_points = result_data.get('key_points', [])
        if key_points and isinstance(key_points, list):
            # Check if it contains a JSON field name (e.g. "analysis_view": "Neutral") 
            if any('"' in str(kp) and ':' in str(kp) for kp in key_points):
                # Regenerate key_points
                new_key_points = []
                if action:
                    new_key_points.append(f"analysis point of view: {action}")
                # 🔥 Only price ranges are shown, not individual values
                if price_range:
                    if isinstance(price_range, (list, tuple)) and len(price_range) == 2:
                        new_key_points.append(f"price analysis range: {price_range[0]}-{price_range[1]}Yuan")
                    else:
                        logger.warning(f"⚠️ [normalize_result_data] price_range Not a valid range format: {price_range}")
                # Do not add target_price to key_points (because this is a single value and does not meet compliance requirements)
                if confidence is not None:
                    new_key_points.append(f"Confidence: {confidence * 100:.1f}%" if confidence <= 1 else f"Confidence: {confidence}%")
                if risk_level:
                    new_key_points.append(f"risk level: {risk_level}")
                if risk_score is not None:
                    new_key_points.append(f"risk score: {risk_score * 100:.1f}%" if risk_score <= 1 else f"risk score: {risk_score}%")

                result_data['key_points'] = new_key_points[:5]

    return result_data


def _has_meaningful_text(value: Any, min_length: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_length


def _summarize_result_completeness(result_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(result_data, dict):
        return {
            "has_summary": False,
            "has_recommendation": False,
            "report_count": 0,
            "has_action": False,
            "has_reasoning": False,
            "has_price_range": False,
            "has_confidence": False,
            "has_risk_score": False,
            "is_complete": False,
        }

    decision = result_data.get("decision") if isinstance(result_data.get("decision"), dict) else {}
    reports = result_data.get("reports") if isinstance(result_data.get("reports"), dict) else {}
    summary = {
        "has_summary": _has_meaningful_text(result_data.get("summary"), 8),
        "has_recommendation": _has_meaningful_text(result_data.get("recommendation"), 8),
        "report_count": len([key for key, value in reports.items() if _has_meaningful_text(value, 10)]),
        "has_action": bool(decision.get("analysis_view") or decision.get("action")),
        "has_reasoning": _has_meaningful_text(decision.get("reasoning"), 10),
        "has_price_range": decision.get("price_analysis_range") is not None,
        "has_confidence": decision.get("confidence") is not None,
        "has_risk_score": decision.get("risk_score") is not None,
    }
    summary["is_complete"] = bool(
        summary["has_summary"] or
        summary["report_count"] > 0 or
        summary["has_action"] or
        summary["has_reasoning"]
    )
    return summary


def _log_result_completeness(source: str, task_id: str, result_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    completeness = _summarize_result_completeness(result_data)
    logger.info(
        f"📊 [RESULT] Source={source} task={task_id} integrity: "
        f"summary={completeness['has_summary']} recommendation={completeness['has_recommendation']} "
        f"reports={completeness['report_count']} action={completeness['has_action']} "
        f"reasoning={completeness['has_reasoning']} price_range={completeness['has_price_range']} "
        f"confidence={completeness['has_confidence']} risk_score={completeness['has_risk_score']} "
        f"complete={completeness['is_complete']}"
    )
    return completeness


def get_market_type_from_symbol(symbol: str) -> str:
    """Get based on stock code market_type

    Args:
        symbol: Stock code

    Returns:
        market_type: "cn" (A shares), "hk" (Hong Kong stocks), "us" (US stocks)
    """
    market = StockUtils.identify_stock_market(symbol)

    # Mapping StockMarket enum to market_type string
    market_type_mapping = {
        StockMarket.CHINA_A: "cn",
        StockMarket.HONG_KONG: "hk",
        StockMarket.US: "us",
        StockMarket.UNKNOWN: "cn"  # Default is China market
    }

    return market_type_mapping.get(market, "cn")


async def get_user_risk_preference(user_id: str) -> str:
    """Get the user s risk preference settings

    Args:
        user_id: User ID

    Returns:
        risk appetite: 'conservative'(conservative) / 'neutral'(Neutral) / 'aggressive'(Radical)
        Return by default 'neutral'
    """
    try:
        db = get_mongo_db()
        users_collection = db["users"]

        # Query user
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if user and "preferences" in user:
            risk_pref = user["preferences"].get("risk_preference", "neutral")
            logger.info(f"📊 Get user {user_id} risk appetite: {risk_pref}")
            return risk_pref

        logger.info(f"📊 User {user_id} No risk preference is set, use default value: neutral")
        return "neutral"
    except Exception as e:
        logger.warning(f"⚠️ Failed to obtain user risk preference: {e}, Use default value: neutral")
        return "neutral"

# Compatibility: retain the original request model
class SingleAnalyzeRequest(BaseModel):
    symbol: str
    parameters: dict = Field(default_factory=dict)

class BatchAnalyzeRequest(BaseModel):
    symbols: List[str]
    parameters: dict = Field(default_factory=dict)
    title: str = Field(default="Batch analysis", description="Batch title")
    description: Optional[str] = Field(None, description="Batch description")

# New API endpoint
@router.post("/single", response_model=Dict[str, Any])
async def submit_single_analysis(
    request: SingleAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """
    Submit a single stock analysis task - supports AB testing

    Select the engine via the request.parameters.engine parameter:
    - v2 (Default): Use new engine WorkflowEngine + v2 agent
    - unified: Use unified engine WorkflowEngine (LangGraph dynamic build)
    - legacy: Disabled (blocked since v3.0, returning 400)
    """
    try:
        logger.info("🎯 Single stock analysis request received")
        logger.info(f"👤 User information: {user}")
        logger.info(f"📊 Request data: {request}")

        # Determine which engine to use
        # v3.0 The V2 engine is used by default from now on (the old version legacy has been discontinued)
        engine_type = AnalysisEngine.V2
        if request.parameters and hasattr(request.parameters, "engine"):
            engine_type = request.parameters.engine
            logger.info(f"🔍 [Engine judgment] Get from request.parameters.engine: {engine_type} (Type: {type(engine_type)})")
            # v3.0 Reject legacy engine
            if engine_type == AnalysisEngine.LEGACY:
                raise HTTPException(
                    status_code=400,
                    detail="[Deactivated] legacy Engine is retired, please use v2 engine instead (request.parameters.engine='v2') . "
                    "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
                )
        else:
            logger.info(f"ℹ️ [Engine judgment] request.parameters If there is no engine field, the default engine is used.: {engine_type.value}")
            if request.parameters:
                logger.info(f"🔍 [Engine judgment] request.parameters Type: {type(request.parameters)}")
                logger.info(f"🔍 [Engine judgment] request.parameters content: {request.parameters}")
                if hasattr(request.parameters, "model_dump"):
                    logger.info(f"🔍 [Engine judgment] request.parameters.model_dump(): {request.parameters.model_dump()}")

        logger.info(f"🔧 [AB test] end use engine: {engine_type.value} (enumeration value: {engine_type})")

        # Select task creation method based on engine type
        # 🔍 Compatibility check: supports both enumerations and string comparisons
        is_v2_engine = (
            engine_type == AnalysisEngine.V2 or 
            (isinstance(engine_type, str) and engine_type.lower() == "v2") or
            (hasattr(engine_type, "value") and engine_type.value == "v2")
        )
        
        if is_v2_engine:
            logger.info(f"✅ [Engine judgment] Confirmed as v2 engine, using unified task service")
            # v2 Engine: Created using Unified Task Service UnifiedAnalysisTask
            from app.services.task_analysis_service import get_task_analysis_service
            from app.models.analysis import AnalysisTaskType
            from app.models.user import PyObjectId

            task_service = get_task_analysis_service()

            # Prepare task parameters - expand the contents of parameters to the top level
            symbol = request.get_symbol()

            # 🔥 Fix: Automatic recognition of market type based on ticker
            market_type = get_market_type_from_symbol(symbol)
            logger.info(f"📊 [single stock analysis] stocks {symbol} identified as market: {market_type}")

            task_params = {
                "symbol": symbol,
                "stock_code": symbol,
                "market_type": market_type,  # 🔑 Automatically identify market types based on stock symbols
            }

            # Merge all fields of request.parameters into task_params
            if request.parameters:
                params_dict = request.parameters.model_dump()
                # Remove the engine field (this is used by the routing layer, not a task parameter)
                params_dict.pop("engine", None)
                task_params.update(params_dict)

            # If the user specifies market_type in parameters, the user-specified
            if request.parameters and hasattr(request.parameters, 'market_type') and request.parameters.market_type:
                task_params["market_type"] = request.parameters.market_type
                logger.info(f"📊 [single stock analysis] Use user-specified market type: {request.parameters.market_type}")

            # 🔥 ETF Routing: Use the ETF analysis process when the user selects an ETF or the symbol identifies as an ETF
            user_market = (request.parameters and getattr(request.parameters, 'market_type', None)) or market_type
            sec_type = StockUtils.identify_security_type(symbol)
            if user_market == "ETF" or sec_type == SecurityType.FUND:
                task_type = AnalysisTaskType.ETF_ANALYSIS
                task_params["market_type"] = "cn"  # ETF Still belongs to the A-share market
                task_params["selected_analysts"] = ["etf", "market", "news"]  # ETF Process Fixed Analyst
                logger.info(f"📊 [single stock analysis] {symbol} Identify as an ETF, use the ETF analysis process")
            else:
                task_type = AnalysisTaskType.STOCK_ANALYSIS

            logger.info(f"📦 v2 Task parameters: {task_params}")

            # 🔥 Read risk preference settings from user preferences
            preference_type = await get_user_risk_preference(user["id"])
            logger.info(f"📊 [single stock analysis] Use user risk preferences: {preference_type}")

            # Create unified task (not executed)
            task = await task_service.create_task(
                user_id=PyObjectId(user["id"]),
                task_type=task_type,
                task_params=task_params,
                engine_type="auto",  # Automatic engine selection
                preference_type=preference_type  # 🔥 Use user preferences
            )

            # 🔑 Key: Create task status in memory at the same time (for fast querying)
            from app.services.memory_state_manager import get_memory_state_manager
            memory_manager = get_memory_state_manager()
            await memory_manager.create_task(
                task_id=task.task_id,
                user_id=user["id"],
                stock_code=request.get_symbol(),
                parameters=task_params,
                stock_name=None  # Can be added later
            )
            logger.info(f"✅ [v2 engine] The task has been created in memory: {task.task_id}")

            # 🔥 v2 Engine: Submit tasks to the queue to be processed by Worker
            from app.services.queue_service import get_queue_service
            queue_service = get_queue_service()
            
            # Prepare queue parameters
            queue_params = {
                "engine": "v2",  # Marked as v2 engine
                "task_id": task.task_id,
                "symbol": symbol,
                "stock_code": symbol,
                "user_id": user["id"],
                **task_params  # Contains all task parameters
            }
            
            # Submit to queue
            await queue_service.enqueue_task(
                user_id=user["id"],
                symbol=symbol,
                params=queue_params,
                batch_id=None,  # Single stock analysis without batches ID
                task_id=task.task_id  # Use generated tasks ID
            )
            logger.info(f"✅ [v2 engine] Task has been submitted to the queue: {task.task_id}")

            result = {
                "task_id": task.task_id,  # Use UUID task_id, not ObjectId
                "status": task.status.value,
                "created_at": task.created_at.isoformat() if task.created_at else None
            }
            task_id = task.task_id  # Use UUID task_id
            user_id = user["id"]
        else:
            # unified Engine: Use simple_analysis_service to create tasks and add them to the queue
            #  (legacy The engine has intercepted and thrown 400 in front; unified actually uses WorkflowEngine, which belongs to the new engine path)
            legacy_service = get_simple_analysis_service()
            result = await legacy_service.create_analysis_task(user["id"], request)
            # 🔥 Note: create_analysis_task has internally submitted the task to the queue and does not require background execution.

        # 🔥 Tasks for all engines have been submitted to the queue and processed by the Worker process
        # No more background tasks in the API process
        logger.info(f"✅ Analysis task has been submitted to the queue: {result}")

        return {
            "success": True,
            "data": result,
            "message": f"The analysis task has been submitted to the queue and is waiting for Worker processing (engine: {engine_type.value})"
        }
    except Exception as e:
        logger.error(f"❌ Failed to submit single stock analysis task: {e}")
        raise HTTPException(status_code=400, detail=format_http_error_detail(e))


# Test routing - Verify that the route is registered correctly
@router.get("/test-route")
async def test_route():
    """Test if routing is working"""
    logger.info("🧪 The test route is called!")
    return {"message": "Test routing works fine", "timestamp": time.time()}


# =============================================================================
# Pre-analysis interface
# =============================================================================

# Cache layer/non-real API data source type, not considered a usable data source
_CACHE_SOURCE_TYPES = {"local", "mongodb", "local_file"}


@router.get("/precheck", response_model=Dict[str, Any])
async def precheck_analysis(
    symbol: Optional[str] = Query(None, description="Stock symbol to analyze (optional)"),
    user: dict = Depends(get_current_user),
):
    """
    Pre-check before analysis submission: Check the data source configuration, basic data synchronization status, and whether the target stock exists.

    Return can_submit=False , the front end should prevent submission and guide the user to complete the corresponding steps first.
    """
    from app.services.config_service import config_service

    try:
        # ── 1. Check data source configuration ──
        config = await config_service.get_system_config()
        enabled_real_sources: List[str] = []
        if config and config.data_source_configs:
            for ds in config.data_source_configs:
                if ds.enabled and ds.type not in _CACHE_SOURCE_TYPES:
                    enabled_real_sources.append(ds.type)

        if not enabled_real_sources:
            return {
                "can_submit": False,
                "reason": "no_datasource",
                "message": "The available data sources have not been configured yet. Please complete the data source configuration first.",
                "redirect": "/settings/config",
                "redirect_tab": "datasource",
                "details": {"enabled_real_sources": []},
            }

        # ── 2. Check basic data synchronization ──
        db = get_mongo_db()
        basics_count = await db["stock_basic_info"].count_documents({})
        if basics_count == 0:
            return {
                "can_submit": False,
                "reason": "no_basics",
                "message": "The basic stock data has not been synchronized, please perform data synchronization first.",
                "redirect": "/settings/sync",
                "details": {
                    "enabled_real_sources": enabled_real_sources,
                    "basics_count": 0,
                },
            }

        # ── 3. Check whether the target stock exists (if symbol is passed) ──
        target_exists = True
        if symbol:
            sym = symbol.strip()
            # Matches both code and symbol fields
            query = {"$or": [{"code": sym}, {"symbol": sym}]}
            doc = await db["stock_basic_info"].find_one(query)
            target_exists = doc is not None

        if symbol and not target_exists:
            return {
                "can_submit": False,
                "reason": "stock_not_found",
                "message": f"stocks {symbol} The basic data of is not synchronized, please synchronize the stock data first",
                "redirect": "/settings/sync",
                "details": {
                    "enabled_real_sources": enabled_real_sources,
                    "basics_count": basics_count,
                    "symbol": symbol,
                },
            }

        # ── 4. All passed ──
        return {
            "can_submit": True,
            "reason": "ok",
            "message": "Data is ready to start analysis",
            "details": {
                "enabled_real_sources": enabled_real_sources,
                "basics_count": basics_count,
                "symbol": symbol,
                "target_exists": target_exists,
            },
        }
    except Exception as e:
        logger.error(f"❌ Analysis preflight failed: {e}", exc_info=True)
        # Failure of the preflight itself does not prevent analysis (downgrade), leaving subsequent worker verification behind.
        return {
            "can_submit": True,
            "reason": "precheck_error",
            "message": "The pre-check service is abnormal and the submission has been released.",
            "details": {"error": str(e)},
        }


@router.get("/tasks/{task_id}/status", response_model=Dict[str, Any])
async def get_task_status_new(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Get analysis task status (new version of asynchronous implementation)
    
    Query priority:
    1. MongoDB (unified_analysis_tasks) - Real data source, Worker process will update here
    2. MongoDB (analysis_tasks) - Legacy tasks
    3. Memory state manager - cache only (in-process, separate for Worker and API processes)
    """
    try:
        logger.info(f"🔍 [NEW ROUTE] Enter the new version status to query routing: {task_id}")
        logger.info(f"👤 [NEW ROUTE] User: {user}")

        # 🔥 Query from MongoDB first (real data source, Worker process will update here)
        # Because the Worker process and the API process are separate, the memory state manager is not shared
        from app.core.database import get_mongo_db
        from bson import ObjectId
        db = get_mongo_db()

        # First try to find (v2 engine tasks) from unified_analysis_tasks collection
        unified_task = await db.unified_analysis_tasks.find_one({"task_id": task_id})
        if unified_task:
            logger.info(f"✅ [STATUS] Find tasks from unified_analysis_tasks: {task_id}")

            # 🔑 Key: Distinguish between step names and messages
            # current_step Stored are short step names (e.g. "market analyst") 
            # message Stored is a detailed description (such as "📈 Market analysts are analyzing technical indicators and market trends...") 
            current_step_name = unified_task.get("current_step", "")
            current_step_description = unified_task.get("message", current_step_name)

            # Get the status and do compatibility mapping (the front-end expects 'running' instead of 'processing') 
            backend_status = unified_task.get("status", "pending")
            # 🔥 Status mapping:processing → running, cancelled → cancelled, failed → failed
            if backend_status == "processing":
                frontend_status = "running"
            elif backend_status == "cancelled":
                frontend_status = "cancelled"  # Keep canceled status
            else:
                frontend_status = backend_status

            # 🔧 Compute time estimate (follows old version logic)
            from app.services.progress.tracker import RedisProgressTracker
            from datetime import datetime, timezone

            # Get task parameters
            task_params = unified_task.get("task_params", {})
            progress_pct = unified_task.get("progress", 0)
            start_time = unified_task.get("started_at")
            end_time = unified_task.get("completed_at")

            # Calculation time estimate
            elapsed_time = 0
            remaining_time = 0
            estimated_total_time = 0

            if end_time:
                # Task completed, using final execution time
                from dateutil import parser

                if isinstance(start_time, str):
                    try:
                        start_time = parser.parse(start_time)
                    except Exception as e:
                        logger.warning(f"⚠️ Unable to parse start time: {start_time}, Error: {e}")
                        start_time = None

                if isinstance(end_time, str):
                    try:
                        end_time = parser.parse(end_time)
                    except Exception as e:
                        logger.warning(f"⚠️ Unable to parse end time: {end_time}, Error: {e}")
                        end_time = None

                if start_time and end_time:
                    # Make sure the time zone matches
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=timezone.utc)
                    if end_time.tzinfo is None:
                        end_time = end_time.replace(tzinfo=timezone.utc)

                    elapsed_time = (end_time - start_time).total_seconds()
                    estimated_total_time = elapsed_time  # The total time for completed tasks is the elapsed time
                    remaining_time = 0

            elif start_time:
                # Task in progress
                if isinstance(start_time, str):
                    try:
                        from dateutil import parser
                        start_time = parser.parse(start_time)
                    except Exception as e:
                        logger.warning(f"⚠️ Unable to parse start time: {start_time}, Error: {e}")
                        start_time = None

                if start_time:
                    # Make sure to use local time (with time zone)
                    current_time = datetime.now(timezone.utc)

                    # Make sure start_time has time zone information
                    if start_time.tzinfo is None:
                        # Assume the time in the database is UTC
                        start_time = start_time.replace(tzinfo=timezone.utc)

                    # Calculate elapsed time
                    elapsed_time = (current_time - start_time).total_seconds()

                    # 🔑 Key: Use the total duration estimated when the task is created (fixed value), rather than dynamically calculating based on progress
                    # Get analyst list and research depth
                    analysts = task_params.get("selected_analysts", [])
                    research_depth = task_params.get("research_depth", "fast")
                    llm_model = task_params.get("quick_analysis_model", "dashscope")
                    llm_provider = llm_model.split("-")[0] if llm_model else "dashscope"

                    # Use the internal method of RedisProgressTracker to calculate the baseline time (estimated total time)
                    temp_tracker = RedisProgressTracker(
                        task_id="temp",
                        analysts=analysts,
                        research_depth=research_depth,
                        llm_provider=llm_provider
                    )
                    estimated_total_time = temp_tracker._get_base_total_time()

                    # Estimated remaining = Estimated total time - elapsed time
                    remaining_time = max(0, estimated_total_time - elapsed_time)

            # 🔑 Try to get detailed step information from Redis
            steps_info = []
            completed_steps = []
            try:
                from app.core.redis_client import get_redis_service, RedisKeys

                redis_service = get_redis_service()
                # 🔥 Check if Redis has been initialized
                try:
                    # Try to access the redis property, an exception will be thrown if it is not initialized
                    _ = redis_service.redis
                except RuntimeError as redis_err:
                    # Redis Not initialized, skips Redis query, but does not affect the main process
                    logger.debug(f"📊 [STATUS] Redis Not initialized, skip step information query: {redis_err}")
                else:
                    # Redis Initialized, safe to query
                    progress_key = RedisKeys.TASK_PROGRESS.format(task_id=task_id)
                    progress_data = await redis_service.get_json(progress_key)

                    if progress_data and "steps" in progress_data:
                        steps_info = progress_data["steps"]
                        # Extract completed step names
                        completed_steps = [
                            step["name"] for step in steps_info
                            if step.get("status") == "completed"
                        ]
                        logger.info(f"📊 [STATUS] Get step information from Redis: {len(steps_info)}steps, {len(completed_steps)}completed")
            except Exception as e:
                # Other exceptions (such as connection errors, etc.) only record warnings and do not affect the main process.
                logger.debug(f"📊 [STATUS] Failed to obtain step information from Redis (does not affect the main process): {e}")

            # 🔥 Constructing messages: determining display content based on status
            error_message = unified_task.get("error_message")
            if frontend_status == "cancelled":
                # Cancellation status: Show cancellation message
                display_message = error_message or "The task has been canceled by the user"
            elif frontend_status == "failed":
                # Failure status: Show error message
                display_message = error_message or "Task execution failed"
            elif frontend_status == "completed":
                # completion status
                display_message = "Analysis completed"
            else:
                # Running: displays the current step
                display_message = current_step_description or f"Task{frontend_status}in..."

            # Construct status response (unified task format, compatible with field names expected by the front end)
            status_data = {
                "task_id": unified_task.get("task_id"),
                "user_id": str(unified_task.get("user_id", "")),
                "status": frontend_status,  # Use the mapped state
                "progress": progress_pct,
                "message": display_message,  # 🔥 Use optimized messages

                # 🔑 Key: Distinguish between step names and descriptions
                "current_step_name": current_step_name,  # ✅ A short step name (e.g. "market analyst") 
                "current_step_description": current_step_description,  # ✅ Detailed description (e.g. "📈 Market analysts are analyzing...") 
                "current_step": current_step_name,  # Keep compatibility

                "start_time": unified_task.get("started_at"),
                "end_time": end_time,
                "elapsed_time": elapsed_time,  # ✅ Use calculated value
                "remaining_time": remaining_time,  # ✅ Use calculated value
                "estimated_total_time": estimated_total_time,  # ✅ Use calculated value
                "symbol": task_params.get("symbol") or task_params.get("stock_code"),
                "stock_code": task_params.get("stock_code") or task_params.get("symbol"),
                "stock_symbol": task_params.get("symbol") or task_params.get("stock_code"),
                "task_type": unified_task.get("task_type"),
                "source": "unified_tasks",  # Mark data sources

                # 🆕 Add step information
                "steps": steps_info,  # Detailed information on all steps
                "completed_steps": completed_steps,  # List of completed step names

                # Add result data (if any)
                "result_data": unified_task.get("result"),
                "error_message": error_message,  # 🔥 Keep original error message
                "parameters": task_params,  # Add parameter information
                "execution_time": unified_task.get("execution_time"),
                "tokens_used": unified_task.get("tokens_used"),
            }

            # 🔥 Format result_data if present
            if status_data.get("result_data"):
                logger.info(f"📊 [STATUS] ========== unified_tasks result_data Before formatting ==========")
                logger.info(f"📊 [STATUS] recommendation: {status_data['result_data'].get('recommendation', '')[:200]}")
                logger.info(f"📊 [STATUS] key_points: {status_data['result_data'].get('key_points', [])[:3]}")

                status_data["result_data"] = normalize_result_data(status_data["result_data"])

                logger.info(f"📊 [STATUS] ========== unified_tasks result_data After formatting ==========")
                logger.info(f"📊 [STATUS] recommendation: {status_data['result_data'].get('recommendation', '')[:200]}")
                logger.info(f"📊 [STATUS] key_points: {status_data['result_data'].get('key_points', [])[:3]}")

            logger.info(f"📊 [STATUS] return status: status={status_data['status']}, progress={status_data['progress']}, step={status_data['current_step_name']}")

            return {
                "success": True,
                "data": status_data,
                "message": "Task status obtained successfully"
            }

        # Then find (legacy tasks) from the analysis_tasks collection
        task_result = await db.analysis_tasks.find_one({"task_id": task_id})

        if task_result:
                logger.info(f"✅ [STATUS] Find tasks from analysis_tasks: {task_id}")

                # Construct status response (ongoing task)
                status = task_result.get("status", "pending")
                progress = task_result.get("progress", 0)
                current_step = task_result.get("current_step", "")
                message = task_result.get("message", f"Task{status}in...")

                # Compute time information
                from datetime import datetime
                start_time = task_result.get("started_at") or task_result.get("created_at")

                # If it is a string, convert to datetime
                if isinstance(start_time, str):
                    try:
                        from dateutil import parser
                        start_time = parser.parse(start_time)
                    except Exception as e:
                        logger.warning(f"⚠️ Unable to parse start time: {start_time}, Error: {e}")
                        start_time = None

                current_time = datetime.utcnow()
                elapsed_time = 0
                estimated_total_time = task_result.get("estimated_total_time", 225.0)  # Default 225 seconds
                remaining_time = 0

                if start_time:
                    # Make sure start_time is a naive datetime (remove time zone information)
                    if start_time.tzinfo is not None:
                        start_time = start_time.replace(tzinfo=None)
                    elapsed_time = (current_time - start_time).total_seconds()

                    # Estimate remaining time based on progress
                    if progress > 0 and progress < 100:
                        remaining_time = max(0, estimated_total_time - elapsed_time)

                # 🔥 Status mapping:processing → running (Frontend expects running)
                frontend_status = "running" if status == "processing" else status

                # Get parameter information
                parameters = task_result.get("parameters", {})

                status_data = {
                    "task_id": task_id,
                    "user_id": str(task_result.get("user_id", "")),
                    "status": frontend_status,
                    "progress": progress,
                    "message": message,
                    "current_step_name": current_step,
                    "current_step_description": message,
                    "current_step": current_step,
                    "start_time": start_time,
                    "end_time": task_result.get("completed_at"),
                    "elapsed_time": elapsed_time,
                    "remaining_time": remaining_time,
                    "estimated_total_time": estimated_total_time,
                    "symbol": task_result.get("symbol") or task_result.get("stock_code"),
                    "stock_code": task_result.get("symbol") or task_result.get("stock_code"),
                    "stock_symbol": task_result.get("symbol") or task_result.get("stock_code"),
                    "task_type": "stock_analysis",
                    "source": "analysis_tasks",  # Mark data sources
                    "steps": [],
                    "completed_steps": [],
                    "result_data": None,
                    "error_message": task_result.get("error_message"),
                    "parameters": parameters,
                    "execution_time": task_result.get("execution_time", 0.0),
                    "tokens_used": task_result.get("tokens_used", 0)
                }

                return {
                    "success": True,
                    "data": status_data,
                    "message": "Task status obtained successfully"
                }

        # If not found in analysis_tasks, then search from the analysis_reports collection (completed tasks)
        mongo_result = await db.analysis_reports.find_one({"task_id": task_id})

        if mongo_result:
            logger.info(f"✅ [STATUS] Find tasks from analysis_reports: {task_id}")

            # Construct status response (simulate completed tasks)
            # Calculate time information for completed tasks
            start_time = mongo_result.get("created_at")
            end_time = mongo_result.get("updated_at")
            elapsed_time = 0
            if start_time and end_time:
                elapsed_time = (end_time - start_time).total_seconds()

            status_data = {
                "task_id": task_id,
                "status": "completed",
                "progress": 100,
                "message": "Analysis completed (restore from history)",
                "current_step": "completed",
                "start_time": start_time,
                "end_time": end_time,
                "elapsed_time": elapsed_time,
                "remaining_time": 0,
                "estimated_total_time": elapsed_time,  # The total time for completed tasks is the elapsed time
                "stock_code": mongo_result.get("stock_symbol"),
                "stock_symbol": mongo_result.get("stock_symbol"),
                "analysts": mongo_result.get("analysts", []),
                "research_depth": mongo_result.get("research_depth", "fast"),
                "source": "mongodb_reports"  # Mark data sources
            }

            return {
                "success": True,
                "data": status_data,
                "message": "Task status obtained successfully (restored from history)"
            }
        else:
            logger.warning(f"❌ [STATUS] MongoDB Not found in: {task_id} trace={task_id}")
            raise HTTPException(status_code=404, detail="Task does not exist")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail=format_http_error_detail(e))

@router.get("/tasks/{task_id}/result", response_model=Dict[str, Any])
async def get_task_result(
    task_id: str,
    include_state: bool = Query(False, description="Whether to include the complete workflow status (for debugging)"),
    include_detailed: bool = Query(False, description="Whether to include detailed analysis data (for debugging)"),
    user: dict = Depends(get_current_user)
):
    """Get analysis task results
    
    By default, only necessary fields are returned (reports, decision, summary etc.), excluding state and detailed_analysis.
    For complete data, query parameters include_state=true&include_detailed=true Get.
    """
    try:
        logger.info(f"🔍 [RESULT] Get task results: {task_id}")
        logger.info(f"👤 [RESULT] User: {user}")

        analysis_service = get_simple_analysis_service()
        task_status = await analysis_service.get_task_status(task_id)

        result_data = None

        if task_status and task_status.get('status') == 'completed':
            # Get result data from memory
            result_data = task_status.get('result_data')
            logger.info(f"📊 [RESULT] Get result data from memory")

            # 🔍 Debugging: Inspecting in-memory data structures
            if result_data:
                logger.info(f"📊 [RESULT] ========== Before formatting ==========")
                logger.info(f"📊 [RESULT] memory data key: {list(result_data.keys())}")
                logger.info(f"📊 [RESULT] recommendation: {result_data.get('recommendation', '')[:200]}")
                logger.info(f"📊 [RESULT] key_points: {result_data.get('key_points', [])[:3]}")
                if result_data.get('decision'):
                    decision = result_data['decision']
                    logger.info(f"📊 [RESULT] decision: action={decision.get('action')}, analysis_view={decision.get('analysis_view')}, target_price={decision.get('target_price')}, price_analysis_range={decision.get('price_analysis_range')}")

                # 🔥 Uniformly formatted result data
                result_data = normalize_result_data(result_data)

                completeness = _log_result_completeness("memory", task_id, result_data)

                logger.info(f"📊 [RESULT] ========== After formatting ==========")
                logger.info(f"📊 [RESULT] recommendation: {result_data.get('recommendation', '')[:200]}")
                logger.info(f"📊 [RESULT] key_points: {result_data.get('key_points', [])[:3]}")

                if not completeness["is_complete"]:
                    logger.warning(f"⚠️ [RESULT] The result_data in the memory is incomplete. Continue to roll back to query the persistent results.: {task_id}")
                    result_data = None
            else:
                logger.warning(f"⚠️ [RESULT] result_data in memory is empty")

        if not result_data:
            # Not found in memory, try to find it from MongoDB
            logger.info(f"📊 [RESULT] Not found in memory, try to find from MongoDB: {task_id}")

            from app.core.database import get_mongo_db
            db = get_mongo_db()

            # 🔧 First find (v2 engine tasks) from unified_analysis_tasks collection
            unified_task = await db.unified_analysis_tasks.find_one({"task_id": task_id})
            if unified_task and unified_task.get("result"):
                logger.info(f"✅ [RESULT] Find results from unified_analysis_tasks: {task_id}")

                result = unified_task["result"]
                task_params = unified_task.get("task_params", {})

                # Calculate execution time
                execution_time = 0
                completed_at = unified_task.get("completed_at")
                started_at = unified_task.get("started_at")
                if completed_at and started_at:
                    try:
                        # If it is a datetime object, subtract directly
                        if hasattr(completed_at, 'timestamp') and hasattr(started_at, 'timestamp'):
                            execution_time = (completed_at - started_at).total_seconds()
                        # If it is a string, parse it first
                        elif isinstance(completed_at, str) and isinstance(started_at, str):
                            from dateutil import parser
                            completed_dt = parser.parse(completed_at)
                            started_dt = parser.parse(started_at)
                            execution_time = (completed_dt - started_dt).total_seconds()
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to calculate execution time: {e}")
                        execution_time = 0

                # Construct result data (compatible with the format expected by the front end)
                result_data = {
                    "analysis_id": unified_task.get("task_id"),  # Use task_id as analysis_id
                    "stock_symbol": task_params.get("symbol") or task_params.get("stock_code"),
                    "stock_code": task_params.get("stock_code") or task_params.get("symbol"),
                    "analysis_date": task_params.get("analysis_date"),
                    "summary": result.get("summary", ""),
                    "recommendation": result.get("recommendation", ""),
                    "confidence_score": result.get("confidence_score", 0.0),
                    "risk_level": result.get("risk_level", "medium"),
                    "key_points": result.get("key_points", []),
                    "execution_time": execution_time,
                    "tokens_used": result.get("tokens_used", 0),
                    "analysts": task_params.get("selected_analysts", []),
                    "research_depth": task_params.get("research_depth", "fast"),
                    "reports": result.get("reports", {}),
                    "created_at": unified_task.get("created_at"),
                    "updated_at": unified_task.get("completed_at"),
                    "status": "completed",
                    "decision": result.get("decision", {}),
                    "source": "unified_tasks"  # Mark data sources
                }
                
                # 🔥 Optional fields: decide whether to include them based on query parameters
                if include_state:
                    result_data["state"] = result.get("state", {})
                if include_detailed:
                    result_data["detailed_analysis"] = result.get("detailed_analysis", {})

                logger.info(f"📊 [RESULT] ========== unified_tasks Before formatting ==========")
                logger.info(f"📊 [RESULT] recommendation: {result_data.get('recommendation', '')[:200]}")
                logger.info(f"📊 [RESULT] key_points: {result_data.get('key_points', [])[:3]}")
                if result_data.get('decision'):
                    decision = result_data['decision']
                    logger.info(f"📊 [RESULT] decision: action={decision.get('action')}, analysis_view={decision.get('analysis_view')}, target_price={decision.get('target_price')}, price_analysis_range={decision.get('price_analysis_range')}")

                # 🔥 Uniformly formatted result data
                result_data = normalize_result_data(result_data)
                completeness = _log_result_completeness("unified_tasks", task_id, result_data)

                logger.info(f"📊 [RESULT] ========== unified_tasks After formatting ==========")
                logger.info(f"📊 [RESULT] recommendation: {result_data.get('recommendation', '')[:200]}")
                logger.info(f"📊 [RESULT] key_points: {result_data.get('key_points', [])[:3]}")

                # 🔑 Defensive check: If unified_analysis_tasks data is incomplete,
                # Fall back to analysis_reports (complete data may have been saved first)
                if not completeness["is_complete"]:
                    logger.warning(f"⚠️ [RESULT] unified_analysis_tasks Incomplete data, return query analysis_reports: {task_id}")
                    result_data = None

            # If not found in unified_analysis_tasks or the data is incomplete, then search from the analysis_reports collection
            if not result_data:
                mongo_result = await db.analysis_reports.find_one({"task_id": task_id})

                if not mongo_result:
                    # Compatible with old data: old records may not have task_id, but analysis_id exists in analysis_tasks.result
                    tasks_doc_for_id = await db.analysis_tasks.find_one({"task_id": task_id}, {"result.analysis_id": 1})
                    analysis_id = tasks_doc_for_id.get("result", {}).get("analysis_id") if tasks_doc_for_id else None
                    if analysis_id:
                        logger.info(f"🔎 [RESULT] Search by analysis_id analysis_reports: {analysis_id}")
                        mongo_result = await db.analysis_reports.find_one({"analysis_id": analysis_id})
            else:
                # If results are found from unified_analysis_tasks, no query is needed analysis_reports
                mongo_result = None

            if mongo_result:
                logger.info(f"✅ [RESULT] Find results from MongoDB: {task_id}")

                # Use data structures in MongoDB directly (consistent with web directories)
                result_data = {
                    "analysis_id": mongo_result.get("analysis_id"),
                    "stock_symbol": mongo_result.get("stock_symbol"),
                    "stock_code": mongo_result.get("stock_symbol"),  # Compatibility
                    "analysis_date": mongo_result.get("analysis_date"),
                    "summary": mongo_result.get("summary", ""),
                    "recommendation": mongo_result.get("recommendation", ""),
                    "confidence_score": mongo_result.get("confidence_score", 0.0),
                    "risk_level": mongo_result.get("risk_level", "medium"),
                    "key_points": mongo_result.get("key_points", []),
                    "execution_time": mongo_result.get("execution_time", 0),
                    "tokens_used": mongo_result.get("tokens_used", 0),
                    "analysts": mongo_result.get("analysts", []),
                    "research_depth": mongo_result.get("research_depth", "fast"),
                    "reports": mongo_result.get("reports", {}),
                    "created_at": mongo_result.get("created_at"),
                    "updated_at": mongo_result.get("updated_at"),
                    "status": mongo_result.get("status", "completed"),
                    "decision": mongo_result.get("decision", {}),
                    "source": "mongodb"  # Mark data sources
                }

                logger.info(f"📊 [RESULT] ========== MongoDB Before formatting ==========")
                logger.info(f"📊 [RESULT] recommendation: {result_data.get('recommendation', '')[:200]}")
                logger.info(f"📊 [RESULT] key_points: {result_data.get('key_points', [])[:3]}")
                if result_data.get('decision'):
                    decision = result_data['decision']
                    logger.info(f"📊 [RESULT] decision: action={decision.get('action')}, analysis_view={decision.get('analysis_view')}")

                # 🔥 Uniformly formatted result data
                result_data = normalize_result_data(result_data)
                _log_result_completeness("mongodb", task_id, result_data)

                logger.info(f"📊 [RESULT] ========== MongoDB After formatting ==========")
                logger.info(f"📊 [RESULT] recommendation: {result_data.get('recommendation', '')[:200]}")
                logger.info(f"📊 [RESULT] key_points: {result_data.get('key_points', [])[:3]}")
            else:
                # Bottom line: the result field in the analysis_tasks collection
                tasks_doc = await db.analysis_tasks.find_one(
                    {"task_id": task_id},
                    {"result": 1, "symbol": 1, "stock_code": 1, "created_at": 1, "completed_at": 1}
                )
                if tasks_doc and tasks_doc.get("result"):
                    r = tasks_doc["result"] or {}
                    logger.info("✅ [RESULT] Find results from analysis_tasks.result")
                    # Get stock code (priority use symbol)
                    symbol = (tasks_doc.get("symbol") or tasks_doc.get("stock_code") or
                             r.get("stock_symbol") or r.get("stock_code"))
                    # 🔥 Clean duplicate data in reports (if present)
                    reports_raw = r.get("reports", {})
                    cleaned_reports = {}
                    if isinstance(reports_raw, dict):
                        for key, value in reports_raw.items():
                            # Skip structured_reports (if present to avoid duplication)
                            if key != "structured_reports":
                                cleaned_reports[key] = value
                    
                    result_data = {
                        "analysis_id": r.get("analysis_id"),
                        "stock_symbol": symbol,
                        "stock_code": symbol,  # Compatible fields
                        "analysis_date": r.get("analysis_date"),
                        "summary": r.get("summary", ""),
                        "recommendation": r.get("recommendation", ""),
                        "confidence_score": r.get("confidence_score", 0.0),
                        "risk_level": r.get("risk_level", "medium"),
                        "key_points": r.get("key_points", []),
                        "execution_time": r.get("execution_time", 0),
                        "tokens_used": r.get("tokens_used", 0),
                        "analysts": r.get("analysts", []),
                        "research_depth": r.get("research_depth", "fast"),
                        "reports": cleaned_reports,  # 🔥 Use the cleaned reports
                        "created_at": tasks_doc.get("created_at"),
                        "updated_at": tasks_doc.get("completed_at"),
                        "status": r.get("status", "completed"),
                        "decision": r.get("decision", {}),
                        "source": "analysis_tasks"  # Data source tag
                    }
                    
                    # 🔥 Optional fields: decide whether to include them based on query parameters
                    if include_state:
                        result_data["state"] = r.get("state", {})
                    if include_detailed:
                        result_data["detailed_analysis"] = r.get("detailed_analysis", {})

                    logger.info(f"📊 [RESULT] ========== analysis_tasks Before formatting ==========")
                    logger.info(f"📊 [RESULT] recommendation: {result_data.get('recommendation', '')[:200]}")
                    logger.info(f"📊 [RESULT] key_points: {result_data.get('key_points', [])[:3]}")
                    if result_data.get('decision'):
                        decision = result_data['decision']
                        logger.info(f"📊 [RESULT] decision: action={decision.get('action')}, analysis_view={decision.get('analysis_view')}")

                    # 🔥 Uniformly formatted result data
                    result_data = normalize_result_data(result_data)
                    _log_result_completeness("analysis_tasks", task_id, result_data)

                    logger.info(f"📊 [RESULT] ========== analysis_tasks After formatting ==========")
                    logger.info(f"📊 [RESULT] recommendation: {result_data.get('recommendation', '')[:200]}")
                    logger.info(f"📊 [RESULT] key_points: {result_data.get('key_points', [])[:3]}")

        if not result_data:
            logger.warning(f"❌ [RESULT] No results found for all data sources: {task_id}")
            raise HTTPException(status_code=404, detail="Analysis result does not exist")

        if not result_data:
            raise HTTPException(status_code=404, detail="Analysis result does not exist")

        # Process reports field - if there is no reports field, first try to load from the file system, secondly extract from the state
        if 'reports' not in result_data or not result_data['reports']:
            import os
            from pathlib import Path

            stock_symbol = result_data.get('stock_symbol') or result_data.get('stock_code')
            # analysis_date It may be a date or timestamp string. Only the date part is taken here.
            analysis_date_raw = result_data.get('analysis_date')
            analysis_date = str(analysis_date_raw)[:10] if analysis_date_raw else None

            loaded_reports = {}
            try:
                # 1) Attempts to read from the location specified by the environment variable TRADINGAGENTS_RESULTS_DIR
                base_env = os.getenv('TRADINGAGENTS_RESULTS_DIR')
                project_root = Path.cwd()
                if base_env:
                    base_path = Path(base_env)
                    if not base_path.is_absolute():
                        base_path = project_root / base_env
                else:
                    base_path = project_root / 'results'

                candidate_dirs = []
                if stock_symbol and analysis_date:
                    candidate_dirs.append(base_path / stock_symbol / analysis_date / 'reports')
                # 2) Compatible with other save paths
                if stock_symbol and analysis_date:
                    candidate_dirs.append(project_root / 'data' / 'analysis_results' / stock_symbol / analysis_date / 'reports')
                    candidate_dirs.append(project_root / 'data' / 'analysis_results' / 'detailed' / stock_symbol / analysis_date / 'reports')

                for d in candidate_dirs:
                    if d.exists() and d.is_dir():
                        for f in d.glob('*.md'):
                            try:
                                content = f.read_text(encoding='utf-8')
                                if content and content.strip():
                                    loaded_reports[f.stem] = content.strip()
                            except Exception:
                                pass
                if loaded_reports:
                    result_data['reports'] = loaded_reports
                    # If summary / recommendation is missing, try to complete it from the report with the same name.
                    if not result_data.get('summary') and loaded_reports.get('summary'):
                        result_data['summary'] = loaded_reports.get('summary')
                    if not result_data.get('recommendation') and loaded_reports.get('recommendation'):
                        result_data['recommendation'] = loaded_reports.get('recommendation')
                    logger.info(f"📁 [RESULT] Load from file system to {len(loaded_reports)} reports: {list(loaded_reports.keys())}")
            except Exception as fs_err:
                logger.warning(f"⚠️ [RESULT] Loading report from file system failed: {fs_err}")

            if 'reports' not in result_data or not result_data['reports']:
                logger.info(f"📊 [RESULT] reports Field is missing, try to extract from state")

                # Extract report content from state
                reports = {}
                state = result_data.get('state', {})

                if isinstance(state, dict):
                    # Prioritize dynamic extraction of report fields from structured_reports generated by the engine
                    structured_reports = state.get('structured_reports', {})
                    if isinstance(structured_reports, dict) and structured_reports:
                        report_fields = [
                            field for field, entry in structured_reports.items()
                            if isinstance(entry, dict) and entry.get("success") and entry.get("content")
                        ]
                    else:
                        # Fallback: Legacy hardcoded lists
                        report_fields = [
                            'market_report',
                            'sentiment_report',
                            'news_report',
                            'fundamentals_report',
                            'chip_report',
                            'investment_plan',
                            'trader_investment_plan',
                            'final_trade_decision'
                        ]

                    # Extract report content from state
                    for field in report_fields:
                        value = state.get(field, "")
                        if isinstance(value, str) and len(value.strip()) > 10:
                            reports[field] = value.strip()

                    # Handle research team debate status report
                    investment_debate_state = state.get('investment_debate_state', {})
                    if isinstance(investment_debate_state, dict):
                        # Extract long researcher history
                        bull_content = investment_debate_state.get('bull_history', "")
                        if isinstance(bull_content, str) and len(bull_content.strip()) > 10:
                            reports['bull_researcher'] = bull_content.strip()

                        # Extract short researcher history
                        bear_content = investment_debate_state.get('bear_history', "")
                        if isinstance(bear_content, str) and len(bear_content.strip()) > 10:
                            reports['bear_researcher'] = bear_content.strip()

                        # Extract Research Manager Analysis
                        judge_decision = investment_debate_state.get('judge_decision', "")
                        if isinstance(judge_decision, str) and len(judge_decision.strip()) > 10:
                            reports['research_team_decision'] = judge_decision.strip()

                    # Handle risk management team debate status report
                    risk_debate_state = state.get('risk_debate_state', {})
                    if isinstance(risk_debate_state, dict):
                        # Extract activist analyst history
                        risky_content = risk_debate_state.get('risky_history', "")
                        if isinstance(risky_content, str) and len(risky_content.strip()) > 10:
                            reports['risky_analyst'] = risky_content.strip()

                        # Extract conservative analyst history
                        safe_content = risk_debate_state.get('safe_history', "")
                        if isinstance(safe_content, str) and len(safe_content.strip()) > 10:
                            reports['safe_analyst'] = safe_content.strip()

                        # Extract neutral analyst history
                        neutral_content = risk_debate_state.get('neutral_history', "")
                        if isinstance(neutral_content, str) and len(neutral_content.strip()) > 10:
                            reports['neutral_analyst'] = neutral_content.strip()

                        # Extract risk assessor decisions
                        risk_decision = risk_debate_state.get('judge_decision', "")
                        if isinstance(risk_decision, str) and len(risk_decision.strip()) > 10:
                            reports['risk_management_decision'] = risk_decision.strip()

                    logger.info(f"📊 [RESULT] Extracted from state {len(reports)} reports: {list(reports.keys())}")
                    result_data['reports'] = reports
                else:
                    logger.warning(f"⚠️ [RESULT] state Field is not a dictionary type: {type(state)}")

        # Make sure everything in the reports field is of type string
        if 'reports' in result_data and result_data['reports']:
            reports = result_data['reports']
            if isinstance(reports, dict):
                # Make sure each report content is a string and not empty
                cleaned_reports = {}
                for key, value in reports.items():
                    if isinstance(value, str) and value.strip():
                        # Make sure the string is not empty
                        cleaned_reports[key] = value.strip()
                    elif value is not None:
                        # If not a string, convert to string
                        str_value = str(value).strip()
                        if str_value:  # Only save non-empty strings
                            cleaned_reports[key] = str_value
                    # If value is None or an empty string, the report is skipped

                result_data['reports'] = cleaned_reports
                logger.info(f"📊 [RESULT] Clean the reports field, including {len(cleaned_reports)} valid reports")

                # If there are no valid reports after cleaning, set to an empty dictionary
                if not cleaned_reports:
                    logger.warning(f"⚠️ [RESULT] No valid reports after cleaning")
                    result_data['reports'] = {}
            else:
                logger.warning(f"⚠️ [RESULT] reports Field is not a dictionary type: {type(reports)}")
                result_data['reports'] = {}

        # Complete key fields:recommendation/summary/key_points
        try:
            reports = result_data.get('reports', {}) or {}
            decision = result_data.get('decision', {}) or {}

            # recommendation Prioritize decisions in decision summaries or reports
            if not result_data.get('recommendation'):
                rec_candidates = []
                if isinstance(decision, dict):
                    # 🔥 Compliance modification: support new and old field names
                    action = decision.get('analysis_view') or decision.get('action')
                    price_range = decision.get('price_analysis_range') or decision.get('target_price')
                    confidence = decision.get('confidence')

                    if action:
                        parts = [
                            f"analysis point of view: {action}",
                            f"price analysis range: {price_range}" if price_range else None,
                            f"Confidence: {confidence}" if confidence is not None else None
                        ]
                        rec_candidates.append("；".join([p for p in parts if p]))
                # Get the scoop from the report
                for k in ['final_trade_decision', 'investment_plan']:
                    v = reports.get(k)
                    if isinstance(v, str) and len(v.strip()) > 10:
                        rec_candidates.append(v.strip())
                if rec_candidates:
                    # Take the most informative one (longest)
                    result_data['recommendation'] = max(rec_candidates, key=len)[:2000]

            # summary Generated from splicing several reports
            if not result_data.get('summary'):
                sum_candidates = []
                for k in ['market_report', 'fundamentals_report', 'sentiment_report', 'news_report']:
                    v = reports.get(k)
                    if isinstance(v, str) and len(v.strip()) > 50:
                        sum_candidates.append(v.strip())
                if sum_candidates:
                    result_data['summary'] = ("\n\n".join(sum_candidates))[:3000]

            # key_points Keep everything in mind
            if not result_data.get('key_points'):
                kp = []
                if isinstance(decision, dict):
                    # 🔥 Compliance modification: support old and new field names and new terminology
                    action = decision.get('analysis_view') or decision.get('action')
                    price_range = decision.get('price_analysis_range') or decision.get('target_price')
                    confidence = decision.get('confidence')
                    risk_level = decision.get('risk_level')

                    if action:
                        kp.append(f"analysis point of view: {action}")
                    if price_range:
                        # Handle price ranges (may be a list or a single value)
                        if isinstance(price_range, (list, tuple)) and len(price_range) == 2:
                            kp.append(f"price analysis range: {price_range[0]}-{price_range[1]}Yuan")
                        else:
                            kp.append(f"reference price: {price_range}Yuan")
                    if confidence is not None:
                        kp.append(f"Confidence: {confidence}")
                    if risk_level:
                        kp.append(f"risk level: {risk_level}")
                # Extract the first few sentences from reports as key points
                for k in ['investment_plan', 'final_trade_decision']:
                    v = reports.get(k)
                    if isinstance(v, str) and len(v.strip()) > 10:
                        kp.append(v.strip()[:120])
                if kp:
                    result_data['key_points'] = kp[:5]
        except Exception as fill_err:
            logger.warning(f"⚠️ [RESULT] Error completing key fields: {fill_err}")


        # Go further: infer and complete from detailed_analysis
        try:
            if not result_data.get('summary') or not result_data.get('recommendation') or not result_data.get('reports'):
                da = result_data.get('detailed_analysis')
                # If reports is still empty, put an original detailed analysis to facilitate the front-end"View report details"
                if (not result_data.get('reports')) and isinstance(da, str) and len(da.strip()) > 20:
                    result_data['reports'] = {'detailed_analysis': da.strip()}
                elif (not result_data.get('reports')) and isinstance(da, dict) and da:
                    # Put long text items of dictionary into reports
                    extracted = {}
                    for k, v in da.items():
                        if isinstance(v, str) and len(v.strip()) > 20:
                            extracted[k] = v.strip()
                    if extracted:
                        result_data['reports'] = extracted

                # supplement summary
                if not result_data.get('summary'):
                    if isinstance(da, str) and da.strip():
                        result_data['summary'] = da.strip()[:3000]
                    elif isinstance(da, dict) and da:
                        # Take the longest text as summary
                        texts = [v.strip() for v in da.values() if isinstance(v, str) and v.strip()]
                        if texts:
                            result_data['summary'] = max(texts, key=len)[:3000]

                # supplement recommendation
                if not result_data.get('recommendation'):
                    rec = None
                    if isinstance(da, str):
                        # Simple keyword extraction contains"Suggestions"paragraph
                        import re
                        m = re.search(r'(investment advice|Suggestions|Conclusion)[:: ]?\s*(.+)', da)
                        if m:
                            rec = m.group(0)
                    elif isinstance(da, dict):
                        for key in ['final_trade_decision', 'investment_plan', 'Conclusion', 'Suggestions']:
                            v = da.get(key)
                            if isinstance(v, str) and len(v.strip()) > 10:
                                rec = v.strip()
                                break
                    if rec:
                        result_data['recommendation'] = rec[:2000]
        except Exception as da_err:
            logger.warning(f"⚠️ [RESULT] Completion failed from detailed_analysis: {da_err}")

        # Rigorous data formatting and validation
        def safe_string(value, default=""):
            """Safely convert to string"""
            if value is None:
                return default
            if isinstance(value, str):
                return value
            return str(value)

        def safe_number(value, default=0):
            """Safely convert to numbers"""
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return value
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        def safe_list(value, default=None):
            """Safely convert to list"""
            if default is None:
                default = []
            if value is None:
                return default
            if isinstance(value, list):
                return value
            return default

        def safe_dict(value, default=None):
            """Convert safely to dictionary"""
            if default is None:
                default = {}
            if value is None:
                return default
            if isinstance(value, dict):
                return value
            return default

        # 🔍 Debugging: Check before final build result_data
        logger.info(f"🔍 [FINAL] Before building the final result, the result_data key: {list(result_data.keys())}")
        logger.info(f"🔍 [FINAL] result_data There is decision: {bool(result_data.get('decision'))}")
        if result_data.get('decision'):
            logger.info(f"🔍 [FINAL] decision content: {result_data['decision']}")

        # Build strictly validated result data (basic fields, must be returned)
        final_result_data = {
            "analysis_id": safe_string(result_data.get("analysis_id"), "unknown"),
            "stock_symbol": safe_string(result_data.get("stock_symbol"), "UNKNOWN"),
            "stock_code": safe_string(result_data.get("stock_code"), "UNKNOWN"),
            "analysis_date": safe_string(result_data.get("analysis_date"), "2025-08-20"),
            "source": safe_string(result_data.get("source"), "unknown"),
            "summary": safe_string(result_data.get("summary"), "Analysis summary not yet available"),
            "recommendation": safe_string(result_data.get("recommendation"), "No investment advice yet"),
            "confidence_score": safe_number(result_data.get("confidence_score"), 0.0),
            "risk_level": safe_string(result_data.get("risk_level"), "medium"),
            "key_points": safe_list(result_data.get("key_points")),
            "execution_time": safe_number(result_data.get("execution_time"), 0),
            "tokens_used": safe_number(result_data.get("tokens_used"), 0),
            "analysts": safe_list(result_data.get("analysts")),
            "research_depth": safe_string(result_data.get("research_depth"), "fast"),
            # 🔥 Key fix: add decision field!
            "decision": safe_dict(result_data.get("decision"))
        }
        
        # 🔥 Optional fields: decide whether to return based on query parameters
        if include_state:
            final_result_data["state"] = safe_dict(result_data.get("state"))
        if include_detailed:
            final_result_data["detailed_analysis"] = safe_dict(result_data.get("detailed_analysis"))

        # Special handling of reports field - ensure every report is a valid string
        reports_data = safe_dict(result_data.get("reports"))
        validated_reports = {}

        for report_key, report_content in reports_data.items():
            # Make sure report keys are strings
            safe_key = safe_string(report_key, "unknown_report")

            # Make sure the report content is a non-empty string
            if report_content is None:
                validated_content = "No report content yet"
            elif isinstance(report_content, str):
                validated_content = report_content.strip() if report_content.strip() else "Report content is empty"
            else:
                validated_content = str(report_content).strip() if str(report_content).strip() else "Report content format error"

            validated_reports[safe_key] = validated_content

        final_result_data["reports"] = validated_reports

        logger.info(f"✅ [RESULT] Successfully obtained task results: {task_id}")
        logger.info(f"📊 [RESULT] eventually return {len(final_result_data.get('reports', {}))} reports")
        logger.info(f"📊 [RESULT] Report list: {list(validated_reports.keys())}")

        # 🔍 Debugging: Examine the final returned data
        logger.info(f"🔍 [FINAL] Finally return the data key: {list(final_result_data.keys())}")
        logger.info(f"🔍 [FINAL] There are some in the final return decision: {bool(final_result_data.get('decision'))}")
        if final_result_data.get('decision'):
            logger.info(f"🔍 [FINAL] final decision content: {final_result_data['decision']}")

        return {
            "success": True,
            "data": final_result_data,
            "message": "Analysis results obtained successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [RESULT] Failed to obtain task results: {e}")
        raise HTTPException(status_code=400, detail=format_http_error_detail(e))


class AnalysisFeedbackRequest(BaseModel):
    """Analyze task feedback requests"""
    rating: int = Field(..., ge=1, le=5, description="Rating 1-5")
    comment: str = Field(default="", description="Feedback content")


@router.post("/tasks/{task_id}/feedback")
async def submit_analysis_feedback(
    task_id: str,
    req: AnalysisFeedbackRequest,
    user: dict = Depends(get_current_user),
):
    """Submit analysis task feedback (score+comments)"""
    try:
        db = get_mongo_db()
        # Check if the task exists
        task = await db.analysis_tasks.find_one({"task_id": task_id})
        if not task:
            raise HTTPException(status_code=404, detail="Task does not exist")

        # Write feedback
        feedback_doc = {
            "task_id": task_id,
            "user_id": str(user["id"]),
            "rating": req.rating,
            "comment": req.comment,
            "code": task.get("code", ""),
            "created_at": now_tz(),
        }
        await db.analysis_feedback.replace_one(
            {"task_id": task_id, "user_id": str(user["id"])},
            feedback_doc,
            upsert=True,
        )

        # Update rating field in task
        await db.analysis_tasks.update_one(
            {"task_id": task_id},
            {"$set": {"user_rating": req.rating, "user_feedback": req.comment}},
        )

        return {"message": "Feedback submitted successfully", "rating": req.rating}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to submit analysis feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/all", response_model=Dict[str, Any])
async def list_all_tasks(
    user: dict = Depends(get_current_user),
    status: Optional[str] = Query(None, description="Task status filter"),
    limit: Optional[int] = Query(None, description="Return quantity limit (optional, if not set, all will be returned)"),
    offset: int = Query(0, ge=0, description="offset")
):
    """Get all task lists (not limited to users)

    Note: If limit is not specified, all records will be returned and paging will be handled by the front end.
    """
    try:
        logger.info(f"📋 Query all task lists")

        # If limit is not specified, all records are returned
        actual_limit = limit if limit is not None else 999999

        tasks = await get_simple_analysis_service().list_all_tasks(
            status=status,
            limit=actual_limit,
            offset=offset
        )

        return {
            "success": True,
            "data": {
                "tasks": tasks,
                "total": len(tasks),
                "limit": limit,
                "offset": offset
            },
            "message": "Task list obtained successfully"
        }

    except Exception as e:
        logger.error(f"❌ Failed to get task list: {e}")
        raise HTTPException(status_code=500, detail=format_http_error_detail(e))

@router.get("/tasks", response_model=Dict[str, Any])
async def list_user_tasks(
    user: dict = Depends(get_current_user),
    status: Optional[str] = Query(None, description="Task status filter"),
    limit: Optional[int] = Query(None, description="Return quantity limit (optional, if not set, all will be returned)"),
    offset: int = Query(0, ge=0, description="offset")
):
    """Get the user s task list

    Note: If limit is not specified, all records will be returned and paging will be handled by the front end.
    """
    try:
        logger.info(f"📋 Query user task list: {user['id']}")

        # If limit is not specified, all records are returned
        actual_limit = limit if limit is not None else 999999

        tasks = await get_simple_analysis_service().list_user_tasks(
            user_id=user["id"],
            status=status,
            limit=actual_limit,
            offset=offset
        )

        return {
            "success": True,
            "data": {
                "tasks": tasks,
                "total": len(tasks),
                "limit": limit,
                "offset": offset
            },
            "message": "Task list obtained successfully"
        }

    except Exception as e:
        logger.error(f"❌ Failed to get task list: {e}")
        raise HTTPException(status_code=500, detail=format_http_error_detail(e))

@router.post("/batch", response_model=Dict[str, Any])
async def submit_batch_analysis(
    request: BatchAnalysisRequest,
    user: dict = Depends(get_current_user)
):
    """
    Submit batch analysis tasks (true concurrent execution) - supports AB testing

    Select the engine via the request.parameters.engine parameter:
    - v2 (Default): Use new engine WorkflowEngine + v2 agent
    - unified: Use unified engine WorkflowEngine
    - legacy: Disabled (blocked since v3.0, returning 400)

    ⚠️ NOTE: BackgroundTasks are not used as it is executed serially!
    Use asyncio.create_task instead to achieve true concurrent execution.
    """
    try:
        logger.info(f"🎯 [Batch analysis] Receive batch analysis request: title={request.title}")

        # Determine which engine to use
        # v3.0 The V2 engine is used by default from now on (the old version legacy has been discontinued)
        engine_type = AnalysisEngine.V2
        if request.parameters and hasattr(request.parameters, "engine"):
            engine_type = request.parameters.engine
            # v3.0 Reject legacy engine
            if engine_type == AnalysisEngine.LEGACY:
                raise HTTPException(
                    status_code=400,
                    detail="[Deactivated] legacy Engine is retired, please use v2 engine instead (request.parameters.engine='v2') . "
                    "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
                )

        logger.info(f"🔧 [AB Test-Batch] use engine: {engine_type.value}")

        simple_service = get_simple_analysis_service()
        unified_service = get_unified_analysis_service()
        batch_id = str(uuid.uuid4())
        task_ids: List[str] = []
        mapping: List[Dict[str, str]] = []

        # Get a list of stock symbols (Compatible with old fields)
        stock_symbols = request.get_symbols()
        logger.info(f"📊 [Batch analysis] Stock code list: {stock_symbols}")

        # Verify ticker list
        if not stock_symbols:
            raise ValueError("Stock symbol list cannot be empty")

        # 🔧 Limit the number of stocks analyzed in batches (maximum 10)
        MAX_BATCH_SIZE = 10
        if len(stock_symbols) > MAX_BATCH_SIZE:
            raise ValueError(f"Batch analysis supports up to {MAX_BATCH_SIZE} stocks, currently submitted {len(stock_symbols)} a")

        # Create a single stock analysis task for each stock
        for i, symbol in enumerate(stock_symbols):
            logger.info(f"📝 [Batch analysis] Creating the {i+1}/{len(stock_symbols)} tasks: {symbol}")

            single_req = SingleAnalysisRequest(
                symbol=symbol,
                stock_code=symbol,  # Compatible fields
                parameters=request.parameters
            )

            try:
                if engine_type == AnalysisEngine.V2:
                    # v2 Engine: Use unified task service
                    from app.services.task_analysis_service import get_task_analysis_service
                    from app.models.analysis import AnalysisTaskType
                    from app.models.user import PyObjectId

                    task_service = get_task_analysis_service()

                    # 🔥 Fix: Prepare task parameters, making sure to include required market_type
                    # Automatically identify market types based on stock symbols
                    market_type = get_market_type_from_symbol(symbol)
                    logger.info(f"📊 [Batch analysis] stocks {symbol} identified as market: {market_type}")

                    task_params = {
                        "symbol": symbol,
                        "stock_code": symbol,
                        "market_type": market_type,  # 🔑 Automatically identify market types based on stock symbols
                    }

                    # Merge all fields of request.parameters into task_params
                    if request.parameters:
                        params_dict = request.parameters.model_dump()
                        # Remove the engine field (this is used by the routing layer, not a task parameter)
                        params_dict.pop("engine", None)
                        task_params.update(params_dict)

                    # If the user specifies market_type in parameters, the user-specified
                    if request.parameters and hasattr(request.parameters, 'market_type') and request.parameters.market_type:
                        task_params["market_type"] = request.parameters.market_type
                        logger.info(f"📊 [Batch analysis] Use user-specified market type: {request.parameters.market_type}")

                    # 🔥 Read risk preference settings from user preferences
                    preference_type = await get_user_risk_preference(user["id"])
                    logger.info(f"📊 [Batch analysis] Use user risk preferences: {preference_type}")

                    task = await task_service.create_task(
                        user_id=PyObjectId(user["id"]),
                        task_type=AnalysisTaskType.STOCK_ANALYSIS,
                        task_params=task_params,
                        engine_type="auto",
                        preference_type=preference_type  # 🔥 Use user preferences
                    )
                    task_id = task.task_id  # Use UUID task_id, not ObjectId
                else:
                    # unified Engine: Use simple_analysis_service to create tasks (legacy has been intercepted earlier)
                    create_res = await simple_service.create_analysis_task(user["id"], single_req)
                    task_id = create_res.get("task_id")
                    if not task_id:
                        raise RuntimeError(f"Failed to create task: did not return task_id (symbol={symbol})")

                task_ids.append(task_id)
                mapping.append({"symbol": symbol, "stock_code": symbol, "task_id": task_id})
                logger.info(f"✅ [Batch analysis] Task created: {task_id} - {symbol}")
            except Exception as create_error:
                logger.error(f"❌ [Batch analysis] Failed to create task: {symbol}, Error: {create_error}", exc_info=True)
                raise

        # 🔧 Use the queue system to uniformly manage tasks and automatically control concurrency
        # No longer use asyncio.create_task direct concurrency, but consumed by Worker through queue
        from app.services.queue_service import get_queue_service
        queue_service = get_queue_service()

        # Prepare queue parameters for each task
        for i, symbol in enumerate(stock_symbols):
            task_id = task_ids[i]
            
            # Prepare queue parameters
            queue_params = {
                "task_id": task_id,
                "symbol": symbol,
                "stock_code": symbol,
                "user_id": user["id"],
                "batch_id": batch_id,
                "engine": engine_type.value,  # Record engine type, Worker needs to know
            }
            
            # Add analysis parameters
            if request.parameters:
                params_dict = request.parameters.model_dump()
                # Remove engine field (already in queue_params)
                params_dict.pop("engine", None)
                queue_params.update(params_dict)
            
            try:
                # Submit tasks to the queue (will automatically check concurrency limits)
                # Use an existing task_id instead of letting the queue generate a new one
                await queue_service.enqueue_task(
                    user_id=user["id"],
                    symbol=symbol,
                    params=queue_params,
                    batch_id=batch_id,
                    task_id=task_id  # Use an already created task ID
                )
                logger.info(f"✅ [Batch analysis] The task has been queued: {task_id} - {symbol} (engine: {engine_type.value})")
            except ValueError as e:
                # Concurrency limit error
                logger.warning(f"⚠️ [Batch analysis] Task enqueue failed (concurrency limit): {task_id} - {symbol}, Error: {e}")
                # Continue to process other tasks, failed ones will stay in the queue waiting
            except Exception as e:
                logger.error(f"❌ [Batch analysis] Task enqueue failed: {task_id} - {symbol}, Error: {e}", exc_info=True)
        
        logger.info(f"🚀 [Batch analysis] Submitted {len(task_ids)} tasks to queue (engine: {engine_type.value})")

        return {
            "success": True,
            "data": {
                "batch_id": batch_id,
                "total_tasks": len(task_ids),
                "task_ids": task_ids,
                "mapping": mapping,
                "status": "submitted",
                "engine": engine_type.value
            },
            "message": f"Batch analysis tasks have been submitted to the queue, a total of{len(task_ids)}For each stock, the Worker will automatically execute according to the concurrency limit. (engine: {engine_type.value})"
        }
    except Exception as e:
        logger.error(f"❌ [Batch analysis] Submission failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=format_http_error_detail(e))

# Compatibility: Keep original endpoints
@router.post("/analyze")
async def analyze_single(
    req: SingleAnalyzeRequest,
    user: dict = Depends(get_current_user),
    svc: QueueService = Depends(get_queue_service)
):
    """Single Stock Analysis (Compatibility Endpoint)"""
    try:
        task_id = await svc.enqueue_task(
            user_id=user["id"],
            symbol=req.symbol,
            params=req.parameters
        )
        return {"task_id": task_id, "status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=format_http_error_detail(e))

@router.post("/analyze/batch")
async def analyze_batch(
    req: BatchAnalyzeRequest,
    user: dict = Depends(get_current_user),
    svc: QueueService = Depends(get_queue_service)
):
    """Batch Analysis (Compatibility Endpoint)"""
    try:
        batch_id, submitted = await svc.create_batch(
            user_id=user["id"],
            symbols=req.symbols,
            params=req.parameters
        )
        return {"batch_id": batch_id, "submitted": submitted}
    except Exception as e:
        raise HTTPException(status_code=400, detail=format_http_error_detail(e))

@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    b = await svc.get_batch(batch_id)
    if not b or b.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="batch not found")
    return b

# Task and batch query endpoints
# NOTE: This route has been moved to /tasks/{task_id}/status Afterwards, avoid routing conflicts
# @router.get("/tasks/{task_id}")
# async def get_task(
#     task_id: str,
#     user: dict = Depends(get_current_user),
#     svc: QueueService = Depends(get_queue_service)
# ):
#     """Get task details"""
#     t = await svc.get_task(task_id)
#     if not t or t.get("user") != user["id"]:
#         raise HTTPException(status_code=404, detail="Task does not exist")
#     return t

# The original routing has been replaced by the new asynchronous implementation
# @router.get("/tasks/{task_id}/status")
# async def get_task_status_old(
#     task_id: str,
#     user: dict = Depends(get_current_user)
# ):
#     """Get task status and progress (old version implementation)"""
#     try:
#         status = await get_analysis_service().get_task_status(task_id)
#         if not status:
#             raise HTTPException(status_code=404, detail="Task does not exist")
#         return {
#             "success": True,
#             "data": status
#         }
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    svc: QueueService = Depends(get_queue_service)
):
    """Cancel task"""
    try:
        # Verify task ownership
        task = await svc.get_task(task_id)
        if not task or task.get("user") != user["id"]:
            raise HTTPException(status_code=404, detail="Task does not exist")

        success = await svc.cancel_task(task_id)
        if success:
            return {"success": True, "message": "Task canceled"}
        else:
            raise HTTPException(status_code=400, detail="Failed to cancel task")
    except Exception as e:
        raise HTTPException(status_code=400, detail=format_http_error_detail(e))

@router.get("/user/queue-status")
async def get_user_queue_status(
    user: dict = Depends(get_current_user),
    svc: QueueService = Depends(get_queue_service)
):
    """Get user queue status"""
    try:
        status = await svc.get_user_queue_status(user["id"])
        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=format_http_error_detail(e))

@router.get("/user/history")
async def get_user_analysis_history(
    user: dict = Depends(get_current_user),
    status: Optional[str] = Query(None, description="Task status filter"),
    start_date: Optional[str] = Query(None, description="start date,YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="end date,YYYY-MM-DD"),
    symbol: Optional[str] = Query(None, description="Stock code"),
    stock_code: Optional[str] = Query(None, description="Stock code(Deprecated,Use symbol)"),
    market_type: Optional[str] = Query(None, description="market type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="page size")
):
    """Obtain user analysis history (supports basic filtering and paging)"""
    try:
        # First get the user task list (memory first, MongoDB takes care of everything)
        raw_tasks = await get_simple_analysis_service().list_user_tasks(
            user_id=user["id"],
            status=status,
            limit=page_size,
            offset=(page - 1) * page_size
        )

        # Perform basic screening
        from datetime import datetime
        def in_date_range(t: Optional[str]) -> bool:
            if not t:
                return True
            try:
                dt = datetime.fromisoformat(t.replace('Z', '+00:00')) if 'Z' in t else datetime.fromisoformat(t)
            except Exception:
                return True
            ok = True
            if start_date:
                try:
                    ok = ok and (dt.date() >= datetime.fromisoformat(start_date).date())
                except Exception:
                    pass
            if end_date:
                try:
                    ok = ok and (dt.date() <= datetime.fromisoformat(end_date).date())
                except Exception:
                    pass
            return ok

        # Get the queried stock code (Compatible with old fields)
        query_symbol = symbol or stock_code

        filtered = []
        for x in raw_tasks:
            if query_symbol:
                task_symbol = x.get("symbol") or x.get("stock_code") or x.get("stock_symbol")
                if task_symbol not in [query_symbol]:
                    continue
            # The market type is temporarily determined from the parameters (if any)
            if market_type:
                params = x.get("parameters") or {}
                if params.get("market_type") != market_type:
                    continue
            # Time range (use start_time or created_at)
            t = x.get("start_time") or x.get("created_at")
            if not in_date_range(t):
                continue
            filtered.append(x)

        return {
            "success": True,
            "data": {
                "tasks": filtered,
                "total": len(filtered),
                "page": page,
                "page_size": page_size
            },
            "message": "History query successful"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=format_http_error_detail(e))

# WebSocket endpoint
@router.websocket("/ws/task/{task_id}")
async def websocket_task_progress(websocket: WebSocket, task_id: str):
    """WebSocket Endpoint: Get task progress in real time"""
    import json
    websocket_manager = get_websocket_manager()

    try:
        await websocket_manager.connect(websocket, task_id)

        # Send connection confirmation message
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "task_id": task_id,
            "message": "WebSocket Connection established"
        }))

        # keep connection active
        while True:
            try:
                # Receive heartbeat messages from the client
                data = await websocket.receive_text()
                # Can handle messages sent by the client
                logger.debug(f"📡 Receive WebSocket message: {data}")
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"⚠️ WebSocket Message processing error: {e}")
                break

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket Client disconnects: {task_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket Connection error: {e}")
    finally:
        await websocket_manager.disconnect(websocket, task_id)

# Task details query routing (put at the end to avoid confusion with /tasks/{task_id}/status conflict)
@router.get("/tasks/{task_id}/details")
async def get_task_details(
    task_id: str,
    user: dict = Depends(get_current_user),
    svc: QueueService = Depends(get_queue_service)
):
    """Get task details (use different paths to avoid conflicts)"""
    t = await svc.get_task(task_id)
    if not t or t.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="Task does not exist")
    return t


# ==================== Zombie task management ====================

@router.get("/admin/zombie-tasks")
async def get_zombie_tasks(
    max_running_hours: int = Query(default=2, ge=1, le=72, description="Maximum run time (hours)"),
    user: dict = Depends(get_current_user)
):
    """Get zombie task list (admin only)

    Zombie tasks: tasks that are in the processing/running/pending state for a long time
    """
    # Check admin rights
    if user.get("username") != "admin":
        raise HTTPException(status_code=403, detail="Accessible only to administrators")

    try:
        svc = get_simple_analysis_service()
        zombie_tasks = await svc.get_zombie_tasks(max_running_hours)

        return {
            "success": True,
            "data": zombie_tasks,
            "total": len(zombie_tasks),
            "max_running_hours": max_running_hours
        }
    except Exception as e:
        logger.error(f"❌ Failed to get zombie mission: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get zombie mission: {str(e)}")


@router.post("/admin/cleanup-zombie-tasks")
async def cleanup_zombie_tasks(
    max_running_hours: int = Query(default=2, ge=1, le=72, description="Maximum run time (hours)"),
    user: dict = Depends(get_current_user)
):
    """Clean zombie task (admin only)

    Mark tasks that have been in the processing/running/pending state for a long time as failed
    """
    # Check admin rights
    if user.get("username") != "admin":
        raise HTTPException(status_code=403, detail="Accessible only to administrators")

    try:
        svc = get_simple_analysis_service()
        result = await svc.cleanup_zombie_tasks(max_running_hours)

        return {
            "success": True,
            "data": result,
            "message": f"Cleaned {result.get('total_cleaned', 0)} zombie mission"
        }
    except Exception as e:
        logger.error(f"❌ Zombie clearing mission failed: {e}")
        raise HTTPException(status_code=500, detail=f"Zombie clearing mission failed: {str(e)}")


@router.post("/tasks/{task_id}/mark-failed")
async def mark_task_as_failed(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Mark the specified task as failed

    Used to manually clean up stuck tasks
    """
    try:
        svc = get_simple_analysis_service()

        # Update task status in memory
        from app.services.memory_state_manager import TaskStatus
        await svc.memory_manager.update_task_status(
            task_id=task_id,
            status=TaskStatus.FAILED,
            message="Manually mark as failed",
            error_message="User manually marks as failed"
        )

        # Update task status in MongoDB
        from app.core.database import get_mongo_db
        from datetime import datetime
        db = get_mongo_db()

        result = await db.analysis_tasks.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": "failed",
                    "last_error": "User manually marks as failed",
                    "completed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )

        if result.modified_count > 0:
            logger.info(f"✅ Task {task_id} Marked as failed")
            return {
                "success": True,
                "message": "Task marked as failed"
            }
        else:
            logger.warning(f"⚠️ Task {task_id} Not found or already in failed state")
            return {
                "success": True,
                "message": "The task was not found or has failed."
            }
    except Exception as e:
        logger.error(f"❌ Mark task failed: {task_id} - {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Mark task failed: {str(e)}"
        )


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Recreate a failed analysis task

    Recreate the task with the same parameters to reproduce the problem or verify the fix.
    
    Returns:
        {
            "success": True,
            "task_id": "new task ID",
            "message": "Task has been recreated"
        }
    """
    try:
        from app.core.database import get_mongo_db
        from bson import ObjectId
        from app.services.task_analysis_service import get_task_analysis_service
        from app.models.analysis import AnalysisTaskType
        from app.models.user import PyObjectId
        
        db = get_mongo_db()
        
        # Find failed tasks
        failed_task = await db.unified_analysis_tasks.find_one({
            "task_id": task_id,
            "user_id": ObjectId(user["id"])
        })
        
        if not failed_task:
            # Try to find from old task collection
            old_task = await db.analysis_tasks.find_one({
                "task_id": task_id,
                "user_id": ObjectId(user["id"])
            })
            if not old_task:
                raise HTTPException(
                    status_code=404,
                    detail="The task does not exist or does not belong to the current user"
                )
            
            # Old task format: needs to be converted to new format
            logger.info(f"🔄 [Retry task] Find old format tasks: {task_id}")
            
            # Extract parameters from old tasks
            task_params = old_task.get("parameters", {})
            symbol = task_params.get("symbol") or task_params.get("stock_code") or old_task.get("stock_code")
            market_type = task_params.get("market_type") or old_task.get("market_type", "cn")
            
            if not symbol:
                raise HTTPException(
                    status_code=400,
                    detail="Unable to extract ticker from old task"
                )
            
            # 🔥 Read risk preference settings from user preferences
            preference_type = await get_user_risk_preference(user["id"])
            logger.info(f"📊 [Retry task] Use user risk preferences: {preference_type}")

            # Create new task
            task_service = get_task_analysis_service()
            new_task = await task_service.create_task(
                user_id=PyObjectId(user["id"]),
                task_type=AnalysisTaskType.STOCK_ANALYSIS,
                task_params={
                    "symbol": symbol,
                    "stock_code": symbol,
                    "market_type": market_type,
                    **task_params  # Incorporate other parameters
                },
                engine_type="auto",
                preference_type=preference_type  # 🔥 Use user preferences
            )
            
            logger.info(f"✅ [Retry task] Old format tasks have been recreated: {task_id} -> {new_task.task_id}")
            
            # 🔑 Key: Add tasks to the queue for execution
            from app.services.queue_service import get_queue_service
            queue_service = get_queue_service()
            
            # Prepare queue parameters
            queue_params = {
                "engine": "v2",  # Use v2 engine
                "symbol": symbol,
                "stock_code": symbol,
                "market_type": market_type,
                **task_params  # Incorporate other parameters
            }
            
            try:
                await queue_service.enqueue_task(
                    user_id=user["id"],
                    symbol=symbol,
                    params=queue_params,
                    task_id=new_task.task_id  # Use an already created task ID
                )
                logger.info(f"✅ [Retry task] Old format task has been queued: {new_task.task_id}")
            except Exception as e:
                logger.error(f"⚠️ [Retry task] Old format task failed to join the queue: {new_task.task_id} - {e}", exc_info=True)
                # Even if the enqueue fails, success is returned (the task has been created and can be triggered manually)
            
            return {
                "success": True,
                "task_id": new_task.task_id,
                "message": "Task has been recreated and queued"
            }
        
        # Check task status
        task_status = failed_task.get("status")
        if isinstance(task_status, str):
            status_str = task_status
        elif hasattr(task_status, "value"):
            status_str = task_status.value
        else:
            status_str = str(task_status)
        
        if status_str not in ["failed", "cancelled"]:
            raise HTTPException(
                status_code=400,
                detail=f"Only failed or canceled tasks can be recreated, current status: {status_str}"
            )
        
        # Get task parameters
        task_params = failed_task.get("task_params", {})
        task_type_str = failed_task.get("task_type")
        
        # Convert task_type
        if isinstance(task_type_str, str):
            try:
                task_type = AnalysisTaskType(task_type_str)
            except ValueError:
                # Use stock analysis by default
                task_type = AnalysisTaskType.STOCK_ANALYSIS
                logger.warning(f"⚠️ [Retry task] Unknown task type: {task_type_str}, Use default type: STOCK_ANALYSIS")
        else:
            task_type = AnalysisTaskType.STOCK_ANALYSIS
        
        # Make sure necessary parameters are present
        symbol = task_params.get("symbol") or task_params.get("stock_code")
        if not symbol:
            raise HTTPException(
                status_code=400,
                detail="Stock symbol missing in task parameters"
            )
        
        # 🔥 Read risk preference settings from user preferences
        preference_type = await get_user_risk_preference(user["id"])
        logger.info(f"📊 [Retry task] Use user risk preferences: {preference_type}")

        # Create new task (with same parameters)
        task_service = get_task_analysis_service()
        new_task = await task_service.create_task(
            user_id=PyObjectId(user["id"]),
            task_type=task_type,
            task_params=task_params,  # Use original parameters
            engine_type="auto",
            preference_type=preference_type  # 🔥 Use user preferences
        )
        
        logger.info(f"✅ [Retry task] Task has been recreated: {task_id} -> {new_task.task_id}")
        
        # 🔑 Key: Add tasks to the queue for execution
        from app.services.queue_service import get_queue_service
        queue_service = get_queue_service()
        
        # Prepare queue parameters
        symbol = task_params.get("symbol") or task_params.get("stock_code")
        queue_params = {
            "engine": "v2",  # Use v2 engine
            **task_params  # Combine all task parameters
        }
        
        try:
            await queue_service.enqueue_task(
                user_id=user["id"],
                symbol=symbol,
                params=queue_params,
                task_id=new_task.task_id  # Use an already created task ID
            )
            logger.info(f"✅ [Retry task] Task has been queued: {new_task.task_id}")
        except Exception as e:
            logger.error(f"⚠️ [Retry task] Failed to add task to queue: {new_task.task_id} - {e}", exc_info=True)
            # Even if the enqueue fails, success is returned (the task has been created and can be triggered manually)
        
        return {
            "success": True,
            "task_id": new_task.task_id,
            "message": "Task has been recreated and queued"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Retry task] Failed to recreate task: {task_id} - {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to recreate task: {str(e)}"
        )
    except Exception as e:
        logger.error(f"❌ Mark task failed: {e}")
        raise HTTPException(status_code=500, detail=f"Mark task failed: {str(e)}")


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Delete specified task

    Delete task records from memory and database
    """
    try:
        svc = get_simple_analysis_service()

        # Remove tasks from memory
        await svc.memory_manager.remove_task(task_id)

        # Delete tasks from MongoDB
        from app.core.database import get_mongo_db
        db = get_mongo_db()

        result = await db.analysis_tasks.delete_one({"task_id": task_id})

        if result.deleted_count > 0:
            logger.info(f"✅ Task {task_id} Deleted")
            return {
                "success": True,
                "message": "Task deleted"
            }
        else:
            logger.warning(f"⚠️ Task {task_id} not found")
            return {
                "success": True,
                "message": "Task not found"
            }
    except Exception as e:
        logger.error(f"❌ Delete task failed: {e}")
        raise HTTPException(status_code=500, detail=f"Delete task failed: {str(e)}")

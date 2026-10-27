"""
Workflow API routing

Provides CRUD and execution endpoints for workflows
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

from app.core.response import ok, fail
from app.core.permissions import require_pro
from app.routers.auth_db import get_current_user
from app.utils.compliance import (
    GENERIC_RESEARCH_RECOMMENDATION,
    build_research_summary,
    filter_analysis_reports,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workflows",
    tags=["workflows"]
)


# ==================== data model ====================

class Position(BaseModel):
    """Node position"""
    x: float
    y: float


class NodeDefinition(BaseModel):
    """Node definition"""
    id: str
    type: str
    agent_id: Optional[str] = None
    label: str
    position: Position
    config: Dict[str, Any] = Field(default_factory=dict)
    condition: Optional[str] = None


class EdgeDefinition(BaseModel):
    """edge definition"""
    id: str
    source: str
    target: str
    type: str = "normal"
    condition: Optional[str] = None
    label: Optional[str] = None
    animated: bool = False


class WorkflowCreate(BaseModel):
    """Create workflow request"""
    id: Optional[str] = None  # Optional, can be passed in during verification
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    version: str = "1.0.0"
    nodes: List[NodeDefinition] = Field(default_factory=list)
    edges: List[EdgeDefinition] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    is_template: bool = False
    config: Dict[str, Any] = Field(default_factory=dict)
    workflow_type: Optional[str] = None


class WorkflowUpdate(BaseModel):
    """Update workflow request"""
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    nodes: Optional[List[NodeDefinition]] = None
    edges: Optional[List[EdgeDefinition]] = None
    tags: Optional[List[str]] = None
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    workflow_type: Optional[str] = None


class ModelConfig(BaseModel):
    """Model configuration"""
    model_name: str = Field(..., description="Model name")
    provider: str = Field(..., description="Model manufacturer: openai/dashscope/deepseek/google, etc.")
    api_key: Optional[str] = Field(default=None, description="API Key (Optional, obtained from database by default)")
    api_base: Optional[str] = Field(default=None, description="API Base URL (optional)")
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=2000, ge=100, le=32000)
    timeout: int = Field(default=60, ge=10, le=600)


class WorkflowExecuteRequest(BaseModel):
    """Execute workflow requests"""
    ticker: Optional[str] = Field(default=None, description="Stock code (stock_analysis/etf_analysis required, other types are optional)")
    analysis_date: Optional[datetime] = None
    research_depth: str = Field(default="Standard", description="Analysis depth: Quick/Basic/Standard/In-depth/Comprehensive")
    # 🆕 Analyst selection (for dynamic cropping workflow)
    selected_analysts: Optional[List[str]] = Field(
        default=None,
        description="List of selected analysts, such as ['market', 'fundamentals'], Empty to use all analysts"
    )
    # Backward compatibility with old fields
    quick_analysis_model: Optional[str] = Field(default=None, description="Quick analysis of model names (backwards compatible)")
    deep_analysis_model: Optional[str] = Field(default=None, description="Deep analysis model name (backwards compatible)")
    # New complete model configuration
    quick_model_config: Optional[ModelConfig] = Field(default=None, description="Quick analysis model complete configuration")
    deep_model_config: Optional[ModelConfig] = Field(default=None, description="Complete configuration of in-depth analysis model")
    lookback_days: int = Field(default=30, ge=1, le=365)
    max_debate_rounds: int = Field(default=3, ge=1, le=10)
    # 🆕 Custom parameters (transparently transmitted to task_params, used for general research and other scenarios)
    custom_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom parameters will be merged into task parameters"
    )


class ValidationResult(BaseModel):
    """Verification results"""
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []


# ==================== API endpoint ====================

@router.get("", dependencies=[Depends(require_pro)])
async def list_workflows():
    """Get a list of all workflows"""
    try:
        from core.api import WorkflowAPI
        from core.workflow.default_workflow_provider import get_default_workflow_provider
        api = WorkflowAPI()
        workflows = api.list_all()
        return ok(workflows)
    except Exception as e:
        logger.error(f"Failed to get workflow list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def get_templates(user: dict = Depends(get_current_user)):
    """Get predefined templates"""
    try:
        from core.api import WorkflowAPI
        from core.workflow.default_workflow_provider import get_default_workflow_provider
        api = WorkflowAPI()
        templates = api.get_templates()
        return ok(templates)
    except Exception as e:
        logger.error(f"Failed to get template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}", dependencies=[Depends(require_pro)])
async def get_workflow(workflow_id: str):
    """Get individual workflow details"""
    try:
        from core.api import WorkflowAPI
        api = WorkflowAPI()
        workflow = api.get(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow does not exist")
        return ok(workflow)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", dependencies=[Depends(require_pro)])
async def create_workflow(data: WorkflowCreate):
    """Create new workflow"""
    try:
        from core.api import WorkflowAPI
        api = WorkflowAPI()
        result = api.create(data.model_dump())

        if not result.get("success"):
            return fail(
                message="Failed to create workflow",
                code=400,
                data={"errors": result.get("errors", ["Creation failed"])}
            )

        return ok(result.get("workflow"), message="Created successfully")
    except Exception as e:
        logger.error(f"Failed to create workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{workflow_id}", dependencies=[Depends(require_pro)])
async def update_workflow(workflow_id: str, data: WorkflowUpdate):
    """Update workflow"""
    try:
        from core.api import WorkflowAPI
        api = WorkflowAPI()

        # Filter out None values
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        result = api.update(workflow_id, update_data)

        if not result.get("success"):
            error = result.get("error") or result.get("errors", ["Update failed"])
            return fail(message=str(error), code=400)

        return ok(result.get("workflow"), message="Update successful")
    except Exception as e:
        logger.error(f"Update workflow failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workflow_id}", dependencies=[Depends(require_pro)])
async def delete_workflow(workflow_id: str):
    """Delete workflow"""
    try:
        from core.api import WorkflowAPI
        api = WorkflowAPI()
        result = api.delete(workflow_id)

        if not result.get("success"):
            return fail(message=result.get("error", "Delete failed"), code=400)

        return ok(None, message="Delete successfully")
    except Exception as e:
        logger.error(f"Deletion workflow failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate", dependencies=[Depends(require_pro)])
async def validate_workflow(data: WorkflowCreate):
    """Validate workflow definition"""
    try:
        from core.api import WorkflowAPI
        api = WorkflowAPI()
        result = api.validate(data.model_dump())
        return ok(result)
    except Exception as e:
        logger.error(f"Validation workflow failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/execute", dependencies=[Depends(require_pro)])
async def execute_workflow(
    workflow_id: str,
    data: WorkflowExecuteRequest,
    user: dict = Depends(get_current_user)
):
    """Execution workflow - using v2.0 Unified Task Engine (asynchronous execution)

    Improvements:
    - Use v2.0 unified task engine to support asynchronous execution
    - Return task_id, the front end can poll the progress
    - Unified reporting format and progress tracking
    """
    try:
        from app.services.task_analysis_service import get_task_analysis_service
        from app.models.analysis import AnalysisTaskType
        from app.models.user import PyObjectId
        from tradingagents.utils.stock_utils import StockUtils, StockMarket
        from app.core.database import get_mongo_db

        task_service = get_task_analysis_service()
        user_id = str(user["id"])

        # 🆕 Query workflow type and input_config for dynamically determining parameters
        db = get_mongo_db()
        wf_doc = await db.workflows.find_one(
            {"_id": workflow_id},
            {"workflow_type": 1, "input_config": 1}
        )
        workflow_type = wf_doc.get("workflow_type", "stock_analysis") if wf_doc else "stock_analysis"
        input_config = wf_doc.get("input_config") if wf_doc else None

        logger.info(f"📊 [Workflow execution] workflow_id={workflow_id}, workflow_type={workflow_type}")

        # 🆕 Determine whether ticker is required based on workflow_type
        TICKER_REQUIRED_TYPES = {"stock_analysis", "etf_analysis"}
        if workflow_type in TICKER_REQUIRED_TYPES and not data.ticker:
            raise HTTPException(status_code=400, detail=f"Workflow type {workflow_type} The ticker parameter is required")

        # 🆕 Mapping based on workflow_type task_type
        WORKFLOW_TYPE_TO_TASK_TYPE = {
            "stock_analysis": AnalysisTaskType.STOCK_ANALYSIS,
            "etf_analysis": AnalysisTaskType.ETF_ANALYSIS,
            "position_analysis": AnalysisTaskType.POSITION_ANALYSIS,
            "trade_review": AnalysisTaskType.TRADE_REVIEW,
            "general": AnalysisTaskType.STOCK_ANALYSIS,  # general There is no independent task_type, use STOCK_ANALYSIS as the carrier
        }
        task_type = WORKFLOW_TYPE_TO_TASK_TYPE.get(workflow_type, AnalysisTaskType.STOCK_ANALYSIS)

        # Prepare task parameters
        task_params = {}

        # ticker Related parameters (only set if ticker is provided)
        if data.ticker:
            market = StockUtils.identify_stock_market(data.ticker)
            market_type_mapping = {
                StockMarket.CHINA_A: "cn",
                StockMarket.HONG_KONG: "hk",
                StockMarket.US: "us",
                StockMarket.UNKNOWN: "cn"
            }
            market_type = market_type_mapping.get(market, "cn")
            task_params["symbol"] = data.ticker
            task_params["stock_code"] = data.ticker
            task_params["market_type"] = market_type
            logger.info(f"📊 [Workflow execution] stocks {data.ticker} identified as market: {market_type}")

        # Common parameters
        task_params["analysis_date"] = data.analysis_date.strftime("%Y-%m-%d") if data.analysis_date else None
        task_params["research_depth"] = data.research_depth
        task_params["quick_analysis_model"] = data.quick_analysis_model
        task_params["deep_analysis_model"] = data.deep_analysis_model
        task_params["lookback_days"] = data.lookback_days
        task_params["max_debate_rounds"] = data.max_debate_rounds
        task_params["selected_analysts"] = data.selected_analysts if hasattr(data, 'selected_analysts') else None

        # 🆕 Supplement missing parameters based on the default value of input_config.fields
        if input_config and isinstance(input_config, dict):
            fields = input_config.get("fields", [])
            for field in fields:
                fname = field.get("name")
                if fname and fname not in task_params and fname not in ("ticker", "symbol", "stock_code"):
                    default_val = field.get("default")
                    if default_val is not None:
                        task_params[fname] = default_val
                        logger.debug(f"📋 [Workflow execution] Supplement parameters from input_config: {fname}={default_val}")

        # 🆕 Merge custom parameters (used in scenarios such as general research)
        if data.custom_params:
            task_params.update(data.custom_params)

        # 🆕 Mark the general type workflow with task_category to facilitate subsequent queries.
        if workflow_type == "general":
            task_params["task_category"] = "general"
            logger.info(f"🏷️ [Workflow execution] Marked as a general research task: workflow_type=general")

        logger.info(f"🚀 [Workflow execution] Create task: workflow_id={workflow_id}, ticker={data.ticker}, user={user_id}")

        # 🔥 Read risk preference settings from user preferences
        from app.routers.analysis import get_user_risk_preference
        preference_type = await get_user_risk_preference(user_id)
        logger.info(f"📊 [Workflow execution] Use user risk preferences: {preference_type}")

        # Create tasks using v2.0 Unified Task Engine
        task = await task_service.create_task(
            user_id=PyObjectId(user_id),
            task_type=task_type,
            task_params=task_params,
            engine_type="workflow",  # Force use of workflow engine
            preference_type=preference_type,  # 🔥 Use user preferences
            workflow_id=workflow_id  # Specify which workflow to use
        )

        # Execute tasks asynchronously (without waiting for completion)
        import asyncio
        asyncio.create_task(task_service.execute_task(task))

        logger.info(f"✅ [Workflow execution] Task has been created: task_id={task.task_id}")

        return ok({
            "task_id": task.task_id,
            "status": task.status,
            "message": "The task has been submitted and is being executed in the background"
        }, message="Task has been submitted")

    except Exception as e:
        logger.error(f"❌ [Workflow execution] Failed to create task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _save_analysis_report(
    ticker: str,
    analysis_date: Optional[datetime],
    research_depth: str,
    workflow_result: Dict[str, Any],
    model_info: str,
    task_id: Optional[str] = None,
    execution_time: float = 0.0
):
    """
    Save research report to MongoDB

    Extract individual reports from the workflow execution results and save them to the analysis_reports collection
    Maintains a reporting structure that is fully consistent with single stock analysis
    """
    try:
        from app.core.database import get_mongo_db
        from datetime import datetime as dt

        db = get_mongo_db()

        # 🔥 Generate analysis ID - use UTC time to keep consistent with old versions
        timestamp = dt.utcnow()
        analysis_id = f"{ticker}_{timestamp.strftime('%Y%m%d_%H%M%S')}"

        # 🔍 Debugging: Print all keys of workflow_result
        logger.info(f"[report save] 🔍 workflow_result Contained fields: {list(workflow_result.keys())}")
        # Check whether index_report and sector_report exist
        if "index_report" in workflow_result:
            logger.info(f"[report save] ✅ index_report exist, length: {len(str(workflow_result.get('index_report', '')))}")
        else:
            logger.warning(f"[report save] ❌ index_report does not exist in workflow_result")
        if "sector_report" in workflow_result:
            logger.info(f"[report save] ✅ sector_report exist, length: {len(str(workflow_result.get('sector_report', '')))}")
        else:
            logger.warning(f"[report save] ❌ sector_report does not exist in workflow_result")

        # Extract reports from workflow results (String type)
        reports = {}
        string_report_fields = [
            # 🆕 Macro research reports (priority extraction)
            ("index_report", "Market Index Research Report"),
            ("sector_report", "Industry sector research report"),
            # Individual stock research reports
            ("market_report", "market research report"),
            ("sentiment_report", "Emotion research report"),
            ("news_report", "news research report"),
            ("fundamentals_report", "Fundamental Research Report"),
            # Risk and debate related direct out fields (if present, save directly)
            ("risk_assessment", "Risk assessment conclusion"),
            ("bull_report", "positive evidence research report"),
            ("bear_report", "Prudence Evidence Research Report"),
            ("risky_opinion", "Highly resilient scenario perspective"),
            ("safe_opinion", "defensive situational view"),
            ("neutral_opinion", "neutral risk view"),
            ("investment_plan", "Research team s conclusion"),
            ("trader_investment_plan", "Research and integrate opinions"),
            ("final_trade_decision", "final research conclusion"),
        ]

        def _extract_text(v):
            if isinstance(v, str):
                return v
            if isinstance(v, dict):
                for k in ("content", "markdown", "text", "message", "report"):
                    x = v.get(k)
                    if isinstance(x, str) and x.strip():
                        return x
            return ""
        for field_name, report_name in string_report_fields:
            content_raw = workflow_result.get(field_name, "")
            content = _extract_text(content_raw)
            if content and isinstance(content, str) and len(content.strip()) > 5:
                reports[field_name] = content
                logger.info(f"[report save] Extract report: {report_name} ({len(content)} character)")

        # Handle research team debate status (dict type) - split into independent sub-reports
        investment_debate = workflow_result.get("investment_debate_state", {})
        if investment_debate and isinstance(investment_debate, dict):
            # 1. Bull Researcher Report
            bull_history = _extract_text(investment_debate.get("bull_history", ""))
            if bull_history and len(bull_history.strip()) > 5:
                reports["bull_researcher"] = bull_history
                logger.info(f"[report save] Extract report: multi-investigator ({len(bull_history)} character)")

            # 2. Short Researcher Report
            bear_history = _extract_text(investment_debate.get("bear_history", ""))
            if bear_history and len(bear_history.strip()) > 5:
                reports["bear_researcher"] = bear_history
                logger.info(f"[report save] Extract report: short researcher ({len(bear_history)} character)")

            # 3. Research Manager Research Report
            judge_decision = _extract_text(investment_debate.get("judge_decision", ""))
            if judge_decision and len(judge_decision.strip()) > 5:
                reports["research_team_decision"] = judge_decision
                logger.info(f"[report save] Extract report: Research Manager Analysis ({len(judge_decision)} character)")
            else:
                formatted = _format_research_team_report(investment_debate)
                if formatted and len(formatted.strip()) > 5:
                    reports["research_team_decision"] = formatted
                    logger.info(f"[report save] Generate report: Research manager comprehensive decision-making ({len(formatted)} character)")

        # Handling risk management team debate status (dict type) - split into independent sub-reports
        risk_debate = workflow_result.get("risk_debate_state", {})
        if risk_debate and isinstance(risk_debate, dict):
            # 1. activist analyst report
            risky_history = _extract_text(risk_debate.get("risky_history", ""))
            if risky_history and len(risky_history.strip()) > 5:
                reports["risky_analyst"] = risky_history
                logger.info(f"[report save] Extract report: activist analyst ({len(risky_history)} character)")

            # 2. conservative analyst report
            safe_history = _extract_text(risk_debate.get("safe_history", ""))
            if safe_history and len(safe_history.strip()) > 5:
                reports["safe_analyst"] = safe_history
                logger.info(f"[report save] Extract report: conservative analyst ({len(safe_history)} character)")

            # 3. Neutral analyst report
            neutral_history = _extract_text(risk_debate.get("neutral_history", ""))
            if neutral_history and len(neutral_history.strip()) > 5:
                reports["neutral_analyst"] = neutral_history
                logger.info(f"[report save] Extract report: neutral analyst ({len(neutral_history)} character)")

            # 4. Risk Assessor Decision Report
            judge_decision = _extract_text(risk_debate.get("judge_decision", ""))
            if judge_decision and len(judge_decision.strip()) > 5:
                reports["risk_management_decision"] = judge_decision
                logger.info(f"[report save] Extract report: risk assessor ({len(judge_decision)} character)")
            else:
                formatted = _format_risk_management_report(risk_debate)
                if formatted and len(formatted.strip()) > 5:
                    reports["risk_management_decision"] = formatted
                    logger.info(f"[report save] Generate report: Comprehensive decision-making by the risk management team ({len(formatted)} character)")

        if not reports:
            logger.warning("[report save] No report content found, skip saving")
            return

        # Get stock name and market type
        stock_name = ticker
        market_type = "A shares"
        try:
            from tradingagents.utils.stock_utils import StockUtils
            market_info = StockUtils.get_market_info(ticker)
            market_type_map = {
                "china_a": "A shares",
                "hong_kong": "Hong Kong stocks",
                "us": "US stocks",
                "unknown": "A shares"
            }
            market_type = market_type_map.get(market_info.get("market", "unknown"), "A shares")

            # Try to get the stock name
            if market_info.get("market") == "china_a":
                from tradingagents.dataflows.interface import get_china_stock_info_unified
                stock_info = get_china_stock_info_unified(ticker)
                if "Stock name:" in stock_info:
                    stock_name = stock_info.split("Stock name:")[1].split("\n")[0].strip()
        except Exception as e:
            logger.warning(f"[report save] Failed to obtain stock information: {e}")

        # Extract recommendations and confidence_score
        recommendation, confidence_score, risk_level = _extract_recommendation_and_confidence(
            workflow_result, reports
        )

        # 🔥 Extract decision field (consistent with single stock analysis)
        decision = workflow_result.get("decision", {})
        if not decision:
            # If there is no decision field, try to build from the final research conclusion
            final_decision_text = _extract_text(workflow_result.get("final_trade_decision", ""))
            if final_decision_text:
                decision = {
                    "action": recommendation,
                    "confidence": confidence_score,
                    "risk_level": risk_level,
                    "reasoning": final_decision_text[:200]  # Truncate the first 200 characters as the reason
                }

        # 🔥 Extract key takeaways (aligned with single stock analysis)
        key_points = workflow_result.get("key_points", [])
        if not key_points:
            # If there are no key_points, try to extract from the summary
            summary_text = _extract_text(workflow_result.get("final_trade_decision", ""))
            if summary_text:
                # Simple extraction: split by row, take the first 5 rows as key points
                lines = [line.strip() for line in summary_text.split('\n') if line.strip()]
                key_points = lines[:5]

        # Build documentation (exactly the same as single stock analysis)
        document = {
            "analysis_id": analysis_id,
            "stock_symbol": ticker,
            "stock_name": stock_name,
            "market_type": market_type,
            "model_info": model_info,
            "analysis_date": analysis_date.strftime('%Y-%m-%d') if analysis_date else timestamp.strftime('%Y-%m-%d'),
            "timestamp": timestamp,
            "status": "completed",
            "source": "workflow",

            # Summary of analysis results
            "summary": (_extract_text(workflow_result.get("final_trade_decision", ""))[:500]
                        if workflow_result.get("final_trade_decision") else ""),
            "analysts": _get_analysts_from_reports(reports),
            "research_depth": research_depth,

            # Report content
            "reports": reports,

            # 🔥 Key field: decision (consistent with single stock analysis)
            "decision": decision,

            # metadata
            "created_at": timestamp,
            "updated_at": timestamp,

            # API Unique fields (consistent with single stock analysis)
            "task_id": task_id or "",
            "recommendation": recommendation,
            "confidence_score": confidence_score,
            "risk_level": risk_level,
            "key_points": key_points,
            "execution_time": execution_time,
            "tokens_used": workflow_result.get("tokens_used", 0),

            # 🆕 Performance indicator data (consistent with single stock analysis)
            "performance_metrics": workflow_result.get("performance_metrics", {})
        }

        # save to MongoDB
        result = await db.analysis_reports.insert_one(document)

        if result.inserted_id:
            logger.info(f"✅ [report save] Research report has been saved to MongoDB: {analysis_id}, total {len(reports)} reporting modules")
        else:
            logger.error("❌ [report save] MongoDB Insertion failed")

    except Exception as e:
        logger.error(f"❌ [report save] Failed to save research report: {e}")
        import traceback
        logger.error(f"❌ [report save] detailed error: {traceback.format_exc()}")


def _extract_recommendation_and_confidence(
    workflow_result: Dict[str, Any],
    reports: Dict[str, Any]
) -> tuple:
    """
    Extract recommendation, confidence_score and risk_level

    Extraction logic:
    1. recommendation: Extract research summaries from safety reports
    2. confidence_score: Extract confidence from text, or calculate based on analytical consistency
    3. risk_level: Extract from risk management decisions

    Returns:
        tuple: (recommendation, confidence_score, risk_level)
    """
    import re

    def _text(v):
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            for k in ("content", "markdown", "text", "message", "report"):
                x = v.get(k)
                if isinstance(x, str) and x.strip():
                    return x
        return ""

    recommendation = GENERIC_RESEARCH_RECOMMENDATION
    confidence_score = 0.0
    risk_level = "medium"

    safe_reports = filter_analysis_reports(reports or {})
    research_summary = build_research_summary(safe_reports, workflow_result.get("summary", ""))
    if research_summary:
        recommendation = research_summary[:200]

    # 2. Extract confidence_score (confidence)
    # Try to extract confidence value from text
    confidence_patterns = [
        r'Confidence[: :]\s*([0-9.]+)%?',
        r'confidence[：:]\s*([0-9.]+)%?',
        r'Credibility[: :]\s*([0-9.]+)%?',
        r'grasp[: :]\s*([0-9.]+)%?',
    ]
    for pattern in confidence_patterns:
        match = re.search(pattern, research_summary, re.IGNORECASE)
        if match:
            try:
                conf_val = float(match.group(1))
                # If the value is greater than 1, it is considered a percentage and needs to be divided by 100
                if conf_val > 1:
                    conf_val = conf_val / 100
                confidence_score = min(1.0, max(0.0, conf_val))
                break
            except ValueError:
                pass

    # If not extracted, estimate confidence based on analytical consistency
    if confidence_score == 0.0:
        # Check how many reports are in agreement
        report_count = len(safe_reports)
        if report_count >= 10:
            confidence_score = 0.85  # full analysis
        elif report_count >= 7:
            confidence_score = 0.75  # standard analysis
        elif report_count >= 4:
            confidence_score = 0.65  # Fundamental analysis
        else:
            confidence_score = 0.55  # Quick analysis

    # 3. Extract risk_level (risk level)
    risk_decision = _text(reports.get("risk_management_decision", ""))
    if risk_decision:
        if re.search(r'high risk|higher risk|cautious', risk_decision):
            risk_level = "high risk"
        elif re.search(r'low risk|lower risk|safe', risk_decision):
            risk_level = "low risk"
        else:
            risk_level = "medium"

    logger.info(f"[report save] Extract results: recommendation={len(recommendation)}character, confidence={confidence_score:.2f}, risk={risk_level}")

    return recommendation, confidence_score, risk_level


def _get_analysts_from_reports(reports: Dict[str, Any]) -> List[str]:
    """
    Dynamically generate analyst lists based on saved reports

    The return format is compatible with older systems and is used for front-end display tabs
    """
    # Mapping of report fields to analyst IDs
    report_to_analyst = {
        # Analyst team (4)
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        # Research team (3)
        "bull_researcher": "bull_researcher",
        "bear_researcher": "bear_researcher",
        "research_team_decision": "research_manager",
        # Trading team (1)
        "trader_investment_plan": "trader",
        # Risk management team (4)
        "risky_analyst": "risky_analyst",
        "safe_analyst": "safe_analyst",
        "neutral_analyst": "neutral_analyst",
        "risk_management_decision": "portfolio_manager",
        # Final research conclusion (1)
        "final_trade_decision": "final_decision",
    }

    analysts = []
    for report_key, analyst_id in report_to_analyst.items():
        if report_key in reports and reports[report_key]:
            # Check if the report content is valid (non-empty string or non-empty dictionary)
            content = reports[report_key]
            if isinstance(content, str) and len(content) > 10:
                analysts.append(analyst_id)
            elif isinstance(content, dict) and content:
                analysts.append(analyst_id)

    return analysts


def _format_research_team_report(debate_state: Dict[str, Any]) -> str:
    """
    Formatted Research Team Research Report

    Extracted from investment_debate_state bull_history, bear_history, judge_decision
    """
    parts = []
    parts.append("# 🔬 Research team research report\n")

    # Analysis by bull researchers
    bull_history = debate_state.get("bull_history", "")
    if bull_history:
        parts.append("## 📈 Analysis by bull researchers\n")
        parts.append(bull_history)
        parts.append("\n")

    # Short Researcher Analysis
    bear_history = debate_state.get("bear_history", "")
    if bear_history:
        parts.append("## 📉 Short Researcher Analysis\n")
        parts.append(bear_history)
        parts.append("\n")

    # Research manager's comprehensive conclusion
    judge_decision = debate_state.get("judge_decision", "")
    if judge_decision:
        parts.append("## 🎯 Research manager s comprehensive conclusion\n")
        parts.append(judge_decision)
        parts.append("\n")

    return "\n".join(parts) if len(parts) > 1 else ""


def _format_risk_management_report(debate_state: Dict[str, Any]) -> str:
    """
    Formatting Risk Review Conclusions

    Extracted from risk_debate_state risky_history, safe_history, neutral_history, judge_decision
    """
    parts = []
    parts.append("# 👔 Risk review conclusion\n")

    # Highly Resilient Scenario Analyst Perspective
    risky_history = debate_state.get("risky_history", "")
    if risky_history:
        parts.append("## 🔥 Highly Resilient Scenario Analyst Perspective\n")
        parts.append(risky_history)
        parts.append("\n")

    # Defense Scenario Analyst Perspective
    safe_history = debate_state.get("safe_history", "")
    if safe_history:
        parts.append("## 🛡️ Defense Scenario Analyst Perspective\n")
        parts.append(safe_history)
        parts.append("\n")

    # Baseline Scenario Analyst View
    neutral_history = debate_state.get("neutral_history", "")
    if neutral_history:
        parts.append("## ⚖️ Baseline Scenario Analyst View\n")
        parts.append(neutral_history)
        parts.append("\n")

    # Risk assessor's final conclusion
    judge_decision = debate_state.get("judge_decision", "")
    if judge_decision:
        parts.append("## 🎯 Risk assessor s final conclusion\n")
        parts.append(judge_decision)
        parts.append("\n")

    return "\n".join(parts) if len(parts) > 1 else ""


async def _build_legacy_config(data: WorkflowExecuteRequest) -> Dict[str, Any]:
    """
    Building LLM configurations for legacy agents

    Use the new ModelConfig first, otherwise query the database based on the model name

    How it is used in old code:
    - quick_thinking_llm: For analysts, researchers(Bull/Bear), Research Integrator, Risk Scenario Analyst
    - deep_thinking_llm: for research integrators(Research Manager), risk assessor(Risk Manager)
    """
    config = {}

    # 🔑 Added selected_analysts (for dynamic cropping workflow)
    if data.selected_analysts:
        config["selected_analysts"] = data.selected_analysts
        logger.info(f"[Workflow execution] selected analysts: {data.selected_analysts}")

    # Prioritize new complete configurations
    if data.quick_model_config:
        qc = data.quick_model_config
        config["llm_provider"] = qc.provider
        config["quick_think_llm"] = qc.model_name
        config["backend_url"] = qc.api_base or ""
        config["quick_api_key"] = qc.api_key
        config["quick_temperature"] = qc.temperature
        config["quick_max_tokens"] = qc.max_tokens
        config["quick_timeout"] = qc.timeout

        # If there is no deep configuration, the quick configuration will be used by default.
        if not data.deep_model_config:
            config["deep_think_llm"] = qc.model_name
            config["deep_api_key"] = qc.api_key

    if data.deep_model_config:
        dc = data.deep_model_config
        config["deep_think_llm"] = dc.model_name
        config["deep_api_key"] = dc.api_key
        config["deep_backend_url"] = dc.api_base or ""
        config["deep_temperature"] = dc.temperature
        config["deep_max_tokens"] = dc.max_tokens
        config["deep_timeout"] = dc.timeout

        # If quick and deep are from different manufacturers, mark them as mixed mode
        if data.quick_model_config and data.quick_model_config.provider != dc.provider:
            config["quick_llm_provider"] = data.quick_model_config.provider
            config["deep_llm_provider"] = dc.provider
        elif not data.quick_model_config:
            # If there is no quick configuration, use the deep configuration.
            config["llm_provider"] = dc.provider
            config["quick_think_llm"] = dc.model_name
            config["quick_api_key"] = dc.api_key

    # If you already have a complete configuration, you need to complete it from the database. API Key
    if config and not config.get("quick_api_key"):
        config = await _fill_api_keys_from_db(config)

    # If there is no new configuration, try to get from the old fields and database
    if not config:
        config = await _get_llm_config_for_model(
            data.quick_analysis_model,
            data.deep_analysis_model
        )

    return config


async def _fill_api_keys_from_db(config: Dict[str, Any]) -> Dict[str, Any]:
    """Populate from database API Keys"""
    from app.core.database import get_mongo_db
    import os

    db = get_mongo_db()

    provider = config.get("llm_provider") or config.get("quick_llm_provider")
    if provider:
        provider_doc = await db.llm_providers.find_one({"name": provider})
        if provider_doc:
            api_key = provider_doc.get("api_key", "")
            if api_key and not api_key.startswith("sk-xxx"):
                config["quick_api_key"] = api_key
                if not config.get("deep_api_key"):
                    config["deep_api_key"] = api_key

    # If the deep manufacturer is different, you also need to obtain its API Key
    deep_provider = config.get("deep_llm_provider")
    if deep_provider and deep_provider != provider:
        provider_doc = await db.llm_providers.find_one({"name": deep_provider})
        if provider_doc:
            api_key = provider_doc.get("api_key", "")
            if api_key and not api_key.startswith("sk-xxx"):
                config["deep_api_key"] = api_key

    return config


async def _get_llm_config_for_model(quick_model: Optional[str], deep_model: Optional[str]) -> Dict[str, Any]:
    """
    Get the complete LLM configuration from the database based on the model name

    Args:
        quick_model: Quickly analyze model names
        deep_model: In-depth analysis model name

    Returns:
        Complete configuration including provider, api_key, backend_url, etc.
    """
    if not quick_model and not deep_model:
        return {}

    from app.core.database import get_mongo_db

    db = get_mongo_db()

    # Get system configuration
    config_doc = await db.system_configs.find_one(
        {"is_active": True},
        sort=[("version", -1)]
    )

    if not config_doc or "llm_configs" not in config_doc:
        logger.warning("[Workflow execution] There is no LLM configuration in the database")
        return {}

    llm_configs = config_doc["llm_configs"]

    # Find matching model configurations
    target_model = quick_model or deep_model
    model_config = None

    for cfg in llm_configs:
        if cfg.get("model_name") == target_model and cfg.get("enabled", True):
            model_config = cfg
            break

    if not model_config:
        logger.warning(f"[Workflow execution] Model configuration not found: {target_model}")
        return {}

    # Get factory configuration
    provider_name = model_config.get("provider", "")
    provider_doc = await db.llm_providers.find_one({"name": provider_name})

    api_key = None
    backend_url = model_config.get("api_base", "")

    if provider_doc:
        api_key = provider_doc.get("api_key", "")
        if not backend_url:
            backend_url = provider_doc.get("default_base_url", "")

    # If the database does not have an API Key, try to get it from the environment variable
    if not api_key or api_key.startswith("sk-xxx"):
        import os
        env_key_map = {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "google": "GOOGLE_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
        }
        env_name = env_key_map.get(provider_name.lower())
        if env_name:
            api_key = os.getenv(env_name)

    result = {
        "llm_provider": provider_name,
        "quick_think_llm": quick_model or target_model,
        "deep_think_llm": deep_model or target_model,
        "backend_url": backend_url,
        "api_key": api_key,
        "quick_temperature": model_config.get("temperature", 0.1),
        "quick_max_tokens": model_config.get("max_tokens", 2000),
        "quick_timeout": model_config.get("timeout", 60),
    }

    logger.info(f"[Workflow execution] Get model configuration from database: provider={provider_name}, model={target_model}")

    return result


class CreateFromTemplateRequest(BaseModel):
    """Create request from template"""
    template_id: str
    name: str


@router.post("/from-template", dependencies=[Depends(require_pro)])
async def create_from_template(data: CreateFromTemplateRequest):
    """Create a workflow from a template"""
    template_id = data.template_id
    name = data.name
    try:
        from core.api import WorkflowAPI
        api = WorkflowAPI()

        # Get template
        templates = api.get_templates()
        template = next((t for t in templates if t.get("id") == template_id), None)

        if template is None:
            raise HTTPException(status_code=404, detail="Template does not exist")

        # Create new workflow
        new_workflow = {
            **template,
            "name": name,
            "is_template": False
        }
        # Remove the original ID and let the system generate a new one ID
        new_workflow.pop("id", None)
        new_workflow.pop("created_at", None)
        new_workflow.pop("updated_at", None)

        result = api.create(new_workflow)

        if not result.get("success"):
            return fail(
                message="Create from template failed",
                code=400,
                data={"errors": result.get("errors", ["Creation failed"])}
            )

        return ok(result.get("workflow"), message="Created successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Creating workflow from template failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class DuplicateRequest(BaseModel):
    """Copy workflow request"""
    name: str


@router.post("/{workflow_id}/duplicate", dependencies=[Depends(require_pro)])
async def duplicate_workflow(workflow_id: str, data: DuplicateRequest):
    """Copy workflow"""
    try:
        from core.api import WorkflowAPI
        api = WorkflowAPI()

        # Get the original workflow
        workflow = api.get(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow does not exist")

        # Create a copy
        new_workflow = {
            **workflow,
            "name": data.name,
            "is_template": False,
        }
        # Remove the original ID and let the system generate a new one ID
        new_workflow.pop("id", None)
        new_workflow.pop("created_at", None)
        new_workflow.pop("updated_at", None)

        result = api.create(new_workflow)

        if not result.get("success"):
            return fail(
                message="Copy failed",
                code=400,
                data={"errors": result.get("errors", ["Copy failed"])}
            )

        return ok(result.get("workflow"), message="Copied successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Copy workflow failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/set-default", dependencies=[Depends(require_pro)])
async def set_as_default(workflow_id: str):
    """Set as default analysis flow"""
    try:
        from core.api import WorkflowAPI
        from core.workflow.default_workflow_provider import get_default_workflow_provider
        api = WorkflowAPI()

        # Get workflow
        workflow = api.get(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow does not exist")

        workflow_name = workflow.get("name", "")
        provider = get_default_workflow_provider()
        workflow_type = provider.infer_workflow_type(workflow, workflow_id)

        # Save as the default analysis flow configuration: the file is used for local analysis, and the database is used for runtime loading.
        import json
        from pathlib import Path

        config_path = Path("config/settings.json")
        config = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

        config.setdefault("default_workflows", {})
        config["default_workflows"][workflow_type] = {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
        }
        if workflow_type == "stock_analysis":
            config["default_workflow_id"] = workflow_id
            config["default_workflow_name"] = workflow_name

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        from app.core.database import get_mongo_db
        db = get_mongo_db()
        await db.workflows.update_many(
            {"workflow_type": workflow_type, "is_default": True},
            {"$set": {"is_default": False, "updated_at": datetime.utcnow()}},
        )
        await db.workflows.update_many(
            {"config.workflow_type": workflow_type, "is_default": True},
            {"$set": {"is_default": False, "updated_at": datetime.utcnow()}},
        )
        await db.workflows.update_one(
            {"id": workflow_id},
            {
                "$set": {
                    "is_default": True,
                    "workflow_type": workflow_type,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        await db.system_configs.update_one(
            {"is_active": True},
            {
                "$set": {
                    "active_workflow_id": workflow_id,
                    "active_workflow_name": workflow_name,
                    "default_workflow_id": workflow_id,
                    "default_workflow_name": workflow_name,
                    f"default_workflows.{workflow_type}": {
                        "workflow_id": workflow_id,
                        "workflow_name": workflow_name,
                    },
                    "updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"created_at": datetime.utcnow()},
            },
            upsert=True,
        )

        return ok(message=f"Already '{workflow_name}' set to {workflow_type} Default analysis flow")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Setting default analysis flow failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

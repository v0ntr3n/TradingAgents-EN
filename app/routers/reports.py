"""
Research Report Management API Routing
"""
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .auth_db import get_current_user
from ..core.database import get_mongo_db
from ..utils.timezone import to_config_tz
import logging

logger = logging.getLogger("webapi")

ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")

# Stock name cache
_stock_name_cache = {}
_DISPLAY_SANITIZED_MODULE_KEYS = {
    "bull_researcher",
    "bull_report",
    "bear_researcher",
    "bear_report",
    "research_team_decision",
    "investment_plan",
    "trader_investment_plan",
    "risky_analyst",
    "risky_opinion",
    "safe_analyst",
    "safe_opinion",
    "neutral_analyst",
    "neutral_opinion",
    "risk_management_decision",
}


def _is_cn_etf_symbol(stock_code: str) -> bool:
    code_str = str(stock_code or "").strip().zfill(6)
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


def _is_invalid_stock_name(stock_code: str, stock_name: Optional[str]) -> bool:
    if not stock_name:
        return True
    code_str = str(stock_code or "").strip().zfill(6)
    name = str(stock_name).strip()
    generic_names = {
        code_str,
        stock_code,
        f"stocks{code_str}",
        f"stocks{stock_code}",
        f"ETF{code_str}",
        f"ETF{stock_code}",
    }
    return name in generic_names

def get_stock_name(stock_code: str) -> str:
    """
    Get stock name
    Priority: Cache -> MongoDB (By data source priority) -> Returns stock code by default
    """
    global _stock_name_cache

    # Check cache
    if stock_code in _stock_name_cache:
        return _stock_name_cache[stock_code]

    try:
        # Get stock names from MongoDB
        from ..core.database import get_mongo_db_sync
        from ..core.unified_config import UnifiedConfigManager

        db = get_mongo_db_sync()
        code6 = str(stock_code).zfill(6)

        if _is_cn_etf_symbol(code6):
            etf_info = db.etf_basic_info.find_one(
                {"code": code6},
                {"name": 1, "fund_name": 1, "etf_name": 1}
            )
            if etf_info:
                etf_name = etf_info.get("name") or etf_info.get("fund_name") or etf_info.get("etf_name")
                if etf_name:
                    _stock_name_cache[stock_code] = etf_name
                    return etf_name

        # 🔥 Query by data source priority
        config = UnifiedConfigManager()
        data_source_configs = config.get_data_source_configs()

        # Extract enabled data sources, sorted by priority
        enabled_sources = [
            ds.type.lower() for ds in data_source_configs
            if ds.enabled and ds.type.lower() in ['tushare', 'akshare', 'baostock']
        ]

        if not enabled_sources:
            enabled_sources = ['tushare', 'akshare', 'baostock']

        # Query by data source priority
        stock_info = None
        for data_source in enabled_sources:
            stock_info = db.stock_basic_info.find_one(
                {"$or": [{"symbol": code6}, {"code": code6}], "source": data_source}
            )
            if stock_info:
                logger.debug(f"✅ Use data sources {data_source} Get stock name {code6}")
                break

        # If all data sources are not available, try querying without source conditions (compatible with old data)
        if not stock_info:
            stock_info = db.stock_basic_info.find_one(
                {"$or": [{"symbol": code6}, {"code": code6}]}
            )
            if stock_info:
                logger.warning(f"⚠️ Get stock name using old data (no source field) {code6}")

        if stock_info and stock_info.get("name"):
            stock_name = stock_info["name"]
            _stock_name_cache[stock_code] = stock_name
            return stock_name

        # If not found, returns the stock code
        _stock_name_cache[stock_code] = stock_code
        return stock_code

    except Exception as e:
        logger.warning(f"⚠️ Failed to get stock name {stock_code}: {e}")
        return stock_code


# Unified build report query: supported _id(ObjectId) / analysis_id / task_id three kinds
def _build_report_query(report_id: str) -> Dict[str, Any]:
    ors = [
        {"analysis_id": report_id},
        {"task_id": report_id},
    ]
    try:
        from bson import ObjectId
        ors.append({"_id": ObjectId(report_id)})
    except Exception:
        pass
    return {"$or": ors}


def _rebuild_report_modules(raw_result: Dict[str, Any], existing_reports: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Restore the complete reporting module from the original results of the task whenever possible."""
    rebuilt_reports: Dict[str, Any] = {}
    from app.utils.compliance import sanitize_display_report_text

    if isinstance(existing_reports, dict):
        for key, value in existing_reports.items():
            if key == "structured_reports":
                continue
            if isinstance(value, str) and value.strip():
                text_value = value.strip()
                if key in _DISPLAY_SANITIZED_MODULE_KEYS:
                    text_value = sanitize_display_report_text(text_value, fallback=text_value)
                rebuilt_reports[key] = text_value
            elif value is not None:
                text_value = str(value).strip()
                if text_value:
                    if key in _DISPLAY_SANITIZED_MODULE_KEYS:
                        text_value = sanitize_display_report_text(text_value, fallback=text_value)
                    rebuilt_reports[key] = text_value

    if not isinstance(raw_result, dict):
        return rebuilt_reports

    try:
        from app.utils.report_formatter import extract_reports_from_state

        extracted_from_result = extract_reports_from_state(raw_result)
        if extracted_from_result:
            rebuilt_reports.update(extracted_from_result)

        state = raw_result.get("state")
        if state:
            extracted_from_state = extract_reports_from_state(state)
            if extracted_from_state:
                rebuilt_reports.update(extracted_from_state)
    except Exception as e:
        logger.warning(f"⚠️ Restoring full reporting module failed: {e}")

    return rebuilt_reports

router = APIRouter(prefix="/api/reports", tags=["reports"])

class ReportFilter(BaseModel):
    """Report filter parameters"""
    search_keyword: Optional[str] = None
    market_filter: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    stock_code: Optional[str] = None
    report_type: Optional[str] = None

class ReportListResponse(BaseModel):
    """Report list response"""
    reports: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int

@router.get("/list", response_model=Dict[str, Any])
async def get_reports_list(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Quantity per page"),
    search_keyword: Optional[str] = Query(None, description="Search keywords"),
    market_filter: Optional[str] = Query(None, description="Market screening (A shares/Hong Kong stocks/US stocks)"),
    start_date: Optional[str] = Query(None, description="start date"),
    end_date: Optional[str] = Query(None, description="end date"),
    stock_code: Optional[str] = Query(None, description="Stock code"),
    user: dict = Depends(get_current_user)
):
    """Get a list of research reports"""
    try:
        logger.info(f"🔍 Get report list: User={user['id']}, Page number={page}, per page={page_size}, market={market_filter}")

        db = get_mongo_db()

        # Build query conditions
        query = {}

        # Search keywords
        if search_keyword:
            query["$or"] = [
                {"stock_symbol": {"$regex": search_keyword, "$options": "i"}},
                {"analysis_id": {"$regex": search_keyword, "$options": "i"}},
                {"summary": {"$regex": search_keyword, "$options": "i"}}
            ]

        # Market screening
        if market_filter:
            query["market_type"] = market_filter

        # Stock code filter
        if stock_code:
            query["stock_symbol"] = stock_code

        # Date range filter
        if start_date or end_date:
            date_query = {}
            if start_date:
                date_query["$gte"] = start_date
            if end_date:
                date_query["$lte"] = end_date
            query["analysis_date"] = date_query

        logger.info(f"📊 Query conditions: {query}")

        # Calculate the total
        total = await db.analysis_reports.count_documents(query)

        # Page query
        skip = (page - 1) * page_size
        cursor = db.analysis_reports.find(query).sort("created_at", -1).skip(skip).limit(page_size)

        reports = []
        async for doc in cursor:
            # Convert to the format required by the front end
            stock_code = doc.get("stock_symbol", "")
            # 🔥 Prioritize using the stock name saved in MongoDB, if not, query
            stock_name = doc.get("stock_name")
            if _is_invalid_stock_name(stock_code, stock_name):
                stock_name = get_stock_name(stock_code)

            # 🔥 Gets the market type, or infers it from the ticker if not available
            market_type = doc.get("market_type")
            if not market_type:
                from tradingagents.utils.stock_utils import StockUtils
                market_info = StockUtils.get_market_info(stock_code)
                market_type_map = {
                    "china_a": "A shares",
                    "hong_kong": "Hong Kong stocks",
                    "us": "US stocks",
                    "unknown": "A shares"
                }
                market_type = market_type_map.get(market_info.get("market", "unknown"), "A shares")

            # Get the creation time (it is UTC time in the database and needs to be converted to UTC+8) 
            created_at = doc.get("created_at", datetime.utcnow())
            created_at_tz = to_config_tz(created_at)  # Convert to UTC+8 and add time zone information

            report = {
                "id": str(doc["_id"]),
                "analysis_id": doc.get("analysis_id", ""),
                "title": f"{stock_name}({stock_code}) research report",
                "stock_code": stock_code,
                "stock_name": stock_name,
                "market_type": market_type,  # 🔥 Add market type field
                "model_info": doc.get("model_info", "Unknown"),  # 🔥 Add model information fields
                "type": "single",  # At present, it is mainly single-stock research
                "format": "markdown",  # Main format
                "status": doc.get("status", "completed"),
                "created_at": created_at_tz.isoformat() if created_at_tz else str(created_at),
                "analysis_date": doc.get("analysis_date", ""),
                "analysts": doc.get("analysts", []),
                "research_depth": doc.get("research_depth", 1),
                "summary": doc.get("summary", ""),
                "file_size": len(str(doc.get("reports", {}))),  # Estimate size
                "source": doc.get("source", "unknown"),
                "task_id": doc.get("task_id", "")
            }
            reports.append(report)

        logger.info(f"✅ Query completed: total={total}, Return={len(reports)}")

        return {
            "success": True,
            "data": {
                "reports": reports,
                "total": total,
                "page": page,
                "page_size": page_size
            },
            "message": "Report list obtained successfully"
        }

    except Exception as e:
        logger.error(f"❌ Failed to get report list: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{report_id}/detail")
async def get_report_detail(
    report_id: str,
    include_state: bool = Query(False, description="Whether to include the complete workflow status (for debugging)"),
    include_detailed: bool = Query(False, description="Whether to include detailed analysis data (for debugging)"),
    user: dict = Depends(get_current_user)
):
    """Get report details
    
    By default, only necessary fields are returned (reports, decision, summary etc.), excluding state and detailed_analysis.
    For complete data, query parameters include_state=true&include_detailed=true Get.
    """
    try:
        logger.info(f"🔍 Get report details: {report_id}")

        db = get_mongo_db()

        # support ObjectId / analysis_id / task_id
        query = _build_report_query(report_id)
        doc = await db.analysis_reports.find_one(query)

        if not doc:
            # Bottom line: Restore report details from unified_analysis_tasks or analysis_tasks.result
            logger.info(f"⚠️ Not found in analysis_reports, try restoring from task center: {report_id}")
            
            # First try querying from unified_analysis_tasks (new task center)
            from bson import ObjectId
            tasks_doc = None
            
            # Try to query unified_analysis_tasks (requires user_id, but try not to restrict users here)
            try:
                # First try to query by task_id
                tasks_doc = await db.unified_analysis_tasks.find_one(
                    {"task_id": report_id},
                    {"result": 1, "task_id": 1, "task_type": 1, "task_params": 1, "created_at": 1, "completed_at": 1, "status": 1}
                )
            except Exception as e:
                logger.warning(f"⚠️ Query for unified_analysis_tasks failed: {e}")
            
            # If not found in unified_analysis_tasks, try querying from analysis_tasks (old system)
            if not tasks_doc:
                logger.info(f"⚠️ unified_analysis_tasks Not found in, try querying from analysis_tasks: {report_id}")
                tasks_doc = await db.analysis_tasks.find_one(
                    {"$or": [{"task_id": report_id}, {"result.analysis_id": report_id}]},
                    {"result": 1, "task_id": 1, "stock_code": 1, "created_at": 1, "completed_at": 1}
                )
            
            if not tasks_doc or not tasks_doc.get("result"):
                raise HTTPException(status_code=404, detail="Report does not exist")

            r = tasks_doc["result"] or {}
            created_at = tasks_doc.get("created_at")
            updated_at = tasks_doc.get("completed_at") or created_at

            # Convert time zone: The UTC time in the database is converted to UTC+8
            created_at_tz = to_config_tz(created_at)
            updated_at_tz = to_config_tz(updated_at)

            def to_iso(x):
                if hasattr(x, "isoformat"):
                    return x.isoformat()
                return x or ""

            # Extract stock symbol from result or task_params
            task_params = tasks_doc.get("task_params", {})
            stock_symbol = (
                r.get("stock_symbol") or 
                r.get("stock_code") or 
                task_params.get("symbol") or 
                task_params.get("stock_code") or 
                task_params.get("code") or
                tasks_doc.get("stock_code", "")
            )
            stock_name = r.get("stock_name")
            if _is_invalid_stock_name(stock_symbol, stock_name):
                stock_name = get_stock_name(stock_symbol)

            reports_raw = r.get("reports", {})
            cleaned_reports = _rebuild_report_modules(r, reports_raw)
            
            report = {
                "id": tasks_doc.get("task_id", report_id),
                "analysis_id": r.get("analysis_id", ""),
                "stock_symbol": stock_symbol,
                "stock_name": stock_name,  # 🔥 Add stock name field
                "model_info": r.get("model_info", "Unknown"),  # 🔥 Add model information fields
                "analysis_date": r.get("analysis_date", ""),
                "status": r.get("status", "completed"),
                "created_at": to_iso(created_at_tz),
                "updated_at": to_iso(updated_at_tz),
                "analysts": r.get("analysts", []),
                "research_depth": r.get("research_depth", 1),
                "summary": r.get("summary", ""),
                "reports": cleaned_reports,  # 🔥 Use the cleaned reports
                "source": "unified_analysis_tasks" if tasks_doc.get("task_type") else "analysis_tasks",
                "task_id": tasks_doc.get("task_id", report_id),
                "recommendation": r.get("recommendation", ""),
                "confidence_score": r.get("confidence_score", 0.0),
                "risk_level": r.get("risk_level", "medium"),
                "key_points": r.get("key_points", []),
                "execution_time": r.get("execution_time", 0),
                "tokens_used": r.get("tokens_used", 0),
                "decision": r.get("decision", {}),  # 🔥 Add decision field
                "task_type": tasks_doc.get("task_type", "")
            }

            if r.get("report_manifest"):
                report["report_manifest"] = r.get("report_manifest")
            
            # 🔥 Optional fields: decide whether to include them based on query parameters
            if include_state:
                report["state"] = r.get("state", {})
            if include_detailed:
                report["detailed_analysis"] = r.get("detailed_analysis", {})
        else:
            # Convert to verbose format (analysis_reports hit)
            stock_symbol = doc.get("stock_symbol", "")
            stock_name = doc.get("stock_name")
            if _is_invalid_stock_name(stock_symbol, stock_name):
                stock_name = get_stock_name(stock_symbol)

            # Get the time (it is UTC time in the database and needs to be converted to UTC+8) 
            created_at = doc.get("created_at", datetime.utcnow())
            updated_at = doc.get("updated_at", datetime.utcnow())

            # Convert time zone: The UTC time in the database is converted to UTC+8
            created_at_tz = to_config_tz(created_at)
            updated_at_tz = to_config_tz(updated_at)

            reports_raw = doc.get("reports", {})
            cleaned_reports = _rebuild_report_modules(doc, reports_raw)
            
            report = {
                "id": str(doc["_id"]),
                "analysis_id": doc.get("analysis_id", ""),
                "stock_symbol": stock_symbol,
                "stock_name": stock_name,  # 🔥 Add stock name field
                "model_info": doc.get("model_info", "Unknown"),  # 🔥 Add model information fields
                "analysis_date": doc.get("analysis_date", ""),
                "status": doc.get("status", "completed"),
                "created_at": created_at_tz.isoformat() if created_at_tz else str(created_at),
                "updated_at": updated_at_tz.isoformat() if updated_at_tz else str(updated_at),
                "analysts": doc.get("analysts", []),
                "research_depth": doc.get("research_depth", 1),
                "summary": doc.get("summary", ""),
                "reports": cleaned_reports,  # 🔥 Use the cleaned reports
                "source": doc.get("source", "unknown"),
                "task_id": doc.get("task_id", ""),
                "recommendation": doc.get("recommendation", ""),
                "confidence_score": doc.get("confidence_score", 0.0),
                "risk_level": doc.get("risk_level", "medium"),
                "key_points": doc.get("key_points", []),
                "execution_time": doc.get("execution_time", 0),
                "tokens_used": doc.get("tokens_used", 0),
                "decision": doc.get("decision", {}),  # 🔥 Add decision field for formatting
                "task_type": doc.get("task_type", "")
            }

            if doc.get("report_manifest"):
                report["report_manifest"] = doc.get("report_manifest")
            
            tasks_doc = None
            task_id = doc.get("task_id", report_id)
            if task_id:
                tasks_doc = await db.unified_analysis_tasks.find_one(
                    {"task_id": task_id},
                    {"result": 1}
                )
                if not tasks_doc:
                    tasks_doc = await db.analysis_tasks.find_one(
                        {"task_id": task_id},
                        {"result": 1}
                    )

            if tasks_doc and tasks_doc.get("result"):
                result = tasks_doc["result"]
                rebuilt_from_task = _rebuild_report_modules(result, cleaned_reports)
                if len(rebuilt_from_task) > len(cleaned_reports):
                    cleaned_reports = rebuilt_from_task
                    report["reports"] = cleaned_reports

                if result.get("report_manifest"):
                    report["report_manifest"] = result.get("report_manifest")

                if include_state:
                    report["state"] = result.get("state", {})
                if include_detailed:
                    report["detailed_analysis"] = result.get("detailed_analysis", {})

            logger.info("📊 [REPORT] Keep report original content returned, skip compression on read")

        return {
            "success": True,
            "data": report,
            "message": "Report details obtained successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get report details: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{report_id}/content/{module}")
async def get_report_module_content(
    report_id: str,
    module: str,
    user: dict = Depends(get_current_user)
):
    """Get the contents of a specific module of the report"""
    try:
        logger.info(f"🔍 Get report module content: {report_id}/{module}")

        db = get_mongo_db()

        # Query report (supports multiple IDs)
        query = _build_report_query(report_id)
        doc = await db.analysis_reports.find_one(query)

        if not doc:
            raise HTTPException(status_code=404, detail="Report does not exist")

        reports = doc.get("reports", {})

        if module not in reports:
            raise HTTPException(status_code=404, detail=f"module {module} does not exist")

        content = reports[module]

        return {
            "success": True,
            "data": {
                "module": module,
                "content": content,
                "content_type": "markdown" if isinstance(content, str) else "json"
            },
            "message": "Module content obtained successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get report module content: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    user: dict = Depends(get_current_user)
):
    """Delete report"""
    try:
        logger.info(f"🗑️ Delete report: {report_id}")

        db = get_mongo_db()

        # Query report (supports multiple IDs)
        query = _build_report_query(report_id)
        result = await db.analysis_reports.delete_one(query)

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Report does not exist")

        logger.info(f"✅ Report successful deletion: {report_id}")

        return {
            "success": True,
            "message": "Report successful deletion"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Delete report failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# The export download endpoint (Pro exclusive, export_reports gated) has been split into reports_export.py
# see docs/05-design/v3.0/v3.6.0-community-edition-separation-plan.md §5.2

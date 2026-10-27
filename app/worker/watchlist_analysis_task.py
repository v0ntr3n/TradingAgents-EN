"""
Stock watch list scheduled analysis tasks

Regularly analyze the stocks in the user s stock watch list and reuse existing analysis services.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.core.database import get_mongo_db
from app.services.notifications_service import NotificationsService
from app.models.notification import NotificationCreate
from app.models.analysis import SingleAnalysisRequest
from app.utils.compliance import GENERIC_RESEARCH_RECOMMENDATION, build_research_summary

logger = logging.getLogger("app.worker.watchlist_analysis")

# global state
_is_running = False


def _build_scheduled_email_attachments(results: List[Dict[str, Any]], analysis_time: str) -> List[tuple]:
    """Build attachments for scheduled analysis completion emails."""
    if not results:
        return []

    markdown_lines = [
        "# Scheduled Analysis Report",
        "",
        f"Analysis Time: {analysis_time}",
        f"Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    export_payload = []
    for item in results:
        stock_code = item.get("stock_code") or item.get("stock_symbol") or "unknown"
        stock_name = item.get("stock_name") or stock_code
        success = item.get("success", False)
        research_overview = build_research_summary({}, item.get("summary") or "")
        confidence_score = item.get("confidence_score") or 0
        risk_level = item.get("risk_level") or "medium"
        summary = (item.get("summary") or "").strip()
        key_points = item.get("key_points") or []

        markdown_lines.append(f"## {stock_code} {stock_name}")
        markdown_lines.append("")
        markdown_lines.append(f"- Status: {'success' if success else 'failed'}")
        markdown_lines.append(f"- Research Overview: {research_overview}")
        markdown_lines.append(f"- Confidence: {confidence_score}")
        markdown_lines.append(f"- Risk Level: {risk_level}")
        if summary:
            markdown_lines.append(f"- Summary: {summary}")
        if key_points:
            markdown_lines.append("- Key Points:")
            for point in key_points[:5]:
                markdown_lines.append(f"  - {point}")
        markdown_lines.append("")

        export_payload.append({
            "stock_code": stock_code,
            "stock_name": stock_name,
            "success": success,
            "recommendation": GENERIC_RESEARCH_RECOMMENDATION,
            "analysis_overview": research_overview,
            "confidence_score": confidence_score,
            "risk_level": risk_level,
            "summary": summary,
            "key_points": key_points,
        })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown_content = "\n".join(markdown_lines).encode("utf-8")
    json_content = json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8")

    return [
        (f"scheduled_analysis_{timestamp}.md", markdown_content, "text/markdown"),
        (f"scheduled_analysis_{timestamp}.json", json_content, "application/json"),
    ]


def _format_completed_task_result(task_id: str, task_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert task results into the required format for emails."""
    result = task_doc.get("result") or {}
    task_params = task_doc.get("task_params") or {}
    stock_code = task_params.get("stock_code") or task_params.get("symbol") or result.get("stock_code") or result.get("stock_symbol") or ""

    return {
        "task_id": task_id,
        "stock_code": stock_code,
        "stock_name": result.get("stock_name") or stock_code,
        "summary": result.get("summary", ""),
        "recommendation": GENERIC_RESEARCH_RECOMMENDATION,
        "confidence_score": result.get("confidence_score", 0),
        "risk_level": result.get("risk_level", "medium"),
        "key_points": result.get("key_points", []),
        "success": task_doc.get("status") == "completed",
    }


async def _wait_for_task_results(task_ids: List[str], timeout_seconds: int = 3600, poll_interval: int = 15) -> List[Dict[str, Any]]:
    """Wait for the batch task to complete and collect results that can be used for mail aggregation."""
    if not task_ids:
        return []

    db = get_mongo_db()
    pending_ids = set(task_ids)
    completed_results: Dict[str, Dict[str, Any]] = {}
    started_at = datetime.now()

    while pending_ids and (datetime.now() - started_at).total_seconds() < timeout_seconds:
        cursor = db.unified_analysis_tasks.find(
            {"task_id": {"$in": list(pending_ids)}},
            {"task_id": 1, "status": 1, "result": 1, "task_params": 1}
        )
        docs = await cursor.to_list(length=len(pending_ids))

        for doc in docs:
            task_id = doc.get("task_id")
            if not task_id:
                continue

            status = doc.get("status")
            if status in {"completed", "failed", "cancelled"}:
                completed_results[task_id] = _format_completed_task_result(task_id, doc)
                pending_ids.discard(task_id)

        if pending_ids:
            await asyncio.sleep(poll_interval)

    if pending_ids:
        logger.warning(f"⚠️ The scheduled mail analysis waits for timeout, and there are still {len(pending_ids)} tasks not completed")

    return [completed_results[task_id] for task_id in task_ids if task_id in completed_results]


async def _send_scheduled_completion_email_when_ready(
    user_id: str,
    task_ids: List[str],
    total: int,
    analysis_time: str,
) -> None:
    """After waiting for the task to complete, send a scheduled analysis completion email with attachments."""
    try:
        results = await _wait_for_task_results(task_ids)
        success = sum(1 for item in results if item.get("success"))
        failed = max(total - success, 0)
        await send_completion_notification(
            user_id=user_id,
            total=total,
            success=success,
            failed=failed,
            results=results,
            analysis_time=analysis_time,
            send_in_app_notification=True,
            send_email_notification=True,
        )
    except Exception as exc:
        logger.warning(f"⚠️ Failed to send scheduled analysis completion email: {exc}", exc_info=True)


async def get_watchlist_stocks() -> List[Dict[str, Any]]:
    """Get the list of stock watchlists for all valid users

    Only the stock watch lists of users that exist in the users collection are returned, and junk data left over from history is filtered out.

    Returns:
        List of dictionaries containing user_id and stocks
    """
    from bson import ObjectId

    db = get_mongo_db()

    # Step one: Get all valid users' ID
    users_cursor = db.users.find({}, {"_id": 1})
    valid_user_ids = set()
    async for user in users_cursor:
        user_id_str = str(user["_id"])
        valid_user_ids.add(user_id_str)

    logger.info(f"📊 There are total in the database {len(valid_user_ids)} valid users")

    # Step 2: Query records with stock watch lists from the user_favorites collection
    cursor = db.user_favorites.find(
        {"favorites": {"$exists": True, "$ne": []}}
    )

    result = []
    skipped_count = 0

    async for doc in cursor:
        user_id = doc.get("user_id", "unknown")
        favorites = doc.get("favorites", [])

        # Check if the user_id is in the list of valid users
        if user_id not in valid_user_ids:
            logger.warning(f"⚠️ Skip the stock watchlist of invalid users: {user_id} (User does not exist in users collection)")
            skipped_count += 1
            continue

        if favorites:
            logger.info(f"📋 Find valid user {user_id} of {len(favorites)} Only stock watch list")
            result.append({
                "user_id": user_id,
                "stocks": favorites
            })

    if skipped_count > 0:
        logger.info(f"🗑️ skipped {skipped_count} pieces of junk data left over from history")

    if not result:
        logger.info("📭 No stock watchlist data found for any valid user")
    else:
        logger.info(f"✅ Found in total {len(result)} valid users have stock watchlists")

    return result


async def analyze_user_watchlist_batch(
    user_id: str,
    stocks: List[Dict[str, Any]],
    analysis_date: str,
    analysis_depth: int = 3,
    quick_analysis_model: str = "qwen-plus",
    deep_analysis_model: str = "qwen-max"
) -> Dict[str, Any]:
    """
    Batch analysis of user s stock watchlist (concurrent execution) - using v2.0 engine

    Refer to the implementation of the batch analysis API:
    1. Create tasks for all stocks first (using v2.0 unified task engine)
    2. Then use asyncio.create_task to execute all tasks concurrently

    Args:
        user_id: User ID
        stocks: Stock Watchlist List
        analysis_date: Analysis date
        analysis_depth: Analysis depth (1-5)
        quick_analysis_model: Quickly analyze models
        deep_analysis_model: Deep analysis model

    Returns:
        A dictionary containing a list of task IDs and statistics
    """
    from app.services.task_analysis_service import get_task_analysis_service
    from app.models.analysis import AnalysisTaskType
    from app.models.user import PyObjectId

    task_service = get_task_analysis_service()

    # Convert numeric depth to Chinese description
    depth_mapping = {
        1: "fast",
        2: "Basics",
        3: "Standard",
        4: "Depth",
        5: "Comprehensive"
    }
    research_depth = depth_mapping.get(analysis_depth, "Standard")

    task_ids = []
    task_mapping = []
    submitted_task_ids = []
    submitted_count = 0
    failed_count = 0

    # Step 1: Create tasks for all stocks (using v2.0 engine)
    logger.info(f"  📝 [v2.0 engine] Start creating {len(stocks)} analysis tasks...")
    for idx, stock in enumerate(stocks, 1):
        stock_code = stock.get("stock_code")
        stock_name = stock.get("stock_name", stock_code)

        try:
            # 🔥 Identify security types based on ticker: ETFs follow the ETF workflow, stocks follow the stock workflow
            from tradingagents.utils.stock_utils import StockUtils, StockMarket, SecurityType

            sec_type = StockUtils.identify_security_type(stock_code)
            market = StockUtils.identify_stock_market(stock_code)
            market_type_mapping = {
                StockMarket.CHINA_A: "cn",
                StockMarket.HONG_KONG: "hk",
                StockMarket.US: "us",
                StockMarket.UNKNOWN: "cn"
            }
            market_type = market_type_mapping.get(market, "cn")

            # ETF Using the ETF Analysis Process
            if sec_type == SecurityType.FUND:
                task_type = AnalysisTaskType.ETF_ANALYSIS
                logger.info(f"    📊 {stock_code} Identify as an ETF, use the ETF analysis process")
            else:
                task_type = AnalysisTaskType.STOCK_ANALYSIS
                logger.info(f"    📊 stocks {stock_code} identified as market: {market_type}")

            # Prepare task parameters
            task_params = {
                "symbol": stock_code,
                "stock_code": stock_code,
                "market_type": market_type,
                "analysis_date": analysis_date,
                "research_depth": research_depth,
                "quick_analysis_model": quick_analysis_model,
                "deep_analysis_model": deep_analysis_model
            }

            # Create tasks using v2.0 Unified Task Engine
            task = await task_service.create_task(
                user_id=PyObjectId(user_id),
                task_type=task_type,
                task_params=task_params,
                engine_type="auto",  # Automatic engine selection
                preference_type="neutral"
            )

            task_id = task.task_id

            task_ids.append(task_id)
            task_mapping.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "task_id": task_id,
                "task": task
            })

            logger.info(f"    ✅ [{idx}/{len(stocks)}] Task created: {task_id} - {stock_code} {stock_name}")

        except Exception as e:
            logger.error(f"    ❌ [{idx}/{len(stocks)}] Failed to create task: {stock_code} {stock_name}, Error: {e}")
            task_mapping.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "task_id": None,
                "error": str(e)
            })

    logger.info(f"  ✅ Task creation completed: success {len(task_ids)}/{len(stocks)}")

    # Step 2: Submit the task to the queue, and the Worker will uniformly manage concurrency
    if task_ids:
        logger.info(f"  🚀 [v2.0 engine] Start submitting {len(task_ids)} analysis tasks to queue...")
        
        from app.services.queue_service import get_queue_service
        queue_service = get_queue_service()
        
        # Generate batch ID (for scheduled batch analysis)
        batch_id = str(uuid.uuid4())
        
        for item in task_mapping:
            if item.get("task_id"):
                task_id = item["task_id"]
                stock_code = item["stock_code"]
                
                # Prepare queue parameters
                queue_params = {
                    "task_id": task_id,
                    "symbol": stock_code,
                    "stock_code": stock_code,
                    "user_id": user_id,
                    "batch_id": batch_id,
                    "engine": "v2",  # v2 engine
                    "analysis_date": analysis_date,
                    "research_depth": depth_mapping.get(analysis_depth, "Standard"),
                    "quick_analysis_model": quick_analysis_model,
                    "deep_analysis_model": deep_analysis_model
                }
                
                try:
                    # Submit tasks to the queue (will automatically check concurrency limits)
                    await queue_service.enqueue_task(
                        user_id=user_id,
                        symbol=stock_code,
                        params=queue_params,
                        batch_id=batch_id,
                        task_id=task_id  # Use an already created task ID
                    )
                    submitted_count += 1
                    submitted_task_ids.append(task_id)
                    logger.info(f"    ✅ [v2.0 engine] The task has been queued: {task_id} - {stock_code}")
                except ValueError as e:
                    # Concurrency limit error
                    failed_count += 1
                    logger.warning(f"    ⚠️ [v2.0 engine] Task enqueue failed (concurrency limit): {task_id} - {stock_code}, Error: {e}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"    ❌ [v2.0 engine] Task enqueue failed: {task_id} - {stock_code}, Error: {e}", exc_info=True)
        
        logger.info(f"  ✅ Submitted {submitted_count} Tasks were queued and failed. {failed_count} a")

    return {
        "total": len(stocks),
        "created": submitted_count,
        "failed": len(stocks) - submitted_count,
        "task_ids": submitted_task_ids,
        "task_mapping": task_mapping
    }


async def send_completion_notification(
    user_id: str,
    total: int,
    success: int,
    failed: int,
    results: List[Dict[str, Any]],
    analysis_time: Optional[str] = None,
    send_in_app_notification: bool = True,
    send_email_notification: bool = True,
):
    """Send analysis completion notification"""
    notifications_service = NotificationsService()
    has_detailed_results = bool(results)
    analysis_time = analysis_time or datetime.now().strftime("%Y-%m-%d %H:%M")

    if has_detailed_results:
        if success > 0:
            severity = "success" if failed == 0 else "warning"
            title = "Stock watch list scheduled analysis completed"
            content = f"Completed {success}/{total} Stock analysis"
            if failed > 0:
                content += f", {failed} Only analysis failed"
        else:
            severity = "error"
            title = "Stock watch list scheduled analysis failed"
            content = f"All {total} Only stock analysis failed"
    else:
        severity = "info" if success > 0 else "error"
        title = "Stock watch list scheduled analysis has started"
        content = f"Submitted {success}/{total} Stock analysis tasks"
        if failed > 0:
            content += f", {failed} Only submission failed"

    notification = NotificationCreate(
        user_id=user_id,
        type="analysis",
        title=title,
        content=content,
        link="/analysis/history",
        source="watchlist_scheduler",
        severity=severity,
        metadata={
            "total": total,
            "success": success,
            "failed": failed,
            "analysis_date": analysis_time,
            "has_detailed_results": has_detailed_results,
            "stocks": [
                {
                    "stock_code": r.get("stock_code"),
                    "stock_name": r.get("stock_name"),
                    "success": r.get("success", False)
                }
                for r in results
            ]
        }
    )

    if send_in_app_notification:
        try:
            await notifications_service.create_and_publish(notification)
            logger.info(f"📬 Analysis notification sent to user {user_id}")
        except Exception as e:
            logger.error(f"❌ Failed to send notification: {e}")

    # Send email notifications (if the user has enabled email notifications)
    if not send_email_notification or not has_detailed_results:
        return

    try:
        from app.services.email_service import get_email_service
        from app.models.email import EmailType
        email_service = get_email_service()

        # Statistical recommendation results
        buy_count = 0
        hold_count = 0
        sell_count = 0

        attachments = _build_scheduled_email_attachments(results, analysis_time)

        await email_service.send_analysis_email(
            user_id=user_id,
            email_type=EmailType.SCHEDULED_ANALYSIS,  # 🔥 Fix: use enum instead of string
            template_name="scheduled_report",
            template_data={
                "task_name": "Stock watch list timing analysis",
                "analysis_date": analysis_time,
                "total_count": total,
                "success_count": success,
                "failed_count": failed,
                "buy_count": buy_count,
                "hold_count": hold_count,
                "sell_count": sell_count,
                "stocks": results[:10],  # Only send details of the first 10 stocks
                "detail_url": "/analysis/history"
            },
            reference_id=f"scheduled_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            attachments=attachments,
        )
        logger.info(f"📧 An attempt has been made to send a scheduled analysis completion email to the user. {user_id}")
    except Exception as email_err:
        logger.warning(f"⚠️ Failed to send email notification(ignore): {email_err}")


async def run_watchlist_analysis():
    """
    Regular analysis of stock watch list tasks - Main entrance

    Called periodically by APScheduler.
    Iterate through all users who have stock watch lists and analyze their stock watch lists for each user.
    """
    global _is_running

    if _is_running:
        logger.warning("⚠️ The stock watch list scheduled analysis task is running, skip this execution")
        return

    _is_running = True
    start_time = datetime.now()
    analysis_date = start_time.strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info("🚀 Start executing stock watch list scheduled analysis tasks")
    logger.info(f"   Analysis date: {analysis_date}")
    logger.info("=" * 60)

    total_stocks = 0
    total_success = 0
    total_failed = 0

    try:
        # 🔥 Get system default model configuration (from database)
        system_default_models = await get_system_default_models()
        default_quick_model = system_default_models.get("quick_analysis_model", "qwen-plus")
        default_deep_model = system_default_models.get("deep_analysis_model", "qwen-max")
        
        logger.info(f"📋 System default model configuration: fast={default_quick_model}, Depth={default_deep_model}")
        
        # Get a list of all users' stock watchlists
        watchlist_data = await get_watchlist_stocks()

        if not watchlist_data:
            logger.info("📭 No user s stock watchlist found, task ended")
            return

        logger.info(f"📊 total {len(watchlist_data)} Users have stock watchlists")

        # Iterate through each user
        for user_idx, user_data in enumerate(watchlist_data, 1):
            user_id = user_data["user_id"]
            stocks = user_data["stocks"]
            user_total = len(stocks)

            logger.info("-" * 40)
            logger.info(f"👤 [{user_idx}/{len(watchlist_data)}] User: {user_id}")
            logger.info(f"📊 Number of stocks to be analyzed: {user_total}")

            # Use the batch analysis method (concurrent execution) and use the system default model
            batch_result = await analyze_user_watchlist_batch(
                user_id=user_id,
                stocks=stocks,
                analysis_date=analysis_date,
                quick_analysis_model=default_quick_model,
                deep_analysis_model=default_deep_model
            )

            user_success = batch_result["created"]
            user_failed = batch_result["failed"]

            # Cumulative statistics
            total_stocks += user_total
            total_success += user_success
            total_failed += user_failed

            # Send notification to this user
            # Note: Due to concurrent execution, the task may still be executing when the notification is sent here.
            # Consider waiting until all tasks are completed before sending the notification, or stating this in the notification"Analysis started"
            await send_completion_notification(
                user_id=user_id,
                total=user_total,
                success=user_success,
                failed=user_failed,
                results=[],
                analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
                send_in_app_notification=True,
                send_email_notification=False,
            )

            if batch_result.get("task_ids"):
                asyncio.create_task(
                    _send_scheduled_completion_email_when_ready(
                        user_id=user_id,
                        task_ids=batch_result["task_ids"],
                        total=user_total,
                        analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
                    )
                )

            logger.info(f"  ✅ User {user_id} Batch analysis started: Created successfully {user_success} tasks, failed {user_failed} a")

        # Calculate total time
        elapsed = (datetime.now() - start_time).total_seconds()

        logger.info("=" * 60)
        logger.info("✅ Stock watch list scheduled analysis tasks are all completed")
        logger.info(f"   Number of users: {len(watchlist_data)}")
        logger.info(f"   Total number of stocks analyzed: {total_stocks}")
        logger.info(f"   total success: {total_success}, total failure: {total_failed}")
        logger.info(f"   Total time spent: {elapsed:.2f} seconds")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Stock watch list scheduled analysis task execution failed: {e}", exc_info=True)
    finally:
        _is_running = False


async def get_system_default_models() -> Dict[str, str]:
    """
    Obtain the system default analysis model configuration from the database
    
    Returns:
        Dictionary containing quick_analysis_model and deep_analysis_model
    """
    try:
        db = get_mongo_db()
        # Get active system configuration
        system_config = await db.system_configs.find_one(
            {"is_active": True},
            sort=[("version", -1)]
        )
        
        if system_config and "system_settings" in system_config:
            system_settings = system_config["system_settings"]
            return {
                "quick_analysis_model": system_settings.get("quick_analysis_model", "qwen-plus"),
                "deep_analysis_model": system_settings.get("deep_analysis_model", "qwen-max")
            }
    except Exception as e:
        logger.warning(f"⚠️ Failed to obtain system default model configuration: {e}, Use code defaults")
    
    # If the acquisition fails, return code default value
    return {
        "quick_analysis_model": "qwen-plus",
        "deep_analysis_model": "qwen-max"
    }


async def _execute_general_workflow_slot(
    config_id: str,
    user_id: str,
    slot: Dict[str, Any],
    workflow_id: str,
    config: Dict[str, Any],
    db,
):
    """
    Execute common research workflow time period tasks

    This function is called when the time period is configured with workflow_id, using the workflow_params in
    analysis_target and custom_params as workflow inputs.

    Args:
        config_id: Configuration ID
        user_id: User ID
        slot: Time period configuration
        workflow_id: Workflow ID
        config: Complete configuration documentation
        db: MongoDB Database handle
    """
    from app.services.task_analysis_service import get_task_analysis_service
    from app.models.analysis import AnalysisTaskType
    from app.models.user import PyObjectId
    from app.utils.timezone import now_tz
    from bson import ObjectId
    import asyncio

    logger.info(f"📋 Common research process execution parameters:")
    workflow_params = slot.get("workflow_params") or {}
    analysis_target = workflow_params.get("analysis_target", "") or ""
    custom_params = workflow_params.get("custom_params") or {}

    logger.info(f"   Analyze goals: {analysis_target}")
    logger.info(f"   Custom parameters: {custom_params}")

    if not analysis_target:
        logger.warning(f"⚠️ Analysis target not configured, execution skipped")
        # Record failure history
        try:
            history_doc = {
                "config_id": config_id,
                "config_name": config.get("name", "Unnamed"),
                "time_slot_name": slot.get("name", "Unnamed"),
                "created_at": now_tz(),
                "status": "failed",
                "total_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "task_ids": [],
                "result_summary": "No analysis target configured"
            }
            await db.scheduled_analysis_history.insert_one(history_doc)
        except Exception as e:
            logger.error(f"❌ Record failure history failure: {e}")
        return

    total_success = 0
    total_failed = 0
    all_task_ids = []

    try:
        task_service = get_task_analysis_service()
        analysis_date = datetime.now().strftime("%Y-%m-%d")

        # 🆕 Query the input_config of the workflow to supplement the default parameters
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        wf_doc = await db.workflows.find_one(
            {"workflow_id": workflow_id} if isinstance(workflow_id, str) else {"_id": workflow_id},
            {"input_config": 1, "workflow_type": 1}
        )
        input_config = wf_doc.get("input_config") if wf_doc else None

        # Build task parameters: analysis target as ticker, merge custom_params
        task_params = {
            "symbol": analysis_target,
            "stock_code": analysis_target,
            "analysis_date": analysis_date,
            "task_category": "general",  # 🆕 Marked as a general research task
            **custom_params,  # Merge custom parameters
        }

        # 🆕 Supplement missing parameters based on the default value of input_config.fields
        if input_config and isinstance(input_config, dict):
            fields = input_config.get("fields", [])
            for field in fields:
                fname = field.get("name")
                if fname and fname not in task_params and fname not in ("ticker", "symbol", "stock_code"):
                    default_val = field.get("default")
                    if default_val is not None:
                        task_params[fname] = default_val

        # General parameters
        task_params.setdefault("research_depth", "Standard")
        task_params.setdefault("market_type", "cn")

        # Obtain user risk preference
        try:
            from app.routers.analysis import get_user_risk_preference
            preference_type = await get_user_risk_preference(user_id)
        except Exception:
            preference_type = "default"

        logger.info(f"🚀 Create a general research task: workflow_id={workflow_id}, target={analysis_target}")

        task = await task_service.create_task(
            user_id=PyObjectId(user_id),
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params=task_params,
            engine_type="workflow",
            preference_type=preference_type,
            workflow_id=workflow_id,
        )

        # Execute tasks asynchronously
        asyncio.create_task(task_service.execute_task(task))

        all_task_ids.append(task.task_id)
        total_success += 1
        logger.info(f"✅ Generic research task created: task_id={task.task_id}")

    except Exception as e:
        total_failed += 1
        logger.error(f"❌ Failed to create universal research task: {e}", exc_info=True)

    # Update configuration last run time
    await db.scheduled_analysis_configs.update_one(
        {"_id": ObjectId(config_id)},
        {"$set": {"last_run_at": now_tz()}}
    )

    # Record execution history
    try:
        history_doc = {
            "config_id": config_id,
            "config_name": config.get("name", "Unnamed"),
            "time_slot_name": slot.get("name", "Unnamed"),
            "created_at": now_tz(),
            "status": "success" if total_failed == 0 else ("failed" if total_success == 0 else "partial"),
            "total_count": total_success + total_failed,
            "success_count": total_success,
            "failed_count": total_failed,
            "task_ids": all_task_ids,
            "result_summary": None
        }
        await db.scheduled_analysis_history.insert_one(history_doc)
    except Exception as e:
        logger.error(f"❌ Recording execution history failed: {e}")

    logger.info("=" * 70)
    logger.info(f"✅ The general research process time period task is completed")
    logger.info(f"   Successfully started: {total_success} tasks")
    logger.info(f"   failed: {total_failed} a")
    logger.info("=" * 70)


async def run_scheduled_analysis_slot(config_id: str, user_id: str, slot_index: int):
    """
    Execute scheduled analysis time period tasks - new version (supports grouping and custom parameters)

    Args:
        config_id: Configuration ID
        user_id: User ID
        slot_index: time period index
    """
    logger.info("=" * 70)
    logger.info(f"🚀 Start executing scheduled analysis time period tasks")
    logger.info(f"   Configuration ID: {config_id}")
    logger.info(f"   User ID: {user_id}")
    logger.info(f"   time period index: {slot_index}")
    logger.info("=" * 70)

    try:
        # 🔥 Get system default model configuration (from database)
        system_default_models = await get_system_default_models()
        logger.info(f"📋 System default model configuration: fast={system_default_models.get('quick_analysis_model', 'qwen-plus')}, Depth={system_default_models.get('deep_analysis_model', 'qwen-max')}")
        
        # Get configuration
        from bson import ObjectId
        config = await get_mongo_db().scheduled_analysis_configs.find_one({
            "_id": ObjectId(config_id),
            "user_id": user_id
        })

        if not config:
            logger.error(f"❌ Configuration does not exist: {config_id}")
            return

        if not config.get("enabled"):
            logger.warning(f"⚠️ Configuration is disabled: {config_id}")
            return

        time_slots = config.get("time_slots", [])
        if slot_index >= len(time_slots):
            logger.error(f"❌ Time period index out of range: {slot_index}")
            return

        slot = time_slots[slot_index]
        if not slot.get("enabled", True):
            logger.warning(f"⚠️ Time period disabled: {slot.get('name')}")
            return

        logger.info(f"📅 time period: {slot.get('name')}")
        logger.info(f"📋 Number of groups: {len(slot.get('group_ids', []))}")

        # 🆕 Branch: If a general research process is configured, workflow execution is called (skipping grouped stock analysis)
        workflow_id = slot.get("workflow_id")
        if workflow_id:
            logger.info(f"🎯 Generic research process configuration detected: workflow_id={workflow_id}")
            await _execute_general_workflow_slot(
                config_id=config_id,
                user_id=user_id,
                slot=slot,
                workflow_id=workflow_id,
                config=config,
                db=db,
            )
            return

        # Get a list of group IDs to analyze
        group_ids = slot.get("group_ids", [])
        
        # If no grouping is specified, try to use the configured default grouping
        if not group_ids:
            group_ids = config.get("default_group_ids", [])
            
        # If still no grouping specified, skip
        if not group_ids:
            logger.warning(f"⚠️ No grouping is configured for the time period: {slot.get('name')}")
            return

        # Get group information
        db = get_mongo_db()
        groups = []
        for group_id in group_ids:
            try:
                group = await db.watchlist_groups.find_one({
                    "_id": ObjectId(group_id),
                    "user_id": user_id,
                    "is_active": True
                })
                if group:
                    groups.append(group)
            except Exception as e:
                logger.error(f"❌ Failed to get group: {group_id} - {e}")

        if not groups:
            logger.warning(f"⚠️ No valid group found")
            return

        logger.info(f"✅ found {len(groups)} valid groups")

        # statistics
        total_stocks = 0
        total_success = 0
        total_failed = 0
        all_task_ids = []

        # Perform analysis for each grouping
        for group in groups:
            group_name = group.get("name", "Unnamed")
            stock_codes = group.get("stock_codes", [])

            if not stock_codes:
                logger.info(f"  📁 Group [{group_name}] No stocks, skip")
                continue

            logger.info(f"  📁 Group [{group_name}]: {len(stock_codes)} only stocks")

            # Determine analysis parameters (priority: time period > Group > configuration default value)
            analysis_depth = (
                slot.get("analysis_depth") or
                group.get("analysis_depth") or
                config.get("default_analysis_depth", 3)
            )
            # 🔥 Determine the analysis model: use the system default values directly (there is no place to configure these fields in the front-end interface)
            quick_model = system_default_models.get("quick_analysis_model", "qwen-plus")
            deep_model = system_default_models.get("deep_analysis_model", "qwen-max")

            logger.info(f"     Analysis depth: {analysis_depth}")
            logger.info(f"     quick model: {quick_model} (system default)")
            logger.info(f"     deep model: {deep_model} (system default)")

            # Build a stock list
            stocks = [{"stock_code": code} for code in stock_codes]

            # Perform batch analysis
            batch_result = await analyze_user_watchlist_batch(
                user_id=user_id,
                stocks=stocks,
                analysis_date=datetime.now().strftime("%Y-%m-%d"),
                analysis_depth=analysis_depth,
                quick_analysis_model=quick_model,
                deep_analysis_model=deep_model
            )

            group_success = batch_result["created"]
            group_failed = batch_result["failed"]

            total_stocks += len(stock_codes)
            total_success += group_success
            total_failed += group_failed
            
            if batch_result.get("task_ids"):
                all_task_ids.extend(batch_result["task_ids"])

            logger.info(f"     ✅ success: {group_success}, failed: {group_failed}")

        # Send notification
        await send_completion_notification(
            user_id=user_id,
            total=total_stocks,
            success=total_success,
            failed=total_failed,
            results=[],
            analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
            send_in_app_notification=True,
            send_email_notification=False,
        )

        if all_task_ids:
            asyncio.create_task(
                _send_scheduled_completion_email_when_ready(
                    user_id=user_id,
                    task_ids=all_task_ids,
                    total=total_stocks,
                    analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
                )
            )

        # Update configuration last run time
        from app.utils.timezone import now_tz
        await db.scheduled_analysis_configs.update_one(
            {"_id": ObjectId(config_id)},
            {"$set": {"last_run_at": now_tz()}}
        )
        
        # Record execution history
        try:
            history_doc = {
                "config_id": config_id,
                "config_name": config.get("name", "Unnamed"),
                "time_slot_name": slot.get("name", "Unnamed"),
                "created_at": now_tz(),
                "status": "success" if total_failed == 0 else ("failed" if total_success == 0 else "partial"),
                "total_count": total_stocks,
                "success_count": total_success,
                "failed_count": total_failed,
                "task_ids": all_task_ids,
                "result_summary": None
            }
            await db.scheduled_analysis_history.insert_one(history_doc)
        except Exception as e:
            logger.error(f"❌ Recording execution history failed: {e}")

        logger.info("=" * 70)
        logger.info(f"✅ Scheduled analysis time period task completed")
        logger.info(f"   Total number of shares: {total_stocks}")
        logger.info(f"   Successfully started: {total_success} analysis tasks")
        logger.info(f"   failed: {total_failed} a")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"❌ Scheduled analysis time period task execution failed: {e}", exc_info=True)

        # Record failure history to ensure that the front end can see execution failure records
        try:
            from app.utils.timezone import now_tz
            from bson import ObjectId
            db = get_mongo_db()
            history_doc = {
                "config_id": config_id,
                "config_name": "unknown",
                "time_slot_name": "unknown",
                "created_at": now_tz(),
                "status": "failed",
                "total_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "task_ids": [],
                "result_summary": f"Execution exception: {str(e)[:200]}"
            }
            # Try to get the configuration name
            try:
                config = await db.scheduled_analysis_configs.find_one({"_id": ObjectId(config_id)})
                if config:
                    history_doc["config_name"] = config.get("name", "unknown")
                    time_slots = config.get("time_slots", [])
                    if slot_index < len(time_slots):
                        history_doc["time_slot_name"] = time_slots[slot_index].get("name", "unknown")
            except Exception:
                pass

            await db.scheduled_analysis_history.insert_one(history_doc)
        except Exception as hist_err:
            logger.error(f"❌ Recording failure history also failed: {hist_err}")


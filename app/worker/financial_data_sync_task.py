#!/usr/bin/env python3
"""
Financial data synchronization task (scheduler entrance)

Use a unified financial data synchronization service to support thread pool parallel processing
"""
import logging
from typing import Dict, Any

from app.worker.financial_data_sync_service import get_financial_sync_service
from app.services.scheduler_service import mark_job_completed, TaskCancelledException

logger = logging.getLogger(__name__)


async def run_financial_data_sync(**kwargs):
    """
    APScheduler Task: Unified financial data synchronization (using thread pool)
    
    Supports parallel synchronization of multiple data sources and uses thread pools to achieve true parallel processing
    """
    job_id = kwargs.get("job_id", "financial_data_sync")
    
    logger.info(f"🚀 [Financial data synchronization] Start task (job_id={job_id})")
    
    # 🔥 Ordinary manual triggering also needs to check whether there are any unfinished tasks, and it will only be skipped if it is forced to execute.
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    
    if not force_execute:
        # 🔥 Check whether there is already an instance running (normal manual triggering also checks)
        from app.worker.tushare_sync_service import _check_task_running
        is_running, instance_id = await _check_task_running(job_id)
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {
                "skipped": True,
                "reason": "There is already an instance running",
                "running_instance_id": instance_id
            }
    else:
        if force_execute:
            logger.info(f"🔧 [APScheduler] Force execution, skip concurrency checks")
    
    try:
        # Get a unified financial data synchronization service
        service = await get_financial_sync_service()
        
        # Get parameters from kwargs
        data_sources = kwargs.get("data_sources", ["tushare", "akshare", "baostock"])
        report_types = kwargs.get("report_types", ["quarterly", "annual"])
        symbols = kwargs.get("symbols", None)  # None Indicates synchronization of all stocks
        
        # Perform synchronization (using thread pool)
        results = await service.sync_financial_data(
            symbols=symbols,
            data_sources=data_sources,
            report_types=report_types,
            job_id=job_id
        )
        
        # Statistics overall results
        total_success = sum(stats.success_count for stats in results.values())
        total_symbols = sum(stats.total_symbols for stats in results.values())
        total_errors = sum(stats.error_count for stats in results.values())
        
        # Mark task complete
        try:
            stats_dict = {
                "total_processed": total_symbols,
                "success_count": total_success,
                "error_count": total_errors,
                "errors": []
            }
            
            # Collect all errors
            for source, stats in results.items():
                if stats.errors:
                    stats_dict["errors"].extend([
                        {"data_source": source, **error} 
                        for error in stats.errors[:5]  # Maximum 5 errors per data source
                    ])
            
            await mark_job_completed(job_id, stats_dict)
        except Exception as e:
            logger.warning(f"⚠️ Failed to update task completion status: {e}")
        
        logger.info(f"✅ [Financial data synchronization] Mission accomplished: job_id={job_id}, "
                   f"success={total_success}/{total_symbols}, failed={total_errors}")
        
        return {
            "success": True,
            "job_id": job_id,
            "total_symbols": total_symbols,
            "success_count": total_success,
            "error_count": total_errors,
            "results": {source: stats.to_dict() for source, stats in results.items()}
        }
        
    except TaskCancelledException:
        logger.info(f"ℹ️ [Financial data synchronization] The task has been canceled by the user: job_id={job_id}")
        return {"cancelled": True, "message": "The task has been canceled by the user"}
    except Exception as e:
        logger.error(f"❌ [Financial data synchronization] Task failed: job_id={job_id}, error={e}", exc_info=True)
        
        # Mark task as failed
        try:
            await mark_job_completed(
                job_id=job_id,
                error_message=f"Financial data synchronization failed: {str(e)}"
            )
        except Exception as mark_error:
            logger.warning(f"⚠️ Mark task failed status failed: {mark_error}")
        
        raise

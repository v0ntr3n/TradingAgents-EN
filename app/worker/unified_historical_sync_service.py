#!/usr/bin/env python3
"""
Unified historical data synchronization service
Supports parallel execution of historical data synchronization tasks from multiple data sources
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.worker.tushare_sync_service import get_tushare_sync_service
from app.worker.akshare_sync_service import get_akshare_sync_service
from app.worker.baostock_sync_service import BaoStockSyncService

logger = logging.getLogger(__name__)


async def run_unified_historical_sync(
    data_sources: List[str] = None,
    incremental: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    Unified historical data synchronization task: perform historical data synchronization of multiple data sources in parallel
    
    Args:
        data_sources: List of data sources to be synchronized, such as ["tushare", "akshare", "baostock"]
                     If None, synchronizes all enabled data sources
        incremental: Whether to incrementally synchronize
        **kwargs: Other parameters (passed to the synchronization function of each data source)
    
    Returns:
        Synchronization result statistics
    """
    # Synchronize all data sources by default
    if data_sources is None:
        data_sources = ["tushare", "akshare", "baostock"]
    
    logger.info(f"🚀 Start unified historical data synchronization: data source={data_sources}, Incremental synchronization={incremental}")
    
    # Prepare task list
    tasks = []
    task_info = []
    
    # 🔥 Create parallel tasks for each data source
    for data_source in data_sources:
        if data_source == "tushare":
            task = _run_tushare_historical_sync_task(incremental, **kwargs)
            tasks.append(task)
            task_info.append("tushare")
        elif data_source == "akshare":
            task = _run_akshare_historical_sync_task(incremental, **kwargs)
            tasks.append(task)
            task_info.append("akshare")
        elif data_source == "baostock":
            task = _run_baostock_historical_sync_task(**kwargs)
            tasks.append(task)
            task_info.append("baostock")
        else:
            logger.warning(f"⚠️ Unsupported data source: {data_source}, skip")
    
    if not tasks:
        logger.warning("⚠️ No data source available for historical data synchronization")
        return {
            "success": False,
            "message": "No data source available",
            "results": {}
        }
    
    # 🔥 Execute synchronization tasks for all data sources in parallel
    logger.info(f"🚀 Start parallel synchronization {len(tasks)} historical data from data sources: {task_info}")
    
    try:
        # Parallel execution using asyncio.gather
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Processing results
        final_results = {}
        success_count = 0
        error_count = 0
        
        for i, (data_source, result) in enumerate(zip(task_info, results)):
            if isinstance(result, Exception):
                logger.error(f"❌ {data_source} Historical data synchronization failed: {result}", exc_info=True)
                final_results[data_source] = {
                    "success": False,
                    "error": str(result)
                }
                error_count += 1
            else:
                logger.info(f"✅ {data_source} Historical data synchronization completed: {result}")
                final_results[data_source] = {
                    "success": True,
                    "result": result
                }
                success_count += 1
        
        logger.info(f"🎉 Unified historical data synchronization completed: success {success_count}/{len(tasks)}, failed {error_count}/{len(tasks)}")
        
        return {
            "success": error_count == 0,
            "total_sources": len(tasks),
            "success_count": success_count,
            "error_count": error_count,
            "results": final_results
        }
        
    except Exception as e:
        logger.error(f"❌ Unified historical data synchronization failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "results": {}
        }


async def _run_tushare_historical_sync_task(incremental: bool, **kwargs):
    """Run Tushare historical data synchronization task"""
    try:
        from app.worker.tushare_sync_service import run_tushare_historical_sync
        # Set manual trigger flag to allow parallel execution
        kwargs["_manual_trigger"] = True
        result = await run_tushare_historical_sync(incremental=incremental, **kwargs)
        return result
    except Exception as e:
        logger.error(f"❌ Tushare Historical data synchronization task failed: {e}", exc_info=True)
        raise


async def _run_akshare_historical_sync_task(incremental: bool, **kwargs):
    """Run AKShare historical data synchronization task"""
    try:
        from app.worker.akshare_sync_service import run_akshare_historical_sync
        # Set manual trigger flag to allow parallel execution
        kwargs["_manual_trigger"] = True
        result = await run_akshare_historical_sync(incremental=incremental, **kwargs)
        return result
    except Exception as e:
        logger.error(f"❌ AKShare Historical data synchronization task failed: {e}", exc_info=True)
        raise


async def _run_baostock_historical_sync_task(**kwargs):
    """Run the BaoStock historical data synchronization task"""
    try:
        from app.worker.baostock_sync_service import run_baostock_historical_sync
        # Set manual trigger flag to allow parallel execution
        kwargs["_manual_trigger"] = True
        result = await run_baostock_historical_sync(**kwargs)
        return result
    except Exception as e:
        logger.error(f"❌ BaoStock Historical data synchronization task failed: {e}", exc_info=True)
        raise

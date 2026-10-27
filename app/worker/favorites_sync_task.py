"""
Stock watch list A-share historical data and financial data synchronization task

During synchronization, it is executed in order according to the unified data source priority (get_enabled_data_sources_async) of the project.
"""

import logging
from typing import List, Set, Dict, Any, Tuple
from datetime import datetime

from app.core.database import get_mongo_db
from app.core.data_source_priority import get_enabled_data_sources_async
from app.worker.tushare_sync_service import get_tushare_sync_service
from app.worker.akshare_sync_service import get_akshare_sync_service
from app.worker.etf_sync_service import get_etf_sync_service
from app.worker.financial_data_sync_service import FinancialDataSyncService

logger = logging.getLogger("webapi")

# ETF Symbol prefix (consistent with ETF sync service)
ETF_SH_PREFIXES = ("50", "51", "52", "56", "58")
ETF_SZ_PREFIXES = ("15", "16", "18")


def _get_sync_data_sources(enabled_sources: List[str]) -> List[str]:
    """Exclude local from enabled data sources to get a list of data sources used for synchronization (in order of priority)."""
    sync_sources = [s for s in enabled_sources if s and s.lower() != "local"]
    return sync_sources if sync_sources else ["tushare", "akshare", "baostock"]


async def get_all_favorite_a_stocks() -> List[str]:
    """
    Get the list of A-share stock codes in all users stock watch lists
    
    Returns:
        A Stock code list (duplication removed)
    """
    db = get_mongo_db()
    
    try:
        # Get all user's stock watchlists from user_favorites collection
        cursor = db.user_favorites.find({}, {"favorites": 1})
        
        a_stock_codes: Set[str] = set()
        
        async for doc in cursor:
            favorites = doc.get("favorites", [])
            for favorite in favorites:
                # Only get A shares
                market = favorite.get("market", "A shares")
                if market == "A shares":
                    stock_code = favorite.get("stock_code")
                    if stock_code:
                        # Make sure the ticker symbol is in 6 digit format
                        stock_code = str(stock_code).zfill(6)
                        a_stock_codes.add(stock_code)
        
        codes_list = sorted(list(a_stock_codes))
        logger.info(f"📊 Get {len(codes_list)} Only the A-share stock watch list needs to be synchronized")
        
        return codes_list
        
    except Exception as e:
        logger.error(f"❌ Failed to obtain stock watch list A-share list: {e}")
        return []


def _is_etf_code(code: str) -> bool:
    """Determine if the 6-digit code is an ETF."""
    normalized = str(code or "").zfill(6)
    return len(normalized) == 6 and normalized.startswith(ETF_SH_PREFIXES + ETF_SZ_PREFIXES)


def _split_stock_and_etf_codes(codes: List[str]) -> Tuple[List[str], List[str]]:
    """Split the ticker list into common stocks and ETFs."""
    stock_codes: List[str] = []
    etf_codes: List[str] = []

    for code in codes:
        if _is_etf_code(code):
            etf_codes.append(code)
        else:
            stock_codes.append(code)

    return stock_codes, etf_codes


def _filter_stock_codes_for_financial_sync(codes: List[str]) -> List[str]:
    """Financial sync only retains ticker symbols and excludes ETFs."""
    stock_codes, _ = _split_stock_and_etf_codes(codes)
    return stock_codes


async def sync_favorites_historical_data():
    """
    Synchronize the historical data of A shares in the stock watch list.
    In order of data source priority (get_enabled_data_sources_async), the first data source that supports the specified stock list is used.
    
    Returns:
        Synchronization result statistics
    """
    logger.info("🔄 Start synchronizing stock watchlist A-share historical data...")
    
    try:
        # 1. Get A-share codes in all stock watchlists
        a_stock_codes = await get_all_favorite_a_stocks()
        
        if not a_stock_codes:
            logger.info("ℹ️ There is no A-share stock watch list that requires synchronization of historical data.")
            return {
                "success": True,
                "message": "There is no A-share stock watch list that needs to be synchronized.",
                "total_count": 0,
                "synced_count": 0,
                "data_source": None
            }

        stock_codes, etf_codes = _split_stock_and_etf_codes(a_stock_codes)
        if etf_codes:
            logger.info(f"🔀 The history of the stock watch list synchronizes the identification of ETFs and switches to the ETF dedicated link.: {len(etf_codes)} only")
        if not stock_codes:
            logger.info("ℹ️ Stock watchlist history sync does not include common stocks, only ETF history sync will be performed")
        
        # 2. Get the list of synchronized data sources by data source priority (excluding local)
        enabled_sources = await get_enabled_data_sources_async("a_shares")
        data_sources = _get_sync_data_sources(enabled_sources)
        logger.info(f"📊 Stock watch list historical data synchronization data source priority: {data_sources}")
        
        # 🔥 Use unified thread pool service to perform synchronization tasks (avoid event loop conflicts)
        from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service
        
        unified_service = await get_unified_thread_pool_sync_service()
        
        # 🔥 Optimization: Different data sources can be executed in parallel (because they use different APIs and do not affect each other)
        # The same data source is still serial internally (to avoid API current limiting)
        import asyncio
        
        tasks = []
        task_sources = []
        
        # Create concurrent tasks (only include data sources that support the specified stock list)
        for source in data_sources:
            source_lower = source.lower()
            
            # BaoStock Specified stock list is not supported, skip
            if source_lower == "baostock":
                logger.debug("BaoStock Historical synchronization does not support the specified stock list, skip")
                continue

            if not stock_codes:
                continue
            
            # 🔥 Create tasks (executed using a unified thread pool service to avoid event loop conflicts)
            if source_lower == "tushare":
                async def sync_tushare(codes=stock_codes):
                    service = await get_tushare_sync_service()
                    # 🔥 Execute synchronized methods in thread pool
                    sync_result = await unified_service.execute_sync_method(
                        sync_method=service.sync_historical_data,
                        method_kwargs={
                            "symbols": codes,
                            "incremental": True,
                            "period": "daily"
                        },
                        job_id="favorites_tushare_historical_sync",
                        rate_limit_per_minute=200  # Tushare rate limit
                    )
                    if sync_result.success:
                        return sync_result.result
                    else:
                        raise RuntimeError(sync_result.error)
                tasks.append(sync_tushare())
                task_sources.append("tushare")
            elif source_lower == "akshare":
                async def sync_akshare(codes=stock_codes):
                    service = await get_akshare_sync_service()
                    # 🔥 Execute synchronized methods in thread pool
                    sync_result = await unified_service.execute_sync_method(
                        sync_method=service.sync_historical_data,
                        method_kwargs={
                            "symbols": codes,
                            "incremental": True,
                            "period": "daily"
                        },
                        job_id="favorites_akshare_historical_sync",
                        rate_limit_per_minute=60  # AKShare rate limit
                    )
                    if sync_result.success:
                        return sync_result.result
                    else:
                        raise RuntimeError(sync_result.error)
                tasks.append(sync_akshare())
                task_sources.append("akshare")

        if etf_codes:
            async def sync_etf(codes=etf_codes):
                service = await get_etf_sync_service()
                return await service.sync_symbols(
                    symbols=codes,
                    force_update=False,
                    days=30,
                    job_id="favorites_etf_historical_sync",
                )

            tasks.append(sync_etf())
            task_sources.append("etf")
        
        # Execute synchronization tasks for all data sources in parallel
        if tasks:
            logger.info(f"🚀 Start parallel synchronization {len(tasks)} historical data from data sources: {task_sources}")
            
            # Parallel execution using asyncio.gather
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Processing results: merge all successful data source results
            stock_success_count = 0
            stock_records = 0
            etf_success_count = 0
            etf_records = 0
            used_sources = []
            all_details = {}
            
            for i, (source, result) in enumerate(zip(task_sources, results)):
                if isinstance(result, Exception):
                    logger.warning(f"⚠️ {source} Historical data synchronization failed: {result}")
                    all_details[source] = {"error": str(result)}
                else:
                    # 🔥 Debugging: print the complete return result and view the actual fields
                    logger.debug(f"📊 {source} Historical data synchronization return results: {result}")
                    
                    # 🔥 Check whether it is a skip situation (incremental synchronization time check)
                    if result.get("skipped", False):
                        skip_reason = result.get("skip_reason", result.get("message", "unknown reason"))
                        logger.info(f"⏸️ {source} Historical data synchronization skipped: {skip_reason}")
                        all_details[source] = {
                            "skipped": True,
                            "skip_reason": skip_reason,
                            "stats": result.get("stats", {})
                        }
                        # 🔥 Skipped situations are also counted in used_sources, but not counted in the number of successes.
                        used_sources.append(source)
                        continue

                    if source == "etf":
                        success_count = result.get("success_count", 0)
                        records = result.get("records_inserted", 0)
                        etf_success_count = success_count
                        etf_records += records
                        etf_source = result.get("data_source_used")
                        used_sources.append(f"etf:{etf_source}" if etf_source else "etf")
                        all_details[source] = result
                        logger.info(f"✅ ETF Historical data synchronization completed: success={success_count}, record={records}, data source={etf_source}")
                        continue

                    # 🔥 Check whether there are nested stats in the returned result (in some cases the return format may be {"stats": {...}}) 
                    if "stats" in result and isinstance(result["stats"], dict):
                        stats = result["stats"]
                        success_count = stats.get("success_count", 0)
                        records = stats.get("total_records", 0)
                    else:
                        # Use fields in result directly
                        success_count = result.get("success_count", 0)
                        records = result.get("total_records", 0)
                    
                    # 🔥 Debug log: Check which fields have values
                    logger.info(f"📊 {source} Historical data return: success_count={success_count}, total_records={records}, "
                               f"total_processed={result.get('total_processed', result.get('stats', {}).get('total_processed', 'N/A'))}, "
                               f"error_count={result.get('error_count', result.get('stats', {}).get('error_count', 'N/A'))}, "
                               f"result keys={list(result.keys())}")

                    stock_success_count = max(stock_success_count, success_count)  # Take the maximum value (because different data sources may cover the same stocks)
                    stock_records += records  # Cumulative number of records (data from different data sources will be merged)
                    used_sources.append(source)
                    all_details[source] = result
                    logger.info(f"✅ {source} Historical data synchronization completed: success={success_count}, record={records}")

            total_success_count = stock_success_count + etf_success_count
            total_records = stock_records + etf_records

            if not used_sources:
                logger.warning("⚠️ Stock watchlist historical data sync: all data sources failed")
                return {
                    "success": False,
                    "message": "Synchronization of all data sources failed",
                    "total_count": len(a_stock_codes),
                    "synced_count": 0,
                    "data_source": None,
                    "error": "Synchronization of all data sources failed",
                    "details": all_details
                }
            
            logger.info(
                f"✅ Stock watch list A-share historical data is synchronized (data source: {', '.join(used_sources)}) : "
                f"Number of shares={len(a_stock_codes)}, success={total_success_count}, Number of records={total_records}"
            )
            
            return {
                "success": True,
                "message": "Stock watch list A-share historical data is synchronized",
                "total_count": len(a_stock_codes),
                "synced_count": total_success_count,
                "total_records": total_records,
                "stock_count": len(stock_codes),
                "etf_count": len(etf_codes),
                "data_source": ", ".join(used_sources) if used_sources else None,
                "data_sources": used_sources,  # 🔥 New: Return list of all successful data sources
                "details": all_details  # 🔥 New: Return detailed results for all data sources
            }
        else:
            logger.warning("⚠️ Stock watch list historical data synchronization: no data source available (tried tushare/akshare)")
            return {
                "success": False,
                "message": "No data sources available or all failed",
                "total_count": len(a_stock_codes),
                "synced_count": 0,
                "data_source": None,
                "error": "No data source available"
            }
        
    except Exception as e:
        logger.error(f"❌ Stock watch list A-share historical data synchronization failed: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Sync failed: {str(e)}",
            "total_count": 0,
            "synced_count": 0,
            "error": str(e)
        }


async def sync_favorites_financial_data():
    """
    Synchronize the financial data of A shares in the stock watch list.
    Synchronize in order of data source priority (get_enabled_data_sources_async).
    
    Returns:
        Synchronization result statistics
    """
    logger.info("💰 Start synchronizing stock watchlist A-share financial data...")
    
    try:
        # 1. Get A-share codes in all stock watchlists
        a_stock_codes = await get_all_favorite_a_stocks()
        
        if not a_stock_codes:
            logger.info("ℹ️ No A-share stock watchlist needs to synchronize financial data")
            return {
                "success": True,
                "message": "There is no A-share stock watch list that needs to be synchronized.",
                "total_count": 0,
                "synced_count": 0
            }
        
        # Financial data is only synchronized for stocks, and ETFs use ETF-specific data links.
        stock_codes = _filter_stock_codes_for_financial_sync(a_stock_codes)
        skipped_etf_count = len(a_stock_codes) - len(stock_codes)

        if skipped_etf_count > 0:
            logger.info(f"⏭️ Stock Watchlist Financial Sync Excluded ETF: {skipped_etf_count} only")

        if not stock_codes:
            logger.info("ℹ️ Only ETFs are included in the stock watchlist, no stock financial sync is required")
            return {
                "success": True,
                "message": "Only includes ETFs, stock financial sync has been skipped",
                "total_count": len(a_stock_codes),
                "synced_count": 0,
                "error_count": 0,
                "skipped_etf_count": skipped_etf_count,
                "details": {}
            }

        # 2. Get the list of synchronized data sources by data source priority (excluding local)
        enabled_sources = await get_enabled_data_sources_async("a_shares")
        data_sources = _get_sync_data_sources(enabled_sources)
        logger.info(f"📊 Stock Watch List Financial Data Synchronization Data Source Priority: {data_sources}")
        
        # 3. Use the financial data synchronization service to synchronize in order of priority
        financial_service = FinancialDataSyncService()
        await financial_service.initialize()
        
        # Synchronize financial data (get the last 20 periods, about 5 years), data sources in order of priority
        result = await financial_service.sync_financial_data(
            symbols=stock_codes,
            data_sources=data_sources,
            report_types=["quarterly", "annual"],  # Quarterly and annual reports
            batch_size=50,
            delay_seconds=1.0,
            job_id="favorites_financial_sync"  # 🔥 Add job_id for progress tracking
        )
        
        # Statistical synchronization results
        total_synced = 0
        total_errors = 0
        for source, stats in result.items():
            total_synced += stats.success_count
            total_errors += stats.error_count
        
        logger.info(
            f"✅ Stock watch list A-share financial data is synchronized: "
            f"Number of shares={len(stock_codes)}, "
            f"exclude ETF={skipped_etf_count}, "
            f"Synced successfully={total_synced}, "
            f"failed={total_errors}"
        )
        
        return {
            "success": True,
            "message": "Stock watch list A-share financial data is synchronized",
            "total_count": len(stock_codes),
            "synced_count": total_synced,
            "error_count": total_errors,
            "skipped_etf_count": skipped_etf_count,
            "details": {source: {
                "success_count": stats.success_count,
                "error_count": stats.error_count,
                "skipped_count": stats.skipped_count,
                "total_symbols": stats.total_symbols
            } for source, stats in result.items()}
        }
        
    except Exception as e:
        logger.error(f"❌ Stock watch list A-share financial data synchronization failed: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Sync failed: {str(e)}",
            "total_count": 0,
            "synced_count": 0,
            "error": str(e)
        }


async def run_favorites_data_sync():
    """
    APScheduler Task: Synchronize the historical data and financial data of A shares in the stock watch list
    
    This task will:
    1. Get the A-share stock codes in all users stock watch lists
    2. Synchronize the historical data of these stocks (incremental synchronization)
    3. Synchronize the financial data of these stocks (last 20 periods)
    """
    job_id = "favorites_data_sync"
    logger.info("🚀 [APScheduler] Start executing the stock watch list A-share data synchronization task")
    
    start_time = datetime.now()
    
    try:
        # Import progress update function
        from app.services.scheduler_service import update_job_progress
        
        # Get the number of stock watchlists (used for progress calculation)
        a_stock_codes = await get_all_favorite_a_stocks()
        total_stocks = len(a_stock_codes)
        
        # Update progress: Started (0%)
        try:
            await update_job_progress(
                job_id=job_id,
                progress=0,
                message="Start synchronizing stock watchlist A-share data...",
                total_items=total_stocks if total_stocks > 0 else 1
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to update task progress: {e}")
        
        # 🔥 Optimization: Historical data and financial data can be executed in parallel (because they use different APIs and do not affect each other)
        # 1. Perform historical and financial data synchronization in parallel
        try:
            await update_job_progress(
                job_id=job_id,
                progress=10,
                message="Synchronizing historical and financial data in parallel...",
                total_items=total_stocks if total_stocks > 0 else 1
            )
        except Exception:
            pass
        
        # Use asyncio.gather to perform historical and financial data synchronization in parallel
        import asyncio
        hist_task = sync_favorites_historical_data()
        fin_task = sync_favorites_financial_data()
        
        hist_result, fin_result = await asyncio.gather(
            hist_task,
            fin_task,
            return_exceptions=True
        )
        
        # Handle abnormal results
        if isinstance(hist_result, Exception):
            logger.error(f"❌ Historical data synchronization failed: {hist_result}", exc_info=True)
            hist_result = {
                "success": False,
                "message": f"Historical data synchronization failed: {str(hist_result)}",
                "total_count": total_stocks,
                "synced_count": 0,
                "error": str(hist_result)
            }
        
        if isinstance(fin_result, Exception):
            logger.error(f"❌ Financial data synchronization failed: {fin_result}", exc_info=True)
            fin_result = {
                "success": False,
                "message": f"Financial data synchronization failed: {str(fin_result)}",
                "total_count": total_stocks,
                "synced_count": 0,
                "error": str(fin_result)
            }
        
        # Update progress: Parallel synchronization completed (90%)
        try:
            hist_synced = hist_result.get('synced_count', 0) if isinstance(hist_result, dict) else 0
            fin_synced = fin_result.get('synced_count', 0) if isinstance(fin_result, dict) else 0
            
            await update_job_progress(
                job_id=job_id,
                progress=90,
                message=f"Parallel synchronization completed: historical data {hist_synced}/{total_stocks}, financial data {fin_synced}/{total_stocks}",
                total_items=total_stocks if total_stocks > 0 else 1,
                processed_items=max(hist_synced, fin_synced)
            )
        except Exception:
            pass
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Update progress: Completed (100%)
        try:
            await update_job_progress(
                job_id=job_id,
                progress=100,
                message=f"Task completed (time consuming): {duration:.2f}seconds)",
                total_items=total_stocks if total_stocks > 0 else 1,
                processed_items=total_stocks if total_stocks > 0 else 1
            )
        except Exception:
            pass
        
        logger.info(
            f"✅ [APScheduler] Stock watch list A-share data synchronization task completed "
            f"(Time consuming: {duration:.2f}seconds)\n"
            f"   historical data: {hist_result.get('synced_count', 0)}/{hist_result.get('total_count', 0)} only stocks\n"
            f"   financial data: {fin_result.get('synced_count', 0)}/{fin_result.get('total_count', 0)} only stocks"
        )
        
        return {
            "success": True,
            "duration_seconds": duration,
            "historical_data": hist_result,
            "financial_data": fin_result
        }
        
    except Exception as e:
        logger.error(f"❌ [APScheduler] Stock watch list A-share data synchronization task failed: {e}", exc_info=True)
        
        # Update progress: failed
        try:
            from app.services.scheduler_service import update_job_progress
            await update_job_progress(
                job_id=job_id,
                progress=0,
                message=f"Task failed: {str(e)}"
            )
        except Exception:
            pass
        
        return {
            "success": False,
            "error": str(e)
        }

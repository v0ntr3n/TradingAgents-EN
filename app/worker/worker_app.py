"""
Worker Service - Analysis task processing service based on FastAPI

Run using Uvicorn, which has the same architecture as Backend and is more stable and reliable.

Start method:
    python -m uvicorn app.worker.worker_app:app --host 0.0.0.0 --port 8001
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Add project root directory to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.core.database import init_database, close_database
from app.core.config import settings
from app.worker.analysis_worker import AnalysisWorker

logger = logging.getLogger(__name__)

# Worker Example
_worker: Optional[AnalysisWorker] = None
_worker_task: Optional[asyncio.Task] = None
_start_time: Optional[datetime] = None


async def start_worker():
    """Start Worker task processing loop"""
    global _worker, _worker_task
    
    logger.info("🚀 Start Worker task processing...")
    
    _worker = AnalysisWorker()
    
    # Run in background worker
    _worker_task = asyncio.create_task(_worker.start())
    
    logger.info("✅ Worker Task processing started")


async def stop_worker():
    """stop Worker"""
    global _worker, _worker_task
    
    logger.info("🛑 stop Worker...")
    
    if _worker:
        _worker.running = False
    
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    
    logger.info("✅ Worker Stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI life cycle management"""
    global _start_time
    _start_time = datetime.now()
    
    # On startup
    logger.info("=" * 60)
    logger.info("🔧 Worker Service starting...")
    logger.info(f"   Python: {sys.executable}")
    logger.info(f"   working directory: {Path.cwd()}")
    logger.info("=" * 60)
    
    # Initializing the database and unifying the Redis life cycle
    await init_database()
    
    # start Worker
    await start_worker()
    
    logger.info("✅ Worker Service startup completed")
    
    yield
    
    # when closed
    logger.info("🛑 Worker Service is closed...")
    
    await stop_worker()
    await close_database()
    
    logger.info("✅ Worker Service is down")


# Create a FastAPI application
app = FastAPI(
    title="TradingAgents Worker Service",
    description="Analysis task processing service",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """root path"""
    return {"service": "worker", "status": "running"}


@app.get("/health")
async def health_check():
    """health check"""
    global _worker, _worker_task, _start_time

    status = "healthy"
    worker_status = "unknown"

    if _worker:
        if _worker.running:
            worker_status = "running"
        elif _worker_task and not _worker_task.done():
            worker_status = "initializing"
            status = "starting"
        else:
            worker_status = "stopped"
            status = "degraded"
    else:
        status = "starting"
        worker_status = "not_created"

    uptime = None
    if _start_time:
        uptime = (datetime.now() - _start_time).total_seconds()

    return {
        "status": status,
        "worker_status": worker_status,
        "uptime_seconds": uptime,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/status")
async def worker_status():
    """Worker detailed status"""
    global _worker, _start_time
    
    if not _worker:
        return JSONResponse(
            status_code=503,
            content={"error": "Worker not initialized"}
        )
    
    return {
        "worker_id": _worker.worker_id,
        "running": _worker.running,
        "current_task": str(_worker.current_task) if _worker.current_task else None,
        "running_tasks_count": len(_worker.running_tasks) if hasattr(_worker, 'running_tasks') else 0,
        "max_concurrent_tasks": _worker.max_concurrent_tasks,
        "start_time": _start_time.isoformat() if _start_time else None,
        "uptime_seconds": (datetime.now() - _start_time).total_seconds() if _start_time else None,
    }


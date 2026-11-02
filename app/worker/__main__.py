from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['launcher', 'worker_app', '__main__']:
    _sys.modules[f"app.worker.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === launcher.py ===
"""
Worker Launcher (main process)
Used to start and monitor Worker sub-processes, capture sub-process exits and record logs

🔥 Solve the problem: When the Worker is forcibly killed by taskkill /F or the task manager,
   Worker The internal exit hook cannot be executed, but the main process can detect the exit of the child process.
"""

import subprocess
import sys
import os
import time
import signal
from pathlib import Path
from datetime import datetime

# Add project root directory to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def write_log(message: str, level: str = "INFO"):
    """write log"""
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "worker.log"
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{timestamp} - LAUNCHER - {level} - {message}\n")
            f.flush()
        
        # Also print to console
        print(f"[{timestamp}] [{level}] {message}")
    except Exception as e:
        print(f"Failed to write log: {e}")


def write_exit_report(pid: int, returncode: int, runtime_seconds: float):
    """Write child process exit report"""
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "worker.log"
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Interpret exit code
        if returncode == 0:
            exit_reason = "Exit normally"
        elif returncode < 0:
            # A negative number indicates termination by a signal (Unix)
            exit_reason = f"terminated by signal (signal {-returncode})"
        elif returncode == 1:
            exit_reason = "General error"
        elif returncode == -1073741510:  # Windows: STATUS_CONTROL_C_EXIT
            exit_reason = "Ctrl+C interrupt"
        elif returncode == -1073741819:  # Windows: STATUS_ACCESS_VIOLATION
            exit_reason = "Access violation (crash)"
        elif returncode == -1073740791:  # Windows: Killed by taskkill
            exit_reason = "Forced to terminate (taskkill /F or task manager)"
        elif returncode == 1:
            exit_reason = "General error exit"
        else:
            exit_reason = f"Unknown exit code: {returncode}"
        
        # Format run time
        hours, remainder = divmod(int(runtime_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        runtime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"{timestamp} - LAUNCHER - Worker Child process exit report\n")
            f.write(f"{'='*60}\n")
            f.write(f"child process PID: {pid}\n")
            f.write(f"exit code: {returncode}\n")
            f.write(f"Reason for exit: {exit_reason}\n")
            f.write(f"Running time: {runtime_str}\n")
            f.write(f"{'='*60}\n\n")
            f.flush()
        
        print(f"\n{'='*60}")
        print("Worker Child process exit report")
        print(f"{'='*60}")
        print(f"child process PID: {pid}")
        print(f"exit code: {returncode}")
        print(f"Reason for exit: {exit_reason}")
        print(f"Running time: {runtime_str}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"Writing exit report failed: {e}")


def main():
    """Main function: start and monitor Worker subprocess"""
    write_log("=" * 50)
    write_log("Worker Launcher starts running")
    write_log(f"Python: {sys.executable}")
    write_log(f"working directory: {os.getcwd()}")
    write_log(f"launcher PID: {os.getpid()}")
    
    # Build startup command
    python_exe = sys.executable
    worker_module = "app.worker"
    
    write_log(f"Start Worker child process: {python_exe} -m {worker_module}")
    
    start_time = time.time()
    
    # Start child process
    process = subprocess.Popen(
        [python_exe, "-m", worker_module],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # line buffer
        encoding='utf-8',
        errors='replace'
    )
    
    child_pid = process.pid
    write_log(f"Worker Child process started, PID: {child_pid}")
    
    try:
        # Real-time output of logs of child processes
        while True:
            line = process.stdout.readline()
            if line:
                print(line.rstrip())
            
            # Check if the child process exited
            returncode = process.poll()
            if returncode is not None:
                # Child process has exited
                runtime = time.time() - start_time
                write_log(f"Worker child process exit detected, exit code: {returncode}", "WARNING")
                write_exit_report(child_pid, returncode, runtime)
                break
            
            # If there is no output and no exit, wait briefly.
            if not line:
                time.sleep(0.1)
                
    except KeyboardInterrupt:
        write_log("received Ctrl+C, Terminating Worker child process...", "WARNING")
        process.terminate()
        process.wait(timeout=5)
        runtime = time.time() - start_time
        write_exit_report(child_pid, process.returncode or -1, runtime)
    
    write_log("Worker Launcher exits")


if __name__ == "__main__":
    main()


# === worker_app.py ===
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


# === __main__.py ===
"""
Worker Module startup entrance
Support using python -m app.worker to start Worker

🔥 Enhanced version: Add global error capture and exit log mechanism
- atexit Hook: recorded when the process exits normally
- Signal handling: capture SIGTERM, SIGINT Waiting for signal
- Global exception hook: catch unhandled exceptions
- Resource monitoring: record memory usage and other information
"""

import asyncio
import sys
import os
import logging
import traceback
import atexit
import signal
import threading
from pathlib import Path
from datetime import datetime

# Add project root directory to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# ==================== global state ====================
_worker_state = {
    "pid": os.getpid(),
    "start_time": datetime.now(),
    "last_task_id": None,
    "last_task_time": None,
    "task_count": 0,
    "error_count": 0,
    "last_error": None,
    "status": "starting",
}


def get_worker_state() -> dict:
    """Get the current status of the Worker (for external updates)"""
    return _worker_state


def update_worker_state(**kwargs):
    """Update Worker status"""
    _worker_state.update(kwargs)
    _worker_state["last_update"] = datetime.now().isoformat()


def setup_logging():
    """Set logging configuration - ensure logs are written to files under all circumstances"""
    # Make sure the log directory exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "worker.log"

    # Create a file handler, using append mode
    file_handler = logging.FileHandler(str(log_file), encoding='utf-8', mode='a')
    file_handler.setLevel(logging.DEBUG)  # Documentation of all levels
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    # Create console handler (may fail due to encoding issues, but does not affect file logs)
    try:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    except Exception:
        console_handler = None

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    if console_handler:
        root_logger.addHandler(console_handler)

    # Force refresh of output (ignoring encoding errors)
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(line_buffering=True, errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(line_buffering=True, errors='replace')
    except Exception:
        pass

    return logging.getLogger(__name__)


def write_startup_log(message: str):
    """Write directly to the startup log (bypassing the logging module to ensure logging)"""
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "worker.log"

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{timestamp} - STARTUP - {message}\n")
            f.flush()
    except Exception:
        pass


def write_exit_log(reason: str, details: str = ""):
    """Write exit log (ensures logging in all cases)"""
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "worker.log"

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Calculate run time
        runtime = datetime.now() - _worker_state.get("start_time", datetime.now())
        runtime_str = str(runtime).split('.')[0]  # Remove microseconds

        # Get memory usage
        memory_info = "unknown"
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            memory_info = f"{memory_mb:.2f} MB"
        except Exception:
            pass

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"{timestamp} - EXIT - Worker Process exits\n")
            f.write(f"{'='*60}\n")
            f.write(f"Reason for exit: {reason}\n")
            f.write(f"PID: {_worker_state.get('pid', 'unknown')}\n")
            f.write(f"Running time: {runtime_str}\n")
            f.write(f"memory usage: {memory_info}\n")
            f.write(f"Number of tasks processed: {_worker_state.get('task_count', 0)}\n")
            f.write(f"number of errors: {_worker_state.get('error_count', 0)}\n")
            f.write(f"final state: {_worker_state.get('status', 'unknown')}\n")
            f.write(f"final task: {_worker_state.get('last_task_id', 'None')}\n")
            f.write(f"final error: {_worker_state.get('last_error', 'None')}\n")
            if details:
                f.write(f"Details:\n{details}\n")
            f.write(f"{'='*60}\n\n")
            f.flush()
    except Exception as e:
        # Last resort: writing to standard error
        try:
            sys.stderr.write(f"EXIT LOG FAILED: {e}\n")
            sys.stderr.write(f"Reason: {reason}\n")
            sys.stderr.flush()
        except Exception:
            pass


def _atexit_handler():
    """atexit Hook - called when the process exits normally"""
    write_exit_log("Exit normally (atexit)", f"Status: {_worker_state}")


def _signal_handler(signum, frame):
    """Signal Handler - Capture SIGTERM, SIGINT Waiting for signal"""
    signal_names = {
        signal.SIGINT: "SIGINT (Ctrl+C)",
        signal.SIGTERM: "SIGTERM (Termination signal)",
    }
    # Windows unique signal
    if hasattr(signal, 'SIGBREAK'):
        signal_names[signal.SIGBREAK] = "SIGBREAK (Ctrl+Break)"

    signal_name = signal_names.get(signum, f"signal {signum}")
    write_exit_log(f"signal received: {signal_name}", f"Status: {_worker_state}")

    # update status
    update_worker_state(status="shutting_down")

    # Exit process
    sys.exit(0)


def _exception_hook(exc_type, exc_value, exc_tb):
    """Global exception hook - catch unhandled exceptions"""
    # Format exception information
    tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))

    # update status
    update_worker_state(
        status="crashed",
        last_error=str(exc_value),
        error_count=_worker_state.get("error_count", 0) + 1
    )

    write_exit_log(
        f"Uncaught exception: {exc_type.__name__}: {exc_value}",
        f"stack trace:\n{tb_str}\n\n Status: {_worker_state}"
    )

    # Call the original exception hook
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _threading_exception_hook(args):
    """Thread exception hook - catches unhandled exceptions in threads (Python 3.8+) """
    tb_str = ''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))

    update_worker_state(
        last_error=f"Thread exception: {args.exc_value}",
        error_count=_worker_state.get("error_count", 0) + 1
    )

    write_exit_log(
        f"Thread exception: {args.exc_type.__name__}: {args.exc_value}",
        f"thread: {args.thread.name if args.thread else 'unknown'}\n stack trace:\n{tb_str}"
    )


def setup_exit_handlers():
    """Set all exit handlers"""
    # 1. atexit hook
    atexit.register(_atexit_handler)

    # 2. signal processor
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    if hasattr(signal, 'SIGBREAK'):  # Windows
        signal.signal(signal.SIGBREAK, _signal_handler)

    # 3. Global exception hook
    sys.excepthook = _exception_hook

    # 4. Thread exception hook (Python 3.8+)
    if hasattr(threading, 'excepthook'):
        threading.excepthook = _threading_exception_hook

    write_startup_log("Exit handler is set (atexit, signal, excepthook)")


async def main():
    """main function"""
    logger = None
    worker = None

    # Write the startup log first (ensures logging even if there is a problem with the logging system)
    write_startup_log("Worker process starting...")
    write_startup_log(f"Python: {sys.executable}")
    write_startup_log(f"Working directory: {os.getcwd()}")
    write_startup_log(f"PID: {os.getpid()}")

    # update status
    update_worker_state(status="initializing")

    try:
        # Set up logging system
        logger = setup_logging()
        logger.info("=" * 60)
        logger.info("Worker process starting...")
        logger.info(f"Python: {sys.executable}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"PID: {os.getpid()}")
        logger.info("=" * 60)

        # Import Worker (delayed import to avoid import errors resulting in no logs)
        update_worker_state(status="importing")
        try:
            from app.worker.analysis_worker import AnalysisWorker
            logger.info("AnalysisWorker module imported successfully")
        except Exception as import_error:
            update_worker_state(status="import_failed", last_error=str(import_error))
            logger.error(f"Failed to import AnalysisWorker: {import_error}")
            logger.error(traceback.format_exc())
            write_exit_log(f"Import failed: {import_error}", traceback.format_exc())
            sys.exit(1)

        # Create Worker instance
        update_worker_state(status="creating_instance")
        logger.info("Creating Worker instance...")
        worker = AnalysisWorker()
        logger.info(f"Worker instance created: {worker.worker_id}")

        # Start the Worker (this function will run until stopped)
        update_worker_state(status="running")
        logger.info("Starting Worker main loop...")
        await worker.start()

        # if start() Return normally, indicating that the Worker was stopped gracefully
        update_worker_state(status="stopped_normally")
        logger.info("Worker main loop ended normally")
        write_exit_log("The main loop ends normally")

    except KeyboardInterrupt:
        update_worker_state(status="interrupted")
        msg = "Received interrupt signal (Ctrl+C), shutting down..."
        if logger:
            logger.info(msg)
        write_exit_log("User interruption (Ctrl+C)")

    except asyncio.CancelledError:
        update_worker_state(status="cancelled")
        msg = "Async task cancelled"
        if logger:
            logger.info(msg)
        write_exit_log("Asynchronous task canceled")

    except Exception as e:
        update_worker_state(
            status="crashed",
            last_error=str(e),
            error_count=_worker_state.get("error_count", 0) + 1
        )
        error_msg = f"Worker crashed with error: {e}"
        tb_str = traceback.format_exc()
        if logger:
            logger.error(error_msg)
            logger.error(tb_str)
        write_exit_log(f"collapse: {e}", tb_str)
        sys.exit(1)

    finally:
        # Make sure workers clean up resources correctly
        if worker is not None:
            try:
                update_worker_state(status="cleaning_up")
                if logger:
                    logger.info("Cleaning up Worker resources...")
                await worker._cleanup()
                if logger:
                    logger.info("Worker resources cleaned up successfully")
            except Exception as cleanup_error:
                if logger:
                    logger.error(f"Error during cleanup: {cleanup_error}")
                update_worker_state(last_error=f"Cleanup failed: {cleanup_error}")

        # Force flush of all log processors
        if logger:
            for handler in logging.getLogger().handlers:
                try:
                    handler.flush()
                except Exception:
                    pass


if __name__ == "__main__":
    # Make sure the log directory exists
    Path("logs").mkdir(exist_ok=True)

    # Write process startup flag
    write_startup_log("=" * 60)
    write_startup_log("Worker __main__ starting")

    # 🔥 Set exit handler (set at earliest opportunity)
    setup_exit_handlers()

    try:
        # run Worker
        asyncio.run(main())
    except SystemExit as e:
        # Exit normally
        write_exit_log(f"System exit (exit code: {e.code})")
        raise
    except Exception as e:
        # The final exception catch
        update_worker_state(
            status="fatal_error",
            last_error=str(e),
            error_count=_worker_state.get("error_count", 0) + 1
        )
        write_exit_log(f"fatal error: {e}", traceback.format_exc())
        sys.exit(1)

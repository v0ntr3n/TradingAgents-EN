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

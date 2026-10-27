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
        print(f"Worker Child process exit report")
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


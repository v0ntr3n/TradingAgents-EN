import os
import sys
import faulthandler

# 🔧 Make sure the project root is in sys.path so that you can import the app module
# This is especially important for portable versions, as the virtual environment may not contain the project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 🔧 Enable faulthandler to capture crashes such as segfault
# When crashing, the Python call stack will be output to logs/crash.log
logs_dir = os.path.join(project_root, "logs")
os.makedirs(logs_dir, exist_ok=True)
crash_log_path = os.path.join(logs_dir, "crash.log")
try:
    crash_log_file = open(crash_log_path, "w")
    faulthandler.enable(file=crash_log_file)
    print(f"🔧 Faulthandler enabled, crash log: {crash_log_path}")
except (PermissionError, OSError) as e:
    # crash.log Failure to open does not block startup (may be a permission issue or path restriction)
    faulthandler.enable()
    print(f"⚠️  Faulthandler enabled (stderr only), crash.log open failed: {e}")

import uvicorn

def main():
    # 🔧 Use pydantic settings to read the configuration (the .env file will be automatically loaded)
    # instead of os.getenv() (Only read system environment variables, do not load .env)
    from app.core.config import settings

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )

if __name__ == "__main__":
    main()
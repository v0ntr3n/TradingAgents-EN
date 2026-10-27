"""
Development environment configuration
Optimize development experience and reduce unnecessary file monitoring
"""

import logging
from typing import List, Optional


class DevConfig:
    """Development environment configuration class"""
    
    # File monitoring configuration
    RELOAD_DIRS: List[str] = ["app"]
    
    # Excluded files and directories
    RELOAD_EXCLUDES: List[str] = [
        # Python Cache files
        "__pycache__",
        "*.pyc",
        "*.pyo", 
        "*.pyd",
        
        # version control
        ".git",
        ".gitignore",
        
        # Testing and caching
        ".pytest_cache",
        ".coverage",
        "htmlcov",
        
        # log file
        "*.log",
        "logs",
        
        # temporary files
        "*.tmp",
        "*.temp",
        "*.swp",
        "*.swo",
        
        # System files
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        
        # IDE File
        ".vscode",
        ".idea",
        "*.sublime-*",
        
        # data file
        "*.db",
        "*.sqlite",
        "*.sqlite3",
        
        # Configuration files (avoid overloading sensitive information)
        ".env",
        ".env.local",
        ".env.production",
        
        # Documentation and static files
        "*.md",
        "*.txt",
        "*.json",
        "*.yaml",
        "*.yml",
        "*.toml",
        
        # Front-end files
        "node_modules",
        "dist",
        "build",
        "*.js",
        "*.css",
        "*.html",
        
        # Others
        "requirements*.txt",
        "Dockerfile*",
        "docker-compose*"
    ]
    
    # Only file types to monitor
    RELOAD_INCLUDES: List[str] = [
        "*.py"
    ]
    
    # Reload delay (seconds)
    RELOAD_DELAY: float = 0.5
    
    # Log configuration
    LOG_LEVEL: str = "info"
    
    # Whether to display access logs
    ACCESS_LOG: bool = True
    
    @classmethod
    def get_uvicorn_config(cls, debug: bool = True) -> dict:
        """Get uvicorn configuration"""
        # Disable reload uniformly to avoid log configuration conflicts
        return {
            "reload": False,  # Disable auto-reload, manual restart
            "log_level": cls.LOG_LEVEL,
            "access_log": cls.ACCESS_LOG,
            # Make sure to use our custom log configuration
            "log_config": None  # Disable uvicorn default log configuration and use our configuration
        }
    
    @classmethod
    def setup_logging(cls, debug: bool = True):
        """Set up a simplified logging configuration"""
        # Set a unified log format
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            force=True  # Force reconfiguration, overwriting previous settings
        )

        if debug:
            # Development Environment: Reduce Noise Logging
            logging.getLogger("watchfiles").setLevel(logging.ERROR)
            logging.getLogger("watchfiles.main").setLevel(logging.ERROR)
            logging.getLogger("watchfiles.watcher").setLevel(logging.ERROR)

            # Ensure important logs are displayed properly
            logging.getLogger("webapi").setLevel(logging.INFO)
            logging.getLogger("app.core.database").setLevel(logging.INFO)
            logging.getLogger("uvicorn.error").setLevel(logging.INFO)

            # Test whether the webapi logger is working
            webapi_logger = logging.getLogger("webapi")
            webapi_logger.info("🔧 DEV_CONFIG: webapi logger test message")
        else:
            # Production environment: tighter log control
            logging.getLogger("watchfiles").setLevel(logging.ERROR)
            logging.getLogger("uvicorn").setLevel(logging.WARNING)


# Development environment quick configuration
DEV_CONFIG = DevConfig()

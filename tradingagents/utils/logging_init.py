#!/usr/bin/env python3
"""
Log system initialization module
Initialize the unified logging system when the application starts
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Add project root directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.utils.logging_manager import setup_logging, get_logger


def init_logging(config_override: Optional[dict] = None) -> None:
    """
    Initialize project log system
    
    Args:
        config_override: Optional configuration overrides
    """
    # Set up logging system
    logger_manager = setup_logging(config_override)
    
    # Get initialization logger
    logger = get_logger('tradingagents.init')
    
    # Record initialization information
    logger.info("🚀 TradingAgents-CN Log system initialization completed")
    logger.info(f"📁 Log directory: {logger_manager.config.get('handlers', {}).get('file', {}).get('directory', 'N/A')}")
    logger.info(f"📊 Log level: {logger_manager.config.get('level', 'INFO')}")
    
    # Docker Special environmental treatment
    if logger_manager.config.get('docker', {}).get('enabled', False):
        logger.info("🐳 Docker Environment detected, use container optimization configuration")
    
    # Record environmental information
    logger.debug(f"🔧 Python version: {sys.version}")
    logger.debug(f"📂 working directory: {os.getcwd()}")
    logger.debug(f"🌍 environment variables: DOCKER_CONTAINER={os.getenv('DOCKER_CONTAINER', 'false')}")


def get_session_logger(session_id: str, module_name: str = 'session') -> 'logging.Logger':
    """
    Get session-specific logger
    
    Args:
        session_id: session ID
        module_name: module name
        
    Returns:
        Configured logger
    """
    logger_name = f"{module_name}.{session_id[:8]}"  # Use top 8 sessions ID
    
    # Add session ID to all logging
    class SessionAdapter:
        def __init__(self, logger, session_id):
            self.logger = logger
            self.session_id = session_id
        
        def debug(self, msg, *args, **kwargs):
            kwargs.setdefault('extra', {})['session_id'] = self.session_id
            return self.logger.debug(msg, *args, **kwargs)
        
        def info(self, msg, *args, **kwargs):
            kwargs.setdefault('extra', {})['session_id'] = self.session_id
            return self.logger.info(msg, *args, **kwargs)
        
        def warning(self, msg, *args, **kwargs):
            kwargs.setdefault('extra', {})['session_id'] = self.session_id
            return self.logger.warning(msg, *args, **kwargs)
        
        def error(self, msg, *args, **kwargs):
            kwargs.setdefault('extra', {})['session_id'] = self.session_id
            return self.logger.error(msg, *args, **kwargs)
        
        def critical(self, msg, *args, **kwargs):
            kwargs.setdefault('extra', {})['session_id'] = self.session_id
            return self.logger.critical(msg, *args, **kwargs)
    
    return SessionAdapter(logger, session_id)


def log_startup_info():
    """Record application startup information"""
    logger = get_logger('tradingagents.startup')
    
    logger.info("=" * 60)
    logger.info("🎯 TradingAgents-CN start")
    logger.info("=" * 60)
    
    # System information
    import platform
    logger.info(f"🖥️  system: {platform.system()} {platform.release()}")
    logger.info(f"🐍 Python: {platform.python_version()}")
    
    # environmental information
    env_info = {
        'DOCKER_CONTAINER': os.getenv('DOCKER_CONTAINER', 'false'),
        'TRADINGAGENTS_LOG_LEVEL': os.getenv('TRADINGAGENTS_LOG_LEVEL', 'INFO'),
        'TRADINGAGENTS_LOG_DIR': os.getenv('TRADINGAGENTS_LOG_DIR', './logs'),
    }
    
    for key, value in env_info.items():
        logger.info(f"🔧 {key}: {value}")
    
    logger.info("=" * 60)


def log_shutdown_info():
    """Record application closing information"""
    logger = get_logger('tradingagents.shutdown')
    
    logger.info("=" * 60)
    logger.info("🛑 TradingAgents-CN close")
    logger.info("=" * 60)


# Convenience function
def setup_web_logging():
    """Set up web application-specific logs"""
    init_logging()
    log_startup_info()
    return get_logger('web')


def setup_analysis_logging(session_id: str):
    """Set up analysis-specific logs"""
    return get_session_logger(session_id, 'analysis')


def setup_dataflow_logging():
    """Set up data flow-specific logs"""
    return get_logger('dataflows')


def setup_llm_logging():
    """Set up LLM adapter-specific logs"""
    return get_logger('llm_adapters')


if __name__ == "__main__":
    # Test logging system
    init_logging()
    log_startup_info()
    
    # Test logs from different modules
    web_logger = setup_web_logging()
    web_logger.info("Web Module log test")
    
    analysis_logger = setup_analysis_logging("test-session-123")
    analysis_logger.info("Analysis module log test")
    
    dataflow_logger = setup_dataflow_logging()
    dataflow_logger.info("Data flow module log test")
    
    llm_logger = setup_llm_logging()
    llm_logger.info("LLM Adapter module log test")
    
    log_shutdown_info()

#!/usr/bin/env python3
"""
Unified log manager
Provide project-level log configuration and management functions
"""

import logging
import logging.handlers
import os
import sys
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union
import json
import toml

# 🔥 Support multi-process safe writing using concurrent-log-handler on all platforms
# Windows: Fix file locking issues
# Linux/Mac: Supports multi-process (backend + Worker) Write to the same log file simultaneously
try:
    from concurrent_log_handler import ConcurrentRotatingFileHandler
    _USE_CONCURRENT_HANDLER = True
except ImportError:
    _USE_CONCURRENT_HANDLER = False
    _IS_WINDOWS = platform.system() == "Windows"
    if _IS_WINDOWS:
        logging.warning("concurrent-log-handler Not installed, may experience log rotation issues on Windows")
    else:
        logging.warning("concurrent-log-handler Not installed, it may be unsafe for multiple processes to write to the log file (backend and Worker write at the same time)")

# Note: You cannot import yourself here, which will cause a circular import.
# Before the logging system is initialized, use the standard library to bootstrap the logger to avoid undefined references.
_bootstrap_logger = logging.getLogger("tradingagents.logging_manager")


class ColoredFormatter(logging.Formatter):
    """Color log formatter"""
    
    # ANSI color code
    COLORS = {
        'DEBUG': '\033[36m',    # cyan
        'INFO': '\033[32m',     # green
        'WARNING': '\033[33m',  # yellow
        'ERROR': '\033[31m',    # red
        'CRITICAL': '\033[35m', # purple
        'RESET': '\033[0m'      # reset
    }
    
    def format(self, record):
        # add color
        if hasattr(record, 'levelname') and record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
        
        return super().format(record)


class StructuredFormatter(logging.Formatter):
    """Structured log formatter (JSON format)"""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add extra fields
        if hasattr(record, 'session_id'):
            log_entry['session_id'] = record.session_id
        if hasattr(record, 'analysis_type'):
            log_entry['analysis_type'] = record.analysis_type
        if hasattr(record, 'stock_symbol'):
            log_entry['stock_symbol'] = record.stock_symbol
        if hasattr(record, 'cost'):
            log_entry['cost'] = record.cost
        if hasattr(record, 'tokens'):
            log_entry['tokens'] = record.tokens
            
        return json.dumps(log_entry, ensure_ascii=False)


class TradingAgentsLogger:
    """TradingAgents Unified log manager"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or self._load_default_config()
        self.loggers: Dict[str, logging.Logger] = {}
        self._setup_logging()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load default log configuration"""
        # Try loading from config file
        config = self._load_config_file()
        if config:
            return config

        # Get configuration from environment variables
        log_level = os.getenv('TRADINGAGENTS_LOG_LEVEL', 'INFO').upper()
        log_dir = os.getenv('TRADINGAGENTS_LOG_DIR', './logs')

        return {
            'level': log_level,
            'format': {
                'console': '%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
                'file': '%(asctime)s | %(name)-20s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(message)s',
                'structured': 'json'
            },
            'handlers': {
                'console': {
                    'enabled': True,
                    'colored': True,
                    'level': log_level
                },
                'file': {
                    'enabled': True,
                    'level': 'DEBUG',
                    'max_size': '10MB',
                    'backup_count': 5,
                    'directory': log_dir
                },
                'error': {
                    'enabled': True,
                    'level': 'WARNING',  # Only record levels of WARNING and above
                    'max_size': '10MB',
                    'backup_count': 5,
                    'directory': log_dir,
                    'filename': 'error.log'
                },
                'structured': {
                    'enabled': False,  # Off by default, can be enabled through environment variables
                    'level': 'INFO',
                    'directory': log_dir
                }
            },
            'loggers': {
                'tradingagents': {'level': log_level},
                'web': {'level': log_level},
                'streamlit': {'level': 'WARNING'},  # Streamlit If there are more logs, set to WARNING
                'urllib3': {'level': 'WARNING'},    # HTTP There are many request logs
                'requests': {'level': 'WARNING'},
                'matplotlib': {'level': 'WARNING'}
            },
            'docker': {
                'enabled': os.getenv('DOCKER_CONTAINER', 'false').lower() == 'true',
                'stdout_only': True  # Docker The environment only outputs to stdout
            }
        }

    def _load_config_file(self) -> Optional[Dict[str, Any]]:
        """Load log configuration from configuration file"""
        # Determine configuration file path
        config_paths = [
            'config/logging_docker.toml' if os.getenv('DOCKER_CONTAINER') == 'true' else None,
            'config/logging.toml',
            './logging.toml'
        ]

        for config_path in config_paths:
            if config_path and Path(config_path).exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_data = toml.load(f)

                    # Convert configuration format
                    return self._convert_toml_config(config_data)
                except Exception as e:
                    _bootstrap_logger.warning(f"warning: Unable to load configuration file {config_path}: {e}")
                    continue

        return None

    def _convert_toml_config(self, toml_config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert TOML configuration to internal configuration format"""
        logging_config = toml_config.get('logging', {})

        # Check Docker environment
        is_docker = (
            os.getenv('DOCKER_CONTAINER') == 'true' or
            logging_config.get('docker', {}).get('enabled', False)
        )

        return {
            'level': logging_config.get('level', 'INFO'),
            'format': logging_config.get('format', {}),
            'handlers': logging_config.get('handlers', {}),
            'loggers': logging_config.get('loggers', {}),
            'docker': {
                'enabled': is_docker,
                'stdout_only': logging_config.get('docker', {}).get('stdout_only', True)
            },
            'performance': logging_config.get('performance', {}),
            'security': logging_config.get('security', {}),
            'business': logging_config.get('business', {})
        }
    
    def _setup_logging(self):
        """Set up logging system"""
        # Create log directory
        if self.config['handlers']['file']['enabled']:
            log_dir = Path(self.config['handlers']['file']['directory'])
            log_dir.mkdir(parents=True, exist_ok=True)
        
        # Set root log level
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.config['level']))
        
        # Clear existing processor
        root_logger.handlers.clear()
        
        # Add processor
        self._add_console_handler(root_logger)

        if not self.config['docker']['enabled'] or not self.config['docker']['stdout_only']:
            self._add_file_handler(root_logger)
            self._add_error_handler(root_logger)  # 🔧 Add error log handler
            if self.config['handlers']['structured']['enabled']:
                self._add_structured_handler(root_logger)
        
        # Configure a specific logger
        self._configure_specific_loggers()
    
    def _add_console_handler(self, logger: logging.Logger):
        """Add console handler"""
        if not self.config['handlers']['console']['enabled']:
            return
            
        console_handler = logging.StreamHandler(sys.stdout)
        console_level = getattr(logging, self.config['handlers']['console']['level'])
        console_handler.setLevel(console_level)
        
        # Select formatter
        if self.config['handlers']['console']['colored'] and sys.stdout.isatty():
            formatter = ColoredFormatter(self.config['format']['console'])
        else:
            formatter = logging.Formatter(self.config['format']['console'])
        
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    def _add_file_handler(self, logger: logging.Logger):
        """Add file handler"""
        if not self.config['handlers']['file']['enabled']:
            return

        log_dir = Path(self.config['handlers']['file']['directory'])
        log_file = log_dir / 'tradingagents.log'

        # Using RotatingFileHandler for log rotation
        max_size = self._parse_size(self.config['handlers']['file']['max_size'])
        backup_count = self.config['handlers']['file']['backup_count']

        # 🔥 Use ConcurrentRotatingFileHandler on Windows to avoid file occupancy issues
        if _USE_CONCURRENT_HANDLER:
            file_handler = ConcurrentRotatingFileHandler(
                log_file,
                maxBytes=max_size,
                backupCount=backup_count,
                encoding='utf-8'
            )
        else:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_size,
                backupCount=backup_count,
                encoding='utf-8'
            )

        file_level = getattr(logging, self.config['handlers']['file']['level'])
        file_handler.setLevel(file_level)

        formatter = logging.Formatter(self.config['format']['file'])
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    def _add_error_handler(self, logger: logging.Logger):
        """Add error log processor (only log WARNING and above levels)"""
        # Check if error handler is enabled
        error_config = self.config['handlers'].get('error', {})
        if not error_config.get('enabled', True):
            return

        log_dir = Path(error_config.get('directory', self.config['handlers']['file']['directory']))
        error_log_file = log_dir / error_config.get('filename', 'error.log')

        # Using RotatingFileHandler for log rotation
        max_size = self._parse_size(error_config.get('max_size', '10MB'))
        backup_count = error_config.get('backup_count', 5)

        # 🔥 Use ConcurrentRotatingFileHandler on Windows to avoid file occupancy issues
        if _USE_CONCURRENT_HANDLER:
            error_handler = ConcurrentRotatingFileHandler(
                error_log_file,
                maxBytes=max_size,
                backupCount=backup_count,
                encoding='utf-8'
            )
        else:
            error_handler = logging.handlers.RotatingFileHandler(
                error_log_file,
                maxBytes=max_size,
                backupCount=backup_count,
                encoding='utf-8'
            )

        # 🔧 Only WARNING and above levels are recorded (WARNING, ERROR, CRITICAL) 
        error_level = getattr(logging, error_config.get('level', 'WARNING'))
        error_handler.setLevel(error_level)

        formatter = logging.Formatter(self.config['format']['file'])
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)
    
    def _add_structured_handler(self, logger: logging.Logger):
        """Add structured log processor"""
        log_dir = Path(self.config['handlers']['structured']['directory'])
        log_file = log_dir / 'tradingagents_structured.log'
        
        structured_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=self._parse_size('10MB'),
            backupCount=3,
            encoding='utf-8'
        )
        
        structured_level = getattr(logging, self.config['handlers']['structured']['level'])
        structured_handler.setLevel(structured_level)
        
        formatter = StructuredFormatter()
        structured_handler.setFormatter(formatter)
        logger.addHandler(structured_handler)
    
    def _configure_specific_loggers(self):
        """Configure a specific logger"""
        for logger_name, logger_config in self.config['loggers'].items():
            logger = logging.getLogger(logger_name)
            level = getattr(logging, logger_config['level'])
            logger.setLevel(level)
    
    def _parse_size(self, size_str: str) -> int:
        """Parse size strings (like'10MB') is the number of bytes"""
        size_str = size_str.upper()
        if size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get the logger with the specified name"""
        if name not in self.loggers:
            self.loggers[name] = logging.getLogger(name)
        return self.loggers[name]
    
    def log_analysis_start(self, logger: logging.Logger, stock_symbol: str, analysis_type: str, session_id: str):
        """Record analysis begins"""
        logger.info(
            f"🚀 Start Analysis - Stocks: {stock_symbol}, Type: {analysis_type}",
            extra={
                'stock_symbol': stock_symbol,
                'analysis_type': analysis_type,
                'session_id': session_id,
                'event_type': 'analysis_start',
                'timestamp': datetime.now().isoformat()
            }
        )

    def log_analysis_complete(self, logger: logging.Logger, stock_symbol: str, analysis_type: str,
                            session_id: str, duration: float, cost: float = 0):
        """Record analysis completed"""
        logger.info(
            f"✅ Analysis Complete - Stocks: {stock_symbol}, Time consuming: {duration:.2f}s, cost: ¥{cost:.4f}",
            extra={
                'stock_symbol': stock_symbol,
                'analysis_type': analysis_type,
                'session_id': session_id,
                'duration': duration,
                'cost': cost,
                'event_type': 'analysis_complete',
                'timestamp': datetime.now().isoformat()
            }
        )

    def log_module_start(self, logger: logging.Logger, module_name: str, stock_symbol: str,
                        session_id: str, **extra_data):
        """The recording module starts analysis"""
        logger.info(
            f"📊 [module start] {module_name} - stocks: {stock_symbol}",
            extra={
                'module_name': module_name,
                'stock_symbol': stock_symbol,
                'session_id': session_id,
                'event_type': 'module_start',
                'timestamp': datetime.now().isoformat(),
                **extra_data
            }
        )

    def log_module_complete(self, logger: logging.Logger, module_name: str, stock_symbol: str,
                           session_id: str, duration: float, success: bool = True,
                           result_length: int = 0, **extra_data):
        """Recording module completes analysis"""
        status = "✅ success" if success else "❌ failed"
        logger.info(
            f"📊 [Module completed] {module_name} - {status} - stocks: {stock_symbol}, Time consuming: {duration:.2f}s",
            extra={
                'module_name': module_name,
                'stock_symbol': stock_symbol,
                'session_id': session_id,
                'duration': duration,
                'success': success,
                'result_length': result_length,
                'event_type': 'module_complete',
                'timestamp': datetime.now().isoformat(),
                **extra_data
            }
        )

    def log_module_error(self, logger: logging.Logger, module_name: str, stock_symbol: str,
                        session_id: str, duration: float, error: str, **extra_data):
        """Logging module analysis errors"""
        logger.error(
            f"❌ [Module error] {module_name} - stocks: {stock_symbol}, Time consuming: {duration:.2f}s, Error: {error}",
            extra={
                'module_name': module_name,
                'stock_symbol': stock_symbol,
                'session_id': session_id,
                'duration': duration,
                'error': error,
                'event_type': 'module_error',
                'timestamp': datetime.now().isoformat(),
                **extra_data
            },
            exc_info=True
        )
    
    def log_token_usage(self, logger: logging.Logger, provider: str, model: str, 
                       input_tokens: int, output_tokens: int, cost: float, session_id: str):
        """Record Token usage"""
        logger.info(
            f"📊 Token Use - {provider}/{model}: input={input_tokens}, output={output_tokens}, cost=¥{cost:.6f}",
            extra={
                'provider': provider,
                'model': model,
                'tokens': {'input': input_tokens, 'output': output_tokens},
                'cost': cost,
                'session_id': session_id,
                'event_type': 'token_usage'
            }
        )


# Global log manager instance
_logger_manager: Optional[TradingAgentsLogger] = None


def get_logger_manager() -> TradingAgentsLogger:
    """Get global log manager instance"""
    global _logger_manager
    if _logger_manager is None:
        _logger_manager = TradingAgentsLogger()
    return _logger_manager


def get_logger(name: str) -> logging.Logger:
    """Get the logger with the specified name (convenience function)"""
    return get_logger_manager().get_logger(name)


def setup_logging(config: Optional[Dict[str, Any]] = None):
    """Set up the project log system (convenience function)"""
    global _logger_manager
    _logger_manager = TradingAgentsLogger(config)
    return _logger_manager

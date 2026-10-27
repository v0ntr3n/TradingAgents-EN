import logging
import logging.config
import sys
import json
from pathlib import Path
import os
import platform

from app.core.logging_context import LoggingContextFilter, trace_id_var

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

try:
    import tomllib as toml_loader  # Python 3.11+
except Exception:
    try:
        import tomli as toml_loader  # Python 3.10 fallback
    except Exception:
        toml_loader = None


def resolve_logging_cfg_path() -> Path:
    """Select the log configuration file path according to the environment (may not exist)
    Prioritize docker configuration, followed by default configuration.
    """
    profile = os.environ.get("LOGGING_PROFILE", "").lower()
    is_docker_env = os.environ.get("DOCKER", "").lower() in {"1", "true", "yes"} or Path("/.dockerenv").exists()
    cfg_candidate = "config/logging_docker.toml" if profile == "docker" or is_docker_env else "config/logging.toml"
    return Path(cfg_candidate)


class SimpleJsonFormatter(logging.Formatter):
    """Minimal JSON formatter without external deps."""
    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "time": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "name": record.name,
            "level": record.levelname,
            "trace_id": getattr(record, "trace_id", "-"),
            "message": record.getMessage(),
        }
        return json.dumps(obj, ensure_ascii=False)


class ErrorLogNoiseFilter(logging.Filter):
    """Filter error.log for known non-fatal third-party/optional capability noise."""

    _NOISY_PATTERNS = (
        "predates v3 hybrid search",
        "BM25 keyword scoring will be disabled",
        "Multiple active PostHog clients detected",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(pattern in message for pattern in self._NOISY_PATTERNS)


def _error_handler_filters() -> list[str]:
    return ["request_context", "error_noise_filter"]


def _build_common_filters() -> dict:
    return {
        "request_context": {"()": "app.core.logging_context.LoggingContextFilter"},
        "error_noise_filter": {"()": "app.core.logging_config.ErrorLogNoiseFilter"},
    }


def _parse_size(size_str: str) -> int:
    """Parse size strings (like '10MB') is the number of bytes"""
    if isinstance(size_str, int):
        return size_str
    if isinstance(size_str, str) and size_str.upper().endswith("MB"):
        try:
            return int(float(size_str[:-2]) * 1024 * 1024)
        except Exception:
            return 10 * 1024 * 1024
    return 10 * 1024 * 1024

def setup_logging(log_level: str = "INFO"):
    """
    Set application log configuration:
    1) First try to read from config/logging.toml and convert it to dictConfig
    2) On failure or non-existence, fall back to the built-in default configuration
    """
    # 🔐 The production environment does not output sensitive configuration information by default
    # settings TRADINGAGENTS_VERBOSE_SETUP=true Enable verbose output (for debugging)
    verbose_setup = os.getenv("TRADINGAGENTS_VERBOSE_SETUP", "").lower() in ("true", "1", "yes")
    
    # 1) If TOML configuration exists and can be parsed, it will be used first.
    try:
        cfg_path = resolve_logging_cfg_path()
        if verbose_setup:
            print(f"🔍 [setup_logging] Log configuration file path: {cfg_path}")
            print(f"🔍 [setup_logging] Configuration file exists: {cfg_path.exists()}")
            print(f"🔍 [setup_logging] TOML Loader available: {toml_loader is not None}")

        if cfg_path.exists() and toml_loader is not None:
            with cfg_path.open("rb") as f:
                toml_data = toml_loader.load(f)

            if verbose_setup:
                print(f"🔍 [setup_logging] Successfully loaded TOML configuration")

            # Read basic fields
            logging_root = toml_data.get("logging", {})
            level = logging_root.get("level", log_level)
            fmt_cfg = logging_root.get("format", {})
            fmt_console = fmt_cfg.get(
                "console", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            fmt_file = fmt_cfg.get(
                "file", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            # Make sure the text format includes trace_id if not included explicitly
            if "%(trace_id)" not in str(fmt_console):
                fmt_console = str(fmt_console) + " trace=%(trace_id)s"
            if "%(trace_id)" not in str(fmt_file):
                fmt_file = str(fmt_file) + " trace=%(trace_id)s"

            handlers_cfg = logging_root.get("handlers", {})
            file_handler_cfg = handlers_cfg.get("file", {})
            file_dir = file_handler_cfg.get("directory", "./logs")
            file_level = file_handler_cfg.get("level", "DEBUG")
            max_bytes = file_handler_cfg.get("max_size", "10MB")
            # support "10MB" form
            if isinstance(max_bytes, str) and max_bytes.upper().endswith("MB"):
                try:
                    max_bytes = int(float(max_bytes[:-2]) * 1024 * 1024)
                except Exception:
                    max_bytes = 10 * 1024 * 1024
            elif not isinstance(max_bytes, int):
                max_bytes = 10 * 1024 * 1024
            backup_count = int(file_handler_cfg.get("backup_count", 5))

            Path(file_dir).mkdir(parents=True, exist_ok=True)

            # Read individual log file paths from TOML configuration
            main_handler_cfg = handlers_cfg.get("main", {})
            webapi_handler_cfg = handlers_cfg.get("webapi", {})
            worker_handler_cfg = handlers_cfg.get("worker", {})

            if verbose_setup:
                print(f"🔍 [setup_logging] handlers Configuration: {list(handlers_cfg.keys())}")
                print(f"🔍 [setup_logging] main_handler_cfg: {main_handler_cfg}")
                print(f"🔍 [setup_logging] webapi_handler_cfg: {webapi_handler_cfg}")
                print(f"🔍 [setup_logging] worker_handler_cfg: {worker_handler_cfg}")

            # Main log file (tradingagents.log)
            main_log = main_handler_cfg.get("filename", str(Path(file_dir) / "tradingagents.log"))
            main_enabled = main_handler_cfg.get("enabled", True)
            main_level = main_handler_cfg.get("level", "INFO")
            main_max_bytes = _parse_size(main_handler_cfg.get("max_size", "100MB"))
            main_backup_count = int(main_handler_cfg.get("backup_count", 5))

            if verbose_setup:
                print(f"🔍 [setup_logging] Master log file configuration:")
                print(f"  - file path: {main_log}")
                print(f"  - Whether to enable: {main_enabled}")
                print(f"  - Log level: {main_level}")
                print(f"  - maximum size: {main_max_bytes} bytes")
                print(f"  - Number of backups: {main_backup_count}")

            # WebAPI log file
            webapi_log = webapi_handler_cfg.get("filename", str(Path(file_dir) / "webapi.log"))
            webapi_enabled = webapi_handler_cfg.get("enabled", True)
            webapi_level = webapi_handler_cfg.get("level", "DEBUG")
            webapi_max_bytes = _parse_size(webapi_handler_cfg.get("max_size", "100MB"))
            webapi_backup_count = int(webapi_handler_cfg.get("backup_count", 5))

            if verbose_setup:
                print(f"🔍 [setup_logging] WebAPI log file: {webapi_log}, enable: {webapi_enabled}")

            # Worker log file
            worker_log = worker_handler_cfg.get("filename", str(Path(file_dir) / "worker.log"))
            worker_enabled = worker_handler_cfg.get("enabled", True)
            worker_level = worker_handler_cfg.get("level", "DEBUG")
            worker_max_bytes = _parse_size(worker_handler_cfg.get("max_size", "100MB"))
            worker_backup_count = int(worker_handler_cfg.get("backup_count", 5))

            if verbose_setup:
                print(f"🔍 [setup_logging] Worker log file: {worker_log}, enable: {worker_enabled}")

            # error log file
            error_handler_cfg = handlers_cfg.get("error", {})
            error_dir = error_handler_cfg.get("directory", file_dir)
            error_filename = error_handler_cfg.get("filename", "error.log")
            # If filename is a relative path, combined with directory
            if not Path(error_filename).is_absolute():
                error_log = str(Path(error_dir) / error_filename)
            else:
                error_log = error_filename
            error_enabled = error_handler_cfg.get("enabled", True)
            error_level = error_handler_cfg.get("level", "WARNING")
            error_max_bytes = _parse_size(error_handler_cfg.get("max_size", "100MB"))
            error_backup_count = int(error_handler_cfg.get("backup_count", 5))

            if verbose_setup:
                print(f"🔍 [setup_logging] Error log file configuration:")
                print(f"  - file path: {error_log}")
                print(f"  - Whether to enable: {error_enabled}")
                print(f"  - Log level: {error_level}")

            # Skill Workshop log file (separately records the skill generation process)
            skill_handler_cfg = handlers_cfg.get("skill", {})
            skill_dir = skill_handler_cfg.get("directory", file_dir)
            skill_filename = skill_handler_cfg.get("filename", "skill_workshop.log")
            if not Path(skill_filename).is_absolute():
                skill_log = str(Path(skill_dir) / skill_filename)
            else:
                skill_log = skill_filename
            skill_enabled = skill_handler_cfg.get("enabled", True)
            skill_level = skill_handler_cfg.get("level", "DEBUG")
            skill_max_bytes = _parse_size(skill_handler_cfg.get("max_size", "20MB"))
            skill_backup_count = int(skill_handler_cfg.get("backup_count", 10))

            if verbose_setup:
                print(f"🔍 [setup_logging] Skill Workshop log file configuration:")
                print(f"  - file path: {skill_log}")
                print(f"  - Whether to enable: {skill_enabled}")
                print(f"  - Log level: {skill_level}")

            # JSON Switch: Maintain backward compatibility (json/mode console only); add file_json/file_mode control file handler
            use_json_console = bool(fmt_cfg.get("json", False)) or str(fmt_cfg.get("mode", "")).lower() == "json"
            use_json_file = (
                bool(fmt_cfg.get("file_json", False))
                or bool(fmt_cfg.get("json_file", False))
                or str(fmt_cfg.get("file_mode", "")).lower() == "json"
            )

            # Build processor configuration
            handlers_config = {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json_console_fmt" if use_json_console else "console_fmt",
                    "level": level,
                    "filters": ["request_context"],
                    "stream": sys.stdout,
                },
            }

            if verbose_setup:
                print(f"🔍 [setup_logging] Start building handlers configuration")

            # 🔥 Select a log handler class (Windows uses ConcurrentRotatingFileHandler)
            handler_class = "concurrent_log_handler.ConcurrentRotatingFileHandler" if _USE_CONCURRENT_HANDLER else "logging.handlers.RotatingFileHandler"

            # Main log file (tradingagents.log)
            if main_enabled:
                if verbose_setup:
                    print(f"✅ [setup_logging] add main_file handler: {main_log} (Use {handler_class})")
                handlers_config["main_file"] = {
                    "class": handler_class,
                    "formatter": "json_file_fmt" if use_json_file else "file_fmt",
                    "level": main_level,
                    "filename": main_log,
                    "maxBytes": main_max_bytes,
                    "backupCount": main_backup_count,
                    "encoding": "utf-8",
                    "filters": ["request_context"],
                }
            else:
                if verbose_setup:
                    print(f"⚠️ [setup_logging] main_file handler Not enabled")

            # WebAPI log file
            if webapi_enabled:
                handlers_config["file"] = {
                    "class": handler_class,
                    "formatter": "json_file_fmt" if use_json_file else "file_fmt",
                    "level": webapi_level,
                    "filename": webapi_log,
                    "maxBytes": webapi_max_bytes,
                    "backupCount": webapi_backup_count,
                    "encoding": "utf-8",
                    "filters": ["request_context"],
                }

            # Worker log file
            if worker_enabled:
                handlers_config["worker_file"] = {
                    "class": handler_class,
                    "formatter": "json_file_fmt" if use_json_file else "file_fmt",
                    "level": worker_level,
                    "filename": worker_log,
                    "maxBytes": worker_max_bytes,
                    "backupCount": worker_backup_count,
                    "encoding": "utf-8",
                    "filters": ["request_context"],
                }

            # Add error log handler (if enabled)
            if error_enabled:
                handlers_config["error_file"] = {
                    "class": handler_class,  # 🔥 Use the same processor class as the main log
                    "formatter": "json_file_fmt" if use_json_file else "file_fmt",
                    "level": error_level,
                    "filename": error_log,
                    "maxBytes": error_max_bytes,
                    "backupCount": error_backup_count,
                    "encoding": "utf-8",
                    "filters": _error_handler_filters(),
                }

            # Skill Workshop log processor (separately records the skill generation process)
            if skill_enabled:
                handlers_config["skill_file"] = {
                    "class": handler_class,
                    "formatter": "json_file_fmt" if use_json_file else "file_fmt",
                    "level": skill_level,
                    "filename": skill_log,
                    "maxBytes": skill_max_bytes,
                    "backupCount": skill_backup_count,
                    "encoding": "utf-8",
                    "filters": ["request_context"],
                }

            # Build a list of logger handlers
            main_handlers = ["console"]
            if main_enabled:
                main_handlers.append("main_file")
            if error_enabled:
                main_handlers.append("error_file")

            if verbose_setup:
                print(f"🔍 [setup_logging] main_handlers: {main_handlers}")

            webapi_handlers = ["console"]
            if webapi_enabled:
                webapi_handlers.append("file")
            if main_enabled:
                webapi_handlers.append("main_file")
            if error_enabled:
                webapi_handlers.append("error_file")

            if verbose_setup:
                print(f"🔍 [setup_logging] webapi_handlers: {webapi_handlers}")

            worker_handlers = ["console"]
            if worker_enabled:
                worker_handlers.append("worker_file")
            if main_enabled:
                worker_handlers.append("main_file")
            if error_enabled:
                worker_handlers.append("error_file")

            if verbose_setup:
                print(f"🔍 [setup_logging] worker_handlers: {worker_handlers}")

            # Skill Workshop handlers:console + skill_file (+ error_file catch errors)
            skill_handlers = ["console"]
            if skill_enabled:
                skill_handlers.append("skill_file")
            if error_enabled:
                skill_handlers.append("error_file")

            if verbose_setup:
                print(f"🔍 [setup_logging] skill_handlers: {skill_handlers}")

            logging_config = {
                "version": 1,
                "disable_existing_loggers": False,
                "filters": _build_common_filters(),
                "formatters": {
                    "console_fmt": {
                        "format": fmt_console,
                        "datefmt": "%Y-%m-%d %H:%M:%S",
                    },
                    "file_fmt": {
                        "format": fmt_file,
                        "datefmt": "%Y-%m-%d %H:%M:%S",
                    },
                    "json_console_fmt": {
                        "()": "app.core.logging_config.SimpleJsonFormatter"
                    },
                    "json_file_fmt": {
                        "()": "app.core.logging_config.SimpleJsonFormatter"
                    },
                },
                "handlers": handlers_config,
                "loggers": {
                    "tradingagents": {
                        "level": "INFO",
                        "handlers": main_handlers,
                        "propagate": False
                    },
                    "webapi": {
                        "level": "INFO",
                        "handlers": webapi_handlers,
                        "propagate": False
                    },
                    "worker": {
                        "level": "DEBUG",
                        "handlers": worker_handlers,
                        "propagate": False
                    },
                    "uvicorn": {
                        "level": "INFO",
                        "handlers": webapi_handlers,
                        "propagate": False
                    },
                    "fastapi": {
                        "level": "INFO",
                        "handlers": webapi_handlers,
                        "propagate": False
                    },
                    "app": {
                        "level": "INFO",
                        "handlers": main_handlers,
                        "propagate": False
                    },
                    "core": {
                        "level": "INFO",
                        "handlers": main_handlers,
                        "propagate": False
                    },
                    # Skill Workshop-specific logger: The logs of the skill generation process are output separately to skill_workshop.log
                    # code_generator / iteration_controller / reconnaissance_controller Use other modules
                    "skill_workshop": {
                        "level": "DEBUG",
                        "handlers": skill_handlers,
                        "propagate": False
                    },
                    # core.tools.external The skill generation related modules under are also output to skill_workshop.log
                    "core.tools.external": {
                        "level": "DEBUG",
                        "handlers": skill_handlers,
                        "propagate": False
                    },
                    "fontTools": {
                        "level": "WARNING",
                        "handlers": main_handlers,
                        "propagate": False
                    },
                    "fontTools.subset": {
                        "level": "WARNING",
                        "handlers": main_handlers,
                        "propagate": False
                    },
                },
                "root": {"level": level, "handlers": main_handlers},
            }

            if verbose_setup:
                print(f"🔍 [setup_logging] Final handlers configuration: {list(handlers_config.keys())}")
                print(f"🔍 [setup_logging] Start applying dictConfig")

            logging.config.dictConfig(logging_config)

            if verbose_setup:
                print(f"✅ [setup_logging] dictConfig Application successful")

            logging.getLogger("webapi").info(f"Logging configured from {cfg_path}")

            # Test whether the main log file is writable
            if main_enabled:
                test_logger = logging.getLogger("tradingagents")
                test_logger.info(f"🔍 Test main log file writing: {main_log}")
                if verbose_setup:
                    print(f"🔍 [setup_logging] Test log written to tradingagents logger")

            return
    except Exception as e:
        # TOML Exists but fails to load, falling back to default configuration
        if verbose_setup:
            print(f"⚠️ [setup_logging] TOML Configuration load failed: {e}, Use default configuration")
        logging.getLogger("webapi").warning(f"Failed to load logging.toml, fallback to defaults: {e}")

    # 2) Default built-in configuration (consistent with the original)
    if verbose_setup:
        print(f"✅ [setup_logging] Use built-in default configuration")
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 🔥 Select a log handler class (Windows uses ConcurrentRotatingFileHandler)
    handler_class = "concurrent_log_handler.ConcurrentRotatingFileHandler" if _USE_CONCURRENT_HANDLER else "logging.handlers.RotatingFileHandler"

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": _build_common_filters(),
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s trace=%(trace_id)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s trace=%(trace_id)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": log_level,
                "filters": ["request_context"],
                "stream": sys.stdout,
            },
            "file": {
                "class": handler_class,
                "formatter": "detailed",
                "level": "DEBUG",
                "filters": ["request_context"],
                "filename": "logs/webapi.log",
                "maxBytes": 10485760,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "worker_file": {
                "class": handler_class,
                "formatter": "detailed",
                "level": "DEBUG",
                "filters": ["request_context"],
                "filename": "logs/worker.log",
                "maxBytes": 10485760,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "error_file": {
                "class": handler_class,
                "formatter": "detailed",
                "level": "WARNING",
                "filters": _error_handler_filters(),
                "filename": "logs/error.log",
                "maxBytes": 10485760,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "skill_file": {
                "class": handler_class,
                "formatter": "detailed",
                "level": "DEBUG",
                "filters": ["request_context"],
                "filename": "logs/skill_workshop.log",
                "maxBytes": 20971520,
                "backupCount": 10,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "webapi": {"level": "INFO", "handlers": ["console", "file", "error_file"], "propagate": True},
            "worker": {"level": "DEBUG", "handlers": ["console", "worker_file", "error_file"], "propagate": False},
            "uvicorn": {"level": "INFO", "handlers": ["console", "file", "error_file"], "propagate": False},
            "fastapi": {"level": "INFO", "handlers": ["console", "file", "error_file"], "propagate": False},
            "app": {"level": "INFO", "handlers": ["console", "file", "error_file"], "propagate": False},
            "core": {"level": "INFO", "handlers": ["console", "file", "error_file"], "propagate": False},
            "skill_workshop": {"level": "DEBUG", "handlers": ["console", "skill_file", "error_file"], "propagate": False},
            "core.tools.external": {"level": "DEBUG", "handlers": ["console", "skill_file", "error_file"], "propagate": False},
            "fontTools": {"level": "WARNING", "handlers": ["console", "file", "error_file"], "propagate": False},
            "fontTools.subset": {"level": "WARNING", "handlers": ["console", "file", "error_file"], "propagate": False},
        },
        "root": {"level": log_level, "handlers": ["console"]},
    }

    logging.config.dictConfig(logging_config)
    logging.getLogger("webapi").info("Logging configured successfully (built-in)")
"""
Log export service
Provides log file query, filtering and export functions
"""

import logging
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import re
import json

logger = logging.getLogger("webapi")


class LogExportService:
    """日志导出服务"""

    def __init__(self, log_dir: str = "./logs"):
        """
        Initialize log export service

        Args:
            log_dir: Log file directory
        """
        self.log_dir = Path(log_dir)
        logger.info(f"🔍 [LogExportService] Initialize log export service")
        logger.info(f"🔍 [LogExportService] Configured log directory: {log_dir}")
        logger.info(f"🔍 [LogExportService] Parsed log directory: {self.log_dir}")
        logger.info(f"🔍 [LogExportService] absolute path: {self.log_dir.absolute()}")
        logger.info(f"🔍 [LogExportService] Does the directory exist?: {self.log_dir.exists()}")

        if not self.log_dir.exists():
            logger.warning(f"⚠️ [LogExportService] Log directory does not exist: {self.log_dir}")
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"✅ [LogExportService] Log directory created: {self.log_dir}")
            except Exception as e:
                logger.error(f"❌ [LogExportService] Failed to create log directory: {e}")
        else:
            logger.info(f"✅ [LogExportService] Log directory exists")

    def list_log_files(self) -> List[Dict[str, Any]]:
        """
        List all log files

        Returns:
            Log file list, including file name, size, modification time and other information
        """
        log_files = []

        try:
            logger.info(f"🔍 [list_log_files] Start listing log files")
            logger.info(f"🔍 [list_log_files] Search catalog: {self.log_dir}")
            logger.info(f"🔍 [list_log_files] absolute path: {self.log_dir.absolute()}")
            logger.info(f"🔍 [list_log_files] Does the directory exist?: {self.log_dir.exists()}")
            logger.info(f"🔍 [list_log_files] Is it a directory?: {self.log_dir.is_dir()}")

            if not self.log_dir.exists():
                logger.error(f"❌ [list_log_files] Log directory does not exist: {self.log_dir}")
                return []

            if not self.log_dir.is_dir():
                logger.error(f"❌ [list_log_files] path is not a directory: {self.log_dir}")
                return []

            # List all files in a directory (for debugging)
            try:
                all_items = list(self.log_dir.iterdir())
                logger.info(f"🔍 [list_log_files] 目录中共有 {len(all_items)} 个项目")
                for item in all_items[:10]:  # Only show the first 10
                    logger.info(f"🔍 [list_log_files]   - {item.name} (is_file: {item.is_file()})")
            except Exception as e:
                logger.error(f"❌ [list_log_files] Failed to list directory contents: {e}")

            # Search log files
            logger.info(f"🔍 [list_log_files] Search mode: *.log*")
            for file_path in self.log_dir.glob("*.log*"):
                logger.info(f"🔍 [list_log_files] find file: {file_path.name}")
                if file_path.is_file():
                    stat = file_path.stat()
                    log_file_info = {
                        "name": file_path.name,
                        "path": str(file_path),
                        "size": stat.st_size,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type": self._get_log_type(file_path.name)
                    }
                    log_files.append(log_file_info)
                    logger.info(f"✅ [list_log_files] Add log file: {file_path.name} ({log_file_info['size_mb']} MB)")
                else:
                    logger.warning(f"⚠️ [list_log_files] Skip non-file items: {file_path.name}")

            # Sort by modification time in descending order
            log_files.sort(key=lambda x: x["modified_at"], reverse=True)

            logger.info(f"📋 [list_log_files] 最终找到 {len(log_files)} 个日志文件")
            return log_files

        except Exception as e:
            logger.error(f"❌ [list_log_files] Failed to list log files: {e}", exc_info=True)
            return []

    def _get_log_type(self, filename: str) -> str:
        """
        Determine log type based on file name
        
        Args:
            filename: file name
            
        Returns:
            Log type
        """
        if "error" in filename.lower():
            return "error"
        elif "webapi" in filename.lower():
            return "webapi"
        elif "worker" in filename.lower():
            return "worker"
        elif "access" in filename.lower():
            return "access"
        else:
            return "other"

    def read_log_file(
        self,
        filename: str,
        lines: int = 1000,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Read log file content (supports filtering)
        
        Args:
            filename: Log file name
            lines: Number of lines read (starting from the end)
            level: Log level filtering (ERROR, WARNING, INFO, DEBUG) 
            keyword: keyword filter
            start_time: Start time (ISO format)
            end_time: End time (ISO format)
            
        Returns:
            Log content and statistics
        """
        file_path = self.log_dir / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {filename}")
        
        try:
            # Read file contents
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            
            # Read the specified number of lines starting from the end
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            # Apply filter
            filtered_lines = []
            stats = {
                "total_lines": len(all_lines),
                "filtered_lines": 0,
                "error_count": 0,
                "warning_count": 0,
                "info_count": 0,
                "debug_count": 0
            }
            
            for line in recent_lines:
                # Statistics log level
                if "ERROR" in line:
                    stats["error_count"] += 1
                elif "WARNING" in line:
                    stats["warning_count"] += 1
                elif "INFO" in line:
                    stats["info_count"] += 1
                elif "DEBUG" in line:
                    stats["debug_count"] += 1
                
                # Apply filters
                if level and level.upper() not in line:
                    continue
                
                if keyword and keyword.lower() not in line.lower():
                    continue
                
                # Time filtering (simple implementation, assuming the log format is YYYY-MM-DD HH:MM:SS) 
                if start_time or end_time:
                    time_match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', line)
                    if time_match:
                        log_time = time_match.group()
                        if start_time and log_time < start_time:
                            continue
                        if end_time and log_time > end_time:
                            continue
                
                filtered_lines.append(line.rstrip())
            
            stats["filtered_lines"] = len(filtered_lines)
            
            return {
                "filename": filename,
                "lines": filtered_lines,
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"❌ 读取日志文件失败: {e}")
            raise

    def export_logs(
        self,
        filenames: Optional[List[str]] = None,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        format: str = "zip"
    ) -> str:
        """
        Export log file
        
        Args:
            filenames: List of log file names to be exported (None means exporting all)
            level: Log level filtering
            start_time: start time
            end_time: end time
            format: Export format (zip, txt) 
            
        Returns:
            Path to exported file
        """
        try:
            # Determine which files to export
            if filenames:
                files_to_export = [self.log_dir / f for f in filenames if (self.log_dir / f).exists()]
            else:
                files_to_export = list(self.log_dir.glob("*.log*"))
            
            if not files_to_export:
                raise ValueError("没有找到要导出的日志文件")
            
            # Create export directory
            export_dir = Path("./exports/logs")
            export_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate export file name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if format == "zip":
                export_path = export_dir / f"logs_export_{timestamp}.zip"
                
                # Create ZIP file
                with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in files_to_export:
                        # If there are filter conditions, filter first and then add
                        if level or start_time or end_time:
                            filtered_data = self.read_log_file(
                                file_path.name,
                                lines=999999,  # read all lines
                                level=level,
                                start_time=start_time,
                                end_time=end_time
                            )
                            # Write filtered content to temporary file
                            temp_file = export_dir / f"temp_{file_path.name}"
                            with open(temp_file, 'w', encoding='utf-8') as f:
                                f.write('\n'.join(filtered_data['lines']))
                            zipf.write(temp_file, file_path.name)
                            temp_file.unlink()  # Delete temporary files
                        else:
                            zipf.write(file_path, file_path.name)
                
                logger.info(f"✅ 日志导出成功: {export_path}")
                return str(export_path)
            
            elif format == "txt":
                export_path = export_dir / f"logs_export_{timestamp}.txt"
                
                # Merge all logs into one text file
                with open(export_path, 'w', encoding='utf-8') as outf:
                    for file_path in files_to_export:
                        outf.write(f"\n{'='*80}\n")
                        outf.write(f"文件: {file_path.name}\n")
                        outf.write(f"{'='*80}\n\n")
                        
                        if level or start_time or end_time:
                            filtered_data = self.read_log_file(
                                file_path.name,
                                lines=999999,
                                level=level,
                                start_time=start_time,
                                end_time=end_time
                            )
                            outf.write('\n'.join(filtered_data['lines']))
                        else:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as inf:
                                outf.write(inf.read())
                        
                        outf.write('\n\n')
                
                logger.info(f"✅ 日志导出成功: {export_path}")
                return str(export_path)
            
            else:
                raise ValueError(f"不支持的导出格式: {format}")
                
        except Exception as e:
            logger.error(f"❌ 导出日志失败: {e}")
            raise

    def get_log_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get log statistics
        
        Args:
            days: Statistics of logs in recent days
            
        Returns:
            Log statistics
        """
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            stats = {
                "total_files": 0,
                "total_size_mb": 0,
                "error_files": 0,
                "recent_errors": [],
                "log_types": {}
            }
            
            for file_path in self.log_dir.glob("*.log*"):
                if not file_path.is_file():
                    continue
                
                stat = file_path.stat()
                modified_time = datetime.fromtimestamp(stat.st_mtime)
                
                if modified_time < cutoff_time:
                    continue
                
                stats["total_files"] += 1
                stats["total_size_mb"] += stat.st_size / (1024 * 1024)
                
                log_type = self._get_log_type(file_path.name)
                stats["log_types"][log_type] = stats["log_types"].get(log_type, 0) + 1
                
                # Statistics error log
                if log_type == "error":
                    stats["error_files"] += 1
                    # Read recent errors
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                            error_lines = [line for line in lines[-100:] if "ERROR" in line]
                            stats["recent_errors"].extend(error_lines[-10:])
                    except Exception:
                        pass
            
            stats["total_size_mb"] = round(stats["total_size_mb"], 2)
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ 获取日志统计失败: {e}")
            return {}


# Global service instance
_log_export_service: Optional[LogExportService] = None


def get_log_export_service() -> LogExportService:
    """获取日志导出服务实例"""
    global _log_export_service

    if _log_export_service is None:
        # Get the log directory from the log configuration
        log_dir = _get_log_directory()
        _log_export_service = LogExportService(log_dir=log_dir)

    return _log_export_service


def _get_log_directory() -> str:
    """
    Get log directory path
    Priority:
    1. Read from the log configuration file (supports Docker environment)
    2. Read from settings configuration
    3. Use default value ./logs
    """
    import os
    from pathlib import Path

    try:
        logger.info(f"🔍 [_get_log_directory] Start getting the log directory")

        # Check if it is a Docker environment
        docker_env = os.environ.get("DOCKER", "")
        dockerenv_exists = Path("/.dockerenv").exists()
        is_docker = docker_env.lower() in {"1", "true", "yes"} or dockerenv_exists

        logger.info(f"🔍 [_get_log_directory] DOCKER environment variables: {docker_env}")
        logger.info(f"🔍 [_get_log_directory] /.dockerenv exist: {dockerenv_exists}")
        logger.info(f"🔍 [_get_log_directory] Determined to be a Docker environment: {is_docker}")

        # Try reading from log configuration file
        try:
            import tomllib as toml_loader
            logger.info(f"🔍 [_get_log_directory] Load using tomllib TOML")
        except ImportError:
            try:
                import tomli as toml_loader
                logger.info(f"🔍 [_get_log_directory] Load using tomli TOML")
            except ImportError:
                toml_loader = None
                logger.warning(f"⚠️ [_get_log_directory] Unable to import TOML loader")

        if toml_loader:
            # Choose a configuration file based on your environment
            profile = os.environ.get("LOGGING_PROFILE", "")
            logger.info(f"🔍 [_get_log_directory] LOGGING_PROFILE: {profile}")

            cfg_path = Path("config/logging_docker.toml") if profile.lower() == "docker" or is_docker else Path("config/logging.toml")
            logger.info(f"🔍 [_get_log_directory] Select profile: {cfg_path}")
            logger.info(f"🔍 [_get_log_directory] Configuration file exists: {cfg_path.exists()}")

            if cfg_path.exists():
                try:
                    with cfg_path.open("rb") as f:
                        toml_data = toml_loader.load(f)

                    logger.info(f"🔍 [_get_log_directory] Configuration file loaded successfully")

                    # Read log directory from configuration file
                    handlers_cfg = toml_data.get("logging", {}).get("handlers", {})
                    file_handler_cfg = handlers_cfg.get("file", {})
                    log_dir = file_handler_cfg.get("directory")

                    logger.info(f"🔍 [_get_log_directory] Log directory in configuration file: {log_dir}")

                    if log_dir:
                        logger.info(f"✅ [_get_log_directory] Read the log directory from the log configuration file: {log_dir}")
                        return log_dir
                except Exception as e:
                    logger.warning(f"⚠️ [_get_log_directory] Failed to read log configuration file: {e}", exc_info=True)

        # Fall back to settings configuration
        try:
            from app.core.config import settings
            log_dir = settings.log_dir
            logger.info(f"🔍 [_get_log_directory] settings.log_dir: {log_dir}")
            if log_dir:
                logger.info(f"✅ [_get_log_directory] Read the log directory from settings: {log_dir}")
                return log_dir
        except Exception as e:
            logger.warning(f"⚠️ [_get_log_directory] Failed to read log directory from settings: {e}", exc_info=True)

        # Docker The environment uses by default /app/logs
        if is_docker:
            logger.info("✅ [_get_log_directory] Docker environment, use the default log directory: /app/logs")
            return "/app/logs"

        # Used by default in non-Docker environments ./logs
        logger.info("✅ [_get_log_directory] Use default log directory: ./logs")
        return "./logs"

    except Exception as e:
        logger.error(f"❌ [_get_log_directory] Failed to obtain log directory: {e}, Use default value ./logs", exc_info=True)
        return "./logs"


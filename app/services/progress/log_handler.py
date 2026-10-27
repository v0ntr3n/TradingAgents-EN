"""
Progress log handler
Monitor the log output of TradingAgents and automatically update the progress tracker
"""

import logging
import re
import threading
from typing import Dict, Optional
from .tracker import RedisProgressTracker

logger = logging.getLogger("app.services.progress_log_handler")


class ProgressLogHandler(logging.Handler):
    """Progress log processor, monitors TradingAgents logs and updates progress"""

    def __init__(self):
        super().__init__()
        self._trackers: Dict[str, RedisProgressTracker] = {}
        self._lock = threading.Lock()

        # log pattern matching
        self.progress_patterns = {
            # basic stage
            r"Verify.*Stock code|Check.*data source": "📋 准备阶段",
            r"Check.*API.*key|environment.*Configuration": "🔧 环境检查",
            r"Estimate.*cost|cost.*Estimate": "💰 成本估算",
            r"Configuration.*parameters|parameters.*settings": "⚙️ 参数设置",
            r"initialization.*engine|start.*engine": "🚀 启动引擎",

            # analyst stage
            r"market analyst.*start|start.*market analysis|market.*data.*analysis": "📊 市场分析师正在分析",
            r"fundamental analyst.*start|start.*fundamental analysis|Finance.*data.*analysis": "💼 基本面分析师正在分析",
            r"news analyst.*start|start.*news analysis|News.*data.*analysis": "📰 新闻分析师正在分析",
            r"social media analyst.*start|start.*social media analysis|emotions.*analysis": "💬 Social media analysts are analyzing",

            # research team stage
            r"bullish researcher|multi-investigator|bull.*researcher|Positive Evidence Researcher": "🐂 Active evidence researcher constructs argument",
            r"bearish researcher|short researcher|bear.*researcher|cautious evidence researcher": "🐻 Cautious Evidence Researchers Identify Risks",
            r"Research.*Debate|Debate.*start|debate.*start|multi-scenario research": "🎯 多情景研究进行中",
            r"research manager|research.*manager|research integrator": "👔 研究整合员汇总",

            # Research integration stage
            r"trader.*decision making|trader.*decision|formulate.*trading strategy|research integrator.*Summary|research integration.*opinion": "🧩 研究整合员汇总",

            # risk management stage
            r"Radical.*risk|risky.*risk|high elasticity scenario": "🔥 高弹性情景研究",
            r"conservative.*risk|conservative.*risk|defense scenario": "🛡️ 防御情景研究",
            r"Neutral.*risk|neutral.*risk|Baseline scenario": "⚖️ 基准情景研究",
            r"risk manager|risk.*manager|risk assessor": "🎯 风险评估师形成结论",

            # final stage
            r"signal processing|signal.*process|Result processing": "📡 结果处理",
            r"generate.*report|report.*generat": "📊 生成研究报告",
            r"analysis.*Complete|analysis.*complet": "✅ 研究完成",
        }

        logger.info("📊 [progress log] Log processor initialization completed")

    def register_tracker(self, task_id: str, tracker: RedisProgressTracker):
        """注册进度跟踪器"""
        with self._lock:
            self._trackers[task_id] = tracker
            logger.info(f"📊 [progress log] Register tracker: {task_id}")

    def unregister_tracker(self, task_id: str):
        """注销进度跟踪器"""
        with self._lock:
            if task_id in self._trackers:
                del self._trackers[task_id]
                logger.info(f"📊 [progress log] Unregister tracker: {task_id}")

    def emit(self, record):
        """处理日志记录"""
        try:
            message = record.getMessage()

            # Check if it is a log message we care about
            progress_message = self._extract_progress_message(message)
            if not progress_message:
                return

            # Find matching trackers (reduce lock holding time)
            trackers_copy = {}
            with self._lock:
                trackers_copy = self._trackers.copy()

            # Handle tracker updates outside of lock
            for task_id, tracker in trackers_copy.items():
                try:
                    # Check tracker status
                    if hasattr(tracker, 'progress_data') and tracker.progress_data.get('status') == 'running':
                        tracker.update_progress(progress_message)
                        logger.debug(f"📊 [progress log] update progress: {task_id} -> {progress_message}")
                        break  # Only update the first matching tracker
                except Exception as e:
                    logger.warning(f"📊 [progress log] Update failed: {task_id} - {e}")

        except Exception as e:
            # Do not let errors in the log processor affect the main program
            logger.error(f"📊 [progress log] Log processing error: {e}")

    def _extract_progress_message(self, message: str) -> Optional[str]:
        """从日志消息中提取进度信息"""
        message_lower = message.lower()

        # Check whether progress-related keywords are included
        progress_keywords = [
            "开始", "完成", "分析", "处理", "执行", "生成",
            "start", "complete", "analysis", "process", "execute", "generate"
        ]

        if not any(keyword in message_lower for keyword in progress_keywords):
            return None

        # Match specific progress patterns
        for pattern, progress_msg in self.progress_patterns.items():
            if re.search(pattern, message_lower):
                return progress_msg

        return None

    def _extract_stock_symbol(self, message: str) -> Optional[str]:
        """从消息中提取股票代码"""
        # Matches common ticker formats
        patterns = [
            r'\b(\d{6})\b',  # 6 Digits (A shares)
            r'\b([A-Z]{1,5})\b',  # 1-5 uppercase letters (U.S. stocks)
            r'\b(\d{4,5}\.HK)\b',  # Hong Kong stock format
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)

        return None


# Global log handler instance
_progress_log_handler = None
_handler_lock = threading.Lock()


def get_progress_log_handler() -> ProgressLogHandler:
    """Get the global progress log processor instance"""
    global _progress_log_handler

    with _handler_lock:
        if _progress_log_handler is None:
            _progress_log_handler = ProgressLogHandler()

            # Add handler to relevant logger
            loggers_to_monitor = [
                "agents",
                "tradingagents",
                "agents.analysts",
                "agents.researchers",
                "agents.traders",
                "agents.managers",
                "agents.risk_mgmt",
            ]

            for logger_name in loggers_to_monitor:
                target_logger = logging.getLogger(logger_name)
                target_logger.addHandler(_progress_log_handler)
                target_logger.setLevel(logging.INFO)

            logger.info(f"📊 [进度日志] 已注册到 {len(loggers_to_monitor)} 个日志记录器")

    return _progress_log_handler


def register_analysis_tracker(task_id: str, tracker: RedisProgressTracker):
    """注册分析跟踪器到日志监控"""
    handler = get_progress_log_handler()
    handler.register_tracker(task_id, tracker)


def unregister_analysis_tracker(task_id: str):
    """Unregister an analytics tracker from log monitoring"""
    handler = get_progress_log_handler()
    handler.unregister_tracker(task_id)


"""
Progress Tracker (Transition Period)
- Temporarily import the RedisProgressTracker class from the old module
- Provide implementation of get_progress_by_id in this module (consistent with old implementation, correct cls reference)
"""
from typing import Any, Dict, Optional, List
import json
import os
import logging
import time



logger = logging.getLogger("app.services.progress.tracker")

from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class AnalysisStep:
    """分析步骤数据类"""
    name: str
    description: str
    status: str = "pending"  # pending, current, completed, failed
    weight: float = 0.1  # Weight, used to calculate progress
    start_time: Optional[float] = None
    end_time: Optional[float] = None


def safe_serialize(data):
    """Safe serialization, handling non-serializable objects"""
    if isinstance(data, dict):
        return {k: safe_serialize(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [safe_serialize(item) for item in data]
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    elif hasattr(data, '__dict__'):
        return safe_serialize(data.__dict__)
    else:
        return str(data)



class RedisProgressTracker:
    """Redis进度跟踪器"""

    def __init__(self, task_id: str, analysts: List[str], research_depth: str, llm_provider: str):
        self.task_id = task_id
        self.analysts = analysts
        self.research_depth = research_depth
        self.llm_provider = llm_provider

        # Redis connect
        self.redis_client = None
        self.use_redis = self._init_redis()

        # progress data
        self.progress_data = {
            'task_id': task_id,
            'status': 'running',
            'progress_percentage': 0.0,
            'current_step': 0,  # Current step index (number)
            'total_steps': 0,
            'current_step_name': '初始化',
            'current_step_description': '准备开始分析',
            'last_message': '分析任务已启动',
            'start_time': time.time(),
            'last_update': time.time(),
            'elapsed_time': 0.0,
            'remaining_time': 0.0,
            'steps': []
        }

        # Generate analysis steps
        self.analysis_steps = self._generate_dynamic_steps()
        self.progress_data['total_steps'] = len(self.analysis_steps)
        self.progress_data['steps'] = [asdict(step) for step in self.analysis_steps]

        # 🔧 Calculate and set estimated total duration
        base_total_time = self._get_base_total_time()
        self.progress_data['estimated_total_time'] = base_total_time
        self.progress_data['remaining_time'] = base_total_time  # initial remaining time = total duration

        # Save initial state
        self._save_progress()

        logger.info(f"📊 [Redis进度] 初始化完成: {task_id}, 步骤数: {len(self.analysis_steps)}")

    def _init_redis(self) -> bool:
        """初始化Redis连接"""
        try:
            # Check the REDIS_ENABLED environment variable
            redis_enabled = os.getenv('REDIS_ENABLED', 'false').lower() == 'true'
            if not redis_enabled:
                logger.info(f"📊 [Redis Progress] Redis Not enabled, uses file storage")
                return False

            import redis

            # Get Redis configuration from environment variables
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', 6379))
            redis_password = os.getenv('REDIS_PASSWORD', None)
            redis_db = int(os.getenv('REDIS_DB', 0))

            # Create a Redis connection
            if redis_password:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    password=redis_password,
                    db=redis_db,
                    decode_responses=True
                )
            else:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True
                )

            # test connection
            self.redis_client.ping()
            logger.info(f"📊 [Redis Progress] Redis Connection successful: {redis_host}:{redis_port}")
            return True
        except Exception as e:
            logger.warning(f"📊 [Redis Progress] Redis Connection failed, using file storage: {e}")
            return False

    def _generate_dynamic_steps(self) -> List[AnalysisStep]:
        """Dynamically generate analysis steps based on number of analysts and depth of research"""
        steps: List[AnalysisStep] = []
        # 1) Basic preparation stage (10%)
        steps.extend([
            AnalysisStep("📋 准备阶段", "Verify stock ticker, check data source availability", "pending", 0.03),
            AnalysisStep("🔧 环境检查", "Check the API key configuration to ensure data acquisition is normal", "pending", 0.02),
            AnalysisStep("💰 成本估算", "Estimate API call costs based on depth of analysis", "pending", 0.01),
            AnalysisStep("⚙️ 参数设置", "Configure analysis parameters and AI model selection", "pending", 0.02),
            AnalysisStep("🚀 启动引擎", "Initialize the AI analysis engine and prepare to start analysis", "pending", 0.02),
        ])
        # 2) Analyst team stage (35%) - Parallel
        analyst_weight = 0.35 / max(len(self.analysts), 1)
        for analyst in self.analysts:
            info = self._get_analyst_step_info(analyst)
            steps.append(AnalysisStep(info["name"], info["description"], "pending", analyst_weight))
        # 3) Research team debate stage (25%)
        rounds = self._get_debate_rounds()
        debate_weight = 0.25 / (3 + rounds)
        steps.extend([
            AnalysisStep("🐂 积极证据研究员", "Research evidence for constructing optimistic interpretations based on analyst reports", "pending", debate_weight),
            AnalysisStep("🐻 谨慎证据研究员", "Research evidence for constructing cautious interpretations based on analyst reports", "pending", debate_weight),
        ])
        for i in range(rounds):
            steps.append(AnalysisStep(f"🎯 多情景研究 第{i+1}轮", "多情景研究视角深度对比", "pending", debate_weight))
        steps.append(AnalysisStep("👔 研究整合员", "Comprehensive multi-scenario research to form a summary of research observations", "pending", debate_weight))
        # 4) Research integration stage (8%)
        steps.append(AnalysisStep("🧩 研究整合员汇总", "Organize research integration opinions and observation lists based on research results", "pending", 0.08))
        # 5) risk management team stage (15%)
        risk_weight = 0.15 / 4
        steps.extend([
            AnalysisStep("🔥 高弹性情景研究", "Study the potential revenue space from the perspective of highly elastic scenarios", "pending", risk_weight),
            AnalysisStep("🛡️ 防御情景研究", "Studying capital protection factors from the perspective of defense scenarios", "pending", risk_weight),
            AnalysisStep("⚖️ 基准情景研究", "Balancing multiple research perspectives from a baseline scenario perspective", "pending", risk_weight),
            AnalysisStep("🎯 风险评估师", "Comprehensive risk research and observation to form risk review conclusions", "pending", risk_weight),
        ])
        # 6) Final research conclusion stage (7%)
        steps.extend([
            AnalysisStep("📡 结果处理", "Collate all research observations and generate research reports", "pending", 0.04),
            AnalysisStep("📊 生成报告", "Organize analysis results and generate complete reports", "pending", 0.03),
        ])
        return steps

    def _get_debate_rounds(self) -> int:
        """根据研究深度获取辩论轮次"""
        if self.research_depth == "快速":
            return 1
        if self.research_depth == "标准":
            return 2
        return 3

    def _get_analyst_step_info(self, analyst: str) -> Dict[str, str]:
        """Get analyst step information (name and description)"""
        mapping = {
            'market': {"name": "📊 市场分析师", "description": "Analyze market performance such as stock price trends, trading volume, and technical indicators"},
            'fundamentals': {"name": "💼 基本面分析师", "description": "Analyze the company s financial status, profitability, growth and other fundamentals"},
            'news': {"name": "📰 新闻分析师", "description": "Analyze the impact of relevant news, announcements, and industry trends on stock prices"},
            'social': {"name": "💬 社交媒体分析师", "description": "Analyze social media discussions, Internet popularity, retail investor sentiment, etc."},
        }
        return mapping.get(analyst, {"name": f"🔍 {analyst}分析师", "description": f"进行{analyst}相关的专业分析"})

    def _estimate_step_time(self, step: AnalysisStep) -> float:
        """估算步骤执行时间（秒）"""
        return self._get_base_total_time() * step.weight

    def _get_base_total_time(self) -> float:
        """
        Estimated total time (seconds) based on number of analysts, research depth, and model type

        Algorithm design ideas (based on actual test data):
        1. Actual measurement: Level 4 depth + 3 analysts = 11 minutes (661 seconds)
        2. Actual measurement: Level 1 fast = 4-5 minutes
        3. Actual test: Level 2 basics = 5-6 minutes
        4. There is parallel processing between analysts, not linear superposition
        """

        # 🔧 Supports 5 levels of analysis depth
        depth_map = {
            "快速": 1,  # 1 Level - Quick Analysis
            "基础": 2,  # 2 Level - Basic Analysis
            "标准": 3,  # 3 Level - Standard Analysis (recommended)
            "深度": 4,  # 4 Level - In-Depth Analysis
            "全面": 5   # 5 Level - Comprehensive Analysis
        }
        d = depth_map.get(self.research_depth, 3)  # Default standard analysis

        # 📊 Base time (seconds) based on actual test data
        # This is the basic time spent by a single analyst
        base_time_per_depth = {
            1: 150,  # 1 Level: 2.5 minutes (the actual measurement is 4-5 minutes for multiple analysts)
            2: 180,  # 2 Level: 3 minutes (the actual measurement is 5-6 minutes for multiple analysts)
            3: 240,  # 3 Level: 4 minutes (front-end display: 6-10 minutes)
            4: 330,  # 4 Level: 5.5 minutes (actual measurement: 11 minutes for 3 analysts, about 5.5 minutes for a single backend)
            5: 480   # 5 Level: 8 minutes (front-end display: 15-25 minutes)
        }.get(d, 240)

        # 📈 Impact coefficient of number of analysts (based on actual test data)
        # Actual measurement: Level 4 + 3 analysts = 11 minutes = 660 seconds
        # Reverse push: 330 seconds * multiplier = 660 seconds => multiplier = 2.0
        analyst_count = len(self.analysts)
        if analyst_count == 1:
            analyst_multiplier = 1.0
        elif analyst_count == 2:
            analyst_multiplier = 1.5  # 2 Analysts take about 1.5 times the time
        elif analyst_count == 3:
            analyst_multiplier = 2.0  # 3 It takes about 2 times as long for an analyst (verified by actual measurement)
        elif analyst_count == 4:
            analyst_multiplier = 2.4  # 4 Analysts spend about 2.4 times longer
        else:
            analyst_multiplier = 2.4 + (analyst_count - 4) * 0.3  # Each additional analyst increases 30%

        # 🚀 Model speed impact (based on actual testing)
        model_mult = {
            'dashscope': 1.0,  # Ali Bailian speed is moderate
            'deepseek': 0.8,   # DeepSeek faster
            'google': 1.2      # Google slower
        }.get(self.llm_provider, 1.0)

        # Calculate total time
        total_time = base_time_per_depth * analyst_multiplier * model_mult

        return total_time

    def _calculate_time_estimates(self) -> tuple[float, float, float]:
        """Return (elapsed, remaining, estimated_total)"""
        now = time.time()
        start = self.progress_data.get('start_time', now)
        elapsed = now - start
        pct = self.progress_data.get('progress_percentage', 0)
        base_total = self._get_base_total_time()

        if pct >= 100:
            # Task completed
            est_total = elapsed
            remaining = 0
        else:
            # Estimated total duration of use (fixed value)
            est_total = base_total
            # Estimated remaining = Estimated total time - elapsed time
            remaining = max(0, est_total - elapsed)

        return elapsed, remaining, est_total

    @staticmethod
    def _calculate_static_time_estimates(progress_data: dict) -> dict:
        """Static: Calculate time estimates for existing progress data"""
        if 'start_time' not in progress_data or not progress_data['start_time']:
            return progress_data
        now = time.time()
        elapsed = now - progress_data['start_time']
        progress_data['elapsed_time'] = elapsed
        pct = progress_data.get('progress_percentage', 0)

        if pct >= 100:
            # Task completed
            est_total = elapsed
            remaining = 0
        else:
            # Use estimated total duration (fixed value), or default if not available
            est_total = progress_data.get('estimated_total_time', 300)
            # Estimated remaining = Estimated total time - elapsed time
            remaining = max(0, est_total - elapsed)

        progress_data['estimated_total_time'] = est_total
        progress_data['remaining_time'] = remaining
        return progress_data

    def update_progress(self, progress_update: Any) -> Dict[str, Any]:
        """update progress and persist; accepts dict or plain message string"""
        try:
            if isinstance(progress_update, dict):
                self.progress_data.update(progress_update)
            elif isinstance(progress_update, str):
                self.progress_data['last_message'] = progress_update
                self.progress_data['last_update'] = time.time()
            else:
                # try to coerce iterable of pairs; otherwise fallback to string
                try:
                    self.progress_data.update(dict(progress_update))
                except Exception:
                    self.progress_data['last_message'] = str(progress_update)
                    self.progress_data['last_update'] = time.time()

            # Automatically update step status based on progress percentage
            progress_pct = self.progress_data.get('progress_percentage', 0)
            self._update_steps_by_progress(progress_pct)

            # Get current step index
            current_step_index = self._detect_current_step()
            self.progress_data['current_step'] = current_step_index

            # 🔑 Key: Automatically set only if progress_update does not provide current_step_name
            # This allows the step names provided by the workflow engine to take precedence
            if isinstance(progress_update, dict):
                has_step_name = 'current_step_name' in progress_update
                has_step_desc = 'current_step_description' in progress_update
            else:
                has_step_name = False
                has_step_desc = False

            # Update the name and description of the current step (if not provided manually)
            if 0 <= current_step_index < len(self.analysis_steps):
                current_step_obj = self.analysis_steps[current_step_index]
                if not has_step_name:
                    self.progress_data['current_step_name'] = current_step_obj.name
                if not has_step_desc:
                    self.progress_data['current_step_description'] = current_step_obj.description

            elapsed, remaining, est_total = self._calculate_time_estimates()
            self.progress_data['elapsed_time'] = elapsed
            self.progress_data['remaining_time'] = remaining
            self.progress_data['estimated_total_time'] = est_total

            # Update progress_data in steps
            self.progress_data['steps'] = [asdict(step) for step in self.analysis_steps]

            self._save_progress()
            logger.debug(f"[RedisProgress] updated: {self.task_id} - {self.progress_data.get('progress_percentage', 0)}%")
            return self.progress_data
        except Exception as e:
            logger.error(f"[RedisProgress] update failed: {self.task_id} - {e}")
            return self.progress_data

    def _update_steps_by_progress(self, progress_pct: float) -> None:
        """Automatically update step status based on progress percentage"""
        try:
            cumulative_weight = 0.0
            current_time = time.time()

            for step in self.analysis_steps:
                step_start_pct = cumulative_weight
                step_end_pct = cumulative_weight + (step.weight * 100)

                if progress_pct >= step_end_pct:
                    # Completed steps
                    if step.status != 'completed':
                        step.status = 'completed'
                        step.end_time = current_time
                elif progress_pct > step_start_pct:
                    # Steps currently being performed
                    if step.status != 'current':
                        step.status = 'current'
                        step.start_time = current_time
                else:
                    # steps not yet started
                    if step.status not in ('pending', 'failed'):
                        step.status = 'pending'

                cumulative_weight = step_end_pct
        except Exception as e:
            logger.debug(f"[RedisProgress] update steps by progress failed: {e}")

    def _detect_current_step(self) -> int:
        """detect current step index by status"""
        try:
            # The priority search status is 'current' steps
            for index, step in enumerate(self.analysis_steps):
                if step.status == 'current':
                    return index
            # if not 'current', Find the first 'pending' steps
            for index, step in enumerate(self.analysis_steps):
                if step.status == 'pending':
                    return index
            # If all are completed, return the index of the last step
            for index, step in enumerate(reversed(self.analysis_steps)):
                if step.status == 'completed':
                    return len(self.analysis_steps) - 1 - index
            return 0
        except Exception as e:
            logger.debug(f"[RedisProgress] detect current step failed: {e}")
            return 0

    def _find_step_by_name(self, step_name: str) -> Optional[AnalysisStep]:
        for step in self.analysis_steps:
            if step.name == step_name:
                return step
        return None

    def _find_step_by_pattern(self, pattern: str) -> Optional[AnalysisStep]:
        for step in self.analysis_steps:
            if pattern in step.name:
                return step
        return None

    def _save_progress(self) -> None:
        try:
            progress_copy = self.to_dict()
            serialized = json.dumps(progress_copy)
            if self.use_redis and self.redis_client:
                key = f"progress:{self.task_id}"
                self.redis_client.set(key, serialized)
                self.redis_client.expire(key, 3600)
            else:
                os.makedirs("./data/progress", exist_ok=True)
                with open(f"./data/progress/{self.task_id}.json", 'w', encoding='utf-8') as f:
                    f.write(serialized)
        except Exception as e:
            logger.error(f"[RedisProgress] save progress failed: {self.task_id} - {e}")

    def mark_completed(self) -> Dict[str, Any]:
        try:
            self.progress_data['progress_percentage'] = 100
            self.progress_data['status'] = 'completed'
            self.progress_data['completed'] = True
            self.progress_data['completed_time'] = time.time()
            for step in self.analysis_steps:
                if step.status != 'failed':
                    step.status = 'completed'
                    step.end_time = step.end_time or time.time()
            self._save_progress()
            return self.progress_data
        except Exception as e:
            logger.error(f"[RedisProgress] mark completed failed: {self.task_id} - {e}")
            return self.progress_data

    def mark_failed(self, reason: str = "") -> Dict[str, Any]:
        try:
            self.progress_data['status'] = 'failed'
            self.progress_data['failed'] = True
            self.progress_data['failed_reason'] = reason
            self.progress_data['completed_time'] = time.time()
            for step in self.analysis_steps:
                if step.status not in ('completed', 'failed'):
                    step.status = 'failed'
                    step.end_time = step.end_time or time.time()
            self._save_progress()
            return self.progress_data
        except Exception as e:
            logger.error(f"[RedisProgress] mark failed failed: {self.task_id} - {e}")
            return self.progress_data

    def to_dict(self) -> Dict[str, Any]:
        try:
            # 🔧 Calculate time estimates in real time to ensure the latest time information is returned
            elapsed, remaining, est_total = self._calculate_time_estimates()

            return {
                'task_id': self.task_id,
                'analysts': self.analysts,
                'research_depth': self.research_depth,
                'llm_provider': self.llm_provider,
                'steps': [asdict(step) for step in self.analysis_steps],
                'start_time': self.progress_data.get('start_time'),
                'elapsed_time': elapsed,  # Use real-time calculated values
                'remaining_time': remaining,  # Use real-time calculated values
                'estimated_total_time': est_total,  # Use real-time calculated values
                'progress_percentage': self.progress_data.get('progress_percentage', 0),
                'status': self.progress_data.get('status', 'pending'),
                'current_step': self.progress_data.get('current_step'),
                'current_step_name': self.progress_data.get('current_step_name', ''),
                'current_step_description': self.progress_data.get('current_step_description', ''),
                'last_message': self.progress_data.get('last_message', ''),
                'last_update': self.progress_data.get('last_update', time.time()),
            }
        except Exception as e:
            logger.error(f"[RedisProgress] to_dict failed: {self.task_id} - {e}")
            return self.progress_data





def get_progress_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    """Get progress based on task ID (consistent with old implementation, fix cls reference)"""
    try:
        # Check the REDIS_ENABLED environment variable
        redis_enabled = os.getenv('REDIS_ENABLED', 'false').lower() == 'true'

        # If Redis is enabled, try first Redis
        if redis_enabled:
            try:
                import redis

                # Get Redis configuration from environment variables
                redis_host = os.getenv('REDIS_HOST', 'localhost')
                redis_port = int(os.getenv('REDIS_PORT', 6379))
                redis_password = os.getenv('REDIS_PASSWORD', None)
                redis_db = int(os.getenv('REDIS_DB', 0))

                # Create a Redis connection
                if redis_password:
                    redis_client = redis.Redis(
                        host=redis_host,
                        port=redis_port,
                        password=redis_password,
                        db=redis_db,
                        decode_responses=True
                    )
                else:
                    redis_client = redis.Redis(
                        host=redis_host,
                        port=redis_port,
                        db=redis_db,
                        decode_responses=True
                    )

                key = f"progress:{task_id}"
                data = redis_client.get(key)
                if data:
                    progress_data = json.loads(data)
                    progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                    return progress_data
            except Exception as e:
                logger.debug(f"📊 [Redis Progress] Redis Read failed: {e}")

        # Try to read from file
        progress_file = f"./data/progress/{task_id}.json"
        if os.path.exists(progress_file):
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                return progress_data

        # Try alternate file locations
        backup_file = f"./data/progress_{task_id}.json"
        if os.path.exists(backup_file):
            with open(backup_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                return progress_data

        return None

    except Exception as e:
        logger.error(f"📊 [Redis Progress] Failed to get progress: {task_id} - {e}")
        return None

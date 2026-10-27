"""
memory state manager
Similar to the implementation of analysis-engine, providing fast status reading and writing
"""

import asyncio
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class TaskState:
    """任务状态数据类"""
    task_id: str
    user_id: str
    stock_code: str
    status: TaskStatus
    stock_name: Optional[str] = None
    progress: int = 0
    message: str = ""
    current_step: str = ""  # Current step (compatible with older versions, can be index or name)
    current_step_name: str = ""  # 🔑 New: Current step name (short, like "market analyst") 
    current_step_description: str = ""  # 🔑 New: current step description (detailed, such as "📈 Market analysts are analyzing...") 
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    # Analysis parameters
    parameters: Optional[Dict[str, Any]] = None

    # Performance indicators
    execution_time: Optional[float] = None
    tokens_used: Optional[int] = None
    estimated_duration: Optional[float] = None  # Estimated total duration (seconds)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        # Handling enumeration types
        data['status'] = self.status.value
        # processing time format
        if self.start_time:
            data['start_time'] = self.start_time.isoformat()
        if self.end_time:
            data['end_time'] = self.end_time.isoformat()

        # Add real-time calculated time information
        if self.start_time:
            if self.end_time:
                # Task completed, using final execution time
                data['elapsed_time'] = self.execution_time or (self.end_time - self.start_time).total_seconds()
                data['remaining_time'] = 0
                data['estimated_total_time'] = data['elapsed_time']
            else:
                # The task is in progress and the elapsed time is calculated in real time.
                from datetime import datetime
                elapsed_time = (datetime.now() - self.start_time).total_seconds()
                data['elapsed_time'] = elapsed_time

                # Calculate estimated remaining time and total duration
                progress = self.progress / 100 if self.progress > 0 else 0

                # Use the total duration estimated when the task was created, or use the default value (5 minutes) if not available
                estimated_total = self.estimated_duration if self.estimated_duration else 300

                if progress >= 1.0:
                    # Task completed
                    data['remaining_time'] = 0
                    data['estimated_total_time'] = elapsed_time
                else:
                    # Estimated total duration of use (fixed value)
                    data['estimated_total_time'] = estimated_total
                    # Estimated remaining = Estimated total time - elapsed time
                    data['remaining_time'] = max(0, estimated_total - elapsed_time)
        else:
            data['elapsed_time'] = 0
            data['remaining_time'] = 300  # Default 5 minutes
            data['estimated_total_time'] = 300

        return data

class MemoryStateManager:
    """内存状态管理器"""

    def __init__(self):
        self._tasks: Dict[str, TaskState] = {}
        # 🔧 Use threading.Lock instead of asyncio.Lock to avoid event loop conflicts
        # When performing analysis in the thread pool, a new event loop is created and asyncio.Lock causes
        # "is bound to a different event loop" Error
        self._lock = threading.Lock()
        self._websocket_manager = None

    def set_websocket_manager(self, websocket_manager):
        """Set up the WebSocket manager"""
        self._websocket_manager = websocket_manager
        
    async def create_task(
        self,
        task_id: str,
        user_id: str,
        stock_code: str,
        parameters: Optional[Dict[str, Any]] = None,
        stock_name: Optional[str] = None,
    ) -> TaskState:
        """创建新任务"""
        with self._lock:
            # Calculate estimated total duration
            estimated_duration = self._calculate_estimated_duration(parameters or {})

            task_state = TaskState(
                task_id=task_id,
                user_id=user_id,
                stock_code=stock_code,
                stock_name=stock_name,
                status=TaskStatus.PENDING,
                start_time=datetime.now(),
                parameters=parameters or {},
                estimated_duration=estimated_duration,
                message="The task has been created and is waiting to be executed..."
            )
            self._tasks[task_id] = task_state
            logger.info(f"📝 创建任务状态: {task_id}")
            logger.info(f"⏱️ 预估总时长: {estimated_duration:.1f}秒 ({estimated_duration/60:.1f}分钟)")
            logger.info(f"📊 当前内存中任务数量: {len(self._tasks)}")
            logger.info(f"🔍 内存管理器实例ID: {id(self)}")
            return task_state

    def _calculate_estimated_duration(self, parameters: Dict[str, Any]) -> float:
        """Calculate estimated total duration (seconds) based on analysis parameters"""
        # Basic time (seconds) - environment preparation, configuration, etc.
        base_time = 60

        # Get analysis parameters
        research_depth = parameters.get('research_depth', '标准')
        selected_analysts = parameters.get('selected_analysts') or []
        llm_provider = parameters.get('llm_provider', 'dashscope')

        # Study depth mapping
        depth_map = {"快速": 1, "标准": 2, "深度": 3}
        d = depth_map.get(research_depth, 2)

        # Basic time spent by each analyst (based on real test data)
        analyst_base_time = {
            1: 180,  # Quick analysis: about 3 minutes per analyst
            2: 360,  # Standard analysis: approximately 6 minutes per analyst
            3: 600   # In-depth analysis: approximately 10 minutes per analyst
        }.get(d, 360)

        analyst_time = len(selected_analysts) * analyst_base_time

        # Model speed impact (based on actual testing)
        model_multiplier = {
            'dashscope': 1.0,  # Ali Bailian speed is moderate
            'deepseek': 0.7,   # DeepSeek faster
            'google': 1.3      # Google slower
        }.get(llm_provider, 1.0)

        # Additional impact of research depth (tool call complexity)
        depth_multiplier = {
            1: 0.8,  # Fast analysis with fewer tool calls
            2: 1.0,  # Standard analysis, standard tool calls
            3: 1.3   # Deep analysis, more tool calls and reasoning
        }.get(d, 1.0)

        total_time = (base_time + analyst_time) * model_multiplier * depth_multiplier
        return total_time

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        current_step: Optional[str] = None,
        current_step_name: Optional[str] = None,  # 🔑 New parameters
        current_step_description: Optional[str] = None,  # 🔑 New parameters
        result_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """更新任务状态"""
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"⚠️ 任务不存在: {task_id}")
                return False

            task = self._tasks[task_id]
            task.status = status

            if progress is not None:
                task.progress = progress
            if message is not None:
                task.message = message
            if current_step is not None:
                task.current_step = current_step
            if current_step_name is not None:  # 🔑 Update step name
                task.current_step_name = current_step_name
            if current_step_description is not None:  # 🔑 Update step description
                task.current_step_description = current_step_description
            if result_data is not None:
                # 🔍 Debugging: Check the saved to memory result_data
                logger.info(f"🔍 [MEMORY] Save result_data to memory: {task_id}")
                logger.info(f"🔍 [MEMORY] result_data key: {list(result_data.keys()) if result_data else 'None'}")
                logger.info(f"🔍 [MEMORY] result_data There is decision: {bool(result_data.get('decision')) if result_data else False}")
                if result_data and result_data.get('decision'):
                    logger.info(f"🔍 [MEMORY] decision content: {result_data['decision']}")

                task.result_data = result_data
            if error_message is not None:
                task.error_message = error_message
                
            # Set end time if task completes or fails
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.end_time = datetime.now()
                if task.start_time:
                    task.execution_time = (task.end_time - task.start_time).total_seconds()
            
            # 🔥 Use task.progress instead of parameter progress (because progress may be None)
            logger.info(f"📊 更新任务状态: {task_id} -> {status.value} ({task.progress}%)")

            # Push status updates to WebSocket
            if self._websocket_manager:
                try:
                    progress_update = {
                        "type": "progress_update",
                        "task_id": task_id,
                        "status": status.value,
                        "progress": task.progress,
                        "message": task.message,
                        "current_step": task.current_step,
                        "current_step_name": task.current_step_name,  # 🔑 Add new field
                        "current_step_description": task.current_step_description,  # 🔑 Add new field
                        "timestamp": datetime.now().isoformat()
                    }
                    # Asynchronous push, no waiting for completion
                    asyncio.create_task(
                        self._websocket_manager.send_progress_update(task_id, progress_update)
                    )
                except Exception as e:
                    logger.warning(f"⚠️ WebSocket Push failed: {e}")

            return True
    
    async def get_task(self, task_id: str) -> Optional[TaskState]:
        """获取任务状态"""
        with self._lock:
            logger.debug(f"🔍 查询任务: {task_id}")
            logger.debug(f"📊 当前内存中任务数量: {len(self._tasks)}")
            logger.debug(f"🔑 List of task IDs in memory: {list(self._tasks.keys())}")
            task = self._tasks.get(task_id)
            if task:
                logger.debug(f"✅ 找到任务: {task_id}")
            else:
                logger.debug(f"❌ 未找到任务: {task_id}")
            return task
    
    async def get_task_dict(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态（字典格式）"""
        task = await self.get_task(task_id)
        return task.to_dict() if task else None
    
    async def list_all_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all task lists (not limited to users)"""
        with self._lock:
            tasks = []
            for task in self._tasks.values():
                if status is None or task.status == status:
                    item = task.to_dict()
                    # Compatible with front-end fields
                    if 'stock_name' not in item or not item.get('stock_name'):
                        item['stock_name'] = None
                    tasks.append(item)

            # Sort by start time in descending order
            tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)

            # Pagination
            return tasks[offset:offset + limit]

    async def list_user_tasks(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """获取用户的任务列表"""
        with self._lock:
            tasks = []
            for task in self._tasks.values():
                if task.user_id == user_id:
                    if status is None or task.status == status:
                        item = task.to_dict()
                        # Compatible with front-end fields
                        if 'stock_name' not in item or not item.get('stock_name'):
                            item['stock_name'] = None
                        tasks.append(item)

            # Sort by start time in descending order
            tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)

            # Pagination
            return tasks[offset:offset + limit]
    
    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.info(f"🗑️ 删除任务: {task_id}")
                return True
            return False
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            total_tasks = len(self._tasks)
            status_counts = {}
            
            for task in self._tasks.values():
                status = task.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_tasks": total_tasks,
                "status_distribution": status_counts,
                "running_tasks": status_counts.get("running", 0),
                "completed_tasks": status_counts.get("completed", 0),
                "failed_tasks": status_counts.get("failed", 0)
            }
    
    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """清理旧任务"""
        with self._lock:
            cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
            tasks_to_remove = []

            for task_id, task in self._tasks.items():
                if task.start_time and task.start_time.timestamp() < cutoff_time:
                    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                        tasks_to_remove.append(task_id)

            for task_id in tasks_to_remove:
                del self._tasks[task_id]

            logger.info(f"🧹 清理了 {len(tasks_to_remove)} 个旧任务")
            return len(tasks_to_remove)

    async def cleanup_zombie_tasks(self, max_running_hours: int = 2) -> int:
        """Clean up zombie tasks (tasks that have been running for a long time)

        Args:
            max_running_hours: Maximum running time (hours), running tasks exceeding this time will be marked as failed

        Returns:
            Number of tasks cleaned
        """
        with self._lock:
            cutoff_time = datetime.now().timestamp() - (max_running_hours * 3600)
            zombie_tasks = []

            for task_id, task in self._tasks.items():
                # Check if it is a long running task
                if task.status in [TaskStatus.RUNNING, TaskStatus.PENDING]:
                    if task.start_time and task.start_time.timestamp() < cutoff_time:
                        zombie_tasks.append(task_id)

            # Mark zombie task as failed
            for task_id in zombie_tasks:
                task = self._tasks[task_id]
                task.status = TaskStatus.FAILED
                task.end_time = datetime.now()
                task.error_message = f"任务超时（运行时间超过 {max_running_hours} 小时）"
                task.message = "The task has timed out and is automatically marked as failed."
                task.progress = 0

                if task.start_time:
                    task.execution_time = (task.end_time - task.start_time).total_seconds()

                logger.warning(f"⚠️ 僵尸任务已标记为失败: {task_id} (运行时间: {task.execution_time:.1f}秒)")

            if zombie_tasks:
                logger.info(f"🧹 清理了 {len(zombie_tasks)} 个僵尸任务")

            return len(zombie_tasks)

    async def remove_task(self, task_id: str) -> bool:
        """Remove tasks from memory

        Args:
            task_id: Task ID

        Returns:
            Deleted successfully or not
        """
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.info(f"🗑️ Task has been removed from memory: {task_id}")
                return True
            else:
                logger.warning(f"⚠️ Task does not exist in memory: {task_id}")
                return False

# global instance
_memory_state_manager = None

def get_memory_state_manager() -> MemoryStateManager:
    """获取内存状态管理器实例"""
    global _memory_state_manager
    if _memory_state_manager is None:
        _memory_state_manager = MemoryStateManager()
    return _memory_state_manager

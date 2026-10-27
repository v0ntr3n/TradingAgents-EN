"""
WebSocket connection manager
Used to push analysis progress updates in real time
"""

import asyncio
import json
import logging
from typing import Dict, Set, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

class WebSocketManager:
    """WebSocket connection manager"""
    
    def __init__(self):
        # Store active connections:{task_id: {websocket1, websocket2, ...}}
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, task_id: str):
        """Establish a WebSocket connection"""
        await websocket.accept()
        
        async with self._lock:
            if task_id not in self.active_connections:
                self.active_connections[task_id] = set()
            self.active_connections[task_id].add(websocket)
        
        logger.info(f"🔌 WebSocket Connection established: {task_id}")
    
    async def disconnect(self, websocket: WebSocket, task_id: str):
        """Disconnect WebSocket"""
        async with self._lock:
            if task_id in self.active_connections:
                self.active_connections[task_id].discard(websocket)
                if not self.active_connections[task_id]:
                    del self.active_connections[task_id]
        
        logger.info(f"🔌 WebSocket Lost connection: {task_id}")
    
    async def send_progress_update(self, task_id: str, message: Dict[str, Any]):
        """Send progress updates to all connections for the specified task"""
        if task_id not in self.active_connections:
            return
        
        # Copy connection collection to avoid modification while iterating
        connections = self.active_connections[task_id].copy()
        
        for connection in connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.warning(f"⚠️ Failed to send WebSocket message: {e}")
                # Remove broken connections
                async with self._lock:
                    if task_id in self.active_connections:
                        self.active_connections[task_id].discard(connection)
    
    async def broadcast_to_user(self, user_id: str, message: Dict[str, Any]):
        """向用户的所有连接广播消息"""
        # This can be extended to manage connections by user ID
        # Currently, the implementation is simplified and only managed by task ID.
        pass
    
    async def get_connection_count(self, task_id: str) -> int:
        """获取指定任务的连接数"""
        async with self._lock:
            return len(self.active_connections.get(task_id, set()))
    
    async def get_total_connections(self) -> int:
        """获取总连接数"""
        async with self._lock:
            total = 0
            for connections in self.active_connections.values():
                total += len(connections)
            return total

# global instance
_websocket_manager = None

def get_websocket_manager() -> WebSocketManager:
    """Get a WebSocket manager instance"""
    global _websocket_manager
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager()
    return _websocket_manager

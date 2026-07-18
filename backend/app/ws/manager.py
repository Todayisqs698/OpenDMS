"""
WebSocket 连接管理（增强版）

从 In-Vehicle-Multimodal-Interaction-System 参考优化：
- 心跳 ping/pong 机制检测死连接
- 客户端元数据追踪（连接时间、最后活跃时间）
- 消息缓冲队列（离线客户端不丢消息）
- 自动清理超时连接
- 按消息类型路由广播
"""
import asyncio
import logging
import time
from typing import Dict, Optional, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ── 配置 ──
HEARTBEAT_INTERVAL = 30     # 服务端心跳间隔（秒）
CLIENT_TIMEOUT = 90         # 客户端超时（秒），超时后自动断开
MAX_BUFFER_SIZE = 100       # 每个客户端最大缓冲消息数


class WSManager:
    """WebSocket 连接管理器（增强版）"""

    def __init__(self):
        # 活跃连接: client_id → WebSocket
        self.connections: Dict[str, WebSocket] = {}

        # 客户端元数据
        self.client_meta: Dict[str, dict] = {}

        # 离线消息缓冲: client_id → [messages]
        self.message_buffer: Dict[str, list] = {}

        # 后台任务
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, client_id: str):
        """接受连接并注册客户端"""
        await websocket.accept()
        now = time.time()
        self.connections[client_id] = websocket
        self.client_meta[client_id] = {
            "connected_at": now,
            "last_active": now,
            "messages_sent": 0,
            "messages_received": 0,
        }

        # 恢复缓冲消息
        buffered = self.message_buffer.pop(client_id, [])
        if buffered:
            logger.info(f"📬 推送 {len(buffered)} 条离线消息给 {client_id}")
            for msg in buffered:
                try:
                    await websocket.send_json(msg)
                except Exception:
                    break

        # 启动后台任务（懒启动）
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(f"🔌 客户端连接: {client_id} (当前在线: {len(self.connections)})")

    def disconnect(self, client_id: str):
        """断开客户端"""
        self.connections.pop(client_id, None)
        self.client_meta.pop(client_id, None)
        # 保留消息缓冲（重连后恢复）
        if client_id not in self.message_buffer:
            self.message_buffer[client_id] = []
        logger.info(f"🔌 客户端断开: {client_id} (当前在线: {len(self.connections)})")

    async def send_to(self, client_id: str, data: dict) -> bool:
        """向指定客户端发送消息"""
        ws = self.connections.get(client_id)
        if ws:
            try:
                await ws.send_json(data)
                meta = self.client_meta.get(client_id, {})
                meta["last_active"] = time.time()
                meta["messages_sent"] = meta.get("messages_sent", 0) + 1
                return True
            except Exception:
                self.disconnect(client_id)
                self._buffer_message(client_id, data)
                return False
        else:
            self._buffer_message(client_id, data)
            return False

    async def broadcast(self, data: dict):
        """广播给所有在线客户端"""
        disconnected = []
        for client_id, ws in list(self.connections.items()):
            try:
                await ws.send_json(data)
                meta = self.client_meta.get(client_id, {})
                meta["last_active"] = time.time()
                meta["messages_sent"] = meta.get("messages_sent", 0) + 1
            except Exception:
                disconnected.append(client_id)

        for cid in disconnected:
            self.disconnect(cid)

    # ── 类型化推送 ──

    async def send_environment(self, env_data: dict):
        """推送环境上下文（你的 NavPanel 接收此消息）"""
        msg = {"type": "environment", "data": env_data, "timestamp": time.time()}
        await self.broadcast(msg)

    async def send_driver_state(self, state: dict):
        """推送驾驶员状态"""
        msg = {"type": "driver_state", "data": state, "timestamp": time.time()}
        await self.broadcast(msg)

    async def send_alert(self, alert: dict):
        """推送告警"""
        msg = {"type": "alert", "data": alert, "timestamp": time.time()}
        await self.broadcast(msg)

    async def send_ai_decision(self, decision: dict):
        """推送 AI 决策链路"""
        msg = {"type": "ai_decision", "data": decision, "timestamp": time.time()}
        await self.broadcast(msg)

    # ── 后台维护 ──

    async def _heartbeat_loop(self):
        """定期发送心跳，检测死连接"""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            now = time.time()
            dead = []
            for client_id, ws in list(self.connections.items()):
                try:
                    await ws.send_json({"type": "ping", "timestamp": now})
                    meta = self.client_meta.get(client_id, {})
                    meta["last_active"] = now
                except Exception:
                    dead.append(client_id)
            for cid in dead:
                self.disconnect(cid)
            if dead:
                logger.debug(f"🧹 清理 {len(dead)} 个死连接")

    async def _cleanup_loop(self):
        """定期清理超时客户端"""
        while True:
            await asyncio.sleep(CLIENT_TIMEOUT // 2)
            now = time.time()
            timeout = []
            for client_id, meta in list(self.client_meta.items()):
                if now - meta.get("last_active", now) > CLIENT_TIMEOUT:
                    timeout.append(client_id)
            for cid in timeout:
                logger.info(f"⏰ 客户端超时断开: {cid}")
                self.disconnect(cid)

            # 清理过大的消息缓冲（超过500条）
            for cid in list(self.message_buffer.keys()):
                if len(self.message_buffer.get(cid, [])) > 500:
                    self.message_buffer[cid] = self.message_buffer[cid][-200:]

    # ── 内部 ──

    def _buffer_message(self, client_id: str, data: dict):
        """缓存消息供离线客户端重连后恢复"""
        if client_id not in self.message_buffer:
            self.message_buffer[client_id] = []
        buf = self.message_buffer[client_id]
        buf.append(data)
        if len(buf) > MAX_BUFFER_SIZE:
            buf.pop(0)

    # ── 统计 ──

    def get_status(self) -> dict:
        """获取连接状态"""
        return {
            "online_clients": len(self.connections),
            "total_messages_sent": sum(
                m.get("messages_sent", 0) for m in self.client_meta.values()
            ),
            "buffered_clients": len(self.message_buffer),
            "clients": {
                cid: {
                    "connected_at": meta.get("connected_at"),
                    "last_active": meta.get("last_active"),
                    "messages_sent": meta.get("messages_sent", 0),
                }
                for cid, meta in self.client_meta.items()
            },
        }

    def handle_message(self, client_id: str, data: dict):
        """处理客户端消息（心跳响应等）"""
        meta = self.client_meta.get(client_id, {})
        meta["last_active"] = time.time()
        meta["messages_received"] = meta.get("messages_received", 0) + 1

        msg_type = data.get("type", "")
        if msg_type == "ping":
            # ping 已由心跳处理，此处做兼容
            return {"type": "pong"}
        elif msg_type == "subscribe":
            topic = data.get("topic", "")
            logger.info(f"📡 {client_id} 订阅: {topic}")
            return {"type": "subscribed", "topic": topic}

        return None


# 全局单例
ws_manager = WSManager()

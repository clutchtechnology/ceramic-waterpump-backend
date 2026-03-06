# ============================================================
# 文件说明: ws_manager.py - WebSocket 连接管理器
# ============================================================
"""
WebSocket 连接管理器

功能:
    1. 管理所有 WebSocket 连接
    2. 订阅/取消订阅频道
    3. 广播消息给订阅者
    4. 后台推送任务 (realtime_data / device_status)
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from app.core.threshold_store import load_thresholds

from config import get_settings
from app.services.polling_service_data_db2 import get_latest_data
from app.services.polling_service_status_db1_3 import get_latest_status, is_status_polling_running
from app.services.mock_service import MockService

logger = logging.getLogger(__name__)
settings = get_settings()

# 推送间隔 (秒) - 使用 DB2 轮询间隔作为推送间隔
PUSH_INTERVAL = settings.poll_interval_db2
HEARTBEAT_TIMEOUT = 45  # 心跳超时时间


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # websocket -> 订阅的频道集合
        self.active_connections: Dict[WebSocket, Set[str]] = {}
        # websocket -> 最后心跳时间
        self.last_heartbeat: Dict[WebSocket, datetime] = {}
        # 推送任务
        self._push_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._is_running = False

    async def connect(self, websocket: WebSocket):
        """接受新的 WebSocket 连接"""
        await websocket.accept()
        self.active_connections[websocket] = set()
        self.last_heartbeat[websocket] = datetime.now(timezone.utc)
        client_host = websocket.client.host if websocket.client else "unknown"
        logger.info(f"[WS] 新连接建立 (来自 {client_host})，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """移除 WebSocket 连接"""
        channels = self.active_connections.get(websocket, set())
        if websocket in self.active_connections:
            del self.active_connections[websocket]
        if websocket in self.last_heartbeat:
            del self.last_heartbeat[websocket]
        logger.info(f"[WS] 连接断开 (订阅频道: {channels or '无'})，剩余连接数: {len(self.active_connections)}")

    def subscribe(self, websocket: WebSocket, channel: str) -> bool:
        """订阅频道"""
        valid_channels = {"realtime", "device_status"}
        if channel not in valid_channels:
            logger.warning(f"[WS] 无效的订阅频道: {channel}")
            return False
        if websocket in self.active_connections:
            self.active_connections[websocket].add(channel)
            logger.info(f"[WS] 客户端订阅频道: {channel}, 当前该频道订阅数: {self.get_channel_subscribers(channel)}")
            return True
        return False

    def unsubscribe(self, websocket: WebSocket, channel: str):
        """取消订阅频道"""
        if websocket in self.active_connections:
            self.active_connections[websocket].discard(channel)
            logger.info(f"[WS] 客户端取消订阅: {channel}")

    def update_heartbeat(self, websocket: WebSocket):
        """更新心跳时间"""
        self.last_heartbeat[websocket] = datetime.now(timezone.utc)
        logger.debug(f"[WS] 收到心跳，连接数: {len(self.active_connections)}")

    async def broadcast(self, channel: str, message: dict):
        """向指定频道的所有订阅者广播消息"""
        disconnected = []
        for ws, channels in self.active_connections.items():
            if channel in channels:
                try:
                    if ws.application_state != WebSocketState.CONNECTED or ws.client_state != WebSocketState.CONNECTED:
                        disconnected.append(ws)
                        continue
                    await ws.send_json(message)
                except WebSocketDisconnect:
                    disconnected.append(ws)
                except Exception as e:
                    logger.warning(f"发送消息失败: {e}")
                    disconnected.append(ws)

        # 清理断开的连接
        for ws in disconnected:
            self.disconnect(ws)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """发送消息给单个客户端"""
        try:
            if websocket.application_state != WebSocketState.CONNECTED or websocket.client_state != WebSocketState.CONNECTED:
                self.disconnect(websocket)
                return
            await websocket.send_json(message)
        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            logger.warning(f"发送消息失败: {e}")
            self.disconnect(websocket)

    def get_connection_count(self) -> int:
        """获取当前连接数"""
        return len(self.active_connections)

    def get_channel_subscribers(self, channel: str) -> int:
        """获取指定频道的订阅者数量"""
        count = 0
        for channels in self.active_connections.values():
            if channel in channels:
                count += 1
        return count

    # ========================================
    # 后台推送任务
    # ========================================
    async def start_push_tasks(self):
        """启动后台推送任务"""
        if self._is_running:
            return

        self._is_running = True
        self._push_task = asyncio.create_task(self._push_loop(), name="ws_push_loop")
        self._cleanup_task = asyncio.create_task(self._cleanup_loop(), name="ws_cleanup_loop")
        logger.info(f"[WS] 推送任务已启动 (间隔: {PUSH_INTERVAL}s, 心跳超时: {HEARTBEAT_TIMEOUT}s)")

    async def stop_push_tasks(self):
        """停止后台推送任务"""
        self._is_running = False

        for task in [self._push_task, self._cleanup_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._push_task = None
        self._cleanup_task = None
        logger.info("[WS] 推送任务已停止")

    async def _push_loop(self):
        """数据推送主循环"""
        while self._is_running:
            try:
                # 检查是否有订阅者
                realtime_subs = self.get_channel_subscribers("realtime")
                status_subs = self.get_channel_subscribers("device_status")

                timestamp = datetime.now(timezone.utc).isoformat()

                # 推送实时数据
                if realtime_subs > 0:
                    await self._push_realtime_data(timestamp)
                    # logger.info(f"[WS] 推送 realtime_data -> {realtime_subs} 个订阅者")

                # 推送设备状态
                if status_subs > 0:
                    await self._push_device_status(timestamp)
                    # logger.info(f"[WS] 推送 device_status -> {status_subs} 个订阅者")

            except Exception as e:
                logger.error(f"[WS] 推送任务异常: {e}", exc_info=True)

            await asyncio.sleep(PUSH_INTERVAL)

    async def _push_realtime_data(self, timestamp: str):
        """推送实时数据 (realtime_data) - 6电表 + 1压力 + 6振动"""
        # 统一使用轮询服务的缓存数据
        latest = get_latest_data()
        
        # 如果缓存为空，返回空数据
        if not latest:
            logger.warning("[WS] 轮询服务缓存为空，无法推送数据")
            return
        
        is_mock = settings.use_mock_data
        source = "mock" if is_mock else "plc"
        # Mock模式: 添加微小波动让数据实时变化 (轮询5s更新一次，推送0.1s一次)
        _n = self._mock_noise if is_mock else lambda v, *_: v

        # 加载运行功率阈值配置
        thresholds = load_thresholds()
        running_power_config = thresholds.get("running_power", {})

        # 构建水泵数组 (电表数据)
        pumps = []
        for i in range(1, 7):
            pump_key = f"pump_{i}"
            pump_data = latest.get(pump_key, {})
            
            # 获取电表数据
            electricity = pump_data.get("electricity", {})
            
            # 计算运行状态 (通过功率与可配置阈值比较判断)
            power = _n(pump_data.get("power", 0.0))
            running_threshold = running_power_config.get(pump_key, 0.5)
            status = "running" if power >= running_threshold else "stopped"
            
            pumps.append({
                "id": i,
                "status": status,
                # 电气参数 (与 InfluxDB 字段名一致)
                "Pt": power,
                "ImpEp": _n(pump_data.get("energy", 0.0)),
                "I_0": _n(electricity.get("I_0", 0.0)),
                "I_1": _n(electricity.get("I_1", 0.0)),
                "I_2": _n(electricity.get("I_2", 0.0)),
                "Ua_0": _n(electricity.get("Ua_0", 0.0)),
                "Ua_1": _n(electricity.get("Ua_1", 0.0)),
                "Ua_2": _n(electricity.get("Ua_2", 0.0)),
            })

        # 构建压力数据
        pressure_data = latest.get("pressure", {})
        pressure = {
            "value": _n(pressure_data.get("value", 0.0)),
            "status": self._calc_pressure_status(pressure_data),
        }

        # 构建振动传感器数组 (6个独立的振动传感器)
        vibrations = []
        for i in range(1, 7):
            vib_key = f"vib_{i}"
            vib_data = latest.get(vib_key, {})
            
            if vib_data:
                vibration = vib_data.get("vibration", {})
                vibrations.append({
                    "device_id": vib_key,
                    "device_name": vib_data.get("device_name", f"{i}号振动传感器"),
                    "vx": _n(vibration.get("vx", 0.0)),
                    "vy": _n(vibration.get("vy", 0.0)),
                    "vz": _n(vibration.get("vz", 0.0)),
                    "dx": _n(vibration.get("dx", 0.0)),
                    "dy": _n(vibration.get("dy", 0.0)),
                    "dz": _n(vibration.get("dz", 0.0)),
                    "hzx": _n(vibration.get("hzx", 0.0)),
                    "hzy": _n(vibration.get("hzy", 0.0)),
                    "hzz": _n(vibration.get("hzz", 0.0)),
                    "status": "normal",
                })

        message = {
            "type": "realtime_data",
            "success": True,
            "timestamp": timestamp,
            "source": source,
            "data": {
                "pumps": pumps,
                "pressure": pressure,
                "vibrations": vibrations,
            },
        }

        await self.broadcast("realtime", message)

    async def _push_device_status(self, timestamp: str):
        """推送设备状态 (device_status) - 仅在状态变化时推送"""
        from app.services.polling_service_status_db1_3 import has_status_changed, reset_status_changed
        
        # 检查状态是否变化
        if not has_status_changed():
            return
        
        latest_status = get_latest_status()
        
        # 如果轮询服务未运行或缓存为空，生成 Mock 设备状态
        if not latest_status or not is_status_polling_running():
            # 生成 Mock 设备状态
            mock_devices = []
            for i in range(1, 7):
                mock_devices.append({
                    "device_id": f"pump_{i}",
                    "device_name": f"{i}#水泵",
                    "data_device_id": f"pump_{i}",
                    "offset": (i - 1) * 4,
                    "enabled": True,
                    "error": False,
                    "status_code": 0,
                    "status_hex": "0000",
                    "is_normal": True,
                })
            
            message = {
                "type": "device_status",
                "success": True,
                "timestamp": timestamp,
                "source": "mock",
                "data": {"db1": mock_devices, "db3": []},
                "summary": {"total": 6, "normal": 6, "error": 0},
                "summary_by_db": {
                    "db1": {"total": 6, "normal": 6, "error": 0},
                    "db3": {"total": 0, "normal": 0, "error": 0},
                },
            }
            await self.broadcast("device_status", message)
            reset_status_changed()
            return
        
        source = latest_status.get("source", "mock" if settings.use_mock_data else "plc")

        data = latest_status.get("data", {})
        summary_by_db = latest_status.get("summary_by_db", {})

        # 计算全局 summary
        total = 0
        normal = 0
        error = 0
        for db_summary in summary_by_db.values():
            total += db_summary.get("total", 0)
            normal += db_summary.get("normal", 0)
            error += db_summary.get("error", 0)

        message = {
            "type": "device_status",
            "success": True,
            "timestamp": timestamp,
            "source": source,
            "data": data,
            "summary": {
                "total": total,
                "normal": normal,
                "error": error,
            },
            "summary_by_db": summary_by_db,
        }

        await self.broadcast("device_status", message)
        reset_status_changed()
        logger.info(f"[WS] 推送 device_status (状态已变化) -> {self.get_channel_subscribers('device_status')} 个订阅者")

    async def _cleanup_loop(self):
        """清理超时连接的循环"""
        while self._is_running:
            await asyncio.sleep(10)  # 优化：每 10 秒检查一次，更快清理断开连接

            now = datetime.now(timezone.utc)
            disconnected = []

            for ws, last_hb in self.last_heartbeat.items():
                delta = (now - last_hb).total_seconds()
                if delta > HEARTBEAT_TIMEOUT:
                    logger.warning(f"[WS] 客户端心跳超时 ({delta:.0f}s)，断开连接")
                    disconnected.append(ws)

            for ws in disconnected:
                try:
                    await ws.close(code=1000, reason="Heartbeat timeout")
                except Exception:
                    pass
                self.disconnect(ws)
            
            # 优化：清理已断开但未正确移除的连接
            stale_connections = []
            for ws in self.active_connections.keys():
                if ws.application_state != WebSocketState.CONNECTED or ws.client_state != WebSocketState.CONNECTED:
                    stale_connections.append(ws)
            
            for ws in stale_connections:
                logger.warning(f"[WS] 清理僵尸连接")
                self.disconnect(ws)

    # ========================================
    # 辅助方法：计算状态和报警
    # ========================================
    @staticmethod
    def _mock_noise(value: float, noise_pct: float = 0.015) -> float:
        """Mock模式: 给数值添加微小随机波动 (默认 ±1.5%)"""
        if abs(value) < 1e-6:
            return 0.0
        return round(value * (1 + random.uniform(-noise_pct, noise_pct)), 4)

    def _calc_pump_status(self, pump_data: Dict[str, Any]) -> str:
        """根据水泵数据计算状态"""
        if not pump_data:
            return "offline"

        current = pump_data.get("current", 0.0)
        if current < 0.1:
            return "offline"

        # 简单判断：有报警则为 alarm，否则 normal
        # 实际应根据阈值判断
        return "normal"

    def _calc_pump_alarms(self, pump_data: Dict[str, Any]) -> list:
        """根据水泵数据计算报警列表"""
        alarms = []
        # 这里可以根据阈值判断，暂时返回空列表
        # 实际报警检测在 polling_service 中完成
        return alarms

    def _calc_pressure_status(self, pressure_data: Dict[str, Any]) -> str:
        """根据压力数据计算状态"""
        if not pressure_data:
            return "offline"
        return "normal"


# 全局单例
_manager: Optional[ConnectionManager] = None


def get_ws_manager() -> ConnectionManager:
    """获取 WebSocket 连接管理器单例"""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager

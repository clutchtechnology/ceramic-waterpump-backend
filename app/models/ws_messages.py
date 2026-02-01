# ============================================================
# 文件说明: ws_messages.py - WebSocket 消息模型
# ============================================================
"""
WebSocket 消息 Pydantic 模型

消息类型:
    - subscribe / unsubscribe: 客户端订阅/取消订阅
    - heartbeat: 心跳消息
    - realtime_data: 实时数据推送
    - device_status: 设备状态推送
    - error: 错误消息
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


# ============================================================
# 客户端 -> 服务端消息
# ============================================================
class SubscribeMessage(BaseModel):
    """订阅消息"""
    type: Literal["subscribe"] = "subscribe"
    channel: Literal["realtime", "device_status"]


class UnsubscribeMessage(BaseModel):
    """取消订阅消息"""
    type: Literal["unsubscribe"] = "unsubscribe"
    channel: Literal["realtime", "device_status"]


class HeartbeatMessage(BaseModel):
    """心跳消息"""
    type: Literal["heartbeat"] = "heartbeat"
    timestamp: Optional[str] = None


# ============================================================
# 服务端 -> 客户端消息
# ============================================================
class PumpData(BaseModel):
    """单个水泵数据"""
    id: int = Field(..., ge=1, le=6, description="水泵编号 (1-6)")
    voltage: float = Field(default=0.0, description="电压值 (V)")
    current: float = Field(default=0.0, description="电流值 (A)")
    power: float = Field(default=0.0, description="功率值 (kW)")
    energy: float = Field(default=0.0, description="累计电量 (kWh)")
    status: Literal["normal", "warning", "alarm", "offline"] = Field(
        default="offline", description="状态"
    )
    alarms: List[str] = Field(default_factory=list, description="当前报警列表")


class PressureData(BaseModel):
    """压力表数据"""
    value: float = Field(default=0.0, description="压力值 (MPa)")
    status: Literal["normal", "warning", "alarm", "offline"] = Field(
        default="offline", description="状态"
    )


class RealtimeDataPayload(BaseModel):
    """实时数据内容"""
    pumps: List[PumpData] = Field(default_factory=list, description="6台水泵数据")
    pressure: PressureData = Field(default_factory=PressureData, description="压力表数据")


class RealtimeDataMessage(BaseModel):
    """实时数据推送消息"""
    type: Literal["realtime_data"] = "realtime_data"
    success: bool = True
    timestamp: str = Field(..., description="ISO 8601 时间戳")
    source: Literal["plc", "mock"] = Field(default="plc", description="数据来源")
    data: RealtimeDataPayload


# ============================================================
# 设备状态消息
# ============================================================
class DeviceStatusItem(BaseModel):
    """单个设备状态"""
    device_id: str = Field(..., description="设备唯一标识")
    device_name: str = Field(..., description="设备显示名称")
    data_device_id: Optional[str] = Field(None, description="关联的数据设备 ID")
    offset: int = Field(default=0, description="DB 中的字节偏移量")
    enabled: bool = Field(default=True, description="设备是否启用")
    error: bool = Field(default=False, description="是否有通信错误")
    status_code: int = Field(default=0, description="状态码原始值")
    status_hex: str = Field(default="0000", description="状态码十六进制显示")
    is_normal: bool = Field(default=True, description="是否正常")


class StatusSummary(BaseModel):
    """状态统计"""
    total: int = Field(default=0, description="设备总数")
    normal: int = Field(default=0, description="正常设备数")
    error: int = Field(default=0, description="异常设备数")


class DeviceStatusMessage(BaseModel):
    """设备状态推送消息"""
    type: Literal["device_status"] = "device_status"
    success: bool = True
    timestamp: str = Field(..., description="ISO 8601 时间戳")
    source: Literal["plc", "mock"] = Field(default="plc", description="数据来源")
    data: Dict[str, List[DeviceStatusItem]] = Field(
        default_factory=dict, description="按 DB 分组的设备状态"
    )
    summary: StatusSummary = Field(default_factory=StatusSummary, description="全局统计")
    summary_by_db: Dict[str, StatusSummary] = Field(
        default_factory=dict, description="按 DB 分组的统计"
    )


# ============================================================
# 错误消息
# ============================================================
class ErrorMessage(BaseModel):
    """错误消息"""
    type: Literal["error"] = "error"
    code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误描述")


# ============================================================
# 错误码枚举
# ============================================================
class ErrorCode:
    """常用错误码"""
    PLC_DISCONNECTED = "PLC_DISCONNECTED"
    DB_ERROR = "DB_ERROR"
    INVALID_CHANNEL = "INVALID_CHANNEL"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_MESSAGE = "INVALID_MESSAGE"

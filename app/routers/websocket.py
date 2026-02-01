# ============================================================
# 文件说明: websocket.py - WebSocket 路由
# ============================================================
"""
WebSocket 实时数据推送端点

端点:
    ws://{host}:{port}/ws/realtime

协议:
    参见 docs/WEBSOCKET_PROTOCOL.md
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws_manager import get_ws_manager
from app.models.ws_messages import ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/realtime")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 实时数据端点

    消息类型:
        - subscribe: 订阅频道 (realtime / device_status)
        - unsubscribe: 取消订阅
        - heartbeat: 心跳保活

    示例:
        ```json
        {"type": "subscribe", "channel": "realtime"}
        {"type": "heartbeat", "timestamp": "2026-02-01T10:30:00Z"}
        ```
    """
    manager = get_ws_manager()
    await manager.connect(websocket)

    try:
        while True:
            # 接收客户端消息
            try:
                data = await websocket.receive_json()
                logger.debug(f"[WS] 收到消息: {data}")
            except WebSocketDisconnect:
                logger.info("[WS] 客户端主动断开连接")
                break
            except Exception as e:
                logger.warning(f"[WS] 接收消息失败: {e}")
                await manager.send_personal(websocket, {
                    "type": "error",
                    "code": ErrorCode.INVALID_MESSAGE,
                    "message": "无效的 JSON 消息格式",
                })
                continue

            msg_type = data.get("type")

            # 处理订阅
            if msg_type == "subscribe":
                channel = data.get("channel")
                if not manager.subscribe(websocket, channel):
                    await manager.send_personal(websocket, {
                        "type": "error",
                        "code": ErrorCode.INVALID_CHANNEL,
                        "message": f"无效的频道: {channel}",
                    })

            # 处理取消订阅
            elif msg_type == "unsubscribe":
                channel = data.get("channel")
                manager.unsubscribe(websocket, channel)

            # 处理心跳
            elif msg_type == "heartbeat":
                manager.update_heartbeat(websocket)
                await manager.send_personal(websocket, {
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            # 未知消息类型
            else:
                logger.warning(f"[WS] 未知消息类型: {msg_type}")
                await manager.send_personal(websocket, {
                    "type": "error",
                    "code": ErrorCode.INVALID_MESSAGE,
                    "message": f"未知的消息类型: {msg_type}",
                })

    except Exception as e:
        logger.error(f"[WS] 连接异常: {e}", exc_info=True)
    finally:
        manager.disconnect(websocket)


@router.get("/ws/status")
async def ws_status():
    """
    获取 WebSocket 连接状态

    Returns:
        连接数、各频道订阅数等统计信息
    """
    manager = get_ws_manager()
    return {
        "success": True,
        "data": {
            "total_connections": manager.get_connection_count(),
            "realtime_subscribers": manager.get_channel_subscribers("realtime"),
            "device_status_subscribers": manager.get_channel_subscribers("device_status"),
        },
    }

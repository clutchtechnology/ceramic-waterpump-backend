# ============================================================
# 文件说明: config.py - 配置管理 API
# ============================================================
# 接口列表:
# 1. GET /api/config/server  - 获取服务端运行配置 (只读)
# ============================================================

import logging
from datetime import datetime
from fastapi import APIRouter

from config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["配置管理"])


@router.get("/config/server", summary="获取服务端运行配置 (只读)")
async def get_server_config():
    """
    返回后端 .env 中的运行配置 (只读展示用)
    """
    try:
        s = get_settings()
        return {
            "success": True,
            "data": {
                "server": {
                    "host": s.server_host,
                    "port": s.server_port,
                    "debug": s.debug,
                },
                "plc": {
                    "ip": s.plc_ip,
                    "rack": s.plc_rack,
                    "slot": s.plc_slot,
                    "timeout": s.plc_timeout,
                    "use_mock_data": s.use_mock_data,
                },
                "polling": {
                    "enable_polling": s.enable_polling,
                    "poll_interval_db2": s.poll_interval_db2,
                    "poll_interval_db1_3": s.poll_interval_db1_3,
                    "poll_interval_db4": s.poll_interval_db4,
                    "verbose_log": s.verbose_polling_log,
                },
                "influxdb": {
                    "url": s.influx_url,
                    "org": s.influx_org,
                    "bucket": s.influx_bucket,
                    "batch_size": s.influx_batch_size,
                },
                "vibration": {
                    "high_precision": s.vib_high_precision,
                },
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error(f"Error in get_server_config: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

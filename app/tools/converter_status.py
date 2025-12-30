# ============================================================
# 文件说明: converter_status.py - 状态数据转换器
# ============================================================
# 转换 DB1 通信状态为存储格式
# ============================================================

from typing import Dict, Any


class StatusConverter:
    """通信状态转换器"""
    
    MODULE_TYPE = "CommStatus"
    
    def convert(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换状态数据为 InfluxDB 存储格式
        
        输入:
            - done: bool
            - busy: bool
            - error: bool
            - status: int (Word)
            - comm_state: str
        
        输出:
            - comm_done: int (0/1)
            - comm_busy: int (0/1)
            - comm_error: int (0/1)
            - comm_status: int
            - comm_state: str
        """
        return {
            "comm_done": 1 if raw_data.get("done", False) else 0,
            "comm_busy": 1 if raw_data.get("busy", False) else 0,
            "comm_error": 1 if raw_data.get("error", True) else 0,
            "comm_status": raw_data.get("status", 0),
            "comm_state": raw_data.get("comm_state", "unknown"),
        }

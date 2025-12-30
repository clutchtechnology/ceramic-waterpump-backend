"""
系统资源监控模块
监控 CPU/内存/磁盘，防止资源耗尽导致轮询失败
"""
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("⚠️ psutil 未安装，资源监控功能不可用（Mock模式下可忽略）")

import asyncio
from datetime import datetime
from typing import Dict, Any

# 资源告警阈值
CPU_THRESHOLD = 90.0  # CPU 使用率 > 90% 告警
MEMORY_THRESHOLD = 90.0  # 内存使用率 > 90% 告警
DISK_THRESHOLD = 90.0  # 磁盘使用率 > 90% 告警

_stats: Dict[str, Any] = {}
_monitor_task = None
_is_monitoring = False


def get_resource_stats() -> Dict[str, Any]:
    """获取当前资源统计"""
    if not PSUTIL_AVAILABLE:
        return {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "disk_percent": 0.0,
            "process_memory_mb": 0.0,
            "process_cpu_percent": 0.0,
            "warning": "psutil not available"
        }
    
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # 当前进程统计
        process = psutil.Process()
        process_memory = process.memory_info().rss / 1024 / 1024  # MB
        process_cpu = process.cpu_percent(interval=0.1)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_percent": round(cpu_percent, 1),
                "memory_percent": round(memory.percent, 1),
                "memory_available_mb": round(memory.available / 1024 / 1024, 1),
                "disk_percent": round(disk.percent, 1),
                "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1)
            },
            "process": {
                "memory_mb": round(process_memory, 1),
                "cpu_percent": round(process_cpu, 1),
                "threads": process.num_threads()
            },
            "alerts": _check_thresholds(cpu_percent, memory.percent, disk.percent)
        }
    except Exception as e:
        return {"error": str(e)}


def _check_thresholds(cpu: float, memory: float, disk: float) -> list:
    """检查资源是否超过阈值"""
    alerts = []
    
    if cpu > CPU_THRESHOLD:
        alerts.append({
            "type": "CPU",
            "level": "critical" if cpu > 95 else "warning",
            "message": f"CPU 使用率过高: {cpu:.1f}%"
        })
    
    if memory > MEMORY_THRESHOLD:
        alerts.append({
            "type": "MEMORY",
            "level": "critical" if memory > 95 else "warning",
            "message": f"内存使用率过高: {memory:.1f}%"
        })
    
    if disk > DISK_THRESHOLD:
        alerts.append({
            "type": "DISK",
            "level": "warning",
            "message": f"磁盘空间不足: {disk:.1f}%"
        })
    
    return alerts


async def _monitor_loop():
    """资源监控循环 (每30秒)"""
    global _stats
    
    while _is_monitoring:
        try:
            stats = get_resource_stats()
            _stats = stats
            
            # 打印告警
            alerts = stats.get("alerts", [])
            for alert in alerts:
                level_symbol = "🔴" if alert["level"] == "critical" else "⚠️"
                print(f"{level_symbol} {alert['message']}")
            
            # 如果 CPU/内存持续过高，建议降低轮询频率
            if stats.get("system", {}).get("cpu_percent", 0) > 95:
                print("💡 建议: CPU 过高，考虑调大 plc_poll_interval 或降低 AI 模型推理频率")
            
        except Exception as e:
            print(f"❌ 资源监控异常: {e}")
        
        await asyncio.sleep(30)


async def start_monitoring():
    """启动资源监控"""
    global _monitor_task, _is_monitoring
    
    if _is_monitoring:
        return
    
    _is_monitoring = True
    _monitor_task = asyncio.create_task(_monitor_loop())
    print("✅ 资源监控已启动 (间隔: 30s)")


async def stop_monitoring():
    """停止资源监控"""
    global _monitor_task, _is_monitoring
    
    _is_monitoring = False
    
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
        _monitor_task = None


def get_monitor_stats() -> Dict[str, Any]:
    """获取监控统计"""
    return _stats if _stats else get_resource_stats()

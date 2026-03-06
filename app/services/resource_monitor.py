"""
系统资源监控模块
监控 CPU/内存/磁盘，防止资源耗尽导致轮询失败
"""
import logging

logger = logging.getLogger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil 未安装，资源监控功能不可用（Mock模式下可忽略）")

import asyncio
from datetime import datetime
from typing import Dict, Any

# 资源告警阈值
CPU_THRESHOLD = 90.0  # CPU 使用率 > 90% 告警
SYSTEM_MEMORY_WARNING = 92.0  # 系统内存 > 92% 警告（提醒注意）
SYSTEM_MEMORY_CRITICAL = 95.0  # 系统内存 > 95% 严重告警（可能死机）
PROCESS_MEMORY_THRESHOLD_MB = 500.0  # 进程内存 > 500MB 告警（关注服务本身）
DISK_THRESHOLD = 90.0  # 磁盘使用率 > 90% 告警

# 告警抑制：同一类型告警在 N 秒内只打印一次
ALERT_SUPPRESS_SECONDS = 300  # 5 分钟内同一告警只打印一次
_last_alert_time = {}  # 记录上次告警时间

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
        
        stats = {
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
            }
        }
        
        # 检查阈值（传入进程内存）
        stats["alerts"] = _check_thresholds(
            cpu_percent, 
            memory.percent, 
            disk.percent,
            process_memory
        )
        
        return stats
    except Exception as e:
        return {"error": str(e)}


def _should_suppress_alert(alert_type: str) -> bool:
    """判断是否应该抑制告警（避免刷屏）"""
    import time
    now = time.time()
    
    if alert_type in _last_alert_time:
        elapsed = now - _last_alert_time[alert_type]
        if elapsed < ALERT_SUPPRESS_SECONDS:
            return True  # 抑制告警
    
    _last_alert_time[alert_type] = now
    return False


def _check_thresholds(cpu: float, system_memory: float, disk: float, process_memory_mb: float) -> list:
    """检查资源是否超过阈值"""
    alerts = []
    
    # 1. CPU 告警
    if cpu > CPU_THRESHOLD:
        alerts.append({
            "type": "CPU",
            "level": "critical" if cpu > 95 else "warning",
            "message": f"系统 CPU 使用率过高: {cpu:.1f}%",
            "suppress": _should_suppress_alert("CPU")
        })
    
    # 2. 系统内存告警（分级告警 + 抑制）
    if system_memory > SYSTEM_MEMORY_CRITICAL:
        # 严重告警：> 95%，可能死机
        alerts.append({
            "type": "SYSTEM_MEMORY_CRITICAL",
            "level": "critical",
            "message": f"系统内存严重不足: {system_memory:.1f}%（危险！可能死机，建议立即关闭其他程序）",
            "suppress": _should_suppress_alert("SYSTEM_MEMORY_CRITICAL")
        })
    elif system_memory > SYSTEM_MEMORY_WARNING:
        # 警告：> 92%，需要注意
        alerts.append({
            "type": "SYSTEM_MEMORY_WARNING",
            "level": "warning",
            "message": f"系统内存使用率较高: {system_memory:.1f}%（建议关注，必要时关闭其他程序）",
            "suppress": _should_suppress_alert("SYSTEM_MEMORY_WARNING")
        })
    
    # 3. 进程内存告警（关注服务本身是否内存泄漏）
    if process_memory_mb > PROCESS_MEMORY_THRESHOLD_MB:
        alerts.append({
            "type": "PROCESS_MEMORY",
            "level": "warning",
            "message": f"服务内存使用过高: {process_memory_mb:.1f} MB（可能存在内存泄漏）",
            "suppress": _should_suppress_alert("PROCESS_MEMORY")
        })
    
    # 4. 磁盘告警
    if disk > DISK_THRESHOLD:
        alerts.append({
            "type": "DISK",
            "level": "warning",
            "message": f"磁盘空间不足: {disk:.1f}%",
            "suppress": _should_suppress_alert("DISK")
        })
    
    return alerts


async def _monitor_loop():
    """资源监控循环 (每30秒)"""
    global _stats
    
    while _is_monitoring:
        try:
            stats = await asyncio.to_thread(get_resource_stats)
            _stats = stats
            
            # 打印告警（带抑制功能，避免刷屏）
            alerts = stats.get("alerts", [])
            for alert in alerts:
                # 如果告警被抑制，跳过打印
                if alert.get("suppress", False):
                    continue
                
                if alert["level"] == "critical":
                    logger.critical(alert['message'])
                else:
                    logger.warning(alert['message'])
            
            # 智能 GC 触发策略
            system_memory_percent = stats.get("system", {}).get("memory_percent", 0)
            process_memory_mb = stats.get("process", {}).get("memory_mb", 0)
            
            # 触发条件 1：系统内存 > 95% 且 进程内存 > 200MB（系统危险，且服务占用不少）
            if system_memory_percent > SYSTEM_MEMORY_CRITICAL and process_memory_mb > 200:
                if not _should_suppress_alert("GC_SYSTEM_CRITICAL"):
                    logger.warning(f"系统内存严重不足 ({system_memory_percent:.1f}%)，且服务占用 {process_memory_mb:.1f} MB，触发垃圾回收")
                    import gc
                    before_mb = process_memory_mb
                    collected = gc.collect()
                    # 重新获取进程内存
                    try:
                        import psutil
                        after_mb = psutil.Process().memory_info().rss / 1024 / 1024
                        freed_mb = before_mb - after_mb
                        logger.info(f"GC 回收了 {collected} 个对象，释放 {freed_mb:.1f} MB 内存 (前: {before_mb:.1f} MB -> 后: {after_mb:.1f} MB)")
                    except:
                        logger.info(f"GC 回收了 {collected} 个对象")
            
            # 触发条件 2：进程内存超过 500MB（服务本身可能有内存泄漏）
            elif process_memory_mb > PROCESS_MEMORY_THRESHOLD_MB:
                if not _should_suppress_alert("GC_PROCESS_HIGH"):
                    logger.warning(f"服务内存使用过高 ({process_memory_mb:.1f} MB)，可能存在内存泄漏，触发垃圾回收")
                    import gc
                    before_mb = process_memory_mb
                    collected = gc.collect()
                    try:
                        import psutil
                        after_mb = psutil.Process().memory_info().rss / 1024 / 1024
                        freed_mb = before_mb - after_mb
                        logger.info(f"GC 回收了 {collected} 个对象，释放 {freed_mb:.1f} MB 内存 (前: {before_mb:.1f} MB -> 后: {after_mb:.1f} MB)")
                    except:
                        logger.info(f"GC 回收了 {collected} 个对象")
            
            # 如果 CPU 持续过高，建议降低轮询频率
            if stats.get("system", {}).get("cpu_percent", 0) > 95:
                if not _should_suppress_alert("CPU_HIGH_SUGGESTION"):
                    logger.warning("建议: CPU 过高，考虑调大 plc_poll_interval 或降低 AI 模型推理频率")
            
        except Exception as e:
            logger.error(f"资源监控异常: {e}")
        
        await asyncio.sleep(30)


async def start_monitoring():
    """启动资源监控"""
    global _monitor_task, _is_monitoring
    
    if _is_monitoring:
        return
    
    _is_monitoring = True
    _monitor_task = asyncio.create_task(_monitor_loop())
    logger.info("资源监控已启动 (间隔: 30s)")


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

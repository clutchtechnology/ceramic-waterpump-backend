# ============================================================
# 文件说明: alarm_checker.py - 报警检查逻辑
# ============================================================
# 方法列表:
# 1. check_device_alarm()        - 统一入口, 检查一次轮询的全部数据
# 2. _check_pump_alarm()         - 水泵电流+电压报警
# 3. _check_pressure_alarm()     - 压力报警 (高/低双向)
# 4. _check_vibration_alarm()    - 振动速度+位移+频率报警
# 5. _check_one()                - 单值检查并写入报警
# ============================================================
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.core.alarm_store import log_alarm
from app.services.threshold_service import get_threshold_service

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# 1. check_device_alarm() - 统一入口
# ------------------------------------------------------------
def check_all_alarms(
    cache_data: Dict[str, Any],
    timestamp: Optional[datetime] = None,
) -> None:
    """
    检查一次轮询周期的全部设备数据。
    由 polling_service_data_db2._data_poll_loop() 在更新内存缓存后调用。
    异常不向上传播。

    cache_data 结构 (_latest_data):
      {
        "pump_1": {"id": 1, "electricity": {"I_0":..., "Ua_0":...}, ...},
        ...
        "pump_6": {...},
        "pressure": {"value": 0.45, ...},
        "vib_1": {"vibration": {"vx":..., "dx":..., "hzx":...}, ...},
        ...
        "vib_6": {...},
      }
    """
    try:
        # 1.1 检查 6 台水泵 (电流 + 电压)
        for idx in range(1, 7):
            pump_key = f"pump_{idx}"
            pump_data = cache_data.get(pump_key)
            if pump_data:
                _check_pump_alarm(idx, pump_data, timestamp)

        # 1.2 检查压力
        pressure_data = cache_data.get("pressure")
        if pressure_data:
            _check_pressure_alarm(pressure_data, timestamp)

        # 1.3 检查 6 个振动传感器 (速度 + 位移 + 频率)
        for idx in range(1, 7):
            vib_key = f"vib_{idx}"
            vib_data = cache_data.get(vib_key)
            if vib_data:
                _check_vibration_alarm(idx, vib_data, timestamp)

    except Exception as e:
        logger.error("[AlarmChecker] 报警检查失败: %s", e, exc_info=True)


# ------------------------------------------------------------
# 2. _check_pump_alarm() - 水泵电流+电压报警
# ------------------------------------------------------------
def _check_pump_alarm(
    pump_idx: int,
    pump_data: Dict[str, Any],
    timestamp: Optional[datetime],
) -> None:
    """检查单台水泵的三相电流和三相电压"""
    device_id = f"pump_{pump_idx}"
    elec = pump_data.get("electricity", {})
    if not elec:
        return

    # 2.1 三相电流: I_0, I_1, I_2
    for phase in ("I_0", "I_1", "I_2"):
        val = elec.get(phase)
        if val is not None and val > 0:
            _check_one(
                device_id=device_id,
                alarm_type="current",
                param_name=f"pump_current_{device_id}_{phase}",
                param_type="current",
                pump_idx=pump_idx,
                value=val,
                unit="A",
                timestamp=timestamp,
            )

    # 2.2 三相电压: Ua_0, Ua_1, Ua_2
    for phase in ("Ua_0", "Ua_1", "Ua_2"):
        val = elec.get(phase)
        if val is not None and val > 0:
            _check_one(
                device_id=device_id,
                alarm_type="voltage",
                param_name=f"pump_voltage_{device_id}_{phase}",
                param_type="voltage",
                pump_idx=pump_idx,
                value=val,
                unit="V",
                timestamp=timestamp,
            )


# ------------------------------------------------------------
# 3. _check_pressure_alarm() - 压力报警 (高/低双向)
# ------------------------------------------------------------
def _check_pressure_alarm(
    pressure_data: Dict[str, Any],
    timestamp: Optional[datetime],
) -> None:
    """检查压力值, 支持高压报警和低压报警"""
    value = pressure_data.get("value")
    if value is None:
        return

    svc = get_threshold_service()
    thresholds = svc.get_threshold("pressure")
    if not thresholds:
        return

    high_alarm = thresholds.get("high_alarm", 1.0)
    low_alarm = thresholds.get("low_alarm", 0.3)

    # 3.1 高压报警
    if value > high_alarm:
        log_alarm(
            device_id="pressure",
            alarm_type="pressure",
            param_name="pressure_high",
            value=value,
            threshold=high_alarm,
            level="alarm",
            timestamp=timestamp,
        )

    # 3.2 低压报警 (仅在压力 > 0 时检查, 避免停机状态误报)
    if 0 < value < low_alarm:
        log_alarm(
            device_id="pressure",
            alarm_type="pressure",
            param_name="pressure_low",
            value=value,
            threshold=low_alarm,
            level="alarm",
            timestamp=timestamp,
        )


# ------------------------------------------------------------
# 4. _check_vibration_alarm() - 振动速度+位移+频率报警
# ------------------------------------------------------------
def _check_vibration_alarm(
    vib_idx: int,
    vib_data: Dict[str, Any],
    timestamp: Optional[datetime],
) -> None:
    """检查单个振动传感器的速度/位移/频率"""
    device_id = f"vib_{vib_idx}"
    vib = vib_data.get("vibration", {})
    if not vib:
        return

    # 4.1 速度: vx, vy, vz -> param_type="speed"
    for axis in ("vx", "vy", "vz"):
        val = vib.get(axis)
        if val is not None and val > 0:
            _check_one(
                device_id=device_id,
                alarm_type="vibration_speed",
                param_name=f"vib_speed_{device_id}_{axis}",
                param_type="speed",
                pump_idx=vib_idx,
                value=val,
                unit="mm/s",
                timestamp=timestamp,
            )

    # 4.2 位移: dx, dy, dz -> param_type="displacement"
    for axis in ("dx", "dy", "dz"):
        val = vib.get(axis)
        if val is not None and val > 0:
            _check_one(
                device_id=device_id,
                alarm_type="vibration_displacement",
                param_name=f"vib_displacement_{device_id}_{axis}",
                param_type="displacement",
                pump_idx=vib_idx,
                value=val,
                unit="um",
                timestamp=timestamp,
            )

    # 4.3 频率: hzx, hzy, hzz -> param_type="frequency"
    for axis in ("hzx", "hzy", "hzz"):
        val = vib.get(axis)
        if val is not None and val > 0:
            _check_one(
                device_id=device_id,
                alarm_type="vibration_frequency",
                param_name=f"vib_frequency_{device_id}_{axis}",
                param_type="frequency",
                pump_idx=vib_idx,
                value=val,
                unit="Hz",
                timestamp=timestamp,
            )


# ------------------------------------------------------------
# 5. _check_one() - 单值检查并写入报警
# ------------------------------------------------------------
def _check_one(
    device_id: str,
    alarm_type: str,
    param_name: str,
    param_type: str,
    pump_idx: int,
    value: float,
    unit: str,
    timestamp: Optional[datetime],
) -> None:
    """
    对单个数值进行阈值判断, 超过 warning_max 则写入报警记录。
    使用 threshold_service 获取阈值 (normal_max / warning_max)。
    """
    svc = get_threshold_service()
    thresholds = svc.get_threshold(param_type, pump_idx)
    if not thresholds:
        return

    warning_max = thresholds.get("warning_max")
    if warning_max is None:
        return

    # 只记录超过 warning_max 的报警 (与磨料车间 alarm_max 概念对应)
    if value <= warning_max:
        return

    log_alarm(
        device_id=device_id,
        alarm_type=alarm_type,
        param_name=param_name,
        value=value,
        threshold=warning_max,
        level="alarm",
        timestamp=timestamp,
    )

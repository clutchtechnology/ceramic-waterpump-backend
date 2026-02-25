from functools import lru_cache
from pathlib import Path
import sys
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Any


# 获取可执行文件所在目录（打包后也能正确工作）
def get_app_dir() -> Path:
    """获取应用程序目录（开发模式和打包后都能正确工作）"""
    if getattr(sys, 'frozen', False):
        # 打包后：使用可执行文件所在目录
        return Path(sys.executable).parent
    else:
        # 开发模式：使用当前文件所在目录
        return Path(__file__).parent


def get_resource_path(relative_path: str) -> Path:
    """获取资源文件的绝对路径（configs/data 等）
    
    打包后: 优先从 exe 所在目录查找（可编辑配置），回退到 _MEIPASS（内置资源）
    开发模式: 从项目根目录查找
    """
    if getattr(sys, 'frozen', False):
        # 1. 优先从 exe 所在目录查找（用户可编辑）
        exe_dir_path = Path(sys.executable).parent / relative_path
        if exe_dir_path.exists():
            return exe_dir_path
        # 2. 回退到 _MEIPASS（PyInstaller 内置资源）
        meipass_path = Path(getattr(sys, '_MEIPASS', '')) / relative_path
        if meipass_path.exists():
            return meipass_path
        # 3. 都不存在，返回 exe 目录路径（让调用方报错）
        return exe_dir_path
    else:
        return Path(__file__).parent / relative_path


class Settings(BaseSettings):
    # 服务器
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_port: int = Field(default=8081, alias="SERVER_PORT")
    debug: bool = Field(default=False, alias="DEBUG")
    
    @field_validator('debug', mode='before')
    @classmethod
    def parse_debug(cls, v: Any) -> bool:
        """处理 debug 字段，兼容字符串值"""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            # 忽略非布尔字符串（如 'WARN'），返回默认值
            if v.lower() in ('true', '1', 'yes', 'on'):
                return True
            if v.lower() in ('false', '0', 'no', 'off'):
                return False
            # 其他字符串值返回默认值 False
            return False
        return bool(v)

    # 轮询开关
    enable_polling: bool = Field(default=True, alias="ENABLE_POLLING")
    verbose_polling_log: bool = Field(default=False, alias="VERBOSE_POLLING_LOG")
    
    # 轮询间隔配置（秒）
    poll_interval_db2: float = Field(default=0.5, alias="POLL_INTERVAL_DB2")  # DB2 数据轮询间隔（默认 0.5s）
    poll_interval_db1_3: float = Field(default=5.0, alias="POLL_INTERVAL_DB1_3")  # DB1/DB3 状态轮询间隔（默认 5s）
    poll_interval_db4: float = Field(default=0.5, alias="POLL_INTERVAL_DB4")  # DB4 振动传感器轮询间隔（默认 5s）

    # Mock模式 (USE_MOCK_DATA=true 时使用模拟数据生成器代替真实PLC)
    use_mock_data: bool = Field(default=True, alias="USE_MOCK_DATA")

    # PLC 配置 (从 .env 文件读取)
    plc_ip: str = Field(default="", alias="PLC_IP")
    plc_rack: int = Field(default=0, alias="PLC_RACK")
    plc_slot: int = Field(default=1, alias="PLC_SLOT")
    plc_timeout: int = Field(default=5000, alias="PLC_TIMEOUT")

    # 批量写入 (缓存数组达到此长度后批量入库)
    influx_batch_size: int = Field(default=13, alias="INFLUX_BATCH_SIZE")

    # InfluxDB (从 .env 文件读取)
    influx_url: str = Field(default="http://localhost:8086", alias="INFLUX_URL")
    influx_token: str = Field(default="", alias="INFLUX_TOKEN")
    influx_org: str = Field(default="", alias="INFLUX_ORG")
    influx_bucket: str = Field(default="", alias="INFLUX_BUCKET")

    # 振动传感器配置
    vib_high_precision: bool = Field(default=False, alias="VIB_HIGH_PRECISION")  # 振动传感器精度模式

    class Config:
        # 使用绝对路径，确保打包后也能找到配置文件
        env_file = str(get_app_dir() / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"
        populate_by_name = True  # 允许通过别名或字段名填充


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    settings = Settings()
    # 打印配置文件路径（调试用）
    env_path = get_app_dir() / '.env'
    print(f"[配置] 配置文件路径: {env_path} (存在: {env_path.exists()})")
    print(f"[配置] USE_MOCK_DATA: {settings.use_mock_data}")
    print(f"[配置] ENABLE_POLLING: {settings.enable_polling}")
    print(f"[配置] POLL_INTERVAL_DB2: {settings.poll_interval_db2}s")
    print(f"[配置] POLL_INTERVAL_DB1_3: {settings.poll_interval_db1_3}s")
    print(f"[配置] POLL_INTERVAL_DB4: {settings.poll_interval_db4}s")
    print(f"[配置] VIB_HIGH_PRECISION: {settings.vib_high_precision}")
    return settings

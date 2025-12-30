from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 服务器
    server_host: str = "0.0.0.0"
    server_port: int = 8081
    debug: bool = False

    # 轮询
    enable_polling: bool = False
    enable_mock_polling: bool = False  # Mock模式下是否启用轮询（模拟PLC→解析→存储流程）
    verbose_polling_log: bool = False
    plc_poll_interval: int = 5

    # PLC
    use_real_plc: bool = False
    use_mock_data: bool = True
    plc_ip: str = ""
    plc_rack: int = 0
    plc_slot: int = 1
    plc_timeout: int = 5000

    # 批量写入
    batch_size: int = 30

    # InfluxDB
    influx_url: str = ""
    influx_token: str = ""
    influx_org: str = ""
    influx_bucket: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

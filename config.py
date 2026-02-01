from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # 服务器
    server_host: str = "0.0.0.0"
    server_port: int = 8081
    debug: bool = False

    # 轮询开关
    enable_polling: bool = False
    verbose_polling_log: bool = False
    plc_poll_interval: int = 5

    # Mock模式 (USE_MOCK_DATA=true 时使用模拟数据生成器代替真实PLC)
    use_mock_data: bool = Field(default=True, alias="USE_MOCK_DATA")

    # PLC 配置
    plc_ip: str = ""
    plc_rack: int = 0
    plc_slot: int = 1
    plc_timeout: int = 5000

    # 批量写入 (轮询12次后批量入库)
    batch_size: int = 12

    # InfluxDB
    influx_url: str = "http://localhost:8086"
    influx_token: str = "SkBJopsvaCCLjXqNAjpYmMl6F-LfKBv0H1hukyt2duk2DwWr5wD0PI0B6Y2TeTphbik9iP-wr34RdW7A1CSt0A=="
    influx_org: str = "clutchtech"
    influx_bucket: str = "waterpump"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
        populate_by_name = True  # 允许通过别名或字段名填充


@lru_cache()
def get_settings() -> Settings:
    return Settings()

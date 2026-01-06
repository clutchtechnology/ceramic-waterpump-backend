from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import api_router
from app.routers.health import health  # 用于根路径健康检查
from app.services.polling_service import start_polling, stop_polling
from app.services.resource_monitor import start_monitoring, stop_monitoring
from config import get_settings

# 1. 配置日志格式 (工控环境需要时间戳便于排查)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting waterpump backend...")
    if settings.enable_polling:
        await start_polling()
    await start_monitoring()
    yield
    if settings.enable_polling:
        await stop_polling()
    await stop_monitoring()


def create_app() -> FastAPI:
    app = FastAPI(title="Waterpump Backend", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 全局 health 接口
    @app.get("/health")
    async def root_health():
        """全局健康检查（根路径）"""
        return await health()
    
    # 注册所有 API 路由 (拆分后的模块化路由)
    # 路由结构:
    #   /api/health           - 健康检查
    #   /api/status           - 系统状态
    #   /api/realtime/*       - 实时数据
    #   /api/history          - 历史数据
    #   /api/statistics       - 统计数据
    #   /api/config/*         - 配置管理
    #   /api/alarms/*         - 报警管理
    #   /api/status/devices   - 设备状态
    app.include_router(api_router, prefix="/api")
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.server_host, port=settings.server_port, reload=False)


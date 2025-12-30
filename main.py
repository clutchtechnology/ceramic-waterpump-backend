from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import waterpump  # auth 暂时禁用（需要bcrypt）
from app.services.polling_service import start_polling, stop_polling
from app.services.resource_monitor import start_monitoring, stop_monitoring
from config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting waterpump backend...")
    if settings.enable_polling:
        await start_polling()
    await start_monitoring()
    yield
    if settings.enable_polling:
        await stop_polling()
    await stop_monitoring()


def create_app() -> FastAPI:
    app = FastAPI(title="Waterpump Backend", version="0.1.0", lifespan=lifespan)
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
        return await waterpump.health()
    
    # waterpump 模块接口
    app.include_router(waterpump.router, prefix="/api/waterpump", tags=["waterpump"])
    
    # auth 认证接口（暂时禁用，需要bcrypt依赖）
    # app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.server_host, port=settings.server_port, reload=False)

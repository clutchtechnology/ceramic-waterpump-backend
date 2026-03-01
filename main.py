from contextlib import asynccontextmanager
import logging
import logging.handlers
import sys
import io
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import api_router, ws_router
from app.routers.health import health  # 用于根路径健康检查
from app.services.polling_service_data_db2 import start_data_polling, stop_data_polling
from app.services.polling_service_status_db1_3 import start_status_polling, stop_status_polling
from app.services.resource_monitor import start_monitoring, stop_monitoring
from app.services.ws_manager import get_ws_manager
from config import get_settings, get_app_dir

# 0. 设置控制台输出编码为 UTF-8（解决 Windows 乱码问题）
if sys.platform == 'win32':
    try:
        # 设置标准输出和错误输出为 UTF-8
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass  # 如果设置失败，继续运行

# 1. 配置日志系统（支持日志轮转和自动清理）
def setup_logging():
    import datetime
    
    # 创建 logs 目录
    log_dir = get_app_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # 日志文件路径（直接使用日期命名）
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"app.log.{today}"
    
    # 创建根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 清除已有的处理器
    root_logger.handlers.clear()
    
    # 1. 控制台处理器（只显示 WARNING 及以上级别）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # 2. 文件处理器（按日期命名，无需轮转 handler）
    file_handler = logging.FileHandler(
        filename=str(log_file),
        encoding='utf-8',
        mode='a'
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # 3. 限制日志总大小（定期清理超过 50GB 的旧日志）
    import threading
    import time
    
    def cleanup_old_logs():
        """定期清理超过 30 天或超过 50GB 的旧日志文件"""
        while True:
            try:
                time.sleep(3600)  # 每小时检查一次
                
                # 获取所有日志文件（按修改时间排序）
                log_files = sorted(log_dir.glob("app.log.*"), key=lambda p: p.stat().st_mtime)
                
                # 1. 删除超过 30 天的日志
                now = datetime.datetime.now()
                for log_file in log_files[:]:
                    file_age_days = (now - datetime.datetime.fromtimestamp(log_file.stat().st_mtime)).days
                    if file_age_days > 30:
                        file_size = log_file.stat().st_size
                        log_file.unlink()
                        log_files.remove(log_file)
                        logging.info(f"[日志清理] 删除过期日志: {log_file.name} (已保存 {file_age_days} 天)")
                
                # 2. 如果总大小超过 50GB，删除最旧的文件
                total_size = sum(f.stat().st_size for f in log_files)
                max_size = 50 * 1024 * 1024 * 1024  # 50GB
                
                while total_size > max_size and len(log_files) > 1:
                    oldest_file = log_files.pop(0)
                    file_size = oldest_file.stat().st_size
                    oldest_file.unlink()
                    total_size -= file_size
                    logging.info(f"[日志清理] 删除旧日志（超过大小限制）: {oldest_file.name} ({file_size / 1024 / 1024:.2f} MB)")
            except Exception as e:
                logging.error(f"[日志清理] 清理失败: {e}")
    
    # 启动后台清理线程
    cleanup_thread = threading.Thread(target=cleanup_old_logs, daemon=True)
    cleanup_thread.start()
    
    logging.info(f"[日志系统] 日志目录: {log_dir}")
    logging.info(f"[日志系统] 当前日志文件: {log_file.name}")
    logging.info(f"[日志系统] 日志轮转: 每天午夜自动创建新文件")
    logging.info(f"[日志系统] 保留策略: 最近 30 天，总大小不超过 50GB")

# 初始化日志系统
setup_logging()

logger = logging.getLogger(__name__)
settings = get_settings()

# 启动诊断: 打印资源路径解析结果
def _log_resource_paths():
    from config import get_resource_path
    frozen = getattr(sys, 'frozen', False)
    meipass = getattr(sys, '_MEIPASS', 'N/A')
    logger.info(f"[启动诊断] frozen={frozen}, _MEIPASS={meipass}")
    logger.info(f"[启动诊断] sys.executable={sys.executable}")
    logger.info(f"[启动诊断] get_app_dir()={get_app_dir()}")
    test_path = get_resource_path("configs/config_waterpump_db2.yaml")
    logger.info(f"[启动诊断] config_waterpump_db2.yaml -> {test_path} (exists={test_path.exists()})")
    test_path2 = get_resource_path("configs/plc_modules.yaml")
    logger.info(f"[启动诊断] plc_modules.yaml -> {test_path2} (exists={test_path2.exists()})")

_log_resource_paths()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting waterpump backend...")
    if settings.enable_polling:
        await start_data_polling()
        await start_status_polling()
    await start_monitoring()
    # 启动 WebSocket 推送任务
    ws_manager = get_ws_manager()
    await ws_manager.start_push_tasks()
    yield
    # 停止 WebSocket 推送任务
    await ws_manager.stop_push_tasks()
    if settings.enable_polling:
        await stop_data_polling()
        await stop_status_polling()
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
    #   /api/config/server    - 服务端运行配置 (只读)
    #   /api/thresholds       - 阈值管理 (CRUD + reset)
    #   /api/alarms/*         - 报警管理 (records + count)
    #   /api/waterpump/history - 历史数据
    #   /ws/realtime          - WebSocket 实时数据推送
    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router, prefix="/ws")
    
    return app


app = create_app()


if __name__ == "__main__":
    # Launch desktop tray + log viewer when running as a script
    from scripts.tray_app import run_tray_app

    run_tray_app()


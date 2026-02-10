"""PyQt-based system tray and log viewer for the backend service."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import psutil
import uvicorn
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon, QFont, QPixmap, QPainter, QColor
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QSystemTrayIcon,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

try:
    from config import get_settings

    _settings = get_settings()
    HOST = _settings.server_host
    PORT = _settings.server_port
    INFLUX_URL = _settings.influx_url
except Exception:
    HOST = os.getenv("SERVER_HOST", "0.0.0.0")
    PORT = os.getenv("SERVER_PORT", "8081")
    INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")

# 检测是否在打包环境中运行
IS_FROZEN = getattr(sys, "frozen", False)

# 获取工作目录（打包后需要特殊处理）
if IS_FROZEN:
    # 打包后，使用 exe 所在目录
    WORKDIR = Path(sys.executable).parent
else:
    # 开发模式，使用脚本所在目录的父目录
    WORKDIR = Path(__file__).resolve().parents[1]

LOG_DIR = WORKDIR / "logs"
LOG_FILE = LOG_DIR / "server.log"
INFLUX_LOG_FILE = LOG_DIR / "influxd.log"
INFLUXD_PATH = Path(os.getenv("INFLUXD_PATH", str(WORKDIR / "influxd.exe")))
# Hide console window when spawning uvicorn (Windows only)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
# 优雅停止超时时间（秒）
STOP_TIMEOUT = 10
# 单例锁名称
SINGLE_INSTANCE_KEY = "waterpump-backend-tray-app"


class ServerController:
    """后端服务进程控制器，管理 uvicorn 服务的启动、停止和状态监控。"""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._log_handle: Optional[object] = None
        self._influx_proc: Optional[subprocess.Popen] = None
        self._influx_log_handle: Optional[object] = None
        self._influx_started_by_me = False
        # 打包模式下使用线程运行服务
        self._server_thread: Optional[threading.Thread] = None
        self._uvicorn_server: Optional[uvicorn.Server] = None
        self._ensure_log_dir()

    # ==================== 公共属性 ====================

    @property
    def pid(self) -> Optional[int]:
        """获取当前服务进程 PID，未运行时返回 None。"""
        if IS_FROZEN:
            # 打包模式：返回当前进程 PID
            return os.getpid() if self.is_running else None
        return self._proc.pid if self.is_running else None

    @property
    def is_running(self) -> bool:
        """检查服务是否正在运行。"""
        if IS_FROZEN:
            # 打包模式：检查线程存活且端口被占用
            if self._server_thread is None or not self._server_thread.is_alive():
                return False
            return self._is_port_in_use(int(PORT))
        self._cleanup_if_exited()
        return self._proc is not None and self._proc.poll() is None

    # ==================== 公共方法 ====================

    def start(self) -> str:
        """启动后端服务。"""
        if self.is_running:
            return f"服务已在运行 (PID {self.pid})"

        influx_msg = self._ensure_influxd_running()
        if influx_msg is not None:
            return influx_msg

        # 检查端口是否被占用，如果被占用则尝试杀死占用进程
        if self._is_port_in_use(int(PORT)):
            kill_msg = self._kill_process_using_port(int(PORT))
            if kill_msg:
                return kill_msg
            # 等待端口释放
            time.sleep(1)
            if self._is_port_in_use(int(PORT)):
                return f"端口 {PORT} 仍被占用，无法启动服务"

        if IS_FROZEN:
            return self._start_in_thread()
        return self._spawn_server()

    def stop(self) -> str:
        """停止后端服务（优雅终止，超时后强制终止）。"""
        if not self.is_running:
            self._stop_influxd_if_needed()
            return "服务未运行"

        pid = self.pid
        try:
            if IS_FROZEN:
                self._stop_uvicorn_server()
            else:
                self._terminate_process()
            self._stop_influxd_if_needed()
            return f"服务已停止 (PID {pid})"
        except Exception as exc:  # noqa: BLE001
            return f"停止服务失败: {exc}"
        finally:
            self._release_resources()

    def stop_all_processes(self) -> str:
        """停止所有相关进程（包括子进程和占用端口的进程）。"""
        try:
            killed_pids = []
            
            # 1. 停止当前服务进程及其子进程
            if self.is_running:
                try:
                    current_pid = self.pid
                    proc = psutil.Process(current_pid)
                    # 杀死所有子进程
                    children = proc.children(recursive=True)
                    for child in children:
                        try:
                            child.kill()
                            killed_pids.append(f"{child.pid}({child.name()})")
                        except Exception:
                            pass
                    # 杀死主进程
                    if IS_FROZEN:
                        self._stop_uvicorn_server()
                    else:
                        proc.kill()
                        killed_pids.append(f"{current_pid}({proc.name()})")
                except Exception as exc:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"停止当前进程失败: {exc}")
            
            # 2. 杀死占用 8081 端口的所有进程
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr.port == int(PORT) and conn.status == "LISTEN":
                    try:
                        proc = psutil.Process(conn.pid)
                        proc_name = proc.name()
                        # 杀死子进程
                        children = proc.children(recursive=True)
                        for child in children:
                            try:
                                child.kill()
                                killed_pids.append(f"{child.pid}({child.name()})")
                            except Exception:
                                pass
                        # 杀死主进程
                        proc.kill()
                        killed_pids.append(f"{conn.pid}({proc_name})")
                    except psutil.NoSuchProcess:
                        pass
                    except Exception:
                        pass
            
            # 3. 停止 InfluxDB
            self._stop_influxd_if_needed()
            
            # 4. 释放资源
            self._release_resources()
            
            if killed_pids:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"已杀死进程: {', '.join(killed_pids)}")
                return f"已停止所有进程: {', '.join(killed_pids)}"
            return "所有进程已停止"
        except Exception as exc:
            return f"停止进程失败: {exc}"

    def status_text(self) -> str:
        """获取服务状态的可读文本。"""
        if not self.is_running:
            return "服务未运行"

        try:
            proc_info = psutil.Process(self.pid)
            return f"服务运行中 (PID {self.pid}) 状态: {proc_info.status()}"
        except psutil.NoSuchProcess:
            self._release_resources()
            return "服务已异常退出"
        except Exception:  # noqa: BLE001
            return f"服务运行中 (PID {self.pid}) 状态: 未知"

    # ==================== 私有方法 ====================

    @staticmethod
    def _ensure_log_dir() -> None:
        """确保日志目录存在。"""
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _is_port_in_use(port: int) -> bool:
        """检查指定端口是否被占用。"""
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port and conn.status == "LISTEN":
                return True
        return False

    @staticmethod
    def _kill_process_using_port(port: int) -> Optional[str]:
        """杀死占用指定端口的进程。"""
        try:
            killed_pids = []
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr.port == port and conn.status == "LISTEN":
                    try:
                        proc = psutil.Process(conn.pid)
                        proc_name = proc.name()
                        # 杀死进程及其所有子进程
                        children = proc.children(recursive=True)
                        for child in children:
                            try:
                                child.kill()
                            except Exception:
                                pass
                        proc.kill()
                        killed_pids.append(f"{conn.pid}({proc_name})")
                    except psutil.NoSuchProcess:
                        pass
                    except psutil.AccessDenied:
                        return f"无权限杀死占用端口 {port} 的进程 (PID {conn.pid})，请以管理员身份运行"
                    except Exception as exc:
                        return f"杀死进程失败: {exc}"
            
            if killed_pids:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"已杀死占用端口 {port} 的进程: {', '.join(killed_pids)}")
            return None
        except Exception as exc:
            return f"检查端口占用失败: {exc}"

    @staticmethod
    def _parse_influx_port(url: str) -> int:
        parsed = urlparse(url)
        if parsed.port:
            return int(parsed.port)
        return 8086

    def _ensure_influxd_running(self) -> Optional[str]:
        """确保 InfluxDB 已启动，若需要则静默启动。"""
        influx_port = self._parse_influx_port(INFLUX_URL)
        if self._is_port_in_use(influx_port):
            return None

        if not INFLUXD_PATH.exists():
            return f"未找到 influxd.exe: {INFLUXD_PATH}"

        try:
            INFLUX_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            self._influx_log_handle = INFLUX_LOG_FILE.open("a", encoding="utf-8", buffering=1)
            self._influx_proc = subprocess.Popen(
                [str(INFLUXD_PATH)],
                cwd=str(WORKDIR),
                stdout=self._influx_log_handle,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
            self._influx_started_by_me = True

            # 等待端口监听
            for _ in range(100):  # 最多 10 秒
                time.sleep(0.1)
                if self._is_port_in_use(influx_port):
                    return None

            return f"InfluxDB 启动超时，请检查日志: {INFLUX_LOG_FILE}"
        except Exception as exc:  # noqa: BLE001
            return f"启动 InfluxDB 失败: {exc}"

    def _stop_influxd_if_needed(self) -> None:
        """停止由本程序启动的 InfluxDB。"""
        if not self._influx_started_by_me:
            return

        if self._influx_proc is None:
            return

        try:
            self._influx_proc.terminate()
            self._influx_proc.wait(timeout=STOP_TIMEOUT)
        except Exception:  # noqa: BLE001
            try:
                self._influx_proc.kill()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._influx_proc = None
            self._influx_started_by_me = False
            if self._influx_log_handle is not None:
                try:
                    self._influx_log_handle.close()
                except Exception:  # noqa: BLE001
                    pass
                self._influx_log_handle = None

    def _cleanup_if_exited(self) -> None:
        """检测进程是否已退出，若已退出则清理资源。"""
        if self._proc is not None and self._proc.poll() is not None:
            self._release_resources()

    def _release_resources(self) -> None:
        """释放进程和日志句柄资源。"""
        self._proc = None
        self._server_thread = None
        self._uvicorn_server = None
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._log_handle = None

    def _build_command(self) -> list[str]:
        """构建 uvicorn 启动命令（仅开发模式使用）。"""
        return [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            str(HOST),
            "--port",
            str(PORT),
        ]

    def _start_in_thread(self) -> str:
        """在线程中启动 uvicorn 服务（打包模式）。"""
        # 用于存储线程中的异常
        self._thread_error: Optional[str] = None

        def run_server():
            try:
                self._uvicorn_server.run()
            except Exception as exc:  # noqa: BLE001
                import traceback
                self._thread_error = f"{exc}\n{traceback.format_exc()}"
            except SystemExit as exc:
                self._thread_error = f"SystemExit: {exc}"

        try:
            # 切换到正确的工作目录
            os.chdir(str(WORKDIR))
            
            # 将工作目录添加到 Python 路径
            if str(WORKDIR) not in sys.path:
                sys.path.insert(0, str(WORKDIR))

            # 配置日志输出到文件
            self._setup_file_logging()

            # 尝试预先导入应用以捕获导入错误
            try:
                from main import app as fastapi_app
            except Exception as exc:
                import traceback
                return f"无法加载应用: {exc}\n{traceback.format_exc()}"

            # 配置 uvicorn（直接传入 app 对象而非字符串）
            config = uvicorn.Config(
                fastapi_app,  # 直接使用导入的 app 对象
                host=str(HOST),
                port=int(PORT),
                log_level="info",
                log_config=None,  # 禁用默认日志配置，使用我们的配置
                access_log=True,
            )
            self._uvicorn_server = uvicorn.Server(config)

            # 在后台线程中运行服务器
            self._server_thread = threading.Thread(
                target=run_server,
                daemon=True,
                name="uvicorn-server",
            )
            self._server_thread.start()

            # 等待服务器启动（通过检测端口是否被监听）
            for i in range(100):  # 最多等待 10 秒
                time.sleep(0.1)
                # 检查是否有错误
                if self._thread_error:
                    return f"服务启动失败: {self._thread_error}"
                # 检查线程是否还存活
                if not self._server_thread.is_alive():
                    if self._thread_error:
                        return f"服务启动失败: {self._thread_error}"
                    return "服务启动失败: 线程已退出（未知错误）"
                # 通过端口检测服务是否已启动
                if self._is_port_in_use(int(PORT)):
                    return f"服务已启动 (PID {os.getpid()})"

            return "服务启动超时，请检查日志"
        except Exception as exc:  # noqa: BLE001
            self._server_thread = None
            self._uvicorn_server = None
            import traceback
            return f"启动失败: {exc}\n{traceback.format_exc()}"

    def _setup_file_logging(self) -> None:
        """配置日志输出到文件（打包模式）。"""
        import logging
        
        # 确保日志目录存在
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        # 创建文件处理器
        file_handler = logging.FileHandler(
            LOG_FILE, 
            mode='a', 
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
        
        # 配置根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        # 移除已有的处理器避免重复
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.addHandler(file_handler)
        
        # 配置 uvicorn 相关日志器
        for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"]:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
            logger.handlers = []
            logger.addHandler(file_handler)
            logger.propagate = False

    def _stop_uvicorn_server(self) -> None:
        """停止 uvicorn 服务器（打包模式）。"""
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
            # 等待线程结束
            if self._server_thread is not None:
                self._server_thread.join(timeout=STOP_TIMEOUT)

    def _spawn_server(self) -> str:
        """启动服务子进程。"""
        try:
            log_file = LOG_FILE.open("a", encoding="utf-8", buffering=1)
        except OSError as exc:
            return f"无法打开日志文件: {exc}"

        try:
            self._proc = subprocess.Popen(
                self._build_command(),
                cwd=str(WORKDIR),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
            self._log_handle = log_file
            return f"服务已启动 (PID {self._proc.pid})"
        except FileNotFoundError:
            log_file.close()
            return "无法启动服务，请确认已安装 uvicorn"
        except Exception as exc:  # noqa: BLE001
            log_file.close()
            return f"启动失败: {exc}"

    def _terminate_process(self) -> None:
        """终止服务进程（先优雅终止，超时后强制终止，包括所有子进程）。"""
        if self._proc is None:
            return

        try:
            # 获取主进程
            main_proc = psutil.Process(self._proc.pid)
            
            # 获取所有子进程
            children = main_proc.children(recursive=True)
            
            # 先尝试优雅终止主进程
            self._proc.terminate()
            try:
                self._proc.wait(timeout=STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                # 超时后强制杀死所有子进程
                for child in children:
                    try:
                        child.kill()
                    except Exception:
                        pass
                # 强制杀死主进程
                self._proc.kill()
                self._proc.wait(timeout=5)
        except psutil.NoSuchProcess:
            # 进程已经不存在
            pass
        except Exception as exc:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"终止进程时出错: {exc}")


class LogWindow(QMainWindow):
    def __init__(self, controller: ServerController, poll_interval_ms: int = 1000, max_blocks: int = 5000, tail_bytes: int = 2 * 1024 * 1024) -> None:
        super().__init__()
        self.controller = controller
        self.log_path = LOG_FILE
        self.offset = 0
        self.max_blocks = max_blocks
        self.tail_bytes = tail_bytes
        self.setWindowTitle("水泵房监测系统 - 日志")
        self.resize(900, 600)

        self.editor = QPlainTextEdit(self)
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setMaximumBlockCount(self.max_blocks)

        self.start_btn = QPushButton("启动服务", self)
        self.stop_btn = QPushButton("停止服务", self)
        self.force_stop_btn = QPushButton("强制停止", self)
        self.clear_log_btn = QPushButton("删除日志", self)
        self.start_btn.clicked.connect(self.handle_start)
        self.stop_btn.clicked.connect(self.handle_stop)
        self.force_stop_btn.clicked.connect(self.handle_force_stop)
        self.clear_log_btn.clicked.connect(self.handle_clear_log)

        toolbar = QToolBar()
        toolbar.addWidget(self.start_btn)
        toolbar.addWidget(self.stop_btn)
        toolbar.addWidget(self.force_stop_btn)
        toolbar.addWidget(self.clear_log_btn)
        self.addToolBar(toolbar)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(self.editor)
        self.setCentralWidget(central)

        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.read_new_lines)
        self.timer.start(poll_interval_ms)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(2000)

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch(exist_ok=True)
        self._load_tail()
        self.update_status()

    def append_line(self, line: str) -> None:
        self.editor.moveCursor(self.editor.textCursor().End)
        self.editor.insertPlainText(line)
        self.editor.moveCursor(self.editor.textCursor().End)

    def read_new_lines(self) -> None:
        try:
            size = self.log_path.stat().st_size
            if size < self.offset:
                self.offset = 0
            with self.log_path.open("r", encoding="utf-8", errors="ignore") as fh:
                fh.seek(self.offset)
                data = fh.read()
                self.offset = fh.tell()
            if data:
                self.append_line(data)
        except Exception as exc:  # noqa: BLE001
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.append_line(f"[{timestamp}] 读取日志失败: {exc}\n")

    def _load_tail(self) -> None:
        """仅加载日志末尾，避免打开窗口时卡顿。"""
        try:
            if not self.log_path.exists():
                return
            size = self.log_path.stat().st_size
            read_size = min(self.tail_bytes, size)
            with self.log_path.open("rb") as fh:
                fh.seek(size - read_size)
                data = fh.read(read_size)
            text = data.decode("utf-8", errors="ignore")
            if size > read_size:
                newline_index = text.find("\n")
                if newline_index != -1:
                    text = text[newline_index + 1:]
            if text:
                self.editor.setPlainText(text)
                self.editor.moveCursor(self.editor.textCursor().End)
            self.offset = size
        except Exception as exc:  # noqa: BLE001
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.append_line(f"[{timestamp}] 读取日志失败: {exc}\n")

    def handle_start(self) -> None:
        msg = self.controller.start()
        self.update_status(msg)

    def handle_stop(self) -> None:
        msg = self.controller.stop()
        self.update_status(msg)

    def handle_force_stop(self) -> None:
        """强制停止所有相关进程"""
        reply = QMessageBox.question(
            self,
            "确认强制停止",
            "这将强制杀死所有相关进程（包括子进程和占用端口的进程），是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        msg = self.controller.stop_all_processes()
        self.update_status(msg)

    def handle_clear_log(self) -> None:
        """删除日志文件"""
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除所有日志吗？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        
        try:
            # 清空编辑器
            self.editor.clear()
            
            # 删除日志文件
            if self.log_path.exists():
                self.log_path.unlink()
                self.log_path.touch()
            
            # 重置偏移量
            self.offset = 0
            
            self.update_status("日志已删除")
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"删除日志失败: {exc}")

    def update_status(self, extra: Optional[str] = None) -> None:
        status = self.controller.status_text()
        if extra:
            status = f"{status} | {extra}"
        self.status_bar.showMessage(status)


class TrayApp(QSystemTrayIcon):
    """系统托盘应用，管理服务控制和日志窗口。"""

    # 图标颜色常量
    COLOR_RUNNING = QColor(34, 197, 94)   # 绿色 - 服务运行中
    COLOR_STOPPED = QColor(239, 68, 68)   # 红色 - 服务停止

    def __init__(self, controller: ServerController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.log_window: Optional[LogWindow] = None
        self._last_running_state: Optional[bool] = None
        # 菜单动作引用（用于动态启用/禁用）
        self._action_start: Optional[QAction] = None
        self._action_stop: Optional[QAction] = None

        self.setToolTip("水泵房监测系统")
        self._update_icon()
        self._setup_context_menu()
        # 双击托盘图标打开日志窗口
        self.activated.connect(self._on_tray_activated)

        # 定时检查服务状态，更新图标和菜单
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._on_status_check)
        self._status_timer.start(2000)  # 每2秒检查一次

    def _create_tray_icon(self, running: bool) -> QIcon:
        """创建托盘图标，根据服务状态显示不同颜色。"""
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        # 根据服务状态选择颜色
        bg_color = self.COLOR_RUNNING if running else self.COLOR_STOPPED
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, size - 8, size - 8)
        # 绘制白色水滴图案
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(20, 18, 24, 28)
        painter.end()
        return QIcon(pixmap)

    def _update_icon(self) -> None:
        """根据当前服务状态更新托盘图标。"""
        running = self.controller.is_running
        self.setIcon(self._create_tray_icon(running))
        self._last_running_state = running

    def _update_menu_state(self) -> None:
        """根据服务状态更新菜单项的启用状态。"""
        running = self.controller.is_running
        if self._action_start:
            self._action_start.setEnabled(not running)
        if self._action_stop:
            self._action_stop.setEnabled(running)

    def _on_status_check(self) -> None:
        """定时检查服务状态，更新图标和菜单。"""
        running = self.controller.is_running
        # 仅在状态变化时更新图标（避免频繁重绘）
        if running != self._last_running_state:
            self._update_icon()
            self._update_menu_state()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """托盘图标被激活时的处理。"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.on_log()

    def _setup_context_menu(self) -> None:
        """设置右键菜单。"""
        menu = QMenu()
        action_status = QAction("服务状态", self)
        self._action_start = QAction("启动服务", self)
        self._action_stop = QAction("停止服务", self)
        action_force_stop = QAction("强制停止所有进程", self)
        action_log = QAction("打开日志", self)
        action_quit = QAction("退出程序", self)

        action_status.triggered.connect(self.on_status)
        self._action_start.triggered.connect(self.on_start)
        self._action_stop.triggered.connect(self.on_stop)
        action_force_stop.triggered.connect(self.on_force_stop)
        action_log.triggered.connect(self.on_log)
        action_quit.triggered.connect(self.on_quit)

        menu.addAction(action_status)
        menu.addAction(self._action_start)
        menu.addAction(self._action_stop)
        menu.addAction(action_force_stop)
        menu.addAction(action_log)
        menu.addSeparator()
        menu.addAction(action_quit)
        self.setContextMenu(menu)

        # 设置初始菜单状态
        self._update_menu_state()

    def notify_text(self, text: str) -> None:
        self.showMessage("水泵房监测系统", text, QSystemTrayIcon.Information, 5000)

    def on_status(self) -> None:
        self.notify_text(self.controller.status_text())

    def on_start(self) -> None:
        msg = self.controller.start()
        self.notify_text(msg)
        self._update_icon()
        self._update_menu_state()

    def on_stop(self) -> None:
        msg = self.controller.stop()
        self.notify_text(msg)
        self._update_icon()
        self._update_menu_state()

    def on_force_stop(self) -> None:
        """强制停止所有相关进程。"""
        reply = QMessageBox.question(
            None,
            "确认强制停止",
            "这将强制杀死所有相关进程（包括子进程和占用端口的进程），是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        msg = self.controller.stop_all_processes()
        self.notify_text(msg)
        self._update_icon()
        self._update_menu_state()

    def on_log(self) -> None:
        """打开或显示日志窗口。"""
        if self.log_window is None or not self.log_window.isVisible():
            self.log_window = LogWindow(self.controller)
        self.log_window.show()
        self.log_window.raise_()
        self.log_window.activateWindow()

    def on_quit(self) -> None:
        """退出程序（会停止所有相关进程）。"""
        reply = QMessageBox.question(
            None,
            "确认退出",
            "退出程序将停止所有后台服务和相关进程，是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if self.log_window:
            self.log_window.close()
        # 使用 stop_all_processes 确保杀死所有相关进程
        msg = self.controller.stop_all_processes()
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"退出程序: {msg}")
        QApplication.instance().quit()


class SingleInstanceApp:
    """单例应用管理器，确保只有一个程序实例运行。"""

    def __init__(self, key: str) -> None:
        self._key = key
        self._server: Optional[QLocalServer] = None
        self._is_running = False
        self._check_existing_instance()

    def _check_existing_instance(self) -> None:
        """检查是否已有实例在运行。"""
        socket = QLocalSocket()
        socket.connectToServer(self._key)
        if socket.waitForConnected(500):
            # 已有实例运行，发送激活信号
            socket.write(b"activate")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            self._is_running = True
        else:
            # 没有实例运行，创建服务器
            self._is_running = False
            self._start_server()

    def _start_server(self) -> None:
        """启动本地服务器监听新实例连接。"""
        self._server = QLocalServer()
        # 清理可能残留的旧服务器
        QLocalServer.removeServer(self._key)
        if not self._server.listen(self._key):
            # 如果监听失败，尝试移除后重试
            QLocalServer.removeServer(self._key)
            self._server.listen(self._key)

    @property
    def is_running(self) -> bool:
        """返回是否已有实例在运行。"""
        return self._is_running

    def set_activation_callback(self, callback) -> None:
        """设置收到激活信号时的回调函数。"""
        if self._server:
            def on_new_connection():
                client = self._server.nextPendingConnection()
                if client:
                    client.waitForReadyRead(1000)
                    client.close()
                    callback()
            self._server.newConnection.connect(on_new_connection)


def run_tray_app() -> None:
    """启动托盘应用。"""
    app = QApplication(sys.argv)
    # 关闭最后一个窗口时不退出应用（保持托盘运行）
    app.setQuitOnLastWindowClosed(False)

    # 单例检查
    single_instance = SingleInstanceApp(SINGLE_INSTANCE_KEY)
    if single_instance.is_running:
        QMessageBox.information(None, "提示", "程序已在运行中")
        sys.exit(0)

    controller = ServerController()
    tray = TrayApp(controller)

    # 设置激活回调：当其他实例尝试启动时，显示当前实例的窗口
    single_instance.set_activation_callback(tray.on_log)

    # 检查系统是否支持托盘
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "错误", "系统不支持托盘图标")
        sys.exit(1)

    tray.show()

    # 自动启动服务
    start_msg = controller.start()
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"自动启动服务: {start_msg}")
    
    # 自动打开日志窗口
    tray.on_log()

    sys.exit(app.exec_())


if __name__ == "__main__":
    run_tray_app()

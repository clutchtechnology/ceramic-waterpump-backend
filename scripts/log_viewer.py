"""PyQt log viewer for real-time tailing of the server log."""
import sys
import time
from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QWidget,
    QVBoxLayout,
)


class LogViewer(QMainWindow):
    def __init__(self, log_path: Path, poll_interval_ms: int = 1000, max_blocks: int = 5000, tail_bytes: int = 2 * 1024 * 1024) -> None:
        super().__init__()
        self.log_path = log_path
        self.offset = 0
        self.max_blocks = max_blocks
        self.tail_bytes = tail_bytes
        self.setWindowTitle(f"日志查看器 - {self.log_path}")
        self.resize(900, 600)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        button_row = QHBoxLayout()
        self.start_btn = QPushButton("启动服务", self)
        self.stop_btn = QPushButton("停止服务", self)
        button_row.addWidget(self.start_btn)
        button_row.addWidget(self.stop_btn)
        layout.addLayout(button_row)

        self.editor = QPlainTextEdit(self)
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setMaximumBlockCount(self.max_blocks)
        layout.addWidget(self.editor)
        self.setCentralWidget(central)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.read_new_lines)
        self.timer.start(poll_interval_ms)

        # Wire buttons to simple start/stop commands via subprocess
        self.start_btn.clicked.connect(self._start_server)
        self.stop_btn.clicked.connect(self._stop_server)

        # Ensure file exists and start from current end
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch(exist_ok=True)
        self._load_tail()

    def read_new_lines(self) -> None:
        try:
            if not self.log_path.exists():
                return

            size = self.log_path.stat().st_size
            if size < self.offset:
                # File was truncated or rotated
                self.offset = 0

            with self.log_path.open("r", encoding="utf-8", errors="ignore") as fh:
                fh.seek(self.offset)
                data = fh.read()
                self.offset = fh.tell()

            if data:
                self.editor.moveCursor(self.editor.textCursor().End)
                self.editor.insertPlainText(data)
                self.editor.moveCursor(self.editor.textCursor().End)
        except Exception as exc:  # noqa: BLE001
            # Avoid spamming dialogs; write to the widget instead
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.editor.appendPlainText(f"[{timestamp}] 读取日志失败: {exc}")

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
                # 尝试从下一行开始，避免截断行
                newline_index = text.find("\n")
                if newline_index != -1:
                    text = text[newline_index + 1:]
            if text:
                self.editor.setPlainText(text)
                self.editor.moveCursor(self.editor.textCursor().End)
            self.offset = size
        except Exception as exc:  # noqa: BLE001
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.editor.appendPlainText(f"[{timestamp}] 读取日志失败: {exc}")

    def _start_server(self) -> None:
        subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"], cwd=str(Path(__file__).resolve().parents[1]))

    def _stop_server(self) -> None:
        # Best-effort stop: find uvicorn with main:app and terminate
        try:
            for proc in psutil.process_iter(["pid", "cmdline"]):
                cmd = proc.info.get("cmdline") or []
                if "uvicorn" in " ".join(cmd) and "main:app" in " ".join(cmd):
                    proc.terminate()
                    proc.wait(timeout=5)
        except Exception:
            pass


def main() -> None:
    if len(sys.argv) > 1:
        log_file = Path(sys.argv[1])
    else:
        log_file = Path(__file__).resolve().parents[1] / "logs" / "server.log"

    app = QApplication(sys.argv)
    viewer = LogViewer(log_file)
    viewer.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

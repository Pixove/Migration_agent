import sys
from datetime import datetime

LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}


class Logger:
    """简单日志器：缓冲待写消息，析构时 flush 时机不可靠。"""

    def __init__(self, name, stream=None):
        self.name = name
        self.stream = stream or sys.stdout
        self.level = LEVELS["INFO"]
        self._buffer = []

    def log(self, level, message):
        self._buffer.append((level, message))

    def flush(self):
        for level, message in self._buffer:
            stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            self.stream.write(f"[{stamp}] {self.name} {level}: {message}\n")
        self._buffer.clear()

    def info(self, message):
        self.log("INFO", message)

    def error(self, message):
        self.log("ERROR", message)

    def __del__(self):
        self.flush()

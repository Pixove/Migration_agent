import queue
from datetime import datetime


class WorkerPool:
    """简单任务池：任务队列在析构时清理，缺少显式生命周期。"""

    def __init__(self, size=2):
        self.size = size
        self.tasks = queue.Queue()
        self.workers = []
        self.running = False
        self.started_at = datetime.utcnow()

    def submit(self, fn):
        self.tasks.put(fn)

    def start(self):
        self.running = True
        for index in range(self.size):
            self.workers.append(f"worker-{index}")

    def stop(self):
        self.running = False
        self.workers.clear()
        while not self.tasks.empty():
            try:
                self.tasks.get_nowait()
            except queue.Empty:
                break

    def __del__(self):
        self.stop()

    def uptime_seconds(self):
        return (datetime.utcnow() - self.started_at).total_seconds()

    def pending(self):
        return self.tasks.qsize()

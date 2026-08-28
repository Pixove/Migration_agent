import queue


class TaskQueue:
    def __init__(self, maxsize=10):
        self.queue = queue.Queue(maxsize=maxsize)
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False
        self.queue = queue.Queue()

    def __del__(self):
        self.stop()

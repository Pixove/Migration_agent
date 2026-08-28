from datetime import datetime


class EventBus:
    """内存事件总线：订阅者只增不减，析构时清理但时机不可靠。"""

    def __init__(self):
        self.subscribers = {}
        self.started = False
        self.last_event_at = datetime.utcnow()

    def subscribe(self, name, callback):
        self.subscribers.setdefault(name, []).append(callback)

    def publish(self, name, payload=None):
        self.last_event_at = datetime.utcnow()
        for callback in self.subscribers.get(name, []):
            callback(payload)

    def start(self):
        self.started = True

    def stop(self):
        self.started = False
        self.subscribers.clear()

    def __del__(self):
        self.stop()

    def idle_seconds(self):
        return (datetime.utcnow() - self.last_event_at).total_seconds()

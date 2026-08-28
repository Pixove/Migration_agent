from datetime import datetime


class Session:
    """会话对象：持有连接状态并在析构时清理，清理时机不可靠。"""

    def __init__(self, name):
        self.name = name
        self.opened = False
        self.created_at = datetime.utcnow()

    def open(self):
        self.opened = True
        return self

    def close(self):
        if self.opened:
            self.opened = False

    def __del__(self):
        self.close()

    def age_seconds(self):
        return (datetime.utcnow() - self.created_at).total_seconds()


def open_session(name):
    session = Session(name)
    return session.open()

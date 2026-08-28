from datetime import datetime


class Connection:
    def __init__(self, name, host):
        self.name = name
        self.host = host
        self.closed = False

    def connect(self):
        self.closed = False
        return self

    def close(self):
        self.closed = True

    def __del__(self):
        self.close()

    def opened_at(self):
        return datetime.utcnow()

class Cache:
    def __init__(self, initial=None):
        self.items = {} if initial is None else dict(initial)

    def put(self, key, value):
        self.items[key] = value

    def get(self, key, default=None):
        return self.items.get(key, default)

    def flush(self):
        self.items.clear()

    def __del__(self):
        self.flush()

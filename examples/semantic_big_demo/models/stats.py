class Counter:
    def __init__(self):
        self.value = 0

    def increment(self):
        self.value += 1

    def snapshot(self):
        return self.value

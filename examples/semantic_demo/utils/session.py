class Session:
    def __init__(self, name):
        self.name = name
        self.opened = True

    def close(self):
        self.opened = False

    def __del__(self):
        self.close()

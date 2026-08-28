_registry = []


class RegistryEntry:
    def __init__(self, name):
        self.name = name

    def cleanup(self):
        pass

    def __del__(self):
        self.cleanup()


def register(entry):
    _registry.append(entry)
    return entry


def registry_size():
    return len(_registry)

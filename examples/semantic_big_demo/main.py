from models.cache import Cache
from models.connection import Connection
from models.stats import Counter
from services.reporting import build_report
from services.scheduler import TaskQueue
from utils.registry import RegistryEntry, register, registry_size
from utils.timeutil import current_utc


def main() -> int:
    connection = Connection('db', 'localhost')
    connection.connect()

    cache = Cache()
    cache.put('a', 1)

    counter = Counter()
    for _ in range(5):
        counter.increment()

    task_queue = TaskQueue()
    task_queue.start()

    register(RegistryEntry('demo'))
    report = build_report(['a', 'b', 'c'])

    print('counter:', counter.snapshot())
    print('cache:', cache.get('a'))
    print('report total:', report['total'])
    print('utc:', current_utc())
    print('queue running:', task_queue.running)
    print('registry size:', registry_size())
    return 0


if __name__ == '__main__':
    main()

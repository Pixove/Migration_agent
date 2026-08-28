from models.cache import Cache
from models.connection import Connection
from models.session import Session
from models.stats import Counter
from services.events import EventBus
from services.reporting import build_report
from services.scheduler import TaskQueue
from services.worker import WorkerPool
from utils.logger import Logger
from utils.registry import RegistryEntry, register, registry_size
from utils.timeutil import current_utc, timestamp_utc


def main() -> int:
    connection = Connection('db', 'localhost')
    connection.connect()

    session = Session('worker-1')
    session.open()

    cache = Cache()
    cache.put('a', 1)
    cache.put('b', 2)

    counter = Counter()
    for _ in range(5):
        counter.increment()

    events = EventBus()
    events.subscribe('created', lambda payload: None)
    events.start()
    events.publish('created', {'id': 1})

    task_queue = TaskQueue()
    task_queue.start()

    workers = WorkerPool(size=2)
    workers.start()
    workers.submit(lambda: None)

    logger = Logger('demo')
    logger.info('boot complete')

    register(RegistryEntry('demo'))
    report = build_report(['a', 'b', 'c'])

    print('counter:', counter.snapshot())
    print('cache:', cache.get('a'))
    print('session opened:', session.opened)
    print('report total:', report['total'])
    print('utc:', current_utc())
    print('epoch utc:', timestamp_utc(1234567890))
    print('queue running:', task_queue.running)
    print('workers running:', workers.running)
    print('event bus running:', events.started)
    print('registry size:', registry_size())
    return 0


if __name__ == '__main__':
    main()

from services.counter import Counter
from utils.session import Session
from utils.timeutil import current_utc


def main() -> int:
    session = Session('demo')
    counter = Counter()
    for _ in range(3):
        counter.increment()

    print('counter:', counter.value)
    print('utc:', current_utc())
    print('session:', session.name)
    return 0


if __name__ == '__main__':
    main()

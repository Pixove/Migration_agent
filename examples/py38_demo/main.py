import sys

from models.stats import average, bounds
from models.user import User
from services.report import print_report
from utils.helper import flatten
from utils.timeutil import current_utc

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass


def main() -> int:
    user = User('张三', {'math': 95, 'english': 88})
    scores = list(user.scores.values())
    stats = {
        '平均分': average(scores),
        '最低分': float(bounds(scores)[0]),
        '最高分': float(bounds(scores)[1]),
    }
    print_report(user, stats)
    print('时间:', current_utc())
    print('扁平化:', flatten([[1, 2], [3]]))
    return 0


if __name__ == '__main__':
    main()

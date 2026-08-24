from typing import Dict


def print_report(user, stats: Dict[str, float]) -> None:
    print('用户:', user.name)
    for key, value in stats.items():
        print(key + ':', value)

from typing import List, Tuple


def average(values: List[int]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def bounds(values: List[int]) -> Tuple[int, int]:
    return (min(values), max(values))

from typing import List


def flatten(values: List[List[int]]) -> List[int]:
    result = []
    for group in values:
        result.extend(group)
    return result

from typing import Dict


class User:
    def __init__(self, name: str, scores: Dict[str, int]):
        self.name = name
        self.scores = scores

    def total(self) -> int:
        return sum(self.scores.values())

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BaseEntity(ABC):
    @property
    def hit_points(self) -> int:
        return self._hit_points

    @hit_points.setter
    def hit_points(self, value: int):
        if value < 0:
            value = 0
        elif value > self.max_hit_points:
            value = self.max_hit_points
        self._hit_points = value

    @property
    @abstractmethod
    def max_hit_points(self) -> int:
        pass

    def __post_init__(self):
        self.hit_points = self.max_hit_points

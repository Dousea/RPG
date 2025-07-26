from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import event
import modifier
import player


@dataclass
class Once:
    effect: Callable[[player.Player], Any]


@dataclass
class Event[T: event.Type]:
    effect: Callable[[T], modifier.Modifier | None]
    condition: Callable[[T], bool] = lambda _: True  # Default to always true

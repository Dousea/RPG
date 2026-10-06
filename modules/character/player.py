from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Imported lazily to break the cycle:
    # effect -> entity.player -> character.player -> effect
    from ..effect import AnyEffect


@dataclass
class PlayerTrait:
    """A trait that reacts to events through the effect pipeline (managers/events.py)."""

    id: str
    name: str
    description: str
    effects: list[AnyEffect]

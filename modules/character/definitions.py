"""Static definitions of occupations and traits (character-creation)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TraitDefinition:
    """`cost` is positive for a good trait (spends points) and negative for a bad one."""

    id: str
    name: str
    description: str
    cost: int
    profession_only: bool = False
    boosts: dict[str, int] = field(default_factory=dict[str, int])
    excludes: frozenset[str] = frozenset()
    granted_traits: tuple[str, ...] = ()
    recipes: tuple[str, ...] = ()


@dataclass(frozen=True)
class OccupationDefinition:
    """`cost` is positive when the occupation adds points and negative when it spends them."""

    id: str
    name: str
    cost: int
    granted_traits: tuple[str, ...] = ()
    boosts: dict[str, int] = field(default_factory=dict[str, int])


@dataclass(frozen=True)
class ClothingChoice:
    """The items offered at one body location; `chance` (percent) applies to random dressing."""

    chance: int
    items: tuple[str, ...]

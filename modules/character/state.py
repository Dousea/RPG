from enum import StrEnum


class Disposition(StrEnum):
    LOYAL = "loyal"
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    WARY = "wary"
    HOSTILE = "hostile"
    TERRIFIED = "terrified"
    HATED = "hated"


class Condition(StrEnum):
    POISONED = "poisoned"
    STUNNED = "stunned"
    BURNED = "burned"
    FROZEN = "frozen"
    PANIC = "panic"

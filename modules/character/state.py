from enum import StrEnum


class CharacterDisposition(StrEnum):
    LOYAL = "loyal"
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    WARY = "wary"
    HOSTILE = "hostile"
    TERRIFIED = "terrified"
    HATED = "hated"


class CharacterCondition(StrEnum):
    POISONED = "poisoned"
    STUNNED = "stunned"
    BURNED = "burned"
    FROZEN = "frozen"
    PANIC = "panic"

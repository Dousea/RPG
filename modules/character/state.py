from enum import StrEnum


class CharacterDisposition(StrEnum):
    LOYAL = "loyal"
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    WARY = "wary"
    HOSTILE = "hostile"
    TERRIFIED = "terrified"
    HATED = "hated"


class CharacterTrust(StrEnum):
    """How far one character will rely on another.

    The qualitative counterpart to the trust score, in the same spirit as
    CharacterDisposition is to affinity. Anything outside the simulation -- the
    prompt above all -- reads the band, never the integer, because a number is
    something no character could observe about another.
    """

    UNWAVERING = "unwavering"
    SOLID = "solid"
    TENTATIVE = "tentative"
    UNFORMED = "unformed"
    GUARDED = "guarded"
    BROKEN = "broken"


class CharacterCondition(StrEnum):
    POISONED = "poisoned"
    STUNNED = "stunned"
    BURNED = "burned"
    FROZEN = "frozen"
    PANIC = "panic"

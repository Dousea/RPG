from enum import StrEnum


class Condition(StrEnum):
    POISONED = "poisoned"
    STUNNED = "stunned"
    BURNED = "burned"
    FROZEN = "frozen"
    PANIC = "panic"

"""The body parts each kind of clothing covers (clothing).

Coverage that reaches the back is folded into `TORSO_UPPER`; a bag covers only
the back, so it covers nothing here.
"""

from modules.body.parts import BodyPart

_P = BodyPart
_TORSO = {_P.TORSO_UPPER, _P.TORSO_LOWER}
_SHORTS = {_P.GROIN, _P.UPPERLEG_L, _P.UPPERLEG_R}
_SHIRT = _TORSO | {_P.UPPERARM_L, _P.UPPERARM_R}
_LONG_SLEEVES = _SHIRT | {_P.FOREARM_L, _P.FOREARM_R}

CLOTHING_COVERAGE: dict[str, frozenset[BodyPart]] = {  # clothing
    "apron": frozenset(_TORSO | {_P.UPPERLEG_L, _P.UPPERLEG_R}),
    "shirt_no_sleeves": frozenset(_TORSO),
    "jumper_no_sleeves": frozenset(_TORSO),
    "shirt": frozenset(_SHIRT),
    "shirt_long_sleeves": frozenset(_LONG_SLEEVES),
    "jumper": frozenset(_LONG_SLEEVES),
    "jacket": frozenset(_LONG_SLEEVES | {_P.NECK}),
    "long_jacket": frozenset(_LONG_SLEEVES | {_P.NECK} | _SHORTS),
    "shorts_short": frozenset(_SHORTS),
    "trousers": frozenset(_SHORTS | {_P.LOWERLEG_L, _P.LOWERLEG_R}),
    "shoes": frozenset({_P.FOOT_L, _P.FOOT_R}),
    "full_helmet": frozenset({_P.HEAD}),
    "bag": frozenset(),
    "hands": frozenset({_P.HAND_L, _P.HAND_R}),
    "head": frozenset({_P.HEAD}),
    "neck": frozenset({_P.NECK}),
    "groin": frozenset({_P.GROIN}),
    "upper_body": frozenset({_P.TORSO_UPPER}),
    "lower_body": frozenset({_P.TORSO_LOWER}),
    "lower_legs": frozenset({_P.LOWERLEG_L, _P.LOWERLEG_R}),
    "upper_legs": frozenset({_P.UPPERLEG_L, _P.UPPERLEG_R}),
    "lower_arms": frozenset({_P.FOREARM_L, _P.FOREARM_R}),
    "upper_arms": frozenset({_P.UPPERARM_L, _P.UPPERARM_R}),
    "hand_l": frozenset({_P.HAND_L}),
    "hand_r": frozenset({_P.HAND_R}),
    "forearm_l": frozenset({_P.FOREARM_L}),
    "forearm_r": frozenset({_P.FOREARM_R}),
    "upperarm_l": frozenset({_P.UPPERARM_L}),
    "upperarm_r": frozenset({_P.UPPERARM_R}),
    "upperleg_l": frozenset({_P.UPPERLEG_L}),
    "upperleg_r": frozenset({_P.UPPERLEG_R}),
    "lowerleg_l": frozenset({_P.LOWERLEG_L}),
    "lowerleg_r": frozenset({_P.LOWERLEG_R}),
    "foot_l": frozenset({_P.FOOT_L}),
    "foot_r": frozenset({_P.FOOT_R}),
}


def covered_parts(*coverage_names: str) -> frozenset[BodyPart]:
    """The union of the named coverages (a clothing item may list several)."""
    parts: set[BodyPart] = set()
    for name in coverage_names:
        parts |= CLOTHING_COVERAGE[name]
    return frozenset(parts)

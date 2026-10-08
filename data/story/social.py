"""How talking to people moves how they regard the player (llm-contract).

The keys are the closed labels defined in `modules/action/parser.py`
(`TALK_APPROACH_LABELS`); tests/test_social.py checks the two agree.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Approach:
    """A `TALK` approach: what the parser is told it means, its deltas and its fact."""

    gloss: str
    affection: int
    trust: int
    fact: str


@dataclass(frozen=True)
class Delta:
    affection: int
    trust: int


SPEECH_FACT = '{name} says: "{speech}"'

TALK_APPROACHES: dict[str, Approach] = {  # llm-contract
    "chat": Approach(
        "small talk, jokes, asking how they are, anything else", 2, 0, "{name} chats with {npc}."
    ),
    "compliment": Approach("praise, thanks, admiration", 2, 0, "{name} compliments {npc}."),
    "flirt": Approach("romantic interest", 3, 0, "{name} flirts with {npc}."),
    "confide": Approach(
        "sharing something personal or vulnerable", 1, 2, "{name} confides in {npc}."
    ),
    "comfort": Approach("reassurance, sympathy, support", 2, 1, "{name} comforts {npc}."),
    "argue": Approach("disagreeing, criticising, refusing", -2, -1, "{name} argues with {npc}."),
    "insult": Approach("mockery, rudeness", -5, -3, "{name} insults {npc}."),
    "threaten": Approach("threats, intimidation", -5, -8, "{name} threatens {npc}."),
}
FLIRT_INELIGIBLE_AFFECTION = -1  # llm-contract: flirting with an NPC who is not romance eligible
GUARDED_POSITIVE_FACTOR = 0.5  # llm-contract: positive deltas for a Hostile or Hated NPC
GIVE_FOOD_DELTA = Delta(affection=4, trust=3)  # llm-contract
GIVE_OTHER_DELTA = Delta(affection=2, trust=2)  # llm-contract
REQUEST_FOLLOW_TRUST_DIVISOR = 40  # llm-contract: trust points; chance is clamp(trust / 40, 0, 1)
REQUEST_GIVE_TRUST_OFFSET = 10  # llm-contract: trust points
REQUEST_GIVE_TRUST_DIVISOR = 40  # llm-contract: chance is clamp((trust - 10) / 40, 0, 1)
REQUEST_REFUSAL_LOCKOUT_MIN = (
    60  # llm-contract: game minutes before a refused request can be asked again
)

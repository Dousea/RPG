"""Things an NPC can tell the player when asked (spec 10, Topics)."""

from dataclasses import dataclass

from modules.character.state import CharacterTrust
from modules.story import Condition, OutbreakStarted


@dataclass(frozen=True)
class Topic:
    """`gloss` is the line the parser sees under the NPC; `requires` hides the topic until it holds."""

    topic_id: str
    npc_id: str
    gloss: str
    requires: Condition | None
    min_trust: CharacterTrust
    fact: str
    discovers: str | None


TOPICS: dict[str, Topic] = {  # spec 10
    "outbreak_news": Topic(
        topic_id="outbreak_news",
        npc_id="npc_jen",
        gloss="what the news says about the outbreak",
        requires=OutbreakStarted(),
        min_trust=CharacterTrust.TENTATIVE,
        fact=(
            "The news is calling it the zombie infection. Bites spread it, and the ones who "
            "die from it get back up."
        ),
        discovers="apocalypse_cause",
    ),
}

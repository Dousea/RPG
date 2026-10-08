"""Things an NPC can tell the player when asked (llm-contract: Topics)."""

from dataclasses import dataclass

from modules.character.state import CharacterTrust
from modules.story.beats import Condition, FlagDiscovered, OutbreakStarted


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


TOPICS: dict[str, Topic] = {  # llm-contract
    "outbreak_news": Topic(
        topic_id="outbreak_news",
        npc_id="npc_jen",
        gloss="what the news says about the outbreak",
        requires=OutbreakStarted(),
        min_trust=CharacterTrust.TENTATIVE,
        fact="The news calls it the Ashby fever. Bites spread it, and the ones who die of it get back up.",
        discovers="apocalypse_cause",
    ),
    "clinic_regulars": Topic(
        topic_id="clinic_regulars",
        npc_id="npc_jen",
        gloss="what Jen has noticed about the clinic's regulars",
        requires=None,
        min_trust=CharacterTrust.TENTATIVE,
        fact=(
            "The clinic's study people came in on payday, a bandage in the crook of every arm. "
            "Lately they'd looked grey, and one fell asleep at the counter."
        ),
        discovers="clinic_odd",
    ),
    "emma_brother": Topic(
        topic_id="emma_brother",
        npc_id="npc_emma",
        gloss="Emma's brother",
        requires=OutbreakStarted(),
        min_trust=CharacterTrust.SOLID,
        fact=(
            "Her brother Danny took the clinic's paid study for rent money. "
            "He stopped answering two days before the sirens."
        ),
        discovers="trial_rumour",
    ),
    "roof_tank": Topic(
        topic_id="roof_tank",
        npc_id="npc_marcus",
        gloss="the building's water tank",
        requires=FlagDiscovered("cordon"),
        min_trust=CharacterTrust.SOLID,
        fact=(
            "The roof tank holds the building's water after the mains go. "
            "The valve's in the boiler room; he has the key."
        ),
        discovers="roof_tank",
    ),
    "jen_mother": Topic(
        topic_id="jen_mother",
        npc_id="npc_jen",
        gloss="Jen's mother at the hospital",
        requires=OutbreakStarted(),
        min_trust=CharacterTrust.TENTATIVE,
        fact=(
            "Her mother is a nurse at St. Agnes. Her last texts said the first fever patients "
            "all had the same bandage in the crook of the arm, and that staff were told to say "
            "nothing. Then they stopped."
        ),
        discovers="hospital_texts",
    ),
    "marcus_port": Topic(
        topic_id="marcus_port",
        npc_id="npc_marcus",
        gloss="what Marcus heard from the port",
        requires=FlagDiscovered("apocalypse_cause"),
        min_trust=CharacterTrust.TENTATIVE,
        fact=(
            "He worked the container terminal for twenty years. A friend still there says the "
            "quarantined ship's crew had a common flu, and not one of them has turned."
        ),
        discovers="ship_doubt",
    ),
    "marcus_tenants": Topic(
        topic_id="marcus_tenants",
        npc_id="npc_marcus",
        gloss="the neighbours who left",
        requires=None,
        min_trust=CharacterTrust.TENTATIVE,
        fact=(
            "The Novaks down the hall left in a hurry the week before the sirens: Tomas had a "
            "fever that wouldn't break, and his wife drove him to St. Agnes. They never came back."
        ),
        discovers="novaks_left",
    ),
    "emma_flyers": Topic(
        topic_id="emma_flyers",
        npc_id="npc_emma",
        gloss="the work Emma did for the study",
        requires=FlagDiscovered("trial_rumour"),
        min_trust=CharacterTrust.SOLID,
        fact=(
            "She designed the study's recruitment flyers for a client called Velloran: "
            '"Paid volunteers wanted. Earn while you heal." Danny saw them on her desk and '
            "signed up."
        ),
        discovers="study_flyers",
    ),
}

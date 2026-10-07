"""Ready-made characters the player can pick instead of building one (spec 07)."""

from modules.character.appearance import Appearance, Gender
from modules.character.build import CharacterBuild

ORTON_POINTS_LEFT = 7  # spec 07

ORTON = CharacterBuild(
    appearance=Appearance(
        forename="Orton",
        surname="",
        gender=Gender.MALE,
        skin_tone=2,
        hair_style="short",
        hair_colour="brown",
        beard_style="",
        backstory="Just moved into apartment 3B in Portland.",
    ),
    occupation_id="unemployed",
    job_title="Software Developer",
    traits=("hemophobic", "shortsighted", "fastreader", "fastlearner"),
    outfit=("item_tshirt", "item_hoodie", "item_jeans", "item_ankle_socks", "item_trainers"),
)

PRESETS: dict[str, CharacterBuild] = {"orton": ORTON}

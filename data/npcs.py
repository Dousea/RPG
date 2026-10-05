"""Starting NPC roster.

Each NPC is placed in the zone that covers their spot: the hallway and lobby
both fall under `zone_building`, and the coffee shop under `zone_neighborhood`.
"""

from modules.character.faction import CharacterFaction
from modules.entity.npc import NpcEntity

# How each NPC feels about the player at the start, keyed by npc_id. The
# direction matters: relationships are stored source -> target, and everything
# that reads them (the prompt's disposition line, UPDATE_RELATIONSHIP) asks how
# the NPC regards the player, so the NPC is the source.
STARTING_RELATIONSHIPS: dict[str, dict[str, int]] = {
    "npc_emma": {"affection": 0, "trust": 5},
    "npc_marcus": {"affection": 0, "trust": 3},
    "npc_jen": {"affection": 0, "trust": 2},
}


def build_starting_npcs() -> dict[str, NpcEntity]:
    """Build a fresh NPC roster.

    Returns new instances on every call -- NpcEntity is mutable game state, so a
    module-level dict would leak one game's mutations into the next.
    """
    npcs = [
        NpcEntity(
            npc_id="npc_emma",
            name="Emma",
            description=(
                "A friendly woman in her late twenties with shoulder-length brown "
                "hair. She lives in the apartment next door and works as a graphic "
                "designer."
            ),
            current_location_id="zone_building",
            age=28,
            faction=CharacterFaction.SURVIVORS,
            personality=["outgoing", "creative", "helpful"],
            status=["friendly", "curious about new neighbor"],
            romance_eligible=True,
        ),
        NpcEntity(
            npc_id="npc_marcus",
            name="Marcus",
            description=(
                "The building superintendent, a man in his fifties with graying "
                "hair and a practical demeanor. He carries a toolbox and seems "
                "knowledgeable about the building."
            ),
            current_location_id="zone_building",
            age=52,
            faction=CharacterFaction.SURVIVORS,
            personality=["practical", "reliable", "quiet"],
            status=["helpful", "responsible"],
            romance_eligible=False,
        ),
        NpcEntity(
            npc_id="npc_jen",
            name="Jen",
            description=(
                "A barista at the local coffee shop, early twenties with bright "
                "eyes and an infectious smile. She seems to know most of the "
                "regulars by name."
            ),
            current_location_id="zone_neighborhood",
            age=23,
            faction=CharacterFaction.NEUTRAL,
            personality=["bubbly", "social", "observant"],
            status=["cheerful", "energetic"],
            romance_eligible=True,
        ),
    ]
    return {npc.npc_id: npc for npc in npcs}

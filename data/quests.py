"""Starting quest roster.

Exposed as a builder, like `data/locations.py` and `data/npcs.py`: `QuestState`
is mutable game state (objectives get completed at runtime), so a shared
module-level dict would leak one game's progress into the next game after a
reset.

Objective keys are matched exactly by `SimulationCore._advance_quests` --
"take:<item_id>", "reach:<location_id>", "discover:<flag_name>",
"defeat:<npc_id>", and "npc_status:<npc_id>:<status>". They must line up with
real ids in `data/items.py`, `data/locations.py`, and `data/npcs.py`, or the
objective can never complete.
"""

from modules.quest import QuestState


def build_starting_quests() -> dict[str, QuestState]:
    """Build a fresh quest roster. Returns new instances on every call."""
    quests = [
        QuestState(
            quest_id="quest_storage_room",
            title="Secure the Storage Room",
            objectives=[
                "take:item_storage_key",
                "reach:location_id_storage",
            ],
            objective_labels={
                "take:item_storage_key": "Find the storage key",
                "reach:location_id_storage": "Get into the storage room",
            },
        ),
        QuestState(
            quest_id="quest_marcus_trust",
            title="Earn the Super's Trust",
            objectives=["npc_status:npc_marcus:trusts_orton"],
            objective_labels={
                # Deliberately says "the super," not "Marcus": Orton hasn't
                # necessarily learned the super's name yet just because this
                # quest exists, and the narrator prompt renders this
                # unconditionally regardless of who's in the room -- see
                # docs/11-knowledge-firewall.md.
                "npc_status:npc_marcus:trusts_orton": "Earn the building super's trust",
            },
        ),
        QuestState(
            quest_id="quest_understand_the_crisis",
            title="Understand What's Happening",
            objectives=["discover:apocalypse_cause"],
            objective_labels={
                "discover:apocalypse_cause": "Find out what's really going on outside",
            },
        ),
    ]
    return {quest.quest_id: quest for quest in quests}

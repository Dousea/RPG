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

Two of those namespaces are *open*: unlike item/location/NPC ids, which the
engine owns and enumerates, flag names and NPC statuses are whatever the
parser model invents from the player's typing. An objective keyed on an
invented name can never fire, so the story-significant names are declared
here as STORY_FLAGS/NPC_STATUSES, taught to the parser verbatim
(`adapters/llm.py`), and checked against the roster by tests/test_quests.py.
Adding a `discover:`/`npc_status:` objective means adding its name here too.

Quest titles and objective labels are rendered into the narrator prompt
unconditionally, with no check for who is in the room -- unlike every other
prompt section. Write them so they never reveal something Orton hasn't
learned yet: name roles, not people ("the building super", not "Marcus").
See docs/11-knowledge-firewall.md.
"""

from modules.quest import QuestState

# Flag names worth tracking, as name -> when the parser should emit it. The
# parser is told these verbatim; anything else it invents still works as an
# incidental fact, it just can't complete an objective.
STORY_FLAGS: dict[str, str] = {
    "apocalypse_cause": "Orton learns what actually caused the outbreak",
}

# NPC status names with mechanical meaning, as name -> when to apply it.
NPC_STATUSES: dict[str, str] = {
    "trusts_orton": "an NPC decides Orton is someone they can rely on",
}


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
                # "the super", not "Marcus" -- see the firewall note in this
                # module's docstring.
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

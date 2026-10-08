"""Starting quest roster.

Exposed as a builder, like `data/locations.py` and `data/npcs.py`: `QuestState`
is mutable game state (objectives get completed at runtime), so a shared
module-level dict would leak one game's progress into the next game after a
reset.

Objective keys are matched exactly by `SimulationCore._advance_quests` --
"take:<item_id>", "take:weapon" (any melee weapon), "reach:<zone_id>", "discover:<flag_name>",
"defeat:<npc_id>", and "npc_status:<npc_id>:<status>". They must line up with
real ids in `data/items.py`, `data/locations.py`, and `data/npcs.py`, or the
objective can never complete.

`discover:` and `npc_status:` objectives are produced by the engine alone: a topic
that discovers a flag (`data/topics.py`) and a derived status (`trusts_player`,
llm-contract), so their names must match those producers (tests/test_quests.py).

Quest titles and objective labels are rendered into the narrator prompt
unconditionally, with no check for who is in the room -- unlike every other
prompt section. Write them so they never reveal something the player hasn't
learned yet: name roles, not people ("the building super", not "Marcus").
See docs/architecture/knowledge-firewall.md.
"""

from modules.story.quest import QuestState

TAKE_ANY_WEAPON = "take:weapon"


def build_starting_quests() -> dict[str, QuestState]:
    """Build a fresh quest roster. Returns new instances on every call."""
    quests = [
        QuestState(
            quest_id="quest_supply_run",
            title="Make a Supply Run",
            objectives=["reach:zone_neighborhood", TAKE_ANY_WEAPON],
            objective_labels={
                "reach:zone_neighborhood": "Make it out to the neighborhood's shops",
                TAKE_ANY_WEAPON: "Find something to defend yourself with",
            },
        ),
        QuestState(
            quest_id="quest_marcus_trust",
            title="Earn the Super's Trust",
            objectives=["npc_status:npc_marcus:trusts_player"],
            objective_labels={
                # "the super", not "Marcus" -- see the firewall note in this
                # module's docstring.
                "npc_status:npc_marcus:trusts_player": "Earn the building super's trust",
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

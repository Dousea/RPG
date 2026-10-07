"""Action Validator: precondition checks only, no state mutation.

This is the piece docs/01-engine-authority.md calls the Action Validator. It
answers "is this legal" for every proposed action *before* the Simulation
Core decides "what happens" and long before the narrator writes a word about
it -- the inversion that makes the engine authoritative instead of the old
narrate-then-vet order.

Every check here is read-only. `Accepted.resolved` carries whatever the check
already looked up (the target NPC, the item entity, the destination zone) as a
`modules.resolution` type, so
`managers/simulation.py` never has to re-resolve them and never has to
re-derive the reason something was legal.
"""

import re
from dataclasses import dataclass

from data import barriers as barrier_k
from data import body as body_k
from data import exercises as ex
from data import survival
from data import zombie_lore as zombie_k
from data.body_locations import EXCLUSIVE_LOCATIONS
from data.clock import (
    SLEEP_CAP_MIN,
    TIME_OF_DAY_START,
    WAIT_CAP_MIN,
    minutes_until,
)
from data.items import ITEMS
from data.topics import TOPICS
from managers.barriers import barriers_between, carried_entities, thumpable_for
from managers.body import limp_factor
from managers.combat import held_entity, held_slots
from managers.exercise import endurance_level
from managers.first_aid import (
    bandage_items,
    disinfectant_items,
    find_part,
    most_needed_part,
    part_word,
)
from managers.game import MAX_PLACE_LENGTH, GameManager
from managers.locations import BARE_DIRECTIONS, connection_target
from managers.loot import find_content, perceived_corpses, with_article
from managers.social import locked_out
from managers.stats.status_effects import status_effect_level
from managers.story import visible_topics
from managers.zombies import approach_minutes, perceived_now
from modules.action.parser import GOAL_HORIZON_LABELS, TALK_APPROACH_LABELS
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AskAction,
    AttackAction,
    BandageAction,
    BarricadeAction,
    CloseAction,
    DisinfectAction,
    DropAction,
    Duration,
    EquipAction,
    ExerciseAction,
    GiveAction,
    MoveAction,
    OpenAction,
    RemoveBandageAction,
    RemoveGoalAction,
    SearchAction,
    ShoutAction,
    ShoveAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TakeOffAction,
    TalkAction,
    UnbarricadeAction,
    UnequipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.corpse import CorpseEntity
from modules.entity.npc import NpcEntity
from modules.entity.zombie import ZombieState
from modules.item import (
    AppliableItem,
    ClothingItem,
    ConsumableItem,
    HoldableItem,
    MedicalItem,
)
from modules.pace import Pace
from modules.resolution import (
    BarricadeKit,
    CorpseItem,
    ExercisePlan,
    FirstAidTarget,
    HeldItem,
    MoveBlocked,
    MoveToSpot,
    MoveToZone,
    NpcItem,
    NpcTopic,
    PryTarget,
    Resolution,
    ShuffleInZone,
    StayPut,
    TargetBarrier,
    TargetCorpse,
    TargetNpc,
    TargetZombie,
    TimeSpan,
)
from modules.stats import CharacterStat, StatusEffect

GOAL_HORIZONS = GOAL_HORIZON_LABELS

ZOMBIE_ID_PATTERN = re.compile(r"z\d+", re.IGNORECASE)

# Names that mean "the nearest corpse".
CORPSE_WORDS = frozenset({"corpse", "the corpse", "a corpse", "body", "the body", "a body"})

# Names that mean "the nearest zombie".
ZOMBIE_WORDS = frozenset({"zombie", "the zombie", "a zombie", "zombies", "the zombies"})


@dataclass
class Accepted:
    action: AnyAction
    resolved: Resolution = None

    def expect[R](self, kind: type[R]) -> R:
        """`resolved` as a `kind`; anything else is a validator bug."""
        if not isinstance(self.resolved, kind):
            raise TypeError(
                f"{type(self.action).__name__} resolved to {self.resolved!r}, "
                f"expected {kind.__name__}"
            )
        return self.resolved


@dataclass
class Rejected:
    action: AnyAction
    reason: str


ValidationResult = Accepted | Rejected


class ActionValidator:
    def __init__(self, manager: GameManager):
        self.manager = manager
        self._talked_to: set[str] = set()

    @property
    def _name(self) -> str:
        return self.manager.player.appearance.forename

    def _keeps_keys(self) -> str:
        looks = self.manager.player.appearance
        return f"{self._name} keeps {looks.possessive} keys on {looks.object}."

    def validate_all(self, actions: list[AnyAction]) -> list[ValidationResult]:
        return [self.validate(action) for action in actions]

    def validate(self, action: AnyAction) -> ValidationResult:
        if self.manager.narrative.game_over:
            # The one sanctioned exception to "MOVE_TO never fails" (and
            # every other action): once the player is dead nothing more can
            # happen, so every action this turn and beyond is refused rather
            # than dispatched. SimulationCore._check_player_death is the only
            # place that sets this flag; the LLM cannot trigger it.
            return Rejected(action, f"{self._name} is dead; nothing more can happen.")
        handler = self._VALIDATORS.get(action.verb)
        if handler is None:
            return Rejected(action, f"No validator registered for {type(action).__name__}.")
        return handler(self, action)

    # === Movement ===

    def _walk_pace(self, action: MoveAction) -> Pace:
        if action.run:
            return Pace.RUN
        return Pace.SNEAK if self.manager.player.sneaking else Pace.WALK

    def _validate_stance(self, action: StanceAction) -> ValidationResult:
        return Accepted(action)

    def _validate_move(self, action: MoveAction) -> ValidationResult:
        """Decide what a MOVE_TO *means*. This never rejects.

        A named zone is reachable from anywhere by walking the connection
        graph (`GameManager.zone_path`); adjacency is not required. A locked
        door along that walk stops the player short of the target zone, but
        the move still resolves to a place (the door), not a refusal -- the
        walk is gated hop by hop so a lock can't be skipped, yet it never
        dead-ends in "you can't do that."

        Anything that isn't a recognized zone, connection, or bare direction
        becomes a free-text spot inside the zone the player is already in.
        The result is one of the five `MoveOutcome` types.
        """
        manager = self.manager
        current = manager.current_location
        raw = action.destination.strip().strip("\"'.,;:")
        if not raw:
            return Accepted(action, StayPut(current))

        folded = raw.casefold()

        # Order: (1) a direction synonym that names a real connection of
        # the current zone wins outright; (2) otherwise a bare direction with
        # no destination behind it is a shuffle, checked before the alias/
        # whole-word resolution below can accidentally claim it (e.g. a zone
        # whose alias list happens to contain a direction word); (3)
        # otherwise fall through to full resolution.
        target = connection_target(folded, current, manager.world.locations)
        if target is None:
            if folded in BARE_DIRECTIONS:
                return Accepted(action, ShuffleInZone(current, raw))
            target = manager.resolve_location(raw)

        if target is None:
            return Accepted(action, MoveToSpot(current, raw[:MAX_PLACE_LENGTH]))

        # "the pharmacy" and "the kitchen" resolve to a zone via an alias, but
        # the words themselves are the interesting part -- they are where in
        # the zone the player actually is. Keep them as the spot unless the
        # model named the zone itself, or just gave a direction.
        place = (
            ""
            if folded in (target.id.casefold(), target.name.casefold()) or folded in BARE_DIRECTIONS
            else raw[:MAX_PLACE_LENGTH]
        )

        if target.id == current.id:
            return Accepted(action, MoveToSpot(current, place))

        path = manager.zone_path(current.id, target.id)
        if path is None:
            # Disconnected map -- not possible with the shipped content, but
            # zone_path can express it, so this must not raise or refuse.
            return Accepted(action, MoveToSpot(current, place))

        hop_from = current
        for hop_id in path:
            stopped = self._stopping_barrier(hop_from.id, hop_id)
            if stopped is not None:
                barrier, place = stopped
                return Accepted(
                    action,
                    MoveBlocked(
                        location=hop_from,
                        place=place[:MAX_PLACE_LENGTH],
                        hops=path.index(hop_id),
                        target=target,
                        pace=self._walk_pace(action),
                        barrier=barrier,
                    ),
                )
            hop_from = manager.world.locations[hop_id]

        return Accepted(
            action, MoveToZone(target, place, hops=len(path), pace=self._walk_pace(action))
        )

    def _stopping_barrier(self, here_id: str, there_id: str) -> tuple[BarrierEntity, str] | None:
        """The barrier on a hop that ends the walk, and where the player stands then.

        Planks stop the walk on either side; a locked door stops anyone outside it without the key.
        """
        there = self.manager.world.locations[there_id]
        for barrier in barriers_between(self.manager.world, here_id, there_id):
            if barrier.total_planks:
                return barrier, f"at the barricaded {barrier.kind.value}"
            if barrier.open or barrier.broken:
                continue
            outside = here_id != barrier.inside_zone
            if barrier.locked and outside and not self._has_key(barrier.key_id):
                return barrier, f"at the locked {barrier.kind.value} to {there.name}"
        return None

    def _has_key(self, key_id: str | None) -> bool:
        if key_id is None:
            return False
        return any(entity.item.id == key_id for entity in self.manager.player.inventory)

    # === Items ===

    def _validate_take(self, action: TakeAction) -> ValidationResult:
        manager = self.manager
        if action.from_name is not None:
            return self._validate_take_from(action, action.from_name)
        entity = manager._find_item_entity(manager._ground_items(), action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' here to take.")
        if len(manager.player.inventory) >= manager.player.max_inventory_size:
            return Rejected(action, "Inventory is full.")
        return Accepted(action, HeldItem(entity))

    def _validate_take_from(self, action: TakeAction, source: str) -> ValidationResult:
        manager = self.manager
        player = manager.player
        if player.asleep:
            return Rejected(action, zombie_k.ASLEEP_REFUSAL.format(name=self._name))
        corpse = self._corpse_target(source)
        if corpse is None:
            return Rejected(action, zombie_k.NO_SUCH_CORPSE.format(target=source))
        if not corpse.searched:
            return Rejected(
                action, zombie_k.NOT_SEARCHED.format(name=self._name, corpse=corpse.corpse_id)
            )
        entity = find_content(corpse, action.item_name)
        if entity is None:
            return Rejected(
                action,
                zombie_k.NOT_ON_CORPSE.format(corpse=corpse.corpse_id, item=action.item_name),
            )
        if len(player.inventory) >= player.max_inventory_size:
            return Rejected(action, "Inventory is full.")
        return Accepted(action, CorpseItem(corpse.corpse_id, entity))

    def _validate_search(self, action: SearchAction) -> ValidationResult:
        manager = self.manager
        if manager.player.asleep:
            return Rejected(action, zombie_k.ASLEEP_REFUSAL.format(name=self._name))
        corpse = self._corpse_target(action.target_name)
        if corpse is None:
            return Rejected(action, zombie_k.NO_SUCH_CORPSE.format(target=action.target_name))
        if corpse.searched:
            return Rejected(
                action, zombie_k.ALREADY_SEARCHED.format(name=self._name, corpse=corpse.corpse_id)
            )
        minutes = approach_minutes(corpse.gap, limp_factor(manager.player))
        return Accepted(action, TargetCorpse(corpse.corpse_id, minutes))

    def _corpse_target(self, name: str) -> CorpseEntity | None:
        """The perceived body `name` points at: its id, or the nearest for "corpse"."""
        needle = name.strip().casefold()
        seen = perceived_corpses(self.manager)
        if needle in CORPSE_WORDS:
            return min(seen, key=lambda c: (c.gap, int(c.corpse_id[1:])), default=None)
        return next((c for c in seen if c.corpse_id == needle), None)

    def _validate_drop(self, action: DropAction) -> ValidationResult:
        entity = self.manager._find_item_entity(self.manager.player.inventory, action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to drop.")
        if self._is_door_key(entity.item.id):
            return Rejected(action, self._keeps_keys())
        return Accepted(action, HeldItem(entity))

    def _validate_wear(self, action: WearAction) -> ValidationResult:
        player = self.manager.player
        entity = self.manager._find_item_entity(player.inventory, action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to wear.")
        item = entity.item
        if not isinstance(item, ClothingItem):
            return Rejected(action, f"{item.name} cannot be worn.")
        occupant = player.worn.get(item.body_location)
        if occupant is not None:
            return Rejected(
                action,
                f"{self._name} is already wearing {with_article(occupant.item.name)} there.",
            )
        blocked = EXCLUSIVE_LOCATIONS.get(item.body_location, frozenset())
        for location, worn in player.worn.items():
            if location in blocked:
                return Rejected(
                    action, f"{self._name} cannot wear {item.name} while wearing {worn.item.name}."
                )
        return Accepted(action, HeldItem(entity))

    def _validate_take_off(self, action: TakeOffAction) -> ValidationResult:
        player = self.manager.player
        entity = self.manager._find_item_entity(list(player.worn.values()), action.item_name)
        if entity is None:
            return Rejected(action, f"{self._name} is not wearing '{action.item_name}'.")
        if len(player.inventory) >= player.max_inventory_size:
            return Rejected(action, "Inventory is full.")
        return Accepted(action, HeldItem(entity))

    def _is_door_key(self, item_id: str) -> bool:
        """Whether `item_id` is the `key_id` of any barrier anywhere in the world --
        engine-owned, not hard-coded to `item_apartment_key`. Dropping (or duplicating) the key
        could strand the player outside their own apartment."""
        return any(barrier.key_id == item_id for barrier in self.manager.world.barriers.values())

    def _validate_use_item(self, action: UseItemAction) -> ValidationResult:
        entity = self.manager._find_item_entity(self.manager.player.inventory, action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to use.")
        item = entity.item
        if isinstance(item, MedicalItem):
            if item.painkiller or item.reduce_infection_power > 0:
                return Accepted(action, HeldItem(entity))
            if item.bandage_power > 0 or item.alcohol_power > 0:
                return Rejected(action, body_k.USE_HINT)
        if not isinstance(item, (ConsumableItem, AppliableItem)):
            return Rejected(action, f"{item.name} cannot be used this way.")
        return Accepted(action, HeldItem(entity))

    def _validate_equip(self, action: EquipAction) -> ValidationResult:
        player = self.manager.player
        entity = self.manager._find_item_entity(player.inventory, action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to hold.")
        item = entity.item
        if not isinstance(item, HoldableItem):
            return Rejected(action, f"{item.name} cannot be held.")
        if entity.broken:
            return Rejected(action, f"The {item.name} is broken.")
        for slot in held_slots(item):
            occupant = player.equipment.get(slot)
            if occupant is not None:
                return Rejected(
                    action, f"{self._name} is already holding the {occupant.item.name}."
                )
        return Accepted(action, HeldItem(entity))

    def _validate_unequip(self, action: UnequipAction) -> ValidationResult:
        player = self.manager.player
        held = held_entity(player)
        needle = action.item_name.strip().casefold()
        if held is None or needle not in (held.item.name.casefold(), held.item.id.casefold()):
            return Rejected(action, f"{self._name} is not holding '{action.item_name}'.")
        if len(player.inventory) >= player.max_inventory_size:
            return Rejected(action, "Inventory is full.")
        return Accepted(action, HeldItem(held))

    # === First aid ===

    def _asleep_refusal(self) -> str:
        return f"{self._name} is asleep." if self.manager.player.asleep else ""

    def _no_such_part(self, action: AnyAction, name: str) -> Rejected:
        return Rejected(action, f"{self._name} has no '{name}'.")

    def _validate_bandage(self, action: BandageAction) -> ValidationResult:
        player = self.manager.player
        if refusal := self._asleep_refusal():
            return Rejected(action, refusal)
        if action.part_name:
            found = find_part(action.part_name)
            if found is None:
                return self._no_such_part(action, action.part_name)
            part = found
        else:
            picked = most_needed_part(player)
            if picked is None:
                return Rejected(action, f"{self._name} has nothing to bandage.")
            part = picked
        state = player.body[part]
        word = part_word(part)
        if not state.injured:
            return Rejected(action, f"The {word} isn't hurt.")
        if state.bandaged:
            return Rejected(action, f"The {word} already has a bandage. Remove it first.")
        candidates = bandage_items(player)
        if action.item_name:
            entity = self.manager._find_item_entity(player.inventory, action.item_name)
            if entity is None:
                return Rejected(action, f"No '{action.item_name}' in inventory to bandage with.")
            if entity not in candidates:
                return Rejected(action, f"{entity.item.name} is not a bandage.")
        elif candidates:
            entity = candidates[0]
        else:
            return Rejected(action, f"{self._name} has nothing to bandage with.")
        return Accepted(action, FirstAidTarget(part, entity))

    def _validate_remove_bandage(self, action: RemoveBandageAction) -> ValidationResult:
        player = self.manager.player
        if refusal := self._asleep_refusal():
            return Rejected(action, refusal)
        part = find_part(action.part_name)
        if part is None:
            return self._no_such_part(action, action.part_name)
        if not player.body[part].bandaged:
            return Rejected(action, f"The {part_word(part)} has no bandage.")
        if len(player.inventory) >= player.max_inventory_size:
            return Rejected(action, "Inventory is full.")
        return Accepted(action, FirstAidTarget(part))

    def _validate_disinfect(self, action: DisinfectAction) -> ValidationResult:
        player = self.manager.player
        if refusal := self._asleep_refusal():
            return Rejected(action, refusal)
        part = find_part(action.part_name)
        if part is None:
            return self._no_such_part(action, action.part_name)
        state = player.body[part]
        word = part_word(part)
        if not state.injured:
            return Rejected(action, f"The {word} isn't hurt.")
        if state.bandaged:
            return Rejected(action, f"The {word} is bandaged. Remove it first.")
        candidates = disinfectant_items(player)
        if action.item_name:
            entity = self.manager._find_item_entity(player.inventory, action.item_name)
            if entity is None:
                return Rejected(action, f"No '{action.item_name}' in inventory to disinfect with.")
            if entity not in candidates:
                return Rejected(action, f"{entity.item.name} cannot disinfect a wound.")
        elif candidates:
            entity = candidates[0]
        else:
            return Rejected(action, f"{self._name} has nothing to disinfect with.")
        return Accepted(action, FirstAidTarget(part, entity))

    # === Doors, windows and planks ===

    def _find_barrier(self, name: str) -> BarrierEntity | None:
        """The barrier `name` points at: its id, its name or an alias, those of this zone first."""
        needle = name.strip().strip("\"'.,;:").casefold()
        needle = needle.removeprefix("the ").removeprefix("my ").strip()
        if not needle:
            return None
        here = self.manager.player.current_location_id
        barriers = sorted(self.manager.world.barriers.values(), key=lambda b: here not in b.zones)
        for barrier in barriers:
            names = (barrier.barrier_id, barrier.name, *barrier.aliases)
            if needle in (n.casefold().removeprefix("the ") for n in names):
                return barrier
        return None

    def _barrier_here(self, name: str) -> BarrierEntity | str:
        """The barrier of the player's zone `name` points at, or the refusal."""
        barrier = self._find_barrier(name)
        if barrier is None:
            return barrier_k.NO_BARRIER_HERE.format(name=f"'{name.strip()}'")
        if self.manager.player.current_location_id not in barrier.zones:
            return barrier_k.NO_BARRIER_HERE.format(name=barrier.kind.value)
        return barrier

    def _walks_to(self, barrier: BarrierEntity) -> bool:
        return self.manager.player.at_barrier != barrier.barrier_id

    def _validate_open(self, action: OpenAction) -> ValidationResult:
        found = self._barrier_here(action.barrier_name)
        if isinstance(found, str):
            return Rejected(action, found)
        barrier = found
        if barrier.broken:
            return Rejected(
                action,
                barrier_k.NO_DOOR_LEFT_OPEN
                if barrier.kind == BarrierKind.DOOR
                else barrier_k.SMASHED_WINDOW,
            )
        if barrier.open:
            return Rejected(action, barrier_k.ALREADY_OPEN.format(barrier=barrier.name))
        if barrier.total_planks:
            return Rejected(action, barrier_k.BARRICADED.format(barrier=barrier.name))
        player = self.manager.player
        outside = player.current_location_id != barrier.inside_zone
        if barrier.locked and outside and not self._has_key(barrier.key_id):
            return Rejected(action, barrier_k.LOCKED)
        return Accepted(action, TargetBarrier(barrier, self._walks_to(barrier)))

    def _validate_close(self, action: CloseAction) -> ValidationResult:
        found = self._barrier_here(action.barrier_name)
        if isinstance(found, str):
            return Rejected(action, found)
        barrier = found
        if barrier.broken:
            return Rejected(
                action,
                barrier_k.NO_DOOR_LEFT
                if barrier.kind == BarrierKind.DOOR
                else barrier_k.SMASHED_WINDOW,
            )
        if not barrier.open:
            return Rejected(action, barrier_k.ALREADY_CLOSED.format(barrier=barrier.name))
        if barrier.total_planks:
            return Rejected(action, barrier_k.BARRICADED.format(barrier=barrier.name))
        return Accepted(action, TargetBarrier(barrier, self._walks_to(barrier)))

    def _validate_barricade(self, action: BarricadeAction) -> ValidationResult:
        found = self._barrier_here(action.barrier_name)
        if isinstance(found, str):
            return Rejected(action, found)
        barrier = found
        player = self.manager.player
        door = barrier.kind == BarrierKind.DOOR
        if door and barrier.broken:
            return Rejected(action, barrier_k.NOTHING_TO_BOARD)
        if door and barrier.open:
            return Rejected(action, barrier_k.CLOSE_FIRST)
        if barrier.plank_count(player.current_location_id) >= barrier_k.MAX_PLANKS_PER_SIDE:
            return Rejected(action, barrier_k.FULL_BARRICADE.format(barrier=barrier.name))
        carried = carried_entities(player)
        hammers = [e for e in carried if barrier_k.HAMMER_TAG in e.item.tags and not e.broken]
        if not hammers:
            return Rejected(action, barrier_k.NO_HAMMER.format(name=self._name))
        planks = [e for e in carried if e.item.id == barrier_k.PLANK_ITEM_ID]
        if not planks:
            return Rejected(action, barrier_k.NO_PLANK.format(name=self._name))
        nails = [e for e in carried if e.item.id == barrier_k.NAILS_ITEM_ID and e.uses > 0]
        if not nails:
            return Rejected(action, barrier_k.NO_NAILS.format(name=self._name))
        best = max(planks, key=lambda e: e.condition)
        return Accepted(
            action, BarricadeKit(barrier, hammers[0], best, nails[0], self._walks_to(barrier))
        )

    def _validate_unbarricade(self, action: UnbarricadeAction) -> ValidationResult:
        found = self._barrier_here(action.barrier_name)
        if isinstance(found, str):
            return Rejected(action, found)
        barrier = found
        side = self.manager.player.current_location_id
        if not barrier.plank_count(side):
            far = barrier.plank_count(barrier.far_side(side))
            return Rejected(
                action,
                barrier_k.PLANKS_ON_OTHER_SIDE
                if far
                else barrier_k.NO_PLANKS.format(barrier=barrier.name),
            )
        tools = [
            e
            for e in carried_entities(self.manager.player)
            if barrier_k.REMOVE_BARRICADE_TAG in e.item.tags and not e.broken
        ]
        if not tools:
            return Rejected(action, barrier_k.NO_PRY_TOOL.format(name=self._name))
        return Accepted(action, PryTarget(barrier, tools[0], self._walks_to(barrier)))

    # === Combat ===

    def _behind_a_barrier(self, zombie_id: str) -> str:
        """The refusal when `zombie_id` is pounding on a barrier between it and the player, else ''."""
        zombie = self.manager.world.zombies[zombie_id]
        barrier = self.manager.world.barriers.get(zombie.thump_barrier or "")
        if zombie.state != ZombieState.THUMPING or barrier is None:
            return ""
        return barrier_k.OTHER_SIDE_OF_BARRIER.format(kind=barrier.kind.value)

    def _validate_attack(self, action: AttackAction) -> ValidationResult:
        manager = self.manager
        zombie_target = self._zombie_target(action.target_name)
        if zombie_target is not None:
            if refusal := self._behind_a_barrier(zombie_target.zombie_id):
                return Rejected(action, refusal)
            return Accepted(action, zombie_target)
        if self._names_a_zombie(action.target_name):
            return Rejected(action, f"'{action.target_name}' is not here to attack.")
        if self._find_barrier(action.target_name) is not None:
            return self._validate_hit_barrier(action)
        npc = manager.resolve_npc(action.target_name)
        if npc is None or npc.current_location_id != manager.player.current_location_id:
            return Rejected(action, f"'{action.target_name}' is not here to attack.")
        if npc.hit_points <= 0:
            return Rejected(action, f"{npc.name} is already down.")
        return Accepted(action, TargetNpc(npc))

    def _validate_hit_barrier(self, action: AttackAction) -> ValidationResult:
        found = self._barrier_here(action.target_name)
        if isinstance(found, str):
            return Rejected(action, found)
        if thumpable_for(found, self.manager.player.current_location_id) is None:
            return Rejected(action, barrier_k.NOTHING_TO_HIT)
        return Accepted(action, TargetBarrier(found, self._walks_to(found)))

    def _validate_shove(self, action: ShoveAction) -> ValidationResult:
        manager = self.manager
        zombie_target = self._zombie_target(action.target_name)
        if zombie_target is None:
            if self._names_a_zombie(action.target_name):
                return Rejected(action, f"'{action.target_name}' is not here to shove.")
            return Rejected(action, f"{self._name} can only shove zombies.")
        if refusal := self._behind_a_barrier(zombie_target.zombie_id):
            return Rejected(action, refusal)
        zombie = manager.world.zombies[zombie_target.zombie_id]
        if zombie.on_floor(manager.narrative.minutes):
            return Rejected(action, "It's already down.")
        return Accepted(action, zombie_target)

    def _names_a_zombie(self, name: str) -> bool:
        needle = name.strip().casefold()
        return needle in ZOMBIE_WORDS or needle in self.manager.world.zombies

    def _zombie_target(self, name: str) -> TargetZombie | None:
        """The perceived zombie `name` points at: its id, or the nearest for "zombie"."""
        manager = self.manager
        needle = name.strip().casefold()
        here = [seen.zombie for seen in perceived_now(manager)]
        if needle in ZOMBIE_WORDS:
            pool = sorted(here, key=lambda z: (z.gap, int(z.zombie_id[1:])))
        else:
            pool = [zombie for zombie in here if zombie.zombie_id == needle]
        if not pool:
            return None
        return TargetZombie(
            pool[0].zombie_id, approach_minutes(pool[0].gap, limp_factor(self.manager.player))
        )

    # === Time ===

    def _span(self, duration: Duration) -> int | None:
        """Minutes a duration covers from now, or None for an unknown time of day."""
        if duration.minutes is not None:
            return duration.minutes
        now = self.manager.narrative.minutes
        if duration.until_minute_of_day is not None:
            return minutes_until(now, duration.until_minute_of_day)
        start = TIME_OF_DAY_START.get(duration.until_time_of_day or "")
        return None if start is None else minutes_until(now, start)

    def _timed(self, action: WaitAction | SleepAction, duration: Duration, cap: int):
        span = self._span(duration)
        if span is None:
            return Rejected(action, f"Unknown time of day: '{duration.until_time_of_day}'.")
        return Accepted(action, TimeSpan(min(span, cap), clamped=span > cap))

    def _validate_wait(self, action: WaitAction) -> ValidationResult:
        return self._timed(action, action.duration, WAIT_CAP_MIN)

    def _validate_sleep(self, action: SleepAction) -> ValidationResult:
        refusal = self._sleep_refusal()
        if refusal:
            return Rejected(action, refusal)
        if action.duration is not None:
            return self._timed(action, action.duration, SLEEP_CAP_MIN)
        minutes = SLEEP_CAP_MIN
        now = self.manager.narrative.minutes
        if self.manager.narrative.time_of_day == "night":
            minutes = min(minutes, minutes_until(now, survival.SLEEP_DEFAULT_WAKE_MINUTE_OF_DAY))
        return Accepted(action, TimeSpan(minutes, clamped=False))

    def _validate_exercise(self, action: ExerciseAction) -> ValidationResult:
        player = self.manager.player
        exercise = ex.find_exercise(action.exercise_name)
        if exercise is None:
            return Rejected(action, f"Unknown exercise: '{action.exercise_name}'.")
        minutes = action.minutes if action.minutes is not None else ex.EXERCISE_MINUTES_DEFAULT
        valid = range(
            ex.EXERCISE_MINUTES_MIN, ex.EXERCISE_MINUTES_MAX + 1, ex.EXERCISE_MINUTES_STEP
        )
        if minutes not in valid:
            return Rejected(
                action,
                f"{exercise.name} takes {ex.EXERCISE_MINUTES_MIN} to {ex.EXERCISE_MINUTES_MAX} "
                f"minutes, in steps of {ex.EXERCISE_MINUTES_STEP}.",
            )
        if endurance_level(player) > ex.EXERCISE_ENDURANCE_STOP_LEVEL:
            return Rejected(action, f"{self._name} is too exhausted to exercise.")
        if exercise.item_id and not any(e.item.id == exercise.item_id for e in player.inventory):
            needed = ITEMS[exercise.item_id].name.lower()
            return Rejected(action, f"{exercise.name} needs a {needed}, and {self._name} has none.")
        return Accepted(action, ExercisePlan(exercise, minutes))

    def _sleep_refusal(self) -> str:
        stats = self.manager.player.stats
        panic = status_effect_level(StatusEffect.PANIC, stats.get(CharacterStat.PANIC))
        if panic >= survival.SLEEP_REFUSED_PANIC_LEVEL:
            return f"{self._name} is too panicked to sleep."
        pain = status_effect_level(StatusEffect.PAIN, stats.get(CharacterStat.PAIN))
        if (
            pain >= survival.SLEEP_REFUSED_PAIN_LEVEL
            and stats.get(CharacterStat.FATIGUE) <= survival.SLEEP_PAIN_FATIGUE_EXCEPTION
        ):
            return f"{self._name} is in too much pain to sleep."
        return ""

    # === Goals ===

    def _validate_add_goal(self, action: AddGoalAction) -> ValidationResult:
        if action.horizon not in GOAL_HORIZONS:
            return Rejected(action, f"Unknown goal horizon: '{action.horizon}'.")
        return Accepted(action)

    def _validate_remove_goal(self, action: RemoveGoalAction) -> ValidationResult:
        if action.horizon not in GOAL_HORIZONS:
            return Rejected(action, f"Unknown goal horizon: '{action.horizon}'.")
        if action.goal_text not in self.manager.narrative.goals.get(action.horizon, []):
            return Rejected(action, f"No such {action.horizon} goal: '{action.goal_text}'.")
        return Accepted(action)

    def _validate_add_relationship_note(
        self, action: AddRelationshipNoteAction
    ) -> ValidationResult:
        npc = self.manager.resolve_npc(action.npc_name)
        if npc is None:
            return Rejected(action, f"Unknown NPC: '{action.npc_name}'.")
        return Accepted(action, TargetNpc(npc))

    # === Talking to people ===

    def begin_turn(self) -> None:
        self._talked_to.clear()

    def note_talked(self, npc_id: str) -> None:
        self._talked_to.add(npc_id)

    def _npc_here(self, name: str) -> NpcEntity | str:
        """The NPC `name` points at if they are in the player's zone, else the refusal."""
        manager = self.manager
        npc = manager.resolve_npc(name)
        if npc is None:
            if ZOMBIE_ID_PATTERN.fullmatch(name.strip()) or self._names_a_zombie(name):
                return f"{name.strip()} isn't listening."
            return f"{name.strip()} isn't here."
        if npc.current_location_id != manager.player.current_location_id:
            return f"{npc.name} isn't here."
        return npc

    def _validate_talk(self, action: TalkAction) -> ValidationResult:
        npc = self._npc_here(action.npc_name)
        if isinstance(npc, str):
            return Rejected(action, npc)
        if action.approach not in TALK_APPROACH_LABELS:
            return Rejected(action, f"'{action.approach}' is not a way to talk.")
        if npc.npc_id in self._talked_to:
            return Rejected(action, f"{self._name} has already spoken to {npc.name} this turn.")
        return Accepted(action, TargetNpc(npc))

    def _validate_give(self, action: GiveAction) -> ValidationResult:
        npc = self._npc_here(action.npc_name)
        if isinstance(npc, str):
            return Rejected(action, npc)
        entity = self.manager._find_item_entity(self.manager.player.inventory, action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to give.")
        if self._is_door_key(entity.item.id):
            return Rejected(action, self._keeps_keys())
        return Accepted(action, NpcItem(npc, entity))

    def _validate_ask(self, action: AskAction) -> ValidationResult:
        npc = self._npc_here(action.npc_name)
        if isinstance(npc, str):
            return Rejected(action, npc)
        match action.request:
            case "follow" | "stay":
                if action.request == "follow" and locked_out(self.manager, npc, "follow"):
                    return Rejected(action, f"{npc.name} has already said no.")
                return Accepted(action, TargetNpc(npc))
            case "give":
                entity = self.manager._find_item_entity(npc.inventory, action.argument)
                if entity is None:
                    return Rejected(action, f"{npc.name} has no {action.argument} to give.")
                if locked_out(self.manager, npc, "give"):
                    return Rejected(action, f"{npc.name} has already said no.")
                if len(self.manager.player.inventory) >= self.manager.player.max_inventory_size:
                    return Rejected(action, "Inventory is full.")
                return Accepted(action, NpcItem(npc, entity))
            case "about":
                topic = TOPICS.get(action.argument)
                if topic is None or topic not in visible_topics(self.manager, npc):
                    return Rejected(action, f"{npc.name} has nothing to say about that.")
                return Accepted(action, NpcTopic(npc, topic.topic_id))
        return Rejected(action, f"'{action.request}' is not something to ask for.")

    # === Noise ===

    def _validate_shout(self, action: ShoutAction) -> ValidationResult:
        return Accepted(action)

    _VALIDATORS = {
        "MOVE_TO": _validate_move,
        "STANCE": _validate_stance,
        "TAKE": _validate_take,
        "SEARCH": _validate_search,
        "DROP": _validate_drop,
        "WEAR": _validate_wear,
        "TAKE_OFF": _validate_take_off,
        "OPEN": _validate_open,
        "CLOSE": _validate_close,
        "BARRICADE": _validate_barricade,
        "UNBARRICADE": _validate_unbarricade,
        "ATTACK": _validate_attack,
        "SHOVE": _validate_shove,
        "EQUIP": _validate_equip,
        "UNEQUIP": _validate_unequip,
        "USE_ITEM": _validate_use_item,
        "BANDAGE": _validate_bandage,
        "REMOVE_BANDAGE": _validate_remove_bandage,
        "DISINFECT": _validate_disinfect,
        "WAIT": _validate_wait,
        "SLEEP": _validate_sleep,
        "EXERCISE": _validate_exercise,
        "SHOUT": _validate_shout,
        "TALK": _validate_talk,
        "ASK": _validate_ask,
        "GIVE": _validate_give,
        "ADD_GOAL": _validate_add_goal,
        "REMOVE_GOAL": _validate_remove_goal,
        "ADD_RELATIONSHIP_NOTE": _validate_add_relationship_note,
    }

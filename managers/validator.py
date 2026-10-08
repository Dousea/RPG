"""Action Validator: precondition checks only, no state mutation.

This is the piece docs/architecture/engine-authority.md calls the Action Validator. It
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
from collections.abc import Iterable
from dataclasses import dataclass

from data import carry as carry_k
from data.body import health as body_k
from data.body import survival as survival_k
from data.character import exercises as exercise_k
from data.clothing.locations import EXCLUSIVE_LOCATIONS
from data.items import ITEMS
from data.loot import containers as container_k
from data.story import mentions as mention_k
from data.story.topics import TOPICS
from data.world import barriers as barrier_k
from data.world.clock import (
    SLEEP_CAP_MIN,
    TIME_OF_DAY_START,
    WAIT_CAP_MIN,
    minutes_until,
)
from data.zombies import lore as zombie_lore
from managers import carry, naming
from managers.body.first_aid import (
    bandage_items,
    disinfectant_items,
    find_part,
    most_needed_part,
    part_word,
)
from managers.body.health import limp_factor
from managers.body.stats.status_effects import status_effect_level
from managers.character.exercise import endurance_level
from managers.combat import weapons
from managers.corpses.search import find_content, perceived_corpses, with_article
from managers.game import MAX_PLACE_LENGTH, GameManager
from managers.story.beats import visible_topics
from managers.story.social import locked_out
from managers.world.barriers import (
    barriers_between,
    carried_entities,
    find_barrier,
    thumpable_for,
)
from managers.world.containers import has_room_for, unopened
from managers.world.locations import BARE_DIRECTIONS, connection_target
from managers.world.rooms import (
    container_by_name,
    current_room,
    resolve_container,
    resolve_room,
    room_holding,
)
from managers.zombies.population import approach_minutes, perceived_now
from modules.action.parser import CORPSE_WORDS, GOAL_HORIZON_LABELS, TALK_APPROACH_LABELS
from modules.action.pins import Pinned, pin_of
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    BandageAction,
    BarricadeAction,
    CarryAction,
    CloseAction,
    DisinfectAction,
    DropAction,
    Duration,
    EquipAction,
    ExerciseAction,
    GiveAction,
    LockAction,
    MoveAction,
    OpenAction,
    PutAction,
    RemoveBandageAction,
    RemoveGoalAction,
    RequestAction,
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
    UnlockAction,
    UnsupportedAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.body.stats import CharacterStat, StatusEffect
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.zombie import ZombieState
from modules.item import (
    AppliableItem,
    ClothingItem,
    ConsumableItem,
    ContainerItem,
    HoldableItem,
    MedicalItem,
)
from modules.resolution import (
    BarricadeKit,
    ExercisePlan,
    FirstAidTarget,
    Gathering,
    HeldItem,
    MoveBlocked,
    MoveToRoom,
    MoveToSpot,
    MoveToZone,
    NpcItem,
    NpcTopic,
    PryTarget,
    Resolution,
    ShuffleInZone,
    StayPut,
    TargetBarrier,
    TargetContainer,
    TargetCorpse,
    TargetNpc,
    TargetRoom,
    TargetZombie,
    TimeSpan,
    Transfer,
)
from modules.world.location import Location
from modules.world.pace import Pace
from modules.world.room import ContainerEntity, RoomEntity

GOAL_HORIZONS = GOAL_HORIZON_LABELS

UNSUPPORTED_REASON = "there is no way to do that yet."  # llm-contract
ZOMBIE_ID_PATTERN = re.compile(r"z\d+", re.IGNORECASE)
CORPSE_ID_PATTERN = re.compile(r"c\d+", re.IGNORECASE)

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
        if isinstance(action, UnsupportedAction):
            return Rejected(action, UNSUPPORTED_REASON)
        handler = self._VALIDATORS.get(action.verb)
        if handler is None:
            return Rejected(action, f"No validator registered for {type(action).__name__}.")
        if (
            action.verb in carry_k.BODY_BLOCKED_VERBS
            and self.manager.player.carrying_corpse is not None
        ):
            return Rejected(action, carry_k.BODY_IN_ARMS.format(name=self._name))
        return handler(self, action)

    # === Movement ===

    def _walk_pace(self, action: MoveAction) -> Pace:
        if action.run:
            return Pace.RUN
        return Pace.SNEAK if self.manager.player.sneaking else Pace.WALK

    def _validate_stance(self, action: StanceAction) -> ValidationResult:
        return Accepted(action)

    def _validate_move(self, action: MoveAction) -> ValidationResult:
        """Decide what a MOVE_TO *means*. It rejects only a move to the room the player is in.

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

        if pin := pin_of(action.destination, "zone", "room"):
            return self._move_pinned(action, pin)

        room = resolve_room(current, raw)
        if room is not None:
            return self._enter_room(action, room)

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
        return self._walk_to_zone(action, target, place)

    def _enter_room(self, action: MoveAction, room: RoomEntity) -> ValidationResult:
        manager = self.manager
        if current_room(manager.current_location, manager.player) is room:
            return Rejected(
                action, container_k.ALREADY_IN_ROOM.format(name=self._name, room=room.name)
            )
        return Accepted(action, MoveToRoom(manager.current_location, room))

    def _move_pinned(self, action: MoveAction, pin: Pinned) -> ValidationResult:
        """A MOVE_TO the player pinned to a zone or a room of this zone, resolved by id with no phrase matching."""
        manager = self.manager
        if pin.kind == "room":
            room = manager.current_location.rooms.get(pin.entity_id)
            if room is None:
                return Rejected(action, mention_k.OUT_OF_REACH.format(name=pin))
            return self._enter_room(action, room)
        zone = manager.world.locations.get(pin.entity_id)
        if zone is None:
            return Rejected(action, mention_k.OUT_OF_REACH.format(name=pin))
        return self._walk_to_zone(action, zone, "")

    def _walk_to_zone(self, action: MoveAction, target: Location, place: str) -> ValidationResult:
        manager = self.manager
        current = manager.current_location
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
        return any(entity.item.id == key_id for entity in carry.carried_items(self.manager.player))

    # === Items ===

    def _cant_carry(self) -> str:
        return carry_k.CANT_CARRY_MORE.format(name=self._name)

    def _asleep(self, action: AnyAction) -> Rejected | None:
        if self.manager.player.asleep:
            return Rejected(action, zombie_lore.ASLEEP_REFUSAL.format(name=self._name))
        return None

    @staticmethod
    def _asked(found: ItemEntity | list[ItemEntity] | None) -> ItemEntity | str | None:
        """A lookup's result with the which-one question in place of several candidates."""
        return naming.which_one(found) if isinstance(found, list) else found

    def _item_named(self, entities: Iterable[ItemEntity], name: str) -> ItemEntity | str | None:
        """The item `name` points at among `entities`; the question to ask when several look different, None when none match."""
        return self._asked(naming.find_named(entities, name))

    def _carried(self, name: str) -> ItemEntity | str | None:
        """The item `name` points at among what the player carries, bags included."""
        return self._item_named(carry.carried_items(self.manager.player), name)

    def _frames(
        self,
        entities: tuple[ItemEntity, ...],
        source: carry.Place,
        target: carry.Place,
        bag: ItemEntity | None = None,
    ) -> float:
        traits = self.manager.player.traits
        return sum(
            carry.transfer_frames(e, source, target, bag=bag, traits=traits) for e in entities
        )

    def _validate_take(self, action: TakeAction) -> ValidationResult:
        manager = self.manager
        if refusal := self._asleep(action):
            return refusal
        if action.from_name is not None:
            return self._validate_take_from(action, action.from_name)
        if action.all_items:
            return self._take_all_here(action)
        entity = self._item_named(manager._ground_items(), action.item_name)
        if isinstance(entity, str):
            return Rejected(action, entity)
        if entity is None:
            if container := self._opened_container_holding(action.item_name):
                return self._take_from_container(action, container)
            return Rejected(action, f"No '{action.item_name}' here to take.")
        if carry.over_the_limit(manager.player, extra=[entity]):
            return Rejected(action, self._cant_carry())
        frames = self._frames((entity,), carry.Place.FLOOR, carry.Place.PACK)
        return Accepted(action, Transfer((entity,), frames))

    def _take_all_here(self, action: TakeAction) -> ValidationResult:
        """Everything on the ground, then everything in each stocked opened container of the room."""
        manager = self.manager
        parts: list[Transfer] = []
        if ground := tuple(manager._ground_items()):
            parts.append(
                Transfer(ground, self._frames(ground, carry.Place.FLOOR, carry.Place.PACK))
            )
        for container in self._stocked_containers():
            entities = tuple(container.contents)
            frames = self._frames(entities, carry.Place.WORLD, carry.Place.PACK)
            parts.append(Transfer(entities, frames, source=container))
        if not parts:
            return Rejected(action, carry_k.NOTHING_HERE)
        everything = [entity for part in parts for entity in part.entities]
        if carry.over_the_limit(manager.player, extra=everything):
            return Rejected(action, self._cant_carry())
        return Accepted(action, parts[0] if len(parts) == 1 else Gathering(tuple(parts)))

    def _stocked_containers(self) -> list[ContainerEntity]:
        """The opened containers of the player's room that hold anything, in layout order."""
        room = current_room(self.manager.current_location, self.manager.player)
        if room is None:
            return []
        return [c for c in room.containers if c.opened and c.contents]

    def _validate_take_from(self, action: TakeAction, source: str) -> ValidationResult:
        if naming.clean_name(source) in CORPSE_WORDS or CORPSE_ID_PATTERN.fullmatch(source.strip()):
            return self._take_from_corpse(action, source)
        bag = (
            None
            if pin_of(source, "container")
            else self._item_named(carry.carried_bags(self.manager.player), source)
        )
        if isinstance(bag, str):
            return Rejected(action, bag)
        if bag is not None:
            return self._take_from_bag(action, bag)
        found = self._container_named(source)
        if found is None:
            return Rejected(action, carry_k.NO_BAG_SOURCE.format(name=self._name, source=source))
        if isinstance(found, str):
            return Rejected(action, found)
        return self._take_from_container(action, found)

    def _opened_container_holding(self, item_name: str) -> ContainerEntity | None:
        """The first opened container of the player's room, in layout order, that holds `item_name`."""
        for container in self._stocked_containers():
            if naming.find_named(container.contents, item_name) is not None:
                return container
        return None

    def _container_named(self, name: str) -> ContainerEntity | str | None:
        """The container `name` points at in this zone; the question to ask when several match, None when none do."""
        manager = self.manager
        if pin := pin_of(name):
            return self._pinned_container(pin)
        found = resolve_container(manager.current_location, manager.player.current_room, name)
        if isinstance(found, list):
            return container_k.WHICH_ONE.format(choices=" or ".join(c.name for c in found))
        return found

    def _pinned_container(self, pin: Pinned) -> ContainerEntity | None:
        """The container of this zone a pin names, by id; None for a pin of another kind or a container not here."""
        if pin.kind != "container":
            return None
        return next(
            (
                container
                for room in self.manager.current_location.rooms.values()
                for container in room.containers
                if container.container_id == pin.entity_id
            ),
            None,
        )

    def _container_reach(self, action: AnyAction, container: ContainerEntity) -> Rejected | None:
        """A refusal when the player can't use an opened container from where they stand."""
        zone = self.manager.current_location
        room = room_holding(zone, container)
        here = current_room(zone, self.manager.player)
        if room is not None and room is not here:
            return Rejected(
                action,
                container_k.NOT_IN_THIS_ROOM.format(container=container.name, room=room.name),
            )
        if not container.opened:
            return Rejected(action, container_k.NOT_OPENED.format(container=container.name))
        return None

    def _take_from_container(
        self, action: TakeAction, container: ContainerEntity
    ) -> ValidationResult:
        if refusal := self._container_reach(action, container):
            return refusal
        if action.all_items:
            entities = tuple(container.contents)
            if not entities:
                return Rejected(action, carry_k.BAG_EMPTY.format(source=container.name))
        else:
            found = self._item_named(container.contents, action.item_name)
            if isinstance(found, str):
                return Rejected(action, found)
            if found is None:
                return Rejected(
                    action,
                    container_k.NO_SUCH_IN_CONTAINER.format(
                        container=container.name, item=action.item_name
                    ),
                )
            entities = (found,)
        if carry.over_the_limit(self.manager.player, extra=entities):
            return Rejected(action, self._cant_carry())
        frames = self._frames(entities, carry.Place.WORLD, carry.Place.PACK)
        return Accepted(action, Transfer(entities, frames, source=container))

    def _take_from_bag(self, action: TakeAction, bag: ItemEntity) -> ValidationResult:
        player = self.manager.player
        label = bag.item.name
        if action.all_items:
            entities = tuple(bag.contents)
            if not entities:
                return Rejected(action, carry_k.BAG_EMPTY.format(source=label))
        else:
            found = self._item_named(bag.contents, action.item_name)
            if isinstance(found, str):
                return Rejected(action, found)
            if found is None:
                return Rejected(action, carry_k.NOT_IN_BAG.format(bag=label, item=action.item_name))
            entities = (found,)
        if carry.over_the_limit(player, without=entities, extra=entities):
            return Rejected(action, self._cant_carry())
        frames = self._frames(entities, carry.Place.BAG, carry.Place.PACK)
        return Accepted(action, Transfer(entities, frames, source=bag))

    def _take_from_corpse(self, action: TakeAction, source: str) -> ValidationResult:
        player = self.manager.player
        corpse = self._corpse_target(source)
        if corpse is None:
            return Rejected(action, zombie_lore.NO_SUCH_CORPSE.format(target=source))
        if not corpse.searched:
            return Rejected(
                action, zombie_lore.NOT_SEARCHED.format(name=self._name, corpse=corpse.corpse_id)
            )
        if action.all_items:
            entities = tuple(corpse.contents)
            if not entities:
                return Rejected(action, carry_k.BAG_EMPTY.format(source=corpse.corpse_id))
            if carry.over_the_limit(player, extra=entities):
                return Rejected(action, self._cant_carry())
            frames = self._frames(entities, carry.Place.WORLD, carry.Place.PACK)
            return Accepted(action, Transfer(entities, frames, source=corpse))
        entity = self._asked(find_content(corpse, action.item_name))
        if isinstance(entity, str):
            return Rejected(action, entity)
        if entity is None:
            return Rejected(
                action,
                zombie_lore.NOT_ON_CORPSE.format(corpse=corpse.corpse_id, item=action.item_name),
            )
        if carry.over_the_limit(player, extra=[entity]):
            return Rejected(action, self._cant_carry())
        frames = self._frames((entity,), carry.Place.WORLD, carry.Place.PACK)
        return Accepted(action, Transfer((entity,), frames, source=corpse))

    def _validate_put(self, action: PutAction) -> ValidationResult:
        player = self.manager.player
        if refusal := self._asleep(action):
            return refusal
        entity = self._item_named(carry.carried_items(player), action.item_name)
        if isinstance(entity, str):
            return Rejected(action, entity)
        if entity is None:
            return Rejected(action, carry_k.NOT_CARRIED_TO_PUT.format(item=action.item_name))
        bag = (
            None
            if pin_of(action.target_name, "container")
            else self._item_named(carry.carried_bags(player), action.target_name)
        )
        if isinstance(bag, str):
            return Rejected(action, bag)
        if bag is None:
            return self._put_in_container(action, entity, action.target_name)
        if carry.inside(entity, bag):
            return Rejected(action, carry_k.BAG_IN_ITSELF)
        if carry.holder_bag(player, entity) is bag:
            return Rejected(
                action, carry_k.ALREADY_IN_BAG.format(item=entity.item.name, bag=bag.item.name)
            )
        if not carry.bag_room(bag, [entity]):
            return Rejected(action, carry_k.BAG_FULL.format(bag=bag.item.name))
        source_bag = carry.holder_bag(player, entity)
        place = carry.Place.BAG if source_bag is not None else carry.Place.PACK
        frames = self._frames((entity,), place, carry.Place.BAG, bag)
        return Accepted(action, Transfer((entity,), frames, source=source_bag, target=bag))

    def _put_in_container(
        self, action: PutAction, entity: ItemEntity, target: str
    ) -> ValidationResult:
        found = self._container_named(target)
        if found is None:
            return Rejected(
                action, carry_k.BAG_NOT_CARRIED.format(name=self._name, bag=action.target_name)
            )
        if isinstance(found, str):
            return Rejected(action, found)
        if refusal := self._container_reach(action, found):
            return refusal
        if not has_room_for(found, entity):
            return Rejected(action, container_k.CONTAINER_FULL.format(container=found.name))
        source_bag = carry.holder_bag(self.manager.player, entity)
        place = carry.Place.BAG if source_bag is not None else carry.Place.PACK
        frames = self._frames((entity,), place, carry.Place.WORLD)
        return Accepted(action, Transfer((entity,), frames, source=source_bag, target=found))

    def _validate_carry(self, action: CarryAction) -> ValidationResult:
        manager = self.manager
        player = manager.player
        if refusal := self._asleep(action):
            return refusal
        if player.carrying_corpse is not None:
            return Rejected(action, carry_k.ALREADY_CARRYING.format(name=self._name))
        corpse = self._corpse_target(action.corpse_name)
        if corpse is None:
            return Rejected(action, zombie_lore.NO_SUCH_CORPSE.format(target=action.corpse_name))
        if any(player.equipment[slot] is not None for slot in CharacterHoldableSlot):
            return Rejected(action, carry_k.HANDS_FULL.format(name=self._name))
        minutes = approach_minutes(corpse.gap, limp_factor(player))
        return Accepted(action, TargetCorpse(corpse.corpse_id, minutes))

    def _validate_search(self, action: SearchAction) -> ValidationResult:
        manager = self.manager
        if manager.player.asleep:
            return Rejected(action, zombie_lore.ASLEEP_REFUSAL.format(name=self._name))
        name = action.target_name
        if not (
            naming.clean_name(name) in CORPSE_WORDS or CORPSE_ID_PATTERN.fullmatch(name.strip())
        ):
            return self._search_place(action)
        corpse = self._corpse_target(action.target_name)
        if corpse is None:
            return Rejected(action, zombie_lore.NO_SUCH_CORPSE.format(target=action.target_name))
        if corpse.searched:
            return Rejected(
                action,
                zombie_lore.ALREADY_SEARCHED.format(name=self._name, corpse=corpse.corpse_id),
            )
        minutes = approach_minutes(corpse.gap, limp_factor(manager.player))
        return Accepted(action, TargetCorpse(corpse.corpse_id, minutes))

    def _search_place(self, action: SearchAction) -> ValidationResult:
        """SEARCH of a room or a container of this zone: what to open, and whether to walk to it first."""
        manager = self.manager
        zone = manager.current_location
        here = current_room(zone, manager.player)
        name = action.target_name
        if pin := pin_of(name, "room"):
            room, exact = zone.rooms.get(pin.entity_id), None
        elif pin := pin_of(name, "container"):
            room, exact = None, self._pinned_container(pin)
        else:
            exact = container_by_name(zone, name)
            room = None if exact is not None else resolve_room(zone, name)
        if room is not None:
            closed = unopened(room)
            if not closed:
                label = container_k.GONE_THROUGH.format(name=self._name, target=room.name)
                return Rejected(action, label)
            return Accepted(action, TargetRoom(room, closed, walk=room is not here))
        container = exact if exact is not None else self._container_named(name)
        if isinstance(container, str):
            return Rejected(action, container)
        if container is None:
            return Rejected(action, container_k.NO_SUCH_SEARCH_TARGET.format(target=name))
        owner = room_holding(zone, container)
        assert owner is not None, "a resolved container belongs to a room"
        if container.opened:
            label = container_k.GONE_THROUGH.format(name=self._name, target=container.name)
            return Rejected(action, label)
        return Accepted(action, TargetContainer(owner, container, walk=owner is not here))

    def _corpse_target(self, name: str) -> CorpseEntity | None:
        """The perceived body `name` points at: its id, or the nearest for "corpse"."""
        needle = name.strip().casefold()
        seen = perceived_corpses(self.manager)
        if needle in CORPSE_WORDS:
            return min(seen, key=lambda c: (c.gap, int(c.corpse_id[1:])), default=None)
        return next((c for c in seen if c.corpse_id == needle), None)

    def _validate_drop(self, action: DropAction) -> ValidationResult:
        player = self.manager.player
        if refusal := self._asleep(action):
            return refusal
        if action.corpse:
            if self.manager.player.carrying_corpse is None:
                return Rejected(action, carry_k.NOT_CARRYING.format(name=self._name))
            return Accepted(action)
        reachable = [
            *carry.carried_items(player),
            *(e for e in carry.on_body(player) if isinstance(e.item, ContainerItem)),
        ]
        entity = self._item_named(reachable, action.item_name)
        if isinstance(entity, str):
            return Rejected(action, entity)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to drop.")
        if self._is_door_key(entity.item.id):
            return Rejected(action, self._keeps_keys())
        bag = carry.holder_bag(player, entity)
        if bag is None:
            return Accepted(action, HeldItem(entity))
        frames = self._frames((entity,), carry.Place.BAG, carry.Place.FLOOR)
        return Accepted(action, Transfer((entity,), frames, source=bag))

    def _validate_wear(self, action: WearAction) -> ValidationResult:
        player = self.manager.player
        entity = self._carried(action.item_name)
        if isinstance(entity, str):
            return Rejected(action, entity)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to wear.")
        item = entity.item
        if not isinstance(item, ClothingItem | ContainerItem) or item.body_location is None:
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
        entity = self._item_named(player.worn.values(), action.item_name)
        if isinstance(entity, str):
            return Rejected(action, entity)
        if entity is None:
            return Rejected(action, f"{self._name} is not wearing '{action.item_name}'.")
        if carry.over_the_limit(player, without=[entity], extra=[entity]):
            return Rejected(action, self._cant_carry())
        return Accepted(action, HeldItem(entity))

    def _is_door_key(self, item_id: str) -> bool:
        """Whether `item_id` is the `key_id` of any barrier anywhere in the world --
        engine-owned, not hard-coded to `item_apartment_key`. Dropping (or duplicating) the key
        could strand the player outside their own apartment."""
        return any(barrier.key_id == item_id for barrier in self.manager.world.barriers.values())

    def _validate_use_item(self, action: UseItemAction) -> ValidationResult:
        entity = self._carried(action.item_name)
        if isinstance(entity, str):
            return Rejected(action, entity)
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
        entity = self._carried(action.item_name)
        if isinstance(entity, str):
            return Rejected(action, entity)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to hold.")
        item = entity.item
        if isinstance(item, ContainerItem):
            return self._validate_equip_bag(action, entity, item)
        if not isinstance(item, HoldableItem):
            return Rejected(action, f"{item.name} cannot be held.")
        if entity.broken:
            return Rejected(action, f"The {item.name} is broken.")
        for slot in weapons.held_slots(item):
            occupant = player.equipment.get(slot)
            if occupant is not None:
                return Rejected(
                    action, f"{self._name} is already holding the {occupant.item.name}."
                )
        return Accepted(action, HeldItem(entity))

    def _validate_equip_bag(
        self, action: EquipAction, entity: ItemEntity, item: ContainerItem
    ) -> ValidationResult:
        if item.body_location is not None:
            return Rejected(action, carry_k.BAG_IS_WORN.format(item=item.name))
        if carry.bag_slot(self.manager.player, entity) is None:
            full = carry_k.HANDS_AND_BACK_FULL if len(item.slots) > 1 else carry_k.HAND_FULL
            return Rejected(action, full.format(name=self._name))
        return Accepted(action, HeldItem(entity))

    def _validate_unequip(self, action: UnequipAction) -> ValidationResult:
        player = self.manager.player
        held = [e for e in player.equipment.values() if e is not None]
        entity = self._item_named(held, action.item_name)
        if isinstance(entity, str):
            return Rejected(action, entity)
        if entity is None:
            return Rejected(action, f"{self._name} is not holding '{action.item_name}'.")
        if carry.over_the_limit(player, without=[entity], extra=[entity]):
            return Rejected(action, self._cant_carry())
        return Accepted(action, HeldItem(entity))

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
            entity = self._carried(action.item_name)
            if isinstance(entity, str):
                return Rejected(action, entity)
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
            entity = self._carried(action.item_name)
            if isinstance(entity, str):
                return Rejected(action, entity)
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
        if pin := pin_of(name, "barrier"):
            return self.manager.world.barriers.get(pin.entity_id)
        return find_barrier(self.manager.world, self.manager.player.current_location_id, name)

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

    def _validate_lock(self, action: LockAction) -> ValidationResult:
        found = self._barrier_here(action.barrier_name)
        if isinstance(found, str):
            return Rejected(action, found)
        barrier = found
        if barrier.broken:
            return Rejected(action, self._gone(barrier, barrier_k.NO_DOOR_LEFT_TO_LOCK))
        if barrier.open:
            return Rejected(action, barrier_k.CLOSE_FIRST)
        if barrier.locked:
            return Rejected(action, barrier_k.ALREADY_LOCKED.format(barrier=barrier.name))
        refusal = self._needs_key(barrier)
        if refusal is not None:
            return Rejected(action, refusal)
        return Accepted(action, TargetBarrier(barrier, self._walks_to(barrier)))

    def _validate_unlock(self, action: UnlockAction) -> ValidationResult:
        found = self._barrier_here(action.barrier_name)
        if isinstance(found, str):
            return Rejected(action, found)
        barrier = found
        if barrier.broken:
            return Rejected(action, self._gone(barrier, barrier_k.NO_DOOR_LEFT_TO_UNLOCK))
        if not barrier.locked:
            return Rejected(action, barrier_k.NOT_LOCKED.format(barrier=barrier.name))
        refusal = self._needs_key(barrier)
        if refusal is not None:
            return Rejected(action, refusal)
        return Accepted(action, TargetBarrier(barrier, self._walks_to(barrier)))

    def _gone(self, barrier: BarrierEntity, door_text: str) -> str:
        return door_text if barrier.kind == BarrierKind.DOOR else barrier_k.SMASHED_WINDOW

    def _needs_key(self, barrier: BarrierEntity) -> str | None:
        """The refusal when the player is outside and does not hold the barrier's key."""
        outside = self.manager.player.current_location_id != barrier.inside_zone
        if outside and not self._has_key(barrier.key_id):
            return barrier_k.NO_KEY.format(name=self._name, barrier=barrier.name)
        return None

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
        npc = self._npc_named(action.target_name)
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
            minutes = min(minutes, minutes_until(now, survival_k.SLEEP_DEFAULT_WAKE_MINUTE_OF_DAY))
        return Accepted(action, TimeSpan(minutes, clamped=False))

    def _validate_exercise(self, action: ExerciseAction) -> ValidationResult:
        player = self.manager.player
        exercise = exercise_k.find_exercise(action.exercise_name)
        if exercise is None:
            return Rejected(action, f"Unknown exercise: '{action.exercise_name}'.")
        minutes = (
            action.minutes if action.minutes is not None else exercise_k.EXERCISE_MINUTES_DEFAULT
        )
        valid = range(
            exercise_k.EXERCISE_MINUTES_MIN,
            exercise_k.EXERCISE_MINUTES_MAX + 1,
            exercise_k.EXERCISE_MINUTES_STEP,
        )
        if minutes not in valid:
            return Rejected(
                action,
                f"{exercise.name} takes {exercise_k.EXERCISE_MINUTES_MIN} to {exercise_k.EXERCISE_MINUTES_MAX} "
                f"minutes, in steps of {exercise_k.EXERCISE_MINUTES_STEP}.",
            )
        if endurance_level(player) > exercise_k.EXERCISE_ENDURANCE_STOP_LEVEL:
            return Rejected(action, f"{self._name} is too exhausted to exercise.")
        if exercise.item_id and not any(
            e.item.id == exercise.item_id for e in carry.carried_items(player)
        ):
            needed = ITEMS[exercise.item_id].name.lower()
            return Rejected(action, f"{exercise.name} needs a {needed}, and {self._name} has none.")
        return Accepted(action, ExercisePlan(exercise, minutes))

    def _sleep_refusal(self) -> str:
        stats = self.manager.player.stats
        panic = status_effect_level(StatusEffect.PANIC, stats.get(CharacterStat.PANIC))
        if panic >= survival_k.SLEEP_REFUSED_PANIC_LEVEL:
            return f"{self._name} is too panicked to sleep."
        pain = status_effect_level(StatusEffect.PAIN, stats.get(CharacterStat.PAIN))
        if (
            pain >= survival_k.SLEEP_REFUSED_PAIN_LEVEL
            and stats.get(CharacterStat.FATIGUE) <= survival_k.SLEEP_PAIN_FATIGUE_EXCEPTION
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
        npc = self._npc_named(action.npc_name)
        if npc is None:
            return Rejected(action, f"Unknown NPC: '{action.npc_name}'.")
        return Accepted(action, TargetNpc(npc))

    # === Talking to people ===

    def begin_turn(self) -> None:
        self._talked_to.clear()

    def note_talked(self, npc_id: str) -> None:
        self._talked_to.add(npc_id)

    def _npc_named(self, name: str) -> NpcEntity | None:
        """The NPC `name` points at: a pinned one by id, else by name or id."""
        if pin := pin_of(name, "npc"):
            return self.manager.npcs.get(pin.entity_id)
        return self.manager.resolve_npc(name)

    def _npc_here(self, name: str) -> NpcEntity | str:
        """The NPC `name` points at if they are in the player's zone, else the refusal."""
        manager = self.manager
        npc = self._npc_named(name)
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
        entity = self._carried(action.item_name)
        if isinstance(entity, str):
            return Rejected(action, entity)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to give.")
        if self._is_door_key(entity.item.id):
            return Rejected(action, self._keeps_keys())
        return Accepted(action, NpcItem(npc, entity))

    def _validate_request(self, action: RequestAction) -> ValidationResult:
        npc = self._npc_here(action.npc_name)
        if isinstance(npc, str):
            return Rejected(action, npc)
        match action.request:
            case "follow" | "stay":
                if action.request == "follow" and locked_out(self.manager, npc, "follow"):
                    return Rejected(action, f"{npc.name} has already said no.")
                return Accepted(action, TargetNpc(npc))
            case "give":
                entity = self._item_named(npc.inventory, action.argument)
                if isinstance(entity, str):
                    return Rejected(action, entity)
                if entity is None:
                    return Rejected(action, f"{npc.name} has no {action.argument} to give.")
                if locked_out(self.manager, npc, "give"):
                    return Rejected(action, f"{npc.name} has already said no.")
                if carry.over_the_limit(self.manager.player, extra=[entity]):
                    return Rejected(action, self._cant_carry())
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
        "PUT": _validate_put,
        "CARRY": _validate_carry,
        "SEARCH": _validate_search,
        "DROP": _validate_drop,
        "WEAR": _validate_wear,
        "TAKE_OFF": _validate_take_off,
        "OPEN": _validate_open,
        "CLOSE": _validate_close,
        "LOCK": _validate_lock,
        "UNLOCK": _validate_unlock,
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
        "REQUEST": _validate_request,
        "GIVE": _validate_give,
        "ADD_GOAL": _validate_add_goal,
        "REMOVE_GOAL": _validate_remove_goal,
        "ADD_RELATIONSHIP_NOTE": _validate_add_relationship_note,
    }

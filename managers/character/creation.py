"""Character creation rules: point pool, exclusions, starting skills, random builds (spec 07)."""

import math
import random
from collections.abc import Iterable

from data.character import creation as k
from data.character.names import (
    BEARD_STYLES,
    FEMALE_FORENAMES,
    HAIR_COLOURS,
    HAIR_STYLES,
    MALE_FORENAMES,
    SURNAMES,
)
from data.character.occupations import OCCUPATIONS
from data.character.presets import PRESETS
from data.character.skills import (
    LOSS_TIMER_DIVISOR,
    LOSS_TIMER_START,
    PASSIVE_SKILLS,
    SKILLS,
)
from data.character.traits import TRAITS
from data.clothing.selection import (
    DEFAULT_CLOTHING,
    OCCUPATION_CLOTHING,
    TRAIT_CLOTHING,
    ClothingList,
)
from data.items import ITEMS
from data.loot.containers import ENTRY_ROOMS
from data.world.locations import STARTING_ZONE_ID
from managers.character.exercise import starting_regularity
from managers.character.skills import SkillEngine
from modules.body.parts import BodyLocation
from modules.character.appearance import Appearance, Gender
from modules.character.build import CharacterBuild, ResolvedCharacter
from modules.character.definitions import ClothingChoice
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.item import ClothingItem


def _clashes(trait_id: str, other: str) -> bool:
    return other in TRAITS[trait_id].excludes or trait_id in TRAITS[other].excludes


def _excluded(trait_id: str, held: Iterable[str]) -> bool:
    """Whether `trait_id` or a trait it grants clashes with any trait in `held`.

    `held` is the full trait set, granted traits included; clashes count in either direction.
    """
    held = list(held)
    return any(
        _clashes(candidate, other)
        for candidate in (trait_id, *TRAITS[trait_id].granted_traits)
        for other in held
    )


def _trait_granted(chosen: Iterable[str]) -> tuple[str, ...]:
    """The traits the chosen traits grant, in order and without repeats."""
    granted: list[str] = []
    for trait_id in chosen:
        granted.extend(g for g in TRAITS[trait_id].granted_traits if g not in granted)
    return tuple(granted)


def _points(occupation_id: str, chosen: Iterable[str]) -> int:
    return OCCUPATIONS[occupation_id].cost - sum(TRAITS[t].cost for t in chosen)


def change_occupation(old_id: str, new_id: str, chosen: Iterable[str]) -> tuple[str, ...]:
    """The chosen traits that survive an occupation swap.

    The old occupation's granted traits go with it; a chosen trait that a new
    granted trait excludes is dropped.
    """
    granted = OCCUPATIONS[new_id].granted_traits
    return tuple(
        trait
        for trait in chosen
        if trait not in OCCUPATIONS[old_id].granted_traits and not _excluded(trait, granted)
    )


def resolve(build: CharacterBuild) -> ResolvedCharacter:
    """Granted traits, the full trait set, starting skills with boosts, and the points left."""
    occupation = OCCUPATIONS[build.occupation_id]
    granted = tuple(
        dict.fromkeys(
            t
            for t in (*occupation.granted_traits, *_trait_granted(build.traits))
            if t not in build.traits
        )
    )
    traits = (*granted, *build.traits)
    levels = {skill: 0 for skill in k.SKILLS}
    levels["fitness"] = k.BASE_FITNESS
    levels["strength"] = k.BASE_STRENGTH
    sources = [occupation.boosts, *(TRAITS[t].boosts for t in traits)]
    for boosts in sources:
        for skill, amount in boosts.items():
            levels[skill] += amount
    skills = {s: max(k.SKILL_LEVEL_MIN, min(k.SKILL_LEVEL_MAX, v)) for s, v in levels.items()}
    skill_boosts = {s: min(k.SKILL_BOOST_CAP, v) for s, v in skills.items()}
    return ResolvedCharacter(
        granted_traits=granted,
        traits=traits,
        skills=skills,
        skill_boosts=skill_boosts,
        points_left=_points(build.occupation_id, build.traits),
    )


def _clothing_sources(
    gender: Gender, occupation_id: str, traits: Iterable[str]
) -> list[ClothingList]:
    """The default, occupation and trait lists in order, each for `gender`.

    A list with no version for `gender` serves it with its female version.
    """
    sources = [DEFAULT_CLOTHING, OCCUPATION_CLOTHING.get(occupation_id, {})]
    sources.extend(TRAIT_CLOTHING.get(t, {}) for t in traits)
    return [source.get(gender) or source.get(Gender.FEMALE, {}) for source in sources]


def clothing_lists(gender: Gender, occupation_id: str, traits: Iterable[str]) -> ClothingList:
    """The lists merged, location by location: the items pooled, the highest chance kept."""
    merged: dict[BodyLocation, ClothingChoice] = {}
    for clothing in _clothing_sources(gender, occupation_id, traits):
        for location, choice in clothing.items():
            held = merged.get(location)
            if held is None:
                merged[location] = choice
                continue
            items = (*held.items, *(i for i in choice.items if i not in held.items))
            merged[location] = ClothingChoice(max(held.chance, choice.chance), items)
    return merged


def _allowed_outfit_items(build: CharacterBuild, traits: Iterable[str]) -> set[str]:
    lists = clothing_lists(build.appearance.gender, build.occupation_id, traits)
    allowed = {item for choice in lists.values() for item in choice.items}
    for preset in PRESETS.values():
        allowed.update(preset.outfit)
    return allowed


def _validate_appearance(appearance: Appearance) -> list[str]:
    errors: list[str] = []
    if not 1 <= len(appearance.forename) <= k.NAME_MAX_CHARS:
        errors.append(f"The forename must be 1 to {k.NAME_MAX_CHARS} characters.")
    if len(appearance.surname) > k.NAME_MAX_CHARS:
        errors.append(f"The surname can be at most {k.NAME_MAX_CHARS} characters.")
    if len(appearance.backstory) > k.BACKSTORY_MAX_CHARS:
        errors.append(f"The backstory can be at most {k.BACKSTORY_MAX_CHARS} characters.")
    if not k.SKIN_TONE_MIN <= appearance.skin_tone <= k.SKIN_TONE_MAX:
        errors.append(f"The skin tone must be {k.SKIN_TONE_MIN} to {k.SKIN_TONE_MAX}.")
    if appearance.hair_style not in HAIR_STYLES:
        errors.append(f"Unknown hair style '{appearance.hair_style}'.")
    if appearance.hair_colour not in HAIR_COLOURS:
        errors.append(f"Unknown hair colour '{appearance.hair_colour}'.")
    if appearance.beard_style not in BEARD_STYLES:
        errors.append(f"Unknown beard style '{appearance.beard_style}'.")
    elif appearance.beard_style and appearance.gender != Gender.MALE:
        errors.append("Only male characters can have a beard.")
    return errors


def _validate_traits(build: CharacterBuild) -> list[str]:
    errors: list[str] = []
    chosen: list[str] = []
    for trait_id in build.traits:
        if trait_id not in TRAITS:
            errors.append(f"Unknown trait '{trait_id}'.")
        elif trait_id in chosen:
            errors.append(f"{TRAITS[trait_id].name} is chosen twice.")
        elif TRAITS[trait_id].profession_only:
            errors.append(f"{TRAITS[trait_id].name} only comes from an occupation.")
        else:
            chosen.append(trait_id)
    held = list(OCCUPATIONS[build.occupation_id].granted_traits)
    for trait_id in chosen:
        clash = next((o for o in held if _excluded(trait_id, [o])), None)
        if clash is not None:
            errors.append(
                f"{TRAITS[trait_id].name} can't be taken together with {TRAITS[clash].name}."
            )
        held.extend((trait_id, *TRAITS[trait_id].granted_traits))
    return errors


def validate(build: CharacterBuild) -> list[str]:
    """Plain-sentence reasons the build can't start a game; empty when it can."""
    if build.occupation_id not in OCCUPATIONS:
        return [f"Unknown occupation '{build.occupation_id}'."]
    errors = _validate_appearance(build.appearance)
    if len(build.job_title) > k.JOB_TITLE_MAX_CHARS:
        errors.append(f"The job title can be at most {k.JOB_TITLE_MAX_CHARS} characters.")
    trait_errors = _validate_traits(build)
    errors.extend(trait_errors)
    if not any(t.startswith("Unknown trait") for t in trait_errors):
        points = _points(build.occupation_id, build.traits)
        if points < k.MIN_POINTS_TO_ACCEPT:
            errors.append(f"The build is {-points} points over: it needs at least 0 points left.")
    allowed = _allowed_outfit_items(build, build.traits if not trait_errors else ())
    locations: set[BodyLocation] = set()
    for item_id in build.outfit:
        item = ITEMS.get(item_id)
        if item_id not in allowed or not isinstance(item, ClothingItem):
            errors.append(f"'{item_id}' is not a starting clothing choice.")
        elif item.body_location in locations:
            errors.append(f"Only one item can be worn at {item.body_location.value}.")
        else:
            locations.add(item.body_location)
    return errors


def _random_appearance(rng: random.Random) -> Appearance:
    gender = rng.choice(list(Gender))
    forenames = FEMALE_FORENAMES if gender == Gender.FEMALE else MALE_FORENAMES
    beard = ""
    if gender == Gender.MALE and rng.randrange(100) < k.RANDOM_BEARD_CHANCE:
        beard = rng.choice([style for style in BEARD_STYLES if style])
    return Appearance(
        forename=rng.choice(forenames),
        surname=rng.choice(SURNAMES),
        gender=gender,
        skin_tone=rng.randint(k.SKIN_TONE_MIN, k.SKIN_TONE_MAX),
        hair_style=rng.choice(HAIR_STYLES),
        hair_colour=rng.choice(HAIR_COLOURS),
        beard_style=beard,
    )


def _random_outfit(
    rng: random.Random, gender: Gender, occupation_id: str, traits: Iterable[str]
) -> tuple[str, ...]:
    """Roll each list in turn; a later success replaces an earlier pick at that location."""
    picked: dict[BodyLocation, str] = {}
    for clothing in _clothing_sources(gender, occupation_id, traits):
        for location, choice in clothing.items():
            if choice.items and rng.randrange(100) < choice.chance:
                picked[location] = rng.choice(choice.items)
    return tuple(picked.values())


def _random_traits(rng: random.Random, occupation_id: str) -> tuple[str, ...]:
    """A random pick: some good and bad traits, then adjust until 0 to 3 points are left."""
    selectable = [t for t in TRAITS.values() if not t.profession_only]
    chosen: list[str] = []
    granted = OCCUPATIONS[occupation_id].granted_traits

    def can_add(trait_id: str) -> bool:
        held = [*granted, *chosen, *_trait_granted(chosen)]
        return trait_id not in chosen and not _excluded(trait_id, held)

    for good in (True, False):
        pool = [t.id for t in selectable if (t.cost > 0) == good]
        for _ in range(rng.randint(k.RANDOM_TRAITS_PER_SIDE_MIN, k.RANDOM_TRAITS_PER_SIDE_MAX)):
            options = [t for t in pool if can_add(t)]
            if options:
                chosen.append(rng.choice(options))
    for _ in range(k.RANDOM_ADJUST_ROUNDS_MAX):
        points = _points(occupation_id, chosen)
        if k.RANDOM_POINTS_MIN <= points <= k.RANDOM_POINTS_MAX:
            return tuple(chosen)
        too_many_points = points > k.RANDOM_POINTS_MAX
        removable = [t for t in chosen if (TRAITS[t].cost < 0) == too_many_points]
        addable = [t.id for t in selectable if (t.cost > 0) == too_many_points and can_add(t.id)]
        if removable and (not addable or rng.random() < 0.5):
            chosen.remove(rng.choice(removable))
        elif addable:
            chosen.append(rng.choice(addable))
    return ()


def randomize(rng: random.Random) -> CharacterBuild:
    """A random legal build with 0 to 3 points left."""
    occupations = list(OCCUPATIONS)
    while True:
        occupation_id = rng.choice(occupations)
        traits = _random_traits(rng, occupation_id)
        if k.RANDOM_POINTS_MIN <= _points(occupation_id, traits) <= k.RANDOM_POINTS_MAX:
            break
    appearance = _random_appearance(rng)
    return CharacterBuild(
        appearance=appearance,
        occupation_id=occupation_id,
        job_title="",
        traits=traits,
        outfit=_random_outfit(rng, appearance.gender, occupation_id, traits),
    )


def new_player(build: CharacterBuild, seed: int = 0) -> PlayerEntity:
    """The starting player for a valid build: dressed in its outfit, holding the apartment key.

    `seed` is the world seed, which the starting exercise regularity is drawn from.
    """
    resolved = resolve(build)
    worn: dict[BodyLocation, ItemEntity] = {}
    for item_id in build.outfit:
        item = ITEMS[item_id]
        assert isinstance(item, ClothingItem)
        worn[item.body_location] = ItemEntity(item=item)
    player = PlayerEntity(
        name=build.appearance.full_name,
        current_location_id=STARTING_ZONE_ID,
        current_room=ENTRY_ROOMS[STARTING_ZONE_ID],
        inventory=[ItemEntity(item=ITEMS["item_apartment_key"])],
        worn=worn,
        appearance=build.appearance,
        occupation_id=build.occupation_id,
        job_title=build.job_title,
        traits=list(resolved.traits),
        skill_boosts=resolved.skill_boosts,
    )
    engine = SkillEngine()
    for skill_id in SKILLS:
        engine.set_level(player, skill_id, resolved.skills.get(skill_id, 0))
    player.exercise.regularity = starting_regularity(build.occupation_id, seed)
    player.loss_timers = {skill_id: LOSS_TIMER_START for skill_id in PASSIVE_SKILLS}
    player.loss_timer_steps = {
        skill_id: math.floor(LOSS_TIMER_START / LOSS_TIMER_DIVISOR) for skill_id in PASSIVE_SKILLS
    }
    return player

"""The creation screen's JSON: what it offers and how a submitted build is read (character-creation)."""

from typing import Any

from data.character import creation as creation_k
from data.character.names import BEARD_STYLES, HAIR_COLOURS, HAIR_STYLES, SKIN_TONE_WORDS
from data.character.occupations import OCCUPATIONS
from data.character.presets import PRESETS
from data.character.traits import TRAITS
from data.clothing.selection import (
    DEFAULT_CLOTHING,
    OCCUPATION_CLOTHING,
    TRAIT_CLOTHING,
    GenderedClothing,
)
from data.items import ITEMS
from data.zombies.clothing import ZOMBIE_CLOTHING
from managers.character import creation
from modules.character.appearance import Appearance, Gender
from modules.character.build import CharacterBuild
from modules.item import ClothingItem


def _skill_name(skill: str) -> str:
    return skill.replace("_", " ").title()


def _outfit_lists(clothing: GenderedClothing) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Per gender, the items offered at each location; a list with no male version serves it."""
    return {
        gender.value: {
            location.value: [{"item_id": i, "name": ITEMS[i].name} for i in choice.items]
            for location, choice in (clothing.get(gender) or clothing[Gender.FEMALE]).items()
        }
        for gender in Gender
    }


def build_to_payload(build: CharacterBuild) -> dict[str, Any]:
    looks = build.appearance
    return {
        "appearance": {
            "forename": looks.forename,
            "surname": looks.surname,
            "gender": looks.gender.value,
            "skin_tone": looks.skin_tone,
            "hair_style": looks.hair_style,
            "hair_colour": looks.hair_colour,
            "beard_style": looks.beard_style,
            "backstory": looks.backstory,
        },
        "occupation_id": build.occupation_id,
        "job_title": build.job_title,
        "traits": list(build.traits),
        "outfit": list(build.outfit),
    }


def creation_screen() -> dict[str, Any]:
    """Occupations, traits, appearance word lists, outfit lists and presets."""

    def trait_entry(trait_id: str) -> dict[str, Any]:
        trait = TRAITS[trait_id]
        return {
            "id": trait.id,
            "name": trait.name,
            "description": trait.description,
            "cost": trait.cost,
            "boosts": dict(trait.boosts),
            "excludes": sorted(trait.excludes),
        }

    selectable = [t for t in TRAITS.values() if not t.profession_only]
    return {
        "occupations": [
            {
                "id": o.id,
                "name": o.name,
                "cost": o.cost,
                "granted_traits": list(o.granted_traits),
                "boosts": dict(o.boosts),
            }
            for o in OCCUPATIONS.values()
        ],
        "traits": {
            "good": [trait_entry(t.id) for t in selectable if t.cost > 0],
            "bad": [trait_entry(t.id) for t in selectable if t.cost < 0],
            "granted": [trait_entry(t.id) for t in TRAITS.values() if t.profession_only],
        },
        "skills": {skill: _skill_name(skill) for skill in creation_k.SKILLS},
        "base_skills": {"fitness": creation_k.BASE_FITNESS, "strength": creation_k.BASE_STRENGTH},
        "skill_limits": {
            "min": creation_k.SKILL_LEVEL_MIN,
            "max": creation_k.SKILL_LEVEL_MAX,
            "boost_cap": creation_k.SKILL_BOOST_CAP,
        },
        "appearance": {
            "genders": [g.value for g in Gender],
            "skin_tones": {str(tone): word for tone, word in SKIN_TONE_WORDS.items()},
            "hair_styles": list(HAIR_STYLES),
            "hair_colours": list(HAIR_COLOURS),
            "beard_styles": list(BEARD_STYLES),
            "name_max_chars": creation_k.NAME_MAX_CHARS,
            "job_title_max_chars": creation_k.JOB_TITLE_MAX_CHARS,
            "backstory_max_chars": creation_k.BACKSTORY_MAX_CHARS,
        },
        "outfits": {
            "default": _outfit_lists(DEFAULT_CLOTHING),
            "occupations": {o: _outfit_lists(c) for o, c in OCCUPATION_CLOTHING.items()},
            "traits": {t: _outfit_lists(c) for t, c in TRAIT_CLOTHING.items()},
        },
        "clothing_items": {
            item_id: {"name": item.name, "location": item.body_location.value}
            for item_id, item in ITEMS.items()
            if isinstance(item, ClothingItem) and item is not ZOMBIE_CLOTHING.get(item_id)
        },
        "min_points_to_accept": creation_k.MIN_POINTS_TO_ACCEPT,
        "presets": {
            preset_id: {
                **build_to_payload(build),
                "points_left": creation.resolve(build).points_left,
            }
            for preset_id, build in PRESETS.items()
        },
    }


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _strings(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    return tuple(value)


def build_from_payload(payload: dict[str, Any]) -> CharacterBuild | None:
    """Read a submitted build, or None when its shape is wrong (not when its rules are)."""
    looks = payload.get("appearance")
    if not isinstance(looks, dict):
        return None
    try:
        gender = Gender(looks.get("gender", Gender.MALE.value))
    except ValueError:
        return None
    skin_tone = looks.get("skin_tone", creation_k.SKIN_TONE_MIN)
    texts = {
        key: _text(looks.get(key, ""))
        for key in ("forename", "surname", "hair_style", "hair_colour", "beard_style", "backstory")
    }
    occupation_id = _text(payload.get("occupation_id"))
    job_title = _text(payload.get("job_title", ""))
    traits = _strings(payload.get("traits", []))
    outfit = _strings(payload.get("outfit", []))
    if (
        isinstance(skin_tone, bool)
        or not isinstance(skin_tone, int)
        or None in (occupation_id, job_title, traits, outfit, *texts.values())
    ):
        return None
    assert occupation_id is not None and job_title is not None
    assert traits is not None and outfit is not None
    return CharacterBuild(
        appearance=Appearance(
            forename=texts["forename"] or "",
            surname=texts["surname"] or "",
            gender=gender,
            skin_tone=skin_tone,
            hair_style=texts["hair_style"] or "",
            hair_colour=texts["hair_colour"] or "",
            beard_style=texts["beard_style"] or "",
            backstory=texts["backstory"] or "",
        ),
        occupation_id=occupation_id,
        job_title=job_title,
        traits=traits,
        outfit=outfit,
    )

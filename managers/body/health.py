"""The player's body: health helpers, wounds, pain, the limp and the zombie infection (health)."""

import random
from collections import defaultdict

from data import carry as carry_k
from data.body import health as body_k
from data.body import status_effects as status_effect_k
from data.body import survival as survival_k
from data.body import thermal as thermal_k
from data.character import traits as trait_k
from data.zombies import lore as zombie_lore
from managers import carry
from managers.body.stats.status_effects import player_status_effect_levels
from managers.body.thermoregulator import health_cap
from modules import units
from modules.body.parts import (
    PART_HEALTH_MAX,
    PART_WEIGHT,
    BodyPart,
    PartState,
    general_wound_infection,
    overall_health,
)
from modules.body.stats import CharacterStat, StatusEffect
from modules.entity.player import PlayerEntity

HOUR_PER_MINUTE = 1 / 60


def reduce_general(player: PlayerEntity, amount: float) -> None:
    """Every part loses `amount / 17 / weight`, so a full body loses `amount` overall."""
    if player.asleep and overall_health(player.body) <= body_k.WAKE_HEALTH:
        player.asleep = False
    for part, state in player.body.items():
        state.health = max(0.0, state.health - amount / body_k.PART_COUNT / PART_WEIGHT[part])


def kill(player: PlayerEntity) -> None:
    """Take every part to zero health."""
    for state in player.body.values():
        state.health = 0.0


def add_general(player: PlayerEntity, amount: float) -> None:
    """Split `amount` evenly over the parts below full health, each capped at full."""
    hurt = [state for state in player.body.values() if state.health < PART_HEALTH_MAX]
    if not hurt:
        return
    share = amount / len(hurt)
    for state in hurt:
        state.health = min(PART_HEALTH_MAX, state.health + share)


def open_wounds(state: PartState) -> list[str]:
    """The wound kinds still open on the part, in the order they are listed."""
    return [
        kind
        for kind, time in (
            (body_k.SCRATCH, state.scratch_time),
            (body_k.LACERATION, state.cut_time),
            (body_k.BITE, state.bite_time),
        )
        if time > 0
    ]


def clear_bandage(state: PartState) -> None:
    state.bandage = None
    state.bandage_life = 0.0
    state.bandage_alcoholic = False


def generate_bleeding(state: PartState, part: BodyPart, rng: random.Random) -> None:
    """Set `bleeding_time` from every wound open on the part, drawing in the spec's order."""
    total = 0.0
    if state.scratch_time > 0:
        total += rng.uniform(*body_k.BLEEDING_TIME_SCRATCH) * state.scratch_time
    if state.cut_time > 0:
        total += rng.uniform(*body_k.BLEEDING_TIME_CUT) * state.cut_time
    if state.bite_time > 0:
        total += rng.uniform(*body_k.BLEEDING_TIME_BITE)
    state.bleeding_time = total * body_k.PARTS[part].bleeding


def _healer_column(traits: list[str]) -> int:
    if trait_k.FAST_HEALER_ID in traits:
        return body_k.FAST_HEALER_INDEX
    if trait_k.SLOW_HEALER_ID in traits:
        return body_k.SLOW_HEALER_INDEX
    return 0


def land_wound(
    player: PlayerEntity,
    kind: str,
    part: BodyPart,
    damage: float,
    zombie_infected: bool,
    rng: random.Random,
) -> None:
    """A wound lands: the part takes the damage, loses its bandage and gets the wound's time."""
    state = player.body[part]
    state.health = max(0.0, state.health - damage)
    clear_bandage(state)
    low, high = body_k.WOUND_TIME[kind][_healer_column(player.traits)]
    time = rng.uniform(low, high)
    if kind == body_k.SCRATCH:
        state.scratch_time = time
    elif kind == body_k.LACERATION:
        state.cut_time = time
    else:
        state.bite_time = time
        state.infected_wound = True
    if zombie_infected:
        state.zombie_infected = True
    if kind != body_k.SCRATCH:
        generate_bleeding(state, part, rng)


def heal_per_hour(levels: dict[StatusEffect, int], *, asleep: bool, fed: bool) -> float:
    """Health the body gives back per game hour in this state (health: Healing)."""
    hungry = levels[StatusEffect.HUNGRY]
    thirst = levels[StatusEffect.THIRST]
    if hungry >= body_k.HEAL_NONE_LEVEL or thirst >= body_k.HEAL_NONE_LEVEL:
        return 0.0
    if asleep:
        rate = body_k.HEAL_ASLEEP_PER_HOUR
    else:
        worst = max(
            hungry,
            thirst,
            levels[StatusEffect.SICK] if levels[StatusEffect.SICK] < body_k.HEAL_NONE_LEVEL else 0,
        )
        if worst >= body_k.HEAL_SEVERELY_REDUCED_LEVEL:
            rate = body_k.HEAL_SEVERELY_REDUCED_PER_HOUR
        elif worst >= body_k.HEAL_REDUCED_LEVEL:
            rate = body_k.HEAL_REDUCED_PER_HOUR
        else:
            rate = body_k.HEAL_AWAKE_PER_HOUR
    return rate + (body_k.HEAL_FOOD_PER_HOUR if fed else 0.0)


def infection_chance(state: PartState) -> float:
    """The chance a wound on this part gets infected in one game minute."""
    n = body_k.WOUND_INFECTION_N_BASE
    if not state.bandaged:
        n += body_k.WOUND_INFECTION_N_NO_BANDAGE
    elif state.bandage_life <= 0:
        n += body_k.WOUND_INFECTION_N_DIRTY_BANDAGE
    if state.scratch_time > 0:
        n += body_k.WOUND_INFECTION_N_SCRATCH
    if state.cut_time > 0:
        n += body_k.WOUND_INFECTION_N_CUT
    n = max(n, body_k.WOUND_INFECTION_N_FLOOR)
    return 1 - (1 - 1 / n) ** units.real_frames_per_minute()


def _can_catch_infection(state: PartState) -> bool:
    if not (state.scratch_time > 0 or state.cut_time > 0) or state.zombie_infected:
        return False
    return not (state.bandaged and state.bandage_alcoholic and state.bandage_life > 0)


def part_pain(state: PartState) -> float:
    """The pain one part gives, before its pain multiplier (health: Pain from each part)."""
    pain = (
        body_k.PAIN_SCRATCH_PER_UNIT * state.scratch_time
        + body_k.PAIN_CUT_PER_UNIT * state.cut_time
    )
    if state.bite_time > 0:
        pain += body_k.PAIN_BITE_BANDAGED if state.bandaged else body_k.PAIN_BITE_OPEN
    if state.bandaged:
        pain /= body_k.PAIN_BANDAGE_DIVISOR
    if state.wound_infection > 0:
        pain += state.wound_infection
    return pain + state.extra_pain + state.stiffness / body_k.PAIN_STIFFNESS_DIVISOR


def pain_target(player: PlayerEntity) -> float:
    return sum(part_pain(state) * body_k.PARTS[part].pain for part, state in player.body.items())


def next_pain(pain: float, target: float) -> float:
    """Pain after a minute: it eases toward a higher target and drops to a lower one at once."""
    if target > pain:
        return target - (target - pain) * body_k.PAIN_RISE_PER_MIN_FACTOR
    return target


def _limp_part(state: PartState, part: BodyPart) -> float:
    foot = part in body_k.LIMP_FOOT_PARTS
    value = 0.0
    if foot and state.bite_time > 0:
        value += body_k.LIMP_FOOT_BITE_TERM * (
            body_k.LIMP_FOOT_BITE_BANDAGED_MULT if state.bandaged else 1.0
        )
    if (
        state.scratch_time > body_k.LIMP_SCRATCH_MIN
        or state.cut_time > body_k.LIMP_CUT_MIN
        or state.bite_time > 0
    ):
        scratch_divisor = body_k.LIMP_FOOT_SCRATCH_DIVISOR if foot else body_k.LIMP_SCRATCH_DIVISOR
        cut_divisor = body_k.LIMP_FOOT_CUT_DIVISOR if foot else body_k.LIMP_CUT_DIVISOR
        wounds = (
            state.scratch_time / scratch_divisor
            + state.cut_time / cut_divisor
            + state.bite_time / body_k.LIMP_BITE_DIVISOR
        )
        value += wounds / body_k.LIMP_BANDAGED_DIVISOR if state.bandaged else wounds
    return value


def limp_value(player: PlayerEntity) -> float:
    return sum(_limp_part(player.body[part], part) for part in body_k.LIMP_PARTS)


def limp_factor(player: PlayerEntity) -> float:
    """The factor every pace is multiplied by while limping; 1 below the limp threshold."""
    value = limp_value(player)
    if value <= body_k.LIMP_THRESHOLD:
        return 1.0
    return max(body_k.LIMP_SPEED_FLOOR, 1 - value / body_k.LIMP_SPEED_DIVISOR)


def _cold_hands(player: PlayerEntity) -> float:
    total = 0.0
    for part, weight in body_k.ACTION_TIME_COLD_HANDS.items():
        skin = player.thermal.skin[part]
        if skin >= body_k.COLD_HANDS_SKIN_LIMIT_C:
            continue
        cold = (1 - (skin - body_k.COLD_HANDS_SKIN_FLOOR_C) / body_k.COLD_HANDS_SKIN_RANGE_C) ** 2
        total += (
            weight
            * body_k.ACTION_TIME_COLD_HANDS_WEIGHT
            * cold
            * thermal_k.THERMAL_NODES[part].skin_surface
        )
    return 1 + total


def action_time_multiplier(player: PlayerEntity) -> float:
    """How much longer a timed action takes from mood, drink, hand pain and cold hands."""
    levels = player_status_effect_levels(player)
    hand_pain = sum(part_pain(player.body[part]) for part in body_k.HAND_PAIN_PARTS)
    return (
        (1 + levels[StatusEffect.UNHAPPY] / body_k.ACTION_TIME_UNHAPPY_DIVISOR)
        * (1 + levels[StatusEffect.DRUNK] / body_k.ACTION_TIME_DRUNK_DIVISOR)
        * (1 + hand_pain / body_k.ACTION_TIME_HAND_PAIN_DIVISOR)
        * _cold_hands(player)
    )


def _part_word(part: BodyPart) -> str:
    return zombie_lore.BODY_PART_WORDS[part.value]


class BodyEngine:
    """Runs the body minute for the player: wounds, bleeding, healing and what they cost."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self.death_fact = ""
        self._reported: set[str] = set()
        self._losses: dict[str, float] = defaultdict(float)

    def begin_turn(self) -> None:
        """Forget which weakening facts were already given, so each turn gives each once."""
        self._reported = set()

    def minute(self, player: PlayerEntity, hours_survived: float) -> list[str]:
        """One game minute of the body; sets `death_fact` when it kills the player."""
        self.death_fact = ""
        self._losses = defaultdict(float)
        facts: list[str] = []
        self._thermal_cap(player)
        if overall_health(player.body) <= 0:
            self.death_fact = self._death_fact(player)
            return facts
        self._zombie_infection_onset(player, hours_survived)
        self._regenerate(player)
        self._status_effect_damage(player, facts)
        self._pain(player)
        self._zombie_infection_progression(player, hours_survived)
        draining = bool(player.exercise.future_stiffness)
        for part, state in player.body.items():
            self._part(player, part, state, facts, draining)
        player.reduce_infection_power = max(
            0.0, player.reduce_infection_power - body_k.ANTIBIOTIC_DECAY_PER_HOUR * HOUR_PER_MINUTE
        )
        self._stress(player)
        if overall_health(player.body) <= 0:
            self.death_fact = self._death_fact(player)
        return facts

    def overload(self, player: PlayerEntity, *, resting: bool) -> None:
        """At Heavy Load 3 or 4, awake and not resting, health above 75 loses HP a minute, down to 75."""
        if player.asleep or resting:
            return
        level = player_status_effect_levels(player)[StatusEffect.HEAVY_LOAD]
        health = overall_health(player.body)
        if level < carry_k.OVERLOAD_MIN_LEVEL or health <= carry_k.OVERLOAD_HEALTH_ABOVE:
            return
        loss = min(carry.overload_loss(level), health - carry_k.OVERLOAD_HEALTH_ABOVE)
        self._lose(player, "overload", loss)

    @staticmethod
    def _pain(player: PlayerEntity) -> None:
        pain = player.stats.get(CharacterStat.PAIN)
        if player.pain_effect_minutes > 0:
            drop = body_k.PAINKILLER_PAIN_DROP_PER_HOUR * HOUR_PER_MINUTE
            player.stats.set(CharacterStat.PAIN, max(0.0, pain - drop))
            player.pain_effect_minutes = max(0.0, player.pain_effect_minutes - 1)
        else:
            player.stats.set(CharacterStat.PAIN, next_pain(pain, pain_target(player)))

    def _lose(self, player: PlayerEntity, cause: str, amount: float) -> None:
        before = overall_health(player.body)
        reduce_general(player, amount)
        self._losses[cause] += before - overall_health(player.body)

    def _kill(self, player: PlayerEntity, cause: str) -> None:
        """Kill the player even when a part at 0 would stop `reduce_general` short."""
        before = overall_health(player.body)
        kill(player)
        self._losses[cause] += before

    def _thermal_cap(self, player: PlayerEntity) -> None:
        stage = player.thermal.thermal_damage
        if stage <= 0:
            return
        if stage >= 1:
            self._kill(player, "thermal")
            return
        health = overall_health(player.body)
        cap = health_cap(stage)
        if health > cap:
            self._lose(player, "thermal", health - cap)

    def _regenerate(self, player: PlayerEntity) -> None:
        rate = heal_per_hour(
            player_status_effect_levels(player),
            asleep=player.asleep,
            fed=player.food_eaten_timer > 0,
        )
        add_general(player, rate * HOUR_PER_MINUTE)

    def _status_effect_damage(self, player: PlayerEntity, facts: list[str]) -> None:
        levels = player_status_effect_levels(player)
        stats = player.stats
        severe = survival_k.SEVERE_STATUS_EFFECT_LEVEL
        sources: list[tuple[float, str]] = []
        if levels[StatusEffect.HUNGRY] >= severe:
            sources.append((survival_k.STARVING_HP_LOSS_per_hour, "starvation"))
        if levels[StatusEffect.THIRST] >= severe:
            sources.append((survival_k.DYING_OF_THIRST_HP_LOSS_per_hour, "thirst"))
        if levels[StatusEffect.SICK] >= severe:
            zombie_infection = stats.get(CharacterStat.ZOMBIE_INFECTION)
            if stats.get(CharacterStat.FOOD_SICKNESS) > zombie_infection:
                sources.append((survival_k.FEVER_HP_LOSS_per_hour, "fever"))
            elif general_wound_infection(player.body) > zombie_infection:
                sources.append((survival_k.FEVER_HP_LOSS_per_hour, "infection"))
        if levels[StatusEffect.BLEEDING] >= status_effect_k.BLEEDING_LEVEL_CAP:
            sources.append((survival_k.FEVER_HP_LOSS_per_hour, "bleeding"))
        for rate, cause in sources:
            self._lose(player, cause, rate * HOUR_PER_MINUTE)
            if cause != "bleeding" and cause not in self._reported:
                self._reported.add(cause)
                facts.append(
                    body_k.WEAKENING_FACT.format(
                        name=player.appearance.forename, cause=body_k.WEAKENING_WORD[cause]
                    )
                )

    def _part(
        self,
        player: PlayerEntity,
        part: BodyPart,
        state: PartState,
        facts: list[str],
        stiffness_draining: bool,
    ) -> None:
        name = _part_word(part)
        state.extra_pain = max(
            0.0, state.extra_pain - body_k.EXTRA_PAIN_DECAY_PER_HOUR * HOUR_PER_MINUTE
        )
        if not stiffness_draining:
            state.stiffness = max(
                0.0, state.stiffness - body_k.STIFFNESS_DECAY_PER_HOUR * HOUR_PER_MINUTE
            )
        was_bleeding = state.bleeding
        self._wound_damage(player, part, state)
        self._timers(state, name, facts)
        self._bandage_wear(state, name, facts)
        if state.bleeding:
            rate = (
                body_k.BLEED_HP_PER_HOUR_PER_UNIT_NECK
                if part is BodyPart.NECK
                else body_k.BLEED_HP_PER_HOUR_PER_UNIT
            )
            self._lose(player, "bleeding", rate * state.bleeding_time * HOUR_PER_MINUTE)
        if was_bleeding and not state.bleeding:
            facts.append(body_k.STOPPED_BLEEDING_FACT.format(part=name))
        self._infection(player, state)

    def _infection(self, player: PlayerEntity, state: PartState) -> None:
        if not state.infected_wound:
            state.alcohol = max(
                0.0, state.alcohol - body_k.ALCOHOL_DECAY_PER_HOUR * HOUR_PER_MINUTE
            )
            if _can_catch_infection(state) and self._rng.random() < infection_chance(state):
                state.infected_wound = True
            return
        treated = False
        if state.alcohol > 0:
            fall = body_k.WOUND_INFECTION_ALCOHOL_PER_HOUR * HOUR_PER_MINUTE
            state.alcohol = max(0.0, state.alcohol - fall)
            state.wound_infection -= fall
            treated = True
        if player.reduce_infection_power > 0:
            fall = body_k.WOUND_INFECTION_POWER_PER_HOUR * HOUR_PER_MINUTE
            state.wound_infection -= fall
            player.reduce_infection_power = max(0.0, player.reduce_infection_power - fall)
            treated = True
        if not treated:
            rise = (
                body_k.WOUND_INFECTION_ZOMBIE_RISE_PER_HOUR
                if state.zombie_infected
                else body_k.WOUND_INFECTION_RISE_PER_HOUR
            )
            state.wound_infection += rise * HOUR_PER_MINUTE
        if state.bandaged and state.bandage_life > 0 and state.bandage_alcoholic:
            state.wound_infection -= (
                body_k.WOUND_INFECTION_ALCOHOL_BANDAGE_PER_HOUR * HOUR_PER_MINUTE
            )
        state.wound_infection = min(body_k.WOUND_INFECTION_MAX, state.wound_infection)
        if state.wound_infection <= 0:
            state.infected_wound = False
        state.wound_infection = max(body_k.WOUND_INFECTION_FLOOR, state.wound_infection)

    def _zombie_infection_onset(self, player: PlayerEntity, hours_survived: float) -> None:
        if player.zombie_infection_since is not None or not any(
            s.zombie_infected for s in player.body.values()
        ):
            return
        player.zombie_infection_since = hours_survived
        hours = (
            self._rng.uniform(*body_k.ZOMBIE_INFECTION_DAYS_RANGE)
            * body_k.ZOMBIE_INFECTION_HOURS_PER_DAY
        )
        if trait_k.RESILIENT_ID in player.traits:
            hours *= body_k.ZOMBIE_INFECTION_RESILIENT_MULT
        if trait_k.PRONE_TO_ILLNESS_ID in player.traits:
            hours *= body_k.ZOMBIE_INFECTION_PRONE_MULT
        player.zombie_infection_hours = hours

    def _zombie_infection_progression(self, player: PlayerEntity, hours_survived: float) -> None:
        if player.zombie_infection_since is None:
            return
        elapsed = hours_survived - player.zombie_infection_since
        x = (
            1.0
            if player.zombie_infection_hours <= 0
            else min(elapsed / player.zombie_infection_hours, 1.0)
        )
        player.stats.set(CharacterStat.ZOMBIE_INFECTION, 100 * x)
        if x >= 1.0:
            self._kill(player, "zombie_infection")
            return
        health = overall_health(player.body)
        cap = 100 * (1 - x**body_k.ZOMBIE_INFECTION_CAP_EXPONENT)
        if cap <= body_k.ZOMBIE_INFECTION_CAP_NONE_ABOVE and health > cap:
            self._lose(player, "zombie_infection", health - cap)

    @staticmethod
    def _stress(player: PlayerEntity) -> None:
        parts = player.body.values()
        sources = sum(
            (
                any(s.bite_time > 0 and not s.bandaged for s in parts),
                any(s.scratch_time > 0 and not s.bandaged for s in parts),
                player.zombie_infection_since is not None,
            )
        )
        player.stats.add(
            CharacterStat.STRESS, sources * body_k.STRESS_FROM_WOUND_PER_HOUR * HOUR_PER_MINUTE
        )

    def _wound_damage(self, player: PlayerEntity, part: BodyPart, state: PartState) -> None:
        if state.bandaged:
            return
        rate = 0.0
        if state.scratch_time > 0:
            rate += body_k.WOUND_DAMAGE_PER_HOUR[body_k.SCRATCH]
        if state.cut_time > 0:
            rate += body_k.WOUND_DAMAGE_PER_HOUR[body_k.LACERATION]
        if state.bite_time > 0:
            rate += body_k.WOUND_DAMAGE_PER_HOUR[body_k.BITE]
        if not rate:
            return
        if part is BodyPart.NECK:
            rate *= body_k.NECK_DAMAGE_SCALER_MULT
        before = overall_health(player.body)
        state.health = max(0.0, state.health - rate * HOUR_PER_MINUTE)
        self._losses["wounds"] += before - overall_health(player.body)

    @staticmethod
    def _timers(state: PartState, name: str, facts: list[str]) -> None:
        column = 1 if state.bandaged else 0
        healed: list[str] = []
        if state.scratch_time > 0:
            state.scratch_time = max(
                0.0, state.scratch_time - body_k.SCRATCH_DECAY_PER_HOUR[column] * HOUR_PER_MINUTE
            )
            if state.scratch_time == 0:
                state.bleeding_time = 0.0
                healed.append(body_k.SCRATCH)
        if state.cut_time > 0:
            state.cut_time = max(
                0.0, state.cut_time - body_k.CUT_DECAY_PER_HOUR[column] * HOUR_PER_MINUTE
            )
            if state.cut_time == 0:
                state.bleeding_time = 0.0
                healed.append(body_k.LACERATION)
        if state.bite_time > 0:
            state.bite_time = max(
                0.0, state.bite_time - body_k.BITE_DECAY_PER_HOUR[column] * HOUR_PER_MINUTE
            )
            if state.bite_time == 0:
                healed.append(body_k.BITE)
        if state.bleeding_time > 0:
            state.bleeding_time = max(
                0.0, state.bleeding_time - body_k.BLEEDING_DECAY_PER_HOUR[column] * HOUR_PER_MINUTE
            )
        for kind in healed:
            state.bandage_xp_ready = True
            facts.append(body_k.HEALED_FACT.format(kind=kind, part=name))
        if healed and not state.wounded:
            state.infected_wound = False
            state.wound_infection = 0.0

    @staticmethod
    def _bandage_wear(state: PartState, name: str, facts: list[str]) -> None:
        if not state.bandaged or state.bandage_life <= 0:
            return
        wear = 0.0
        if state.bite_time > 0:
            wear += body_k.BANDAGE_WEAR_BITE_PER_HOUR
        if state.bleeding_time > 0:
            wear += body_k.BANDAGE_WEAR_BLEEDING_PER_HOUR
        if state.infected_wound:
            wear += body_k.BANDAGE_WEAR_INFECTED_PER_HOUR
        if state.scratch_time > 0:
            wear += body_k.BANDAGE_WEAR_SCRATCH_PER_HOUR
        if state.cut_time > 0:
            wear += body_k.BANDAGE_WEAR_CUT_PER_HOUR
        state.bandage_life = max(0.0, state.bandage_life - wear * HOUR_PER_MINUTE)
        if state.bandage_life == 0:
            state.bandage_xp_ready = True
            facts.append(body_k.SOAKED_FACT.format(part=name))

    def _death_fact(self, player: PlayerEntity) -> str:
        name = player.appearance.forename
        cause = max(self._losses, key=lambda each: self._losses[each], default="wounds")
        if cause == "bleeding":
            return body_k.DEATH_BLEEDING.format(name=name)
        if cause == "wounds":
            return body_k.DEATH_WOUNDS.format(name=name)
        if cause == "zombie_infection":
            return body_k.DEATH_ZOMBIE_INFECTION.format(name=name)
        if cause == "thermal":
            cold = player.stats.get(CharacterStat.TEMPERATURE) < CharacterStat.TEMPERATURE.default
            return (body_k.DEATH_COLD if cold else body_k.DEATH_HEAT).format(name=name)
        return body_k.DEATH_STATUS_EFFECT.format(name=name, cause=cause)

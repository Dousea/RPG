"""Body parts, body locations (clothing) and the health of each part (health)."""

from dataclasses import dataclass
from enum import StrEnum


class BodyPart(StrEnum):
    HAND_L = "hand_l"
    HAND_R = "hand_r"
    FOREARM_L = "forearm_l"
    FOREARM_R = "forearm_r"
    UPPERARM_L = "upperarm_l"
    UPPERARM_R = "upperarm_r"
    TORSO_UPPER = "torso_upper"
    TORSO_LOWER = "torso_lower"
    HEAD = "head"
    NECK = "neck"
    GROIN = "groin"
    UPPERLEG_L = "upperleg_l"
    UPPERLEG_R = "upperleg_r"
    LOWERLEG_L = "lowerleg_l"
    LOWERLEG_R = "lowerleg_r"
    FOOT_L = "foot_l"
    FOOT_R = "foot_r"


class BodyLocation(StrEnum):
    """The places an item can be worn, declared from innermost layer to outermost."""

    BANDAGE = "base:bandage"
    WOUND = "base:wound"
    BELTEXTRA = "base:beltextra"
    BELT = "base:belt"
    BELLYBUTTON = "base:bellybutton"
    MAKEUP_FULLFACE = "base:makeup_fullface"
    MAKEUP_EYES = "base:makeup_eyes"
    MAKEUP_EYESSHADOW = "base:makeup_eyesshadow"
    MAKEUP_LIPS = "base:makeup_lips"
    MASK = "base:mask"
    MASKEYES = "base:maskeyes"
    MASKFULL = "base:maskfull"
    UNDERWEARBOTTOM = "base:underwearbottom"
    UNDERWEARTOP = "base:underweartop"
    UNDERWEAR = "base:underwear"
    UNDERWEAREXTRA1 = "base:underwearextra1"
    UNDERWEAREXTRA2 = "base:underwearextra2"
    HAT = "base:hat"
    FULLHAT = "base:fullhat"
    EARS = "base:ears"
    EARTOP = "base:eartop"
    NOSE = "base:nose"
    TORSO1 = "base:torso1"
    TORSO1LEGS1 = "base:torso1legs1"
    TANKTOP = "base:tanktop"
    TSHIRT = "base:tshirt"
    SHORTSLEEVESHIRT = "base:shortsleeveshirt"
    LEFTWRIST = "base:leftwrist"
    RIGHTWRIST = "base:rightwrist"
    SHIRT = "base:shirt"
    RIGHTARM = "base:rightarm"
    LEFTARM = "base:leftarm"
    NECK = "base:neck"
    NECK_TEXTURE = "base:neck_texture"
    NECKLACE = "base:necklace"
    NECKLACE_LONG = "base:necklace_long"
    RIGHT_MIDDLEFINGER = "base:right_middlefinger"
    LEFT_MIDDLEFINGER = "base:left_middlefinger"
    LEFT_RINGFINGER = "base:left_ringfinger"
    RIGHT_RINGFINGER = "base:right_ringfinger"
    HANDS = "base:hands"
    HANDSLEFT = "base:handsleft"
    HANDSRIGHT = "base:handsright"
    CALF_LEFT_TEXTURE = "base:calf_left_texture"
    CALF_RIGHT_TEXTURE = "base:calf_right_texture"
    SOCKS = "base:socks"
    LEGS1 = "base:legs1"
    SHOES = "base:shoes"
    CODPIECE = "base:codpiece"
    SHORTSSHORT = "base:shortsshort"
    SHORTPANTS = "base:shortpants"
    PANTS_SKINNY = "base:pants_skinny"
    GAITER_RIGHT = "base:gaiter_right"
    GAITER_LEFT = "base:gaiter_left"
    PANTS = "base:pants"
    SKIRT = "base:skirt"
    DRESS = "base:dress"
    LEGS5 = "base:legs5"
    FOREARM_LEFT = "base:forearm_left"
    FOREARM_RIGHT = "base:forearm_right"
    LONGSKIRT = "base:longskirt"
    LONGDRESS = "base:longdress"
    VESTTEXTURE = "base:vesttexture"
    BODYCOSTUME = "base:bodycostume"
    SPORTSHOULDERPAD = "base:sportshoulderpad"
    GORGET = "base:gorget"
    JERSEY = "base:jersey"
    SWEATER = "base:sweater"
    SWEATERHAT = "base:sweaterhat"
    PANTSEXTRA = "base:pantsextra"
    JACKET = "base:jacket"
    JACKET_DOWN = "base:jacket_down"
    JACKET_BULKY = "base:jacket_bulky"
    JACKETHAT = "base:jackethat"
    JACKETHAT_BULKY = "base:jackethat_bulky"
    JACKETSUIT = "base:jacketsuit"
    FULLSUIT = "base:fullsuit"
    BOILERSUIT = "base:boilersuit"
    FULLSUITHEAD = "base:fullsuithead"
    FULLSUITHEADSCBA = "base:fullsuitheadscba"
    KNEE_LEFT = "base:knee_left"
    KNEE_RIGHT = "base:knee_right"
    CALF_LEFT = "base:calf_left"
    CALF_RIGHT = "base:calf_right"
    THIGH_LEFT = "base:thigh_left"
    THIGH_RIGHT = "base:thigh_right"
    SPORTSHOULDERPADONTOP = "base:sportshoulderpadontop"
    SHOULDERPADRIGHT = "base:shoulderpadright"
    SHOULDERPADLEFT = "base:shoulderpadleft"
    ELBOW_LEFT = "base:elbow_left"
    ELBOW_RIGHT = "base:elbow_right"
    FULLTOP = "base:fulltop"
    BATHROBE = "base:bathrobe"
    FANNYPACKFRONT = "base:fannypackfront"
    FANNYPACKBACK = "base:fannypackback"
    WEBBING = "base:webbing"
    SCBA = "base:scba"
    SCBANOTANK = "base:scbanotank"
    AMMOSTRAP = "base:ammostrap"
    SATCHEL = "base:satchel"
    SHOULDERHOLSTER = "base:shoulderholster"
    ANKLEHOLSTER = "base:ankleholster"
    TORSOEXTRA = "base:torsoextra"
    TORSOEXTRAVEST = "base:torsoextravest"
    TORSOEXTRAVESTBULLET = "base:torsoextravestbullet"
    CUIRASS = "base:cuirass"
    TAIL = "base:tail"
    FULLROBE = "base:fullrobe"
    BACK = "base:back"
    LEFTEYE = "base:lefteye"
    RIGHTEYE = "base:righteye"
    EYES = "base:eyes"
    SCARF = "base:scarf"
    ZEDDMG = "base:zeddmg"


LAYER_ORDER: dict[BodyLocation, int] = {location: i for i, location in enumerate(BodyLocation)}


PART_WEIGHT: dict[BodyPart, float] = {  # health: overall health lost per point of part damage
    BodyPart.HAND_L: 0.1,
    BodyPart.HAND_R: 0.1,
    BodyPart.FOREARM_L: 0.2,
    BodyPart.FOREARM_R: 0.2,
    BodyPart.UPPERARM_L: 0.3,
    BodyPart.UPPERARM_R: 0.3,
    BodyPart.TORSO_UPPER: 0.35,
    BodyPart.TORSO_LOWER: 0.4,
    BodyPart.HEAD: 0.6,
    BodyPart.NECK: 0.7,
    BodyPart.GROIN: 0.4,
    BodyPart.UPPERLEG_L: 0.3,
    BodyPart.UPPERLEG_R: 0.3,
    BodyPart.LOWERLEG_L: 0.2,
    BodyPart.LOWERLEG_R: 0.2,
    BodyPart.FOOT_L: 0.2,
    BodyPart.FOOT_R: 0.2,
}
PART_HEALTH_MAX = 100.0  # health
OVERALL_DAMAGE_CAP = 100.0  # health
GENERAL_INFECTION_PER_LEVEL = 10  # health
GENERAL_INFECTION_CAP = 100.0  # health


@dataclass
class PartState:
    """One body part: its health, open wounds, bandage and infection (health)."""

    health: float = PART_HEALTH_MAX
    scratch_time: float = 0.0
    cut_time: float = 0.0
    bite_time: float = 0.0
    bleeding_time: float = 0.0
    bandage: str | None = None
    bandage_life: float = 0.0
    bandage_alcoholic: bool = False
    bandage_xp_ready: bool = True
    zombie_infected: bool = False
    infected_wound: bool = False
    wound_infection: float = 0.0
    alcohol: float = 0.0
    extra_pain: float = 0.0
    stiffness: float = 0.0

    @property
    def bandaged(self) -> bool:
        return self.bandage is not None

    @property
    def bleeding(self) -> bool:
        return self.bleeding_time > 0 and not self.bandaged

    @property
    def injured(self) -> bool:
        return (
            self.scratch_time > 0
            or self.cut_time > 0
            or self.bite_time > 0
            or self.bleeding_time > 0
        )

    @property
    def wounded(self) -> bool:
        """Whether any wound time is still running."""
        return self.scratch_time > 0 or self.cut_time > 0 or self.bite_time > 0


def new_body() -> dict[BodyPart, PartState]:
    return {part: PartState() for part in BodyPart}


def overall_damage(body: dict[BodyPart, PartState]) -> float:
    total = sum(
        (PART_HEALTH_MAX - state.health) * PART_WEIGHT[part] for part, state in body.items()
    )
    return min(OVERALL_DAMAGE_CAP, total)


def overall_health(body: dict[BodyPart, PartState]) -> float:
    """100 less the weighted damage of every part, the damage capped at 100."""
    return OVERALL_DAMAGE_CAP - overall_damage(body)


def general_wound_infection(body: dict[BodyPart, PartState]) -> float:
    """Ten times the infection levels of the infected wounds, at most 100."""
    total = sum(
        state.wound_infection
        for state in body.values()
        if state.infected_wound and state.wound_infection > 0
    )
    return min(GENERAL_INFECTION_CAP, GENERAL_INFECTION_PER_LEVEL * total)

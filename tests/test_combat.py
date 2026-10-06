"""ATTACK resolution: weapons, damage and trait reactions."""

import random
import unittest

from data.items import ITEMS
from data.perks import PERKS
from data.traits import TRAITS
from managers.game import GameManager
from modules.action.types import AttackAction
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.item import MeleeWeaponItem, RangedWeaponItem
from tests.support import simulate


def _npc(gm: GameManager, name: str) -> NpcEntity:
    npc = gm.resolve_npc(name)
    assert npc is not None
    return npc


def _damage(item_id: str) -> int:
    item = ITEMS[item_id]
    assert isinstance(item, MeleeWeaponItem | RangedWeaponItem)
    return item.damage


class CombatResolutionTests(unittest.TestCase):
    def _fixed_rng(self) -> random.Random:
        # A jitter-free RNG so damage numbers are exact in assertions.
        rng = random.Random()
        rng.uniform = lambda a, b: 0.0
        return rng

    def test_unarmed_attack_deals_damage_and_reports_it(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"  # Emma starts here
        emma = _npc(gm, "Emma")
        before = emma.hit_points
        facts = simulate(gm, AttackAction(target_name="Emma"), rng=self._fixed_rng())
        self.assertLess(emma.hit_points, before)
        self.assertIn("Attack Emma", facts[0])

    def test_equipped_weapon_deals_its_damage(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"  # Emma starts here
        crowbar = ItemEntity(item=ITEMS["item_crowbar"])
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = crowbar
        emma = _npc(gm, "Emma")
        before = emma.hit_points
        simulate(gm, AttackAction(target_name="Emma"), rng=self._fixed_rng())
        self.assertEqual(before - emma.hit_points, _damage("item_crowbar"))

    def test_small_frame_takes_more_damage_than_an_unmodified_defender(self):
        # TraitID_SmallFrame's WeaponDamageTakenEffect (+10% damage taken)
        # must reach its handler through managers/events.py's matcher.
        # The pistol's damage (10) is used rather than the crowbar's (5) so
        # the 10% bump survives int() truncation in the assertion below.
        gm = GameManager()
        gm.player.current_location_id = "zone_building"  # Emma starts here
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(
            item=ITEMS["item_pistol"]
        )
        # Baseline: attack an NPC with no traits (Emma has none).
        baseline_npc = _npc(gm, "Emma")
        before = baseline_npc.hit_points
        simulate(gm, AttackAction(target_name="Emma"), rng=self._fixed_rng())
        baseline_damage = before - baseline_npc.hit_points

        # Now attack a stand-in defender carrying Small Frame, whose
        # WeaponDamageTakenEffect multiplies incoming damage by 1.1.
        gm2 = GameManager()
        gm2.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(
            item=ITEMS["item_pistol"]
        )
        marcus = _npc(gm2, "Marcus")
        marcus.traits = [TRAITS["TraitID_SmallFrame"]]  # type: ignore[attr-defined]
        marcus.current_location_id = gm2.player.current_location_id
        before2 = marcus.hit_points
        simulate(gm2, AttackAction(target_name="Marcus"), rng=self._fixed_rng())
        modified_damage = before2 - marcus.hit_points

        self.assertGreater(modified_damage, baseline_damage)

    def test_gun_slinger_deals_more_and_takes_less_ranged_damage(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"  # Emma starts here
        gm.player.perks = [PERKS["PerkID_GunSlinger"]]
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(
            item=ITEMS["item_pistol"]
        )
        emma = _npc(gm, "Emma")
        before = emma.hit_points
        simulate(gm, AttackAction(target_name="Emma"), rng=self._fixed_rng())
        dealt = before - emma.hit_points
        # Base pistol damage is 10; Gun Slinger's +20% dealt bonus applies.
        self.assertEqual(dealt, int(_damage("item_pistol") * 1.2))

    def test_attack_on_absent_npc_is_rejected_before_any_damage(self):
        gm = GameManager()
        facts = simulate(gm, AttackAction(target_name="Marcus"))
        self.assertTrue(facts[0].startswith("Refused:"))


if __name__ == "__main__":
    unittest.main()

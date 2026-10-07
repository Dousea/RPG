"""Spec 14, Outfits and Attached weapons: what a zombie wears and carries."""

import random
import unittest
from unittest import mock

from data.items import ITEMS
from data.loot.tables import BAG_TABLES, LootTable
from data.zombies import loot as zombie_loot
from data.zombies import outfits as zombie_outfits
from data.zombies.lore import STANDING_HIT_PARTS
from managers.combat.melee import SwingKind, hit_part, zombie_defence
from managers.corpses import bodies as corpses
from managers.corpses import search as loot
from managers.corpses.bodies import kill_corpse, outbreak_corpse
from managers.game import GameManager
from managers.zombies import dress as zombie_dress
from managers.zombies.population import roll_zombie, start_outbreak
from modules.body.parts import BodyLocation, BodyPart
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieEntity, ZombieState
from modules.item import ClothingItem, ContainerItem
from modules.world.location import World
from tests.combat.test_melee import FixedRng, add, street_game, swing
from tests.support import ScriptedRandom

DRAWS = 20000


def bare_zombie(outfit: str = "generic01", female: bool = False) -> ZombieEntity:
    return ZombieEntity(
        zombie_id="z1",
        zone_id="zone_street",
        health=1.0,
        speed_type=3,
        speed_mod=0.6,
        lunger=False,
        strength=3,
        memory=800,
        sight=2,
        hearing=2,
        female=female,
        outfit=outfit,
    )


class OutfitPoolTests(unittest.TestCase):
    """Spec 14, Outfits: the pool of 27 and its chances."""

    def test_the_pool_is_the_27_outfits_with_their_chances(self):
        pool = {name: (chance, sex) for name, chance, sex in zombie_outfits.ZOMBIE_OUTFIT_POOL}
        self.assertEqual(len(pool), 27)
        for name in ("generic01", "generic02", "generic03", "generic04", "generic05"):
            self.assertEqual(pool[name], (20, "any"))
        self.assertEqual(pool["generic_skirt"], (20, "female"))
        for name in ("dress_long", "dress_normal", "dress_short"):
            self.assertEqual(pool[name], (3, "female"))
        self.assertEqual(pool["office_worker"], (2, "male"))
        self.assertEqual(pool["office_worker_skirt"], (2, "female"))
        self.assertEqual(pool["young"], (2, "any"))
        self.assertEqual(pool["retiree"], (1, "any"))
        self.assertEqual(pool["student"], (1, "any"))
        for name in ("cyclist", "farmer", "varsity"):
            self.assertEqual(pool[name], (0.5, "any"))
        self.assertEqual(pool["construction_worker"], (0.5, "male"))
        self.assertEqual(pool["foreman"], (0.5, "male"))
        self.assertEqual(pool["biker"], (0.3, "any"))
        for name in ("police", "ranger", "evacuee"):
            self.assertEqual(pool[name], (0.25, "any"))
        self.assertEqual(pool["golfer"], (0.2, "any"))
        self.assertEqual(pool["police_state"], (0.1, "any"))
        self.assertEqual(pool["sanitation"], (0.1, "any"))
        self.assertEqual(pool["exterminator_suited"], (0.01, "any"))

    def test_every_outfit_has_a_reference_list_for_each_sex_it_is_pooled_for(self):
        for name, _, sex in zombie_outfits.ZOMBIE_OUTFIT_POOL:
            sexes = {"any": ("male", "female"), "male": ("male",), "female": ("female",)}[sex]
            for each in sexes:
                with self.subTest(outfit=name, sex=each):
                    self.assertTrue(zombie_outfits.ZOMBIE_OUTFIT_REFERENCES[name][each])

    def test_generic_outfits_are_91_percent_of_males_and_87_percent_of_females(self):
        rng = random.Random(4)
        for female, expected in ((False, 0.91), (True, 0.87)):
            picks = [zombie_dress.pick_outfit(rng, female) for _ in range(DRAWS)]
            generic = sum(1 for name in picks if name.startswith("generic"))
            with self.subTest(female=female):
                self.assertAlmostEqual(generic / DRAWS, expected, delta=0.01)

    def test_a_male_never_wears_a_female_outfit_and_the_reverse(self):
        rng = random.Random(5)
        pool = {name: sex for name, _, sex in zombie_outfits.ZOMBIE_OUTFIT_POOL}
        for _ in range(3000):
            self.assertNotEqual(pool[zombie_dress.pick_outfit(rng, False)], "female")
            self.assertNotEqual(pool[zombie_dress.pick_outfit(rng, True)], "male")


class OutfitItemTests(unittest.TestCase):
    """Spec 14, Outfits: a reference's probability and its choices."""

    def dress(self, references, rolls):
        with mock.patch.dict(
            zombie_outfits.ZOMBIE_OUTFIT_REFERENCES, {"generic01": {"male": references}}
        ):
            return zombie_dress.dress_outfit("generic01", False, ScriptedRandom(**rolls))[0]

    def test_a_reference_is_worn_when_the_roll_is_at_most_its_probability(self):
        refs = ((0.3, ("item_tshirt",)),)
        worn = self.dress(refs, {"random": [0.3], "randrange": [0]})
        self.assertEqual(worn[BodyLocation.TSHIRT].item.id, "item_tshirt")
        worn = self.dress(refs, {"random": [0.31], "randrange": [0]})
        self.assertEqual(worn, {})

    def test_the_choice_is_uniform_over_the_item_and_its_sub_items(self):
        refs = ((1.0, ("item_tshirt", "item_hoodie", "item_black_jacket")),)
        picks = []
        for choice in (0, 1, 2):
            worn = self.dress(refs, {"random": [0.0], "randrange": [choice]})
            picks.append(next(iter(worn.values())).item.id)
        self.assertEqual(picks, ["item_tshirt", "item_hoodie", "item_black_jacket"])

    def test_a_choice_outside_the_catalogue_is_skipped(self):
        refs = ((1.0, ("item_tshirt", None)),)
        worn = self.dress(refs, {"random": [0.0], "randrange": [1]})
        self.assertEqual(worn, {})

    def test_worn_items_are_made_at_full_condition(self):
        refs = ((1.0, ("item_trainers",)),)
        worn = self.dress(refs, {"random": [0.0], "randrange": [0]})
        entity = worn[BodyLocation.SHOES]
        self.assertEqual(entity.hit_points, 24)
        self.assertEqual(entity.holes, set())

    def test_every_reference_item_is_in_the_catalogue_or_none(self):
        for by_sex in zombie_outfits.ZOMBIE_OUTFIT_REFERENCES.values():
            for references in by_sex.values():
                for probability, choices in references:
                    self.assertTrue(0 < probability <= 1)
                    for item_id in choices:
                        self.assertTrue(item_id is None or item_id in ITEMS, item_id)


class OutfitBagTests(unittest.TestCase):
    """Spec 25, New items: bags in outfits resolve, and a bag on a corpse fills when searched."""

    BAGS = {"item_schoolbag", "item_duffel_bag", "item_satchel", "item_fanny_pack"}

    def references(self):
        return [
            choices
            for by_sex in zombie_outfits.ZOMBIE_OUTFIT_REFERENCES.values()
            for references in by_sex.values()
            for _, choices in references
        ]

    def test_the_bag_references_name_catalogue_bags(self):
        found = {
            item_id for choices in self.references() for item_id in choices if item_id in ITEMS
        }
        bags = {i for i in found if isinstance(ITEMS[i], ContainerItem)}
        self.assertEqual(bags, self.BAGS)
        self.assertEqual(sum(1 for choices in self.references() if self.BAGS & set(choices)), 9)

    def test_a_bag_reference_gives_a_carried_bag_and_no_worn_item(self):
        refs = ((1.0, ("item_schoolbag", "item_tshirt")),)
        with mock.patch.dict(
            zombie_outfits.ZOMBIE_OUTFIT_REFERENCES, {"generic01": {"male": refs}}
        ):
            worn, bags = zombie_dress.dress_outfit(
                "generic01", False, ScriptedRandom(random=[0.0], randrange=[0])
            )
        self.assertEqual(worn, {})
        self.assertEqual([b.item.id for b in bags], ["item_schoolbag"])
        self.assertEqual(bags[0].contents, [])

    def test_dressing_a_zombie_puts_the_bag_in_what_it_carries(self):
        refs = ((1.0, ("item_satchel",)),)
        zombie = bare_zombie()
        with (
            mock.patch.dict(zombie_outfits.ZOMBIE_OUTFIT_REFERENCES, {"generic01": {"male": refs}}),
            mock.patch.object(zombie_dress, "pick_outfit", return_value="generic01"),
            mock.patch.object(zombie_dress, "attach_weapon"),
        ):
            zombie_dress.dress(zombie, ScriptedRandom(random=[0.0], randrange=[1, 0]), 0.0)
        self.assertEqual([e.item.id for e in zombie.carried], ["item_satchel"])

    def test_a_searched_body_fills_its_bag_from_the_bags_table_once(self):
        table = LootTable(1, (("nails", 100.0),), 1, (), False)
        zombie = bare_zombie()
        zombie.carried = [ItemEntity(item=ITEMS["item_schoolbag"], loot_pending=True)]
        body = kill_corpse(World(), zombie, 0, random.Random(1))
        self.assertEqual(body.contents[0].contents, [])
        with (
            mock.patch.dict(BAG_TABLES, {"bag_schoolbag": table}),
            mock.patch.object(loot, "roll_pockets", return_value=[]),
        ):
            loot.search(body, ScriptedRandom())
            bag = body.contents[0]
            self.assertEqual([e.item.id for e in bag.contents], ["item_nails"])
            loot.search(body, ScriptedRandom())
        self.assertEqual(len(bag.contents), 1)

    def test_a_bag_that_already_holds_things_is_not_refilled(self):
        zombie = bare_zombie()
        bag = ItemEntity(
            item=ITEMS["item_duffel_bag"],
            contents=[ItemEntity(item=ITEMS["item_bandage"])],
            loot_pending=True,
        )
        zombie.carried = [bag]
        body = kill_corpse(World(), zombie, 0, random.Random(1))
        with mock.patch.object(loot, "roll_pockets", return_value=[]):
            loot.search(body, ScriptedRandom())
        self.assertEqual([e.item.id for e in bag.contents], ["item_bandage"])

    def search_with(self, body, table):
        with (
            mock.patch.dict(BAG_TABLES, {"bag_schoolbag": table}),
            mock.patch.object(loot, "roll_pockets", return_value=[]),
        ):
            loot.search(body, ScriptedRandom())

    def test_an_outfit_bag_is_marked_to_roll_and_a_player_bag_is_not(self):
        refs = ((1.0, ("item_schoolbag",)),)
        with mock.patch.dict(
            zombie_outfits.ZOMBIE_OUTFIT_REFERENCES, {"generic01": {"male": refs}}
        ):
            _, bags = zombie_dress.dress_outfit(
                "generic01", False, ScriptedRandom(random=[0.0], randrange=[0])
            )
        self.assertTrue(bags[0].loot_pending)
        self.assertFalse(ItemEntity(item=ITEMS["item_schoolbag"]).loot_pending)

    def test_a_bag_from_the_players_inventory_is_not_filled_on_the_body(self):
        table = LootTable(1, (("nails", 100.0),), 1, (), False)
        zombie = bare_zombie()
        bag = ItemEntity(item=ITEMS["item_schoolbag"])
        zombie.carried = [bag]
        body = kill_corpse(World(), zombie, 0, random.Random(1))
        self.search_with(body, table)
        self.assertEqual(bag.contents, [])

    def test_a_bag_is_not_filled_again_after_the_body_rises_and_dies(self):
        table = LootTable(1, (("nails", 100.0),), 1, (), False)
        zombie = bare_zombie()
        zombie.carried = [ItemEntity(item=ITEMS["item_schoolbag"], loot_pending=True)]
        body = kill_corpse(World(), zombie, 0, random.Random(1))
        self.search_with(body, table)
        bag = body.contents[0]
        bag.contents.clear()
        risen = bare_zombie()
        corpses.dress_from_corpse(risen, body)
        again = kill_corpse(World(), risen, 5, random.Random(1))
        self.search_with(again, table)
        self.assertEqual(bag.contents, [])

    def test_a_filled_outfit_bag_never_exceeds_its_capacity(self):
        item = ITEMS["item_fanny_pack"]
        assert isinstance(item, ContainerItem)
        table = LootTable(40, (("tinned_beans", 100.0),), 0, (), False)
        filled = 0
        for seed in range(30):
            zombie = bare_zombie()
            zombie.carried = [ItemEntity(item=item, loot_pending=True)]
            body = kill_corpse(World(), zombie, 0, random.Random(seed))
            with (
                mock.patch.dict(BAG_TABLES, {"bag_fanny_pack_front": table}),
                mock.patch.object(loot, "roll_pockets", return_value=[]),
            ):
                loot.search(body, random.Random(seed))
            held = sum(e.weight for e in body.contents[0].contents)
            self.assertLessEqual(round(held, 4), item.capacity)
            filled += bool(body.contents[0].contents)
        self.assertGreater(filled, 0)

    def test_the_outbreak_corpses_carry_their_bags(self):
        refs = ((1.0, ("item_schoolbag",)),)
        zone = GameManager().world.locations["zone_street"]
        with (
            mock.patch.dict(zombie_outfits.ZOMBIE_OUTFIT_REFERENCES, {"generic01": {"male": refs}}),
            mock.patch.object(zombie_dress, "pick_outfit", return_value="generic01"),
            mock.patch.object(zombie_dress, "attach_weapon"),
        ):
            rng = ScriptedRandom(random=[0.0], randrange=[1, 1, 1, 0])
            body = outbreak_corpse(World(), zone, 0, rng)
        self.assertIn("item_schoolbag", [e.item.id for e in body.contents])


class ZombieClothingTests(unittest.TestCase):
    """Spec 14, Outfits: the catalogue holds every item the outfits can produce."""

    def test_the_catalogue_gained_about_270_clothing_items(self):
        used = {
            item_id
            for by_sex in zombie_outfits.ZOMBIE_OUTFIT_REFERENCES.values()
            for references in by_sex.values()
            for _, choices in references
            for item_id in choices
            if item_id is not None
        }
        self.assertGreaterEqual(len(used), 270)
        self.assertTrue(all(isinstance(ITEMS[i], ClothingItem | ContainerItem) for i in used))

    def test_a_police_jacket_has_its_clothing_stats(self):
        item = ITEMS["item_jacket_police"]
        assert isinstance(item, ClothingItem)
        self.assertEqual(item.name, "Police Jacket")
        self.assertEqual(item.body_location, BodyLocation.JACKET)
        self.assertEqual((item.scratch_defense, item.bite_defense), (30, 20))
        self.assertEqual(item.neck_protection, 0.5)
        self.assertEqual(
            (item.insulation, item.wind_resistance, item.water_resistance, item.weight),
            (0.6, 0.45, 0.25, 2.0),
        )
        self.assertIn(BodyPart.NECK, item.covers)
        self.assertIn(BodyPart.FOREARM_L, item.covers)

    def test_an_existing_catalogue_item_is_not_replaced(self):
        self.assertEqual(ITEMS["item_trainers"].max_hit_points, 24)
        self.assertEqual(ITEMS["item_black_jacket"].name, "Black jacket")


class DressingTests(unittest.TestCase):
    """Spec 14, What a zombie gains: every zombie is dressed when it is made."""

    def test_a_rolled_zombie_has_a_sex_an_outfit_and_clothes(self):
        rng = random.Random(8)
        zombies = [roll_zombie(rng, f"z{i}", "zone_street") for i in range(2000)]
        self.assertAlmostEqual(sum(z.female for z in zombies) / 2000, 0.5, delta=0.04)
        self.assertTrue(all(z.outfit for z in zombies))
        self.assertTrue(all(z.worn for z in zombies if z.outfit.startswith("generic")))
        for zombie in zombies:
            for location, entity in zombie.worn.items():
                assert isinstance(entity.item, ClothingItem)
                self.assertEqual(entity.item.body_location, location)

    def test_the_outbreak_population_is_dressed(self):
        from managers.game import GameManager

        gm = GameManager()
        start_outbreak(gm.world, 0, gm.player.current_location_id, random.Random(2))
        self.assertTrue(gm.world.zombies)
        self.assertTrue(all(z.outfit and z.worn for z in gm.world.zombies.values()))


class AttachedWeaponTests(unittest.TestCase):
    """Spec 14, Attached weapons."""

    def test_six_percent_of_zombies_roll_a_weapon(self):
        rng = random.Random(21)
        rolled = sum(
            1 for _ in range(DRAWS) if zombie_dress.attach_weapon(bare_zombie(), rng, 100.0)
        )
        self.assertAlmostEqual(rolled / DRAWS, 0.06, delta=0.008)

    def test_the_roll_passes_at_6_and_fails_at_7(self):
        rolls = ScriptedRandom(randrange=[5, 0, 0, 0, 0])
        self.assertTrue(zombie_dress.attach_weapon(bare_zombie(), rolls, 0.0))
        rolls = ScriptedRandom(randrange=[6])
        self.assertEqual(zombie_dress.attach_weapon(bare_zombie(), rolls, 0.0), [])

    def test_the_day_zero_pool_has_total_chance_155_and_day_ten_233(self):
        early = zombie_dress.attached_pool("generic01", 0.0)
        later = zombie_dress.attached_pool("generic01", 10.5)
        self.assertEqual(sum(d.chance for _, d in early), 155)
        self.assertEqual(sum(d.chance for _, d in later), 233)
        self.assertEqual(
            sum(d.chance for _, d in zombie_dress.attached_pool("generic01", 10.0)), 155
        )

    def test_an_outfit_definition_needs_the_outfit(self):
        names = {name for name, _ in zombie_dress.attached_pool("biker", 0.0)}
        generic = {name for name, _ in zombie_dress.attached_pool("generic01", 0.0)}
        self.assertTrue(names > generic)
        self.assertIn("meat_cleaver_back_low_quality", generic)

    def test_a_knife_is_never_carried_before_day_ten(self):
        rng = random.Random(31)
        for _ in range(30000):
            zombie = bare_zombie()
            zombie_dress.attach_weapon(zombie, rng, 5.0)
            if zombie.attached is not None:
                self.assertIn(
                    zombie.attached.item.id,
                    {"item_hand_axe", "item_meat_cleaver", "item_screwdriver"},
                )

    def test_from_day_ten_about_043_percent_carry_a_kitchen_knife(self):
        rng = random.Random(32)
        carried = 0
        total = 60000
        for _ in range(total):
            zombie = bare_zombie()
            zombie_dress.attach_weapon(zombie, rng, 11.0)
            if zombie.attached is not None and zombie.attached.item.id == "item_kitchen_knife":
                carried += 1
        self.assertAlmostEqual(carried / total, 0.0043, delta=0.0012)

    def test_condition_lies_in_max_less_five_to_max_exclusive(self):
        definition = zombie_loot.StuckWeaponEntry(
            1, 0, (), (BodyPart.TORSO_LOWER,), ("kitchen_knife",)
        )
        seen = set()
        for seed in range(200):
            zombie = bare_zombie()
            zombie_dress.add_attached_weapon(zombie, definition, random.Random(seed))
            assert zombie.attached is not None
            seen.add(zombie.attached.condition)
        self.assertEqual(seen, {5, 6, 7, 8, 9})

    def test_a_crowbar_condition_lies_in_10_to_14(self):
        definition = zombie_loot.StuckWeaponEntry(1, 0, (), (), ("crowbar",))
        seen = set()
        for seed in range(300):
            zombie = bare_zombie()
            zombie_dress.add_attached_weapon(zombie, definition, random.Random(seed))
            assert zombie.attached is not None
            seen.add(zombie.attached.condition)
        self.assertEqual(seen, {10, 11, 12, 13, 14})

    def test_a_weapon_outside_the_catalogue_attaches_nothing_and_makes_no_holes(self):
        jacket = ItemEntity(item=ITEMS["item_black_jacket"])
        zombie = bare_zombie()
        zombie.worn = {BodyLocation.JACKET: jacket}
        definition = zombie_loot.StuckWeaponEntry(
            1, 0, (), (BodyPart.TORSO_UPPER,), ("spear_crafted",)
        )
        zombie_dress.add_attached_weapon(zombie, definition, random.Random(1))
        self.assertIsNone(zombie.attached)
        self.assertEqual(jacket.holes, set())

    def test_the_definitions_holes_land_on_every_layer_covering_the_part(self):
        jacket = ItemEntity(item=ITEMS["item_black_jacket"])
        shirt = ItemEntity(item=ITEMS["item_tshirt"])
        zombie = bare_zombie()
        zombie.worn = {BodyLocation.JACKET: jacket, BodyLocation.TSHIRT: shirt}
        definition = zombie_loot.StuckWeaponEntry(1, 0, (), (BodyPart.TORSO_UPPER,), ("crowbar",))
        zombie_dress.add_attached_weapon(zombie, definition, random.Random(1))
        self.assertEqual(jacket.holes, {BodyPart.TORSO_UPPER})
        self.assertEqual(shirt.holes, {BodyPart.TORSO_UPPER})
        self.assertEqual(jacket.holes & {BodyPart.TORSO_LOWER}, set())

    def test_a_police_zombie_rolls_its_own_entry_before_the_general_chance(self):
        rolls = ScriptedRandom(randrange=[39, 0, 0, 100])
        zombie = bare_zombie("police")
        self.assertEqual(zombie_dress.attach_weapon(zombie, rolls, 0.0), ["handgun_holster_police"])


def dressed(*item_ids: str, holes: dict[str, set[BodyPart]] | None = None) -> ZombieEntity:
    zombie = bare_zombie()
    for item_id in item_ids:
        item = ITEMS[item_id]
        assert isinstance(item, ClothingItem)
        entity = ItemEntity(item=item)
        entity.holes = set((holes or {}).get(item_id, set()))
        zombie.worn[item.body_location] = entity
    return zombie


class ZombieDefenceTests(unittest.TestCase):
    """Spec 14, Armour against melee: the defence of a part."""

    def test_defence_is_scratch_half_plus_bite_doubled(self):
        # police jacket: scratch 30, bite 20 -> (30 x 0.5 + 20) x 2
        zombie = dressed("item_jacket_police")
        self.assertEqual(zombie_defence(zombie, BodyPart.TORSO_UPPER), 70)

    def test_the_defence_is_capped_at_85(self):
        zombie = dressed("item_jacket_police", "item_vest_bullet_police")
        self.assertEqual(zombie_defence(zombie, BodyPart.TORSO_UPPER), 85)

    def test_the_layers_on_a_part_add_before_the_formula(self):
        # a T-shirt adds nothing; a leather vest adds scratch 30 and bite 10 to the jacket
        zombie = dressed("item_jacket_police", "item_vest_leather")
        self.assertEqual(zombie_defence(zombie, BodyPart.TORSO_UPPER), 85)
        zombie = dressed("item_vest_leather")
        self.assertEqual(zombie_defence(zombie, BodyPart.TORSO_UPPER), 50)

    def test_a_hole_removes_the_items_share(self):
        zombie = dressed("item_jacket_police", holes={"item_jacket_police": {BodyPart.TORSO_UPPER}})
        self.assertEqual(zombie_defence(zombie, BodyPart.TORSO_UPPER), 0)
        self.assertEqual(zombie_defence(zombie, BodyPart.UPPERARM_L), 70)

    def test_the_neck_modifier_scales_an_items_share_below_one(self):
        # neck protection 0.5: scratch 15, bite 10 -> (7.5 + 10) x 2
        zombie = dressed("item_jacket_police")
        self.assertEqual(zombie_defence(zombie, BodyPart.NECK), 35)

    def test_a_part_the_clothes_do_not_cover_has_no_defence(self):
        zombie = dressed("item_jacket_police")
        self.assertEqual(zombie_defence(zombie, BodyPart.LOWERLEG_L), 0)

    def test_two_thirds_have_no_defence_on_the_ten_standing_hit_parts(self):
        rng = random.Random(11)
        bare = 0
        for index in range(DRAWS):
            zombie = roll_zombie(rng, f"z{index}", "zone_street")
            if all(zombie_defence(zombie, part) == 0 for part in STANDING_HIT_PARTS):
                bare += 1
        self.assertAlmostEqual(bare / DRAWS, 0.66, delta=0.02)


class HitPartTests(unittest.TestCase):
    """Spec 14, Armour against melee: which part a swing lands on."""

    def test_a_standing_target_is_hit_on_one_of_ten_parts_uniformly(self):
        rng = random.Random(3)
        parts = [hit_part(SwingKind.HIT, rng) for _ in range(10000)]
        self.assertEqual(
            set(parts),
            {
                BodyPart.HAND_L,
                BodyPart.HAND_R,
                BodyPart.FOREARM_L,
                BodyPart.FOREARM_R,
                BodyPart.UPPERARM_L,
                BodyPart.UPPERARM_R,
                BodyPart.TORSO_UPPER,
                BodyPart.TORSO_LOWER,
                BodyPart.HEAD,
                BodyPart.NECK,
            },
        )
        self.assertAlmostEqual(parts.count(BodyPart.NECK) / 10000, 0.1, delta=0.01)

    def test_a_floor_attack_or_stomp_hits_the_head_or_the_neck(self):
        rng = random.Random(4)
        for kind in (SwingKind.FLOOR_ATTACK, SwingKind.STOMP):
            parts = {hit_part(kind, rng) for _ in range(200)}
            self.assertEqual(parts, {BodyPart.HEAD, BodyPart.NECK})


class ArmourInTheChainTests(unittest.TestCase):
    """Spec 14, Armour against melee: `split` takes the defence after the head and before the ramp."""

    def hit(self, zombie: ZombieEntity, *, down: bool = False, by_size=None, shove=False):
        gm = street_game(weapon="item_crowbar")
        add(gm, zombie)
        zombie.zone_id = "zone_street"
        zombie.health = 100.0
        zombie.gap = 1.0
        zombie.facing_cos = 1.0
        zombie.state = ZombieState.CHASING
        if down:
            zombie.down_until = 5
        swing(gm, rng=FixedRng(by_size=by_size), shove=shove, now=0)
        return zombie

    def test_a_crowbar_hit_on_the_upper_torso_in_a_police_jacket_takes_30_percent(self):
        zombie = self.hit(dressed("item_jacket_police"), by_size={10: 6})
        self.assertAlmostEqual(100 - zombie.health, 0.864 * 0.15 * 0.3)

    def test_a_naked_zombie_takes_the_full_hit(self):
        zombie = self.hit(bare_zombie(), by_size={10: 6})
        self.assertAlmostEqual(100 - zombie.health, 0.864 * 0.15)

    def test_a_floor_attack_on_the_neck_takes_defence_then_the_ramp_without_the_head_triple(self):
        zombie = dressed("item_jacket_police")
        zombie.hits_taken = 3
        self.hit(zombie, down=True, by_size={2: 1})
        # split 1.2 (no head triple on the neck) x0.65 (neck defence 35) x3 (fourth hit), x1.6 x1.5 x0.3 x5 x0.15
        expected = 1.2 * 0.65 * 3 * 1.6 * 1.5 * 0.3 * 5 * 0.15
        self.assertAlmostEqual(100 - zombie.health, expected)

    def test_a_shove_ignores_the_defence_and_does_no_damage(self):
        zombie = self.hit(dressed("item_jacket_police"), by_size={10: 6}, shove=True)
        self.assertEqual(zombie.health, 100.0)


if __name__ == "__main__":
    unittest.main()

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from config import FRONT_NEIGHBORS, PARTISAN_STRENGTH, SHOP_ITEMS, WAR_FATIGUE_MAX


@dataclass
class BattleResult:
    success: bool
    message: str
    casualties_attacker: int
    casualties_defender: int
    resources_gained: Dict[str, int]
    fatigue_increase: int
    image_path: Optional[str] = None


class WarEngine:
    MAX_TERRITORY_CONTROL = 48

    def __init__(self, db, visualizer):
        self.db = db
        self.vis = visualizer

    def calculate_battle_power(
        self,
        resources: Dict,
        fatigue: int,
        logistics: int,
        fortification: int = 0,
        overextension: int = 0,
        is_defender: bool = False,
    ) -> int:
        base = resources.get("manpower", 0) * 1.0
        base += resources.get("tanks", 0) * 50
        base += resources.get("artillery", 0) * 30
        base += resources.get("ammo", 0) * 0.3
        base += fortification * 1.1

        morale_factor = max(0.3, resources.get("morale", 100) / 100)
        fatigue_factor = max(0.4, 1 - (fatigue / 100) * 0.5)
        logistics_factor = max(0.45, min(1.3, logistics / 100))
        overextension_factor = max(0.35, 1 - overextension * 0.025)

        power = base * morale_factor * fatigue_factor * logistics_factor * overextension_factor
        if is_defender:
            power *= 1.35

        return max(int(power), 100)

    def get_attackable_regions(self, user_id: int) -> List[Dict[str, int]]:
        owned_regions = self.db.get_front_regions(user_id)
        if not owned_regions:
            return []

        candidate_regions = set(owned_regions)
        for region in owned_regions:
            candidate_regions.update(FRONT_NEIGHBORS.get(region, set()))

        output: List[Dict[str, int]] = []
        for region in sorted(candidate_regions):
            targets = self.db.get_attack_targets_for_region(user_id, region)
            if targets:
                output.append({"region": region, "targets": len(targets)})
        return output

    def _is_front_attack(self, user_id: int, target_region: str) -> bool:
        owned_regions = self.db.get_front_regions(user_id)
        if target_region in owned_regions:
            return True

        for my_region in owned_regions:
            if target_region in FRONT_NEIGHBORS.get(my_region, set()):
                return True
        return False

    def _avg_logistics(self, user_id: int) -> int:
        terrs = self.db.get_territories(user_id)
        if not terrs:
            return 100
        return int(sum(t.get("logistics", 100) for t in terrs) / len(terrs))

    def _apply_losses(self, resources: Dict, manpower: int, ammo: int, fuel: int) -> Dict:
        new_res = resources.copy()
        new_res["manpower"] = max(0, new_res.get("manpower", 0) - manpower)
        new_res["ammo"] = max(0, new_res.get("ammo", 0) - ammo)
        new_res["fuel"] = max(0, new_res.get("fuel", 0) - fuel)
        return new_res

    def attack(self, attacker_id: int, target_district: str, target_region: str) -> BattleResult:
        attacker = self.db.get_player(attacker_id)
        if not attacker:
            return BattleResult(False, "❌ Командир не найден", 0, 0, {}, 0)

        # Проверка усталости
        if attacker["war_fatigue"] >= WAR_FATIGUE_MAX:
            return BattleResult(False, "❌ Армия истощена! Отдохните.", 0, 0, {}, 0)

        all_terrs = self.db.get_territories()
        target = next((t for t in all_terrs if t["district"] == target_district and t["region"] == target_region), None)

        if not target:
            return BattleResult(False, "❌ Цель не существует", 0, 0, {}, 0)

        if target["owner_id"] == attacker_id:
            return BattleResult(False, "❌ Это твоя территория", 0, 0, {}, 0)

        defender = self.db.get_player(target["owner_id"]) if target["owner_id"] else None

        # Расчёт сил
        att_power = self.calculate_battle_power(
            attacker["resources"],
            attacker["war_fatigue"],
            logistics=self._avg_logistics(attacker_id),
            is_defender=False,
        )
        def_power = target["defense"] * 10

        if defender:
            def_power += self.calculate_battle_power(
                defender["resources"],
                defender.get("war_fatigue", 0),
                logistics=target.get("logistics", 100),
                is_defender=True,
            )

        # Партизаны
        if target.get("original_faction") and target["owner_id"]:
            owner = self.db.get_player(target["owner_id"])
            if owner and target["original_faction"] != owner["faction"]:
                partisan_bonus = 1 + (target.get("partisan", 0) / 100) * PARTISAN_STRENGTH
                def_power *= partisan_bonus

        # Бросок кубика
        att_roll = random.uniform(0.7, 1.3)
        def_roll = random.uniform(0.8, 1.2)

        att_total = att_power * att_roll
        def_total = def_power * def_roll

        cas_att = int(attacker["resources"]["manpower"] * random.uniform(0.08, 0.25))
        cas_def = int((def_power / 10) * random.uniform(0.05, 0.20))
        fatigue_inc = random.randint(5, 15)

        # Определяем победу
        victory = att_total > def_total

        if victory:
            # Адаптация к текущей БД: захват по ID территории
            self.db.capture_territory(target["id"], attacker_id)
            self.db.refresh_territory_counts()

            new_res = attacker["resources"].copy()
            new_res["manpower"] = max(0, new_res.get("manpower", 0) - cas_att)
            new_res["ammo"] = max(0, new_res.get("ammo", 0) - random.randint(100, 300))
            new_res["fuel"] = max(0, new_res.get("fuel", 0) - random.randint(50, 150))
            new_res["morale"] = min(100, new_res.get("morale", 100) + 5)
            new_res["money"] = new_res.get("money", 0) + random.randint(300, 800)

            trophies = {
                "ammo": random.randint(200, 500),
                "fuel": random.randint(100, 300),
                "manpower": random.randint(100, 300),
                "money": random.randint(500, 1500),
            }
            for k, v in trophies.items():
                new_res[k] = new_res.get(k, 0) + v

            self.db.update_resources(attacker_id, new_res)
            self.db.update_fatigue(attacker_id, min(WAR_FATIGUE_MAX, attacker["war_fatigue"] + fatigue_inc))
            self.db.update_stats(attacker_id, win=True)

            if defender:
                self.db.update_stats(target["owner_id"], loss=True)
                self.db.add_war_log(
                    f"⚔️ {attacker['username']} ({attacker['faction']}) захватил {target_district} у {defender['username']}"
                )

            # НОВЫЙ ВЫЗОВ - ВСЕ АРГУМЕНТЫ
            image = self.vis.generate_battle_image(
                region=target_region,
                district=target_district,
                att_name=attacker["username"],
                att_faction=attacker["faction"],
                def_name=defender["username"] if defender else "Нейтралы",
                def_faction=defender["faction"] if defender else "Нет",
                result="ПОБЕДА",
                casualties=(cas_att, cas_def),
                victory=True,
            )

            self.db.log_battle(
                attacker_id,
                target["owner_id"] or 0,
                target_region,
                target_district,
                "victory",
                cas_att,
                cas_def,
                fatigue_inc,
                image,
            )

            return BattleResult(
                True,
                f"✅ ЗАХВАЧЕНО: {target_district}\n💀 Твои потери: {cas_att} чел.\n💰 Трофеи: {trophies}\n😴 Усталость +{fatigue_inc}",
                cas_att,
                cas_def,
                trophies,
                fatigue_inc,
                image,
            )
        else:
            new_res = attacker["resources"].copy()
            new_res["manpower"] = max(0, new_res.get("manpower", 0) - cas_att)
            new_res["ammo"] = max(0, new_res.get("ammo", 0) - random.randint(50, 150))
            new_res["fuel"] = max(0, new_res.get("fuel", 0) - random.randint(20, 80))
            new_res["morale"] = max(0, new_res.get("morale", 100) - 20)

            self.db.update_resources(attacker_id, new_res)
            self.db.update_fatigue(attacker_id, min(WAR_FATIGUE_MAX, attacker["war_fatigue"] + fatigue_inc))
            self.db.update_stats(attacker_id, loss=True)

            # НОВЫЙ ВЫЗОВ - ПОРАЖЕНИЕ
            image = self.vis.generate_battle_image(
                region=target_region,
                district=target_district,
                att_name=attacker["username"],
                att_faction=attacker["faction"],
                def_name=defender["username"] if defender else "Нейтралы",
                def_faction=defender["faction"] if defender else "Нет",
                result="ПОРАЖЕНИЕ",
                casualties=(cas_att, cas_def),
                victory=False,
            )

            self.db.log_battle(
                attacker_id,
                target["owner_id"] or 0,
                target_region,
                target_district,
                "defeat",
                cas_att,
                cas_def,
                fatigue_inc,
                image,
            )

            return BattleResult(
                False,
                f"❌ ПРОВАЛ: Штурм отбит\n💀 Потери: {cas_att} чел.\n📉 Мораль -20\n😴 Усталость +{fatigue_inc}",
                cas_att,
                cas_def,
                {},
                fatigue_inc,
                image,
            )

    def rest_army(self, user_id: int) -> str:
        player = self.db.get_player(user_id)
        if not player:
            return "❌ Командир не найден"

        fatigue = player.get("war_fatigue", 0)
        if fatigue <= 0:
            return "✅ Армия уже в форме"

        resources = player["resources"].copy()
        rest_cost = 120
        if resources.get("money", 0) < rest_cost:
            return "❌ Нужно 120 денег на отдых и ротацию"

        resources["money"] = max(0, resources.get("money", 0) - rest_cost)
        resources["morale"] = min(100, resources.get("morale", 100) + 10)
        self.db.update_resources(user_id, resources)

        new_fatigue = max(0, fatigue - 35)
        self.db.update_fatigue(user_id, new_fatigue)
        return f"✅ Отдых завершён. Усталость: {fatigue} → {new_fatigue}, мораль +10"

    def collect_resources(self, user_id: int) -> Dict:
        territories = self.db.get_territories(owner_id=user_id)
        player = self.db.get_player(user_id)

        if not player or not territories:
            return {"error": "Нет территорий"}

        resources = player["resources"].copy()
        collected = {"manpower": 0, "ammo": 0, "fuel": 0, "money": 0}

        for terr in territories:
            occupied = terr.get("original_faction") != player.get("faction")
            partisan = terr.get("partisan", 0)
            logistics = terr.get("logistics", 100)
            fort = terr.get("fortification", 0)

            base_income = {
                "manpower": random.randint(28, 76),
                "ammo": random.randint(18, 52),
                "fuel": random.randint(10, 30),
                "money": random.randint(110, 320),
            }

            if occupied:
                partisan_loss = (partisan / 100) * 0.6
                multiplier = max(0.35, 1.0 - partisan_loss)
                partisan_delta = random.randint(1, 4) - (fort // 70)
                logistics_delta = -1 if partisan > 45 else 0
            else:
                multiplier = min(1.25, 0.9 + (logistics / 100) * 0.2)
                partisan_delta = -random.randint(1, 3)
                logistics_delta = 1 if fort > 0 else 0

            for key, value in base_income.items():
                gain = int(value * multiplier)
                resources[key] = resources.get(key, 0) + gain
                collected[key] += gain

            self.db.update_territory_dynamic(
                terr["id"],
                partisan_delta=partisan_delta,
                logistics_delta=logistics_delta,
            )

        fatigue = player.get("war_fatigue", 0)
        fatigue_factor = max(0.55, 1 - (fatigue / 100) * 0.45)
        if fatigue_factor < 1:
            for key in collected:
                reduced = int(collected[key] * fatigue_factor)
                diff = collected[key] - reduced
                collected[key] = reduced
                resources[key] = max(0, resources.get(key, 0) - diff)

        resources["morale"] = min(100, resources.get("morale", 100) + 2)
        self.db.update_resources(user_id, resources)
        self.db.refresh_territory_counts()

        return collected

    def buy_item(self, user_id: int, item_key: str) -> Tuple[bool, str]:
        player = self.db.get_player(user_id)
        if not player:
            return False, "Командир не найден"

        item = SHOP_ITEMS.get(item_key)
        if not item:
            return False, "Товар не найден"

        resources = player["resources"].copy()

        for res_name, amount in item["price"].items():
            if resources.get(res_name, 0) < amount:
                return False, f"Недостаточно {res_name}: нужно {amount}"

        for res_name, amount in item["price"].items():
            resources[res_name] -= amount

        if item_key == "tank":
            resources["tanks"] = resources.get("tanks", 0) + 1
        elif item_key == "artillery":
            resources["artillery"] = resources.get("artillery", 0) + 1
        elif item_key == "ammo":
            resources["ammo"] = resources.get("ammo", 0) + item.get("amount", 0)
        elif item_key == "fuel":
            resources["fuel"] = resources.get("fuel", 0) + item.get("amount", 0)
        elif item_key == "manpower":
            resources["manpower"] = resources.get("manpower", 0) + item.get("amount", 0)
        elif item_key == "fortification":
            terrs = self.db.get_territories(owner_id=user_id)
            if not terrs:
                return False, "Нет территорий для укрепления"
            target = min(terrs, key=lambda t: t.get("defense", 0))
            self.db.add_fortification(target["id"], item.get("defense", 0))
            self.db.update_resources(user_id, resources)
            return True, f"✅ Укрепления построены в {target['district']}"

        self.db.update_resources(user_id, resources)
        return True, f"✅ Куплено: {item['name']}"

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple


@dataclass
class BattleResult:
    success: bool
    message: str
    casualties_attacker: int = 0
    casualties_defender: int = 0
    resources_gained: Dict[str, int] = field(default_factory=dict)
    image_path: Optional[str] = None


class WarEngine:
    MIN_ATTACK_AMMO = 30
    MIN_ATTACK_FUEL = 15
    COLLECT_COOLDOWN_SECONDS = 30 * 60

    def __init__(self, db, visualizer):
        self.db = db
        self.vis = visualizer

    def calculate_battle_power(
        self, resources: Dict[str, int], is_defender: bool = False, territory_defense: int = 0
    ) -> int:
        manpower = resources.get("manpower", 0)
        tanks = resources.get("tanks", 0)
        artillery = resources.get("artillery", 0)
        ammo = resources.get("ammo", 0)
        fuel = resources.get("fuel", 0)
        morale = max(0.2, resources.get("morale", 100) / 100)

        power = manpower * 1.0
        power += tanks * 45
        power += artillery * 28
        power += ammo * 0.35
        power += fuel * 0.20
        power += territory_defense * 9
        power *= morale

        if is_defender:
            power *= 1.15

        return int(power)

    def _decrease_with_floor(self, value: int, delta: int) -> int:
        return max(0, value - max(0, delta))

    def attack(self, attacker_id: int, target_id: int) -> BattleResult:
        attacker = self.db.get_player(attacker_id)
        if not attacker:
            return BattleResult(False, "Игрок не найден.")

        target = self.db.get_territory_by_id(target_id)
        if not target:
            return BattleResult(False, "Цель не найдена.")

        if target["owner_id"] == attacker_id:
            return BattleResult(False, "Это уже твоя территория.")

        ares = attacker["resources"]
        if ares.get("ammo", 0) < self.MIN_ATTACK_AMMO or ares.get("fuel", 0) < self.MIN_ATTACK_FUEL:
            return BattleResult(
                False,
                f"Недостаточно ресурсов для атаки. Нужно минимум {self.MIN_ATTACK_AMMO} боеприпасов "
                f"и {self.MIN_ATTACK_FUEL} топлива.",
            )

        defender = self.db.get_player(target["owner_id"]) if target["owner_id"] else None

        att_power = self.calculate_battle_power(ares)
        def_resources = defender["resources"] if defender else {"morale": 100}
        def_power = self.calculate_battle_power(
            def_resources, is_defender=True, territory_defense=target["defense"]
        )

        att_total = att_power * random.uniform(0.82, 1.20)
        def_total = def_power * random.uniform(0.85, 1.22)

        cas_att = max(5, int(ares.get("manpower", 0) * random.uniform(0.03, 0.16)))
        defender_source = def_resources.get("manpower", target["defense"] * 12)
        cas_def = max(5, int(defender_source * random.uniform(0.04, 0.18)))

        ammo_spent = random.randint(35, 120)
        fuel_spent = random.randint(18, 70)

        new_attacker = ares.copy()
        new_attacker["manpower"] = self._decrease_with_floor(new_attacker.get("manpower", 0), cas_att)
        new_attacker["ammo"] = self._decrease_with_floor(new_attacker.get("ammo", 0), ammo_spent)
        new_attacker["fuel"] = self._decrease_with_floor(new_attacker.get("fuel", 0), fuel_spent)

        if att_total > def_total:
            self.db.capture_territory(target["id"], attacker_id)

            trophies = {
                "ammo": random.randint(80, 240),
                "fuel": random.randint(40, 130),
                "manpower": random.randint(30, 120),
            }

            new_attacker["ammo"] += trophies["ammo"]
            new_attacker["fuel"] += trophies["fuel"]
            new_attacker["manpower"] += trophies["manpower"]
            new_attacker["morale"] = min(100, new_attacker.get("morale", 100) + random.randint(3, 8))
            self.db.update_resources(attacker_id, new_attacker)

            if defender:
                new_def = defender["resources"].copy()
                new_def["manpower"] = self._decrease_with_floor(new_def.get("manpower", 0), cas_def)
                new_def["morale"] = max(0, new_def.get("morale", 100) - random.randint(4, 10))
                self.db.update_resources(defender["user_id"], new_def)

            image = self.vis.generate_battle_image(
                target["region"],
                target["district"],
                attacker["faction"],
                defender["faction"] if defender else "Нейтралы",
                "захват",
                (cas_att, cas_def),
            )
            self.db.log_battle(
                attacker_id,
                defender["user_id"] if defender else None,
                target["region"],
                target["district"],
                "victory",
                cas_att,
                cas_def,
                image,
            )

            message = (
                f"Успех. Район {target['district']} захвачен.\n"
                f"Потери: {cas_att}.\n"
                f"Трофеи: +{trophies['manpower']} личного состава, +{trophies['ammo']} боеприпасов, "
                f"+{trophies['fuel']} топлива."
            )
            return BattleResult(True, message, cas_att, cas_def, trophies, image)

        new_attacker["morale"] = max(0, new_attacker.get("morale", 100) - random.randint(8, 14))
        self.db.update_resources(attacker_id, new_attacker)

        if defender:
            new_def = defender["resources"].copy()
            new_def["morale"] = min(100, new_def.get("morale", 100) + random.randint(1, 4))
            self.db.update_resources(defender["user_id"], new_def)

        image = self.vis.generate_battle_image(
            target["region"],
            target["district"],
            attacker["faction"],
            defender["faction"] if defender else "Нейтралы",
            "поражение",
            (cas_att, cas_def),
        )
        self.db.log_battle(
            attacker_id,
            defender["user_id"] if defender else None,
            target["region"],
            target["district"],
            "defeat",
            cas_att,
            cas_def,
            image,
        )

        return BattleResult(
            False,
            f"Штурм {target['district']} провалился.\nПотери: {cas_att}.\nМораль войск снизилась.",
            cas_att,
            cas_def,
            {},
            image,
        )

    def get_available_targets(self, user_id: int, limit: int = 15) -> list:
        all_territories = self.db.get_territories()
        targets = [t for t in all_territories if t["owner_id"] != user_id]
        return targets[:limit]

    def produce_resources(self, user_id: int, force: bool = False) -> Tuple[bool, Dict[str, int]]:
        player = self.db.get_player(user_id)
        if not player:
            return False, {"error": "Игрок не найден"}

        if not force and player.get("last_collect"):
            last_collect = datetime.fromisoformat(player["last_collect"])
            next_collect = last_collect + timedelta(seconds=self.COLLECT_COOLDOWN_SECONDS)
            if datetime.utcnow() < next_collect:
                wait_seconds = int((next_collect - datetime.utcnow()).total_seconds())
                return False, {"wait_seconds": max(0, wait_seconds)}

        territories = self.db.get_territories(user_id)
        if not territories:
            now_iso = datetime.utcnow().isoformat()
            self.db.set_last_collect(user_id, now_iso)
            return True, {"manpower": 0, "ammo": 0, "fuel": 0}

        gain = {"manpower": 0, "ammo": 0, "fuel": 0}
        for terr in territories:
            infra_bonus = max(0, terr["infrastructure"] // 10)
            gain["manpower"] += random.randint(8, 22) + infra_bonus
            gain["ammo"] += random.randint(5, 14) + infra_bonus // 2
            gain["fuel"] += random.randint(4, 11) + infra_bonus // 3

        updated = player["resources"].copy()
        updated["manpower"] = updated.get("manpower", 0) + gain["manpower"]
        updated["ammo"] = updated.get("ammo", 0) + gain["ammo"]
        updated["fuel"] = updated.get("fuel", 0) + gain["fuel"]

        self.db.update_resources(user_id, updated)
        self.db.set_last_collect(user_id, datetime.utcnow().isoformat())
        return True, gain

    def produce_resources_for_all(self) -> int:
        players = self.db.get_all_players()
        count = 0
        for player in players:
            self.produce_resources(player["user_id"], force=True)
            count += 1
        return count

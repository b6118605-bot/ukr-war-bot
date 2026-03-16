import json
import random
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from config import DB_PATH, REGIONS, START_RESOURCES


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS players (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    faction TEXT DEFAULT 'neutral',
                    resources TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_action TIMESTAMP,
                    last_collect TIMESTAMP
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS territories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    region TEXT NOT NULL,
                    district TEXT NOT NULL,
                    owner_id INTEGER,
                    defense_power INTEGER DEFAULT 100,
                    infrastructure INTEGER DEFAULT 50,
                    last_battle TIMESTAMP,
                    UNIQUE(region, district),
                    FOREIGN KEY (owner_id) REFERENCES players(user_id)
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS battles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attacker_id INTEGER NOT NULL,
                    defender_id INTEGER,
                    region TEXT,
                    district TEXT,
                    result TEXT,
                    casualties_attacker INTEGER,
                    casualties_defender INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    battle_image_path TEXT
                )
                """
            )
        self.seed_world_map()

    def seed_world_map(self) -> None:
        rows = [(region, district) for region, districts in REGIONS.items() for district in districts]
        with self._connect() as conn:
            c = conn.cursor()
            c.executemany(
                """
                INSERT OR IGNORE INTO territories (region, district, owner_id, defense_power, infrastructure)
                VALUES (?, ?, NULL, 100, 50)
                """,
                rows,
            )

    def get_player(self, user_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "faction": row["faction"],
            "resources": json.loads(row["resources"]) if row["resources"] else {},
            "created_at": row["created_at"],
            "last_collect": row["last_collect"],
        }

    def get_all_players(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM players").fetchall()
        players: List[Dict] = []
        for row in rows:
            players.append(
                {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "faction": row["faction"],
                    "resources": json.loads(row["resources"]) if row["resources"] else {},
                    "created_at": row["created_at"],
                    "last_collect": row["last_collect"],
                }
            )
        return players

    def create_player(self, user_id: int, username: str, faction: str) -> Dict:
        existing = self.get_player(user_id)
        if existing:
            return existing

        resources = json.dumps(START_RESOURCES, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO players (user_id, username, faction, resources) VALUES (?, ?, ?, ?)",
                (user_id, username, faction, resources),
            )
        self.assign_start_territory(user_id)
        return self.get_player(user_id) or {}

    def assign_start_territory(self, user_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            unowned = conn.execute(
                "SELECT id, region, district FROM territories WHERE owner_id IS NULL"
            ).fetchall()

            if not unowned:
                return None
            selected = random.choice(unowned)

            conn.execute(
                """
                UPDATE territories
                SET owner_id = ?, defense_power = 150, infrastructure = infrastructure + 5
                WHERE id = ?
                """,
                (user_id, selected["id"]),
            )

        return self.get_territory_by_id(int(selected["id"]))

    def get_territory_by_id(self, territory_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM territories WHERE id = ?", (territory_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "region": row["region"],
            "district": row["district"],
            "owner_id": row["owner_id"],
            "defense": row["defense_power"],
            "infrastructure": row["infrastructure"],
        }

    def get_territories(self, owner_id: Optional[int] = None) -> List[Dict]:
        with self._connect() as conn:
            if owner_id is None:
                rows = conn.execute("SELECT * FROM territories").fetchall()
            else:
                rows = conn.execute("SELECT * FROM territories WHERE owner_id = ?", (owner_id,)).fetchall()

        return [
            {
                "id": row["id"],
                "region": row["region"],
                "district": row["district"],
                "owner_id": row["owner_id"],
                "defense": row["defense_power"],
                "infrastructure": row["infrastructure"],
            }
            for row in rows
        ]

    def update_resources(self, user_id: int, resources: Dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE players SET resources = ?, last_action = ? WHERE user_id = ?",
                (json.dumps(resources, ensure_ascii=False), datetime.utcnow().isoformat(), user_id),
            )

    def set_last_collect(self, user_id: int, timestamp_iso: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE players SET last_collect = ? WHERE user_id = ?", (timestamp_iso, user_id))

    def capture_territory(self, territory_id: int, new_owner: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE territories
                SET owner_id = ?, defense_power = 100, last_battle = ?
                WHERE id = ?
                """,
                (new_owner, datetime.utcnow().isoformat(), territory_id),
            )

    def log_battle(
        self,
        attacker_id: int,
        defender_id: Optional[int],
        region: str,
        district: str,
        result: str,
        cas_att: int,
        cas_def: int,
        image_path: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO battles (
                    attacker_id, defender_id, region, district, result,
                    casualties_attacker, casualties_defender, battle_image_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (attacker_id, defender_id, region, district, result, cas_att, cas_def, image_path),
            )

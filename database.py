import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Set

from config import DB_PATH, REGIONS, START_RESOURCES


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _column_exists(self, conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r["name"] == column for r in rows)

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        if not self._column_exists(conn, table, column):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def init_db(self) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS players (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    faction TEXT UNIQUE,
                    resources TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_action TIMESTAMP,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    war_fatigue INTEGER DEFAULT 0,
                    total_territories INTEGER DEFAULT 0
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
                    original_faction TEXT,
                    defense_power INTEGER DEFAULT 100,
                    fortification INTEGER DEFAULT 0,
                    partisan_activity INTEGER DEFAULT 0,
                    logistics_level INTEGER DEFAULT 100,
                    last_battle TIMESTAMP,
                    capture_date TIMESTAMP,
                    UNIQUE(region, district),
                    FOREIGN KEY (owner_id) REFERENCES players(user_id)
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS battles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attacker_id INTEGER,
                    defender_id INTEGER,
                    region TEXT,
                    district TEXT,
                    result TEXT,
                    casualties_attacker INTEGER,
                    casualties_defender INTEGER,
                    war_fatigue_impact INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    battle_image_path TEXT
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS war_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message TEXT
                )
                """
            )

            # Safe schema migration for existing DB files.
            self._ensure_column(conn, "players", "wins", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "players", "losses", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "players", "war_fatigue", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "players", "total_territories", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "territories", "original_faction", "TEXT")
            self._ensure_column(conn, "territories", "fortification", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "territories", "partisan_activity", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "territories", "logistics_level", "INTEGER DEFAULT 100")
            self._ensure_column(conn, "territories", "capture_date", "TIMESTAMP")
            self._ensure_column(conn, "battles", "war_fatigue_impact", "INTEGER DEFAULT 0")

        self.seed_world_map()
        self.refresh_territory_counts()

    def seed_world_map(self) -> None:
        rows = []
        for region, districts in REGIONS.items():
            for district in districts:
                rows.append((region, district, region, 100, 0, 0, 100))

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO territories (
                    region, district, owner_id, original_faction,
                    defense_power, fortification, partisan_activity, logistics_level
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_occupied_factions(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT faction FROM players WHERE faction IS NOT NULL").fetchall()
        return [r["faction"] for r in rows if r["faction"]]

    def get_player_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM players").fetchone()
        return int(row["cnt"] if row else 0)

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
            "wins": row["wins"] or 0,
            "losses": row["losses"] or 0,
            "war_fatigue": row["war_fatigue"] or 0,
            "total_territories": row["total_territories"] or 0,
        }

    def get_player_by_faction(self, faction: str) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM players WHERE faction = ?", (faction,)).fetchone()
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "faction": row["faction"],
            "resources": json.loads(row["resources"]) if row["resources"] else {},
            "wins": row["wins"] or 0,
            "losses": row["losses"] or 0,
            "war_fatigue": row["war_fatigue"] or 0,
            "total_territories": row["total_territories"] or 0,
        }

    def _assign_faction_territories(self, conn: sqlite3.Connection, user_id: int, faction: str) -> None:
        districts = REGIONS.get(faction, [])
        if not districts:
            raise ValueError("Неизвестная фракция")

        locked = conn.execute(
            """
            SELECT district FROM territories
            WHERE region = ? AND owner_id IS NOT NULL AND owner_id != ?
            """,
            (faction, user_id),
        ).fetchall()
        if locked:
            raise ValueError("Область уже занята")

        capital = districts[0]
        for district in districts:
            defense = 220 if district == capital else 120
            fortification = 20 if district == capital else 0
            conn.execute(
                """
                UPDATE territories
                SET owner_id = ?, defense_power = ?, fortification = ?,
                    partisan_activity = 0, logistics_level = 100,
                    original_faction = COALESCE(original_faction, region)
                WHERE region = ? AND district = ?
                """,
                (user_id, defense, fortification, faction, district),
            )

    def create_player(self, user_id: int, username: str, faction: str) -> Dict:
        existing = self.get_player(user_id)
        if existing:
            return existing

        if self.get_player_by_faction(faction):
            raise ValueError("Эта область уже занята")

        resources = json.dumps(START_RESOURCES, ensure_ascii=False)
        clean_username = username or f"user_{user_id}"

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO players (
                    user_id, username, faction, resources,
                    wins, losses, war_fatigue, total_territories
                ) VALUES (?, ?, ?, ?, 0, 0, 0, 0)
                """,
                (user_id, clean_username, faction, resources),
            )
            self._assign_faction_territories(conn, user_id, faction)

        self.refresh_territory_counts()
        self.add_war_log(f"🪖 {clean_username} возглавил область {faction}")
        return self.get_player(user_id) or {}

    def get_territory_by_id(self, territory_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM territories WHERE id = ?", (territory_id,)).fetchone()
        if not row:
            return None
        return self._row_to_territory(row)

    def get_territory_by_region_district(self, region: str, district: str) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM territories WHERE region = ? AND district = ?",
                (region, district),
            ).fetchone()
        if not row:
            return None
        return self._row_to_territory(row)

    def get_territories(self, owner_id: Optional[int] = None, region: Optional[str] = None) -> List[Dict]:
        query = "SELECT * FROM territories"
        params: List[object] = []
        clauses = []

        if owner_id is not None:
            clauses.append("owner_id = ?")
            params.append(owner_id)
        if region is not None:
            clauses.append("region = ?")
            params.append(region)

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_territory(r) for r in rows]

    def get_attack_targets_for_region(self, user_id: int, region: str) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM territories
                WHERE region = ? AND (owner_id IS NULL OR owner_id != ?)
                ORDER BY district
                """,
                (region, user_id),
            ).fetchall()
        return [self._row_to_territory(r) for r in rows]

    def get_front_regions(self, user_id: int) -> Set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT region FROM territories WHERE owner_id = ?",
                (user_id,),
            ).fetchall()
        return {r["region"] for r in rows if r["region"]}

    def update_resources(self, user_id: int, resources: Dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE players SET resources = ?, last_action = ? WHERE user_id = ?",
                (json.dumps(resources, ensure_ascii=False), datetime.utcnow().isoformat(), user_id),
            )

    def update_fatigue(self, user_id: int, fatigue: int) -> None:
        fatigue = max(0, min(100, fatigue))
        with self._connect() as conn:
            conn.execute("UPDATE players SET war_fatigue = ? WHERE user_id = ?", (fatigue, user_id))

    def update_stats(self, user_id: int, win: bool = False, loss: bool = False) -> None:
        with self._connect() as conn:
            if win:
                conn.execute("UPDATE players SET wins = wins + 1 WHERE user_id = ?", (user_id,))
            if loss:
                conn.execute("UPDATE players SET losses = losses + 1 WHERE user_id = ?", (user_id,))

    def refresh_territory_counts(self) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE players SET total_territories = 0")
            conn.execute(
                """
                UPDATE players
                SET total_territories = (
                    SELECT COUNT(*) FROM territories t WHERE t.owner_id = players.user_id
                )
                """
            )

    def capture_territory(self, territory_id: int, new_owner_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE territories
                SET owner_id = ?,
                    defense_power = MAX(70, defense_power - 20),
                    fortification = MAX(0, fortification - 20),
                    partisan_activity = 30,
                    logistics_level = MAX(65, logistics_level - 10),
                    capture_date = ?,
                    last_battle = ?
                WHERE id = ?
                """,
                (new_owner_id, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), territory_id),
            )
        self.refresh_territory_counts()

    def add_fortification(self, territory_id: int, amount: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE territories
                SET fortification = fortification + ?,
                    defense_power = defense_power + ?,
                    logistics_level = MIN(120, logistics_level + 5)
                WHERE id = ?
                """,
                (amount, max(10, amount // 2), territory_id),
            )

    def update_territory_dynamic(
        self,
        territory_id: int,
        partisan_delta: int = 0,
        logistics_delta: int = 0,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT partisan_activity, logistics_level FROM territories WHERE id = ?",
                (territory_id,),
            ).fetchone()
            if not row:
                return
            partisan = max(0, min(100, int(row["partisan_activity"] or 0) + partisan_delta))
            logistics = max(30, min(130, int(row["logistics_level"] or 100) + logistics_delta))
            conn.execute(
                "UPDATE territories SET partisan_activity = ?, logistics_level = ? WHERE id = ?",
                (partisan, logistics, territory_id),
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
        fatigue: int,
        image_path: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO battles (
                    attacker_id, defender_id, region, district, result,
                    casualties_attacker, casualties_defender, war_fatigue_impact, battle_image_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (attacker_id, defender_id, region, district, result, cas_att, cas_def, fatigue, image_path),
            )

    def add_war_log(self, message: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO war_log (message) VALUES (?)", (message,))

    def get_war_log(self, limit: int = 10) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT message FROM war_log ORDER BY timestamp DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r["message"] for r in rows]

    def get_leaderboard(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, username, faction, wins, losses, total_territories
                FROM players
                ORDER BY wins DESC, total_territories DESC, losses ASC
                LIMIT 10
                """
            ).fetchall()
        return [
            {
                "user_id": r["user_id"],
                "username": r["username"],
                "faction": r["faction"],
                "wins": r["wins"] or 0,
                "losses": r["losses"] or 0,
                "territories": r["total_territories"] or 0,
            }
            for r in rows
        ]

    def _row_to_territory(self, row: sqlite3.Row) -> Dict:
        return {
            "id": row["id"],
            "region": row["region"],
            "district": row["district"],
            "owner_id": row["owner_id"],
            "original_faction": row["original_faction"] or row["region"],
            "defense": row["defense_power"] or 0,
            "fortification": row["fortification"] or 0,
            "partisan": row["partisan_activity"] or 0,
            "logistics": row["logistics_level"] or 100,
            "capture_date": row["capture_date"],
        }

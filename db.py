import json
import asyncio
import datetime as dt
from typing import Optional, List, Dict, Tuple

import aiosqlite

from config import (
    DB_PATH, DEFAULT_MAP_POOL, TIERS,
    INITIATOR_COOLDOWN_DAYS, DEFENDER_PROTECTION_DAYS,
    REMATCH_DISTINCT_DEFENDERS_REQUIRED,
)
from utils import utcnow, tier_for_position, tier_index


# -------------------- DB init (NO migrations) --------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                map_pool_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS players (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                display_name TEXT NOT NULL,
                tier TEXT NOT NULL,
                created_at TEXT NOT NULL,
                balance INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                ladder_pos INTEGER,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_players_ladderpos
            ON players(guild_id, ladder_pos);

            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                played_at TEXT NOT NULL,
                challenger_id INTEGER NOT NULL,
                defender_id INTEGER NOT NULL,
                challenger_score INTEGER NOT NULL,
                defender_score INTEGER NOT NULL,
                challenger_ban TEXT,
                defender_ban TEXT,
                game1_map TEXT,
                replay_url TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL, -- PENDING, READY, COMPLETED, CANCELED
                challenger_id INTEGER NOT NULL,
                defender_id INTEGER NOT NULL,
                challenger_ban TEXT,
                defender_ban TEXT,
                game1_map TEXT,
                thread_id INTEGER,
                map_pool_json TEXT
            );

            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                challenge_id INTEGER NOT NULL,
                bettor_id INTEGER NOT NULL,
                pick_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        await db.commit()


# -------------------- Settings: map pool --------------------
async def get_map_pool(guild_id: int) -> List[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT map_pool_json FROM guild_settings WHERE guild_id=?", (guild_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO guild_settings (guild_id, map_pool_json) VALUES (?, ?)",
                (guild_id, json.dumps(DEFAULT_MAP_POOL)),
            )
            await db.commit()
            return DEFAULT_MAP_POOL[:]
        try:
            return json.loads(row[0])
        except Exception:
            return DEFAULT_MAP_POOL[:]


async def set_map_pool(guild_id: int, maps: List[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO guild_settings (guild_id, map_pool_json)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET map_pool_json=excluded.map_pool_json
            """,
            (guild_id, json.dumps(maps)),
        )
        await db.commit()


# -------------------- Players + ladder --------------------
async def ensure_player_row(guild_id: int, user_id: int, display_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM players WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        row = await cur.fetchone()
        if row:
            await db.execute(
                "UPDATE players SET display_name=? WHERE guild_id=? AND user_id=?",
                (display_name, guild_id, user_id),
            )
            await db.commit()
            return

        await db.execute(
            """
            INSERT INTO players (guild_id, user_id, display_name, tier, created_at, balance, is_active, ladder_pos)
            VALUES (?, ?, ?, 'F', ?, 1000, 0, NULL)
            """,
            (guild_id, user_id, display_name, utcnow().isoformat()),
        )
        await db.commit()


async def get_player(guild_id: int, user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT user_id, display_name, tier, balance, created_at, is_active, ladder_pos
            FROM players
            WHERE guild_id=? AND user_id=?
            """,
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "user_id": int(row[0]),
            "display_name": str(row[1]),
            "tier": str(row[2]),
            "balance": int(row[3]),
            "created_at": str(row[4]),
            "is_active": int(row[5]),
            "ladder_pos": row[6] if row[6] is None else int(row[6]),
        }


async def get_ladder_pos(guild_id: int, user_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT ladder_pos FROM players WHERE guild_id=? AND user_id=? AND is_active=1",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None


async def recompute_tiers_db_only(guild_id: int):
    """
    Re-number ladder positions to 1..N and set tiers, without ever violating
    UNIQUE(guild_id, ladder_pos).

    Strategy:
      1) Ensure inactive players have NULL ladder_pos
      2) Shift all active ladder_pos upward by +10000 (freeing 1..N)
      3) Assign new ladder_pos sequentially (safe because old values are 10000+)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN")

        # Safety cleanup: inactive players should not have a ladder_pos
        await db.execute(
            "UPDATE players SET ladder_pos=NULL WHERE guild_id=? AND is_active=0",
            (guild_id,),
        )

        # Shift active positions away to avoid collisions with 1..N
        await db.execute(
            """
            UPDATE players
            SET ladder_pos = ladder_pos + 10000
            WHERE guild_id=? AND is_active=1 AND ladder_pos IS NOT NULL
            """,
            (guild_id,),
        )

        # Read in the order of old ladder positions (now 10000+)
        cur = await db.execute(
            """
            SELECT user_id
            FROM players
            WHERE guild_id=? AND is_active=1 AND ladder_pos IS NOT NULL
            ORDER BY ladder_pos ASC
            """,
            (guild_id,),
        )
        rows = await cur.fetchall()
        user_ids = [int(r[0]) for r in rows]

        # Assign new positions + tiers (safe because current positions are 10000+)
        for idx, uid in enumerate(user_ids, start=1):
            tier = tier_for_position(idx)
            await db.execute(
                "UPDATE players SET ladder_pos=?, tier=? WHERE guild_id=? AND user_id=?",
                (idx, tier, guild_id, uid),
            )

        await db.commit()

async def ladder_join_db(guild_id: int, user_id: int, display_name: str) -> bool:
    await ensure_player_row(guild_id, user_id, display_name)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT is_active FROM players WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        row = await cur.fetchone()
        if row and int(row[0]) == 1:
            return False

        await db.execute(
            "UPDATE players SET is_active=1, display_name=? WHERE guild_id=? AND user_id=?",
            (display_name, guild_id, user_id),
        )

        cur2 = await db.execute(
            "SELECT COALESCE(MAX(ladder_pos), 0) FROM players WHERE guild_id=? AND is_active=1 AND ladder_pos IS NOT NULL",
            (guild_id,),
        )
        max_pos = int((await cur2.fetchone())[0])

        await db.execute(
            "UPDATE players SET ladder_pos=? WHERE guild_id=? AND user_id=?",
            (max_pos + 1, guild_id, user_id),
        )
        await db.commit()

    await recompute_tiers_db_only(guild_id)
    return True


async def ladder_withdraw_db(guild_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT is_active, ladder_pos FROM players WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        if not row or int(row[0]) == 0:
            return False

        removed_pos = row[1]
        await db.execute(
            "UPDATE players SET is_active=0, ladder_pos=NULL WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        if removed_pos is not None:
            await db.execute(
                """
                UPDATE players
                SET ladder_pos = ladder_pos - 1
                WHERE guild_id=? AND is_active=1 AND ladder_pos IS NOT NULL AND ladder_pos > ?
                """,
                (guild_id, int(removed_pos)),
            )
        await db.commit()

    await recompute_tiers_db_only(guild_id)
    return True


async def list_ladder(guild_id: int, limit: int) -> List[Tuple[int, int, str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT user_id, ladder_pos, tier
            FROM players
            WHERE guild_id=? AND is_active=1 AND ladder_pos IS NOT NULL
            ORDER BY ladder_pos ASC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        rows = await cur.fetchall()
    return [(int(uid), int(pos), str(tier)) for uid, pos, tier in rows]


# -------------------- Cooldowns + rematch constraints --------------------
async def initiator_cooldown_until(guild_id: int, user_id: int) -> Optional[dt.datetime]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT played_at
            FROM matches
            WHERE guild_id=? AND challenger_id=?
            ORDER BY played_at DESC, id DESC
            LIMIT 1
            """,
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        played_at = dt.datetime.fromisoformat(row[0])
        return played_at + dt.timedelta(days=INITIATOR_COOLDOWN_DAYS)


async def defender_protection_until(guild_id: int, user_id: int) -> Optional[dt.datetime]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT played_at
            FROM matches
            WHERE guild_id=? AND defender_id=?
            ORDER BY played_at DESC, id DESC
            LIMIT 1
            """,
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        played_at = dt.datetime.fromisoformat(row[0])
        return played_at + dt.timedelta(days=DEFENDER_PROTECTION_DAYS)


async def get_last_match(guild_id: int) -> Optional[Tuple[int, int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT challenger_id, defender_id
            FROM matches
            WHERE guild_id=?
            ORDER BY played_at DESC, id DESC
            LIMIT 1
            """,
            (guild_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return int(row[0]), int(row[1])


async def challenger_rematch_spacing_ok(guild_id: int, challenger_id: int, defender_id: int) -> bool:
    last = await get_last_match(guild_id)
    if last and set(last) == {challenger_id, defender_id}:
        return False

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id
            FROM matches
            WHERE guild_id=? AND challenger_id=? AND defender_id=?
            ORDER BY played_at DESC, id DESC
            LIMIT 1
            """,
            (guild_id, challenger_id, defender_id),
        )
        row = await cur.fetchone()
        if not row:
            return True

        last_id = int(row[0])
        cur2 = await db.execute(
            """
            SELECT DISTINCT defender_id
            FROM matches
            WHERE guild_id=? AND challenger_id=? AND id > ? AND defender_id != ?
            """,
            (guild_id, challenger_id, last_id, defender_id),
        )
        defenders = await cur2.fetchall()
        return len(defenders) >= REMATCH_DISTINCT_DEFENDERS_REQUIRED


# -------------------- Challenges --------------------
async def get_open_challenge(guild_id: int, user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id, status, created_at, challenger_id, defender_id,
                   challenger_ban, defender_ban, game1_map,
                   thread_id, map_pool_json
            FROM challenges
            WHERE guild_id=?
              AND status IN ('PENDING','READY')
              AND (challenger_id=? OR defender_id=?)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (guild_id, user_id, user_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "id": int(row[0]),
            "status": str(row[1]),
            "created_at": str(row[2]),
            "challenger_id": int(row[3]),
            "defender_id": int(row[4]),
            "challenger_ban": row[5],
            "defender_ban": row[6],
            "game1_map": row[7],
            "thread_id": row[8],
            "map_pool": json.loads(row[9]) if row[9] else [],
        }


async def can_challenge(guild_id: int, challenger_id: int, defender_id: int) -> Tuple[bool, str]:
    if challenger_id == defender_id:
        return False, "You can’t challenge yourself."

    ch = await get_player(guild_id, challenger_id)
    de = await get_player(guild_id, defender_id)
    if not ch:
        return False, "You are not registered. Use /join."
    if not de:
        return False, "Defender is not registered. Ask them to /join."
    if ch["is_active"] != 1:
        return False, "You are withdrawn. Use /join."
    if de["is_active"] != 1:
        return False, "That player is withdrawn and cannot be challenged."

    allowed = {ch["tier"]}
    if ch["tier"] != "S":
        allowed.add(TIERS[tier_index(ch["tier"]) - 1])  # one tier above
    if de["tier"] not in allowed:
        return False, f"Tier rule: you can only challenge same tier ({ch['tier']}) or 1 tier above."

    cd = await initiator_cooldown_until(guild_id, challenger_id)
    if cd and cd > utcnow():
        return False, f"Initiator cooldown: you can challenge again after {cd.isoformat()}."

    prot = await defender_protection_until(guild_id, defender_id)
    if prot and prot > utcnow():
        return False, f"Defender protection: that player can’t be challenged until {prot.isoformat()}."

    if await get_open_challenge(guild_id, challenger_id):
        return False, "You already have an active challenge."
    if await get_open_challenge(guild_id, defender_id):
        return False, "That player already has an active challenge."

    if not await challenger_rematch_spacing_ok(guild_id, challenger_id, defender_id):
        return False, "Rematch rule: you can’t play the same opponent twice in a row, and you must face 2 other defenders before re-challenging them."

    return True, "OK"


async def eligible_defenders(guild_id: int, challenger_id: int) -> List[int]:
    ch = await get_player(guild_id, challenger_id)
    if not ch or ch["is_active"] != 1:
        return []

    allowed = {ch["tier"]}
    if ch["tier"] != "S":
        allowed.add(TIERS[tier_index(ch["tier"]) - 1])

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id FROM players WHERE guild_id=? AND is_active=1 AND tier IN (%s) AND user_id != ?"
            % ",".join("?" * len(allowed)),
            tuple([guild_id, *list(allowed), challenger_id]),
        )
        rows = await cur.fetchall()

    out: List[int] = []
    for (uid,) in rows:
        ok, _ = await can_challenge(guild_id, challenger_id, int(uid))
        if ok:
            out.append(int(uid))
    return out


async def create_challenge(
    guild_id: int,
    challenger_id: int,
    defender_id: int,
    map_pool_snapshot: list[str],
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO challenges (
                guild_id, created_at, status,
                challenger_id, defender_id,
                challenger_ban, defender_ban, game1_map,
                thread_id, map_pool_json
            )
            VALUES (?, ?, 'PENDING', ?, ?, NULL, NULL, NULL, NULL, ?)
            """,
            (guild_id, utcnow().isoformat(), challenger_id, defender_id, json.dumps(map_pool_snapshot)),
        )
        await db.commit()
        return int(cur.lastrowid)

async def set_challenge_thread_id(guild_id: int, challenge_id: int, thread_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE challenges SET thread_id=? WHERE guild_id=? AND id=?",
            (thread_id, guild_id, challenge_id),
        )
        await db.commit()

async def update_challenge(guild_id: int, challenge_id: int, **kwargs):
    allowed = {"challenger_ban", "defender_ban", "game1_map", "status"}
    fields = []
    params = []
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        fields.append(f"{k}=?")
        params.append(v)
    if not fields:
        return
    params.extend([guild_id, challenge_id])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE challenges SET {', '.join(fields)} WHERE guild_id=? AND id=?", tuple(params))
        await db.commit()


async def cancel_challenge(guild_id: int, challenge_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE challenges SET status='CANCELED' WHERE guild_id=? AND id=?", (guild_id, challenge_id))
        await db.commit()


async def complete_challenge_to_match(
    guild_id: int,
    challenge_id: int,
    challenger_score: int,
    defender_score: int,
    replay_url: Optional[str],
    notes: Optional[str],
):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT challenger_id, defender_id, challenger_ban, defender_ban, game1_map
            FROM challenges
            WHERE guild_id=? AND id=? AND status IN ('PENDING','READY')
            """,
            (guild_id, challenge_id),
        )
        row = await cur.fetchone()
        if not row:
            raise ValueError("Challenge not found or not active.")

        challenger_id, defender_id, cb, dban, g1 = int(row[0]), int(row[1]), row[2], row[3], row[4]

        await db.execute(
            """
            INSERT INTO matches (
                guild_id, played_at, challenger_id, defender_id,
                challenger_score, defender_score,
                challenger_ban, defender_ban, game1_map,
                replay_url, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                utcnow().isoformat(),
                challenger_id,
                defender_id,
                challenger_score,
                defender_score,
                cb,
                dban,
                g1,
                replay_url,
                notes,
            ),
        )
        await db.execute("UPDATE challenges SET status='COMPLETED' WHERE guild_id=? AND id=?", (guild_id, challenge_id))
        await db.commit()


async def swap_positions_by_result(guild_id: int, winner_id: int, loser_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT user_id, ladder_pos, is_active
            FROM players
            WHERE guild_id=? AND user_id IN (?, ?)
            """,
            (guild_id, winner_id, loser_id),
        )
        rows = await cur.fetchall()
        if len(rows) != 2:
            return

        data = {int(uid): (pos, int(active)) for uid, pos, active in rows}
        wpos, wactive = data.get(winner_id, (None, 0))
        lpos, lactive = data.get(loser_id, (None, 0))

        if not (wactive == 1 and lactive == 1 and wpos is not None and lpos is not None):
            return

        wpos = int(wpos)
        lpos = int(lpos)
        if wpos == lpos:
            return

        # TEMP slot that cannot collide with normal ladder positions
        TEMP = -1

        await db.execute("BEGIN")

        # Ensure TEMP isn't already used (paranoia)
        await db.execute(
            "UPDATE players SET ladder_pos=NULL WHERE guild_id=? AND ladder_pos=?",
            (guild_id, TEMP),
        )

        # Move winner out of the way
        await db.execute(
            "UPDATE players SET ladder_pos=? WHERE guild_id=? AND user_id=?",
            (TEMP, guild_id, winner_id),
        )

        # Move loser into winner's old position
        await db.execute(
            "UPDATE players SET ladder_pos=? WHERE guild_id=? AND user_id=?",
            (wpos, guild_id, loser_id),
        )

        # Move winner into loser's old position
        await db.execute(
            "UPDATE players SET ladder_pos=? WHERE guild_id=? AND user_id=?",
            (lpos, guild_id, winner_id),
        )

        await db.commit()

    await recompute_tiers_db_only(guild_id)


# -------------------- History --------------------
async def list_recent_matches(guild_id: int, limit: int) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT played_at, challenger_id, defender_id, challenger_score, defender_score, replay_url
            FROM matches
            WHERE guild_id=?
            ORDER BY played_at DESC, id DESC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        rows = await cur.fetchall()

    return [
        {
            "played_at": r[0],
            "challenger_id": int(r[1]),
            "defender_id": int(r[2]),
            "challenger_score": int(r[3]),
            "defender_score": int(r[4]),
            "replay_url": r[5],
        }
        for r in rows
    ]


# -------------------- Gambling --------------------
async def place_bet(guild_id: int, challenge_id: int, bettor_id: int, pick_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT status, challenger_id, defender_id FROM challenges WHERE guild_id=? AND id=?",
            (guild_id, challenge_id),
        )
        row = await cur.fetchone()
        if not row:
            raise ValueError("Challenge not found.")
        status = str(row[0])
        challenger_id, defender_id = int(row[1]), int(row[2])

        if status not in ("PENDING", "READY"):
            raise ValueError("You can only bet on active (pending/ready) challenges.")
        if pick_id not in (challenger_id, defender_id):
            raise ValueError("Pick must be the challenger or defender of that challenge.")

        cur2 = await db.execute("SELECT balance FROM players WHERE guild_id=? AND user_id=?", (guild_id, bettor_id))
        prow = await cur2.fetchone()
        if not prow:
            raise ValueError("You are not registered. Use /join first.")
        bal = int(prow[0])
        if amount <= 0:
            raise ValueError("Bet amount must be positive.")
        if bal < amount:
            raise ValueError(f"Insufficient balance. You have {bal}.")

        await db.execute("UPDATE players SET balance=balance-? WHERE guild_id=? AND user_id=?", (amount, guild_id, bettor_id))
        await db.execute(
            "INSERT INTO bets (guild_id, challenge_id, bettor_id, pick_id, amount, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, challenge_id, bettor_id, pick_id, amount, utcnow().isoformat()),
        )
        await db.commit()


async def settle_bets_and_rewards(guild_id: int, challenge_id: int, winner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE players SET balance=balance+50 WHERE guild_id=? AND user_id=?", (guild_id, winner_id))

        cur = await db.execute("SELECT bettor_id, pick_id, amount FROM bets WHERE guild_id=? AND challenge_id=?", (guild_id, challenge_id))
        rows = await cur.fetchall()
        for bettor_id, pick_id, amount in rows:
            if int(pick_id) == int(winner_id):
                payout = int(amount) * 2
                await db.execute("UPDATE players SET balance=balance+? WHERE guild_id=? AND user_id=?", (payout, guild_id, int(bettor_id)))
        await db.commit()

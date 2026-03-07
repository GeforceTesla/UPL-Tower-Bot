import re
import datetime as dt
from typing import Tuple
from config import TIERS


DURATION_PATTERN = re.compile(r"(\d+)([smhd])")

MULTIPLIER = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}

TIERS = ["S", "A", "B", "C", "D", "E", "F"]

def parse_duration(text: str) -> int:
    text = text.lower().strip()
    total = 0

    for amount, unit in DURATION_PATTERN.findall(text):
        total += int(amount) * MULTIPLIER[unit]

    if total == 0:
        raise ValueError("Invalid duration format")

    return total

def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def parse_score(score: str) -> Tuple[int, int]:
    m = re.fullmatch(r"\s*(\d)\s*-\s*(\d)\s*", score)
    if not m:
        raise ValueError("Score must look like `2-1` or `0-2`.")
    a, b = int(m.group(1)), int(m.group(2))
    if (a, b) not in [(2, 0), (2, 1), (1, 2), (0, 2)]:
        raise ValueError("BO3 score must be one of: 2-0, 2-1, 1-2, 0-2.")
    return a, b

def tier_for_position(pos: int, bracket_size: int) -> str:
    if bracket_size <= 0:
        raise ValueError("bracket_size must be > 0")

    if pos <= bracket_size:
        return "S"
    if pos <= bracket_size * 2:
        return "A"
    if pos <= bracket_size * 3:
        return "B"
    if pos <= bracket_size * 4:
        return "C"
    if pos <= bracket_size * 5:
        return "D"
    if pos <= bracket_size * 6:
        return "E"
    return "F"

def tier_index(tier: str) -> int:
    return TIERS.index(tier)

def is_admin_interaction(user) -> bool:
    # user is discord.Member
    return getattr(user, "guild_permissions", None) and user.guild_permissions.manage_guild

def discord_ts(dt: dt.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt.timezone.utc)
    ts = int(dt.timestamp())
    return f"<t:{ts}:F> (<t:{ts}:R>)"

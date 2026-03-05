import re
import datetime as dt
from typing import Tuple
from config import TIERS

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

def tier_for_position(pos: int) -> str:
    if pos <= 6:  return "S"
    if pos <= 12: return "A"
    if pos <= 18: return "B"
    if pos <= 24: return "C"
    if pos <= 30: return "D"
    if pos <= 36: return "E"
    return "F"

def tier_index(tier: str) -> int:
    return TIERS.index(tier)

def is_admin_interaction(user) -> bool:
    # user is discord.Member
    return getattr(user, "guild_permissions", None) and user.guild_permissions.manage_guild

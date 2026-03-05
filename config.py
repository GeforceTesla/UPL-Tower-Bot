import os

DB_PATH = os.environ.get("CHALLENGE_DB", "challenge_bot.sqlite3")
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

TIERS = ["S", "A", "B", "C", "D", "E", "F"]

DEFAULT_MAP_POOL = [
    "Fighting Spirit",
    "Polypoid",
    "Circuit Breaker",
    "Good Night",
    "Heartbreak Ridge",
    "Nostalgia",
    "Destination",
    "Eclipse",
]

INITIATOR_COOLDOWN_DAYS = 2
DEFENDER_PROTECTION_DAYS = 7
REMATCH_DISTINCT_DEFENDERS_REQUIRED = 2

CROSSED_SWORDS = "⚔️"

TIER_ROLE_NAMES = {
    "S": "S Rankers",
    "A": "A Floor",
    "B": "B Floor",
    "C": "C Floor",
    "D": "D Floor",
    "E": "E Floor",
    "F": "F Floor",
}
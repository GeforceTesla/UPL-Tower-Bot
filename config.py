import os

DB_PATH = os.environ.get("CHALLENGE_DB", "challenge_bot.sqlite3")
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
print(DISCORD_TOKEN)

TIERS = ["Champion", "S", "A", "B", "C", "D", "E", "F"]

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

CROSSED_SWORDS = "⚔️"

TIER_ROLE_NAMES = {
    "S": "S",
    "A": "A",
    "B": "B",
    "C": "C",
    "D": "D",
    "E": "E",
    "F": "F",
}
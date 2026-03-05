import discord
from discord.ext import commands

from config import DISCORD_TOKEN
from db import init_db

INITIAL_EXTENSIONS = [
    "cogs.admin",
    "cogs.ladder",
    "cogs.challenges",
    "cogs.gamble",
    "cogs.history",
]

class ChallengeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        for ext in INITIAL_EXTENSIONS:
            await self.load_extension(ext)
        await self.tree.sync()

bot = ChallengeBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} | guilds={len(bot.guilds)}")

bot.run(DISCORD_TOKEN)

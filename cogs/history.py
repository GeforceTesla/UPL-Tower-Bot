import discord
from discord.ext import commands
from discord import app_commands

from db import get_history_events
from utils import discord_ts_from_iso

class HistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="history", description="Show recent match and admin history.")
    @app_commands.describe(limit="How many events to show (max 30)")
    async def history(self, interaction: discord.Interaction, limit: int = 10):
        assert interaction.guild
    
        limit = max(1, min(limit, 30))
    
        events = await get_history_events(interaction.guild.id, limit)
    
        if not events:
            await interaction.response.send_message("No history yet.", ephemeral=True)
            return
    
        lines = []
    
        for e in events:
            when = discord_ts_from_iso(e["timestamp"])
    
            if e["type"] == "MATCH":
                lines.append(
                    f"🎮 {when}\n"
                    f"<@{e['challenger_id']}> vs <@{e['defender_id']}> — "
                    f"**{e['challenger_score']}-{e['defender_score']}**"
                )
    
            elif e["type"] == "SWAP_PLAYERS":
                lines.append(
                    f"🛠️ {when}\n"
                    f"Admin <@{e['admin_id']}> swapped "
                    f"<@{e['player_a_id']}> and <@{e['player_b_id']}>\n"
                    f"Reason: {e['reason']}"
                )
    
            else:
                lines.append(
                    f"🛠️ {when}\n"
                    f"Admin event: **{e['type']}**"
                )
    
        message = "**History**\n\n" + "\n\n".join(lines)
    
        if len(message) > 1900:
            message = message[:1900] + "\n..."
    
        await interaction.response.send_message(message, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HistoryCog(bot))

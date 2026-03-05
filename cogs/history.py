import discord
from discord.ext import commands
from discord import app_commands

from db import list_recent_matches

class HistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="history", description="Show recent match history.")
    @app_commands.describe(limit="How many matches to show (max 20)")
    async def history(self, interaction: discord.Interaction, limit: int = 10):
        assert interaction.guild
        limit = max(1, min(limit, 20))
        rows = await list_recent_matches(interaction.guild.id, limit)
        if not rows:
            await interaction.response.send_message("No matches recorded yet.", ephemeral=True)
            return

        lines = []
        for r in rows:
            lines.append(
                f"- {r['played_at']}: <@{r['challenger_id']}> vs <@{r['defender_id']}> "
                f"**{r['challenger_score']}-{r['defender_score']}** "
                f"{'(replay)' if r['replay_url'] else ''}"
            )
        await interaction.response.send_message("**Recent matches:**\n" + "\n".join(lines), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HistoryCog(bot))

import discord
from discord.ext import commands
from discord import app_commands

from db import get_player, place_bet

class GambleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Show your gambling balance.")
    async def balance(self, interaction: discord.Interaction):
        assert interaction.guild
        p = await get_player(interaction.guild.id, interaction.user.id)
        if not p:
            await interaction.response.send_message("Use /join first.", ephemeral=True)
            return
        await interaction.response.send_message(f"Balance: **{p['balance']}**", ephemeral=True)

    @app_commands.command(name="bet", description="Bet on an active match by challenge ID.")
    @app_commands.describe(challenge_id="Challenge ID", pick="Who will win", amount="Amount to bet")
    async def bet(self, interaction: discord.Interaction, challenge_id: int, pick: discord.Member, amount: int):
        assert interaction.guild
        p = await get_player(interaction.guild.id, interaction.user.id)
        if not p:
            await interaction.response.send_message("Use /join first.", ephemeral=True)
            return
        try:
            await place_bet(interaction.guild.id, challenge_id, interaction.user.id, pick.id, amount)
        except Exception as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(f"Bet placed: **{amount}** on {pick.mention} for challenge **{challenge_id}**.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GambleCog(bot))

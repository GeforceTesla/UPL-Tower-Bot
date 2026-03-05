from discord.ext import commands
from discord import app_commands
import discord

from utils import is_admin_interaction
from db import get_map_pool, set_map_pool
from config import DEFAULT_MAP_POOL

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="admin_maps_set", description="[Admin] Replace server map pool (comma-separated).")
    @app_commands.describe(maps_csv="Example: Fighting Spirit, Polypoid, Circuit Breaker")
    async def admin_maps_set(self, interaction: discord.Interaction, maps_csv: str):
        assert interaction.guild
        if not is_admin_interaction(interaction.user):
            await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
            return

        maps = [m.strip() for m in maps_csv.split(",") if m.strip()]
        if len(maps) < 3:
            await interaction.response.send_message("Need at least 3 maps.", ephemeral=True)
            return

        seen = set()
        out = []
        for m in maps:
            if m not in seen:
                seen.add(m)
                out.append(m)

        await set_map_pool(interaction.guild.id, out)
        await interaction.response.send_message(f"Server map pool set to **{len(out)}** maps.", ephemeral=True)

    @app_commands.command(name="admin_maps_add", description="[Admin] Add a map to the server pool.")
    async def admin_maps_add(self, interaction: discord.Interaction, map_name: str):
        assert interaction.guild
        if not is_admin_interaction(interaction.user):
            await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
            return

        map_name = map_name.strip()
        if not map_name:
            await interaction.response.send_message("Map name cannot be empty.", ephemeral=True)
            return

        pool = await get_map_pool(interaction.guild.id)
        if map_name in pool:
            await interaction.response.send_message("That map is already in the pool.", ephemeral=True)
            return

        pool.append(map_name)
        await set_map_pool(interaction.guild.id, pool)
        await interaction.response.send_message(f"Added **{map_name}**. Pool size: **{len(pool)}**.", ephemeral=True)

    @app_commands.command(name="admin_maps_remove", description="[Admin] Remove a map from the server pool.")
    async def admin_maps_remove(self, interaction: discord.Interaction, map_name: str):
        assert interaction.guild
        if not is_admin_interaction(interaction.user):
            await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
            return

        pool = await get_map_pool(interaction.guild.id)
        if map_name not in pool:
            await interaction.response.send_message("Map not found in pool. Use /maps and copy exact name.", ephemeral=True)
            return
        if len(pool) <= 3:
            await interaction.response.send_message("Refusing: pool must have at least 3 maps.", ephemeral=True)
            return

        pool = [m for m in pool if m != map_name]
        await set_map_pool(interaction.guild.id, pool)
        await interaction.response.send_message(f"Removed **{map_name}**. Pool size: **{len(pool)}**.", ephemeral=True)

    @app_commands.command(name="admin_maps_reset", description="[Admin] Reset server map pool to default.")
    async def admin_maps_reset(self, interaction: discord.Interaction):
        assert interaction.guild
        if not is_admin_interaction(interaction.user):
            await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
            return

        await set_map_pool(interaction.guild.id, DEFAULT_MAP_POOL[:])
        await interaction.response.send_message(f"Server map pool reset to default (**{len(DEFAULT_MAP_POOL)}** maps).", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))

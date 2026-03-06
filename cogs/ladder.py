from discord.ext import commands
from discord import app_commands
import discord

from db import (
    get_player,
    ladder_join_db,
    ladder_withdraw_db,
    list_ladder,
    initiator_cooldown_until,
    defender_protection_until,
    get_map_pool,
    can_challenge,
)
from roles import recompute_and_sync_roles
from utils import utcnow

class LadderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="join", description="Join the ladder (placed at the bottom).")
    async def join(self, interaction: discord.Interaction):
        assert interaction.guild
        ok = await ladder_join_db(interaction.guild.id, interaction.user.id, interaction.user.display_name)
        if not ok:
            await interaction.response.send_message("You are already active on the ladder.", ephemeral=True)
            return

        await recompute_and_sync_roles(self.bot, interaction.guild.id)
        p = await get_player(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            f"Joined the ladder.\nTier: **{p['tier']}** | Rank: **#{p['ladder_pos']}** | Balance: **{p['balance']}**",
            ephemeral=True,
        )

    @app_commands.command(name="withdraw", description="Withdraw from the ladder (everyone below shifts up).")
    async def withdraw(self, interaction: discord.Interaction):
        assert interaction.guild
        ok = await ladder_withdraw_db(interaction.guild.id, interaction.user.id)
        if not ok:
            await interaction.response.send_message("You are not currently active on the ladder.", ephemeral=True)
            return

        await recompute_and_sync_roles(self.bot, interaction.guild.id)
        await interaction.response.send_message("Withdrawn from the ladder. Slots below shifted up.", ephemeral=True)

    @app_commands.command(name="ladder", description="Show the ladder (ordered) with tiers.")
    @app_commands.describe(limit="Max players to show (default 60, max 200)")
    async def ladder(self, interaction: discord.Interaction, limit: int = 60):
        assert interaction.guild
        limit = max(1, min(limit, 200))
        rows = await list_ladder(interaction.guild.id, limit)
        if not rows:
            await interaction.response.send_message("Ladder is empty. Use /join.", ephemeral=True)
            return

        lines = []
        current_tier = None
        for uid, pos, tier in rows:
            if tier != current_tier:
                current_tier = tier
                lines.append(f"\n**{tier}**")
            lines.append(f"`{pos:>3}` <@{uid}>")

        await interaction.response.send_message("🏆 **Ladder**" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="profile", description="Show tier/rank/balance and cooldown info.")
    async def profile(self, interaction: discord.Interaction, user: discord.Member | None = None):
        assert interaction.guild
        user = user or interaction.user
        p = await get_player(interaction.guild.id, user.id)
        if not p:
            await interaction.response.send_message("Not registered. Use /join.", ephemeral=True)
            return

        icd = await initiator_cooldown_until(interaction.guild.id, user.id)
        dcd = await defender_protection_until(interaction.guild.id, user.id)
        now = utcnow()

        msg = [
            f"**{user.display_name}**",
            f"Active: **{'yes' if p['is_active'] == 1 else 'no'}**",
            f"Rank: **#{p['ladder_pos'] if p['ladder_pos'] is not None else '—'}**",
            f"Tier: **{p['tier']}**",
            f"Balance: **{p['balance']}**",
            f"Initiator cooldown ends: **{icd.isoformat() if icd else 'N/A'}** ({'ACTIVE' if icd and icd > now else 'ok'})",
            f"Defender protection ends: **{dcd.isoformat() if dcd else 'N/A'}** ({'ACTIVE' if dcd and dcd > now else 'ok'})",
        ]
        await interaction.response.send_message("\n".join(msg), ephemeral=True)

    @app_commands.command(name="maps", description="Show the current server map pool.")
    async def maps(self, interaction: discord.Interaction):
        assert interaction.guild

        pool = await get_map_pool(interaction.guild.id)

        if not pool:
            await interaction.response.send_message("Map pool is empty.", ephemeral=True)
            return

        lines = [f"{i+1}. {m}" for i, m in enumerate(pool)]

        await interaction.response.send_message(
            "**Current Map Pool**\n" + "\n".join(lines),
            ephemeral=True
        )

    @app_commands.command(
        name="players",
        description="Show players from rank 1 to X and whether you can challenge them."
    )
    @app_commands.describe(limit="Show ranks 1 to this number (default 30, max 100)")
    async def players(self, interaction: discord.Interaction, limit: int = 30):
        assert interaction.guild

        limit = max(1, min(limit, 100))

        me = await get_player(interaction.guild.id, interaction.user.id)
        if not me or me["is_active"] != 1:
            await interaction.response.send_message(
                "You must be on the ladder to use this command. Use /join first.",
                ephemeral=True,
            )
            return

        rows = await list_ladder(interaction.guild.id, limit)
        if not rows:
            await interaction.response.send_message("Ladder is empty.", ephemeral=True)
            return

        lines = []
        for uid, pos, tier in rows:
            member = interaction.guild.get_member(uid)
            display = member.display_name if member else f"User {uid}"

            if uid == interaction.user.id:
                lines.append(f"`#{pos:>2}` **{display}** [{tier}] — you")
                continue

            ok, reason = await can_challenge(interaction.guild.id, interaction.user.id, uid)

            if ok:
                status = "✅ AVAILABLE"
            else:
                status = f"❌ {reason}"

            lines.append(f"`#{pos:>2}` **{display}** [{tier}] — {status}")

        # Discord message length safety
        message = "**Players**\n" + "\n".join(lines)
        if len(message) > 1900:
            chunks = []
            current = "**Players**\n"
            for line in lines:
                if len(current) + len(line) + 1 > 1900:
                    chunks.append(current)
                    current = line + "\n"
                else:
                    current += line + "\n"
            if current:
                chunks.append(current)

            await interaction.response.send_message(chunks[0], ephemeral=True)
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk, ephemeral=True)
            return

        await interaction.response.send_message(message, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(LadderCog(bot))

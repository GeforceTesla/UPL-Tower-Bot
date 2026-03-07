import aiosqlite
import db
from discord.ext import commands
from discord import app_commands
import discord
import re
from roles import recompute_and_sync_roles
from utils import (
    is_admin_interaction,
    parse_duration,
)
from db import (
    get_map_pool,
    set_map_pool,
    get_rules,
    set_rules,
    ensure_player_row,
)
from config import (
    DEFAULT_MAP_POOL,
)

MENTION_RE = re.compile(r"<@!?(\d+)>")

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="admin_rules", description="[Admin] Show current ladder rule settings.")
    async def admin_rules(self, interaction: discord.Interaction):
        assert interaction.guild
        if not is_admin_interaction(interaction.user):
            await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
            return

        rules = await get_rules(interaction.guild.id)
        await interaction.response.send_message(
            f"**Current Rules**\n"
            f"- Initiator cooldown: **{rules['initiator_cooldown_seconds']}s**\n"
            f"- Defender protection: **{rules['defender_protection_seconds']}s**\n"
            f"- Other defenders required before rematch: **{rules['rematch_required_others']}**\n"
            f"- Players per bracket: **{rules['bracket_size']}**",
            ephemeral=True,
        )

    @app_commands.command(name="admin_set_rules", description="[Admin] Configure ladder cooldown, rematch, and bracket rules.")
    @app_commands.describe(
        initiator_cd="Cooldown before a challenger can initiate again (30s, 10m, 2h, 1d, 1d12h)",
        defender_cd="Protection time for defenders after a match (30s, 10m, 2h, 1d)",
        rematch_count="Number of other defenders required before re-challenging the same player",
        bracket_size="Players per bracket (example: 6 means 6 players each in S/A/B/C/D/E)"
    )
    async def admin_set_rules(
        self,
        interaction: discord.Interaction,
        initiator_cd: str,
        defender_cd: str,
        rematch_count: int,
        bracket_size: int,
    ):
        assert interaction.guild
        if not is_admin_interaction(interaction.user):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        if rematch_count < 0 or bracket_size <= 0:
            await interaction.response.send_message(
                "rematch_count must be 0 or greater, and bracket_size must be greater than 0.",
                ephemeral=True,
            )
            return

        try:
            initiator_seconds = parse_duration(initiator_cd)
            defender_seconds = parse_duration(defender_cd)
        except ValueError:
            await interaction.response.send_message(
                "Invalid duration. Example: 30s, 10m, 2h, 1d",
                ephemeral=True,
            )
            return

        await set_rules(
            interaction.guild.id,
            initiator_cooldown_seconds=initiator_seconds,
            defender_protection_seconds=defender_seconds,
            rematch_required_others=rematch_count,
            bracket_size=bracket_size,
        )

        await recompute_and_sync_roles(self.bot, interaction.guild.id)

        await interaction.response.send_message(
            f"**Rules updated**\n"
            f"- Initiator cooldown: **{initiator_cd}**\n"
            f"- Defender protection: **{defender_cd}**\n"
            f"- Other defenders required before rematch: **{rematch_count}**\n"
            f"- Players per bracket: **{bracket_size}**",
            ephemeral=True,
        )

    @app_commands.command(
        name="admin_seed_ladder",
        description="[Admin] Replace the current ladder with a manually pasted ordered list of users."
    )
    @app_commands.describe(
        ladder_text="Paste one user mention per line, top to bottom. Example: @UserA"
    )
    async def admin_seed_ladder(self, interaction: discord.Interaction, ladder_text: str):
        assert interaction.guild

        if not is_admin_interaction(interaction.user):
            await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        tokens = []
        for line in ladder_text.splitlines():
            for part in line.split(","):
                part = part.strip()
                if part:
                    tokens.append(part)

        if not tokens:
            await interaction.followup.send("No players found in input.", ephemeral=True)
            return

        ordered_user_ids: list[int] = []
        seen: set[int] = set()

        for token in tokens:
            m = MENTION_RE.search(token)
            if not m:
                await interaction.followup.send(
                    f"Could not parse a user mention from token: `{token}`",
                    ephemeral=True,
                )
                return

            uid = int(m.group(1))
            if uid in seen:
                await interaction.followup.send(
                    f"Duplicate player found: <@{uid}>",
                    ephemeral=True,
                )
                return

            member = interaction.guild.get_member(uid)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(uid)
                except Exception:
                    await interaction.followup.send(
                        f"User not found in this server: <@{uid}>",
                        ephemeral=True,
                    )
                    return

            seen.add(uid)
            ordered_user_ids.append(uid)

        # Ensure rows exist first
        for uid in ordered_user_ids:
            member = interaction.guild.get_member(uid)
            if member is None:
                member = await interaction.guild.fetch_member(uid)
            await ensure_player_row(interaction.guild.id, member.id, member.display_name)

        # Replace active ladder with this exact ordering
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute("BEGIN")

            # Withdraw everyone first
            await conn.execute(
                """
                UPDATE players
                SET is_active=0, ladder_pos=NULL
                WHERE guild_id=?
                """,
                (interaction.guild.id,),
            )

            # Insert ordered ladder
            for pos, uid in enumerate(ordered_user_ids, start=1):
                member = interaction.guild.get_member(uid)
                if member is None:
                    member = await interaction.guild.fetch_member(uid)

                await conn.execute(
                    """
                    UPDATE players
                    SET display_name=?, is_active=1, ladder_pos=?
                    WHERE guild_id=? AND user_id=?
                    """,
                    (member.display_name, pos, interaction.guild.id, uid),
                )

            await conn.commit()

        await recompute_and_sync_roles(self.bot, interaction.guild.id)

        preview = "\n".join(
            f"`{idx}` <@{uid}>"
            for idx, uid in enumerate(ordered_user_ids[:20], start=1)
        )
        extra = ""
        if len(ordered_user_ids) > 20:
            extra = f"\n...and {len(ordered_user_ids) - 20} more"

        await interaction.followup.send(
            f"Ladder initialized with **{len(ordered_user_ids)}** players.\n\n{preview}{extra}",
            ephemeral=True,
        )

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

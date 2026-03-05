import asyncio
from typing import Optional, Dict

import discord
import aiosqlite

from config import DB_PATH, TIER_ROLE_NAMES
from db import recompute_tiers_db_only


def resolve_tier_roles(guild: discord.Guild) -> Dict[str, discord.Role]:
    name_to_role = {r.name: r for r in guild.roles}
    out: Dict[str, discord.Role] = {}
    for tier, role_name in TIER_ROLE_NAMES.items():
        role = name_to_role.get(role_name)
        if role:
            out[tier] = role
    return out


async def sync_member_tier_role(guild: discord.Guild, member: discord.Member, tier: Optional[str], is_active: bool):
    roles_by_tier = resolve_tier_roles(guild)
    tier_role_ids = {r.id for r in roles_by_tier.values()}

    # Remove all tier roles except target
    target = roles_by_tier.get(tier) if (is_active and tier in roles_by_tier) else None
    remove_roles = [r for r in member.roles if r.id in tier_role_ids and (target is None or r.id != target.id)]

    add_roles = []
    if target and target not in member.roles:
        add_roles = [target]

    try:
        if remove_roles:
            await member.remove_roles(*remove_roles, reason="Ladder tier role sync")
        if add_roles:
            await member.add_roles(*add_roles, reason="Ladder tier role sync")
    except discord.Forbidden:
        # Bot role is below target roles or missing Manage Roles
        pass
    except Exception:
        pass


async def recompute_and_sync_roles(bot: discord.Client, guild_id: int):
    # 1) recompute tiers in DB
    await recompute_tiers_db_only(guild_id)

    # 2) sync roles
    guild = bot.get_guild(guild_id)
    if guild is None:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, tier, is_active FROM players WHERE guild_id=?", (guild_id,))
        rows = await cur.fetchall()

    for uid, tier, is_active in rows:
        uid = int(uid)

        member = guild.get_member(uid)
        if member is None:
            try:
                member = await guild.fetch_member(uid)  # fallback if cache missing
            except Exception:
                continue

        await sync_member_tier_role(guild, member, str(tier), bool(is_active))
        await asyncio.sleep(0.1)

import json
from typing import Optional
import db
import discord
from discord.ext import commands
from discord import app_commands

from config import CROSSED_SWORDS
from db import (
    get_map_pool, get_open_challenge, can_challenge, eligible_defenders,
    create_challenge, update_challenge, cancel_challenge,
    complete_challenge_to_match, swap_positions_by_result, get_ladder_pos,
    set_challenge_thread_id
)
from roles import recompute_and_sync_roles
from utils import parse_score

async def post_to_thread(guild: discord.Guild, thread_id: int | None, content: str):
    if not thread_id:
        return
    ch = guild.get_channel(thread_id)
    if ch is None:
        try:
            ch = await guild.fetch_channel(thread_id)
        except Exception:
            return
    if isinstance(ch, discord.Thread):
        try:
            await ch.send(content)
        except Exception:
            pass

async def create_challenge_thread(
    challenge_id: int,
    interaction: discord.Interaction,
    announcement_message: discord.Message,
    challenger: discord.Member,
    defender: discord.Member,
    map_pool_snapshot: list[str],
) -> int | None:
    if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
        return None

    a_pos = await get_ladder_pos(interaction.guild.id, challenger.id)
    b_pos = await get_ladder_pos(interaction.guild.id, defender.id)
    a_rank = f"(#{a_pos})" if a_pos is not None else "(#?)"
    b_rank = f"(#{b_pos})" if b_pos is not None else "(#?)"

    thread_name = f"[#{challenge_id}] {challenger.display_name} {a_rank} {CROSSED_SWORDS} {defender.display_name} {b_rank}"
    thread_name = thread_name[:95]

    try:
        thread = await announcement_message.create_thread(
            name=thread_name,
            auto_archive_duration=1440,
            reason="Challenge thread",
        )
        try:
            await thread.add_user(challenger)
        except Exception:
            pass
        try:
            await thread.add_user(defender)
        except Exception:
            pass

        pool_lines = "\n".join([f"{i+1}. {m}" for i, m in enumerate(map_pool_snapshot)]) if map_pool_snapshot else "—"
        await thread.send(
            f"🧵 **Challenge thread**\n"
            f"**Challenger:** {challenger.mention}\n"
            f"**Defender:** {defender.mention}\n\n"
            f"**Format:** Best of 3\n"
            f"- Challenger bans first\n"
            f"- Defender chooses the first map\n"
            f"- Loser picks thereafter\n\n"
            f"**Map pool for THIS challenge (locked):**\n{pool_lines}\n\n"
            f"✅ **Commands (no IDs needed):**\n"
            f"1) Challenger: `/ban <map name>`\n"
            f"2) Defender: `/ban <map name>`\n"
            f"3) Defender: `/pickmap <map name>` (sets Game 1)\n"
            f"4) After match: `/report winner:@Player games_won:2 games_lost:1`\n"
            f"   Optional: attach replay or provide `replay_url`\n\n"
            f"Useful:\n"
            f"- `/mychallenge` shows your active challenge state\n"
            f"- `/eligible` shows who you can challenge\n"
        )
        return thread.id
    except discord.Forbidden:
        return None
    except Exception:
        return None

class ChallengesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="eligible", description="List players you are allowed to challenge right now.")
    async def eligible(self, interaction: discord.Interaction):
        assert interaction.guild
        ids = await eligible_defenders(interaction.guild.id, interaction.user.id)
        if not ids:
            await interaction.response.send_message("No eligible defenders right now.", ephemeral=True)
            return
        members = []
        for uid in ids[:25]:
            m = interaction.guild.get_member(uid)
            members.append(m.mention if m else f"<@{uid}>")
        await interaction.response.send_message("Eligible defenders:\n" + ", ".join(members), ephemeral=True)

    @app_commands.command(name="challenge", description="Start a challenge vs a defender (same tier or 1 tier above).")
    async def challenge(self, interaction: discord.Interaction, defender: discord.Member):
        assert interaction.guild
        ok, reason = await can_challenge(interaction.guild.id, interaction.user.id, defender.id)
        if not ok:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        map_pool_snapshot = await get_map_pool(interaction.guild.id)

        await interaction.response.send_message(
            f"⚔️ **Challenge created**\n"
            f"**Challenger:** {interaction.user.mention}\n"
            f"**Defender:** {defender.mention}\n\n"
            f"Creating thread…"
        )
        announcement = await interaction.original_response()

        cid = await create_challenge(interaction.guild.id, interaction.user.id, defender.id, map_pool_snapshot)
        thread_id = await create_challenge_thread(cid, interaction, announcement, interaction.user, defender, map_pool_snapshot)
        

        if thread_id:
            await set_challenge_thread_id(interaction.guild.id, cid, thread_id)
            await post_to_thread(interaction.guild, thread_id, "Challenge is now **PENDING**. Challenger bans first with `/ban <map name>`.")
            await interaction.followup.send("Challenge thread created ✅", ephemeral=True)
        else:
            await interaction.followup.send(
                f"Challenge created (ID **{cid}**) but I couldn't create a thread. Check bot perms for threads.",
                ephemeral=True,
            )

    @app_commands.command(name="mychallenge", description="Show your active challenge (if any).")
    async def mychallenge(self, interaction: discord.Interaction):
        assert interaction.guild
        ch = await get_open_challenge(interaction.guild.id, interaction.user.id)
        if not ch:
            await interaction.response.send_message("No active challenge for you.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Challenge ({ch['status']})\n"
            f"Created: **{ch['created_at']}**\n"
            f"Challenger: <@{ch['challenger_id']}>\n"
            f"Defender: <@{ch['defender_id']}>\n"
            f"Challenger ban: **{ch['challenger_ban'] or '—'}**\n"
            f"Defender ban: **{ch['defender_ban'] or '—'}**\n"
            f"Game 1 map: **{ch['game1_map'] or '—'}**",
            ephemeral=True,
        )

    @app_commands.command(name="ban", description="Ban a map for your active challenge.")
    async def ban(self, interaction: discord.Interaction, map_name: str):
        assert interaction.guild
        ch = await get_open_challenge(interaction.guild.id, interaction.user.id)
        if not ch:
            await interaction.response.send_message("You have no active challenge.", ephemeral=True)
            return

        pool = ch["map_pool"]
        if map_name not in pool:
            await interaction.response.send_message("Map not in THIS challenge's locked pool. Copy exact name from the thread.", ephemeral=True)
            return

        if interaction.user.id == ch["challenger_id"]:
            if ch["challenger_ban"]:
                await interaction.response.send_message("You already banned a map.", ephemeral=True)
                return
            if ch["defender_ban"] and map_name == ch["defender_ban"]:
                await interaction.response.send_message("That map is already banned by defender.", ephemeral=True)
                return

            await update_challenge(interaction.guild.id, ch["id"], challenger_ban=map_name)
            await interaction.response.send_message(f"Challenger ban recorded: **{map_name}**.")
            await post_to_thread(interaction.guild, ch.get("thread_id"), f"🛑 Challenger {interaction.user.mention} banned **{map_name}**.\nDefender: `/ban <map>` then `/pickmap <map>`.")
            return

        if interaction.user.id == ch["defender_id"]:
            if not ch["challenger_ban"]:
                await interaction.response.send_message("Challenger must ban first.", ephemeral=True)
                return
            if ch["defender_ban"]:
                await interaction.response.send_message("You already banned a map.", ephemeral=True)
                return
            if map_name == ch["challenger_ban"]:
                await interaction.response.send_message("That map is already banned by challenger.", ephemeral=True)
                return

            await update_challenge(interaction.guild.id, ch["id"], defender_ban=map_name)
            await interaction.response.send_message(f"Defender ban recorded: **{map_name}**.")
            await post_to_thread(interaction.guild, ch.get("thread_id"), f"🛑 Defender {interaction.user.mention} banned **{map_name}**.\nNow `/pickmap <map>`.")
            return

        await interaction.response.send_message("You are not a participant in this challenge.", ephemeral=True)

    @app_commands.command(name="pickmap", description="Defender selects the first map (after both bans).")
    async def pickmap(self, interaction: discord.Interaction, map_name: str):
        assert interaction.guild
        ch = await get_open_challenge(interaction.guild.id, interaction.user.id)
        if not ch:
            await interaction.response.send_message("You have no active challenge.", ephemeral=True)
            return
        if interaction.user.id != ch["defender_id"]:
            await interaction.response.send_message("Only the defender picks Game 1 map.", ephemeral=True)
            return
        if not ch["challenger_ban"] or not ch["defender_ban"]:
            await interaction.response.send_message("Both bans must be done first.", ephemeral=True)
            return
        if map_name not in ch["map_pool"]:
            await interaction.response.send_message("Map not in THIS challenge's locked pool.", ephemeral=True)
            return
        if map_name in (ch["challenger_ban"], ch["defender_ban"]):
            await interaction.response.send_message("That map is banned.", ephemeral=True)
            return

        await update_challenge(interaction.guild.id, ch["id"], game1_map=map_name, status="READY")
        await interaction.response.send_message(f"Game 1 map selected: **{map_name}**. Challenge is now READY.")
        await post_to_thread(interaction.guild, ch.get("thread_id"), f"🗺️ Game 1 map: **{map_name}**.\nAfter match: `/report score:2-1`.")

    @app_commands.command(name="cancel", description="Cancel your active challenge (participants only).")
    async def cancel(self, interaction: discord.Interaction):
        assert interaction.guild
        ch = await get_open_challenge(interaction.guild.id, interaction.user.id)
        if not ch:
            await interaction.response.send_message("No active challenge to cancel.", ephemeral=True)
            return
        await cancel_challenge(interaction.guild.id, ch["id"])
        await interaction.response.send_message("Challenge canceled.")
        await post_to_thread(interaction.guild, ch.get("thread_id"), "❌ Challenge canceled.")

    @app_commands.command(name="report", description="Report the result of your active challenge.")
    @app_commands.describe(
        winner="The winner of the match",
        games_won="Winner's game count (must be 2 in a BO3)",
        games_lost="Loser's game count (0 or 1 in a BO3)",
        replay="Optional replay file upload",
        replay_url="Optional replay link",
        notes="Optional notes",
    )
    async def report(
        self,
        interaction: discord.Interaction,
        winner: discord.Member,
        games_won: int,
        games_lost: int,
        replay: Optional[discord.Attachment] = None,
        replay_url: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        assert interaction.guild

        ch = None

        if interaction.channel_id is not None:
            ch = await db.get_challenge_by_thread_id(interaction.guild.id, interaction.channel_id)

        if ch is None:
            ch = await db.get_open_challenge(interaction.guild.id, interaction.user.id)

        if not ch:
            await interaction.response.send_message(
                "You have no active challenge.",
                ephemeral=True,
            )
            return

        challenger_id = ch["challenger_id"]
        defender_id = ch["defender_id"]

        if interaction.user.id not in (challenger_id, defender_id):
            await interaction.response.send_message(
                "Only the challenger or defender can report this match.",
                ephemeral=True,
            )
            return

        if winner.id not in (challenger_id, defender_id):
            await interaction.response.send_message(
                "The winner must be one of the two players in this challenge.",
                ephemeral=True,
            )
            return

        # Validate BO3 score
        if games_won != 2 or games_lost not in (0, 1):
            await interaction.response.send_message(
                "Invalid BO3 score. Use winner games_won=2 and games_lost=0 or 1.",
                ephemeral=True,
            )
            return

        if not replay_url and replay is not None:
            replay_url = replay.url

        if winner.id == challenger_id:
            loser_id = defender_id
            challenger_score = games_won
            defender_score = games_lost
        else:
            loser_id = challenger_id
            challenger_score = games_lost
            defender_score = games_won

        try:
            await db.complete_challenge_to_match(
                interaction.guild.id,
                ch["id"],
                challenger_score=challenger_score,
                defender_score=defender_score,
                replay_url=replay_url,
                notes=notes,
            )

            await db.settle_bets_and_rewards(
                interaction.guild.id,
                ch["id"],
                winner.id,
            )

            if winner.id == challenger_id:
                await db.swap_positions_by_result(
                    interaction.guild.id,
                    winner.id,
                    loser_id,
                )

            await recompute_and_sync_roles(self.bot, interaction.guild.id)

        except Exception as e:
            await interaction.response.send_message(
                f"Failed: {e}",
                ephemeral=True,
            )
            return

        winner_member = interaction.guild.get_member(winner.id)
        loser_member = interaction.guild.get_member(loser_id)

        winner_name = winner_member.display_name if winner_member else f"<@{winner.id}>"
        loser_name = loser_member.display_name if loser_member else f"<@{loser_id}>"

        rank_note = "Ladder position swapped." if winner.id == challenger_id else "No ladder swap (defender held position)."

        await interaction.response.send_message(
            f"Result recorded.\n"
            f"**{winner_name}** defeated **{loser_name}** **{games_won}-{games_lost}**.\n"
            f"{rank_note}\n"
            f"Replay: {replay_url or '—'}"
        )

        thread_id = ch.get("thread_id")
        if thread_id:
            try:
                thread = interaction.guild.get_channel(thread_id)
                if thread is None:
                    thread = await interaction.guild.fetch_channel(thread_id)

                if isinstance(thread, discord.Thread):
                    await thread.send(
                        f"✅ **Result recorded**\n"
                        f"Winner: <@{winner.id}>\n"
                        f"Score: **{games_won}-{games_lost}**\n"
                        f"Replay: {replay_url or '—'}\n\n"
                        f"🔒 Thread closed."
                    )
                    await thread.edit(
                        archived=True,
                        locked=True,
                        reason="Match reported",
                    )
            except Exception:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(ChallengesCog(bot))

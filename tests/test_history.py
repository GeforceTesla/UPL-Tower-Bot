import os
import sys
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ["DISCORD_TOKEN"] = "test-token"
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import db
from cogs.history import HistoryCog


class DummyResponse:
    def __init__(self):
        self.send_message = AsyncMock()


class DummyUser:
    def __init__(self, user_id=999):
        self.id = user_id


class DummyGuild:
    def __init__(self, guild_id: int):
        self.id = guild_id


class DummyInteraction:
    def __init__(self, guild):
        self.guild = guild
        self.user = DummyUser()
        self.response = DummyResponse()


@pytest.fixture
def history_cog():
    return HistoryCog(SimpleNamespace())


@pytest.mark.asyncio
async def test_history_events_include_matches_and_admin_swaps_sorted(fresh_db):
    guild_id = 1

    await db.ladder_join_db(guild_id, 1, "Alpha")
    await db.ladder_join_db(guild_id, 2, "Beta")

    pool = await db.get_map_pool(guild_id)

    cid = await db.create_challenge(guild_id, 2, 1, pool)
    await db.complete_challenge_to_match(
        guild_id,
        cid,
        challenger_score=2,
        defender_score=1,
        replay_url=None,
        notes=None,
    )

    await db.admin_swap_players(
        guild_id=guild_id,
        admin_id=999,
        player_a_id=1,
        player_b_id=2,
        reason="Fix misreport",
    )

    events = await db.get_history_events(guild_id, limit=10)

    assert len(events) == 2
    assert events[0]["type"] == "SWAP_PLAYERS"
    assert events[0]["admin_id"] == 999
    assert events[0]["player_a_id"] == 1
    assert events[0]["player_b_id"] == 2
    assert events[0]["reason"] == "Fix misreport"

    assert events[1]["type"] == "MATCH"
    assert events[1]["challenger_id"] == 2
    assert events[1]["defender_id"] == 1
    assert events[1]["challenger_score"] == 2
    assert events[1]["defender_score"] == 1


@pytest.mark.asyncio
async def test_history_command_displays_match_and_admin_swap(fresh_db, history_cog):
    guild_id = 1
    guild = DummyGuild(guild_id)
    interaction = DummyInteraction(guild)

    await db.ladder_join_db(guild_id, 1, "Alpha")
    await db.ladder_join_db(guild_id, 2, "Beta")

    pool = await db.get_map_pool(guild_id)

    cid = await db.create_challenge(guild_id, 2, 1, pool)
    await db.complete_challenge_to_match(
        guild_id,
        cid,
        challenger_score=2,
        defender_score=0,
        replay_url=None,
        notes=None,
    )

    await db.admin_swap_players(
        guild_id=guild_id,
        admin_id=999,
        player_a_id=1,
        player_b_id=2,
        reason="Manual correction",
    )

    await history_cog.history.callback(history_cog, interaction, 10)

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    msg = args[0]

    assert "History" in msg
    assert "Admin <@999> swapped <@1> and <@2>" in msg
    assert "Reason: Manual correction" in msg
    assert "<@2> vs <@1>" in msg
    assert "**2-0**" in msg
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_history_command_empty(fresh_db, history_cog):
    guild = DummyGuild(1)
    interaction = DummyInteraction(guild)

    await history_cog.history.callback(history_cog, interaction, 10)

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args

    assert "No history yet." in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_history_limit_is_respected(fresh_db):
    guild_id = 1

    await db.ladder_join_db(guild_id, 1, "Alpha")
    await db.ladder_join_db(guild_id, 2, "Beta")

    pool = await db.get_map_pool(guild_id)

    for _ in range(5):
        cid = await db.create_challenge(guild_id, 2, 1, pool)
        await db.complete_challenge_to_match(
            guild_id,
            cid,
            challenger_score=2,
            defender_score=1,
            replay_url=None,
            notes=None,
        )

    events = await db.get_history_events(guild_id, limit=3)

    assert len(events) == 3

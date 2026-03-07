import os
import sys
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ["DISCORD_TOKEN"] = "test-token"
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import db
from cogs.challenges import ChallengesCog


class DummyResponse:
    def __init__(self):
        self.send_message = AsyncMock()
        self.defer = AsyncMock()


class DummyFollowup:
    def __init__(self):
        self.send = AsyncMock()


class DummyGuild:
    def __init__(self, guild_id: int, members=None):
        self.id = guild_id
        self._members = members or {}
        self._channels = {}

    def get_member(self, user_id: int):
        return self._members.get(user_id)

    async def fetch_member(self, user_id: int):
        member = self._members.get(user_id)
        if member is None:
            raise ValueError(f"Member {user_id} not found")
        return member

    def get_channel(self, channel_id: int):
        return self._channels.get(channel_id)

    async def fetch_channel(self, channel_id: int):
        ch = self._channels.get(channel_id)
        if ch is None:
            raise ValueError(f"Channel {channel_id} not found")
        return ch


class DummyGuildPermissions:
    def __init__(self, manage_guild: bool = False):
        self.manage_guild = manage_guild


class DummyMember:
    def __init__(self, user_id: int, display_name: str, manage_guild: bool = False):
        self.id = user_id
        self.display_name = display_name
        self.guild_permissions = DummyGuildPermissions(manage_guild)

    @property
    def mention(self):
        return f"<@{self.id}>"


class DummyThread:
    def __init__(self):
        self.send = AsyncMock()
        self.edit = AsyncMock()


class DummyGuild:
    def __init__(self, guild_id: int, members: dict[int, DummyMember] | None = None):
        self.id = guild_id
        self._members = members or {}
        self._channels = {}

    def get_member(self, user_id: int):
        return self._members.get(user_id)

    async def fetch_member(self, user_id: int):
        member = self._members.get(user_id)
        if member is None:
            raise ValueError(f"Member {user_id} not found")
        return member

    def get_channel(self, channel_id: int):
        return self._channels.get(channel_id)

    async def fetch_channel(self, channel_id: int):
        ch = self._channels.get(channel_id)
        if ch is None:
            raise ValueError(f"Channel {channel_id} not found")
        return ch


class DummyInteraction:
    def __init__(self, guild, user, channel_id: int | None = None):
        self.guild = guild
        self.user = user
        self.channel_id = channel_id
        self.response = DummyResponse()
        self.followup = DummyFollowup()
        self.attachments = []


@pytest.fixture
def challenges_cog():
    bot = SimpleNamespace()
    return ChallengesCog(bot)


@pytest.mark.asyncio
async def test_report_rejects_non_participant(fresh_db, challenges_cog):
    guild_id = 1
    thread_id = 999

    members = {
        1: DummyMember(1, "Defender"),
        2: DummyMember(2, "Challenger"),
        3: DummyMember(3, "Spectator"),
    }
    guild = DummyGuild(guild_id, members)
    guild._channels[thread_id] = DummyThread()

    await db.ladder_join_db(guild_id, 1, "Defender")
    await db.ladder_join_db(guild_id, 2, "Challenger")
    await db.ladder_join_db(guild_id, 3, "Spectator")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)

    # store thread_id on the challenge
    await db.set_challenge_thread_id(guild_id, cid, thread_id)
    await db.update_challenge(
        guild_id,
        cid,
        challenger_ban="Fighting Spirit",
        defender_ban="Polypoid",
        game1_map="Circuit Breaker",
        status="READY",
        thread_id=thread_id,
    )

    interaction = DummyInteraction(guild, members[3], channel_id=thread_id)

    await challenges_cog.report.callback(
        challenges_cog,
        interaction,
        members[2],
        2,
        1,
        None,
        None,
        None,
    )

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "Only the challenger or defender can report this match." in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_report_rejects_winner_not_in_match(fresh_db, challenges_cog):
    guild_id = 1

    members = {
        1: DummyMember(1, "Defender"),
        2: DummyMember(2, "Challenger"),
        3: DummyMember(3, "OtherGuy"),
    }
    guild = DummyGuild(guild_id, members)

    await db.ladder_join_db(guild_id, 1, "Defender")
    await db.ladder_join_db(guild_id, 2, "Challenger")
    await db.ladder_join_db(guild_id, 3, "OtherGuy")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)
    await db.update_challenge(
        guild_id,
        cid,
        challenger_ban="Fighting Spirit",
        defender_ban="Polypoid",
        game1_map="Circuit Breaker",
        status="READY",
    )

    interaction = DummyInteraction(guild, members[2])

    await challenges_cog.report.callback(
        challenges_cog,
        interaction,
        members[3],   # invalid winner
        2,
        1,
        None,
        None,
        None,
    )

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "winner must be one of the two players" in args[0].lower()
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_report_rejects_invalid_bo3_score(fresh_db, challenges_cog):
    guild_id = 1

    members = {
        1: DummyMember(1, "Defender"),
        2: DummyMember(2, "Challenger"),
    }
    guild = DummyGuild(guild_id, members)

    await db.ladder_join_db(guild_id, 1, "Defender")
    await db.ladder_join_db(guild_id, 2, "Challenger")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)
    await db.update_challenge(
        guild_id,
        cid,
        challenger_ban="Fighting Spirit",
        defender_ban="Polypoid",
        game1_map="Circuit Breaker",
        status="READY",
    )

    interaction = DummyInteraction(guild, members[2])

    await challenges_cog.report.callback(
        challenges_cog,
        interaction,
        members[2],
        1,   # invalid winner score
        1,
        None,
        None,
        None,
    )

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "invalid bo3 score" in args[0].lower()
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_report_maps_score_correctly_when_challenger_wins(fresh_db, challenges_cog, monkeypatch):
    guild_id = 1

    members = {
        1: DummyMember(1, "Defender"),
        2: DummyMember(2, "Challenger"),
    }
    guild = DummyGuild(guild_id, members)

    # avoid Discord role sync dependency in this unit test
    monkeypatch.setattr("cogs.challenges.recompute_and_sync_roles", AsyncMock())

    await db.ladder_join_db(guild_id, 1, "Defender")
    await db.ladder_join_db(guild_id, 2, "Challenger")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)
    await db.update_challenge(
        guild_id,
        cid,
        challenger_ban="Fighting Spirit",
        defender_ban="Polypoid",
        game1_map="Circuit Breaker",
        status="READY",
    )

    interaction = DummyInteraction(guild, members[2])

    await challenges_cog.report.callback(
        challenges_cog,
        interaction,
        members[2],   # challenger wins
        2,
        1,
        None,
        None,
        None,
    )

    matches = await db.list_recent_matches(guild_id, 1)
    assert len(matches) == 1
    match = matches[0]

    assert match["challenger_id"] == 2
    assert match["defender_id"] == 1
    assert match["challenger_score"] == 2
    assert match["defender_score"] == 1

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "Result recorded" in args[0]


@pytest.mark.asyncio
async def test_report_maps_score_correctly_when_defender_wins(fresh_db, challenges_cog, monkeypatch):
    guild_id = 1

    members = {
        1: DummyMember(1, "Defender"),
        2: DummyMember(2, "Challenger"),
    }
    guild = DummyGuild(guild_id, members)

    monkeypatch.setattr("cogs.challenges.recompute_and_sync_roles", AsyncMock())

    await db.ladder_join_db(guild_id, 1, "Defender")
    await db.ladder_join_db(guild_id, 2, "Challenger")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)
    await db.update_challenge(
        guild_id,
        cid,
        challenger_ban="Fighting Spirit",
        defender_ban="Polypoid",
        game1_map="Circuit Breaker",
        status="READY",
    )

    interaction = DummyInteraction(guild, members[1])

    await challenges_cog.report.callback(
        challenges_cog,
        interaction,
        members[1],   # defender wins
        2,
        0,
        None,
        None,
        None,
    )

    matches = await db.list_recent_matches(guild_id, 1)
    assert len(matches) == 1
    match = matches[0]

    assert match["challenger_id"] == 2
    assert match["defender_id"] == 1
    assert match["challenger_score"] == 0
    assert match["defender_score"] == 2


@pytest.mark.asyncio
async def test_swap_positions_by_result_direct(fresh_db):
    guild_id = 1

    await db.ladder_join_db(guild_id, 1, "TopDefender")
    await db.ladder_join_db(guild_id, 2, "LowerChallenger")

    before_def = await db.get_player(guild_id, 1)
    before_ch = await db.get_player(guild_id, 2)

    assert before_def["ladder_pos"] == 1
    assert before_ch["ladder_pos"] == 2

    await db.swap_positions_by_result(guild_id, winner_id=2, loser_id=1)

    after_def = await db.get_player(guild_id, 1)
    after_ch = await db.get_player(guild_id, 2)

    assert after_ch["ladder_pos"] == 1
    assert after_def["ladder_pos"] == 2


@pytest.mark.asyncio
async def test_report_swaps_positions_and_rewards_winner(fresh_db, challenges_cog):
    guild_id = 1

    members = {
        1: DummyMember(1, "TopDefender"),
        2: DummyMember(2, "LowerChallenger"),
    }
    guild = DummyGuild(guild_id, members)

    # Let recompute_and_sync_roles run DB recompute, but skip Discord role sync
    challenges_cog.bot = SimpleNamespace(get_guild=lambda guild_id: None)

    await db.ladder_join_db(guild_id, 1, "TopDefender")
    await db.ladder_join_db(guild_id, 2, "LowerChallenger")

    before_def = await db.get_player(guild_id, 1)
    before_ch = await db.get_player(guild_id, 2)
    assert before_def["ladder_pos"] == 1
    assert before_ch["ladder_pos"] == 2

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)
    await db.update_challenge(
        guild_id,
        cid,
        challenger_ban="Fighting Spirit",
        defender_ban="Polypoid",
        game1_map="Circuit Breaker",
        status="READY",
    )

    interaction = DummyInteraction(guild, members[2])

    await challenges_cog.report.callback(
        challenges_cog,
        interaction,
        members[2],   # challenger wins
        2,
        1,
        None,
        None,
        None,
    )
    args, kwargs = interaction.response.send_message.await_args
    print(args[0])

    after_def = await db.get_player(guild_id, 1)
    after_ch = await db.get_player(guild_id, 2)

    # winner takes better spot
    assert after_ch["ladder_pos"] == 1
    assert after_def["ladder_pos"] == 2

    # winner gets +50
    assert after_ch["balance"] == 1050

@pytest.mark.asyncio
async def test_report_defender_win_does_not_swap_positions(fresh_db, challenges_cog):
    guild_id = 1

    members = {
        1: DummyMember(1, "TopDefender"),
        2: DummyMember(2, "LowerChallenger"),
    }
    guild = DummyGuild(guild_id, members)

    challenges_cog.bot = SimpleNamespace(get_guild=lambda guild_id: None)

    await db.ladder_join_db(guild_id, 1, "TopDefender")
    await db.ladder_join_db(guild_id, 2, "LowerChallenger")

    before_def = await db.get_player(guild_id, 1)
    before_ch = await db.get_player(guild_id, 2)
    assert before_def["ladder_pos"] == 1
    assert before_ch["ladder_pos"] == 2

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)
    await db.update_challenge(
        guild_id,
        cid,
        challenger_ban="Fighting Spirit",
        defender_ban="Polypoid",
        game1_map="Circuit Breaker",
        status="READY",
    )

    interaction = DummyInteraction(guild, members[1])

    await challenges_cog.report.callback(
        challenges_cog,
        interaction,
        members[1],   # defender wins
        2,
        1,
        None,
        None,
        None,
    )

    args, kwargs = interaction.response.send_message.await_args
    assert "Result recorded" in args[0]

    after_def = await db.get_player(guild_id, 1)
    after_ch = await db.get_player(guild_id, 2)

    # No swap when defender wins
    assert after_def["ladder_pos"] == 1
    assert after_ch["ladder_pos"] == 2

    # Winner still gets +50
    assert after_def["balance"] == 1050

import sys
import pathlib
import os

os.environ["DISCORD_TOKEN"] = "test-token"
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import db
from cogs.admin import AdminCog


class DummyResponse:
    def __init__(self):
        self.send_message = AsyncMock()
        self.defer = AsyncMock()


class DummyFollowup:
    def __init__(self):
        self.send = AsyncMock()

class DummyGuildPermissions:
    def __init__(self, manage_guild: bool):
        self.manage_guild = manage_guild


class DummyUser:
    def __init__(self, user_id: int = 999, manage_guild: bool = True, display_name: str = "AdminUser"):
        self.id = user_id
        self.display_name = display_name
        self.guild_permissions = DummyGuildPermissions(manage_guild)


class DummyMember:
    def __init__(self, user_id: int, display_name: str):
        self.id = user_id
        self.display_name = display_name


class DummyGuild:
    def __init__(self, guild_id: int, members: dict[int, DummyMember] | None = None):
        self.id = guild_id
        self._members = members or {}

    def get_member(self, user_id: int):
        return self._members.get(user_id)

    async def fetch_member(self, user_id: int):
        member = self._members.get(user_id)
        if member is None:
            raise ValueError(f"Member {user_id} not found")
        return member


class DummyInteraction:
    def __init__(self, guild, user):
        self.guild = guild
        self.user = user
        self.response = DummyResponse()
        self.followup = DummyFollowup()


@pytest.fixture
def admin_cog():
    bot = SimpleNamespace()
    return AdminCog(bot)


@pytest.mark.asyncio
async def test_admin_rules_requires_admin(fresh_db, admin_cog):
    guild = DummyGuild(1)
    interaction = DummyInteraction(guild, DummyUser(manage_guild=False))

    await admin_cog.admin_rules.callback(admin_cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "Admin only" in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_admin_rules_shows_defaults(fresh_db, admin_cog):
    guild = DummyGuild(1)
    interaction = DummyInteraction(guild, DummyUser(manage_guild=True))

    await admin_cog.admin_rules.callback(admin_cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    msg = args[0]

    assert "Current Rules" in msg
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_admin_set_rules_updates_db(fresh_db, admin_cog, monkeypatch):
    guild_id = 1
    guild = DummyGuild(guild_id)
    interaction = DummyInteraction(guild, DummyUser(manage_guild=True))

    monkeypatch.setattr("cogs.admin.recompute_and_sync_roles", AsyncMock())

    await admin_cog.admin_set_rules.callback(
        admin_cog,
        interaction,
        "1h",
        "2d",
        3,
        8,
    )

    rules = await db.get_rules(guild_id)
    assert rules["initiator_cooldown_seconds"] == 3600
    assert rules["defender_protection_seconds"] == 2 * 86400
    assert rules["rematch_required_others"] == 3
    assert rules["bracket_size"] == 8

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "Rules updated" in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_admin_set_rules_rejects_invalid_values(fresh_db, admin_cog):
    guild = DummyGuild(1)
    interaction = DummyInteraction(guild, DummyUser(manage_guild=True))

    await admin_cog.admin_set_rules.callback(
        admin_cog,
        interaction,
        "1h",
        "2d",
        -1,
        6,
    )

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "0 or greater" in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_admin_maps_set(fresh_db, admin_cog):
    guild_id = 1
    guild = DummyGuild(guild_id)
    interaction = DummyInteraction(guild, DummyUser(manage_guild=True))

    await admin_cog.admin_maps_set.callback(
        admin_cog,
        interaction,
        "Map A, Map B, Map C, Map A",
    )

    pool = await db.get_map_pool(guild_id)
    assert pool == ["Map A", "Map B", "Map C"]

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "set to" in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_admin_maps_add(fresh_db, admin_cog):
    guild_id = 1
    guild = DummyGuild(guild_id)
    interaction = DummyInteraction(guild, DummyUser(manage_guild=True))

    await db.set_map_pool(guild_id, ["Map A", "Map B", "Map C"])

    await admin_cog.admin_maps_add.callback(admin_cog, interaction, "Map D")

    pool = await db.get_map_pool(guild_id)
    assert pool == ["Map A", "Map B", "Map C", "Map D"]


@pytest.mark.asyncio
async def test_admin_maps_remove(fresh_db, admin_cog):
    guild_id = 1
    guild = DummyGuild(guild_id)
    interaction = DummyInteraction(guild, DummyUser(manage_guild=True))

    await db.set_map_pool(guild_id, ["Map A", "Map B", "Map C", "Map D"])

    await admin_cog.admin_maps_remove.callback(admin_cog, interaction, "Map B")

    pool = await db.get_map_pool(guild_id)
    assert pool == ["Map A", "Map C", "Map D"]


@pytest.mark.asyncio
async def test_admin_maps_reset(fresh_db, admin_cog):
    guild_id = 1
    guild = DummyGuild(guild_id)
    interaction = DummyInteraction(guild, DummyUser(manage_guild=True))

    await db.set_map_pool(guild_id, ["Custom 1", "Custom 2", "Custom 3"])

    await admin_cog.admin_maps_reset.callback(admin_cog, interaction)

    pool = await db.get_map_pool(guild_id)
    assert pool == db.DEFAULT_MAP_POOL


@pytest.mark.asyncio
async def test_admin_seed_ladder(fresh_db, admin_cog, monkeypatch):
    guild_id = 1
    members = {
        101: DummyMember(101, "Alpha"),
        102: DummyMember(102, "Beta"),
        103: DummyMember(103, "Gamma"),
    }
    guild = DummyGuild(guild_id, members)
    interaction = DummyInteraction(guild, DummyUser(manage_guild=True))

    # avoid role-sync dependency in unit test
    monkeypatch.setattr("cogs.admin.recompute_and_sync_roles", AsyncMock())

    ladder_text = "\n".join([
        "<@101>",
        "<@102>",
        "<@103>",
    ])

    await admin_cog.admin_seed_ladder.callback(admin_cog, interaction, ladder_text)

    p1 = await db.get_player(guild_id, 101)
    p2 = await db.get_player(guild_id, 102)
    p3 = await db.get_player(guild_id, 103)

    assert p1["ladder_pos"] == 1
    assert p2["ladder_pos"] == 2
    assert p3["ladder_pos"] == 3

    assert p1["is_active"] == 1
    assert p2["is_active"] == 1
    assert p3["is_active"] == 1

    interaction.followup.send.assert_awaited_once()
    args, kwargs = interaction.followup.send.await_args
    assert "Ladder initialized" in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_admin_seed_ladder_rejects_duplicate_players(fresh_db, admin_cog, monkeypatch):
    guild_id = 1
    members = {
        101: DummyMember(101, "Alpha"),
    }
    guild = DummyGuild(guild_id, members)
    interaction = DummyInteraction(guild, DummyUser(manage_guild=True))

    monkeypatch.setattr("cogs.admin.recompute_and_sync_roles", AsyncMock())

    ladder_text = "\n".join([
        "<@101>",
        "<@101>",
    ])

    await admin_cog.admin_seed_ladder.callback(admin_cog, interaction, ladder_text)

    interaction.followup.send.assert_awaited_once()
    args, kwargs = interaction.followup.send.await_args
    assert "Duplicate player found" in args[0]
    assert kwargs["ephemeral"] is True
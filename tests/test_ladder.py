import pytest
import aiosqlite

import db


@pytest.mark.asyncio
async def test_join_players_assigns_positions_and_tiers(fresh_db):
    guild_id = 1

    for i in range(1, 9):
        await db.ladder_join_db(guild_id, i, f"user{i}")

    p1 = await db.get_player(guild_id, 1)
    p6 = await db.get_player(guild_id, 6)
    p7 = await db.get_player(guild_id, 7)
    p8 = await db.get_player(guild_id, 8)

    assert p1["ladder_pos"] == 1
    assert p6["ladder_pos"] == 6
    assert p7["ladder_pos"] == 7
    assert p8["ladder_pos"] == 8

    assert p1["tier"] == "S"
    assert p6["tier"] == "S"
    assert p7["tier"] == "A"
    assert p8["tier"] == "A"


@pytest.mark.asyncio
async def test_withdraw_shifts_players_up(fresh_db):
    guild_id = 1

    for i in range(1, 6):
        await db.ladder_join_db(guild_id, i, f"user{i}")

    ok = await db.ladder_withdraw_db(guild_id, 2)
    assert ok is True

    p1 = await db.get_player(guild_id, 1)
    p2 = await db.get_player(guild_id, 2)
    p3 = await db.get_player(guild_id, 3)
    p4 = await db.get_player(guild_id, 4)
    p5 = await db.get_player(guild_id, 5)

    assert p1["ladder_pos"] == 1
    assert p2["ladder_pos"] is None
    assert p2["is_active"] == 0
    assert p3["ladder_pos"] == 2
    assert p4["ladder_pos"] == 3
    assert p5["ladder_pos"] == 4


@pytest.mark.asyncio
async def test_list_ladder_returns_ordered_players(fresh_db):
    guild_id = 1

    for i in range(1, 5):
        await db.ladder_join_db(guild_id, i, f"user{i}")

    rows = await db.list_ladder(guild_id, 10)
    assert [uid for uid, _, _ in rows] == [1, 2, 3, 4]

import pytest
import db


@pytest.mark.asyncio
async def test_default_rules_exist(fresh_db):
    guild_id = 1
    rules = await db.get_rules(guild_id)

    assert "initiator_cooldown_seconds" in rules
    assert "defender_protection_seconds" in rules
    assert "rematch_required_others" in rules
    assert "bracket_size" in rules


@pytest.mark.asyncio
async def test_set_rules_updates_values(fresh_db):
    guild_id = 1

    await db.set_rules(
        guild_id,
        initiator_cooldown_seconds=3600,
        defender_protection_seconds=7200,
        rematch_required_others=3,
        bracket_size=4,
    )

    rules = await db.get_rules(guild_id)
    assert rules["initiator_cooldown_seconds"] == 3600
    assert rules["defender_protection_seconds"] == 7200
    assert rules["rematch_required_others"] == 3
    assert rules["bracket_size"] == 4


@pytest.mark.asyncio
async def test_bracket_size_changes_tiers(fresh_db):
    guild_id = 1

    await db.set_rules(guild_id, bracket_size=4)

    for i in range(1, 10):
        await db.ladder_join_db(guild_id, i, f"user{i}")

    p1 = await db.get_player(guild_id, 1)
    p4 = await db.get_player(guild_id, 4)
    p5 = await db.get_player(guild_id, 5)
    p8 = await db.get_player(guild_id, 8)
    p9 = await db.get_player(guild_id, 9)

    assert p1["tier"] == "S"
    assert p4["tier"] == "S"
    assert p5["tier"] == "A"
    assert p8["tier"] == "A"
    assert p9["tier"] == "B"

import pytest
import db


@pytest.mark.asyncio
async def test_players_start_with_1000_balance(fresh_db):
    guild_id = 1
    await db.ladder_join_db(guild_id, 1, "user1")
    p = await db.get_player(guild_id, 1)
    assert p["balance"] == 1000


@pytest.mark.asyncio
async def test_place_bet_reduces_balance(fresh_db):
    guild_id = 1

    await db.ladder_join_db(guild_id, 1, "user1")
    await db.ladder_join_db(guild_id, 2, "user2")
    await db.ladder_join_db(guild_id, 3, "user3")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)

    await db.place_bet(guild_id, cid, bettor_id=3, pick_id=2, amount=200)

    bettor = await db.get_player(guild_id, 3)
    assert bettor["balance"] == 800


@pytest.mark.asyncio
async def test_settle_bets_and_winner_reward(fresh_db):
    guild_id = 1

    await db.ladder_join_db(guild_id, 1, "user1")
    await db.ladder_join_db(guild_id, 2, "user2")
    await db.ladder_join_db(guild_id, 3, "user3")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)

    await db.place_bet(guild_id, cid, bettor_id=3, pick_id=2, amount=200)
    await db.settle_bets_and_rewards(guild_id, cid, winner_id=2)

    winner = await db.get_player(guild_id, 2)
    bettor = await db.get_player(guild_id, 3)

    # winner +50
    assert winner["balance"] == 1050
    # bettor started 1000, bet 200 => 800, then won 400 payout => 1200
    assert bettor["balance"] == 1200

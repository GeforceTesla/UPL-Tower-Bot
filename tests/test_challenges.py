import pytest
import db


@pytest.mark.asyncio
async def test_can_challenge_same_tier_and_one_above(fresh_db):
    guild_id = 1

    # With default bracket size 6:
    # 1-6 S, 7-12 A, 13-18 B
    for i in range(1, 15):
        await db.ladder_join_db(guild_id, i, f"user{i}")

    # user 13 is B
    ok_same, _ = await db.can_challenge(guild_id, 13, 14)   # B -> B
    ok_above, _ = await db.can_challenge(guild_id, 13, 12)  # B -> A
    ok_two_above, _ = await db.can_challenge(guild_id, 13, 1)  # B -> S

    assert ok_same is True
    assert ok_above is True
    assert ok_two_above is False


@pytest.mark.asyncio
async def test_create_challenge_and_open_challenge_lookup(fresh_db):
    guild_id = 1

    for i in range(1, 3):
        await db.ladder_join_db(guild_id, i, f"user{i}")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)

    ch = await db.get_open_challenge(guild_id, 2)
    assert ch is not None
    assert ch["id"] == cid
    assert ch["challenger_id"] == 2
    assert ch["defender_id"] == 1
    assert ch["challenger_ban"] is None
    assert ch["defender_ban"] is None
    assert ch["game1_map"] is None


@pytest.mark.asyncio
async def test_update_challenge_bans_and_pickmap(fresh_db):
    guild_id = 1

    for i in range(1, 3):
        await db.ladder_join_db(guild_id, i, f"user{i}")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)

    await db.update_challenge(guild_id, cid, challenger_ban="Fighting Spirit")
    await db.update_challenge(guild_id, cid, defender_ban="Polypoid")
    await db.update_challenge(guild_id, cid, game1_map="Circuit Breaker", status="READY")

    ch = await db.get_open_challenge(guild_id, 2)
    assert ch["challenger_ban"] == "Fighting Spirit"
    assert ch["defender_ban"] == "Polypoid"
    assert ch["game1_map"] == "Circuit Breaker"
    assert ch["status"] == "READY"


@pytest.mark.asyncio
async def test_report_completes_challenge_and_swaps_positions(fresh_db):
    guild_id = 1

    # rank1 user1, rank2 user2
    await db.ladder_join_db(guild_id, 1, "user1")
    await db.ladder_join_db(guild_id, 2, "user2")

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

    await db.complete_challenge_to_match(
        guild_id,
        cid,
        challenger_score=2,
        defender_score=1,
        replay_url=None,
        notes=None,
    )

    await db.swap_positions_by_result(guild_id, winner_id=2, loser_id=1)

    p1 = await db.get_player(guild_id, 1)
    p2 = await db.get_player(guild_id, 2)

    assert p2["ladder_pos"] == 1
    assert p1["ladder_pos"] == 2


@pytest.mark.asyncio
async def test_initiator_cooldown_applies_after_match(fresh_db):
    guild_id = 1

    await db.set_rules(guild_id, initiator_cooldown_seconds=3600)

    await db.ladder_join_db(guild_id, 1, "user1")
    await db.ladder_join_db(guild_id, 2, "user2")
    await db.ladder_join_db(guild_id, 3, "user3")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)
    await db.complete_challenge_to_match(
        guild_id, cid, challenger_score=2, defender_score=0, replay_url=None, notes=None
    )

    ok, reason = await db.can_challenge(guild_id, 2, 3)
    assert ok is False
    assert "Initiator cooldown" in reason


@pytest.mark.asyncio
async def test_defender_protection_applies_after_match(fresh_db):
    guild_id = 1

    await db.set_rules(guild_id, defender_protection_seconds=3600)

    await db.ladder_join_db(guild_id, 1, "user1")
    await db.ladder_join_db(guild_id, 2, "user2")
    await db.ladder_join_db(guild_id, 3, "user3")

    pool = await db.get_map_pool(guild_id)
    cid = await db.create_challenge(guild_id, 2, 1, pool)
    await db.complete_challenge_to_match(
        guild_id, cid, challenger_score=2, defender_score=0, replay_url=None, notes=None
    )

    ok, reason = await db.can_challenge(guild_id, 3, 1)
    assert ok is False
    assert "Defender protection" in reason

@pytest.mark.asyncio
async def test_rematch_requires_other_defenders(fresh_db):
    guild_id = 1

    await db.set_rules(
        guild_id,
        initiator_cooldown_seconds=0,
        defender_protection_seconds=0,
        rematch_required_others=2,
    )

    for i in range(1, 6):
        await db.ladder_join_db(guild_id, i, f"user{i}")

    pool = await db.get_map_pool(guild_id)

    # 5 challenges 4
    cid1 = await db.create_challenge(guild_id, 5, 4, pool)
    await db.complete_challenge_to_match(guild_id, cid1, 2, 0, None, None)

    # immediate re-challenge blocked
    ok, reason = await db.can_challenge(guild_id, 5, 4)
    assert ok is False

    # challenge 3
    cid2 = await db.create_challenge(guild_id, 5, 3, pool)
    await db.complete_challenge_to_match(guild_id, cid2, 2, 0, None, None)

    # still blocked
    ok, _ = await db.can_challenge(guild_id, 5, 4)
    assert ok is False

    # challenge 2
    cid3 = await db.create_challenge(guild_id, 5, 2, pool)
    await db.complete_challenge_to_match(guild_id, cid3, 2, 0, None, None)

    # now allowed
    ok, reason = await db.can_challenge(guild_id, 5, 4)
    assert ok is True

from services.clash_royale import ClanMember, WarHistory, former_member_tags, race_participants
from services.scoring import score_members


def log_item(season: int, section: int, participants: list[dict]) -> dict:
    return {
        "seasonId": season,
        "sectionIndex": section,
        "standings": [{"clan": {"participants": participants}}],
    }


def player(tag: str, fame: int, decks: int = 4) -> dict:
    return {"tag": f"#{tag}", "name": f"name-{tag}", "fame": fame, "decksUsed": decks}


def make_history() -> WarHistory:
    # Deliberately out of order; WarHistory must sort newest first.
    items = [
        log_item(10, 1, [player("AAA", 2000), player("BBB", 1000)]),          # 2 wars ago
        log_item(10, 2, [player("AAA", 3000)]),                                # 1 war ago (newest)
        log_item(10, 0, [player("AAA", 1000), player("BBB", 500)]),            # 3 wars ago
    ]
    return WarHistory(items)


def test_ordering_and_fame():
    history = make_history()
    assert len(history) == 3
    assert history.fame("AAA", 1) == 3000
    assert history.fame("AAA", 2) == 2000
    assert history.fame("AAA", 3) == 1000
    assert history.fame("#aaa", 1) == 3000  # normalization
    assert history.fame("AAA", 4) == 0  # out of range
    assert history.fame("ZZZ", 1) == 0  # unknown player


def test_weeks_in_clan_requires_consecutive_presence():
    history = make_history()
    assert history.weeks_in_clan("AAA") == 3
    # BBB missed the most recent war, so presence isn't consecutive from war 1.
    assert history.weeks_in_clan("BBB") == 0
    assert history.is_new_member("BBB")
    assert not history.is_new_member("AAA")


def test_average_fame():
    history = make_history()
    assert history.average_fame("AAA") == (3000 + 2000 + 1000) / 3
    assert history.average_fame("BBB") == 0.0


def test_race_participants_and_former_members():
    race = {"clan": {"participants": [
        {"tag": "#AAA", "name": "name-AAA", "fame": 100, "decksUsed": 2},
        {"tag": "#LEFT99", "name": "Ghost", "fame": 50, "decksUsed": 1},
    ]}}
    members = [ClanMember("AAA", "name-AAA", "member")]

    participants = race_participants(race)
    assert participants["AAA"]["fame"] == 100
    assert former_member_tags(race, members) == {"LEFT99": "Ghost"}
    assert race_participants(None) == {}


def test_scoring_marks_new_members_unscorable():
    history = make_history()
    members = [ClanMember("AAA", "name-AAA", "member"), ClanMember("BBB", "name-BBB", "elder")]
    scores = score_members(members, history)

    by_tag = {s.tag: s for s in scores}
    assert by_tag["BBB"].total is None

    aaa = by_tag["AAA"]
    assert aaa.total is not None
    assert aaa.weeks == 3
    assert aaa.fame_score == (3000 + 2000 + 1000) / 3
    # Fame rises toward the present => positive trend => slope score above neutral 10.
    assert aaa.slope_score > 10
    assert aaa.total == aaa.fame_score + aaa.slope_score + aaa.weeks

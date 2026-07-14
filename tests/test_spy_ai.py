from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from cogs.misc import SpyDuelView, format_spy_report


def player_deck(card_name: str) -> list[dict]:
    return [{"name": card_name, "level": 14}]


def opponent_deck(win_rates, date="2024-12-07T21:26:52.000Z", cards=None):
    return {"deck": cards or [{"name": "Some Card", "level": 14}], "winRates": win_rates,
            "gameMode": "Clan War Duel", "date": date}


def make_interaction():
    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    return interaction


# ---- format_spy_report ----

def test_format_spy_report_no_data():
    assert "No data found" in format_spy_report(None)


def test_format_spy_report_separates_available_from_used_today_and_suggests_opener():
    today = datetime.now(UTC).strftime("%Y-%m-%dT12:00:00.000Z")
    war_data = {
        "playerDecks": [player_deck("A"), player_deck("B")],
        "opponentDecks": [
            opponent_deck([0.20, 0.80], date=today),  # used today (excluded)
            opponent_deck([0.10, 0.90], date="2024-12-01T12:00:00.000Z"),  # available
        ],
    }

    report = format_spy_report(war_data)

    assert "Opponent has 1 deck(s) available for their next duel** (1 already used today)" in report
    assert "Opponent Deck 1:" in report
    assert "Opponent Deck 2:" not in report  # only one deck is available
    assert "Already used today" in report
    assert "Suggested opening deck:** Your Deck 2" in report  # deck B (index 1) wins 0.90 to 0.10


# ---- SpyDuelView ----

async def make_view():
    player_decks = [player_deck("P0"), player_deck("P1"), player_deck("P2"), player_deck("P3")]
    available = [
        opponent_deck([0.10, 0.90, 0.50, 0.20]),  # original index 0
        opponent_deck([0.20, 0.10, 0.60, 0.70]),  # original index 1
        opponent_deck([0.30, 0.40, 0.05, 0.65]),  # original index 2
    ]
    return SpyDuelView(author_id=1, player_decks=player_decks, available_opponent_decks=available)


async def test_first_round_options_labeled_with_original_indices():
    view = await make_view()
    opponent_select, player_select = view.children
    assert [o.value for o in opponent_select.options] == ["0", "1", "2"]
    labels = [o.label.split(":")[0] for o in opponent_select.options]
    assert labels == ["Opponent Deck 1", "Opponent Deck 2", "Opponent Deck 3"]
    assert [o.value for o in player_select.options] == ["0", "1", "2", "3"]


async def test_round_recommends_and_renumbers_survivors_by_original_index():
    view = await make_view()
    interaction = make_interaction()

    # Opponent played their (positional) deck 1 -> original index 1; player played Your Deck 3 (index 2).
    view.opponent_choice = 1
    view.player_choice = 2
    await view.maybe_advance(interaction)

    content = interaction.response.edit_message.call_args.kwargs["content"]
    assert "Match 1 recorded" in content
    # Remaining opponent decks (original idx 0 and 2) vs remaining player decks (0, 1, 3):
    # idx0 avg=(0.10+0.30)/2=0.20, idx1 avg=(0.90+0.40)/2=0.65, idx3 avg=(0.20+0.65)/2=0.425 -> idx1 wins.
    assert "Suggested pick for Match 2:** Your Deck 2 (avg 65.0%" in content

    opponent_select, player_select = view.children
    labels = [o.label.split(":")[0] for o in opponent_select.options]
    assert labels == ["Opponent Deck 1", "Opponent Deck 3"]  # original indices preserved, not renumbered 1,2
    assert [o.value for o in player_select.options] == ["0", "1", "3"]


async def test_second_round_produces_final_recommendation_and_stops():
    view = await make_view()
    interaction = make_interaction()
    view.opponent_choice = 1
    view.player_choice = 2
    await view.maybe_advance(interaction)

    interaction2 = make_interaction()
    # Remaining opponent decks are positions [0, 1] -> original indices [0, 2]; pick position 0 (original idx 0).
    # Remaining player decks are [0, 1, 3]; pick index 0.
    view.opponent_choice = 0
    view.player_choice = 0
    await view.maybe_advance(interaction2)

    content = interaction2.response.edit_message.call_args.kwargs["content"]
    assert "Match 2 recorded" in content
    # Only original opponent idx 2 remains: winRates[1]=0.40, winRates[3]=0.65 among remaining player decks {1,3}.
    assert "Suggested pick for Match 3:** Your Deck 4 (avg 65.0% against their remaining 1 deck(s))" in content
    assert view.children == []  # no more rounds after match 3's recommendation
    assert view.is_finished()


async def test_incomplete_selection_only_defers():
    view = await make_view()
    interaction = make_interaction()
    view.opponent_choice = 0
    # player_choice not yet set
    await view.maybe_advance(interaction)

    interaction.response.defer.assert_awaited_once()
    interaction.response.edit_message.assert_not_called()

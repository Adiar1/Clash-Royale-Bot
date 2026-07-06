from cogs.reminders import format_reminder, local_label, war_day_sort_key, war_day_totals, war_day_utc_hours


def test_war_day_utc_hours():
    hours = war_day_utc_hours()
    assert hours[0] == 11  # first hour after the 10:00 UTC reset
    assert hours[-1] == 9  # last hour before the next reset
    assert 10 not in hours  # nobody wants a reminder the second the day starts
    assert len(hours) == 23


def test_war_day_sort_key_orders_by_war_day():
    times = ["05:00", "23:00", "11:00"]
    assert sorted(times, key=war_day_sort_key) == ["11:00", "23:00", "05:00"]


def test_local_label():
    # America/Phoenix has no DST, so 11:00 UTC is always 04:00 there.
    assert local_label("11:00", "America/Phoenix") == "04:00"
    assert local_label("09:00", "America/Phoenix") == "02:00"
    assert local_label("11:00", "UTC") == "11:00"


def test_war_day_totals():
    participants = {
        "AAA": {"decksUsedToday": 4},
        "BBB": {"decksUsedToday": 1},
        "CCC": {"decksUsedToday": 0},
    }
    assert war_day_totals(participants) == (195, 48)


def test_war_day_totals_empty_race():
    assert war_day_totals({}) == (200, 50)


def test_format_reminder():
    text = format_reminder("Highlanders", 50, 12, {
        4: ["DorfKnight", "<@712677591047340105>", "<@615847224768856074> (ŁoştŁęgęnd)"],
        1: ["<@1075798964483403786>", "XDEX"],
    })
    assert text.startswith("## __Reminder!__\n\nPlease finish your hits ASAP")
    assert "**Highlanders**" in text
    assert "Decks Remaining: **50**" in text
    assert "Slots Remaining: **12**" in text
    assert "**__4 Attacks__**" in text
    assert "**__1 Attack__**" in text  # singular for one attack left
    assert "**__3 Attacks__**" not in text  # empty groups are omitted
    assert "- <@615847224768856074> (ŁoştŁęgęnd)" in text
    assert text.index("**__4 Attacks__**") < text.index("**__1 Attack__**")

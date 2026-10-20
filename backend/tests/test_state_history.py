"""Tile history: half-hour bars and the share of time not bad, from tone periods."""

from datetime import UTC, datetime, timedelta

from app.models import StateTone
from app.state_history import summarize

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
GOOD, WARN, BAD, UNKNOWN = StateTone.GOOD, StateTone.WARN, StateTone.BAD, StateTone.UNKNOWN


def ago(**delta: float) -> datetime:
    return NOW - timedelta(**delta)


def test_nothing_checked() -> None:
    history = summarize([], NOW)
    assert history.bucket_seconds == 1800
    assert history.buckets == [None] * 48
    assert history.ok_percent is None


def test_a_bar_shows_the_worst_tone_checked_in_it() -> None:
    history = summarize(
        [
            (GOOD, ago(hours=30), ago(minutes=50)),  # Started before the window.
            (BAD, ago(minutes=50), ago(minutes=40)),
            (GOOD, ago(minutes=40), NOW),
        ],
        NOW,
    )
    assert history.buckets[:46] == [GOOD] * 46
    # 60 to 30 minutes ago held the red ten minutes; the last bar is green again.
    assert history.buckets[46:] == [BAD, GOOD]
    # 10 minutes of 24 hours.
    assert history.ok_percent == round(100 * (1 - 10 / (24 * 60)), 2)


def test_unchecked_time_and_unknown_are_left_out() -> None:
    history = summarize(
        [
            (GOOD, ago(hours=2), ago(hours=1)),
            (UNKNOWN, ago(hours=1), ago(minutes=30)),
            (WARN, ago(minutes=30), ago(minutes=20)),
            (BAD, ago(minutes=20), NOW),
        ],
        NOW,
    )
    assert history.buckets[:44] == [None] * 44
    # Green ends where the third bar starts; unknown and amber are outdone by red.
    assert history.buckets[44:] == [GOOD, GOOD, UNKNOWN, BAD]
    # Of 90 checked minutes (good 60, warn 10, bad 20), 70 were not bad.
    assert history.ok_percent == round(100 * 70 / 90, 2)


def test_an_unknown_bar_beats_green_but_not_amber() -> None:
    history = summarize(
        [(GOOD, ago(minutes=20), ago(minutes=10)), (UNKNOWN, ago(minutes=10), NOW)], NOW
    )
    assert history.buckets[-1] == UNKNOWN
    assert history.ok_percent == 100.0

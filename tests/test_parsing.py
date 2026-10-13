import pytest

from editor.media import MediaItem
from editor.plan import PlanError, validate, total_duration
from editor.rules import parse
from editor.timecode import TimecodeError, fmt, to_seconds


def lib():
    return [
        MediaItem("video1", "/x/trip.mp4", "video", "trip.mp4", 370.0, 1280, 720, True),
        MediaItem("video2", "/x/party.mov", "video", "party.mov", 20.0, 720, 1280, True),
        MediaItem("photo1", "/x/beach.jpg", "image", "beach.jpg", 0, 1024, 768, False),
    ]


@pytest.mark.parametrize("text,expected", [
    ("2:34", 154), ("05:50", 350), ("1:02:03", 3723), ("154", 154), ("12.5", 12.5),
    ("45s", 45), ("45 seconds", 45), ("2m34s", 154), ("2 min 34 sec", 154), (90, 90),
])
def test_to_seconds(text, expected):
    assert to_seconds(text) == expected


@pytest.mark.parametrize("bad", ["", "abc", "2:75", "-3", "1:2:3:4"])
def test_to_seconds_rejects(bad):
    with pytest.raises(TimecodeError):
        to_seconds(bad)


def test_fmt():
    assert fmt(154) == "2:34"
    assert fmt(3723) == "1:02:03"


def steps_of(prompt):
    raw, notes = parse(prompt, lib())
    return validate(raw, lib()), notes


def simple(steps):
    return [(s.type, s.source, s.start, s.end) for s in steps]


def test_example_with_names():
    steps, _ = steps_of(
        "From video1 take 2:34 to 2:55 and 5:12 to 5:50. "
        "Then put clip 1, the picture for 4 seconds, clip 2 and then video2."
    )
    assert simple(steps) == [
        ("clip", "video1", 154, 175),
        ("image", "photo1", 0, 4),
        ("clip", "video1", 312, 350),
        ("clip", "video2", 0, 20),
    ]
    assert total_duration(steps) == 21 + 4 + 38 + 20


def test_example_in_users_own_words():
    steps, _ = steps_of(
        "from one video i want two clips from 2:34 to 2:55 and 5:12 to 5:50, now combine "
        "the first clip then picture and second clip then and later the second video"
    )
    assert simple(steps) == [
        ("clip", "video1", 154, 175),
        ("image", "photo1", 0, 3),
        ("clip", "video1", 312, 350),
        ("clip", "video2", 0, 20),
    ]


def test_source_after_range_and_filenames():
    steps, _ = steps_of("take 0:05 to 0:10 from party.mov, then show beach.jpg for 2 seconds, then trip")
    assert simple(steps) == [
        ("clip", "video2", 5, 10),
        ("image", "photo1", 0, 2),
        ("clip", "video1", 0, 370),
    ]


def test_no_order_joins_clips_in_written_order():
    steps, _ = steps_of("cut video2 0:01 to 0:03 and 0:10-0:12")
    assert simple(steps) == [("clip", "video2", 1, 3), ("clip", "video2", 10, 12)]


def test_nothing_recognised_joins_everything():
    steps, notes = steps_of("make a video")
    assert [s.source for s in steps] == ["video1", "video2", "photo1"]
    assert notes


def test_range_past_end_is_reported():
    with pytest.raises(PlanError) as e:
        steps_of("from video2 take 0:10 to 0:45")
    assert "only 0:20 long" in str(e.value)


def test_end_before_start_is_reported():
    with pytest.raises(PlanError):
        validate([{"type": "clip", "source": "video1", "start": "3:00", "end": "2:00"}], lib())


def test_unknown_clip_reference():
    with pytest.raises(ValueError):
        parse("from video1 take 0:01 to 0:02 then clip 3", lib())


def test_llm_style_plan_validates():
    raw = [
        {"type": "clip", "source": "Video 1", "start": "2:34", "end": "2:55"},
        {"type": "image", "source": "photo1", "duration": "4"},
        {"type": "clip", "source": "video2", "start": "start", "end": "end"},
    ]
    assert simple(validate(raw, lib())) == [
        ("clip", "video1", 154, 175), ("image", "photo1", 0, 4), ("clip", "video2", 0, 20)]

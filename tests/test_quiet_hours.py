from app.quiet_hours import in_quiet_hours_hour


def test_quiet_hours_overnight_23_to_7() -> None:
    assert in_quiet_hours_hour(23, 23, 7) is True
    assert in_quiet_hours_hour(0, 23, 7) is True
    assert in_quiet_hours_hour(6, 23, 7) is True
    assert in_quiet_hours_hour(7, 23, 7) is False
    assert in_quiet_hours_hour(22, 23, 7) is False


def test_quiet_hours_same_day_window() -> None:
    assert in_quiet_hours_hour(9, 9, 17) is True
    assert in_quiet_hours_hour(16, 9, 17) is True
    assert in_quiet_hours_hour(8, 9, 17) is False
    assert in_quiet_hours_hour(17, 9, 17) is False


def test_quiet_hours_equal_start_end_disabled() -> None:
    assert in_quiet_hours_hour(12, 8, 8) is False

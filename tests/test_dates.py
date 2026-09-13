from datetime import date

from tara.core.dates import add_years, derive_backward_deadline, next_recurrence


def test_add_years_basic():
    assert add_years(date(2019, 3, 14), 8) == date(2027, 3, 14)


def test_add_years_leap_day_falls_back():
    assert add_years(date(2020, 2, 29), 1) == date(2021, 2, 28)


def test_add_years_never_off_by_one_like_a_model_might_be():
    # The architecture doc's own example of the failure mode this module
    # exists to prevent: 2019 + 8 must be 2027, never 2026.
    assert add_years(date(2019, 3, 14), 8) != date(2026, 3, 14)


def test_next_recurrence_before_first_anniversary():
    anchor = date(2023, 1, 10)
    assert next_recurrence(anchor, 8, on_or_after=date(2026, 9, 6)) == date(2031, 1, 10)


def test_next_recurrence_acceptance_criterion():
    # PLOT must return 2027-03-14 for a 2019-03-14 acquisition, as of a
    # run date before that anniversary.
    anchor = date(2019, 3, 14)
    assert next_recurrence(anchor, 8, on_or_after=date(2026, 9, 6)) == date(2027, 3, 14)


def test_derive_backward_deadline():
    assert derive_backward_deadline(date(2027, 3, 14), 30) == date(2027, 2, 12)


def test_derive_backward_deadline_rejects_negative_lead_time():
    import pytest
    with pytest.raises(ValueError):
        derive_backward_deadline(date(2027, 3, 14), -1)

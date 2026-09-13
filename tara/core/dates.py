"""Deterministic date arithmetic.

Non-negotiable per the architecture: dates, diffs and threshold comparisons
are never computed by a model. Every date returned anywhere in TARA is
produced by a function in this module, tested, and traceable back to here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


def parse_iso_date(value: str) -> date:
    """Parse a YYYY-MM-DD string. Raises ValueError on anything else."""
    return date.fromisoformat(value)


def add_years(anchor: date, years: int) -> date:
    """Add a whole number of years to a date, handling Feb 29 correctly.

    This is the function behind the deemed-disposal date trigger. It must
    never be approximated as ``anchor + years * 365`` — that drifts by a full
    day roughly every four years and would silently mis-date an eight-year
    anniversary.
    """
    try:
        return anchor.replace(year=anchor.year + years)
    except ValueError:
        # anchor was Feb 29 and the target year isn't a leap year.
        return anchor.replace(year=anchor.year + years, month=2, day=28)


def next_recurrence(anchor: date, interval_years: int, on_or_after: date) -> date:
    """The next date of form ``anchor + n*interval_years`` that falls on or
    after ``on_or_after``. Used for recurring date triggers such as the
    8-year deemed disposal, which fires again on every subsequent
    anniversary for as long as the holding continues.
    """
    if interval_years <= 0:
        raise ValueError("interval_years must be positive")
    candidate = anchor
    n = 0
    while candidate < on_or_after:
        n += 1
        candidate = add_years(anchor, interval_years * n)
    return candidate


def resolve_recurrence(anchor: date, interval_years: int, as_of: date) -> tuple[date, bool]:
    """Resolves a recurring trigger (such as the 8-year deemed disposal) to
    a single operative date as of ``as_of``, plus whether that date is
    already due (on or before ``as_of``) or still upcoming.

    If the most recent anniversary has already passed, that anniversary is
    the operative, due date — this is the instance that needs evidence.
    If no anniversary has occurred yet, the first future one is returned
    as an informational date, not yet due.
    """
    if interval_years <= 0:
        raise ValueError("interval_years must be positive")

    n = 1
    last_due: date | None = None
    while True:
        candidate = add_years(anchor, interval_years * n)
        if candidate > as_of:
            if last_due is not None:
                return last_due, True
            return candidate, False
        last_due = candidate
        n += 1


def days_between(start: date, end: date) -> int:
    return (end - start).days


def derive_backward_deadline(statutory_date: date, lead_time_days: int) -> date:
    """Derive an action deadline backward from a statutory date.

    COURSE never assigns deadlines arbitrarily — every deadline is the
    statutory date minus a stated lead time, so the reasoning is inspectable.
    """
    if lead_time_days < 0:
        raise ValueError("lead_time_days must not be negative")
    return statutory_date - timedelta(days=lead_time_days)


def is_within_window(reference: date, window_start: date, window_end: date) -> bool:
    return window_start <= reference <= window_end


@dataclass(frozen=True)
class VerificationStatus:
    source_id: str
    last_verified: date
    max_age_days: int
    as_of: date

    @property
    def age_days(self) -> int:
        return days_between(self.last_verified, self.as_of)

    @property
    def stale(self) -> bool:
        return self.age_days > self.max_age_days

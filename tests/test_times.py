# flepimop2-epiworldr: A flepimop2 external provider for epiworldR
# Copyright (C) 2026  George G. Vega Yon
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""Tests for mapping flepimop2 evaluation times onto epiworldR days."""

import numpy as np
import pytest

from flepimop2_epiworldr._times import TIME_ATOL, plan_days


def test_contiguous_times() -> None:
    """The common case: every day from zero."""
    assert plan_days(np.arange(0.0, 6.0)) == (5, [0, 1, 2, 3, 4, 5])


def test_sparse_times_still_simulate_to_the_maximum() -> None:
    """EpiworldR must run the full span even when few days are reported."""
    assert plan_days(np.array([0.0, 5.0, 20.0])) == (20, [0, 5, 20])


def test_unsorted_and_duplicate_times_are_preserved() -> None:
    """
    Caller order is the contract.

    The engine echoes the caller's times back in column 0, matching flepimop2's
    other engines, so normalizing here would silently reorder their output.
    """
    assert plan_days(np.array([10.0, 0.0, 10.0])) == (10, [10, 0, 10])


def test_arange_drift_is_tolerated() -> None:
    """
    flepimop2 builds times with np.arange, which accumulates error.

    A value a hair off a whole day is floating-point noise, not a mistake.
    """
    times = np.array([0.0, 1.0 - TIME_ATOL / 2.0, 2.0 + TIME_ATOL / 2.0])
    assert plan_days(times) == (2, [0, 1, 2])


def test_empty_times_rejected() -> None:
    """An empty times array means the simulate block is misconfigured."""
    with pytest.raises(ValueError, match="at least one evaluation time"):
        plan_days(np.array([]))


def test_negative_times_rejected() -> None:
    """EpiworldR history starts at day 0."""
    with pytest.raises(ValueError, match="non-negative"):
        plan_days(np.array([0.0, -1.0]))


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_times_rejected(bad: float) -> None:
    """A non-finite time cannot index a day."""
    with pytest.raises(ValueError, match="finite"):
        plan_days(np.array([0.0, bad]))


def test_fractional_times_rejected() -> None:
    """EpiworldR advances a whole day per step, so half days cannot exist."""
    with pytest.raises(ValueError, match="whole-day"):
        plan_days(np.array([0.0, 0.5, 1.0]))


def test_fractional_time_error_names_the_offender() -> None:
    """The message must say which value and index to fix."""
    with pytest.raises(ValueError, match=r"t=2\.5 at index 2"):
        plan_days(np.array([0.0, 1.0, 2.5]))

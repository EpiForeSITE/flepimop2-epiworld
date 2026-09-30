# flepimop2-epiworld: A flepimop2 external provider for epiworld
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
"""
Regression tests for the epiworld initial-state mapping.

These are the guard against silently wrong initial conditions. They check the
pure arithmetic; `test_run_model.py` checks the same targets against a real
epiworld run.
"""

import pytest

from flepimop2_epiworld._initial_state import (
    SeirCounts,
    SeirSeeding,
    epiworld_realize,
    epiworld_realized_seir_counts,
    nudged_fraction,
    seir_seeding_arguments,
)


def _naive_seeding(counts: SeirCounts) -> SeirSeeding:
    """
    Build seeding arguments the obvious, wrong way: bare ratios.

    Args:
        counts: The target compartment counts.

    Returns:
        Seeding arguments without the half-unit nudge.
    """
    n = sum(counts)
    seeded = counts.exposed + counts.infected
    non_seeded = counts.susceptible + counts.recovered
    return SeirSeeding(
        n=n,
        prevalence=seeded / n,
        proportions=(
            counts.infected / seeded if seeded else 0.0,
            counts.recovered / non_seeded if non_seeded else 0.0,
        ),
    )


# Cases where the bare ratio `k / total` truncates one short, verified against
# epiworldR 0.15.1. These exist because epiworld stores prevalence as C float
# and truncates both the seeding and the initial_states conversions.
NAIVE_FORMULA_FAILURES = [
    SeirCounts(7112, 11, 1116, 1761),
    SeirCounts(40318, 4484, 2459, 76196),
    SeirCounts(748301, 942, 3970, 246770),
]

REPRESENTATIVE_CASES = [
    SeirCounts(999, 0, 1, 0),
    SeirCounts(800, 120, 60, 20),
    SeirCounts(777, 33, 17, 173),
    SeirCounts(9990, 0, 10, 0),
    SeirCounts(333, 111, 7, 49),
    SeirCounts(1000, 0, 0, 0),
    SeirCounts(1, 0, 0, 0),
    SeirCounts(0, 0, 1, 0),
    SeirCounts(0, 0, 0, 1),
    SeirCounts(0, 5, 0, 0),
]


@pytest.mark.parametrize("counts", REPRESENTATIVE_CASES + NAIVE_FORMULA_FAILURES)
def test_seeding_round_trips_exactly(counts: SeirCounts) -> None:
    """Epiworld's own arithmetic must land back on the configured counts."""
    assert epiworld_realized_seir_counts(counts) == counts


@pytest.mark.parametrize("counts", NAIVE_FORMULA_FAILURES)
def test_naive_ratio_would_have_drifted(counts: SeirCounts) -> None:
    """
    Pin the defect these cases exist for.

    Bare ratios lose an agent to truncation. If this ever stops failing,
    epiworld's arithmetic changed and the nudge should be re-derived rather
    than left in place on faith.
    """
    assert epiworld_realize(_naive_seeding(counts)) != counts


def test_nudged_fraction_degenerate_denominators() -> None:
    """Empty and saturated populations must not divide by zero."""
    assert nudged_fraction(0, 0) == 0.0
    assert nudged_fraction(7, 0) == 0.0
    assert nudged_fraction(5, 5) == 1.0
    assert nudged_fraction(9, 5) == 1.0


def test_seeding_rejects_negative_counts() -> None:
    """A negative compartment is a configuration error, not something to clamp."""
    with pytest.raises(ValueError, match="non-negative"):
        seir_seeding_arguments(SeirCounts(-1, 0, 1, 0))


def test_seeding_rejects_empty_population() -> None:
    """Epiworld cannot build a model with no agents."""
    with pytest.raises(ValueError, match="at least one agent"):
        seir_seeding_arguments(SeirCounts(0, 0, 0, 0))

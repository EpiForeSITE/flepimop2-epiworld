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
Translate flepimop2 compartment counts into epiworld seeding arguments.

epiworld does not accept absolute initial compartment counts. A `Model*CONN`
model is seeded with a population size `n`, a `prevalence` *proportion*, and an
`initial_states()` vector of *proportions*. Recovering exact counts from those
requires care, because epiworld truncates at two separate points:

- `virus-distribute-meat.hpp` computes the seeded population as
  `floor(prevalence * n)` in `epiworld_double`, which `config.hpp` defines as
  C `float` -- only 24 bits of mantissa.
- `init-functions.hpp` converts `proportions[i] * ... * n` to `size_t`, which
  truncates toward zero.

Passing the bare ratio `k / total` therefore lands one below the intended
integer whenever the product falls microscopically short, which a fuzz test
against epiworldR 0.15.1 hit in roughly a third of random draws. Adding half a
unit before dividing moves the product safely inside the target integer's
interval without ever reaching the next one, making truncation exact.
"""

__all__ = [
    "SeirCounts",
    "SeirSeeding",
    "epiworld_realize",
    "epiworld_realized_seir_counts",
    "nudged_fraction",
    "seir_seeding_arguments",
]

from typing import NamedTuple

import numpy as np


class SeirCounts(NamedTuple):
    """
    Compartment counts for an SEIR-family model.

    Attributes:
        susceptible: Agents in `Susceptible`.
        exposed: Agents in `Exposed`.
        infected: Agents in `Infected`.
        recovered: Agents in `Recovered`.
    """

    susceptible: int
    exposed: int
    infected: int
    recovered: int


class SeirSeeding(NamedTuple):
    """
    epiworld seeding arguments derived from target compartment counts.

    Attributes:
        n: Population size passed to the model constructor.
        prevalence: Proportion passed to the model constructor.
        proportions: The vector passed to `initial_states()`.
    """

    n: int
    prevalence: float
    proportions: tuple[float, float]


def nudged_fraction(numerator: int, denominator: int) -> float:
    """
    Build a fraction that survives epiworld's truncation to `numerator`.

    Args:
        numerator: The count we want epiworld to arrive back at.
        denominator: The population the fraction is taken out of.

    Returns:
        A fraction `f` such that truncating `f * denominator` yields
        `numerator` exactly.

    Examples:
        >>> from flepimop2_epiworld._initial_state import nudged_fraction
        >>> nudged_fraction(1, 1000)
        0.0015
        >>> int(nudged_fraction(1, 1000) * 1000)
        1

        Truncation still lands on the target for awkward denominators:

        >>> int(nudged_fraction(2459, 6943) * 6943)
        2459
        >>> int(nudged_fraction(942, 999983) * 999983)
        942

        Degenerate denominators collapse to zero, and a full numerator to one:

        >>> nudged_fraction(0, 0)
        0.0
        >>> nudged_fraction(5, 5)
        1.0
    """
    if denominator <= 0:
        return 0.0
    if numerator >= denominator:
        return 1.0
    return (numerator + 0.5) / denominator


def seir_seeding_arguments(counts: SeirCounts) -> SeirSeeding:
    """
    Derive `n`, `prevalence`, and `initial_states()` proportions from counts.

    epiworld's `create_init_function_seir` reads the proportions vector as:

    - `proportions[0]`: the share of *seeded* agents promoted from `Exposed`
      to `Infected`. Note this is the reverse of what the argument name
      suggests -- the C++ samples from state 1 and writes state 2.
    - `proportions[1]`: the share of *non-seeded* agents moved from
      `Susceptible` to `Recovered`.

    Args:
        counts: The target initial compartment counts.

    Returns:
        The constructor and `initial_states()` arguments reproducing `counts`.

    Raises:
        ValueError: If any count is negative or the population is empty.

    Examples:
        >>> from flepimop2_epiworld._initial_state import (
        ...     SeirCounts,
        ...     seir_seeding_arguments,
        ... )
        >>> seeding = seir_seeding_arguments(SeirCounts(999, 0, 1, 0))
        >>> seeding.n
        1000
        >>> seeding.prevalence
        0.0015
        >>> seeding.proportions
        (1.0, 0.0005005005005005005)

        That second value is deliberately not zero: it truncates to zero
        recovered agents while staying safely inside the target interval.

        >>> int(seeding.proportions[1] * 999)
        0
    """
    if any(count < 0 for count in counts):
        msg = f"epiworld initial compartment counts must be non-negative; got {counts}."
        raise ValueError(msg)
    n = sum(counts)
    if n < 1:
        msg = (
            "epiworld needs at least one agent, but the initial compartment "
            f"counts sum to {n}."
        )
        raise ValueError(msg)
    seeded = counts.exposed + counts.infected
    return SeirSeeding(
        n=n,
        prevalence=nudged_fraction(seeded, n),
        proportions=(
            nudged_fraction(counts.infected, seeded),
            nudged_fraction(counts.recovered, counts.susceptible + counts.recovered),
        ),
    )


def epiworld_realize(seeding: SeirSeeding) -> SeirCounts:
    """
    Predict the day-0 counts epiworld produces for given seeding arguments.

    This mirrors epiworld's own arithmetic, including the `float` precision of
    the prevalence step and the truncation of both steps, so the mapping can be
    regression-tested without running a simulation.

    Args:
        seeding: The constructor and `initial_states()` arguments.

    Returns:
        The compartment counts epiworld will report at day 0.

    Examples:
        Nudged fractions land exactly on the target:

        >>> from flepimop2_epiworld._initial_state import (
        ...     SeirCounts,
        ...     epiworld_realize,
        ...     seir_seeding_arguments,
        ... )
        >>> target = SeirCounts(7112, 11, 1116, 1761)
        >>> epiworld_realize(seir_seeding_arguments(target)) == target
        True

        Bare ratios do not, which is the whole reason for the nudge:

        >>> from flepimop2_epiworld._initial_state import SeirSeeding
        >>> naive = SeirSeeding(
        ...     n=10000,
        ...     prevalence=1127 / 10000,
        ...     proportions=(1116 / 1127, 1761 / 8873),
        ... )
        >>> epiworld_realize(naive)
        SeirCounts(susceptible=7113, exposed=11, infected=1116, recovered=1760)
    """
    n = seeding.n

    # `Virus::distribute` seeds floor(prevalence * n) agents in float32.
    seeded = int(
        np.floor(np.float32(seeding.prevalence) * np.float32(n), dtype=np.float32)
    )
    seeded = min(seeded, n)

    # `create_init_function_seir` then works in double, but truncates to size_t.
    share_seeded = seeded / n
    infected = int(seeding.proportions[0] * share_seeded * n)
    recovered = int(seeding.proportions[1] * (1.0 - share_seeded) * n)

    return SeirCounts(
        susceptible=n - seeded - recovered,
        exposed=seeded - infected,
        infected=infected,
        recovered=recovered,
    )


def epiworld_realized_seir_counts(counts: SeirCounts) -> SeirCounts:
    """
    Predict the day-0 counts epiworld will actually produce for target counts.

    Args:
        counts: The target initial compartment counts.

    Returns:
        The compartment counts epiworld will report at day 0.

    Examples:
        >>> from flepimop2_epiworld._initial_state import (
        ...     SeirCounts,
        ...     epiworld_realized_seir_counts,
        ... )
        >>> target = SeirCounts(7112, 11, 1116, 1761)
        >>> epiworld_realized_seir_counts(target) == target
        True
    """
    return epiworld_realize(seir_seeding_arguments(counts))

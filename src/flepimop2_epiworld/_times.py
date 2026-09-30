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
"""Map flepimop2 evaluation times onto epiworld's integer day grid."""

__all__ = ["TIME_ATOL", "plan_days"]

from typing import Final

import numpy as np
from flepimop2.typing import Float64NDArray

TIME_ATOL: Final = 1e-9
"""
Tolerance for accepting a float time as a whole day.

flepimop2 builds `times` with `np.arange`, which accumulates representation
error, so an exact integer comparison would reject perfectly reasonable
configurations. Anything further off than this is a genuine mistake rather than
floating-point noise.
"""


def plan_days(times: Float64NDArray) -> tuple[int, list[int]]:
    """
    Resolve evaluation times into an epiworld run length and day indices.

    epiworld advances exactly one day per step and reports history on the
    integer grid `0..ndays`, so every requested time must land on a whole day.

    Order and duplicates are deliberately preserved rather than normalized: the
    engine echoes the caller's own `times` back in column 0, matching how
    flepimop2's other engines behave.

    Args:
        times: Evaluation times from the simulate configuration.

    Returns:
        The number of days to simulate, and the requested days in caller order.

    Raises:
        ValueError: If `times` is empty, or contains a non-finite, negative, or
            non-whole-day value.

    Examples:
        >>> import numpy as np
        >>> from flepimop2_epiworld._times import plan_days
        >>> plan_days(np.array([0.0, 1.0, 2.0]))
        (2, [0, 1, 2])

        Sparse and unsorted requests are fine; `ndays` covers the largest:

        >>> plan_days(np.array([0.0, 5.0, 10.0, 20.0]))
        (20, [0, 5, 10, 20])
        >>> plan_days(np.array([10.0, 0.0]))
        (10, [10, 0])

        Fractional days are rejected, because epiworld cannot produce them:

        >>> plan_days(np.array([0.0, 0.5]))
        Traceback (most recent call last):
            ...
        ValueError: The epiworld engine requires whole-day evaluation times ...
    """
    if times.size == 0:
        msg = (
            "The epiworld engine requires at least one evaluation time, but "
            "`simulate.<target>.times` produced an empty array."
        )
        raise ValueError(msg)

    finite = np.isfinite(times)
    if not bool(np.all(finite)):
        index = int(np.argmin(finite))
        msg = (
            "The epiworld engine requires finite evaluation times; got "
            f"t={times[index]} at index {index}."
        )
        raise ValueError(msg)

    if bool(np.any(times < 0.0)):
        index = int(np.argmax(times < 0.0))
        msg = (
            "The epiworld engine requires non-negative evaluation times "
            f"because epiworld starts at day 0; got t={times[index]} at index "
            f"{index}."
        )
        raise ValueError(msg)

    rounded = np.round(times)
    off_grid = np.abs(times - rounded) > TIME_ATOL
    if bool(np.any(off_grid)):
        index = int(np.argmax(off_grid))
        msg = (
            "The epiworld engine requires whole-day evaluation times because "
            f"epiworld advances one day per step; got t={times[index]} at "
            f"index {index}. Use whole-day steps such as times: '0:1:150'."
        )
        raise ValueError(msg)

    days = [int(day) for day in rounded]
    return max(days), days

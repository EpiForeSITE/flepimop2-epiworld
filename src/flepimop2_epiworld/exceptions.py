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
"""Exceptions raised by the epiworld bridge."""

__all__ = ["EpiworldError", "EpiworldUnavailableError"]


class EpiworldError(RuntimeError):
    """
    Raised when an epiworld run fails.

    Carries enough context to reproduce the failure by hand: the model, the
    population size, the run length, and the seed.

    Examples:
        >>> from flepimop2_epiworld.exceptions import EpiworldError
        >>> raise EpiworldError("boom")
        Traceback (most recent call last):
            ...
        flepimop2_epiworld.exceptions.EpiworldError: boom
    """


class EpiworldUnavailableError(EpiworldError):
    """
    Raised when epiworldpy is missing or lacks a feature this provider needs.

    Distinct from `EpiworldError` so callers can tell "your environment is not
    set up" apart from "the model run failed".

    Examples:
        >>> from flepimop2_epiworld.exceptions import (
        ...     EpiworldError,
        ...     EpiworldUnavailableError,
        ... )
        >>> issubclass(EpiworldUnavailableError, EpiworldError)
        True
    """

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
"""Exceptions raised by the epiworldR bridge."""

__all__ = ["EpiworldrError", "EpiworldrUnavailableError"]


class EpiworldrError(RuntimeError):
    """
    Raised when an epiworldR run fails.

    Carries enough context to reproduce the failure by hand: the exit status,
    what the R driver wrote to stderr, and a truncated echo of the request that
    produced it.

    Examples:
        >>> from flepimop2_epiworldr.exceptions import EpiworldrError
        >>> raise EpiworldrError("boom")
        Traceback (most recent call last):
            ...
        flepimop2_epiworldr.exceptions.EpiworldrError: boom
    """


class EpiworldrUnavailableError(EpiworldrError):
    """
    Raised when R or the epiworldR package cannot be located.

    Distinct from `EpiworldrError` so callers can tell "your environment is not
    set up" apart from "the model run failed".

    Examples:
        >>> from flepimop2_epiworldr.exceptions import (
        ...     EpiworldrError,
        ...     EpiworldrUnavailableError,
        ... )
        >>> issubclass(EpiworldrUnavailableError, EpiworldrError)
        True
    """

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
"""Structural contract between the epiworldR system and engine modules."""

__all__ = ["SupportsEpiworldrRun"]

from typing import Protocol, runtime_checkable

from flepimop2_epiworldr._models import EpiworldrModelSpec


@runtime_checkable
class SupportsEpiworldrRun(Protocol):
    """
    What `EpiworldrEngine` needs from a system in order to drive it.

    Declared structurally rather than as a base class so the engine module does
    not import the system module, and so a third party can supply their own
    epiworldR-backed system without subclassing ours.

    Examples:
        >>> from flepimop2_epiworldr._contract import SupportsEpiworldrRun
        >>> class NotASystem:
        ...     pass
        >>> isinstance(NotASystem(), SupportsEpiworldrRun)
        False
    """

    def epiworldr_spec(self) -> EpiworldrModelSpec:
        """
        Describe the epiworldR model this system represents.

        Returns:
            The registry entry for the configured model.
        """
        ...

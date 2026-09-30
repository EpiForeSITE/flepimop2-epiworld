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
"""Structural contract between the epiworld system and engine modules."""

__all__ = ["SupportsEpiworldRun"]

from typing import Protocol, runtime_checkable

from flepimop2_epiworld._models import EpiworldModelSpec


@runtime_checkable
class SupportsEpiworldRun(Protocol):
    """
    What `EpiworldEngine` needs from a system in order to drive it.

    Declared structurally rather than as a base class so the engine module does
    not import the system module, and so a third party can supply their own
    epiworld-backed system without subclassing ours.

    Examples:
        >>> from flepimop2_epiworld._contract import SupportsEpiworldRun
        >>> class NotASystem:
        ...     pass
        >>> isinstance(NotASystem(), SupportsEpiworldRun)
        False
    """

    def epiworld_spec(self) -> EpiworldModelSpec:
        """
        Describe the epiworld model this system represents.

        Returns:
            The registry entry for the configured model.
        """
        ...

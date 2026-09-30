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
Shared bridge code for the flepimop2 epiworld provider.

The flepimop2-facing module classes live in the `flepimop2.system.epiworld`
and `flepimop2.engine.epiworld` namespace packages. This package holds the
implementation they share: the model registry, the initial-state mapping, the
time mapping, and the epiworldpy runner itself.
"""

__all__ = [
    "MODEL_SPECS",
    "EpiworldError",
    "EpiworldModelKey",
    "EpiworldModelSpec",
    "EpiworldUnavailableError",
    "SeirCounts",
]

from flepimop2_epiworld._initial_state import SeirCounts
from flepimop2_epiworld._models import (
    MODEL_SPECS,
    EpiworldModelKey,
    EpiworldModelSpec,
)
from flepimop2_epiworld.exceptions import EpiworldError, EpiworldUnavailableError

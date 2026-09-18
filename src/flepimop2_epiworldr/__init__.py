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
"""
Shared bridge code for the flepimop2 epiworldR provider.

The flepimop2-facing module classes live in the `flepimop2.system.epiworldr`
and `flepimop2.engine.epiworldr` namespace packages. This package holds the
implementation they share: the model registry, the initial-state mapping, the
time mapping, and the `Rscript` bridge itself.
"""

__all__ = [
    "MODEL_SPECS",
    "EpiworldrError",
    "EpiworldrModelKey",
    "EpiworldrModelSpec",
    "EpiworldrUnavailableError",
    "SeirCounts",
]

from flepimop2_epiworldr._initial_state import SeirCounts
from flepimop2_epiworldr._models import (
    MODEL_SPECS,
    EpiworldrModelKey,
    EpiworldrModelSpec,
)
from flepimop2_epiworldr.exceptions import EpiworldrError, EpiworldrUnavailableError

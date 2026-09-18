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
"""Shared fixtures and R-availability gating for the test suite."""

import functools
import shutil
import subprocess

import pytest

_PROBE_TIMEOUT = 120.0


@functools.lru_cache(maxsize=1)
def has_epiworldr() -> bool:
    """
    Report whether an Rscript with epiworldR installed is reachable.

    Returns:
        True when the R side of the bridge can actually run.
    """
    rscript = shutil.which("Rscript")
    if rscript is None:
        return False
    probe = "quit(status = if (requireNamespace('epiworldR', quietly = TRUE)) 0 else 1)"
    proc = subprocess.run(
        [rscript, "--vanilla", "-e", probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=_PROBE_TIMEOUT,
    )
    return proc.returncode == 0


requires_epiworldr = pytest.mark.skipif(
    not has_epiworldr(),
    reason="needs Rscript with the epiworldR package installed",
)

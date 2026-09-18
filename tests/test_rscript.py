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
"""Tests for locating Rscript, without requiring a real R installation."""

import os
from pathlib import Path

import pytest

from flepimop2_epiworldr._rscript import (
    RSCRIPT_ENV_VAR,
    resolve_rscript,
    subprocess_env,
)
from flepimop2_epiworldr.exceptions import EpiworldrUnavailableError


@pytest.fixture
def _clear_discovery_cache() -> None:
    """Discovery is cached per process, so isolate each test from the last."""
    resolve_rscript.cache_clear()


pytestmark = pytest.mark.usefixtures("_clear_discovery_cache")


def _fake_rscript(directory: Path, name: str = "Rscript") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_explicit_path_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An engine's `rscript:` option must override everything else."""
    explicit = _fake_rscript(tmp_path / "explicit", "Rscript")
    monkeypatch.setenv(RSCRIPT_ENV_VAR, str(_fake_rscript(tmp_path / "env")))
    assert resolve_rscript(explicit) == explicit.resolve()


def test_explicit_missing_path_is_an_error(tmp_path: Path) -> None:
    """A configured path that does not exist is a mistake worth reporting."""
    with pytest.raises(EpiworldrUnavailableError, match="does not exist"):
        resolve_rscript(tmp_path / "nope" / "Rscript")


def test_environment_variable_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The env var lets CI point at an R that is not on PATH."""
    target = _fake_rscript(tmp_path)
    monkeypatch.setenv(RSCRIPT_ENV_VAR, str(target))
    assert resolve_rscript() == target.resolve()


def test_r_home_is_consulted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R sets R_HOME, so honor it before falling back to PATH."""
    target = _fake_rscript(tmp_path / "bin")
    monkeypatch.delenv(RSCRIPT_ENV_VAR, raising=False)
    monkeypatch.setenv("R_HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "")
    assert resolve_rscript() == target.resolve()


def test_path_is_the_last_resort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordinary case: Rscript is simply on PATH."""
    target = _fake_rscript(tmp_path)
    monkeypatch.delenv(RSCRIPT_ENV_VAR, raising=False)
    monkeypatch.delenv("R_HOME", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert resolve_rscript() == target.resolve()


def test_missing_r_explains_how_to_fix_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The error must name both escape hatches, not just say 'not found'."""
    monkeypatch.delenv(RSCRIPT_ENV_VAR, raising=False)
    monkeypatch.delenv("R_HOME", raising=False)
    monkeypatch.setenv("PATH", "")
    with pytest.raises(EpiworldrUnavailableError) as excinfo:
        resolve_rscript()
    message = str(excinfo.value)
    assert "rscript:" in message
    assert RSCRIPT_ENV_VAR in message


def test_r_libs_is_prepended(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    `--vanilla` drops ~/.Renviron, so R_LIBS is how a user library is reached.

    An existing R_LIBS must be kept, after ours, rather than clobbered.
    """
    monkeypatch.setenv("R_LIBS", "/existing")
    env = subprocess_env((Path("/opt/R/library"),))
    assert env["R_LIBS"] == os.pathsep.join(["/opt/R/library", "/existing"])


def test_r_libs_absent_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the option we must not invent an R_LIBS and shadow the default."""
    monkeypatch.delenv("R_LIBS", raising=False)
    assert "R_LIBS" not in subprocess_env()

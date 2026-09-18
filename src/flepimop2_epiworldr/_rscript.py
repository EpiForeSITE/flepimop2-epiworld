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
"""Locate `Rscript` and confirm the R side of the bridge is usable."""

__all__ = [
    "MIN_EPIWORLDR_VERSION",
    "epiworldr_version",
    "resolve_rscript",
    "subprocess_env",
]

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Final

from flepimop2_epiworldr.exceptions import EpiworldrUnavailableError

MIN_EPIWORLDR_VERSION: Final = (0, 15, 1)
"""Oldest epiworldR whose state names and seeding semantics this driver assumes."""

RSCRIPT_ENV_VAR: Final = "FLEPIMOP2_EPIWORLDR_RSCRIPT"
"""Environment variable overriding `Rscript` discovery."""

_PROBE_TIMEOUT: Final = 120.0


@lru_cache(maxsize=8)
def resolve_rscript(explicit: Path | None = None) -> Path:
    """
    Find the `Rscript` executable to drive epiworldR with.

    Resolution order: an explicitly configured path, then the
    `FLEPIMOP2_EPIWORLDR_RSCRIPT` environment variable, then `$R_HOME/bin`,
    then `PATH`.

    Args:
        explicit: A path configured on the engine, if any.

    Returns:
        The resolved path to `Rscript`.

    Raises:
        EpiworldrUnavailableError: If no usable `Rscript` can be found, or if
            the explicitly configured one does not exist.
    """
    if explicit is not None:
        candidate = Path(explicit).expanduser()
        if not candidate.is_file():
            msg = f"The engine's configured `rscript` path does not exist: {candidate}."
            raise EpiworldrUnavailableError(msg)
        return candidate.resolve()

    if (from_env := os.environ.get(RSCRIPT_ENV_VAR)) and Path(from_env).is_file():
        return Path(from_env).resolve()

    if (r_home := os.environ.get("R_HOME")) and (
        candidate := Path(r_home) / "bin" / "Rscript"
    ).is_file():
        return candidate.resolve()

    if found := shutil.which("Rscript"):
        return Path(found).resolve()

    msg = (
        "Could not find `Rscript`. The epiworldr engine runs epiworldR in an R "
        "subprocess, so R must be installed. Install R from "
        "https://cran.r-project.org, or set the engine's `rscript:` option or "
        f"the {RSCRIPT_ENV_VAR} environment variable to its path."
    )
    raise EpiworldrUnavailableError(msg)


def subprocess_env(r_libs: tuple[Path, ...] = ()) -> dict[str, str]:
    """
    Build the environment for an `Rscript --vanilla` call.

    `--vanilla` implies `--no-environ`, which discards `~/.Renviron` and with it
    any `R_LIBS_USER` that a CRAN-style install relies on. `R_LIBS` passed
    through the process environment is still honored, so that is how an
    out-of-tree library is reached.

    Args:
        r_libs: Extra R library directories to prepend.

    Returns:
        The environment mapping to pass to `subprocess.run`.
    """
    env = dict(os.environ)
    if r_libs:
        existing = env.get("R_LIBS")
        entries = [str(Path(path).expanduser()) for path in r_libs]
        if existing:
            entries.append(existing)
        env["R_LIBS"] = os.pathsep.join(entries)
    return env


@lru_cache(maxsize=8)
def epiworldr_version(
    explicit: Path | None = None, r_libs: tuple[Path, ...] = ()
) -> tuple[int, ...]:
    """
    Report the installed epiworldR version.

    Cached, because this costs a full R startup (~0.4s) and the answer cannot
    change within a process.

    Args:
        explicit: A path configured on the engine, if any.
        r_libs: Extra R library directories.

    Returns:
        The version as a tuple of integers.

    Raises:
        EpiworldrUnavailableError: If epiworldR is not installed, or its version
            cannot be parsed.
    """
    rscript = resolve_rscript(explicit)
    proc = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [
            str(rscript),
            "--vanilla",
            "-e",
            'cat(as.character(utils::packageVersion("epiworldR")))',
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=_PROBE_TIMEOUT,
        env=subprocess_env(r_libs),
    )
    if proc.returncode != 0:
        msg = (
            "The R package 'epiworldR' is not installed or not on .libPaths(). "
            "Install it with install.packages('epiworldR'), or point the "
            "engine's `r_libs:` option at the library containing it.\n"
            f"  Rscript: {rscript}\n"
            f"  stderr: {proc.stderr.strip()[:500]}"
        )
        raise EpiworldrUnavailableError(msg)
    raw = proc.stdout.strip()
    try:
        # epiworldR uses both "0.15.1-1" and "0.15.1.0" style versions.
        return tuple(int(part) for part in raw.replace("-", ".").split("."))
    except ValueError as exc:
        msg = f"Could not parse the reported epiworldR version {raw!r}."
        raise EpiworldrUnavailableError(msg) from exc

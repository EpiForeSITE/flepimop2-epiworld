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
"""A flepimop2 engine that runs epiworldR models in an R subprocess."""

__all__ = ["EpiworldrEngine"]

from pathlib import Path
from typing import Any

from flepimop2.engine.abc import EngineABC
from flepimop2.exceptions import ValidationIssue
from flepimop2.system.abc import SystemABC
from flepimop2.typing import StateChangeEnum
from pydantic import Field

from flepimop2_epiworldr._bridge import DRIVER_PATH, RunnerConfig, make_runner
from flepimop2_epiworldr._contract import SupportsEpiworldrRun
from flepimop2_epiworldr._models import MODEL_SPECS
from flepimop2_epiworldr._rscript import (
    MIN_EPIWORLDR_VERSION,
    epiworldr_version,
)
from flepimop2_epiworldr.exceptions import EpiworldrUnavailableError


class EpiworldrEngine(EngineABC, module="epiworldr"):
    """
    Drive an epiworldR model through an `Rscript` subprocess.

    Unlike a solver engine, this one ignores the system's stepper: epiworldR
    runs its own loop in C++, and this engine's job is to translate flepimop2's
    configured parameters into an epiworldR run and translate the resulting
    compartment history back into flepimop2's `(time, state...)` array.

    Running R out of process rather than in-process keeps a fault in epiworld's
    C++ from taking down the pipeline, and avoids a build-fragile dependency.
    The cost is roughly 0.4s of R startup per run.

    Attributes:
        state_change: Always `state`; epiworldR reports absolute counts.
        rscript: Explicit path to `Rscript`, if it is not discoverable.
        r_libs: Extra R library directories, exported as `R_LIBS`. Needed when
            epiworldR lives somewhere `--vanilla` would not look.
        timeout: Seconds to allow a single epiworldR run.
        seed: Fallback seed when no `seed` parameter is configured.
        model_name: Name handed to the epiworldR model constructor.
        check_r: Probe for R and epiworldR during validation, so a missing
            toolchain surfaces at `--dry-run` rather than mid-run.
        keep_temp: Preserve the request and response files for debugging.

    Examples:
        >>> from flepimop2.engine.abc import build
        >>> engine = build({"module": "epiworldr", "check_r": False})
        >>> engine.module
        'flepimop2.engine.epiworldr'
        >>> engine.state_change
        <StateChangeEnum.STATE: 'state'>
    """

    state_change: StateChangeEnum = StateChangeEnum.STATE
    rscript: Path | None = None
    r_libs: list[Path] = Field(default_factory=list)
    timeout: float = Field(default=300.0, gt=0.0)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    model_name: str = "flepimop2"
    check_r: bool = True
    keep_temp: bool = False

    def model_post_init(self, __context: Any, /) -> None:  # ruff: ignore[any-type]
        """
        Install the runner closure.

        Args:
            __context: Pydantic model post-init context.
        """
        super().model_post_init(__context)
        self._runner = make_runner(
            RunnerConfig(
                rscript=self.rscript,
                r_libs=tuple(self.r_libs),
                timeout=self.timeout,
                seed=self.seed,
                model_name=self.model_name,
                keep_temp=self.keep_temp,
            )
        )

    def validate_system(self, system: SystemABC) -> list[ValidationIssue] | None:
        """
        Check the system, the driver, and the R toolchain before running.

        `Simulator.__init__` calls this, so `flepimop2 simulate --dry-run`
        reports a missing R, a missing epiworldR, an incompatible system, or a
        broken install once, up front, instead of failing partway through a
        scenario sweep.

        Args:
            system: The system to validate against.

        Returns:
            The validation issues found, or `None` if the pairing is usable.
        """
        issues: list[ValidationIssue] = []

        if isinstance(system, SupportsEpiworldrRun):
            spec = system.epiworldr_spec()
            if spec.key not in MODEL_SPECS:
                issues.append(
                    ValidationIssue(
                        msg=(
                            f"Unknown epiworldR model {spec.key!r}; this "
                            "provider knows: "
                            f"{', '.join(sorted(MODEL_SPECS))}."
                        ),
                        kind="unknown_model",
                    )
                )
        else:
            issues.append(
                ValidationIssue(
                    msg=(
                        "The 'epiworldr' engine requires an epiworldR-backed "
                        "system exposing `epiworldr_spec()`, but got "
                        f"{type(system).__name__}. Use `system: epiworldr`."
                    ),
                    kind="incompatible_system",
                )
            )

        if system.state_change is not StateChangeEnum.STATE:
            issues.append(
                ValidationIssue(
                    msg=(
                        "epiworldR reports absolute compartment counts, so the "
                        "'epiworldr' engine requires state_change 'state'; the "
                        f"system declares {system.state_change.value!r}."
                    ),
                    kind="incompatible_state_change",
                )
            )

        if not DRIVER_PATH.is_file():
            issues.append(
                ValidationIssue(
                    msg=(
                        f"The epiworldR driver script is missing from "
                        f"{DRIVER_PATH}; the installed flepimop2-epiworldr "
                        "appears incomplete. Reinstall it."
                    ),
                    kind="missing_driver",
                )
            )

        if self.check_r:
            issues.extend(self._probe_r())

        return issues or None

    def _probe_r(self) -> list[ValidationIssue]:
        """
        Confirm R and a new enough epiworldR are reachable.

        Returns:
            Any issues found probing the R toolchain.
        """
        try:
            version = epiworldr_version(self.rscript, tuple(self.r_libs))
        except EpiworldrUnavailableError as exc:
            return [ValidationIssue(msg=str(exc), kind="epiworldr_unavailable")]
        if version < MIN_EPIWORLDR_VERSION:
            readable = ".".join(str(part) for part in MIN_EPIWORLDR_VERSION)
            found = ".".join(str(part) for part in version)
            return [
                ValidationIssue(
                    msg=(
                        f"This provider needs epiworldR >= {readable} for its "
                        f"state names and seeding semantics, but found {found}."
                    ),
                    kind="epiworldr_too_old",
                )
            ]
        return []

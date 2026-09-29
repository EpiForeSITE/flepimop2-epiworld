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
"""A flepimop2 engine that runs epiworld models through epiworldpy."""

__all__ = ["EpiworldEngine"]

from typing import Any

from flepimop2.engine.abc import EngineABC
from flepimop2.exceptions import ValidationIssue
from flepimop2.system.abc import SystemABC
from flepimop2.typing import StateChangeEnum
from pydantic import Field

from flepimop2_epiworld._bridge import (
    MAX_SEED,
    RunnerConfig,
    load_constructor,
    make_runner,
)
from flepimop2_epiworld._contract import SupportsEpiworldRun
from flepimop2_epiworld._models import MODEL_SPECS, EpiworldModelSpec
from flepimop2_epiworld.exceptions import EpiworldUnavailableError


class EpiworldEngine(EngineABC, module="epiworld"):
    """
    Drive an epiworld model through epiworldpy.

    Unlike a solver engine, this one ignores the system's stepper: epiworld
    runs its own loop in C++, and this engine's job is to translate flepimop2's
    configured parameters into an epiworld run and translate the resulting
    compartment history back into flepimop2's `(time, state...)` array.

    Attributes:
        state_change: Always `state`; epiworld reports absolute counts.
        seed: Fallback seed when no `seed` parameter is configured.
        model_name: Name handed to the epiworld model constructor.

    Examples:
        >>> from flepimop2.engine.abc import build
        >>> engine = build({"module": "epiworld"})
        >>> engine.module
        'flepimop2.engine.epiworld'
        >>> engine.state_change
        <StateChangeEnum.STATE: 'state'>
    """

    state_change: StateChangeEnum = StateChangeEnum.STATE
    seed: int | None = Field(default=None, ge=0, le=MAX_SEED)
    model_name: str = "flepimop2"

    def model_post_init(self, __context: Any, /) -> None:  # ruff: ignore[any-type]
        """
        Install the runner closure.

        Args:
            __context: Pydantic model post-init context.
        """
        super().model_post_init(__context)
        self._runner = make_runner(
            RunnerConfig(seed=self.seed, model_name=self.model_name)
        )

    def validate_system(self, system: SystemABC) -> list[ValidationIssue] | None:
        """
        Check the system and the installed epiworldpy before running.

        `Simulator.__init__` calls this, so `flepimop2 simulate --dry-run`
        reports an incompatible system or an unusable epiworldpy once, up
        front, instead of failing partway through a scenario sweep.

        Args:
            system: The system to validate against.

        Returns:
            The validation issues found, or `None` if the pairing is usable.
        """
        issues: list[ValidationIssue] = []

        if isinstance(system, SupportsEpiworldRun):
            spec = system.epiworld_spec()
            if spec.key in MODEL_SPECS:
                issues.extend(self._probe_epiworldpy(spec))
            else:
                issues.append(
                    ValidationIssue(
                        msg=(
                            f"Unknown epiworld model {spec.key!r}; this "
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
                        "The 'epiworld' engine requires an epiworld-backed "
                        "system exposing `epiworld_spec()`, but got "
                        f"{type(system).__name__}. Use `system: epiworld`."
                    ),
                    kind="incompatible_system",
                )
            )

        if system.state_change is not StateChangeEnum.STATE:
            issues.append(
                ValidationIssue(
                    msg=(
                        "epiworld reports absolute compartment counts, so the "
                        "'epiworld' engine requires state_change 'state'; the "
                        f"system declares {system.state_change.value!r}."
                    ),
                    kind="incompatible_state_change",
                )
            )

        return issues or None

    @staticmethod
    def _probe_epiworldpy(spec: EpiworldModelSpec) -> list[ValidationIssue]:
        """
        Confirm epiworldpy provides the model and the features it needs.

        Args:
            spec: The model registry entry to look up.

        Returns:
            Any issues found probing epiworldpy.
        """
        try:
            load_constructor(spec)
        except EpiworldUnavailableError as exc:
            return [ValidationIssue(msg=str(exc), kind="epiworldpy_unavailable")]
        return []

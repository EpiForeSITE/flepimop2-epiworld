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
"""A flepimop2 system backed by an epiworldR agent-based model."""

__all__ = ["EpiworldrSystem"]

from typing import Any

import numpy as np
from flepimop2.axis import AxisCollection
from flepimop2.parameter.abc import (
    ModelStateSpecification,
    ParameterRequest,
)
from flepimop2.system.abc import SystemABC
from flepimop2.typing import (
    Float64NDArray,
    IdentifierString,
    StateChangeEnum,
    SystemProtocol,
    as_system_protocol,
)

from flepimop2_epiworldr._models import (
    MODEL_SPECS,
    EpiworldrModelKey,
    EpiworldrModelSpec,
)


def _unsupported_stepper(
    time: np.float64,
    state: Float64NDArray,
    /,
    **params: Any,
) -> Float64NDArray:
    """
    Stand in for a stepper epiworldR fundamentally cannot provide.

    Raises:
        NotImplementedError: Always.
    """
    msg = (
        "An epiworldR system cannot be stepped from Python. epiworldR owns its "
        "own simulation loop and tracks per-agent exposure and recovery clocks, "
        "so evaluating a single day in isolation would silently discard agent "
        "state and produce different dynamics. Pair this system with "
        "`engine: epiworldr`, which runs the whole simulation inside R; the "
        "generic engines (wrapper, solve_ivp, euler) are not compatible with it."
    )
    raise NotImplementedError(msg)


class EpiworldrSystem(SystemABC, module="epiworldr"):
    """
    Declarative description of an epiworldR model.

    This system carries no dynamics of its own. It exists to tell flepimop2
    which compartments the model has, which configured parameters supply their
    initial counts, and which rate parameters the model needs -- everything
    `Simulator.resolve_inputs` needs in order to sample the `parameter:`
    section. The simulation itself is run by `engine: epiworldr`.

    Attributes:
        model: Which epiworldR model to run.
        state_change: Always `state`; epiworldR reports absolute counts.
        population_name: Name given to the epiworldR model constructor, which
            surfaces in epiworldR's own summaries.

    Examples:
        >>> from flepimop2.system.abc import build
        >>> system = build({"module": "epiworldr", "state_change": "state"})
        >>> system.module
        'flepimop2.system.epiworldr'
        >>> system.epiworldr_spec().r_constructor
        'ModelSEIRCONN'
    """

    model: EpiworldrModelKey = "seirconn"
    state_change: StateChangeEnum = StateChangeEnum.STATE
    population_name: str = "flepimop2"

    def epiworldr_spec(self) -> EpiworldrModelSpec:
        """
        Describe the epiworldR model this system represents.

        Returns:
            The registry entry for the configured model.

        Examples:
            >>> from flepimop2.system.epiworldr import EpiworldrSystem
            >>> EpiworldrSystem().epiworldr_spec().states
            ('Susceptible', 'Exposed', 'Infected', 'Recovered')
        """
        return MODEL_SPECS[self.model]

    def model_state(self, axes: AxisCollection) -> ModelStateSpecification:
        """
        Declare which parameters hold each compartment's initial count.

        Args:
            axes: Resolved runtime axes. Ignored: epiworldR populations are not
                stratified by this provider yet, and a stratified extension
                would map axes onto epiworld entities rather than array shape.

        Returns:
            The model-state specification for the configured model.

        Examples:
            >>> from flepimop2.axis import AxisCollection
            >>> from flepimop2.system.epiworldr import EpiworldrSystem
            >>> EpiworldrSystem().model_state(AxisCollection()).parameter_names
            ('s0', 'e0', 'i0', 'r0')
        """
        del axes
        spec = self.epiworldr_spec()
        return ModelStateSpecification(
            parameter_names=spec.state_parameters,
            labels=spec.states,
        )

    def requested_parameters(
        self, axes: AxisCollection
    ) -> dict[IdentifierString, ParameterRequest]:
        """
        Declare the model's rate parameters, plus an optional seed.

        This override is required, not merely convenient. The inherited
        implementation infers requests from the bound stepper's signature, and
        this system's stepper is a sentinel that takes only `**params` -- so
        the default would silently request nothing at all and the model would
        run on epiworldR's defaults.

        Args:
            axes: Resolved runtime axes. Ignored; see `model_state`.

        Returns:
            A mapping of parameter names to their runtime requests.

        Examples:
            >>> from flepimop2.axis import AxisCollection
            >>> from flepimop2.system.epiworldr import EpiworldrSystem
            >>> sorted(EpiworldrSystem().requested_parameters(AxisCollection()))
            ['contact_rate', 'incubation_days', 'recovery_rate', 'seed',
             'transmission_rate']
        """
        del axes
        spec = self.epiworldr_spec()
        requests = {name: ParameterRequest(name=name) for name in spec.parameters}
        # Optional so a single deterministic run needs no `seed:` entry, while a
        # `scenario: grid` over `seed` still reaches the engine through params.
        requests["seed"] = ParameterRequest(name="seed", optional=True)
        return requests

    def _bind_impl(  # ruff: ignore[no-self-use]
        self, params: dict[IdentifierString, Any] | None = None
    ) -> SystemProtocol:
        """
        Return the sentinel stepper.

        `EngineABC.run` calls `bind()` unconditionally and passes the result to
        its runner. The epiworldR runner ignores that argument, so the sentinel
        is constructed but never invoked during a normal run.

        Args:
            params: Ignored; epiworldR parameters are bound inside R.

        Returns:
            A callable that raises if anything actually tries to step it.
        """
        del params
        return as_system_protocol(_unsupported_stepper)

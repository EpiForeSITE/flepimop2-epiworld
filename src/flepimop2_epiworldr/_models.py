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
"""Registry describing the epiworldR models this provider can drive."""

__all__ = ["MODEL_SPECS", "EpiworldrModelKey", "EpiworldrModelSpec"]

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from flepimop2.typing import IdentifierString

EpiworldrModelKey = Literal["seirconn"]
"""Config values accepted by `EpiworldrSystem.model`."""


@dataclass(frozen=True, slots=True)
class EpiworldrModelSpec:
    """
    Static description of one epiworldR model.

    This is the seam for supporting additional epiworldR models. Adding, say,
    `ModelSIRCONN` means one entry here, one matching entry in the R driver's
    own registry, and widening `EpiworldrModelKey`. A parity test compares the
    two registries so a half-finished addition fails in CI rather than at run
    time.

    Attributes:
        key: Config value and shared registry key, e.g. `"seirconn"`.
        r_constructor: The epiworldR function name, for diagnostics and the
            cross-language parity check.
        states: epiworld compartment names, in epiworld's own state order.
        state_parameters: flepimop2 parameter names supplying the initial count
            for each compartment, aligned with `states`.
        parameters: flepimop2 parameter names for the model's rate parameters.
        init_arity: Length of the `proportions` vector `initial_states()` wants.

    Examples:
        >>> from flepimop2_epiworldr._models import MODEL_SPECS
        >>> spec = MODEL_SPECS["seirconn"]
        >>> spec.r_constructor
        'ModelSEIRCONN'
        >>> spec.states
        ('Susceptible', 'Exposed', 'Infected', 'Recovered')
        >>> spec.state_parameters
        ('s0', 'e0', 'i0', 'r0')
    """

    key: str
    r_constructor: str
    states: tuple[str, ...]
    state_parameters: tuple[IdentifierString, ...]
    parameters: tuple[IdentifierString, ...]
    init_arity: int

    def __post_init__(self) -> None:
        """
        Validate that compartments and their initial-count parameters align.

        Raises:
            ValueError: If `states` and `state_parameters` differ in length, or
                if either contains duplicates.

        Examples:
            >>> from flepimop2_epiworldr._models import EpiworldrModelSpec
            >>> EpiworldrModelSpec(
            ...     key="bad",
            ...     r_constructor="ModelBad",
            ...     states=("S", "I"),
            ...     state_parameters=("s0",),
            ...     parameters=(),
            ...     init_arity=1,
            ... )
            Traceback (most recent call last):
                ...
            ValueError: EpiworldrModelSpec 'bad' has 2 states but 1 ...
        """
        if len(self.states) != len(self.state_parameters):
            msg = (
                f"EpiworldrModelSpec {self.key!r} has {len(self.states)} states "
                f"but {len(self.state_parameters)} state_parameters; they must "
                "correspond one-to-one and in the same order."
            )
            raise ValueError(msg)
        for field_name, values in (
            ("states", self.states),
            ("state_parameters", self.state_parameters),
            ("parameters", self.parameters),
        ):
            if len(set(values)) != len(values):
                msg = (
                    f"EpiworldrModelSpec {self.key!r} has duplicate entries in "
                    f"{field_name}: {values}."
                )
                raise ValueError(msg)


MODEL_SPECS: Final[Mapping[str, EpiworldrModelSpec]] = MappingProxyType({
    "seirconn": EpiworldrModelSpec(
        key="seirconn",
        r_constructor="ModelSEIRCONN",
        # epiworld registers these in `seirconnected.hpp` as states 0..3.
        states=("Susceptible", "Exposed", "Infected", "Recovered"),
        state_parameters=("s0", "e0", "i0", "r0"),
        parameters=(
            "contact_rate",
            "transmission_rate",
            "incubation_days",
            "recovery_rate",
        ),
        init_arity=2,
    ),
})
"""Every epiworldR model this provider knows how to drive."""

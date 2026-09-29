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
"""Registry describing the epiworld models this provider can drive."""

__all__ = ["MODEL_SPECS", "EpiworldModelKey", "EpiworldModelSpec"]

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from flepimop2.typing import IdentifierString

EpiworldModelKey = Literal["seirconn"]
"""Config values accepted by `EpiworldSystem.model`."""


@dataclass(frozen=True, slots=True)
class EpiworldModelSpec:
    """
    Static description of one epiworld model.

    This is the seam for supporting additional epiworld models. Adding, say,
    `ModelSIRCONN` means one entry here and widening `EpiworldModelKey`. A test
    builds every registered model through epiworldpy and checks its states, so
    a mistyped entry fails in CI rather than at run time.

    Attributes:
        key: Config value and shared registry key, e.g. `"seirconn"`.
        constructor: The model class name in `epiworldpy.epimodels`.
        states: epiworld compartment names, in epiworld's own state order.
        state_parameters: flepimop2 parameter names supplying the initial count
            for each compartment, aligned with `states`.
        parameters: flepimop2 parameter names for the model's rate parameters.
        init_arity: Length of the `proportions` vector `initial_states()` wants.

    Examples:
        >>> from flepimop2_epiworld._models import MODEL_SPECS
        >>> spec = MODEL_SPECS["seirconn"]
        >>> spec.constructor
        'ModelSEIRCONN'
        >>> spec.states
        ('Susceptible', 'Exposed', 'Infected', 'Recovered')
        >>> spec.state_parameters
        ('s0', 'e0', 'i0', 'r0')
    """

    key: str
    constructor: str
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
            >>> from flepimop2_epiworld._models import EpiworldModelSpec
            >>> EpiworldModelSpec(
            ...     key="bad",
            ...     constructor="ModelBad",
            ...     states=("S", "I"),
            ...     state_parameters=("s0",),
            ...     parameters=(),
            ...     init_arity=1,
            ... )
            Traceback (most recent call last):
                ...
            ValueError: EpiworldModelSpec 'bad' has 2 states but 1 ...
        """
        if len(self.states) != len(self.state_parameters):
            msg = (
                f"EpiworldModelSpec {self.key!r} has {len(self.states)} states "
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
                    f"EpiworldModelSpec {self.key!r} has duplicate entries in "
                    f"{field_name}: {values}."
                )
                raise ValueError(msg)


MODEL_SPECS: Final[Mapping[str, EpiworldModelSpec]] = MappingProxyType({
    "seirconn": EpiworldModelSpec(
        key="seirconn",
        constructor="ModelSEIRCONN",
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
"""Every epiworld model this provider knows how to drive."""

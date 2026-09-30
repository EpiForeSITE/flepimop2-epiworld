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
"""Invariants for the epiworld model registry."""

import pytest
from flepimop2.typing import IdentifierString
from pydantic import TypeAdapter

from flepimop2_epiworld._models import MODEL_SPECS, EpiworldModelSpec

_IDENTIFIER = TypeAdapter(IdentifierString)


@pytest.mark.parametrize("spec", MODEL_SPECS.values(), ids=list(MODEL_SPECS))
def test_states_and_state_parameters_align(spec: EpiworldModelSpec) -> None:
    """Each compartment needs exactly one parameter supplying its initial count."""
    assert len(spec.states) == len(spec.state_parameters)


@pytest.mark.parametrize("spec", MODEL_SPECS.values(), ids=list(MODEL_SPECS))
def test_parameter_names_are_valid_flepimop2_identifiers(
    spec: EpiworldModelSpec,
) -> None:
    """
    flepimop2 config keys are lowercase identifiers.

    A name that fails here could never be referenced from a `parameter:` block.
    """
    for name in (*spec.state_parameters, *spec.parameters):
        _IDENTIFIER.validate_python(name)


@pytest.mark.parametrize("spec", MODEL_SPECS.values(), ids=list(MODEL_SPECS))
def test_key_matches_registry_key(spec: EpiworldModelSpec) -> None:
    """The registry key and the spec's own key must not drift apart."""
    assert MODEL_SPECS[spec.key] is spec


def test_mismatched_states_rejected() -> None:
    """A half-specified model should fail at import, not at run time."""
    with pytest.raises(ValueError, match="2 states but 1"):
        EpiworldModelSpec(
            key="bad",
            constructor="ModelBad",
            states=("S", "I"),
            state_parameters=("s0",),
            parameters=(),
            init_arity=1,
        )


def test_duplicate_states_rejected() -> None:
    """Duplicate compartments would collapse when the history is pivoted."""
    with pytest.raises(ValueError, match="duplicate entries in states"):
        EpiworldModelSpec(
            key="bad",
            constructor="ModelBad",
            states=("S", "S"),
            state_parameters=("s0", "s1"),
            parameters=(),
            init_arity=1,
        )

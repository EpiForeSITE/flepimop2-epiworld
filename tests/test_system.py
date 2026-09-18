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
"""Tests for the declarative epiworldR system module."""

import numpy as np
import pytest
from flepimop2.axis import AxisCollection
from flepimop2.system.abc import build
from flepimop2.typing import StateChangeEnum

from flepimop2.system.epiworldr import EpiworldrSystem

AXES = AxisCollection()


def test_module_resolves_through_flepimop2() -> None:
    """`module: epiworldr` must reach this class via the namespace package."""
    system = build({"module": "epiworldr", "state_change": "state"})
    assert isinstance(system, EpiworldrSystem)
    assert system.module == "flepimop2.system.epiworldr"


def test_defaults_to_state_change_state() -> None:
    """EpiworldR reports absolute counts, so `state` is the only correct value."""
    assert EpiworldrSystem().state_change is StateChangeEnum.STATE


def test_model_state_declares_compartments_in_epiworld_order() -> None:
    """Column order in the output follows this declaration."""
    spec = EpiworldrSystem().model_state(AXES)
    assert spec.parameter_names == ("s0", "e0", "i0", "r0")
    assert spec.labels == ("Susceptible", "Exposed", "Infected", "Recovered")


def test_requested_parameters_are_complete() -> None:
    """
    Guard the override of `requested_parameters`.

    The inherited implementation introspects the bound stepper's signature.
    This system's stepper is a sentinel taking only `**params`, so the default
    would return an empty mapping and the model would silently run on
    epiworldR's own defaults instead of the configured ones. If this test ever
    fails with an empty set, the override was lost.
    """
    requests = EpiworldrSystem().requested_parameters(AXES)
    assert set(requests) == {
        "contact_rate",
        "transmission_rate",
        "incubation_days",
        "recovery_rate",
        "seed",
    }


def test_only_seed_is_optional() -> None:
    """Rate parameters must be configured; seed may come from a scenario sweep."""
    requests = EpiworldrSystem().requested_parameters(AXES)
    optional = {name for name, request in requests.items() if request.optional}
    assert optional == {"seed"}


def test_bind_returns_a_callable_that_refuses_to_step() -> None:
    """
    `EngineABC.run` calls `bind()` unconditionally, so it must not raise.

    The sentinel it returns raises only if something actually tries to step it,
    which the epiworldR engine never does.
    """
    stepper = EpiworldrSystem().bind()
    assert callable(stepper)
    with pytest.raises(NotImplementedError, match="owns its own simulation loop"):
        stepper(np.float64(0.0), np.zeros(4))


def test_step_helper_explains_the_incompatibility() -> None:
    """The troubleshooting helper should say why, not just fail."""
    with pytest.raises(NotImplementedError, match="engine: epiworldr"):
        EpiworldrSystem().step(np.float64(0.0), np.zeros(4))

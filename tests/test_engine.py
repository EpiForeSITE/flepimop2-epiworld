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
"""Tests for the epiworldR engine module, without invoking R."""

import inspect
import json

import numpy as np
import pytest
from flepimop2.axis import AxisCollection, ResolvedShape
from flepimop2.engine.abc import build
from flepimop2.parameter.abc import ModelStateSpecification, ParameterValue
from flepimop2.system.abc import SystemABC
from flepimop2.typing import StateChangeEnum, SystemProtocol

from flepimop2.engine.epiworldr import EpiworldrEngine
from flepimop2.system.epiworldr import EpiworldrSystem
from flepimop2_epiworldr._bridge import (
    MAX_SEED,
    build_request,
    resolve_seed,
    spec_for_model_state,
)
from flepimop2_epiworldr._initial_state import SeirCounts
from flepimop2_epiworldr._models import MODEL_SPECS
from flepimop2_epiworldr.exceptions import EpiworldrError


class _ForeignSystem(SystemABC, module="flepimop2.system._foreign_test"):
    """A system with no epiworldR affiliation."""

    state_change: StateChangeEnum = StateChangeEnum.STATE

    def _bind_impl(self, params: dict[str, object] | None = None) -> SystemProtocol:
        return lambda time, state, **kwargs: state


def _scalar(value: float) -> ParameterValue:
    return ParameterValue(np.asarray(value, dtype=np.float64), ResolvedShape())


def test_module_resolves_through_flepimop2() -> None:
    """`module: epiworldr` must reach this class via the namespace package."""
    engine = build({"module": "epiworldr", "check_r": False})
    assert isinstance(engine, EpiworldrEngine)
    assert engine.module == "flepimop2.engine.epiworldr"


def test_accepts_the_epiworldr_system() -> None:
    """The intended pairing must validate cleanly."""
    engine = EpiworldrEngine(check_r=False)
    assert engine.validate_system(EpiworldrSystem()) is None


def test_rejects_a_foreign_system() -> None:
    """A non-epiworldR system cannot be driven by this engine."""
    engine = EpiworldrEngine(check_r=False)
    issues = engine.validate_system(_ForeignSystem())
    assert issues is not None
    assert [issue.kind for issue in issues] == ["incompatible_system"]


def test_rejects_wrong_state_change() -> None:
    """A flow system would be silently misinterpreted as counts."""
    engine = EpiworldrEngine(check_r=False)
    issues = engine.validate_system(EpiworldrSystem(state_change=StateChangeEnum.FLOW))
    assert issues is not None
    assert [issue.kind for issue in issues] == ["incompatible_state_change"]


def test_runner_is_a_plain_function() -> None:
    """
    Guard against storing a bound method in the private attribute.

    A bound method referencing the engine makes the engine self-referential,
    and `ModuleBase.patch` deep-copies modules.
    """
    engine = EpiworldrEngine(check_r=False)
    assert not inspect.ismethod(engine._runner)


def test_engine_survives_a_deep_copy() -> None:
    """`ModuleBase.patch(conflict=replace)` deep-copies; it must not recurse."""
    engine = EpiworldrEngine(check_r=False)
    assert engine.model_copy(deep=True).timeout == engine.timeout


def test_spec_is_recovered_from_model_state() -> None:
    """The engine identifies the model structurally, not by importing the system."""
    model_state = EpiworldrSystem().model_state(AxisCollection())
    assert spec_for_model_state(model_state) is MODEL_SPECS["seirconn"]


def test_unrecognized_model_state_is_rejected() -> None:
    """A mismatched system should fail loudly rather than mis-seed the model."""
    with pytest.raises(EpiworldrError, match="does not match any epiworldR model"):
        spec_for_model_state(
            ModelStateSpecification(parameter_names=("a", "b"), labels=("A", "B"))
        )


def test_missing_model_state_is_rejected() -> None:
    """flepimop2 allows a system with no model state; this engine cannot."""
    with pytest.raises(EpiworldrError, match="requires a system that declares"):
        spec_for_model_state(None)


def test_seed_comes_from_parameters_first() -> None:
    """A scenario sweep injects seed through params; it must win."""
    assert resolve_seed({"seed": _scalar(1912.0)}, 7) == 1912


def test_seed_falls_back_to_engine_option() -> None:
    """Without a seed parameter, the engine's own option applies."""
    assert resolve_seed({}, 7) == 7


def test_missing_seed_warns_about_identical_replicates() -> None:
    """Silently defaulting would make a replicate sweep produce identical runs."""
    with pytest.warns(UserWarning, match="every replicate would be identical"):
        assert resolve_seed({}, None) == 0


def test_out_of_range_seed_rejected() -> None:
    """R coerces the seed with as.integer, which NAs above 2**31-1."""
    with pytest.raises(EpiworldrError, match="between 0 and"):
        resolve_seed({"seed": _scalar(float(MAX_SEED + 1))}, None)


def test_request_is_json_safe() -> None:
    """Numpy scalars are not JSON-serializable; the request must hold plain types."""
    request = build_request(
        spec=MODEL_SPECS["seirconn"],
        counts=SeirCounts(9700, 120, 60, 120),
        parameters={"contact_rate": np.float64(6.0)},
        days=[0, 1],
        ndays=1,
        seed=1912,
        model_name="test",
    )
    encoded = json.dumps(request, allow_nan=False)
    assert '"protocol": 1' in encoded
    assert request["initial_state"]["Susceptible"] == 9700
    assert request["n"] == 10000


def test_oversized_population_rejected() -> None:
    """Beyond 2**24 the float32 prevalence can no longer name every integer."""
    with pytest.raises(EpiworldrError, match="ceiling"):
        build_request(
            spec=MODEL_SPECS["seirconn"],
            counts=SeirCounts(2**25, 0, 1, 0),
            parameters={},
            days=[0],
            ndays=0,
            seed=0,
            model_name="test",
        )

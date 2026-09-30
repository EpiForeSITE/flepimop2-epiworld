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
"""Tests for the epiworld engine module."""

import inspect

import numpy as np
import pytest
from flepimop2.axis import AxisCollection, ResolvedShape
from flepimop2.engine.abc import build
from flepimop2.parameter.abc import ModelStateSpecification, ParameterValue
from flepimop2.system.abc import SystemABC
from flepimop2.typing import StateChangeEnum, SystemProtocol

from flepimop2.engine.epiworld import EpiworldEngine
from flepimop2.system.epiworld import EpiworldSystem
from flepimop2_epiworld._bridge import (
    MAX_SEED,
    resolve_seed,
    run_model,
    spec_for_model_state,
)
from flepimop2_epiworld._initial_state import SeirCounts
from flepimop2_epiworld._models import MODEL_SPECS
from flepimop2_epiworld.exceptions import EpiworldError, EpiworldUnavailableError


class _ForeignSystem(SystemABC, module="flepimop2.system._foreign_test"):
    """A system with no epiworld affiliation."""

    state_change: StateChangeEnum = StateChangeEnum.STATE

    def _bind_impl(self, params: dict[str, object] | None = None) -> SystemProtocol:
        return lambda time, state, **kwargs: state


def _scalar(value: float) -> ParameterValue:
    return ParameterValue(np.asarray(value, dtype=np.float64), ResolvedShape())


def test_module_resolves_through_flepimop2() -> None:
    """`module: epiworld` must reach this class via the namespace package."""
    engine = build({"module": "epiworld"})
    assert isinstance(engine, EpiworldEngine)
    assert engine.module == "flepimop2.engine.epiworld"


def test_accepts_the_epiworld_system() -> None:
    """The intended pairing must validate cleanly."""
    engine = EpiworldEngine()
    assert engine.validate_system(EpiworldSystem()) is None


def test_rejects_a_foreign_system() -> None:
    """A non-epiworld system cannot be driven by this engine."""
    engine = EpiworldEngine()
    issues = engine.validate_system(_ForeignSystem())
    assert issues is not None
    assert [issue.kind for issue in issues] == ["incompatible_system"]


def test_rejects_wrong_state_change() -> None:
    """A flow system would be silently misinterpreted as counts."""
    engine = EpiworldEngine()
    issues = engine.validate_system(EpiworldSystem(state_change=StateChangeEnum.FLOW))
    assert issues is not None
    assert [issue.kind for issue in issues] == ["incompatible_state_change"]


def test_runner_is_a_plain_function() -> None:
    """
    Guard against storing a bound method in the private attribute.

    A bound method referencing the engine makes the engine self-referential,
    and `ModuleBase.patch` deep-copies modules.
    """
    engine = EpiworldEngine()
    assert not inspect.ismethod(engine._runner)


def test_engine_survives_a_deep_copy() -> None:
    """`ModuleBase.patch(conflict=replace)` deep-copies; it must not recurse."""
    engine = EpiworldEngine()
    assert engine.model_copy(deep=True).seed == engine.seed


def test_spec_is_recovered_from_model_state() -> None:
    """The engine identifies the model structurally, not by importing the system."""
    model_state = EpiworldSystem().model_state(AxisCollection())
    assert spec_for_model_state(model_state) is MODEL_SPECS["seirconn"]


def test_unrecognized_model_state_is_rejected() -> None:
    """A mismatched system should fail loudly rather than mis-seed the model."""
    with pytest.raises(EpiworldError, match="does not match any epiworld model"):
        spec_for_model_state(
            ModelStateSpecification(parameter_names=("a", "b"), labels=("A", "B"))
        )


def test_missing_model_state_is_rejected() -> None:
    """flepimop2 allows a system with no model state; this engine cannot."""
    with pytest.raises(EpiworldError, match="requires a system that declares"):
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
    """Epiworld takes the seed as a C int, which overflows above 2**31-1."""
    with pytest.raises(EpiworldError, match="between 0 and"):
        resolve_seed({"seed": _scalar(float(MAX_SEED + 1))}, None)


def test_missing_epiworldpy_feature_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An epiworldpy without `initial_states` must surface at validation time."""

    def unavailable(_spec: object) -> object:
        msg = "no initial_states"
        raise EpiworldUnavailableError(msg)

    monkeypatch.setattr("flepimop2.engine.epiworld.load_constructor", unavailable)
    issues = EpiworldEngine().validate_system(EpiworldSystem())
    assert issues is not None
    assert [issue.kind for issue in issues] == ["epiworldpy_unavailable"]


def test_missing_rate_parameter_rejected() -> None:
    """Running on epiworld's defaults instead of the configuration must not happen."""
    with pytest.raises(EpiworldError, match="Missing epiworld model parameter"):
        run_model(
            MODEL_SPECS["seirconn"],
            counts=SeirCounts(9700, 120, 60, 120),
            parameters={"contact_rate": 6.0},
            days=[0],
            ndays=0,
            seed=0,
            model_name="test",
        )


def test_oversized_population_rejected() -> None:
    """Beyond 2**24 the float32 prevalence can no longer name every integer."""
    with pytest.raises(EpiworldError, match="ceiling"):
        run_model(
            MODEL_SPECS["seirconn"],
            counts=SeirCounts(2**25, 0, 1, 0),
            parameters=dict.fromkeys(MODEL_SPECS["seirconn"].parameters, 0.1),
            days=[0],
            ndays=0,
            seed=0,
            model_name="test",
        )

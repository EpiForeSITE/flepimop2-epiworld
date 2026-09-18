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
"""Tests that actually run epiworldR through the R driver."""

import json
import subprocess

import numpy as np
import pytest
from flepimop2.axis import ResolvedShape
from flepimop2.parameter.abc import ModelStateSpecification, ParameterValue

from flepimop2_epiworldr._bridge import (
    DRIVER_PATH,
    RunnerConfig,
    build_request,
    invoke_driver,
    make_runner,
)
from flepimop2_epiworldr._initial_state import SeirCounts
from flepimop2_epiworldr._models import MODEL_SPECS
from flepimop2_epiworldr._rscript import resolve_rscript
from flepimop2_epiworldr.exceptions import EpiworldrError
from tests.conftest import requires_epiworldr

pytestmark = requires_epiworldr

STATE_SPEC = ModelStateSpecification(
    parameter_names=MODEL_SPECS["seirconn"].state_parameters,
    labels=MODEL_SPECS["seirconn"].states,
)
PARAMETERS = {
    "contact_rate": 6.0,
    "transmission_rate": 0.08,
    "incubation_days": 3.0,
    "recovery_rate": 0.2,
}

# Targets that the bare-ratio seeding formula gets wrong, verified against
# epiworldR 0.15.1. These are the end-to-end counterpart of the pure-Python
# regression table in test_initial_state.py.
NAIVE_FORMULA_FAILURES = [
    SeirCounts(7112, 11, 1116, 1761),
    SeirCounts(40318, 4484, 2459, 76196),
]

REPRESENTATIVE_CASES = [
    SeirCounts(999, 0, 1, 0),
    SeirCounts(800, 120, 60, 20),
    SeirCounts(777, 33, 17, 173),
    SeirCounts(9990, 0, 10, 0),
    SeirCounts(333, 111, 7, 49),
]


def _scalar(value: float) -> ParameterValue:
    return ParameterValue(np.asarray(value, dtype=np.float64), ResolvedShape())


def _run(counts: SeirCounts, times: list[float], seed: int = 1912) -> np.ndarray:
    runner = make_runner(RunnerConfig(seed=seed))
    initial_state = dict(
        zip(
            MODEL_SPECS["seirconn"].state_parameters,
            (_scalar(float(count)) for count in counts),
            strict=True,
        )
    )
    params = {name: _scalar(value) for name, value in PARAMETERS.items()}
    result: np.ndarray = runner(
        None,
        np.asarray(times, dtype=np.float64),
        initial_state,
        params,
        model_state=STATE_SPEC,
    )
    return result


def test_registry_parity_between_python_and_r() -> None:
    """
    The Python and R registries must agree.

    They are the two halves of one contract, so a model added to only one side
    should fail here rather than at run time.
    """
    proc = subprocess.run(
        [str(resolve_rscript()), "--vanilla", str(DRIVER_PATH), "--print-spec"],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    r_specs = json.loads(proc.stdout)
    assert set(r_specs) == set(MODEL_SPECS)
    for key, spec in MODEL_SPECS.items():
        assert r_specs[key]["r_constructor"] == spec.r_constructor
        assert tuple(r_specs[key]["states"]) == spec.states
        assert tuple(r_specs[key]["parameters"]) == spec.parameters
        assert r_specs[key]["init_arity"] == spec.init_arity


@pytest.mark.parametrize(
    "counts", REPRESENTATIVE_CASES + NAIVE_FORMULA_FAILURES, ids=str
)
def test_day_zero_matches_configuration_exactly(counts: SeirCounts) -> None:
    """The configured initial conditions are what epiworldR actually simulates."""
    result = _run(counts, [0.0, 1.0, 2.0])
    assert result[0, 1:].astype(int).tolist() == list(counts)


def test_population_is_conserved() -> None:
    """SEIRCONN has no births or deaths, so the total must never move."""
    counts = SeirCounts(9700, 120, 60, 120)
    result = _run(counts, list(np.arange(0.0, 31.0)))
    assert np.all(result[:, 1:].sum(axis=1) == sum(counts))


def test_result_shape_and_time_column() -> None:
    """The backend contract is (n_times, 1 + n_compartments) with time first."""
    result = _run(SeirCounts(999, 0, 1, 0), [0.0, 5.0, 10.0])
    assert result.shape == (3, 5)
    assert result[:, 0].tolist() == [0.0, 5.0, 10.0]


def test_unsorted_times_preserve_caller_order() -> None:
    """Rows come back in the order asked for, not sorted."""
    counts = SeirCounts(999, 0, 1, 0)
    result = _run(counts, [10.0, 0.0, 5.0])
    assert result[:, 0].tolist() == [10.0, 0.0, 5.0]
    assert result[1, 1:].astype(int).tolist() == list(counts)


def test_same_seed_is_reproducible() -> None:
    """Reproducibility is why the seed is always passed explicitly."""
    times = [0.0, 10.0, 20.0]
    counts = SeirCounts(9700, 120, 60, 120)
    np.testing.assert_array_equal(
        _run(counts, times, seed=99), _run(counts, times, seed=99)
    )


def test_different_seeds_diverge() -> None:
    """Replicates must actually be independent draws."""
    times = [0.0, 10.0, 20.0]
    counts = SeirCounts(9700, 120, 60, 120)
    assert not np.array_equal(
        _run(counts, times, seed=1)[:, 1:], _run(counts, times, seed=2)[:, 1:]
    )


def test_driver_keeps_stdout_empty() -> None:
    """
    Stdout must stay clean.

    epiworldR prints a progress bar unless verbose_off() is called, and the
    bridge treats any stdout as a contract violation.
    """
    request = build_request(
        spec=MODEL_SPECS["seirconn"],
        counts=SeirCounts(999, 0, 1, 0),
        parameters=PARAMETERS,
        days=[0, 1],
        ndays=1,
        seed=1,
        model_name="test",
    )
    invoke_driver(request, RunnerConfig(), 4)


def test_time_beyond_run_length_is_rejected() -> None:
    """A request asking past the simulated span must not be silently clipped."""
    request = build_request(
        spec=MODEL_SPECS["seirconn"],
        counts=SeirCounts(999, 0, 1, 0),
        parameters=PARAMETERS,
        days=[0, 999],
        ndays=1,
        seed=1,
        model_name="test",
    )
    with pytest.raises(EpiworldrError, match=r"outside 0\.\."):
        invoke_driver(request, RunnerConfig(), 4)


def test_unknown_model_is_rejected_by_the_driver() -> None:
    """The R side validates the model key independently of Python."""
    request = build_request(
        spec=MODEL_SPECS["seirconn"],
        counts=SeirCounts(999, 0, 1, 0),
        parameters=PARAMETERS,
        days=[0],
        ndays=0,
        seed=1,
        model_name="test",
    )
    request["model"] = "nonexistent"
    with pytest.raises(EpiworldrError, match="unsupported model"):
        invoke_driver(request, RunnerConfig(), 4)


def test_protocol_mismatch_is_rejected() -> None:
    """A future Python talking to an old driver must fail clearly."""
    request = build_request(
        spec=MODEL_SPECS["seirconn"],
        counts=SeirCounts(999, 0, 1, 0),
        parameters=PARAMETERS,
        days=[0],
        ndays=0,
        seed=1,
        model_name="test",
    )
    request["protocol"] = 999
    with pytest.raises(EpiworldrError, match="unsupported request protocol"):
        invoke_driver(request, RunnerConfig(), 4)

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
"""Tests that actually run epiworld through epiworldpy."""

import numpy as np
import pytest
from flepimop2.axis import ResolvedShape
from flepimop2.parameter.abc import ModelStateSpecification, ParameterValue

from flepimop2_epiworld import _bridge
from flepimop2_epiworld._bridge import (
    RunnerConfig,
    load_constructor,
    make_runner,
    run_model,
)
from flepimop2_epiworld._initial_state import SeirCounts, SeirSeeding
from flepimop2_epiworld._models import MODEL_SPECS, EpiworldModelSpec
from flepimop2_epiworld.exceptions import EpiworldError

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


@pytest.mark.parametrize("spec", MODEL_SPECS.values(), ids=list(MODEL_SPECS))
def test_registry_matches_epiworldpy(spec: EpiworldModelSpec) -> None:
    """
    Every registered model must exist in epiworldpy with the declared states.

    This replaces the old Python/R registry parity check: epiworldpy itself is
    now the other half of the contract.
    """
    model = load_constructor(spec)(
        name="registry",
        n=10,
        prevalence=0.1,
        **dict.fromkeys(spec.parameters, 0.1),
    )
    assert tuple(model.get_states()) == spec.states


@pytest.mark.parametrize(
    "counts", REPRESENTATIVE_CASES + NAIVE_FORMULA_FAILURES, ids=str
)
def test_day_zero_matches_configuration_exactly(counts: SeirCounts) -> None:
    """The configured initial conditions are what epiworld actually simulates."""
    result = _run(counts, [0.0, 1.0, 2.0])
    assert result[0, 1:].astype(int).tolist() == list(counts)


def test_day_zero_is_exact_for_random_populations() -> None:
    """
    Fuzz the seeding mapping against real epiworld.

    `run_model` raises on any day-0 drift, so reaching the end is the check.
    """
    rng = np.random.default_rng(20260929)
    for _ in range(100):
        n = int(rng.integers(1, 100_000))
        cuts = np.sort(rng.integers(0, n + 1, size=3))
        counts = SeirCounts(*np.diff([0, *cuts, n]).astype(int).tolist())
        run_model(
            MODEL_SPECS["seirconn"],
            counts=counts,
            parameters=PARAMETERS,
            days=[0],
            ndays=0,
            seed=1,
            model_name="fuzz",
        )


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


def test_run_keeps_stdout_empty(capfd: pytest.CaptureFixture[str]) -> None:
    """Epiworld prints a progress bar unless `verbose_off()` is called."""
    _run(SeirCounts(999, 0, 1, 0), [0.0, 5.0])
    assert not capfd.readouterr().out


def test_day_zero_drift_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A seeding regression must fail loudly, not simulate the wrong state."""
    counts = NAIVE_FORMULA_FAILURES[0]

    def naive(target: SeirCounts) -> SeirSeeding:
        n = sum(target)
        seeded = target.exposed + target.infected
        return SeirSeeding(
            n=n,
            prevalence=seeded / n,
            proportions=(
                target.infected / seeded,
                target.recovered / (target.susceptible + target.recovered),
            ),
        )

    monkeypatch.setattr(_bridge, "seir_seeding_arguments", naive)
    with pytest.raises(EpiworldError, match="Day-0 drift"):
        _run(counts, [0.0])


def test_unexpected_state_is_rejected() -> None:
    """A history naming a compartment outside the registry must not be dropped."""
    hist = {
        "dates": np.array([0, 0]),
        "states": {"values": np.array(["Susceptible", "Zombie"]), "indexes": [0, 1]},
        "counts": np.array([1, 1]),
    }
    with pytest.raises(EpiworldError, match="unexpected state"):
        _bridge._pivot_history(hist, MODEL_SPECS["seirconn"].states, 0)


def test_incomplete_history_is_rejected() -> None:
    """A missing (day, state) cell would otherwise surface as a NaN count."""
    hist = {
        "dates": np.array([0]),
        "states": {"values": np.array(["Susceptible"]), "indexes": [0]},
        "counts": np.array([1]),
    }
    with pytest.raises(EpiworldError, match="missing"):
        _bridge._pivot_history(hist, MODEL_SPECS["seirconn"].states, 0)

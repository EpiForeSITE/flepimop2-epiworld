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
"""The epiworldpy bridge: build a model, run it, and read back its history."""

__all__ = [
    "MAX_POPULATION",
    "MAX_SEED",
    "RunnerConfig",
    "load_constructor",
    "make_runner",
    "resolve_seed",
    "run_model",
    "spec_for_model_state",
]

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from flepimop2.parameter.abc import ModelStateSpecification, ParameterValue
from flepimop2.typing import Float64NDArray, IdentifierString, SystemProtocol

from flepimop2_epiworld._initial_state import SeirCounts, seir_seeding_arguments
from flepimop2_epiworld._models import MODEL_SPECS, EpiworldModelSpec
from flepimop2_epiworld._times import plan_days
from flepimop2_epiworld.exceptions import EpiworldError, EpiworldUnavailableError

MAX_SEED: Final = 2**31 - 1
"""
Largest seed epiworld accepts.

`Model::run` takes the seed as a C `int`, and a negative value means "keep the
current generator state" rather than "seed with this".
"""

MAX_POPULATION: Final = 2**24
"""
Largest population epiworld can seed exactly.

Prevalence is stored as C `float`, so beyond 2**24 consecutive integers are no
longer representable and the seeded count would drift.
"""

_COUNT_ATOL: Final = 1e-9


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    """
    Scalar settings the engine's runner closure captures.

    Deliberately a frozen dataclass of plain values rather than a reference to
    the engine: the closure is stored in a Pydantic private attribute, and
    `ModuleBase.patch` deep-copies modules, which recurses forever through a
    bound method.

    Attributes:
        seed: Fallback seed when the configuration supplies none.
        model_name: Name handed to the epiworld model constructor.
    """

    seed: int | None = None
    model_name: str = "flepimop2"


def load_constructor(spec: EpiworldModelSpec) -> Any:  # ruff: ignore[any-type]
    """
    Look up a model's class in `epiworldpy.epimodels`.

    Args:
        spec: The model registry entry.

    Returns:
        The epiworldpy model class.

    Raises:
        EpiworldUnavailableError: If epiworldpy cannot be imported, does not
            provide the model, or predates the `initial_states` binding.
    """
    try:
        from epiworldpy import epimodels  # ruff: ignore[import-outside-top-level]
    except ImportError as exc:
        msg = (
            "Could not import epiworldpy, which the epiworld engine runs models "
            "with. Reinstall flepimop2-epiworld, or install it with "
            "`uv add epiworldpy`."
        )
        raise EpiworldUnavailableError(msg) from exc
    constructor = getattr(epimodels, spec.constructor, None)
    if constructor is None:
        msg = (
            f"The installed epiworldpy has no `epimodels.{spec.constructor}`, "
            f"which the {spec.key!r} model needs. Upgrade epiworldpy."
        )
        raise EpiworldUnavailableError(msg)
    if not hasattr(constructor, "initial_states"):
        msg = (
            "The installed epiworldpy does not expose `initial_states()`, "
            "without which the configured Exposed and Recovered counts cannot "
            "be seeded. Upgrade epiworldpy."
        )
        raise EpiworldUnavailableError(msg)
    return constructor


def spec_for_model_state(
    model_state: ModelStateSpecification | None,
) -> EpiworldModelSpec:
    """
    Recover the model registry entry from a system's model-state declaration.

    `EngineABC.run` hands the engine a `ModelStateSpecification` but not the
    system itself, so the model is identified by matching the declared
    parameter names and compartment labels against the registry. Matching
    structurally keeps the engine decoupled from the system class.

    Args:
        model_state: The specification declared by the system.

    Returns:
        The matching registry entry.

    Raises:
        EpiworldError: If `model_state` is absent or matches no known model.
    """
    if model_state is None:
        msg = (
            "The epiworld engine requires a system that declares `model_state`, "
            "naming the parameters that hold each compartment's initial count."
        )
        raise EpiworldError(msg)
    for spec in MODEL_SPECS.values():
        if (
            tuple(model_state.parameter_names) == spec.state_parameters
            and tuple(model_state.labels or ()) == spec.states
        ):
            return spec
    known = ", ".join(
        f"{spec.key} ({'/'.join(spec.state_parameters)})"
        for spec in MODEL_SPECS.values()
    )
    msg = (
        "The system's model_state does not match any epiworld model known to "
        f"this provider. Got parameters {tuple(model_state.parameter_names)} "
        f"with labels {tuple(model_state.labels or ())}; known models are: "
        f"{known}."
    )
    raise EpiworldError(msg)


def _as_count(name: str, value: ParameterValue) -> int:
    """
    Read a parameter as a non-negative whole number of agents.

    Args:
        name: Parameter name, for diagnostics.
        value: The sampled parameter.

    Returns:
        The count as an integer.

    Raises:
        EpiworldError: If the value is not a non-negative scalar whole number.
    """
    if value.shape.sizes != ():
        msg = (
            f"The epiworld engine needs a scalar count for '{name}', but it "
            f"resolved to shape {value.shape.sizes} over axes "
            f"{value.shape.axis_names}. Stratified populations are not "
            "supported yet."
        )
        raise EpiworldError(msg)
    raw = value.item()
    if raw < 0 or abs(raw - round(raw)) > _COUNT_ATOL:
        msg = (
            f"The epiworld engine needs '{name}' to be a non-negative whole "
            f"number of agents; got {raw}."
        )
        raise EpiworldError(msg)
    return round(raw)


def resolve_seed(
    params: Mapping[IdentifierString, ParameterValue], fallback: int | None
) -> int:
    """
    Decide which seed to hand epiworld.

    A seed is always passed explicitly. Leaving it out would make `run()` keep
    drawing from the generator's current state, so results would stop being
    reproducible without any visible sign.

    Args:
        params: Resolved stepper parameters, possibly holding `seed`.
        fallback: The engine's configured seed, if any.

    Returns:
        The seed to use.

    Raises:
        EpiworldError: If the seed is outside epiworld's non-negative `int` range.
    """
    if (configured := params.get("seed")) is not None:
        seed = round(configured.item())
    elif fallback is not None:
        seed = fallback
    else:
        seed = 0
        warnings.warn(
            "No `seed` parameter is configured and the epiworld engine has no "
            "`seed:` option set, so every replicate would be identical. "
            "Defaulting to seed 0. Set `parameter: seed:` for one run, or "
            "sweep it with a `scenario: grid` to get independent replicates.",
            UserWarning,
            stacklevel=2,
        )
    if not 0 <= seed <= MAX_SEED:
        msg = (
            f"The epiworld seed must be between 0 and {MAX_SEED} because epiworld "
            f"takes it as a C int and treats negative values specially; got {seed}."
        )
        raise EpiworldError(msg)
    return seed


def _pivot_history(
    hist: Mapping[str, Any], states: tuple[str, ...], ndays: int
) -> Float64NDArray:
    """
    Turn epiworldpy's long-form history into a `(ndays + 1, n_states)` matrix.

    `DataBase.get_hist_total()` returns parallel `dates` and `counts` arrays and
    a factor-encoded `states` entry (`values` holding the names, `indexes`
    pointing into them). Columns follow `states`, the registry's declared
    order, rather than whatever order epiworld reports.

    Args:
        hist: The mapping returned by `get_hist_total()`.
        states: Compartment names in the declared order.
        ndays: Number of simulated days.

    Returns:
        The compartment counts, one row per day starting at day 0.

    Raises:
        EpiworldError: If the history names an unexpected state, falls outside
            `0..ndays`, or leaves a `(day, state)` cell empty.
    """
    names = [str(name) for name in hist["states"]["values"]]
    if unexpected := sorted(set(names) - set(states)):
        msg = f"epiworld reported unexpected state(s): {', '.join(unexpected)}."
        raise EpiworldError(msg)
    column = np.array([states.index(name) for name in names], dtype=np.intp)

    dates = np.asarray(hist["dates"], dtype=np.intp)
    if dates.size and (dates.min() < 0 or dates.max() > ndays):
        msg = f"epiworld history contains dates outside 0..{ndays}."
        raise EpiworldError(msg)

    wide = np.full((ndays + 1, len(states)), np.nan, dtype=np.float64)
    wide[dates, column[np.asarray(hist["states"]["indexes"], dtype=np.intp)]] = (
        np.asarray(hist["counts"], dtype=np.float64)
    )
    if bool(np.isnan(wide).any()):
        msg = "epiworld history has missing (day, state) cells."
        raise EpiworldError(msg)
    return wide


def run_model(  # ruff: ignore[too-many-arguments]
    spec: EpiworldModelSpec,
    *,
    counts: SeirCounts,
    parameters: Mapping[str, float],
    days: Sequence[int],
    ndays: int,
    seed: int,
    model_name: str,
) -> Float64NDArray:
    """
    Run one epiworld simulation and return the requested days.

    Args:
        spec: The model registry entry.
        counts: Target initial compartment counts.
        parameters: The model's rate parameters.
        days: Requested days, in caller order.
        ndays: Number of days to simulate.
        seed: The epiworld seed.
        model_name: Name for the epiworld model constructor.

    Returns:
        A `(len(days), 1 + n_states)` array with the day in column 0.

    Raises:
        EpiworldError: If a parameter is missing, the population exceeds what
            epiworld can seed exactly, epiworld fails, or the realized day-0
            counts disagree with `counts`.
    """
    if missing := [name for name in spec.parameters if name not in parameters]:
        msg = f"Missing epiworld model parameter(s): {', '.join(missing)}."
        raise EpiworldError(msg)
    seeding = seir_seeding_arguments(counts)
    if seeding.n > MAX_POPULATION:
        msg = (
            f"The configured population is {seeding.n}, above the "
            f"{MAX_POPULATION} ceiling where epiworld's float32 prevalence can "
            "still represent every integer exactly, so the seeded counts would "
            "drift from the configuration."
        )
        raise EpiworldError(msg)

    constructor = load_constructor(spec)
    try:
        model = constructor(
            name=model_name,
            n=seeding.n,
            prevalence=seeding.prevalence,
            **{name: float(parameters[name]) for name in spec.parameters},
        )
        model.initial_states(list(seeding.proportions))
        # Otherwise epiworld prints a progress bar to stdout.
        model.verbose_off()
        model.run(ndays, seed)
    except Exception as exc:
        msg = (
            f"epiworld failed while running model {spec.key!r} with "
            f"n={seeding.n} for {ndays} days (seed {seed}): {exc}"
        )
        raise EpiworldError(msg) from exc
    reported_states = tuple(str(state) for state in model.get_states())
    hist = model.get_db().get_hist_total()

    # Guard against an epiworldpy release whose state vector no longer matches.
    if reported_states != spec.states:
        msg = (
            f"epiworld reports states {reported_states} but the registry "
            f"declares {spec.states}; this epiworldpy version is incompatible "
            "with the provider."
        )
        raise EpiworldError(msg)

    wide = _pivot_history(hist, spec.states, ndays)

    # The seeding arithmetic is nudged precisely so that epiworld's truncation
    # lands on these counts. If it ever does not, fail loudly rather than
    # silently simulating different initial conditions than were configured.
    if wide[0].tolist() != [float(count) for count in counts]:
        realized = "/".join(str(int(count)) for count in wide[0])
        msg = (
            f"Day-0 drift: configured {'/'.join(map(str, counts))} but epiworld "
            f"realized {realized} (n={seeding.n}). This is a rounding "
            "regression in the initial-state mapping."
        )
        raise EpiworldError(msg)

    index = np.asarray(days, dtype=np.intp)
    return np.column_stack([index.astype(np.float64), wide[index]])


def make_runner(config: RunnerConfig) -> Any:  # ruff: ignore[any-type]
    """
    Build the engine runner closure.

    The returned callable matches `EngineProtocol`. It ignores the `stepper`
    argument entirely: epiworld owns its own simulation loop, so there is
    nothing for flepimop2 to step.

    A plain closure over `config` is returned rather than a bound method
    because the engine stores it in a Pydantic private attribute, and
    deep-copying a module holding a bound method to itself recurses forever.

    Args:
        config: Scalar settings to capture.

    Returns:
        A callable conforming to `flepimop2.engine.abc.EngineProtocol`.
    """

    def runner(
        stepper: SystemProtocol,  # ruff: ignore[unused-function-argument]
        times: Float64NDArray,
        initial_state: dict[IdentifierString, ParameterValue],
        params: Mapping[IdentifierString, ParameterValue],
        model_state: ModelStateSpecification | None = None,
        **kwargs: Any,  # ruff: ignore[unused-function-argument]
    ) -> Float64NDArray:
        spec = spec_for_model_state(model_state)
        counts = SeirCounts(
            *(_as_count(name, initial_state[name]) for name in spec.state_parameters)
        )
        ndays, days = plan_days(times)
        data = run_model(
            spec,
            counts=counts,
            parameters={
                name: params[name].item() for name in spec.parameters if name in params
            },
            days=days,
            ndays=ndays,
            seed=resolve_seed(params, config.seed),
            model_name=config.model_name,
        )
        # Echo back the caller's own float64 times so they round-trip exactly.
        data[:, 0] = times
        return data

    return runner

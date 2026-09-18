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
"""The `Rscript` bridge: build a request, run the driver, parse the response."""

__all__ = [
    "DRIVER_PATH",
    "MAX_POPULATION",
    "PROTOCOL",
    "RunnerConfig",
    "build_request",
    "invoke_driver",
    "make_runner",
    "resolve_seed",
    "spec_for_model_state",
]

import json
import subprocess
import tempfile
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from flepimop2.parameter.abc import ModelStateSpecification, ParameterValue
from flepimop2.typing import Float64NDArray, IdentifierString, SystemProtocol

from flepimop2_epiworldr._initial_state import SeirCounts, seir_seeding_arguments
from flepimop2_epiworldr._models import MODEL_SPECS, EpiworldrModelSpec
from flepimop2_epiworldr._rscript import resolve_rscript, subprocess_env
from flepimop2_epiworldr._times import plan_days
from flepimop2_epiworldr.exceptions import EpiworldrError

PROTOCOL: Final = 1
"""Version of the JSON request contract understood by the shipped R driver."""

DRIVER_PATH: Final[Path] = Path(__file__).resolve().parent / "r" / "run_epiworldr.R"
"""
Filesystem path to the R driver.

Resolved eagerly from `__file__` rather than through `importlib.resources`
because every run needs a stable path to hand to a subprocess, and wheels are
always installed unzipped.
"""

MAX_SEED: Final = 2**31 - 1
"""R's `as.integer` ceiling; anything larger becomes `NA` with only a warning."""

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
        rscript: Explicit `Rscript` path, or `None` to discover one.
        r_libs: Extra R library directories.
        timeout: Seconds to allow a single epiworldR run.
        seed: Fallback seed when the configuration supplies none.
        model_name: Name handed to the epiworldR model constructor.
        keep_temp: Keep the request/response files behind on failure.
    """

    rscript: Path | None = None
    r_libs: tuple[Path, ...] = ()
    timeout: float = 300.0
    seed: int | None = None
    model_name: str = "flepimop2"
    keep_temp: bool = False


def spec_for_model_state(
    model_state: ModelStateSpecification | None,
) -> EpiworldrModelSpec:
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
        EpiworldrError: If `model_state` is absent or matches no known model.
    """
    if model_state is None:
        msg = (
            "The epiworldr engine requires a system that declares `model_state`, "
            "naming the parameters that hold each compartment's initial count."
        )
        raise EpiworldrError(msg)
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
        "The system's model_state does not match any epiworldR model known to "
        f"this provider. Got parameters {tuple(model_state.parameter_names)} "
        f"with labels {tuple(model_state.labels or ())}; known models are: "
        f"{known}."
    )
    raise EpiworldrError(msg)


def _as_count(name: str, value: ParameterValue) -> int:
    """
    Read a parameter as a non-negative whole number of agents.

    Args:
        name: Parameter name, for diagnostics.
        value: The sampled parameter.

    Returns:
        The count as an integer.

    Raises:
        EpiworldrError: If the value is not a non-negative scalar whole number.
    """
    if value.shape.sizes != ():
        msg = (
            f"The epiworldr engine needs a scalar count for '{name}', but it "
            f"resolved to shape {value.shape.sizes} over axes "
            f"{value.shape.axis_names}. Stratified populations are not "
            "supported yet."
        )
        raise EpiworldrError(msg)
    raw = value.item()
    if raw < 0 or abs(raw - round(raw)) > _COUNT_ATOL:
        msg = (
            f"The epiworldr engine needs '{name}' to be a non-negative whole "
            f"number of agents; got {raw}."
        )
        raise EpiworldrError(msg)
    return round(raw)


def resolve_seed(
    params: Mapping[IdentifierString, ParameterValue], fallback: int | None
) -> int:
    """
    Decide which seed to hand epiworldR.

    A seed is always passed explicitly. Leaving it to R would make `run()` draw
    from R's own RNG, so results would stop being reproducible without any
    visible sign.

    Args:
        params: Resolved stepper parameters, possibly holding `seed`.
        fallback: The engine's configured seed, if any.

    Returns:
        The seed to use.

    Raises:
        EpiworldrError: If the seed is outside R's 32-bit signed integer range.
    """
    if (configured := params.get("seed")) is not None:
        seed = round(configured.item())
    elif fallback is not None:
        seed = fallback
    else:
        seed = 0
        warnings.warn(
            "No `seed` parameter is configured and the epiworldr engine has no "
            "`seed:` option set, so every replicate would be identical. "
            "Defaulting to seed 0. Set `parameter: seed:` for one run, or "
            "sweep it with a `scenario: grid` to get independent replicates.",
            UserWarning,
            stacklevel=2,
        )
    if not 0 <= seed <= MAX_SEED:
        msg = (
            f"The epiworldR seed must be between 0 and {MAX_SEED} because R "
            f"coerces it with `as.integer`; got {seed}."
        )
        raise EpiworldrError(msg)
    return seed


def build_request(  # ruff: ignore[too-many-arguments]
    spec: EpiworldrModelSpec,
    *,
    counts: SeirCounts,
    parameters: Mapping[str, float],
    days: list[int],
    ndays: int,
    seed: int,
    model_name: str,
) -> dict[str, Any]:
    """
    Assemble the JSON-serializable request for the R driver.

    Args:
        spec: The model registry entry.
        counts: Target initial compartment counts.
        parameters: The model's rate parameters.
        days: Requested days, in caller order.
        ndays: Number of days to simulate.
        seed: The epiworldR seed.
        model_name: Name for the epiworldR model constructor.

    Returns:
        A mapping of plain Python values ready for `json.dumps`.

    Raises:
        EpiworldrError: If the population exceeds what epiworld can seed exactly.
    """
    seeding = seir_seeding_arguments(counts)
    if seeding.n > MAX_POPULATION:
        msg = (
            f"The configured population is {seeding.n}, above the "
            f"{MAX_POPULATION} ceiling where epiworld's float32 prevalence can "
            "still represent every integer exactly, so the seeded counts would "
            "drift from the configuration."
        )
        raise EpiworldrError(msg)
    return {
        "protocol": PROTOCOL,
        "model": spec.key,
        "model_name": str(model_name),
        "states": list(spec.states),
        "initial_state": dict(zip(spec.states, counts, strict=True)),
        "n": seeding.n,
        "prevalence": seeding.prevalence,
        "proportions": list(seeding.proportions),
        "parameters": {name: float(value) for name, value in parameters.items()},
        "ndays": ndays,
        "times": [int(day) for day in days],
        "seed": seed,
    }


def invoke_driver(
    request: dict[str, Any], config: RunnerConfig, n_states: int
) -> Float64NDArray:
    """
    Run the R driver on a request and read back its result matrix.

    Args:
        request: The request mapping from `build_request`.
        config: Runner settings.
        n_states: Expected number of compartment columns.

    Returns:
        A `(len(times), 1 + n_states)` array with time in column 0.

    Raises:
        EpiworldrError: If the driver is missing, exits non-zero, times out, or
            returns a result of unexpected shape.
    """
    if not DRIVER_PATH.is_file():
        msg = (
            f"The epiworldR driver script is missing from {DRIVER_PATH}. The "
            "installed flepimop2-epiworldr wheel appears to be incomplete; "
            "reinstall it."
        )
        raise EpiworldrError(msg)

    rscript = resolve_rscript(config.rscript)
    n_times = len(request["times"])

    with tempfile.TemporaryDirectory(
        prefix="flepimop2-epiworldr-", delete=not config.keep_temp
    ) as tmp:
        tmp_path = Path(tmp)
        request_path = tmp_path / "request.json"
        response_path = tmp_path / "response.csv"
        request_path.write_text(json.dumps(request, allow_nan=False), encoding="utf-8")

        command = [
            str(rscript),
            "--vanilla",
            str(DRIVER_PATH),
            str(request_path),
            str(response_path),
        ]
        try:
            proc = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=config.timeout,
                cwd=tmp_path,
                env=subprocess_env(config.r_libs),
            )
        except subprocess.TimeoutExpired as exc:
            msg = (
                f"epiworldR did not finish within {config.timeout}s while "
                f"running model {request['model']!r} with n={request['n']} for "
                f"{request['ndays']} days. Raise the engine's `timeout:` option, "
                "or reduce the population or run length."
            )
            raise EpiworldrError(msg) from exc

        if proc.returncode != 0:
            raise EpiworldrError(_failure_message(request, command, proc))
        if proc.stdout:
            msg = (
                "The epiworldR driver wrote to stdout, which it must keep empty "
                f"for the result contract:\n{proc.stdout[:2000]}"
            )
            raise EpiworldrError(msg)

        data = np.loadtxt(response_path, delimiter=",", ndmin=2).astype(np.float64)

    expected = (n_times, 1 + n_states)
    if data.shape != expected:
        msg = (
            f"The epiworldR driver returned a {data.shape} result but "
            f"{expected} was expected for {n_times} time(s) and {n_states} "
            "compartments."
        )
        raise EpiworldrError(msg)
    return data


def _failure_message(
    request: dict[str, Any],
    command: list[str],
    proc: subprocess.CompletedProcess[str],
) -> str:
    """
    Render a non-zero driver exit into an actionable message.

    Args:
        request: The request that was sent.
        command: The command line that was run.
        proc: The completed subprocess.

    Returns:
        The message for the raised `EpiworldrError`.
    """
    stderr_tail = "\n".join(
        f"    {line}" for line in proc.stderr.strip().splitlines()[-40:]
    )
    echo = json.dumps(request)[:400]
    summary = (
        f"Rscript exited {proc.returncode} while running epiworldR model "
        f"{request['model']!r}."
    )
    parts = [summary, f"  command: {' '.join(command)}"]
    if stderr_tail:
        parts.append(f"  stderr:\n{stderr_tail}")
    if proc.stdout.strip():
        parts.append(f"  stdout: {proc.stdout.strip()[:500]}")
    hint = (
        "  Set `keep_temp: true` on the engine to preserve the request and "
        "response files for inspection."
    )
    parts.extend((f"  request (truncated): {echo}", hint))
    return "\n".join(parts)


def make_runner(config: RunnerConfig) -> Any:  # ruff: ignore[any-type]
    """
    Build the engine runner closure.

    The returned callable matches `EngineProtocol`. It ignores the `stepper`
    argument entirely: epiworldR owns its own simulation loop, so there is
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
        request = build_request(
            spec=spec,
            counts=counts,
            parameters={
                name: params[name].item() for name in spec.parameters if name in params
            },
            days=days,
            ndays=ndays,
            seed=resolve_seed(params, config.seed),
            model_name=config.model_name,
        )
        data = invoke_driver(request, config, len(spec.states))
        # Echo back the caller's own float64 times so they round-trip exactly.
        data[:, 0] = times
        return data

    return runner

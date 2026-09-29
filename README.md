# flepimop2-epiworld


A [flepimop2](https://github.com/ACCIDDA/flepimop2) external provider
that runs [epiworld](https://github.com/UofUEpiBio/epiworld) agent-based
models from a flepimop2 configuration, through the
[epiworldpy](https://github.com/UofUEpiBio/epiworldpy) Python bindings.

## Status

Supports epiworld’s `ModelSEIRCONN`. Other models plug into the same
seam; see [Adding a model](#adding-a-model).

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)

epiworldpy ships prebuilt wheels, so there is no compiler, R, or other
toolchain to install.

## Install

``` bash
uv add flepimop2-epiworld
```

## Use

``` yaml
system:
  - module: epiworld
    model: seirconn
    state_change: state

engine:
  - module: epiworld

backend:
  - module: csv

parameter:
  s0: 9700      # initial compartment counts
  e0: 120
  i0: 60
  r0: 120
  contact_rate: 6.0
  transmission_rate: 0.08
  incubation_days: 3.0
  recovery_rate: 0.2
  seed: 1912

simulate:
  demo:
    times: '0:1:150'
```

`flepimop2 simulate config.yaml` writes the usual `(time, S, E, I, R)`
CSV.

### Replicates and confidence intervals

flepimop2 has no replicate concept, and does not need one: `simulate`
already runs one simulation per scenario tuple and writes each to its
own file. Sweeping `seed` over a grid gives independent epiworld
replicates, which a `process:` step can aggregate:

``` yaml
scenarios:
  - module: grid
    parameters:
      seed: [1, 2, 3, 4, 5]

simulate:
  replicates:
    times: '0:1:150'
    scenario: default
```

## Example

The folder
[`examples/seirconn-replicates`](examples/seirconn-replicates) contains
a complete project that produces a median and 95% interval plot. You can
look at the configuration file
[here](examples/seirconn-replicates/config.yaml). The following code
executes the simulation and processing steps:

``` bash
cd examples/seirconn-replicates
rm -f model_output/*.csv
uv run --group example flepimop2 simulate config.yaml
uv run --group example flepimop2 process config.yaml
```

    wrote figures/seirconn_ci.png from 20 replicates

We can look at the generated image:

<img src="examples/seirconn-replicates/figures/seirconn_ci.png"
style="width:70.0%" />

## How it works

epiworld is an agent-based model whose C++ core owns its own simulation
loop and tracks per-agent exposure clocks. It cannot be expressed as
flepimop2’s `f(time, state) -> state` stepper, so the work is split:

- **`EpiworldSystem`** is declarative. It names the compartments, the
  parameters holding their initial counts, and the model’s rate
  parameters, so flepimop2 can resolve them from the `parameter:`
  section.
- **`EpiworldEngine`** ignores the stepper and runs the whole simulation
  in-process through epiworldpy, translating the resulting compartment
  history back into flepimop2’s array contract.

Running in-process has no per-run startup cost. The flip side is that a
fault in epiworld’s C++ takes the flepimop2 process down with it, and a
run cannot be interrupted by a timeout.

### Initial conditions are exact

epiworld seeds a model from a population size, a prevalence
*proportion*, and an `initial_states()` proportion vector, not from
absolute counts. Recovering exact counts takes care, because epiworld
stores prevalence as a C `float` and truncates in two places. Passing
the bare ratio lands one agent short in roughly a third of
configurations. This provider adds a half unit before dividing so
truncation is exact, and the engine hard-fails if realized day-0 counts
ever disagree with the config. The test suite fuzzes this against real
epiworld runs.

## Adding a model

1.  Add an `EpiworldModelSpec` to `MODEL_SPECS` in
    `src/flepimop2_epiworld/_models.py` and widen `EpiworldModelKey`.
    Its `constructor` is the class name in `epiworldpy.epimodels`.
2.  Confirm the model’s `initial_states()` semantics — they differ per
    family — and extend the seeding mapping if it is not SEIR-shaped.

A test builds every registered model through epiworldpy and compares its
states with the registry, so a mistyped entry fails in CI rather than at
run time.

## Development

``` bash
uv sync --group dev
just dev        # ruff, mypy, tests
just example    # run the replicate example end to end
```

The integration test installs this package into a throwaway environment
via `flepimop2.testing`, which needs flepimop2 itself to be a *source*
install. The lockfile resolves flepimop2 from git, so point it at a
local checkout to run that test — otherwise it skips itself:

``` bash
uv pip install -e ../flepimop2
just integration
```

A [dev container](.devcontainer) is published to
`ghcr.io/epiforesite/flepimop2-epiworld`.

## License

GPL-3.0-or-later, as required for a flepimop2 provider. See
[LICENSE](LICENSE).

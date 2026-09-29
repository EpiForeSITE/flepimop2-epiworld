# Changelog

## Unreleased

### Added

- `flepimop2.system.epiworld` and `flepimop2.engine.epiworld`, letting a
  flepimop2 configuration run epiworld's `ModelSEIRCONN`.
- An `examples/seirconn-replicates` project showing stochastic replicates via a
  `scenario: grid` over `seed`, aggregated into a median and 95% interval.
- CI covering the full suite, including real epiworld runs, across Python
  3.11-3.14, plus an integration job, the example end to end, and a smoke job
  inside the published dev container.
- A dev container published to `ghcr.io/epiforesite/flepimop2-epiworld` and
  rebuilt weekly so it picks up base-image releases.

### Changed

- Models now run in-process through [epiworldpy](https://github.com/UofUEpiBio/epiworldpy)
  instead of an `Rscript` subprocess driving epiworldR. R is no longer needed
  anywhere, including the example's plotting step, which is now Python.
  Results are identical: for the README configuration, every day and
  compartment matches the epiworldR 0.17.0 output bit for bit.
- Renamed from `flepimop2-epiworldr` to `flepimop2-epiworld`: the distribution,
  the `flepimop2_epiworld` package, the `module: epiworld` config key, and the
  `Epiworld*` class names.
- Removed the engine's `rscript`, `r_libs`, `timeout`, `check_r`, and
  `keep_temp` options, which only applied to the R subprocess.

### Notes

- Initial compartment counts round-trip exactly. epiworld seeds from a
  prevalence proportion stored as a C `float` and truncates in two places, so
  the bare ratio loses an agent in roughly a third of configurations; the
  seeding fractions are nudged by half a unit to compensate, and the engine
  hard-fails if realized day-0 counts ever disagree with the configuration.
- Requires an epiworldpy that exposes `initial_states()`, without which the
  Exposed and Recovered counts cannot be seeded.

# Changelog

## Unreleased

### Added

- `flepimop2.system.epiworldr` and `flepimop2.engine.epiworldr`, letting a
  flepimop2 configuration run epiworldR's `ModelSEIRCONN`.
- An `examples/seirconn-replicates` project showing stochastic replicates via a
  `scenario: grid` over `seed`, aggregated into a median and 95% interval.
- CI covering an R-free matrix across Python 3.11-3.14, a single R-backed job,
  and a smoke job inside the published dev container.
- A dev container built on the same base image as epiworldR, published to
  `ghcr.io/epiforesite/flepimop2-epiworldr` and rebuilt weekly so it picks up
  new epiworldR and base-image releases.

### Notes

- Initial compartment counts round-trip exactly. epiworldR seeds from a
  prevalence proportion stored as a C `float` and truncates in two places, so
  the bare ratio loses an agent in roughly a third of configurations; the
  seeding fractions are nudged by half a unit to compensate, and the R driver
  hard-fails if realized day-0 counts ever disagree with the configuration.
- Requires epiworldR >= 0.14.0, the release that stopped drawing a random seed
  when one was supplied. Verified against both 0.14.0 (current CRAN) and 0.15.1.

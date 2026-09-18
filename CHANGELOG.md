# Changelog

## Unreleased

### Added

- `flepimop2.system.epiworldr` and `flepimop2.engine.epiworldr`, letting a
  flepimop2 configuration run epiworldR's `ModelSEIRCONN`.
- An `examples/seirconn-replicates` project showing stochastic replicates via a
  `scenario: grid` over `seed`, aggregated into a median and 95% interval.
- A dev container built on the same base image as epiworldR, published to
  `ghcr.io/epiforesite/flepimop2-epiworldr`.

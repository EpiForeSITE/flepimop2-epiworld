#!/usr/bin/env Rscript
# flepimop2-epiworldr: A flepimop2 external provider for epiworldR
# Copyright (C) 2026  George G. Vega Yon
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Usage:
#   Rscript --vanilla run_epiworldr.R <request.json> <response.csv>
#   Rscript --vanilla run_epiworldr.R --print-spec
#
# Contract with the Python side:
#   * stdout MUST stay empty in run mode.  The caller treats anything on stdout
#     as a bug, so every diagnostic goes to stderr prefixed "flepimop2-epiworldr: ".
#   * A non-zero exit means failure.  Exit codes: 1 generic, 2 bad usage,
#     3 unsupported protocol/model, 4 missing R dependency.
#   * The seeding arithmetic (population size, prevalence, initial_states
#     proportions) is computed in Python and passed in.  This script APPLIES it
#     and then verifies the realized day-0 counts, so the two languages cannot
#     silently disagree.

PROTOCOL <- 1L

die <- function(msg, status = 1L) {
  cat(sprintf("flepimop2-epiworldr: %s\n", msg), file = stderr())
  quit(save = "no", status = status)
}

## --- model registry (mirrors flepimop2_epiworldr/_models.py) ----------------
## A parity test compares this against the Python registry, so keep them in sync.
MODEL_SPECS <- list(
  seirconn = list(
    r_constructor = "ModelSEIRCONN",
    states     = c("Susceptible", "Exposed", "Infected", "Recovered"),
    parameters = c(
      "contact_rate", "transmission_rate", "incubation_days", "recovery_rate"
    ),
    init_arity = 2L,
    build = function(n, prevalence, p, model_name) {
      epiworldR::ModelSEIRCONN(
        name              = model_name,
        n                 = n,
        prevalence        = prevalence,
        contact_rate      = p[["contact_rate"]],
        transmission_rate = p[["transmission_rate"]],
        incubation_days   = p[["incubation_days"]],
        recovery_rate     = p[["recovery_rate"]]
      )
    }
  )
)

## --- long -> wide, in the DECLARED compartment order ------------------------
pivot_history <- function(hist, states, ndays) {
  dates <- 0:ndays
  out <- matrix(
    NA_real_,
    nrow = length(dates), ncol = length(states),
    dimnames = list(NULL, states)
  )
  di <- match(hist$date, dates)
  si <- match(hist$state, states)
  if (anyNA(si)) {
    die(sprintf(
      "model reported unexpected state(s): %s",
      paste(unique(hist$state[is.na(si)]), collapse = ", ")
    ))
  }
  if (anyNA(di)) die("model history contains dates outside 0..ndays")
  out[cbind(di, si)] <- as.numeric(hist$counts)
  if (anyNA(out)) die("model history has missing (date, state) cells")
  out
}

print_spec <- function() {
  spec <- lapply(MODEL_SPECS, function(s) {
    list(
      r_constructor = s$r_constructor,
      states        = s$states,
      parameters    = s$parameters,
      init_arity    = s$init_arity
    )
  })
  cat(jsonlite::toJSON(spec, auto_unbox = TRUE))
}

main <- function(argv) {
  if (!requireNamespace("epiworldR", quietly = TRUE)) {
    die(paste(
      "R package 'epiworldR' is not installed or not on .libPaths().",
      "Install it with install.packages('epiworldR'), or point the engine at",
      "the right library with its `r_libs:` option."
    ), 4L)
  }
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    die("R package 'jsonlite' is not installed or not on .libPaths().", 4L)
  }

  if (length(argv) == 1L && identical(argv[[1L]], "--print-spec")) {
    print_spec()
    return(invisible(NULL))
  }
  if (length(argv) != 2L) {
    die("usage: run_epiworldr.R <request.json> <response.csv>", 2L)
  }

  req <- jsonlite::fromJSON(argv[[1L]])

  if (!identical(as.integer(req$protocol), PROTOCOL)) {
    die(sprintf(
      "unsupported request protocol %s (this driver speaks %d)",
      req$protocol, PROTOCOL
    ), 3L)
  }

  spec <- MODEL_SPECS[[req$model]]
  if (is.null(spec)) {
    die(sprintf(
      "unsupported model '%s'; known models: %s",
      req$model, paste(names(MODEL_SPECS), collapse = ", ")
    ), 3L)
  }
  if (!identical(as.character(req$states), spec$states)) {
    die(sprintf(
      "request states (%s) disagree with this driver's registry (%s)",
      paste(req$states, collapse = "/"), paste(spec$states, collapse = "/")
    ), 3L)
  }

  target <- unlist(req$initial_state)[spec$states]
  if (anyNA(target)) die("initial_state is missing one or more compartments")
  if (any(target < 0)) die("initial_state has a negative compartment count")

  n <- as.integer(req$n)
  if (is.na(n) || n < 1L) die("n must be a positive integer")
  if (n != sum(target)) {
    die(sprintf(
      "n (%d) disagrees with the initial_state total (%d)", n, sum(target)
    ))
  }

  proportions <- as.numeric(req$proportions)
  if (length(proportions) != spec$init_arity) {
    die(sprintf(
      "model '%s' needs %d initial_states proportion(s); got %d",
      req$model, spec$init_arity, length(proportions)
    ), 3L)
  }

  missing_params <- setdiff(spec$parameters, names(req$parameters))
  if (length(missing_params)) {
    die(sprintf(
      "missing model parameter(s): %s", paste(missing_params, collapse = ", ")
    ))
  }

  ndays <- as.integer(req$ndays)
  if (is.na(ndays) || ndays < 0L) die("ndays must be a non-negative integer")

  # as.integer() on an out-of-range value only WARNS and yields NA; the
  # tryCatch below escalates warnings, but check explicitly for a clear message.
  seed <- suppressWarnings(as.integer(req$seed))
  if (is.na(seed)) die("seed must fit in a 32-bit signed integer")

  model <- spec$build(n, as.numeric(req$prevalence), req$parameters, req$model_name)
  epiworldR::initial_states(model, proportions)
  epiworldR::verbose_off(model) # otherwise a progress bar lands on stdout
  epiworldR::run(model, ndays = ndays, seed = seed) # seed is ALWAYS explicit

  # Guard against an epiworldR version whose state vector no longer matches.
  actual_states <- as.character(epiworldR::get_states(model))
  if (!identical(actual_states, spec$states)) {
    die(sprintf(
      paste(
        "epiworldR reports states (%s) but the registry declares (%s);",
        "this epiworldR version is incompatible with the driver"
      ),
      paste(actual_states, collapse = "/"), paste(spec$states, collapse = "/")
    ))
  }

  wide <- pivot_history(epiworldR::get_hist_total(model), spec$states, ndays)

  # The seeding arithmetic is nudged in Python precisely so that epiworld's
  # truncation lands on these counts.  If it ever does not, fail loudly rather
  # than silently simulating different initial conditions than were configured.
  day0 <- as.numeric(wide[1L, ])
  if (!identical(day0, as.numeric(target))) {
    die(sprintf(
      paste(
        "day-0 drift: configured %s but epiworldR realized %s (n=%d).",
        "This is a rounding regression in the initial-state mapping."
      ),
      paste(target, collapse = "/"), paste(day0, collapse = "/"), n
    ))
  }

  times <- as.integer(req$times)
  idx <- match(times, 0:ndays)
  if (anyNA(idx)) {
    die(sprintf(
      "requested time(s) outside 0..%d: %s",
      ndays, paste(times[is.na(idx)], collapse = ", ")
    ))
  }

  out <- cbind(times, wide[idx, , drop = FALSE])
  utils::write.table(
    unname(out),
    file = argv[[2L]], sep = ",", row.names = FALSE, col.names = FALSE
  )
  invisible(NULL)
}

# Warnings are escalated because several R coercions used above degrade to a
# warning plus NA rather than an error, which would corrupt a run silently.
tryCatch(
  main(commandArgs(trailingOnly = TRUE)),
  error   = function(e) die(conditionMessage(e)),
  warning = function(w) die(sprintf("warning escalated to error: %s", conditionMessage(w)))
)

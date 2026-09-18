#!/usr/bin/env Rscript
# Aggregate per-replicate flepimop2 CSVs into a median + 95% interval plot.
#
# Each replicate is one `scenario_<i>_simulate_<timestamp>.csv` written by
# `flepimop2 simulate`, holding a headerless (time, S, E, I, R) matrix.
suppressPackageStartupMessages({
  library(data.table)
  library(ggplot2)
})

.args <- commandArgs(trailingOnly = TRUE)
if (length(.args) != 2L) {
  stop("usage: summarize_replicates.R <results_dir> <output_png>")
}
results_dir <- .args[[1L]]
output_file <- .args[[2L]]
states <- c("Susceptible", "Exposed", "Infected", "Recovered")

files <- list.files(
  results_dir,
  pattern = "^scenario_[0-9]+_simulate_[0-9]{8}_[0-9]{6}\\.csv$",
  full.names = TRUE
)
if (!length(files)) stop("no replicate CSVs found in ", results_dir)

# flepimop2's RunMeta.timestamp is evaluated once at import, so every scenario
# in a single `flepimop2 simulate` invocation shares one timestamp. Keeping
# only the newest batch stops a re-run from being pooled with the previous one.
stamps <- sub("^.*_simulate_([0-9]{8}_[0-9]{6})\\.csv$", "\\1", basename(files))
files <- files[stamps == max(stamps)]

dt <- rbindlist(lapply(files, fread), idcol = "replicate")
setnames(dt, c("replicate", "time", states))

long <- melt(
  dt,
  id.vars = c("replicate", "time"),
  variable.name = "compartment",
  value.name = "count"
)

ribbon <- long[, .(
  lo  = quantile(count, 0.025, names = FALSE),
  med = median(count),
  hi  = quantile(count, 0.975, names = FALSE)
), by = .(time, compartment)]

p <- ggplot(ribbon, aes(x = time)) +
  geom_ribbon(aes(ymin = lo, ymax = hi, fill = compartment), alpha = 0.25) +
  geom_line(aes(y = med, colour = compartment), linewidth = 0.7) +
  labs(
    x = "day", y = "agents",
    title = "epiworldR ModelSEIRCONN via flepimop2",
    subtitle = sprintf(
      "median and 95%% interval across %d replicates", length(files)
    ),
    colour = "compartment", fill = "compartment"
  ) +
  theme_bw()

dir.create(dirname(output_file), recursive = TRUE, showWarnings = FALSE)
ggsave(output_file, p, width = 10, height = 6, dpi = 150)
cat(sprintf("wrote %s from %d replicates\n", output_file, length(files)))

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
"""
Aggregate per-replicate flepimop2 CSVs into a median + 95% interval plot.

Each replicate is one `scenario_<i>_simulate_<timestamp>.csv` written by
`flepimop2 simulate`, holding a headerless (time, S, E, I, R) matrix.

Usage:
    python summarize_replicates.py <results_dir> <output_png>
"""

import re
import sys
from pathlib import Path

import matplotlib as mpl
import numpy as np

mpl.use("Agg")

import matplotlib.pyplot as plt

STATES = ("Susceptible", "Exposed", "Infected", "Recovered")
REPLICATE_FILE = re.compile(r"^scenario_\d+_simulate_(\d{8}_\d{6})\.csv$")
USAGE = "usage: summarize_replicates.py <results_dir> <output_png>"


def newest_batch(results_dir: Path) -> list[Path]:
    """
    Find the replicate CSVs from the most recent `flepimop2 simulate` call.

    flepimop2's `RunMeta.timestamp` is evaluated once at import, so every
    scenario in a single invocation shares one timestamp. Keeping only the
    newest batch stops a re-run from being pooled with the previous one.

    Args:
        results_dir: Directory holding the backend's CSV output.

    Returns:
        The replicate files from the newest batch, sorted by name.

    Raises:
        SystemExit: If no replicate CSVs are found.
    """
    stamped = {
        path: match.group(1)
        for path in results_dir.iterdir()
        if (match := REPLICATE_FILE.match(path.name))
    }
    if not stamped:
        msg = f"no replicate CSVs found in {results_dir}"
        raise SystemExit(msg)
    newest = max(stamped.values())
    return sorted(path for path, stamp in stamped.items() if stamp == newest)


def main(results_dir: Path, output_file: Path) -> None:
    """
    Plot the median and 95% interval of each compartment across replicates.

    Args:
        results_dir: Directory holding the backend's CSV output.
        output_file: Where to write the PNG.
    """
    files = newest_batch(results_dir)
    # Shape (replicate, time, 1 + state).
    runs = np.stack([np.loadtxt(path, delimiter=",", ndmin=2) for path in files])
    time = runs[0, :, 0]
    lo, med, hi = np.quantile(runs[:, :, 1:], [0.025, 0.5, 0.975], axis=0)

    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    for column, state in enumerate(STATES):
        (line,) = ax.plot(time, med[:, column], linewidth=1.2, label=state)
        ax.fill_between(
            time, lo[:, column], hi[:, column], color=line.get_color(), alpha=0.25
        )
    ax.set_xlabel("day")
    ax.set_ylabel("agents")
    ax.set_title(
        "epiworld ModelSEIRCONN via flepimop2\n"
        f"median and 95% interval across {len(files)} replicates"
    )
    ax.legend(title="compartment")
    ax.grid(visible=True, alpha=0.3)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_file, bbox_inches="tight")
    sys.stdout.write(f"wrote {output_file} from {len(files)} replicates\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(USAGE)
    main(Path(sys.argv[1]), Path(sys.argv[2]))

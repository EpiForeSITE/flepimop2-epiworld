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
"""
End-to-end test of the provider as a real installed package.

This installs flepimop2-epiworldr into a throwaway virtual environment and
drives it through the `flepimop2` CLI, which is the only way to prove that
namespace-package discovery, the packaged R driver, and the CLI all work
together in an environment that is not this repo's checkout.
"""

import os
import subprocess
import sys
from pathlib import Path

import flepimop2.testing
import numpy as np
import pytest
from flepimop2.testing import external_provider_package, flepimop2_run

from tests.conftest import requires_epiworldr

PROVIDER_ROOT = Path(__file__).resolve().parents[2]

# `flepimop2.testing` builds its throwaway project by pip-installing flepimop2
# from a source checkout, which it locates by walking up from its own file.
requires_flepimop2_source = pytest.mark.skipif(
    not (
        Path(flepimop2.testing.__file__).resolve().parents[2] / "pyproject.toml"
    ).is_file(),
    reason="flepimop2 must be installed from a source checkout",
)

CONFIG = """---
name: epiworldr-integration
system:
  - module: epiworldr
    state_change: state
engine:
  - module: epiworldr
backend:
  - module: csv
    root: ./model_output
parameter:
  s0: 9700
  e0: 120
  i0: 60
  r0: 120
  contact_rate: 6.0
  transmission_rate: 0.08
  incubation_days: 3.0
  recovery_rate: 0.2
scenarios:
  - module: grid
    parameters:
      seed: [1, 2, 3]
simulate:
  replicates:
    times: '0:1:10'
    scenario: default
"""


@pytest.fixture
def working_python_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Put the running interpreter first on PATH.

    `flepimop2.testing` resolves the interpreter for its throwaway venv with
    `shutil.which("python")`, which a pyenv shim for an uninstalled version can
    shadow with something that exits 127.
    """
    monkeypatch.setenv(
        "PATH", os.pathsep.join([str(Path(sys.executable).parent), os.environ["PATH"]])
    )


@requires_epiworldr
@requires_flepimop2_source
@pytest.mark.usefixtures("working_python_on_path")
def test_provider_runs_through_the_cli(tmp_path: Path) -> None:
    """A freshly installed provider must be discoverable and runnable."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG, encoding="utf-8")

    # `external_provider_package` builds the venv and installs flepimop2 from
    # its source checkout, which is all we want from it here. The provider
    # itself is installed separately, for two reasons: its `copy_files` path
    # only packages `src/flepimop2`, so it would drop the shared bridge package
    # and the R driver; and its generated pyproject omits
    # `tool.hatch.metadata.allow-direct-references`, so a PEP 508 direct
    # reference in `dependencies` is rejected by hatchling.
    venv_python = external_provider_package(tmp_path)
    subprocess.run(
        [venv_python, "-m", "pip", "install", str(PROVIDER_ROOT)],
        capture_output=True,
        text=True,
        check=True,
    )
    (tmp_path / "model_output").mkdir(exist_ok=True)

    result = flepimop2_run("simulate", args=["config.yaml"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    outputs = sorted((tmp_path / "model_output").glob("scenario_*_simulate_*.csv"))
    assert len(outputs) == 3

    data = np.loadtxt(outputs[0], delimiter=",")
    assert data.shape == (11, 5)
    np.testing.assert_array_equal(data[0, 1:], [9700, 120, 60, 120])
    assert np.all(data[:, 1:].sum(axis=1) == 10000)

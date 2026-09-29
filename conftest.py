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
"""Pytest test configuration."""

# ruff: file-ignore[docstring-missing-returns]

from importlib import import_module
from pathlib import Path

import pytest
from _pytest.doctest import DoctestModule


def _find_repo_root(start: Path) -> Path:
    """
    Find the repository root by searching for a parent with `pyproject.toml`.

    Args:
        start: The starting directory to search from.

    Returns:
        The path to the repository root directory.

    Raises:
        FileNotFoundError: If no repository root is found.

    """
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    msg = f"Could not find repository root from {start} (missing `pyproject.toml`)."
    raise FileNotFoundError(msg)


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
SOURCE_ROOT = REPO_ROOT / "src"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """
    Get the repository root directory containing `pyproject.toml`.

    Returns:
        The path to the repository root directory.

    """
    return REPO_ROOT


def _module_name_for(file_path: Path) -> str:
    """
    Derive a module's real dotted name from its path under `src/`.

    Pytest's own name inference collapses the two leaf modules both named
    `epiworld` (one under `flepimop2/system/`, one under `flepimop2/engine/`)
    onto each other and fails collection with an import-file-mismatch. Deriving
    the name from the path avoids that.

    Importantly this returns the *canonical* name rather than a synthetic one,
    so doctests share class objects with the rest of the suite. Importing the
    same file twice under two names would give, for example, two distinct
    `EpiworldError` classes and make `issubclass` checks quietly fail.

    Args:
        file_path: Path to a Python source file under `src/`.

    Returns:
        The dotted module name.
    """
    relative_path = file_path.relative_to(SOURCE_ROOT)
    parts = list(relative_path.parts)
    parts[-1] = relative_path.stem
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


class SourceDoctestModule(DoctestModule):
    """Doctest collector that imports source modules by their real dotted name."""

    def _getobj(self) -> object:
        return import_module(_module_name_for(self.path))


def pytest_collect_file(
    file_path: Path, parent: pytest.Collector
) -> pytest.Collector | None:
    """Collect doctests from source modules by path."""
    if file_path.suffix == ".py" and file_path.is_relative_to(SOURCE_ROOT):
        return SourceDoctestModule.from_parent(parent, path=file_path)
    return None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Automatically mark tests in tests/integration as integration tests.

    Args:
        items: The list of collected pytest items to modify.

    """
    integration_prefix = "tests/integration/"
    marker = pytest.mark.integration
    for item in items:
        if item.nodeid.startswith(integration_prefix):
            item.add_marker(marker)

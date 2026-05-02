"""helm lint — must pass cleanly on every PR. No cluster needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers.chart_yaml import lint


@pytest.mark.chart
def test_helm_lint_clean(chart_path: Path) -> None:
    out = lint(chart_path)
    # `helm lint` allows INFO/WARNING but not ERROR. Bail loudly on any error.
    assert "[ERROR]" not in out, f"helm lint reported errors:\n{out}"

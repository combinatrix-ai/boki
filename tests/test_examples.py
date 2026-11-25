"""Every example plan exports to Excel and recalculates to boki's values, as the READMEs say."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import excel_check  # noqa: E402

EXAMPLES = sorted(p.parent.name for p in (ROOT / "examples").glob("*/plan.py"))


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_recalculates_in_excel_without_mismatches(name, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                    # a plan may write its workbook to the working directory
    result = excel_check.check(ROOT / "examples" / name, keep=tmp_path / "model.xlsx")
    assert result["compared"] > 0
    assert result["bad"] == []

"""Historical actuals (actual_until) and seamless transition into forecast periods."""
from __future__ import annotations

import pytest

import boki as b
from boki.units import USD, day, year

formulas = pytest.importorskip("formulas")


def _recalc(path):
    sol = formulas.ExcelModel().loads(str(path)).finish().calculate()
    out = {}
    for key, rng in sol.items():
        k = str(key).upper()
        if "]" in k and "!" in k and ":" not in k.split("!")[1]:
            sheet, cell = k.split("]", 1)[1].split("'!")
            out[(sheet.strip("'"), cell)] = rng.value[0, 0]
    return out


def _row(ws, label):
    return next(i for i in range(1, ws.max_row + 1) if (ws.cell(i, 1).value or "").strip() == label)


def test_actuals_carry_balances_into_forecast_and_verify_historical_bs():
    m = b.Model("Acme", start="2022", periods=5, step=year, actual_until="2024")
    assert m.actual_until == 2
    co = m.entity("Acme", standard=b.USGAAP, currency=USD)

    growth = m.input("Revenue growth", 0.10)
    rev_fcst = m.series("Revenue forecast")
    sales = co.pl.revenue(
        "Revenue",
        rev_fcst,
        actuals={"2022": 100 * USD, "2023": 120 * USD, "2024": 145 * USD},
    )
    rev_fcst.define(sales.lag(1) * (1 + growth))

    cogs = co.pl.cogs(
        "COGS",
        0.50 * sales,
        actuals={"2022": 52 * USD, "2023": 61 * USD, "2024": 72 * USD},
    )
    sga = co.pl.sga(
        "SG&A",
        0.20 * sales,
        actuals={"2022": 24 * USD, "2023": 28 * USD, "2024": 33 * USD},
    )

    dso_in = m.input("Forecast DSO", 45 * day)
    ar = co.bs.receivable(
        "Accounts receivable",
        target=sales * dso_in / (365 * day),
        actuals={"2022": 12 * USD, "2023": 15 * USD, "2024": 18 * USD},
    )
    # Historical DSO is derived from actuals; forecast DSO uses the input.
    dso = m.series("AR days (DSO)", (ar / sales * 365 * day).where(m.is_actual, dso_in))

    loan = co.bs.loan(
        "Term loan",
        rate=0.05,
        repay=10 * USD,
        actuals={"2022": 60 * USD, "2023": 50 * USD, "2024": 40 * USD},
    )
    tax = co.pl.income_tax(
        "Income tax",
        rate=0.25,
        base=co.pl.pretax_income,
        actuals={"2022": 5 * USD, "2023": 7 * USD, "2024": 9 * USD},
    )
    co.load_actuals({
        loan.interest_expense: {"2022": 3.5 * USD, "2023": 3.0 * USD, "2024": 2.5 * USD},
        co.bs.cash: {"2022": 88 * USD, "2023": 95 * USD, "2024": 102 * USD},
        co.bs.retained_earnings: {"2022": 40 * USD, "2023": 60 * USD, "2024": 80 * USD},
    })

    r = m.render()
    assert r[sales][:3] == pytest.approx([100, 120, 145])
    assert r[sales][3:] == pytest.approx([159.5, 175.45])
    assert r[co.pl.gross_profit][:3] == pytest.approx([48, 59, 73])
    assert r[co.pl.net_income][:3] == pytest.approx([15.5, 21.0, 28.5])
    # Forecast loan interest starts from the 2024A closing balance of 40.
    assert r[loan.interest_expense][2] == pytest.approx(2.5)
    assert r[loan.interest_expense][3] == pytest.approx(40 * 0.05)
    assert r[loan][3:] == pytest.approx([30, 20])
    # Retained earnings in 2025E = 2024A RE (80) + 2025E net income.
    assert r[co.bs.retained_earnings][2] == pytest.approx(80)
    assert r[co.bs.retained_earnings][3] == pytest.approx(80 + r[co.pl.net_income][3])
    assert r[co.bs.total_assets] == pytest.approx(r[co.bs.total_liabilities + co.bs.total_equity])
    # Historical DSO back-computed, forecast DSO equals input, and AR follows target in forecast.
    assert r[dso][2] == pytest.approx(18 / 145 * 365)
    assert r[dso][3] == pytest.approx(45)
    assert r[ar][2] == pytest.approx(18)
    assert r[ar][3] == pytest.approx(159.5 * 45 / 365)


def test_unbalanced_historical_bs_raises_ledger_error():
    m = b.Model("Bad", start="2023", periods=3, step=year, actual_until="2024")
    co = m.entity("Bad", standard=b.USGAAP, currency=USD)
    co.pl.revenue("Sales", 100 * USD, actuals={"2023": 80 * USD, "2024": 90 * USD})
    co.load_actuals({
        co.bs.cash: {"2023": 50 * USD, "2024": 60 * USD},
        co.bs.retained_earnings: {"2023": 50 * USD, "2024": 55 * USD},
    })
    with pytest.raises(b.LedgerError, match="2024"):
        m.render()


def test_actuals_validation_errors():
    m_no = b.Model("NoActuals", start="2025", periods=2, step=year)
    co_no = m_no.entity("Co", standard=b.USGAAP, currency=USD)
    with pytest.raises(ValueError, match="actual_until"):
        co_no.pl.revenue("Sales", 100 * USD, actuals={"2025": 100 * USD})
    with pytest.raises(ValueError, match="actual_until"):
        co_no.load_actuals({co_no.bs.cash: {"2025": 10 * USD}})

    m = b.Model("WithActuals", start="2023", periods=3, step=year, actual_until="2024")
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    with pytest.raises(ValueError, match="after actual_until"):
        co.pl.revenue("Sales", 100 * USD, actuals={"2025": 100 * USD})


def test_actuals_excel_export_formats_ae_headings_divider_and_recalculates(tmp_path):
    import openpyxl

    m = b.Model("Acme", start="2023", periods=4, step=year, actual_until="2024")
    co = m.entity("Acme", standard=b.USGAAP, currency=USD)
    growth = m.input("Revenue growth", 0.10, source="Management guidance")
    rev_fcst = m.series("Revenue forecast")
    sales = co.pl.revenue("Revenue", rev_fcst, actuals={"2023": 100 * USD, "2024": 120 * USD})
    rev_fcst.define(sales.lag(1) * (1 + growth))
    co.pl.cogs("COGS", 0.50 * sales, actuals={"2023": 50 * USD, "2024": 60 * USD})
    co.load_actuals({
        co.bs.cash: {"2023": 40 * USD, "2024": 55 * USD},
        co.bs.retained_earnings: {"2023": 40 * USD, "2024": 55 * USD},
    })
    r = m.render()
    path = tmp_path / "acme.xlsx"
    report = r.to_excel(path, money="$mm")
    assert report.values == 0

    wb = openpyxl.load_workbook(path)
    ws_is = wb["Acme IS"]
    # Year headings carry A/E suffixes via number formats and a vertical border at the forecast boundary.
    assert ws_is.cell(4, 3).value == 2023 and ws_is.cell(4, 3).number_format == '"FY"0"A"_)'
    assert ws_is.cell(4, 4).value == 2024 and ws_is.cell(4, 4).number_format == '"FY"0"A"_)'
    assert ws_is.cell(4, 5).value == 2025 and ws_is.cell(4, 5).number_format == '"FY"0"E"_)'
    assert ws_is.cell(4, 5).border.left.style == "medium"

    # Model sheet holds blue data in actual periods and live formulas in forecast periods.
    ws_model = wb["Model"]
    rev_row = _row(ws_model, "Revenue")
    assert ws_model.cell(rev_row, 3).value == 100
    assert ws_model.cell(rev_row, 4).value == 120
    assert str(ws_model.cell(rev_row, 5).value).startswith("=")

    got = _recalc(path)
    assert got[("CHECKS", "B5")] == "OK"
    ni_row = _row(ws_is, "Net income")
    for t, want in enumerate(r[co.pl.net_income]):
        assert got[("ACME IS", f"{chr(67 + t)}{ni_row}")] == pytest.approx(want / 1e6)

"""Display units: tables and Excel show a series in the unit it was written in, or a readable SI prefix."""
import math

import openpyxl
import pytest

import boki as b
from boki.units import MWh, USD, Wh, h, kW, kWh, month, unit, year

formulas = pytest.importorskip("formulas")


def recalc(path):
    sol = formulas.ExcelModel().loads(str(path)).finish().calculate()
    out = {}
    for key, rng in sol.items():
        k = str(key).upper()
        if "]" in k and "!" in k and ":" not in k.split("!")[1]:
            sheet, cell = k.split("]", 1)[1].split("'!")
            out[(sheet.strip("'"), cell)] = rng.value[0, 0]
    return out


def _model():
    return b.Model("pv", start="2027-01", periods=3, step=year)


def _row(ws, label):
    return next(i for i in range(1, ws.max_row + 1) if (ws.cell(i, 1).value or "").strip() == label)


def test_an_input_written_in_mwh_shows_in_mwh():
    m = _model()
    sold = m.input("sold", 400 * MWh)
    r = m.render()
    assert r[sold] == 400e6                                   # stored in Wh
    assert r.display_unit(sold) is MWh
    t = r.table([sold])
    assert t.row("sold") == [400, 400, 400]
    assert "sold (MWh)" in str(t)


def test_a_series_defined_as_a_literal_keeps_the_unit_written():
    m = _model()
    cap = m.series("capacity", 6000 * kW)
    r = m.render()
    assert r.display_unit(cap) is kW and r.table([cap]).row("capacity") == [6000, 6000, 6000]


def test_a_computed_energy_series_gets_a_prefix_from_its_largest_value():
    m = _model()
    cap = m.input("capacity", 1000 * kW)
    hours = m.input("hours", b.by_year({0: 100, 1: 1500, 2: 800})) * h
    gen = m.series("gen", cap * hours)                    # 0.1, 1.5 and 0.8 GWh: peak 1.5 GWh
    small = m.series("small", gen / 1e6)                  # peak 1.5 kWh
    zero = m.series("zero", gen * 0)
    r = m.render()
    assert r.display_unit(gen).name == "GWh" and r.display_unit(small).name == "kWh"
    assert r.display_unit(zero).name == "Wh"
    assert r.table([gen]).row("gen") == pytest.approx([0.1, 1.5, 0.8])   # one unit for the row, every period
    assert r.table([small]).row("small") == pytest.approx([0.1, 1.5, 0.8])
    assert "gen (GWh)" in str(r.table([gen]))


@pytest.mark.parametrize("peak,name", [(0.5, "mWh"), (1, "Wh"), (999.9, "Wh"), (1000, "kWh"), (2.5e6, "MWh"),
                                        (7e12, "TWh")])
def test_the_prefix_puts_the_peak_in_one_to_a_thousand(peak, name):
    m = _model()
    x = m.series("x", m.input("base", peak * Wh) * 1)             # computed, so boki picks the prefix
    assert m.render().display_unit(x).name == name


def test_mass_and_per_month_forms_take_prefixes_but_money_and_counts_do_not():
    g, GPU = unit("g"), unit("GPU")
    m = _model()
    mass = m.series("mass", m.input("tonnes", 2e6 * g) * 1)
    flow = m.series("flow", m.input("per month", 4e5 * g / month) * 1)
    money = m.series("money", m.input("fee", 5e6 * USD) * 1)
    count = m.series("count", m.input("gpus", 5000 * GPU) * 1)
    plain = m.series("plain", m.input("ratio", 123456.0) * 1)
    r = m.render()
    assert r.display_unit(mass).name == "Mg" and r.display_unit(flow).name == "kg/month"
    assert r.display_unit(money) is None and r.display_unit(count) is None and r.display_unit(plain) is None
    t = r.table([money, count, plain])
    assert t.row("money") == [5e6] * 3 and t.row("count") == [5000] * 3
    assert "(USD)" not in str(t) and "GPU" not in str(t)


def test_display_overrides_the_choice_and_must_match_the_dimension():
    m = _model()
    gen = m.series("gen", m.input("cap", 1000 * kW) * (3000 * h), display=kWh)
    assert m.render().table([gen]).row("gen") == [3_000_000] * 3
    with pytest.raises(b.UnitError, match="display=USD"):
        m.series("bad", m.input("cap2", 1000 * kW) * 1, display=USD)
    with pytest.raises(b.UnitError, match="display=MWh"):
        m.input("price", 5 * USD, display=MWh)
    ok = m.input("sold", 3 * kWh, display=MWh)
    assert m.render().table([ok]).row("sold") == pytest.approx([0.003] * 3)


def test_a_monthly_rate_can_be_shown_per_year():
    m = b.Model("churn", start="2027-01", periods=3, step=month)
    churn = m.series("churn", m.input("monthly churn", 0.01 / month) * 1, display=1 / year)
    r = m.render()
    assert r.display_unit(churn).name == "1/year"
    assert r.table([churn]).row("churn") == pytest.approx([0.12] * 3)
    assert "churn (1/year)" in str(r.table([churn]))


def test_an_explicit_table_unit_still_overrides():
    m = _model()
    sold = m.input("sold", 400 * MWh)
    gen = m.series("gen", sold * 3)
    r = m.render()
    t = r.table([sold, gen], unit=kWh)
    assert t.row("sold") == [400_000] * 3 and t.row("gen") == [1_200_000] * 3
    assert "(" not in str(t).split("\n")[1]                       # no display label next to an explicit unit


def test_grouping_keeps_the_unit_label():
    m = b.Model("pv", start="2027-01", periods=24, step=month)
    co = m.entity("Co", standard=b.USGAAP, currency=USD, fiscal=b.fiscal("12-31"))
    gen = m.series("gen", m.input("cap", 1000 * kW) * (100 * h) * 1)
    t = m.render().table([gen], by="fiscal_year", entity=co)
    assert t.rows[0].unit == "MWh" and "gen (MWh)" in str(t)


def _plan():
    m = b.Model("pv", start="2027-01", periods=3, step=year)
    cap = m.input("capacity", 1000 * kW)
    hours = m.input("hours", b.by_year({0: 1000, 1: 1500, 2: 800}))
    gen = m.series("generation", cap * hours * h)
    twice = m.series("twice", gen * 2)                          # references generation: must see Wh
    churn = m.series("churn", m.input("monthly", 0.01 / month) * 1, display=1 / year)
    yearly = m.series("yearly", churn * 1)                      # references a row shown per year
    return m, gen, twice, churn, yearly


def test_excel_shows_display_units_and_formulas_still_recalculate(tmp_path):
    m, gen, twice, churn, yearly = _plan()
    r = m.render()
    report = r.to_excel(tmp_path / "pv.xlsx")
    assert report.values == 0
    ws = openpyxl.load_workbook(tmp_path / "pv.xlsx")["Model"]
    g, tw = _row(ws, "generation"), _row(ws, "twice")
    assert ws.cell(g, 2).value == "GWh" and ws.cell(tw, 2).value == "GWh"
    assert ws.cell(g, 3).number_format.startswith("#,##0.0,,,")      # shown in GWh by format; cells stay in Wh
    got = recalc(tmp_path / "pv.xlsx")
    for col, wh in zip("CDE", [1e9, 1.5e9, 0.8e9]):                     # 1,000 kW for 1,000 / 1,500 / 800 hours
        assert math.isclose(got[("MODEL", f"{col}{g}")], wh, rel_tol=1e-9)        # the cell keeps base Wh
        assert math.isclose(got[("MODEL", f"{col}{tw}")], 2 * wh, rel_tol=1e-9)


def test_excel_converts_a_non_power_of_1000_unit_through_the_row_factor(tmp_path):
    m, gen, twice, churn, yearly = _plan()
    m.render().to_excel(tmp_path / "pv.xlsx")
    ws = openpyxl.load_workbook(tmp_path / "pv.xlsx")["Model"]
    c, y = _row(ws, "churn"), _row(ws, "yearly")
    assert ws.cell(c, 2).value == "1/year"
    got = recalc(tmp_path / "pv.xlsx")
    assert math.isclose(got[("MODEL", f"C{c}")], 0.12, rel_tol=1e-9)                # the cell holds the display value
    assert math.isclose(got[("MODEL", f"C{y}")], 0.01, rel_tol=1e-9)   # a reference converts back to base
    assert str(ws.cell(c, 3).value).startswith("=") and str(ws.cell(y, 3).value).startswith("=")


def test_excel_units_argument_overrides_and_takes_any_factor(tmp_path):
    m, gen, twice, churn, yearly = _plan()
    m.render().to_excel(tmp_path / "pv.xlsx", units={gen: kWh, yearly: b.units.Unit("1/quarter", churn.unit, 1 / 3)})
    ws = openpyxl.load_workbook(tmp_path / "pv.xlsx")["Model"]
    assert ws.cell(_row(ws, "generation"), 2).value == "kWh" and ws.cell(_row(ws, "yearly"), 2).value == "1/quarter"
    got = recalc(tmp_path / "pv.xlsx")
    assert math.isclose(got[("MODEL", f"C{_row(ws, 'yearly')}")], 0.03, rel_tol=1e-9)


def test_excel_leaves_currency_rows_alone(tmp_path):
    m = _model()
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    price = m.series("price", 5e6 * USD)
    co.bs.opening(cash=10 * USD)
    m.render().to_excel(tmp_path / "c.xlsx")
    ws = openpyxl.load_workbook(tmp_path / "c.xlsx")["Model"]
    p = _row(ws, "price")
    assert ws.cell(p, 2).value == "USD" and ws.cell(p, 3).number_format.startswith("#,##0")
    assert recalc(tmp_path / "c.xlsx")[("MODEL", f"C{p}")] == 5e6


def test_an_input_cell_holds_its_display_value_and_can_be_edited(tmp_path):
    m = _model()
    sold = m.input("sold", 400 * MWh)
    revenue = m.series("revenue", sold * (50 * USD / MWh))
    m.render().to_excel(tmp_path / "in.xlsx")
    wb = openpyxl.load_workbook(tmp_path / "in.xlsx")
    ws = wb["Inputs"]
    r = _row(ws, "sold")
    assert ws.cell(r, 2).value == "MWh" and ws.cell(r, 3).value == 400      # the cell holds 400, no number format
    assert ws.cell(r, 3).number_format == "General"
    mr = _row(wb["Model"], "revenue")
    assert recalc(tmp_path / "in.xlsx")[("MODEL", f"C{mr}")] == pytest.approx(20_000)
    ws.cell(r, 3).value = 500                                               # a user types 500 MWh
    wb.save(tmp_path / "edited.xlsx")
    assert recalc(tmp_path / "edited.xlsx")[("MODEL", f"C{mr}")] == pytest.approx(25_000)


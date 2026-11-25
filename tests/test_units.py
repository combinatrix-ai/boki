import pytest

import boki as b
from boki.units import EUR, JPY, USD, h, kW, month, year


def test_adding_kw_to_euros_is_rejected_when_written():
    m = b.Model("t", start="2016-06", periods=4, step=3 * month)
    capacity = m.input("capacity", 6000 * kW)
    om = m.series("O&M", 5 * EUR / kW / year * capacity * 3 * month)
    with pytest.raises(b.UnitError, match=r"cannot add O&M \(EUR\) and capacity \(kW\)"):
        om + capacity


def test_countable_units_do_not_mix():
    GPU, user = b.unit("GPU"), b.unit("user")
    m = b.Model("t", start=0, periods=2, step=b.year)
    gpus = m.input("gpus", 1024 * GPU)
    gpu_revenue = m.series("gpu revenue", gpus * (3.0 * USD / GPU / h))
    seat_revenue = m.series("seat revenue", m.input("users", 10 * user) * (10 * USD / user / h))
    assert m.render()[gpu_revenue + seat_revenue] == pytest.approx(3.0 * 1024 + 100)
    with pytest.raises(b.UnitError):
        gpus * (10 * USD / user / h) + gpu_revenue


def test_derived_units_convert():
    GPU = b.unit("GPU")
    node = b.unit("node", 8 * GPU)
    m = b.Model("t", start=0, periods=1, step=b.year)
    fleet = m.series("fleet", m.input("nodes", 128 * node) + 0 * GPU)
    assert m.render()[fleet] == 1024


def test_plain_numbers_do_not_silently_join_currencies_but_zero_does():
    m = b.Model("t", start=0, periods=1, step=b.year)
    cash = m.input("cash", 100 * JPY)
    assert m.render()[cash + 0] == 100
    with pytest.raises(b.UnitError, match="dimensionless"):
        cash + 5


def test_annual_rates_are_stored_per_month_and_must_be_converted_for_compound():
    m = b.Model("t", start=0, periods=3, step=b.year)
    with pytest.raises(b.UnitError, match="must be dimensionless"):
        b.lib.compound(100 * JPY, 0.05 / year)
    per_period = m.series("rate", 0.05 / year * m.period_length)
    assert m.render()[per_period] == pytest.approx([0.05, 0.05, 0.05])


def test_dates_move_by_months():
    m = b.Model("t", start="2027-04", periods=24, step=month)
    opening = m.input("opening", b.date("2027-07-01"))
    after_year = m.date >= opening + 12 * month
    r = m.render()
    assert r[opening - 1 * month] == b.date("2027-06-01")
    assert r[after_year].index(True) == 15


def test_decorated_function_works_on_plain_numbers_and_checks_its_unit():
    SAR = b.unit("SAR")
    m = b.Model("t", start=0, periods=3, step=b.year)
    ebit = m.series("ebit", b.step({0: -10 * SAR, 1: 4 * SAR}))

    @m.series(unit=SAR)
    def nol(t):
        if t == 0:
            return max(-ebit[t], 0 * SAR)
        return nol[t - 1] + max(-ebit[t], 0 * SAR) - min(max(ebit[t], 0 * SAR), nol[t - 1])

    assert m.render()[nol] == [10, 6, 2]
    assert nol.unit == SAR.dims
    with pytest.raises(b.UnitError):
        nol + 1 * JPY


def test_unit_divided_by_a_quantity():
    usd, cf = b.unit("USD"), b.unit("cf")
    per_mcf = 8 * (usd / (1000 * cf))
    assert (per_mcf * (30 * cf)).value == pytest.approx(0.24)

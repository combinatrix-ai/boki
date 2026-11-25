"""boki provides the parts of EBITDA (operating income, depreciation, amortization), never a default EBITDA."""
import dataclasses

import pytest

import boki as b
from boki.units import JPY, USD, year


def _plant(standard, currency=USD, layout=None):
    """One entity with every way depreciation can come about, 10 per period each unless noted."""
    m = b.Model("parts", start=0, periods=4, step=year)
    co = m.entity("Co", standard=standard, currency=currency, layout=layout)
    co.bs.opening(cash=1_000 * currency)
    co.pl.revenue("sales", 500 * currency)
    co.pl.cogs("materials", 100 * currency)
    co.pl.sga("rent", 50 * currency, category="Rent")
    co.bs.fixed_asset("press", 40 * currency, at=0, life=4 * year, category="Lease costs")       # custom category
    co.bs.fixed_asset("truck", opening=30 * currency, depreciation=5 * currency)                  # depreciation=
    co.bs.construction("plant", spend=30 * currency, complete_at=1, life=3 * year)                 # completed in 1
    co.bs.intangible("licence", 20 * currency, at=0, life=2 * year)
    co.bs.intangible("brand", opening=8 * currency, depreciation=2 * currency)
    return m, co


@pytest.mark.parametrize("standard,currency", [(b.USGAAP, USD), (b.IFRS, USD), (b.JGAAP, JPY)])
def test_entity_parts_follow_the_assets_under_every_standard(standard, currency):
    m, co = _plant(standard, currency)
    r = m.render()
    # press 40/4y from t=1; truck 5; plant 30/3y from t=1 (completed at period 1)
    assert r[co.depreciation] == pytest.approx([5, 5 + 10 + 10, 25, 25])
    # licence 20/2y from t=1; brand 2
    assert r[co.amortization] == pytest.approx([2, 12, 12, 2])
    assert r[co.operating_income] == pytest.approx(r[co.pl.operating_income])
    ebitda = m.series("EBITDA", co.operating_income + co.depreciation + co.amortization)
    assert r[ebitda] == pytest.approx(
        [a + d + e for a, d, e in zip(r[co.operating_income], r[co.depreciation], r[co.amortization])])
    # revenue 500 - materials 100 - rent 50 + 0 = 350 before the parts are expensed
    assert r[ebitda] == pytest.approx([350] * 4)


def test_depreciation_does_not_depend_on_the_pl_line_it_sits_on():
    general = b.JGAAP.general
    cost_of_sales = dataclasses.replace(general, depreciation_kind="cogs")
    base, co_base = _plant(b.JGAAP, JPY)
    moved, co_moved = _plant(b.JGAAP, JPY, layout=cost_of_sales)
    rb, rm = base.render(), moved.render()
    assert rm[co_moved.pl.cogs.total] != pytest.approx(rb[co_base.pl.cogs.total])        # it moved to cost of sales
    assert rm[co_moved.depreciation] == pytest.approx(rb[co_base.depreciation])
    assert rm[co_moved.amortization] == pytest.approx(rb[co_base.amortization])
    assert rm[co_moved.operating_income] == pytest.approx(rb[co_base.operating_income])   # same total either way


def test_capex_program_and_intercompany_assets_are_found_from_the_assets():
    m = b.Model("stores", start="2027-01", periods=8, step=b.month)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=1_000 * USD)
    capex = m.series("capex", data={0: 60 * USD, 3: 120 * USD})
    co.bs.fixed_asset("stores", capex, life=b.year / 2)
    r = m.render()
    assert r[co.depreciation] == pytest.approx([0, 10, 10, 10, 30, 30, 30, 20])
    assert r[co.amortization] == pytest.approx([0] * 8)


def _group(*, standard=b.JGAAP, goodwill_life=10 * year, impairment=None, fair_value=True, acquired=True):
    m = b.Model("g", start=0, periods=4, step=year)
    parent = m.entity("Parent", standard=standard, currency=JPY)
    sub = m.entity("Sub", standard=standard, currency=JPY, tax_rate=0.3)
    parent.bs.opening(cash=3_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    land = sub.bs.other_asset("Land", opening=200 * JPY)
    machine = sub.bs.fixed_asset("Machine", 60 * JPY, at=0, life=3 * year)
    sub.bs.intangible("Software", 40 * JPY, at=0, life=10 * year)
    sub.pl.revenue("Sales", 300 * JPY)
    parent.pl.revenue("Fees", 100 * JPY)
    parent.bs.fixed_asset("Office", 80 * JPY, at=0, life=4 * year)
    g = m.group("Group", parent=parent)
    kwargs = {} if goodwill_life is None else {"goodwill_life": goodwill_life}
    if impairment is not None:
        kwargs["impairment"] = m.series("impairment", data={2: impairment * JPY})
    if fair_value:
        kwargs["fair_value"] = {machine: (50 * JPY, 5 * year)}
    if acquired:
        kwargs["acquired"] = {"Customers": (60 * JPY, 6 * year)}
    g.own(sub, method="consolidate", consideration=1_000 * JPY, **kwargs)
    return m, g


def test_a_group_s_parts_include_goodwill_and_fair_value_amortization_but_not_impairment():
    m, g = _group(impairment=7)
    r = m.render()
    pl = r.pl(g)
    goodwill = pl.row("Goodwill amortization")
    assert goodwill[1] > 0
    # Office 80/4y = 20 and Machine 60/3y = 20 from period 1, plus the machine's 50 step-up over 5 years
    assert r[g.depreciation] == pytest.approx([10, 50, 50, 50])
    # Software 40/10y = 4 from period 1, the acquired customers 60/6y = 10, and the goodwill amortization
    assert r[g.amortization] == pytest.approx([10 + goodwill[0], 14 + goodwill[1], 14 + goodwill[2], 14 + goodwill[3]])
    assert r[g.operating_income] == pytest.approx(pl.row("Operating income (EBIT)"))
    # impairment is a separate line below operating income under J-GAAP and in neither part
    assert any(pl.row("Goodwill impairment"))
    other, other_group = _group(impairment=None)
    assert other.render()[other_group.depreciation] == pytest.approx(r[g.depreciation])


def test_a_group_without_goodwill_amortization_has_only_the_members_amortization():
    m, g = _group(standard=b.IFRS, goodwill_life=None, fair_value=False, acquired=False)
    r = m.render()
    assert r[g.amortization] == pytest.approx([0, 4, 4, 4])
    assert r[g.depreciation] == pytest.approx([0, 40, 40, 40])


def test_the_bank_layout_has_no_operating_income():
    m = b.Model("bank", start=0, periods=2, step=year)
    bank = m.entity("Bank", standard=b.JGAAP, currency=JPY, layout=b.layouts.bank)
    bank.bs.opening(cash=100 * JPY)
    bank.bs.fixed_asset("branch", 40 * JPY, at=0, life=4 * year)
    with pytest.raises(AttributeError, match="bank layout has no operating income subtotal"):
        bank.operating_income
    assert m.render()[bank.depreciation][1] == pytest.approx(10)


@pytest.mark.parametrize("name", ["ebitda", "adjusted_ebitda", "ebitdar"])
def test_boki_never_defines_ebitda_and_shows_how_to_build_it(name):
    m, co = _plant(b.USGAAP)
    g = m.group("Group", parent=co)
    for obj, var in ((co, "co"), (g, "group")):
        with pytest.raises(AttributeError) as error:
            getattr(obj, name)
        text = str(error.value)
        assert "no standard definition" in text
        assert f'm.series("EBITDA", {var}.operating_income + {var}.depreciation + {var}.amortization)' in text
        assert "goodwill amortization" in text and "impairment is not included" in text
        assert "adjusted EBITDA" in text
    assert not hasattr(co, name)


def test_ebit_and_noi_point_to_the_parts():
    m, co = _plant(b.USGAAP)
    with pytest.raises(AttributeError, match=r"Build it from co\.operating_income"):
        co.ebit
    with pytest.raises(AttributeError, match="Build it from revenue and operating expense lines"):
        co.noi
    with pytest.raises(AttributeError, match="has no attribute 'nothing'"):
        co.nothing


def test_intercompany_asset_depreciation_is_eliminated_in_the_group_but_not_in_the_buyer():
    m = b.Model("s6", start=0, periods=2, step=year)
    parent = m.entity("Parent", standard=b.JGAAP, currency=JPY, tax_rate=0.3)
    sub = m.entity("Sub", standard=b.JGAAP, currency=JPY, tax_rate=0.3)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    g = m.group("Group", parent=parent)
    g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY, goodwill_life=10 * year)
    parent.pl.revenue("Machine", data={0: 200 * JPY}, counterparty=sub.bs.fixed_asset, margin=0.25, life=5 * year)
    parent.pl.cogs("Machine production cost", data={0: 150 * JPY})
    r = m.render()
    assert r[sub.depreciation] == pytest.approx([40, 40])          # 200 over 5 years
    assert r[g.depreciation] == pytest.approx([30, 30])            # the seller's 50 margin is realized over 5 years
    assert r[sub.amortization] == pytest.approx([0, 0])


def test_only_the_unwind_of_an_intangible_adjustment_is_amortization():
    def build(**acquired):
        m = b.Model("ppa", start=0, periods=3, step=year)
        parent = m.entity("Parent", standard=b.JGAAP, currency=JPY)
        sub = m.entity("Sub", standard=b.JGAAP, currency=JPY, tax_rate=0.3)
        parent.bs.opening(cash=3_000 * JPY)
        sub.bs.opening(cash=500 * JPY)
        g = m.group("Group", parent=parent)
        g.own(sub, method="consolidate", consideration=1_000 * JPY, goodwill_life=10 * year,
              acquired={name: (amount * JPY, 5 * year) for name, amount in acquired.items()})
        return m, g

    both, g = build(**{"Customers": 60, "Warranty liability": -100})
    r = both.render()
    goodwill = r.pl(g).row("Goodwill amortization")
    assert any(goodwill)
    # customers 60 over 5 years = 12; the 100 warranty liability unwinds by 20 but is not amortization
    assert r[g.amortization] == pytest.approx([12 + goodwill[0], 12 + goodwill[1], 12 + goodwill[2]])
    assert r[g.depreciation] == pytest.approx([0, 0, 0])
    liability_only, g2 = build(**{"Warranty liability": -100})
    r2 = liability_only.render()
    assert r2.pl(g2).row("Acquisition adjustment amortization") != [0, 0, 0]       # it is on the PL, not in D&A
    assert r2[g2.amortization] == pytest.approx(r2.pl(g2).row("Goodwill amortization"))

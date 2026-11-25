import pytest

import boki as b
from boki.units import JPY, USD, month, year


def shop_model():
    m = b.Model("shop", start="2027-01", periods=6, step=month)
    co = m.entity("shop", standard=b.JGAAP, fiscal=b.fiscal(year_end="03-31"))
    return m, co


def test_revenue_collected_next_month_builds_a_receivable():
    m, co = shop_model()
    sales = co.pl.revenue("sales", 100 * JPY / month, settle=b.delay(1))
    r = m.render()
    assert r[sales] == [100] * 6
    assert r[co.bs.cash] == [0, 100, 200, 300, 400, 500]
    bs = r.bs(co)
    assert bs.row("Accounts receivable") == [100] * 6


def test_settle_and_recognize_kernels_must_distribute_the_amount():
    # A kernel given to settle=/recognize= distributes one amount over later periods, so
    # in total it must move exactly that amount. curve([1.0]) used to collect the same
    # sale again in every period — cash from nothing, receivables driven negative —
    # because nothing checked the kernel's total.
    from boki.shapes import Kernel
    m, co = shop_model()
    with pytest.raises(ValueError, match="keeps applying its last weight"):
        co.pl.revenue("sales", 100 * JPY / month, settle=b.curve([1.0]))
    m, co = shop_model()
    with pytest.raises(ValueError, match="must sum to 1"):
        co.pl.revenue("sales", 100 * JPY / month, settle=Kernel([0.5], "custom"))
    m, co = shop_model()
    with pytest.raises(ValueError, match="keeps applying its last weight"):
        co.pl.revenue("sales", 100 * JPY / month, recognize=b.curve([0.5, 0.5]))
    m, co = shop_model()
    with pytest.raises(ValueError, match="keeps applying its last weight"):
        co.vat_settlement(settle=b.curve([1.0]))


def test_settle_with_a_curve_that_ends_in_zero_collects_each_sale_once():
    m, co = shop_model()
    co.pl.revenue("sales", 100 * JPY / month, settle=b.curve([0.5, 0.5, 0]))
    r = m.render()
    assert r[co.bs.cash] == [50, 150, 250, 350, 450, 550]  # each 100 collected half now, half next month
    assert r.bs(co).row("Accounts receivable") == [50] * 6


def test_recognition_and_settlement_have_independent_timing():
    m, co = shop_model()
    sales = co.pl.revenue("sales", 120 * JPY / month, recognize=b.even(3), settle=b.delay(1), vat=0.10)
    r = m.render()
    assert r[sales] == pytest.approx([40, 80, 120, 120, 120, 120])
    assert r[co.bs.cash] == pytest.approx([0, 132, 264, 396, 528, 660])


def test_recognition_and_explicit_cash_schedule_have_independent_timing():
    m, co = shop_model()
    sales = co.pl.revenue("sales", 120 * JPY / month, recognize=b.even(3),
                          cash=b.step({0: 0 * JPY, 1: 120 * JPY}))
    r = m.render()
    assert r[sales] == pytest.approx([40, 80, 120, 120, 120, 120])
    assert r[co.bs.cash] == pytest.approx([0, 120, 240, 360, 480, 600])


@pytest.mark.parametrize("timing", [
    {"settle": b.delay(1)},
    {"cash": b.step({0: 0 * JPY, 1: 10 * JPY})},
    {"recognize": b.even(2)},
])
def test_against_cannot_be_combined_with_timing(timing):
    _, co = shop_model()
    asset = co.bs.other_asset("asset", opening=10 * JPY)
    with pytest.raises(TypeError, match="against=.*settle=.*cash=.*recognize="):
        co.pl.sga("expense", 10 * JPY, against=asset, **timing)


def test_statements_tie_out():
    m, co = shop_model()
    co.bs.capital("paid-in", 1_000 * JPY, at=0)
    sales = co.pl.revenue("sales", 300 * JPY / month, settle=b.mix({b.delay(0): 0.7, b.delay(1): 0.3}))
    co.pl.cogs("purchases", 0.35 * sales, settle=b.delay(1))
    co.pl.sga("rent", 50 * JPY / month, category="Rent")
    co.bs.fixed_asset("oven", 600 * JPY, at=0, life=5 * year)
    r = m.render()
    pl, bs = r.pl(co), r.bs(co)
    assert pl.row(co.label("gross_profit")) == pytest.approx([195] * 6)
    assert pl.row(co.label("operating_income")) == pytest.approx([145, 135, 135, 135, 135, 135])  # oven from period 1
    assert bs.row(co.label("total_assets")) == pytest.approx(bs.row(co.label("total_liabilities_equity")))
    cf = r.cf(co)
    assert cf.row(co.label("investing"))[0] == pytest.approx(-600)
    assert cf.row(co.label("financing"))[0] == pytest.approx(1_000)


def test_loan_amortizes_with_interest_on_the_opening_balance():
    m, co = shop_model()
    loan = co.bs.loan("bank", draw={0: 1_200 * JPY}, rate=0.12 / year, repay=(200 * JPY / month).where(m.t >= 1, 0))
    r = m.render()
    assert r[loan.balance] == pytest.approx([1200, 1000, 800, 600, 400, 200])
    assert r[loan.interest] == pytest.approx([0, 12, 10, 8, 6, 4])
    assert r[co.pl.non_operating_expense.total] == pytest.approx([0, 12, 10, 8, 6, 4])


def test_income_tax_with_loss_carryforward():
    m = b.Model("t", start=0, periods=4, step=b.year)
    co = m.entity("t", standard=b.USGAAP)
    co.pl.revenue("sales", m.series("s", b.step({0: 0 * USD, 1: 100 * USD})))
    co.pl.sga("costs", 40 * USD)
    tax = co.pl.income_tax("tax", rate=0.3, base=co.pl.pretax_income)
    co.checks.cash(level="off")      # these tests are about something other than funding
    r = m.render()
    assert r[co.pl.pretax_income] == [-40, 60, 60, 60]
    assert r[tax] == pytest.approx([0, 0.3 * 20, 18, 18])
    assert r[tax.nol.balance] == [40, 0, 0, 0] and r[tax.nol.used] == [0, 40, 0, 0]


def test_income_tax_with_losses_carried_in():
    m = b.Model("t", start=0, periods=3, step=b.year)
    co = m.entity("t", standard=b.USGAAP)
    co.pl.revenue("sales", 100 * USD)
    tax = co.pl.income_tax("tax", rate=0.3, base=co.pl.pretax_income, nol=150 * USD)
    co.checks.cash(level="off")
    r = m.render()
    assert r[tax.nol.balance] == [50, 0, 0]
    assert r[tax] == pytest.approx([0, 15, 30])


def test_nol_with_opening_and_a_cap():
    m = b.Model("t", start=0, periods=6, step=b.year)
    ebt = m.input("ebt", b.step({0: -100, 1: 30, 2: 50, 3: 200, 4: -20, 5: 100}) * USD)
    r = m.render()
    plain = b.nol(ebt)
    assert r[plain.balance] == [100, 70, 20, 0, 20, 0]
    assert r[plain.taxable] == [0, 0, 0, 180, 0, 80]
    balance, used, taxable = b.nol(ebt, opening=40 * USD, cap=0.8)
    assert r[balance] == pytest.approx([140, 116, 76, 0, 20, 0])
    assert r[used] == pytest.approx([0, 24, 40, 76, 0, 20])
    assert r[taxable] == pytest.approx([0, 6, 10, 124, 0, 80])


def test_deferred_tax_tracks_closing_temporary_difference_without_cash():
    m = b.Model("tax", start=0, periods=3, step=b.year)
    co = m.entity("Co", standard=b.USGAAP, tax_rate=0.3)
    difference = m.series("temporary difference", data={
        0: 100 * USD,
        1: 150 * USD,
        2: 50 * USD,
    })

    co.bs.deferred_tax("depreciation", difference)
    r = m.render()

    assert r.bs(co).row(f"{co.label('deferred_tax_liability')}: depreciation") == [30, 45, 15]
    assert r.pl(co).row(co.label("deferred_tax")) == [30, 15, -30]
    assert r[co.bs.cash] == [0, 0, 0]


def test_deferred_tax_recognition_fraction_reduces_only_deductible_asset():
    m = b.Model("tax", start=0, periods=3, step=b.year)
    co = m.entity("Co", standard=b.USGAAP, tax_rate=0.3)
    difference = m.series("temporary difference", data={
        0: -100 * USD,
        1: -200 * USD,
        2: -100 * USD,
    })

    co.bs.deferred_tax("loss allowance", difference, recognized=0.25)
    r = m.render()

    assert r.bs(co).row(f"{co.label('deferred_tax_asset')}: loss allowance") == pytest.approx([7.5, 15, 7.5])
    assert r.pl(co).row(co.label("deferred_tax")) == pytest.approx([-7.5, -7.5, 7.5])


def test_tax_effects_require_a_tax_rate_when_the_entity_has_none():
    m = b.Model("tax", start=0, periods=1, step=b.year)
    co = m.entity("Co", standard=b.USGAAP)

    with pytest.raises(ValueError, match="rate=.*tax_rate="):
        co.bs.deferred_tax("difference", 100 * USD)

    asset = co.bs.other_asset("security", opening=0 * USD)
    with pytest.raises(ValueError, match="tax_rate"):
        co.oci("valuation", 100 * USD, against=asset, tax=True)

    explicit = m.entity("Explicit rate", standard=b.USGAAP)
    explicit.bs.deferred_tax("difference", 100 * USD, rate=0.25)
    assert m.render().bs(explicit).row(f"{explicit.label('deferred_tax_liability')}: difference") == [25]


def test_oci_is_after_tax_and_comprehensive_income_follows_period_oci():
    m = b.Model("oci", start=0, periods=3, step=b.year)
    co = m.entity("Co", standard=b.IFRS, tax_rate=0.3)
    security = co.bs.other_asset("security", opening=0 * USD)
    amount = m.series("fair value change", data={
        0: 100 * USD,
        2: -40 * USD,
    })

    oci = co.oci("fair value reserve", amount, against=security, tax=True)
    r = m.render()
    pl = r.pl(co)
    bs = r.bs(co)

    assert r[oci] == pytest.approx([70, 0, -28])
    assert r[co.comprehensive_income] == pytest.approx([70, 0, -28])
    assert bs.row(f"{co.label('oci')}: fair value reserve") == pytest.approx([70, 70, 42])
    assert bs.row(f"{co.label('deferred_tax_liability')}: fair value reserve OCI") == pytest.approx([30, 30, 18])
    assert pl.row(co.label("other_comprehensive_income")) == pytest.approx([70, 0, -28])
    assert pl.row("fair value reserve") == pytest.approx([70, 0, -28])
    assert pl.row(co.label("comprehensive_income")) == pytest.approx([70, 0, -28])
    assert r[co.pl.income_tax.total] == [0, 0, 0]


def test_oci_against_a_profit_line_reclassifies_its_amount_from_net_income():
    m = b.Model("oci line", start=0, periods=1, step=b.year)
    co = m.entity("Co", standard=b.IFRS)
    gain = co.pl.other_income("gain", 100 * USD)
    co.oci("reserve", 20 * USD, against=gain)

    r = m.render()

    assert r[gain] == pytest.approx(80)
    assert r[co.net_income] == pytest.approx([80])
    assert r[co.comprehensive_income] == pytest.approx([100])
    assert r[co.bs.cash] == pytest.approx([100])


def test_general_layouts_include_noncurrent_deferred_tax_and_oci_kinds():
    for layout in (b.JGAAP.general, b.USGAAP.general, b.IFRS.general, b.layouts.bank):
        asset = layout.bs_kind("deferred_tax_asset")
        liability = layout.bs_kind("deferred_tax_liability")
        oci = layout.bs_kind("oci")

        assert (asset.side, asset.section) == ("asset", "noncurrent")
        assert (liability.side, liability.section) == ("liability", "noncurrent")
        assert oci.side == "equity"


@pytest.mark.parametrize(("standard", "deferred_tax", "oci"), [
    (b.JGAAP, "Deferred tax", "Accumulated other comprehensive income"),
    (b.USGAAP, "Deferred income tax", "Accumulated other comprehensive income"),
    (b.IFRS, "Deferred tax", "Other components of equity"),
])
def test_tax_and_oci_labels_follow_the_accounting_standard(standard, deferred_tax, oci):
    co = b.Model("labels", start=0, periods=1, step=b.year).entity("Co", standard=standard)

    assert co.label("deferred_tax") == deferred_tax
    assert co.label("oci") == oci


def test_statements_omit_oci_rows_when_the_entity_has_no_oci():
    m = b.Model("no OCI", start=0, periods=1, step=b.year)
    co = m.entity("Co", standard=b.IFRS)

    labels = [row.label for row in m.render().pl(co).rows]

    assert co.label("other_comprehensive_income") not in labels
    assert co.label("comprehensive_income") not in labels


def test_indirect_cash_flow_includes_fx_in_total_change():
    m = b.Model("fx", start=0, periods=2, step=b.year)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=100 * USD)
    foreign_cash = co.bs.other_asset("foreign cash", opening=20 * USD)
    fx = m.series("FX revaluation", data={0: 10 * USD})
    co.journal("FX revaluation", fx, debit=co.bs.cash, credit=foreign_cash, cf="fx")

    r = m.render()
    indirect = r.cf(co, method="indirect")
    direct = r.cf(co)

    assert indirect.row(co.label("fx")) == [10, 0]
    assert indirect.row(co.label("net_change")) == direct.row(co.label("net_change")) == [10, 0]


def test_oci_release_recycles_to_profit_or_retained_earnings():
    m = b.Model("release", start=0, periods=2, step=b.year)
    co = m.entity("Co", standard=b.USGAAP)
    asset = co.bs.other_asset("security", opening=0 * USD)
    gain = m.series("fair value gain", data={0: 100 * USD})
    release = m.series("released gain", data={1: 100 * USD})
    co.oci("recyclable", gain, against=asset, recycle=True)
    co.oci("non-recyclable", gain, against=asset, recycle=False)

    co.oci_release("recyclable", release)
    co.oci_release("non-recyclable", release)
    r = m.render()
    pl, bs = r.pl(co), r.bs(co)

    assert pl.row(co.label("other_comprehensive_income")) == pytest.approx([200, -100])
    assert pl.row(co.label("net_income")) == pytest.approx([0, 100])
    assert pl.row(co.label("comprehensive_income")) == pytest.approx([200, 0])
    assert bs.row("Retained earnings") == pytest.approx([0, 200])
    assert bs.row(f"{co.label('oci')}: recyclable") == pytest.approx([100, 0])
    assert bs.row(f"{co.label('oci')}: non-recyclable") == pytest.approx([100, 0])


@pytest.mark.parametrize(("recycle", "oci_flow", "net_income", "comprehensive_income", "retained_earnings", "cash"), [
    (True, [70, -28], [0, 28], [70, 0], [20, 48], [20, 8]),
    (False, [70, 0], [0, 0], [70, 0], [20, 60], [20, 20]),
])
def test_taxed_oci_release_releases_a_gross_part_with_proportional_tax(
        recycle, oci_flow, net_income, comprehensive_income, retained_earnings, cash):
    m = b.Model("taxed release", start=0, periods=2, step=b.year)
    co = m.entity("Co", standard=b.USGAAP, tax_rate=0.3)
    co.bs.opening(cash=20 * USD)
    security = co.bs.other_asset("security", opening=0 * USD)
    gain = m.series("fair value gain", data={0: 100 * USD})
    release = m.series("released gain", data={1: 40 * USD})
    co.oci("reserve", gain, against=security, recycle=recycle, tax=True)
    if recycle:
        co.pl.income_tax("realized gain tax", data={1: 12 * USD})

    co.oci_release("reserve", release)
    r = m.render()
    pl, bs = r.pl(co), r.bs(co)

    assert pl.row(co.label("other_comprehensive_income")) == pytest.approx(oci_flow)
    assert pl.row(co.label("net_income")) == pytest.approx(net_income)
    assert pl.row(co.label("comprehensive_income")) == pytest.approx(comprehensive_income)
    assert bs.row(f"{co.label('oci')}: reserve") == pytest.approx([70, 42])
    assert bs.row(f"{co.label('deferred_tax_liability')}: reserve OCI") == pytest.approx([30, 18])
    assert bs.row("Retained earnings") == pytest.approx(retained_earnings)
    assert bs.row(co.label("total_assets")) == pytest.approx(bs.row(co.label("total_liabilities_equity")))
    assert r[co.bs.cash] == pytest.approx(cash)
    if recycle:
        assert pl.row("OCI release: reserve") == pytest.approx([0, 40])
    else:
        assert "OCI release: reserve" not in [row.label for row in pl.rows]


def test_ddb_depreciation_stops_at_salvage_and_sells_at_book():
    m = b.Model("t", start=0, periods=11, step=b.year)
    co = m.entity("t", standard=b.USGAAP)
    eq = co.bs.fixed_asset("equipment", 50_000 * USD, at=0, life=10 * b.year, method="ddb",
                           salvage=10_000 * USD, sell_at=10)
    co.checks.cash(level="off")      # these tests are about something other than funding
    r = m.render()
    dep = r[eq.depreciation]
    assert dep[1] == pytest.approx(10_000) and dep[8] == pytest.approx(485.76) and dep[9] == 0
    assert r[eq.book][-1] == pytest.approx(0)
    assert r[co.bs.cash][-1] == pytest.approx(-40_000)


def test_standard_limits_the_kinds():
    m = b.Model("t", start=0, periods=1, step=b.year)
    ifrs = m.entity("eu", standard=b.IFRS)
    with pytest.raises(AttributeError, match="IFRS has no PL kind 'special_loss'"):
        ifrs.pl.special_loss("impairment", 1 * USD)


def test_books_keep_one_currency():
    m, co = shop_model()
    co.pl.revenue("sales", 100 * JPY / month)
    with pytest.raises(b.UnitError, match="books are in JPY"):
        co.pl.sga("rent", 5 * USD / month)


def test_grouping_by_fiscal_year_and_changing_the_year_end():
    m = b.Model("t", start="2027-01", end="2029-06", step=month)
    co = m.entity("t", standard=b.JGAAP, fiscal=b.fiscal(year_end="12-31", change={"2029-03-31": "03-31"}))
    co.pl.revenue("sales", 1 * JPY / month)
    pl = m.render().pl(co, by="fiscal_year")
    assert pl.columns == ["FY2027-12", "FY2028-12", "FY2029-03", "FY2030-03"]
    assert pl.row(co.label("revenue")) == [12, 12, 3, 3]


def test_business_days():
    m = b.Model("t", start="2027-07", periods=1, step=month)
    cal = b.calendar(m, closed=["Sun"])
    r = m.render()
    assert r[cal.days("Mon-Sat")] == [27]
    assert r[cal.days("Fri-Sat")] == [10]   # 2027-07-01 is a Thursday


def test_counted_stocks_are_plain_series():
    account = b.unit("account")
    m = b.Model("t", start=0, periods=3, step=b.year)
    basic, pro = m.series("Basic", unit=account), m.series("Pro", unit=account)
    basic0, pro0 = basic.lag(1, fill=100 * account), pro.lag(1, fill=10 * account)
    up = m.series("upgrade", b.round(basic0 * 0.1))
    basic.define(basic0 + 20 * account - up - b.round(basic0 * 0.05))
    pro.define(pro0 + up)
    r = m.render()
    assert r[up] == [10, 11, 11]          # round(10.5) is 11: halves round up, as in Excel
    assert r[basic] == [105, 109, 113]
    assert r[pro] == [20, 31, 42]
    stray = m.series("stray", unit=account)
    with pytest.raises(b.UnitError):
        stray.define(basic0 + 5 * USD)


def test_indirect_cash_flow_matches_direct_and_prepayments_show_as_liabilities():
    m, co = shop_model()
    co.bs.capital("paid-in", 1_000 * JPY, at=0)
    co.pl.revenue("subscriptions", 100 * JPY / month, cash=b.step({0: 600 * JPY, 1: 0 * JPY}))
    co.pl.cogs("hosting", 20 * JPY / month, settle=b.delay(1))
    co.bs.fixed_asset("server", 120 * JPY, at=0, life=1 * year)
    r = m.render()
    indirect, direct = r.cf(co, method="indirect"), r.cf(co)
    assert indirect.row(co.label("operating")) == pytest.approx(direct.row(co.label("operating")))
    assert indirect.row(co.label("noncash"))[1] == pytest.approx(10)
    bs = r.bs(co)
    assert bs.row(co.label("deferred_from_receivable"))[0] == pytest.approx(500)
    assert bs.row(co.label("total_assets")) == pytest.approx(bs.row(co.label("total_liabilities_equity")))


def test_beancount_export_loads_and_matches_balances():
    from beancount import loader
    from beancount.core import realization
    from boki.export import _account_names, to_beancount

    m, co = shop_model()
    co.bs.capital("paid-in", 1_000 * JPY, at=0)
    co.pl.revenue("sales", 300 * JPY / month, settle=b.delay(1))
    co.pl.sga("Rent", 50 * JPY / month)
    co.bs.fixed_asset("oven", 600 * JPY, at=0, life=5 * year)
    r = m.render()
    entries, errors, options = loader.load_string(to_beancount(r, co))
    assert errors == []
    real = realization.realize(entries)
    names = _account_names(co)
    cash = realization.get(real, names[co._cash_account]).balance.get_currency_units("JPY").number
    assert float(cash) == pytest.approx(r[co.bs.cash][-1])


def year_model(**kw):
    m = b.Model("co", start="2027-01", periods=3, step=year)
    return m, m.entity("co", standard=b.USGAAP, **kw)


def test_fixed_asset_and_construction_lives_must_be_positive():
    # life= used to be unchecked: 0 died at render time with a raw
    # ZeroDivisionError (period months / life months), and a negative life
    # depreciated upwards — the book value grew every period.
    m, co = year_model()
    with pytest.raises(ValueError, match="life must be positive"):
        co.bs.fixed_asset("oven", 600 * USD, at=0, life=0 * year)
    m, co = year_model()
    with pytest.raises(ValueError, match="life must be positive"):
        co.bs.fixed_asset("oven", 600 * USD, at=0, life=-5 * year)
    m, co = year_model()
    with pytest.raises(ValueError, match="life must be positive"):
        co.bs.construction("plant", spend=600 * USD, complete_at=1, life=0 * year)


def test_opening_balance_sheet_and_target_lines():
    m, co = year_model()
    co.bs.opening(cash=100 * USD)
    ar = co.bs.receivable("AR", target=b.by_year({0: 50, 1: 80, 2: 60}) * USD, opening=40 * USD)
    loan = co.bs.loan("loan", rate=0.1, opening=120 * USD)
    r = m.render()
    assert r[ar] == [50, 80, 60]
    assert r[ar.change] == [10, 30, -20]
    assert r[loan.interest] == pytest.approx([12, 12, 12])
    # retained earnings defaults to whatever balances the opening sheet: 100 + 40 - 120 = 20
    assert r.bs(co).row(co.label("total_assets")) == pytest.approx(r.bs(co).row(co.label("total_liabilities_equity")))
    assert r[co.cf.operating] == pytest.approx([-22, -42, 8])     # interest paid, then the change in AR


def test_an_unbalanced_opening_sheet_is_an_error():
    m, co = year_model()
    co.bs.opening(cash=100 * USD, retained_earnings=50 * USD)
    co.bs.other_liability("other", opening=40 * USD)
    with pytest.raises(b.LedgerError, match="opening balance sheet does not balance"):
        m.render()


def test_draw_or_repay_from_cash_flow_series_and_journal_classes():
    m, co = year_model()
    co.bs.opening(cash=10 * USD)
    co.pl.revenue("sales", b.by_year({0: 5, 1: -30, 2: 40}) * USD)
    other = co.bs.other_asset("other", opening=20 * USD)
    co.journal("reimbursed", 5 * USD, debit=co.bs.cash, credit=other, cf="operating")
    revolver = co.bs.loan("revolver", rate=0)
    before = co.bs.cash.opening + co.cf.operating + co.cf.investing + co.cf.financing_excluding(revolver)
    revolver.draw_or_repay(b.max(10 * USD - before, -revolver.opening))     # keep 10 of cash, repay when possible
    r = m.render()
    assert r[co.bs.cash] == pytest.approx([20, 10, 40])
    assert r[revolver.balance] == pytest.approx([0, 15, 0])
    assert r[co.cf.operating] == pytest.approx([10, -25, 45])
    assert r.cf(co, method="indirect").row(co.label("operating")) == pytest.approx([10, -25, 45])


def test_journal_into_a_pl_line_changes_profit():
    m, co = year_model()
    deposits = co.bs.liability("deposits", amount=100 * USD * (m.t == 0), cf="financing")
    retention = co.pl.revenue("retention", 0 * USD)
    fees = co.pl.sga("fees", 3 * USD)
    co.journal("retained", 10 * USD * (m.t == 1), debit=deposits, credit=retention)
    co.journal("waived", 1 * USD, debit=deposits, credit=fees)
    r = m.render()                                                # would not balance if profit missed the journals
    assert r[retention] == pytest.approx([0, 10, 0])
    assert r[fees] == pytest.approx(2)
    assert r[co.pl.net_income] == pytest.approx([-2, 8, -2])


def test_layouts_decide_the_kinds():
    m, bank = year_model(layout=b.layouts.bank)
    bank.pl.interest_income("loans", 10 * USD)
    bank.pl.interest_expense("deposits", 4 * USD)
    assert m.render()[bank.pl.net_interest_income] == [6, 6, 6]
    with pytest.raises(AttributeError, match="the bank layout has no PL kind 'revenue'"):
        bank.pl.revenue
    with pytest.raises(AttributeError, match="no balance-sheet kind 'receivable'"):
        bank.bs.receivable


def test_loan_interest_uses_the_lenders_layout():
    m = b.Model("g", start=0, periods=3, step=year)
    borrower = m.entity("borrower", currency=JPY)
    bank = m.entity("bank", standard=b.USGAAP, layout=b.layouts.bank, currency=JPY)
    borrower.bs.opening(cash=100 * JPY)
    bank.bs.opening(cash=1_000 * JPY)
    loan = borrower.bs.loan("loan", draw={0: 100 * JPY}, rate=0.10, repay=50 * JPY, counterparty=bank)

    assert loan.interest_expense.counterparty.kind == "interest_income"
    assert m.render()[loan.interest_expense.counterparty] == pytest.approx([0, 10, 5])


def test_loan_rejects_lenders_without_an_income_kind_before_posting():
    from boki.layouts import Kind, Layout, Stage

    layout = Layout(
        "no income",
        pl=(Kind("bank_revenue", "income"), Stage("net_income", lambda pl: pl.bank_revenue.total)),
        bs=b.layouts.bank.bs,
        interest_kind="interest_expense",
        depreciation_kind="non_interest_expense",
    )
    m = b.Model("g", start=0, periods=2, step=year)
    borrower = m.entity("borrower", currency=JPY)
    lender = m.entity("lender", layout=layout, currency=JPY)

    with pytest.raises(ValueError, match="no PL kind for interest income or dividends"):
        borrower.bs.loan("loan", draw={0: 100 * JPY}, rate=0.10, counterparty=lender)
    assert borrower._postings == []
    assert lender._postings == []


def test_finance_functions():
    from boki.lib import macrs, pmt
    assert pmt(0.05 / 12, 360, 100_000) == pytest.approx(536.8216, abs=1e-4)
    assert pmt(0, 10, 100) == 10
    m = b.Model("x", start=0, periods=7, step=year)
    capex = b.by_year({0: 100, 1: 0})
    r = m.render()
    assert r[capex.spread(macrs(5))] == pytest.approx([20, 32, 19.2, 11.52, 11.52, 5.76, 0])
    assert r[capex.reverse_cumsum()] == [100, 0, 0, 0, 0, 0, 0]


def test_kernel_constructors_validate_their_arguments():
    # The kernel constructors used to accept arguments that only failed later, or
    # not at all: even(0) and straight_line(0) died with a raw ZeroDivisionError,
    # delay(-1) silently behaved like delay(0), straight_line(-2) built a kernel
    # with negative weights, and curve([]) failed with an IndexError at render time.
    from boki.lib import straight_line
    with pytest.raises(ValueError, match=r"delay\(\) needs"):
        b.delay(-1)
    with pytest.raises(ValueError, match=r"even\(\) needs"):
        b.even(0)
    with pytest.raises(ValueError, match=r"straight_line\(\) needs"):
        straight_line(0)
    with pytest.raises(ValueError, match=r"straight_line\(\) needs"):
        straight_line(-2)
    with pytest.raises(ValueError, match="at least one weight"):
        b.curve([])
    # valid kernels are unchanged
    assert b.delay(2).weights == (0.0, 0.0, 1.0)
    assert b.even(2).weights == (0.5, 0.5)
    assert straight_line(2, half_year=False).weights == (0.5, 0.5)


def test_statements_show_constant_lines():
    m, co = year_model()
    co.pl.revenue("fee", 10 * USD)
    r = m.render()
    assert r.pl(co).row("fee") == [10, 10, 10]
    assert r.cf(co, method="indirect").row(co.label("net_income")) == [10, 10, 10]


def test_vat_is_collected_paid_and_settled_next_period():
    m, co = shop_model()
    co.pl.revenue("sales", 1_000 * JPY / month, vat=0.10)
    co.pl.cogs("purchases", 400 * JPY / month, vat=0.10, settle=b.delay(1))
    co.vat_settlement(settle=b.delay(1))
    r = m.render()
    assert r[co.pl.net_income] == [600] * 6                           # VAT does not touch profit
    vat = next(a for a in co._accounts if a.kind == "vat")
    assert r[co._balance(vat)] == [60] * 6                             # one month of net VAT is owed
    assert r[co.bs.cash][:2] == [1100, 1100 + 1100 - 440 - 60]          # purchases paid a month late, VAT settled next month
    assert r.cf(co).row(co.label("operating"))[1] == 1100 - 440 - 60


def test_income_tax_brackets_after_loss_carryforward():
    m, co = year_model()
    co.pl.revenue("result", b.by_year({0: -50_000, 1: 100_000, 2: 100_000}) * USD)
    brackets = lambda x: 0.15 * b.min(x, 38_120 * USD) + 0.25 * b.max(x - 38_120 * USD, 0)
    tax = co.pl.income_tax("IS", rate=brackets, base=co.pl.pretax_income)
    co.checks.cash(level="off")      # these tests are about something other than funding
    assert m.render()[tax] == pytest.approx([0, 5_718 + 0.25 * (50_000 - 38_120), 5_718 + 0.25 * (100_000 - 38_120)])


def test_subtotals_get_the_books_currency_for_unit_checks():
    from boki.units import kWh
    m, co = year_model()
    co.pl.revenue("sales", 10 * USD)
    with pytest.raises(b.UnitError):
        co.pl.gross_profit + 5 * kWh
    m2 = b.Model("m2", start=0, periods=1, step=year)
    declared = m2.entity("co", currency=USD)
    with pytest.raises(b.UnitError):
        declared.pl.operating_income - 1 * kWh
    with pytest.raises(b.UnitError, match="books are in"):
        declared.pl.revenue("sales", 3 * kWh)


def _group_model():
    m = b.Model("g", start=0, periods=3, step=year)
    parent, sub = m.entity("Parent", currency=JPY), m.entity("Subsidiary", currency=JPY)
    parent.bs.opening(cash=500 * JPY)
    sub.bs.opening(cash=200 * JPY)
    parent.pl.revenue("Product sales", 300 * JPY, settle=b.delay(1))
    parts = sub.pl.revenue("Component sales", 100 * JPY, settle=b.delay(1), counterparty=parent.pl.cogs)
    fee = parent.pl.revenue("Management fee", 10 * JPY, counterparty=sub.pl.sga)
    sub.pl.sga("Personnel costs", 40 * JPY)
    g = m.group("Group", parent=parent)
    g.own(sub, method="consolidate", consideration=200 * JPY, goodwill_life=10 * year)
    return m, parent, sub, g, parts, fee


def test_a_trade_with_another_entity_is_booked_on_both_sides():
    m, parent, sub, g, parts, fee = _group_model()
    r = m.render()
    assert parts.counterparty.entity is parent and parts.counterparty.kind == "cogs"
    assert parts.counterparty.expr is parts.expr and r[parts.counterparty] == r[parts] == 100   # one expression
    assert r[fee.counterparty] == 10 and fee.counterparty.kind == "sga"
    assert r[sub._balance(sub._shared("receivable"))] == [100, 100, 100]        # paid a period later
    assert r.pl(parent).row("Cost of revenue") == [100, 100, 100]


def test_consolidation_drops_trades_inside_the_group():
    m, parent, sub, g, parts, fee = _group_model()
    r = m.render()
    pl = r.pl(g)
    assert pl.row("Revenue") == [300, 300, 300]                                  # only sales outside the group
    assert "Cost of revenue" not in [x.label for x in pl.rows]                         # the parts bought inside
    assert pl.row("Operating expenses") == [40, 40, 40]                         # the fee is gone, wages stay
    assert pl.row("Net income") == [a + c for a, c in zip(r.pl(parent).row("Net income"), r.pl(sub).row("Net income"))]
    bs = r.bs(g)
    cash = [a + c for a, c in zip(r[parent.bs.cash], r[sub.bs.cash])]
    assert r[g.books.bs.cash] == cash
    assert r[g.books.bs.total_assets] == [x + y for x, y in zip(r[g.books.bs.total_liabilities],
                                                                r[g.books.bs.total_equity])]
    assert r[g.books._balance(g.books._shared("receivable"))] == [300, 300, 300]   # the subsidiary's receivable is gone
    assert bs.title == "BS Group"


def test_group_rebuilds_books_after_member_pl_changes():
    m = b.Model("g", start=0, periods=1, step=year)
    parent, sub = m.entity("Parent", currency=JPY), m.entity("Subsidiary", currency=JPY)
    parent.pl.revenue("Existing revenue", 10 * JPY)
    g = m.group("Group", parent=parent)
    g.own(sub, method="consolidate", consideration=0 * JPY, goodwill_life=10 * year)

    first = m.render()
    assert first.pl(g).row("Existing revenue") == [10]

    sub.pl.revenue("Additional revenue", 50 * JPY)
    second = m.render()
    assert second.pl(g).row("Additional revenue") == [50]
    assert second.pl(g).row("Revenue") == [60]


def test_consolidation_keeps_journals_to_paired_pl_lines():
    m = b.Model("g", start=0, periods=1, step=year)
    parent, sub = m.entity("Parent", currency=JPY), m.entity("Subsidiary", currency=JPY)
    parent.bs.opening(cash=10 * JPY)
    sub.bs.opening(cash=10 * JPY)
    fee = parent.pl.revenue("fee", 10 * JPY, counterparty=sub.pl.sga)
    parent.journal("fee adjustment", 2 * JPY, debit=parent.bs.cash, credit=fee)
    g = m.group("Group", parent=parent)
    g.own(sub, method="consolidate", consideration=10 * JPY, goodwill_life=10 * year)

    r = m.render()
    books = g.books
    assert r.pl(g).row("fee") == [2]
    assert r[books.bs.total_assets] == pytest.approx(
        [a + e for a, e in zip(r[books.bs.total_liabilities], r[books.bs.total_equity])])


def test_render_verifies_consolidated_group_books(monkeypatch):
    import importlib

    from boki.statements import LedgerError

    group_module = importlib.import_module("boki.group.core")
    consolidate = group_module._consolidate
    m = b.Model("g", start=0, periods=1, step=year)
    parent = m.entity("Parent", currency=JPY)
    g = m.group("Group", parent=parent)

    def unbalanced(group):
        books = consolidate(group)
        stray = books._account("stray", "income", "revenue", "pl")
        books._post("stray", 1, books._cash_account, stray)
        return books

    monkeypatch.setattr(group_module, "_consolidate", unbalanced)
    with pytest.raises(LedgerError, match="Group: assets"):
        m.render()


def test_counterparty_errors():
    m = b.Model("g", start=0, periods=2, step=year)
    parent, sub = m.entity("P", currency=JPY), m.entity("S", currency=JPY)
    with pytest.raises(TypeError, match="opposite side"):
        sub.pl.revenue("x", 1 * JPY, counterparty=parent.pl.revenue)
    with pytest.raises(TypeError, match="requires margin"):
        sub.pl.revenue("y", 1 * JPY, counterparty=parent.bs.inventory)
    with pytest.raises(ValueError, match="itself"):
        sub.pl.revenue("z", 1 * JPY, counterparty=sub.pl.cogs)
    g = m.group("G", parent=parent)
    with pytest.raises(TypeError, match="method"):
        g.own(sub, 0.8)


def test_trade_errors_identify_balance_sheet_counterparties():
    m = b.Model("g", start=0, periods=1, step=year)
    sub = m.entity("S", currency=JPY)
    bank = m.entity("bank", standard=b.USGAAP, layout=b.layouts.bank, currency=JPY)

    with pytest.raises(TypeError, match="a balance-sheet kind"):
        sub.pl.revenue("x", 1 * JPY, counterparty=bank.bs.deposits)


def test_entity_balances_helper_is_removed():
    _, co = shop_model()

    assert not hasattr(co, "balances")


def test_bs_liability_does_not_accept_section():
    _, co = shop_model()
    with pytest.raises(TypeError, match="unexpected keyword argument 'section'"):
        co.bs.liability("deposit", 1 * JPY, section="current")


def test_loans_capital_and_dividends_between_entities_and_their_consolidation():
    m = b.Model("g", start=0, periods=4, step=year)
    parent, sub = m.entity("Parent", currency=JPY), m.entity("Subsidiary", currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    paid_in = sub.bs.capital("Capital contribution", 300 * JPY, at=0, counterparty=parent)
    loan = sub.bs.loan("Loan from parent", draw={0: 200 * JPY}, rate=0.05, repay=50 * JPY, counterparty=parent)
    sub.pl.revenue("Sales", 400 * JPY)
    sub.pl.sga("Expenses", 300 * JPY)
    dividend = sub.bs.dividend("Dividend", 20 * JPY, counterparty=parent)
    g = m.group("Group", parent=parent)
    g.own(sub, method="consolidate", goodwill_life=10 * year)
    r = m.render()
    assert r[loan.counterparty] == r[loan] == [200, 150, 100, 50]               # the loan made = the loan taken
    assert r[loan.interest_expense.counterparty] == r[loan.interest_expense] == [0, 10, 7.5, 5]
    assert loan.interest_expense.counterparty.kind == "non_operating_income"
    assert r[paid_in.counterparty] == [300] * 4                                 # the parent holds the shares
    assert r[dividend.counterparty] == 20 and dividend.counterparty.entity is parent
    books = g.books
    eliminated = [a for a in books._accounts
                  if a.name in {"Capital contribution", "Loan from parent", "Loan from parent (Subsidiary)", "Subsidiary shares"}]
    assert eliminated and all(r[books._balance(a)] == pytest.approx([0] * m.n) for a in eliminated)
    pl = r.pl(g)
    assert pl.row("Operating income (EBIT)") == [100] * 4                                       # 400 - 300, nothing from inside
    assert pl.row("Net income") == [100] * 4                                     # no interest, no dividend income
    assert r[books.bs.cash] == [a + c for a, c in zip(r[parent.bs.cash], r[sub.bs.cash])]
    assert r[books.bs.total_assets] == [x + y for x, y in zip(r[books.bs.total_liabilities],
                                                              r[books.bs.total_equity])]
    with pytest.raises(TypeError, match="target="):
        sub.bs.loan("x", target=10 * JPY, counterparty=parent)


def test_repeated_capital_contributions_reuse_the_owner_shares_line():
    m = b.Model("g", start=0, periods=2, step=year)
    parent, sub = m.entity("P", currency=JPY), m.entity("S", currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    first = sub.bs.capital("first contribution", 100 * JPY, at=0, counterparty=parent)
    second = sub.bs.capital("second contribution", 50 * JPY, at=1, counterparty=parent)

    assert first.counterparty is second.counterparty
    assert len(parent.bs.other_asset.items) == 1
    assert m.render()[first.counterparty] == [100, 150]


def test_fixed_asset_capex_program_depreciates_each_purchase():
    # cost= a series without at= used to demand at= (one date) or a hand-written depreciation=.
    m = b.Model("x", start="2027-01", periods=5, step=year)
    co = m.entity("x", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=1000 * USD)
    capex = m.series("capex", data={0: 300 * USD, 2: 300 * USD})
    stores = co.bs.fixed_asset("stores", capex, life=3 * year)
    oven = co.bs.fixed_asset("oven", 300 * USD, at=0, life=3 * year)
    r = m.render()
    assert r[oven.depreciation] == [0, 100, 100, 100, 0]           # the same convention as one purchase
    assert r[stores.depreciation] == [0, 100, 100, 200, 100]
    assert r[stores.balance] == [300, 200, 400, 200, 100]
    with pytest.raises(TypeError, match="straight-line to zero"):
        co.bs.fixed_asset("ddb", capex, life=3 * year, method="ddb")
    with pytest.raises(ValueError, match="whole number of periods"):
        co.bs.fixed_asset("odd", capex, life=b.year / 2)
    # a constant cost without at= is a forgotten date, not a purchase in every period
    with pytest.raises(TypeError, match="constant cost needs at="):
        co.bs.fixed_asset("forgot at", 300 * USD, life=3 * year)
    mixed = b.Model("x", timeline=b.timeline("2027-01", [(2, month), (2, year)]))
    co = mixed.entity("x", standard=b.USGAAP, currency=USD)
    with pytest.raises(TypeError, match="periods of one length"):
        co.bs.fixed_asset("mixed", 10 * USD * (mixed.t == 0), life=1 * year)


def test_fiscal_year_tables_keep_balances_and_sum_flows():
    # r.table(by="fiscal_year") used to add up every row, so a loan balance or a headcount
    # read as twelve times its year-end value.
    m = b.Model("x", start="2027-01", periods=24, step=month)
    co = m.entity("x", standard=b.USGAAP, currency=USD, fiscal=b.fiscal(year_end="12-31"))
    co.bs.opening(cash=100 * USD)
    loan = co.bs.loan("loan", draw={0: 120 * USD}, rate=None, repay=5 * USD)
    heads = m.series("heads", 3 + m.t)
    r = m.render()
    t = r.table([loan.principal, loan.balance, loan.opening, co.bs.cash, co.bs.total_assets, co.bs.total_equity,
                 heads], by="fiscal_year", entity=co, stock=[heads])
    assert t.row("loan: principal") == [55, 60]
    assert t.row("loan") == [65, 5]
    assert t.row("loan (opening)") == [0, 65]
    assert t.row("Cash") == [165, 105]
    assert t.row("x: total assets") == [165, 105]
    assert t.row("heads") == [14, 26]


def test_capitalized_interest_into_a_construction_is_depreciated_with_it():
    # capitalize_during= alone parks the interest in a shared construction-in-progress account
    # that never depreciates, so it stayed on the balance sheet after completion.
    m, co = year_model()
    plant = co.bs.construction("plant", spend=1000 * USD * (m.t == 0), complete_at=2, life=2 * year)
    loan = co.bs.loan("loan", draw={0: 1000 * USD}, rate=0.1, capitalize_during=m.t < 2,
                      capitalize_into=plant)
    co.checks.cash(level="off")      # these tests are about something other than funding
    r = m.render()
    assert r[loan.capitalized_interest] == [0, 100, 0]
    bs = r.bs(co)
    assert "Construction in progress (capitalized interest)" not in str(bs)
    # the cost at completion includes the 100 of interest, and so does depreciation
    assert r[plant.depreciation] == [0, 0, 550]
    assert bs.row("plant") == [1000, 1100, 550]
    with pytest.raises(TypeError, match="bs.construction line"):
        co.bs.loan("other", draw={0: 1 * USD}, rate=0.1, capitalize_during=m.t == 1, capitalize_into=loan)
    with pytest.raises(TypeError, match="needs capitalize_during"):
        co.bs.loan("third", draw={0: 1 * USD}, rate=0.1, capitalize_into=plant)


def test_amounts_take_a_dict_of_periods_like_loan_draws():
    # loan(draw={...}) took a dict but construction(spend={...}) and the balance-sheet rows
    # raised TypeError, so the same "amount in these periods" needed two spellings.
    m, co = shop_model()
    plant = co.bs.construction("plant", spend={"2027-02": 300 * JPY}, complete_at="2027-04", life=1 * year)
    deposit = co.bs.deposit("deposit", {0: 50 * JPY})
    fee = co.bs.prepaid("fee", data={"2027-03": 20 * JPY})
    co.checks.cash(level="off")      # these tests are about something other than funding
    r = m.render()
    assert r[plant.spend] == [0, 300, 0, 0, 0, 0]
    assert r[deposit.balance] == [50] * 6
    assert r[fee.balance] == [0, 0, 20, 20, 20, 20]
    with pytest.raises(TypeError, match="not both"):
        co.bs.deposit("twice", 1 * JPY, data={0: 1 * JPY})


def test_data_series_cannot_be_defined_and_says_how_to_combine():
    m, co = shop_model()
    x = m.series("x", data={0: 1})
    with pytest.raises(TypeError, match="cannot be defined"):
        x.define(x.lag(1, fill=0) + 1)


# ---- opening= / opening_collect= on settle= rows ----------------------------------

def _with_opening(kernel, opening=200 * JPY, **kw):
    m, co = shop_model()
    co.pl.revenue("sales", 100 * JPY / month, settle=kernel, opening=opening, **kw)
    return m, co, m.render()


def test_opening_receivable_default_collection_delay_1_comes_in_at_once():
    m, co, r = _with_opening(b.delay(1))
    assert r[co.bs.cash] == [200, 300, 400, 500, 600, 700]
    assert r.bs(co).row("Accounts receivable") == [100] * 6


def test_opening_receivable_default_collection_delay_2_is_half_and_half():
    m, co, r = _with_opening(b.delay(2))
    assert r[co.bs.cash] == [100, 200, 300, 400, 500, 600]      # 100 + 100 of the opening, then each sale 2 months late
    assert r.bs(co).row("Accounts receivable") == [200] * 6


def test_opening_receivable_default_collection_for_a_mix_kernel():
    # w = [.5, 0, .5], so T = [.5, .5, 0]: the opening comes in evenly over two periods
    m, co, r = _with_opening(b.mix({b.delay(0): 0.5, b.delay(2): 0.5}), opening=300 * JPY)
    assert r[co.bs.cash] == pytest.approx([200, 400, 500, 600, 700, 800])
    assert r.bs(co).row("Accounts receivable") == pytest.approx([200, 100, 100, 100, 100, 100])


def test_opening_receivable_default_collection_for_an_even_kernel():
    # w = [1/3] * 3, so T = [2/3, 1/3, 0] and the shares are 2/3 and 1/3
    m, co, r = _with_opening(b.even(3), opening=300 * JPY)
    assert r[co.bs.cash] == pytest.approx([200 + 100 / 3, 400, 500, 600, 700, 800])
    assert r.bs(co).row("Accounts receivable") == pytest.approx([300 + 100 - 200 - 100 / 3, 100, 100, 100, 100, 100])


def test_opening_collect_replaces_the_default_schedule():
    m, co, r = _with_opening(b.delay(2), opening_collect={0: 50 * JPY, "2027-03": 150 * JPY})
    assert r[co.bs.cash] == [50, 50, 300, 400, 500, 600]
    assert r.bs(co).row("Accounts receivable") == [250, 350, 200, 200, 200, 200]


def test_opening_collect_must_sum_to_the_opening_balance_and_not_be_negative():
    m, co = shop_model()
    with pytest.raises(ValueError, match=r"sums to 150 but opening= is 200"):
        co.pl.revenue("sales", 100 * JPY / month, settle=b.delay(2), opening=200 * JPY,
                      opening_collect={0: 50 * JPY, 1: 100 * JPY})
    m, co = shop_model()
    with pytest.raises(ValueError, match="negative"):
        co.pl.revenue("sales", 100 * JPY / month, settle=b.delay(2), opening=200 * JPY,
                      opening_collect={0: 250 * JPY, 1: -50 * JPY})
    m, co = shop_model()
    with pytest.raises(TypeError, match="give opening= too"):
        co.pl.revenue("sales", 100 * JPY / month, settle=b.delay(2), opening_collect={0: 50 * JPY})


def test_opening_needs_settle_and_a_kernel_that_leaves_a_balance():
    m, co = shop_model()
    with pytest.raises(TypeError, match="settle="):
        co.pl.revenue("sales", 100 * JPY / month, opening=200 * JPY)
    with pytest.raises(ValueError, match="leaves nothing outstanding"):
        co.pl.revenue("sales", 100 * JPY / month, settle=b.delay(0), opening=200 * JPY)


def test_opening_payable_is_paid_by_the_default_schedule():
    m, co = shop_model()
    co.bs.opening(cash=1000 * JPY, retained_earnings=800 * JPY)
    co.pl.cogs("purchases", 100 * JPY / month, settle=b.delay(2), opening=200 * JPY)
    r = m.render()
    assert r[co.bs.cash] == [900, 800, 700, 600, 500, 400]
    assert r.bs(co).row("Accounts payable") == [200] * 6


def test_opening_receivable_is_part_of_the_opening_sheet():
    m, co = shop_model()
    co.bs.opening(cash=1000 * JPY, retained_earnings=1200 * JPY)
    co.pl.revenue("sales", 100 * JPY / month, settle=b.delay(2), opening=200 * JPY)
    m.render()                                                  # cash 1000 + receivable 200 = equity 1200
    m, co = shop_model()
    co.bs.opening(cash=1000 * JPY, retained_earnings=1000 * JPY)
    co.pl.revenue("sales", 100 * JPY / month, settle=b.delay(2), opening=200 * JPY)
    with pytest.raises(b.LedgerError, match="opening balance sheet does not balance"):
        m.render()
    m, co = shop_model()
    co.bs.opening(cash=1000 * JPY)
    co.pl.revenue("sales", 100 * JPY / month, settle=b.delay(2), opening=200 * JPY)
    r = m.render()
    assert r.bs(co).row("Retained earnings")[0] == pytest.approx(1200 + 100)    # the plug takes the receivable, plus period 0's profit


def test_two_revenue_lines_share_one_receivable_and_add_their_openings():
    m, co = shop_model()
    co.pl.revenue("retail", 100 * JPY / month, settle=b.delay(1), opening=100 * JPY)
    co.pl.revenue("wholesale", 60 * JPY / month, settle=b.delay(2), opening=120 * JPY)
    r = m.render()
    # retail's 100 comes in in period 0, wholesale's 120 as 60 + 60; then each line's sales by its own terms
    assert r[co.bs.cash] == [160, 320, 480, 640, 800, 960]
    assert r.bs(co).row("Accounts receivable") == [220] * 6        # steady state: one month of retail, two of wholesale


def test_declaring_the_shared_receivable_collides_and_points_to_opening():
    m, co = shop_model()
    co.pl.revenue("sales", 100 * JPY / month, settle=b.delay(1))
    with pytest.raises(ValueError, match=r"opening= on the PL row"):
        co.bs.receivable("Accounts receivable", opening=100 * JPY)
    m, co = shop_model()
    co.bs.receivable("Accounts receivable", opening=100 * JPY)
    with pytest.raises(ValueError, match=r"opening= on the PL row"):
        co.pl.revenue("sales", 100 * JPY / month, settle=b.delay(1))

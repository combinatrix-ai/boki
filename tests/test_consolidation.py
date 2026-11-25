import pytest

import boki as b
from boki.statements import LedgerError
from boki.units import EUR, JPY, USD, year


def _s2_group(*, share=0.8, consideration=400, standard=None, periods=3, sales=100):
    m = b.Model("s2", start=0, periods=periods, step=year)
    parent = m.entity("Parent", standard=standard or b.JGAAP, currency=JPY)
    sub = m.entity("Sub", standard=standard or b.JGAAP, currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    if sales is not None:
        sub.pl.revenue("Sales", sales * JPY)
    g = m.group("Group", parent=parent)
    g.own(sub, share, since=0, method="consolidate", consideration=consideration * JPY,
          goodwill_life=10 * year)
    return m, parent, sub, g


def _s4_controlled_group(*, standard=b.JGAAP, share=0.8, consideration=400, periods=3):
    m = b.Model("s4", start=0, periods=periods, step=year)
    parent = m.entity("Parent", standard=standard, currency=JPY)
    sub = m.entity("Sub", standard=standard, currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    group = m.group("Group", parent=parent)
    kwargs = {"goodwill_life": 10 * year} if standard is b.JGAAP else {}
    if standard is b.USGAAP:
        kwargs.update(nci="fair_value", nci_value=100 * JPY)
    group.own(sub, share, since=0, method="consolidate", consideration=consideration * JPY, **kwargs)
    return m, parent, sub, group


def _nci(result, group):
    account = next(a for a in group.books._accounts if a.kind == "nci")
    return result[group.books._balance(account)]


def _tagged_pl_row(result, books, tag):
    account = next(a for a in books._accounts if tag in a.tags)
    return result.pl(books).row(account.name)


def _s2c_group(standard):
    m = b.Model("s2-c", start=0, periods=3, step=year)
    parent = m.entity("Parent", standard=standard, currency=JPY)
    sub = m.entity("Sub", standard=standard, currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", data={0: 100 * JPY, 2: 300 * JPY})
    sub.pl.cogs("Loss", data={1: 800 * JPY}, settle=b.delay(1))
    g = m.group("Group", parent=parent)
    kwargs = {"goodwill_life": 10 * year} if standard is b.JGAAP else {}
    g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY, **kwargs)
    return m, sub, g


def _s5_entities(standard=b.JGAAP, periods=2, tax_rate=None):
    m = b.Model("s5", start=0, periods=periods, step=year)
    parent = m.entity("Parent", standard=standard, currency=JPY)
    associate = m.entity("Associate", standard=standard, currency=JPY, tax_rate=tax_rate)
    parent.bs.opening(cash=1_000 * JPY)
    plant = associate.bs.other_asset("Plant", opening=600 * JPY)
    group = m.group("Group", parent=parent)
    return m, parent, associate, group, plant


def _associate_investment(result, group, associate):
    account = next(a for a in group.books._accounts if "equity_method_investment" in a.tags)
    assert account.kind == "other_asset"
    return result[group.books._balance(account)]


def test_s5a_jgaap_equity_method_amortizes_embedded_goodwill():
    m, _, associate, group, _ = _s5_entities(periods=2)
    associate.pl.revenue("Profit", 50 * JPY)
    associate.bs.dividend("Dividend to parent", 6 * JPY, counterparty=group.parent)
    associate.bs.dividend("Dividend to other owners", 14 * JPY)
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY,
              goodwill_life=10 * year)

    result = m.render()
    books = group.books

    assert _associate_investment(result, group, associate) == pytest.approx([207, 214])
    assert result.pl(group).row("Equity method earnings") == pytest.approx([13, 13])
    assert result.cf(group).row("Cash flow from investing") == pytest.approx([-200, 0])
    assert result.cf(group).row("Cash flow from operations") == pytest.approx([6, 6])
    assert result[books.bs.total_assets] == pytest.approx([1_013, 1_026])
    assert result.bs(group).row("Investments in associates: Associate") == pytest.approx([207, 214])
    assert "Profit" not in [row.label for row in result.pl(group).rows]
    assert "Dividend to parent (Associate)" not in [row.label for row in result.pl(group).rows]


def test_jgaap_equity_method_does_not_require_goodwill_life_when_there_is_no_goodwill():
    m, _, associate, group, _ = _s5_entities(periods=1)
    associate.pl.revenue("Profit", 50 * JPY)
    group.own(associate, 0.3, since=0, method="equity", consideration=180 * JPY)

    result = m.render()

    assert _associate_investment(result, group, associate) == pytest.approx([195])
    assert result.pl(group).row("Equity method earnings") == pytest.approx([15])


def test_s5b_loss_limit_suspends_excess_and_recovers_it_first():
    m, _, associate, group, _ = _s5_entities(standard=b.IFRS, periods=3)
    associate.bs.opening(cash=1_000 * JPY)
    associate.pl.revenue("Profit", data={0: 50 * JPY, 2: 400 * JPY})
    associate.pl.sga("Loss", data={1: 1_000 * JPY})
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY)

    result = m.render()

    assert _associate_investment(result, group, associate) == pytest.approx([215, 0, 35])
    assert result.pl(group).row("Share of profit of associates") == pytest.approx([15, -215, 35])


def test_ifrs_equity_method_keeps_associate_oci_by_component_without_goodwill_amortization():
    m, _, associate, group, _ = _s5_entities(standard=b.IFRS, periods=1)
    security = associate.bs.other_asset("Security", opening=0 * JPY)
    associate.pl.revenue("Profit", 50 * JPY)
    associate.oci("Equity reserve", 30 * JPY, against=security)
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY)

    result = m.render()
    books = group.books

    assert _associate_investment(result, group, associate) == pytest.approx([224])
    assert result.bs(group).row("Investments in associates: Associate") == pytest.approx([224])
    assert result.pl(group).row("Share of profit of associates") == pytest.approx([15])
    assert result.pl(group).row("Equity reserve") == pytest.approx([9])
    assert books._oci_components["Equity reserve"].line is not None


def test_equity_method_fair_value_amortization_uses_tax_effect_and_adjusts_goodwill():
    m, _, associate, group, plant = _s5_entities(periods=1, tax_rate=0.3)
    associate.pl.revenue("Profit", 50 * JPY)
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY,
              fair_value={plant: (50 * JPY, 5 * year)}, tax_basis="carryover", goodwill_life=10 * year)

    result = m.render()

    assert _associate_investment(result, group, associate) == pytest.approx([211.95])
    assert result.pl(group).row("Equity method earnings") == pytest.approx([11.95])
    assert not any(a.kind == "deferred_tax_liability" for a in group.books._accounts)


def test_us_gaap_equity_method_uses_affiliate_earnings_label_and_private_company_amortization():
    m, _, associate, group, _ = _s5_entities(standard=b.USGAAP, periods=1)
    associate.pl.revenue("Profit", 50 * JPY)
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY,
              goodwill_life=10 * year, private_company=True)

    result = m.render()

    assert _associate_investment(result, group, associate) == pytest.approx([213])
    assert result.pl(group).row("Equity in earnings of affiliates") == pytest.approx([13])


@pytest.mark.parametrize(
    "standard,goodwill_kwargs,expected_investment,earnings_label,expected_earnings",
    [
        (b.JGAAP, {"goodwill_life": 10 * year}, 193, "Equity method earnings", 13),
        (b.USGAAP, {"goodwill_life": 10 * year, "private_company": True}, 193,
         "Equity in earnings of affiliates", 13),
        (b.IFRS, {}, 195, "Share of profit of associates", 15),
    ],
)
def test_equity_method_impairment_reduces_the_investment_for_each_standard(
        standard, goodwill_kwargs, expected_investment, earnings_label, expected_earnings):
    m, _, associate, group, _ = _s5_entities(standard=standard, periods=1)
    associate.pl.revenue("Profit", 50 * JPY)
    impairment = m.series("investment impairment", data={0: 20 * JPY})
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY,
              impairment=impairment, **goodwill_kwargs)

    result = m.render()

    assert _associate_investment(result, group, associate) == pytest.approx([expected_investment])
    assert result.pl(group).row(earnings_label) == pytest.approx([expected_earnings])
    assert result[group.books.net_income] == pytest.approx([expected_earnings - 20])


def test_equity_method_keeps_parent_trades_with_associate_and_classifies_its_dividend_as_operating_cash():
    m, parent, associate, group, _ = _s5_entities(standard=b.IFRS, periods=1)
    associate.pl.revenue("Profit", 50 * JPY)
    associate.pl.revenue("Sale to parent", 30 * JPY, counterparty=parent.pl.cogs)
    associate.pl.cogs("Cost of sale", 30 * JPY)
    associate.bs.dividend("Dividend to parent", 6 * JPY, counterparty=parent)
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY)

    result = m.render()

    assert _associate_investment(result, group, associate) == pytest.approx([209])
    assert result.pl(group).row("Share of profit of associates") == pytest.approx([15])
    assert result.pl(group).row("Cost of sales") == pytest.approx([30])
    assert result.cf(group).row("Cash flow from operations") == pytest.approx([-24])
    assert result.cf(group).row("Cash flow from investing") == pytest.approx([-200])
    assert result.pl(group).row("Sale to parent") == pytest.approx([30])


@pytest.mark.parametrize(
    "proceeds,expected_gain,expected_loss,individual_gain,individual_loss",
    [(90, 12.7125, 0, 20, 0), (60, 0, 17.2875, 0, 10)],
)
def test_equity_method_lots_scale_proportionally_on_a_later_partial_sale(
        proceeds, expected_gain, expected_loss, individual_gain, individual_loss):
    m, parent, associate, group, plant = _s5_entities(periods=3, tax_rate=0.3)
    associate.pl.revenue("Profit", 50 * JPY)
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY,
              goodwill_life=10 * year)
    group.own(associate, 0.4, since=1, method="equity", consideration=80 * JPY,
              fair_value={plant: (50 * JPY, 5 * year)}, goodwill_life=10 * year)
    group.own(associate, 0.3, since=2, method="equity", proceeds=proceeds * JPY)

    result = m.render()

    assert _associate_investment(result, group, associate) == pytest.approx([213, 309.15, 243.975])
    assert result.pl(group).row("Equity method earnings") == pytest.approx([13, 16.15, 12.1125])
    assert result.pl(group).row("Gain on sale of investments in affiliates") == pytest.approx([0, 0, expected_gain])
    assert result.pl(group).row("Loss on sale of investments in affiliates") == pytest.approx([0, 0, expected_loss])
    assert result.pl(parent).row("Gain on sale of investments in affiliates") == pytest.approx([0, 0, individual_gain])
    assert result.pl(parent).row("Loss on sale of investments in affiliates") == pytest.approx([0, 0, individual_loss])
    assert result.cf(group).row("Cash flow from investing") == pytest.approx([-200, -80, proceeds])


def test_equity_method_partial_sale_is_presented_separately_from_equity_method_earnings():
    m, _, associate, group, _ = _s5_entities(standard=b.IFRS, periods=2)
    associate.pl.revenue("Profit", 50 * JPY)
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY)
    group.own(associate, 0.2, since=1, method="equity", proceeds=90 * JPY)

    result = m.render()

    assert _associate_investment(result, group, associate) == pytest.approx([215, 153.3333333333])
    assert result.pl(group).row("Share of profit of associates") == pytest.approx([15, 10])
    assert result.pl(group).row("Gain (loss) on disposal of interests in associates") \
        == pytest.approx([0, 18.3333333333])


def test_s2a_acquisition_imports_opening_assets_and_attributes_profit():
    m, parent, sub, g = _s2_group()
    r = m.render()
    books = g.books

    assert _nci(r, g) == pytest.approx([120, 140, 160])
    assert r.pl(g).row("Net income attributable to noncontrolling interests") == pytest.approx([20, 20, 20])
    assert r.pl(g).row("Net income attributable to owners of the parent") == pytest.approx([80, 80, 80])
    assert r[books.bs.cash] == pytest.approx([1_200, 1_300, 1_400])
    assert r[books.cf.investing] == pytest.approx([100, 0, 0])
    assert r[books.cf.operating] == pytest.approx([100, 100, 100])
    assert r[books.bs.total_assets] == pytest.approx([1_200, 1_300, 1_400])


@pytest.mark.parametrize("trade, nci_profit", [
    ("service sold to the parent", [36, 36, 36]),
    ("service bought from the parent", [4, 4, 4]),
    ("loan from the parent", [20, 18, 18]),
], ids=["upstream service", "downstream service", "intercompany loan"])
def test_nci_shares_the_subsidiarys_profit_including_intercompany_trades(trade, nci_profit):
    m, parent, sub, g = _s2_group()
    if trade == "service sold to the parent":
        sub.pl.revenue("Service", 80 * JPY, counterparty=parent.pl.sga)
    elif trade == "service bought from the parent":
        parent.pl.revenue("Service", 80 * JPY, counterparty=sub.pl.sga)
    else:
        sub.bs.loan("Loan", draw={0: 100 * JPY}, rate=0.1, counterparty=parent)
    r = m.render()

    assert r.pl(g).row("Net income attributable to noncontrolling interests") == pytest.approx(nci_profit)
    assert r.pl(g).row("Net income attributable to owners of the parent") == \
        pytest.approx([100 - x for x in nci_profit])
    assert _nci(r, g) == pytest.approx([100 + sum(nci_profit[:i + 1]) for i in range(3)])


def test_acquisition_records_goodwill_from_consideration_and_nci():
    m, _, _, g = _s2_group(consideration=450)
    r = m.render()
    goodwill = next(a for a in g.books._accounts if a.name == "Goodwill")

    assert r[g.books._balance(goodwill)] == pytest.approx([45, 40, 35])


def test_existing_counterparty_shareholding_is_the_acquisition_investment():
    m = b.Model("s2", start=0, periods=1, step=year)
    parent = m.entity("Parent", currency=JPY)
    sub = m.entity("Sub", currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.capital("Paid in", 300 * JPY, at=0, counterparty=parent)
    g = m.group("Group", parent=parent)
    g.own(sub, 0.8, since=0, method="consolidate", goodwill_life=10 * year)

    r = m.render()
    books = g.books
    goodwill = next(a for a in books._accounts if a.name == "Goodwill")

    assert _nci(r, g) == pytest.approx([60])
    assert r[books._balance(goodwill)] == pytest.approx([54])
    assert r[books.bs.cash] == pytest.approx([1_000])
    assert r[books.cf.investing] == pytest.approx([0])
    assert r[books.cf.financing] == pytest.approx([0])


def test_existing_investment_is_recognized_by_its_tag_not_its_name():
    m = b.Model("s2", start=0, periods=2, step=year)
    parent = m.entity("Parent", currency=JPY)
    sub = m.entity("Sub", currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.capital("Paid in", 300 * JPY, at=0, counterparty=parent)
    g = m.group("Group", parent=parent)
    g.own(sub, 0.8, since=1, method="consolidate", goodwill_life=10 * year)

    investment = next(a for a in parent._accounts if a.name == "Sub shares")
    investment.name = "Ownership asset"
    r = m.render()

    assert _nci(r, g) == pytest.approx([0, 60])
    assert "Acquisition clearing" not in [row.label for row in r.bs(g).rows]


def test_render_checks_acquisition_clearing_balance(monkeypatch):
    import importlib

    group_module = importlib.import_module("boki.group.consolidate")
    net_assets = group_module._net_assets
    m, _, _, _ = _s2_group()

    def wrong_snapshot(group, entity, period, scopes):
        return net_assets(group, entity, period, scopes) + 10 * JPY * (group.model.t == period)

    monkeypatch.setattr(group_module, "_net_assets", wrong_snapshot)
    with pytest.raises(LedgerError) as exc:
        m.render()

    message = str(exc.value)
    assert "Group" in message
    assert "period 0" in message
    assert "10" in message


def test_jgaap_nci_loss_floor_and_later_profit_recovery_include_acquisition_nci():
    m = b.Model("s2", start=0, periods=4, step=year)
    parent = m.entity("Parent", currency=JPY)
    sub = m.entity("Sub", currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    security = sub.bs.other_asset("Security", opening=600 * JPY)
    sub.bs.liability("Debt", opening=500 * JPY)
    sub.bs.capital("Paid in", 300 * JPY, at=0, counterparty=parent)
    sub.pl.special_loss("Loss", data={0: 600 * JPY}, against=security)
    sub.pl.revenue("Later profit", data={1: 100 * JPY, 2: 100 * JPY, 3: 100 * JPY})
    g = m.group("Group", parent=parent)
    g.own(sub, 0.8, since=0, method="consolidate", goodwill_life=10 * year)

    r = m.render()

    assert _nci(r, g) == pytest.approx([0, 0, 0, 20])
    assert r.pl(g).row("Net income attributable to noncontrolling interests") == pytest.approx([-80, 0, 0, 20])
    assert r.pl(g).row("Net income attributable to owners of the parent") == pytest.approx([-500, 100, 100, 80])


def test_s2c_ifrs_allows_negative_nci_and_allocates_later_profit():
    m, sub, g = _s2c_group(b.IFRS)
    r = m.render()

    assert r[sub.net_income] == pytest.approx([100, -800, 300])
    assert r.pl(g).row("Non-controlling interests") == pytest.approx([20, -160, 60])
    assert r.pl(g).row("Owners of the parent") == pytest.approx([80, -640, 240])
    assert _nci(r, g) == pytest.approx([120, -40, 20])


def test_s2c_jgaap_floors_nci_and_recovers_parent_borne_loss_first():
    m, sub, g = _s2c_group(b.JGAAP)
    r = m.render()

    assert r[sub.net_income] == pytest.approx([100, -800, 300])
    assert r.pl(g).row("Net income attributable to noncontrolling interests") == pytest.approx([20, -120, 20])
    assert r.pl(g).row("Net income attributable to owners of the parent") == pytest.approx([80, -680, 280])
    assert _nci(r, g) == pytest.approx([120, 0, 20])


def test_s2b_controlled_purchase_reduces_nci_and_clears_negative_capital_surplus():
    m, _, sub, g = _s2_group()
    g.own(sub, 0.9, since=1, consideration=70 * JPY)
    r = m.render()
    books = g.books
    capital_surplus = next(a for a in books._accounts if a.name == "Additional paid-in capital")

    assert _nci(r, g) == pytest.approx([120, 70, 80])
    assert r.pl(g).row("Net income attributable to owners of the parent") == pytest.approx([80, 90, 90])
    assert r[books._balance(capital_surplus)] == pytest.approx([0, 0, 0])
    assert r[books.cf.financing] == pytest.approx([0, -70, 0])
    assert r[books.bs.total_assets] == pytest.approx([1_200, 1_230, 1_330])


def test_s2_buyout_from_90_to_100_removes_all_nci():
    m, _, sub, g = _s2_group(share=0.9, consideration=450)
    g.own(sub, 1.0, since=1, consideration=70 * JPY)
    r = m.render()
    books = g.books
    capital_surplus = next(a for a in books._accounts if a.name == "Additional paid-in capital")

    assert _nci(r, g) == pytest.approx([60, 0, 0])
    assert r.pl(g).row("Net income attributable to owners of the parent") == pytest.approx([90, 100, 100])
    assert r[books._balance(capital_surplus)] == pytest.approx([0, 0, 0])
    assert r[books.cf.financing] == pytest.approx([0, -70, 0])


def test_s4_decrease_requires_proceeds_before_booking_sale():
    m = b.Model("s2", start=0, periods=2, step=year)
    parent, sub = m.entity("Parent", currency=JPY), m.entity("Sub", currency=JPY)
    g = m.group("Group", parent=parent)
    g.own(sub, 1.0, since=0, method="consolidate", consideration=100 * JPY,
          goodwill_life=10 * year)

    with pytest.raises(TypeError, match="requires proceeds"):
        g.own(sub, 0.9, since=1)

    assert [p.name for p in parent._postings if "Sub shares" in p.name] == ["Sub shares acquisition"]


def test_s4a_jgaap_loss_of_control_to_equity_replaces_individual_gain():
    m, parent, sub, group = _s4_controlled_group()
    group.own(sub, 0.4, since=2, method="equity", proceeds=300 * JPY)

    result = m.render()
    books = group.books

    assert _tagged_pl_row(result, parent, "equity_method_disposal") == pytest.approx([0, 0, 100])
    assert _tagged_pl_row(result, books, "control_disposal_gain") == pytest.approx([0, 0, 20])
    assert result.pl(books).row("Equity method earnings") == pytest.approx([0, 0, 40])
    assert result[books.net_income] == pytest.approx([100, 100, 60])
    assert _nci(result, group) == pytest.approx([120, 140, 0])
    assert result[books.cf.investing] == pytest.approx([100, 0, -400])


def test_s4_jgaap_loss_to_equity_carries_and_amortizes_remaining_goodwill():
    m, _, sub, group = _s4_controlled_group(consideration=480)
    group.own(sub, 0.4, since=2, method="equity", proceeds=350 * JPY)

    result = m.render()
    books = group.books

    assert _balance_named(result, books, "Goodwill", "other_asset") == pytest.approx([72, 64, 0])
    assert _tagged_pl_row(result, books, "control_disposal_gain") == pytest.approx([0, 0, 38])
    assert result.pl(books).row("Equity method earnings") == pytest.approx([0, 0, 36])
    assert _associate_investment(result, group, sub) == pytest.approx([0, 0, 348])


@pytest.mark.parametrize(
    "standard,equity_income_label",
    [(b.IFRS, "Share of profit of associates"), (b.USGAAP, "Equity in earnings of affiliates")],
)
def test_s4_loss_of_control_to_equity_uses_retained_fair_value(standard, equity_income_label):
    m, parent, sub, group = _s4_controlled_group(standard=standard)
    group.own(sub, 0.4, since=2, method="equity", proceeds=300 * JPY, retained_value=280 * JPY)

    result = m.render()
    books = group.books

    assert _tagged_pl_row(result, parent, "equity_method_disposal") == pytest.approx([0, 0, 100])
    assert _tagged_pl_row(result, books, "control_disposal_gain") == pytest.approx([0, 0, 20])
    assert result.pl(books).row(equity_income_label) == pytest.approx([0, 0, 40])
    assert result[books.net_income] == pytest.approx([100, 100, 60])
    assert _nci(result, group) == pytest.approx([120, 140, 0])
    assert result[books.cf.investing] == pytest.approx([100, 0, -400])


def test_s4_jgaap_step_acquisition_remeasures_equity_method_interest():
    m = b.Model("s4-step", start=0, periods=2, step=year)
    parent = m.entity("Parent", currency=JPY)
    sub = m.entity("Sub", currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    group = m.group("Group", parent=parent)
    group.own(sub, 0.3, since=0, method="equity", consideration=150 * JPY)
    group.own(sub, 0.8, since=1, method="consolidate", consideration=400 * JPY,
              previously_held_value=200 * JPY, goodwill_life=10 * year)

    result = m.render()
    books = group.books

    assert _tagged_pl_row(result, books, "step_acquisition_gain") == pytest.approx([0, 20])
    assert _balance_named(result, books, "Goodwill", "other_asset") == pytest.approx([0, 108])
    assert result.pl(books).row("Equity method earnings") == pytest.approx([30, 0])
    assert _nci(result, group) == pytest.approx([0, 140])
    assert result[books.net_income] == pytest.approx([30, 108])
    assert result[books.cf.investing] == pytest.approx([-150, 200])


def test_s4_same_share_step_acquisition_needs_no_consideration():
    m = b.Model("s4-same-share-step", start=0, periods=2, step=year)
    parent = m.entity("Parent", currency=JPY)
    sub = m.entity("Sub", currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    group = m.group("Group", parent=parent)
    group.own(sub, 0.8, since=0, method="equity", consideration=400 * JPY)
    group.own(sub, 0.8, since=1, method="consolidate", previously_held_value=500 * JPY,
              goodwill_life=10 * year)

    result = m.render()
    books = group.books

    assert _tagged_pl_row(result, books, "step_acquisition_gain") == pytest.approx([0, 20])
    assert _balance_named(result, books, "Goodwill", "other_asset") == pytest.approx([0, 18])
    assert _nci(result, group) == pytest.approx([0, 140])
    assert result[books.cf.investing] == pytest.approx([-400, 600])


def test_s4_same_share_loss_of_control_needs_no_proceeds():
    m, _, sub, group = _s4_controlled_group()
    group.own(sub, 0.8, since=2, method="equity")

    result = m.render()
    books = group.books

    assert _tagged_pl_row(result, books, "control_disposal_gain") == pytest.approx([0, 0, 0])
    assert result.pl(books).row("Equity method earnings") == pytest.approx([0, 0, 80])
    assert _associate_investment(result, group, sub) == pytest.approx([0, 0, 640])
    assert _nci(result, group) == pytest.approx([120, 140, 0])
    assert result[books.cf.investing] == pytest.approx([100, 0, -700])


def test_s4_ifrs_fvoci_step_acquisition_releases_to_retained_earnings():
    m = b.Model("s4-fvoci", start=0, periods=2, step=year)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = m.entity("Sub", standard=b.IFRS, currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    group = m.group("Group", parent=parent)
    group.own(sub, 0.3, since=0, method="cost", consideration=200 * JPY)
    shares = group._ownership[sub][0].investment
    parent.oci("FVOCI reserve", m.series(data={0: 100 * JPY}), against=shares, recycle=False)
    group.own(sub, 0.8, since=1, method="consolidate", consideration=400 * JPY,
              previously_held_value=300 * JPY)

    result = m.render()
    books = group.books
    oci = next(a for a in books._accounts if a.name == "FVOCI reserve" and a.kind == "oci")

    assert _tagged_pl_row(result, books, "step_acquisition_gain") == pytest.approx([0, 0])
    assert _balance_named(result, books, "Goodwill", "other_asset") == pytest.approx([0, 220])
    assert result[books._balance(oci)] == pytest.approx([100, 0])
    transfer = next(post for post in books._postings if post.name == "Transfer FVOCI reserve to retained earnings")
    assert result[transfer.amount] == pytest.approx([0, 100])
    assert result[books.net_income] == pytest.approx([0, 100])


def test_s4_controlled_sale_is_a_capital_transaction_and_financing_cash_flow():
    m, parent, sub, group = _s4_controlled_group(share=1.0, consideration=500)
    group.own(sub, 0.9, since=1, proceeds=70 * JPY)

    result = m.render()
    books = group.books
    capital_surplus = next(a for a in books._accounts if a.name == "Additional paid-in capital")

    assert _tagged_pl_row(result, parent, "equity_method_disposal") == pytest.approx([0, 20, 0])
    assert "Gain on sale of investments in affiliates" not in [row.label for row in result.pl(books).rows]
    assert _nci(result, group) == pytest.approx([0, 70, 80])
    assert result[books._balance(capital_surplus)] == pytest.approx([0, 10, 10])
    assert result[books.cf.financing] == pytest.approx([0, 70, 0])


def test_s4_loss_to_cost_keeps_jgaap_individual_basis_and_dividends_as_income():
    m, parent, sub, group = _s4_controlled_group()
    sub.bs.dividend("Dividend", m.series(data={2: 10 * JPY}), counterparty=parent)
    group.own(sub, 0.3, since=1, method="cost", proceeds=200 * JPY)

    result = m.render()
    books = group.books
    shares = next(a for a in books._accounts if a.name == "Sub shares")

    assert result[parent._balance(group._ownership[sub][1].investment)] == pytest.approx([400, 150, 150])
    assert result[books._balance(shares)] == pytest.approx([0, 150, 150])
    assert result.pl(parent).row("Loss on sale of investments in affiliates") == pytest.approx([0, 50, 0])
    assert _tagged_pl_row(result, books, "control_disposal_gain") == pytest.approx([0, -100, 0])
    assert result.pl(books).row("Dividend (Sub)") == pytest.approx([0, 0, 10])
    assert _nci(result, group) == pytest.approx([120, 0, 0])
    assert result[books.cf.investing] == pytest.approx([100, -400, 0])
    assert result[books.cf.operating] == pytest.approx([100, 0, 10])


def test_s4_loss_of_control_recycles_parent_oci_and_derecognizes_nci():
    m = b.Model("s4-oci", start=0, periods=2, step=year)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = m.entity("Sub", standard=b.IFRS, currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    reserve = sub.bs.other_asset("Reserve asset", opening=0 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    sub.oci("Reserve", m.series(data={0: 50 * JPY}), against=reserve, recycle=True)
    group = m.group("Group", parent=parent)
    group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY)
    group.own(sub, 0.8, since=1, method="equity", proceeds=0 * JPY, retained_value=520 * JPY)

    result = m.render()
    books = group.books
    oci = next(a for a in books._accounts if a.name == "Reserve" and a.kind == "oci")

    assert result.pl(books).row("OCI release: Reserve") == pytest.approx([0, 40])
    assert result[books._balance(oci)] == pytest.approx([40, 0])
    assert result.pl(books).row("Share of profit of associates") == pytest.approx([0, 80])
    assert _nci(result, group) == pytest.approx([130, 0])
    assert result[books.cf.investing] == pytest.approx([100, -600])


def test_s4_zero_share_removes_all_remaining_interest():
    m, _, sub, group = _s4_controlled_group(periods=2)
    group.own(sub, 0, since=1, proceeds=100 * JPY)

    result = m.render()
    books = group.books

    assert _tagged_pl_row(result, books, "control_disposal_gain") == pytest.approx([0, -380])
    assert _nci(result, group) == pytest.approx([120, 0])
    assert not any("equity_method_investment" in a.tags for a in books._accounts)
    assert result[books.cf.investing] == pytest.approx([100, -500])


def test_us_gaap_partial_acquisition_uses_fair_value_nci():
    m = b.Model("s2", start=0, periods=1, step=year)
    parent = m.entity("Parent", standard=b.USGAAP, currency=JPY)
    sub = m.entity("Sub", standard=b.USGAAP, currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    g = m.group("Group", parent=parent)

    g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY,
          nci="fair_value", nci_value=150 * JPY)
    r = m.render()
    books = g.books
    goodwill = next(a for a in books._accounts if a.name == "Goodwill")
    nci = next(a for a in books._accounts if a.kind == "nci")

    assert r[books._balance(goodwill)] == pytest.approx([50])
    assert r[books._balance(nci)] == pytest.approx([170])
    assert r.pl(g).row("Attributable to noncontrolling interests") == pytest.approx([20])


def test_acquisition_scope_excludes_pre_acquisition_profit_and_cash_flow():
    m = b.Model("s2", start=0, periods=2, step=year)
    parent = m.entity("Parent", currency=JPY)
    sub = m.entity("Sub", currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    g = m.group("Group", parent=parent)
    g.own(sub, 0.8, since=1, method="consolidate", consideration=480 * JPY,
          goodwill_life=10 * year)

    r = m.render()
    assert r.pl(g).row("Net income") == pytest.approx([0, 100])
    assert _nci(r, g) == pytest.approx([0, 140])
    assert r[g.books.cf.investing] == pytest.approx([0, 120])


def test_outside_subsidiary_dividend_reduces_nci_and_is_financing():
    m, _, sub, g = _s2_group(sales=None)
    sub.bs.dividend("Outside dividend", m.series(data={0: 10 * JPY}))

    r = m.render()
    assert _nci(r, g) == pytest.approx([90, 90, 90])
    assert r[g.books.cf.financing] == pytest.approx([-10, 0, 0])


def test_subsidiary_oci_is_reported_and_its_nci_share_moves_to_nci():
    m = b.Model("s2", start=0, periods=1, step=year)
    parent = m.entity("Parent", currency=JPY)
    sub = m.entity("Sub", currency=JPY)
    parent.bs.opening(cash=500 * JPY)
    security = sub.bs.other_asset("Security", opening=100 * JPY)
    sub.oci("Reserve", 50 * JPY, against=security)
    g = m.group("Group", parent=parent)
    g.own(sub, 0.8, since=0, method="consolidate", consideration=80 * JPY,
          goodwill_life=10 * year)

    r = m.render()
    books = g.books
    oci_account = next(a for a in books._accounts if a.kind == "oci")

    assert r[books.other_comprehensive_income] == pytest.approx([50])
    assert r[books._balance(oci_account)] == pytest.approx([40])
    assert _nci(r, g) == pytest.approx([30])


def test_later_buyer_consumption_is_not_marked_as_part_of_the_trade():
    m = b.Model("s2", start=0, periods=2, step=year)
    parent = m.entity("Parent", currency=JPY)
    sub = m.entity("Sub", currency=JPY)
    parent.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Internal sale", 100 * JPY, counterparty=parent.pl.cogs)
    parent.pl.cogs("Later consumption", data={1: 25 * JPY})
    g = m.group("Group", parent=parent)
    g.own(sub, 1.0, since=0, method="consolidate", consideration=0 * JPY,
          goodwill_life=10 * year)

    r = m.render()
    assert "Internal sale" not in [row.label for row in r.pl(g).rows]
    assert r.pl(g).row("Later consumption") == pytest.approx([0, 25])
    assert all(p.counterparty is not None for p in sub._postings if p.name == "Internal sale")


def test_render_checks_group_profit_attribution_ties_to_net_income(monkeypatch):
    import importlib

    group_module = importlib.import_module("boki.group.core")
    consolidate = group_module._consolidate
    m, _, _, g = _s2_group()

    def unbalanced_attribution(group):
        books = consolidate(group)
        books._group_profit_attribution = {"section": None, "nci_label": "NCI", "parent_label": "Parent",
                                           "nci": books.net_income, "parent": books.net_income}
        return books

    monkeypatch.setattr(group_module, "_consolidate", unbalanced_attribution)
    with pytest.raises(LedgerError, match="profit attribution"):
        m.render()


def _s3_entities(standard=b.JGAAP, periods=2):
    m = b.Model("s3", start=0, periods=periods, step=year)
    parent = m.entity("Parent", standard=standard, currency=JPY)
    sub = m.entity("Sub", standard=standard, currency=JPY, tax_rate=0.3)
    parent.bs.opening(cash=1_000 * JPY)
    land = sub.bs.other_asset("Land", opening=200 * JPY)
    plant = sub.bs.other_asset("Plant", opening=300 * JPY)
    group = m.group("Group", parent=parent)
    return m, sub, group, land, plant


def _s3_group(*, standard=b.JGAAP, consideration=600, share=0.8, fair_value=None, acquired=None,
              tax_basis="carryover", nci="proportionate", nci_value=None, goodwill_life=10 * year,
              private_company=False, impairment=None, periods=2):
    m, sub, group, land, plant = _s3_entities(standard, periods)
    kwargs = {
        "consideration": consideration * JPY,
        "fair_value": fair_value,
        "acquired": acquired,
        "tax_basis": tax_basis,
        "nci": nci,
        "nci_value": nci_value * JPY if nci_value is not None else None,
        "goodwill_life": goodwill_life,
        "private_company": private_company,
        "impairment": impairment,
    }
    kwargs = {key: value for key, value in kwargs.items() if value is not None}
    group.own(sub, share, since=0, method="consolidate", **kwargs)
    return m, group, land, plant


def _pl_values(result, books, label):
    return result.pl(books).row(label)


def _balance_named(result, books, name, kind=None):
    account = next(a for a in books._accounts if a.name == name and (kind is None or a.kind == kind))
    return result[books._balance(account)]


def _tax_balance(result, books, kind):
    accounts = [a for a in books._accounts if a.kind == kind]
    return [sum(result[books._balance(a)][t] for a in accounts) for t in range(result.model.n)]


def test_s3a_proportionate_goodwill_fair_value_amortization_and_tax_unwind():
    m, sub, group, land, plant = _s3_entities()
    group.own(sub, 0.8, since=0, method="consolidate", consideration=600 * JPY,
              fair_value={land: 100 * JPY, plant: (50 * JPY, 5 * year)},
              tax_basis="carryover", nci="proportionate", goodwill_life=10 * year)
    result = m.render()
    books = group.books
    nci = next(a for a in books._accounts if a.kind == "nci")
    nci_profit = _pl_values(result, books, books._group_profit_attribution["nci_label"])

    assert _tax_balance(result, books, "deferred_tax_liability") == pytest.approx([42, 39])
    assert _balance_named(result, books, "Goodwill", "other_asset") == pytest.approx([104.4, 92.8])
    assert result[books._balance(nci)] == pytest.approx([119.6, 118.2])
    assert [end - sum(nci_profit[:i + 1]) for i, end in enumerate(result[books._balance(nci)])] == pytest.approx([121, 121])
    assert _pl_values(result, books, "Acquisition adjustment amortization") == pytest.approx([10, 10])
    assert _pl_values(result, books, books.label("deferred_tax")) == pytest.approx([-3, -3])
    assert _pl_values(result, books, "Goodwill amortization") == pytest.approx([11.6, 11.6])
    assert result[books.net_income] == pytest.approx([-18.6, -18.6])
    assert nci_profit == pytest.approx([-1.4, -1.4])
    assert _pl_values(result, books, books._group_profit_attribution["parent_label"]) == pytest.approx([-17.2, -17.2])
    assert _balance_named(result, books, "Land", "other_asset") == pytest.approx([300, 300])
    assert _balance_named(result, books, "Plant", "other_asset") == pytest.approx([340, 330])


def test_s3b_ifrs_full_goodwill_uses_fair_value_nci_without_amortization():
    m, sub, group, land, plant = _s3_entities(b.IFRS)
    group.own(sub, 0.8, since=0, method="consolidate", consideration=600 * JPY,
              fair_value={land: 100 * JPY, plant: (50 * JPY, 5 * year)}, tax_basis="carryover",
              nci="fair_value", nci_value=150 * JPY)
    result = m.render()
    books = group.books
    nci = next(a for a in books._accounts if a.kind == "nci")
    nci_profit = _pl_values(result, books, books._group_profit_attribution["nci_label"])

    assert _balance_named(result, books, "Goodwill", "other_asset") == pytest.approx([145, 145])
    assert [end - sum(nci_profit[:i + 1]) for i, end in enumerate(result[books._balance(nci)])] == pytest.approx([150, 150])
    assert _tax_balance(result, books, "deferred_tax_liability") == pytest.approx([42, 39])
    assert all(a.name != "Goodwill amortization" for a in books._accounts)


def test_us_gaap_rejects_proportionate_nci_for_a_partial_acquisition():
    _, sub, group, _, _ = _s3_entities(b.USGAAP)

    with pytest.raises(ValueError, match="nci='fair_value'"):
        group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY,
                  nci="proportionate")


def test_us_gaap_requires_nci_value_for_a_partial_acquisition():
    _, sub, group, _, _ = _s3_entities(b.USGAAP)

    with pytest.raises(ValueError, match="nci_value"):
        group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY,
                  nci="fair_value")


def test_us_gaap_goodwill_life_requires_private_company_election():
    _, sub, group, _, _ = _s3_entities(b.USGAAP)

    with pytest.raises(ValueError, match="private_company=True"):
        group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY,
                  nci="fair_value", nci_value=110 * JPY, goodwill_life=10 * year)


def test_us_gaap_private_company_goodwill_life_cannot_exceed_10_years():
    _, sub, group, _, _ = _s3_entities(b.USGAAP)

    with pytest.raises(ValueError, match="10 years"):
        group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY,
                  nci="fair_value", nci_value=110 * JPY, goodwill_life=11 * year, private_company=True)


def test_ifrs_rejects_goodwill_life():
    _, sub, group, _, _ = _s3_entities(b.IFRS)

    with pytest.raises(ValueError, match="IFRS"):
        group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY,
                  nci="proportionate", goodwill_life=10 * year)


def test_jgaap_requires_goodwill_life():
    _, sub, group, _, _ = _s3_entities(b.JGAAP)

    with pytest.raises(ValueError, match="goodwill_life"):
        group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY)


def test_jgaap_goodwill_life_cannot_exceed_20_years():
    _, sub, group, _, _ = _s3_entities(b.JGAAP)

    with pytest.raises(ValueError, match="20 years"):
        group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY,
                  goodwill_life=21 * year)


@pytest.mark.parametrize(
    "standard,nci,nci_value,goodwill_life,gain_label",
    [
        (b.JGAAP, "proportionate", None, 10 * year, "Gain on bargain purchase"),
        (b.USGAAP, "fair_value", 100, None, "Gain on bargain purchase"),
        (b.IFRS, "fair_value", 100, None, "Gain on bargain purchase"),
    ],
)
def test_negative_goodwill_is_a_gain_in_the_acquisition_period(standard, nci, nci_value, goodwill_life,
                                                                gain_label):
    m, group, _, _ = _s3_group(standard=standard, consideration=300, fair_value={}, nci=nci,
                               nci_value=nci_value, goodwill_life=goodwill_life)
    result = m.render()
    books = group.books

    assert _pl_values(result, books, gain_label) == pytest.approx([100, 0])
    assert _balance_named(result, books, books.label("goodwill"), "other_asset") == pytest.approx([0, 0])
    assert result[books.net_income] == pytest.approx([100, 0])


def test_stepped_up_tax_basis_does_not_recognize_deferred_tax():
    m, sub, group, _, plant = _s3_entities()
    group.own(sub, 0.8, since=0, method="consolidate", consideration=500 * JPY,
              fair_value={plant: (50 * JPY, 5 * year)}, tax_basis="stepped_up",
              nci="proportionate", goodwill_life=10 * year)
    result = m.render()
    books = group.books

    assert not any(a.kind in ("deferred_tax_asset", "deferred_tax_liability") for a in books._accounts)
    assert _balance_named(result, books, "Plant", "other_asset") == pytest.approx([340, 330])
    assert _pl_values(result, books, "Acquisition adjustment amortization") == pytest.approx([10, 10])


def test_acquired_intangible_is_recognized_amortized_and_taxed_in_group_books():
    m, group, _, _ = _s3_group(acquired={"Customer relationships": (40 * JPY, 8 * year)})
    result = m.render()
    books = group.books

    assert _balance_named(result, books, "Customer relationships", "intangible") == pytest.approx([35, 30])
    assert _tax_balance(result, books, "deferred_tax_liability") == pytest.approx([10.5, 9])
    assert _pl_values(result, books, "Acquisition adjustment amortization") == pytest.approx([5, 5])
    assert _pl_values(result, books, books.label("deferred_tax")) == pytest.approx([-1.5, -1.5])


def test_negative_acquired_value_is_a_liability_with_a_deferred_tax_asset():
    m, group, _, _ = _s3_group(acquired={"Warranty liability": -100 * JPY}, consideration=500)
    result = m.render()
    books = group.books

    assert _balance_named(result, books, "Warranty liability", "other_liability") == pytest.approx([100, 100])
    assert _tax_balance(result, books, "deferred_tax_asset") == pytest.approx([30, 30])


def test_acquired_amount_input_selects_asset_or_liability_per_scenario():
    m, sub, group, _, _ = _s3_entities(b.IFRS, periods=2)
    amount = m.input("Acquired item value", 40 * JPY, scenarios={"liability": -40 * JPY})
    group.own(sub, 0.8, since=0, method="consolidate", consideration=500 * JPY,
              acquired={"Contingent item": (amount, 10 * year)})

    asset_result = m.render()
    asset_books = group.books
    assert _balance_named(asset_result, asset_books, "Contingent item", "intangible") == pytest.approx([36, 32])
    assert _balance_named(asset_result, asset_books, "Contingent item", "other_liability") == pytest.approx([0, 0])
    assert _tax_balance(asset_result, asset_books, "deferred_tax_liability") == pytest.approx([10.8, 9.6])
    assert _pl_values(asset_result, asset_books,
                      asset_books.label("acquisition_adjustment_amortization")) == pytest.approx([4, 4])

    liability_result = m.render(scenario="liability")
    liability_books = group.books
    assert _balance_named(liability_result, liability_books, "Contingent item", "intangible") == pytest.approx([0, 0])
    assert _balance_named(liability_result, liability_books, "Contingent item", "other_liability") == pytest.approx([36, 32])
    assert _tax_balance(liability_result, liability_books, "deferred_tax_asset") == pytest.approx([10.8, 9.6])
    assert _pl_values(liability_result, liability_books,
                      liability_books.label("acquisition_adjustment_amortization")) == pytest.approx([-4, -4])


@pytest.mark.parametrize(
    "standard,nci,nci_value,consideration,goodwill_life,expected_goodwill,nci_profit,expense_label",
    [
        (b.JGAAP, "proportionate", None, 450, 10 * year, [25, 200 / 9], [0, 0], "Goodwill impairment"),
        (b.USGAAP, "fair_value", 110, 440, None, [30, 30], [-4, 0], "Goodwill impairment"),
        (b.IFRS, "fair_value", 110, 440, None, [30, 30], [-4, 0], "Goodwill impairment"),
    ],
)
def test_goodwill_impairment_classification_and_nci_allocation(standard, nci, nci_value, consideration,
                                                               goodwill_life, expected_goodwill, nci_profit,
                                                               expense_label):
    m, sub, group, _, _ = _s3_entities(standard)
    impairment = m.series("impairment", data={0: 20 * JPY})
    kwargs = {"consideration": consideration * JPY, "nci": nci, "impairment": impairment}
    if nci_value is not None:
        kwargs["nci_value"] = nci_value * JPY
    if goodwill_life is not None:
        kwargs["goodwill_life"] = goodwill_life
    group.own(sub, 0.8, since=0, method="consolidate", **kwargs)
    result = m.render()
    books = group.books

    assert _balance_named(result, books, books.label("goodwill"), "other_asset") == pytest.approx(expected_goodwill)
    assert _pl_values(result, books, expense_label) == pytest.approx([20, 0])
    assert _pl_values(result, books, books._group_profit_attribution["nci_label"]) == pytest.approx(nci_profit)


def test_us_gaap_private_company_can_amortize_goodwill():
    m, group, _, _ = _s3_group(standard=b.USGAAP, consideration=440, nci="fair_value", nci_value=110,
                               goodwill_life=10 * year, private_company=True)
    result = m.render()
    books = group.books

    assert _balance_named(result, books, "Goodwill", "other_asset") == pytest.approx([45, 40])
    assert _pl_values(result, books, "Goodwill amortization") == pytest.approx([5, 5])


def _s6_group(*, standard=b.JGAAP, periods=3, parent_tax=0.3, sub_tax=0.3):
    m = b.Model("s6", start=0, periods=periods, step=year)
    parent = m.entity("Parent", standard=standard, currency=JPY, tax_rate=parent_tax)
    sub = m.entity("Sub", standard=standard, currency=JPY, tax_rate=sub_tax)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    group = m.group("Group", parent=parent)
    kwargs = {"goodwill_life": 10 * year} if standard is b.JGAAP else {}
    if standard is b.USGAAP:
        kwargs.update(nci="fair_value", nci_value=100 * JPY)
    group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY, **kwargs)
    return m, parent, sub, group


def test_s6a_jgaap_upstream_inventory_eliminates_and_realizes_profit():
    m, parent, sub, group = _s6_group()
    sub.pl.revenue("Parts", 100 * JPY, counterparty=parent.bs.inventory, margin=0.3,
                   used=b.delay(1))
    sub.pl.cogs("Production cost", 70 * JPY)
    sub.pl.income_tax("Current tax", 9 * JPY)
    parent.pl.revenue("External sales", data={1: 100 * JPY, 2: 100 * JPY})

    result = m.render()
    books = group.books
    nci_label = books._group_profit_attribution["nci_label"]
    parent_label = books._group_profit_attribution["parent_label"]

    assert _balance_named(result, parent, "Parts (Sub)", "inventory") == pytest.approx([100, 100, 100])
    assert _balance_named(result, books, "Parts (Sub)", "inventory") == pytest.approx([70, 70, 70])
    assert _tax_balance(result, books, "deferred_tax_asset") == pytest.approx([9, 9, 9])
    assert result[books.net_income] == pytest.approx([0, 21, 21])
    nci_profit = result.pl(books).row(nci_label)
    parent_profit = result.pl(books).row(parent_label)
    assert nci_profit == pytest.approx([0, 4.2, 4.2])
    assert parent_profit == pytest.approx([0, 16.8, 16.8])
    assert [amount - 4.2 for amount in nci_profit] == pytest.approx([-4.2, 0, 0])
    assert [amount - 16.8 for amount in parent_profit] == pytest.approx([-16.8, 0, 0])


def test_s6b_jgaap_downstream_machine_uses_seller_cost_and_closing_margin():
    m, parent, sub, group = _s6_group(periods=1)
    parent.pl.revenue("Machine", 200 * JPY, counterparty=sub.bs.fixed_asset, margin=0.25,
                      life=5 * year)
    parent.pl.cogs("Machine production cost", 150 * JPY)

    result = m.render()
    books = group.books

    assert _balance_named(result, sub, "Machine (Parent)", "fixed_asset") == pytest.approx([160])
    assert _balance_named(result, books, "Machine (Parent)", "fixed_asset") == pytest.approx([120])
    assert result.pl(sub).row(sub.label("sga")) == pytest.approx([40])
    assert result.pl(books).row(books.label("sga")) == pytest.approx([30])
    assert result.pl(books).row("Cost of revenue") == pytest.approx([0])
    assert _tax_balance(result, books, "deferred_tax_asset") == pytest.approx([12])


def test_s6_ifrs_uses_buyer_rate_for_unrealized_inventory_tax():
    m, parent, sub, group = _s6_group(standard=b.IFRS, periods=1, parent_tax=0.3, sub_tax=0.1)
    sub.pl.revenue("Parts", 100 * JPY, counterparty=parent.bs.inventory, margin=0.3,
                   used=b.delay(1))

    result = m.render()
    books = group.books

    assert _tax_balance(result, books, "deferred_tax_asset") == pytest.approx([9])


def test_s6_us_gaap_inventory_uses_seller_rate_as_prepaid_tax_not_dta():
    m, parent, sub, group = _s6_group(standard=b.USGAAP, periods=1, parent_tax=0.3, sub_tax=0.1)
    sub.pl.revenue("Parts", 100 * JPY, counterparty=parent.bs.inventory, margin=0.3,
                   used=b.delay(1))

    result = m.render()
    books = group.books

    prepaid = [a for a in books._accounts if a.kind == "prepaid_tax"]
    assert len(prepaid) == 1
    assert result[books._balance(prepaid[0])] == pytest.approx([3])
    assert _tax_balance(result, books, "deferred_tax_asset") == pytest.approx([0])


@pytest.mark.parametrize("seller_is_sub", [False, True], ids=["downstream", "upstream"])
def test_s6_bs_sell_eliminates_disposal_gain_and_realizes_it_through_depreciation(seller_is_sub):
    m, parent, sub, group = _s6_group(periods=3)
    seller = sub if seller_is_sub else parent
    buyer = parent if seller_is_sub else sub
    old_asset = seller.bs.fixed_asset("Old machine", opening=100 * JPY, depreciation=10 * JPY)
    seller.bs.sell(old_asset, 150 * JPY, at=1, counterparty=buyer.bs.fixed_asset, life=5 * year)

    result = m.render()
    books = group.books
    buyer_asset = "Old machine (Sub)" if buyer is parent else "Old machine (Parent)"

    assert _balance_named(result, seller, "Old machine", "fixed_asset") == pytest.approx([90, 0, 0])
    assert _balance_named(result, buyer, buyer_asset, "fixed_asset") == pytest.approx([0, 120, 90])
    assert _balance_named(result, books, buyer_asset, "fixed_asset") == pytest.approx([0, 72, 54])
    assert _tax_balance(result, books, "deferred_tax_asset") == pytest.approx([0, 14.4, 10.8])
    assert result.pl(books).row(books.label("sga")) == pytest.approx([10, 18, 18])
    assert result.pl(books).row("Gain on sale of fixed assets") == pytest.approx([0, 0, 0])


def test_s6_sale_to_equity_method_associate_eliminates_only_investor_share():
    m = b.Model("s6-associate", start=0, periods=1, step=year)
    parent = m.entity("Parent", currency=JPY, tax_rate=0.3)
    associate = m.entity("Associate", currency=JPY, tax_rate=0.3)
    parent.bs.opening(cash=1_000 * JPY)
    associate.bs.opening(cash=100 * JPY)
    parent.pl.revenue("Parts", 100 * JPY, counterparty=associate.bs.inventory, margin=0.3,
                      used=b.delay(1))
    parent.pl.cogs("Production cost", 70 * JPY)
    group = m.group("Group", parent=parent)
    group.own(associate, 0.3, since=0, method="equity", consideration=30 * JPY,
              goodwill_life=10 * year)

    result = m.render()
    books = group.books

    assert result.pl(parent).row("Revenue") == pytest.approx([100])
    assert result.pl(books).row("Revenue") == pytest.approx([100])
    assert result.pl(books).row("Cost of revenue") == pytest.approx([79])
    assert _associate_investment(result, group, associate) == pytest.approx([21])
    assert _tax_balance(result, books, "deferred_tax_asset") == pytest.approx([2.7])


def test_s7a_opening_controlled_subsidiary_matches_s2_without_acquisition_cash_flow():
    reference_model, _, _, reference_group = _s2_group()
    reference = reference_model.render()

    model = b.Model("s7", start=0, periods=3, step=year)
    parent = model.entity("Parent", standard=b.JGAAP, currency=JPY)
    sub = model.entity("Sub", standard=b.JGAAP, currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=400 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * JPY, "nci": 100 * JPY})

    result = model.render()
    books = group.books
    reference_books = reference_group.books

    assert result[books.bs.cash] == pytest.approx([1_200, 1_300, 1_400])
    assert result[books.bs.total_assets] == pytest.approx(reference[reference_books.bs.total_assets])
    assert result.pl(group).row("Net income attributable to noncontrolling interests") == pytest.approx(
        reference.pl(reference_group).row("Net income attributable to noncontrolling interests"))
    assert result.pl(group).row("Net income attributable to owners of the parent") == pytest.approx(
        reference.pl(reference_group).row("Net income attributable to owners of the parent"))
    assert result[books.cf.investing] == pytest.approx([0, 0, 0])
    assert result[books.cf.operating] == pytest.approx([100, 100, 100])


def test_s7_opening_reconciliation_reports_difference_instead_of_plugging_retained_earnings():
    model = b.Model("s7-unbalanced", start=0, periods=1, step=year)
    parent = model.entity("Parent", currency=JPY)
    sub = model.entity("Sub", currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=400 * JPY)
    sub.bs.opening(cash=500 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * JPY, "nci": 101 * JPY})

    with pytest.raises(LedgerError, match=r"difference -1"):
        model.render()


def test_s7_parent_investment_cannot_be_recorded_both_sides_of_opening():
    model = b.Model("s7-double-investment", start=0, periods=1, step=year)
    parent = model.entity("Parent", currency=JPY)
    sub = model.entity("Sub", currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=400 * JPY)
    sub.bs.capital("Paid in", opening=400 * JPY, counterparty=parent)
    group = model.group("Group", parent=parent)

    with pytest.raises(ValueError, match="both opening investment records"):
        group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
                  opening={"goodwill": 0 * JPY, "nci": 100 * JPY})


def test_s7_opening_counterparty_capital_supplies_the_parent_investment():
    model = b.Model("s7-mirrored-capital", start=0, periods=1, step=year)
    parent = model.entity("Parent", currency=JPY)
    sub = model.entity("Sub", currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.bs.capital("Paid in", opening=400 * JPY, counterparty=parent)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate",
              opening={"goodwill": 0 * JPY, "nci": 100 * JPY})

    result = model.render()

    assert result[group.books.bs.total_assets] == pytest.approx([1_100])
    assert result[group.books.bs.total_equity] == pytest.approx([1_100])
    assert result[group.books.cf.investing] == pytest.approx([0])


def test_s7_jgaap_opening_goodwill_amortizes_over_its_remaining_life():
    model = b.Model("s7-goodwill", start=0, periods=2, step=year)
    parent = model.entity("Parent", standard=b.JGAAP, currency=JPY)
    sub = model.entity("Sub", standard=b.JGAAP, currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=500 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": (100 * JPY, 10 * year), "nci": 100 * JPY})

    result = model.render()
    books = group.books
    goodwill = next(account for account in books._accounts if account.name == "Goodwill")

    assert result[books._balance(goodwill)] == pytest.approx([90, 80])
    assert result[books.net_income] == pytest.approx([90, 90])
    assert result.pl(group).row("Net income attributable to noncontrolling interests") == pytest.approx([20, 20])
    assert result.pl(group).row("Net income attributable to owners of the parent") == pytest.approx([70, 70])


def test_s7_opening_fair_value_and_deferred_tax_unwind_together():
    model = b.Model("s7-fair-value", start=0, periods=2, step=year)
    parent = model.entity("Parent", standard=b.JGAAP, currency=JPY)
    sub = model.entity("Sub", standard=b.JGAAP, currency=JPY, tax_rate=0.3)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=270 * JPY)
    land = sub.bs.other_asset("Land", opening=300 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * JPY, "nci": 100 * JPY,
                       "fair_value": {land: (100 * JPY, 10 * year)}, "deferred_tax": 30 * JPY})

    result = model.render()
    books = group.books
    land_account = next(account for account in books._accounts if account.name == "Land")

    assert result[books._balance(land_account)] == pytest.approx([390, 380])
    assert _tax_balance(result, books, "deferred_tax_liability") == pytest.approx([27, 24])
    assert result[books.net_income] == pytest.approx([-7, -7])


def test_s7_opening_nci_oci_is_included_in_nci_and_not_added_again():
    model = b.Model("s7-oci", start=0, periods=1, step=year)
    parent = model.entity("Parent", standard=b.JGAAP, currency=JPY)
    sub = model.entity("Sub", standard=b.JGAAP, currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=380 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.oci("Translation reserve", 0 * JPY, against=sub.bs.cash, recycle=False)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * JPY, "nci": 100 * JPY,
                       "oci": {"Translation reserve": (20 * JPY, 10 * JPY)}})

    result = model.render()
    books = group.books
    nci = next(account for account in books._accounts if account.kind == "nci")
    oci = next(account for account in books._accounts if account.name == "Translation reserve")

    assert result[books._balance(nci)] == pytest.approx([100])
    assert result[books._balance(oci)] == pytest.approx([20])
    assert result[books.bs.total_assets] == pytest.approx([1_100])
    assert result[books.bs.total_equity] == pytest.approx([1_100])


def test_s7_opening_acquired_item_and_deferred_tax_unwind():
    model = b.Model("s7-acquired-item", start=0, periods=2, step=year)
    parent = model.entity("Parent", standard=b.JGAAP, currency=JPY)
    sub = model.entity("Sub", standard=b.JGAAP, currency=JPY, tax_rate=0.3)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=270 * JPY)
    sub.bs.opening(cash=300 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * JPY, "nci": 100 * JPY,
                       "acquired": {"Customer relationships": (100 * JPY, 10 * year)},
                       "deferred_tax": 30 * JPY})

    result = model.render()
    books = group.books
    customer_relationships = next(account for account in books._accounts
                                  if account.name == "Customer relationships" and account.kind == "intangible")

    assert result[books._balance(customer_relationships)] == pytest.approx([90, 80])
    assert _tax_balance(result, books, "deferred_tax_liability") == pytest.approx([27, 24])
    assert result[books.net_income] == pytest.approx([-7, -7])


def test_s7_opening_unrealized_inventory_profit_releases_and_uses_s6_seller_tax():
    model = b.Model("s7-unrealized", start=0, periods=2, step=year)
    parent = model.entity("Parent", standard=b.JGAAP, currency=JPY)
    sub = model.entity("Sub", standard=b.JGAAP, currency=JPY, tax_rate=0.3)
    parent.bs.opening(cash=100 * JPY)
    inventory = parent.bs.inventory("Inventory", opening=100 * JPY)
    parent_shares = parent.bs.other_asset("Sub shares", opening=100 * JPY)
    sub.bs.opening(cash=100 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 1.0, since="before", method="consolidate", investment=parent_shares,
              opening={"goodwill": 0 * JPY, "nci": 0 * JPY,
                       "unrealized": {inventory: (30 * JPY, b.delay(1))}})

    result = model.render()
    books = group.books
    group_inventory = next(account for account in books._accounts
                           if account.name == "Inventory" and account.kind == "inventory")

    assert result[books._balance(group_inventory)] == pytest.approx([70, 100])
    assert _tax_balance(result, books, "deferred_tax_asset") == pytest.approx([9, 0])
    assert result[books.net_income] == pytest.approx([0, 21])


def test_s7_opening_equity_method_investment_carries_suspended_losses():
    model = b.Model("s7-equity", start=0, periods=2, step=year)
    parent = model.entity("Parent", standard=b.JGAAP, currency=JPY)
    associate = model.entity("Associate", standard=b.JGAAP, currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    shares = parent.bs.other_asset("Associate shares", opening=100 * JPY)
    associate.bs.opening(cash=20 * JPY)
    associate.pl.cogs("Opening period loss", data={0: 20 * JPY})
    associate.pl.revenue("Later profit", data={1: 50 * JPY})
    group = model.group("Group", parent=parent)
    group.own(associate, 0.3, since="before", method="equity", investment=shares,
              opening={"investment": 100 * JPY, "embedded_goodwill": 0 * JPY,
                       "suspended_losses": 10 * JPY})

    result = model.render()
    books = group.books

    assert _associate_investment(result, group, associate) == pytest.approx([94, 99])
    assert result.pl(group).row("Equity method loss") == pytest.approx([6, 0])
    assert result.pl(group).row("Equity method earnings") == pytest.approx([0, 5])
    assert result[books._equity_method_suspended_losses[associate]] == pytest.approx([10, 0])


def test_s7_opening_equity_method_amortizes_goodwill_and_fair_value_and_keeps_oci():
    model = b.Model("s7-equity-basis", start=0, periods=2, step=year)
    parent = model.entity("Parent", standard=b.JGAAP, currency=JPY)
    associate = model.entity("Associate", standard=b.JGAAP, currency=JPY, tax_rate=0.3)
    parent.bs.opening(cash=1_000 * JPY)
    shares = parent.bs.other_asset("Associate shares", opening=100 * JPY)
    associate.bs.opening(cash=100 * JPY)
    land = associate.bs.other_asset("Land", opening=100 * JPY)
    associate.oci("Translation reserve", 0 * JPY, against=associate.bs.cash, recycle=False)
    group = model.group("Group", parent=parent)
    group.own(associate, 0.3, since="before", method="equity", investment=shares,
              opening={"investment": 100 * JPY, "embedded_goodwill": (10 * JPY, 5 * year),
                       "fair_value": {land: (20 * JPY, 5 * year)},
                       "oci": {"Translation reserve": 15 * JPY}})

    result = model.render()
    books = group.books
    oci = next(account for account in books._accounts if account.name == "Translation reserve")

    assert _associate_investment(result, group, associate) == pytest.approx([97.16, 94.32])
    assert result[books._balance(oci)] == pytest.approx([15, 15])
    assert result[books.bs.total_assets] == pytest.approx([1_097.16, 1_094.32])
    assert result[books.bs.total_equity] == pytest.approx([1_097.16, 1_094.32])


def test_s7_opening_intercompany_loan_is_created_on_both_sides_and_eliminated():
    model = b.Model("s7-loan", start=0, periods=1, step=year)
    parent = model.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = model.entity("Sub", standard=b.IFRS, currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=270 * JPY)
    parent_loan = sub.bs.loan("Parent loan", opening=100 * JPY, counterparty=parent).counterparty
    sub.bs.opening(cash=300 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 170 * JPY, "nci": 100 * JPY})

    result = model.render()
    books = group.books

    assert parent_loan is not None
    assert result[books.bs.total_assets] == pytest.approx([1_070])
    assert result[books.bs.total_liabilities] == pytest.approx([0])
    assert result[books.bs.total_equity] == pytest.approx([1_070])
    assert result[books._balance(next(a for a in books._accounts if a.name == "Parent loan"))] == pytest.approx([0])


def test_s7_opening_receivable_creates_payable_and_both_are_eliminated():
    model = b.Model("s7-receivable", start=0, periods=1, step=year)
    parent = model.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = model.entity("Sub", standard=b.IFRS, currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=100 * JPY)
    receivable = parent.bs.receivable("Sub receivable", opening=100 * JPY, counterparty=sub)
    sub.bs.opening(cash=100 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 1.0, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 100 * JPY, "nci": 0 * JPY})

    result = model.render()
    books = group.books
    receivable_account = next(a for a in books._accounts if a.name == "Sub receivable" and a.side == "asset")
    payable_account = next(a for a in books._accounts if a.name == "Sub receivable (Parent)" and a.side == "liability")

    assert receivable.counterparty is not None
    assert result[books._balance(receivable_account)] == pytest.approx([0])
    assert result[books._balance(payable_account)] == pytest.approx([0])
    assert result[books.bs.total_assets] == pytest.approx([1_200])
    assert result[books.bs.total_liabilities] == pytest.approx([0])
    assert result[books.bs.total_equity] == pytest.approx([1_200])


def test_s7_opening_oci_recycling_uses_nci_component_share():
    model = b.Model("s7-oci-recycle", start=0, periods=1, step=year)
    parent = model.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = model.entity("Sub", standard=b.IFRS, currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=380 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.oci("Translation reserve", 0 * JPY, against=sub.bs.cash, recycle=True)
    sub.oci_release("Translation reserve", 30 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * JPY, "nci": 100 * JPY,
                       "oci": {"Translation reserve": (20 * JPY, 10 * JPY)}})

    result = model.render()
    books = group.books
    nci = next(a for a in books._accounts if a.kind == "nci")
    oci = next(a for a in books._accounts if a.name == "Translation reserve")

    assert result[books.net_income] == pytest.approx([30])
    assert _pl_values(result, books, books._group_profit_attribution["nci_label"]) == pytest.approx([10])
    assert _pl_values(result, books, books._group_profit_attribution["parent_label"]) == pytest.approx([20])
    assert result[books._balance(oci)] == pytest.approx([0])
    assert result[books._balance(nci)] == pytest.approx([100])


def test_s7_opening_oci_transfer_to_retained_earnings_uses_nci_component_share():
    model = b.Model("s7-oci-transfer", start=0, periods=1, step=year)
    parent = model.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = model.entity("Sub", standard=b.IFRS, currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=380 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.oci("Translation reserve", 0 * JPY, against=sub.bs.cash, recycle=False)
    sub.oci_release("Translation reserve", 30 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * JPY, "nci": 100 * JPY,
                       "oci": {"Translation reserve": (20 * JPY, 10 * JPY)}})

    result = model.render()
    books = group.books
    nci = next(a for a in books._accounts if a.kind == "nci")
    oci = next(a for a in books._accounts if a.name == "Translation reserve")

    assert result[books.net_income] == pytest.approx([0])
    assert result[books._balance(oci)] == pytest.approx([0])
    assert result[books._balance(nci)] == pytest.approx([100])
    assert result[books._balance(books.retained_earnings)] == pytest.approx([1_000])


def test_s7_opening_parent_oci_is_recycled_when_control_is_lost():
    model = b.Model("s7-oci-loss", start=0, periods=2, step=year)
    parent = model.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = model.entity("Sub", standard=b.IFRS, currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=380 * JPY)
    sub.bs.opening(cash=500 * JPY)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * JPY, "nci": 100 * JPY,
                       "oci": {"Translation reserve": (20 * JPY, 10 * JPY)}})
    group.own(sub, 0, since=1, proceeds=500 * JPY)

    result = model.render()
    books = group.books
    nci = next(a for a in books._accounts if a.kind == "nci")
    oci = next(a for a in books._accounts if a.name == "Translation reserve")

    assert result[books.net_income] == pytest.approx([0, 120])
    assert result[books._balance(oci)] == pytest.approx([20, 0])
    assert result[books._balance(nci)] == pytest.approx([100, 0])


def test_s7_opening_oci_transfers_with_controlled_share_purchase():
    model = b.Model("s7-oci-purchase", start=0, periods=3, step=year)
    parent = model.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = model.entity("Sub", standard=b.IFRS, currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=380 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.oci("Translation reserve", 0 * JPY, against=sub.bs.cash, recycle=True)
    sub.oci_release("Translation reserve", model.series(data={2: 30 * JPY}))
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * JPY, "nci": 100 * JPY,
                       "oci": {"Translation reserve": (20 * JPY, 10 * JPY)}})
    group.own(sub, 0.9, since=1, consideration=50 * JPY)

    result = model.render()
    books = group.books
    nci = next(a for a in books._accounts if a.kind == "nci")
    oci = next(a for a in books._accounts if a.name == "Translation reserve")
    capital_surplus = next(a for a in books._accounts if a.name == books.label("capital_surplus"))

    assert result[books._balance(oci)] == pytest.approx([20, 25, 0])
    assert result[books._balance(nci)] == pytest.approx([100, 50, 50])
    assert result[books._balance(capital_surplus)] == pytest.approx([0, -5, -5])
    assert _pl_values(result, books, books._group_profit_attribution["nci_label"]) == pytest.approx([0, 0, 5])


def test_s7_opening_oci_transfers_to_nci_on_controlled_share_sale():
    model = b.Model("s7-oci-sale", start=0, periods=2, step=year)
    parent = model.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = model.entity("Sub", standard=b.IFRS, currency=JPY)
    parent.bs.opening(cash=600 * JPY)
    shares = parent.bs.other_asset("Sub shares", opening=380 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.oci("Translation reserve", 0 * JPY, against=sub.bs.cash, recycle=True)
    group = model.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * JPY, "nci": 100 * JPY,
                       "oci": {"Translation reserve": (20 * JPY, 10 * JPY)}})
    group.own(sub, 0.7, since=1, proceeds=50 * JPY)

    result = model.render()
    books = group.books
    nci = next(a for a in books._accounts if a.kind == "nci")
    oci = next(a for a in books._accounts if a.name == "Translation reserve")
    capital_surplus = next(a for a in books._accounts if a.name == books.label("capital_surplus"))

    assert result[books._balance(oci)] == pytest.approx([20, 17.5])
    assert result[books._balance(nci)] == pytest.approx([100, 150])
    assert result[books._balance(capital_surplus)] == pytest.approx([0, 2.5])


def test_s6_asset_trade_balance_survives_later_loss_of_control():
    m, parent, sub, group = _s6_group(periods=3)
    parent.pl.revenue("Parts", 100 * JPY, counterparty=sub.bs.inventory, margin=0.3,
                      used=b.delay(1))
    parent.pl.cogs("Production cost", 70 * JPY)
    group.own(sub, 0.0, since=1, proceeds=0 * JPY)

    result = m.render()
    statement = result.bs(group)

    assert statement.row(group.books.label("total_assets")) == pytest.approx(
        statement.row(group.books.label("total_liabilities_equity")))


def test_s8a_translates_profit_net_assets_and_cta_at_current_rates():
    m = b.Model("s8-a", start=0, periods=2, step=year)
    m.fx(USD, JPY, closing=[150, 160], average=[145, 155], opening=150)
    parent = m.entity("Parent", currency=JPY)
    sub = m.entity("US Inc.", currency=USD)
    parent.bs.opening(cash=15_000 * JPY)
    sub.bs.opening(cash=100 * USD)
    sub.pl.revenue("Profit", 10 * USD)
    group = m.group("Group", parent=parent)
    group.own(sub, 1, since=0, method="consolidate", consideration=15_000 * JPY,
              goodwill_life=10 * year)

    result = m.render()
    books = group.books

    assert result[books.net_income] == pytest.approx([1_450, 1_550])
    assert result[books.bs.total_assets] == pytest.approx([16_500, 19_200])
    cta = next(account for account in books._accounts if account.kind == "oci")
    assert result[books._balance(cta)] == pytest.approx([50, 1_200])
    assert result.pl(group).row("Other comprehensive income") == pytest.approx([50, 1_150])
    assert result[books.cf.fx] == pytest.approx([50, 1_150])


def test_s8_splits_translation_adjustment_with_nci():
    m = b.Model("s8-nci", start=0, periods=2, step=year)
    m.fx(USD, JPY, closing=[150, 160], average=[145, 155], opening=150)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = m.entity("US Inc.", standard=b.IFRS, currency=USD)
    parent.bs.opening(cash=12_000 * JPY)
    sub.bs.opening(cash=100 * USD)
    sub.pl.revenue("Profit", 10 * USD)
    group = m.group("Group", parent=parent)
    group.own(sub, 0.8, since=0, method="consolidate", consideration=12_000 * JPY)

    result = m.render()
    books = group.books
    cta = next(account for account in books._accounts if account.kind == "oci")
    nci = next(account for account in books._accounts if account.kind == "nci")

    assert result[books._balance(cta)] == pytest.approx([40, 960])
    assert result[books._balance(nci)] == pytest.approx([3_300, 3_840])


def test_s8_translates_goodwill_at_closing_rate():
    m = b.Model("s8-goodwill", start=0, periods=2, step=year)
    m.fx(USD, JPY, closing=[150, 160], average=[145, 155], opening=150)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = m.entity("US Inc.", standard=b.IFRS, currency=USD)
    parent.bs.opening(cash=18_000 * JPY)
    sub.bs.opening(cash=100 * USD)
    group = m.group("Group", parent=parent)
    group.own(sub, 0.8, since=0, method="consolidate", consideration=18_000 * JPY)

    result = m.render()
    books = group.books
    goodwill = next(account for account in books._accounts
                    if account.kind == "other_asset" and account.name == books.label("goodwill"))
    cta = next(account for account in books._accounts if account.kind == "oci")
    nci = next(account for account in books._accounts if account.kind == "nci")

    assert result[books._balance(goodwill)] == pytest.approx([6_000, 6_400])
    assert result[books._balance(cta)] == pytest.approx([0, 1_200])
    assert result[books._balance(nci)] == pytest.approx([3_000, 3_200])
    assert result[books.other_comprehensive_income] == pytest.approx([0, 1_400])


def test_s8_translates_fair_value_adjustments_at_closing_rate():
    m = b.Model("s8-fair-value", start=0, periods=2, step=year)
    m.fx(USD, JPY, closing=[150, 160], average=[145, 155], opening=150)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = m.entity("US Inc.", standard=b.IFRS, currency=USD)
    parent.bs.opening(cash=22_500 * JPY)
    sub.bs.opening(cash=100 * USD)
    land = sub.bs.other_asset("Land", opening=30 * USD)
    group = m.group("Group", parent=parent)
    group.own(sub, 1, since=0, method="consolidate", consideration=22_500 * JPY,
              fair_value={land: (20 * USD, 4 * year)}, tax_basis="stepped_up")

    result = m.render()
    books = group.books
    land_account = next(account for account in books._accounts if account.name == "Land" and account.side == "asset")
    cta = next(account for account in books._accounts if account.kind == "oci")

    assert result[books._balance(land_account)] == pytest.approx([6_750, 6_400])
    assert result[books._balance(cta)] == pytest.approx([-25, 1_400])


def test_s8_records_intercompany_trade_in_buyers_currency():
    m = b.Model("s8-trade", start=0, periods=1, step=year)
    m.fx(USD, EUR, closing=[0.95], average=[0.9], opening=0.95)
    seller = m.entity("Seller", standard=b.IFRS, currency=USD)
    buyer = m.entity("Buyer", standard=b.IFRS, currency=EUR)
    buyer.bs.opening(cash=90 * EUR)
    sale = seller.pl.revenue("Service", 100 * USD, counterparty=buyer.pl.cogs)

    result = m.render()

    assert result[sale.counterparty] == pytest.approx([90])


def test_s8_consolidates_cross_currency_trade_difference_to_cta():
    m = b.Model("s8-trade-cta", start=0, periods=1, step=year)
    m.fx(USD, JPY, closing=[150], average=[145], opening=150)
    m.fx(USD, EUR, closing=[0.9], average=[0.9], opening=0.9)
    m.fx(EUR, JPY, closing=[160], average=[160], opening=160)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    seller = m.entity("Seller", standard=b.IFRS, currency=USD)
    buyer = m.entity("Buyer", standard=b.IFRS, currency=EUR)
    parent.bs.opening(cash=14_400 * JPY)
    buyer.bs.opening(cash=90 * EUR)
    sale = seller.pl.revenue("Service", 100 * USD, counterparty=buyer.pl.cogs)
    group = m.group("Group", parent=parent)
    group.own(seller, 1, since=0, method="consolidate", consideration=0 * JPY)
    group.own(buyer, 1, since=0, method="consolidate", consideration=14_400 * JPY)

    result = m.render()
    books = group.books
    cta = next(account for account in books._accounts if account.kind == "oci")

    assert result[sale.counterparty] == pytest.approx([90])
    assert result[books.net_income] == pytest.approx([0])
    assert result[books._balance(books._cash_account)] == pytest.approx([15_000])
    assert result[books._balance(cta)] == pytest.approx([600])


def test_s8_translates_intercompany_inventory_at_buyer_average_rate():
    m = b.Model("s8-inventory-trade", start=0, periods=1, step=year)
    m.fx(USD, JPY, closing=[150], average=[145], opening=150)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY, tax_rate=0.3)
    sub = m.entity("US Inc.", standard=b.IFRS, currency=USD, tax_rate=0.1)
    parent.bs.opening(cash=20_000 * JPY)
    sale = sub.pl.revenue("Parts", 100 * USD, counterparty=parent.bs.inventory,
                          margin=0.3, used=b.delay(1))
    sub.pl.cogs("Production cost", 70 * USD)
    group = m.group("Group", parent=parent)
    group.own(sub, 1, since=0, method="consolidate", consideration=0 * JPY)

    result = m.render()
    books = group.books
    inventory = next(account for account in books._accounts if account.name == "Parts (US Inc.)")
    cta = next(account for account in books._accounts if account.kind == "oci")

    assert result[sale.counterparty] == pytest.approx([14_500])
    assert result[books._balance(inventory)] == pytest.approx([10_150])
    assert result[books._balance(cta)] == pytest.approx([150])


@pytest.mark.parametrize("net_investment", [False, True])
def test_s8_translates_intercompany_loan_and_routes_fx_difference(net_investment):
    m = b.Model(f"s8-loan-{net_investment}", start=0, periods=2, step=year)
    m.fx(USD, JPY, closing=[150, 160], average=[145, 155], opening=150)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = m.entity("US Inc.", standard=b.IFRS, currency=USD)
    parent.bs.opening(cash=15_000 * JPY)
    sub.bs.loan("Parent loan", draw={0: 100 * USD}, rate=None, counterparty=parent,
                net_investment=net_investment)
    group = m.group("Group", parent=parent)
    group.own(sub, 1, since=0, method="consolidate", consideration=0 * JPY)

    result = m.render()
    books = group.books
    if net_investment:
        assert result[books.net_income] == pytest.approx([0, 0])
        assert result[books.other_comprehensive_income] == pytest.approx([500, 1_000])
    else:
        assert result[books.net_income] == pytest.approx([500, 1_000])


@pytest.mark.parametrize(
    "standard,expected_release,expected_cta",
    [(b.IFRS, 40, 0), (b.USGAAP, 40, 0), (b.JGAAP, 20, 20)],
)
def test_s8_recycles_translation_reserve_on_loss_of_control(
        standard, expected_release, expected_cta):
    m = b.Model(f"s8-loss-{standard.name}", start=0, periods=2, step=year)
    m.fx(USD, JPY, closing=[150, 160], average=[145, 155], opening=150)
    parent = m.entity("Parent", standard=standard, currency=JPY)
    sub = m.entity("US Inc.", standard=standard, currency=USD)
    parent.bs.opening(cash=50_000 * JPY)
    sub.bs.opening(cash=100 * USD)
    sub.pl.revenue("Profit", 10 * USD)
    group = m.group("Group", parent=parent)
    acquisition = {"goodwill_life": 10 * year} if standard is b.JGAAP else {}
    if standard is b.USGAAP:
        acquisition.update(nci="fair_value", nci_value=3_000 * JPY)
    group.own(sub, 0.8, since=0, method="consolidate", consideration=12_000 * JPY,
              **acquisition)
    loss = {"retained_value": 7_000 * JPY} if standard is not b.JGAAP else {}
    group.own(sub, 0.4, since=1, method="equity", proceeds=7_000 * JPY, **loss)

    result = m.render()
    books = group.books
    cta = next(account for account in books._accounts if account.kind == "oci")
    release = result.pl(books).row(f"OCI release: {cta.name}")

    assert release == pytest.approx([0, expected_release])
    associate_cta = 460
    assert result[books._balance(cta)] == pytest.approx([40, expected_cta + associate_cta])
    expected_oci_change = associate_cta - expected_release
    assert result[books.other_comprehensive_income] == pytest.approx([50, expected_oci_change])


def test_s8_translates_opening_foreign_nci_and_fair_value_at_fx_rates():
    m = b.Model("s8-opening", start=0, periods=1, step=year)
    m.fx(USD, JPY, closing=[160], average=[155], opening=150)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = m.entity("US Inc.", standard=b.IFRS, currency=USD, tax_rate=0)
    parent.bs.opening(cash=20_000 * JPY)
    shares = parent.bs.other_asset("US shares", opening=18_000 * JPY)
    sub.bs.opening(cash=100 * USD)
    land = sub.bs.other_asset("Land", opening=30 * USD)
    group = m.group("Group", parent=parent)
    group.own(sub, 0.8, since="before", method="consolidate", investment=shares,
              opening={"goodwill": 0 * USD, "nci": 4_500 * JPY,
                       "fair_value": {land: (20 * USD, 4 * year)}})

    result = m.render()
    books = group.books
    group_land = next(account for account in books._accounts
                      if account.name == "Land" and account.side == "asset")
    cta = next(account for account in books._accounts if account.kind == "oci")

    assert result[books._balance(group_land)] == pytest.approx([7_200])
    assert result[books.other_comprehensive_income] == pytest.approx([1_475])
    assert result[books._balance(cta)] == pytest.approx([1_180])


def test_s8_consolidates_foreign_dividend_at_transaction_rate():
    m = b.Model("s8-dividend", start=0, periods=1, step=year)
    m.fx(USD, JPY, closing=[150], average=[145], opening=150)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = m.entity("US Inc.", standard=b.IFRS, currency=USD)
    parent.bs.opening(cash=30_000 * JPY)
    sub.bs.opening(cash=100 * USD)
    sub.bs.dividend("Dividend", 10 * USD, counterparty=parent, fx_rate=148)
    group = m.group("Group", parent=parent)
    group.own(sub, 1, since=0, method="consolidate", consideration=15_000 * JPY)

    result = m.render()
    books = group.books

    assert result[books._balance(books._cash_account)] == pytest.approx([29_980])
    assert result[books.net_income] == pytest.approx([0])
    assert result[books.cf.fx] == pytest.approx([-20])

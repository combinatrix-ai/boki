import pytest

import boki as b
from boki.units import JPY, USD, year


def test_s8_fx_rates_have_quote_per_base_units():
    m = b.Model("s8-fx", start=0, periods=2, step=year)
    fx = m.fx(USD, JPY, closing=[150, 160], average=[145, 155], opening=150)

    result = m.render()

    assert fx.closing.unit == (JPY / USD).dims
    assert fx.average.unit == (JPY / USD).dims
    assert result[fx.closing] == [150, 160]
    assert result[fx.average] == [145, 155]


def test_entity_exposes_its_functional_currency():
    m = b.Model("currency", start=0, periods=1, step=year)
    entity = m.entity("US Inc.", currency=USD)

    assert entity.currency is USD


def test_s8_capital_and_dividend_use_transaction_fx_rate_when_given():
    model = b.Model("fx-transaction-rate", start=0, periods=1, step=year)
    model.fx(USD, JPY, closing=[150], average=[145], opening=150)
    parent = model.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = model.entity("US Inc.", standard=b.IFRS, currency=USD)
    parent.bs.opening(cash=20_000 * JPY)

    capital = sub.bs.capital("Paid in", 100 * USD, at=0, counterparty=parent, fx_rate=147)
    dividend = sub.bs.dividend("Dividend", 10 * USD, counterparty=parent, fx_rate=148)
    result = model.render()

    assert result[capital.counterparty] == pytest.approx([14_700])
    assert result[dividend.counterparty] == pytest.approx(1_480)

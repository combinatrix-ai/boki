import pytest

import boki as b
from boki.lib import compound, discount, fade, irr, npv
from boki.units import USD


def test_expressions_lag_where_and_reductions():
    m = b.Model("t", start="2027-01", periods=4, step=b.month)
    x = m.series("x", m.t * 10)
    prev = x.lag(1, fill=0)
    r = m.render()
    assert r[x] == [0, 10, 20, 30]
    assert r[prev] == [0, 0, 10, 20]
    assert r[x.lag(-1)] == [10, 20, 30, None]
    assert r[x.where(m.t >= 2, -1)] == [-1, -1, 20, 30]
    assert r[x.where(m.t >= 2).min()] == 20
    assert r[x.sum()] == 60
    assert r[x.change] == [0, 10, 10, 10]
    assert r[x[2]] == 20


def test_lag_by_a_series_offset():
    m = b.Model("t", start="2027-01", periods=4, step=b.month)
    x = m.series("x", m.t * 10)
    k = m.series("k", data={0: 1, 1: 0, 2: 2, 3: 5})
    assert m.render()[x.lag(k, fill=-1)] == [-1, 10, 0, -1]


def test_series_have_no_truth_value_at_build_time():
    m = b.Model("t", start=0, periods=3, step=b.year)
    with pytest.raises(TypeError, match="no truth value"):
        if m.t > 1:
            pass


def test_decorated_function_reads_values_and_recurses():
    m = b.Model("t", start=0, periods=5, step=b.year)
    churn = m.input("churn", 0.5)

    @m.series
    def customers(t):
        if t == 0:
            return 100
        return customers[t - 1] * (1 - churn[t]) + 10

    assert m.render()[customers] == [100, 60.0, 40.0, 30.0, 25.0]


def test_cycle_is_reported_with_the_chain():
    m = b.Model("t", start=0, periods=2, step=b.year)
    debt = m.series("debt")
    uses = m.series("uses", 1000 + 0.05 * debt)
    debt.define(0.8 * uses)
    with pytest.raises(b.CycleError, match=r"circular reference: debt -> uses -> debt \(in period 0\)"):
        m.render()[debt]


def test_forward_declaration_without_a_cycle():
    m = b.Model("t", start=0, periods=3, step=b.year)
    need = m.series("need")
    draw = m.series("draw", 0.6 * need)
    need.define(m.t * 100 + draw.lag(1, fill=0))
    assert m.render()[need] == [0, 100, 260]


def test_data_points_and_dates():
    m = b.Model("t", start="2027-04", end="2027-09", step=b.month)
    one_off = m.series("one-off", data={"2027-07": 500, 0: 1})
    r = m.render()
    assert r[one_off] == [1, 0, 0, 500, 0, 0]
    assert m.timeline.index("2027-07-15") == 3


def test_inputs_scenarios_and_choices():
    m = b.Model("t", start=0, periods=1, step=b.year)
    churn = m.input("churn", 0.03, scenarios={"bear": 0.05})
    method = m.input("method", "ddb", choices={"straight": 1, "ddb": 2})
    assert m.render()[churn] == 0.03
    assert m.render(scenario="bear")[churn] == 0.05
    assert m.render(inputs={"churn": 0.1})[churn] == 0.1
    assert m.render()[method] == 2
    with pytest.raises(ValueError, match="not one of"):
        m.render(inputs={"method": "sum-of-years"})[method]


def test_names_must_be_unique():
    m = b.Model("t", start=0, periods=1, step=b.year)
    m.series("x", 1)
    with pytest.raises(ValueError, match="already exists"):
        m.series("x", 2)


def test_entity_name_cannot_match_a_group_name():
    m = b.Model("t", start=0, periods=1, step=b.year)
    parent = m.entity("parent")
    m.group("shared", parent=parent)

    with pytest.raises(ValueError, match="already exists"):
        m.entity("shared")


def test_solve_scalar_fixed_point():
    m = b.Model("t", start=0, periods=1, step=b.year)
    size = m.unknown("debt size", init=0)
    uses = 1000 + 0.05 * size
    m.solve(size, size == 0.8 * uses)
    r = m.render()
    assert r[size] == pytest.approx(800 / 0.96)


def test_render_fix_skips_the_solve_and_uses_the_given_value():
    m = b.Model("t", start=0, periods=1, step=b.year)
    size = m.unknown("debt size", init=0)
    uses = 1000 + 0.05 * size
    m.solve(size, size == 0.8 * uses)
    r = m.render(fix={size: 500})
    assert r[size] == 500
    assert r[uses] == pytest.approx(1025)


def test_solve_fixed_point_through_dict_amounts():
    # Amounts given as a dict (Data points) must follow the unknown during
    # m.solve iterations. Render.invalidate() used to leave the Data-point
    # cache (_sparse) stale, so a dict amount froze at its first-iteration
    # value and solve silently returned a self-contradictory result.
    from boki.units import USD
    m = b.Model("t", start=0, periods=3, step=b.year)
    co = m.entity("co", standard=b.USGAAP)
    u = m.unknown("u", init=500, unit=USD.dims)
    loan = co.bs.loan("loan", draw={0: u}, rate=None)
    m.solve(u, u == loan.balance[0] * 0.5 + 500 * USD)
    r = m.render()
    assert r[u] == pytest.approx(1000.0, rel=1e-6)
    assert r[loan.balance][0] == pytest.approx(float(r[u]), rel=1e-9)  # the draw must equal the solved unknown


def test_solve_per_period_smallest_integer():
    m = b.Model("t", start=0, periods=4, step=b.year)
    demand = m.series("demand", m.input("d", b.step({0: 3, 2: 10})))
    hires = m.unknown("hires", per_period=True)
    capacity = m.series("capacity", hires.cumsum() * 2.5)
    m.solve(hires, capacity >= demand, integer=True, min=0)
    r = m.render()
    assert r[hires] == [2, 0, 2, 0]
    assert r[capacity] == [5.0, 5.0, 10.0, 10.0]


def test_solve_rejects_a_declared_series_and_names_m_unknown():
    # A series declared with m.series("x") used to fail at render with "declared but never defined".
    m = b.Model("t", start=0, periods=2, step=b.year)
    hires = m.series("hires")
    with pytest.raises(TypeError, match=r"m\.unknown\('hires'"):
        m.solve(hires, hires >= 3, integer=True)


def _short_cash_model(**kw):
    m = b.Model("t", start=0, periods=3, step=b.year)
    cash = m.series("cash", 10 - m.t * 6)
    m.check(cash >= 0, "cash never runs out", **kw)
    return m, cash


def test_a_failing_check_stops_render_and_hands_back_the_result():
    m, cash = _short_cash_model()
    with pytest.raises(b.CheckFailed) as e:
        m.render()
    assert e.value.result[cash] == [10, 4, -2]
    assert "cash never runs out (fails in 2; worst 2: cash -2 vs 0)" in str(e.value)
    [failure] = e.value.failures
    assert (failure.name, failure.level, failure.passed, failure.periods) == ("cash never runs out", "error", False, ["2"])
    assert e.value.result.checks == [failure]


def test_the_message_names_both_sides_of_a_comparison_at_the_worst_period():
    m = b.Model("t", start="2028-01", periods=8, step=b.month)
    cash = m.series("Minimum cash", 5_000_000 - m.t * 3_100_000)
    m.check(cash >= 5_000_000 - m.t * 0, "minimum cash")
    m.check((cash > 0) & (m.t < 100), "no sides")
    with pytest.raises(b.CheckFailed) as e:
        m.render()
    lines = str(e.value).splitlines()[1:]
    assert lines[0] == ("minimum cash (fails in 2028-02, 2028-03, 2028-04, 2028-05, 2028-06, ...; "
                        "worst 2028-08: Minimum cash -16,700,000 vs expression 5,000,000)")
    assert lines[-1] == "no sides (fails in 2028-03, 2028-04, 2028-05, 2028-06, 2028-07, ...)"


def test_an_unnamed_constant_side_is_shown_as_its_value():
    m = b.Model("t", start="2028-01", periods=2, step=b.month)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=1 * USD)
    m.check(co.bs.cash >= 5 * USD, "minimum cash")
    with pytest.raises(b.CheckFailed, match=r"worst 2028-01: Cash 1 vs 5\)"):
        m.render()


def test_a_warn_level_check_warns_and_does_not_stop():
    m, cash = _short_cash_model(level="warn")
    with pytest.warns(UserWarning, match="check failed: cash never runs out"):
        r = m.render()
    assert [(c.level, c.passed) for c in r.checks] == [("warn", False)]


def test_an_off_level_check_is_not_evaluated_or_reported(recwarn):
    m, cash = _short_cash_model(level="off")
    r = m.render()
    assert r.checks == [] and not recwarn.list


def test_render_checks_warn_downgrades_error_checks_but_not_off_checks():
    m, cash = _short_cash_model()
    m.check(cash >= 100, "off stays off", level="off")
    with pytest.warns(UserWarning, match="cash never runs out"):
        r = m.render(checks="warn")
    assert [(c.name, c.level) for c in r.checks] == [("cash never runs out", "warn")]


def test_invalid_levels_are_rejected():
    m = b.Model("t", start=0, periods=3, step=b.year)
    with pytest.raises(ValueError, match="'error', 'warn', 'off'"):
        m.check(m.t >= 0, "x", level="strict")
    with pytest.raises(ValueError, match="checks="):
        m.render(checks="error")
    with pytest.raises(ValueError, match="'error', 'warn', 'off'"):
        m.entity("Co").checks.cash(level="loud")


def _poor_entity():
    m = b.Model("t", start=0, periods=3, step=b.year)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=10 * USD)
    co.pl.sga("rent", 8 * USD)
    return m, co


def test_every_entity_has_a_cash_check_that_stops_render_by_default():
    m, co = _poor_entity()
    with pytest.raises(b.CheckFailed, match="Co: cash is not negative") as e:
        m.render()
    assert e.value.result[co.bs.cash] == pytest.approx([2, -6, -14])
    assert [c.name for c in e.value.result.checks] == ["Co: cash is not negative"]


def test_the_cash_check_can_be_a_warning_or_off(recwarn):
    m, co = _poor_entity()
    co.checks.cash(level="warn")
    with pytest.warns(UserWarning, match="Co: cash is not negative"):
        assert m.render().checks[0].level == "warn"
    co.checks.cash(level="off")
    recwarn.clear()
    assert m.render().checks == [] and not recwarn.list
    co.checks.cash()
    with pytest.raises(b.CheckFailed):
        m.render()


def test_library_shapes_and_valuation():
    m = b.Model("t", start=0, periods=4, step=b.year)
    assert m.render()[compound(100, 0.1)] == pytest.approx([100, 110, 121, 133.1])
    assert m.render()[fade(1.0, 2.0, over=(1, 3))] == [1.0, 1.0, 1.5, 2.0]
    assert m.render()[discount(0.1)] == pytest.approx([1 / 1.1, 1 / 1.1 ** 2, 1 / 1.1 ** 3, 1 / 1.1 ** 4])
    cf = m.series("cf", b.step({0: -100, 1: 40}))
    at_year0 = -100 + 40 / 1.1 + 40 / 1.21 + 40 / 1.331
    assert m.render()[npv(cf, 0.1, at=0)] == pytest.approx(at_year0)                  # value at the end of period 0
    assert m.render()[npv(cf, 0.1)] == pytest.approx(at_year0 / 1.1)                  # default: start of the model
    assert m.render()[npv(cf, 0.1, initial=-5)] == pytest.approx(at_year0 / 1.1 - 5)
    assert m.render()[(cf * discount(0.1)).sum()] == pytest.approx(at_year0 / 1.1)    # same timing as discount()
    assert m.render()[irr(cf)] == pytest.approx(0.09701, abs=1e-5)


def test_npv_discounts_each_period_at_its_own_rate():
    m = b.Model("t", start=0, periods=3, step=b.year)
    rate = m.series("rate", b.by_year({0: 0.10, 1: 0.20, 2: 0.05}))
    cf = m.series("cf", b.by_year({0: 100, 1: 50, 2: 80}))
    growth = [1.1, 1.1 * 1.2, 1.1 * 1.2 * 1.05]                  # the product of (1 + rate) up to each period
    r = m.render()
    at_start = sum(c / g for c, g in zip([100, 50, 80], growth))
    assert r[npv(cf, rate)] == pytest.approx(at_start)
    assert r[npv(cf, rate)] == pytest.approx(r[(cf * discount(rate)).sum()])     # same timing as discount()
    assert r[npv(cf, rate, at=0)] == pytest.approx(at_start * growth[0])
    assert r[npv(cf, rate, at=2)] == pytest.approx(at_start * growth[2])
    assert r[npv(cf, rate, initial=-120)] == pytest.approx(at_start - 120)
    assert r[npv(cf, rate, at=1, initial=-120)] == pytest.approx((at_start - 120) * growth[1])
    flat = m.series("flat rate", 0.1 + 0 * m.t)                   # a series that happens to be constant
    assert r[npv(cf, flat, at=0, initial=-5)] == pytest.approx(r[npv(cf, 0.1, at=0, initial=-5)])
    with pytest.raises(ValueError, match="at="):
        npv(cf, rate, at=-2)
    with pytest.raises(IndexError, match="outside the model"):
        m.render()[npv(cf, rate, at=3)]


def test_variable_period_lengths():
    tl = b.timeline("2015-09", [(2, b.month), (2, 3 * b.month)])
    m = b.Model("t", timeline=tl)
    r = m.render()
    assert [p.label for p in tl.periods] == ["2015-09", "2015-10", "2015-11", "2016-02"]
    assert r[m.period_length] == [1, 1, 3, 3]
    assert m.timeline.index("2016-01-20") == 2


def test_month_end_starts_and_period_boundaries_stay_aligned():
    from datetime import date

    from boki.model import add_months

    m = b.Model("t", start="2027-01-31", periods=3, step=b.month)
    periods = m.timeline.periods
    assert [(p.start, p.end) for p in periods] == [
        (date(2027, 1, 31), date(2027, 2, 28)),
        (date(2027, 2, 28), date(2027, 3, 31)),
        (date(2027, 3, 31), date(2027, 4, 30)),
    ]
    assert add_months(date(2027, 1, 31), 2) == date(2027, 3, 31)
    assert m.timeline.index("2027-03-30") == 1


def test_expect_lists_all_mismatches():
    m = b.Model("t", start=0, periods=2, step=b.year)
    x = m.series("x", m.t + 1)
    r = m.render()
    b.expect(r, {x[0]: 1, x[1]: 2})
    with pytest.raises(AssertionError, match=r"x\[0\]: expected 5"):
        b.expect(r, {x[0]: 5, x[1]: 2})


def test_render_inputs_by_node_or_name_and_unknown_keys_fail():
    m = b.Model("m", start=0, periods=1, step=b.year)
    x = m.input("x", 1)
    y = m.series("y", x * 2)
    assert m.render(inputs={x: 5})[y] == 10
    assert m.render(inputs={"x": 3})[y] == 6
    with pytest.raises(KeyError, match="no input named 'z'"):
        m.render(inputs={"z": 1})


def test_solve_goal_seeks_a_scalar_unknown():
    from boki.lib import npv
    m = b.Model("m", start=0, periods=5, step=b.year)
    price = m.unknown("price", init=1.0)
    cash = m.series("cash", (price * 10).where(m.t > 0, -100.0))
    m.solve(price, npv(cash, 0.1) == 0)
    r = m.render()
    assert r[npv(cash, 0.1)] == pytest.approx(0, abs=1e-6)
    assert r[price] == pytest.approx(100 / sum(10 / 1.1 ** t for t in range(1, 5)))


def test_shared_secant_iteration_uses_the_given_probes():
    from boki.model import _secant_iterate

    probes = []

    def residual(x):
        probes.append(x)
        return x * x - 2

    root = _secant_iterate(residual, 1.0, 2.0, tol=1e-12, max_iter=20, inclusive=False,
                           scale=None, stalled=lambda value: f"stalled at {value}",
                           exhausted="did not converge")
    assert probes[:2] == [1.0, 2.0]
    assert root == pytest.approx(2 ** 0.5, abs=1e-12)


def test_solve_goal_seek_without_the_unknown_raises():
    # _goal_seek used to treat equal residuals at the two probe points as success
    # without looking at their size, so an equation that never mentions the unknown
    # (a typo, and no solution) rendered successfully with the probe value.
    m = b.Model("m", start=0, periods=3, step=b.year)
    u = m.unknown("u", init=1.0)
    five = m.series("five", 5)
    m.solve(u, five == 7)
    with pytest.raises(ArithmeticError, match="could not find 'u'"):
        m.render()


def test_solve_goal_seek_already_satisfied_renders():
    # A residual that is zero at both probe points is a genuine success, not stagnation.
    m = b.Model("m", start=0, periods=3, step=b.year)
    u = m.unknown("u", init=1.0)
    five = m.series("five", 5)
    m.solve(u, five == 5)
    r = m.render()
    assert r[five] == 5


def test_solve_goal_seek_accepts_the_float_limit_of_large_terms():
    # With terms in the hundreds of billions, rounding leaves lhs - rhs near 1e-5 at
    # the best float of the unknown, above the absolute tolerance of an equation whose
    # rhs is 0. The secant stops moving there; that is a solution, not stagnation.
    from boki.lib import npv
    m = b.Model("m", start=0, periods=5, step=b.year)
    price = m.unknown("price", init=0.1)
    cash = m.series("cash", (price * 1.7e11).where(m.t > 0, -1.234567e11))
    m.solve(price, npv(cash, 0.1) == 0)
    r = m.render()
    assert r[price] == pytest.approx(1.234567e11 / sum(1.7e11 / 1.1 ** t for t in range(1, 5)), rel=1e-12)


def test_solve_per_period_without_the_unknown_raises():
    # The per-period secant had the same stagnation hole as _goal_seek, one step
    # later: with f1 == f0 the step divided by (f1 - f0) and the render died with
    # a raw ZeroDivisionError instead of the usual did-not-converge ArithmeticError.
    m = b.Model("m", start=0, periods=2, step=b.year)
    u = m.unknown("u", init=1.0, per_period=True)
    five = m.series("five", 5)
    m.solve(u, five == 7)
    with pytest.raises(ArithmeticError, match="did not converge for 'u'"):
        m.render()


def test_lookup_bands():
    from boki.lib import lookup
    m = b.Model("m", start=0, periods=3, step=b.year)
    x = b.by_year({0: 0.3, 1: 4.0, 2: 99.0})
    assert m.render()[lookup(x, {-1e9: 1, 0.5: 2, 4.0: 3})] == [1, 3, 3]


def test_compare_lists_every_number_and_expect_fails_on_mismatch():
    m = b.Model("m", start=0, periods=3, step=b.year)
    x = m.series("x", b.by_year({0: 1, 1: 2, 2: 3}))
    r = m.render()
    c = b.compare(r, {x: [1, 2, 4], x[0]: 1})
    assert [e.ok for e in c.entries] == [True, True, False, True]
    assert c.mismatches[0].diff == -1
    assert "≠" in str(c)
    with pytest.raises(AssertionError, match=r"x \[2\]: expected 4"):
        b.expect(r, {x: [1, 2, 4]})


def test_a_series_is_not_iterable_and_expect_accepts_series_references():
    m = b.Model("t", start=0, periods=3, step=b.year)
    x = m.series("x", m.t * 2)
    with pytest.raises(TypeError, match="not iterable"):
        list(x)
    r = m.render()
    b.expect(r, {x: b.by_year({0: 0, 1: 2, 2: 4})})
    b.expect(r, {x: [None, 2, None]})                               # periods the source leaves empty are skipped
    with pytest.raises(AssertionError):
        b.expect(r, {x: 2})                                         # one value is compared in every period


def test_expect_compares_dates():
    from datetime import date, datetime
    m = b.Model("t", start="2027-01", periods=2, step=b.month)
    r = m.render()
    b.expect(r, {m.date: [date(2027, 1, 1), datetime(2027, 2, 1)]})      # a source cell read as a datetime at midnight
    with pytest.raises(AssertionError, match=r"expected 2027-03-01, got 2027-02-01"):
        b.expect(r, {m.date: [None, date(2027, 3, 1)]})
    assert "2027-02-01" in str(b.compare(r, {m.date: [None, date(2027, 3, 1)]}))


def test_ssfa_risk_weights():
    from boki.lib import ssfa
    assert ssfa(0.08, 0.0, 0.0, 0.05) == 12.5                        # entirely below KA: 1,250%
    assert ssfa(0.08, 0.0, 0.5, 1.0) == 0.20                         # senior tranche: the 20% floor
    straddle = ssfa(0.08, 0.0, 0.04, 0.12)
    assert 0.5 * 12.5 < straddle < 12.5                              # half below KA at 1,250%, half above it


def test_irr_picks_the_root_where_value_falls_with_the_rate():
    from boki.lib import irr
    m = b.Model("t", start=0, periods=4, step=b.year)
    flows = b.by_year({0: -31, 1: 56, 2: 47, 3: -6})                 # invest, earn, then a closure cost
    r = m.render()
    assert r[irr(flows)] == pytest.approx(1.4, abs=0.1)               # not the negative root near −0.9


def test_time_keys_can_be_dates_or_period_labels():
    from boki.units import JPY, month
    m = b.Model("t", start="2027-04", periods=24, step=month)
    rate = m.series("rate", b.by_year({"2028-04": 0.05}, default=0.03))       # the model year April 2028 falls in
    price = m.series("price", b.step({"2027-04": 100, "2028-06": 120}))
    co = m.entity("Co", currency=JPY)
    loan = co.bs.loan("loan", draw={"2027-07": 50 * JPY})
    r = m.render()
    assert r[rate] == [0.03] * 12 + [0.05] * 12
    assert r[price][13] == 100 and r[price][14] == 120
    assert r[loan][2] == 0 and r[loan][3] == 50
    y = b.Model("y", start=2027, periods=3, step=b.year)                         # periods labelled 2027, 2028, ...
    g = y.series("g", b.by_year({"2028": 0.1}, default=0))
    assert y.render()[g] == [0, 0.1, 0]
    late = y.series("late", b.by_year({"2035": 1}, default=0))
    with pytest.raises(IndexError, match="outside"):
        y.render()[late]


def test_irr_default_replaces_the_no_root_error():
    # Excel models write IFERROR(IRR(...), 0); without default= boki keeps the error, since the flows
    # may be wrong rather than early.
    m = b.Model("t", start=0, periods=3, step=b.year)
    cf = m.series("cf", m.t * 0 - 1.0)
    with pytest.raises(ArithmeticError, match="no sign change"):
        m.render()[irr(cf)]
    assert m.render()[irr(cf, default=0)] == 0
    from boki.lib import xirr
    dated = b.Model("t", start="2027-01", periods=3, step=b.year)
    costs = dated.series("costs", dated.t * 0 - 1.0)
    assert dated.render()[xirr(costs, dated.date, default=-1)] == -1
    with pytest.raises(TypeError, match="takes a number"):
        irr(cf, default="n/a")


def test_running_irr_lets_a_flip_depend_on_the_irr_to_date():
    # A partnership flip: the investor takes 99% until its IRR to date reaches 8%, then 5%. The IRR to date
    # reads only the periods so far, so the share can depend on last period's value without a cycle.
    m = b.Model("flip", start=0, periods=8, step=b.year)
    project = m.series("project", b.by_year({0: -100}, default=25))
    share = m.series("share")
    investor = m.series("investor", project * share)
    to_date = m.series("IRR to date", irr(investor, running=True, default=0))
    share.define(0.99 - 0.94 * (to_date.lag(1, fill=0) >= 0.08))
    r = m.render()
    assert r[to_date][0] == 0                                  # one negative flow: no IRR yet
    assert r[to_date][1] == pytest.approx(-0.75)
    assert r[to_date][5] == pytest.approx(0.0793, abs=1e-4)    # below the target
    assert r[to_date][6] == pytest.approx(0.1298, abs=1e-4)    # reached, so the flip is next period
    assert r[investor][6] == pytest.approx(24.75) and r[investor][7] == pytest.approx(1.25)
    assert r[to_date][-1] == pytest.approx(r[irr(investor)])
    with pytest.raises(TypeError, match="initial="):
        irr(investor, initial=-5, running=True)


def test_negative_base_to_a_fractional_power_is_an_error_not_a_complex_number():
    m = b.Model("t", start=0, periods=2, step=b.year)
    root = m.series("root", (m.t - 5.0) ** 0.5)
    with pytest.raises(ValueError, match="no real value"):
        m.render()[root]


def test_by_month_gives_seasonality_by_calendar_month():
    m = b.Model("t", start="2027-11", periods=4, step=b.month)
    season = m.input("season", b.by_month({12: 1.5, 1: 1.2}, default=1.0))
    r = m.render()
    assert r[season] == [1.0, 1.5, 1.2, 1.0]
    listed = m.series("listed", b.by_month([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]))
    assert m.render()[listed] == [11, 12, 1, 2]
    with pytest.raises(ValueError, match=r"no value for months \[2, 3"):
        b.by_month({1: 1.0, 12: 1.0})
    with pytest.raises(ValueError, match="calendar months 1-12"):
        b.by_month({0: 1.0}, default=1.0)
    q = b.Model("q", start="2027-01", periods=2, step=b.quarter)
    bad = q.series("bad", b.by_month({1: 1.0}, default=1.0))
    with pytest.raises(ValueError, match="monthly periods"):
        q.render()[bad]


def test_months_and_days_do_not_convert_silently():
    m = b.Model("t", start="2027-01", periods=2, step=b.month)
    with pytest.raises(b.UnitError, match="months and days"):
        m.period_length / b.day
    days = m.period_end - m.date                                     # a date difference is a number of days
    r = m.render()
    assert r[days] == [31, 28]
    assert r[days * 2 * USD / b.day] == [62, 56]


def test_lag_fill_takes_one_value_or_a_series():
    m = b.Model("t", start=0, periods=3, step=b.year)
    with pytest.raises(TypeError, match="fill="):
        m.t.lag(2, fill=[1, 2])


def test_by_year_keys_outside_the_model_years_raise():
    m = b.Model("t", start=2027, periods=3, step=b.year)
    with pytest.raises(ValueError, match=r"2027.*model years 0-2.*'2027'"):
        m.render()[m.series("k", b.by_year({2027: 1, 2028: 2, 2029: 3}))]
    assert m.render()[b.by_year({"2027": 1, "2029": 3}, default=0)] == [1, 0, 3]
    bi = b.Model("bi", start="2027-01", periods=6, step=2 * b.month)   # one model year
    with pytest.raises(ValueError, match="model years 0-0"):
        bi.render()[b.by_year({0: 60, 5: 140}, default=0)]


def test_irr_of_a_long_monthly_series():
    m = b.Model("i", start="2027-01", periods=200, step=b.month)
    cf = m.series("cf", (m.t == 0) * -100 + (m.t > 0) * 1.0)
    r = m.render()
    rate = r[irr(cf)]
    assert 0.0079 < rate < 0.008
    assert r[irr(cf, running=True, default=0)][-1] == pytest.approx(rate)


def test_expect_compares_a_constant_series_in_every_period():
    m = b.Model("t", start=0, periods=3, step=b.year)
    c = m.series("c", 5 * USD)
    r = m.render()
    b.expect(r, {c: [5, 5, None]})
    with pytest.raises(AssertionError, match=r"c \[2\]: expected 6, got 5"):
        b.expect(r, {c: [5, 5, 6]})


def test_expect_rejects_a_list_longer_or_shorter_than_the_periods():
    m = b.Model("t", start=0, periods=1, step=b.year)
    c = m.series("c", 1.0)                                       # a constant series
    x = m.series("x", 1.0 + 0 * m.t)                             # a series with a value per period
    r = m.render()
    b.expect(r, {c: [1.0], x: [1.0]})
    for key in (c, x):
        with pytest.raises(ValueError, match="2 reference values for 1 periods"):
            b.expect(r, {key: [1.0, 999.0]})
        with pytest.raises(ValueError, match="0 reference values for 1 periods"):
            b.expect(r, {key: []})
    b.expect(r, {x: [None]})                                     # None skips a period: the list keeps its length


def test_expect_takes_ranges_and_a_tolerance_per_key():
    m = b.Model("t", start=0, periods=3, step=b.year)
    x = m.series("x", b.by_year({0: 1.341, 1: 0.62, 2: 9.0}))
    money = m.series("money", 100.4 * USD)
    r = m.render()
    b.expect(r, {
        x[0]: b.approx(1.34, tol=0.005),
        x[1]: b.above(0.5),
        x[2]: b.between(9, 10),
        x: [b.above(1), b.below(1), b.approx(9.1, rel=0.02)],
        money: b.approx(100 * USD, tol=1 * USD),
        money * 2: b.approx(200 * USD, rel=0.005),
    }, tol=0)
    with pytest.raises(AssertionError, match=r"x\[1\]: expected > 0.7, got 0.62"):
        b.expect(r, {x[1]: b.above(0.7)})
    with pytest.raises(AssertionError, match=r"expected 1.34 ± 0.0005"):
        b.expect(r, {x[0]: b.approx(1.34, tol=0.0005)})
    assert "> 0.7" in str(b.compare(r, {x[1]: b.above(0.7)}))
    with pytest.raises(b.UnitError):
        b.expect(r, {money: b.above(1 * b.month)})


def test_dates_move_by_days_and_xnpv_discounts_by_them():
    from datetime import date
    from boki.lib import xirr, xnpv
    m = b.Model("t", start="2027-01", periods=3, step=b.month)
    last_day = m.period_end - 1 * b.day
    r = m.render()
    assert r[last_day] == [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31)]
    assert r[m.date + 14 * b.day] == [date(2027, 1, 15), date(2027, 2, 15), date(2027, 3, 15)]
    cf = m.series("cf", b.step({0: -100, 1: 50, 2: 60}))
    rate = r[xirr(cf, last_day)]
    assert r[xnpv(cf, rate, last_day)] == pytest.approx(0, abs=1e-6)
    assert r[xnpv(cf, 0.1, m.date)] == pytest.approx(-100 + 50 / 1.1 ** (31 / 365) + 60 / 1.1 ** (59 / 365))


def test_year_and_month_of_a_date_series():
    m = b.Model("t", start="2027-11", periods=4, step=b.month)
    r = m.render()
    assert r[m.date.year] == [2027, 2027, 2028, 2028]
    assert r[m.date.month] == [11, 12, 1, 2]
    assert r[(m.period_end - 1 * b.day).month] == [11, 12, 1, 2]
    assert r[m.date.month == 1] == [False, False, True, False]
    with pytest.raises(TypeError, match="date series"):
        m.t.year
    with pytest.raises(TypeError, match="date series"):
        m.series("price", 2 * USD).month


def test_reductions_over_one_model_year():
    m = b.Model("t", start="2027-01", periods=30, step=b.month)
    x = m.series("x", m.t + 1)
    c = m.series("c", 2 * USD)
    r = m.render()
    assert [r[x.sum(year=y)] for y in range(3)] == [78, 222, 165]       # the third year has six months
    assert [r[x.last(year=y)] for y in range(3)] == [12, 24, 30]
    assert r[x.mean(year=1)] == 18.5 and r[x.min(year=1)] == 13 and r[x.max(year=2)] == 30
    assert r[x.last()] == 30 and r[x.sum()] == 465
    assert r[c.sum(year=0)] == 24 and r[c.last(year=2)] == 2
    assert r[x.where(m.t > 100).mean(year=0)] is None
    with pytest.raises(ValueError, match="outside the model years 0-2"):
        r[x.sum(year=3)]
    with pytest.raises(TypeError, match="model year number"):
        x.sum(year="2028")


def test_rounding_integer_and_math_functions():
    m = b.Model("t", start=0, periods=4, step=b.year)
    x = m.series("x", b.by_year({0: 2.675, 1: -2.675, 2: 1234.5, 3: 7.0}))
    r = m.render()
    assert r[b.round(x, 2)] == [2.68, -2.68, 1234.5, 7.0]           # Excel's ROUND, not Python's round(2.675, 2)
    assert r[b.round(x, -2)] == [0.0, -0.0, 1200.0, 0.0]
    assert r[b.rounddown(x, 1)] == [2.6, -2.6, 1234.5, 7.0]
    assert r[b.roundup(x, 1)] == [2.7, -2.7, 1234.5, 7.0]
    assert r[b.floor(x)] == [2, -3, 1234, 7]
    assert r[x % 2] == r[b.mod(x, 2)] == pytest.approx([0.675, 1.325, 0.5, 1.0])
    assert r[m.t // 2] == [0, 0, 1, 1]
    assert r[b.exp(b.log(m.t + 1))] == pytest.approx([1, 2, 3, 4])
    assert r[b.sqrt(m.t * m.t)] == [0, 1, 2, 3]
    assert r[x.mean()] == pytest.approx(310.375)
    assert r[x.where(m.t >= 2).mean()] == pytest.approx(620.75)       # periods without a value are left out
    money = m.series("money", 10.5 * USD)
    assert r[b.round(money, 0)] == 11 and r[money % (4 * USD)] == 2.5 and r[(money // (4 * USD))] == 2
    with pytest.raises(b.UnitError):
        b.exp(money)
    with pytest.raises(b.UnitError):
        money % 4 * b.month


def test_reading_a_period_outside_the_model_names_the_series():
    m = b.Model("t", start=0, periods=3, step=b.year)
    x = m.series("x", 1 + m.t)
    with pytest.raises(IndexError, match=r"period 7 is outside the model \(0\.\.2\) for x"):
        m.render()._r.value(x, 7)

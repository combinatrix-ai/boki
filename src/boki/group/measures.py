"""Ownership scopes, member amounts, net assets, and acquisition adjustments for the consolidation."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..ledger import (AMORTIZATION, DEPRECIATION, SUBSIDIARY_INVESTMENT, Account, _AssetTrade,
                      _AssetTradeFlow, Entity, Posting, _Total)
from ..series import Series, lift, smax, smin
from ..units import month
from .series import _OpeningOciBalance, _OpeningOciRelease
from .terms import (AcquisitionAdjustment, EquityMethodLot, EquityMethodTerms, OpeningConsolidation,
                    OwnershipEvent, Scope)

if TYPE_CHECKING:
    from .core import Group


def _currency_dims(currency):
    return getattr(currency, "dims", currency)


def _fx_rate(model, base, quote, method: str) -> tuple[Series, bool]:
    return model._fx_rate(base, quote, method)


def _convert_currency(model, amount: Series, base, quote, method: str = "average", *, rate=None) -> Series:
    return model._convert_currency(amount, base, quote, method, rate=rate)


def _equity_method_sale_labels(entity: Entity) -> tuple[str, str, str, str]:
    if entity.standard.name == "J-GAAP":
        return "special_gain", "special_loss", "Gain on sale of investments in affiliates", "Loss on sale of investments in affiliates"
    if entity.standard.name == "US GAAP":
        label = "Gain (loss) on sale of investments in affiliates"
    else:
        label = "Gain (loss) on disposal of interests in associates"
    return "other_income", "other_expense", label, label


def _sale_account(entity: Entity, name: str, kind: str, side: str) -> Account:
    account = next((a for a in entity._accounts if a.name == name and a.kind == kind), None)
    if account is None:
        account = entity._account(name, side, kind, "pl", category=name)
    account.tags = account.tags | {"equity_method_disposal"}
    return account


def _control_disposal_account(entity: Entity) -> Account:
    if entity.standard.name == "J-GAAP":
        name, kind, side = "Gain (loss) on sale of subsidiary shares", "special_gain", "income"
    else:
        name = "Gain (loss) on disposal of subsidiary"
        kind, side = "other_income", "income"
    account = _group_pl_account(entity, name, kind, side)
    account.tags = account.tags | {"control_disposal_gain"}
    return account


def _step_acquisition_account(entity: Entity) -> Account:
    if entity.standard.name == "J-GAAP":
        name, kind, side = "Gain (loss) on step acquisition", "special_gain", "income"
    else:
        name = "Gain (loss) on step acquisition"
        kind, side = "other_income", "income"
    account = _group_pl_account(entity, name, kind, side)
    account.tags = account.tags | {"step_acquisition_gain"}
    return account


def _ownership_scope(events: list[OwnershipEvent], method: str) -> Scope:
    intervals = []
    start = None
    for event in events:
        active = event.method == method and event.share > 0
        if active and start is None:
            start = event.period
        elif not active and start is not None:
            intervals.append((start, event.period))
            start = None
    if start is not None:
        intervals.append((start, None))
    return Scope(tuple(intervals))


def _ownership_event_mask(group: Group, event: OwnershipEvent, method: str) -> Series:
    next_change = min((candidate.period for candidate in group._ownership[event.entity]
                       if candidate.period > event.period and
                       (candidate.method != method or candidate.share == 0)), default=None)
    mask = group.model.t >= event.period
    if next_change is not None:
        mask *= group.model.t < next_change
    return mask


def _control_event_mask(group: Group, event: OwnershipEvent) -> Series:
    return _ownership_event_mask(group, event, "consolidate")


def _scoped_native_amount(group: Group, entity: Entity, post: Posting,
                         scopes: dict[Entity, Scope], eliminate_trades: bool = True) -> Series:
    """The posting's amount while `entity` is in scope, without the trades the group eliminates.

    With ``eliminate_trades=False`` the amount keeps the entity's side of a P&L trade or loan with another member,
    as the member's own profit does; an asset sale stays eliminated, because its unrealized profit is adjusted
    separately.
    """
    if post.fx_remeasurement:
        return post.amount * scopes[entity].mask(group.model)
    if post.counterpart in group.parent._associate_dividend_receipts:
        return post.amount * scopes[entity].mask(group.model)
    acquired_pair = getattr(group, "_acquisition_pair_amounts", {}).get(post)
    if acquired_pair is not None:
        return acquired_pair
    amount = post.amount * scopes[entity].mask(group.model)
    if post.counterparty in scopes and (eliminate_trades or post.asset_trade is not None):
        amount *= 1 - scopes[post.counterparty].mask(group.model)
    return amount


def _scoped_amount(group: Group, entity: Entity, post: Posting, scopes: dict[Entity, Scope],
                   eliminate_trades: bool = True) -> Series:
    amount = _scoped_native_amount(group, entity, post, scopes, eliminate_trades)
    return _convert_currency(group.model, amount, entity._currency, group.parent._currency,
                             rate=post.fx_rate)


def _share_series(group: Group, events: list[OwnershipEvent]) -> Series:
    share = lift(0)
    for event in events:
        share = share.where(group.model.t < event.period, event.share)
    return share


def _asset_trade_share(group: Group, trade: _AssetTrade, scopes: dict[Entity, Scope]) -> Series:
    seller, buyer = trade.seller, trade.buyer
    if seller in scopes and buyer in scopes:
        return scopes[seller].mask(group.model) * scopes[buyer].mask(group.model)
    if seller in scopes and buyer in group._ownership:
        events = group._ownership[buyer]
        scope = _ownership_scope(events, "equity")
        if scope.intervals:
            return scopes[seller].mask(group.model) * scope.mask(group.model) * _share_series(group, events)
    if buyer in scopes and seller in group._ownership:
        events = group._ownership[seller]
        scope = _ownership_scope(events, "equity")
        if scope.intervals:
            return scopes[buyer].mask(group.model) * scope.mask(group.model) * _share_series(group, events)
    return lift(0)


def _asset_trade_buyer_scope(group: Group, trade: _AssetTrade, scopes: dict[Entity, Scope]) -> Series:
    if trade.buyer in scopes:
        return scopes[trade.buyer].mask(group.model)
    events = group._ownership.get(trade.buyer, [])
    scope = _ownership_scope(events, "equity")
    return scope.mask(group.model) if scope.intervals else lift(0)


def _asset_trade_states(group: Group, scopes: dict[Entity, Scope]) -> dict[_AssetTrade, dict[str, Series]]:
    opening_specs = {spec.trade: spec for events in group._ownership.values() for event in events
                     if isinstance(event.opening, OpeningConsolidation) for spec in event.opening.unrealized}
    trades = {trade for entity in group._members for trade in entity._asset_trades} | set(opening_specs)
    states = {}
    for trade in trades:
        share = _asset_trade_share(group, trade, scopes)
        if trade in opening_specs:
            specification = opening_specs[trade]
            opening_balance = specification.amount.cumsum() * share
            starting = specification.amount * share * (group.model.t == 0)
            if trade.asset_kind == "inventory":
                realized = starting.spread(trade.used)
            else:
                realized = _AssetTradeFlow(group.model, starting, trade.life_months,
                                            f"{trade.name}: opening realized intercompany profit")
            buyer_scope = _asset_trade_buyer_scope(group, trade, scopes)
            realized *= buyer_scope
            states[trade] = {
                "share": share,
                "initial": specification.amount * 0,
                "realized": realized,
                "unrealized": (opening_balance - realized.cumsum()) * buyer_scope,
                "opening": (opening_balance - realized.cumsum().lag(1, fill=0)) * buyer_scope,
                "opening_balance": opening_balance,
            }
            continue
        initial = trade.profit * share
        if trade.asset_kind == "inventory":
            realized = initial.spread(trade.used)
        else:
            realized = _AssetTradeFlow(group.model, initial, trade.life_months,
                                        f"{trade.name}: consolidated realized profit")
        realized *= _asset_trade_buyer_scope(group, trade, scopes)
        cumulative = initial.cumsum() - realized.cumsum()
        states[trade] = {
            "share": share,
            "initial": initial,
            "realized": realized,
            "unrealized": cumulative * _asset_trade_buyer_scope(group, trade, scopes),
            "opening": cumulative.lag(1, fill=0),
        }
    return states


def _equity_method_lots(group: Group, events: list[OwnershipEvent]) -> list[EquityMethodLot]:
    lots = []
    for event in events:
        if event.method != "equity" or event.kind not in ("opening", "acquisition", "purchase"):
            continue
        acquired_share = event.share if event.kind == "opening" else event.share - event.previous_share
        held_share = lift(acquired_share).where(group.model.t >= event.period, 0)
        for sale in events:
            if sale.kind == "sale" and sale.previous_method == "equity" and sale.period > event.period:
                retention = sale.share / sale.previous_share
                held_share = held_share.where(group.model.t < sale.period, held_share * retention)
        lots.append(EquityMethodLot(event, acquired_share, held_share))
    return lots


def _equity_method_sale_retention(group: Group, events: list[OwnershipEvent]) -> Series:
    retention = lift(1)
    for event in events:
        if event.kind == "sale" and event.previous_method == "equity":
            factor = event.share / event.previous_share
            retention = retention.where(group.model.t < event.period, retention * factor)
    return retention


def _member_profit(group: Group, entity: Entity, scopes: dict[Entity, Scope],
                   eliminate_trades: bool = True) -> Series:
    parts = []
    for post in entity._postings:
        amount = _scoped_amount(group, entity, post, scopes, eliminate_trades)
        if post.debit.cf == "pl":
            parts.append(-amount)
        if post.credit.cf == "pl":
            parts.append(amount)
    return _sum(parts, group.parent, f"{entity.name}: consolidated profit")


def _member_oci(group: Group, entity: Entity, source: Account, scopes: dict[Entity, Scope]) -> Series:
    parts = []
    for post in entity._postings:
        amount = _scoped_amount(group, entity, post, scopes)
        if post.debit is source:
            parts.append(-amount)
        if post.credit is source:
            parts.append(amount)
    return _sum(parts, group.parent, f"{entity.name}: {source.name} OCI")


def _member_oci_release(group: Group, entity: Entity, source: Account,
                        scopes: dict[Entity, Scope]) -> Series:
    parts = [_scoped_amount(group, entity, post, scopes) for post in entity._postings
             if post.debit is source and (post.credit.cf == "pl" or post.credit is entity.retained_earnings)]
    return _sum(parts, group.parent, f"{entity.name}: {source.name} OCI releases")


def _opening_oci_attribution(entity: Entity, name: str, release: Series, share: Series,
                             opening_parent: dict, opening_nci: dict,
                             events: list[OwnershipEvent]):
    key = (entity, name)
    parent = opening_parent.get(key, release * 0)
    nci = opening_nci.get(key, release * 0)
    parent_balance = _OpeningOciBalance(parent, nci, release, events, nci=False)
    nci_balance = _OpeningOciBalance(parent, nci, release, events, nci=True)
    opening_release = _OpeningOciRelease(release, parent_balance, nci_balance, nci_only=False)
    nci_release = _OpeningOciRelease(release, parent_balance, nci_balance, nci_only=True)
    nci_adjustment = nci_release - opening_release * (1 - share)
    return opening_release, nci_release, nci_adjustment, parent_balance, nci_balance


def _tagged_opening(group: Group, entity: Entity, source: Account, period: int,
                    scopes: dict[Entity, Scope], newly_acquired: set[Entity], *, net_assets: bool = False,
                    membership_period: int | None = None) -> Series:
    """The tagged balance included by a new acquisition, or present in a subsidiary's raw net assets."""
    amount = _tagged_opening_native(group, entity, source, period, scopes, newly_acquired,
                                    net_assets=net_assets, membership_period=membership_period)
    if entity._currency is None or group.parent._currency is None:
        return amount
    return _convert_currency(group.model, amount, entity._currency, group.parent._currency, "acquisition")


def _tagged_opening_native(group: Group, entity: Entity, source: Account, period: int,
                           scopes: dict[Entity, Scope], newly_acquired: set[Entity], *,
                           net_assets: bool = False, membership_period: int | None = None) -> Series:
    parts = []
    membership_period = period if membership_period is None else membership_period
    mirror = source.mirror
    if mirror is not None and mirror.opening is not None and mirror.entity in scopes and \
            scopes[mirror.entity].contains(membership_period) and source.kind != "cash" and \
            not (source.kind == "other_asset" and SUBSIDIARY_INVESTMENT in source.tags):
        parts.append(_at_period(entity._balance(source).opening, period, group))
    for post in entity._postings:
        other = post.counterparty
        if post.asset_trade is not None:
            continue
        if other not in scopes or not scopes[other].contains(membership_period) or source not in (post.debit, post.credit):
            continue
        if source.kind == "cash" or (source.kind == "other_asset" and SUBSIDIARY_INVESTMENT in source.tags):
            continue
        entity_start = scopes[entity].start_at(membership_period) if scopes[entity].contains(membership_period) else period
        other_start = scopes[other].start_at(membership_period)
        if not net_assets and max(entity_start, other_start) != period:
            continue
        first = 0 if net_assets or entity in newly_acquired else entity_start
        stop = period if net_assets or entity in newly_acquired else min(period, other_start)
        if stop <= first:
            continue
        movement = post.amount * (group.model.t >= first) * (group.model.t < stop)
        prior = movement.cumsum().lag(1, fill=0)
        direction = (1 if source.side == "asset" else -1) if post.debit is source else \
            (-1 if source.side == "asset" else 1)
        parts.append(direction * prior * (group.model.t == period))
    return _sum(parts, entity, f"{entity.name}: {source.name} intercompany opening")


def _at_period(value: Series, period: int, group: Group) -> Series:
    return lift(value) * (group.model.t == period)


def _sum(parts: list[Series], entity: Entity, name: str) -> Series:
    return _Total(lambda parts=parts: parts, name, entity)


def _net_assets(group: Group, entity: Entity, period: int, scopes: dict[Entity, Scope], *,
                membership_period: int | None = None) -> Series:
    parts = []
    for account in entity._accounts:
        if account.side not in ("asset", "liability"):
            continue
        balance = _at_period(entity._balance(account).opening, period, group)
        if entity._currency is not None and group.parent._currency is not None:
            balance = _convert_currency(group.model, balance, entity._currency, group.parent._currency,
                                        "acquisition")
        if account.kind != "cash" and not (account.kind == "other_asset" and SUBSIDIARY_INVESTMENT in account.tags):
            balance -= _tagged_opening(group, entity, account, period, scopes, {entity}, net_assets=True,
                                       membership_period=membership_period)
        for trade, state in getattr(group, "_s6_trade_states", {}).items():
            if trade.buyer is entity and trade.buyer_item.account is account:
                balance -= state["opening"] * (group.model.t == period)
        parts.append(balance if account.side == "asset" else -balance)
    return _sum(parts, group.parent, f"{entity.name}: net assets at period {period}")


def _foreign_balance_delta(group: Group, entity: Entity, source: Account,
                           scopes: dict[Entity, Scope]) -> Series:
    native_changes, translated_changes = [], []
    for post in entity._postings:
        if source not in (post.debit, post.credit):
            continue
        direction = 1 if ((source.side == "asset" and post.debit is source) or
                          (source.side == "liability" and post.credit is source)) else -1
        if post in getattr(group, "_acquisition_pair_amounts", {}):
            native = group._acquisition_pair_amounts[post]
        elif post.asset_trade is not None or post.intercompany_trade is not None:
            native = post.amount * scopes[entity].mask(group.model)
        else:
            native = _scoped_native_amount(group, entity, post, scopes)
        translated = _convert_currency(group.model, native, entity._currency, group.parent._currency,
                                       rate=post.fx_rate)
        native_changes.append(native * direction)
        translated_changes.append(translated * direction)

    native_movement = _sum(native_changes, entity, f"{entity.name}: {source.name} native movement")
    translated_movement = _sum(translated_changes, group.parent,
                               f"{entity.name}: {source.name} translated movement")
    native_cumulative = native_movement.cumsum()
    opening_balance = entity._balance(source).opening
    deltas = []
    for raw_start, end in scopes[entity].intervals:
        start = max(raw_start, 0)
        if start >= group.model.n:
            continue
        interval = group.model.t >= start
        if end is not None:
            interval *= group.model.t < end
        opening = opening_balance[start]
        opening -= _tagged_opening_native(group, entity, source, start, scopes, {entity}, net_assets=True)[start]
        baseline = native_cumulative.lag(1, fill=0)[start]
        native_end = (opening + native_cumulative - baseline) * interval
        translated_opening = _convert_currency(group.model, opening, entity._currency,
                                                group.parent._currency, "acquisition") * (group.model.t == start)
        desired = _convert_currency(group.model, native_end, entity._currency,
                                    group.parent._currency, "closing")
        prior = translated_opening.where(group.model.t == start, desired.lag(1, fill=0))
        deltas.append((desired - prior - translated_movement) * interval)
    return _sum(deltas, group.parent, f"{entity.name}: {source.name} closing-rate adjustment")


def _adjustment_amortization(group: Group, event: OwnershipEvent,
                             adjustment: AcquisitionAdjustment, value: Series | None = None) -> Series:
    if adjustment.remaining_life is None:
        return adjustment.value * 0
    model = group.model
    active = model.t >= event.period
    elapsed = (model.period_length * active).cumsum().lag(1, fill=0)
    life = adjustment.remaining_life * month
    remaining = smax(life - elapsed, 0)
    fraction = smin(model.period_length, remaining) / life
    return -(adjustment.value if value is None else value).cumsum() * fraction


def _opening_amortization_fraction(group: Group, remaining_life: int) -> Series:
    model = group.model
    elapsed = model.period_length.cumsum().lag(1, fill=0)
    life = remaining_life * month
    remaining = smax(life - elapsed, 0)
    return smin(model.period_length, remaining) / life


def _group_pl_account(books: Entity, name: str, kind: str, side: str = "expense") -> Account:
    existing = next((a for a in books._accounts if a.name == name and a.kind == kind), None)
    return existing or books._account(name, side, kind, "pl", category=name)


def _adjustment_amortization_account(books: Entity, active: set) -> Account:
    """The PL account that carries the unwind of acquisition-date fair-value adjustments."""
    account = _group_pl_account(books, books.label("acquisition_adjustment_amortization"),
                                books.layout.depreciation_kind)
    active.add(account)
    return account


def _post_unwind(books: Entity, name: str, amount, expense: Account, target: Account) -> Posting:
    """Book the unwind of a fair-value adjustment on `target` and say whether it is depreciation.

    Only the unwind of a depreciable or amortizable asset is depreciation or amortization: a fixed
    asset or construction in progress is depreciation, an intangible is amortization. The unwind of
    anything else (a liability, inventory, receivables, other assets) is not D&A and stays untagged.
    The posting carries the tag, so all unwinds can share one statement line and
    `Group.depreciation` and `Group.amortization` still pick out only the asset postings.
    """
    post = books._post(name, amount, debit=expense, credit=target)
    if target.kind in ("fixed_asset", "construction"):
        post.da = DEPRECIATION
    elif target.kind == "intangible":
        post.da = AMORTIZATION
    return post


def _book_acquisition_adjustments(group: Group, books: Entity, event: OwnershipEvent, clearing: Account,
                                  mapped: dict[Account, Account], active_pl_accounts: set[Account]):
    terms = event.acquisition
    if terms is None or not terms.adjustments:
        zero = _sum([], books, f"{event.entity.name}: no acquisition adjustments")
        return zero, zero, zero

    entity, parent = event.entity, group.parent
    foreign = _currency_dims(entity._currency) != _currency_dims(parent._currency)
    control_mask = _control_event_mask(group, event)
    tax_expense = books._deferred_tax_line() if terms.tax_rate is not None else None
    adjustment_values, tax_effects, profit_parts = [], [], []
    for adjustment in terms.adjustments:
        if adjustment.source is not None:
            target = mapped[adjustment.source]
            targets = {adjustment.side: target}
        else:
            sides = ("asset", "liability") if adjustment.side == "dynamic" else (adjustment.side,)
            targets = {}
            for side in sides:
                kind = "intangible" if side == "asset" else "other_liability"
                bs_kind = books.layout.bs_kind(kind)
                if bs_kind is None and side == "asset":
                    kind = "other_asset"
                    bs_kind = books.layout.bs_kind(kind)
                if bs_kind is None:
                    raise ValueError(f"{books.layout.name} has no balance-sheet kind for acquired {side}s")
                target = next((a for a in books._accounts if a.name == adjustment.name and a.kind == kind), None)
                if target is None:
                    target = books._account(adjustment.name, side, kind, bs_kind.cf)
                targets[side] = target

        value = _convert_currency(group.model, adjustment.value, entity._currency, parent._currency,
                                  "acquisition") if foreign else adjustment.value
        if adjustment.side == "dynamic":
            asset_value = smax(value, 0)
            liability_value = -smax(-value, 0)
            books._post(f"{event.entity.name} acquired: {adjustment.name} (asset)", asset_value,
                        debit=targets["asset"], credit=clearing)
            books._post(f"{event.entity.name} acquired: {adjustment.name} (liability)", liability_value,
                        debit=targets["liability"], credit=clearing)
        else:
            books._post(f"{event.entity.name} acquired: {adjustment.name}", value,
                        debit=targets[adjustment.side], credit=clearing)
        adjustment_values.append(value)

        amortization_native = _adjustment_amortization(group, event, adjustment) * control_mask
        amortization = _convert_currency(group.model, amortization_native, entity._currency,
                                         parent._currency) if foreign else amortization_native
        if adjustment.remaining_life is not None:
            amort_account = _adjustment_amortization_account(books, active_pl_accounts)
            if adjustment.side == "dynamic":
                asset_amortization_native = _adjustment_amortization(
                    group, event, adjustment, smax(adjustment.value, 0)) * control_mask
                liability_amortization_native = _adjustment_amortization(
                    group, event, adjustment, -smax(-adjustment.value, 0)) * control_mask
                asset_amortization = _convert_currency(
                    group.model, asset_amortization_native, entity._currency, parent._currency) \
                    if foreign else asset_amortization_native
                liability_amortization = _convert_currency(
                    group.model, liability_amortization_native, entity._currency, parent._currency) \
                    if foreign else liability_amortization_native
                _post_unwind(books, f"{event.entity.name} acquisition adjustment amortization: {adjustment.name} (asset)", -asset_amortization, amort_account, targets["asset"])
                _post_unwind(books, f"{event.entity.name} acquisition adjustment amortization: {adjustment.name} (liability)", -liability_amortization, amort_account, targets["liability"])
                if foreign:
                    schedules = getattr(books, "_foreign_adjustment_schedules", [])
                    schedules.extend(((entity, targets["asset"], "asset", smax(adjustment.value, 0),
                                       asset_amortization_native, event, False),
                                      (entity, targets["liability"], "liability",
                                       smax(-adjustment.value, 0), -liability_amortization_native,
                                       event, False)))
                    books._foreign_adjustment_schedules = schedules
            else:
                _post_unwind(books, f"{event.entity.name} acquisition adjustment amortization: {adjustment.name}", -amortization, amort_account, targets[adjustment.side])
        elif foreign and adjustment.side == "dynamic":
            schedules = getattr(books, "_foreign_adjustment_schedules", [])
            schedules.extend(((entity, targets["asset"], "asset", smax(adjustment.value, 0),
                               adjustment.value * 0, event, False),
                              (entity, targets["liability"], "liability", smax(-adjustment.value, 0),
                               adjustment.value * 0, event, False)))
            books._foreign_adjustment_schedules = schedules

        if foreign and adjustment.side != "dynamic":
            side = adjustment.side
            origin = adjustment.value if side == "asset" else -adjustment.value
            movement = amortization_native if side == "asset" else -amortization_native
            schedules = getattr(books, "_foreign_adjustment_schedules", [])
            schedules.append((entity, targets[side], side, origin, movement, event, False))
            books._foreign_adjustment_schedules = schedules

        if terms.tax_rate is not None:
            tax_name = f"{event.entity.name}: {adjustment.name}"
            liability = books._tax_account(tax_name, "deferred_tax_liability", "liability", "operating")
            asset = books._tax_account(tax_name, "deferred_tax_asset", "asset", "operating")
            remaining_difference = adjustment.value.cumsum() + amortization_native.cumsum()
            liability_balance = terms.tax_rate * smax(remaining_difference, 0)
            asset_balance = terms.tax_rate * smax(-remaining_difference, 0)
            initial_liability_native = terms.tax_rate * smax(adjustment.value, 0)
            initial_asset_native = terms.tax_rate * smax(-adjustment.value, 0)
            initial_liability = _convert_currency(
                group.model, initial_liability_native, entity._currency, parent._currency, "acquisition") \
                if foreign else initial_liability_native
            initial_asset = _convert_currency(
                group.model, initial_asset_native, entity._currency, parent._currency, "acquisition") \
                if foreign else initial_asset_native
            books._post(f"{tax_name} initial deferred tax liability", initial_liability,
                        debit=clearing, credit=liability)
            books._post(f"{tax_name} initial deferred tax asset", initial_asset,
                        debit=asset, credit=clearing)
            liability_change_native = liability_balance.change - initial_liability_native
            asset_change_native = asset_balance.change - initial_asset_native
            liability_change = _convert_currency(
                group.model, liability_change_native, entity._currency, parent._currency) \
                if foreign else liability_change_native
            asset_change = _convert_currency(
                group.model, asset_change_native, entity._currency, parent._currency) \
                if foreign else asset_change_native
            tax_change = liability_change - asset_change
            books._deferred_tax_movements.append(tax_change)
            books._post(f"{tax_name} deferred tax liability unwind", liability_change,
                        debit=tax_expense, credit=liability)
            books._post(f"{tax_name} deferred tax asset unwind", asset_change,
                        debit=asset, credit=tax_expense)
            tax_effect = terms.tax_rate * adjustment.value
            tax_effects.append(_convert_currency(group.model, tax_effect, entity._currency,
                                                 parent._currency, "acquisition") if foreign else tax_effect)
            profit_parts.append(amortization - tax_change)
            if foreign:
                schedules = getattr(books, "_foreign_adjustment_schedules", [])
                schedules.extend(((entity, liability, "liability", initial_liability_native,
                                   liability_change_native, event, False),
                                  (entity, asset, "asset", initial_asset_native,
                                   asset_change_native, event, False)))
                books._foreign_adjustment_schedules = schedules
        else:
            profit_parts.append(amortization)

    return (_sum(adjustment_values, books, f"{event.entity.name}: acquisition adjustments"),
            _sum(tax_effects, books, f"{event.entity.name}: acquisition deferred tax"),
            _sum(profit_parts, books, f"{event.entity.name}: acquisition profit adjustments"))


def _standalone_net_assets(entity: Entity, period: int, group: Group) -> Series:
    parts = []
    for source in entity._accounts:
        if source.side not in ("asset", "liability"):
            continue
        balance = _at_period(entity._balance(source).opening, period, group)
        parts.append(balance if source.side == "asset" else -balance)
    return _sum(parts, group.parent, f"{entity.name}: standalone net assets at period {period}")


def _equity_adjustment_amounts(group: Group, books: Entity, event: OwnershipEvent, terms: EquityMethodTerms):
    values, tax_effects, profit_parts = [], [], []
    for adjustment in terms.adjustments:
        amortization = _adjustment_amortization(group, event, adjustment)
        values.append(adjustment.value)
        if terms.tax_rate is None:
            profit_parts.append(amortization)
            continue

        remaining_difference = adjustment.value.cumsum() + amortization.cumsum()
        liability_balance = terms.tax_rate * smax(remaining_difference, 0)
        asset_balance = terms.tax_rate * smax(-remaining_difference, 0)
        initial_liability = terms.tax_rate * smax(adjustment.value, 0)
        initial_asset = terms.tax_rate * smax(-adjustment.value, 0)
        tax_change = (liability_balance.change - initial_liability) - (asset_balance.change - initial_asset)
        tax_effects.append(terms.tax_rate * adjustment.value)
        profit_parts.append(amortization - tax_change)

    adjustments = _sum(values, books, f"{event.entity.name}: associate acquisition adjustments")
    deferred_tax = _sum(tax_effects, books, f"{event.entity.name}: associate acquisition deferred tax")
    profit = _sum(profit_parts, books, f"{event.entity.name}: associate acquisition profit adjustments")
    return adjustments, deferred_tax, profit

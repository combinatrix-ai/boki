"""Input preparation that `Group` methods run when ownership, acquisition, and sale terms are added."""
from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from numbers import Real

from ..ledger import Account, _AssetTrade, Entity, LineItem, Posting, _account_of, _points
from ..shapes import Kernel, _check_kernel_distribution
from ..series import Series, smax, smin
from ..units import Quantity, Unit, UnitError
from .measures import _equity_method_sale_labels, _sale_account
from .terms import AcquisitionAdjustment, AcquisitionTerms, EquityMethodTerms, OpeningUnrealized


def _sale_line(entity: Entity, name: str, kind: str, side: str, amount: Series) -> Account:
    account = _sale_account(entity, name, kind, side)
    getattr(entity.pl, kind)._items.append(LineItem(name, amount, entity, kind, account, name))
    return account


def _book_equity_method_sale(entity: Entity, investment: Account, proceeds: Series, carrying: Series,
                             associate_name: str) -> tuple[Posting, ...]:
    gain_kind, loss_kind, gain_name, loss_name = _equity_method_sale_labels(entity)
    if gain_kind not in entity.layout.pl_kinds or loss_kind not in entity.layout.pl_kinds:
        raise ValueError(f"{entity.layout.name} has no profit-and-loss kinds for associate disposals")

    gain = smax(proceeds - carrying, 0)
    loss = smax(carrying - proceeds, 0)
    recovered_cost = smin(proceeds, carrying)
    posts = [entity._post(f"Sell {associate_name} shares at cost", recovered_cost,
                          debit=entity._cash_account, credit=investment, cf="investing")]
    gain_account = _sale_line(entity, gain_name, gain_kind, "income", gain)
    loss_account = _sale_line(entity, loss_name, loss_kind, "expense", loss)
    posts.append(entity._post(gain_name, gain, debit=entity._cash_account, credit=gain_account, cf="investing"))
    posts.append(entity._post(loss_name, loss, debit=loss_account, credit=investment))
    return tuple(posts)


_MONTH_DIMS = frozenset({("month", 1)})


def _life_months(value, what: str) -> int:
    if isinstance(value, Unit):
        amount, dims = value.scale, value.dims
    elif isinstance(value, Quantity):
        amount, dims = value.value, value.dims
    else:
        raise TypeError(f"{what} must be a time quantity such as 10 * year, got {value!r}")
    if dims != _MONTH_DIMS or not isfinite(amount):
        raise UnitError(f"{what} must be a finite time quantity in months")
    months = int(round(amount))
    if months <= 0:
        raise ValueError(f"{what} must be positive")
    return months


def _acquisition_amount(entity: Entity, amount, period: int, name: str) -> Series:
    return _points(entity, amount, name) * (entity.model.t == period)


def _opening_amount(entity: Entity, amount, name: str) -> Series:
    return _points(entity, amount, name) * (entity.model.t == 0)


def _prepare_opening_oci(entity: Entity, parent: Entity,
                         opening) -> tuple[tuple[str, Account | None, Series, Series], ...]:
    if not isinstance(opening, Mapping):
        raise TypeError("opening['oci'] must be a mapping of components to (parent_part, nci_part)")
    parts = []
    for key, specification in opening.items():
        if isinstance(key, str):
            name = key
            component = entity._oci_components.get(name)
            source = component.account if component is not None else next(
                (account for account in entity._accounts if account.kind == "oci" and account.name == name), None)
        else:
            source = _account_of(key)
            if source.entity is not entity or source.kind != "oci":
                raise ValueError("opening['oci'] keys must name an OCI component in the subsidiary")
            name = source.name
        if not name.strip():
            raise ValueError("opening['oci'] component names must be nonempty")
        if not isinstance(specification, tuple) or len(specification) != 2:
            raise ValueError(f"opening['oci'][{name!r}] must be (parent_part, nci_part)")
        parent_part = _opening_amount(parent, specification[0], f"opening OCI {name} parent part")
        nci_part = _opening_amount(parent, specification[1], f"opening OCI {name} NCI part")
        parts.append((name, source, parent_part, nci_part))
    return tuple(parts)


def _prepare_opening_equity_oci(entity: Entity, parent: Entity,
                                opening) -> tuple[tuple[str, Account | None, Series], ...]:
    if not isinstance(opening, Mapping):
        raise TypeError("opening['oci'] must map component names to the group's accumulated share")
    parts = []
    for name, amount in opening.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("opening['oci'] component names must be nonempty strings")
        component = entity._oci_components.get(name)
        parts.append((name, component.account if component is not None else None,
                      _opening_amount(parent, amount, f"opening equity-method OCI {name}")))
    return tuple(parts)


def _prepare_opening_unrealized(entity: Entity, parent: Entity, opening) -> tuple[OpeningUnrealized, ...]:
    if not isinstance(opening, Mapping):
        raise TypeError("opening['unrealized'] must map buyer balance-sheet lines to (amount, realization)")
    parts = []
    for key, specification in opening.items():
        source = _account_of(key)
        if source.entity not in (entity, parent) or source.kind not in ("inventory", "fixed_asset"):
            raise ValueError("opening['unrealized'] keys must be inventory or fixed-asset lines in the group")
        if not isinstance(specification, tuple) or len(specification) != 2:
            raise ValueError(f"opening unrealized profit for {source.name!r} must be (amount, realization)")
        amount, realization = specification
        buyer_items = getattr(source.entity.bs, source.kind)._items
        buyer_line = key if isinstance(key, LineItem) else next(
            (line for line in buyer_items if line.account is source), None)
        if buyer_line is None:
            buyer_line = LineItem(source.name, source.entity._balance(source), source.entity, source.kind, source)
        if buyer_line.counterparty is not None:
            seller = buyer_line.counterparty.entity
        else:
            seller = parent if source.entity is entity else entity
        if seller not in (entity, parent) or seller is source.entity:
            raise ValueError(f"opening unrealized profit for {source.name!r} needs a seller in the group")

        if source.kind == "inventory":
            if not isinstance(realization, Kernel):
                raise TypeError(f"opening inventory profit for {source.name!r} needs a release kernel")
            _check_kernel_distribution(realization, f"opening unrealized profit for {source.name!r}")
            used, life_months = realization, None
        else:
            used, life_months = None, _life_months(realization, f"opening fixed-asset profit life for {source.name!r}")
        opening_profit = _opening_amount(entity, amount, f"opening unrealized profit: {source.name}")
        trade = _AssetTrade(seller=seller, buyer=source.entity, name=source.name, asset_kind=source.kind,
                            price=opening_profit * 0, profit=opening_profit, buyer_item=buyer_line,
                            used=used, life_months=life_months)
        parts.append(OpeningUnrealized(trade, opening_profit))
    return tuple(parts)


def _goodwill_life(entity: Entity, goodwill_life, private_company: bool, *, required: bool = True) -> int | None:
    standard = entity.standard.name
    life = None if goodwill_life is None else _life_months(goodwill_life, "goodwill_life")
    if standard == "J-GAAP":
        if required and life is None:
            raise ValueError("J-GAAP requires goodwill_life=")
        if life is not None and life > 20 * 12:
            raise ValueError("J-GAAP goodwill_life= cannot exceed 20 years")
        if private_company:
            raise ValueError("private_company=True applies only to US GAAP")
    elif standard == "US GAAP":
        if life is not None and not private_company:
            raise ValueError("US GAAP goodwill_life= requires private_company=True")
        if life is not None and life > 10 * 12:
            raise ValueError("US GAAP private-company goodwill_life= cannot exceed 10 years")
    elif standard == "IFRS":
        if life is not None:
            raise ValueError("IFRS does not amortize goodwill; omit goodwill_life=")
        if private_company:
            raise ValueError("private_company=True applies only to US GAAP")
    return life


def _prepare_adjustments(entity: Entity, period: int, fair_value, acquired, tax_basis: str,
                         entity_role: str) -> tuple[tuple[AcquisitionAdjustment, ...], Series | None]:
    if tax_basis not in ("carryover", "stepped_up"):
        raise ValueError("tax_basis= must be 'carryover' or 'stepped_up'")

    adjustments = []
    if fair_value is not None:
        if not isinstance(fair_value, Mapping):
            raise TypeError(f"fair_value= must be a mapping of {entity_role} balance-sheet items to adjustments")
        for item, specification in fair_value.items():
            source = _account_of(item)
            if source.entity is not entity or source.side not in ("asset", "liability"):
                raise ValueError(f"fair_value= keys must be balance-sheet items in the {entity_role}")
            if isinstance(specification, tuple):
                if len(specification) != 2:
                    raise ValueError(f"fair_value for {source.name!r} must be amount or (amount, remaining_life)")
                amount, remaining_life = specification
                remaining_life = _life_months(remaining_life, f"fair_value life for {source.name!r}")
            else:
                amount, remaining_life = specification, None
            signed = _acquisition_amount(entity, amount, period, f"fair value adjustment: {source.name}")
            if source.side == "liability":
                signed = -signed
            adjustments.append(AcquisitionAdjustment(source.name, source, source.side, signed, remaining_life))

    if acquired is not None:
        if not isinstance(acquired, Mapping):
            raise TypeError("acquired= must be a mapping of item names to amounts")
        for name, specification in acquired.items():
            if not isinstance(name, str) or not name.strip():
                raise TypeError("acquired= keys must be nonempty item names")
            if isinstance(specification, tuple):
                if len(specification) != 2:
                    raise ValueError(f"acquired item {name!r} must be amount or (amount, remaining_life)")
                amount, remaining_life = specification
                remaining_life = _life_months(remaining_life, f"acquired life for {name!r}")
            else:
                amount, remaining_life = specification, None
            if isinstance(amount, Quantity):
                sign_source = amount.value
            elif isinstance(amount, Real):
                sign_source = amount
            elif isinstance(amount, (Series, dict)):
                sign_source = None
            else:
                raise TypeError(f"acquired item {name!r} needs an amount; negative means liability")
            if sign_source is not None and not isfinite(sign_source):
                raise ValueError(f"acquired item {name!r} amount must be finite")
            side = "dynamic" if sign_source is None else ("liability" if sign_source < 0 else "asset")
            signed = _acquisition_amount(entity, amount, period, f"acquired item: {name}")
            adjustments.append(AcquisitionAdjustment(name, None, side, signed, remaining_life))

    tax_rate = entity._tax_rate(None, f"{entity_role} acquisition fair-value adjustments") \
        if tax_basis == "carryover" and adjustments else None
    return tuple(adjustments), tax_rate


def _prepare_impairment(entity: Entity, period: int, impairment, asset_name: str) -> Series | None:
    if impairment is None:
        return None
    impairment_series = _points(entity, impairment, f"{asset_name} impairment") * (entity.model.t >= period)
    entity.model.check(impairment_series >= 0,
                       f"{entity.name}: {asset_name} impairment must be nonnegative and start at acquisition")
    return impairment_series


def _prepare_acquisition(parent: Entity, entity: Entity, period: int, share: float, fair_value, acquired,
                         tax_basis: str, nci: str | None, nci_value, goodwill_life,
                         private_company: bool, impairment) -> AcquisitionTerms:
    standard = entity.standard.name
    if tax_basis not in ("carryover", "stepped_up"):
        raise ValueError("tax_basis= must be 'carryover' or 'stepped_up'")
    if standard == "US GAAP":
        if share < 1 and nci != "fair_value":
            raise ValueError("US GAAP partial acquisitions require nci='fair_value'")
        if nci not in (None, "fair_value"):
            raise ValueError("US GAAP requires nci='fair_value'")
        nci_method = "fair_value"
        if share < 1 and nci_value is None:
            raise ValueError("US GAAP partial acquisitions require nci_value=")
    else:
        nci_method = "proportionate" if nci is None else nci
        if nci_method not in ("proportionate", "fair_value"):
            raise ValueError("nci= must be 'proportionate' or 'fair_value'")
        if standard == "J-GAAP" and nci_method != "proportionate":
            raise ValueError("J-GAAP requires nci='proportionate'")
    if nci_method == "fair_value" and share < 1 and nci_value is None:
        raise ValueError("nci='fair_value' requires nci_value= for a partial acquisition")
    if nci_method == "proportionate" and nci_value is not None:
        raise ValueError("nci_value= is only valid with nci='fair_value'")
    if share == 1 and nci_value is not None:
        raise ValueError("nci_value= is not used when there is no noncontrolling interest")

    life = _goodwill_life(entity, goodwill_life, private_company)
    adjustments, tax_rate = _prepare_adjustments(entity, period, fair_value, acquired, tax_basis, "acquired subsidiary")
    normalized_nci_value = None if nci_value is None else \
        _acquisition_amount(parent, nci_value, period, "nci_value")
    impairment_series = _prepare_impairment(entity, period, impairment, "goodwill")
    return AcquisitionTerms(adjustments, tax_basis, nci_method, normalized_nci_value, life,
                            private_company, impairment_series, tax_rate)


def _prepare_equity_method(entity: Entity, period: int, fair_value, acquired, tax_basis: str,
                           goodwill_life, private_company: bool, impairment, loss_limit: bool) \
        -> EquityMethodTerms:
    if not isinstance(loss_limit, bool):
        raise TypeError("loss_limit= must be a boolean")
    if tax_basis not in ("carryover", "stepped_up"):
        raise ValueError("tax_basis= must be 'carryover' or 'stepped_up'")
    life = _goodwill_life(entity, goodwill_life, private_company, required=False)
    adjustments, tax_rate = _prepare_adjustments(entity, period, fair_value, acquired, tax_basis, "associate")
    impairment_series = _prepare_impairment(entity, period, impairment, "investment")
    return EquityMethodTerms(adjustments, tax_basis, life, private_company, impairment_series, tax_rate, loss_limit)


def _capital_share_pairs(parent: Entity, entity: Entity, investment: Account) -> tuple[Posting, ...]:
    parent_posts = [post for post in parent._postings if post.debit is investment and post.counterparty is entity]
    child_posts = [post for post in entity._postings
                   if any(post.counterpart is parent_post for parent_post in parent_posts)]
    return tuple(parent_posts + child_posts)

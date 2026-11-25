"""A group's consolidated ledger, derived from the member ledgers and ownership timeline."""
from __future__ import annotations

from collections.abc import Mapping
from numbers import Real
from typing import TYPE_CHECKING

from ..ledger import (SUBSIDIARY_INVESTMENT, Entity, _account_of, _held_by, _parts_doc, _points,
                      refuse_default_measures)
from ..series import Series, lift
from ..units import Quantity
from .consolidate import _consolidate
from .measures import _sum
from .prepare import (_acquisition_amount, _book_equity_method_sale, _capital_share_pairs, _goodwill_life,
                      _opening_amount, _prepare_acquisition, _prepare_adjustments, _prepare_equity_method,
                      _prepare_opening_equity_oci, _prepare_opening_oci, _prepare_opening_unrealized)
from .series import _OpeningDeferredTaxShare
from .terms import EquityMethodTerms, OpeningConsolidation, OpeningEquityMethod, OwnershipEvent

if TYPE_CHECKING:
    from ..model import Model


class Group:
    """A group of entities consolidated under a parent, and the ownership events that link them.

    ``m.group(name, parent=entity)`` makes a group, and `own` adds the entities the parent owns, with the terms of each
    acquisition, purchase, sale or change of method. The consolidated statements are derived from the members'
    ledgers and never booked by hand: ``r.pl(group)``, ``r.bs(group)`` and ``r.cf(group)`` read them, ``books`` is the
    consolidated ledger as an entity, and ``depreciation``, ``amortization`` and ``operating_income`` are the
    consolidated parts of EBITDA. The group uses the parent's accounting standard, layout and currency.

    Parameters
    ----------
    model : Model
        The model the group belongs to. Created through ``Model.group``, which also registers the group there.
    name : str
        Group name; required. It must be unique among the entities and groups of the model.
    parent : Entity
        The parent entity, an entity of the same model. It is consolidated from the first period.

    Attributes
    ----------
    model : Model
        The model the group belongs to.
    name : str
        The group's name.
    parent : Entity
        The parent entity.

    Raises
    ------
    ValueError
        At construction through ``Model.group``, if the parent is not an entity of the model, or if the name is
        already used by an entity or group.

    See Also
    --------
    boki.group.core.Group.own : Add an owned entity.
    boki.group.core.Group.books : The consolidated books.

    Notes
    -----
    Separate books stay entity-specific, and consolidation is derived from them in three steps: replay each
    member's entries for the periods it is in the group, eliminate the entries of trades between members (booked with
    ``counterparty=``), and add the consolidation entries (acquisition, goodwill, non-controlling interests,
    unrealized profit, equity-method accounting, translation). Members must share the parent's layout. A group does not
    define EBITDA, EBIT or NOI, like an entity: the parts are provided and reading those names raises
    ``AttributeError``. See the `consolidation notes
    <https://github.com/combinatrix-ai/boki/blob/master/docs/consolidation.md>`_ for the rules of each standard.

    Examples
    --------
    A parent that buys 80% of a subsidiary at the start of the first year. The non-controlling interests are 20% of the
    subsidiary's net assets, and the consolidated books hold both companies' cash:

    >>> import boki as b
    >>> from boki.units import JPY
    >>> m = b.Model("Group", start="2027-01", periods=2, step=b.year)
    >>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    >>> sub = m.entity("Sub", standard=b.IFRS, currency=JPY)
    >>> parent.bs.opening(cash=1000 * JPY)
    >>> sub.bs.opening(cash=500 * JPY)
    >>> sales = sub.pl.revenue("Sales", 100 * JPY)
    >>> group = m.group("Group", parent=parent)
    >>> group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY)
    >>> r = m.render()
    >>> books = group.books
    >>> round(r.value(books.bs.cash, "2027")), round(r.value(books.net_income, "2027"))
    (1200, 100)
    """

    model: Model
    name: str
    parent: Entity

    def __init__(self, model: Model, name: str, parent: Entity):
        if parent not in model.entities:
            raise ValueError(f"group {name!r}: the parent is not an entity of this model")
        self.model, self.name, self.parent = model, name, parent
        self._members: list[Entity] = [parent]
        self._ownership: dict[Entity, list[OwnershipEvent]] = {}

    def __repr__(self):
        return f"<Group {self.name}: {', '.join(e.name for e in self._members)}>"

    @property
    @_parts_doc("The consolidated operating income subtotal, as in ``r.pl(group)``.\n\n"
                "    The layout of the parent decides the subtotal; a layout without one (bank) raises\n"
                "    AttributeError. Built from the consolidated books, so intercompany items are eliminated.",
                "Consolidated operating income in each period, in the parent's currency per period.",
                raises="    AttributeError\n        At construction, when the property is read and the parent's layout has no operating\n"
                       "        income subtotal, such as the bank layout.",
                examples="    The group's operating income adds up the members', here 300 and 100:\n\n"
                         "    >>> import boki as b\n"
                         "    >>> from boki.units import JPY\n"
                         '    >>> m = b.Model("Group income", start="2027-01", periods=2, step=b.year)\n'
                         '    >>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY)\n'
                         '    >>> sub = m.entity("Sub", standard=b.IFRS, currency=JPY)\n'
                         "    >>> parent.bs.opening(cash=1000)\n"
                         "    >>> sub.bs.opening(cash=500)\n"
                         '    >>> parent_sales = parent.pl.revenue("Parent sales", 300 * JPY)\n'
                         '    >>> sub_sales = sub.pl.revenue("Sub sales", 100 * JPY)\n'
                         '    >>> group = m.group("Group", parent=parent)\n'
                         '    >>> group.own(sub, method="consolidate", consideration=500 * JPY)\n'
                         "    >>> r = m.render()\n"
                         '    >>> round(r.value(group.operating_income, "2027"))\n'
                         "    400")
    def operating_income(self) -> Series:
        return self.books.operating_income

    @property
    @_parts_doc("Consolidated depreciation of tangible assets, as a Series of positive expense.\n\n"
                "    The members' depreciation within the consolidation scope, with the intercompany profit in\n"
                "    depreciated assets eliminated, plus the depreciation of acquisition-date fair-value\n"
                "    step-ups of fixed assets. Impairment is not included.",
                "Consolidated depreciation expense in each period, positive, in the parent's currency per period.",
                examples="    The members' depreciation is added up, here one machine of the subsidiary:\n\n"
                         "    >>> import boki as b\n"
                         "    >>> from boki.units import JPY\n"
                         '    >>> m = b.Model("Group D&A", start="2027-01", periods=3, step=b.year)\n'
                         '    >>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY)\n'
                         '    >>> sub = m.entity("Sub", standard=b.IFRS, currency=JPY)\n'
                         "    >>> parent.bs.opening(cash=1000)\n"
                         "    >>> sub.bs.opening(cash=500)\n"
                         '    >>> machine = sub.bs.fixed_asset("Machine", cost=300, at=0, life=3 * b.year)\n'
                         '    >>> group = m.group("Group", parent=parent)\n'
                         '    >>> group.own(sub, method="consolidate", consideration=500 * JPY)\n'
                         "    >>> r = m.render()\n"
                         '    >>> [round(r.value(group.depreciation, year)) for year in ("2027", "2028", "2029")]\n'
                         "    [0, 100, 100]")
    def depreciation(self) -> Series:
        return self.books.depreciation

    @property
    @_parts_doc("Consolidated amortization, as a Series of positive expense.\n\n"
                "    The members' amortization of intangibles, the unwind of acquisition-date\n"
                "    fair-value adjustments on intangibles (not on liabilities or other items), and goodwill amortization where the group\n"
                "    amortizes goodwill (``goodwill_life=``, J-GAAP or the US GAAP private-company alternative).\n"
                "    Impairment is not included.",
                "Consolidated amortization expense in each period, positive, in the parent's currency per period.",
                examples="    The members' amortization is added up, here one piece of software of the subsidiary:\n\n"
                         "    >>> import boki as b\n"
                         "    >>> from boki.units import JPY\n"
                         '    >>> m = b.Model("Group amortization", start="2027-01", periods=3, step=b.year)\n'
                         '    >>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY)\n'
                         '    >>> sub = m.entity("Sub", standard=b.IFRS, currency=JPY)\n'
                         "    >>> parent.bs.opening(cash=1000)\n"
                         "    >>> sub.bs.opening(cash=500)\n"
                         '    >>> software = sub.bs.intangible("Software", cost=300, at=0, life=3 * b.year)\n'
                         '    >>> group = m.group("Group", parent=parent)\n'
                         '    >>> group.own(sub, method="consolidate", consideration=500 * JPY)\n'
                         "    >>> r = m.render()\n"
                         '    >>> [round(r.value(group.amortization, year)) for year in ("2027", "2028", "2029")]\n'
                         "    [0, 100, 100]")
    def amortization(self) -> Series:
        return self.books.amortization

    def own(self, entity: Entity, share: float = 1.0, *, since=0, method: str | None = None,
            consideration=None, proceeds=None, fair_value: Mapping | None = None, acquired: Mapping | None = None,
            tax_basis: str = "carryover", nci: str | None = None, nci_value=None, goodwill_life=None,
            private_company: bool = False, impairment=None, loss_limit: bool = True,
            previously_held_value=None, retained_value=None, opening: Mapping | None = None,
            investment=None) -> None:
        """Record a dated ownership event and its consolidation or equity-method terms.

        Each call adds one event for one entity: its acquisition, a later purchase, a sale, a change of accounting
        method, or the existing holding at the model start (``since="before"``). The event takes effect at the start of the
        ``since`` period, and the consolidated books are derived from the events when the model renders. Which
        arguments are valid depends on the kind of event; the group derives the kind from the entity's previous event.

        Parameters
        ----------
        entity : Entity
            The entity owned. It must be an entity of the group's model, not the parent, and it must have the same
            layout as the parent. Required.
        share : float, default=1.0
            The ownership after the event, a dimensionless fraction from 0 to 1. A share below the previous share is
            a sale, and 0 ends the ownership.
        since : int, str, date, or "before", default=0
            The period the event takes effect at the start of, as an index, a period label, or a date. ``"before"``
            says the holding began before the model starts; it must be the first event, and ``opening`` then supplies the
            balances at the start.
        method : str, optional
            ``"consolidate"``, ``"equity"`` or ``"cost"`` (an investment held as a financial asset). Required on the
            first event. After that, an omitted ``method`` keeps the previous one.
        consideration : scalar or Quantity, optional
            Price paid by the parent for shares from outside the group, in the parent's currency, booked in the
            ``since`` period as an investment on the parent's books. Omit it when the parent already holds the shares
            through a capital contribution made with ``counterparty=`` on the entity's ``bs.capital``. Not for a sale.
        proceeds : scalar, Quantity, or Series, optional
            Price received for shares sold, in the parent's currency, in the ``since`` period. Required when ``share``
            falls and not allowed otherwise. It must not be negative.
        fair_value : mapping, optional
            Acquisition-date fair-value adjustments to the entity's balance-sheet lines, as ``{line: amount}`` or
            ``{line: (amount, remaining_life)}``. A line is a line item or account of the entity, and a life is a time
            such as ``5 * b.year``; a depreciating asset needs one. Liability adjustments are given positive.
        acquired : mapping, optional
            Assets and liabilities that exist only at acquisition, as ``{name: amount}`` or
            ``{name: (amount, remaining_life)}``. A negative amount is a liability.
        tax_basis : str, default="carryover"
            ``"carryover"`` keeps the tax basis, so fair-value adjustments carry deferred tax at the entity's
            ``tax_rate``, and ``"stepped_up"`` has no deferred tax.
        nci : str, optional
            How non-controlling interests are measured at acquisition: ``"proportionate"`` (the default under IFRS and the only
            choice under J-GAAP) or ``"fair_value"`` (full goodwill, required under US GAAP for a partial acquisition). Only for
            ``method="consolidate"``.
        nci_value : scalar or Quantity, optional
            Acquisition-date fair value of the non-controlling interests, in the parent's currency. Required with
            ``nci="fair_value"`` when ``share`` is below 1, and not allowed otherwise.
        goodwill_life : Quantity, optional
            Amortization period of goodwill, a time such as ``10 * b.year``. J-GAAP requires it for a consolidated acquisition
            (at most 20 years). US GAAP allows it with ``private_company=True`` (at most 10 years). IFRS does not allow it.
        private_company : bool, default=False
            Use the US GAAP private-company alternative that amortizes goodwill. Only for US GAAP.
        impairment : scalar, Quantity, or Series, optional
            Impairment of goodwill (consolidate) or of the investment (equity), in the parent's currency per period from the
            ``since`` period on. It is an input, not tested by boki, and must not be negative.
        loss_limit : bool, default=True
            For ``method="equity"``: stop recognizing losses when the investment reaches 0, and recover the excess from later
            earnings first. ``False`` is not allowed for other methods.
        previously_held_value : scalar or Quantity, optional
            Fair value of the interest held before a step acquisition, in the parent's currency. Required for a step
            acquisition and not allowed otherwise.
        retained_value : scalar or Quantity, optional
            Fair value of the interest kept after a loss of control, in the parent's currency. Required under IFRS and
            US GAAP when ``share`` stays above 0, and not allowed under J-GAAP or for other events.
        opening : mapping, optional
            Required with ``since="before"``, not allowed otherwise. For ``method="consolidate"``, the balances at
            the model start, with the required key ``"nci"`` and the optional keys ``"goodwill"``, ``"fair_value"``,
            ``"acquired"``, ``"deferred_tax"``, ``"unrealized"``, ``"oci"`` and ``"capital_surplus"``. For
            ``method="equity"``, the required key ``"investment"`` and the optional keys ``"embedded_goodwill"``,
            ``"fair_value"``, ``"suspended_losses"`` and ``"oci"``. Amounts are in the parent's currency. See the
            consolidation notes for the forms of the values.
        investment : LineItem, optional
            With ``since="before"``, the parent's opening ``other_asset`` line that holds the shares, when the entity
            has no mirrored capital line. Omit it when the entity's ``bs.capital(..., opening=, counterparty=parent)`` records
            the investment.

        Raises
        ------
        ValueError
            At construction, if ``entity`` is not an entity of the model or is the parent, ``share`` is outside 0 to 1,
            ``method`` is not one of the three, an event is not in a later period than the previous one or changes neither
            the share nor the method, or the first event has no positive share. Also if a term is used with an event
            it does not belong to (``proceeds`` on a purchase, acquisition terms on a sale or on ``method="cost"``,
            ``nci`` or ``nci_value`` with ``method="equity"``, ``retained_value`` or ``previously_held_value`` outside a
            loss of control or a step acquisition, ``opening`` or ``investment`` without ``since="before"``); if a step
            acquisition lowers the share or a loss of control raises it; if a standard's goodwill rule is broken
            (``goodwill_life`` missing or too long under J-GAAP, given under IFRS, or without ``private_company`` under US
            GAAP; ``nci`` other than ``"fair_value"`` under US GAAP or other than ``"proportionate"`` under J-GAAP;
            a missing ``nci_value``); if ``tax_basis`` is not ``"carryover"`` or ``"stepped_up"``; if a ``fair_value``
            key is not a balance-sheet line of the entity or a life is not positive; or if an ``opening`` mapping has
            unsupported keys.
        TypeError
            At construction, if ``method`` is missing on the first event, a decrease has no ``proceeds``, a step acquisition
            has no ``previously_held_value`` or no ``consideration`` when the share rises, a loss of control that keeps
            a stake has no ``retained_value`` (IFRS and US GAAP), an equity-method purchase has neither ``consideration``
            nor a matching capital contribution, ``loss_limit`` is not a bool, a ``fair_value``, ``acquired`` or
            ``opening`` argument is not a mapping, an ``opening`` mapping lacks its required key, or ``goodwill_life`` or a
            life is not a time quantity.
        NotImplementedError
            At construction, if the entity's layout differs from the parent's, or the method changes in a way that is
            not supported (for example from ``"equity"`` to ``"cost"``).
        IndexError
            At construction, if ``since`` is a period outside the model timeline.
        UnitError
            At construction, if an amount is in a unit other than the currency of the books it is booked in, or a life
            is a quantity that is not a time.
        CheckFailed
            At evaluation (``m.render``), if ``proceeds`` or ``impairment`` is negative, or an ``opening`` amount that has to
            be non-negative is not (embedded goodwill and suspended losses), or the equity-method opening investment
            differs from the balance recorded on the parent's books.

        See Also
        --------
        boki.group.core.Group.books : The consolidated books these events produce.
        boki.ledger.BS.sell : Sell a fixed asset to another entity, which is a trade and not an ownership event.

        Notes
        -----
        The kind of event follows from the previous event: the first one is an acquisition, a higher share with the same
        method a purchase, a lower share a sale, a move from ``"equity"`` or ``"cost"`` to ``"consolidate"`` a step
        acquisition, and a move from ``"consolidate"`` away from control a loss of control. Under ``"consolidate"``
        the subsidiary's assets and liabilities enter the consolidated books at their acquisition-date balances
        (the previous period's closing balances), its equity and the parent's shares are eliminated, non-controlling
        interests and goodwill are recorded, and the subsidiary's earlier income is excluded. Each period the non-controlling
        share of profit moves from retained earnings to non-controlling interests. Under ``"equity"``, the investment
        grows by the parent's share of the associate's profit and OCI, less dividends, goodwill-equivalent amortization and
        impairment, and the associate's entries are not replayed. Cash flows of acquisitions and disposals are
        investing activities, net of cash acquired or disposed of; changes that keep control are financing.

        The goodwill, non-controlling interest, step-acquisition and loss-of-control rules differ by standard; the
        `consolidation notes
        <https://github.com/combinatrix-ai/boki/blob/master/docs/consolidation.md>`_ give each rule and a worked example
        for every stage. Amounts that meet the parent's books should be quantities such as ``400 * JPY``.

        Examples
        --------
        The parent buys 80% of a subsidiary at the start of the first year for 400, the 80% share of net assets of 500.
        Goodwill is 0, non-controlling interests are 100 plus their share of profit, and 20 of the subsidiary's profit of 100
        belongs to them:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> years = ["2027", "2028", "2029"]
        >>> m = b.Model("Acquisition", start="2027-01", periods=3, step=b.year)
        >>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
        >>> sub = m.entity("Sub", standard=b.IFRS, currency=JPY)
        >>> parent.bs.opening(cash=1000 * JPY)
        >>> sub.bs.opening(cash=500 * JPY)
        >>> sales = sub.pl.revenue("Sales", 100 * JPY)
        >>> group = m.group("Group", parent=parent)
        >>> group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY)
        >>> r = m.render()
        >>> books = group.books
        >>> [round(r.value(books.bs.total_assets, year)) for year in years]
        [1200, 1300, 1400]
        >>> [round(r.value(books.net_income, year)) for year in years]
        [100, 100, 100]

        A 30% associate under the equity method: the investment is the price plus the parent's 30% share of the
        associate's profit of 50 each year:

        >>> m = b.Model("Associate", start="2027-01", periods=2, step=b.year)
        >>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
        >>> associate = m.entity("Associate", standard=b.IFRS, currency=JPY)
        >>> parent.bs.opening(cash=1000 * JPY)
        >>> plant = associate.bs.other_asset("Plant", opening=600 * JPY)
        >>> profit = associate.pl.revenue("Profit", 50 * JPY)
        >>> group = m.group("Group", parent=parent)
        >>> group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY)
        >>> r = m.render()
        >>> [round(r.value(group.books.bs.total_assets, year)) for year in ("2027", "2028")]
        [1015, 1030]
        """  # noqa: DOC105, DOC107, DOC503
        if entity not in self.model.entities:
            raise ValueError(f"{entity!r} is not an entity of this model")
        if entity is self.parent:
            raise ValueError(f"{entity.name} is already the parent of {self.name}")
        if not 0 <= share <= 1:
            raise ValueError(f"{self.name}: share must be between 0 and 1, got {share}")
        if since == "before":
            self._own_before(entity, share, method, opening, investment, consideration, proceeds,
                             fair_value, acquired, tax_basis, nci, nci_value, goodwill_life, private_company,
                             impairment, loss_limit, previously_held_value, retained_value)
            return
        if opening is not None or investment is not None:
            raise ValueError(f"{self.name}: opening= and investment= apply only to since='before'")
        period = self.model.timeline.index(since)
        if entity.layout is not self.parent.layout:
            raise NotImplementedError(f"{entity.name} uses {entity.layout.name}, {self.parent.name} "
                                      f"{self.parent.layout.name}; members must share a layout for now")

        events = self._ownership.get(entity, [])
        if not events:
            if share == 0:
                raise ValueError(f"{self.name}: an initial ownership event must have a positive share")
            if method is None:
                raise TypeError(f"{self.name}: method= is required on the first own()")
            kind, previous_method, previous_share = "acquisition", None, 0.0
        else:
            previous = events[-1]
            if period <= previous.period:
                raise ValueError(f"{self.name}: ownership events for {entity.name} must be in later periods")
            method = previous.method if method is None else method
            previous_method, previous_share = previous.method, previous.share
            if previous_share == 0 and share > 0:
                kind, previous_method = "acquisition", None
            elif method == previous_method:
                if share == previous_share:
                    raise ValueError(f"{self.name}: an ownership event must change the share or method")
                kind = "loss" if previous_method == "consolidate" and share == 0 else \
                    ("sale" if share < previous_share else "purchase")
            elif previous_method in ("equity", "cost") and method == "consolidate":
                if share < previous_share:
                    raise ValueError(f"{self.name}: a step acquisition cannot reduce ownership")
                kind = "step"
            elif previous_method == "consolidate" and method in ("equity", "cost"):
                if share > previous_share:
                    raise ValueError(f"{self.name}: a loss of control cannot increase ownership")
                kind = "loss"
            else:
                raise NotImplementedError(f"{self.name}: method changes from {previous_method!r} to {method!r} "
                                          "are not supported in S4")

        if method not in ("consolidate", "equity", "cost"):
            raise ValueError(f"{self.name}: method= must be 'consolidate', 'equity' or 'cost'")
        if method == "equity" and not isinstance(loss_limit, bool):
            raise TypeError("loss_limit= must be a boolean")
        if method == "equity" and (nci is not None or nci_value is not None):
            raise ValueError(f"{self.name}: nci= and nci_value= apply only to method='consolidate'")
        if method != "equity" and not loss_limit:
            raise ValueError(f"{self.name}: loss_limit= applies only to method='equity'")

        if kind in ("sale", "loss"):
            if share < previous_share and proceeds is None:
                raise TypeError(f"{self.name}: a decrease in ownership requires proceeds=")
            if consideration is not None:
                raise ValueError(f"{self.name}: consideration= cannot be used on a sale")
            if (fair_value or acquired or tax_basis != "carryover" or nci is not None or nci_value is not None
                    or goodwill_life is not None or private_company or impairment is not None):
                raise ValueError(f"{self.name}: acquisition terms cannot be set on a sale")
            if previously_held_value is not None:
                raise ValueError(f"{self.name}: previously_held_value= applies only to a step acquisition")
        elif proceeds is not None:
            raise ValueError(f"{self.name}: proceeds= applies only to a decrease in ownership")

        if kind == "step":
            if previously_held_value is None:
                raise TypeError(f"{self.name}: a step acquisition requires previously_held_value=")
            if retained_value is not None:
                raise ValueError(f"{self.name}: retained_value= applies only to a loss of control")
        elif previously_held_value is not None:
            raise ValueError(f"{self.name}: previously_held_value= applies only to a step acquisition")

        if kind == "loss":
            if retained_value is not None and share == 0:
                raise ValueError(f"{self.name}: retained_value= cannot be set when share is zero")
            if entity.standard.name == "J-GAAP":
                if retained_value is not None:
                    raise ValueError(f"{self.name}: retained_value= is not used under J-GAAP")
            elif share > 0 and retained_value is None:
                raise TypeError(f"{self.name}: a retained interest requires retained_value=")
        elif retained_value is not None:
            raise ValueError(f"{self.name}: retained_value= applies only to a loss of control")

        if method == "cost" and (fair_value or acquired or tax_basis != "carryover" or nci is not None
                                  or nci_value is not None or goodwill_life is not None or private_company
                                  or impairment is not None):
            raise ValueError(f"{self.name}: acquisition terms do not apply to method='cost'")

        acquisition = None
        if method == "equity" and kind in ("acquisition", "purchase"):
            acquisition = _prepare_equity_method(entity, period, fair_value, acquired, tax_basis,
                                                  goodwill_life, private_company, impairment, loss_limit)
        elif method == "equity" and kind == "loss":
            acquisition = EquityMethodTerms((), "carryover", None, False, None, None, loss_limit)
        elif method == "consolidate" and kind in ("acquisition", "step"):
            acquisition = _prepare_acquisition(self.parent, entity, period, share, fair_value, acquired, tax_basis, nci,
                                               nci_value, goodwill_life, private_company, impairment)
        elif kind == "purchase" and method == "equity" and not loss_limit:
            raise ValueError(f"{self.name}: loss_limit= must be set on the first equity-method own()")
        elif method != "equity" and kind == "purchase" and (
                fair_value or acquired or tax_basis != "carryover" or nci is not None or nci_value is not None
                or goodwill_life is not None or private_company or impairment is not None):
            raise ValueError(f"{self.name}: acquisition terms can be set only on an acquisition or step")

        investment, _ = _held_by(self.parent, f"{entity.name} shares", tags={SUBSIDIARY_INVESTMENT})
        opening_value = self.parent._balance(investment).opening * (self.model.t == period)
        purchase_amount = None
        sale_proceeds = None
        held_value = None
        retained_basis = None
        posting = None
        if consideration is not None:
            purchase_amount = _points(self.parent, {period: consideration}, f"{entity.name} shares")
            posting = self.parent._post(f"{entity.name} shares {'acquisition' if kind == 'acquisition' else 'purchase'}",
                                        purchase_amount, debit=investment, credit=self.parent._cash_account)
        if proceeds is not None:
            sale_proceeds = _points(self.parent, proceeds, f"{entity.name} shares sale proceeds") \
                * (self.model.t == period)
            self.model.check(sale_proceeds >= 0, f"{entity.name}: sale proceeds must be nonnegative")
        if previously_held_value is not None:
            held_value = _acquisition_amount(self.parent, previously_held_value, period, "previously_held_value")
        if retained_value is not None:
            retained_basis = _acquisition_amount(self.parent, retained_value, period, "retained_value")

        previous_end = events[-1].investment_end if events else None
        paired_postings = _capital_share_pairs(self.parent, entity, investment) \
            if (kind == "acquisition" or (kind in ("purchase", "step") and method in ("equity", "consolidate"))) \
            and consideration is None else ()
        contribution_parts = [post.amount * (self.model.t == period) for post in paired_postings
                              if post.debit.entity is self.parent]
        acquisition_contribution = _sum(contribution_parts, self.parent,
                                        f"{entity.name}: capital at acquisition") if paired_postings else lift(0)
        individual_carrying_sold = lift(0)
        sale_postings = ()
        if kind == "acquisition":
            investment_cost = opening_value + (purchase_amount if purchase_amount is not None else acquisition_contribution)
        elif kind in ("purchase", "step"):
            if method == "equity" and purchase_amount is None and not paired_postings:
                raise TypeError(f"{self.name}: an equity-method purchase requires consideration= or a matching "
                                "counterparty= capital contribution")
            if purchase_amount is not None:
                investment_cost = purchase_amount
            elif paired_postings:
                investment_cost = acquisition_contribution
            elif kind == "step" and share == previous_share:
                investment_cost = lift(0)
            elif kind == "step" and share > previous_share:
                raise TypeError(f"{self.name}: a step acquisition that increases ownership requires consideration=")
            else:
                investment_cost = opening_value - previous_end
        else:
            individual_carrying_sold = lift(0)
            if share < previous_share:
                sold_fraction = (previous_share - share) / previous_share
                individual_carrying_sold = opening_value * sold_fraction
                sale_postings = _book_equity_method_sale(
                    self.parent, investment, sale_proceeds, individual_carrying_sold, entity.name)
            investment_cost = lift(0)

        if kind in ("sale", "loss"):
            investment_end = opening_value - individual_carrying_sold
        else:
            investment_end = opening_value + (purchase_amount if purchase_amount is not None else acquisition_contribution)
            sale_postings = ()
        event = OwnershipEvent(entity=entity, period=period, share=share, method=method, kind=kind,
                               previous_method=previous_method, previous_share=previous_share,
                               consideration=purchase_amount, proceeds=sale_proceeds,
                               previously_held_value=held_value, retained_value=retained_basis,
                               investment=investment, posting=posting,
                               investment_end=investment_end, investment_cost=investment_cost,
                               individual_carrying_sold=individual_carrying_sold,
                               paired_postings=paired_postings, acquisition_contribution=acquisition_contribution,
                               acquisition=acquisition, sale_postings=sale_postings)
        self._ownership.setdefault(entity, []).append(event)
        if entity not in self._members:
            self._members.append(entity)

    def _own_before(self, entity, share, method, opening, investment, consideration, proceeds,
                    fair_value, acquired, tax_basis, nci, nci_value, goodwill_life, private_company,
                    impairment, loss_limit, previously_held_value, retained_value) -> None:
        if self._ownership.get(entity):
            raise ValueError(f"{self.name}: since='before' must be the first ownership event for {entity.name}")
        if share <= 0:
            raise ValueError(f"{self.name}: an initial ownership event must have a positive share")
        if method not in ("consolidate", "equity"):
            raise ValueError(f"{self.name}: since='before' supports method='consolidate' or 'equity'")
        if entity.layout is not self.parent.layout:
            raise NotImplementedError(f"{entity.name} uses {entity.layout.name}, {self.parent.name} "
                                      f"{self.parent.layout.name}; members must share a layout for now")
        if any(value is not None for value in (consideration, proceeds, fair_value, acquired, nci, nci_value,
                                                impairment, previously_held_value, retained_value)) or \
                tax_basis != "carryover" or (method == "consolidate" and loss_limit is not True) or \
                goodwill_life is not None:
            raise ValueError(f"{self.name}: since='before' uses opening= for existing balances and terms")
        if not isinstance(opening, Mapping):
            raise TypeError(f"{self.name}: since='before' requires opening= as a mapping")
        if method == "equity":
            self._own_opening_equity(entity, share, opening, investment, private_company, loss_limit)
            return
        allowed = {"goodwill", "nci", "fair_value", "acquired", "deferred_tax", "unrealized", "oci",
                   "capital_surplus"}
        extra = set(opening) - allowed
        if extra:
            raise ValueError(f"{self.name}: opening= has unsupported keys for method='consolidate': "
                             f"{', '.join(sorted(map(str, extra)))}")
        if "nci" not in opening:
            raise TypeError(f"{self.name}: opening= for method='consolidate' requires 'nci'")

        goodwill_spec = opening.get("goodwill", 0)
        if isinstance(goodwill_spec, tuple):
            if len(goodwill_spec) != 2:
                raise ValueError("opening['goodwill'] must be amount or (amount, remaining_life)")
            goodwill_amount, remaining_life = goodwill_spec
        else:
            goodwill_amount, remaining_life = goodwill_spec, None
        goodwill = _opening_amount(entity, goodwill_amount, "opening goodwill")
        goodwill_nonzero = goodwill_amount.value != 0 if isinstance(goodwill_amount, Quantity) else \
            (goodwill_amount != 0 if isinstance(goodwill_amount, Real) else True)
        goodwill_life = _goodwill_life(entity, remaining_life, private_company,
                                       required=entity.standard.name == "J-GAAP" and goodwill_nonzero)

        mirrored = [account for account in entity._accounts
                    if account.kind == "capital" and account.side == "equity" and account.mirror is not None]
        if investment is not None and mirrored:
            raise ValueError(f"{self.name}: both opening investment records were supplied for {entity.name}")
        if investment is None:
            if len(mirrored) != 1:
                raise TypeError(f"{self.name}: since='before' requires exactly one opening investment record "
                                f"for {entity.name}")
            investment_account = mirrored[0].mirror
        else:
            investment_account = _account_of(investment)
            if investment_account.entity is not self.parent or investment_account.side != "asset" or \
                    investment_account.kind != "other_asset":
                raise ValueError(f"{self.name}: investment= must reference the parent's opening other_asset")
            if investment_account.opening is None:
                raise ValueError(f"{self.name}: investment= must have an opening balance")
        if investment_account is None or investment_account.opening is None:
            raise ValueError(f"{self.name}: {entity.name} shares need an opening investment balance")
        investment_account.tags = investment_account.tags | {SUBSIDIARY_INVESTMENT}

        adjustments, tax_rate = _prepare_adjustments(entity, 0, opening.get("fair_value"),
                                                     opening.get("acquired"), "carryover", "acquired subsidiary")
        nci_amount = _opening_amount(self.parent, opening["nci"], "opening NCI")
        deferred_tax = _opening_amount(entity, opening.get("deferred_tax", 0), "opening deferred tax")
        deferred_tax_shares = tuple(_OpeningDeferredTaxShare(deferred_tax,
                                                              tuple(adjustment.value * tax_rate
                                                                    for adjustment in adjustments),
                                                              index)
                                    for index in range(len(adjustments))) if tax_rate is not None else ()
        capital_surplus = _opening_amount(self.parent, opening.get("capital_surplus", 0),
                                           "opening capital surplus")
        unrealized = _prepare_opening_unrealized(entity, self.parent, opening.get("unrealized", {}))
        oci = _prepare_opening_oci(entity, self.parent, opening.get("oci", {}))
        if deferred_tax is not None and not adjustments and "deferred_tax" in opening:
            entity.model.check(deferred_tax == 0,
                               f"{entity.name}: opening deferred_tax requires fair_value= or acquired= items")
        terms = OpeningConsolidation(goodwill, goodwill_life, nci_amount, tuple(adjustments), deferred_tax,
                                     deferred_tax_shares, tax_rate, capital_surplus, unrealized, oci)
        zero = lift(0)
        event = OwnershipEvent(entity=entity, period=-1, share=share, method=method, kind="opening",
                               previous_method=None, previous_share=0, consideration=None, proceeds=None,
                               previously_held_value=None, retained_value=None, investment=investment_account,
                               posting=None,
                               investment_end=self.parent._balance(investment_account).opening,
                               investment_cost=investment_account.opening, individual_carrying_sold=zero,
                               opening=terms)
        self._ownership.setdefault(entity, []).append(event)
        if entity not in self._members:
            self._members.append(entity)

    def _own_opening_equity(self, entity, share, opening, investment, private_company, loss_limit) -> None:
        if not isinstance(loss_limit, bool):
            raise TypeError("loss_limit= must be a boolean")
        allowed = {"investment", "embedded_goodwill", "fair_value", "suspended_losses", "oci"}
        extra = set(opening) - allowed
        if extra:
            raise ValueError(f"{self.name}: opening= has unsupported keys for method='equity': "
                             f"{', '.join(sorted(map(str, extra)))}")
        if "investment" not in opening:
            raise TypeError(f"{self.name}: opening= for method='equity' requires 'investment'")

        mirrored = [account for account in entity._accounts
                    if account.kind == "capital" and account.side == "equity" and account.mirror is not None]
        if investment is not None and mirrored:
            raise ValueError(f"{self.name}: both opening investment records were supplied for {entity.name}")
        if investment is None:
            if len(mirrored) != 1:
                raise TypeError(f"{self.name}: since='before' requires exactly one opening investment record "
                                f"for {entity.name}")
            investment_account = mirrored[0].mirror
        else:
            investment_account = _account_of(investment)
            if investment_account.entity is not self.parent or investment_account.side != "asset" or \
                    investment_account.kind != "other_asset":
                raise ValueError(f"{self.name}: investment= must reference the parent's opening other_asset")
            if investment_account.opening is None:
                raise ValueError(f"{self.name}: investment= must have an opening balance")
        if investment_account is None or investment_account.opening is None:
            raise ValueError(f"{self.name}: {entity.name} shares need an opening investment balance")
        investment_account.tags = investment_account.tags | {SUBSIDIARY_INVESTMENT}

        investment_amount = _opening_amount(self.parent, opening["investment"], "opening equity-method investment")
        matches_opening = (entity.model.t != 0) | (investment_account.opening == investment_amount)
        entity.model.check(matches_opening,
                           f"{self.name}: opening investment for {entity.name} must match the parent's recorded balance")
        goodwill_spec = opening.get("embedded_goodwill", 0)
        if isinstance(goodwill_spec, tuple):
            if len(goodwill_spec) != 2:
                raise ValueError("opening['embedded_goodwill'] must be amount or (amount, remaining_life)")
            goodwill_amount, remaining_life = goodwill_spec
        else:
            goodwill_amount, remaining_life = goodwill_spec, None
        goodwill = _opening_amount(entity, goodwill_amount, "opening embedded goodwill")
        goodwill_nonzero = goodwill_amount.value != 0 if isinstance(goodwill_amount, Quantity) else \
            (goodwill_amount != 0 if isinstance(goodwill_amount, Real) else True)
        goodwill_life = _goodwill_life(entity, remaining_life, private_company, required=goodwill_nonzero)
        entity.model.check(goodwill >= 0, f"{entity.name}: opening embedded goodwill must be nonnegative")

        fair_value, tax_rate = _prepare_adjustments(entity, 0, opening.get("fair_value"), None,
                                                    "carryover", "associate")
        suspended_losses = _opening_amount(self.parent, opening.get("suspended_losses", 0),
                                           "opening suspended equity-method losses")
        entity.model.check(suspended_losses >= 0,
                           f"{entity.name}: opening suspended equity-method losses must be nonnegative")
        oci = _prepare_opening_equity_oci(entity, self.parent, opening.get("oci", {}))
        terms = OpeningEquityMethod(investment_amount, goodwill, goodwill_life, suspended_losses,
                                    fair_value, tax_rate, oci)
        acquisition = EquityMethodTerms(fair_value, "carryover", goodwill_life, private_company,
                                        None, tax_rate, loss_limit)
        zero = lift(0)
        event = OwnershipEvent(entity=entity, period=-1, share=share, method="equity", kind="opening",
                               previous_method=None, previous_share=0, consideration=None, proceeds=None,
                               previously_held_value=None, retained_value=None, investment=investment_account,
                               posting=None, investment_end=investment_amount,
                               investment_cost=investment_amount, individual_carrying_sold=zero,
                               acquisition=acquisition, opening=terms)
        self._ownership.setdefault(entity, []).append(event)
        if entity not in self._members:
            self._members.append(entity)

    @property
    def books(self) -> Entity:
        """The group's consolidated books, as an entity.

        The consolidated ledger has the same statements as any entity (``books.pl``, ``books.bs``, ``books.cf``,
        ``books.net_income``). It replays the members' entries, eliminates the trades between them, and adds the
        consolidation entries for the ownership events recorded with `own`.

        Returns
        -------
        Entity
            A new entity that is not registered in the model. The property builds the consolidated ledger again on
            every read, so read it once and use the result, because series of two reads are different objects.

        Raises
        ------
        ValueError
            At evaluation (``m.render`` builds the books), if a member's currency differs from the parent's and the
            model has no ``Model.fx`` rates between the two currencies.

        See Also
        --------
        boki.group.core.Group.own : Record the ownership events the books are derived from.

        Examples
        --------
        The consolidated books of a group whose subsidiary earns 100 a year:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> m = b.Model("Books", start="2027-01", periods=2, step=b.year)
        >>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
        >>> sub = m.entity("Sub", standard=b.IFRS, currency=JPY)
        >>> parent.bs.opening(cash=1000 * JPY)
        >>> sub.bs.opening(cash=500 * JPY)
        >>> sales = sub.pl.revenue("Sales", 100 * JPY)
        >>> group = m.group("Group", parent=parent)
        >>> group.own(sub, method="consolidate", consideration=500 * JPY)
        >>> r = m.render()
        >>> books = group.books
        >>> round(r.value(books.net_income, "2027")), round(r.value(books.bs.total_assets, "2028"))
        (100, 1200)
        """  # noqa: DOC502
        return _consolidate(self)


refuse_default_measures(Group, "group")

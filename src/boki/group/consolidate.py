"""The consolidation: replays member postings into the group's books, step by step."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..ledger import (ACQUISITION_CLEARING, AMORTIZATION, SHARED, SUBSIDIARY_INVESTMENT, Account, Entity,
                      LineItem, _OCIComponent, _Total)
from ..series import Series, lift, smax, smin
from .measures import (_adjustment_amortization, _adjustment_amortization_account, _asset_trade_states,
                       _at_period, _book_acquisition_adjustments, _control_disposal_account,
                       _control_event_mask, _convert_currency, _currency_dims, _equity_adjustment_amounts,
                       _equity_method_lots, _equity_method_sale_labels, _equity_method_sale_retention,
                       _foreign_balance_delta, _fx_rate, _group_pl_account, _member_oci, _member_oci_release,
                       _member_profit, _net_assets, _opening_amortization_fraction, _opening_oci_attribution,
                       _ownership_event_mask, _ownership_scope, _post_unwind, _sale_account, _scoped_amount,
                       _share_series, _standalone_net_assets, _step_acquisition_account, _sum,
                       _tagged_opening)
from .series import (_EquityMethodAvailable, _EquityMethodProfit, _GoodwillAmortization, _JgaapNciProfit,
                     _JgaapSuspendedLoss, _OpeningOciBalance)
from .terms import (AcquisitionAdjustment, AcquisitionTerms, EquityMethodTerms, OpeningConsolidation,
                    OpeningEquityMethod, OwnershipEvent, Scope)

if TYPE_CHECKING:
    from .core import Group


class _Consolidation:
    def __init__(self, g: Group):
        self.g = g
        p = self.p = g.parent
        for entity in g._members:
            if entity._currency is not None and p._currency is not None and entity._currency != p._currency:
                _fx_rate(g.model, entity._currency, p._currency, "average")
        books = self.books = Entity(g.model, g.name, p.standard, p.fiscal, p.layout, p.currency)
        self.subsidiaries = {e: events for e, events in g._ownership.items()
                             if _ownership_scope(events, "consolidate").intervals}
        self.associates = {e: events for e, events in g._ownership.items()
                           if _ownership_scope(events, "equity").intervals}
        self.opening_events = [event for events in self.subsidiaries.values() for event in events
                               if event.kind == "opening" and isinstance(event.opening, OpeningConsolidation)]
        self.opening_equity_events = [event for events in self.associates.values() for event in events
                                      if event.kind == "opening" and isinstance(event.opening, OpeningEquityMethod)]
        self.opening_by_entity = {event.entity: event for event in self.opening_events}
        self.opening_investments = {event.investment for event in (*self.opening_events, *self.opening_equity_events)}
        self.opening_unrealized = {spec.trade: spec for event in self.opening_events
                                   for spec in event.opening.unrealized}
        self.opening_oci_parent = {(event.entity, name): parent_part for event in self.opening_events
                               for name, _, parent_part, _ in event.opening.oci}
        self.opening_oci_nci = {(event.entity, name): nci_part for event in self.opening_events
                                for name, _, _, nci_part in event.opening.oci}
        self.opening_oci_source = {(event.entity, name): source for event in self.opening_events
                                   for name, source, _, _ in event.opening.oci}
        books._opening_oci_parent = self.opening_oci_parent
        books._opening_oci_nci = self.opening_oci_nci
        self.replay_entities = [p, *self.subsidiaries]
        self.scopes = {p: Scope(((0, None),))} | {e: _ownership_scope(events, "consolidate")
                                                  for e, events in self.subsidiaries.items()}
        g._s6_trade_states = _asset_trade_states(g, self.scopes)
        g._acquisition_pair_amounts = {
            post: post.amount * (g.model.t <= event.period if post.debit.entity is p
                                  else g.model.t == event.period)
            for events in self.subsidiaries.values() for event in events
            if event.method == "consolidate" and event.kind in ("acquisition", "step")
            for post in event.paired_postings
        }
        self.acquired_capital_receipts = {
            post for events in self.subsidiaries.values() for event in events
            if event.method == "consolidate" and event.kind in ("acquisition", "step")
            for post in event.paired_postings if post.debit.entity is event.entity
        }
        self.control_sale_events = [event for events in g._ownership.values() for event in events
                                    if event.previous_method == "consolidate" and event.kind in ("sale", "loss")]
        self.control_sale_postings = {post for event in self.control_sale_events for post in event.sale_postings}
        self.mapped: dict[Account, Account] = {}
        self.openings: dict[Account, list[Series]] = {}

        self.has_subsidiaries = bool(self.subsidiaries)
        self.nci_accounts: dict[Entity, Account] = {}
        self.clearing = self.goodwill = self.capital_surplus = None
        self.equity_investments: dict[Entity, Account] = {}
        self.active_pl_accounts = set()
        self.cta_accounts: dict[Entity, Account] = {}
        self.cta_parts: dict[Entity, list[Series]] = {}
        self.cta_parent_only_parts: dict[Entity, list[Series]] = {}
        self.net_investment_fx_posts = []
        self.s6_profit_adjustments: dict[Entity, list[Series]] = {}
        self.acquisition_nci: dict[OwnershipEvent, Series] = {}
        self.acquisition_profit_adjustments: dict[Entity, list[Series]] = {}
        self.full_goodwill_impairments: dict[Entity, list[Series]] = {}
        self.goodwill_schedules: dict[OwnershipEvent, tuple[Series, list[Series]]] = {}
        self.foreign_goodwill_schedules: dict[OwnershipEvent, tuple[Series, list[Series]]] = {}
        self.cap_changes = []
        self.opening_oci_transfers: dict[tuple[Entity, str], list[Series]] = {}
        self.released_oci: dict[tuple[Entity, str], list[Series]] = {}
        self.cta_release_oci: dict[Entity, list[Series]] = {}
        self.oci_parts: dict[str, list[Series]] = {}
        self.oci_targets: dict[str, Account] = {}
        self.oci_policies: dict[str, bool] = {}
        self.equity_oci_movements: dict[Entity, list[Series]] = {}
        self.profit_shares = []

    def account(self, source: Account) -> Account:
        g, p, books = self.g, self.p, self.books
        if source not in self.mapped:
            entity = source.entity
            if source is entity._cash_account:
                target = books._cash_account
            elif source is entity.retained_earnings:
                target = books.retained_earnings
            elif source.kind in SHARED and source is entity._shared_accounts.get(source.kind):
                target = books._shared(source.kind)
            else:
                target = next((a for a in books._accounts
                               if (a.side, a.kind, a.name) == (source.side, source.kind, source.name)), None)
                if target is None:
                    target = books._account(source.name, source.side, source.kind, source.cf, source.category,
                                            tags=source.tags)
            target.tags = target.tags | source.tags
            self.mapped[source] = target
            opening_member = entity is p or entity in self.opening_by_entity
            opening_balance = source.opening is not None and source is not entity.retained_earnings
            if entity is not p:
                opening_balance = opening_balance and source.side in ("asset", "liability")
            if source in self.opening_investments:
                opening_balance = False
            mirror = source.mirror
            if opening_member and mirror is not None and mirror.opening is not None and \
                    mirror.side in ("asset", "liability") and \
                    (mirror.entity is p or mirror.entity in self.opening_by_entity):
                opening_balance = False
            if opening_member and opening_balance:
                opening_amount = source.opening
                if entity is not p and entity._currency is not None and p._currency is not None:
                    opening_amount = _convert_currency(g.model, opening_amount, entity._currency, p._currency,
                                                       "opening")
                self.openings.setdefault(target, []).append(opening_amount)
        return self.mapped[source]

    def run(self) -> Entity:
        self.map_accounts()
        self.create_group_accounts()
        self.create_associate_investments()
        self.replay_postings()
        self.translate_foreign_members()
        self.translate_intercompany_trades()
        self.eliminate_opening_unrealized()
        self.eliminate_intercompany_trades()
        self.book_acquisitions()
        self.book_opening_acquisition_adjustments()
        self.book_opening_goodwill()
        self.translate_goodwill()
        self.translate_acquisition_adjustments()
        self.book_ownership_changes()
        self.transfer_opening_oci()
        self.book_loss_of_control()
        self.collect_oci()
        self.book_equity_method()
        self.register_oci_lines()
        self.attribute_to_nci()
        self.attribute_group_profit()
        self.add_pl_lines()
        return self.books

    def map_accounts(self):
        p, books = self.p, self.books
        for entity in self.replay_entities:
            for source in entity._accounts:
                self.account(source)
        for target, parts in self.openings.items():
            openings_total = lift(parts[0])
            for part in parts[1:]:
                openings_total = openings_total + part
            target.opening = openings_total
        if self.opening_events or self.opening_equity_events:
            books.retained_earnings.opening = p.retained_earnings.opening

    def create_group_accounts(self):
        g, p, books = self.g, self.p, self.books
        if self.has_subsidiaries:
            nci_name = books.label("nci")
            for entity in self.subsidiaries:
                name = f"{nci_name} ({entity.name})"
                nci = books._account(name, "equity", "nci", "financing")
                self.nci_accounts[entity] = nci
                opening_event = self.opening_by_entity.get(entity)
                if opening_event is not None:
                    nci.opening = opening_event.opening.nci
                nci_line = LineItem(name, books._balance(nci), books, "nci", nci)
                nci_line.balance = nci_line.expr
                if hasattr(books.bs, "nci"):
                    books.bs.nci._items.append(nci_line)
            self.clearing = books._account("Acquisition clearing", "equity", "capital", "financing",
                                           tags={ACQUISITION_CLEARING})
            books._consolidation_clearing_account = self.clearing
            goodwill_name = books.label("goodwill")
            self.goodwill = next((a for a in books._accounts
                                  if a.kind == "other_asset" and a.name == goodwill_name), None)
            if self.goodwill is None:
                self.goodwill = books._account(goodwill_name, "asset", "other_asset", "investing")
            capital_name = books.label("capital_surplus")
            self.capital_surplus = next((a for a in books._accounts
                                         if a.kind == "capital" and a.name == capital_name), None)
            if self.capital_surplus is None:
                self.capital_surplus = books._account(capital_name, "equity", "capital", "financing")
            if self.opening_events:
                self.capital_surplus.opening = _sum([event.opening.capital_surplus for event in self.opening_events],
                                                    books, "opening capital surplus")
            if self.opening_events:
                self.goodwill.opening = _sum([
                    _convert_currency(g.model, event.opening.goodwill, event.entity._currency,
                                      p._currency, "opening")
                    for event in self.opening_events
                ], books, "opening goodwill")

    def create_associate_investments(self):
        books = self.books
        for entity in self.associates:
            bs_kind = books.layout.bs_kind("other_asset")
            if bs_kind is None:
                raise ValueError(f"{books.layout.name} has no balance-sheet kind for investments in associates")
            name = f"{books.label('investments_in_associates')}: {entity.name}"
            investment = books._account(name, "asset", "other_asset", bs_kind.cf,
                                        tags={"equity_method_investment"})
            self.equity_investments[entity] = investment
            opening_event = next((event for event in self.opening_equity_events if event.entity is entity), None)
            if opening_event is not None:
                investment.opening = opening_event.opening.investment
            line = LineItem(name, books._balance(investment), books, "other_asset", investment)
            line.balance = line.expr
            if hasattr(books.bs, "other_asset"):
                books.bs.other_asset._items.append(line)

    def replay_postings(self):
        g, p, books = self.g, self.p, self.books
        # Parent postings are always in scope. Subsidiary postings follow their control intervals.
        for entity in self.replay_entities:
            for post in entity._postings:
                if entity is p and post in p._associate_dividend_receipts and \
                        (post.counterparty in self.associates or post.counterparty in self.subsidiaries):
                    events = g._ownership[post.counterparty]
                    equity_scope = _ownership_scope(events, "equity").mask(g.model)
                    cost_interval = _ownership_scope(events, "cost")
                    cost_scope = cost_interval.mask(g.model)
                    if post.counterparty in self.subsidiaries:
                        control_scope = self.scopes[post.counterparty].mask(g.model)
                        amount = post.amount * control_scope
                        income = self.account(post.credit)
                        child_equity = self.account(post.counterpart.debit if post.counterpart.debit.side == "equity"
                                                    else post.counterpart.credit)
                        books._post(post.name, amount, self.account(post.debit), income, cf="financing")
                        books._post(f"Eliminate {post.name}", amount, debit=income, credit=child_equity)
                    if post.counterparty in self.equity_investments:
                        books._post(f"{post.counterparty.name} dividend received", post.amount * equity_scope,
                                    self.account(post.debit), self.equity_investments[post.counterparty],
                                    cf="operating")
                    if cost_interval.intervals:
                        books._post(post.name, post.amount * cost_scope,
                                    self.account(post.debit), self.account(post.credit), cf="operating")
                        self.active_pl_accounts.add(self.account(post.credit))
                    continue
                if entity is p and post in self.control_sale_postings:
                    continue
                amount = _scoped_amount(g, entity, post, self.scopes)
                counterparty_scope = self.scopes.get(post.counterparty)
                has_external_period = counterparty_scope is None or any(
                    self.scopes[entity].contains(period) and not counterparty_scope.contains(period)
                    for period in range(len(g.model.timeline.periods)))
                has_external_period = has_external_period or post.fx_remeasurement
                if has_external_period:
                    if post.debit.cf == "pl":
                        self.active_pl_accounts.add(self.account(post.debit))
                    if post.credit.cf == "pl":
                        self.active_pl_accounts.add(self.account(post.credit))
                if post in entity._external_dividends and entity is not p:
                    debit = self.nci_accounts[entity]
                else:
                    debit = self.account(post.debit)
                cf = "financing" if any(event.kind == "purchase" and event.previous_method == "consolidate"
                                         and event.posting is post
                                        for events in self.subsidiaries.values() for event in events) else post.cf
                if post in self.acquired_capital_receipts:
                    cf = "investing"
                books._post(post.name, amount, debit, self.account(post.credit), cf=cf)
                if post.fx_remeasurement and post.net_investment and post.counterparty is not None:
                    self.net_investment_fx_posts.append((post.counterparty, self.account(post.credit), amount))

    def translate_foreign_members(self):
        g, p, books = self.g, self.p, self.books
        foreign_members = list(dict.fromkeys((*self.subsidiaries, *self.associates)))
        for entity in foreign_members:
            if entity._currency is None or p._currency is None or entity._currency == p._currency:
                continue
            cta_name = f"Foreign currency translation ({entity.name})"
            cta = books._account(cta_name, "equity", "oci", "financing")
            movements = []
            if entity in self.subsidiaries:
                for source in entity._accounts:
                    if source.side not in ("asset", "liability"):
                        continue
                    delta = _foreign_balance_delta(g, entity, source, self.scopes)
                    if source.side == "asset":
                        books._post(f"Translate {entity.name}: {source.name}", delta,
                                    debit=self.account(source), credit=cta,
                                    cf="fx" if source.kind == "cash" else None)
                        movements.append(delta)
                    else:
                        books._post(f"Translate {entity.name}: {source.name}", delta,
                                    debit=cta, credit=self.account(source))
                        movements.append(-delta)
            if entity in self.associates:
                associate_scope = {entity: _ownership_scope(g._ownership[entity], "equity")}
                net_asset_deltas = []
                for source in entity._accounts:
                    if source.side not in ("asset", "liability"):
                        continue
                    delta = _foreign_balance_delta(g, entity, source, associate_scope)
                    net_asset_deltas.append(delta if source.side == "asset" else -delta)
                movement = _sum(net_asset_deltas, books,
                                f"{entity.name}: foreign associate translation adjustment") \
                    * _share_series(g, g._ownership[entity])
                books._post(f"Translate foreign associate {entity.name}", movement,
                            debit=self.equity_investments[entity], credit=cta)
                movements.append(movement)
            self.cta_accounts[entity] = cta
            self.cta_parts[entity] = movements
            self.cta_parent_only_parts[entity] = []

        for entity, income, amount in self.net_investment_fx_posts:
            if entity not in self.cta_accounts:
                continue
            books._post(f"Reclassify {entity.name} net investment loan FX difference", amount,
                        debit=income, credit=self.cta_accounts[entity])
            self.cta_parts[entity].append(amount)

    def translate_intercompany_trades(self):
        g, p, books = self.g, self.p, self.books
        intercompany_trades = {trade for entity in self.replay_entities for trade in entity._intercompany_trades}
        for trade in intercompany_trades:
            if trade.seller not in self.scopes or trade.buyer not in self.scopes or \
                    _currency_dims(trade.seller._currency) == _currency_dims(trade.buyer._currency):
                continue
            translated_effects = []
            joint_scope = self.scopes[trade.seller].mask(g.model) * self.scopes[trade.buyer].mask(g.model)
            for post in trade._postings:
                amount = _convert_currency(g.model, post.amount * joint_scope,
                                           post.debit.entity._currency, p._currency)
                if post.debit.side in ("asset", "liability"):
                    translated_effects.append(amount)
                if post.credit.side in ("asset", "liability"):
                    translated_effects.append(-amount)
            difference = _sum(translated_effects, books, f"{trade.name}: intercompany translation difference")
            target = trade.seller if trade.seller in self.cta_accounts else trade.buyer
            if target not in self.cta_accounts:
                continue
            books._post(f"{trade.name}: intercompany FX translation difference", difference,
                        debit=books._cash_account, credit=self.cta_accounts[target], cf="fx")
            self.cta_parts[target].append(difference)

    def post_s6(self, name, amount, debit, credit, seller, *, translated=False):
        g, p, books = self.g, self.p, self.books
        translated = amount if translated else _convert_currency(g.model, amount, seller._currency, p._currency)
        books._post(name, translated, debit, credit)
        if debit.cf == "pl":
            self.s6_profit_adjustments.setdefault(seller, []).append(-translated)
            self.active_pl_accounts.add(debit)
        if credit.cf == "pl":
            self.s6_profit_adjustments.setdefault(seller, []).append(translated)
            self.active_pl_accounts.add(credit)

    def post_trade_tax(self, trade, remaining):
        g, p, books = self.g, self.p, self.books
        standard = books.standard.name
        if standard == "J-GAAP":
            tax_entity = trade.seller
        elif standard == "US GAAP" and trade.asset_kind == "inventory":
            tax_entity = trade.seller
        else:
            tax_entity = trade.buyer
        rate = tax_entity._tax_rate(None, f"intercompany asset tax for {trade.name!r}")
        remaining = _convert_currency(g.model, remaining, trade.seller._currency, p._currency, "closing")
        tax_name = f"Unrealized profit: {trade.seller.name} to {trade.buyer.name}: {trade.name}"
        tax_expense = books._deferred_tax_line()
        if standard == "US GAAP" and trade.asset_kind == "inventory":
            prepaid = books._account(f"Prepaid income taxes: {trade.name}", "asset", "prepaid_tax",
                                     "operating", category=tax_name)
            target = rate * smax(remaining, 0)
            change = target - target.lag(1, fill=0)
            books._post(f"{tax_name} prepaid income tax", -change, debit=tax_expense, credit=prepaid)
            books._deferred_tax_movements.append(-change)
            self.s6_profit_adjustments.setdefault(trade.seller, []).append(change)
            return
        asset, liability, asset_change, liability_change = books._tax_accounts(
            tax_name, -remaining, rate, lift(1), "operating")
        books._deferred_tax_names.add(tax_name)
        books._post(f"{tax_name} deferred tax asset", -asset_change, debit=tax_expense, credit=asset)
        books._post(f"{tax_name} deferred tax liability", liability_change,
                    debit=tax_expense, credit=liability)
        books._deferred_tax_movements.append(liability_change - asset_change)
        self.s6_profit_adjustments.setdefault(trade.seller, []).append(asset_change - liability_change)

    def eliminate_opening_unrealized(self):
        g, books = self.g, self.books
        opening_retained_earnings_adjustments = []
        for trade, specification in self.opening_unrealized.items():
            buyer_asset = self.account(trade.buyer_item.account)
            buyer_asset.opening = (buyer_asset.opening if buyer_asset.opening is not None else lift(0)) \
                - specification.amount
            standard = books.standard.name
            tax_entity = trade.seller if standard == "J-GAAP" or \
                (standard == "US GAAP" and trade.asset_kind == "inventory") else trade.buyer
            rate = tax_entity._tax_rate(None, f"intercompany asset tax for {trade.name!r}")
            opening_tax_effect = lift(0)
            tax_name = f"Unrealized profit: {trade.seller.name} to {trade.buyer.name}: {trade.name}"
            tax_expense = books._deferred_tax_line()
            if standard == "US GAAP" and trade.asset_kind == "inventory":
                prepaid = books._account(f"Prepaid income taxes: {trade.name}", "asset", "prepaid_tax",
                                         "operating", category=tax_name)
                opening_tax_effect = rate * smax(specification.amount, 0)
                prepaid.opening = opening_tax_effect
                remaining = g._s6_trade_states[trade]["unrealized"]
                target = rate * smax(remaining, 0)
                change = target - target.lag(1, fill=opening_tax_effect)
                books._post(f"{tax_name} prepaid income tax", -change, debit=tax_expense, credit=prepaid)
                books._deferred_tax_movements.append(-change)
                self.s6_profit_adjustments.setdefault(trade.seller, []).append(change)
            else:
                asset, liability, _, _ = books._tax_accounts(tax_name, -specification.amount, rate, lift(1),
                                                             "operating")
                books._deferred_tax_names.add(tax_name)
                opening_asset = rate * smax(specification.amount, 0)
                opening_liability = rate * smax(-specification.amount, 0)
                asset.opening, liability.opening = opening_asset, opening_liability
                opening_tax_effect = opening_asset - opening_liability
                remaining = g._s6_trade_states[trade]["unrealized"]
                asset_balance = rate * smax(remaining, 0)
                liability_balance = rate * smax(-remaining, 0)
                asset_change = asset_balance - asset_balance.lag(1, fill=opening_asset)
                liability_change = liability_balance - liability_balance.lag(1, fill=opening_liability)
                books._post(f"{tax_name} deferred tax asset", -asset_change, debit=tax_expense, credit=asset)
                books._post(f"{tax_name} deferred tax liability", liability_change,
                            debit=tax_expense, credit=liability)
                books._deferred_tax_movements.append(liability_change - asset_change)
                self.s6_profit_adjustments.setdefault(trade.seller, []).append(asset_change - liability_change)
            opening_retained_earnings_adjustments.append(-specification.amount + opening_tax_effect)
        if opening_retained_earnings_adjustments:
            books.retained_earnings.opening = books.retained_earnings.opening + _sum(
                opening_retained_earnings_adjustments, books, "opening unrealized profit elimination")

    def eliminate_intercompany_trades(self):
        g, p, books = self.g, self.p, self.books
        for trade, state in g._s6_trade_states.items():
            seller, buyer = trade.seller, trade.buyer
            fully_consolidated = seller in self.scopes and buyer in self.scopes
            downstream_associate = seller in self.scopes and buyer in self.associates
            upstream_associate = seller in self.associates and buyer in self.scopes
            if not (fully_consolidated or downstream_associate or upstream_associate):
                continue
            price = trade.price * state["share"]
            seller_price = _convert_currency(g.model, price, seller._currency, p._currency)
            buyer_price = _convert_currency(g.model, trade.buyer_price * state["share"],
                                            buyer._currency, p._currency)
            profit = state["initial"]
            realized = state["realized"]

            if fully_consolidated:
                buyer_asset = self.account(trade.buyer_item.account)
                if trade.source == "disposal":
                    seller_asset = self.account(trade.seller_asset)
                    gain_account, loss_account = self.account(trade.gain_account), self.account(trade.loss_account)
                    gain, loss = smax(profit, 0), smax(-profit, 0)
                    self.post_s6(f"Transfer {trade.name} to {buyer.name}", buyer_price,
                                 buyer_asset, seller_asset, seller, translated=True)
                    self.post_s6(f"Recognize {trade.name} disposal gain", gain, seller_asset, gain_account, seller)
                    self.post_s6(f"Recognize {trade.name} disposal loss", loss, loss_account, seller_asset, seller)
                    initial_gain, initial_loss = gain, loss
                    profit_account = gain_account
                    loss_profit_account = loss_account
                else:
                    cogs = _group_pl_account(books, books.label("cogs"), "cogs")
                    self.active_pl_accounts.add(cogs)
                    self.post_s6(f"Transfer {trade.name} at transaction price", buyer_price,
                                 buyer_asset, cogs, seller, translated=True)
                    initial_gain, initial_loss = smax(profit, 0), smax(-profit, 0)
                    profit_account = loss_profit_account = cogs

                currency_difference = seller_price - buyer_price
                cta_entity = seller if seller in self.cta_accounts else buyer
                if currency_difference.unit is not None and cta_entity in self.cta_accounts:
                    books._post(f"{trade.name}: cross-currency elimination difference", currency_difference,
                                debit=buyer_asset, credit=self.cta_accounts[cta_entity])
                    self.cta_parts[cta_entity].append(currency_difference)

                self.post_s6(f"Eliminate {trade.name} unrealized gain", initial_gain,
                             profit_account, buyer_asset, seller)
                self.post_s6(f"Eliminate {trade.name} unrealized loss", initial_loss,
                             buyer_asset, loss_profit_account, seller)
                if trade.asset_kind == "inventory":
                    cogs = _group_pl_account(books, books.label("cogs"), "cogs")
                    self.active_pl_accounts.add(cogs)
                    self.post_s6(f"Realize {trade.name} profit as consumed", realized, buyer_asset, cogs, seller)
                else:
                    depreciation = self.account(trade.buyer_item.depreciation.account)
                    self.post_s6(f"Realize {trade.name} profit through depreciation", realized,
                                 buyer_asset, depreciation, seller)
            elif downstream_associate:
                investment = self.equity_investments[buyer]
                profit_account = self.account(trade.gain_account) if trade.source == "disposal" else \
                    _group_pl_account(books, books.label("cogs"), "cogs")
                if trade.source != "disposal":
                    self.active_pl_accounts.add(profit_account)
                self.post_s6(f"Eliminate investor share of {trade.name} profit", profit,
                             profit_account, investment, seller)
                self.post_s6(f"Realize investor share of {trade.name} profit", realized,
                             investment, profit_account, seller)
            else:
                income_kind = "non_operating_income" if books.standard.name == "J-GAAP" else "other_income"
                income = _group_pl_account(books, books.label("equity_method_income"), income_kind, "income")
                income.tags = income.tags | {"equity_method_presentation"}
                self.active_pl_accounts.add(income)
                buyer_asset = self.account(trade.buyer_item.account)
                amount_factor = lift(1)
                if books.standard.name == "J-GAAP":
                    seller_rate = seller._tax_rate(None, f"equity-method upstream tax for {trade.name!r}")
                    amount_factor = 1 - seller_rate
                self.post_s6(f"Eliminate investor share of {trade.name} profit", profit * amount_factor,
                             income, buyer_asset, seller)
                self.post_s6(f"Realize investor share of {trade.name} profit", realized * amount_factor,
                             buyer_asset, income, seller)

            if not (upstream_associate and books.standard.name == "J-GAAP"):
                if trade not in self.opening_unrealized:
                    self.post_trade_tax(trade, state["unrealized"])

    def book_acquisitions(self):
        g, p, books = self.g, self.p, self.books
        acquisitions: dict[int, list[OwnershipEvent]] = {}
        for events in self.subsidiaries.values():
            for event in events:
                if event.kind in ("acquisition", "step") and event.method == "consolidate":
                    acquisitions.setdefault(event.period, []).append(event)
        # Import each acquired subsidiary's opening assets and liabilities at the start of its first period.
        for period, events in sorted(acquisitions.items()):
            new_entities = {event.entity for event in events}
            for event in events:
                entity = event.entity
                for source in entity._accounts:
                    if source.side not in ("asset", "liability"):
                        continue
                    opening = _at_period(entity._balance(source).opening, period, g)
                    if entity._currency is not None and p._currency is not None:
                        opening = _convert_currency(g.model, opening, entity._currency, p._currency, "acquisition")
                    target = self.account(source)
                    if source.side == "asset":
                        books._post(f"{entity.name} acquired: {source.name}", opening,
                                    debit=target, credit=self.clearing,
                                    cf="investing" if source is entity._cash_account else None)
                    else:
                        books._post(f"{entity.name} acquired: {source.name}", opening,
                                    debit=self.clearing, credit=target)

            # Clear tagged balance-sheet amounts that were outside the group before this acquisition.
            for entity in self.replay_entities:
                for source in entity._accounts:
                    if source.side not in ("asset", "liability"):
                        continue
                    if source.kind == "cash" or (source.kind == "other_asset" and SUBSIDIARY_INVESTMENT in source.tags):
                        continue
                    internal = _tagged_opening(g, entity, source, period, self.scopes, new_entities)
                    if source.side == "asset":
                        books._post(f"Eliminate acquired balance: {source.name}", internal,
                                    debit=self.clearing, credit=self.account(source))
                    else:
                        books._post(f"Eliminate acquired balance: {source.name}", internal,
                                    debit=self.account(source), credit=self.clearing)

            for event in events:
                self.book_acquisition(event, period)

    def book_acquisition(self, event: OwnershipEvent, period: int):
        g, p, books = self.g, self.p, self.books
        entity = event.entity
        opening_net_assets = _net_assets(g, entity, period, self.scopes)
        adjustments, deferred_tax, adjustment_profit = _book_acquisition_adjustments(
            g, books, event, self.clearing, self.mapped, self.active_pl_accounts)
        net_assets = opening_net_assets + event.acquisition_contribution + adjustments - deferred_tax
        terms = event.acquisition
        if terms is None:
            raise RuntimeError(f"{entity.name}: acquisition terms were not prepared")
        if terms.nci == "fair_value":
            nci_at_acquisition = terms.nci_value if terms.nci_value is not None else lift(0)
        else:
            nci_at_acquisition = net_assets * (1 - event.share)
        self.acquisition_nci[event] = nci_at_acquisition
        self.acquisition_profit_adjustments.setdefault(entity, []).append(adjustment_profit)
        previous_value = event.previously_held_value if event.previously_held_value is not None else lift(0)
        investment_cost = event.investment_cost + previous_value
        previous_investment = None
        previous_carrying = lift(0)
        if event.kind == "step":
            if event.previous_method == "equity":
                previous_investment = self.equity_investments[entity]
            else:
                previous_investment = self.account(event.investment)
            previous_carrying = books._balance(previous_investment).opening * (g.model.t == period)
            remeasurement = previous_value - previous_carrying
            fvoci_components = []
            if books.standard.name == "IFRS" and event.previous_method == "cost":
                for component in p._oci_components.values():
                    if component.recycle:
                        continue
                    amounts = [post.amount for post in p._postings
                               if post.debit is event.investment and post.credit is component.account]
                    if not amounts:
                        continue
                    accumulated = _sum(amounts, p, f"{entity.name}: {component.name} FVOCI reserve") \
                        .cumsum().lag(1, fill=0) * (g.model.t == period)
                    fvoci_components.append((component, accumulated))
            if fvoci_components:
                first_component = fvoci_components[0][0]
                first_target = self.account(first_component.account)
                books._post(f"Remeasure {entity.name} previously held FVOCI interest",
                            smax(remeasurement, 0), debit=previous_investment, credit=first_target)
                books._post(f"Remeasure {entity.name} previously held FVOCI interest",
                            smax(-remeasurement, 0), debit=first_target, credit=previous_investment)
                for index, (component, accumulated) in enumerate(fvoci_components):
                    release = accumulated + (remeasurement if index == 0 else lift(0))
                    books._post(f"Transfer {component.name} to retained earnings",
                                release, debit=self.account(component.account), credit=books.retained_earnings)
                gain_amount = lift(0)
            else:
                gain_amount = remeasurement
            step_gain = _step_acquisition_account(books)
            self.active_pl_accounts.add(step_gain)
            books._post(f"Remeasure {entity.name} previously held interest", smax(gain_amount, 0),
                        debit=previous_investment, credit=step_gain)
            books._post(f"Remeasure {entity.name} previously held interest", smax(-gain_amount, 0),
                        debit=step_gain, credit=previous_investment)
        base_credit = opening_net_assets + adjustments - deferred_tax
        if event.kind == "step" and event.previous_method == "equity":
            books._post(f"Eliminate {entity.name} shares", event.investment_cost,
                        debit=self.clearing, credit=self.account(event.investment))
            books._post(f"Eliminate {entity.name} previously held equity investment", base_credit - event.investment_cost,
                        debit=self.clearing, credit=previous_investment)
        else:
            books._post(f"Eliminate {entity.name} shares", base_credit,
                        debit=self.clearing, credit=self.account(event.investment))
        for post in event.paired_postings:
            if post.debit.entity is entity:
                contribution = post.amount * (g.model.t == period)
                books._post(f"Eliminate {entity.name} capital contribution", contribution,
                            debit=self.account(post.credit), credit=self.account(event.investment))
        books._post(f"Recognize {entity.name} noncontrolling interests", nci_at_acquisition,
                    debit=self.goodwill, credit=self.nci_accounts[entity])
        books._post(f"Recognize {entity.name} goodwill", investment_cost - net_assets,
                    debit=self.goodwill,
                    credit=previous_investment if event.kind == "step" and event.previous_method == "equity"
                    else self.account(event.investment))
        recognized_goodwill = investment_cost + nci_at_acquisition - net_assets
        bargain_amount = smax(-recognized_goodwill, 0)
        if entity.standard.name == "J-GAAP":
            gain_kind = "special_gain"
        else:
            gain_kind = "other_income"
        bargain_gain = _group_pl_account(books, books.label("bargain_purchase_gain"), gain_kind, "income")
        self.active_pl_accounts.add(bargain_gain)
        books._post(f"{entity.name} gain on bargain purchase", bargain_amount,
                    debit=self.goodwill, credit=bargain_gain)

        positive_goodwill = smax(recognized_goodwill, 0)
        impairment = terms.impairment if terms.impairment is not None else positive_goodwill * 0
        control_mask = _control_event_mask(g, event)
        foreign = _currency_dims(entity._currency) != _currency_dims(p._currency)
        native_origin = None
        if foreign:
            native_origin = _convert_currency(g.model, positive_goodwill, p._currency, entity._currency,
                                              "acquisition")
            native_impairment = terms.impairment if terms.impairment is not None else native_origin * 0
            native_controlled_impairment = native_impairment * control_mask
            controlled_impairment = _convert_currency(
                g.model, native_controlled_impairment, entity._currency, p._currency)
        else:
            native_controlled_impairment = None
            controlled_impairment = impairment * control_mask
        reductions = [controlled_impairment]
        native_reductions = [native_controlled_impairment] if foreign else []
        if terms.goodwill_life is not None:
            if foreign:
                native_amortization = _GoodwillAmortization(
                    g.model, native_origin, native_impairment, event.period, terms.goodwill_life) * control_mask
                amortization = _convert_currency(g.model, native_amortization, entity._currency, p._currency)
                native_reductions.append(native_amortization)
            else:
                amortization = _GoodwillAmortization(
                    g.model, positive_goodwill, impairment, event.period, terms.goodwill_life) * control_mask
            reductions.append(amortization)
            amort_kind = "sga" if "sga" in books.layout.pl_kinds else books.layout.depreciation_kind
            amort_account = _group_pl_account(books, books.label("goodwill_amortization"), amort_kind)
            amort_account.tags = amort_account.tags | {AMORTIZATION}
            self.active_pl_accounts.add(amort_account)
            books._post(f"{entity.name} goodwill amortization", amortization,
                        debit=amort_account, credit=self.goodwill)
        if terms.impairment is not None:
            impairment_kind = "special_loss" if entity.standard.name == "J-GAAP" else \
                ("sga" if "sga" in books.layout.pl_kinds else books.layout.depreciation_kind)
            impairment_account = _group_pl_account(
                books, books.label("goodwill_impairment"), impairment_kind)
            self.active_pl_accounts.add(impairment_account)
            books._post(f"{entity.name} goodwill impairment", controlled_impairment,
                        debit=impairment_account, credit=self.goodwill)
            if terms.nci == "fair_value":
                self.full_goodwill_impairments.setdefault(entity, []).append(
                    controlled_impairment * (1 - event.share))
        self.goodwill_schedules[event] = (positive_goodwill, reductions)
        if foreign:
            self.foreign_goodwill_schedules[event] = (native_origin, native_reductions)

    def book_opening_acquisition_adjustments(self):
        g, p, books = self.g, self.p, self.books
        for event in self.opening_events:
            terms = event.opening
            entity = event.entity
            foreign = _currency_dims(entity._currency) != _currency_dims(p._currency)
            tax_name = f"{event.entity.name}: opening acquisition items"
            tax_liability = books._tax_account(tax_name, "deferred_tax_liability", "liability", "operating") \
                if terms.deferred_tax_shares else None
            tax_asset = books._tax_account(tax_name, "deferred_tax_asset", "asset", "operating") \
                if terms.deferred_tax_shares else None
            if terms.deferred_tax_shares:
                liability_opening = _sum([smax(share, 0) for share in terms.deferred_tax_shares],
                                         entity, f"{event.entity.name}: native opening deferred tax liabilities")
                asset_opening = _sum([smax(-share, 0) for share in terms.deferred_tax_shares],
                                     entity, f"{event.entity.name}: native opening deferred tax assets")
                tax_liability.opening = _convert_currency(g.model, liability_opening, entity._currency,
                                                           p._currency, "opening") if foreign else liability_opening
                tax_asset.opening = _convert_currency(g.model, asset_opening, entity._currency,
                                                       p._currency, "opening") if foreign else asset_opening
                tax_expense = books._deferred_tax_line()
            else:
                tax_expense = None

            profit_parts = []
            control_mask = _control_event_mask(g, event)
            for index, adjustment in enumerate(terms.fair_value):
                if adjustment.source is not None:
                    target = self.account(adjustment.source)
                    opening_adjustment = adjustment.value if adjustment.side == "asset" else -adjustment.value
                    if foreign:
                        opening_adjustment = _convert_currency(
                            g.model, opening_adjustment, entity._currency, p._currency, "opening")
                    target.opening = (target.opening if target.opening is not None else lift(0)) + opening_adjustment
                    targets = {adjustment.side: target}
                    origins = {adjustment.side: adjustment.value if adjustment.side == "asset" else -adjustment.value}
                else:
                    targets = {}
                    origins = {}
                    for side in ("asset", "liability"):
                        kind = "intangible" if side == "asset" else "other_liability"
                        bs_kind = books.layout.bs_kind(kind)
                        if bs_kind is None and side == "asset":
                            kind, bs_kind = "other_asset", books.layout.bs_kind("other_asset")
                        if bs_kind is None:
                            raise ValueError(f"{books.layout.name} has no balance-sheet kind for acquired {side}s")
                        target = next((account for account in books._accounts
                                       if account.name == adjustment.name and account.kind == kind), None)
                        if target is None:
                            target = books._account(adjustment.name, side, kind, bs_kind.cf)
                        amount = smax(adjustment.value, 0) if side == "asset" else smax(-adjustment.value, 0)
                        opening_amount = _convert_currency(
                            g.model, amount, entity._currency, p._currency, "opening") if foreign else amount
                        target.opening = (target.opening if target.opening is not None else lift(0)) + opening_amount
                        targets[side] = target
                        origins[side] = amount

                amortization_native = _adjustment_amortization(g, event, adjustment) * control_mask
                amortization = _convert_currency(g.model, amortization_native, entity._currency,
                                                 p._currency) if foreign else amortization_native
                if adjustment.remaining_life is not None:
                    amort_account = _adjustment_amortization_account(books, self.active_pl_accounts)
                    if adjustment.side == "dynamic":
                        asset_amortization_native = _adjustment_amortization(
                            g, event, adjustment, smax(adjustment.value, 0)) * control_mask
                        liability_amortization_native = _adjustment_amortization(
                            g, event, adjustment, -smax(-adjustment.value, 0)) * control_mask
                        asset_amortization = _convert_currency(
                            g.model, asset_amortization_native, entity._currency, p._currency) \
                            if foreign else asset_amortization_native
                        liability_amortization = _convert_currency(
                            g.model, liability_amortization_native, entity._currency, p._currency) \
                            if foreign else liability_amortization_native
                        _post_unwind(books, f"{event.entity.name} opening acquisition adjustment amortization: "
                                    f"{adjustment.name} (asset)", -asset_amortization, amort_account, targets["asset"])
                        _post_unwind(books, f"{event.entity.name} opening acquisition adjustment amortization: "
                                    f"{adjustment.name} (liability)", -liability_amortization, amort_account, targets["liability"])
                        amortization = asset_amortization + liability_amortization
                    else:
                        _post_unwind(books, f"{event.entity.name} opening acquisition adjustment amortization: "
                                    f"{adjustment.name}", -amortization, amort_account, targets[adjustment.side])

                if foreign:
                    schedules = getattr(books, "_foreign_adjustment_schedules", [])
                    if adjustment.side == "dynamic":
                        if adjustment.remaining_life is not None:
                            asset_movement = asset_amortization_native
                            liability_movement = -liability_amortization_native
                        else:
                            asset_movement = adjustment.value * 0
                            liability_movement = adjustment.value * 0
                        schedules.extend(((entity, targets["asset"], "asset", origins["asset"],
                                           asset_movement, event, origins["asset"]),
                                          (entity, targets["liability"], "liability", origins["liability"],
                                           liability_movement, event, origins["liability"])))
                    else:
                        side = adjustment.side
                        movement = amortization_native if side == "asset" else -amortization_native
                        schedules.append((entity, targets[side], side, origins[side],
                                          movement, event, origins[side]))
                    books._foreign_adjustment_schedules = schedules

                tax_change = lift(0)
                if tax_expense is not None:
                    fraction = _opening_amortization_fraction(g, adjustment.remaining_life) * control_mask \
                        if adjustment.remaining_life is not None else lift(0)
                    share = terms.deferred_tax_shares[index]
                    liability_origin = smax(share, 0)
                    asset_origin = smax(-share, 0)
                    liability_change_native = -liability_origin * fraction
                    asset_change_native = -asset_origin * fraction
                    liability_change = _convert_currency(
                        g.model, liability_change_native, entity._currency, p._currency) \
                        if foreign else liability_change_native
                    asset_change = _convert_currency(
                        g.model, asset_change_native, entity._currency, p._currency) \
                        if foreign else asset_change_native
                    books._post(f"{tax_name} deferred tax liability unwind", liability_change,
                                debit=tax_expense, credit=tax_liability)
                    books._post(f"{tax_name} deferred tax asset unwind", asset_change,
                                debit=tax_expense, credit=tax_asset)
                    tax_change = liability_change + asset_change
                    books._deferred_tax_movements.append(tax_change)
                    if foreign:
                        schedules = getattr(books, "_foreign_adjustment_schedules", [])
                        schedules.extend(((entity, tax_liability, "liability", liability_origin,
                                           liability_change_native, event, liability_origin),
                                          (entity, tax_asset, "asset", asset_origin,
                                           asset_change_native, event, asset_origin)))
                        books._foreign_adjustment_schedules = schedules
                profit_parts.append(amortization - tax_change)
            if profit_parts:
                self.acquisition_profit_adjustments.setdefault(event.entity, []).append(
                    _sum(profit_parts, books, f"{event.entity.name}: opening acquisition profit adjustments"))

    def book_opening_goodwill(self):
        g, p, books = self.g, self.p, self.books
        for event in self.opening_events:
            terms = event.opening
            reductions = []
            foreign = _currency_dims(event.entity._currency) != _currency_dims(p._currency)
            if foreign:
                native_origin = terms.goodwill * (g.model.t == 0)
                native_reductions = []
            if terms.goodwill_life is not None:
                if foreign:
                    native_amortization = _GoodwillAmortization(
                        g.model, terms.goodwill, lift(0), 0, terms.goodwill_life) * _control_event_mask(g, event)
                    amortization = _convert_currency(g.model, native_amortization,
                                                      event.entity._currency, p._currency)
                    native_reductions.append(native_amortization)
                else:
                    amortization = _GoodwillAmortization(g.model, terms.goodwill, lift(0), 0,
                                                         terms.goodwill_life) * _control_event_mask(g, event)
                amort_kind = "sga" if "sga" in books.layout.pl_kinds else books.layout.depreciation_kind
                amort_account = _group_pl_account(books, books.label("goodwill_amortization"), amort_kind)
                amort_account.tags = amort_account.tags | {AMORTIZATION}
                self.active_pl_accounts.add(amort_account)
                books._post(f"{event.entity.name} goodwill amortization", amortization,
                            debit=amort_account, credit=self.goodwill)
                reductions.append(amortization)
            self.goodwill_schedules[event] = (terms.goodwill, reductions)
            if foreign:
                self.foreign_goodwill_schedules[event] = (native_origin, native_reductions)

    def translate_goodwill(self):
        g, p, books = self.g, self.p, self.books
        for entity in self.subsidiaries:
            if entity not in self.cta_accounts or not any(event.entity is entity
                                                    for event in self.foreign_goodwill_schedules):
                continue
            translation_parts = []
            parent_only_parts = []
            for event, (origin, reductions) in self.foreign_goodwill_schedules.items():
                if event.entity is not entity:
                    continue
                native_reduction = _sum(reductions, entity, f"{entity.name}: goodwill reductions")
                active_scope = self.scopes[entity].mask(g.model)
                native_closing = (origin.cumsum() - native_reduction.cumsum()) * active_scope
                desired = _convert_currency(g.model, native_closing, entity._currency, p._currency, "closing")
                opening = _convert_currency(g.model, event.opening.goodwill, entity._currency,
                                            p._currency, "opening") if event.kind == "opening" else 0
                prior = desired.lag(1, fill=opening)
                translated_movement = -_convert_currency(g.model, native_reduction,
                                                         entity._currency, p._currency)
                if event.kind != "opening":
                    translated_movement += _convert_currency(
                        g.model, origin, entity._currency, p._currency, "acquisition")
                event_delta = (desired - prior - translated_movement) * active_scope
                translation_parts.append(event_delta)
                terms = event.acquisition
                if event.kind != "opening" and isinstance(terms, AcquisitionTerms) and terms.nci == "proportionate":
                    parent_only_parts.append(event_delta)
            delta = _sum(translation_parts, books, f"{entity.name}: goodwill translation adjustment")
            books._post(f"Translate {entity.name} goodwill", delta,
                        debit=self.goodwill, credit=self.cta_accounts[entity])
            self.cta_parts[entity].append(delta)
            if parent_only_parts:
                self.cta_parent_only_parts[entity].append(
                    (delta * 0) + _sum(parent_only_parts, books, f"{entity.name}: parent-only goodwill translation"))

    def translate_acquisition_adjustments(self):
        g, p, books = self.g, self.p, self.books
        for entity, target, side, origin, movement, event, opening_balance in \
                getattr(books, "_foreign_adjustment_schedules", []):
            if entity not in self.cta_accounts:
                continue
            active_scope = self.scopes[entity].mask(g.model)
            native_closing = (origin.cumsum() + movement.cumsum()) * active_scope
            desired = _convert_currency(g.model, native_closing, entity._currency, p._currency, "closing")
            translated_opening = _convert_currency(g.model, opening_balance, entity._currency,
                                                    p._currency, "opening") if opening_balance is not False else 0
            prior = desired.lag(1, fill=translated_opening)
            translated_movement = _convert_currency(g.model, movement, entity._currency, p._currency)
            if opening_balance is False:
                translated_movement += _convert_currency(
                    g.model, origin, entity._currency, p._currency, "acquisition")
            delta = (desired - prior - translated_movement) * active_scope
            if side == "asset":
                books._post(f"Translate {entity.name} acquired {target.name}", delta,
                            debit=target, credit=self.cta_accounts[entity])
                self.cta_parts[entity].append(delta)
            else:
                books._post(f"Translate {entity.name} acquired {target.name}", delta,
                            debit=self.cta_accounts[entity], credit=target)
                self.cta_parts[entity].append(-delta)

    def active_goodwill(self, entity: Entity, period: int) -> Series:
        g, p, books = self.g, self.p, self.books
        events = g._ownership[entity]
        last_loss = max((event.period for event in events if event.kind == "loss" and event.period < period),
                        default=-1)
        parts = []
        for event, (origin, reductions) in self.goodwill_schedules.items():
            if event.entity is not entity or event.period <= last_loss or event.period >= period:
                continue
            if event in self.foreign_goodwill_schedules:
                native_origin, native_reductions = self.foreign_goodwill_schedules[event]
                native_closing = native_origin.cumsum()
                if native_reductions:
                    native_closing -= _sum(native_reductions, entity,
                                           f"{entity.name}: native goodwill reductions").cumsum()
                translated_closing = _convert_currency(g.model, native_closing, entity._currency,
                                                        p._currency, "closing")
                opening = _convert_currency(g.model, event.opening.goodwill, entity._currency,
                                             p._currency, "opening") if event.kind == "opening" else 0
                remaining = translated_closing.lag(1, fill=opening)
            else:
                remaining = origin if event.kind == "opening" and period == 0 else origin.cumsum().lag(1, fill=0)
                if reductions:
                    remaining -= _sum(reductions, books, f"{entity.name}: goodwill reductions").cumsum().lag(1, fill=0)
            parts.append(remaining)
        return _sum(parts, books, f"{entity.name}: goodwill before period {period}") * (g.model.t == period)

    def acquisition_adjustments_at_open(
            self, entity: Entity, period: int
    ) -> tuple[Series, list[tuple[OwnershipEvent, AcquisitionAdjustment, Series]]]:
        g, books = self.g, self.books
        events = g._ownership[entity]
        last_loss = max((event.period for event in events if event.kind == "loss" and event.period < period),
                        default=-1)
        parts = []
        adjustment_values = []
        for event in events:
            if event.method != "consolidate" or event.kind not in ("acquisition", "step") or \
                    event.period <= last_loss or event.period >= period or not isinstance(event.acquisition, AcquisitionTerms):
                continue
            terms = event.acquisition
            for adjustment in terms.adjustments:
                amortization = _adjustment_amortization(g, event, adjustment)
                remaining = (adjustment.value.cumsum() + amortization.cumsum()).lag(1, fill=0) * \
                    (g.model.t == period)
                parts.append(remaining if terms.tax_rate is None else remaining * (1 - terms.tax_rate))
                adjustment_values.append((event, adjustment, remaining))
        return _sum(parts, books, f"{entity.name}: acquisition adjustments at period {period}"), adjustment_values

    def book_ownership_changes(self):
        g, books = self.g, self.books
        # Purchases and sales while control continues are equity transactions, not gains or losses.
        for events in self.subsidiaries.values():
            for event in events:
                if event.method != "consolidate" or event.previous_method != "consolidate" or \
                        event.kind not in ("purchase", "sale"):
                    continue
                net_assets = _net_assets(g, event.entity, event.period, self.scopes,
                                         membership_period=event.period - 1)
                if event.kind == "purchase":
                    nci_change = -(event.share - event.previous_share) * net_assets
                    investment_cost = event.investment_cost
                    capital_change = -investment_cost - nci_change
                    books._post(f"Eliminate {event.entity.name} shares purchase", investment_cost,
                                debit=self.clearing, credit=self.account(event.investment))
                    books._post(f"Change noncontrolling interests: {event.entity.name}", nci_change,
                                debit=self.clearing, credit=self.nci_accounts[event.entity])
                    books._post(f"Change capital surplus: {event.entity.name}", capital_change,
                                debit=self.clearing, credit=self.capital_surplus)
                else:
                    nci_change = (event.previous_share - event.share) * net_assets
                    proceeds = event.proceeds if event.proceeds is not None else lift(0)
                    capital_change = proceeds - nci_change
                    books._post(f"Proceeds from sale of {event.entity.name} shares while controlled", proceeds,
                                debit=books._cash_account, credit=self.clearing, cf="financing")
                    books._post(f"Change noncontrolling interests: {event.entity.name}", nci_change,
                                debit=self.clearing, credit=self.nci_accounts[event.entity])
                    books._post(f"Change capital surplus: {event.entity.name}", capital_change,
                                debit=self.clearing, credit=self.capital_surplus)
                self.cap_changes.append(capital_change)

    def transfer_opening_oci(self):
        g, books = self.g, self.books
        for entity, events in self.subsidiaries.items():
            for event in events:
                if event.previous_method != "consolidate" or event.kind not in ("purchase", "sale"):
                    continue
                for key, parent_opening in self.opening_oci_parent.items():
                    if key[0] is not entity:
                        continue
                    name = key[1]
                    nci_opening = self.opening_oci_nci[key]
                    release = _member_oci_release(g, entity, self.account(self.opening_oci_source[key]), self.scopes) \
                        if self.opening_oci_source[key] is not None else lift(0)
                    parent_balance = _OpeningOciBalance(parent_opening, nci_opening, release, events,
                                                        nci=False, apply_current_transfer=False)
                    nci_balance = _OpeningOciBalance(parent_opening, nci_opening, release, events,
                                                     nci=True, apply_current_transfer=False)
                    if event.kind == "purchase" and event.previous_share < 1:
                        transfer = nci_balance * ((event.share - event.previous_share) / (1 - event.previous_share))
                    else:
                        transfer = -parent_balance * ((event.previous_share - event.share) / event.previous_share)
                    transfer *= g.model.t == event.period
                    source = self.opening_oci_source[key]
                    if source is not None:
                        target = self.account(source)
                    else:
                        target = next((account for account in books._accounts
                                       if account.side == "equity" and account.kind == "oci" and
                                       account.name == name), None)
                        if target is None:
                            target = books._account(name, "equity", "oci", "financing")
                    books._post(f"Transfer {entity.name} opening {name} OCI to parent", smax(transfer, 0),
                                debit=self.capital_surplus, credit=target)
                    books._post(f"Transfer {entity.name} opening {name} OCI to NCI", smax(-transfer, 0),
                                debit=target, credit=self.capital_surplus)
                    self.opening_oci_transfers.setdefault(key, []).append(transfer)

    def book_loss_of_control(self):
        # Losing control removes the subsidiary at the start of the event period.
        for event in self.control_sale_events:
            if event.kind != "loss":
                continue
            self.lose_control(event)

    def lose_control(self, event: OwnershipEvent):
        g, books = self.g, self.books
        entity, period = event.entity, event.period
        raw_net_assets = _net_assets(g, entity, period, self.scopes, membership_period=period - 1)
        adjustment_net_assets, adjustment_values = self.acquisition_adjustments_at_open(entity, period)
        net_assets = raw_net_assets + adjustment_net_assets
        full_goodwill = self.active_goodwill(entity, period)
        nci_opening = books._balance(self.nci_accounts[entity]).opening * (g.model.t == period)
        proceeds = event.proceeds if event.proceeds is not None else lift(0)
        retained_share = event.share
        sold_share = event.previous_share - retained_share
        if entity.standard.name == "J-GAAP":
            sold_fraction = sold_share / event.previous_share
            retained_fraction = retained_share / event.previous_share
            sold_goodwill = full_goodwill * sold_fraction
            retained_goodwill = full_goodwill * retained_fraction
            sold_carrying = sold_share * net_assets + sold_goodwill
            gain = proceeds - sold_carrying
            if event.method == "equity" and retained_share > 0:
                retained_amount = retained_share * net_assets + retained_goodwill
            elif event.method == "cost" and retained_share > 0:
                retained_amount = event.investment_end
            else:
                retained_amount = lift(0)
        else:
            sold_goodwill = full_goodwill
            retained_goodwill = lift(0)
            retained_amount = event.retained_value if event.retained_value is not None else lift(0)
            gain = proceeds + retained_amount + nci_opening - (net_assets + full_goodwill)

        self.derecognize_subsidiary(event, adjustment_values)

        books._post(f"Remove {entity.name} goodwill on loss of control", full_goodwill,
                    debit=self.clearing, credit=self.goodwill)
        books._post(f"Derecognize {entity.name} noncontrolling interests", nci_opening,
                    debit=self.nci_accounts[entity], credit=self.clearing)
        if event.method == "equity" and retained_share > 0:
            retained_account = self.equity_investments[entity]
        elif event.method == "cost" and retained_share > 0:
            retained_account = self.account(event.investment)
        else:
            retained_account = None
        if retained_account is not None:
            books._post(f"Recognize retained investment in {entity.name}", retained_amount,
                        debit=retained_account, credit=self.clearing)
        books._post(f"Proceeds from loss of control of {entity.name}", proceeds,
                    debit=books._cash_account, credit=self.clearing, cf="investing")
        disposal_gain = _control_disposal_account(books)
        self.active_pl_accounts.add(disposal_gain)
        books._post(f"Gain on loss of control of {entity.name}", smax(gain, 0),
                    debit=self.clearing, credit=disposal_gain)
        books._post(f"Loss on loss of control of {entity.name}", smax(-gain, 0),
                    debit=disposal_gain, credit=self.clearing)

        if entity.standard.name == "J-GAAP" and event.method != "equity":
            residual = net_assets + full_goodwill - proceeds - retained_amount - nci_opening + gain
            books._post(f"Release remaining {entity.name} consolidation adjustments to retained earnings",
                        smax(residual, 0), debit=books.retained_earnings, credit=self.clearing)
            books._post(f"Release remaining {entity.name} consolidation adjustments to retained earnings",
                        smax(-residual, 0), debit=self.clearing, credit=books.retained_earnings)

        self.release_member_oci(event)
        self.release_translation(event, sold_share, retained_share)

    def derecognize_subsidiary(self, event: OwnershipEvent, adjustment_values):
        g, p, books = self.g, self.p, self.books
        entity, period = event.entity, event.period
        for source in entity._accounts:
            if source.side not in ("asset", "liability"):
                continue
            raw_balance = _at_period(entity._balance(source).opening, period, g)
            for trade, state in g._s6_trade_states.items():
                if trade.buyer is entity and trade.buyer_item.account is source:
                    raw_balance -= state["opening"] * (g.model.t == period)
            if _currency_dims(entity._currency) != _currency_dims(p._currency):
                raw_balance = _convert_currency(g.model, raw_balance, entity._currency, p._currency, "acquisition")
            target = self.account(source)
            if source.side == "asset":
                books._post(f"Deconsolidate {entity.name}: {source.name}", raw_balance,
                            debit=self.clearing, credit=target,
                                    cf="investing" if source is entity._cash_account else None)
            else:
                books._post(f"Deconsolidate {entity.name}: {source.name}", raw_balance,
                            debit=target, credit=self.clearing)
        for acquisition_event, adjustment, remaining in adjustment_values:
            terms = acquisition_event.acquisition
            if adjustment.source is not None:
                target = self.account(adjustment.source)
                if adjustment.side == "liability":
                    books._post(f"Remove {entity.name} acquisition adjustment: {adjustment.name}", -remaining,
                                debit=target, credit=self.clearing)
                else:
                    books._post(f"Remove {entity.name} acquisition adjustment: {adjustment.name}", remaining,
                                debit=self.clearing, credit=target)
            else:
                sides = ("asset", "liability") if adjustment.side == "dynamic" else (adjustment.side,)
                for side in sides:
                    kind = "intangible" if side == "asset" else "other_liability"
                    target = next(a for a in books._accounts if a.name == adjustment.name and a.kind == kind)
                    value = smax(remaining, 0) if side == "asset" else smax(-remaining, 0)
                    if side == "asset":
                        books._post(f"Remove {entity.name} acquisition adjustment: {adjustment.name}", value,
                                    debit=self.clearing, credit=target)
                    else:
                        books._post(f"Remove {entity.name} acquisition adjustment: {adjustment.name}", value,
                                    debit=target, credit=self.clearing)
            if terms is not None and isinstance(terms, AcquisitionTerms) and terms.tax_rate is not None:
                difference = remaining / (1 - terms.tax_rate)
                tax_liability = next((a for a in books._accounts if a.name == f"{entity.name}: {adjustment.name}"
                                      and a.kind == "deferred_tax_liability"), None)
                tax_asset = next((a for a in books._accounts if a.name == f"{entity.name}: {adjustment.name}"
                                  and a.kind == "deferred_tax_asset"), None)
                if tax_liability is not None:
                    amount = terms.tax_rate * smax(difference, 0)
                    books._post(f"Remove {entity.name} acquisition deferred tax", amount,
                                debit=tax_liability, credit=self.clearing)
                if tax_asset is not None:
                    amount = terms.tax_rate * smax(-difference, 0)
                    books._post(f"Remove {entity.name} acquisition deferred tax", amount,
                                debit=self.clearing, credit=tax_asset)

    def release_member_oci(self, event: OwnershipEvent):
        g, books = self.g, self.books
        entity, period = event.entity, event.period
        opening_oci_names = {name for owner, name in self.opening_oci_parent if owner is entity}
        for name in set(entity._oci_components) | opening_oci_names:
            component = entity._oci_components.get(name)
            source = component.account if component is not None else self.opening_oci_source.get((entity, name))
            source_oci = _member_oci(g, entity, source, self.scopes) if source is not None else \
                self.opening_oci_parent[(entity, name)] * 0
            share = _share_series(g, g._ownership[entity])
            release = _member_oci_release(g, entity, source, self.scopes) if source is not None else source_oci * 0
            _, _, nci_adjustment, _, _ = _opening_oci_attribution(
                entity, name, release, share, self.opening_oci_parent, self.opening_oci_nci, g._ownership[entity])
            opening_parent = self.opening_oci_parent.get((entity, name), source_oci * 0)[0]
            prior_transfers = _sum(self.opening_oci_transfers.get((entity, name), []), books,
                                   f"{entity.name}: {name} OCI ownership transfers")
            parent_movement = share * source_oci + nci_adjustment + prior_transfers
            parent_oci = (opening_parent + parent_movement.cumsum().lag(1, fill=0)) * \
                (g.model.t == period)
            previous_releases = self.released_oci.get((entity, name), [])
            already_released = parent_oci * 0
            if previous_releases:
                already_released = _sum(previous_releases, books,
                                        f"{entity.name}: previously released {name} OCI").cumsum().lag(1, fill=0) * \
                    (g.model.t == period)
            parent_share = parent_oci - already_released
            self.released_oci.setdefault((entity, name), []).append(parent_share)
            if source is not None:
                target = self.account(source)
            else:
                target = next((account for account in books._accounts
                               if account.side == "equity" and account.kind == "oci" and account.name == name), None)
                if target is None:
                    target = books._account(name, "equity", "oci", "financing")
            recycle = component.recycle if component is not None else True
            if recycle:
                preferred = ("other_income", "non_operating_income", "non_interest_income", "special_gain",
                             "finance_income")
                kind = next((candidate for candidate in preferred if candidate in books.layout.income_kinds), None)
                if kind is None:
                    raise ValueError(f"{books.layout.name} has no non-revenue income kind for OCI recycling")
                release = _group_pl_account(books, f"OCI release: {name}", kind, "income")
                self.active_pl_accounts.add(release)
                books._post(f"OCI release: {name}", parent_share, debit=target, credit=release)
            else:
                books._post(f"OCI release: {name}", parent_share,
                            debit=target, credit=books.retained_earnings)

    def release_translation(self, event: OwnershipEvent, sold_share, retained_share):
        g, books = self.g, self.books
        entity, period = event.entity, event.period
        if entity in self.cta_accounts:
            cta = self.cta_accounts[entity]
            cumulative = books._balance(cta).opening * (g.model.t == period)
            if entity.standard.name == "J-GAAP":
                sold_fraction = sold_share / event.previous_share
                to_profit = cumulative * sold_fraction
                to_retained_earnings = cumulative - to_profit \
                    if event.method != "equity" or retained_share == 0 else cumulative * 0
            else:
                to_profit = cumulative
                to_retained_earnings = cumulative * 0
            if entity.standard.name != "J-GAAP" or sold_share:
                preferred = ("other_income", "non_operating_income", "non_interest_income", "special_gain",
                             "finance_income")
                kind = next((candidate for candidate in preferred if candidate in books.layout.income_kinds), None)
                if kind is None:
                    raise ValueError(f"{books.layout.name} has no non-revenue income kind for OCI recycling")
                release = _group_pl_account(books, f"OCI release: {cta.name}", kind, "income")
                self.active_pl_accounts.add(release)
                books._post(f"OCI release: {cta.name}", to_profit, debit=cta, credit=release)
            if entity.standard.name == "J-GAAP" and (event.method != "equity" or retained_share == 0):
                books._post(f"Transfer remaining {cta.name} to retained earnings", to_retained_earnings,
                            debit=cta, credit=books.retained_earnings)
            self.cta_release_oci.setdefault(entity, []).append(-to_profit - to_retained_earnings)

    def collect_oci(self):
        g, books = self.g, self.books
        for entity in self.replay_entities:
            for name, component in entity._oci_components.items():
                self.oci_parts.setdefault(name, []).append(_member_oci(g, entity, component.account, self.scopes))
                self.oci_targets[name] = self.account(component.account)
                if name in self.oci_policies and self.oci_policies[name] != component.recycle:
                    raise ValueError(f"OCI {name!r} uses different recycle policies across group members")
                self.oci_policies[name] = component.recycle
        for entity, target in self.cta_accounts.items():
            name = target.name
            self.oci_parts.setdefault(name, []).append(
                _sum(self.cta_parts[entity], books, f"{entity.name}: translation adjustment"))
            self.oci_parts[name].extend(self.cta_release_oci.get(entity, []))
            self.oci_targets[name] = target
            self.oci_policies[name] = True
        for event in self.opening_events:
            for name, source, parent_part, nci_part in event.opening.oci:
                if source is None:
                    target = next((account for account in books._accounts
                                   if account.side == "equity" and account.kind == "oci"
                                   and account.name == name), None)
                    if target is None:
                        target = books._account(name, "equity", "oci", "financing")
                    recycle = True
                else:
                    target = self.account(source)
                    component = event.entity._oci_components.get(name)
                    recycle = component.recycle if component is not None else True
                target.opening = (target.opening if target.opening is not None else lift(0)) + parent_part
                self.oci_parts.setdefault(name, []).append(parent_part * 0)
                self.oci_targets[name] = target
                if name in self.oci_policies and self.oci_policies[name] != recycle:
                    raise ValueError(f"OCI {name!r} uses different recycle policies across group members")
                self.oci_policies[name] = recycle
                books._opening_oci_parent[(event.entity, name)] = parent_part
                books._opening_oci_nci[(event.entity, name)] = nci_part
        for event in self.opening_equity_events:
            for name, source, amount in event.opening.oci:
                if source is None:
                    target = next((account for account in books._accounts
                                   if account.side == "equity" and account.kind == "oci"
                                   and account.name == name), None)
                    if target is None:
                        target = books._account(name, "equity", "oci", "financing")
                    recycle = True
                else:
                    target = self.account(source)
                    component = event.entity._oci_components.get(name)
                    recycle = component.recycle if component is not None else True
                target.opening = (target.opening if target.opening is not None else lift(0)) + amount
                books.retained_earnings.opening = books.retained_earnings.opening - amount
                self.oci_parts.setdefault(name, []).append(amount * 0)
                self.oci_targets[name] = target
                if name in self.oci_policies and self.oci_policies[name] != recycle:
                    raise ValueError(f"OCI {name!r} uses different recycle policies across group members")
                self.oci_policies[name] = recycle
        for entity, events in self.associates.items():
            share = _share_series(g, events)
            associate_scope = _ownership_scope(events, "equity")
            investment = self.equity_investments[entity]
            for name, component in entity._oci_components.items():
                amount = _member_oci(g, entity, component.account, {entity: associate_scope}) * share
                target = next((a for a in books._accounts if a.side == "equity" and a.kind == "oci"
                               and a.name == component.account.name), None)
                if target is None:
                    target = books._account(component.account.name, "equity", "oci", "financing")
                books._post(f"Share of {entity.name} OCI: {name}", amount, debit=investment, credit=target)
                self.oci_parts.setdefault(name, []).append(amount)
                self.oci_targets[name] = target
                if name in self.oci_policies and self.oci_policies[name] != component.recycle:
                    raise ValueError(f"OCI {name!r} uses different recycle policies across group members")
                self.oci_policies[name] = component.recycle
                self.equity_oci_movements.setdefault(entity, []).append(amount)

    def book_equity_method(self):
        books = self.books
        books._equity_method_suspended_losses = {}
        for entity, events in self.associates.items():
            self.book_equity_method_associate(entity, events)

    def book_equity_method_associate(self, entity: Entity, events: list[OwnershipEvent]):
        g, p, books = self.g, self.p, self.books
        equity_acquisitions = [event for event in events if event.method == "equity" and
                               event.kind in ("opening", "acquisition", "loss")]
        initial_acquisition = equity_acquisitions[0]
        initial_terms = initial_acquisition.acquisition
        if not isinstance(initial_terms, EquityMethodTerms):
            initial_terms = EquityMethodTerms((), "carryover", None, False, None, None, True)
        investment = self.equity_investments[entity]
        associate_scopes = {entity: _ownership_scope(events, "equity")}
        share = _share_series(g, events)
        lots = _equity_method_lots(g, events)
        investment_movements, adjustment_profit_parts, goodwill_amortization_parts = \
            self.equity_method_event_movements(entity, events, investment, share)
        impairment_parts = []

        for lot in lots:
            event = lot.event
            terms = event.acquisition
            if not isinstance(terms, EquityMethodTerms):
                raise RuntimeError(f"{entity.name}: equity-method lot terms were not prepared")
            adjustments, deferred_tax, adjustment_profit = _equity_adjustment_amounts(g, books, event, terms)
            if isinstance(event.opening, OpeningEquityMethod):
                embedded_goodwill = event.opening.embedded_goodwill
            else:
                acquisition_net_assets = _standalone_net_assets(entity, event.period, g)
                embedded_goodwill = event.investment_cost - lot.acquired_share * (
                    acquisition_net_assets + adjustments - deferred_tax)
            adjustment_profit_parts.append(adjustment_profit * lot.held_share)
            if terms.goodwill_life is not None:
                amortization = _GoodwillAmortization(
                    g.model, smax(embedded_goodwill, 0), lift(0),
                    0 if event.kind == "opening" else event.period, terms.goodwill_life)
                ownership_factor = lift(1) if event.kind == "opening" else lot.held_share / lot.acquired_share
                goodwill_amortization_parts.append(amortization * ownership_factor)
            elif books.standard.name == "J-GAAP":
                g.model.check(smax(embedded_goodwill, 0) <= 0,
                              f"{entity.name}: J-GAAP equity-method goodwill requires goodwill_life= on each lot")
            if terms.impairment is not None:
                impairment_parts.append(terms.impairment)

        raw_profit = _member_profit(g, entity, associate_scopes) * share
        raw_profit += _sum(adjustment_profit_parts, books, f"{entity.name}: equity-method basis adjustments")
        raw_profit -= _sum(goodwill_amortization_parts, books, f"{entity.name}: embedded goodwill amortization")

        income_kind = "non_operating_income" if books.standard.name == "J-GAAP" else "other_income"
        income = _group_pl_account(books, books.label("equity_method_income"), income_kind, "income")
        income.tags = income.tags | {"equity_method_presentation"}
        self.active_pl_accounts.add(income)
        opening_suspended = initial_acquisition.opening.suspended_losses \
            if isinstance(initial_acquisition.opening, OpeningEquityMethod) else lift(0)
        profit = _EquityMethodProfit(raw_profit, lift(0), initial_terms.loss_limit,
                                     _equity_method_sale_retention(g, events), opening_suspended, entity.name)

        dividends = []
        for post in p._associate_dividend_receipts:
            if post.counterparty is entity:
                dividends.append(post.amount * (g.model.t >= initial_acquisition.period))
        other_movements = [-dividend for dividend in dividends]
        other_movements.extend(self.equity_oci_movements.get(entity, []))
        total_impairment = None
        if impairment_parts:
            total_impairment = _sum(impairment_parts, books, f"{entity.name}: investment impairment")
            other_movements.append(-total_impairment)
        available = _EquityMethodAvailable(investment_movements, other_movements, profit, entity.name)
        profit.available = available
        books._equity_method_suspended_losses[entity] = profit.suspended

        if books.standard.name == "J-GAAP":
            loss = _group_pl_account(books, books.label("equity_method_loss"), "non_operating_expense")
            loss.tags = loss.tags | {"equity_method_presentation"}
            self.active_pl_accounts.add(loss)
            books._post(f"Recognize {entity.name} equity-method income", smax(profit, 0),
                        debit=investment, credit=income)
            books._post(f"Recognize {entity.name} equity-method loss", -smin(profit, 0),
                        debit=loss, credit=investment)
        else:
            books._post(f"Recognize {entity.name} equity-method earnings", profit,
                        debit=investment, credit=income)

        if total_impairment is not None:
            impairment_kind = "special_loss" if books.standard.name == "J-GAAP" else \
                ("sga" if "sga" in books.layout.pl_kinds else books.layout.depreciation_kind)
            impairment = _group_pl_account(
                books, books.label("equity_method_impairment"), impairment_kind)
            impairment.tags = impairment.tags | {"equity_method_presentation"}
            self.active_pl_accounts.add(impairment)
            books._post(f"Impairment of investment in {entity.name}", total_impairment,
                        debit=impairment, credit=investment)

    def equity_method_event_movements(self, entity: Entity, events: list[OwnershipEvent],
                                     investment: Account, share: Series):
        g, books = self.g, self.books
        investment_movements = []
        adjustment_profit_parts = []
        goodwill_amortization_parts = []

        for event in events:
            if event.method == "equity" and event.kind == "opening":
                investment_movements.append(event.opening.investment * (g.model.t == 0))
            elif event.method == "equity" and event.kind in ("acquisition", "purchase"):
                books._post(f"Recognize investment in {entity.name}", event.investment_cost,
                            debit=investment, credit=self.account(event.investment))
                investment_movements.append(event.investment_cost)
            elif event.method == "equity" and event.kind == "sale":
                for post in event.sale_postings:
                    books._post(f"Eliminate parent sale: {post.name}", post.amount,
                                debit=self.account(post.credit), credit=self.account(post.debit), cf=post.cf)
                sold_fraction = (event.previous_share - event.share) / event.previous_share
                carrying = books._balance(investment).opening * sold_fraction * (g.model.t == event.period)
                investment_movements.append(-carrying)
                if event.proceeds is None:
                    raise RuntimeError(f"{entity.name}: an equity-method sale has no proceeds")
                gain_kind, loss_kind, gain_name, loss_name = _equity_method_sale_labels(books)
                gain = smax(event.proceeds - carrying, 0)
                loss = smax(carrying - event.proceeds, 0)
                recovered_cost = smin(event.proceeds, carrying)
                gain_account = _sale_account(books, gain_name, gain_kind, "income")
                loss_account = _sale_account(books, loss_name, loss_kind, "expense")
                self.active_pl_accounts.update((gain_account, loss_account))
                books._post(f"Sell {entity.name} investment at carrying amount", recovered_cost,
                            debit=books._cash_account, credit=investment, cf="investing")
                books._post(gain_name, gain, debit=books._cash_account, credit=gain_account, cf="investing")
                books._post(loss_name, loss, debit=loss_account, credit=investment)
            elif event.method == "equity" and event.kind == "loss":
                retained_basis = event.retained_value if event.retained_value is not None else lift(0)
                if event.entity.standard.name == "J-GAAP":
                    raw_assets = _net_assets(g, entity, event.period, self.scopes,
                                             membership_period=event.period - 1)
                    adjustment_assets, _ = self.acquisition_adjustments_at_open(entity, event.period)
                    goodwill_balance = self.active_goodwill(entity, event.period) * \
                        (event.share / event.previous_share)
                    retained_basis = event.share * (raw_assets + adjustment_assets) + goodwill_balance
                prior_loss = max((candidate.period for candidate in events
                                  if candidate.kind == "loss" and candidate.period < event.period), default=-1)
                equity_interval = _ownership_event_mask(g, event, "equity")
                for basis_event in events:
                    terms = basis_event.acquisition
                    if basis_event.method != "consolidate" or basis_event.kind not in ("acquisition", "step") or \
                            basis_event.period <= prior_loss or basis_event.period >= event.period or \
                            not isinstance(terms, AcquisitionTerms) or not terms.adjustments:
                        continue
                    equity_terms = EquityMethodTerms(terms.adjustments, terms.tax_basis, terms.goodwill_life,
                                                     terms.private_company, None, terms.tax_rate, True)
                    _, _, basis_profit = _equity_adjustment_amounts(g, books, basis_event, equity_terms)
                    adjustment_profit_parts.append(basis_profit * share * equity_interval)
                if event.entity.standard.name == "J-GAAP":
                    for goodwill_event, (origin, reductions) in self.goodwill_schedules.items():
                        terms = goodwill_event.acquisition
                        if goodwill_event.entity is not entity or goodwill_event.period <= prior_loss or \
                                goodwill_event.period >= event.period or not isinstance(terms, AcquisitionTerms) or \
                                terms.goodwill_life is None:
                            continue
                        remaining = origin.cumsum().lag(1, fill=0) - \
                            _sum(reductions, books, f"{entity.name}: embedded goodwill reductions").cumsum().lag(1, fill=0)
                        remaining *= (event.share / event.previous_share) * (g.model.t == event.period)
                        elapsed = sum(g.model.timeline.periods[index].months
                                      for index in range(goodwill_event.period, event.period))
                        remaining_life = terms.goodwill_life - elapsed
                        if remaining_life > 0:
                            amortization = _GoodwillAmortization(
                                g.model, remaining, remaining * 0, event.period, remaining_life) * equity_interval
                            goodwill_amortization_parts.append(amortization)
                investment_movements.append(retained_basis)
            elif event.kind == "step" and event.previous_method == "equity":
                investment_movements.append(-books._balance(investment).opening * (g.model.t == event.period))

        return investment_movements, adjustment_profit_parts, goodwill_amortization_parts

    def register_oci_lines(self):
        books = self.books
        for name, parts in self.oci_parts.items():
            line = LineItem(name, _sum(parts, books, f"{name}: consolidated OCI"), books, "oci", self.oci_targets[name])
            line.balance = books._balance(self.oci_targets[name])
            component = _OCIComponent(name, self.oci_targets[name], recycle=self.oci_policies[name],
                                      taxed=False, line=line)
            books._oci_components[name] = component
            if hasattr(books.bs, "oci"):
                books.bs.oci._items.append(line)

    def attribute_to_nci(self):
        g, books = self.g, self.books
        for entity, events in self.subsidiaries.items():
            share = _share_series(g, events)
            adjustment_profit = _sum(self.acquisition_profit_adjustments.get(entity, []), books,
                                     f"{entity.name}: acquisition profit adjustments")
            asset_trade_profit = _sum(self.s6_profit_adjustments.get(entity, []), books,
                                      f"{entity.name}: intercompany asset profit adjustments")
            oci_profit_adjustments = []
            for source in entity._accounts:
                if source.kind != "oci":
                    continue
                target = self.account(source)
                component = entity._oci_components.get(source.name)
                released = _member_oci_release(g, entity, source, self.scopes)
                _, opening_nci_release, nci_adjustment, _, _ = _opening_oci_attribution(
                    entity, source.name, released, share, self.opening_oci_parent, self.opening_oci_nci, events)
                if component is not None and component.recycle:
                    oci_profit_adjustments.append(nci_adjustment)
                elif component is not None:
                    books._post(f"Transfer opening {entity.name} NCI OCI to retained earnings: {source.name}",
                                opening_nci_release, debit=books.retained_earnings,
                                credit=self.nci_accounts[entity])
                allocation = _member_oci(g, entity, source, self.scopes) * (1 - share) - nci_adjustment
                books._post(f"Transfer {entity.name} OCI to NCI", allocation, debit=target,
                            credit=self.nci_accounts[entity])
            if entity in self.cta_accounts:
                parent_only = _sum(self.cta_parent_only_parts[entity], books,
                                   f"{entity.name}: parent-only translation adjustments")
                total_translation = _sum(self.cta_parts[entity], books,
                                         f"{entity.name}: translation adjustment for NCI")
                allocation = (total_translation - parent_only) * (1 - share) * self.scopes[entity].mask(g.model)
                books._post(f"Transfer {entity.name} translation adjustment to NCI", allocation,
                            debit=self.cta_accounts[entity], credit=self.nci_accounts[entity])
            # NCI shares the subsidiary's own profit, its trades with other members included
            own_profit = _member_profit(g, entity, self.scopes, eliminate_trades=False)
            raw_profit = (own_profit + adjustment_profit + asset_trade_profit) * (1 - share)
            raw_profit += _sum(oci_profit_adjustments, books, f"{entity.name}: opening OCI profit attribution")
            full_impairment = _sum(self.full_goodwill_impairments.get(entity, []), books,
                                   f"{entity.name}: noncontrolling goodwill impairment")
            raw_profit -= full_impairment
            initial_parts = [_at_period(self.acquisition_nci[event], event.period, g)
                             for event in events if event.kind in ("acquisition", "step")
                             and event.method == "consolidate"]
            purchase_parts = [-(event.share - event.previous_share) * _net_assets(g, entity, event.period, self.scopes)
                              for event in events if event.method == "consolidate" and
                              event.previous_method == "consolidate" and event.kind in ("purchase", "sale")]
            initial = _sum(initial_parts, books, f"{entity.name}: acquisition NCI")
            purchase_change = _sum(purchase_parts, books, f"{entity.name}: purchase NCI change")
            opening = books._balance(self.nci_accounts[entity]).opening + initial + purchase_change
            if entity.standard.name == "J-GAAP":
                profit = _JgaapNciProfit(raw_profit, opening, entity.name)
                profit.suspended = _JgaapSuspendedLoss(raw_profit, opening, entity.name)
            else:
                profit = raw_profit
            books._post(f"Transfer {entity.name} profit to NCI", profit,
                        debit=books.retained_earnings, credit=self.nci_accounts[entity])
            self.profit_shares.append(profit)

    def attribute_group_profit(self):
        p, books = self.p, self.books
        if self.has_subsidiaries:
            total_nci_profit = _sum(self.profit_shares, books, "NCI share of consolidated profit")
            parent_profit = books.net_income - total_nci_profit
            if books.standard.name == "J-GAAP":
                cap_change = _sum(self.cap_changes, books, "capital surplus changes")
                cap_balance = books._balance(self.capital_surplus)
                clear_amount = smax(-(cap_balance.opening + cap_change), 0)
                books._post("Clear negative capital surplus against retained earnings", clear_amount,
                            debit=books.retained_earnings, credit=self.capital_surplus)

            if books.standard.name == "IFRS":
                attribution = {"section": "Attributable to:", "nci_label": "Non-controlling interests",
                               "parent_label": "Owners of the parent", "nci": total_nci_profit,
                               "parent": parent_profit}
            elif books.standard.name == "US GAAP":
                attribution = {"section": None, "nci_label": "Attributable to noncontrolling interests",
                               "parent_label": f"Attributable to {p.name}", "nci": total_nci_profit,
                               "parent": parent_profit}
            else:
                attribution = {"section": None, "nci_label": books.label("nci_profit"),
                               "parent_label": books.label("parent_profit"), "nci": total_nci_profit,
                               "parent": parent_profit}
            books._group_profit_attribution = attribution
            books._group_parent_name = p.name

    def add_pl_lines(self):
        books = self.books
        for account_ in books._accounts:
            if account_.cf != "pl" or account_ not in self.active_pl_accounts:
                continue
            sign = 1 if account_.side == "expense" else -1
            amounts = [post.amount * sign for post in account_.debits] + \
                [post.amount * -sign for post in account_.credits]
            total = _Total(lambda amounts=amounts: amounts, f"{account_.name} (consolidated)", books)
            getattr(books.pl, account_.kind)._items.append(
                LineItem(account_.name, total, books, account_.kind, account_, account_.category))


def _consolidate(g: Group) -> Entity:
    return _Consolidation(g).run()

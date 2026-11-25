"""Series nodes that the group's consolidation adds to the consolidated books."""
from __future__ import annotations

from ..series import Series
from .terms import OwnershipEvent


class _JgaapNciProfit(Series):
    """Limit NCI losses at zero and recover parent-borne losses before allocating later profit."""

    def __init__(self, raw: Series, opening: Series, name: str):
        self.raw, self.nci_opening, self.suspended = raw, opening, None
        self.name, self.unit = f"{name}: NCI profit", raw.unit

    def _eval(self, r, t):
        raw = r.value(self.raw, None if self.raw.scalar else t) or 0
        suspended = r.value(self.suspended, t - 1) if t > 0 else 0
        if raw >= 0:
            return raw - min(raw, suspended)
        available = max(r.value(self.nci_opening, None if self.nci_opening.scalar else t) or 0, 0)
        return -min(-raw, available)


class _JgaapSuspendedLoss(Series):
    """Losses allocated to parent owners because NCI was exhausted, awaiting later NCI profits."""

    def __init__(self, raw: Series, opening: Series, name: str):
        self.raw, self.nci_opening = raw, opening
        self.name, self.unit = f"{name}: NCI losses borne by parent", raw.unit

    def _eval(self, r, t):
        prior = r.value(self, t - 1) if t > 0 else 0
        raw = r.value(self.raw, None if self.raw.scalar else t) or 0
        if raw >= 0:
            return max(prior - raw, 0)
        available = max(r.value(self.nci_opening, None if self.nci_opening.scalar else t) or 0, 0)
        return prior + (-raw - min(-raw, available))


class _EquityMethodProfit(Series):
    """Recognize losses only down to the investment balance and recover them from later profits."""

    def __init__(self, raw: Series, available: Series, loss_limit: bool, sale_retention: Series,
                 opening_suspended: Series, name: str):
        self.raw, self.available, self.loss_limit = raw, available, loss_limit
        self.sale_retention = sale_retention
        self.opening_suspended = opening_suspended
        self.suspended = _EquityMethodSuspended(self)
        self.name, self.unit = f"{name}: recognized equity-method profit", raw.unit

    def _eval(self, r, t):
        raw = r.value(self.raw, None if self.raw.scalar else t) or 0
        suspended = (r.value(self.suspended, t - 1) if t > 0 else
                     r.value(self.opening_suspended, None if self.opening_suspended.scalar else t)) * \
            (r.value(self.sale_retention, None if self.sale_retention.scalar else t) or 0)
        if raw >= 0:
            return raw - min(raw, suspended)
        if not self.loss_limit:
            return raw
        available = r.value(self.available, None if self.available.scalar else t) or 0
        return -min(-raw, max(available, 0))


class _EquityMethodSuspended(Series):
    """Carry excess losses forward and apply later profits to them before recognizing income."""

    def __init__(self, profit: _EquityMethodProfit):
        self.profit = profit
        self.name = f"{profit.name}: unrecognized losses"
        self.unit = profit.unit

    def _eval(self, r, t):
        if not self.profit.loss_limit:
            return 0
        prior = (r.value(self, t - 1) if t > 0 else
                 r.value(self.profit.opening_suspended,
                         None if self.profit.opening_suspended.scalar else t)) * \
            (r.value(self.profit.sale_retention,
                     None if self.profit.sale_retention.scalar else t) or 0)
        raw = r.value(self.profit.raw, None if self.profit.raw.scalar else t) or 0
        if raw >= 0:
            return max(prior - raw, 0)
        available = r.value(self.profit.available, None if self.profit.available.scalar else t) or 0
        recognized = min(-raw, max(available, 0))
        return prior + (-raw - recognized)


class _EquityMethodAvailable(Series):
    """Carrying amount before current-period equity earnings, floored at zero."""

    def __init__(self, costs: list[Series], other_movements: list[Series], profit: _EquityMethodProfit, name: str):
        self.costs, self.other_movements, self.profit = costs, other_movements, profit
        self.name = f"{name}: carrying amount available for equity-method losses"

    def _eval(self, r, t):
        total = 0
        for series in self.costs + self.other_movements:
            for period in range(t + 1):
                total += r.value(series, None if series.scalar else period) or 0
        for period in range(t):
            total += r.value(self.profit, None if self.profit.scalar else period) or 0
        return max(total, 0)


class _OpeningOciBalance(Series):
    """Opening OCI share after earlier releases and controlled ownership changes."""

    def __init__(self, parent_opening: Series, nci_opening: Series, release: Series,
                 events: list[OwnershipEvent], *, nci: bool, apply_current_transfer: bool = True):
        self.parent_opening, self.nci_opening, self.release = parent_opening, nci_opening, release
        self.events, self.nci, self.apply_current_transfer = events, nci, apply_current_transfer
        self.name = "opening OCI NCI balance" if nci else "opening OCI parent balance"
        self.unit = parent_opening.unit

    def _eval(self, r, t):
        parent = r.value(self.parent_opening, 0) or 0
        nci = r.value(self.nci_opening, 0) or 0
        for period in range(t + 1):
            if period < t or self.apply_current_transfer:
                for event in self.events:
                    if event.period != period or event.previous_method != "consolidate" or \
                            event.kind not in ("purchase", "sale"):
                        continue
                    if event.kind == "purchase" and event.previous_share < 1:
                        transfer = nci * (event.share - event.previous_share) / (1 - event.previous_share)
                        parent += transfer
                        nci -= transfer
                    elif event.kind == "sale" and event.previous_share > 0:
                        transfer = parent * (event.previous_share - event.share) / event.previous_share
                        parent -= transfer
                        nci += transfer
            if period == t:
                return nci if self.nci else parent
            released = r.value(self.release, None if self.release.scalar else period) or 0
            total = parent + nci
            if total * released > 0:
                consumed = min(abs(total), abs(released))
                amount = consumed if total > 0 else -consumed
                parent -= amount * parent / total
                nci -= amount * nci / total


class _OpeningOciRelease(Series):
    """The portion of an OCI release that consumes its opening accumulated balance."""

    def __init__(self, release: Series, parent_balance: Series, nci_balance: Series, *, nci_only: bool):
        self.release, self.parent_balance, self.nci_balance, self.nci_only = \
            release, parent_balance, nci_balance, nci_only
        self.name = "opening OCI release attributable to NCI" if nci_only else "opening OCI release"
        self.unit = release.unit

    def _eval(self, r, t):
        parent = r.value(self.parent_balance, None if self.parent_balance.scalar else t) or 0
        nci = r.value(self.nci_balance, None if self.nci_balance.scalar else t) or 0
        total = parent + nci
        released = r.value(self.release, None if self.release.scalar else t) or 0
        if total * released <= 0:
            return 0
        consumed = min(abs(total), abs(released))
        amount = consumed if released > 0 else -consumed
        return amount * nci / total if self.nci_only else amount


class _GoodwillAmortization(Series):
    """Straight-line goodwill amortization, recalculated over the remaining life after impairment."""

    def __init__(self, model, goodwill: Series, impairment: Series, period: int, life_months: int):
        self.model, self.goodwill, self.impairment = model, goodwill, impairment
        self.period, self.life_months = period, life_months
        self.name = "Goodwill amortization schedule"

    @property
    def unit(self):
        return self.goodwill.unit

    def _eval(self, r, t):
        if t < self.period:
            return 0
        elapsed = sum(self.model.timeline.periods[k].months for k in range(self.period, t))
        remaining = self.life_months - elapsed
        if remaining <= 0:
            return 0
        opening = r.value(self.goodwill, None if self.goodwill.scalar else self.period) or 0
        for k in range(self.period, t):
            opening -= (r.value(self.impairment, None if self.impairment.scalar else k) or 0)
            opening -= r.value(self, k) or 0
        return max(opening, 0) * min(self.model.timeline.periods[t].months, remaining) / remaining


class _OpeningDeferredTaxShare(Series):
    """Allocate opening net deferred tax to items by their opening tax effect."""

    def __init__(self, balance: Series, weights: tuple[Series, ...], index: int):
        self.balance, self.weights, self.index = balance, weights, index
        self.name = f"opening deferred tax share {index + 1}"

    @property
    def unit(self):
        return self.balance.unit

    def _eval(self, r, t):
        total = r.value(self.balance, None if self.balance.scalar else 0) or 0
        weights = [r.value(weight, None if weight.scalar else 0) or 0 for weight in self.weights]
        denominator = sum(weights)
        if abs(denominator) < 1e-12:
            return total if self.index == len(weights) - 1 else 0
        if self.index == len(weights) - 1:
            return total - sum(total * weights[index] / denominator for index in range(self.index))
        return total * weights[self.index] / denominator

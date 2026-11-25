"""Ownership, acquisition, and opening-balance terms that a group records for its members."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..ledger import Account, _AssetTrade, Entity, Posting
from ..series import Series, lift


@dataclass(eq=False)
class OwnershipEvent:
    entity: Entity
    period: int
    share: float
    method: str
    kind: str
    previous_method: str | None
    previous_share: float
    consideration: Series | None
    proceeds: Series | None
    previously_held_value: Series | None
    retained_value: Series | None
    investment: Account
    posting: Posting | None
    investment_end: Series
    investment_cost: Series
    individual_carrying_sold: Series
    paired_postings: tuple[Posting, ...] = ()
    acquisition_contribution: Series | None = None
    acquisition: "AcquisitionTerms | EquityMethodTerms | None" = None
    sale_postings: tuple[Posting, ...] = ()
    opening: "OpeningConsolidation | OpeningEquityMethod | None" = None


@dataclass(frozen=True)
class AcquisitionAdjustment:
    name: str
    source: Account | None
    side: Literal["asset", "liability", "dynamic"]
    value: Series
    remaining_life: int | None


@dataclass(frozen=True)
class AcquisitionTerms:
    adjustments: tuple[AcquisitionAdjustment, ...]
    tax_basis: Literal["carryover", "stepped_up"]
    nci: Literal["proportionate", "fair_value"]
    nci_value: Series | None
    goodwill_life: int | None
    private_company: bool
    impairment: Series | None
    tax_rate: Series | None


@dataclass(frozen=True)
class OpeningConsolidation:
    goodwill: Series
    goodwill_life: int | None
    nci: Series
    fair_value: tuple[AcquisitionAdjustment, ...]
    deferred_tax: Series
    deferred_tax_shares: tuple[Series, ...]
    tax_rate: Series | None
    capital_surplus: Series
    unrealized: tuple["OpeningUnrealized", ...]
    oci: tuple[tuple[str, Account | None, Series, Series], ...]


@dataclass(frozen=True)
class OpeningEquityMethod:
    investment: Series
    embedded_goodwill: Series
    goodwill_life: int | None
    suspended_losses: Series
    fair_value: tuple[AcquisitionAdjustment, ...]
    tax_rate: Series | None
    oci: tuple[tuple[str, Account | None, Series], ...]


@dataclass(frozen=True)
class OpeningUnrealized:
    trade: _AssetTrade
    amount: Series


@dataclass(frozen=True)
class EquityMethodTerms:
    adjustments: tuple[AcquisitionAdjustment, ...]
    tax_basis: Literal["carryover", "stepped_up"]
    goodwill_life: int | None
    private_company: bool
    impairment: Series | None
    tax_rate: Series | None
    loss_limit: bool


@dataclass(frozen=True)
class EquityMethodLot:
    event: OwnershipEvent
    acquired_share: float
    held_share: Series


@dataclass(frozen=True)
class Scope:
    intervals: tuple[tuple[int, int | None], ...]

    def contains(self, period: int) -> bool:
        return any(start <= period and (end is None or period < end) for start, end in self.intervals)

    def start_at(self, period: int) -> int:
        return next(start for start, end in self.intervals if start <= period and (end is None or period < end))

    def mask(self, model) -> Series:
        mask = lift(0)
        for start, end in self.intervals:
            interval = model.t >= start
            if end is not None:
                interval *= model.t < end
            mask += interval
        return mask

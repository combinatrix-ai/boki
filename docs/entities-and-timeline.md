# Entities, fiscal periods, and account names (proposal)

Proposal (2026-10-16), based on the user's comments:

- Irregular fiscal periods may justify an explicit fiscal-calendar concept, perhaps something like a `TimelineGroup`.
- It would be useful to consolidate group companies easily. A `Company` concept could support one-line consolidation, majority ownership, and intercompany transactions.
- A `company` or `entity` concept seems useful. A model could be an outer structure associated with those entities.

## Overall structure

```text
Model (outer container for the period axis, inputs, scenarios, and evaluator)
├── Timeline             Ordered calculation periods, each with its own length (months and quarters can be mixed)
├── Entity "Parent"      Has a fiscal calendar and accounts. Each entity's books balance independently.
│   ├── FiscalCalendar   Sequence of fiscal year ends, including irregular periods
│   └── Account ...      Typed accounts created from a chart of accounts (class)
├── Entity "Subsidiary A"
└── Group                Ownership between entities (percentage and start date) and consolidation method
```

- **The Model contains entities.** It has one period axis and evaluator, with one or more entities inside it. A single-entity plan creates one entity; the single-entity layer in design layer 3 hides this structure.
- **Use a shared calculation timeline and each entity's fiscal calendar for reporting.** Calculate on the Timeline, such as monthly, and report each entity's P&L and BS by fiscal period. Monthly values let entities with different fiscal calendars align for consolidation.

## Fiscal calendars and irregular periods

Represent a fiscal calendar as a sequence of fiscal year ends. If an entity changes its year-end, only that fiscal period has a different length.

```python
m = b.Model("Group plan", start="2027-04", end="2032-03", step=b.month)

parent = m.entity("Parent", fiscal=b.fiscal(year_end="03-31"))
sub = m.entity("Subsidiary A", fiscal=b.fiscal(year_end="12-31", change={"2029-03-31": "03-31"}))
# Subsidiary A has a December 2028 year-end, a three-month period ending March 2029, then March year-ends.

sub.fiscal.periods()
# [2027-04 to 2027-12 (nine-month first year), 2028-01 to 2028-12, 2029-01 to 2029-03 (irregular three-month period), 2029-04 to 2030-03, ...]
```

- The same system can create quarters and half-years by stepping back from the fiscal year-end in three-month intervals.
- Interest rates and depreciation stated as annual rates must be prorated for irregular periods. Monthly calculations handle the proration automatically.
- Fiscal periods are reporting units, not calculation units. A Timeline period, such as a month, maps to a fiscal period for each entity.

## Accounts

Accounts are typed objects, and users define a chart of accounts with a class ([double-entry.md](double-entry.md)). The proposal to infer account type from a string prefix has been withdrawn.

- The proposal used a chart class to describe accounts. The implementation selects `standard=` and optional `layout=` on `m.entity`; the statement rows derive their accounts from that layout. See [api.md](api.md#entities-and-statement-rows).
- Each entity has an accounting standard, such as `standard=b.JGAAP`. Warn when accounts or entities with different standards are combined.

## Intercompany transactions

> 2026-10-28: The `counterparty=` proposal in [api-principles.md](api-principles.md) §3 is expected to replace the syntax below. `b.intercompany` is the old proposal.

**Each move stays within one entity**, with both accounts belonging to that entity. This keeps each entity's books balanced on their own. Record an intercompany transaction with one move in each entity's books and mark the moves as a pair.

```python
b.intercompany("Parts sale", seller=sub, buyer=parent, amount=parts_qty * transfer_price,
               settle=delay(1))
# Subsidiary A: Accounts receivable (group) <- Revenue (group)
# Parent: Cost of goods sold (group) <- Accounts payable (group)
# Consolidation eliminates this pair.
```

- Paired moves share a transaction ID. Consolidation can check that revenue matches cost of goods sold and receivables match payables on both sides. Intercompany mismatches are common in practice.
- If inventory remains with the buyer at period-end, eliminate unrealized profit. Add this with inventory valuation in v0.4 or later.

## Consolidation with Group

```python
g = m.group("Group", parent=parent)
g.own(sub, 0.80, since="2027-04")                   # Majority ownership: full consolidation, 20% NCI
g.own(assoc, 0.30, since="2028-01", method="equity") # Associate: equity method (one-line consolidation)
consol = g.consolidate()                             # Consolidated P&L, BS, and CF on the parent's fiscal calendar
```

| Method | Applies to | Treatment |
|---|---|---|
| Full consolidation | Subsidiaries the group controls, such as majority-owned entities | Combine 100% of each entity's accounts, eliminate intercompany transactions and balances, and eliminate the parent's investment against the subsidiary's equity (record any difference as goodwill). Allocate the non-controlling share of the subsidiary's equity and profit to `Equity:Non-controlling interests` and `Expenses:Profit attributable to non-controlling interests`. |
| Equity method (one-line consolidation) | Associates over which the investor has significant influence, often with 20% to 50% ownership | Do not combine accounts. Record the investor's share of profit as `Revenue:Equity-method income` and increase `Assets:Investments:Associates` by the same amount. Reduce the investment when dividends are received. |
| Cost method | Other investments | Carry the investment at cost and recognize dividends as income. |

- Record changes in ownership, such as additional purchases or partial sales, with multiple date-stamped `own` calls. The engine treats a change in control as a period boundary when it changes the consolidation method.
- Monthly values let subsidiaries with different fiscal periods be consolidated on the parent's calendar. Add an option for the Japanese practice of using a subsidiary's statements when its period-end is within three months of the parent's.

## Open questions

- How much to support goodwill amortization and impairment, and details of non-controlling interest calculations such as fair-value measurement at acquisition.
- Taxes such as consolidated tax filing and group tax sharing.
- Whether to infer control and significant influence from ownership percentages or require an explicit method. The proposal makes `method=` available and infers it from ownership by default.
- Foreign currency translation for overseas subsidiaries and translation differences. Currencies are units, so translation will likely multiply by an exchange-rate series.

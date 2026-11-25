# Representing double-entry bookkeeping in boki (proposal)

Proposal (2026-10-16), based on the user's question: "It would be useful to record basic bookkeeping while writing a business plan. Could Account provide that?"

Revision (same day): The user objected that "a text-based approach is not good," so the proposal to identify accounts with strings such as `"Assets:Receivables"` was withdrawn. Accounts are typed objects, and users define the chart of accounts with a class. Entities carry an accounting standard, and boki warns when standards are mixed. The user also noted that standard charts of accounts likely exist and that adding accounts under different standards may need a warning.

## Conclusion

Yes. **Accounts and moves are double-entry bookkeeping itself**, so users do not need to write journal entries.

- A `move` transfers an amount from one account to another in a period. Each move creates a debit and a credit with the same amount, so **the books balance by construction**.
- Users describe business activity, such as when revenue is recognized and when cash is collected. The standard-library `flow` expands that description into two moves: recognition and collection.
- P&L, BS, and CF are views that aggregate account balances and moves. The BS balances by construction, as explained below.

## Data shape

```text
Account   Kind (Asset / Liability / Equity / Revenue / Expense / Quantity), parent account, unit, opening balance, and accounting standard
Move      Name, amount per period (series), source account, and destination account
Ledger    Collection of (period, move, source, destination, amount). Account balances and P&L, BS, and CF are derived from it.
```

- Accounts are **typed objects**. Declare kinds with classes such as `b.Asset` and `b.Revenue`, and represent the hierarchy with nested classes.
- Do not identify accounts with strings. A typo raises `AttributeError` instead of silently creating an account. Editors can also provide completion and rename support.
- Represent customer counts, AE headcount, and component inventory with `b.Quantity(unit=...)`. Quantities are excluded from P&L and BS totals.
- Create Beancount account names such as `Assets:Receivables:ProductA` only during export.
- In `move(name, amount, src=, dst=)`, `dst` is the debit and `src` is the credit.

## Example

The chart-class interface below was part of the early proposal and is not the current public API. Current models select an accounting standard and optional layout on `m.entity`; statement rows create the needed accounts. See [api.md](api.md#entities-and-statement-rows).

```python
class CompanyAccounts(b.jgaap.Accounts):  # Extend the standard Japanese GAAP chart of accounts.
    class Receivables(b.Asset):
        product_a = b.Asset()
    shipped_units = b.Quantity(unit=units)

# Historical proposal only; the implementation uses statement-row methods.
sales = m.series("Revenue", customers * price)
m.move("Recognize revenue", sales, src=acc.revenue, dst=acc.receivables.product_a)
m.move("Collect cash", sales.lag(1), src=acc.receivables.product_a, dst=acc.cash)  # Collect next month.
m.move("Purchase inventory", 0.35 * sales, src=acc.accounts_payable, dst=acc.cost_of_revenue)
m.move("Pay for inventory", (0.35 * sales).lag(1), src=acc.cash, dst=acc.accounts_payable)
```

The standard library expresses the same four moves as follows:

```python
flow("Revenue", sales, pl=acc.revenue, via=acc.receivables.product_a, settle=delay(1))
flow("Purchases", 0.35 * sales, pl=acc.cost_of_revenue, via=acc.accounts_payable, settle=delay(1), outflow=True)
```

The business plan states only how much revenue to recognize and that cash arrives the following month. It does not include journal entries.

## Why the BS always balances

1. Each move increases one account by the same amount that it decreases another. The sum across all accounts is always 0.
2. Treat revenue and expense accounts as closed to retained earnings at period-end. The engine does this during aggregation; users do not write the entries.
3. Therefore, `Assets = Liabilities + Equity` holds in every period.

The BS check is therefore an **engine invariant**, not a check for user input errors. User errors appear in other ways, as described next.

## Errors double-entry bookkeeping can detect

| Error | Detection |
|---|---|
| Unit mismatch (adding kW to euros) | Raise an error when a move amount's unit does not match its account. |
| Cash runs out | Warn when a cash account has a negative balance. |
| Receivables remain uncollected or payables remain unpaid | List accrual accounts, such as receivables and deferred revenue, that still have balances in the final period. |
| Cash receipts and revenue are counted twice, such as using both `working_capital` and settlement terms | Warn when two cash-flow paths map to the same P&L account. |
| Sign error, such as posting an expense as revenue | Warn when a move credits a revenue account or debits an expense account. Explicitly allow exceptions such as returns. |
| Cycle | Detect cycles in the dependency graph before evaluation, report the series in the cycle, and raise an error. Use `solve` to solve supported cycles. |

## KPIs from balance-sheet and quantity accounts

Account balances and moves may be enough to calculate common KPIs from their definitions. This is uncertain; the user shared that uncertainty.

- Average unit price: moves in `acc.revenue.product_a` divided by moves in the quantity account `acc.shipped_units.product_a`.
- Days sales outstanding (DSO): `acc.receivables` balance divided by revenue, multiplied by days in the period.
- Inventory turnover: cost of revenue divided by average inventory balance.
- Churn rate: moves from `acc.customers.basic` to `b.outside`, divided by opening balance.

**Inventory valuation is harder.** Component inventory has separate units for quantity and amount. The amount issued depends on the cost-flow method, such as moving average or FIFO. Beancount records quantity and acquisition cost. One option for boki is to pair quantity and amount accounts and update both with each inventory move. This remains open.

## Equity, loans, and generating all three statements

The user asked on 2026-10-16, "What concepts handle equity, the equity section of the balance sheet, loans, and always producing all three statements?"

### Equity

Represent equity with an account hierarchy. The standard Japanese GAAP chart (`b.jgaap.Accounts`) uses the following structure. The example is written as text; the implementation uses nested classes.

```text
Equity:Shareholders' equity:Share capital
Equity:Shareholders' equity:Capital surplus:Capital reserve
Equity:Shareholders' equity:Retained earnings  <- Revenue and expense balances close here each period during aggregation.
Equity:Shareholders' equity:Treasury shares
Equity:Valuation and translation differences:Foreign currency translation adjustment
Equity:Share options
Equity:Non-controlling interests              <- Consolidation only.
```

Every equity transaction can be represented with a move. Add convenience functions to the standard library.

| Transaction | Move (`src` → `dst`) |
|---|---|
| Capital increase | `acc.share_capital` → `acc.cash`. Whether to transfer up to half to capital reserves is an accounting-policy option. |
| Dividend declaration and payment | `acc.retained_earnings` → `acc.dividends_payable`, then `acc.dividends_payable` → `acc.cash` in the next period |
| Treasury-share purchase | `acc.cash` → `acc.treasury_shares` |

### Loans

`loan` is a helper that creates a loan account and moves for draws, interest, and repayments.

| Event | Move (`src` → `dst`) |
|---|---|
| Draw | `acc.loans.senior` → `acc.cash` |
| Interest (opening balance × rate) | `acc.cash` → `acc.interest_expense`. If paid in arrears, route it through `acc.interest_payable`. |
| Capitalize construction interest | `acc.cash` → `acc.construction_in_progress` (bypasses the P&L) |
| Repayment | `acc.cash` → `acc.loans.senior` |

Repayment methods such as equal principal, bullet repayment, a percentage of principal, and sculpting differ only in the function that creates the repayment series.

### Generate all three statements at any time

The ledger (period, move, source, destination, and amount) is the source of truth. All three statements are views of the ledger and can be produced for any period grouping, including months, quarters, each entity's fiscal periods, and irregular periods.

- **P&L:** Total moves to revenue and expense accounts during the period.
- **BS:** Ending balances of asset, liability, and equity accounts. Retained earnings include profits through that date.
- **CF:** Classify moves that touch cash by the other account.
  - Classify moves against fixed assets and investments as investing CF, moves against loans and equity as financing CF, and other moves as operating CF. The account type determines the section; for example, `b.FixedAsset` maps to investing CF.
  - Whether interest paid appears in operating or financing CF is an accounting-policy option. Japanese GAAP allows either. Override the section on an account with `cf=`.
  - Generate both **direct-method CF**, which shows cash movements, and **indirect-method CF**, which starts with profit and adjusts for depreciation and changes in working capital, from the same ledger.

The engine checks consistency across the three statements each time it builds them.

1. BS: `Assets = Liabilities + Equity`
2. Total CF equals the change in cash balance.
3. P&L net income equals the change in retained earnings minus dividends and other equity transactions.
4. Indirect-method CF equals direct-method CF.

If any check fails, either the engine has a bug or values are being created outside the ledger, such as calculating cash from a series without posting to accounts. Warn users about the latter.

## Accounting standards

Provide a standard chart of accounts for each accounting standard. Entities carry a standard, and boki warns when standards are mixed.

```python
parent = m.entity("Parent", standard=b.JGAAP, fiscal=b.fiscal(year_end="03-31"))
us_sub = m.entity("US subsidiary", standard=b.USGAAP, fiscal=b.fiscal(year_end="12-31"))
eu_sub = m.entity("EU subsidiary", standard=b.IFRS, fiscal=b.fiscal(year_end="12-31"))
```

- **Standard charts of accounts:** `b.jgaap.Accounts`, `b.ifrs.Accounts`, and `b.usgaap.Accounts`. Each standard also defines statement presentation. Japanese GAAP P&L includes operating income, ordinary income, extraordinary items, and income before taxes. IFRS has no ordinary-income or extraordinary-item categories.
- **Accounts carry a standard tag.** Accounts common to all standards, such as cash and receivables, are shared. Standard-specific accounts, such as `special_loss` in Japanese GAAP and `right_of_use_asset` in IFRS, carry their standard's tag.
- **Accounting policy options are standard-specific.** Examples include goodwill (amortized under Japanese GAAP and tested for impairment without amortization under IFRS and US GAAP), the operating or financing classification for interest paid (either is allowed under Japanese GAAP), and leases (IFRS 16 generally requires lessees to recognize right-of-use assets and liabilities). Set a default for each standard and let users override it.

Warn in these cases:

| Situation | Example | Handling |
|---|---|---|
| An entity uses an account from another standard | An entity using Japanese GAAP posts to `ifrs.right_of_use_asset`. | Warning |
| An entity selects a policy its standard does not allow | An IFRS entity amortizes goodwill. | Warning; allow it when the user explicitly requests it. |
| The group consolidates entities with different standards | A Japanese GAAP parent consolidates an IFRS subsidiary. | Warning. Japan permits foreign subsidiaries to use IFRS or US GAAP, but some items, such as goodwill amortization, need adjustment (Practical Issues Task Force Report No. 18; check the original text for applicable items during implementation). |
| A move uses accounts from different standards | A move has one Japanese GAAP account and one IFRS account. | Error. Each move must stay within one entity, so this should not occur. |

Build complete, sourced charts of accounts, presentation rules, and policy options for each standard. Like goal 4 (useful formulas and functions), this area can attract open-source contributions.

## Open questions

- Use nested accounts such as `acc.receivables.product_a` to change aggregation detail. Keep entities separate from accounts, as described in [entities-and-timeline.md](entities-and-timeline.md).
- Should the engine close accounts to retained earnings implicitly, or require an explicit move at period-end?
- How many standard account names for tax, dividends, and equity transactions should layer 3 (single-entity models) define?

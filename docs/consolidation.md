# Consolidation: Partial Ownership, Acquisitions, Equity Method, Unrealized Profits, Opening Balances, and Currency

Status: as of 2026-10-29, S1–S6 are implemented. S7–S8 are designed contracts awaiting implementation. This continues §3 v1 (`counterparty=`, combining wholly owned subsidiaries and eliminating counterpart entries). Astra (gpt-6-astra) independently reviewed the first draft; this version incorporates feedback on standard-specific rules, consolidation mechanics, cash flow, and example assumptions.

User decisions (2026-10-29): support subsidiaries with less than 100% ownership and changes in ownership over time. Specify the equity method explicitly with `method=`; ownership percentage does not determine it. Include unrealized profits on intercompany asset sales. Follow J-GAAP, US GAAP, and IFRS rules for goodwill. Include acquisition-date fair-value adjustments, tax effects, changes in control (step acquisitions and loss of control), OCI, opening intercompany balances, and entities with different currencies. All opening balances are user inputs. Do not support changes in accounting standards during a model. Add features incrementally in separate PRs.

Implementation order: **S1 → S2 → S3 → S5 → S4 → S6 → S7 → S8**. Use the examples in this document as regression-test expectations for each stage. Raise an error for inputs that require unsupported features instead of silently approximating them.

## Shared mechanics

- **Separate books remain entity-specific; consolidation is derived.** Consolidated books (`g.books`) combine three components:
  1. **Replay within the consolidation scope:** replay each member's journal entries only for periods when it is in scope. Exclude periods before acquisition and after loss of control; retain consolidated results for periods before control was lost.
  2. **Elimination of counterpart entries:** eliminate entries for intercompany transactions themselves (sales and purchases, receivables and payables, settlements, loans and borrowings, capital contributions, and dividends). Eliminate **only transaction entries**; keep the buyer's subsequent consumption and depreciation entries and any FX gains or losses. Restrict `_tag` to transaction entries.
  3. **Consolidation entries:** acquisitions, goodwill, fair-value adjustments, non-controlling interests, unrealized profits, equity-method accounting, translation, and more.
- **Ownership over time:** for each entity, the group tracks ownership percentage and method by period, plus **events** for acquisitions, sales, and method changes. Each event takes a **snapshot** of opening balances (net assets, goodwill, non-controlling interests, and OCI components on the acquisition or loss-of-control date).
- **Profit attribution:** consolidated net income closes entirely to retained earnings under the current ledger mechanics. Transfer the non-controlling share from retained earnings to non-controlling interests (debit retained earnings, credit non-controlling interests). P&L rows for net income attributable to non-controlling interests and to parent shareholders display this transfer; they are not journal entries.
- **Cash-flow classification:** classify subsidiary acquisitions and disposals (gaining or losing control) as investing activities, net of the acquired or disposed subsidiary's cash. Classify ownership transactions that retain control and dividends to non-controlling interests as financing activities. Add checks for direct versus indirect cash flow and for classification; the indirect method also includes FX classification.
- **Timing:** ownership changes take place at the **start** of the `since=` period. Acquisition-date balances equal opening balances for that period (the prior period's closing balance, or the model's opening balance for its first period). Start goodwill and fair-value-adjustment amortization **in the acquisition period**, for the full period.
- **Tax rates:** set `m.entity(..., tax_rate=0.3)`. Consolidation entries use this rate for tax effects. Raise an error if a required rate is missing.
- **Standards:** consolidated books use the parent's accounting standard and layout. Assume member layouts match.
- **`entity.currency` is the functional currency** used in that entity's books.

## Explicit v1 assumptions (approximations)

- The user determines whether deferred tax assets are recoverable with `recognized=` (the share to recognize; defaults to all). boki does not assess recoverability.
- For J-GAAP tax effects on unrealized profits, assume the seller has enough taxable income in the year the profit arose; do not cap the amount based on taxable income.
- Use the period-average exchange rate for transactions during the period. Pass the transaction-date rate for dividends and capital transactions with `fx_rate=`; the default is the period average.
- The user supplies goodwill and investment impairment amounts with `impairment=`. boki does not perform impairment tests.

## S1: Tax effects and OCI (separate-book tools)

### Deferred taxes

```python
co = m.entity("Co", tax_rate=0.3)
co.bs.deferred_tax("Depreciation difference", difference, recognized=1.0)   # Period-end temporary difference (positive for taxable, negative for deductible).
```

- Balance = tax rate × temporary difference (deductible differences are also multiplied by `recognized`). A positive balance is a deferred tax liability; a negative balance is a deferred tax asset.
- Changes flow through the income tax adjustment row, an `income_tax` kind: J-GAAP "Income taxes—deferred", US GAAP "Deferred income tax", or IFRS "Deferred tax". Cash does not change.
- Add the BS kinds `deferred_tax_asset` and `deferred_tax_liability` to the layout. They are non-current and non-cash. Use `rate=` to override the tax rate.

Example (S1-a): at a 30% tax rate, temporary differences [100, 150, 50] produce deferred tax liabilities [30, 45, 15] and income tax adjustments [30, 15, −30].

### Other comprehensive income (OCI)

```python
co.oci("Unrealized gain on securities", amount, against=securities, recycle=True, tax=True)
```

- Equity kind `oci` (J-GAAP "Accumulated other comprehensive income", US GAAP "Accumulated other comprehensive income", IFRS "Other components of equity"). Each name has an account (component) and a **`recycle=`** setting that determines whether disposal reclassifies the amount to earnings. If false, transfer it directly to retained earnings, as with IFRS FVOCI equity instruments and defined-benefit remeasurements.
- Transfer OCI against the account specified by `against=`. With `tax=True`, recognize tax at the entity's rate through deferred taxes; OCI is shown net of tax.
- `co.comprehensive_income` = net income + current-period OCI after tax. When OCI exists, show OCI components and comprehensive income below `r.pl(co)` and in Excel statements.
- `co.oci_release(name, amount)` transfers OCI on disposal (`recycle=True` to earnings, false to retained earnings). Used by S4 and S8.

Example (S1-b): at a 30% tax rate, fair-value changes [100, 0, −40] with `tax=True` produce OCI [70, 0, −28], cumulative OCI [70, 70, 42], and deferred tax liabilities [30, 30, 18].

## S2: Partially owned subsidiaries and non-controlling interests (through additional purchases)

```python
g = m.group("Group", parent=parent)
g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY)
g.own(sub, 0.9, since=1, consideration=70 * JPY)        # Additional purchase; control continues.
```

- `method=` is `"consolidate"`, `"equity"`, or `"cost"` (an investment treated as a financial asset). It is required on the first `own` and whenever the method changes.
- **Record each investment once.** `consideration=` records a share purchase from outside the group as an acquisition of "<subsidiary> shares" (`other_asset`) on the parent's separate books. If shares already exist from a capital contribution by the parent (`sub.bs.capital(..., counterparty=parent)`), `own` without `consideration=` uses that balance as the investment. Do not record the same investment twice.
- Acquisition consolidation entry (at the start of `since`): bring in the subsidiary's assets and liabilities at acquisition-date balances; eliminate its equity and the parent's shares; record non-controlling interests = non-controlling percentage × net assets; and goodwill = consideration + non-controlling interests − net assets. Exclude the subsidiary's pre-acquisition income. Classify cash flow as investing: "Acquisition of subsidiary, net of cash acquired."
- Each period: transfer the non-controlling percentage of the subsidiary's net income (after consolidation adjustments) from retained earnings to non-controlling interests. Allocate the same percentage of the subsidiary's OCI to non-controlling interests.
- Subsidiary dividends: eliminate the parent's share as a counterpart entry. Dividends to parties outside the group (without `counterparty`) reduce non-controlling interests and are financing cash flows: "Dividends paid to non-controlling interests."
- **Additional purchases while retaining control** (equity transactions): change in non-controlling interests = −Δ ownership percentage × the subsidiary's consolidated carrying amount of net assets (excluding acquisition-date goodwill under the proportionate method). The difference from consideration changes additional paid-in capital (the `capital` kind account). Goodwill does not change. This also covers buying out the remaining 10% (90% to 100%): non-controlling interests become 0 and the difference goes to additional paid-in capital. Classify cash flow as financing. S2 covers additional purchases only; decreases in ownership (such as 100% to 90%) raise `NotImplementedError` until S4.
- **J-GAAP exception:** parent shareholders bear any subsidiary losses that would make non-controlling interests negative. Subsequent profits first recover the amount borne by the parent. If additional paid-in capital becomes negative, offset it with retained earnings at period-end. US GAAP and IFRS allow negative non-controlling interests.
- **US GAAP** measures non-controlling interests at fair value on acquisition (full goodwill in S3). Before S3, US GAAP acquisitions with less than 100% ownership raise an error.

Presentation:

| | J-GAAP | US GAAP | IFRS |
|---|---|---|---|
| P&L | Net income / net income attributable to non-controlling interests / net income attributable to parent shareholders | Net income / attributable to noncontrolling interests / attributable to <parent> | Profit for the year / attributable to: Owners of the parent, Non-controlling interests |
| BS | Equity: Non-controlling interests | Equity: Noncontrolling interests | Equity: Non-controlling interests |

Example (S2-a, J-GAAP): three annual periods. Parent opening cash: 1,000. Subsidiary opening cash (and net assets): 500; annual cash sales: 100, with no expenses. Acquire 80% for 400 at the start of period 0.

- Goodwill is 0. Non-controlling interests: 120 at the end of period 0, 140 at the end of period 1, and 160 at the end of period 2. Annual income attribution: 80 to parent shareholders and 20 to non-controlling interests.
- Period 0 ending balance sheet: assets 1,200 = parent shareholders' equity 1,080 + non-controlling interests 120.
- Period 0 cash flow: consolidated opening cash 1,000; investing +100 (consideration 400 − cash acquired 500); operating +100; ending cash 1,200.

Example (S2-b, J-GAAP): as in S2-a, plus an additional 10% acquired for 70 at the start of period 1 (80% to 90%).

- Change in non-controlling interests = −0.1 × 600 = −60 (the subsidiary's opening net assets in period 1). The difference, 70 − 60 = 10, reduces additional paid-in capital. Since there is no other additional paid-in capital, offset it with retained earnings at period-end: period 1 ending additional paid-in capital is 0 and retained earnings are 10 lower.
- Non-controlling interests: 60 at the start of period 1, 70 at period-end, and 80 at the end of period 2. Period 1 net income attributable to parent shareholders is 90. Period 1 financing cash flow: −70.
- Period 1 ending balance sheet: assets 1,230 = parent shareholders' equity 1,160 + non-controlling interests 70.

Example (S2-c, IFRS and J-GAAP, losses): use the acquisition terms from S2-a and set the subsidiary's net income to −800 in period 1 and +300 in period 2.

- IFRS: period 1 net loss attributable to non-controlling interests is −160. Ending non-controlling interests are 120 − 160 = −40 (negative balances are allowed). The period 2 share is 60, giving ending non-controlling interests of 20.
- J-GAAP: ending non-controlling interests in period 1 are 0. Parent shareholders bear the excess loss of 40. Of the period 2 share of 60, recover that 40 first; net income attributable to non-controlling interests is 20 and ending non-controlling interests are 20.

## S3: Acquisition-date fair-value adjustments and goodwill

```python
g.own(sub, 0.8, since=0, method="consolidate", consideration=600 * JPY,
      fair_value={sub_land: 100 * JPY, sub_plant: (50 * JPY, 5 * year)},   # Fair-value adjustments; amortizing assets use remaining useful life.
      acquired={"Customer relationships": (40 * JPY, 8 * year)},  # Acquisition-date assets not on the subsidiary's books; liabilities are negative.
      tax_basis="carryover",       # "carryover" (tax basis unchanged, so deferred tax liability) | "stepped_up" (taxable acquisition)
      nci="proportionate",          # IFRS also allows "fair_value" (full goodwill); US GAAP requires "fair_value".
      nci_value=None,               # Acquisition-date fair value of non-controlling interests when nci="fair_value".
      goodwill_life=10 * year,      # Required by J-GAAP (up to 20 years); US GAAP only with private_company=True (up to 10 years); error under IFRS.
      impairment=None)              # Series of goodwill impairment amounts (input).
```

- Fair-value adjustments and acquisition-date assets and liabilities exist only in consolidation. With `tax_basis="carryover"`, record deferred taxes at the tax rate and reverse them as the items are amortized. With `"stepped_up"`, do not record deferred taxes.
- Net assets after fair-value adjustments, N = book net assets + fair-value adjustments + assets and liabilities recognized at acquisition − related deferred taxes.
- Goodwill under the proportionate method (always used by J-GAAP; an IFRS option) = consideration − parent's percentage × N. Full goodwill (always used by US GAAP; an IFRS option) = consideration + `nci_value` − N. Negative goodwill is a gain in the acquisition period: J-GAAP "Gain on negative goodwill"; US GAAP and IFRS "Gain on bargain purchase."
- Amortization: J-GAAP amortizes straight-line over `goodwill_life` as an SGA expense ("Goodwill amortization"). US GAAP amortizes only under the private-company alternative. Pass impairment through `impairment=` (J-GAAP extraordinary loss; US GAAP and IFRS operating expense). After impairment, amortize the remaining carrying amount over the remaining life. Under full goodwill, allocate the non-controlling share of impairment to non-controlling interests.
- Allocate amortization of fair-value adjustments and reversal of deferred taxes to non-controlling interests as adjustments to the subsidiary's income.

Example (S3-a, J-GAAP): the subsidiary's book net assets are 500 (land at book value 200; equipment at 300 with five years remaining). Fair-value adjustments: land +100 and equipment +50 (five years). Tax rate 30%, with carryover basis. Acquire 80% for 600 with `goodwill_life=10*year`.

- Fair-value adjustments are 150, deferred tax liability is 45, and N = 605. Non-controlling interests are 121 and goodwill is 116.
- Each period: additional equipment depreciation of 10 and deferred tax reversal of 3 produce a net −7 adjustment to subsidiary income (−1.4 to non-controlling interests and −5.6 to the parent). Goodwill amortization is 11.6 from period 0, attributable only to parent shareholders. Period 0 ending deferred tax liability is 42 and goodwill is 104.4.

Example (S3-b, IFRS full goodwill): in S3-a, use `nci="fair_value", nci_value=150` and omit `goodwill_life` → goodwill 145, no amortization, and opening non-controlling interests of 150.

Example (S3-c, US GAAP): `nci="proportionate"` raises an error. `goodwill_life` raises an error unless `private_company=True`.

## S5: Equity method

```python
g.own(assoc, 0.3, since=0, method="equity", consideration=200 * JPY,
      goodwill_life=10 * year)
g.own(assoc, 0.4, since=1, method="equity", consideration=80 * JPY,
      fair_value={plant: (50 * JPY, 5 * year)}, tax_basis="carryover",
      goodwill_life=10 * year, impairment=None)
g.own(assoc, 0.3, since=2, method="equity", proceeds=90 * JPY)
```

- Do not include associates in the consolidation replay scope. Do not replay their journal entries or fully eliminate entries whose counterparty is an associate.
- Investment = cost + share of post-acquisition net income (adjusted for fair-value amortization and tax effects) + share of OCI − dividends received − J-GAAP goodwill-equivalent amortization − impairment.
- The initial acquisition and each additional purchase under the equity method create separate basis lots. For a purchase, measure only the increase in ownership (`share - previous_share`) against the associate's opening net assets and consideration. Calculate `fair_value=` and `acquired=` adjustments, tax effects, and embedded goodwill for that lot as of its acquisition date, and amortize from that period. J-GAAP requires `goodwill_life=` for each lot with goodwill. US GAAP amortizes only with `private_company=True`; IFRS does not allow `goodwill_life=`.
- When selling part of an equity-method investment, reduce each lot's remaining share by the sale percentage (interest sold ÷ ownership before sale). Reduce carrying value by the same percentage, including cost, post-acquisition earnings, fair-value adjustments, and embedded goodwill. Allocate subsequent net income and OCI using the remaining share. Set the sale price with `proceeds=`; consolidated gain or loss = proceeds − consolidated carrying amount of the investment sold. Eliminate the gain or loss recorded on the parent's separate books and replace it with the consolidated amount.
- Present partial-sale gains and losses as follows: J-GAAP extraordinary gain "Gain on sale of shares in affiliates" or extraordinary loss "Loss on sale of shares in affiliates"; US GAAP other income or expense "Gain (loss) on sale of investments in affiliates"; IFRS other income or expense "Gain (loss) on disposal of interests in associates." Do not include them in equity-method earnings.
- Recognize losses only until the investment reaches 0 by default (`loss_limit=True`). Track any excess losses and recover them first from later earnings.
- On a partial sale, reduce unrecognized losses by the sale percentage too. Later earnings first recover unrecognized losses on the remaining interest.
- The user supplies impairment through `impairment=`. IFRS treats the entire investment, including goodwill, as one asset. Use the same investment impairment input under J-GAAP and US GAAP.
- Present equity-method earnings as J-GAAP non-operating income (or non-operating expense for losses), "Equity-method investment income"; US GAAP "Equity in earnings of affiliates"; or IFRS "Share of profit of associates." Include the investor's share of OCI in consolidated OCI, preserving its components.
- Dividends received (`counterparty=parent`) reduce the investment rather than income on consolidation. Classify cash dividends received as operating activities, following boki's default. Classify acquisitions, additional purchases, and partial sales of investments as investing activities.

Example (S5-a, J-GAAP): the associate's acquisition-date net assets are 600. Acquire 30% for 200 with `goodwill_life=10*year`. The associate earns 50 and pays dividends of 20 each period; the parent receives 6.

- Goodwill equivalent: 20; annual amortization: 2. Equity-method investment income each period = 15 − 2 = 13. Investment balance: 207 at the end of period 0 and 214 at the end of period 1.

Example (S5-b, loss limit): change S5-a to IFRS (omit `goodwill_life`) and no dividends, making the period 0 investment 200 + 15 = 215. If the associate reports net income of −1,000 in period 1, the investor's share is −300: recognize losses up to the 215 investment and track 85 (investment is 0). With period 2 income of +400, the investor's share is 120: recover 85 and recognize 35 (investment is 35).

Example (S5-c, J-GAAP, two lots and a partial sale): associate net assets are 600. Acquire 30% for 200 and assume annual net income of 50. Period 0 investment = 200 + (30% × 50 − 2) = 213. Buy an additional 10% for 80 at the start of period 1, when net assets are 650. The acquisition-date fair-value adjustment on a plant is 50 with five years remaining. At a 30% tax rate, the deferred tax liability is 15 and the after-tax fair-value adjustment is 35. Embedded goodwill in the second lot = 80 − 10% × (650 + 50 − 15) = 11.5, amortized at 1.15 per year.

- Period 1 equity-method investment income: first lot, 15 − 2 = 13; second lot, 5 − 0.7 − 1.15 = 3.15; total 16.15. Ending period 1 investment is 309.15.
- Sell 10% for 90 at the start of period 2. Sale percentage = 10% ÷ 40% = 25%. Consolidated carrying amount sold = 309.15 × 25% = 77.2875; gain = 12.7125. Eliminate the parent's separate-book gain of 20.
- Remaining ownership is 30%. Period 2 equity-method investment income is 12.1125. Ending investment = 309.15 − 77.2875 + 12.1125 = 243.975.

## S4: Changes in control and disposals

```python
g.own(assoc, 0.7, since=2, method="consolidate", consideration=330 * JPY,
      previously_held_value=180 * JPY)          # Step acquisition: acquisition-date fair value of the existing interest.
g.own(sub, 0.4, since=3, method="equity", proceeds=300 * JPY,
      retained_value=250 * JPY)                 # Loss of control: fair value of the retained interest (US GAAP and IFRS).
g.own(sub, 0.6, since=4, proceeds=90 * JPY)     # Partial sale while retaining control (equity transaction).
```

- **Step acquisition:** remeasure the existing interest at acquisition-date fair value (`previously_held_value`). Recognize the difference in earnings (J-GAAP "Gain (loss) on step acquisition"). Under IFRS, if the existing interest is an FVOCI equity instrument, transfer the difference from OCI to retained earnings without recognizing it in earnings. Goodwill = (consideration + fair value of existing interest + non-controlling interests) − N. Cash flow is net of cash acquired.
- **Loss of control:** remove the subsidiary from the consolidation scope at the start of the period, including its assets, liabilities, goodwill, non-controlling interests, and OCI.
  - US GAAP and IFRS: remeasure any retained interest at fair value (`retained_value`). Gain or loss = consideration received + fair value of retained interest + non-controlling interests − (net assets + goodwill). Treat OCI by component policy (`recycle=True` moves the parent's share to earnings; false moves it to retained earnings. The non-controlling share is removed with non-controlling interests).
  - J-GAAP: if the interest continues under the equity method, keep it at its consolidated carrying amount (ownership percentage × net assets plus remaining goodwill). If it is no longer an associate or subsidiary, use its **separate-book carrying amount** and reverse remaining consolidation adjustments to retained earnings (or OCI for OCI components). Gain or loss is consideration received less the consolidated carrying amount of the interest sold. Reclassify the share of the foreign-currency translation adjustment relating to the interest sold to earnings (S8). Passing `retained_value` raises an error.
  - Classify cash flow as investing, net of the disposed subsidiary's cash.
- Parent's separate books: `proceeds=` records the share sale at average cost and the resulting separate-book gain or loss. On consolidation, eliminate that separate-book amount and replace it with the consolidated gain or loss.
- A partial sale that retains control is an S2 equity transaction (financing cash flow). A partial sale while retaining the equity method is a partial disposal of the equity-method investment.

Example (S4-a, J-GAAP, transition to equity method): in S2-a, sell 40% for 300 at the start of period 2 (80% to 40%). At the end of period 1, the subsidiary has net assets of 700, non-controlling interests of 140, and no goodwill.

- Retained interest = 0.4 × 700 = 280 (consolidated carrying amount). Consolidated gain on sale = 300 − 0.4 × 700 = 20.
- Separate books: cost sold 200, separate-book gain 100. Eliminate 100 and recognize 20 on consolidation. Cash flow: investing 300 − 700 = −400 (subsidiary cash disposed of: 700).
- Period 2: account for the remaining 40% under the equity method (40).

## S6: Intercompany asset sales and unrealized profits

```python
sub.pl.revenue("Parts sale", 100 * JPY, settle=b.delay(1),
               counterparty=parent.bs.inventory, margin=0.3, used=b.delay(1))
sub.pl.revenue("Machine sale", 200 * JPY, counterparty=parent.bs.fixed_asset, margin=0.25, life=5 * year)

machine = parent.bs.fixed_asset("Machine", opening=100 * JPY, depreciation=10 * JPY)
parent.bs.sell(machine, 150 * JPY, at=0, counterparty=sub.bs.fixed_asset, life=5 * year)
```

- The buyer can specify the asset kind. On the buyer's books, inventory enters a "<name> from <seller>" inventory row and moves to COGS through `used=`. Fixed assets are recorded at acquisition cost and depreciated over `life=`. Consumption and depreciation entries are not counterpart entries and are not eliminated.
- For product sales, use `pl.revenue(..., counterparty=buyer.bs.inventory, margin=, used=)` or `counterparty=buyer.bs.fixed_asset, margin=, life=`. The seller supplies `margin=` because the model cannot derive the seller's cost for this transaction alone.
- To sell an existing fixed asset, use `seller.bs.sell(asset_line, price, at=, counterparty=buyer.bs.fixed_asset, life=)` instead of recording revenue. The seller derecognizes the opening book value in `at=` and records the difference from proceeds as a gain or loss. Under J-GAAP, show an extraordinary gain "Gain on sale of fixed assets" or extraordinary loss "Loss on sale of fixed assets". Under US GAAP and IFRS, show other income or expense. The buyer records the asset at the sale price and depreciates it over `life=`.
- Consolidation, after eliminating the transaction entries:
  1. Transfer: debit the asset at the transaction price; credit the same income statement category as the seller's profit (COGS for a product, gain or loss on sale for an existing asset).
  2. Initially eliminate unrealized profit: debit the same category and credit the asset (product: `margin × transaction price`; existing asset: the gain on sale). In the transfer period, the asset equals the seller's cost or book value at sale, and the profit is eliminated.
  3. Realize the profit: reverse unrealized profit through COGS as inventory is consumed, or through depreciation expense as the fixed asset is depreciated (reverse excess depreciation).
- Tax effects (unrealized-profit balance × tax rate):
  - J-GAAP: deferred tax asset at the seller's tax rate (v1 assumes the seller has sufficient taxable income).
  - IFRS: deferred tax at the buyer's tax rate (the buyer's tax basis is the transaction price).
  - US GAAP: for inventory, defer the seller's tax paid as **prepaid income tax**, not as a deferred tax asset. For other assets, use the buyer's tax rate for deferred tax.
- Attribution: downstream transactions (parent is seller) are fully attributable to parent shareholders. Allocate upstream transactions (subsidiary is seller) between parent and non-controlling interests by ownership percentage. For transactions with equity-method associates, eliminate only the investor's share. Under J-GAAP, include the tax effect of upstream transactions in the investment (equity-method earnings).

Example (S6-a, J-GAAP, upstream): the 80%-owned subsidiary in S2-a (tax rate 30%) sells 100 of parts to the parent each period. Subsidiary cost is 70 (COGS 70, margin 0.3), with `used=b.delay(1)`.

- At each period-end: parent separate-book inventory 100, consolidated inventory 70, unrealized profit 30, and deferred tax asset 9. Period 0 unrealized-profit adjustment reduces consolidated net income by 21 (non-controlling interests −4.2, parent −16.8). From period 1 onward, the balance remains 30 (30 realized and 30 generated), with no net income effect.

Example (S6-b, J-GAAP, fixed asset, downstream): the parent sells a machine to the subsidiary for 200 (parent's cost 150, `margin=0.25`, `life=5*year`).

- Consolidated carrying amount at transfer is 150. At the end of period 0: subsidiary separate-book asset 160, consolidated asset 120, depreciation 40 on the subsidiary's books and 30 on consolidation (10 reversal of unrealized profit), remaining unrealized profit 40, and deferred tax asset 12.

## S7: Opening balances at model start (all supplied by the user)

```python
g.own(sub, 0.8, since="before", method="consolidate",
      opening={"goodwill": (50 * JPY, 8 * year),          # Goodwill balance and remaining amortization life (J-GAAP).
               "nci": 130 * JPY,
               "fair_value": {sub_land: 100 * JPY, sub_plant: (40 * JPY, 4 * year)},
               "deferred_tax": 42 * JPY,
               "unrealized": {parent_inventory: (30 * JPY, b.delay(1))},   # Balance and realization schedule.
               "oci": {"Foreign currency translation adjustment": (20 * JPY, 5 * JPY)}, # Parent and non-controlling portions.
               "capital_surplus": 0 * JPY})
sub.bs.loan("Loan from parent", opening=100 * JPY, rate=0.02, repay=20 * JPY, counterparty=parent)
```

- `since="before"` means the acquisition occurred before the model starts. Supply consolidated opening balances and information needed to continue (remaining amortization life, realization schedule, OCI attribution, unrecognized equity-method losses, and historical translation rates) through `opening=`. boki does not calculate from the acquisition date.
- `opening["nci"]` is total opening non-controlling interests, including OCI attributable to non-controlling interests. `opening["oci"][component] = (parent_part, nci_part)` specifies each OCI component. `nci_part` is already included in `nci`; do not add it again. Do not separately reconcile the NCI portion of OCI to `nci`; validate it through the opening balance-sheet check. Release opening OCI before later OCI. For ownership changes that retain control, move cumulative OCI from NCI to the parent for additional purchases, or from the parent to NCI for sales, offsetting the presentation change through additional paid-in capital. `suspended_losses` is the opening balance for the equity method (`method="equity"`).
- Equity-method `opening` requires `investment` (opening carrying amount) and accepts `embedded_goodwill` (an amount or amount with remaining life), `fair_value`, `suspended_losses`, and `oci`. Match `investment` to the parent's opening investment balance. Amortize goodwill and fair-value adjustments over their remaining lives; recover unrecognized losses from later income first. Set equity-method `oci` as `{component: amount}` for cumulative OCI attributable to the group, and transfer it from opening retained earnings to OCI.
- `opening["acquired"]` uses the same format as `acquired=` and adds unrecorded acquisition items as opening balances. `opening["deferred_tax"]` is a net balance: positive for a deferred tax liability, negative for a deferred tax asset. It covers opening balances related to fair-value adjustments and acquired items. Reverse it as those items are amortized or consumed using the subsidiary's tax rate (allocate in proportion to each item's `amount × tax_rate`, and include rounding in the final item). Do not include tax on opening unrealized profits; calculate that separately using the seller and buyer tax treatment in S6.
- Key `opening["unrealized"]` by the buyer's inventory or fixed-asset row. For inventory, give a release kernel; for fixed assets, give remaining useful life. Use `line.counterparty` as the seller when available, otherwise the other entity in this `own()` call. Apply the S6 tax treatment.
- Opening investment and capital balances: create the parent's opening "<subsidiary> shares" balance either through `capital(..., opening=, counterparty=parent)` on the subsidiary (which creates the matching balance on the other side), or with `other_asset(..., opening=)` on the parent and reference it with `own(..., investment=line)`. Use only one approach.
- **Opening reconciliation:** check that the opening consolidated BS (replayed opening balances − eliminations + `opening`) balances. On failure, raise an error showing the difference; do not plug it automatically to retained earnings.
- Opening intercompany balances: allow `opening=` for loans, capital, and receivables with `counterparty=`, create the matching opening balance on the other side, and eliminate both in consolidation.

Example (S7-a): rewrite S2-a as an acquisition before the model starts. Parent opening balances: cash 600 and subsidiary shares 400. Set `opening={"goodwill": 0, "nci": 100}`.

- Ending BS, period income, and profit attribution match S2-a. Cash flow differs: S7-a consolidated opening cash is 1,100, investing cash flow is 0, operating cash flow is +100, and ending cash is 1,200.

## S8: Entities with different currencies

```python
m.fx(USD, JPY, closing=..., average=..., opening=150)   # Closing and period-average rate series (JPY/USD) and opening rate.
us = m.entity("US Inc.", currency=USD, tax_rate=0.21)
g.own(us, 1.0, since=0, method="consolidate", consideration=15_000 * JPY)
```

- Keep the subsidiary's books in its functional currency. Translate into the parent's currency on consolidation using the closing-rate method: assets and liabilities at the closing rate; income and period changes at the average rate (dividends and capital transactions at the transaction-date rate from `fx_rate=`); acquisition-date capital at the acquisition-date rate. Record the difference in the foreign-currency translation adjustment in OCI with `recycle=True`. Attribute the non-controlling share to non-controlling interests.
- Keep goodwill and fair-value adjustments in the subsidiary's currency and translate them at the closing rate. Under the proportionate method, translation differences on goodwill attributable only to the parent belong only to parent shareholders.
- Keep FX gains and losses on intercompany monetary receivables and payables in earnings after eliminating the balances. These are separate-book FX gains and losses, not translation adjustments. For loans treated as part of the net investment (`counterparty=parent, net_investment=True`), move the FX gain or loss to the foreign-currency translation adjustment on consolidation.
- Loss of control:
  - IFRS and US GAAP: reclassify all cumulative foreign-currency translation adjustments attributable to the parent to earnings. Remove the non-controlling share with non-controlling interests, without recognizing it in earnings.
  - J-GAAP: reclassify only the share relating to the interest sold to earnings. If the remaining interest continues under the equity method, retain the rest in the equity-method investment. If it is no longer an investment in an associate, transfer the remainder to retained earnings.
- For acquisitions before `since="before"`, do not replay historical translation. Enter cumulative translation differences through the model start in `opening["oci"]`, split between the parent and NCI, then update translation differences after the start. Enter `opening["nci"]` and `opening["oci"]` in the parent's currency; enter the subsidiary's opening balances, goodwill, and fair-value adjustments in its currency. Use the `opening=` exchange rate to translate balances at the model start.
- For foreign-currency equity-method investments, recognize the investor's share of the associate's translation difference in OCI and adjust the investment carrying amount. If the equity method continues after loss of control, J-GAAP retains translation differences that are not recycled in the investment.
- Include FX classification in indirect cash flow and reconcile it to the direct method.

Example (S8-a): the subsidiary has opening net assets of 100 USD and net income of 10 USD each period, with no dividends. Opening rate 150; period averages [145, 155]; closing rates [150, 160]. Acquire 100% for JPY 15,000, equal to acquisition-date net assets (no goodwill).

- Period 0: income 1,450. Closing net assets 16,500. Foreign-currency translation adjustment = 16,500 − 15,000 − 1,450 = 50.
- Period 1: income 1,550. Closing net assets 19,200. Cumulative foreign-currency translation adjustment is 1,200 (period 1 change: 1,150).

## Stages and checks

| Stage | Scope | Depends on |
|---|---|---|
| [x] S1 | Deferred taxes (`recognized=`), OCI components and `recycle=`, `oci_release`, `tax_rate=`, comprehensive-income presentation, FX in indirect cash flow | — |
| [x] S2 | Ownership over time and events, `own(share, method=, consideration=)`, scoped replay, transaction-only `_tag`, non-controlling interests and transfers, additional purchases (equity transactions), J-GAAP exception, cash-flow classification, presentation | S1 |
| [x] S3 | Fair-value adjustments, acquisition-date assets and liabilities, tax basis, standard-specific goodwill and private-company option, negative goodwill, impairment | S1, S2 |
| [x] S5 | Equity method (lot-level adjustments, OCI, loss limits and recovery, impairment, dividends, additional purchases and partial sales) | S2, S3 |
| [x] S4 | Step acquisitions, loss of control by standard, partial sales, separate-book gains and losses, cash flow | S2, S3, S5 |
| [x] S6 | Asset sales, unrealized profit (classification, realization, standard-specific tax effects), attribution to non-controlling interests and equity-method investments | S1, S2, S5 |
| S7 | Opening balances and continuation data, reconciliation, opening intercompany balances | S2–S6 |
| [x] S8 | Translation, foreign-currency translation adjustment, FX gains and losses on monetary items, net investment, standard-specific recycling | S1, S2, S4, S7 |

Completion criteria for each stage: the examples in this document match hand-calculated regression-test values; consolidated books pass `render()` checks (balance sheet, cash flow equals change in cash, direct equals indirect cash flow, and income equals change in retained earnings); cash-flow classifications are tested; and `to_excel` consolidated statements recalculate to match boki, with Checks passing. Existing tests and the corpus (`excel_all` mismatches: 0) continue to pass. Raise errors for unsupported inputs at each stage. Additional tests to add: losses, partial sales from 100% ownership, entities with different tax rates, OCI disposal, realization of opening unrealized profit, and acquisition/disposal cash flow.

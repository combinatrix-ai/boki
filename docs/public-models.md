# Public models recreated in boki

boki was built by rewriting public financial models line by line and comparing the results with the source
workbooks. The rewritten plans follow their sources cell by cell, so they are kept in a separate repository and
are not published here. This list says what each source is, where it is published, and how far the rewrite
reproduces it.

Recreation status:

- **Matches source**: the plan runs and every value compared with the source agrees.
- **Sketch**: the plan does not match the source yet, for the reason given.
- **Not comparable**: only the structure was written down, for the reason given.

A finding is a place where the source does not agree with itself: a formula that skips a row, a figure that the
same document contradicts, a result that its own table does not reproduce. Each was checked against the
published file; the cell or page is given so it can be checked again. Findings are listed by ID
(`<model>-<n>`).

## Matches source (117)

### 2024 Honeycrisp Enterprise Budget, V-Trellis (orchard establishment and production) (Washington State University School of Economic Sciences Extension)

- URL: https://ses.wsu.edu/enterprise_budgets/
- Recreation status: Matches source (Every row and column of the budget (Table 2.1), App1 capital requirements, App3&4 and App7 depreciation and interest, App6 per-acre costs, App8 amortization, Break-even Return and the Price & Yield table; source figures compared on the source's basis (three inputs set as the source applies them), cost rows also on the plan's basis)
- Note: Per-acre cost and returns of establishing and running a Honeycrisp orchard on an angled V trellis in Washington, Years 1-5 and full production
- Finding [wsu-honeycrisp-1]: Returns apply the pack-out twice: net bins = gross bins x pack-out (24.5 = 49 x 50%), and the $/bin price is $/box x boxes per bin, where boxes per bin (ROUND(825/40 x 50%) = 10) already applies the pack-out. Picking, hauling and packing are charged on the 49 gross bins, and packing at 10 boxes per bin. Total returns are $10,780 / $30,888 / $38,491 (years 4, 5, full production); 49 x $440, 65 x $660 and 81 x $660 give $21,560 / $42,900 / $53,460. (Honeycrisp-Angled V Budget!G4:I7; App9. Data for tables!F4:H4, F62:H64, F67; App5. Estab Costs!E85:F88)
- Finding [wsu-honeycrisp-2]: Netting depreciation ($500/acre) and interest ($250/acre) are charged from year 1, but the netting ($10,000/acre, $260,000 for the block) is bought in year 4. (Honeycrisp-Angled V Budget!D37:F37, D44:F44; App9. Data for tables!F21; App1. Capital Req!F6)
- Finding [wsu-honeycrisp-3]: Full-production thinning is hand thinning only (60 h x $23.75 = $1,425) and leaves out chemical thinning (2 h x $27.79), which every establishment-year thinning line includes; with it the cost is $1,480.58. (App6. Full Prod Costs!E6; App9. Data for tables!H32:H35; App5. Estab Costs!F17, F34, F50, F69, F91)

### ATSI 2026 projected transmission revenue requirement (PTRR) (American Transmission Systems Inc. (FirstEnergy), posted by PJM)

- URL: https://www.pjm.com/markets-and-operations/billing-settlements-and-credit/formula-rates.aspx
- Recreation status: Matches source (Allocators, 13-month average plant, accumulated depreciation and capital structure, ADIT, working capital and rate base, O&M with regulatory asset amortization, depreciation, other taxes, cost of capital, composite tax rate, income taxes, return and gross revenue requirement (Attachment H-21A pages 2-4), the per-project RTEP and MTEP revenue requirements and credits (Appendices D, E), the true-up with interest (Appendix H), net revenue requirement and network and point-to-point rates (page 1), for 2026)
- Note: ATSI's 2026 transmission revenue requirement and rates from rate base, return, income taxes, O&M, depreciation and other taxes, less revenue credits, plus the 2024 true-up

### Aurora Energy CPP financial model with ComCom adjustments - final decision (31 Mar 2021) (Commerce Commission New Zealand)

- URL: https://comcom.govt.nz/regulated-industries/electricity-lines/electricity-distributor-price-quality-paths
- Recreation status: Matches source (RABx (RAB with and without revaluations, depreciation, revaluation, TFVCA), TAXx (profit, permanent differences, tax adjustments, NDI, initial differences, tax losses, taxable income, tax allowance), DTAXx deferred tax, BBARx (subtotals A and B, BBAR before and after tax, RIV) for RY20-RY26, and MARx (MAR path, MAR after tax, NPVs) and the output sheet for RY22-RY26)
- Note: Aurora Energy's maximum allowable revenue for the 2021-2026 CPP: RAB roll-forward, regulatory tax and deferred tax, building blocks revenue, and a CPI-X MAR path NPV-neutral to it

### Ausgrid distribution determination 2024-29 Final decision PTRM (Distribution, Public) (Australian Energy Regulator (AER))

- URL: https://www.aer.gov.au/industry/registers/resources/models/post-tax-revenue-models-transmission-and-distribution-january-2015-amendment
- Recreation status: Matches source (Inflation, nominal and real vanilla WACC, real and nominal capex, real straight-line depreciation, the real and nominal RAB roll-forward, regulatory depreciation, tax depreciation and tax asset base (Assets rows 10-1430), return on equity and debt, opex with debt raising costs, revenue adjustments, tax allowance, imputation credits, taxable income and the annual revenue requirement (Analysis rows 7-56), the discount factors, the solved X5 and smoothed expected revenue (X factors rows 8, 35, 60, 63), each for 2024-25 to 2028-29)
- Note: Ausgrid's annual revenue requirement 2024-29 from the regulatory asset base, return on capital, depreciation, opex and tax, smoothed into expected revenue with X factors

### Automated Milk Collection Centers (Tamil Nadu Agricultural University)

- URL: https://agritech.tnau.ac.in/banking/crbank_nabard_animal.html
- Recreation status: Matches source
- Note: bankable project
- Finding [tnau-milk-collection-1]: The parameter table lists depreciation of 15%, but the year-7 depreciated value of the 1.25-lakh unit is 0.125 lakh (10% of cost); neither 15% straight-line (fully written off) nor 15% declining balance (about 0.40 lakh) gives 0.125. (Annexure I, D.i Depreciation on AMCU (%); Annexure III, row 5 Depreciated Value of AMCS)
- Finding [tnau-milk-collection-2]: In the repayment schedule, 'Total Outgo' equals interest plus principal only in year 1; for years 2-7 it is lower (year 2: 0.214 vs 0.110363 + 0.12 = 0.230363), and the DSCR column does not equal gross surplus divided by either figure (year 2: 1.66 vs 0.4347/0.2304 = 1.887). The stated average DSCR of 1.81 is the mean of that column. (Annexure IV, Total Outgo, Net available and DSCR columns, years II-VII)

### Bank Equity Excess Return Valuation (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Bank equity / regulatory capital

### Biodiesel Cash Flow / Income Statement Worksheet (Montana State University (Extension software downloads))

- URL: https://www.montana.edu/softwaredownloads/financialmgtdownloads.html
- Recreation status: Matches source (Feedstock totals, crushing output, meal revenue, equipment loan and depreciation, operating costs and oil cost (Oilseed Crushing); biodiesel inputs, costs, subsidies and per-gallon summary (Biodiesel Production); cash flow and income statement for both options (IncomeExp_CashFlow))
- Note: Annual cost of on-farm biodiesel from crushed canola and camelina for two equipment sizes, compared with buying diesel
- Finding [montana-biodiesel-1]: Fuel taxes (3,608.20 and 3,808.66) are 0.529 per gallon (0.244 federal + 0.285 Montana) times the oil produced (6,820.80 and 7,199.73 gallons), while the biodiesel produced is 6,870.80 and 7,249.73 gallons. The diesel saving (row 17), the subsidies and the per-gallon summary (Biodiesel Production F143:G143) use the biodiesel gallons; on that basis the tax would be 3,634.65 and 3,835.11. (IncomeExp_CashFlow!C33:D33, G33:H33 (rows 7-8))
- Finding [montana-biodiesel-2]: Cash inflow per gallon (C19:D19, 5.4757 and 5.5083) divides total inflows by the oil produced (row 7); every other per-gallon row on the sheet (G19:H19, C38:D38, C42:D42, G38:H38, G42:H42) divides by the biodiesel produced (row 8). On the biodiesel basis C19:D19 would be 5.4358 and 5.4704. (IncomeExp_CashFlow!C19:D19)

### Bond-implied probability of distress (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Survival probability and distress value

### Break-even and minimum sales template (Queensland Government, Business Queensland)

- URL: https://www.publications.qld.gov.au/dataset/business-queensland-finance-templates
- Recreation status: Matches source (Sales, variable and fixed costs, contribution and gross margin, net profit, break-even in dollars and units, minimum sales, and the 11-column sales volume table)
- Note: Break-even point and minimum sales for a product from its price, variable costs per unit and fixed costs

### Bulk Milk Cooling Centers (Tamil Nadu Agricultural University)

- URL: https://agritech.tnau.ac.in/banking/crbank_nabard_animal.html
- Recreation status: Matches source
- Note: bankable project
- Finding [tnau-milk-cooling-1]: The year-9 depreciated value is 1% of capital cost for the 2,000 L unit (0.118 of 11.78 lakh) but 10% for the 5,000 L unit (1.724 of 17.24 lakh), although both use a 10% depreciation rate. (Annexure IV(A) and IV(B), row 5 Depreciated value; Annexure II C.1 Depreciation (%))
- Finding [tnau-milk-cooling-2]: For the 2,000 L unit the text reports an IRR of 27.89%, while the financial-analysis table gives 29.89%; the table's net benefits give 29.90%. (p.6, text section on Financial Analysis; p.10, Annexure IV(A) row 13)

### Buying vs Raising Replacement Heifers (Colorado State University Extension)

- URL: https://abm.extension.colostate.edu/decision-tools
- Recreation status: Matches source (Beginning cost, breeding, pasture, feed, other, interest and cull sales, the raising total, cost per bred heifer and the advantage of raising on Welcome & Results (breeding, feed, interest and totals adjusted for the two source errors))
- Note: One-year cost of raising 40 bred replacement heifers from 50 retained calves ($3,264 each in the source) against buying them at $3,400
- Finding [csu-replacement-heifers-1]: Breeding cost multiplies the number of bulls by Data Input!F32, which is empty; the annual bull cost ($1,050/bull) is in F31. Breeding costs show $4,875 instead of $4,875 + 3 x $1,050 = $8,025. (Welcome & Results!K12; Data Input!F31:F32)
- Finding [csu-replacement-heifers-2]: Non-pasture feed cost sums AB6:AB12, and AB9, AB10 and AB11 each include the salt and minerals ration (row 19, $855.47), so it is counted three times. The total is $17,920.16; counting it once gives $16,209.22. (Welcome & Results!K14; Data Input!AB9:AB11)

### capbudg.xls (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Finding [damodaran-capbudg-1]: The sheet's NPV (47,927.65) discounts the year-10 cash flow including the salvage of 10,000 for equipment and 14,641 for working capital, while its IRR (23.55%) is computed on the NATCF row without that salvage. With salvage the IRR is 24.91%; without salvage the NPV at 10.685% is 38,999.31. (CapBudgWS!C54 (NPV), C55 (IRR), B49:L49 (NATCF), L34:L35 (salvage), L51 (discounted CF year 10))

### Capital Investment Analysis (Donald W. Lybecker and Karen L. Holman)

- URL: https://www.montana.edu/softwaredownloads/financialmgtdownloads.html
- Recreation status: Matches source (Receipts, expenses, income tax, net receipts, tax depreciation, weighted cost of capital and NPV; loan amortization, after-tax payment and net cash flow for years 0-10 on the Program sheet)
- Note: NPV and cash-flow feasibility of a $24,000 farm machine with 75% loan financing, tax depreciation and inflation
- Finding [montana-capital-investment-2]: The Description sheet says depreciation uses MACRS, but the computed 7-year schedule (6,857.14, 4,897.96, 3,498.54, 2,498.96, 1,784.97, 1,274.98, 3,187.45 on a 24,000 basis) is 200% declining balance over 7 years with no half-year convention and no switch to straight line. The IRS 7-year MACRS table spreads the basis over 8 years, starting at 14.29% (3,429.60) in year 1. (Program!AR8:AX8; Description!B16, B44)

### Carbon Innovation feasibility worked case (Government of Western Australia)

- URL: https://www.wa.gov.au/government/publications/carbon-innovation-grants-program-feasibility-studies-financial-model-case-study
- Recreation status: Matches source
- Note: Carbon Innovation feasibility worked case
- Finding [wa-carbon-feasibility-example-1]: The NPV cell adds the 1,300,000 capital cost to the 3% NPV of the 20 annual savings, giving 3,382,846; with the capital cost subtracted the NPV is 782,846. The IRR cell in the same table treats the capital cost as an outflow. (Project Model!F90, F89, F86, D100:D120)
- Finding [wa-carbon-feasibility-example-2]: Milestone 6 ('Final feasibility report', 10,000) has no CIGP payment formula, while a payment of 10,000 is typed into the 'Final Report Submitted' row; the payment total is 206,156 against a CIGP request of 200,000. With the allocation formula on milestone 6 the total would be 200,000. (Project Model!G43, G49, G50, B21)
- Finding [wa-carbon-feasibility-example-4]: 'Other revenue' is given a unit of $/year (value 5, described as a premium price per tonne of cement), but the formula multiplies it by production volume in PU/year, which treats it as $/PU. (Outputs and Inputs!A51:D51, C69; Project Model!J74)

### Carbon Innovation pilot and capital works worked case (Government of Western Australia)

- URL: https://www.wa.gov.au/government/publications/carbon-innovation-grants-program-pilot-projects-and-capital-works-financial-model-case-study
- Recreation status: Matches source
- Note: Carbon Innovation pilot and capital works worked case
- Finding [wa-carbon-capital-example-1]: 'Decommission current industrial process' (1 x 50,000) sits in a module with sign -1, so it enters eligible costs as -50,000 and receives a grant allocation of -7,299; counted as a cost, eligible costs would be 6,950,000 instead of 6,850,000. (Project Model!H3, H5, Q5, H22, F22, H38)
- Finding [wa-carbon-capital-example-2]: The assumption labels read 'Investment threshold/hurdle rate (WACC = 7.33%)' and 'Discount rate for NPV (WACC = 7.33%)', but the values used are 9% and 5%; the NPV results are discounted at 5%. (Inputs+outputs!C37:G38, E29:E32; Funding!E13)

### Cash flow table, detailed version with preparation steps and worked example (資金繰り表 詳細版【作成手順及び記載例】) (Japan Finance Corporation (日本政策金融公庫), SME Unit)

- URL: https://www.jfc.go.jp/n/service/dl_chusho.html
- Recreation status: Matches source (Operating, non-operating and financing receipts, payments and balances, cash carried forward and the eight balance roll-forwards for six months, and the total column)
- Note: Six-month corporate cash-flow table with receivable, note and loan balances rolled forward from sales, purchases and cash lines

### Cash flow table, filled-in example (資金繰り表（記入例）) (Japan Finance Corporation (日本政策金融公庫), Micro Business and Individual Unit)

- URL: https://www.jfc.go.jp/n/service/dl_kokumin.html
- Recreation status: Matches source (Receipts, payments, operating, non-operating and financing balances and cash carried forward for the four filled-in months)
- Note: Monthly cash-flow table that carries each month's closing cash into the next month

### Cash flow table, simple version with preparation steps and worked example (資金繰り表 簡易版【作成手順及び記載例】) (Japan Finance Corporation (日本政策金融公庫), SME Unit)

- URL: https://www.jfc.go.jp/n/service/dl_chusho.html
- Recreation status: Matches source (Receipts, payments, monthly balance, borrowing, repayments and cash carried forward for six months and the total column, on both sheets)
- Note: Six-month corporate cash-flow table in two layouts of the monthly balance, with cash carried forward

### Cherries - Investment and Gross Margin Analysis (Department of Natural Resources and Environment Tasmania)

- URL: https://nre.tas.gov.au/agriculture/investing-in-irrigation/farm-business-planning-tools
- Recreation status: Matches source (Per-hectare yield, price, income, variable costs and gross margin on Gross margin, establishment cost and the overhead totals on Overheads and capital, and area, production, income, capital, growing, harvest and overhead rows, net cash flow, cumulative cash flow, IRR and peak cash demand for years 0-10 on Investment summary (net cash flow restated with the source's three cash-flow errors))
- Note: Ten-year investment in 10 ha of cherries: $1.8m capital and establishment, $77,850/ha gross margin at full yield, IRR 13.8% in the source
- Finding [tasnre-cherries-1]: Net cash flow subtracts revenue, capital, harvest/packing and overheads but not the cherry-growing variable cost in row 25 ($139,454.50 a year from year 2), so each year's cash flow, the cumulative cash flow and the IRR omit it. (Investment summary!D28:M28, E25:M25, C31)
- Finding [tasnre-cherries-2]: The overhead row is offset by one year relative to the capital rows: year 1 (D27) takes the year-0 overheads ($207,500), year 2 takes year 1's ($183,000), year 0 has no overheads, and year 10's overheads (N17) are not used, while capital in C20 (year 0) takes the year-0 column D37. (Investment summary!C28, D27:M27, C20; Overheads and capital!D17:N17)
- Finding [tasnre-cherries-3]: The year-10 salvage value of $750,000 is added to the capital-cost total and so subtracted from cash flow: year-10 net cash flow is $44,954.50 instead of $794,954.50 + $750,000 = $1,544,954.50. (Investment summary!M22, M23, M28)
- Finding [tasnre-cherries-4]: The year-1 on-cost is 20% of the farm manager only (SUM(E9:E9)), leaving out the supervisor's $60,000 that is in E10, while year 0 takes 20% of both. Year-1 overheads are $183,000; with the supervisor's on-cost they would be $195,000. (Overheads and capital!D11, E11, E17)

### Chorus PQP2 final determination - Demonstration building blocks model (New Zealand Commerce Commission)

- URL: https://comcom.govt.nz/regulated-industries/fibre/projects/chorus-fibre-price-quality-path-from-2025
- Recreation status: Matches source (WACC, RAB roll-forward and adjusted values, Crown financing benefit, asset stranding allowance, return on capital, regulatory profit and tax, tax losses, building blocks revenue, smoothing, wash-up and forecast allowable revenue for 2025-2028)
- Note: Chorus fibre forecast allowable revenue 2025-2028 from the regulatory asset base, return, depreciation, opex and tax, smoothed with CPI and quantity
- Finding [comcom-chorus-pqp2-1]: The tilted-depreciation RAB adjustments do not carry forward: each year's opening adjustment (Inputs F64:H64: 67,115.04, 136,764.43, 206,333.22) exceeds the previous year's closing adjustment (E65:G65: 66,585.72, 136,025.86, 205,446.50) by 529.32, 738.58 and 886.72, so the adjusted opening RAB (Asset F38:H38) exceeds the previous adjusted closing RAB (E42:G42) by those amounts, while the unadjusted RAB carries forward exactly. The adjusted opening RAB drives the return on capital (BBR row 44). (Inputs!E64:H65; Asset!E38:H42; BBR!F29:H29)

### Composite Fish Culture (Tamil Nadu Agricultural University)

- URL: https://agritech.tnau.ac.in/banking/crbank_nabard_fisheries.html
- Recreation status: Matches source
- Note: bankable project
- Finding [tnau-composite-fish-1]: Harvesting charges are computed on 4,000 kg (4,000 x Rs 1.5 = 6,000), while the same sheet gives total production of 4,675 kg. (Annexure II (pp.9-10), item 9 Harvesting charges; C. Production and Income, Total Production)

### Copper mine valuation and real options, problem set 3 solutions (15.997 Practice of Finance) (MIT OpenCourseWare (15.997, MIT Sloan))

- URL: https://ocw.mit.edu/courses/15-997-practice-of-finance-advanced-corporate-risk-management-spring-2009/resources/sol_pset3/
- Recreation status: Matches source (Tree parameters; every node of the copper price, probability, revenue, net cash flow, backward-induction value, abandonment value, abandonment decision and option-value trees; yearly risk-neutral, risk-adjusted and forward-price valuations of revenue, cost and net cash flow)
- Note: Ten-year binomial-tree valuation of a copper mine, with and without the option to abandon

### Cow Herd Budget Model (Iowa State University)

- URL: https://www.extension.iastate.edu/AGDm/decisiontools.html
- Recreation status: Matches source
- Note: financial planning

### CREST Anaerobic Digestion (NREL)

- URL: https://www.nlr.gov/analysis/crest
- Recreation status: Matches source
- Note: Renewable project economics

### CREST Fuel Cell (NREL)

- URL: https://www.nlr.gov/analysis/crest
- Recreation status: Matches source
- Note: Renewable project economics

### CREST Geothermal (NREL)

- URL: https://www.nlr.gov/analysis/crest
- Recreation status: Matches source
- Note: Renewable project economics

### CREST Solar (NREL)

- URL: https://www.nlr.gov/analysis/crest
- Recreation status: Matches source
- Note: Renewable project economics

### CREST Wind (NREL)

- URL: https://www.nlr.gov/analysis/crest
- Recreation status: Matches source
- Note: Renewable project economics
- Finding [nrel-crest-wind-1]: The equity NPV cell applies Excel NPV() to a range that starts with the year-0 equity investment, so every cash flow, including the year-0 investment, is discounted one extra period; the reported 27,001.84 is the year-0 value divided by 1.15. (Cash Flow!D72 (F67:AJ67))
- Finding [nrel-crest-wind-2]: The project's useful life is 20 years, but the cash-flow rows produce a year-21 after-tax equity cash flow of 2,230.31 from 3,750 of interest on the reserve balance carried from year 20, and this year-21 amount is included in the equity IRR and NPV ranges. (Cash Flow!AA22, AA67, AA208; Inputs!G11; D71:D72)
- Finding [nrel-crest-wind-3]: In the 'Simple' cost mode the reserve accounts open with 1,262,906.62 at year 0 (debt-service reserve 686,216.40 + O&M reserve 576,690.22), but no year-0 cash flow funds them: sources are 12.5M debt + 12.5M equity = the 25M installed cost. The reserves still earn interest from year 1 and are released to equity later (e.g. 551,690.22 in year 20). The 'Intermediate' mode adds these reserves to installed cost through Inputs!G20. (Cash Flow!F199:F206, F52, F82, G22, Z47; Inputs!G14, G20, G22, G63:G66, Q66, Q69)

### Culture of Vannamei White Legged Shrimp (Tamil Nadu Agricultural University)

- URL: https://agritech.tnau.ac.in/banking/crbank_nabard_fisheries.html
- Recreation status: Matches source
- Note: bankable project
- Finding [tnau-shrimp-1]: The reported present worth of benefits (196.71 lakh) matches discounting the benefit stream over 14 years at 15%, while the analysis table covers years 1-8; the reported present worth of costs (166.68) is close to but not equal to the 14-year value (166.50). Over 8 years at 15%, PW costs are 129.27, PW benefits 150.71, NPW 21.44 and B/C 1.17, versus the reported NPW 30.03 and B/C 1.18. (Financial Analysis - 1 Ha Model table (p.10): Present Worth of Costs/Benefit, NPW, BCR)

### Dairy - Conventional Dairy Conversion - Investment Analysis (Department of Natural Resources and Environment Tasmania (with Macquarie Franklin))

- URL: https://nre.tas.gov.au/agriculture/investing-in-irrigation/farm-business-planning-tools
- Recreation status: Matches source (Herd, milk solids and feed assumptions, capital development groups, capital investment, debt and equity, income, expense groups, EBIT, interest, net profit and returns on the Profit sheet, and EBIT and net profit at seven milk prices on Sensitivity (capital-dependent results with the two irrigation items the source omits set to zero))
- Note: Steady-state budget for converting a 350 ha farm to a 950-cow irrigated dairy: $10.9m capital, EBIT $581,235 and a 5.3% return on total capital in the source
- Finding [tasnre-dairy-conversion-1]: The centre-pivot line sums pivots 1-3 and the pivot pads but not centre pivot 4 ($67,500), and the pipes line leaves out rock fill for wheel tracks ($1,600). Irrigation development is therefore $495,100, while the itemised total on Capital development is $564,200; total capital, debt, the 5% irrigation replacement allowance, interest and net profit use the lower figure. (Capital investment!H26, H27, H30; Capital development!H65, H68, H79)

### Dairy and Goat Business Projections (2023) (University of Vermont Extension)

- URL: https://www.uvm.edu/extension/goat-dairy-business-calculator
- Recreation status: Matches source (Monthly milk volume, price and milk check, kids, mortalities, cull bucklings, hay, minerals and hired labor, and (with the source's 50% replacement) culls, replacements, doelings, grain, milk replacer, total cash income, cash expenses and net farm income by month and for the year on 12-Month Production and CF, the bred-doe cost, and investing cash flow and year-end cash on Changes to Cash Flow Statement)
- Note: First-year monthly cash budget for a 250-doe goat dairy: $253,495 cash income, $242,361 cash expenses and $335,750 capital in the source
- Finding [uvm-dairy-goat-1]: Row 29 is labelled a 25% replacement rate, but the typed culls and replacements (50 in February, 75 in March; 125 in total) are 50% of the 250-doe herd (25% would be 62.5). The replacement count drives grain, milk replacer, per-head costs and doeling sales. (12-Month Production and CF!B29, E29:F30, P29:P31, C2)

### Dairy Farming — 10 buffaloes (Tamil Nadu Agricultural University)

- URL: https://agritech.tnau.ac.in/banking/crbank_nabard_animal.html
- Recreation status: Matches source
- Note: bankable project
- Finding [tnau-dairy-buffalo-1]: Year-4 milk revenue is 585,000, but the lactation chart gives 210 + 270 = 480 lactation days per animal in year 4, which at 5 animals x 10 L x Rs 26 gives 624,000; the year-4 feed cost (223,200) and concentrate quantity (12,000 kg) use 480 days. (p.6-7, D. Economics, Sale of Milk year 4; C.iii Lactation Chart year IV)
- Finding [tnau-dairy-buffalo-2]: In the loan repayment schedule, the year-4 'Surplus' (after repayment) is 209,380, equal to the gross surplus; gross surplus minus total repayment is 87,736. (p.7, F. Loan Repayment Schedule, year 4, Surplus column)

### Dairy Foods Processing Investment Analysis Tool (Sarah Cornelisse)

- URL: https://extension.psu.edu/dairy-foods-processing-investment-analysis-tool
- Recreation status: Matches source (Investment, retail and wholesale sales, total benefits, raw milk, business operation and total costs, net income and discounted net income for years 1-20 and their totals on Expansion NPV Table, and the present value, NPV and IRR on Input-Output (the IRR as the source computes it, over discounted flows))
- Note: Twenty-year NPV of a $378,526 fluid-milk bottling and delivery investment: present value $300,732 and NPV -$77,794 at 4% in the source
- Finding [psu-dairy-processing-1]: The reported IRR is the IRR of the discounted net incomes (column O), -2.74%. The IRR of the undiscounted net incomes (column N) is 1.15%; -2.74% equals (1 + 1.15%) / (1 + 4%) - 1 at the 4% discount rate. (Input-Output!B5; Expansion NPV Table!N4:O24)

### Default tariff cap level model v1.31 (Ofgem)

- URL: https://www.ofgem.gov.uk/energy-regulation/domestic-and-non-domestic/energy-pricing-rules/energy-price-cap/energy-price-cap-default-tariff-levels
- Recreation status: Matches source (Core operating costs, debt-related costs, EBIT, headroom and total cap level for the Other Payment Method (direct debit) cap, single-rate and multi-register electricity and gas, Nil and benchmark consumption, all 14 regions, July 2025 - December 2026 (calculation sheets rows 25-29 of each region block); the EBIT cost of equity and fixed and variable allowances (3k EBIT rows 13-14, 42-50); and the October-December 2026 cap table with GB averages and dual fuel (1a Default tariff cap C14:J28, H29))
- Note: The GB energy price cap for direct debit customers by region, fuel and consumption level, built up from wholesale, network, policy, operating, debt-related, EBIT and headroom allowances

### Dipaleseng 2020-21 municipal draft budget (Dipaleseng Local Municipality)

- URL: https://www.dipaleseng.gov.za/documents/budget
- Recreation status: Matches source (A1 summary rows 5-50 (financial performance, capital expenditure and funding, financial position totals, cash flows, cash backing) and the subtotals of Tables A4, A5, A6, A7 and A8, for 2016/17-2018/19 audited, all four 2019/20 versions (original, adjusted, full year forecast, pre-audit) and the 2020/21-2022/23 MTREF)
- Note: Dipaleseng's 2020/21 draft MTREF budget in the National Treasury A1 schedule: revenue and expenditure, capital funding, financial position, cash flows and cash backing for 2016/17-2022/23.
- Finding [dipaleseng-municipal-budget-1]: A7-CFlow!E39 (2018/19 opening cash) is typed 3,108,152, which equals A6-FinPos D6 + D7 (2017/18 cash plus call deposits), while the 2017/18 closing balance A7-CFlow!D40 is 3,118,511.42; A8-ResRecon!D6 shows the -10,359.42 gap. (A7-CFlow!E39, D40)
- Finding [dipaleseng-municipal-budget-2]: Capital expenditure by vote (A5-Capex row 40) and by function (A5-Capex row 63, reported in A1-Sum row 27) differ: 2017/18 40,069,338 vs 70,197,826; 2018/19 10,698,065 vs 41,355,881.74; 2019/20 original 159,739,200 vs 145,875,200; 2019/20 adjusted, forecast and pre-audit 13,864,000 vs 145,875,200. (A5-Capex!D40:I40, D63:I63; A1-Sum!C27:H27)
- Finding [dipaleseng-municipal-budget-3]: 2019/20 capital transfers are 145,875,200 in all four versions in A5-Capex!F70:I70 (and A1-Sum!E28:H28), while A4-FinPerf RE!F38:I38 and A7-CFlow rows 10 and 26 (F:I) show 145,875,000. (A5-Capex!F70:I70; A4-FinPerf RE!F38:I38; A7-CFlow!F10:I10, F26:I26)
- Finding [dipaleseng-municipal-budget-4]: A6-FinPos cash plus call deposits does not equal A7-CFlow closing cash in the budget columns: 2019/20 original 13,896,545.31 vs 10,324,059.79; adjusted, forecast and pre-audit 525,693.13 vs 145,693.13; 2020/21-2022/23 525,693.13 each year vs 2,849,903.92, 6,197,222.28 and 10,177,917.77; A8-ResRecon row 6 ('Other current investments > 90 days') carries the difference (2020/21 -2,324,210.80). (A6-FinPos!F6:L7; A7-CFlow!F40:L40; A8-ResRecon!F6:L6)
- Finding [dipaleseng-municipal-budget-5]: A6-FinPos columns J:L (2020/21-2022/23) repeat the 2019/20 adjusted, forecast and pre-audit columns G:I (property, plant and equipment 405,349,359.87, 406,321,359.87, 407,345,847.87; total equity 458,844,459.75, 459,816,459.75, 460,840,947.75), so equity does not move with the budgeted surpluses of 133,912,982.80, 99,943,840.36 and 101,306,167.49 (A4-FinPerf RE!J47:L47). (A6-FinPos!J19:L48)

### Dividend discount valuation (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Dividend payout, ROE, growth stages
- Finding [damodaran-divginzu-1]: The rows labeled 'Earnings per share' and 'Dividends per share' contain whole-company amounts (year 1: 49,552 and 13,463, the aggregate net income and dividends), while the same sheet reports earnings per share of 17.04. (Valuation Output!C14:L14, C16:L16, D6; Inputs!B9:B11)
- Finding [damodaran-divginzu-2]: Year-1 forecast earnings equal the trailing net income of 49,552 with no growth applied, although the sheet shows an expected growth rate of 10.92% for year 1; year-1 dividends likewise equal the current 13,463. Growth is first applied in year 2 (54,965.35 = 49,552 x 1.10925). (Valuation Output!C12, C14, D14, C16, C18)

### Economic value added (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Invested capital, return on capital, economic profit

### EDB DPP4 Financial model (draft determination, 29 May 2024) (New Zealand Commerce Commission)

- URL: https://www.comcom.govt.nz/regulated-industries/electricity-lines/projects/2025-2030-electricity-default-price-quality-path/
- Recreation status: Matches source (For the selected distributor (Vector Lines), TIMING, RAB, TAX, BBAR, MAR and the IRR present values for 2023/24-2029/30; for all 16 distributors, the Outputs data table (PV of BBAR and MAR, starting prices, MAR with both X factors and BBAR 2026-2030, closing RAB 2025-2030, total depreciation 2024-2030, total MAR) and the starting prices in Table 1.1.1 of Outputs to Determination)
- Note: Draft DPP4 starting prices for 16 New Zealand electricity distributors for 2025-2030 from a RAB roll-forward, regulatory tax and building blocks revenue, with CPI-X paths NPV-neutral to it

### Electricity distribution price control financial model V5 (Ofgem)

- URL: https://www.ofgem.gov.uk/guidance/ed2-price-control-financial-model
- Recreation status: Matches source (For the saved licensee SSES, FY2023/24 to FY2027/28 (columns AR:AV): allowed and actual totex by allocation and category (Totex rows 19, 30, 58, 71, 75-82); post-TIM totex, fast and slow money (TIM rows 40, 46, 66, 68); RIIO-2 and total depreciation and net additions (Depn rows 27, 31, 32); opening, closing and discounted RAV, return base and return (Return&RAV rows 17, 23, 30, 43, 46); base revenue, equity issuance costs, calculated revenue before tax, tax allowance and calculated revenue (Revenue rows 12, 14, 19, 20, 22); notional net debt, regearing, equity issuance, interest, accretion, dividends, tax base, tax trigger, tax losses, tax allowance and tax paid (Finance&Tax rows 26, 28, 36, 41, 55, 71, 78, 86, 108, 116, 122, 129, 167, 169, 170, 184, 194, 207, 219, 220, 225, 237, 256, 267, 274, 288, 292, 299); tax pool additions, capital allowances and pool balances (TaxPools rows 46-50, 67, 68, 80, 81, 93, 94, 103, 104, 112); nominal calculated revenue, correction term, recovered revenue, forecasting penalty, time value of money and allowed revenue (AR rows 49, 50, 53, 62, 67))
- Note: SSES's RIIO-ED2 allowed revenue from totex sharing, the RAV roll-forward and WACC return, notional financing and the grossed-up tax allowance

### Engineering economy: modelling uncertainty, session 3-1 part 2 (ESD.70J) (Michel-Alexandre Cardin)

- URL: https://ocw.mit.edu/courses/esd-70j-engineering-economy-module-fall-2009/resources/esd70session3_1part2/
- Recreation status: Matches source (Exponential trend fit, squared errors, SSE, MSE and standard errors and the least-squares regression statistics on the GOOG sheet; deterministic and realized S-curve demand for 24 years, with the source's random draws read as data)
- Note: Estimating growth and volatility of Google's stock price by log-linear regression, and an S-curve demand forecast with random deviations

### Evaluating Organic Transitions — 10 Year (Iowa State University)

- URL: https://www.extension.iastate.edu/AGDm/decisiontools.html
- Recreation status: Matches source
- Note: financial planning

### Farmland Purchase Analysis (Iowa State University)

- URL: https://www.extension.iastate.edu/AGDm/decisiontools.html
- Recreation status: Matches source
- Note: financial planning

### Farmland Tile Drainage Investment Analysis (Iowa State University)

- URL: https://www.extension.iastate.edu/AGDm/decisiontools.html
- Recreation status: Matches source
- Note: financial planning

### Farmplan v3 - Example Farm (Manitoba Agriculture)

- URL: https://gov.mb.ca/agriculture/farm-management/financial-management/index.html
- Recreation status: Matches source (Monthly term-loan payments, cash inflow, outflow, net cash flow and operating loan with interest (Cash Flow); crop closing inventory; cash and accrued net farm income (Income & Exp); ending debts, total assets, liabilities and net worth (Pro-Forma NW))
- Note: One-year whole-farm plan for a Manitoba grain and cow-calf example farm: monthly cash flow and operating loan, accrued income and projected net worth

### FCFE equity valuation (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Reinvestment and equity cash flow

### fcffsimpleginzu.xlsx (FCFF DCF, example: Almarai) (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source

### Financial model - EDB DPP3 final determination (27 Nov 2019) (Commerce Commission New Zealand)

- URL: https://comcom.govt.nz/regulated-industries/electricity-lines/electricity-distributor-price-quality-paths
- Recreation status: Matches source (For the selected distributor (Aurora Energy), TIMING, RAB, TAX, BBAR, MAR and the IRR present values for 2018/19-2024/25; for each of the 16 distributors with results (Powerco is #N/A), the Outputs data table: PV of BBAR and MAR, starting prices, MAR and BBAR 2021-2025, closing RAB 2021-2025, total depreciation 2019-2025 and total MAR)
- Note: Starting prices for 16 New Zealand electricity distributors for 2020-2025 from a RAB roll-forward, regulatory tax and building blocks revenue, with a CPI-X path NPV-neutral to it

### Financial Model for Railways Toolkit v1.1 (PPIAF / World Bank (Railway Reform Toolkit))

- URL: https://ppiaf.org/sites/ppiaf.org/files/documents/toolkits/railways_toolkit/financialmodel.html
- Recreation status: Matches source (Freight company income statement for 2010-2039 (Income statement rows 56-83: revenues, track access and operating costs, non-operating items, EBITDA, depreciation, EBIT, net finance expense, tax, net income), net asset value of the six fixed-asset classes, gross ton-km by traction, capital subsidy amortization, debt service, and the local-currency balance of each of the seven loans (Calculations sheet))
- Note: Thirty-year income statement of the example freight railway company: commodity traffic and indexed tariffs, traffic-driven operating costs, a fixed-asset register by class, and existing and new loans in three currencies
- Finding [ppiaf-railways-1]: The repayment profile of New debt 3 ('Assumptions - Freight'!E532 =IF(F535=F5321,IF(F535=F533,2,3))) refers to the empty cell F5321 and returns FALSE, so none of the repayment branches in Calculations row 438 applies and the R$50 million loan stays outstanding from 2016 to 2039 (Calculations row 445), while New debts 1, 2 and 4 are repaid in full in 2026 (Calculations U378, U408, U468 = 50). ('Assumptions - Freight'!E532; Calculations!E438:AH438, E445:AH445, U378, U408, U468)

### Fish Cold Storage (Tamil Nadu Agricultural University)

- URL: https://agritech.tnau.ac.in/banking/crbank_nabard_fisheries.html
- Recreation status: Matches source
- Note: bankable project
- Finding [tnau-fish-cold-storage-1]: The reported present worth of cost (176.09, 282.18 and 419.77 lakh for 1,000/2,000/3,000 MT) equals the discounted operating costs only and excludes the capital cost (190, 395, 600.5 lakh). Including capital in year 1, present worth of cost is 341.31, 625.66 and 941.95 lakh, giving NPW of about 88.6, 234.1 and 347.7 lakh and B/C of 1.26, 1.37 and 1.37 instead of the reported 253.80/577.60/869.89 and 2.4/3.0/3.1. (pp.19, 21, 23, Annexures III(a), IV(a), V(a): Present worth of cost, NPW, BCR; p.15 summary table)
- Finding [tnau-fish-cold-storage-2]: The 1,000 MT repayment figures do not tie to one loan amount: interest of 14.82 is 12% of 123.5 and falls by 2.96 a year (12% of 24.7, i.e. 123.5 over 5 years), while the principal row repays 22.80 a year (114 in total); 75% of the 167.50 'cost considered for bank loan' is 125.6. (p.18, Annexure III, Interest on Term Loan and Repayment of Term Loan rows; p.17 Annexure II)

### Gas DPP4 final decision modelling suite (27 May 2026) (New Zealand Commerce Commission)

- URL: https://comcom.govt.nz/regulated-industries/gas-pipelines/gas-pipelines-price-quality-paths/gas-pipelines-default-price-quality-path/2026-gas-default-price-quality-path
- Recreation status: Matches source (Financial model, Firstgas Transmission with mitigation (the business the file is saved with): timing factors (Timing rows 24-32), RAB roll-forward of existing and additional assets and the TCSD allowance (RAB rows 28-141), tax asset value, tax depreciation and notional deductible interest (Tax rows 90-125), BBAR with tax payable and its present value (BBAR rows 40-92), and both MAR price paths with their real increases (MAR rows 30-75) for 2025-2031)
- Note: Firstgas Transmission's 2027-2031 building blocks revenue and CPI-X price paths under the Gas DPP4 final decision, with accelerated depreciation of the gas pipeline asset base

### Greenlink Cap and Floor Financial Model (GCFFM1) (Ofgem)

- URL: https://www.ofgem.gov.uk/publications/update-provisional-cap-and-floor-level-greenlink-interconnector
- Recreation status: Matches source (Operational years 1-25 on Op Rav (RAV, depreciation, cap and floor return), Allowances Cap and Floor (unprofiled allowances, actual-floor allowances and debt weighting), Tax Deductions (uplift, pools, capital allowances, notional debt, total deductions), Tax Cap and Tax Floor (profits, losses, tax allowance), and every level on Cap Floor Levels (I8-I38); the actual floor with the source's year-25 debt rate)
- Note: Cap and floor revenue levels for the Greenlink interconnector as 25-year annuities of RAV depreciation, return, opex and tax allowances
- Finding [ofgem-greenlink-cap-floor-1]: Regime year 25 appears on two timeline columns (Inputs AR164 and AS164, 2046 and the partial 2047), and the senior debt cost is taken by SUMIF over that label, so the year-25 rate is the sum of the two columns: AI48 = 6.643% (3.322% + 3.322%) and the real rate AI49 = +2.27% instead of -0.92%. This gives a floor return rate I52 of -1.149% instead of -1.189% and floor levels I28 17.2014 (17.2136 with a single rate), I30 1.3954 (1.4032) and I34/I38 18.5968 (18.6168), £m 2020/21 prices. (Inputs!AR164:AS164, 'Allowances Floor'!AI48:AI49, 'Allowances Floor'!I52, 'Cap Floor Levels'!I28:I38)

### H2A Current Central Hydrogen Production: PEM Electrolysis case study (Nov 2020) (National Laboratory of the Rockies (ex-NREL) / US DOE Hydrogen and Fuel Cell Technologies Office)

- URL: https://www.nlr.gov/hydrogen/h2a-production-models
- Recreation status: Matches source (Hydrogen price (start-up-year nominal E17 and 2016 real E16), after-tax and pre-tax nominal IRR (E20, E21), and every year 2014-2054 of the Cash Flow Analysis rows 65-105 for kg sold, revenue, equity capital, replacements, working capital, land, salvage, decommissioning, fixed O&M, utilities, interest, pre-depreciation income, depreciation, taxable income, taxes, principal, after-tax and pre-tax cash flow, plus the row-114 totals)
- Note: Hydrogen selling price that gives an 8% real after-tax IRR over a 40-year discounted cash flow for a 50 t/day grid-powered PEM electrolysis plant
- Finding [nrel-h2a-pem-1]: The tornado and risk-analysis results are stored values from an earlier run: the base-case hydrogen cost is a typed 2.4111 $/kg ('Tornado Charts & Risk Analysis'!K51, shown in E78, E81, ... E111) and the risk-analysis percentiles range from 2.2951 to 2.5255 $/kg (W14:W34, C195:C196), while the model's current hydrogen cost is 4.8303 $/kg (2016 real; 'Cash Flow Analysis'!E16, Results!C26). ('Tornado Charts & Risk Analysis'!K51, E77:E111, W14:W34, C195:C196; 'Cash Flow Analysis'!E16; Results!C26)

### Heathrow H8 Initial Proposals Price Control Model (31 Mar 2026) (UK Civil Aviation Authority)

- URL: https://www.caa.co.uk/data-and-publications/publications/documents/content/cap3232/
- Recreation status: Matches source (Core H8 engine for 2027-2031: nominal WACC (C_WACC row 90); existing RAB, RAB 1, basic and total RAB roll-forward, indexation and year-average RAB (C_RAB rows 40-156, 333-357); regulatory depreciation (C_RABDep row 255); opex (C_Opex row 85); commercial, ORC and non-aero revenue, return on RAB, asymmetric risk allowance, allowed airport charges, unprofiled yield, price path, profiled revenue and profiling adjustment (C_Revenue rows 24-464); Summary Table rows 4-29 and their H8 totals; discount factor and present values (Macros row 20/26, C_Revenue row 244) for 2027-2028)
- Note: Heathrow's allowed airport charges and yield per passenger for 2027-2031 from the RAB roll-forward, return, depreciation, opex and non-aeronautical revenue, with the profiled price path and its RAB adjustment
- Finding [caa-heathrow-h8-1]: The 'discount factor to start of H8 period' (Macros row 20, e.g. AG20 = MAX(AG19^0.5*AF19, AG19^0.5)) multiplies the mid-year factor by only the previous year's one-year factor, giving 1.03991, 1.12418, 1.12358, 1.12402, 1.12424 for 2027-2031 instead of the compounded 1.03991, 1.12418, 1.21505, 1.31358, 1.42024; the profiling NPV check (Macros!F33 = 1.8e-12) holds at the opening price 30.7986, while with compounded factors the present value of unprofiled charges is 7.41m lower than that of profiled charges and the NPV-neutral opening price is 30.7793. (Macros!AF20:AJ20, Macros!F33, C_Revenue!AF242:AJ244, InpS!F439)
- Finding [caa-heathrow-h8-4]: The CPIH factor used to index airport charges (InpS row 389) is typed to two decimals (1.07, 1.09, 1.11, 1.14, 1.16, 1.18 for 2026-2031) while C_Index row 72 compounds the CPIH rates of InpS row 395 to 1.06654, 1.08947, 1.11213, 1.13559, 1.15978, 1.18448; the H8 price path therefore rises 1.87%, 1.83%, 2.70%, 1.75%, 1.72% (C_Revenue row 250) against CPIH of 2.15%, 2.08%, 2.11%, 2.13%, 2.13%. (InpS!AE389:AJ389, InpS!AF395:AJ395, C_Index!AE72:AJ72, C_Index!AF186:AJ186, C_Revenue!AF250:AJ250)

### Hokkaido startup profit and cash flow plan (Hokkaido Credit Guarantee Corporation)

- URL: https://cgc-hokkaido.or.jp/startup/information.html
- Recreation status: Matches source
- Note: Short and long term profitability and cash financing schedules.

### Income property valuation (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Rent, vacancy, operating costs, debt and equity value

### Integrated Financial Statements with Example (Kansas State University (AgManager.info))

- URL: https://agmanager.info/node/10323
- Recreation status: Matches source (Balance-sheet totals, averages and ratios at Jan. 1 and Dec. 31, the accrual income statement through net farm income and its ratios, and the 2018 monthly cash flow with the operating-loan and cash balances)
- Note: Accrual net farm income of $124,030 for an example Kansas farm in 2017 from its balance sheets and records, and the operating loan its 2018 monthly cash flow needs (peak $463,237 in September)

### Inverness College financial model (Scottish Futures Trust)

- URL: https://contracts.scottishfuturestrust.org.uk/category/npd
- Recreation status: Matches source (The pro-forma formula layer over the values-only engine: PF6_Cashflows rows 5-54 (FY2013-FY2043, nominal totals and XNPV), PF7_Profit and Loss rows 4-36 (FY2013-FY2048, totals and XNPV), PF8_Balance Sheet rows 4-44 (31 March 2013-2043), PF2 surpluses, PF9 sources and uses and the Dashboard construction funding plan)
- Note: Annual cash flow, profit and loss and balance sheet of the Inverness College NPD project company (£40.4m senior debt, £3.97m subordinated debt), from financial close in May 2013 to the end of the 25-year service period
- Finding [sft-inverness-college-1]: PF6_Cashflows!E20 subtracts the pre-close VAT received (Semester Workings!E182, 45,540) in FY2013 only, so PF6 closing cash for FY2013 (E52) is -45,540 against 0 per Semester Workings (E53), and the check row E54 shows -45,540; the two agree from FY2014. (PF6_Cashflows!E20,E52:E54)
- Finding [sft-inverness-college-2]: PF7_Profit and Loss!AJ9:AO9 (Utility costs, FY2043-FY2048, after the last year with operating costs, FY2041) hold the typed values 1 to 6, which add 21 to cost of sales (C12), net profit and retained profit, so retained profit carried forward is 21 (AO35, C35) against 0 per Semester Workings (AO36). (PF7_Profit and Loss!AJ9:AO9)

### Japan Finance Corporation Challenge Support Capital Enhancement Business Plan (original title: 日本政策金融公庫 挑戦支援資本強化 事業計画書)

- URL: https://www.jfc.go.jp/n/service/dl_kokumin.html
- Recreation status: Matches source
- Note: business plan

### JFC Business Startup Plan and Monthly Cash Flow Plan (Japan Finance Corporation)

- URL: https://www.jfc.go.jp/n/service/dl_kokumin.html
- Recreation status: Matches source

### Juba clean water supply project financial model annexes (JICA)

- URL: https://openjicareport.jica.go.jp/pdf/1000054566_02.pdf
- Recreation status: Matches source
- Note: Annex 1 Financial Model. Country and sector to be confirmed from downloaded contents.

### KSU-Beef Replacements (value of replacement females) (Kansas State University (AgManager.info))

- URL: https://agmanager.info/node/10323
- Recreation status: Matches source (The 10-year rows of Net present value (cows, weights, prices, incomes, costs, discount factors, NPV if sold each year), the cow-cost and cull-rate tables, the discount-rate and price sensitivities, and the Sensitivity Table)
- Note: Net present value of a bred replacement heifer bought in 2026, by the year she is sold ($5,273 per head after 10 calves at 8%)

### KSU-Landbuy (Kansas State University Department of Agricultural Economics (AgManager.info))

- URL: https://agmanager.info/node/10323
- Recreation status: Matches source (Calculated outputs (rows 18-38) and the 30-year rent, discounted rent, land value and cash-flow tables (rows 48-77) for crop, pasture, waste and the average acre on KSU-Landbuy; not compared: row 34 and the average column's E21, E29, E31 and E33)
- Note: Present value and approximate returns of buying Kansas cropland and pasture held 30 years (crop: $3,360/acre against a $2,400 price)
- Finding [ksu-landbuy-1]: In the average column, the ag growth rate (2.956%) is the rate that takes the classes' combined after-property-tax rent from now to year 30, but it is applied to the average land value: $2,193.75 x 1.02956^30 = $5,256.76, while the acre-weighted year-30 ag-only values of the classes are $5,082.30. PVSA ($1,499.57 vs $1,454.50 weighted) and AMVP (0.8354 vs 0.8200) follow; the other outputs in the column equal the acre-weighted class values. (KSU-Landbuy!E18, E29, E31, E33)
- Finding [ksu-landbuy-2]: The rent-to-value AMVP in row 34 equals each class's after-property-tax rent-to-value ratio divided by 6.26%, which is Indiana's ag cap rate in the Guidelines table, not Kansas's 6.59%, although the state is KS. With 6.59% the crop value would be 0.4451 instead of 0.4686. (KSU-Landbuy!B34:C34, B5; Guidelines!E8, E19)

### lboval.xls (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Finding [damodaran-lbo-1]: The total cost of the deal is 6,201.9 (201 x 21.9 million shares), but the results table shows the investment by all investors as 6,200, the sum of the financing sources (1,000 equity + 1,700 + 3,500 debt); the 1.9 difference is not funded or explained in the sheet. (Sheet 1!C5, B10:B15, G103; B87)

### LIC Debt Sustainability Framework template (DSF country files) (International Monetary Fund / World Bank)

- URL: https://www.imf.org/external/pubs/ft/dsa/lic.htm
- Recreation status: Matches source (External DSA baseline for 2018-2038: PV of old MLT debt by creditor (Ext_Debt_Data rows 232-261), new-borrowing stock, interest, amortization, PV and grant element for each of 20 creditors (PV_Base, Input 4 column I), total PV of new external MLT debt excluding locally-issued debt, and the external debt dynamics table (Baseline - external rows 12-31 and 52-59))
- Note: External debt of the example 'Country X' for 2018-2038: present value of old and new public external debt by creditor, and the decomposition of the change in the external debt-to-GDP ratio
- Finding [imf-lic-dsf-1]: The PV per 100 and grant element of IDA blend loans (PV_Base rows 45-49; D48 = 64.55) use IDA's repayment schedule (3.3% a year from year 6, 6.8% in years 26-30; J45 = 3.3), while the new IDA debt is repaid in equal instalments over maturity minus grace (PV_Base row 62, J62 = 285.75/25 = 11.43 in 2024); the PV of new IDA debt (row 59) applies the first schedule's factor 64.55 to flows paid on the second, for which the factor would be about 66.50. (PV_Base!D45:BD48, D59:BD62; Ext_Debt_Data!F270:N270)

### LoanPlan calculator (Manitoba Agriculture)

- URL: https://gov.mb.ca/agriculture/farm-management/financial-management/index.html
- Recreation status: Matches source (Calculated payment, the 80-row quarterly schedule (dates, balance, payment, interest, principal) and total paid and interest paid on Sheet1)
- Note: Level-payment amortization of a $100,000 farm loan at 4.875% over 20 years with quarterly payments

### Local Authority Financial Model (council housing self-financing / HRA 30-year business plan) (UK Department for Communities and Local Government (now MHCLG))

- URL: https://www.gov.uk/government/publications/local-council-financial-model-for-council-housing
- Recreation status: Matches source (HRA valuation cash flow 2012-2041 and its NPVs, valuation and indicative debt management, opening debt, debt taken on and indicative debt cap, and the indicative 30-year debt roll-forward, for Adur (Your Authority F9-F22, Debt Total by LA row 16), Luton (Debt Total by LA rows 2-12 and 107, Indicative cash flow by LA rows 10-16) and England (National Debt Total rows 1-11, Debt Total by LA row 198, Indicative national cash flow rows 10-16); M&M and MRA for both councils (Main workings))
- Note: Opening HRA debt for each English council under self-financing (NPV at 6.5% of 30 years of rent less management, maintenance and major repairs) and the indicative 30-year debt roll-forward
- Finding [dclg-hra-self-financing-1]: The per-council output sheets hold Luton's figures while the selected council is Adur: 'Your Authority'!B3 and 'Debt Total by LA'!C2 name Adur, but 'Debt Total by LA'!G2 = 124,797.8 (Luton's opening debt, C107; Adur's is 58,909.2 in C16 and 'Your Authority'!F13), rows 6-12 hold Luton's cash flows (debt management -101.72 = Luton I107), and 'Indicative cash flow by LA'!A1 reads 'Luton'. ('Your Authority'!B3, F13; 'Debt Total by LA'!C2, G2, rows 6-12, C16, C107, I107; 'Indicative cash flow by LA'!A1)

### Lulea research centre financing plan (Lulea University of Technology)

- URL: https://www.ltu.se/forskning/centrumbildningar-och-samarbeten/att-skapa-en-centrumbildning
- Recreation status: Matches source
- Note: Public university financing schedule for creating a research centre.

### Merger synergy valuation (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Combined operations and financing synergy

### MIT equity distribution and dilution (MIT OpenCourseWare)

- URL: https://ocw.mit.edu/courses/15-393-nuts-and-bolts-of-new-ventures-january-iap-2025/resources/mit15_393_iap25_equity_distribution_ses4_part2_xls/
- Recreation status: Matches source
- Note: Nuts and Bolts of New Ventures course financial workbook. Equity example is credited by MIT to Charlie Tillett.

### MIT new venture financial projections (MIT OpenCourseWare)

- URL: https://ocw.mit.edu/courses/15-393-nuts-and-bolts-of-new-ventures-january-iap-2025/resources/mit15_393_iap25_financial_template_ses4_part2_xls/
- Recreation status: Matches source (Whole workbook, 16 quarters (columns E-T): Sales Plan, COGS, Staffing Plan, Expenses, CapEx and cash, quarterly and annual P&L (4 years), Balance Sheet and Cash Flow; year-4 totals compared on the source's basis after the documented rent and telecom differences)
- Note: Quarterly four-year plan for a hardware start-up: unit sales and support revenue, staffing, COGS, departmental expenses, cash and balance sheet.
- Finding [mit-ventures-financial-template-1]: Expenses!Q25:T25 (Rent, source 'See Below') is 300,000 in each year-4 quarter while the budgeted rent in Expenses!Q43:T43 is 225,000; years 1-3 agree. (Expenses!Q25:T25, Q43:T43)
- Finding [mit-ventures-financial-template-2]: Expenses!S26 (Tel & Internet, 200 per employee per month) is 22,400 for year-4 Q3, while the rule applied in the other quarters gives 67,200 for 112 employees (Q26 54,000 for 90, R26 60,000 for 100, T26 73,200 for 122). (Expenses!S26)
- Finding [mit-ventures-financial-template-3]: Together the two year-4 entries make expenses 75,000, 75,000, 30,200 and 75,000 higher per quarter than budgeted rent and the telecom rule give, so year-4 operating profit is 12,034,467.21 (P & L by Year!N24) instead of 12,289,667.21 and year-4 closing cash is 5,372,169.34 (Balance Sheet!T5) instead of the plan's 5,589,869.34. (P & L by Year!N24; Balance Sheet!T5)

### Monthly Profitability of Biodiesel Production (Iowa State University)

- URL: https://www.extension.iastate.edu/AGDm/decisiontools.html
- Recreation status: Matches source
- Note: financial planning

### Monthly Profitability of Ethanol Production (Iowa State University)

- URL: https://www.extension.iastate.edu/AGDm/decisiontools.html
- Recreation status: Matches source
- Note: financial planning

### Natural resource option valuation (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Finite resource reserves and development timing

### nrel sam ppa financial model template historical 2011.xlsm (NREL)

- URL: https://sam.nlr.gov/financial-models
- Recreation status: Matches source (All four structure sheets, years 0-40 (columns B:AP): shared production, O&M, property tax, insurance, salvage, major equipment reserve and replacement depreciation (All Equity Partnership Flip rows 5-41, 358, 611-637); for both partnership flips and the single owner the PPA price and revenue, EBITDA, reserves and interest, investing and pre-tax cash flow, project pre- and after-tax returns with cumulative IRR and NPV, federal ITC, state and federal depreciation, taxable income and tax, negative-benefit years, NPV of revenue and generation and LCOE; constant-DSCR debt (CAFDS, its present value, size, P&I, principal, balance, DSRA) for the leveraged flip and single owner; tax investor and sponsor flows, cumulative IRRs and NPVs, sponsor capital recovery and the year the flip target is reached for the two flips; for the sale leaseback the lessee margin, lease payment, reserves and interest, lessor depreciation, ITC, tax, pre- and after-tax returns, IRRs, NPVs and target year, and the lessee's tax and returns; development fee, financing costs, total installed cost, equity, purchase price and lessee equity on Inputs & Results rows 171-213)
- Note: NREL's 2011 template behind SAM's PPA models: one 10 MW PV project financed as an all-equity flip, a leveraged flip, a sale leaseback and a single owner, each with its own PPA price, debt, tax and investor returns over 40 years.

### Olives - Oil Production - Investment and Gross Margin Analysis (Department of Natural Resources and Environment Tasmania)

- URL: https://nre.tas.gov.au/agriculture/investing-in-irrigation/farm-business-planning-tools
- Recreation status: Matches source (Per-hectare oil yield, drums, income, variable costs, gross margin, maintenance and harvest costs on Gross margin, establishment cost and overhead totals on Overheads and capital, and area, production, income, capital, growing, harvest and overhead rows, net cash flow, cumulative cash flow, IRR and peak cash demand for years 0-20 on Investment summary (costs without lime and net cash flow restated with the source's cash-flow errors))
- Note: Twenty-year investment in 10 ha of olives for oil: $890,000 capital and establishment, $12,280/ha gross margin at full yield, IRR 5.7% in the source
- Finding [tasnre-olive-oil-1]: Total variable costs, maintenance costs and the nutrients summary all start at row 23, so the lime line in row 22 ($25/ha) is in none of them. Variable costs are $10,820/ha; with lime they would be $10,850/ha (after rounding up to $10). (Gross margin!I22, I60, I63, F71)
- Finding [tasnre-olive-oil-2]: Net cash flow does not subtract the olives-growing variable cost in row 24 ($14,981 a year from year 2), so each year's cash flow, the cumulative cash flow and the IRR omit it. (Investment summary!D27:W27, E24:W24, C30)
- Finding [tasnre-olive-oil-3]: The overhead row is offset by one year relative to the capital rows: year 1 (D26) takes the year-0 overheads ($28,000), year 0 has no overheads, and year 20's overheads (X16) are not used, while capital in C19 (year 0) takes the year-0 column D33. (Investment summary!C27, D26:W26, C19; Overheads and capital!D16:X16)
- Finding [tasnre-olive-oil-4]: The year-20 salvage value of $300,000 is added to the capital-cost total and so subtracted from cash flow: year-20 net cash flow is -$188,219 instead of $111,781 + $300,000 = $411,781. (Investment summary!W21, W22, W27)

### Operating lease adjustment (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Lease payment schedule and debt conversion

### Optimal capital structure using adjusted present value (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Unlevered value, tax shield, distress costs

### Optimum Capital Structure — Cost of Capital Approach (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Debt capacity / credit ratings
- Finding [nyu-capital-structure-1]: With indirect bankruptcy costs switched off (Inputs!B34 = 'No'), the worksheet still raises EBITDA from the reported 11,767 to 12,007.14 by dividing it by (1 - 2%), the EBITDA drop assigned to the current A- rating, and uses 12,007.14 at every debt ratio. (Optimal CS Worksheet!F45, F43, K30, B53:K53; Inputs!B11, B34)

### Option to abandon investment (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Downside protection and salvage value

### Option to delay investment (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Option to wait before capital commitment

### Option to expand investment (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Follow-on expansion contingent on initial investment

### P3-VALUE 2.3 Analytical Tool (US DOT Federal Highway Administration (FHWA), Center for Innovative Finance Support)

- URL: https://www.fhwa.dot.gov/ipd/p3/toolkit/analytical_tools/p3_value/
- Recreation status: Matches source (P3 toll concession shadow bid for 2020-2079: transferred costs (Construction rows 167/197, O&M rows 144/173); financing requirement, equity, debt drawdown, fee, IDC, debt commitment, target DSCR, sculpted interest, capitalized interest, repayment, debt balance and DSCR (P3 Financing rows 23-387); MMRA and DSRA (P3 Reserves rows 20-124); cash waterfall (P3 CWF rows 29-58); depreciation, profit before tax and taxes (P3 Depreciation, P3 FinStat row 23, P3 Financing rows 306/316); equity cash flows, NPV at 12% and pre- and post-tax equity IRR (Subsidy & Bid rows 235-260); P3 toll revenue, transferred costs, financing cost and shadow bid NPVs (VfM Output Summary E9-E56))
- Note: Highway toll concession shadow bid: sculpted senior debt sized on CFADS, reserve accounts, taxes and equity returns at a 12% target, and the bid's value-for-money NPVs
- Finding [fhwa-p3-value-1]: The P3 WACC cash flows (P3 Financing rows 419-435; IRRs in F438 and F446) include long-term debt interest during construction (row 423) but not the long-term debt arrangement fee (row 132, 5,066.29 in 2022), which the VfM financing cost (VfM Graph Data row 676, rows 661-675) includes; the WACCs are 7.306% pre-tax and 7.042% post-tax, and 7.385% and 7.121% with the fee. ('P3 Financing'!F438, F446, rows 419-435, L132; 'VfM Graph Data'!661:676)
- Finding [fhwa-p3-value-2]: Interest earned on the MMRA (P3 FinStat row 21) is included in profit before tax (row 23), which sets state and federal tax via P3 Financing row 255, but interest earned on the DSRA (row 25, 3,411.94 in total) is added after profit before tax and is not taxed. ('P3 FinStat'!21, 23, 25; 'P3 Financing'!255)

### Pig Farming — 20 sows and 2 boars (Tamil Nadu Agricultural University)

- URL: https://agritech.tnau.ac.in/banking/crbank_nabard_animal.html
- Recreation status: Matches source
- Note: bankable project
- Finding [tnau-pig-breeding-1]: Year-2 piglet sales of 758,400 correspond to 126.4 pigs at 75 kg x Rs 80, while the projection chart lists 158 piglets available for sale in year 2. (p.7-8, D. Income and expenditure statement, Sale of piglets year II; C. Projection chart year II)
- Finding [tnau-pig-breeding-2]: In the repayment schedule, year-2 'Gross income' is 215,550, while income minus recurring cost plus the recurring cost included in project cost gives 431,550 (779,600 - 898,310 + 550,260); year 1 and years 3-6 follow income minus recurring cost (plus the capitalised amount in year 1). (p.7-8, D. Income and expenditure statement, Gross Income year II; E. Repayment schedule year 2)
- Finding [tnau-pig-breeding-4]: The repayment schedule's outstanding balances do not roll forward from the principal paid: year 4 opens at 619,116 although 1,044,450 - 300,000 = 744,450, year 5 opens at 344,822 versus 419,116, and principal payments total 900,000 against a loan of 1,044,450. Interest is 12% of the stated balance in years 3-6, and year-2 interest (174,145) equals 12% of 1,044,450 plus 12% of the year-1 loan of 406,755. (p.7-8, E. Repayment schedule, Loan outstanding / Interest / Principle columns)

### Poultry Broiler Farming (Tamil Nadu Agricultural University)

- URL: https://agritech.tnau.ac.in/banking/crbank_nabard_animal.html
- Recreation status: Matches source
- Note: bankable project
- Finding [tnau-broiler-1]: Year-1 costs use different batch counts: chicks for 7 batches, feed for 6.67 batches (40 rearing weeks / 6), and medicines and bird insurance for 6 batches, although the flock chart places 7 batches. (p.6-7, D. Income and Expenditure Statement, Year 1 column; C. Flock Chart)
- Finding [tnau-broiler-2]: The project cost table labels the margin as 25%, but the margin of 476,550 is 15% of 3,177,000 (and the parameter table gives Margin 15%); the bank loan of 2,700,450 is 85%. (p.6, A. Project Cost (Margin (25%)); B. Techno Economic Parameters (Margin (%)))
- Finding [tnau-broiler-3]: Capital cost 2,037,500 plus recurring expenditure 1,058,075 totals 3,095,575, but the project cost used for financing is 'Say 3,177,000', 81,425 higher. (p.6, A. Project Cost, Grand Total (A+B) / Say)
- Finding [tnau-broiler-4]: Gunny-bag revenue equals Rs 10 per 750 kg of feed (year 1: 224,400 kg of feed gives 2,992); the publisher's layer model computes Rs 10 per 75 kg of feed. (p.7, D. Income and Expenditure Statement, Sale of gunny bags)
- Finding [tnau-broiler-5]: Repayment-table interest is 12.5% of the opening balance only in year 1 (337,556); for years 2-8 it is about 0.2-0.8% of the balance (year 2: 19,869 on 2,362,894, versus 295,362 at 12.5%), and year-8 interest (4,812) exceeds year 7 (4,811) on a smaller balance. (p.8, E. Repayment Schedule, Interest column)
- Finding [tnau-broiler-6]: The NPW, B/C ratio and IRR discount the three table columns ('1', '2 to 7', '8') as if they were years 1-3, omitting years 3-7 and placing the residual value in year 3. Over all eight years at 15% the NPW is about 3.34 million and the B/C ratio 1.10, versus the reported 803,236 and 1.05. (p.7, E. Calculation of NPV, BCR & IRR)

### Poultry Layer Farming (Tamil Nadu Agricultural University)

- URL: https://agritech.tnau.ac.in/banking/crbank_nabard_animal.html
- Recreation status: Matches source
- Note: bankable project
- Finding [tnau-layer-1]: The year-8 principal repayment is 1,675,641 while the opening balance is 317,907, so scheduled principal totals 9,675,641 against a loan of 8,317,907 (1,357,734 more than the loan). (p.9, F. Repayment Schedule, year 8)

### Power and transmission reserves risk toolkit (Bonneville Power Administration)

- URL: https://www.bpa.gov/energy-and-services/rate-and-tariff-proceedings/bp-26-rate-case
- Recreation status: Matches source (PS and TS end-of-year financial reserves FY25-FY28 for all 2,700 games (TPP sheet columns B-E and N-Q), and the Main sheet summary rows 35-52 for PS and TS (CRAC, RDC, FRP surcharge and revenue financing frequencies and expected values; reserves expected value, 5th-95th percentiles and probability below zero), from the FY00-FY03 roll-forward with BaseMcCf cash flows as inputs)
- Note: BPA's BP-26 financial reserves risk toolkit: 2,700 simulated games of Power and Transmission Services reserves FY25-FY28, with CRAC, FRP surcharge, revenue financing and reserves distribution (RDC) triggers.

### Power revenue requirement (Bonneville Power Administration)

- URL: https://www.bpa.gov/energy-and-services/rate-and-tariff-proceedings/bp-26-rate-case
- Recreation status: Matches source
- Note: Bonneville BP-26 rate case published workbook. External add-ins may be needed to rerun simulations; stored cells only inspected.

### PR19 financial model - South East Water FD (capital allowance update, Apr 2023) (Ofwat (Water Services Regulation Authority))

- URL: https://www.ofwat.gov.uk/regulated-companies/price-review/2019-price-review/
- Recreation status: Matches source (For the WR and WN control sheets in 2020-21 to 2024-25: nominal and real WACC (rows 855, 860, 980), the CPIH-linked, CPIH + RPI wedge linked and additions RCV parts with their run-off and return (rows 808, 819, 871, 957, 968, 991, 1006, 1047, 1054, 1124), total indexation, RCV, run-off and return (rows 1069, 1075, 1097, 1130), PAYG, pension deficit repair, post-financeability adjustments and the revenue requirement before tax (rows 111, 116, 123, 132))
- Note: South East Water's 2020-25 wholesale revenue requirement from an RCV split between CPIH and CPIH + RPI wedge indexation, RCV additions, run-off, PAYG and the real WACC return

### PR24 bill waterfall model (TMS92) (Thames Water)

- URL: https://www.thameswater.co.uk/about-us/regulation/our-five-year-plan/previous-updates
- Recreation status: Matches source
- Note: Regulated water utility business plan

### PR24 Final Determination Financial Model - Anglian Water (FM02) (Ofwat)

- URL: https://www.ofwat.gov.uk/regulated-companies/price-review/2024-price-review/final-determinations/
- Recreation status: Matches source (For each of the four wholesale controls (WR, WN, WWN, BR) in 2025-26 to 2029-30: nominal and real WACC (RCV rows 29-48), the pre-2020, 2020-25 and post-2025 RCV closing balances, additions, run-off and return (RCV rows 99-102, 158-161, 284-287, 352-355, 426-429, 536-539, 587-590, 689-692, 742-745, 873-876), total RCV, run-off and return on capital nominal and real (RCV rows 920-923, 947-950, 976-979, 992-995, 1031-1034, 1009), PAYG (PAYG Calc rows 44-47), revenue requirement before and after tax and allowed revenue real and nominal (PRE wholesale revenues rows 53-56, 120-123, 218-221, 233, 286-289, 302-305), and CPIH inflation (Indexation row 140))
- Note: Anglian Water's 2025-30 wholesale allowed revenue by price control from the CPIH-indexed RCV tranches, run-off, PAYG and the real WACC return
- Finding [ofwat-pr24-anglian-1]: The April CPIH index input for 2030-31 (121.399) is below 2029-30 (148.189) while the year-on-year CPIH input for 2030-31 is 2%; the financial-year index falls from 1.21538 to 0.99611 (-18.04%), giving negative indexation in 2030-31 (WR RCV indexation -195.44) and lowering RCV balances from 2030-31 (WR RCV 1,083.28 in 2029-30, 885.45 in 2030-31); the 2025-30 price control years are unaffected. ('Active inputs'!R2776:S2776, 'Active inputs'!S2752, Indexation!R97:S97, Indexation!S140, RCV!S1203, RCV!R1031:S1031)

### Recirculation Aquaculture Systems Example budget (Indoor Recirculating Aquaculture Analysis) (Kwamena Quagrainie; Ulka Malekar)

- URL: https://ag.purdue.edu/department/agecon/extension/aquaculture/budget.html
- Recreation status: Matches source (Per-cycle costs and receipts (Enter Operation Parameters Here F54:F57, F84, I28, G76); monthly fish sales, operating cost rows, total variable cost, maintenance, administration, loan principal and cumulative cash flow on the Cash Flow sheet for 2012-2021 (120 months); annual rows of Operating-Overhead Cost B3:K19; Income Statement D5:M17 (sales, operating and miscellaneous expenses, depreciation, interest, net farm income from operations), with the tank rental and demand charge the source leaves out added back)
- Note: Indoor recirculating aquaculture farm stocked monthly: per-cycle biomass, feed and energy, a ten-year monthly cash flow and an annual income statement with depreciation and a 5-year loan
- Finding [purdue-recirculating-aquaculture-1]: Oxygen tank rental ($9,000/yr) and electrical demand charge ($1,200/yr) are in total overhead on 'Operating-Overhead Cost'!B16:B19 (B19 = $14,828.53 in 2012) and in 'Enter Operation Parameters Here'!F72, but the Cash Flow overhead block (rows 22-25; O26 = $4,628.53 in 2012), and therefore 'Income Statement'!D10:M10, leave them out; with miscellaneous at 5% of costs, net farm income from operations is $10,710 a year higher than with them. ('Enter Operation Parameters Here'!F66, F67, F72; 'Operating-Overhead Cost'!B16:B19; 'Cash Flow'!O22:O26, O18; 'Income Statement'!D10:M10, D17:M17)
- Finding [purdue-recirculating-aquaculture-2]: The monthly Cash Flow leaves out miscellaneous cost (only the annual total 'Cash Flow'!O18 is filled, so the cumulative row 30 excludes it) and loan interest (row 28 carries principal only), while the Income Statement charges miscellaneous cost in D11 and interest in the loan-repayment lines D14/D16. ('Cash Flow'!C18:N18, O18, C28:N28, C30:N30; 'Income Statement'!D11, D13, D14)
- Finding [purdue-recirculating-aquaculture-3]: Loan principal is straight-line ('Enter Operation Parameters Here'!M81:Q81 = F76/5 = $18,300.48 a year) while interest (M76:Q76) is IPMT of a level-payment loan (G76 = $23,524.58 a year; level-payment principal in year 1 = $15,289.36); under straight-line repayment year-2 interest would be $6,588.17, not $6,859.17. ('Enter Operation Parameters Here'!M76:Q76, M81:Q81, G76)
- Finding [purdue-recirculating-aquaculture-4]: 'Cash Flow'!O28 = SUM(F28:N28) adds April-December only ($13,725.36) while C28:N28 hold twelve monthly payments of $1,525.04 ($18,300.48, used in the cumulative cash flow); 'Income Statement'!D14 uses the nine-month figure. ('Cash Flow'!O28, C28:N28; 'Income Statement'!D14)
- Finding [purdue-recirculating-aquaculture-6]: Total Capital Investment 'Enter Operation Parameters Here'!D28 = SUM(D5:D27) adds the unit-cost column ($114,378), not the cost column F ($116,824, which multiplies tank plywood 28 x 258, water storage 750 x 3, purge tanks, agitators and blowers by quantity and includes $5,000 labour); the loan F76 = 80% of D28 = $91,502.40 (80% of the cost column would be $93,459.20). ('Enter Operation Parameters Here'!D28, F5:F27, F76)
- Finding [purdue-recirculating-aquaculture-7]: Well & motor has unit cost D25 $20,000 x 1, but its cost F25 is typed $2,500 (salvage H25 typed $1), so depreciation (I25 = $124.95) uses $2,500 while D28 includes $20,000. ('Enter Operation Parameters Here'!D25, E25, F25, H25, I25)
- Finding [purdue-recirculating-aquaculture-8]: Maintenance, labelled 'Maintenance (3% of cap inv)', is D68 = 0.03 x yearly depreciation I28 x 12 = $2,504.50, while 3% of the capital investment D28 is $3,431.34. ('Enter Operation Parameters Here'!B68, C68, D68, I28, D28)
- Finding [purdue-recirculating-aquaculture-9]: Insurance: D69 holds 0.1 next to the label '3% of TCI' (C69), but the Cash Flow (row 23) and 'Operating-Overhead Cost'!B14 read the empty G69, so insurance is 0. ('Enter Operation Parameters Here'!C69, D69, G69; 'Cash Flow'!C23:N23; 'Operating-Overhead Cost'!B14:K14)
- Finding [purdue-recirculating-aquaculture-10]: Depreciation is $6,956.95 in every year 2012-2021 ('Income Statement'!D12:M12 = I28), although the blower and miscellaneous equipment have 5 years of use: over ten years the blower is depreciated $3,420 on a depreciable $1,710 and the miscellaneous equipment $4,500 on $2,250, with no replacement in the cash flow. ('Income Statement'!D12:M12; 'Enter Operation Parameters Here'!I15, I26, I28, G15, G26)
- Finding [purdue-recirculating-aquaculture-13]: The schedule helper 'Cash Flow'!X5:AI5 lists 'Stock P2' in all twelve months of 2012 (AJ5 = 12, typed), including January, the month of the first nursery stocking (phase 1 lasts 30 days, SpecieData!I17), while harvests start in May (8 in 2012); the 2012 feed cost ('Operating-Overhead Cost'!B4 = $6,766.53) uses that count. ('Cash Flow'!X5:AJ5; 'Operating-Overhead Cost'!B4; 'Enter Systems Parameters Here'!B38:M39)

### RIIO-3 Final Determinations Electricity Transmission Business Plan Financial Model (Ofgem)

- URL: https://www.ofgem.gov.uk/decision/riio-3-final-determinations-electricity-transmission-gas-distribution-and-gas-transmission-sectors
- Recreation status: Matches source (For the licensee with saved calculations (SHET), FY2026/27-FY2030/31 (columns AU:AY): fast and slow money (TIM rows 107, 109); inflation, semi-nominal and nominal WACC, RAV indexation, depreciation, nominal RAV roll-forward, real closing RAV, NPV-neutral return base and return (Return&RAV rows 20-102, 350-371); base, pre-tax and calculated revenue (Revenue rows 15, 22, 26); nominal calculated revenue, legacy revenue, correction term, forecasting penalty and allowed revenue (AR rows 22-87); notional net debt with the RIIO-3 regearing, late equity issuance, interest and accretion, dividends, tax base, tax losses, tax allowance and tax paid (Finance&Tax rows 43-323); capital allowances (TaxPools rows 61-127); EBITDA, EBIT, PAT, FFO, RCF, capex, equity issuance and regulated equity (FinancialStatements rows 46-154); and the notional credit and equity ratios (FinancialRatios rows 20-111))
- Note: SHET's RIIO-3 allowed revenue for 2026/27-2030/31 from a semi-nominal RAV, return, fast money, incentives and tax allowance, with the notional company's debt, tax and credit ratios at 55% gearing

### RIIO-3 Final Determinations Gas Distribution Business Plan Financial Model (Ofgem)

- URL: https://www.ofgem.gov.uk/decision/riio-3-final-determinations-electricity-transmission-gas-distribution-and-gas-transmission-sectors
- Recreation status: Matches source (For the licensee with saved calculations (East), FY2026/27-FY2030/31 (columns AU:AY): fast and slow money over three TIM pools (TIM rows 107, 109); inflation, WACC, RAV indexation, sum-of-digits depreciation of RIIO-3 additions, nominal RAV roll-forward, real closing RAV, return base and return (Return&RAV rows 24-247); base, pre-tax and calculated revenue with the revenue profiling adjustment (Revenue rows 15-27, MainInputs row 348 for 2026/27-2029/30); allowed revenue (AR rows 22-87); notional net debt, regearing, constant gearing dividends, interest, tax losses, tax allowance and tax paid (Finance&Tax rows 42-313); capital allowances (TaxPools rows 59-124); the notional company's revenue, EBITDA, PAT, FFO and RCF (FinRatios RoRE decomposition rows 46-53); the published statements and ratios (FinancialStatements rows 46-155, FinancialRatios rows 21-109), which add the profiling adjustment)
- Note: Cadent East's RIIO-3 allowed revenue for 2026/27-2030/31 from a semi-nominal RAV, return, fast money and tax allowance, with revenue profiling and the notional company's debt, tax and credit ratios at 60% gearing
- Finding [ofgem-riio3-gd-1]: The revenue profiling adjustment (Revenue AU26:AY26) is included in calculated revenue and in FinancialStatements operating revenue (row 100) but not in notional net debt or the tax base (Finance&Tax rows 43 and 237 take Revenue row 23) nor in the FinRatios RoRE decomposition, so the workbook's checks are non-zero for FY2026/27-FY2030/31: FinancialStatements AU159:AY159 = -46.251, -13.4125, 4.563, 22.1257, 46.8897 (the profiling adjustment in nominal terms) and AU93:AY93 the same with opposite sign; AU49:AY49 = 46.251, 59.664, 55.101, 32.975, -13.915 (cumulative); FinRatios RoRE decomposition AU56:AY61 = 42.2545, 12, -4, -19, -39.4423 (£m 2023/24); RoRE checks rows 125 and 144 differ from FinancialRatios rows 91 and 99 by up to 2.5 percentage points. These feed Checks rows 8, 10, 11 and 15-22, which are FALSE. (Revenue!AU26:AY26, 'Finance&Tax'!AU43:AY43, 'Finance&Tax'!AU237:AY237, FinancialStatements!AU49:AY49, FinancialStatements!AU93:AY93, FinancialStatements!AU159:AY159, 'FinRatios RoRE decomposition'!AU56:AY61, 'FinRatios RoRE decomposition'!AU125:AY125, 'FinRatios RoRE decomposition'!AU144:AY144)
- Finding [ofgem-riio3-gd-2]: Revenue AY26 reads MainInputs AZ344 (39.44232, the amount that closes the profiling time-value account) while AU26:AX26 read row 343; the account itself uses the input AY343 (39.43989), so it closes at -0.00244 (MainInputs AY348) while the revenue applied would close it at zero. (Revenue!AY26, MainInputs!AY343, MainInputs!AZ344, MainInputs!AY347:AY348)

### sam cash flow sample residential 2020 2 29.xlsx (NREL (System Advisor Model))

- URL: https://sam.nlr.gov/financial-models
- Recreation status: Matches source (Cash Flow rows 14-47 (O&M, insurance, property tax, operating expenses, loan interest/principal, pre-tax cash flow), 81-109 (state and federal tax, federal ITC, after-tax costs and cash flow), 113-121 (payback cash flows) for years 0-25; debt and equity; LCOE real and nominal, NPV, payback and discounted payback (Inputs and Outputs E7-E11, Cash Flow C117/C123))
- Note: Homeowner economics of a 4.7 kW rooftop PV system bought with a 25-year loan: bill savings, mortgage-interest tax deductions, the federal ITC, LCOE, NPV and payback

### sam cashflow sampe ppa all equity partnership flip 2022 11 21.xlsx (NREL (System Advisor Model))

- URL: https://sam.nlr.gov/financial-models
- Recreation status: Matches source (Cash Flow sheet, years 0-25 (columns B:AA): PPA price, O&M, EBITDA, capital costs at closing, working capital and major equipment reserves with interest, investing cash flow, equity, distributions, project pre- and after-tax returns, IRR to date and NPV (rows 16-141); LCOE and levelized PPA price (rows 144-154); developer capital recovery, developer and tax investor equity, cash, ITC and tax shares, after-tax returns, IRRs to date and NPVs (rows 166-207); depreciable basis allocation, ITC qualifying costs, replacement depreciation, state and federal depreciation, taxable income and tax (rows 214-434); reserve rows 668-773; Inputs F13-F20)
- Note: A 100 MW PV project owned by a tax investor and a developer in an all-equity partnership flip: the developer recovers its capital first, the investor takes most cash and tax benefits until its IRR target is reached in year 17, and the plan reproduces each partner's after-tax returns and IRR to date.

### sam cashflow sampe ppa leveraged partnership flip 2022 11 21.xlsx (NREL (System Advisor Model))

- URL: https://sam.nlr.gov/financial-models
- Recreation status: Matches source (Cash Flow sheet, years 0-25 (columns B:AA): PPA price, O&M, EBITDA, capital costs at closing, working capital, debt service and major equipment reserves with interest, investing cash flow, equity, distributions, project pre- and after-tax returns, IRR to date and NPV (rows 16-141); LCOE and levelized PPA price (rows 144-154); developer and tax investor equity, cash, ITC and tax shares, after-tax returns, IRRs to date and NPVs (rows 172-207); depreciable basis allocation, ITC qualifying costs, replacement depreciation, state and federal depreciation, taxable income and tax (rows 214-434); term debt CAFDS, present value, size at DSCR 1.3, P&I, interest, principal and balance (rows 632-647); debt service reserve against 6 months of next P&I (row 662); Inputs F15-F23)
- Note: A 100 MW PV project owned by a tax investor and a developer in a leveraged partnership flip with 18-year debt sized to a 1.3 DSCR; the investor's IRR to date stays below the flip target, and the plan reproduces the debt schedule and each partner's after-tax returns.

### sam cashflow sample commercial 2022 11 21.xlsx (NREL (System Advisor Model))

- URL: https://sam.nlr.gov/financial-models
- Recreation status: Matches source (Cash Flow rows 14-47, 77-124 and 128-136 for years 0-25 (operating costs, loan, ITC, depreciation basis and MACRS depreciation, state and federal tax, after-tax cash flow, payback cash flows); LCOE real and nominal, NPV, payback and discounted payback (Inputs and Outputs E7-E11); state-tax rows from year 2 with the source's row-95 range error reproduced by a switch)
- Note: A business's economics of a 540 kW rooftop PV system bought with a 25-year loan: bill savings, MACRS depreciation, the federal ITC, state and federal tax, LCOE, NPV and payback
- Finding [sam-cashflow-sample-commercial-2022-11-21-1]: State total deductions use SUM(C89,C93:C94) in year 1 and SUM(D89:D94) in years 2-25, which also adds the depreciation percentage in row 91 (0.32 in year 2, 0.192 in year 3, ...); D95 is 335,973.17 against 335,972.85 for operating expenses plus depreciation plus interest, giving after-tax cash flow in year 2 of 53,072.5478 instead of 53,072.5301, NPV 293,402.0323 instead of 293,401.9987 and payback 13.0535212 instead of 13.0535221 years. (Cash Flow!D95:AA95 (row 91))

### sam cashflow sample merchant plant 2022 11 21.xlsx (NREL (System Advisor Model))

- URL: https://sam.nlr.gov/financial-models
- Recreation status: Matches source (Cash Flow sheet, years 0-25: revenue, expenses and EBITDA, major equipment reserve, CAFDS, sculpted debt (P&I, interest, principal, balance, size), DSRA, working capital reserve and reserve interest, capital cost and equity, operating/investing/financing and pre-tax cash flow, ITC, depreciable basis by class, replacement and total tax depreciation, state and federal taxable income and tax, after-tax returns, running IRR, NPV, annual costs, LCOE and levelized revenue (Inputs F9-F18))
- Note: A 100 MW merchant PV project selling at market prices with sculpted debt, reserves, ITC and MACRS: after-tax IRR, NPV and LCOE

### sam cashflow sample ppa sale leaseback 2022 11 21.xlsx (NREL (System Advisor Model))

- URL: https://sam.nlr.gov/financial-models
- Recreation status: Matches source (Cash Flow sheet, years 0-25: revenue, expenses and developer margin, purchase and sale of the plant, reserves and reserve interest, lessee cash flow and lease payment, investor depreciable basis, tax depreciation, state and federal tax, ITC, pre- and after-tax returns, running IRR and NPV, developer pre-tax returns, taxes, development-fee tax, after-tax returns and NPV, annual costs, LCOE and levelized PPA price (Inputs F11-F19))
- Note: A 100 MW PV project sold to a tax investor and leased back by the developer: investor and developer after-tax returns, IRR, NPV and LCOE

### sam cashflow sample ppa single owner 2022 11 21.xlsx (NREL (System Advisor Model))

- URL: https://sam.nlr.gov/financial-models
- Recreation status: Matches source (Cash Flow sheet, years 0-25: revenue, expenses and EBITDA, major equipment reserve, CAFDS, sculpted debt (P&I, interest, principal, balance, size), DSRA, working capital reserve and reserve interest, capital cost and equity, operating/investing/financing and pre-tax cash flow, ITC, depreciable basis by class, replacement and total tax depreciation, state and federal taxable income and tax, after-tax returns, running IRR, NPV, annual costs, LCOE and levelized PPA price (Inputs F11-F21))
- Note: A 100 MW single-owner PV project under a PPA with sculpted debt, reserves, ITC and MACRS: after-tax IRR, NPV, LCOE and levelized PPA price

### sam cashflow sample third party host developer 2022 11 21.xlsx (NREL (System Advisor Model))

- URL: https://sam.nlr.gov/financial-models
- Recreation status: Matches source (Cash Flow years 0-25: developer revenue, O&M, EBITDA, reserves (rows 87-130, 599-647, 740), sculpted debt (rows 599-622), depreciation bases by class (Q258-Q263, Q394-Q399) and tax depreciation (rows 181, 218, 337), state and federal taxable income and tax, ITC, after-tax cash flow (row 145), running IRR in years 20 and 25, year target IRR reached, developer NPV, LCOE and levelized PPA price (rows 153-166, Inputs F11-F13); host savings, indifference point and levelized indifference point; host payments, cash flow, cumulative payback and NPV (rows 20-23, Inputs F14) with the source's PPA price row reproduced by a switch)
- Note: Third-party ownership of a 540 kW PV system: the developer's PPA project with sculpted debt, reserves, MACRS depreciation and the ITC, and the host's savings under the PPA
- Finding [sam-cashflow-sample-third-party-host-developer-2022-11-21-1]: The PPA price row has no values for years 1-3 (Inputs D156:F156 empty; G156 = 11.4017 c/kWh is year 4), so the host's agreement cost (Cash Flow row 20) is 0 in years 1-3 while the developer's PPA revenue (row 29) is 103,865, 104,379 and 104,895; the host NPV (Inputs F14) is -141,926 and would be -405,786 if the host paid the PPA revenue in every year, and 'PPA price, year 1' (F9) shows 0. (Inputs!D156:F156; Cash Flow!C19:E20, C28:E29; Inputs!F9, F14)

### Sheep Farming (Tamil Nadu Agricultural University)

- URL: https://agritech.tnau.ac.in/banking/crbank_nabard_animal.html
- Recreation status: Matches source
- Note: bankable project
- Finding [tnau-sheep-1]: Ram feed and insurance use ewe rates: feed for 4 rams is 3,092.6 (4 x 773.15, the ewe rate) although ram feed is listed at 739.55 per head, and insurance (18,720 = 104 x 4,500 x 4%) values rams at the ewe price of 4,500 rather than the ram cost of 5,500. (C. Cash flow statement, Cost of feed - Male adult and Insurance rows; feed consumption table; A. Project Cost)
- Finding [tnau-sheep-2]: Lamb feed and medicine costs use non-integer lamb counts equal to 90% of the ewes at lambing from year 2 (e.g. 85.5 = 0.9 x 95, 193.5 = 0.9 x 215), which differ from the projection table's lambs born (86, 194, 108 ...) and from the stated 80% lambing rate. (C. Cash flow statement, Lambs feed and Cost of medicines for kids rows; flock table; B. parameter 12 Lambing 80%)
- Finding [tnau-sheep-3]: Skin sales equal ewes x 5% x Rs 150 plus lambs x 15% x Rs 100 in years 1, 2, 4 and 7, but not in years 3, 5 and 6 (year 3: 3,832.5 versus 4,515 by the same rule). (C. Cash flow statement, Sale of skins row)
- Finding [tnau-sheep-4]: The 10% revenue-decrease sensitivity adds the 719,000 salvage value in year 6, while the base case adds it in year 7; the reported sensitivity IRR (30.47%) uses this placement. (C. Sensitivity analysis, Net profit row (years 6 and 7))

### SSFA Securitization Capital Job Aid (Federal Reserve Board)

- URL: https://www.federalreserve.gov/supervisionreg/srletters/SR1504.htm
- Recreation status: Matches source
- Note: Regulatory securitization capital

### Start-up / restart plan, input sheet with filled example (創業・再挑戦計画書（R3.8改正）入力用・記入例) (Nagano Credit Guarantee Corporation (長野県信用保証協会))

- URL: https://www.nagano-cgc.or.jp/service/dl/
- Recreation status: Matches source (Funds needed and raised, and both periods' sales, cost of sales, each expense line, total expenses and profit for the four filled-in examples (used-car retail: second-period cost of sales, staff, other expenses, total and profit not compared))
- Note: Start-up plans for four small businesses: funds needed and raised, and a two-period income plan built from seats, turns, prices and monthly costs
- Finding [cgc-nagano-startup-plan-1]: Used-car retail, second period: cost of sales is 23,625 (X102) while the stated basis, 75% of sales of 31,700, gives 23,775; staff costs are 600 (X105) and other expenses 2,400 (X111) while the stated 60 thousand yen a month each gives 720. Total expenses (4,784) and profit (3,291) follow the typed figures; on the stated basis they would be 3,224 and 4,701. (記入例（自動車小売）!X102, X105, X111, X117, X119; basis AF99)

### Taranaki ironsand project financial assessment (Whanganui District Council)

- URL: https://www.fasttrack.govt.nz/__data/assets/pdf_file/0015/13263/Whanganui-District-Council-Appendix-financial-model-assessment.pdf
- Recreation status: Matches source
- Note: Independent assessment including ten-year project discounted cash-flow tables; retains critique and assumptions.
- Finding [nz-ttr-ironsand-assessment-1]: Principal repayments total 679.7 against a loan of 671.5. After year-9 repayments the remaining balance is 106.9, but year 10 repays 115.1 and shows no interest charge (7.6% of 106.9 would be 8.1). (PDF p.16 Table 4 (repeated as Attachment 8, p.33): Financing Principal repayments and Interest rows)
- Finding [nz-ttr-ironsand-assessment-2]: The row 'Corporate tax rate. Loss not C/fwd' shows tax of -28% of the losses in years 4-9 (e.g. -25.3 on -90.5) but 0.0 on the year-3 loss of -102.7; at the same treatment year 3 would be -28.8, and if losses attract no tax, years 4-9 would be 0. (PDF p.16 Table 4 (and p.33): NPBT and Tax rows)
- Finding [nz-ttr-ironsand-assessment-3]: The table's IRR (-8.8%) is computed on capital expenditure plus NIAT-DA (no loan drawdown or principal repayments), while the NPV (-316.7) is computed on the free cash flow row that includes the 671.5 drawdown and the repayments, so the two measures use different cash flows. (PDF p.16 Table 4 (and p.33): CF - Free Cash Flow, NPV of CFs and IRR rows)

### Toll road PPP numerical financial model (Operis v3) (PPIAF / World Bank, Toolkit for PPP in Roads and Highways (model by Operis, audited 2009))

- URL: https://ppiaf.org/sites/ppiaf.org/files/documents/toolkits/highwaystoolkit/6/financial_models/numerical_model.html
- Recreation status: Matches source (2009-2059 rows of the Cash Flows waterfall (revenue, construction and operating costs, subsidy, tax paid, funding, CFADS, debt service, dividends, cash), Funding construction (drawdowns and capitalised interest by tranche), Debt repayment (interest, debt service and balance of three tranches), Income Statement (EBITDA to net profit, retained profits) and Ratios (ADSCR, project and equity cash flows); project and equity IRR (nominal and real), project NPV, average debt rate and life, and the State's subsidies, VAT and corporate tax in real terms and present value (Results))
- Note: Toll highway concession over 2009-2058: traffic and indexed tolls, construction funding with three amortising debt tranches, an operating subsidy that holds the annual debt service cover ratio at 1.3, dividends, project and equity IRR, and the State's flows
- Finding [ppiaf-toll-road-1]: The pre-financing depreciation (Depreciation and VAT row 53-54, 'w/o financing plans') is based on 742.222 = construction 723.915 + concessionaire costs 8.408 + financing fees 9.899, giving 16.1353 a year, while the pre-financing project cash flows (Ratios row 12) leave the fees out of investment (Ratios F12 = -72.165 = -(70.125 + 2.04)); without the fees depreciation would be 15.9201 and the pre-financing tax (Income Statement row 36, 30%) 0.0646 lower each year. ('Depreciation and VAT'!J53:J54; 'Funding construction'!rows 17, 34, 36; Ratios!F12; 'Income Statement'!row 36)

### Transmission expense model (Bonneville Power Administration)

- URL: https://www.bpa.gov/energy-and-services/rate-and-tariff-proceedings/bp-26-rate-case
- Recreation status: Matches source
- Note: Bonneville BP-26 rate case published workbook. External add-ins may be needed to rerun simulations; stored cells only inspected.

### Transmission rates analysis model (Bonneville Power Administration)

- URL: https://www.bpa.gov/energy-and-services/rate-and-tariff-proceedings/bp-26-rate-case
- Recreation status: Matches source (Tables 1-3 (segment revenue requirements, 23 revenue credits and their segmentation keys, Eastern Intertie and industrial delivery adjustments, segmented revenue requirement by segment for FY2026-2028 and the BP-26 average), Table 6 network PTP/NT rates and SDD credit, Table 7 southern intertie, TGT, IM and IE rates, Table 8.1 SCD costs and rates, and the IM/TGT revenues in Table 10 rows 43 and 142)
- Note: BPA's BP-26 transmission rate design: segmented revenue requirements less allocated revenue credits, divided by forecast sales into network, intertie and scheduling (SCD) rates for FY2026-2028.

### Transmission revenue requirement (Bonneville Power Administration)

- URL: https://www.bpa.gov/energy-and-services/rate-and-tariff-proceedings/bp-26-rate-case
- Recreation status: Matches source
- Note: Bonneville BP-26 rate case published workbook. External add-ins may be needed to rerun simulations; stored cells only inspected.
- Finding [bpa-transmission-revenue-1]: Interest income for 2024 and 2025 is looked up by year from the 'Interest Income' table, which only has columns for 2026-2028, so those cells return #N/A and net interest expense, total expenses and total revenue requirement for 2024 and 2025 are #N/A. (Revenue Requirement!E25:F25, E26:F26, E28:F28, E34:F34; Interest Income!B2:D2)

### Transpower RCP4 revenue model - Attachment C (s53ZD allowances used to set final revenue) (New Zealand Commerce Commission (model maintained by Transpower))

- URL: https://www.comcom.govt.nz/regulated-industries/electricity-lines/projects/2025-transpower-individual-price-quality-path/
- Recreation status: Matches source (WACC and CPI adjustments (WACC & CPI rows 16-24, 41, 46), the existing and new-asset RAB roll-forward (RAB rows 9-38), every MAR building block in year-end and revenue-date terms (MAR rows 10-59), the tax allowance and its parts (Tax rows 12-79) for 2025-2030, and the RCP4 SMAR (SMAR H25:H27, rows 12 and 28))
- Note: Transpower's forecast maximum allowable revenue 2025-2030 from the indexed RAB, new-asset vintages, opex, tax and EV recovery, smoothed into the RCP4 SMAR path

### Ube startup course real estate business plan (Ube Chamber of Commerce and Industry)

- URL: https://www.ubecci.or.jp/found/post_4.html
- Recreation status: Matches source
- Note: Public course reference example for a real estate business.

### UR TSO financial model v1.1 (SONI 2020-25 draft determination) (Utility Regulator Northern Ireland)

- URL: https://www.uregni.gov.uk/publications/ur-financial-model-soni-draft-determination
- Recreation status: Matches source (WACC (WACC B14:B17), the RPI-to-CPIH uplift (RAB K18), the 2020-25 roll-forward of the four RAB classes (RAB rows 105, 154, 253-266, 292-297, 331-335), return on RAB (Return rows 19-33) and every subtotal of maximum regulated revenue (Regulated revenue rows 10-57 and the 2020-25 total I57) for 2020/21-2024/25)
- Note: SONI's maximum regulated SSS/TUoS revenue 2020/21-2024/25 from opex allowances, RAB depreciation and return, risk allowance, pass-through costs and the margin on collection agent revenues

### Value of corporate control (Aswath Damodaran)

- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
- Recreation status: Matches source
- Note: Status quo versus improved management valuation

### Wellington Electricity CPP financial model (New Zealand Commerce Commission)

- URL: https://www.comcom.govt.nz/__data/assets/pdf_file/0027/59913/CPP-financial-model-November-2017.pdf
- Recreation status: Matches source
- Note: Wellington Electricity CPP financial model PDF
- Finding [nz-wellington-electricity-cpp-1]: Two different amounts carry the label 'Maximum Allowable Revenue After Tax': OUT6 shows 97,993 / 99,650 / 101,250 (MAR before tax less tax allowance), while the MAR module shows 'MAR after tax' of 100,791 / 102,496 / 104,141 directly under 'MAR before tax 107,414 less tax allowance 9,421'. 'Building Blocks Allowable Revenue After Tax' likewise appears as 96,594 (OUT4) and 99,352 (MAR module). (PDF p.4 OUTPUTS OUT4, OUT6; PDF p.5 MAR module 'MAR after tax' and 'BBAR after tax' rows; PDF p.6 'BBAR after tax, Total')

### West Tey 250 dwellings per annum financial appraisal (Braintree District Council)

- URL: https://www.braintree.gov.uk/downloads/file/726/exd085-1of2-illustrative-via-ass-250dpa-savills-on-behalf-landq-cirrus-andg120-financial-model
- Recreation status: Matches source
- Note: West Tey 250 dwellings per annum financial appraisal
- Finding [braintree-west-tey-2]: Land acquisition costs (6.5% in total) are computed on a land value of 194,500,484, while the residual land value the same summary arrives at is 194,546,713. (PDF p.3, Land Acquisition Costs block and RESIDUAL LAND VALUE; PDF p.4, Land Value)

### What You Can Pay For A Cow (Colorado State University Extension (Agriculture and Business Management))

- URL: https://abm.extension.colostate.edu/decision-tools
- Recreation status: Matches source (Revenue by class, cow costs, pre-tax profit (total and per cow) for each of the 8 years and the 8-, 5- and 3-year totals on Computations (the discounted-value row is not compared; see README))
- Note: Most a rancher can pay for a bred cow from a 250-cow herd's profit per cow over an 8-, 5- or 3-year productive life
- Finding [csu-cow-value-1]: The discount factors divide the 4% rate (stored as 0.04) by 100 again, giving 0.04% (P8 = 1.0004), and the discounted row multiplies profit by the factor instead of dividing. The 'Discounted Value' totals ($3,381, $2,283, $1,551) are above the undiscounted sums ($3,375, $2,280, $1,550); discounting at 4% gives about $2,880, $2,047 and $1,435. (Computations!P8:P15, C32:J32, L32:N32; Input!E19)

### Yarra Valley Water 2023 Price Review Model (ESC template, submission) (Yarra Valley Water (state-owned) via Essential Services Commission Victoria)

- URL: https://www.esc.vic.gov.au/water/water-prices-tariffs-and-special-drainage/water-price-reviews/water-price-review-2023/yarra-valley-water-price-review-2023
- Recreation status: Matches source (2023-24 to 2027-28: inflation factor, trailing cost of debt and the real rate of return (KeyAssumptionsPriceControl_FO rows 15, 32, 38, 42); existing-asset depreciation for each of the 36 depreciating asset classes and in total, total regulatory depreciation and the rolled-forward RAB (RollForward_FO rows 41-82, 17, 30); existing and new asset bases, averages and returns, return on assets, revenue requirement before tax, interest, before-tax income, gross and net benchmark tax (MOD and real) and the total revenue requirement (Rev&RAV_FO rows 16, 23, 43-64, 98, 107, 114-122))
- Note: Yarra Valley Water's 2023-28 revenue requirement from opex, the return on and of a RAB split into existing and new assets, and a benchmark tax allowance

## Models that do not match their source

Of the 228 models rewritten, 17 do not match their source. They are counted here by reason, without names.

| Reason | Models |
|---|---|
| The source was published without formulas | 6 |
| The source's own numbers contradict its inputs | 5 |
| The source holds random-simulation results | 3 |
| The source depends on macros or add-ins | 1 |
| The source has formulas without calculated values | 1 |
| Needs period lengths boki does not have yet | 1 |

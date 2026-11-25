"""How the Excel export looks: presets as data, overridden with replace().

    r.to_excel("plan.xlsx")                                     # banker, the default
    r.to_excel("plan.xlsx", money="$mm")                        # keyword arguments override the style
    r.to_excel("plan.xlsx", style=b.styles.japanese(money="millions JPY"), units={generation: MWh})

The style changes only how numbers are shown. The Model sheet keeps base units and the formulas
that the export is checked against; the statement sheets refer to it.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import timedelta

from ._dataclass_docs import document_init

SCALES = {"": 1, "k": 1e3, "000": 1e3, "thousand": 1e3, "thousands": 1e3, "mm": 1e6, "m": 1e6,
          "million": 1e6, "millions": 1e6, "hundred million": 1e8, "hundred millions": 1e8,
          "bn": 1e9, "b": 1e9, "billion": 1e9, "billions": 1e9}
_CURRENCY = {"$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "¥": "JPY",
             "yen": "JPY", "jpy": "JPY", "cn¥": "CNY", "cny": "CNY", "yuan": "CNY"}
_EN_SCALE = {1: "", 1e3: "thousands", 1e6: "millions", 1e8: "hundred millions", 1e9: "billions"}
# Keep the legacy selector import; both label sets now use English.
_JA_SCALE = _EN_SCALE
_EN_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "CN¥"}


def money_scale(money: str | float | int | None) -> float:
    """'$mm' -> 1e6, 'millions JPY' -> 1e6, '000' -> 1e3, 1000 -> 1e3. Currency marks are ignored; books have one."""
    if money is None:
        return 1.0
    if isinstance(money, (int, float)):
        return float(money)
    s = money.strip().lower()
    for mark in sorted(_CURRENCY, key=len, reverse=True):
        s = s.replace(mark, "")
    s = re.sub(r"^[\s(]*in\s+", "", s).strip(" ()")
    if s not in SCALES:
        raise ValueError(f"money={money!r}: use a scale such as '$mm', '$000', 'millions JPY', 'thousands JPY' or a number")
    return float(SCALES[s])


# ---- names of kinds and automatic accounts, by language ----------------------------

LABELS = {
    "en": {
        "revenue": "Revenue", "cogs": "Cost of revenue", "sga": "Operating expenses",
        "gross_profit": "Gross profit", "operating_income": "Operating income (EBIT)",
        "other_income": "Other income", "other_expense": "Other expense",
        "interest_expense": "Interest expense", "pretax_income": "Pre-tax income",
        "income_tax": "Income taxes", "net_income": "Net income",
        "non_operating_income": "Non-operating income", "non_operating_expense": "Non-operating expenses",
        "ordinary_income": "Ordinary income", "special_gain": "Extraordinary gains",
        "special_loss": "Extraordinary losses", "finance_income": "Finance income", "finance_cost": "Finance costs",
        "interest_income": "Interest income", "net_interest_income": "Net interest income",
        "provision": "Provision for credit losses", "non_interest_income": "Non-interest income",
        "non_interest_expense": "Non-interest expense",
        # automatic accounts
        "cash": "Cash", "retained_earnings": "Retained earnings", "receivable": "Accounts receivable",
        "payable": "Accounts payable", "deferred_revenue": "Deferred revenue", "prepaid": "Prepaid expenses",
        "deferred_tax_asset": "Deferred tax asset", "deferred_tax_liability": "Deferred tax liability",
        "oci": "Accumulated other comprehensive income", "goodwill": "Goodwill",
        "nci": "Noncontrolling interests", "capital_surplus": "Additional paid-in capital",
        "construction": "Construction in progress (capitalized interest)", "vat": "VAT payable (net)",
        # statement lines
        "assets": "Assets", "current_assets": "Total current assets", "noncurrent_assets": "Total non-current assets",
        "noncurrent_liabilities": "Total non-current liabilities", "total_assets": "Total assets",
        "liabilities_equity": "Liabilities & equity", "current_liabilities": "Total current liabilities",
        "total_liabilities": "Total liabilities", "total_equity": "Total equity",
        "total_liabilities_equity": "Total liabilities & equity", "balance_check": "Balance check",
        "operating": "Cash flow from operations", "investing": "Cash flow from investing",
        "financing": "Cash flow from financing", "fx": "Effect of exchange rates",
        "net_change": "Net change in cash", "cash_begin": "Cash, beginning of period",
        "cash_end": "Cash, end of period", "growth": "% growth", "margin": "% margin",
        "tax_rate": "% effective tax rate", "total": "Total {}", "change_in": "Change in {}",
        "deferred_tax": "Deferred tax", "other_comprehensive_income": "Other comprehensive income",
        "comprehensive_income": "Comprehensive income",
        "noncash": "Depreciation and other non-cash charges", "other_noncash": "Other non-cash items",
        "goodwill_amortization": "Goodwill amortization",
        "acquisition_adjustment_amortization": "Acquisition adjustment amortization",
        "goodwill_impairment": "Goodwill impairment", "bargain_purchase_gain": "Gain on bargain purchase",
        "investments_in_associates": "Investments in associates",
        "equity_method_income": "Equity method earnings", "equity_method_loss": "Equity method loss",
        "equity_method_impairment": "Impairment of investment in associates",
        "deferred_from_receivable": "Deferred revenue (cash received ahead of revenue)",
        "accrued_from_prepaid": "Accrued expenses (paid less than expensed)",
        "IS": "Income Statement", "BS": "Balance Sheet", "CF": "Cash Flow Statement", "SC": "Schedules",
        "debt": "Debt", "fixed_assets": "Fixed assets", "working_capital": "Working capital",
        "opening": "Opening balance", "closing": "Closing balance", "additions": "Additions",
        "reductions": "Reductions", "interest_memo": "Interest expense (memo)",
        "nci_profit": "Net income attributable to noncontrolling interests",
        "parent_profit": "Net income attributable to owners of the parent",
    },

}
# Retain the selector while keeping every emitted label in English.
LABELS["ja"] = LABELS["en"]
# boki names the accounts it opens itself; these are their kinds.
AUTOMATIC = {"cash", "retained_earnings", "receivable", "payable", "deferred_revenue", "prepaid", "construction", "vat"}


@document_init("Create a style for the Excel output.")
@dataclass(frozen=True)
class Style:
    """How the Excel output looks: number scale and formats, colors, signs, headings, and which sheets to build.

    A style changes only how numbers are shown. The Model sheet keeps base units and the formulas the export is
    checked against, and the statement sheets refer to it. The presets in ``b.styles`` are styles. Pass one as
    ``style=`` to ``Result.to_excel``, or pass the settings you want to change as keyword arguments, which
    override the style: ``r.to_excel("plan.xlsx", money="$mm")``. A `Style` is immutable; ``replace`` (or calling the
    style) makes a changed copy.

    Parameters
    ----------
    name : str
        Name of the style, such as ``"banker"``. Required. It is a label and does not change the output.
    money : str, float, or int, optional
        The money scale of the whole workbook: ``"$mm"``, ``"$000"``, ``"millions JPY"``, ``"thousands JPY"``,
        ``"hundred millions JPY"`` or a number such as ``1000``. Currency marks are ignored, because the books have one currency.
        Statement sheets divide by the scale and caption it, such as ``(in millions)``. The default is ``None``, which means
        no scaling.
    units : dict, optional
        Display unit for series on the Model sheet, as ``{series: Unit}``, such as ``{generation: MWh}``. The unit must have
        the dimension of the series. The default is an empty dict.
    hide : iterable, optional
        Named series (or their names) to fold away like helper rows on the Model sheet. The default is an empty tuple.
    helpers : str, default="group"
        ``"group"`` folds the helper rows (rows for unnamed intermediate expressions) and ``"show"`` leaves them open.
    language : str, default="en"
        Language of the names of kinds, automatic accounts and statement lines. ``"en"`` is the default. ``"ja"`` takes the
        same English labels and changes the sheet names and the sheet title format.
    negatives : str, default="parens"
        How a negative number is shown: ``"parens"`` as (1,234), ``"triangle"`` with a triangle mark in front, or
        ``"minus"`` as -1,234.
    zero : str, default="–"
        The text shown for a zero.
    expenses : str, default="negative"
        ``"negative"`` shows expenses as negative numbers and subtotals add them. ``"positive"`` shows expenses as
        positive numbers and subtotals subtract them.
    colors : bool, default=True
        Color the text: inputs blue, formulas black, links to other sheets green.
    ratios : bool, default=True
        Add growth under revenue, margin under each profit subtotal, and the effective tax rate under income taxes.
    gridlines : bool, default=False
        Show the gridlines of the sheets.
    periods : str, default="fy"
        How period columns are headed: ``"fy"`` as ``FY2027E``, ``"year"`` as plain years such as ``2027``, or ``"raw"``
        with the model's own period labels.
    statements : bool, default=True
        Build the statement sheets (income statement, balance sheet, cash flow) in this style. ``False`` writes only the
        plain link sheets.
    columns : str, default="fiscal"
        Statement columns for a model with periods shorter than a year: ``"fiscal"`` sums them into fiscal years,
        ``"periods"`` keeps one column for each model period.
    font : str, optional
        Font name for the statement sheets, such as ``"Arial"``. The default is ``None``, the spreadsheet default.
    decimals : int, optional
        Digits after the decimal point. The default is ``None``, which uses 1 when the money scale is a million or more and
        0 otherwise.
    band : str, optional
        Fill color of the title band and the column headers, as a hex RGB string such as ``"1F3864"``; the text on it is
        white. The default is ``None``, no band.
    shade : str, optional
        Fill color of the final totals, as a hex RGB string. The default is ``None``, no fill.
    dollars : bool, default=False
        Put a dollar sign on the first line and the totals, and caption the statements on three lines, as a 10-K does.
    titles : dict, optional
        Statement and line names that differ in this style, as ``{key: name}``, such as ``{"IS": "Consolidated Statements
        of Operations"}``. The default is an empty dict.
    header : str, optional
        A line above the period headings, where ``{end}`` is the fiscal year end such as ``December 31``: ``"Year Ended
        {end},"``. The default is ``None``, no line.

    Attributes
    ----------
    name : str
        The style's name.
    money : str | float | None
        The money scale as given.
    units : dict
        The display units of series.
    hide : tuple
        The series folded away.
    helpers : str
        ``"group"`` or ``"show"``.
    language : str
        The label language.
    negatives : str
        The negative-number format.
    zero : str
        The text for zero.
    expenses : str
        ``"negative"`` or ``"positive"``.
    colors : bool
        Whether text is colored.
    ratios : bool
        Whether ratio rows are added.
    gridlines : bool
        Whether gridlines show.
    periods : str
        The period heading format.
    statements : bool
        Whether statement sheets are built.
    columns : str
        The statement column grouping.
    font : str | None
        The font name.
    decimals : int | None
        Digits after the point.
    band : str | None
        The band fill color.
    shade : str | None
        The totals fill color.
    dollars : bool
        Whether dollar signs are shown as in a filing.
    titles : dict
        The names that differ.
    header : str | None
        The line above the period headings.

    Raises
    ------
    TypeError
        At construction through ``replace``, if a setting is not a field of the style.
    ValueError
        At construction through ``replace``, if ``columns`` is not ``"fiscal"`` or ``"periods"``, ``helpers`` is not
        ``"group"`` or ``"show"``, or ``money`` is not a scale boki knows. A `Style` made directly is not checked
        until it is used.

    See Also
    --------
    boki.styles.styles : The presets.
    boki.Style.replace : Make a changed copy.

    Notes
    -----
    Settings apply in this order: the preset, then the keyword overrides, which are applied to it with ``replace``. The scale
    changes only the statement sheets and number formats; formulas and values on the Model sheet stay in base units, and every
    formula recalculates to boki's value. See `Excel presentation
    <https://github.com/combinatrix-ai/boki/blob/master/docs/excel-presentation.md>`_.

    Examples
    --------
    Change a preset's settings, and an invalid setting is an error:

    >>> import boki as b
    >>> style = b.styles.banker(money="$mm", negatives="minus")
    >>> style.name, style.money, style.negatives, style.band
    ('banker', '$mm', 'minus', '1F3864')
    >>> b.styles.banker(columns="weekly")
    Traceback (most recent call last):
    ...
    ValueError: columns= must be 'fiscal' or 'periods'
    """  # noqa: DOC105, DOC107, DOC603

    name: str
    money: str | float | None = None      # '$mm', 'millions JPY', 1e3 ...: the whole workbook's money scale
    units: dict = field(default_factory=dict)   # series -> Unit to show it in (Model sheet), e.g. {generation: MWh}
    hide: tuple = ()                      # named series to fold away like helper rows
    helpers: str = "group"               # helper rows: "group" (folded) or "show"
    language: str = "en"                  # names of kinds, automatic accounts and statement lines
    negatives: str = "parens"            # parens (1,234) / triangle △1,234 / minus -1234
    zero: str = "–"
    expenses: str = "negative"           # negative: shown in parentheses, subtotals add; positive: subtotals subtract
    colors: bool = True                   # inputs blue, formulas black, links to other sheets green
    ratios: bool = True                   # % growth under revenue, % margin under each profit
    gridlines: bool = False
    periods: str = "fy"                   # fy: FY2027E / ja: FY2027E / raw: the model's labels
    statements: bool = True               # IS / BS / CF sheets in this style (False: the plain link sheets)
    columns: str = "fiscal"               # statement columns: fiscal years for sub-annual models, or "periods"
    font: str | None = None
    decimals: int | None = None           # digits after the point; None: 1 when money is in millions or more
    band: str | None = None               # fill of the title band and column headers (dark: white text)
    shade: str | None = None              # fill of the final totals
    dollars: bool = False                 # $ on the first line and the totals, as in a 10-K
    titles: dict = field(default_factory=dict)   # statement and line names that differ in this style
    header: str | None = None             # a line over the period headers: "Year Ended {end}," ({end}: December 31)

    def __call__(self, **kw: object) -> "Style":
        """Return a copy of the style with some settings changed; the same as ``replace``.

        Parameters
        ----------
        **kw : object
            Settings to change, by the names of the fields of `Style`, such as ``money="$mm"``.

        Returns
        -------
        Style
            A new style with the given settings. The original is unchanged.

        Raises
        ------
        TypeError
            At construction, if a keyword is not a field of the style.
        ValueError
            At construction, if ``columns``, ``helpers`` or ``money`` has an invalid value.

        See Also
        --------
        boki.Style.replace : The same operation under its method name.

        Examples
        --------
        >>> import boki as b
        >>> b.styles.plain(gridlines=False).gridlines
        False
        """  # noqa: DOC502
        return self.replace(**kw)

    def replace(self, **kw: object) -> "Style":
        """Return a copy of the style with some settings changed.

        The checks that settings are valid run here, so a mistake fails when the style is made and not when the workbook is
        written.

        Parameters
        ----------
        **kw : object
            Settings to change, by the names of the fields of `Style`. ``units``, ``hide`` and ``titles`` are copied
            to a dict, a tuple and a dict.

        Returns
        -------
        Style
            A new style with the given settings. The original is unchanged.

        Raises
        ------
        TypeError
            At construction, if a keyword is not a field of the style.
        ValueError
            At construction, if ``columns`` is not ``"fiscal"`` or ``"periods"``, ``helpers`` is not ``"group"`` or
            ``"show"``, or ``money`` is not a scale boki knows, such as ``"$mm"``.

        See Also
        --------
        boki.Style : The settings.

        Examples
        --------
        A preset in millions, with the scale checked:

        >>> import boki as b
        >>> style = b.styles.japanese.replace(money="millions JPY")
        >>> style.money, style.negatives
        ('millions JPY', 'triangle')
        >>> b.styles.banker.replace(money="lots")
        Traceback (most recent call last):
        ...
        ValueError: money='lots': use a scale such as '$mm', '$000', 'millions JPY', 'thousands JPY' or a number
        >>> b.styles.banker.replace(colour=False)
        Traceback (most recent call last):
        ...
        TypeError: unknown style setting(s): colour
        """
        if "units" in kw:
            kw["units"] = dict(kw["units"])
        if "hide" in kw:
            kw["hide"] = tuple(kw["hide"])
        if "titles" in kw:
            kw["titles"] = dict(kw["titles"])
        unknown = set(kw) - {f.name for f in dataclasses.fields(self)}
        if unknown:
            raise TypeError(f"unknown style setting(s): {', '.join(sorted(unknown))}")
        if kw.get("columns", self.columns) not in ("fiscal", "periods"):
            raise ValueError("columns= must be 'fiscal' or 'periods'")
        if kw.get("helpers", self.helpers) not in ("group", "show"):
            raise ValueError("helpers= must be 'group' or 'show'")
        money_scale(kw.get("money", self.money))       # fail early on a bad scale
        return dataclasses.replace(self, **kw)

    # -- derived -----------------------------------------------------------------------

    @property
    def scale(self) -> float:
        return money_scale(self.money)

    def label(self, key: str, standard=None) -> str:
        """A name in the style's language: the standard's own term first (IFRS says "Profit for the year"),
        then the style's (a 10-K says "Consolidated Statements of Operations"), then the common table."""
        if standard is not None:
            own = getattr(standard, "display", {}).get(self.language, {})
            if key in own:
                return own[key]
        if key in self.titles:
            return self.titles[key]
        return LABELS[self.language].get(key, key)

    def dollar_format(self) -> str:
        d = self.decimals if self.decimals is not None else (1 if self.scale >= 1e6 else 0)
        n = "#,##0" + ("." + "0" * d if d else "")
        return f'_("$"* {n}_);_("$"* ({n});_("$"* "{self.zero}"_);_(@_)'

    def number_format(self, scale_by_format: float = 1) -> str:
        """Excel number format; scale_by_format=1e6 shows millions by format alone (#,##0,,)."""
        commas = "," * _powers_of_1000(scale_by_format)
        d = self.decimals if self.decimals is not None else (1 if self.scale >= 1e6 else 0)
        n = "#,##0" + ("." + "0" * d if d else "") + commas
        zero = f'"{self.zero}"' if self.zero != "0" else "0"
        if self.negatives == "parens":
            return f'{n}_);({n});{zero}_)'
        if self.negatives == "triangle":
            return f'{n};"△"{n};{zero}'
        return n

    def percent_format(self) -> str:
        if self.negatives == "parens":
            return f'0.0%_);(0.0%);"{self.zero}"_)'
        if self.negatives == "triangle":
            return f'0.0%;"△"0.0%;"{self.zero}"'
        return "0.0%"

    def caption(self, currency: str | None) -> str:
        k = self.scale
        if currency is None:
            return f"(in {_EN_SCALE.get(k, f'{k:g}')})" if k != 1 else ""
        symbol = _EN_SYMBOL.get(currency, currency + " ")
        return f"({symbol} in {_EN_SCALE[k]})" if k in _EN_SCALE and k != 1 else f"(in {symbol.strip()})"

    def period_label(self, period, fiscal=None) -> str | int:
        """A column heading: the fiscal year as a number for a year or longer (shown by heading_format), else text."""
        if self.periods == "raw" or period.start is None:
            return period.label
        if period.months >= 12:
            end = fiscal._end_for(period.start) if fiscal is not None else period.end - timedelta(days=1)
            return end.year
        return period.start.strftime("%b-%y")

    def heading_format(self, actual: bool = False, has_actuals: bool = False) -> str:
        """Number format of a year heading: FY2024A / FY2025E for periods="fy", 2024A / 2025E when the model has
        actuals with periods="year", or plain 2027 otherwise, padded like the numbers below."""
        pad = "_)" if self.negatives == "parens" else ""
        suffix = "A" if actual else "E"
        if self.periods == "fy":
            return f'"FY"0"{suffix}"{pad}'
        if has_actuals:
            return f'0"{suffix}"{pad}'
        return f"0{pad}"


def _powers_of_1000(k: float) -> int:
    n = 0
    while k >= 1000 and k % 1000 == 0:
        k /= 1000
        n += 1
    return n if k == 1 else 0


class styles:
    """The Excel style presets: ``b.styles.banker`` (the default for every standard), ``sec``, ``japanese`` and ``plain``.

    Each preset is a `Style`. Use one as ``r.to_excel("plan.xlsx", style=b.styles.sec)`` or change it with
    keyword arguments: ``b.styles.banker(money="$mm")``. The class only holds the presets.

    Attributes
    ----------
    banker : Style
        Investment-banking look, the default: expenses negative in parentheses, blue inputs and green links, growth and
        margin rows, a dark title band, shaded totals, Arial.
    sec : Style
        A filing look: Times New Roman, no colors, no ratio rows, dollar signs on the first line and the totals, plain
        year headings with a "Year Ended" line, and "Consolidated" statement titles.
    japanese : Style
        Japanese accounting presentation: triangle marks for negatives, expenses shown positive with subtotals that
        subtract, no ratio rows, fiscal-year headings.
    plain : Style
        The plain output: minus signs, expenses positive, no colors or ratio rows, gridlines on, the model's own period
        labels, no statement sheets, and helper rows shown.

    See Also
    --------
    boki.Style : The settings of a style.

    Examples
    --------
    The presets differ in how they show negatives and expenses:

    >>> import boki as b
    >>> b.styles.banker.negatives, b.styles.japanese.negatives, b.styles.plain.negatives
    ('parens', 'triangle', 'minus')
    >>> b.styles.banker.expenses, b.styles.plain.expenses
    ('negative', 'positive')
    """  # noqa: DOC605
    banker = Style("banker", band="1F3864", shade="DDEBF7", font="Arial")
    sec = Style("sec", font="Times New Roman", colors=False, ratios=False, zero="—", dollars=True, periods="year",
                header="Year Ended {end},", titles={
                    "IS": "Consolidated Statements of Operations", "BS": "Consolidated Balance Sheets",
                    "CF": "Consolidated Statements of Cash Flows"})
    japanese = Style("japanese", language="ja", negatives="triangle", zero="–", expenses="positive",
                     ratios=False, periods="fy")
    plain = Style("plain", negatives="minus", zero="0", expenses="positive", colors=False, ratios=False,
                  gridlines=True, periods="raw", statements=False, helpers="show")

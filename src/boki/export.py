"""Write an entity's ledger as Beancount text, so plain-text-accounting tools can read it.

Each posting with a non-zero amount in a period becomes one transaction dated the period's
last day. Beancount derives retained earnings from Income and Expenses itself.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ledger import Account, Entity
    from .model import Result

_ROOT = {"asset": "Assets", "liability": "Liabilities", "equity": "Equity", "income": "Income",
         "expense": "Expenses"}


def _camel(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(w[:1].upper() + w[1:] for w in words)


def _account_names(entity: "Entity") -> dict["Account", str]:
    """Beancount names: Root:Kind:Name, ASCII only; non-ASCII names become A1, A2, ... (kept as metadata)."""
    names: dict = {}
    used: set[str] = set()
    for i, a in enumerate(entity._accounts, 1):
        leaf = _camel(a.name) or f"A{i}"
        leaf = leaf if leaf[0].isalpha() else f"A{leaf}"
        name = f"{_ROOT[a.side]}:{_camel(a.kind.replace('_', ' '))}:{leaf}"
        if name in used:
            name = f"{name}-{i}"
        used.add(name)
        names[a] = name
    return names


def to_beancount(result: "Result", entity: "Entity", currency: str | None = None) -> str:
    """Write an entity's ledger as Beancount text.

    Each posting of the entity with a non-zero amount in a period becomes one transaction dated the last day of that
    period, with the debit and the credit as its two legs. The text is meant for plain-text-accounting tools, which read
    the account tree, the opening balances and the transactions.

    Parameters
    ----------
    result : Result
        The result of ``m.render()`` that holds the amounts. Required.
    entity : Entity
        The entity whose books to write, such as ``co``, or ``group.books`` for the consolidated books. Required.
    currency : str, optional
        The Beancount commodity of every amount, such as ``"JPY"``. The default is ``None``, which uses the entity's
        currency when its books are in a single currency.

    Returns
    -------
    str
        The Beancount text: two ``option`` lines, an ``open`` directive for every account, one dated transaction for the
        opening balances (the day before the first period), and the transactions of the periods. Amounts have two decimals.

    Raises
    ------
    ValueError
        At evaluation, if the model's periods are not dated, or if ``currency`` is omitted and the entity's books are
        not in one currency (for example when nothing has been booked).

    See Also
    --------
    boki.Style : How the Excel output looks.

    Notes
    -----
    Account names are ``Root:Kind:Name``, where the root is ``Assets``, ``Liabilities``, ``Equity``, ``Income`` or
    ``Expenses``, and the kind and the name are written in CamelCase with ASCII characters only. A name with no ASCII
    characters becomes ``A1``, ``A2`` and so on, and a duplicate gets a numeric suffix. The original name is kept as the
    ``boki-name`` metadata of the ``open`` directive. Beancount derives retained earnings from the Income and
    Expenses accounts itself, so profit is not closed into the retained earnings account.

    Examples
    --------
    A café with opening cash of 1,000 for two months, written as Beancount text, which Beancount loads without errors:

    >>> import boki as b
    >>> from boki.units import JPY
    >>> from boki.export import to_beancount
    >>> m = b.Model("Cafe", start="2027-01", periods=2, step=b.month)
    >>> co = m.entity("Cafe", standard=b.IFRS, currency=JPY)
    >>> co.bs.opening(cash=1000)
    >>> sales = co.pl.revenue("Sales", 100)
    >>> rent = co.pl.sga("Rent", 30)
    >>> r = m.render()
    >>> text = to_beancount(r, co)
    >>> print("\\n".join(text.splitlines()[:5]))
    option "title" "Cafe"
    option "operating_currency" "JPY"
    <BLANKLINE>
    2026-12-31 open Assets:Cash:Cash JPY
      boki-name: "Cash"
    >>> from beancount import loader
    >>> entries, errors, options = loader.load_string(text)
    >>> errors
    []
    """  # noqa: DOC105, DOC107, DOC503
    periods = result.model.timeline.periods
    if periods[0].start is None:
        raise ValueError("Beancount export needs a dated timeline")
    unit = entity._currency
    if currency is None:
        if unit is None or len(unit) != 1 or next(iter(unit))[1] != 1:
            raise ValueError("pass currency= (the books' unit is not a single currency)")
        currency = next(iter(unit))[0]
    names = _account_names(entity)
    lines = [f'option "title" "{entity.name}"', f'option "operating_currency" "{currency}"', ""]
    opened = periods[0].start - timedelta(days=1)
    for a, name in names.items():
        lines.append(f'{opened} open {name} {currency}')
        lines.append(f'  boki-name: "{a.name}"')
    lines.append("")
    opening = [(names[a], result[entity._balance(a).opening][0] * (1 if a.side == "asset" else -1))
               for a in entity._accounts]
    opening = [(name, v) for name, v in opening if abs(v) > 1e-9]
    if opening:
        lines.append(f'{opened} * "opening balances"')
        lines += [f"  {name:<60} {v:.2f} {currency}" for name, v in opening]
        lines.append("")
    for p in entity._postings:
        vals = result[p.amount]
        vals = vals if isinstance(vals, list) else [vals] * len(periods)
        for t, v in enumerate(vals):
            if v is None or abs(v) < 1e-9:
                continue
            day = periods[t].end - timedelta(days=1)
            amount = f"{v:.2f}"
            lines.append(f'{day} * "{p.name}"')
            lines.append(f"  {names[p.debit]:<60} {amount} {currency}")
            lines.append(f"  {names[p.credit]:<60} {_neg(amount)} {currency}")
    return "\n".join(lines) + "\n"


def _neg(amount: str) -> str:
    return amount[1:] if amount.startswith("-") else f"-{amount}"


__all__ = ["to_beancount"]

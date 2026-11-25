"""Docstrings for the ``__init__`` methods that ``@dataclass`` generates.

A generated ``__init__`` has no docstring, so ``help(Kind.__init__)`` and the docstring checks see nothing. The
class docstring documents the fields as Parameters; this decorator copies that section into the generated
``__init__`` so that the two stay one text.
"""
from __future__ import annotations

import inspect
import re
from collections.abc import Callable

_PARAMETERS = re.compile(r"^Parameters\n-{10}\n.*?(?=\n\n[A-Z][A-Za-z ]*\n-{3,}\n|\Z)", re.S | re.M)


def document_init(summary: str) -> Callable[[type], type]:
    """Return a class decorator that gives a dataclass's generated ``__init__`` a docstring.

    Apply it above ``@dataclass``. The docstring is ``summary`` and the Parameters section of the class docstring.

    Parameters
    ----------
    summary : str
        The summary line of the ``__init__`` docstring, imperative, such as ``"Create a kind."``.

    Returns
    -------
    Callable[[type], type]
        The class decorator.
    """
    def apply(cls):
        found = _PARAMETERS.search(inspect.cleandoc(cls.__doc__ or ""))
        if found is None:
            raise ValueError(f"{cls.__qualname__}: the class docstring has no Parameters section to copy")
        cls.__init__.__doc__ = f"{summary}\n\n{found.group(0)}\n"
        return cls
    return apply

"""Pull-based, memoized evaluation of series nodes, with cycle detection.

A Render owns every value computed for one set of inputs. Asking for (node, t)
computes it on demand, remembers it, and reports a cycle if the same (node, t)
is requested again while it is still being computed.
"""
from __future__ import annotations

import contextvars
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .model import Model, Period
    from .series import Series

_current: contextvars.ContextVar["Render | None"] = contextvars.ContextVar("boki_render", default=None)


def current() -> "Render | None":
    return _current.get()


class CycleError(RecursionError):
    """Error raised when a series depends on itself in the same period.

    The message names the series in the cycle and the period, and says how to break it: read an earlier period with
    ``x.lag(1)``, or wrap the loop in `Model.solve`. A circular reference is found when the values are read, by
    `Model.render` or by ``r[x]`` and ``r.value(x, period)``. It subclasses `RecursionError`.

    Parameters
    ----------
    chain : list[tuple[Series, int | None]]
        The series and period index of each step of the cycle, from the first repeated step to the request that
        closed the loop. The period is ``None`` for a scalar series. Unnamed intermediate expressions are included.
    periods : list[Period] | None
        The model's periods, used to write period labels in the message. The default shows period indices.

    Attributes
    ----------
    chain : list[tuple[Series, int | None]]
        The steps of the cycle, as given at construction.

    See Also
    --------
    boki.Model.solve : Solve a deliberate circular reference.
    boki.Series.lag : Read an earlier period to break a cycle.

    Examples
    --------
    Two series defined in terms of each other:

    >>> import boki as b
    >>> m = b.Model("Cycle", start="2027-01", periods=2, step=b.month)
    >>> a = m.series("A")
    >>> c = m.series("C", a + 1)
    >>> _ = a.define(c + 1)
    >>> r = m.render()
    >>> try:
    ...     r[a]
    ... except b.CycleError as error:
    ...     print(str(error).splitlines()[0])
    circular reference: A -> C -> A (in 2027-01)
    """  # noqa: DOC602, DOC603

    def __init__(self, chain: list[tuple["Series", int | None]], periods: list[Period] | None = None):
        self.chain = chain
        named = [(n, t) for n, t in chain if getattr(n, "name", None)] or chain
        steps, last = [], None
        for n, t in named:
            if steps and n.name == steps[-1][0] and t == last:
                continue
            steps.append((n.name or type(n).__name__, t))
            last = t
        same = len({t for _, t in steps}) == 1
        text = " -> ".join(name if same else f"{name} [{_when(t, periods)}]" for name, t in steps)
        where = f" (in {_when(steps[0][1], periods)})" if same and steps[0][1] is not None else ""
        super().__init__(
            f"circular reference: {text}{where}\n"
            "Break it by reading an earlier period (x.lag(1)), or wrap the loop in m.solve(...)."
        )


def _when(t, periods) -> str:
    if t is None:
        return "all periods"
    if periods is None or not 0 <= t < len(periods):
        return f"period {t}"
    p = periods[t]
    return p.label if p.start is not None else f"period {p.label}"       # dated periods read "2027", "2027-04"


class Render:
    def __init__(self, model: "Model", inputs: dict[Any, Any]):
        self.model = model
        self.n = model.timeline.n
        self.inputs = inputs
        self._memo: dict[tuple[int, int | None], Any] = {}
        self._active: dict[tuple[int, int | None], int] = {}
        self._stack: list[tuple["Series", int | None]] = []
        self._sparse: dict[int, dict[int, Any]] = {}
        # Memo keys use id(node). Holding every evaluated node keeps its id from being
        # reused by a later temporary node, which would otherwise return a stale value.
        self._alive: dict[int, "Series"] = {}

    # ---- core ------------------------------------------------------------------
    def value(self, node: "Series", t: int | None) -> Any:
        key = (id(node), t)
        if key in self._memo:
            return self._memo[key]
        if key in self._active:
            raise CycleError(self._stack[self._active[key]:] + [(node, t)], self.model.timeline.periods)
        if t is not None and not (0 <= t < self.n):
            raise IndexError(f"period {t} is outside the model (0..{self.n - 1}) for {getattr(node, 'name', None) or type(node).__name__}")
        self._alive[key[0]] = node
        self._active[key] = len(self._stack)
        self._stack.append((node, t))
        token = _current.set(self)
        try:
            v = node._eval(self, t)
        finally:
            _current.reset(token)
            self._stack.pop()
            del self._active[key]
        self._memo[key] = v
        return v

    def values(self, node: "Series") -> list[Any]:
        if node.scalar:
            return [self.value(node, None)] * self.n
        return [self.value(node, t) for t in range(self.n)]

    def invalidate(self) -> None:
        self._memo.clear()
        self._sparse.clear()

    # ---- helpers used by nodes -------------------------------------------------
    def period_index(self, key) -> int:
        if hasattr(key, "_eval"):          # a scalar series such as an input
            key = self.value(key, None)
            key = int(key) if isinstance(key, float) and key.is_integer() else key
        return self.model.timeline.index(key)

    def sparse(self, node) -> dict[int, Any]:
        cached = self._sparse.get(id(node))
        if cached is None:
            cached = {}
            for k, v in node.points.items():
                i = self.period_index(k)
                cached[i] = cached.get(i, 0) + (self.value(v, None) if hasattr(v, "_eval") else v)
            self._sparse[id(node)] = cached
        return cached


def ensure_recursion_limit(n_periods: int) -> None:
    # A recurrence over N periods nests about 4 frames per period in value()/_eval().
    need = 2000 + 40 * n_periods
    if sys.getrecursionlimit() < need:
        sys.setrecursionlimit(need)

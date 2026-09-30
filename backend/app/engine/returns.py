"""Money-weighted return (XIRR)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date


def xnpv(rate: float, cashflows: list[tuple[date, float]]) -> float:
    t0 = min(d for d, _ in cashflows)
    return sum(cf / (1.0 + rate) ** ((d - t0).days / 365.0) for d, cf in cashflows)


def xirr(
    cashflows: Iterable[tuple[date, float]],
    low: float = -0.9999,
    high: float = 100.0,
    tol: float = 1e-10,
    max_iter: int = 300,
) -> float | None:
    """Annualised money-weighted return, or None when it cannot be determined.

    Sign convention: money paid into the account is negative; withdrawals and the current value
    (added as a final flow dated today) are positive. Solved by bisection, which is slower than
    Newton but cannot diverge on the small flow lists this app produces.
    """
    flows = [(d, float(a)) for d, a in cashflows if abs(a) > 1e-12]
    if len(flows) < 2 or not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        return None
    f_low, f_high = xnpv(low, flows), xnpv(high, flows)
    if f_low * f_high > 0:
        return None
    for _ in range(max_iter):
        mid = (low + high) / 2.0
        f_mid = xnpv(mid, flows)
        if abs(f_mid) < tol or (high - low) / 2.0 < tol:
            return mid
        if f_low * f_mid < 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2.0

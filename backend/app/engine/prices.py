"""Price normalisation: minor currency units (pence), FX to GBP and Yahoo's 100x pence glitch.

Yahoo quotes most London-listed shares and ETFs in pence and reports the currency as 'GBp'
(lower-case p). Treating that number as pounds overstates the holding 100x, the most common bug
in UK portfolio trackers. Everything that leaves this module is in GBP.
"""

from __future__ import annotations

from collections.abc import Mapping

# provider currency code -> (major currency, multiplier to reach the major unit)
MINOR_UNITS: dict[str, tuple[str, float]] = {
    "GBp": ("GBP", 0.01),
    "GBX": ("GBP", 0.01),
    "ZAc": ("ZAR", 0.01),
    "ILA": ("ILS", 0.01),
}


class MissingFxRate(LookupError):
    """No GBP conversion rate is available for a currency."""


def major_currency(currency: str) -> tuple[str, float]:
    """('GBP', 0.01) for 'GBp'; (CODE, 1.0) for anything that is already a major unit.

    The minor-unit lookup is case-sensitive on purpose: 'GBp' is pence, 'GBP' is pounds.
    """
    if currency in MINOR_UNITS:
        return MINOR_UNITS[currency]
    return currency.upper(), 1.0


def fx_symbol(currency: str) -> str:
    """Yahoo symbol whose price is the GBP value of one unit: 'USD' -> 'USDGBP=X'."""
    return f"{major_currency(currency)[0]}GBP=X"


def to_gbp(price: float, currency: str, gbp_per_unit: Mapping[str, float] | None = None) -> float:
    """Convert a native price to GBP. `gbp_per_unit` maps major currency -> GBP per 1 unit."""
    major, scale = major_currency(currency)
    value = price * scale
    if major == "GBP":
        return value
    rate = (gbp_per_unit or {}).get(major)
    if rate is None or rate <= 0:
        raise MissingFxRate(major)
    return value * rate


def fix_pence_glitch(price_gbp: float, reference_gbp: float | None) -> tuple[float, bool]:
    """Undo a 100x pence/pounds mix-up by comparing with a trusted recent GBP price.

    Returns (price, corrected). A genuine 50x move in a day is not a realistic case for the funds
    and shares this app tracks; a 100x jump is almost always the data glitch.
    """
    if not reference_gbp or reference_gbp <= 0 or price_gbp <= 0:
        return price_gbp, False
    ratio = price_gbp / reference_gbp
    if 50 <= ratio <= 200:
        return price_gbp / 100, True
    if 0.005 <= ratio <= 0.02:
        return price_gbp * 100, True
    return price_gbp, False

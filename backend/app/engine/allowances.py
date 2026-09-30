"""ISA, LISA, JISA and pension annual allowance usage for a UK tax year.

Allowance figures are data (`tax_year_rules` table), never hard-coded in services.
Simplifications, shown in the UI as footnotes:
- Pension usage is gross contributions to DC pensions. Tapered allowance, carry-forward and
  defined-benefit accrual are not modelled.
- ISA transfers between providers and the LISA government bonus never use allowance.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .dates import tax_year_end, tax_year_label, tax_year_start

ISA_WRAPPERS = {"isa", "lisa"}
PENSION_WRAPPERS = {"sipp", "workplace_pension"}
PENSION_SOURCES = {"personal", "employer", "salary_sacrifice", "tax_relief"}


@dataclass(frozen=True)
class AllowanceRules:
    isa: float = 20_000.0
    lisa: float = 4_000.0
    jisa: float = 9_000.0
    pension_annual: float = 60_000.0
    cash_isa_limit: float | None = None


@dataclass(frozen=True)
class Contribution:
    person_id: int  # the account owner (the child for a JISA)
    date: date
    amount: float  # amount credited to the account (gross for pensions)
    wrapper: str
    source: str = "personal"
    is_cash: bool = False  # cash ISA subscription


@dataclass
class AllowanceUsage:
    person_id: int
    tax_year: str
    tax_year_end: date
    isa_used: float = 0.0  # includes LISA subscriptions
    isa_limit: float = 0.0
    lisa_used: float = 0.0
    lisa_limit: float = 0.0
    cash_isa_used: float = 0.0
    cash_isa_limit: float | None = None
    jisa_used: float = 0.0
    jisa_limit: float = 0.0
    pension_used: float = 0.0
    pension_limit: float = 0.0

    @property
    def isa_remaining(self) -> float:
        return max(self.isa_limit - self.isa_used, 0.0)

    @property
    def lisa_remaining(self) -> float:
        return max(min(self.lisa_limit - self.lisa_used, self.isa_remaining), 0.0)

    @property
    def pension_remaining(self) -> float:
        return max(self.pension_limit - self.pension_used, 0.0)

    @property
    def jisa_remaining(self) -> float:
        return max(self.jisa_limit - self.jisa_used, 0.0)


def allowance_usage(
    contributions: Iterable[Contribution],
    on: date,
    rules: AllowanceRules,
    person_ids: Iterable[int] = (),
) -> dict[int, AllowanceUsage]:
    """Usage per person for the tax year containing `on`. `person_ids` adds zero rows."""
    start, end = tax_year_start(on), tax_year_end(on)
    label = tax_year_label(on)

    def blank(pid: int) -> AllowanceUsage:
        return AllowanceUsage(
            person_id=pid,
            tax_year=label,
            tax_year_end=end,
            isa_limit=rules.isa,
            lisa_limit=rules.lisa,
            cash_isa_limit=rules.cash_isa_limit,
            jisa_limit=rules.jisa,
            pension_limit=rules.pension_annual,
        )

    usage = {pid: blank(pid) for pid in person_ids}
    for c in contributions:
        if not (start <= c.date <= end) or c.amount <= 0:
            continue
        u = usage.setdefault(c.person_id, blank(c.person_id))
        if c.wrapper in ISA_WRAPPERS and c.source == "personal":
            u.isa_used += c.amount
            if c.wrapper == "lisa":
                u.lisa_used += c.amount
            if c.is_cash:
                u.cash_isa_used += c.amount
        elif c.wrapper == "jisa" and c.source == "personal":
            u.jisa_used += c.amount
        elif c.wrapper in PENSION_WRAPPERS and c.source in PENSION_SOURCES:
            u.pension_used += c.amount
    return usage

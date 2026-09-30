"""Pure financial engine for the net worth tracker.

No database, no network, no clock. Every function takes plain values and dates and returns plain
values, so it is fully unit-tested in tests/engine/.

Modules
    dates        calendar helpers, UK tax year, projection timeline
    growth       compound/linear appreciation and depreciation, inflation
    prices       pence -> pounds, FX to GBP, Yahoo 100x glitch guard
    amortisation mortgage/loan schedules with rate periods and overpayments
    ledger       transactions -> positions (average cost), cash, contributions
    recurring    dated occurrences of regular contributions with escalation and tax relief
    projection   month-by-month net worth forecast across accounts and people
    returns      XIRR (money-weighted annual return)
    allowances   ISA / LISA / JISA / pension annual allowance usage per tax year
"""

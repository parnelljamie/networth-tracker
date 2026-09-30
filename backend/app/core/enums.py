"""Every enum in docs/02-data-model.md, stored as TEXT in SQLite."""
from __future__ import annotations

from enum import StrEnum


class Category(StrEnum):
    investment = "investment"
    pension = "pension"
    cash = "cash"
    property = "property"
    mortgage = "mortgage"
    loan = "loan"
    credit_card = "credit_card"
    other_asset = "other_asset"
    other_liability = "other_liability"


class Wrapper(StrEnum):
    none = "none"
    isa = "isa"
    lisa = "lisa"
    jisa = "jisa"
    gia = "gia"
    sipp = "sipp"
    workplace_pension = "workplace_pension"
    db_pension = "db_pension"


class ValuationMethod(StrEnum):
    holdings = "holdings"
    balance = "balance"
    model = "model"
    amortising = "amortising"
    defined_benefit = "defined_benefit"


class TxnType(StrEnum):
    OPENING_BALANCE = "OPENING_BALANCE"
    BUY = "BUY"
    SELL = "SELL"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"
    TAX = "TAX"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    SPLIT = "SPLIT"
    ADJUSTMENT = "ADJUSTMENT"


class ContributionSource(StrEnum):
    personal = "personal"
    employer = "employer"
    salary_sacrifice = "salary_sacrifice"
    tax_relief = "tax_relief"
    government_bonus = "government_bonus"
    transfer = "transfer"


class TxnStatus(StrEnum):
    confirmed = "confirmed"
    pending = "pending"


class TxnSource(StrEnum):
    manual = "manual"
    opening = "opening"
    recurring = "recurring"
    import_ = "import"


class BalanceSource(StrEnum):
    manual = "manual"
    statement = "statement"
    valuation = "valuation"
    csv = "csv"
    estimate = "estimate"


class AssetClass(StrEnum):
    equity = "equity"
    bond = "bond"
    multi_asset = "multi_asset"
    property = "property"
    commodity = "commodity"
    cash = "cash"
    crypto = "crypto"
    other = "other"


class PriceSource(StrEnum):
    yahoo = "yahoo"
    manual = "manual"


class GrowthMethod(StrEnum):
    compound = "compound"
    linear = "linear"


class RepaymentType(StrEnum):
    repayment = "repayment"
    interest_only = "interest_only"


class OverpaymentEffect(StrEnum):
    reduce_term = "reduce_term"
    reduce_payment = "reduce_payment"


class RateType(StrEnum):
    fixed = "fixed"
    tracker = "tracker"
    variable = "variable"
    svr = "svr"


class PlanKind(StrEnum):
    contribution = "contribution"
    withdrawal = "withdrawal"
    overpayment = "overpayment"


class Frequency(StrEnum):
    weekly = "weekly"
    fortnightly = "fortnightly"
    monthly = "monthly"
    quarterly = "quarterly"
    annually = "annually"


class SnapshotSource(StrEnum):
    daily = "daily"
    backfill = "backfill"
    rebuild = "rebuild"


class ScenarioEventKind(StrEnum):
    lump_sum = "lump_sum"
    stop_plan = "stop_plan"
    change_plan_amount = "change_plan_amount"
    set_return_rate = "set_return_rate"


class GoalScope(StrEnum):
    household = "household"
    person = "person"
    account = "account"
    category = "category"


class ImportKind(StrEnum):
    transactions = "transactions"
    balances = "balances"


class ImportStatus(StrEnum):
    pending = "pending"
    previewed = "previewed"
    committed = "committed"
    rolled_back = "rolled_back"

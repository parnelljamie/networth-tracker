"""Import every model module so Base.metadata is complete for Alembic autogenerate."""

from app.models.accounts import Account, AccountOwner
from app.models.balances import BalanceEntry
from app.models.broker_links import BrokerLink
from app.models.db_pension import DbPensionDetails
from app.models.goals import Goal
from app.models.growth import GrowthModel
from app.models.imports import ImportBatch, ImportProfile, InstrumentAlias
from app.models.instruments import Instrument
from app.models.loans import LoanDetails, LoanOverpayment, LoanRatePeriod
from app.models.people import Person
from app.models.positions import Position
from app.models.prices import FxRate, InstrumentPrice
from app.models.property import PropertyDetails
from app.models.recurring import RecurringPlan, RecurringPlanAllocation
from app.models.scenarios import Scenario, ScenarioEvent
from app.models.settings import Setting
from app.models.snapshots import AccountSnapshot
from app.models.sync import SyncAppliedOp, SyncDevice, SyncOutbox
from app.models.tax_year_rules import TaxYearRule
from app.models.transactions import Transaction

__all__ = [
    "Account",
    "AccountOwner",
    "AccountSnapshot",
    "BalanceEntry",
    "BrokerLink",
    "DbPensionDetails",
    "FxRate",
    "Goal",
    "GrowthModel",
    "ImportBatch",
    "ImportProfile",
    "Instrument",
    "InstrumentAlias",
    "InstrumentPrice",
    "LoanDetails",
    "LoanOverpayment",
    "LoanRatePeriod",
    "Person",
    "Position",
    "PropertyDetails",
    "RecurringPlan",
    "RecurringPlanAllocation",
    "Scenario",
    "ScenarioEvent",
    "Setting",
    "SyncAppliedOp",
    "SyncDevice",
    "SyncOutbox",
    "TaxYearRule",
    "Transaction",
]

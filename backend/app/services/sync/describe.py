"""Plain-English labels for the changes in the phone's outbox, shown in the sync report
("Balance £850.00 for Joint current on 10 Sep 2026" rather than `POST /api/accounts/3/balances`).
Worked out before the request runs, so a deleted account still has its name."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.accounts import Account
from app.models.instruments import Instrument

_VERBS = {"POST": "Added", "PUT": "Changed", "PATCH": "Changed", "DELETE": "Deleted"}
_NOUNS = {
    "people": "a person",
    "goals": "a goal",
    "recurring": "a regular payment",
    "scenarios": "a scenario",
    "scenario-events": "a scenario event",
    "rate-periods": "a rate period",
    "overpayments": "an overpayment",
    "instruments": "an instrument",
    "settings": "settings",
    "tax-year-rules": "tax-year rules",
    "balances": "a balance",
    "transactions": "a transaction",
    "growth-model": "the growth model",
    "property": "property details",
    "loan": "loan details",
    "db-pension": "pension details",
}


def _money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "?"
    sign = "−" if amount < 0 else ""
    return f"{sign}£{abs(amount):,.2f}"


def _day(value: Any) -> str:
    try:
        d = date.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return f"{d.day} {d:%b %Y}"


def _account(db: Session, account_id: str) -> str:
    account = db.get(Account, int(account_id))
    return account.name if account else "an account"


def _instrument(db: Session, instrument_id: Any) -> str:
    try:
        instrument = db.get(Instrument, int(instrument_id))
    except (TypeError, ValueError):
        return "an instrument"
    return instrument.symbol if instrument else "an instrument"


def _units(value: Any) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return "?"


def describe(db: Session, method: str, path: str, body: Any) -> str:
    body = body if isinstance(body, dict) else {}
    p = path.removeprefix("/api")

    if m := re.fullmatch(r"/accounts/(\d+)/balances", p):
        return f"Balance {_money(body.get('balance_gbp'))} for {_account(db, m[1])} on {_day(body.get('date'))}"
    if p == "/balances/bulk" and method == "POST":
        n = len(body.get("entries") or [])
        return f"Quick update of {n} balance{'s' if n != 1 else ''}"
    if m := re.fullmatch(r"/accounts/(\d+)/transactions", p):
        kind = str(body.get("type", "transaction")).replace("_", " ").lower()
        where = _account(db, m[1])
        if body.get("instrument_id") is not None and body.get("units") is not None:
            return (
                f"{kind.capitalize()} {_units(body['units'])} {_instrument(db, body['instrument_id'])} "
                f"in {where} on {_day(body.get('date'))}"
            )
        return f"{kind.capitalize()} {_money(body.get('amount_gbp'))} in {where} on {_day(body.get('date'))}"
    if m := re.fullmatch(r"/accounts/(\d+)/holdings/(\d+)", p):
        symbol = _instrument(db, m[2])
        if method == "DELETE":
            return f"Removed {symbol} from {_account(db, m[1])}"
        return f"Set {symbol} in {_account(db, m[1])} to {_units(body.get('units'))} units"
    if m := re.fullmatch(r"/accounts/(\d+)/cash", p):
        return f"Set cash in {_account(db, m[1])} to {_money(body.get('cash_gbp'))}"
    if p == "/accounts" and method == "POST":
        return f"New account: {body.get('name', 'unnamed')}"
    if m := re.fullmatch(r"/accounts/(\d+)", p):
        return f"{'Deleted' if method == 'DELETE' else 'Edited'} {_account(db, m[1])}"
    if m := re.fullmatch(r"/accounts/(\d+)/(archive|unarchive)", p):
        return f"{m[2].capitalize()}d {_account(db, m[1])}"
    if m := re.fullmatch(r"/accounts/(\d+)/([a-z-]+)(?:/.*)?", p):
        noun = _NOUNS.get(m[2], m[2].replace("-", " "))
        return f"{_VERBS.get(method, 'Changed')} {noun} on {_account(db, m[1])}"
    if p == "/transactions/confirm":
        n = len(body.get("items") or [])
        return f"Confirmed {n} pending transaction{'s' if n != 1 else ''}"
    if p == "/people" and method == "POST":
        return f"New person: {body.get('name', 'unnamed')}"
    if p == "/goals" and method == "POST":
        return f"New goal: {body.get('name', 'unnamed')}"

    resource = next((s for s in reversed(p.split("/")) if s and not s.isdigit()), "item")
    return f"{_VERBS.get(method, 'Changed')} {_NOUNS.get(resource, resource.replace('-', ' '))}"

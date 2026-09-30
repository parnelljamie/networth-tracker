"""docs/07-mobile.md "Ids created on the phone".

On the phone every new row with a single integer `id` primary key gets an id from `PHONE_ID_BASE`
up, from **one counter shared by every table**, so a phone id names exactly one row anywhere.
Rows copied from the PC are far below it, so any integer >= `PHONE_ID_BASE` in a path or a JSON
body is an id the phone made, and the PC can swap it for the id it made for the same row.
"""
from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import Integer, event, func, select
from sqlalchemy.orm import Mapper

from app.config import settings
from app.db import Base

PHONE_ID_BASE = 2**40


def is_phone_id(value: Any) -> bool:
    # bool is an int subclass; True is never an id.
    return isinstance(value, int) and not isinstance(value, bool) and value >= PHONE_ID_BASE


def _single_int_id_column(mapper: Mapper):
    pk = mapper.primary_key
    if len(pk) != 1 or pk[0].name != "id" or not isinstance(pk[0].type, Integer):
        return None
    if pk[0].table.name.startswith("sync_"):
        return None  # local bookkeeping; never sent to the PC
    return pk[0]


_counter: int | None = None
_counter_lock = threading.Lock()


def _id_tables() -> list:
    tables = []
    for mapper in Base.registry.mappers:
        column = _single_int_id_column(mapper)
        if column is not None:
            tables.append(column)
    return tables


def _highest_phone_id(connection) -> int:  # noqa: ANN001
    highest = PHONE_ID_BASE - 1
    for column in _id_tables():
        value = connection.execute(select(func.max(column)).where(column >= PHONE_ID_BASE)).scalar()
        if value is not None:
            highest = max(highest, value)
    return highest


def reset_counter() -> None:
    """Forget the counter, e.g. after the database file was replaced."""
    global _counter
    with _counter_lock:
        _counter = None


@event.listens_for(Base, "before_insert", propagate=True)
def _allocate_phone_id(mapper: Mapper, connection, target) -> None:  # noqa: ANN001
    global _counter
    if settings.role != "phone":
        return
    column = _single_int_id_column(mapper)
    if column is None or getattr(target, column.key) is not None:
        return
    with _counter_lock:
        if _counter is None:
            _counter = _highest_phone_id(connection)
        table_max = connection.execute(select(func.max(column))).scalar() or 0
        _counter = max(_counter + 1, table_max + 1, PHONE_ID_BASE)
        setattr(target, column.key, _counter)


def rewrite_ids(value: Any, id_map: dict[int, int]) -> tuple[Any, int | None]:
    """Replace every phone id in a JSON value with its PC id. Returns the new value and the first
    phone id that has no mapping (its create was rejected), or None."""
    missing: int | None = None

    def walk(v: Any) -> Any:
        nonlocal missing
        if is_phone_id(v):
            if v in id_map:
                return id_map[v]
            if missing is None:
                missing = v
            return v
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    return walk(value), missing


def rewrite_path(path: str, id_map: dict[int, int]) -> tuple[str, int | None]:
    parts = path.split("/")
    missing: int | None = None
    for i, part in enumerate(parts):
        if part.isdigit() and is_phone_id(int(part)):
            phone_id = int(part)
            if phone_id in id_map:
                parts[i] = str(id_map[phone_id])
            elif missing is None:
                missing = phone_id
    return "/".join(parts), missing


def learn_ids(phone_response: Any, pc_response: Any, id_map: dict[int, int]) -> None:
    """Walk the phone's and the PC's responses to the same request side by side; wherever the
    phone's has a phone id, the PC's has the id it made for the same row."""
    if is_phone_id(phone_response):
        if isinstance(pc_response, int) and not isinstance(pc_response, bool):
            id_map.setdefault(phone_response, pc_response)
        return
    if isinstance(phone_response, list) and isinstance(pc_response, list):
        for a, b in zip(phone_response, pc_response, strict=False):
            learn_ids(a, b, id_map)
    elif isinstance(phone_response, dict) and isinstance(pc_response, dict):
        for key, a in phone_response.items():
            if key in pc_response:
                learn_ids(a, pc_response[key], id_map)

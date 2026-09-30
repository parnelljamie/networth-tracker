"""docs/07-mobile.md: pairing (PC) and sync client (phone) endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SyncDeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    paired_at: datetime
    last_seen_at: datetime | None
    last_sync_at: datetime | None


class SyncStatusOut(BaseModel):
    role: str
    enabled: bool
    running: bool
    port: int
    addresses: list[str]
    pc_name: str
    devices: list[SyncDeviceOut]


class SyncEnabledIn(BaseModel):
    enabled: bool
    port: int | None = Field(default=None, ge=1024, le=65535)


class PairIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class PairOut(BaseModel):
    device_id: int
    token: str
    pairing_uri: str
    addresses: list[str]
    port: int


class SyncRejectedOut(BaseModel):
    summary: str
    message: str | None


class SyncReportOut(BaseModel):
    status: str  # ok | pc_unreachable | version_mismatch | already_running | failed
    at: str | None = None
    applied: int = 0
    rejected: list[SyncRejectedOut] = []
    message: str | None = None


class SyncClientOut(BaseModel):
    role: str
    paired: bool
    pc_name: str | None
    last_sync_at: str | None
    last_attempt_at: str | None
    pending_changes: int
    last_report: SyncReportOut | None


class SyncClientPairIn(BaseModel):
    pairing_uri: str


def report_out(report: dict[str, Any] | None) -> SyncReportOut | None:
    return SyncReportOut(**report) if report else None

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    # docs/07-mobile.md "Roles": the UI hides desktop-only pages and shows Sync on the phone.
    role: str = "desktop"

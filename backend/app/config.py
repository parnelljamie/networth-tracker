from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core import paths


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NW_")

    data_dir: str = str(paths.data_dir())
    host: str = "127.0.0.1"
    port: int = 8000
    env: str = "development"
    # docs/07-mobile.md "Roles": "desktop" (every PC install) or "phone" (the Android app).
    role: str = "desktop"
    # Settings -> Updates reads the latest release from here. Versions up to 0.5.2 read
    # parnelljamie/waymark-releases instead, which release.yml still publishes to for them.
    update_repo: str = "parnelljamie/networth-tracker"


settings = Settings()

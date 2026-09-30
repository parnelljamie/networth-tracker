"""The live price provider for this install: yfinance on the PC, plain HTTPS on the phone
(docs/07-mobile.md), where yfinance's curl_cffi dependency can't be installed."""
from __future__ import annotations

from app.config import settings
from app.providers.base import PriceProvider


def default_provider() -> PriceProvider:
    if settings.role == "phone":
        from app.providers.yahoo_http import YahooHttpProvider

        return YahooHttpProvider()
    from app.providers.yahoo import YahooProvider

    return YahooProvider()

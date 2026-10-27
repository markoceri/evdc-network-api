"""EVDC Network API — Unofficial Python client for the EVDC EV charging network API."""

from __future__ import annotations

__version__ = "0.1.0"

from .async_client import AsyncEvdcApiClient
from .client import EvdcApiClient
from .const import DEFAULT_BASE_URL, DEFAULT_PAGE_SIZE
from .exceptions import EvdcApiError, EvdcAuthError, EvdcTwoFactorRequiredError
from .models import (
    Address,
    ChargingFacility,
    ChargingHistoryPage,
    ChargingSession,
    Evse,
    OngoingSession,
    Pricing,
    Receipt,
    SessionProgress,
    User,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_PAGE_SIZE",
    "Address",
    "AsyncEvdcApiClient",
    "ChargingFacility",
    "ChargingHistoryPage",
    "ChargingSession",
    "EvdcApiClient",
    "EvdcApiError",
    "EvdcAuthError",
    "EvdcTwoFactorRequiredError",
    "Evse",
    "OngoingSession",
    "Pricing",
    "Receipt",
    "SessionProgress",
    "User",
    "__version__",
]

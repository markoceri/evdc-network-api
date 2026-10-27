"""EVDC Network API — Unofficial Python client for the EVDC EV charging network API."""

from __future__ import annotations

__version__ = "0.1.0"

from .async_client import AsyncEvdcApiClient
from .client import EvdcApiClient
from .const import DEFAULT_BASE_URL, DEFAULT_PAGE_SIZE
from .crypto import generate_device_key
from .exceptions import EvdcApiError, EvdcAuthError, EvdcTwoFactorRequiredError
from .models import (
    Address,
    ChargingFacility,
    ChargingHistoryPage,
    ChargingSession,
    ConnectedSession,
    Evse,
    Notification,
    NotificationPage,
    OngoingSession,
    Pricing,
    Receipt,
    SessionProgress,
    User,
    Wallet,
    WalletHistoryPage,
    WalletTransaction,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_PAGE_SIZE",
    "Address",
    "AsyncEvdcApiClient",
    "ChargingFacility",
    "ChargingHistoryPage",
    "ChargingSession",
    "ConnectedSession",
    "EvdcApiClient",
    "EvdcApiError",
    "EvdcAuthError",
    "EvdcTwoFactorRequiredError",
    "Evse",
    "Notification",
    "NotificationPage",
    "OngoingSession",
    "Pricing",
    "Receipt",
    "SessionProgress",
    "User",
    "Wallet",
    "WalletHistoryPage",
    "WalletTransaction",
    "__version__",
    "generate_device_key",
]

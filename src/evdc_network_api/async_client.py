"""Async wrapper for the EVDC API client.

Wraps the synchronous ``EvdcApiClient`` using ``asyncio.to_thread()`` to provide a non-blocking interface for async
frameworks (Home Assistant, FastAPI, etc.).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .const import DEFAULT_NEARBY_RADIUS_M, DEFAULT_PAGE_SIZE, NEARBY_PAGE_SIZE

if TYPE_CHECKING:
    from .client import EvdcApiClient
    from .models import ChargingHistoryPage, ChargingSession, ConnectedSession, Evse, OngoingSession, Receipt, User


class AsyncEvdcApiClient:
    """Async wrapper around :class:`EvdcApiClient`.

    All methods delegate to the sync client via ``asyncio.to_thread()``.
    """

    def __init__(self, client: EvdcApiClient) -> None:
        self._client = client

    @property
    def client(self) -> EvdcApiClient:
        """Access the underlying synchronous client."""
        return self._client

    async def close(self) -> None:
        await asyncio.to_thread(self._client.close)

    async def login(self) -> User:
        return await asyncio.to_thread(self._client.login)

    @property
    def two_factor_pending(self) -> str | None:
        """The pending second factor (``"email"`` / ``"totp"``), or ``None``."""
        return self._client.two_factor_pending

    async def verify_two_factor(self, code: str) -> User:
        return await asyncio.to_thread(self._client.verify_two_factor, code)

    async def verify_recovery_code(self, code: str) -> User:
        return await asyncio.to_thread(self._client.verify_recovery_code, code)

    async def resend_two_factor_code(self) -> None:
        await asyncio.to_thread(self._client.resend_two_factor_code)

    async def token_refresh(self) -> None:
        await asyncio.to_thread(self._client.token_refresh)

    async def get_profile(self) -> User:
        return await asyncio.to_thread(self._client.get_profile)

    async def get_charge_history(self, page: int = 1, limit: int = DEFAULT_PAGE_SIZE) -> ChargingHistoryPage:
        return await asyncio.to_thread(self._client.get_charge_history, page, limit)

    async def get_all_charge_history(
        self, limit: int = DEFAULT_PAGE_SIZE, max_pages: int | None = None
    ) -> list[ChargingSession]:
        """Fetch the whole charging history (all pages, or up to *max_pages*)."""
        return await asyncio.to_thread(lambda: list(self._client.iter_charge_history(limit, max_pages)))

    async def get_ongoing_sessions(self) -> list[OngoingSession]:
        return await asyncio.to_thread(self._client.get_ongoing_sessions)

    async def get_receipt(self, session_id: str) -> Receipt:
        return await asyncio.to_thread(self._client.get_receipt, session_id)

    async def get_evse(self, evse_id: str) -> Evse:
        return await asyncio.to_thread(self._client.get_evse, evse_id)

    async def get_connected_sessions(self) -> list[ConnectedSession]:
        return await asyncio.to_thread(self._client.get_connected_sessions)

    async def revoke_session(self, session_id: str) -> None:
        await asyncio.to_thread(self._client.revoke_session, session_id)

    async def revoke_all_sessions(self) -> None:
        await asyncio.to_thread(self._client.revoke_all_sessions)

    async def get_nearby_stations(
        self, latitude: float, longitude: float, page: int = 1, page_size: int = NEARBY_PAGE_SIZE
    ) -> list[Evse]:
        return await asyncio.to_thread(self._client.get_nearby_stations, latitude, longitude, page, page_size)

    async def find_stations_near(
        self,
        latitude: float,
        longitude: float,
        *,
        radius_m: float = DEFAULT_NEARBY_RADIUS_M,
        max_results: int | None = None,
    ) -> list[Evse]:
        """Charging points within *radius_m* metres of a point, nearest first (see the sync client)."""
        return await asyncio.to_thread(
            lambda: self._client.find_stations_near(latitude, longitude, radius_m=radius_m, max_results=max_results)
        )

"""Async wrapper for the EVDC API client.

Wraps the synchronous ``EvdcApiClient`` using ``asyncio.to_thread()`` to provide a non-blocking interface for async
frameworks (Home Assistant, FastAPI, etc.).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .const import DEFAULT_PAGE_SIZE

if TYPE_CHECKING:
    from .client import EvdcApiClient
    from .models import ChargingHistoryPage, ChargingSession, Evse, OngoingSession, Receipt, User


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

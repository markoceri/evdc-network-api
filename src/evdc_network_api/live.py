"""Live charging session progress over socket.io.

Requires the ``live`` extra: ``pip install "evdc-network-api[live]"``.

The backend pushes ``chargingSessionProgress`` events while a session runs, when the charge point operator sends
progress notifications through Hubject. Some stations never do: poll
:meth:`EvdcApiClient.get_ongoing_sessions` as a fallback. The event format is verified on a real session: about
one event every 5 minutes, with the consumed energy and no power.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .const import SOCKET_EVENT_PROGRESS, SOCKET_EVENT_REGISTER
from .exceptions import EvdcApiError
from .models import SessionProgress

if TYPE_CHECKING:
    from collections.abc import Callable

    from .client import EvdcApiClient

_LOGGER = logging.getLogger(__name__)


class EvdcLiveClient:
    """Receives live progress of the user's ongoing sessions.

    ``on_progress`` is called with a :class:`SessionProgress` for each update, from the socket's background thread.
    ``on_event`` (optional) receives every other server event as ``(name, args)``, for debugging.
    """

    def __init__(
        self,
        client: EvdcApiClient,
        on_progress: Callable[[SessionProgress], None],
        *,
        on_event: Callable[[str, tuple[Any, ...]], None] | None = None,
    ) -> None:
        try:
            import socketio
        except ImportError as exc:  # pragma: no cover - depends on the installed extras
            raise EvdcApiError('Live updates need the "live" extra: pip install "evdc-network-api[live]"') from exc

        self._client = client
        self._on_progress = on_progress
        self._on_event = on_event
        self._sio = socketio.Client(reconnection=True, reconnection_delay=1, reconnection_delay_max=5)
        self._sio.on("connect", self._handle_connect)
        self._sio.on("connect_error", self._handle_connect_error)
        self._sio.on(SOCKET_EVENT_PROGRESS, self._handle_progress)
        self._sio.on("*", self._handle_any)

    @property
    def connected(self) -> bool:
        return bool(self._sio.connected)

    def connect(self) -> None:
        """Open the socket with the current access token, logging in or refreshing first if needed."""
        self._client._ensure_token()
        self._sio.connect(self._url(), transports=["websocket"])

    def wait(self) -> None:
        """Block until the socket is disconnected."""
        self._sio.wait()

    def disconnect(self) -> None:
        self._sio.disconnect()

    def _url(self) -> str:
        return f"{self._client.base_url}?token={self._client.access_token}"

    def _handle_connect(self) -> None:
        _LOGGER.debug("EVDC socket connected")
        self._sio.emit(SOCKET_EVENT_REGISTER)

    def _handle_connect_error(self, data: Any) -> None:
        message = data.get("message") if isinstance(data, dict) else str(data)
        _LOGGER.debug("EVDC socket connect error: %s", message)
        if message and "auth" in message.lower():
            # The token travels in the URL: refresh it and point the next reconnection attempt at the new one.
            try:
                self._client._reauthenticate()
            except EvdcApiError:
                _LOGGER.warning("EVDC socket authentication failed and the token could not be refreshed")
                return
            self._sio.connection_url = self._url()

    def _handle_progress(self, *args: Any) -> None:
        payload = next((a for a in args if isinstance(a, dict)), None)
        if payload is None:
            return
        progress = SessionProgress.from_dict(payload)
        if progress.evse_id is None:
            _LOGGER.debug("EVDC progress event without an EVSE id, ignored")
            return
        self._on_progress(progress)

    def _handle_any(self, event: str, *args: Any) -> None:
        if self._on_event is not None:
            self._on_event(event, args)

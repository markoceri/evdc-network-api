"""EVDC API exception hierarchy."""

from __future__ import annotations


class EvdcApiError(Exception):
    """Base EVDC API error.

    ``status_code`` is the HTTP status when the error comes from a response.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class EvdcAuthError(EvdcApiError):
    """Authentication failed (wrong credentials, expired session, social-only account)."""


class EvdcTwoFactorRequiredError(EvdcAuthError):
    """The account has two-factor authentication enabled, which this library does not support yet."""

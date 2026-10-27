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
    """The account has two-factor authentication enabled and the login needs a verification code.

    Complete the login with :meth:`EvdcApiClient.verify_two_factor` (or
    :meth:`EvdcApiClient.verify_recovery_code`). ``method`` is the factor the backend asks for,
    ``"email"`` (a one-time code sent by e-mail) or ``"totp"`` (an authenticator app).
    """

    def __init__(self, message: str, *, method: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message, status_code=status_code)
        self.method = method

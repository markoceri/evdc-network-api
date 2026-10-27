"""EVDC API constants."""

from __future__ import annotations

DEFAULT_BASE_URL = "https://api-v2.evdccharge.co/"
DEFAULT_APP_VERSION = "1.1.10"
DEFAULT_DEVICE_MODEL = "Android-14-Google-Pixel 8"
DEFAULT_TIMEOUT = 30
DEFAULT_PAGE_SIZE = 10

# Constant ``req-scope`` header the app sends with every request.
REQ_SCOPE = "MOBILEMED-FE"

# RSA public key the app uses to encrypt the password for ``/api/signIn-enc``
# (``PASSWORD_ENC_KEY`` in the app's build config). Public, needed for interoperability.
PASSWORD_ENC_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAw9Ks8dfDPz/dZA+UjeQi
3Y80D65ZbHqUOk0mA7quzu/Jp2qNSqG3HZKVd/run5PyJ1DBFSAG9cAwbIksj4DH
ysUDxwmYkZ6MN5jf1y18bB5rWMAQZejq5FAi5hNG0dde+xwI45a5NwolE89xjbpv
l9pFEXm5h4+Lo2rjchPah7POd/a6iYsJyfMAYVkzyIYVYp5nX+QLSrjNrXyooGGm
db9sj+cWCE1kCPQlJeLkOvMKyg4CIjtt54GdqdVZqH0VTTr90CEmPo8YyV9U/cmK
WT4dArYMR/uJs9wikhVX/odWl7BUJ3xEzO3OKROIdJfDFeZVYFKLVL33NasLihR6
EQIDAQAB
-----END PUBLIC KEY-----
"""  # noqa: S105 - a public key, not a secret

# Endpoint paths, relative to the base URL.
PATH_SIGN_IN = "api/signIn-enc"
PATH_REFRESH_TOKEN = "api/refresh-token"  # noqa: S105 - a URL path, not a secret
PATH_SIGN_OUT = "api/signOut"
PATH_PROFILE = "api/profile"
PATH_CHARGE_HISTORY = "api/hubject/charge-history"
PATH_RECEIPT = "api/hubject/download-pdf/{session_id}"
PATH_ONGOING_SESSIONS = "api/hubject/ongoing-sessionsV2"
PATH_EVSE = "api/hubject/{evse_id}"

# socket.io event names.
SOCKET_EVENT_REGISTER = "register"
SOCKET_EVENT_PROGRESS = "chargingSessionProgress"

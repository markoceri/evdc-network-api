"""List the account's logged-in sessions / devices, and optionally revoke them.

    python sessions.py                 # list the connected sessions
    python sessions.py revoke <id>     # revoke one session by its id
    python sessions.py revoke-all      # revoke the other sessions

Set EVDC_DEVICE_ID to a stable value so this client is one device, not a new one each run.
"""

import os
import sys

from evdc_network_api import EvdcApiClient, EvdcApiError

EMAIL = os.environ.get("EVDC_EMAIL", "")
PASSWORD = os.environ.get("EVDC_PASSWORD", "")
DEVICE_ID = os.environ.get("EVDC_DEVICE_ID")  # stable 64-hex id, reused across runs

if not EMAIL or not PASSWORD:
    print("ERROR: set EVDC_EMAIL and EVDC_PASSWORD.")
    sys.exit(1)


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    with EvdcApiClient(email=EMAIL, password=PASSWORD, device_id=DEVICE_ID) as client:
        try:
            if command == "revoke" and len(sys.argv) > 2:
                client.revoke_session(sys.argv[2])
                print(f"Revoked session {sys.argv[2]}")
            elif command == "revoke-all":
                client.revoke_all_sessions()
                print("Revoked the other sessions")
            else:
                for s in client.get_connected_sessions():
                    here = " (this device)" if s.is_current else ""
                    location = ", ".join(p for p in (s.city, s.country) if p)
                    print(
                        f"{s.id}  {s.device_model or '?':<20} {location or s.ip or '':<20} {s.created_at or ''}{here}"
                    )
        except EvdcApiError as exc:
            print(f"EVDC error: {exc}")
            sys.exit(1)


if __name__ == "__main__":
    main()

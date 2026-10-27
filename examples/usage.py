"""Log in to EVDC and print the account, ongoing sessions and recent charging history."""

import os
import sys
from pathlib import Path

from evdc_network_api import EvdcApiClient, EvdcApiError

EMAIL = os.environ.get("EVDC_EMAIL", "")
PASSWORD = os.environ.get("EVDC_PASSWORD", "")
DEVICE_ID = os.environ.get("EVDC_DEVICE_ID")  # optional: a stable 64-hex id, reused across runs
RECEIPT_DIR = os.environ.get("EVDC_RECEIPT_DIR")  # optional: download the latest receipt here

if not EMAIL or not PASSWORD:
    print("ERROR: Set EVDC_EMAIL and EVDC_PASSWORD environment variables.")
    sys.exit(1)


def main() -> None:
    with EvdcApiClient(email=EMAIL, password=PASSWORD, device_id=DEVICE_ID) as client:
        try:
            user = client.login()
            print(f"Logged in as {user.first_name} {user.last_name} ({user.email})\n")

            ongoing = client.get_ongoing_sessions()
            print(f"Ongoing sessions: {len(ongoing)}")
            for session in ongoing:
                print(f"  {session.evse_id}  started {session.created_at}  {session.amount} {session.currency}")

            page = client.get_charge_history(page=1, limit=10)
            print(f"\nCharging history: {page.total_documents} sessions, showing page {page.page}")
            for s in page.sessions:
                when = f"{s.created_at:%Y-%m-%d %H:%M}" if s.created_at else "?"
                print(
                    f"  {when}  {s.energy_kwh or 0:6.2f} kWh  {s.amount or 0:7.2f} {s.currency or ''}"
                    f"  {s.evse_id}  {s.operator or ''}"
                )

            if RECEIPT_DIR and page.sessions and page.sessions[0].session_id:
                latest = page.sessions[0]
                receipt = client.get_receipt(latest.session_id or "")
                target = Path(RECEIPT_DIR) / (receipt.filename or f"{latest.session_id}.pdf")
                target.write_bytes(receipt.content)
                print(f"\nSaved receipt to {target}")
        except EvdcApiError as exc:
            print(f"EVDC error: {exc}")
            sys.exit(1)


if __name__ == "__main__":
    main()

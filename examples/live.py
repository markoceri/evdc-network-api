"""Print live progress of ongoing charging sessions (needs the ``live`` extra)."""

import os
import sys

from evdc_network_api import EvdcApiClient, SessionProgress
from evdc_network_api.live import EvdcLiveClient

EMAIL = os.environ.get("EVDC_EMAIL", "")
PASSWORD = os.environ.get("EVDC_PASSWORD", "")

if not EMAIL or not PASSWORD:
    print("ERROR: Set EVDC_EMAIL and EVDC_PASSWORD environment variables.")
    sys.exit(1)


def on_progress(progress: SessionProgress) -> None:
    print(
        f"{progress.time}  {progress.evse_id}  power={progress.power_kw} kW  "
        f"energy={progress.consumed_energy_kwh} kWh  current={progress.current_a} A"
    )


def main() -> None:
    client = EvdcApiClient(email=EMAIL, password=PASSWORD)
    sessions = client.get_ongoing_sessions()
    print(f"Ongoing sessions: {len(sessions)}. Waiting for live updates, Ctrl+C to stop.")

    live = EvdcLiveClient(client, on_progress, on_event=lambda name, args: print(f"[event] {name}"))
    live.connect()
    try:
        live.wait()
    except KeyboardInterrupt:
        pass
    finally:
        live.disconnect()
        client.close()


if __name__ == "__main__":
    main()

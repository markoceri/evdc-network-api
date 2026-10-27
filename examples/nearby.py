"""List the charging points around a position (e.g. the vehicle's) with their price and status."""

import os
import sys

from evdc_network_api import EvdcApiClient, EvdcApiError

EMAIL = os.environ.get("EVDC_EMAIL", "")
PASSWORD = os.environ.get("EVDC_PASSWORD", "")

if not EMAIL or not PASSWORD or len(sys.argv) < 3:
    print("usage: EVDC_EMAIL=... EVDC_PASSWORD=... python nearby.py <latitude> <longitude> [radius_m]")
    sys.exit(1)


def main() -> None:
    latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    radius_m = float(sys.argv[3]) if len(sys.argv) > 3 else 1000

    with EvdcApiClient(email=EMAIL, password=PASSWORD) as client:
        try:
            stations = client.find_stations_near(latitude, longitude, radius_m=radius_m)
        except EvdcApiError as exc:
            print(f"EVDC error: {exc}")
            sys.exit(1)

    print(f"{len(stations)} charging points within {radius_m:.0f} m")
    for evse in stations:
        p = evse.pricing
        price = f"{p.price} {p.currency}/{p.unit} (card {p.card_price})" if p else "no price"
        print(
            f"{evse.distance_m or 0:6.0f} m  {evse.status or '?':<12} {evse.max_power_kw or 0:5.0f} kW  "
            f"{price:<28} {evse.operator_name or ''}  {evse.evse_id}"
        )


if __name__ == "__main__":
    main()

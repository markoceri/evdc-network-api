# Examples

Example scripts for reading your own EVDC data.

## Prerequisites

1. Install the package from the project root (the `live` extra is only needed by `live.py`):

   ```bash
   pip install -e ".[live]"
   ```

2. Set your EVDC credentials. Only email/password accounts without two-factor authentication are supported for now;
   an account created with Google or Apple sign-in has no EVDC password.

   ```bash
   export EVDC_EMAIL="you@example.com"
   export EVDC_PASSWORD="your_password"
   ```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `EVDC_EMAIL` | yes | Account email |
| `EVDC_PASSWORD` | yes | Account password |
| `EVDC_DEVICE_ID` | no | Stable 64-hex device id, reused across runs (a random one is generated otherwise) |
| `EVDC_RECEIPT_DIR` | no | `usage.py` saves the latest session's PDF receipt here |

## Scripts

| Script | What it does |
|---|---|
| `usage.py` | Logs in and prints the account, ongoing sessions and the first page of the charging history |
| `live.py` | Connects to the live socket and prints `chargingSessionProgress` updates while charging |
| `nearby.py` | `python nearby.py <lat> <lng> [radius_m]`: charging points around a position, with price and status |

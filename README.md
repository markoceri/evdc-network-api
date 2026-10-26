# evdc-network-api

[![License](https://img.shields.io/github/license/markoceri/evdc-network-api)](https://github.com/markoceri/evdc-network-api/blob/main/LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/type--checked-mypy-blue.svg)](https://mypy-lang.org/)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20me-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/markoceri)

Unofficial Python client for the [EVDC](https://evdc.network) EV charging network API.

> [!IMPORTANT]
> This project is **not affiliated with, endorsed by, or supported by EVDC** or its developers.
> It is an independent interoperability project. Read the [legal notice](LEGAL.md) before using or contributing.

## Purpose

EVDC keeps a log of the user's charging sessions — duration, energy delivered and cost — but offers no public API
to retrieve it. This library gives an EVDC account holder programmatic access to **their own** charging data, so it
can be imported into other tools.

A typical use is charging cost tracking: vehicle or home-automation software often knows when and how much a car
charged, but not what each session **cost** at a public charger. With this library such software can match its
charging sessions with the EVDC sessions and attach the price paid to each of them.

```
 EVDC cloud ──► evdc-network-api ──► your application
               (sessions, kWh, cost)
```

## Scope

In scope:

- authentication with the user's own EVDC credentials;
- charging session history: start and end time, station, energy delivered, cost, currency;
- the data needed to read the history (account, station and tariff details).

Out of scope, and not accepted as contributions:

- starting, stopping or paying for charging sessions on behalf of third parties;
- access to any data other than the authenticated user's own;
- circumventing payment, tariffs, rate limits, or any technical protection measure;
- redistribution of EVDC code, assets, keys or certificates;
- bulk scraping of stations, prices or other network-wide data.

## How the interface is documented

The API is documented by observing the traffic between the official EVDC app and its backend, while using the app
with the author's own lawfully held account, and by studying the app only as far as needed to understand the data
format exchanged with the server. Only the information strictly needed for interoperability is recorded in this
repository, under [`docs/`](docs/). See the [legal notice](LEGAL.md) for the European legal framework this relies on.

## Status

🚧 Early development — the API surface is not defined yet.

## Installation

Not yet published on PyPI.

## Legal

- [Legal notice and interoperability statement](LEGAL.md)

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).

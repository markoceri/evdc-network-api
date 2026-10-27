# Contributing to evdc-network-api

Thanks for your interest in contributing! Read the [legal notice](LEGAL.md) and the scope in the
[README](README.md#scope) first: contributions outside that scope are not accepted.

## Development Setup

### Prerequisites

- Python 3.12+
- [Hatch](https://hatch.pypa.io/) (recommended) or pip

### Clone and install

```bash
git clone https://github.com/markoceri/evdc-network-api.git
cd evdc-network-api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running tests

```bash
pytest
pytest --cov   # with coverage
```

### Linting and type checking

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
```

### Pre-commit hooks

```bash
pre-commit install
pre-commit install --hook-type pre-push
```

This runs `ruff` before each commit, and `mypy` and `pytest` before each push.

## Project Structure

```
src/evdc_network_api/
├── __init__.py          # Package exports and version
├── client.py            # Synchronous API client
├── async_client.py      # Async wrapper around the sync client
├── live.py              # Live session progress over socket.io (optional extra)
├── models.py            # Dataclasses for the account, sessions, stations
├── const.py             # Constants (URLs, endpoints, app public key)
├── crypto.py            # Password encryption
└── exceptions.py        # Custom exceptions
```

## Working with real data

- Never commit captures, APKs, decompiled sources, credentials or tokens. Keep them in `ignore/` (git-ignored).
- Test fixtures must be **anonymised**: fake ids, names, addresses, coordinates and amounts.
- Document in `docs/api.md` only what is needed to interoperate, with personal data redacted.
- Keep request rates low when testing against the real backend.

## Pull Request Guidelines

### Before you start

- Check the [issue tracker](https://github.com/markoceri/evdc-network-api/issues) for existing issues or feature
  requests.
- For new features or significant changes, open an issue first to discuss the approach.

### PR requirements

- Keep changes small and focused — one concern per PR.
- Add or update tests for any new functionality.
- Ensure all checks pass: `pytest`, `ruff check`, `ruff format --check`, `mypy`.
- Follow the existing code style — the project uses [Ruff](https://github.com/astral-sh/ruff) for formatting and
  linting.

### Commit messages

Use [conventional commits](https://www.conventionalcommits.org/):

- `feat:` new feature or field
- `fix:` bug fix
- `docs:` documentation changes
- `chore:` maintenance, dependency updates
- `refactor:` code restructuring without behaviour change
- `test:` adding or updating tests

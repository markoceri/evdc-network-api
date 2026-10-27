"""Shared test helpers: fixtures loader and a fake ``requests.Session``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import requests

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@dataclass
class FakeResponse:
    status_code: int
    body: Any

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    def json(self) -> Any:
        if self.body is None:
            raise ValueError("no JSON")
        return self.body


@dataclass
class Call:
    method: str
    path: str
    headers: dict[str, str]
    params: dict[str, Any] | None
    json: dict[str, Any] | None


@dataclass
class FakeSession:
    """Routes requests by ``(method, path)`` to queued responses and records every call.

    A route value is either a single response (reused) or a list consumed one per call.
    """

    base_url: str = "https://api-v2.evdccharge.co/"
    routes: dict[tuple[str, str], FakeResponse | list[FakeResponse]] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)
    closed: bool = False

    def add(self, method: str, path: str, *responses: FakeResponse) -> None:
        self.routes[(method, path)] = list(responses) if len(responses) > 1 else responses[0]

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> FakeResponse:
        path = url.removeprefix(self.base_url)
        self.calls.append(Call(method, path, headers, params, json))
        route = self.routes.get((method, path))
        if route is None:
            raise requests.ConnectionError(f"no route for {method} {path}")
        if isinstance(route, list):
            return route.pop(0) if len(route) > 1 else route[0]
        return route

    def close(self) -> None:
        self.closed = True

    def paths(self) -> list[str]:
        return [c.path for c in self.calls]


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()

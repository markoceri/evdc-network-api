"""EVDC API data models.

Field names follow the backend payloads; see ``docs/api.md``. ``User`` and the history page envelope are verified
against real responses. ``ChargingSession``, ``OngoingSession``, ``Receipt``, ``Evse`` and ``SessionProgress`` are
reconstructed from the app and may gain or change fields once seen populated, so every field is optional and the
original payload stays available as ``raw``.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Keys never kept in ``raw`` payloads, so models can be printed or logged safely.
_SECRET_KEYS = frozenset({"accessToken", "refreshToken", "token", "password", "fcmToken", "fcmTokens", "biometricKeys"})


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 string or an epoch (seconds or milliseconds) into an aware UTC datetime."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        seconds = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(seconds, tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _without_secrets(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k not in _SECRET_KEYS}


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class User:
    """The authenticated account (``/api/profile`` and the login response)."""

    id: str | None
    email: str | None
    first_name: str | None = None
    last_name: str | None = None
    mobile: str | None = None
    country_short_code: str | None = None
    is_verified: bool | None = None
    is_two_factor_enabled: bool | None = None
    two_factor_method: str | None = None
    evco_id: str | None = None
    rfid_method: str | None = None
    company_name: str | None = None
    vat_id: str | None = None
    total_spending: float | None = None
    last_visit_at: datetime | None = None

    # -- Raw payload, secrets removed --
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        return cls(
            id=_str(data.get("_id")),
            email=_str(data.get("email")),
            first_name=_str(data.get("firstName")),
            last_name=_str(data.get("lastName")),
            mobile=_str(data.get("mobile")),
            country_short_code=_str(data.get("countryShortCode")),
            is_verified=_bool(data.get("isVerified")),
            is_two_factor_enabled=_bool(data.get("isTwoFactorEnabled")),
            two_factor_method=_str(data.get("twoFactorMethod")),
            evco_id=_str(data.get("evcoId")),
            rfid_method=_str(data.get("rfidMethod")),
            company_name=_str(data.get("companyName")),
            vat_id=_str(data.get("vatId")),
            total_spending=_float(data.get("totalSpending")),
            last_visit_at=_datetime(data.get("lastVisitAt")),
            raw=_without_secrets(data),
        )


# ---------------------------------------------------------------------------
# Stations and tariffs
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Address:
    """Postal address of a charging station (Hubject OICP field names)."""

    street: str | None = None
    city: str | None = None
    postal_code: str | None = None
    region: str | None = None
    state: str | None = None
    country: str | None = None

    @classmethod
    def from_dict(cls, data: Any) -> Address | None:
        if not isinstance(data, dict) or not data:
            return None
        return cls(
            street=_str(data.get("Street")),
            city=_str(data.get("City")),
            postal_code=_str(data.get("PostalCode")),
            region=_str(data.get("Region")),
            state=_str(data.get("State")),
            country=_str(data.get("Country")),
        )


@dataclass(slots=True)
class Pricing:
    """A tariff, per ``unit`` (e.g. ``kWh``), in ``currency``.

    ``price`` is what the user pays with the EVDC wallet/tokens (the app's default); ``card_price`` is the price when
    paying by card, usually a little higher; ``base_price`` is the operator's base amount. Time-based fees and
    restrictions stay in ``raw``.
    """

    price: float | None = None
    unit: str | None = None
    currency: str | None = None
    card_price: float | None = None
    token_price: float | None = None
    base_price: float | None = None
    base_currency: str | None = None
    parking_fee_enabled: bool | None = None
    parking_fee: float | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Pricing | None:
        if not isinstance(data, dict) or not data:
            return None
        by_type = _dict(data.get("pricingByType"))
        parking = _dict(data.get("parkingPricing"))
        return cls(
            price=_float(data.get("Price")),
            unit=_str(data.get("Unit")),
            currency=_str(data.get("Currency")),
            card_price=_float(_dict(by_type.get("CARD")).get("Price")),
            token_price=_float(_dict(by_type.get("TOKEN")).get("Price")),
            base_price=_float(data.get("BaseAmount")),
            base_currency=_str(data.get("BaseCurrency")),
            parking_fee_enabled=_bool(parking.get("IsParkingFeeEnabled")) if parking else None,
            parking_fee=_float(parking.get("ParkingFee")),
            raw=data,
        )


@dataclass(slots=True)
class ChargingFacility:
    """One power option of a charging point (Hubject OICP ``ChargingFacilities``)."""

    power_kw: float | None = None
    power_type: str | None = None
    """``AC_1_PHASE``, ``AC_3_PHASE`` or ``DC``."""
    voltage: float | None = None
    amperage: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargingFacility:
        return cls(
            power_kw=_float(data.get("Power")),
            power_type=_str(data.get("PowerType")),
            voltage=_float(data.get("Voltage")),
            amperage=_float(data.get("Amperage")),
        )


@dataclass(slots=True)
class Evse:
    """A charging point (EVSE): one connector of a charging station.

    Returned by :meth:`EvdcApiClient.get_evse` and the nearby search, and embedded in a session as
    ``chargingStation``. Coordinates come from the backend as stored: a few records have latitude and longitude
    swapped.
    """

    evse_id: str | None
    id: str | None = None
    name: str | None = None
    partner: str | None = None
    operator_name: str | None = None
    operator_id: str | None = None
    status: str | None = None
    """Live status from the operator: ``Available``, ``Occupied``, ``OutOfService``, ``Unknown``, …"""
    distance_m: float | None = None
    """Distance from the searched point, in metres (nearby search only)."""
    address: Address | None = None
    latitude: float | None = None
    longitude: float | None = None
    plugs: list[str] = field(default_factory=list)
    facilities: list[ChargingFacility] = field(default_factory=list)
    is_open_24h: bool | None = None
    pricing: Pricing | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def max_power_kw(self) -> float | None:
        powers = [f.power_kw for f in self.facilities if f.power_kw is not None]
        return max(powers) if powers else None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evse:
        evse_data = _dict(data.get("EvseData"))
        coords = _dict(_dict(evse_data.get("GeoCoordinates")).get("DecimalDegree"))
        plugs = evse_data.get("Plugs")
        facilities = evse_data.get("ChargingFacilities")
        names = evse_data.get("ChargingStationNames")
        name = next((n.get("value") for n in names if isinstance(n, dict) and n.get("value")), None) if names else None
        return cls(
            evse_id=_str(data.get("EvseID") or data.get("evseId") or evse_data.get("EvseID")),
            id=_str(data.get("_id")),
            name=_str(name),
            partner=_str(data.get("partner")),
            operator_name=_str(evse_data.get("OperatorName") or data.get("OperatorName")),
            operator_id=_str(evse_data.get("OperatorID") or data.get("OperatorID")),
            status=_str(data.get("status")),
            distance_m=_float(data.get("distance")),
            address=Address.from_dict(evse_data.get("Address")),
            latitude=_float(coords.get("Latitude")),
            longitude=_float(coords.get("Longitude")),
            plugs=[str(p) for p in plugs] if isinstance(plugs, list) else [],
            facilities=[ChargingFacility.from_dict(f) for f in facilities if isinstance(f, dict)]
            if isinstance(facilities, list)
            else [],
            is_open_24h=_bool(evse_data.get("IsOpen24Hours")),
            pricing=Pricing.from_dict(data.get("pricing") or data.get("pricingDetails")),
            raw=data,
        )


# ---------------------------------------------------------------------------
# Charging sessions
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ChargingSession:
    """A completed charging session from the history (``/api/hubject/charge-history``)."""

    session_id: str | None
    evse_id: str | None = None
    id: str | None = None
    invoice_no: str | None = None
    created_at: datetime | None = None
    amount: float | None = None
    currency: str | None = None
    energy_kwh: float | None = None
    operator: str | None = None
    charging_duration_minutes: float | None = None
    time_fee: float | None = None
    parking_duration_minutes: float | None = None
    parking_fee: float | None = None
    time_surcharge_duration_minutes: float | None = None
    time_surcharge_fee: float | None = None
    address: Address | None = None
    pricing: Pricing | None = None
    """Tariff applied when billing this session (``pricingDetails``); may differ from the station's current one."""
    station: Evse | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargingSession:
        pricing = _dict(data.get("pricingDetails"))
        time_details = _dict(data.get("timeDetails"))
        parking = _dict(data.get("parkingDetails"))
        station = data.get("chargingStation")
        energy = data.get("consumedEnergy")
        return cls(
            session_id=_str(data.get("sessionId")),
            evse_id=_str(data.get("evseId")),
            id=_str(data.get("_id")),
            invoice_no=_str(data.get("invoiceNo")),
            created_at=_datetime(data.get("createdAt")),
            amount=_float(data.get("amount")),
            currency=_str(data.get("currency")),
            energy_kwh=_float(energy if energy is not None else pricing.get("consumedEnergy")),
            operator=_str(data.get("operator")),
            charging_duration_minutes=_float(time_details.get("durationInMinutes")),
            time_fee=_float(time_details.get("timeFee")),
            parking_duration_minutes=_float(parking.get("durationInMinutes")),
            parking_fee=_float(parking.get("parkingFee")),
            time_surcharge_duration_minutes=_float(data.get("timeSurchargeDurationInMinutes")),
            time_surcharge_fee=_float(data.get("timeSurchargeFee")),
            address=Address.from_dict(_dict(data.get("evseDetails")).get("address")),
            pricing=Pricing.from_dict(pricing),
            station=Evse.from_dict(station) if isinstance(station, dict) and station else None,
            raw=data,
        )


@dataclass(slots=True)
class ChargingHistoryPage:
    """One page of the charging history, with the backend's pagination counters."""

    sessions: list[ChargingSession]
    page: int | None = None
    limit: int | None = None
    total_pages: int | None = None
    total_documents: int | None = None

    @property
    def has_next(self) -> bool:
        if self.page is not None and self.total_pages is not None:
            return self.page < self.total_pages
        return self.limit is not None and len(self.sessions) >= self.limit

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargingHistoryPage:
        items = data.get("data")

        def _int(value: Any) -> int | None:
            number = _float(value)
            return int(number) if number is not None else None

        return cls(
            sessions=[ChargingSession.from_dict(i) for i in items if isinstance(i, dict)]
            if isinstance(items, list)
            else [],
            page=_int(data.get("page")),
            limit=_int(data.get("limit")),
            total_pages=_int(data.get("totalPages")),
            total_documents=_int(data.get("totalDocuments")),
        )


@dataclass(slots=True)
class Receipt:
    """The PDF receipt of a session (``/api/hubject/download-pdf/{sessionId}``)."""

    filename: str | None
    content: bytes = field(repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Receipt:
        encoded = data.get("base64")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("Receipt payload has no base64 content")
        if encoded.startswith("data:") and "," in encoded:
            encoded = encoded.split(",", 1)[1]
        try:
            content = base64.b64decode(encoded, validate=False)
        except binascii.Error as exc:
            raise ValueError("Receipt content is not valid base64") from exc
        return cls(filename=_str(data.get("filename")), content=content)


@dataclass(slots=True)
class OngoingSession:
    """A session in progress (``/api/hubject/ongoing-sessionsV2``)."""

    session_id: str | None
    evse_id: str | None = None
    amount: float | None = None
    currency: str | None = None
    created_at: datetime | None = None
    is_paid: bool | None = None
    is_stop: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OngoingSession:
        return cls(
            session_id=_str(data.get("sessionId")),
            evse_id=_str(data.get("evseId") or data.get("EvseID")),
            amount=_float(data.get("amount")),
            currency=_str(data.get("currency")),
            created_at=_datetime(data.get("createdAt")),
            is_paid=_bool(data.get("isPaid")),
            is_stop=_bool(data.get("isStop")),
            raw=data,
        )


@dataclass(slots=True)
class SessionProgress:
    """A live progress update pushed on the socket (``chargingSessionProgress``).

    Keyed by ``evse_id``: match it to :class:`OngoingSession` through the EVSE, not the session id.
    Units follow the app's labels (kW, A, kWh) and are not yet confirmed on real events.
    """

    evse_id: str | None
    time: datetime | None = None
    session_start: datetime | None = None
    charging_start: datetime | None = None
    power_kw: float | None = None
    max_power_kw: float | None = None
    current_a: float | None = None
    max_current_a: float | None = None
    energy_import_kwh: float | None = None
    energy_export_kwh: float | None = None
    consumed_energy_kwh: float | None = None
    parking_time: Any = None
    reservation_time: Any = None
    timeline: list[Any] = field(default_factory=list, repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionProgress:
        timeline = data.get("Timeline")
        return cls(
            evse_id=_str(data.get("evseId") or data.get("EvseID")),
            time=_datetime(data.get("Time")),
            session_start=_datetime(data.get("SessionStart")),
            charging_start=_datetime(data.get("ChargingStart")),
            power_kw=_float(data.get("Power")),
            max_power_kw=_float(data.get("MaxPower")),
            current_a=_float(data.get("Current")),
            max_current_a=_float(data.get("MaxCurrent")),
            energy_import_kwh=_float(data.get("EnergyImport")),
            energy_export_kwh=_float(data.get("EnergyExport")),
            consumed_energy_kwh=_float(data.get("ConsumedEnergyProgress")),
            parking_time=data.get("ParkingTime"),
            reservation_time=data.get("ReservationTime"),
            timeline=timeline if isinstance(timeline, list) else [],
            raw=data,
        )

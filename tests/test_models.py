"""Tests for evdc_network_api.models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from evdc_network_api.models import (
    ChargingHistoryPage,
    ChargingSession,
    ConnectedSession,
    Evse,
    OngoingSession,
    Receipt,
    SessionProgress,
    User,
)

from .conftest import load_fixture


def test_user_from_login_strips_secrets() -> None:
    user = User.from_dict(load_fixture("login")["data"])
    assert user.id == "64b7f0c2a1b2c3d4e5f60718"
    assert user.email == "mario.rossi@example.com"
    assert user.first_name == "Mario"
    assert user.is_two_factor_enabled is False
    assert user.evco_id == "IT-TST-C00000001-X"
    assert user.last_visit_at == datetime(2026, 1, 15, 10, 20, 30, tzinfo=UTC)
    for key in ("accessToken", "refreshToken", "token", "fcmToken", "fcmTokens"):
        assert key not in user.raw
    assert "test-access-token" not in repr(user)


def test_user_from_profile_has_profile_fields() -> None:
    user = User.from_dict(load_fixture("profile"))
    assert user.total_spending == 42
    assert user.raw["geolocation"]["currency"] == "EUR"


def test_charging_session_fields() -> None:
    page = ChargingHistoryPage.from_dict(load_fixture("charge_history"))
    session = page.sessions[0]
    assert session.session_id == "00000000-0000-4000-8000-000000000001"
    assert session.evse_id == "IT*TST*E0001*1"
    assert session.invoice_no == "INV-TEST-0001"
    assert session.created_at == datetime(2026, 1, 11, 18, 30, tzinfo=UTC)
    assert session.amount == pytest.approx(10.86)
    assert session.currency == "EUR"
    assert session.energy_kwh == pytest.approx(18.4)
    assert session.charging_duration_minutes == 95
    assert session.parking_fee == 0
    assert session.started_at == datetime(2026, 1, 11, 18, 30, tzinfo=UTC)
    assert session.ended_at == datetime(2026, 1, 11, 20, 5, tzinfo=UTC)
    assert session.is_paid is True
    assert session.is_stopped is True
    assert session.is_failed is False
    assert session.is_test_session is False
    assert session.address is not None
    assert session.address.city == "Milano"
    assert session.pricing is not None
    assert session.pricing.price == pytest.approx(0.59)
    assert session.station is not None
    assert session.station.operator_name == "Test Charging Srl"


def test_charging_session_energy_falls_back_to_pricing_details() -> None:
    session = ChargingSession.from_dict({"sessionId": "s", "pricingDetails": {"consumedEnergy": "3.5"}})
    assert session.energy_kwh == pytest.approx(3.5)


def test_charging_session_tolerates_missing_fields() -> None:
    session = ChargingSession.from_dict({})
    assert session.session_id is None
    assert session.address is None
    assert session.pricing is None
    assert session.station is None


def test_history_page_pagination() -> None:
    first = ChargingHistoryPage.from_dict(load_fixture("charge_history"))
    last = ChargingHistoryPage.from_dict(load_fixture("charge_history_last"))
    assert (first.page, first.total_pages, first.total_documents) == (1, 2, 3)
    assert first.has_next is True
    assert last.has_next is False


def test_history_page_without_counters_uses_page_size() -> None:
    page = ChargingHistoryPage.from_dict({"limit": 2, "data": [{"sessionId": "a"}, {"sessionId": "b"}]})
    assert page.has_next is True
    assert ChargingHistoryPage.from_dict({"data": []}).has_next is False


def test_receipt_decodes_pdf() -> None:
    receipt = Receipt.from_dict(load_fixture("receipt"))
    assert receipt.content.startswith(b"%PDF-")
    assert receipt.filename == "receipt-INV-TEST-0001.pdf"
    assert "PDF" not in repr(receipt)


def test_receipt_accepts_data_uri() -> None:
    receipt = Receipt.from_dict({"base64": "data:application/pdf;base64,JVBERg=="})
    assert receipt.content == b"%PDF"


def test_receipt_without_content_is_an_error() -> None:
    with pytest.raises(ValueError, match="no base64"):
        Receipt.from_dict({"filename": "x.pdf"})


def test_ongoing_session() -> None:
    session = OngoingSession.from_dict(load_fixture("ongoing_sessions")[0])
    assert session.evse_id == "IT*TST*E0001*1"
    assert session.is_paid is False
    assert session.created_at == datetime(2026, 1, 20, 8, tzinfo=UTC)


def test_evse() -> None:
    evse = Evse.from_dict(load_fixture("evse"))
    assert evse.evse_id == "IT*TST*E0001*1"
    assert evse.operator_id == "IT*TST"
    assert evse.latitude == pytest.approx(45.4642)
    assert evse.plugs == ["Type2Outlet"]
    assert evse.pricing is not None
    assert evse.pricing.unit == "KWH"


def test_session_progress() -> None:
    progress = SessionProgress.from_dict(load_fixture("session_progress"))
    assert progress.evse_id == "IT*TST*E0001*1"
    assert progress.power_kw == pytest.approx(21.6)
    assert progress.consumed_energy_kwh == pytest.approx(5.4)
    assert progress.time == datetime(2026, 1, 20, 8, 15, tzinfo=UTC)
    assert len(progress.timeline) == 1


def test_session_progress_accepts_camel_case_evse_id_and_epoch_time() -> None:
    progress = SessionProgress.from_dict({"evseId": "X*1", "Time": 1768896000000})
    assert progress.evse_id == "X*1"
    assert progress.time == datetime(2026, 1, 20, 8, tzinfo=UTC)


def test_nearby_evse_fields() -> None:
    evse = Evse.from_dict(load_fixture("nearby_page1")["result"][9])
    assert evse.evse_id == "IT*TST*E1004*2"
    assert evse.name == "Test Station 1004"
    assert evse.status == "Occupied"
    assert evse.distance_m == 1500
    assert evse.max_power_kw == 150
    assert evse.facilities[0].power_type == "DC"
    assert evse.address is not None
    assert evse.address.city == "Testville"
    assert evse.latitude == pytest.approx(45.0009)


def test_pricing_by_payment_type() -> None:
    pricing = Evse.from_dict(load_fixture("nearby_page1")["result"][1]).pricing
    assert pricing is not None
    assert pricing.price == pytest.approx(0.50)
    assert pricing.token_price == pytest.approx(0.50)
    assert pricing.card_price == pytest.approx(0.55)
    assert pricing.base_price == pytest.approx(0.48)
    assert (pricing.unit, pricing.currency, pricing.base_currency) == ("kWh", "EUR", "EUR")
    assert pricing.parking_fee_enabled is False


def test_evse_without_facilities_has_no_max_power() -> None:
    assert Evse.from_dict({"EvseID": "X*1"}).max_power_kw is None


def test_connected_session_from_dict() -> None:
    session = ConnectedSession.from_dict(
        {
            "_id": "abc",
            "deviceId": "f" * 64,
            "deviceModel": "Pixel 8",
            "appVersion": "1.1.10",
            "ip": "203.0.113.1",
            "city": "Milano",
            "country": "IT",
            "timezone": "Europe/Rome",
            "latitude": 45.46,
            "longitude": 9.19,
            "status": "ACTIVE",
            "isCurrent": True,
            "createdAt": "2024-01-02T03:04:05Z",
            "expiresAt": "2024-01-09T03:04:05Z",
            "user": "u1",
        }
    )
    assert session.id == "abc"
    assert session.device_id == "f" * 64
    assert session.device_model == "Pixel 8"
    assert session.app_version == "1.1.10"
    assert session.city == "Milano"
    assert session.latitude == pytest.approx(45.46)
    assert session.status == "ACTIVE"
    assert session.is_current is True
    assert session.user_id == "u1"
    assert session.created_at == datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert session.expires_at == datetime(2024, 1, 9, 3, 4, 5, tzinfo=UTC)

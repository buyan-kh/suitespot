from datetime import date, timedelta
from typing import Annotated

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.search import HotelSearchParams


def days_from_today(n: int) -> date:
    return date.today() + timedelta(days=n)


# --- Login ---


def test_login_normalizes_email():
    req = LoginRequest(email="  Guest@Example.COM ", password="x")
    assert req.email == "guest@example.com"


@pytest.mark.parametrize("email", ["", "no-at-sign", "a@b", "a b@c.com", "@example.com"])
def test_login_rejects_bad_email(email):
    with pytest.raises(ValidationError):
        LoginRequest(email=email, password="x")


def test_login_requires_password():
    with pytest.raises(ValidationError):
        LoginRequest(email="a@example.com", password="")


def test_email_max_length_boundary():
    domain = "@example.com"
    ok = "a" * (255 - len(domain)) + domain
    assert LoginRequest(email=ok, password="x").email == ok
    with pytest.raises(ValidationError):
        LoginRequest(email="a" + ok, password="x")


# --- Register ---


def test_register_valid_without_names():
    req = RegisterRequest(email="new@example.com", password="abcdefg1")
    assert req.first_name is None
    assert req.last_name is None


def test_register_valid_with_names():
    req = RegisterRequest(
        email="new@example.com",
        password="abcdefg1",
        first_name="  Ada ",
        last_name="Lovelace",
        phone="408-555-0100",
    )
    assert req.first_name == "Ada"


def test_register_password_length_boundary():
    assert RegisterRequest(email="a@example.com", password="abcdefg1")
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@example.com", password="abcdef1")


@pytest.mark.parametrize("password", ["abcdefgh", "12345678"])
def test_register_password_needs_letter_and_number(password):
    with pytest.raises(ValidationError, match="at least one letter and one number"):
        RegisterRequest(email="a@example.com", password=password)


def test_register_rejects_role():
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@example.com", password="abcdefg1", role="admin")


def test_register_rejects_blank_name():
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@example.com", password="abcdefg1", first_name="   ")


# --- Search ---


def search(**overrides) -> HotelSearchParams:
    params = {
        "destination": "San Jose",
        "checkIn": days_from_today(1),
        "checkOut": days_from_today(3),
        "guests": 2,
    }
    params.update(overrides)
    return HotelSearchParams(**params)


def test_search_accepts_camel_case():
    params = search()
    assert params.check_in == days_from_today(1)
    assert params.guests == 2


def test_search_accepts_snake_case():
    params = HotelSearchParams(
        destination="Miami",
        check_in=days_from_today(1),
        check_out=days_from_today(2),
        min_price=50,
        room_type="suite",
    )
    assert params.room_type == "suite"
    assert params.guests == 1


def test_search_check_in_today_allowed():
    assert search(checkIn=date.today(), checkOut=days_from_today(1))


def test_search_rejects_past_check_in():
    with pytest.raises(ValidationError, match="past"):
        search(checkIn=days_from_today(-1))


@pytest.mark.parametrize("nights", [0, -1])
def test_search_check_out_must_follow_check_in(nights):
    with pytest.raises(ValidationError, match="after check-in"):
        search(checkIn=days_from_today(2), checkOut=days_from_today(2 + nights))


def test_search_stay_length_boundary():
    assert search(checkIn=days_from_today(1), checkOut=days_from_today(31))
    with pytest.raises(ValidationError, match="30 nights"):
        search(checkIn=days_from_today(1), checkOut=days_from_today(32))


def test_search_guests_boundary():
    assert search(guests=10).guests == 10
    for guests in (0, 11):
        with pytest.raises(ValidationError):
            search(guests=guests)


def test_search_rejects_blank_destination():
    with pytest.raises(ValidationError):
        search(destination="   ")


def test_search_rejects_inverted_price_range():
    with pytest.raises(ValidationError, match="Minimum price"):
        search(minPrice=200, maxPrice=100)


def test_search_rejects_unknown_room_type():
    with pytest.raises(ValidationError):
        search(roomType="penthouse")


# --- FastAPI query parsing ---


def make_client() -> TestClient:
    app = FastAPI()

    @app.get("/search")
    def _search(params: Annotated[HotelSearchParams, Query()]):
        return params.model_dump(mode="json")

    return TestClient(app)


def test_query_params_parse_through_fastapi():
    client = make_client()
    res = client.get(
        "/search",
        params={
            "destination": "San Jose",
            "checkIn": days_from_today(1).isoformat(),
            "checkOut": days_from_today(2).isoformat(),
            "guests": "3",
        },
    )
    assert res.status_code == 200
    assert res.json()["guests"] == 3
    assert res.json()["check_in"] == days_from_today(1).isoformat()


def test_bad_query_params_return_422():
    client = make_client()
    res = client.get(
        "/search",
        params={
            "destination": "San Jose",
            "checkIn": days_from_today(-1).isoformat(),
            "checkOut": days_from_today(2).isoformat(),
        },
    )
    assert res.status_code == 422

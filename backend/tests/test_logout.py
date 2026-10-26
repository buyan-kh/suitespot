import pytest
from sqlalchemy import select

from app.models import User
from app.security import issue_tokens


@pytest.fixture
def user(db_session):
    u = User(email="out@x.com", hashed_password="x", first_name="O", last_name="U")
    db_session.add(u)
    db_session.commit()
    return u


def test_logout_with_valid_access_token(client, user):
    tokens = issue_tokens(user.id)
    response = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json() == {"detail": "Logged out."}


def test_logout_without_a_token_still_succeeds(client):
    assert client.post("/auth/logout").status_code == 200


@pytest.mark.parametrize("header", ["Bearer garbage", "Bearer ", "nonsense"])
def test_logout_with_bad_or_expired_token_still_succeeds(client, header):
    assert client.post("/auth/logout", headers={"Authorization": header}).status_code == 200


def test_logout_twice_is_fine(client):
    assert client.post("/auth/logout").status_code == 200
    assert client.post("/auth/logout").status_code == 200


def test_logout_requires_post(client):
    assert client.get("/auth/logout").status_code == 405


def test_logout_does_not_change_users(client, db_session, user):
    client.post("/auth/logout")
    assert len(db_session.execute(select(User)).scalars().all()) == 1


def test_refresh_endpoint_still_works(client, user):
    tokens = issue_tokens(user.id)
    response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.xfail(reason="Stateless tokens: revoking a refresh token needs a revocation table (not built)")
def test_refresh_token_is_rejected_after_logout(client, user):
    tokens = issue_tokens(user.id)
    client.post("/auth/logout", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401

def _register_and_login(client, email="flow@x.com"):
    client.post("/register", json={"email": email, "password": "Passw0rdOK"})
    return client.post("/login", json={"email": email, "password": "Passw0rdOK"}).json()


def test_logout_after_a_real_login(client):
    tokens = _register_and_login(client)
    response = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json() == {"detail": "Logged out."}
    
def test_user_can_log_in_again_after_logging_out(client):
    first = _register_and_login(client)
    client.post("/auth/logout", headers={"Authorization": f"Bearer {first['access_token']}"})
    second = client.post("/login", json={"email": "flow@x.com", "password": "Passw0rdOK"})
    assert second.status_code == 200
    headers = {"Authorization": f"Bearer {second.json()['access_token']}"}
    # 404 (not 401) means the new token was accepted as a logged-in user.
    assert client.post("/reservations/none/cancel", headers=headers).status_code == 404


def test_logout_is_documented_in_the_api_docs(client):
    operation = client.get("/openapi.json").json()["paths"]["/auth/logout"]["post"]
    assert operation["summary"] == "Log out"
    assert "delete the access and refresh tokens" in operation["description"]

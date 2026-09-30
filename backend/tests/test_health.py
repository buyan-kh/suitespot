def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_schema(client):
    data = client.get("/health").json()
    assert data["status"] == "healthy"
    assert data["database"] == "healthy"
    assert "version" in data


def test_health_version_matches(client):
    from app.config import settings

    data = client.get("/health").json()
    assert data["version"] == settings.APP_VERSION

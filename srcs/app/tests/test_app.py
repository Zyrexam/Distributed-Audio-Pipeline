import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import app


def client() -> TestClient:
    return TestClient(app)


def test_health_returns_ok():
    response = client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_security_headers_are_applied():
    headers = client().get("/health").headers

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cache-Control"] == "no-store"


def test_openapi_schema_exposes_current_routes():
    schema = client().get("/openapi.json").json()

    assert schema["info"]["title"] == "Distributed Audio Pipeline"
    assert set(schema["paths"]) == {"/health", "/auth/register", "/auth/login", "/auth/me"}


def test_unknown_route_returns_404():
    assert client().get("/does-not-exist").status_code == 404


def test_config_requires_dummy_hash(monkeypatch):
    monkeypatch.delenv("AUTH_DUMMY_HASH", raising=False)

    with pytest.raises(RuntimeError, match="AUTH_DUMMY_HASH is not set"):
        Settings.from_env()


def test_config_rejects_dummy_hash_that_is_not_bcrypt(monkeypatch):
    monkeypatch.setenv("AUTH_DUMMY_HASH", "plaintext-not-a-bcrypt-hash")

    with pytest.raises(RuntimeError, match="must be a bcrypt hash"):
        Settings.from_env()


def test_config_reads_minio_and_rabbitmq_settings(monkeypatch):
    monkeypatch.setenv("MINIO_BUCKET", "custom-bucket")
    monkeypatch.setenv("MINIO_SECURE", "true")
    monkeypatch.setenv("RABBITMQ_QUEUE", "custom.jobs")

    settings = Settings.from_env()

    assert settings.minio_bucket == "custom-bucket"
    assert settings.minio_secure is True
    assert settings.rabbitmq_queue == "custom.jobs"


def test_config_rejects_invalid_minio_secure(monkeypatch):
    monkeypatch.setenv("MINIO_SECURE", "maybe")

    with pytest.raises(RuntimeError, match="MINIO_SECURE"):
        Settings.from_env()


def test_metrics_endpoint_exposes_prometheus_text():
    response = client().get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "uploads_total" in response.text

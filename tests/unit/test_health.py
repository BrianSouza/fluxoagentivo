from fastapi.testclient import TestClient

import harness
from harness.api.app import create_app


def test_health_returns_ok_with_version() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": harness.__version__}


def test_health_not_exposed_outside_v1_prefix() -> None:
    client = TestClient(create_app())
    assert client.get("/health").status_code == 404

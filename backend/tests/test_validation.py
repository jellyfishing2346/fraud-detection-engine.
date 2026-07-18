"""Input validation and startup checks that need no database."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def payload(**overrides):
    body = {
        "transaction_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "amount_cents": 5000,
        "currency": "USD",
        "occurred_at": "2026-06-06T14:00:00Z",
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "usd"),
        ("currency", "USDX"),
        ("country_code", "USA"),
        ("ip_address", "999.1.1.1"),
        ("ip_address", "not-an-ip"),
        ("amount_cents", -100),
        ("lat", 91),
        ("lon", -181),
    ],
)
def test_score_rejects_values_the_database_cannot_store(field, value):
    response = client.post("/v1/score", json=payload(**{field: value}))
    assert response.status_code == 422


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=-1", "limit=101", "state=deleted", "severity=extreme"]
)
def test_list_alerts_rejects_bad_query_params(query):
    assert client.get(f"/v1/alerts?{query}").status_code == 422


def test_review_rejects_unknown_verdict_before_touching_the_database():
    response = client.patch(
        f"/v1/alerts/{uuid.uuid4()}/review", json={"verdict": "maybe"}
    )
    assert response.status_code == 422


def test_model_loads_regardless_of_working_directory(tmp_path):
    from ml import predict

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        predict.load_model()
    finally:
        os.chdir(cwd)
    assert predict._model is not None


def test_engine_is_created_once_and_reused(monkeypatch):
    from db import models

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/unused")
    models.get_engine.cache_clear()
    try:
        assert models.get_engine() is models.get_engine()
    finally:
        models.get_engine.cache_clear()


def test_missing_database_url_gives_a_clear_error(monkeypatch):
    from db import models

    monkeypatch.delenv("DATABASE_URL", raising=False)
    models.get_engine.cache_clear()
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        models.get_engine()
    models.get_engine.cache_clear()


def test_server_errors_do_not_leak_details(monkeypatch):
    import api.routes.score as score_module
    from ml import predict

    predict.load_model()

    def explode(**_kwargs):
        raise RuntimeError("postgresql://admin:hunter2@db.internal:5432/prod")

    monkeypatch.setattr(score_module, "score_transaction", explode)
    quiet_client = TestClient(app, raise_server_exceptions=False)
    response = quiet_client.post("/v1/score", json=payload())
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "hunter2" not in response.text

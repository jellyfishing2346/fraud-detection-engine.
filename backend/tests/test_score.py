"""
Week 5: pytest test suite for the fraud detection API.

Run with:
    cd backend
    python3.12 -m pytest tests/ -v
"""

import uuid

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def make_score_payload(
    transaction_id=None,
    user_id=None,
    amount_cents=50000,
    occurred_at="2026-06-06T14:00:00Z",
):
    return {
        "transaction_id": transaction_id or str(uuid.uuid4()),
        "user_id": user_id or str(uuid.uuid4()),
        "amount_cents": amount_cents,
        "currency": "USD",
        "occurred_at": occurred_at,
    }


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_score_missing_required_field():
    payload = {
        "transaction_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "currency": "USD",
        "occurred_at": "2026-06-06T14:00:00Z",
    }
    response = client.post("/v1/score", json=payload)
    assert response.status_code in (404, 422)


def test_score_invalid_uuid():
    payload = make_score_payload(transaction_id="not-a-uuid")
    response = client.post("/v1/score", json=payload)
    assert response.status_code in (404, 422)


def test_severity_mapping():
    from api.routes.score import map_severity

    assert map_severity(0.85) == "high"
    assert map_severity(0.75) == "medium"
    assert map_severity(0.45) == "low"


def test_list_alerts_invalid_cursor():
    response = client.get("/v1/alerts?cursor=not-a-date")
    assert response.status_code == 400


def test_review_invalid_verdict():
    response = client.patch(
        f"/v1/alerts/{uuid.uuid4()}/review",
        json={"verdict": "maybe"},
    )
    assert response.status_code in (404, 422)

# 📡 API Reference

Base URL: `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs` (Swagger UI)

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/dashboard` | Reviewer dashboard (HTML) |
| `POST` | `/v1/score` | Score a transaction |
| `GET` | `/v1/alerts` | List alerts |
| `GET` | `/v1/alerts/{id}` | Get alert detail |
| `PATCH` | `/v1/alerts/{id}/review` | Submit reviewer verdict |

---

## GET /health

Returns API status. Used by monitoring and Docker healthchecks.

### Response `200`
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

## POST /v1/score

Scores a transaction in real time. Writes to `transactions` and `fraud_scores` tables. Creates a `fraud_alerts` row if the score exceeds the threshold.

**Target latency:** < 50ms

### Request body
```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id":        "550e8400-e29b-41d4-a716-446655440001",
  "merchant_id":    "550e8400-e29b-41d4-a716-446655440002",
  "amount_cents":   150000,
  "currency":       "USD",
  "country_code":   "US",
  "ip_address":     "203.0.113.5",
  "device_fingerprint": "sha256-abc123",
  "occurred_at":    "2026-06-06T02:30:00Z",
  "lat":            40.7128,
  "lon":            -74.0060
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `transaction_id` | UUID | ✅ | Unique transaction identifier |
| `user_id` | UUID | ✅ | User performing the transaction |
| `merchant_id` | UUID | ❌ | Merchant identifier |
| `amount_cents` | integer | ✅ | Amount in cents (never float) |
| `currency` | string | ❌ | ISO 4217 code. Default: `USD` |
| `country_code` | string | ❌ | ISO 3166 2-letter code |
| `ip_address` | string | ❌ | Client IP address |
| `device_fingerprint` | string | ❌ | Hashed device info |
| `occurred_at` | ISO 8601 | ✅ | When the transaction occurred |
| `lat` | float | ❌ | Latitude for geo-distance feature |
| `lon` | float | ❌ | Longitude for geo-distance feature |

### Response `200` — approved
```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "score":          0.0043,
  "verdict":        "approved",
  "severity":       null,
  "latency_ms":     27,
  "model_version":  "xgb-v1.0.0",
  "features": {
    "amount_log":       11.92,
    "hour_of_day":      2.0,
    "is_night":         1.0,
    "velocity_1h":      0.0,
    "velocity_24h":     0.0,
    "geo_distance_km":  0.0,
    "is_new_location":  1.0
  }
}
```

### Response `200` — flagged
```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "score":          0.8231,
  "verdict":        "flagged",
  "severity":       "high",
  "latency_ms":     3,
  "model_version":  "xgb-v1.0.0",
  "features": {
    "amount_log":       11.92,
    "hour_of_day":      2.0,
    "is_night":         1.0,
    "velocity_1h":      4.0,
    "velocity_24h":     7.0,
    "geo_distance_km":  8420.5,
    "is_new_location":  0.0
  }
}
```

### Error responses
| Code | Condition |
|---|---|
| `409 Conflict` | Transaction ID already scored |
| `422 Unprocessable Entity` | Missing or invalid fields |
| `500 Internal Server Error` | Model not loaded |

### Example (curl)
```bash
curl -X POST http://localhost:8000/v1/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "550e8400-e29b-41d4-a716-446655440001",
    "amount_cents": 150000,
    "currency": "USD",
    "occurred_at": "2026-06-06T02:30:00Z"
  }'
```

---

## GET /v1/alerts

Returns paginated list of fraud alerts. Supports filtering by state and severity.

### Query parameters
| Parameter | Type | Default | Description |
|---|---|---|---|
| `state` | string | (all) | `open` \| `in_review` \| `closed` |
| `severity` | string | (all) | `low` \| `medium` \| `high` |
| `limit` | integer | 20 | Max results (max: 100) |
| `cursor` | string | (none) | ISO timestamp for pagination |

### Response `200`
```json
{
  "alerts": [
    {
      "alert_id":       "abba1e31-...",
      "transaction_id": "ff000000-...",
      "score":          0.8231,
      "severity":       "high",
      "state":          "open",
      "sla_deadline":   "2026-06-07T06:22:00Z",
      "escalated":      false,
      "created_at":     "2026-06-07T02:22:00Z"
    }
  ],
  "total": 47,
  "next_cursor": "2026-06-07T01:15:00Z"
}
```

### Pagination
Use cursor-based pagination for consistent results under concurrent writes:

```bash
# Page 1
GET /v1/alerts?state=open&limit=20

# Page 2 (use next_cursor from previous response)
GET /v1/alerts?state=open&limit=20&cursor=2026-06-07T01:15:00Z
```

### Example
```bash
# Get all high-severity open alerts
curl "http://localhost:8000/v1/alerts?state=open&severity=high&limit=50"
```

---

## GET /v1/alerts/{alert_id}

Returns full alert detail including feature breakdown and transaction info.

### Path parameters
| Parameter | Description |
|---|---|
| `alert_id` | UUID of the alert |

### Response `200`
```json
{
  "alert_id":       "abba1e31-...",
  "transaction_id": "ff000000-...",
  "score":          0.8231,
  "severity":       "high",
  "state":          "open",
  "sla_deadline":   "2026-06-07T06:22:00Z",
  "escalated":      false,
  "created_at":     "2026-06-07T02:22:00Z",
  "amount_cents":   950000,
  "currency":       "USD",
  "country_code":   "GB",
  "top_features": {
    "geo_distance_km":  9558.56,
    "amount_log":       9.16,
    "velocity_1h":      3.0,
    "is_night":         1.0,
    "hour_of_day":      2.0
  }
}
```

### Error responses
| Code | Condition |
|---|---|
| `404 Not Found` | Alert ID does not exist |

---

## PATCH /v1/alerts/{alert_id}/review

Submit a reviewer verdict. Closes the alert and records feedback for retraining.

### Request body
```json
{
  "verdict": "false_positive",
  "notes":   "Verified with customer — legitimate travel purchase to London"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `verdict` | string | ✅ | `confirmed` \| `false_positive` |
| `notes` | string | ❌ | Analyst notes |

### Response `200`
```json
{
  "alert_id":    "abba1e31-...",
  "state":       "closed",
  "verdict":     "false_positive",
  "reviewed_at": "2026-06-07T03:15:00Z"
}
```

### Error responses
| Code | Condition |
|---|---|
| `404 Not Found` | Alert ID does not exist |
| `409 Conflict` | Alert is already closed |
| `422 Unprocessable Entity` | Invalid verdict value |

### Example
```bash
curl -X PATCH "http://localhost:8000/v1/alerts/abba1e31-.../review" \
  -H "Content-Type: application/json" \
  -d '{"verdict": "confirmed", "notes": "Confirmed with fraud team"}'
```

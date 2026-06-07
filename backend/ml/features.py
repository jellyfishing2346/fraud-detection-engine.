"""
Week 4: Redis-backed feature engineering for real-time scoring.

Features built here:
- velocity_1h:     number of transactions by this user in the last hour
- velocity_24h:    number of transactions by this user in the last 24 hours
- geo_distance_km: distance from user's last known location (haversine)
- is_new_location: 1 if no prior location on record
- amount_log:      log-normalised transaction amount
- hour_of_day:     hour of the transaction (0-23)
- is_night:        1 if transaction occurred between 11pm and 5am
"""

import json
import math
import os
from datetime import datetime

import redis

# ─── Redis client (singleton) ─────────────────────────────────────────────────

_redis_client = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
    return _redis_client


# ─── Haversine distance ───────────────────────────────────────────────────────


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lng points."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── Velocity features ────────────────────────────────────────────────────────


def get_velocity_features(user_id: str, occurred_at: datetime) -> dict:
    """
    Count transactions in the last 1h and 24h using Redis sorted sets.
    Key: velocity:{user_id}  Score: unix timestamp  Member: transaction_id
    """
    r = get_redis()
    key = f"velocity:{user_id}"
    now_ts = occurred_at.timestamp()
    one_hour_ago = now_ts - 3600
    one_day_ago = now_ts - 86400

    velocity_1h = r.zcount(key, one_hour_ago, now_ts)
    velocity_24h = r.zcount(key, one_day_ago, now_ts)

    return {
        "velocity_1h": int(velocity_1h),
        "velocity_24h": int(velocity_24h),
    }


def record_transaction_velocity(
    user_id: str,
    transaction_id: str,
    occurred_at: datetime,
) -> None:
    """
    Add this transaction to the velocity sorted set.
    TTL is set to 25 hours so we never accumulate stale data.
    """
    r = get_redis()
    key = f"velocity:{user_id}"
    ts = occurred_at.timestamp()

    r.zadd(key, {transaction_id: ts})
    r.expire(key, 90000)  # 25 hours in seconds


# ─── Geo-distance features ────────────────────────────────────────────────────


def get_geo_features(
    user_id: str,
    lat: float | None,
    lon: float | None,
) -> dict:
    """
    Compare current transaction location with user's last known location.
    Returns distance in km and a new_location flag.
    """
    r = get_redis()
    key = f"location:{user_id}"

    if lat is None or lon is None:
        return {"geo_distance_km": 0.0, "is_new_location": 0}

    stored = r.get(key)
    if stored is None:
        return {"geo_distance_km": 0.0, "is_new_location": 1}

    last = json.loads(stored)
    distance = haversine_km(last["lat"], last["lon"], lat, lon)

    return {
        "geo_distance_km": round(distance, 2),
        "is_new_location": 0,
    }


def update_user_location(user_id: str, lat: float, lon: float) -> None:
    """Store the user's most recent transaction location. TTL: 7 days."""
    r = get_redis()
    key = f"location:{user_id}"
    r.set(key, json.dumps({"lat": lat, "lon": lon}), ex=604800)


# ─── Main feature builder ─────────────────────────────────────────────────────


def build_features(
    user_id: str,
    transaction_id: str,
    amount_cents: int,
    occurred_at: datetime,
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    """
    Build the complete feature vector for a transaction.
    Called before scoring — does NOT record the transaction yet
    (recording happens after the score is written to DB).
    """
    amount = amount_cents / 100.0
    amount_log = math.log1p(amount)
    hour_of_day = occurred_at.hour
    is_night = 1 if hour_of_day >= 23 or hour_of_day <= 5 else 0

    velocity = get_velocity_features(user_id, occurred_at)
    geo = get_geo_features(user_id, lat, lon)

    return {
        "amount_log": round(amount_log, 6),
        "hour_of_day": float(hour_of_day),
        "is_night": float(is_night),
        "velocity_1h": float(velocity["velocity_1h"]),
        "velocity_24h": float(velocity["velocity_24h"]),
        "geo_distance_km": float(geo["geo_distance_km"]),
        "is_new_location": float(geo["is_new_location"]),
    }


def post_score_update(
    user_id: str,
    transaction_id: str,
    occurred_at: datetime,
    lat: float | None = None,
    lon: float | None = None,
) -> None:
    """
    After the score is written to DB, update Redis with the new transaction.
    Separated from build_features so the velocity count doesn't include
    the current transaction at score time.
    """
    record_transaction_velocity(user_id, transaction_id, occurred_at)
    if lat is not None and lon is not None:
        update_user_location(user_id, lat, lon)

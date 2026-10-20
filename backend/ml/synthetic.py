"""
Synthetic training data for the v2 model.

The v1 model was trained on the Kaggle credit card dataset, whose strongest
signals are 28 anonymised PCA components (V1-V28). The live API cannot
compute those, so they were always zero at inference time and no request
could reach the alert threshold.

v2 is trained on exactly the features the API builds in ml/features.py.
No public dataset has these features, so this module simulates them. The
fraud patterns follow well-known card fraud behaviour; the proportions and
distributions are assumptions, documented below, not measurements. Metrics
from this data describe how well the model learns the simulation, not
real-world performance.

Legitimate transactions
  - Amount: log-normal around $35, clipped to $1-$5,000; 6% are big-ticket
    purchases (electronics, travel, furniture) around $700
  - Hour: mostly daytime and evening, rarely 1am-5am
  - Velocity: low (about 0.2 per hour, 1.5 per day)
  - Location: usually within a few km of the last one; about 4% are travel

Fraud patterns (share of fraud)
  - Card testing (30%): $0.50-$5 charges in rapid succession
  - Account takeover (35%): large amounts, often at night, from a new or
    distant location
  - Bust-out (15%): many purchases over a day at moderate amounts
  - Camouflaged (20%): fraud that looks like ordinary spending, so the
    classes overlap and the model cannot be perfect

Missing context
  The API only has velocity and location history when Redis is reachable and
  the user has transacted before, and only has a location when the client
  sends one. Both classes are sampled with that context missing at the
  same rates, so the model's scores stay sensible when those features are 0.
"""

import math

import numpy as np

FEATURES = [
    "amount_log",
    "hour_of_day",
    "is_night",
    "velocity_1h",
    "velocity_24h",
    "geo_distance_km",
    "is_new_location",
]

# Relative likelihood of a legitimate purchase in each hour (0-23).
_LEGIT_HOUR_WEIGHTS = np.array(
    [2, 1, 1, 1, 1, 2, 4, 6, 8, 9, 10, 11, 12, 11, 10, 10, 11, 12, 13, 12, 10, 8, 5, 3],
    dtype=float,
)
_NIGHT_HOURS = [23, 0, 1, 2, 3, 4, 5]

P_NO_VELOCITY_DATA = 0.25  # Redis unavailable or no history yet
P_NO_LOCATION = 0.30  # client sent no coordinates
P_FIRST_SEEN_LOCATION = 0.10  # coordinates, but no previous location on record


def _hours(rng, n, night_share=None):
    if night_share is None:
        p = _LEGIT_HOUR_WEIGHTS / _LEGIT_HOUR_WEIGHTS.sum()
        return rng.choice(24, size=n, p=p)
    night = rng.random(n) < night_share
    return np.where(night, rng.choice(_NIGHT_HOURS, size=n), _hours(rng, n))


def _legit(rng, n):
    big_ticket = rng.random(n) < 0.06
    amount = np.where(
        big_ticket,
        np.clip(rng.lognormal(math.log(700), 0.7, n), 150, 8_000),
        np.clip(rng.lognormal(math.log(35), 1.0, n), 1, 5_000),
    )
    hour = _hours(rng, n)
    v1 = rng.poisson(0.2, n)
    v24 = v1 + rng.poisson(1.5, n)
    travelling = rng.random(n) < 0.04
    distance = np.where(travelling, rng.uniform(300, 9_000, n), rng.exponential(8.0, n))
    new_location = rng.random(n) < 0.02
    return amount, hour, v1, v24, distance, new_location


def _fraud(rng, n):
    kind = rng.choice(4, size=n, p=[0.30, 0.35, 0.15, 0.20])
    la, lh, lv1, lv24, ld, ln = _legit(rng, n)

    amount = la.copy()
    hour = lh.copy()
    v1, v24 = lv1.copy(), lv24.copy()
    distance, new_location = ld.copy(), ln.copy()

    # Card testing
    m = kind == 0
    k = m.sum()
    amount[m] = rng.uniform(0.5, 5, k)
    hour[m] = rng.integers(0, 24, k)
    v1[m] = rng.poisson(10, k) + 3
    v24[m] = v1[m] + rng.poisson(5, k)

    # Account takeover
    m = kind == 1
    k = m.sum()
    amount[m] = np.clip(rng.lognormal(math.log(900), 0.7, k), 100, 9_000)
    hour[m] = _hours(rng, k, night_share=0.6)
    far = rng.random(k) < 0.55
    distance[m] = np.where(far, rng.uniform(800, 12_000, k), rng.exponential(8.0, k))
    new_location[m] = ~far & (rng.random(k) < 0.7)

    # Bust-out
    m = kind == 2
    k = m.sum()
    amount[m] = np.clip(rng.lognormal(math.log(400), 0.6, k), 20, 5_000)
    v1[m] = rng.poisson(3, k)
    v24[m] = v1[m] + rng.poisson(15, k) + 5

    # Camouflaged: ordinary-looking, slightly larger and later
    m = kind == 3
    k = m.sum()
    amount[m] = np.clip(la[m] * rng.uniform(1.5, 4, k), 1, 5_000)
    hour[m] = _hours(rng, k, night_share=0.25)

    return amount, hour, v1, v24, distance, new_location


def _assemble(rng, amount, hour, v1, v24, distance, new_location):
    n = len(amount)
    no_velocity = rng.random(n) < P_NO_VELOCITY_DATA
    v1 = np.where(no_velocity, 0, v1)
    v24 = np.where(no_velocity, 0, v24)

    context = rng.random(n)
    no_location = context < P_NO_LOCATION
    first_seen = (context >= P_NO_LOCATION) & (
        context < P_NO_LOCATION + P_FIRST_SEEN_LOCATION
    )
    # Mirrors ml/features.get_geo_features
    distance = np.where(no_location | first_seen | new_location, 0.0, distance)
    new_location = np.where(no_location, 0, (first_seen | new_location).astype(int))

    return np.column_stack(
        [
            np.log1p(amount),
            hour.astype(float),
            np.isin(hour, _NIGHT_HOURS).astype(float),
            v1.astype(float),
            v24.astype(float),
            np.round(distance, 2),
            new_location.astype(float),
        ]
    )


def generate(n: int, fraud_rate: float = 0.03, seed: int = 42):
    """Return (X, y): n rows of FEATURES and 0/1 fraud labels, shuffled."""
    rng = np.random.default_rng(seed)
    n_fraud = int(round(n * fraud_rate))
    X = np.vstack(
        [
            _assemble(rng, *_legit(rng, n - n_fraud)),
            _assemble(rng, *_fraud(rng, n_fraud)),
        ]
    )
    y = np.concatenate([np.zeros(n - n_fraud, dtype=int), np.ones(n_fraud, dtype=int)])
    order = rng.permutation(n)
    return X[order], y[order]

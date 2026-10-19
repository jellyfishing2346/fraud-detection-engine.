"""
Shared test setup.

Tests marked `integration` run against a real Postgres (TEST_DATABASE_URL);
everything else gets a stand-in session so it runs with no database at all.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import get_session  # noqa: E402
from main import app  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: needs a Postgres database at TEST_DATABASE_URL"
    )


@pytest.fixture(autouse=True)
def no_database_unless_integration(request):
    if request.node.get_closest_marker("integration"):
        yield
        return

    def fake_session():
        session = MagicMock()
        # Lookups find nothing, like an empty database
        session.query.return_value.filter.return_value.first.return_value = None
        yield session

    app.dependency_overrides[get_session] = fake_session
    yield
    app.dependency_overrides.pop(get_session, None)

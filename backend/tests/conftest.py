"""Test fixtures: the app on a throwaway SQLite database, MQTT disabled."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", mqtt_enabled=False)


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:  # `with` runs the lifespan (creates tables)
        yield test_client


@pytest.fixture
def engine(client):
    return client.app.state.engine

import os
import tempfile

import pytest

from app import create_app
from app.config.settings import TestingConfig
from app.db import init_db
from data.seed import seed_database


@pytest.fixture
def test_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path=path)
    seed_database(db_path=path)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def app(test_db_path):
    class CustomTestingConfig(TestingConfig):
        DATABASE_PATH = test_db_path

    app = create_app(CustomTestingConfig)
    return app


@pytest.fixture
def client(app):
    return app.test_client()

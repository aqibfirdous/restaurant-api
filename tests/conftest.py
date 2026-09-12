import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from harness.contract import ContractClient
from harness.reset_db import reset_db
from src.app import create_app

SCHEMA = os.path.join(ROOT, "schema.sql")
SEED = os.path.join(ROOT, "seed.sql")
SPEC = os.path.join(ROOT, "openapi.yaml")


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "restaurant.db")
    reset_db(path, SCHEMA, SEED)
    return path


@pytest.fixture
def env_db(db_path):
    old = os.environ.get("RESTAURANT_DB")
    os.environ["RESTAURANT_DB"] = db_path
    yield db_path
    if old is None:
        os.environ.pop("RESTAURANT_DB", None)
    else:
        os.environ["RESTAURANT_DB"] = old


@pytest.fixture
def app(env_db):
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return ContractClient(app, SPEC)
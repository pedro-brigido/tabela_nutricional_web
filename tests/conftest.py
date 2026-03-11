"""
Shared test fixtures.
"""

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def flask_app():
    """Create application for the test session."""
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
    yield app
    with app.app_context():
        _db.drop_all()


@pytest.fixture(autouse=True)
def _rollback(flask_app):
    """Roll back DB changes after each test."""
    with flask_app.app_context():
        yield
        _db.session.rollback()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture()
def client(flask_app):
    """Flask test client."""
    return flask_app.test_client()


@pytest.fixture()
def db_session(flask_app):
    """Provide a DB session scoped to the test."""
    with flask_app.app_context():
        yield _db.session

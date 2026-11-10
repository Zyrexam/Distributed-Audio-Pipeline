"""Auth unit tests: password hashing, JWT, service logic and HTTP routes.

The repository layer is replaced with fakes, so these run without a database.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.auth.dependencies import get_auth_service
from app.auth.jwt_handler import ALGORITHM, create_access_token, decode_access_token
from app.auth.service import (
    AuthService,
    DuplicateUserError,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.main import app
from app.models.user import User, UserRole

PASSWORD = "correct-horse-battery"


def make_user(**overrides) -> User:
    defaults = {
        "id": uuid4(),
        "username": "alice",
        "email": "alice@example.com",
        "password_hash": hash_password(PASSWORD),
        "role": UserRole.USER,
        "created_at": datetime.now(timezone.utc),
        "is_active": True,
    }
    return User(**{**defaults, **overrides})


def user_row(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "password_hash": user.password_hash,
        "role": user.role.value,
        "created_at": user.created_at,
        "is_active": user.is_active,
    }


class FakeDatabase:
    """Stands in for DatabaseConnection in service tests."""

    def __init__(self, row=None, error=None) -> None:
        self.row = row
        self.error = error
        self.calls = []

    def fetch_one(self, query, params=()):
        self.calls.append((query, params))
        if self.error is not None:
            raise self.error
        return self.row


class FakeAuthService:
    """Stands in for AuthService in route tests."""

    def __init__(self, user=None, error=None) -> None:
        self.user = user
        self.error = error

    def register_user(self, username, email, password):
        if self.error is not None:
            raise self.error
        return self.user

    def authenticate_user(self, username, password):
        return self.user

    def get_user_by_id(self, user_id):
        return self.user


@pytest.fixture
def client():
    """TestClient factory that swaps in a fake auth service."""

    def make(fake: FakeAuthService) -> TestClient:
        app.dependency_overrides[get_auth_service] = lambda: fake
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #


def test_password_hash_is_salted_and_verifiable():
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)

    assert first != second
    assert verify_password(PASSWORD, first)
    assert not verify_password("wrong-password", first)


def test_verify_password_returns_false_for_malformed_hash():
    assert verify_password(PASSWORD, "not-a-bcrypt-hash") is False


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #


def test_jwt_roundtrip_preserves_subject():
    subject = str(uuid4())

    assert decode_access_token(create_access_token(subject)) == subject


def test_jwt_rejects_garbage_token():
    assert decode_access_token("not.a.jwt") is None


def test_jwt_rejects_expired_token():
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        get_settings().auth_secret_key,
        algorithm=ALGORITHM,
    )

    assert decode_access_token(token) is None


def test_jwt_rejects_token_signed_with_another_secret():
    token = jwt.encode(
        {"sub": str(uuid4())}, "a-different-secret-of-sufficient-length", algorithm=ALGORITHM
    )

    assert decode_access_token(token) is None


# --------------------------------------------------------------------------- #
# AuthService (repository faked)
# --------------------------------------------------------------------------- #


def test_register_user_maps_row_and_stores_bcrypt_hash():
    user = make_user()
    database = FakeDatabase(row=user_row(user))

    created = AuthService(database).register_user("alice", "alice@example.com", PASSWORD)

    assert created.id == user.id
    assert created.username == "alice"
    assert created.role is UserRole.USER
    _, params = database.calls[0]
    assert params[2] != PASSWORD
    assert verify_password(PASSWORD, params[2])


def test_register_user_raises_on_duplicate():
    database = FakeDatabase(error=psycopg.errors.UniqueViolation())

    with pytest.raises(DuplicateUserError):
        AuthService(database).register_user("alice", "alice@example.com", PASSWORD)


def test_authenticate_user_accepts_correct_password():
    user = make_user()

    assert AuthService(FakeDatabase(row=user_row(user))).authenticate_user("alice", PASSWORD) == user


def test_authenticate_user_rejects_wrong_password():
    user = make_user()

    assert AuthService(FakeDatabase(row=user_row(user))).authenticate_user("alice", "nope") is None


def test_authenticate_user_rejects_unknown_user():
    assert AuthService(FakeDatabase(row=None)).authenticate_user("ghost", PASSWORD) is None


def test_authenticate_user_rejects_inactive_user():
    user = make_user(is_active=False)

    assert AuthService(FakeDatabase(row=user_row(user))).authenticate_user("alice", PASSWORD) is None


# --------------------------------------------------------------------------- #
# HTTP routes
# --------------------------------------------------------------------------- #


def test_register_returns_user_without_password_hash(client):
    user = make_user()

    response = client(FakeAuthService(user=user)).post(
        "/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": PASSWORD},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "alice"
    assert body["role"] == "USER"
    assert "password_hash" not in body


def test_register_returns_409_for_duplicate(client):
    auth_service = FakeAuthService(error=DuplicateUserError("duplicate"))

    response = client(auth_service).post(
        "/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": PASSWORD},
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "alice", "email": "alice@example.com", "password": "short"},
        {"username": "alice smith", "email": "alice@example.com", "password": PASSWORD},
        {"username": "alice", "email": "not-an-email", "password": PASSWORD},
    ],
)
def test_register_rejects_invalid_payload(client, payload):
    response = client(FakeAuthService()).post("/auth/register", json=payload)

    assert response.status_code == 422


def test_login_returns_bearer_token_for_valid_credentials(client):
    user = make_user()

    response = client(FakeAuthService(user=user)).post(
        "/auth/login", data={"username": "alice", "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"]) == str(user.id)


def test_login_returns_401_for_bad_credentials(client):
    response = client(FakeAuthService(user=None)).post(
        "/auth/login", data={"username": "alice", "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_requires_authentication(client):
    response = client(FakeAuthService(user=make_user())).get("/auth/me")

    assert response.status_code == 401


def test_me_returns_current_user(client):
    user = make_user()
    headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

    response = client(FakeAuthService(user=user)).get("/auth/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_me_rejects_token_for_unknown_user(client):
    headers = {"Authorization": f"Bearer {create_access_token(str(uuid4()))}"}

    response = client(FakeAuthService(user=None)).get("/auth/me", headers=headers)

    assert response.status_code == 401


def test_me_rejects_token_with_non_uuid_subject(client):
    headers = {"Authorization": f"Bearer {create_access_token('not-a-uuid')}"}

    response = client(FakeAuthService(user=make_user())).get("/auth/me", headers=headers)

    assert response.status_code == 401

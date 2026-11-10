import logging
from uuid import UUID

import bcrypt
import psycopg

from app.config import get_settings
from app.infrastructure.database import DatabaseConnection, db
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

BCRYPT_ROUNDS = 12

INSERT_USER_SQL = """
    INSERT INTO users (username, email, password_hash, role)
    VALUES (%s, %s, %s, 'USER')
    RETURNING id, username, email, password_hash, role, created_at, is_active
"""

SELECT_BY_USERNAME_SQL = """
    SELECT id, username, email, password_hash, role, created_at, is_active
    FROM users WHERE username = %s
"""

SELECT_BY_ID_SQL = """
    SELECT id, username, email, password_hash, role, created_at, is_active
    FROM users WHERE id = %s
"""


class DuplicateUserError(Exception):
    """Username or email already exists."""


def _row_to_user(row: dict) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=UserRole(row["role"]),
        created_at=row["created_at"],
        is_active=row["is_active"],
    )


def hash_password(password: str) -> str:
    digest = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    )
    return digest.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


class AuthService:
    """User account operations. DB is injected for testability."""

    def __init__(self, database: DatabaseConnection) -> None:
        self._db = database

    def get_user_by_username(self, username: str) -> User | None:
        row = self._db.fetch_one(SELECT_BY_USERNAME_SQL, (username,))
        return _row_to_user(row) if row else None

    def get_user_by_id(self, user_id: UUID) -> User | None:
        row = self._db.fetch_one(SELECT_BY_ID_SQL, (str(user_id),))
        return _row_to_user(row) if row else None

    def register_user(self, username: str, email: str, password: str) -> User:
        try:
            row = self._db.fetch_one(
                INSERT_USER_SQL,
                (username, email, hash_password(password)),
            )
        except psycopg.errors.UniqueViolation as exc:
            logger.info("Registration rejected: duplicate user %s", username)
            raise DuplicateUserError(
                "username or email already exists"
            ) from exc
        if row is None:  # defensive: INSERT ... RETURNING always returns
            raise RuntimeError("user insert returned no row")
        user = _row_to_user(row)
        logger.info("User registered: id=%s username=%s", user.id, username)
        return user

    def authenticate_user(self, username: str, password: str) -> User | None:
        user = self.get_user_by_username(username)
        # Always run a bcrypt verify (dummy hash if no such user)
        # to avoid a timing side-channel for user enumeration.
        stored_hash = user.password_hash if user else get_settings().auth_dummy_hash
        password_ok = verify_password(password, stored_hash)
        if user is None or not password_ok or not user.is_active:
            logger.warning("Failed login attempt: username=%s", username)
            return None
        logger.info("User logged in: id=%s username=%s", user.id, username)
        return user


# Default instance for routes; tests can override via app.dependency_overrides.
default_service = AuthService(db)

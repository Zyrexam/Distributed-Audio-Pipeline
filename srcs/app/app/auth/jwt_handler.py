import logging
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from app.config import get_settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"


def create_access_token(subject: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.auth_token_expire_minutes),
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Return the subject (user id) or None if invalid/expired.

    Never raises and never logs the token itself.
    """
    try:
        payload = jwt.decode(
            token, get_settings().auth_secret_key, algorithms=[ALGORITHM]
        )
    except JWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) and subject else None

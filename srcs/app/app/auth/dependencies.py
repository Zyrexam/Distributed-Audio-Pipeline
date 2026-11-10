import logging
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.auth.jwt_handler import decode_access_token
from app.auth.service import AuthService, default_service
from app.models.user import User

logger = logging.getLogger(__name__)

# tokenUrl tells Swagger UI (/docs) where to fetch a token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_auth_service() -> AuthService:
    return default_service


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    subject = decode_access_token(token)
    if subject is None:
        raise _UNAUTHORIZED
    try:
        user_id = UUID(subject)
    except (ValueError, AttributeError, TypeError):
        raise _UNAUTHORIZED
    user = auth_service.get_user_by_id(user_id)
    if user is None or not user.is_active:
        logger.warning("Token rejected: subject=%s", subject)
        raise _UNAUTHORIZED
    return user

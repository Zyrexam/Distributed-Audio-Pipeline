"""Auth HTTP routes.

Thin layer only: parse/validate input (Pydantic), call the
service, map domain outcomes to HTTP codes. No SQL here.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.dependencies import get_auth_service, get_current_user
from app.auth.jwt_handler import create_access_token
from app.auth.service import AuthService, DuplicateUserError
from app.models.user import User
from app.schemas.auth_schema import (
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        is_active=user.is_active,
    )


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    try:
        user = auth_service.register_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
        )
    except DuplicateUserError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="username or email already exists",
        )
    return _to_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user = auth_service.authenticate_user(
        username=form.username, password=form.password
    )
    if user is None:
        # Generic message by design: do not reveal which part failed.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def read_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return _to_response(current_user)

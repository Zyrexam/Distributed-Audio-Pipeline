from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class UserRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"
    WORKER = "WORKER"


@dataclass(frozen=True)
class User:
    id: UUID
    username: str
    email: str
    password_hash: str
    role: UserRole = UserRole.USER
    created_at: datetime | None = None
    is_active: bool = True

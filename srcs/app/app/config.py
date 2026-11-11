import logging
import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache

DEFAULT_DATABASE_URL = "postgresql://app:app@postgres:5432/audio_pipeline"
DEFAULT_FRONTEND_ORIGINS = ("http://localhost:5173", "http://localhost:8080")
DEFAULT_MINIO_ENDPOINT = "minio:9000"
DEFAULT_MINIO_BUCKET = "raw-audio"
DEFAULT_RABBITMQ_HOST = "rabbitmq"
DEFAULT_RABBITMQ_QUEUE = "audio.jobs"


@dataclass(frozen=True)
class Settings:
    """Validated runtime settings (from environment)."""

    auth_secret_key: str = field(repr=False)
    auth_dummy_hash: str
    database_url: str = DEFAULT_DATABASE_URL
    auth_token_expire_minutes: int = 60
    frontend_origins: tuple[str, ...] = DEFAULT_FRONTEND_ORIGINS
    log_level: str = "INFO"
    minio_endpoint: str = DEFAULT_MINIO_ENDPOINT
    minio_access_key: str = "minio"
    minio_secret_key: str = field(default="minio123", repr=False)
    minio_bucket: str = DEFAULT_MINIO_BUCKET
    minio_secure: bool = False
    rabbitmq_host: str = DEFAULT_RABBITMQ_HOST
    rabbitmq_user: str = "app"
    rabbitmq_password: str = field(default="app", repr=False)
    rabbitmq_queue: str = DEFAULT_RABBITMQ_QUEUE

    @classmethod
    def from_env(cls) -> "Settings":
        secret = os.getenv("AUTH_SECRET_KEY", "").strip()
        if not secret:
            raise RuntimeError(
                "AUTH_SECRET_KEY is not set. Refusing to start: "
                "generate one with: openssl rand -hex 32"
            )
        if len(secret) < 32:
            raise RuntimeError(
                "AUTH_SECRET_KEY must be at least 32 characters "
                "(generate one with: openssl rand -hex 32)"
            )

        # Used only to burn a real bcrypt verify for unknown usernames,
        # so login timing does not reveal whether an account exists.
        dummy_hash = os.getenv("AUTH_DUMMY_HASH", "").strip()
        if not dummy_hash:
            raise RuntimeError(
                "AUTH_DUMMY_HASH is not set. Generate one with: "
                "python -c \"import bcrypt,secrets;"
                "print(bcrypt.hashpw(secrets.token_bytes(24), bcrypt.gensalt()).decode())\""
            )
        if not dummy_hash.startswith(("$2a$", "$2b$", "$2y$")) or len(
            dummy_hash
        ) != 60:
            raise RuntimeError(
                "AUTH_DUMMY_HASH must be a bcrypt hash, e.g. $2b$12$..."
            )

        expire_raw = os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "60")
        try:
            expire = int(expire_raw)
        except ValueError as exc:
            raise RuntimeError(
                "AUTH_TOKEN_EXPIRE_MINUTES must be an integer"
            ) from exc
        if not 1 <= expire <= 1440:
            raise RuntimeError(
                "AUTH_TOKEN_EXPIRE_MINUTES must be between 1 and 1440"
            )

        origins_raw = os.getenv(
            "FRONTEND_ORIGINS", ",".join(DEFAULT_FRONTEND_ORIGINS)
        )
        origins = tuple(o.strip() for o in origins_raw.split(",") if o.strip())
        if not origins:
            raise RuntimeError("FRONTEND_ORIGINS must not be empty")

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise RuntimeError(f"Invalid LOG_LEVEL: {log_level}")

        secure_raw = os.getenv("MINIO_SECURE", "false").strip().lower()
        if secure_raw not in ("true", "false", "1", "0", "yes", "no"):
            raise RuntimeError("MINIO_SECURE must be a boolean")

        return cls(
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            auth_secret_key=secret,
            auth_dummy_hash=dummy_hash,
            auth_token_expire_minutes=expire,
            frontend_origins=origins,
            log_level=log_level,
            minio_endpoint=os.getenv(
                "MINIO_ENDPOINT", DEFAULT_MINIO_ENDPOINT
            ),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minio"),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minio123"),
            minio_bucket=os.getenv("MINIO_BUCKET", DEFAULT_MINIO_BUCKET),
            minio_secure=secure_raw in ("true", "1", "yes"),
            rabbitmq_host=os.getenv(
                "RABBITMQ_HOST", DEFAULT_RABBITMQ_HOST
            ),
            rabbitmq_user=os.getenv("RABBITMQ_USER", "app"),
            rabbitmq_password=os.getenv("RABBITMQ_PASSWORD", "app"),
            rabbitmq_queue=os.getenv(
                "RABBITMQ_QUEUE", DEFAULT_RABBITMQ_QUEUE
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings. Raises RuntimeError on invalid/missing config."""
    return Settings.from_env()


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once. Safe to call multiple times."""
    if logging.getLogger().handlers:
        logging.getLogger().setLevel(level)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
    )
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(level)

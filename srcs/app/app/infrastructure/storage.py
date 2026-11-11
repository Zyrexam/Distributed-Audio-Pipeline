import io
import logging
from minio import Minio
from minio.error import S3Error
from app.config import get_settings

logger = logging.getLogger(__name__)


class MinIOStorage:
    """Object storage operations used by the upload route and the worker."""

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        secure: bool | None = None,
        client=None,
    ) -> None:
        settings = get_settings()
        self.endpoint = endpoint or settings.minio_endpoint
        self.access_key = access_key or settings.minio_access_key
        self.secret_key = secret_key or settings.minio_secret_key
        self.bucket = bucket or settings.minio_bucket
        self.secure = settings.minio_secure if secure is None else secure
        self.client = client or Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )

    def ensure_bucket_exists(self) -> None:
        """Create the configured bucket if it does not exist yet."""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info("Created bucket %s", self.bucket)
        except S3Error as exc:
            raise RuntimeError(
                f"unable to prepare bucket {self.bucket!r}: {exc}"
            ) from exc

    def upload_bytes(
        self, object_key: str, data: bytes, content_type: str | None = None
    ) -> None:
        """Store bytes under object_key in the configured bucket."""
        self.client.put_object(
            bucket_name=self.bucket,
            object_name=object_key,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
        )

    def download_bytes(self, object_key: str) -> bytes:
        """Read an object fully into memory."""
        response = self.client.get_object(self.bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete_object(self, object_key: str) -> None:
        """Delete an object (used to clean up orphaned uploads)."""
        self.client.remove_object(self.bucket, object_key)

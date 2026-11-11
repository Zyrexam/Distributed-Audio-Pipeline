from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


class MetricsCollector:
    """The six pipeline metrics defined in SPEC §9.1."""

    def __init__(self) -> None:
        self.uploads_total = Counter(
            "uploads_total", "Audio files uploaded"
        )
        self.upload_seconds = Histogram(
            "upload_seconds", "Upload request latency"
        )
        self.jobs_published_total = Counter(
            "jobs_published_total", "Jobs published to the queue"
        )
        self.jobs_completed_total = Counter(
            "jobs_completed_total", "Jobs completed by a worker"
        )
        self.jobs_failed_total = Counter(
            "jobs_failed_total", "Jobs that failed permanently"
        )
        self.job_processing_seconds = Histogram(
            "job_processing_seconds", "Worker processing time"
        )

    def record_upload(self) -> None:
        self.uploads_total.inc()

    def record_upload_latency(self, seconds: float) -> None:
        self.upload_seconds.observe(seconds)

    def record_job_published(self) -> None:
        self.jobs_published_total.inc()

    def record_job_completed(self) -> None:
        self.jobs_completed_total.inc()

    def record_job_failed(self) -> None:
        self.jobs_failed_total.inc()

    def record_job_processing_time(self, seconds: float) -> None:
        self.job_processing_seconds.observe(seconds)


metrics = MetricsCollector()


def render_metrics() -> bytes:
    """Prometheus text exposition for the /metrics endpoint."""
    return generate_latest()

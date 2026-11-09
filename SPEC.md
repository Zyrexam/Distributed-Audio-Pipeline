# SPEC — Distributed Audio Processing Pipeline with Observability

> **Purpose:** Complete specification for rebuilding this system **from scratch**, in your own code,
> so as to learn every concept it contains.
> **Reference original:** Matteo Cardellini, University of Bologna — Distributed Systems course project.
> Original repo: `https://github.com/matteo1610/distributed-audio-pipeline` (MIT License).
> Do not copy the original code verbatim — implement from this spec and credit the original if you publish.

---

## 1. System Overview

A web application where authenticated users upload **WAV audio files**. A FastAPI API stores the
file in object storage (MinIO), publishes a processing job to a message queue (RabbitMQ), and
independent worker processes extract audio metadata (duration, sample rate, channels), persisting
results in PostgreSQL. Users poll for job status/results. The whole system is observable via
Prometheus metrics and Grafana dashboards, containerized with Docker, and deployable on Kubernetes.

### 1.1 Core capabilities
- User registration, login, JWT auth, role-based access (USER / ADMIN / WORKER)
- Async audio upload → queued job → background processing → retrievable results
- Ownership enforcement: users only see their own jobs (admins see all)
- Fault tolerance: retries with a persistent attempt budget; permanent failures fail fast
- Observability: metrics on API + worker, 4 alert rules, provisioned Grafana dashboard
- Horizontal scaling: workers are stateless and horizontally scalable (incl. K8s HPA)
- Containerized: Docker Compose (local) and Helm charts on kind (Kubernetes)

### 1.2 Design goals (from the project proposal)
- Event-driven architecture, asynchronous communication, loose coupling
- Clear service boundaries, eventual consistency in the pipeline
- Scalability (horizontal worker scaling) and fault tolerance (retry/reassignment)
- Observability (metrics collection + visualization)
- Reproducible deployment (Docker → Kubernetes)

---

## 2. Technology Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Language | Python | 3.12 |
| Package manager | Poetry | 1.8.3, lockfiles committed |
| API framework | FastAPI + Uvicorn (standard) | 0.115.12 / 0.34.0 |
| Validation | Pydantic | v2 (>=2.5) |
| Database | PostgreSQL 16 | image `postgres:16.13-bookworm`, driver `psycopg[binary]` 3.2.6, **raw SQL, no ORM** |
| Message broker | RabbitMQ 4.2.5 (management) | client `pika` 1.3.2, durable queue `audio.jobs` |
| Object storage | MinIO | image `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z-cpuv1`, S3 API, client `minio` 7.2.15 |
| Auth | python-jose[cryptography] (JWT HS256), passlib[bcrypt] + bcrypt<5 | access token expiry 60 min |
| Audio | Python stdlib `wave` | WAV only: duration, sample rate, channels |
| Metrics | prometheus_client 0.21.1 | Counter + Histogram |
| Frontend | Vanilla HTML/CSS/JS + nginx 1.29-alpine | no build step, no framework |
| Containers | Docker (multi-stage builds) + Docker Compose | healthchecks, named volumes |
| Orchestration | Kubernetes via kind + Helm (2 charts) | Deployments, Services, PVCs, ConfigMap, Secret, HPA |
| Testing | pytest 8.3.5, httpx, pytest-asyncio | 37 tests total (see §13) |
| Linting | Ruff | line-length 100, rules E/F/W (E501 ignored) |
| CI/CD | GitHub Actions | pytest matrix + DockerHub image push |

---

## 3. Architecture

```
                        ┌──────────────────────────────────────────────┐
                        │                    Browser                   │
                        │   nginx :5173 — static HTML/CSS/JS (SPA)     │
                        │   JWT in localStorage, polls for job status  │
                        └───────────────────┬──────────────────────────┘
                                            │ HTTP/REST (Bearer JWT)
                                            ▼
                        ┌──────────────────────────────────────────────┐
                        │            FastAPI API  :8000              │
                        │  /auth/*  /api/*  /health  /metrics        │
                        └──┬───────────────┬───────────────┬─────────┘
                           │               │               │
              upload bytes │   publish     │    SQL        │  query
                           ▼   {job_id,    │               ▼
                        ┌──────┐ object_key}│        ┌────────────┐
                        │ MinIO│◄───────────┘        │ PostgreSQL │
                        │ :9000│                     │ :5432      │
                        │bucket│                     │ users/jobs │
                        │raw-  │                     │ results    │
                        │audio │                     └─────▲──────┘
                        └──▲───┘                           │ save
                           │ download                      │ results
                           │                               │
              ┌────────────┴─────────────┐        ┌────────┴──────────┐
              │      RabbitMQ :5672      │        │  Worker(s)        │
              │  durable queue audio.jobs│◄───────│  consume → process│
              │  prefetch=1, ack always  │publish │  → retry/fail     │
              └──────────────────────────┘ retry  │  metrics :9100    │
                                                  └────────┬──────────┘
                                                           │ scrape /metrics
                        ┌──────────────────────────────────▼──────────────┐
                        │  Prometheus :9090  ──►  Grafana :3000         │
                        │  4 alert rules, provisioned dashboard         │
                        └─────────────────────────────────────────────────┘
```

### 3.1 Components
1. **API (FastAPI)** — auth, uploads, job queries. Holds no job state in memory; all state in Postgres.
2. **Worker (standalone Python process)** — consumes queue, downloads from MinIO, extracts WAV
   features, writes results. Stateless; scale by adding replicas.
3. **RabbitMQ** — durable queue `audio.jobs`, persistent delivery mode, `basic_qos(prefetch_count=1)`.
4. **PostgreSQL** — system of record: users, jobs, processing results.
5. **MinIO** — object store for uploaded audio, single bucket `raw-audio`, key `uploads/{uuid}-{filename}`.
6. **Frontend (nginx)** — static SPA; configurable API base URL (default `http://localhost:8000`).
7. **Observability stack** — Prometheus scrapes API (`:8000/metrics`) and worker (`:9100/metrics`)
   every 10s; Grafana visualizes; alerts evaluate every 10s.

---

## 4. Repository Layout (target structure for the rebuild)

```
distributed-audio-pipeline/
├── README.md                  # overview, quickstart, architecture summary
├── .gitignore
├── .github/workflows/
│   ├── python-tests.yml       # pytest for app + worker on push/PR (path-filtered)
│   ├── dockerhub-manual-push.yml  # manual: build+push 3 images (amd64+arm64)
│   
├── docs/
│   ├── report/                # LaTeX final report + figures (architecture, class, ER,
│   │                          #   component, 4 sequence-flow, 2 state-diagram, k8s, grafana)
└── srcs/
    ├── docker-compose.yaml    # 6 services (see §11.1)
    ├── db/init.sql            # schema (see §6)
    ├── app/                   # FastAPI backend
    │   ├── main.py            # create_app() factory, lifespan, CORS, /health, /metrics
    │   ├── config.py          # logging configuration
    │   ├── api/routes/upload.py
    │   ├── auth/              # jwt_handler.py, service.py, routes.py, dependencies.py
    │   ├── models/            # user.py, audio_job.py  (dataclasses + Enums)
    │   ├── schemas/           # auth_schema.py, job_schema.py (Pydantic)
    │   ├── services/          # job_service.py, audio_processor.py
    │   ├── repositories/      # job_repository.py (raw SQL)
    │   ├── infrastructure/    # database.py, broker.py, storage.py, metrics.py
    │   ├── tests/             # test_api.py, test_auth.py
    │   ├── Dockerfile         # multi-stage build
    │   ├── pyproject.toml     # poetry, script `api = app.main:main`
    │   └── .env.example
    ├── worker/
    │   ├── worker.py          # ProcessorWorker + run_worker()
    │   ├── tests/test_worker.py
    │   ├── Dockerfile         # copies app/ package + worker.py
    │   ├── pyproject.toml     # script `worker = worker:run_worker`
    │   └── poetry.lock
    ├── frontend/              # index.html, app.js, styles.css, Dockerfile (nginx)
    ├── observability/
    │   ├── docker-compose.observability.yaml
    │   ├── prometheus/prometheus.yml, alerts.yml
    │   └── grafana/{dashboards,provisioning}
    ├── k8s/
    │   ├── distributed-audio-pipeline/  # Helm chart: app stack (see §11.3)
    │   ├── observability/               # Helm chart: prometheus + grafana
    │   ├── kind/kind-config.yaml
    │   ├── values-kind.yaml, observability/values-kind.yaml
    └── scripts/
        ├── stress_uploads.sh  # load generator: synth WAVs, register user, upload patterns
        └── sync_k8s_assets.sh # copy db/init.sql + observability files into Helm charts
```

---

## 5. Backend Design (layered architecture)

```
HTTP request
  → Routes        (api/routes/, auth/routes.py)      — parse input, map errors to HTTP codes
  → Services      (services/)                        — business logic, orchestration
  → Repositories  (repositories/)                    — SQL data access
  → Infrastructure (infrastructure/)                — DB / RabbitMQ / MinIO / metrics clients
  ← Models        (models/)  dataclasses             — domain objects
  ← Schemas       (schemas/) Pydantic                — API contracts
```

### 5.1 `main.py` (FastAPI factory)
- `create_app()` builds app with title/version, `lifespan` handler, CORS middleware
- Lifespan startup: wait up to 20s for Postgres health (`is_healthy()` poll, 1s interval),
  `ensure_bucket_exists()` on MinIO, best-effort RabbitMQ health check (warn, don't fail)
- CORS origins from `FRONTEND_ORIGINS` env (default includes localhost:5173 and :8080)
- Routes: `GET /health` → `{"status": "ok"}`; `GET /metrics` → Prometheus exposition format
- Entry: `uvicorn.run(app, host="0.0.0.0", port=8000)`

### 5.2 Auth (`auth/`)
- `jwt_handler.py` — HS256; payload `{"sub": user_id, "exp": now + AUTH_TOKEN_EXPIRE_MINUTES (60)}`;
  **refuses to import/start if `AUTH_SECRET_KEY` is unset** (no insecure default)
- `service.py` — bcrypt via passlib: `register_user()` inserts user (role USER), `authenticate_user()`
- `dependencies.py` — `OAuth2PasswordBearer(tokenUrl="/auth/login")`; `get_current_user` decodes JWT,
  loads user from DB, rejects inactive/unknown users with 401
- `routes.py` — `POST /auth/register`, `POST /auth/login` (OAuth2 form → `TokenResponse`), `GET /auth/me`

### 5.3 Models (`models/`)
- `User` dataclass: id, username, email, password_hash, role, created_at, is_active
- `UserRole` enum: USER, ADMIN, WORKER
- `AudioJob` dataclass: id, owner_id, object_key, status, created/updated_at, error_message, attempt_count
- `JobStatus` enum: PENDING, PROCESSING, DONE, FAILED (+ `is_processing/is_completed/is_failed`)
- `AudioFeatures` / `ProcessedAudio` dataclasses with `is_valid()` validators

### 5.4 Services
- `JobService` (constructed with repo, broker, storage — dependency injection by hand):
  - `create_and_publish_job(owner_id, object_key)` → repo insert → publish `{"job_id", "object_key"}`
  - `get_job_details(job_id)` → `{"job": ..., "result": ...}` or None
  - `mark_job_processing / mark_job_pending / mark_job_completed / mark_job_failed`
  - `increment_attempt(job_id)` → persistent retry counter
  - `save_job_results(...)` → delegates to repo
- `AudioProcessor.extract_audio_features(bytes)` → `(duration, sample_rate, channels)` or
  `(None, None, None)` on any decode error. Uses `wave` module: `duration = nframes / framerate`.

### 5.5 Repositories (`repositories/job_repository.py`, 266 lines)
Raw SQL via `psycopg` (no ORM): `create_job`, `get_job`, `get_processing_result`,
`update_job_status`, `increment_attempt`, `save_processing_result`.

### 5.6 Infrastructure clients (all env-configurable with Docker-hostname defaults)
- `database.py` — `DatabaseConnection`: `get_connection`, `execute_query`, `fetch_one`, `is_healthy`
- `broker.py` — `RabbitMQBroker`: durable queue declare, persistent publish (`PERSISTENT_DELIVERY_MODE`),
  `consume_messages(callback, prefetch_count=1)`, `is_healthy()`
- `storage.py` — `MinIOStorage`: `ensure_bucket_exists`, `upload_bytes`, `download_bytes`,
  `delete_object` (orphan cleanup), `is_healthy`
- `metrics.py` — `MetricsCollector` (see §9.1)

---

## 6. Data Model (`srcs/db/init.sql`)

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

users (
  id UUID PK DEFAULT gen_random_uuid(),
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'USER' CHECK (role IN ('USER','ADMIN','WORKER')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  is_active BOOLEAN DEFAULT TRUE
)

jobs (
  id UUID PK DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  object_key TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING','PROCESSING','DONE','FAILED')),
  error_message TEXT,
  attempt_count INT NOT NULL DEFAULT 0,
  created_at / updated_at TIMESTAMPTZ DEFAULT NOW()
)

processing_results (
  id UUID PK DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  output_path TEXT NOT NULL,
  duration_seconds NUMERIC, sample_rate INT, channels INT, audio_format TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
)

Indexes: jobs(status), jobs(owner_id), jobs(object_key),
         processing_results(job_id), users(username), users(email)
```

No migration framework — schema is applied once by Postgres' `/docker-entrypoint-initdb.d/`.
(The `ALTER TABLE ... ADD COLUMN IF NOT EXISTS attempt_count` line shows schema evolution was
handled ad-hoc.)

---

## 7. API Specification

### 7.1 Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | — | JSON `{username, email, password}` → user |
| POST | `/auth/login` | — | OAuth2 form `{username, password}` → `{access_token}` |
| GET | `/auth/me` | Bearer | current user |
| POST | `/api/uploads` | Bearer | multipart file → `JobResponse{job_id, object_key, message}` |
| GET | `/api/jobs/{job_id}` | Bearer | `JobStatusResponse{job_id, status, created_at, updated_at, error_message}` |
| GET | `/api/jobs/{job_id}/results` | Bearer | `ProcessedAudioResponse` (404 if no result yet) |
| GET | `/health` | — | `{"status":"ok"}` |
| GET | `/metrics` | — | Prometheus text exposition |

### 7.2 Behavioural rules
- Upload: reject empty file (400); object key `uploads/{uuid4}-{original filename}`;
  record `uploads_total` + `upload_seconds`; on publish failure → delete MinIO object, return 500.
- Job access: owner **or** ADMIN role, else 403. Invalid UUID → 400. Missing job → 404.
- All `/api/*` routes require a valid Bearer token (401 otherwise).

---

## 8. Worker Specification (`worker/worker.py`)

- `ProcessorWorker(broker, storage, job_service, metrics, max_retries=3, retry_delay_seconds=0)`
- `run_worker()`: wait for DB (20×1s), `ensure_bucket_exists`, start metrics HTTP server on
  `WORKER_METRICS_PORT` (9100), then consume.
- Per message (`process_message`):
  1. Parse JSON → `job_id`, `object_key`, `attempt`
  2. Mark `PROCESSING`; **increment persistent attempt counter in DB first** (so crash/redelivery
     can't reset the retry budget — the queue payload's attempt is *not* durable)
  3. Download bytes from MinIO; extract WAV features; time the work
  4. **Undecodable audio** → permanent failure: mark `FAILED`, `jobs_failed_total++`, ack, return
  5. Success → save results, mark `DONE`, record `job_processing_seconds` + `jobs_completed_total`, ack
  6. **Any other exception** → if `attempt < max_retries`: mark `PENDING`, optional sleep,
     re-publish `{job_id, object_key, attempt+1}`; else mark `FAILED` + metric. Always ack at the end
     (no redelivery loops; retries are explicit re-publishes).

---

## 9. Observability

### 9.1 Metrics (`infrastructure/metrics.py`)
| Metric | Type | Recorded when |
|---|---|---|
| `uploads_total` | Counter | successful upload to MinIO |
| `upload_seconds` | Histogram | upload endpoint latency |
| `jobs_published_total` | Counter | job published to queue |
| `jobs_completed_total` | Counter | worker success |
| `jobs_failed_total` | Counter | worker permanent failure / retries exhausted |
| `job_processing_seconds` | Histogram | worker processing time |

### 9.2 Prometheus (`observability/prometheus/prometheus.yml`)
- `scrape_interval: 10s`, `evaluation_interval: 10s`
- Jobs: `prometheus` (self), `api` → `api:8000/metrics`, `worker` → `worker:9100/metrics`
- Alert rules file: `alerts.yml`

### 9.3 Alerts (`alerts.yml`, 4 rules)
1. `ApiDown` — `up{job="api"} == 0` for 30s — critical
2. `WorkerDown` — `up{job="worker"} == 0` for 30s — critical
3. `JobFailuresDetected` — `increase(jobs_failed_total[5m]) > 0` for 1m — warning
4. `HighUploadLatency` — avg `upload_seconds` > 0.5s for 2m — warning

### 9.4 Grafana
- Dashboard **provisioned automatically** from JSON (`distributed-audio-overview.json`) — no manual import
- Datasource provisioned via YAML; default login `admin`/`admin`; UI :3000, Prometheus UI :9090
- Separate deployable: `docker compose -f observability/docker-compose.observability.yaml up -d`
  (requires API + worker already running)

---

## 10. Frontend Specification (`srcs/frontend/`, vanilla JS, nginx)

- Single page (`index.html`, 102 lines): Auth panel (register/login forms, "Who am I?", logout),
  Upload panel (file input `accept="audio/*"`), Job Tracking (job-id input, status/results buttons,
  start/stop polling), System panel (health check, sample metrics), console log output (`<pre>`)
- `app.js` (321 lines): ES module; `fetch` wrapper adding `Authorization: Bearer <token>`;
  token persisted in `localStorage` (`pipeline.token`); configurable API base URL input
  (default `http://localhost:8000`); polling loop for job status; log-to-console helper
- `styles.css` (240 lines): custom styling, Google Fonts (Space Grotesk + IBM Plex Mono)
- Served read-only by nginx on `:5173` (note: root README says :8080 — **compose is correct**)

---

## 11. Deployment

### 11.1 Docker Compose (`srcs/docker-compose.yaml`) — 6 services

| Service | Image / Build | Ports | Notes |
|---|---|---|---|
| postgres | `postgres:16.13-bookworm` | 5432 | volume `postgres_data`, mounts `db/init.sql`, healthcheck `pg_isready` |
| rabbitmq | `rabbitmq:4.2.5-management` | 5672, 15672 | healthcheck `rabbitmq-diagnostics check_port_connectivity` |
| minio | `quay.io/minio/minio:...-cpuv1` | 9000, 9001 | volume `minio_data`, healthcheck `mc ready local` |
| api | build `./app` | 8000 | `depends_on` all infra `service_healthy`; requires `AUTH_SECRET_KEY` |
| worker | build `./worker` (dockerfile) | (9100 internal) | env `WORKER_MAX_RETRIES=3`, `WORKER_RETRY_DELAY_SECONDS=0` |
| frontend | `nginx:1.29-alpine` | 5173 | mounts `./frontend` read-only |

**Run:** `cd srcs && AUTH_SECRET_KEY=$(openssl rand -hex 32) docker compose up -d`
**Dev credentials (hardcoded):** Postgres `app/app`, RabbitMQ `app/app`, MinIO `minio/minio123`.

### 11.2 Dockerfiles
- **API (multi-stage):** builder `python:3.12.13-slim-bookworm` + build-essential → Poetry install
  (`--only main --no-root`, in-project venv) → runtime slim + `curl` + `postgresql-client`,
  venv copied, `HEALTHCHECK curl -f localhost:8000/health`, `CMD ["python","-m","app.main"]`
- **Worker (single-stage):** Poetry 1.8.3, `POETRY_VIRTUALENVS_CREATE=false`, installs deps,
  copies `app/` package + `worker.py` flat, `CMD ["python","worker.py"]`
- **Frontend:** nginx alpine serving static files

### 11.3 Kubernetes (kind + Helm)
- **Prereqs:** Docker, `kind`, `helm`, `kubectl`
- **Two charts:**
  - `distributed-audio-pipeline` — API, worker (+ **HPA** on worker, CPU utilization),
    frontend, Postgres, RabbitMQ, MinIO; PVCs for stateful services; `Secret` for credentials;
    `ConfigMap` for init SQL (synced from `db/init.sql`); images pulled pre-built from
    DockerHub `matteo1610/*` (multi-arch, so Apple Silicon works)
  - `observability` — Prometheus + Grafana + alert rules + dashboard (synced from `observability/`)
- **Usage:** `kind create cluster --name audio-pipeline --config k8s/kind/kind-config.yaml` →
  `helm install dap k8s/distributed-audio-pipeline -f k8s/values-kind.yaml` →
  `helm install dap-observability k8s/observability -f k8s/observability/values-kind.yaml`
- Scrape targets assume app release name `dap` (`dap-api:8000`, `dap-worker-metrics:9100`) —
  override `prometheus.scrapeTargets` if renamed
- Exposed: API :8000, frontend :30517, RabbitMQ :15672, MinIO :9001, worker metrics :9100,
  Prometheus :9090, Grafana :3000
- `scripts/sync_k8s_assets.sh` keeps chart copies of `init.sql`/observability in sync with canonical sources

### 11.4 CI/CD (GitHub Actions)
- **`python-tests.yml`** — on push/PR touching `srcs/app/**` or `srcs/worker/**`: matrix over
  app/worker on ubuntu-latest, Python 3.12, Poetry 1.8.3, `poetry install --with dev`, `pytest -q`
- **`dockerhub-manual-push.yml`** — manual (`workflow_dispatch`): builds api/frontend/worker
  multi-arch images, pushes to DockerHub using repo secrets `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN`

### 11.5 Utility scripts
- `stress_uploads.sh` — env-tunable (`TOTAL_UPLOADS=50`, `CONCURRENCY=10`,
  `PATTERN=mixed|steady|ramp|burst`, WAV duration/sample-rate/channels): registers a fresh user,
  synthesizes WAV tones via embedded Python, uploads concurrently, exercises the pipeline under load
- `sync_k8s_assets.sh` — asset sync described above

---

## 12. Environment Variables

| Variable | Default | Required | Used by |
|---|---|---|---|
| `AUTH_SECRET_KEY` | — (app **refuses to start** without it) | ✅ | API JWT signing |
| `AUTH_TOKEN_EXPIRE_MINUTES` | `60` | | API |
| `DATABASE_URL` | `postgresql://app:app@postgres:5432/audio_pipeline` | | API, worker |
| `RABBITMQ_HOST` / `_USER` / `_PASSWORD` / `_QUEUE` | `rabbitmq` / `app` / `app` / `audio.jobs` | | API, worker |
| `MINIO_ENDPOINT` / `_ACCESS_KEY` / `_SECRET_KEY` / `_BUCKET` | `minio:9000` / `minio` / `minio123` / `raw-audio` | | API, worker |
| `FRONTEND_ORIGINS` | localhost:5173 + :8080 list | | API CORS |
| `WORKER_MAX_RETRIES` | `3` | | worker |
| `WORKER_RETRY_DELAY_SECONDS` | `0` | | worker |
| `WORKER_METRICS_PORT` | `9100` | | worker |

Defaults assume Docker Compose service names — for bare-metal runs override hostnames to `localhost`
(see `srcs/app/.env.example`). There are **no third-party API keys** anywhere in the system.

---

## 13. Testing

- **37 tests total:** `app/tests/test_api.py` (15), `app/tests/test_auth.py` (10),
  `worker/tests/test_worker.py` (12)
- Run: `poetry run pytest` from `srcs/app` or `srcs/worker` (testpaths configured in each `pyproject.toml`)
- CI runs both suites on every relevant change (§11.4)

---

## 14. Request Flows (sequence summary)

1. **Register/Login:** client → `/auth/register` → bcrypt hash → insert user; `/auth/login` → verify →
   JWT issued → stored in `localStorage` → sent as `Bearer` on subsequent calls.
2. **Upload & job creation:** `POST /api/uploads` (multipart) → validate → MinIO put →
   `jobs` row (PENDING) → RabbitMQ publish → `JobResponse`. Publish failure ⇒ MinIO delete + 500.
3. **Worker processing:** consume → PROCESSING → persistent attempt++ → MinIO get → WAV parse →
   `processing_results` row → DONE → ack. Errors per §8 (retry ≤3, permanent fail fast).
4. **Status/results:** `GET /api/jobs/{id}` (poll from frontend) → status; when DONE,
   `GET /api/jobs/{id}/results` → features. Ownership enforced (owner or ADMIN).

---

## 15. Concurrency & Scaling Notes
- Workers are stateless; scale with `docker compose up --scale worker=N` or K8s HPA (CPU-based)
- `basic_qos(prefetch_count=1)` = fair distribution, one job per worker at a time
- Acknowledgement model: ack after terminal handling; retries are **explicit re-publish**,
  not redelivery — avoids poison-message loops
- Durable queue + persistent messages survive RabbitMQ restarts; DB `attempt_count` survives workers
- Eventual consistency: API returns job immediately (PENDING); result appears later — clients poll

---

## 16. Known Limitations & Improvement Ideas (v2)
1. WAV only — add MP3/OGG via `ffmpeg`/`librosa`
2. No dead-letter queue/exchange for exhausted retries
3. Upload reads entire file into memory — add streaming + file-size limit
4. Schema via one-shot `init.sql` — adopt a migration tool (Alembic)
5. Raw SQL + hand-rolled DI — consider SQLAlchemy + FastAPI `Depends`
6. README/compose port mismatch (:8080 vs :5173) — fix docs
7. Worker metrics port not published in main compose
8. No rate limiting / no CORS lockdown beyond env list

---

## 17. Acceptance Criteria (rebuild checklist)

- [ ] `docker compose up -d` (with `AUTH_SECRET_KEY` set) starts all 6 services healthy
- [ ] Register → login → upload WAV → job reaches DONE → results return correct duration/rate/channels
- [ ] Non-WAV upload → job FAILED with "Invalid or unsupported audio data", no retries consumed
- [ ] Transient worker failure → retried up to 3× (attempt_count visible in DB), then FAILED
- [ ] Users cannot access other users' jobs (403); admins can
- [ ] `/metrics` on API + worker; Prometheus scrapes both; 4 alerts fire under fault injection
- [ ] Grafana dashboard shows uploads, processing time, completed/failed counts
- [ ] pytest: 37+ tests pass locally and in CI
- [ ] Helm install on kind brings up full stack; worker HPA scales under `stress_uploads.sh`
- [ ] HPA + stress script demonstrate concurrent processing (pattern: burst)

---

## 18. Suggested Build Order
1. Compose infra (Postgres + RabbitMQ + MinIO) + healthchecks
2. DB schema (`init.sql`) + psycopg connection layer
3. Auth (register/login/JWT/dependency)
4. API core (factory, CORS, /health, /metrics, upload, job queries)
5. Queue publish + worker consume/process/retry + state machine
6. Frontend (auth, upload, polling)
7. Observability (metrics → Prometheus → alerts → Grafana)
8. Tests (API, auth, worker)
9. Dockerfiles + full Compose
10. Kubernetes + Helm + HPA on kind
11. CI/CD (pytest + image push)
12. Docs (README, diagrams, report)


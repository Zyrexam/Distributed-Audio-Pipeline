# Distributed Audio Pipeline

A work-in-progress audio processing pipeline: a FastAPI service, Postgres for
state, RabbitMQ for the job queue, MinIO for audio files, a Python worker that
does the processing, and Prometheus with Grafana for metrics. The full design is
in [SPEC.md](SPEC.md).

The auth slice is finished. You can register, log in and fetch the current user.
The database schema exists, and the MinIO, RabbitMQ and metrics clients are
written. Uploads, jobs and the worker come next.

## Status

Working:

- FastAPI app with CORS, security headers and JSON error handlers
- Postgres connection pool (psycopg, no ORM) and the `users`, `jobs`, `processing_results` tables
- Register, login and current-user endpoints with bcrypt hashes and HS256 tokens
- Settings validated at startup; the app will not start without `AUTH_SECRET_KEY`
- MinIO client for bucket setup, upload, download and delete, plus a RabbitMQ publisher
- Prometheus metrics behind `/metrics`
- Docker Compose with Postgres, RabbitMQ and MinIO
- 41 tests that need no containers

Still empty:

- `POST /api/uploads` and the two job query routes
- Job repository and service
- The worker (`srcs/worker` has no code)
- Frontend, observability stack, Dockerfiles, Kubernetes manifests, CI

## Layout

```
srcs/
  app/                  FastAPI service
    app/
      auth/             routes, service, JWT, dependencies
      config.py         env settings, validated at startup
      main.py           app factory, middleware, /health, /metrics
      infrastructure/   database, storage, broker, metrics
      models/           domain dataclasses
      repositories/     SQL (empty for now)
      schemas/          request/response models
      services/         business logic (auth only so far)
    tests/
    pyproject.toml
  db/init.sql           schema, loaded by Postgres on first start
  docker-compose.yaml   Postgres + RabbitMQ + MinIO
  worker/               queue consumer (not written yet)
  frontend/ k8s/ observability/ scripts/
```

## Running it

You need Docker and Python 3.12+ with Poetry.

Start the infrastructure:

```bash
cd srcs
docker compose up -d
```

Start the API:

```bash
cd srcs/app
```

`.env.example` lists every variable the app reads. Nothing loads that file for
you, so export the values first. On PowerShell, `$env:AUTH_SECRET_KEY = "..."` and
so on.

```bash
export AUTH_SECRET_KEY=$(openssl rand -hex 32)
export AUTH_DUMMY_HASH='$2b$12$4.Ddy7ZCvMZyKnbIBhiAR.gvSwa7lCMTKtqO2rb8Gh/J6ce2sFbVa'
export DATABASE_URL=postgresql://app:app@localhost:5432/audio_pipeline
# MinIO and RabbitMQ default to the compose hostnames, so use localhost locally:
export MINIO_ENDPOINT=localhost:9000
export RABBITMQ_HOST=localhost

poetry install
poetry run api
```

Then:

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Metrics: http://localhost:8000/metrics
- MinIO console: http://localhost:9001 (`minio` / `minio123`)
- RabbitMQ management: http://localhost:15672 (`app` / `app`)

## Tests

```bash
cd srcs/app
poetry install --with dev
poetry run pytest -q
```

The 41 tests run without Postgres, RabbitMQ or MinIO. The database, storage and
broker are replaced with fakes, so there is no container that can fail and hide a
bug in the code. They cover settings validation, security headers, password
hashing, JWTs, the auth service, the auth routes and the infrastructure clients.

## API

| Method | Path | Auth | Status |
|---|---|---|---|
| GET | `/health` | - | implemented |
| GET | `/metrics` | - | implemented |
| POST | `/auth/register` | - | implemented |
| POST | `/auth/login` | - | implemented |
| GET | `/auth/me` | Bearer | implemented |
| POST | `/api/uploads` | Bearer | planned |
| GET | `/api/jobs/{id}` | Bearer | planned |
| GET | `/api/jobs/{id}/results` | Bearer | planned |

Login takes an OAuth2 form (`username`, `password`); the other endpoints take
JSON.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `AUTH_SECRET_KEY` | none | Required, 32+ chars. JWT signing key. |
| `AUTH_DUMMY_HASH` | none | Required. Bcrypt hash used to equalise login timing for unknown users. |
| `AUTH_TOKEN_EXPIRE_MINUTES` | `60` | Between 1 and 1440. |
| `DATABASE_URL` | `postgresql://app:app@postgres:5432/audio_pipeline` | |
| `FRONTEND_ORIGINS` | `http://localhost:5173,http://localhost:8080` | Comma-separated CORS allowlist. |
| `LOG_LEVEL` | `INFO` | |
| `MINIO_ENDPOINT` | `minio:9000` | Compose hostname; use `localhost:9000` locally. |
| `MINIO_ACCESS_KEY` | `minio` | |
| `MINIO_SECRET_KEY` | `minio123` | |
| `MINIO_BUCKET` | `raw-audio` | |
| `MINIO_SECURE` | `false` | |
| `RABBITMQ_HOST` | `rabbitmq` | Compose hostname. |
| `RABBITMQ_USER` | `app` | |
| `RABBITMQ_PASSWORD` | `app` | |
| `RABBITMQ_QUEUE` | `audio.jobs` | Durable queue. |

Nothing in this list needs a third-party API key.

## Design notes

Settings are parsed once at startup and validated. A missing or short
`AUTH_SECRET_KEY` stops the process instead of falling back to a default secret.

Login timing does not reveal whether an account exists. An unknown username still
gets a real bcrypt check against `AUTH_DUMMY_HASH`, so the response takes about as
long as a wrong password.

Routes parse input, services hold the logic and repositories hold the SQL. Imports
point downwards only.

There is no ORM. Queries are parameterised and each concern keeps its SQL in one
place.

Tests replace the edges (`AuthService(database)`, `MinIOStorage(client=...)`),
which is why the suite runs without containers.

## Next

In build order: job model and repository, upload route with queue publish and
orphan cleanup on failure, job status and results routes, then the worker with its
retry accounting, then the frontend and observability.

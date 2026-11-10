CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      TEXT UNIQUE NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'USER'
                  CHECK (role IN ('USER', 'ADMIN', 'WORKER')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    object_key    TEXT NOT NULL,
    status        TEXT NOT NULL
                  CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED')),
    error_message TEXT,
    attempt_count INT NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS processing_results (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           UUID NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    filename         TEXT NOT NULL,
    output_path      TEXT NOT NULL,
    duration_seconds NUMERIC,
    sample_rate      INT,
    channels         INT,
    audio_format     TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_jobs_status     ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_owner_id   ON jobs (owner_id);
CREATE INDEX IF NOT EXISTS idx_jobs_object_key ON jobs (object_key);

CREATE INDEX IF NOT EXISTS idx_processing_results_job_id
    ON processing_results (job_id);

CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);
CREATE INDEX IF NOT EXISTS idx_users_email    ON users (email);


ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempt_count INT NOT NULL DEFAULT 0;

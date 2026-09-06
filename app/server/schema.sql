CREATE TABLE IF NOT EXISTS installations (
    id BIGINT PRIMARY KEY,
    account_login TEXT NOT NULL,
    account_type TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS repositories (
    id BIGSERIAL PRIMARY KEY,
    github_id BIGINT UNIQUE,
    installation_id BIGINT,
    full_name TEXT NOT NULL UNIQUE,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    is_private BOOLEAN NOT NULL DEFAULT TRUE,
    default_branch TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pull_requests (
    repository_id BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    base_ref TEXT NOT NULL DEFAULT '',
    head_ref TEXT NOT NULL DEFAULT '',
    head_sha TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open',
    html_url TEXT,
    additions INTEGER NOT NULL DEFAULT 0,
    deletions INTEGER NOT NULL DEFAULT 0,
    changed_files INTEGER NOT NULL DEFAULT 0,
    files JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repository_id, number)
);
ALTER TABLE pull_requests ADD COLUMN IF NOT EXISTS body TEXT NOT NULL DEFAULT '';
ALTER TABLE pull_requests ADD COLUMN IF NOT EXISTS html_url TEXT;
ALTER TABLE pull_requests ADD COLUMN IF NOT EXISTS additions INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pull_requests ADD COLUMN IF NOT EXISTS deletions INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pull_requests ADD COLUMN IF NOT EXISTS changed_files INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pull_requests ADD COLUMN IF NOT EXISTS files JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS commits (
    repository_id BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    pr_number INTEGER NOT NULL,
    sha TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    committed_at TIMESTAMPTZ,
    PRIMARY KEY (repository_id, pr_number, sha)
);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id TEXT PRIMARY KEY,
    event TEXT NOT NULL,
    action TEXT NOT NULL,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id BIGSERIAL PRIMARY KEY,
    delivery_id TEXT UNIQUE REFERENCES deliveries(delivery_id),
    repository TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    head_sha TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    attempt INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    lease_id TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS lease_id TEXT;
CREATE INDEX IF NOT EXISTS jobs_claim_idx
    ON jobs (status, available_at, created_at);

CREATE TABLE IF NOT EXISTS runs (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL UNIQUE REFERENCES jobs(id),
    repository TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    head_sha TEXT NOT NULL,
    status TEXT NOT NULL,
    session_path TEXT NOT NULL,
    report TEXT,
    findings JSONB,
    preview_comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS runs_pr_idx
    ON runs (repository, pr_number, created_at DESC);

CREATE TABLE IF NOT EXISTS job_logs (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS job_logs_job_idx ON job_logs (job_id, created_at);

CREATE TABLE IF NOT EXISTS publish_audit (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES runs(id),
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    comment_id BIGINT,
    head_sha TEXT NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

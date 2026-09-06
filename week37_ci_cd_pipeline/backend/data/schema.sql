-- ══════════════════════════════════════════════════════════════
-- Week 37: CI/CD Pipeline Setup — Database Schema
-- ══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT NOT NULL,
    environment TEXT NOT NULL,          -- 'staging', 'production', 'development'
    version TEXT NOT NULL,              -- Semantic version, e.g. '1.0.0'
    commit_hash TEXT NOT NULL,          -- Git commit SHA
    triggered_by TEXT NOT NULL,         -- 'github-actions', 'pipeline-runner', 'admin'
    status TEXT NOT NULL DEFAULT 'success', -- 'pending', 'success', 'failed', 'rolled_back'
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_name TEXT NOT NULL,        -- 'ci.yml', 'cd.yml', 'local-pipeline'
    branch TEXT NOT NULL,               -- 'main', 'develop', 'feature/xyz'
    commit_sha TEXT NOT NULL,
    lint_status TEXT NOT NULL,          -- 'passed', 'failed', 'skipped'
    security_status TEXT NOT NULL,      -- 'passed', 'failed', 'skipped'
    test_status TEXT NOT NULL,          -- 'passed', 'failed', 'skipped'
    build_status TEXT NOT NULL,         -- 'passed', 'failed', 'skipped'
    deploy_status TEXT NOT NULL,        -- 'passed', 'failed', 'skipped'
    overall_status TEXT NOT NULL,       -- 'success', 'failed'
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_deployments_env ON deployments (environment);
CREATE INDEX IF NOT EXISTS idx_deployments_status ON deployments (status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs (overall_status);

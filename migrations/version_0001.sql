-- Personal Agent Orchestrator Database Schema
-- Version: 0001
-- PostgreSQL 16.x with pgcrypto and uuid-ossp extensions
-- Implements SKIP LOCKED patterns for safe concurrent job processing

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Agent table: stores agent credentials and scope permissions
CREATE TABLE agent (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  scopes TEXT[] NOT NULL,
  webhook_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Schedule kind enumeration for different scheduling types
CREATE TYPE schedule_kind AS ENUM ('cron','rrule','once','event','condition');

-- Task table: stores task definitions with scheduling and execution configuration
CREATE TABLE task (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  created_by UUID NOT NULL REFERENCES agent(id),
  schedule_kind schedule_kind NOT NULL,
  schedule_expr TEXT,                       -- cron string / RRULE / ISO timestamp / event topic
  timezone TEXT NOT NULL DEFAULT 'Europe/Chisinau',
  payload JSONB NOT NULL,                   -- declarative pipeline
  status TEXT NOT NULL DEFAULT 'active',    -- active|paused|canceled
  priority INT NOT NULL DEFAULT 5,          -- 1..9
  dedupe_key TEXT,
  dedupe_window_seconds INT NOT NULL DEFAULT 0,
  max_retries INT NOT NULL DEFAULT 3,
  backoff_strategy TEXT NOT NULL DEFAULT 'exponential_jitter',
  concurrency_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Task run table: tracks individual execution attempts with timing and results
CREATE TABLE task_run (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES task(id),
  lease_owner TEXT,
  leased_until TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  success BOOLEAN,
  error TEXT,
  attempt INT NOT NULL DEFAULT 1,
  output JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Due work table: implements SKIP LOCKED pattern for safe concurrent job distribution
-- Rows created by scheduler, consumed by workers using FOR UPDATE SKIP LOCKED
CREATE TABLE due_work (
  id BIGSERIAL PRIMARY KEY,
  task_id UUID NOT NULL REFERENCES task(id),
  run_at TIMESTAMPTZ NOT NULL,
  locked_until TIMESTAMPTZ,
  locked_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit log table: comprehensive operation tracking for security and debugging
CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY,
  actor_agent_id UUID REFERENCES agent(id),
  action TEXT NOT NULL,
  subject_id UUID,
  details JSONB,
  at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Worker heartbeat table: tracks worker health and activity for monitoring
CREATE TABLE worker_heartbeat (
  worker_id TEXT PRIMARY KEY,
  last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_count BIGINT NOT NULL DEFAULT 0,
  pid INTEGER,
  hostname TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Performance indexes for due_work table (critical for worker queries)
CREATE INDEX idx_due_work_run_at ON due_work (run_at);
CREATE INDEX idx_due_work_task_id ON due_work (task_id);

-- Index for worker lease queries - supports WHERE clause in worker SELECT
CREATE INDEX idx_due_work_ready ON due_work (run_at, locked_until) 
WHERE locked_until IS NULL;

-- Task table performance indexes
CREATE INDEX idx_task_created_by ON task (created_by);
CREATE INDEX idx_task_status ON task (status);
CREATE INDEX idx_task_schedule_kind ON task (schedule_kind);
CREATE INDEX idx_task_priority_created ON task (priority DESC, created_at ASC);

-- Task run table indexes for monitoring and reporting
CREATE INDEX idx_task_run_task_id ON task_run (task_id);
CREATE INDEX idx_task_run_started_at ON task_run (started_at);
CREATE INDEX idx_task_run_success ON task_run (success);
CREATE INDEX idx_task_run_task_success ON task_run (task_id, success, started_at DESC);

-- Audit log indexes for compliance and debugging
CREATE INDEX idx_audit_log_actor ON audit_log (actor_agent_id);
CREATE INDEX idx_audit_log_at ON audit_log (at);
CREATE INDEX idx_audit_log_action ON audit_log (action);
CREATE INDEX idx_audit_log_subject ON audit_log (subject_id);

-- Worker heartbeat indexes for monitoring and health checks
CREATE INDEX idx_worker_heartbeat_last_seen ON worker_heartbeat (last_seen);
CREATE INDEX idx_worker_heartbeat_hostname ON worker_heartbeat (hostname);

-- JSONB GIN indexes for flexible payload querying
CREATE INDEX idx_task_payload_gin ON task USING GIN(payload);
CREATE INDEX idx_task_run_output_gin ON task_run USING GIN(output);
CREATE INDEX idx_audit_log_details_gin ON audit_log USING GIN(details);

-- Constraint to ensure valid schedule expressions based on schedule_kind
ALTER TABLE task ADD CONSTRAINT chk_schedule_expr_required 
CHECK (
  (schedule_kind IN ('cron', 'rrule', 'once') AND schedule_expr IS NOT NULL) OR
  (schedule_kind IN ('event', 'condition') AND schedule_expr IS NOT NULL) OR
  schedule_expr IS NULL
);

-- Constraint to ensure valid priority range
ALTER TABLE task ADD CONSTRAINT chk_priority_range 
CHECK (priority >= 1 AND priority <= 9);

-- Constraint to ensure valid status values
ALTER TABLE task ADD CONSTRAINT chk_status_valid 
CHECK (status IN ('active', 'paused', 'canceled'));

-- Constraint to ensure valid max_retries
ALTER TABLE task ADD CONSTRAINT chk_max_retries_positive 
CHECK (max_retries >= 0);

-- Constraint to ensure valid dedupe_window_seconds
ALTER TABLE task ADD CONSTRAINT chk_dedupe_window_non_negative 
CHECK (dedupe_window_seconds >= 0);

-- Constraint to ensure valid attempt numbers
ALTER TABLE task_run ADD CONSTRAINT chk_attempt_positive 
CHECK (attempt >= 1);

-- Constraint to ensure leased_until is in the future when set
ALTER TABLE task_run ADD CONSTRAINT chk_leased_until_future 
CHECK (leased_until IS NULL OR leased_until > now());

-- Constraint to ensure locked_until is in the future when set
ALTER TABLE due_work ADD CONSTRAINT chk_locked_until_future 
CHECK (locked_until IS NULL OR locked_until > now());

-- Unique index for deduplication support
CREATE UNIQUE INDEX idx_task_dedupe ON task (dedupe_key, created_by) 
WHERE dedupe_key IS NOT NULL AND status = 'active';

-- Comments for schema documentation
COMMENT ON TABLE agent IS 'Agents that can create and manage tasks with scope-based permissions';
COMMENT ON TABLE task IS 'Task definitions with scheduling configuration and pipeline payloads';
COMMENT ON TABLE task_run IS 'Individual task execution attempts with lease management and results';
COMMENT ON TABLE due_work IS 'Work items ready for execution - implements SKIP LOCKED job queue pattern';
COMMENT ON TABLE audit_log IS 'Comprehensive audit trail for all system operations';
COMMENT ON TABLE worker_heartbeat IS 'Worker health monitoring and activity tracking for distributed job processing';

COMMENT ON COLUMN task.payload IS 'JSONB pipeline definition with steps, parameters, and execution configuration';
COMMENT ON COLUMN task.schedule_expr IS 'Schedule expression: cron format, RRULE string, ISO timestamp, or event topic';
COMMENT ON COLUMN task.dedupe_key IS 'Optional key for preventing duplicate tasks within dedupe_window_seconds';
COMMENT ON COLUMN task.concurrency_key IS 'Optional key for limiting concurrent execution of similar tasks';
COMMENT ON COLUMN task_run.lease_owner IS 'Worker ID that has leased this run for execution';
COMMENT ON COLUMN due_work.locked_by IS 'Worker ID that has locked this work item for processing';

-- Sample data for system agent (required for initial setup)
INSERT INTO agent (id, name, scopes) VALUES 
('00000000-0000-0000-0000-000000000001', 'system', ARRAY['admin', 'system']);

-- Grant necessary permissions for application user
-- Note: These would be executed separately in production with proper role setup
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO orchestrator_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO orchestrator_app;